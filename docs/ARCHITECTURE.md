# Arquitectura — Fertilizaciones

Documento técnico de referencia de la aplicación. Complementa al [README](../README.md) con detalle de endpoints, modelo de datos, flujos de negocio, cálculos, middlewares y troubleshooting.

## Contenido

- [Arquitectura general](#arquitectura-general)
- [Middlewares](#middlewares)
- [Endpoints](#endpoints)
- [Modelo de datos](#modelo-de-datos)
- [Flujos de negocio](#flujos-de-negocio)
- [Cálculos](#cálculos)
- [Convenciones de UI](#convenciones-de-ui)
- [Gotchas conocidos](#gotchas-conocidos)
- [Troubleshooting](#troubleshooting)

## Arquitectura general

La aplicación sigue un patrón monolítico server-rendered con enriquecimiento progresivo vía HTMX. No existe separación backend/frontend ni API REST consumida por un cliente JavaScript; los endpoints devuelven HTML completo o fragmentos.

```
Navegador
    │
    │  HTTP + cookies
    ▼
Cloud Run (Uvicorn)
    │
    ├── SessionMiddleware   (Starlette + itsdangerous)
    ├── AuthMiddleware      (propio, redirige a /login)
    ├── ContextMiddleware   (inyecta sucursal activa)
    │
    └── FastAPI endpoints ──► queries.py ──► PyMySQL
                                                   │
                                                   │ Unix socket
                                                   ▼
                                           Cloud SQL (MySQL 8)
```

El render se realiza con `Jinja2Templates`. HTMX se usa para guardar dosis de la matriz, autoguardar nutrientes de un producto y refrescar fragmentos de selectores, sin recargar la página completa.

## Middlewares

Orden de ejecución entrante: `Session → Auth → Context → endpoint`. El archivo [api/main.py](../api/main.py) los declara en orden inverso al de ejecución (regla de Starlette).

### SessionMiddleware
Provisto por Starlette. Firma y verifica una cookie llamada `ferti_session` usando `itsdangerous`. Máximo 12 horas. Requiere la variable `SESSION_SECRET_KEY`.

### AuthMiddleware
Define dos colecciones:

- `PUBLIC_PATHS = {"/login", "/logout", "/health", "/", "/docs", "/openapi.json", "/redoc"}`
- `PUBLIC_PREFIXES = ("/static", "/papeleta", "/registro-semanal")`

Si el path de la request no está en ninguna de las dos y la sesión no tiene `user_id`, redirige a `/login?next=<path>`. El parámetro `next` permite volver al destino original tras autenticarse.

### ContextMiddleware
Poblador de datos globales para los templates. En cada request inyecta en `request.state`:

- `id_sucursal_activa`: `int | None` leído desde `request.session["id_sucursal"]`.
- `sucursales_all`: lista cacheada de sucursales visibles (se lee una sola vez en la vida del proceso y se guarda en `app.state.sucursales_cache`).

Esto permite que `base.html` renderice el selector de sucursal en la topbar sin que cada endpoint tenga que pasar la data explícitamente.

## Endpoints

### Sistema
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/` | Redirige a `/app` |
| GET | `/health` | Retorna `{"status": "ok"}` |

### Autenticación
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/login` | Formulario de inicio de sesión |
| POST | `/login` | Valida credenciales contra `z_usuarios_test` y crea la sesión |
| GET | `/logout` | Limpia la sesión y redirige a `/login` |
| POST | `/set-sucursal` | Persiste `id_sucursal` en la sesión y redirige al `next` recibido por form |

### Aplicación web
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/app` | Redirige a `/app/programas` |
| GET | `/app/programas` | Listado de cuarteles agrupados por sucursal |
| GET | `/app/matriz` | Redirige a `/app/programas` |
| GET | `/app/matriz/{id_cuartel}` | Matriz semana × producto del cuartel |
| GET | `/app/unidades-requeridas` | Listado de cuarteles filtrado por estado de UR |
| GET | `/app/unidades/{id_cuartel}` | Formulario para calcular UR del cuartel |
| GET | `/app/unidades/{id_cuartel}/preview` | Vista previa del cálculo antes de guardar |
| POST | `/app/unidades/{id_cuartel}` | Persiste la UR calculada |

### Edición de matriz (HTMX)
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/app/matriz/{id_cuartel}/productos-disponibles` | Fragmento HTML con el select de productos aún no asignados |
| POST | `/app/matriz/{id_cuartel}/agregar-producto` | Crea el registro en `PRODUCTOSPROGRAMA` para todas las semanas del cuartel |
| POST | `/app/matriz/{id_cuartel}/eliminar-producto` | Elimina el producto de todas las semanas del cuartel |
| POST | `/app/matriz/{id_cuartel}/dosis` | Actualiza `cantidad_producto` de una celda. Retorna 204 sin cuerpo |

### Parámetros y catálogos
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/app/parametros` | Vigores y factores agronómicos |
| POST | `/app/parametros/vigor` | Alta o edición de vigor |
| POST | `/app/parametros/factor/{id_factor}` | Edición de factores por especie |
| GET | `/app/parametros/productos` | Catálogo de productos fertilizantes (`id_actividad = 5`) |
| POST | `/app/parametros/productos` | Alta de producto con sus nutrientes |
| POST | `/app/parametros/productos/{id_producto}/nutrientes` | Edición de aportes y eficiencia |

### Reportes PDF
| Método | Ruta | Descripción |
|---|---|---|
| GET | `/papeleta/{id_programa}` | PDF de la papeleta individual de un programa |
| GET | `/registro-semanal/{etiqueta_semana}` | PDF agregado por semana. Acepta `?pro=true` para la versión con sectores |

Los endpoints de PDF son **públicos** (exentos de `AuthMiddleware`) para que sistemas externos puedan consumirlos directamente por URL.

## Modelo de datos

### Núcleo transaccional

**`FACT_AREATECNICA_FERTILIZACION_PROGRAMA`** — cabecera semanal del programa de un cuartel.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | varchar(45) | PK, UUID o id compuesto |
| `id_responsable` | int | FK a `DIM_GENERAL_COLABORADOR` |
| `id_temporada` | int | FK a `DIM_GENERAL_TEMPORADA` |
| `id_cuartel` | int | FK a `DIM_GENERAL_CECO` |
| `semana` | varchar(20) | FK a `DIM_GENERAL_SEMANASTEMPORADA.id`. Guarda el id como string |
| `fecha_inicio`, `fecha_termino` | date | Ventana operativa de la semana |
| `etapa` | varchar(20) | Valores `PRECOSECHA` o `POSTCOSECHA`. En Cloud SQL puede estar tipado como `int`; ver [gotchas](#gotchas-conocidos) |
| `hora_registro` | datetime | Auditoría |

**`FACT_AREATECNICA_FERTILIZACION_PRODUCTOSPROGRAMA`** — producto asignado a una semana específica.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | varchar(45) | PK |
| `id_fertilizacion` | varchar(45) | FK a `PROGRAMA.id` |
| `id_producto` | varchar(25) | FK a `DIM_AREATECNICA_FITO_PRODUCTO.id` |
| `cantidad_producto` | float | Dosis en kg/ha (o la unidad del producto) |
| `unidades_n`...`unidades_mn` | float | Cache precomputado del aporte en kg/ha por nutriente |

**`FACT_AREATECNICA_FERTILIZACION_UNIDADESREQUERIDAS`** — UR calculadas por cuartel.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | varchar(45) | PK, UUID |
| `id_cuartel`, `id_temporada`, `id_vigor`, `id_responsable` | int | Claves |
| `factor_agronomico` | float | Factor específico aplicado |
| `unidades_N`...`unidades_Mn` | float | kg/ha requeridos por nutriente |
| `hora_registro` | datetime | La app lee la UR más reciente por cuartel/temporada |

### Catálogo de productos

**`DIM_AREATECNICA_FITO_PRODUCTO`** — productos. La aplicación filtra siempre por `id_actividad = 5` (fertilizantes).

| Columna | Tipo | Notas |
|---|---|---|
| `id` | varchar(25) | PK, UUID |
| `nombre_comercial` | varchar | Nombre para mostrar |
| `id_unidad` | int | FK a `DIM_GENERAL_UNIDAD` |
| `codigo_softland` | int | Opcional, para integración con Softland |
| `id_actividad` | int | **5 = fertilizante**. Hardcoded en `save_producto()` |

**`DIM_AREATECNICA_FITO_PRODUCTONUTRIENTES`** — una fila por producto con su composición.

| Columna | Tipo | Notas |
|---|---|---|
| `id_producto` | varchar(25) | FK única a `PRODUCTO.id` |
| `eficiencia_fertilizante` | float | **Fracción** 0.0–1.0 (100 % = 1.0) |
| `n`, `k`, `p`, `mg`, `b`, `ca`, `zn`, `mn` | float | **Fracción** del peso del producto (46 % = 0.46) |

### Dimensiones generales

| Tabla | Rol |
|---|---|
| `DIM_GENERAL_TEMPORADA` | Temporadas (ej. id=9 → "26-27") |
| `DIM_GENERAL_SEMANASTEMPORADA` | 53 semanas por temporada, con `fecha_inicio`, `fecha_fin`, `etiqueta_semana` |
| `DIM_GENERAL_SUCURSAL` | Sucursales visibles: ids 2, 3, 4, 5, 7, 8, 9, 27 (constante `SUCURSALES_VISIBLES` en `queries.py`) |
| `DIM_GENERAL_CECO` | Cuarteles. Usa `descripcion_ceco` como nombre y contiene `sup_productiva` en ha |
| `DIM_GENERAL_VARIEDAD` | Variedad del cuartel |
| `DIM_GENERAL_PORTAINJERTO` | Portainjerto del cuartel |
| `DIM_GENERAL_UNIDAD` | Unidades de medida. Columna mostrada: `nombre` (aliasada como `unidad`) |
| `DIM_GENERAL_COLABORADOR` | Usuarios del ERP para el campo `id_responsable` |

### Configuración agronómica

| Tabla | Rol |
|---|---|
| `DIM_AREATECNICA_FERTILIZACION_VIGOR` | Categorías de vigor con su factor multiplicador |
| `DIM_AREATECNICA_FERTILIZANTESFACTOR` | Factores kg/ton de nutriente por especie. Columnas: `fertilizante`, `factor_uva`, `factor_cereza`, `factor_ciruela`, `factor_nectarin`, `factor_durazno`, `factor_damasco` |
| `VISTA_FERTILIZACIONES_ESTIMACION_BASE` | Vista que entrega las estimaciones de producción (ton/ha estimadas) por cuartel, combinando `FACT_AREAPYC_PRODUCCION_ESTIMACIONADMINISTRADORES`, `DIM_GENERAL_ESPECIE` y `FACT_AREAPYC_PRODUCCION_RENDIMIENTOEMBALAJE` |

### Riego (opcional por cuartel)

| Tabla | Rol |
|---|---|
| `DIM_AREATECNICA_RIEGO_SECTOR` | Sectores de riego |
| `PIVOT_AREATECNICA_RIEGO_SECTORCUARTEL` | Relación N:N entre cuarteles y sectores |

### Usuarios

**`z_usuarios_test`**

| Columna | Tipo | Notas |
|---|---|---|
| `id` | int AI | PK |
| `usuario` | varchar(45) | Único |
| `nombre`, `apellido` | varchar(45) | — |
| `contraseña` | varchar(45) | **Texto plano**. Ver deuda de seguridad en el README |

## Flujos de negocio

### 1. Login

1. Usuario accede a una ruta protegida sin sesión.
2. `AuthMiddleware` redirige a `/login?next=<ruta>`.
3. Usuario envía usuario y contraseña por POST.
4. `validar_login()` ejecuta `SELECT id, usuario, nombre, apellido FROM z_usuarios_test WHERE usuario = %s AND contraseña = %s LIMIT 1`.
5. Si coincide, se escribe en la sesión `user_id`, `user_usuario`, `user_name`, `user_initials` y se redirige al `next`.
6. Si no, se re-renderiza `login.html` con HTTP 401.

### 2. Cálculo de Unidades Requeridas (UR)

1. Usuario abre `/app/unidades/{id_cuartel}`.
2. La vista carga las estimaciones del cuartel (de la vista `VISTA_FERTILIZACIONES_ESTIMACION_BASE`), los vigores disponibles y las temporadas.
3. Usuario selecciona una estimación, un vigor y una temporada.
4. Preview opcional en `/app/unidades/{id_cuartel}/preview` que recalcula sin persistir.
5. Al confirmar, se ejecuta `save_unidades_requeridas()`:
   - Se resuelve el nombre de columna de especie (`factor_uva`, `factor_cereza`, etc.) mediante `_col_especie()`.
   - Para cada fila de `DIM_AREATECNICA_FERTILIZANTESFACTOR`, calcula `unidades_<X> = ton_estimadas × vigor × factor_especie`, donde `vigor = vigor_factor` solo si `X == "N"`, y `vigor = 1` para el resto de los nutrientes (regla de gerencia: el vigor solo afecta al Nitrógeno).
   - Inserta una fila nueva en `FACT_AREATECNICA_FERTILIZACION_UNIDADESREQUERIDAS`.
6. Redirige a la matriz del cuartel con la temporada activa.

### 3. Edición de la matriz

1. Usuario abre `/app/matriz/{id_cuartel}`.
2. `build_matriz()` construye:
   - Una lista de semanas ordenadas por `fecha_inicio` (cada fila de la matriz).
   - Una lista de productos únicos con sus aportes por nutriente.
   - Una grilla `{(id_programa, id_producto): dosis_kg_ha}` con las dosis actuales.
   - Totales por producto y aporte global por nutriente.
3. El template renderiza la matriz con inputs `type="number"` que disparan HTMX al cambiar.
4. Cada cambio hace `POST /app/matriz/{id}/dosis` con `id_programa`, `id_producto`, `dosis`; el servidor ejecuta `update_dosis()` y responde 204.
5. En el cliente, JavaScript recalcula en vivo:
   - Los totales por producto y semana.
   - Los aportes de nutrientes por producto.
   - La tabla de balance Req/Prog/Saldo del panel lateral.

### 4. Gestión de productos fertilizantes

1. `/app/parametros/productos` muestra una lista de productos filtrados por `id_actividad = 5`.
2. Al expandir una tarjeta, aparece un formulario inline con eficiencia y los 8 nutrientes. Cada campo usa porcentaje (0–100) en la UI.
3. Al cambiar cualquier input, HTMX dispara `POST /app/parametros/productos/{id}/nutrientes` con delay de 400 ms.
4. El endpoint divide cada valor por 100 antes de delegar en `update_producto_nutrientes()` (la base guarda fracciones 0–1).
5. Un botón en la topbar abre un drawer lateral con el formulario de alta. El endpoint `POST /app/parametros/productos` crea dos filas atómicamente: una en `DIM_AREATECNICA_FITO_PRODUCTO` (con `id_actividad = 5` hardcoded) y otra en `DIM_AREATECNICA_FITO_PRODUCTONUTRIENTES`.

### 5. Generación de papeletas

- **Individual** (`/papeleta/{id_programa}`): carga el programa, sus productos y los sectores de riego del cuartel; renderiza `papeleta.html` y lo convierte a PDF con WeasyPrint.
- **Agregada por semana** (`/registro-semanal/{etiqueta_semana}`): resuelve todos los programas de esa semana, consulta productos y sectores en una sola query batch (`get_productos_multiples`, `get_sectores_multiples`), y renderiza `papeleta_bodega.html` o `papeleta_bodega_pro.html` según el flag `?pro`.

## Cálculos

### Aporte de nutrientes de un producto

```
aporte_kg_ha_nutriente = dosis_kg_ha × pct_nutriente
```

donde `pct_nutriente` está **almacenado como fracción** (urea al 46 % de N → `n = 0.46`). No se divide adicionalmente por 100 al calcular. La UI de productos invierte esta convención al mostrar: multiplica por 100 para exponer al usuario un "46", y divide por 100 antes de guardar.

### Total kg/supprod de un producto

```
total_kg_supprod = sum(dosis_semana_producto for semana in temporada) × sup_productiva_cuartel
```

Usado en la matriz para conocer la compra real en bodega.

### Unidades requeridas por nutriente

Para cada nutriente (ver `calcular_unidades` en [api/queries.py](../api/queries.py)):

```
unidades[N]    = ton_estimadas × vigor_factor × factor_especie_N
unidades[X≠N]  = ton_estimadas × 1            × factor_especie_X
```

- `ton_estimadas` proviene de la vista de estimaciones (columna `ton_estimadas`).
- `vigor_factor` se selecciona de `DIM_AREATECNICA_FERTILIZACION_VIGOR.factor` y, por regla de gerencia, **solo se aplica al cálculo de N**. El resto de los nutrientes ignora el vigor (multiplica por 1).
- `factor_especie_X` se lee de la columna correspondiente en `DIM_AREATECNICA_FERTILIZANTESFACTOR` según la especie del cuartel (uva, cereza, ciruela, nectarin, durazno, damasco).

### Saldo del balance

En el panel lateral de la matriz, cada fila muestra:

```
saldo = requerido - programado
```

Coloreado:
- `saldo > 0.05` → falta (rojo)
- `saldo < -0.05` → sobra (naranja)
- caso contrario → equilibrado (verde)

## Convenciones de UI

### Sistema de diseño

- **Paleta**: verdes La Hornilla en escala OKLCH desde `--lh-50` (muy claro) hasta `--lh-900` (casi negro). Los neutros están tintados hacia el mismo hue.
- **Tipografías**: `Anybody` para display (títulos, etiquetas de marca) y `Archivo` para cuerpo y UI. Ambas desde Google Fonts, cargadas en `base.html`.
- **Escala de espaciado**: 4 pt (`--sp-1` a `--sp-8`).
- **Radios**: 5–10 px según el componente.
- **Transiciones**: curva `--ease-out = cubic-bezier(0.16, 1, 0.3, 1)` para todos los componentes animados.

### HTMX

- `hx-indicator="#global-indicator"` está declarado en `base.html` para que todos los requests muestren la barra de carga.
- Patrón de autoguardado: en cada input se colocan `hx-post`, `hx-trigger="change"` y clases que cambian temporalmente con `hx-on::before-request` / `hx-on::after-request` para dar feedback visual de *saving / saved*.

### Layouts clave

- Todas las páginas logueadas usan `base.html` que provee sidebar, topbar, selector de sucursal global y área principal.
- Los reportes PDF usan plantillas independientes (`papeleta*.html`) sin sidebar.

## Gotchas conocidos

### Tipo de `etapa` distinto entre bases
En el datacenter legacy (`lahornilla_LH_Operaciones`), `FACT_AREATECNICA_FERTILIZACION_PROGRAMA.etapa` es `varchar(20)` con valores `'PRECOSECHA'` y `'POSTCOSECHA'`. En Cloud SQL (`lahornilla_operaciones`) la columna se creó como `int`.

El script `sql/migrar_desde_dc.sql` incluye un `ALTER TABLE` que alinea el tipo a `varchar(20)` antes de hacer los INSERTs.

### Convención de fracciones vs porcentajes
La base guarda las composiciones de nutrientes y la eficiencia como **fracciones** (0.46 = 46 %). La UI de productos recibe/muestra **porcentajes** (0–100). La conversión ocurre en los endpoints `crear_producto` y `editar_nutrientes` de [api/main.py](../api/main.py), no en JavaScript.

Error histórico: antes se guardaba "46" directamente, lo que producía aportes 100 veces mayores al real en la matriz.

### Columna inexistente `DIM_GENERAL_UNIDAD.unidad`
La query `get_unidades_lista()` alias a `nombre AS unidad` porque la columna `unidad` no existe en ninguna de las dos bases. El template usa `u.unidad`, que es en realidad el valor de `nombre`.

### Contraseña con ñ
La columna se llama literalmente `contraseña` (con eñe). Requiere backticks en queries crudas y los archivos SQL se guardan en UTF-8.

### Ids con guiones bajos mixtos en UR
`unidades_N`, `unidades_K`, etc. usan mayúsculas; `unidades_n`, `unidades_k` (en `PRODUCTOSPROGRAMA`) usan minúsculas. Son dos tablas distintas con convenciones distintas. El código respeta cada una.

### Datos divergentes entre DC y Cloud SQL
Las bases operan en paralelo pero con volúmenes distintos. Cualquier cambio estructural debe replicarse en ambas si se quiere volver al datacenter.

## Troubleshooting

### `500 Internal Server Error` tras deploy

Revisar logs en Cloud Run → buscar la traza completa. Causas frecuentes:

- `Can't connect to MySQL server on 'localhost'` → falta `INSTANCE_CONNECTION_NAME` o la vinculación Cloud SQL no está hecha en Cloud Run.
- `Access denied for user 'UserApp'@'cloudsqlproxy~...'` → la variable `MYSQL_PASSWORD` está mal copiada. Revisar caracteres especiales al final.
- `Unknown column 'X' in 'field list'` → la query referencia una columna que no existe en la base actual. Validar con `SHOW COLUMNS FROM ...`.
- `Unknown database 'lahornilla_LH_Operaciones'` → el `MYSQL_DB` apunta a un nombre que existe en el datacenter pero no en Cloud SQL (esta última usa `lahornilla_operaciones`, minúsculas y sin prefijo).

### La matriz se muestra vacía (empty state) para un cuartel que sí debería tener programa

1. Confirmar que existen filas en `FACT_AREATECNICA_FERTILIZACION_PROGRAMA` para `(id_cuartel, id_temporada)`.
2. Verificar que `prog.semana` contiene ids numéricos válidos que cruzan con `DIM_GENERAL_SEMANASTEMPORADA.id`. Si el valor es tipo `"2025-40"`, el JOIN falla silenciosamente y la matriz queda sin filas.
3. Revisar que la temporada por defecto (la más reciente en `DIM_GENERAL_TEMPORADA`) sea la correcta o usar el query param `?temporada=X`.

### El dropdown "Agregar producto" no muestra nada

Verificar que existan productos con `id_actividad = 5` en `DIM_AREATECNICA_FITO_PRODUCTO`. El filtro se aplica tanto en la vista de productos como en `get_productos_disponibles()`.

### El build de Cloud Run redeploya pero los cambios no se reflejan

En Cloud Run, la revisión activa puede no ser la última si hay una edición de configuración en curso. Ir a *Revisions* y confirmar que la revisión con el tag de commit correcto tiene el 100 % del tráfico.

### Logs vía API de Cloud Logging

Si `gcloud` local está desautenticado, se puede consultar logs con un token de ADC:

```bash
TOKEN=$(gcloud auth application-default print-access-token)
curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -X POST "https://logging.googleapis.com/v2/entries:list" \
  -d '{
    "resourceNames": ["projects/gestion-la-hornilla"],
    "filter": "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"fastapi-gestionfertilizaciones\" AND severity>=ERROR",
    "orderBy": "timestamp desc",
    "pageSize": 3
  }'
```
