# Fertilizaciones — Plataforma de Gestión

Aplicación web interna de La Hornilla para planificar, calcular y realizar el seguimiento de programas de fertilización por cuartel productivo a lo largo de una temporada agrícola.

## Contenido

- [Alcance funcional](#alcance-funcional)
- [Stack técnico](#stack-técnico)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Variables de entorno](#variables-de-entorno)
- [Desarrollo local](#desarrollo-local)
- [Despliegue en Cloud Run](#despliegue-en-cloud-run)
- [Autenticación](#autenticación)
- [Base de datos](#base-de-datos)
- [Documentación adicional](#documentación-adicional)

## Alcance funcional

### Unidades Requeridas (UR)
Cálculo de las unidades de nutrientes necesarias por cuartel a partir de las toneladas estimadas, el factor de vigor y los factores específicos de la especie. El resultado queda registrado en la tabla `FACT_AREATECNICA_FERTILIZACION_UNIDADESREQUERIDAS` y se expresa en kg/ha por cada nutriente (N, K, P, Mg, B, Ca, Zn, Mn).

### Matriz de programación
Interfaz tipo planilla con productos fertilizantes en columnas y semanas de la temporada en filas. Permite editar las dosis (kg/ha) en cada celda con guardado automático vía HTMX. Recalcula en vivo los aportes globales por nutriente y los contrasta contra las UR (columna *Saldo* por nutriente: rojo si falta, naranja si sobra, verde si está equilibrado).

### Gestión de cuarteles
Listado filtrable por sucursal, temporada y estado (con UR / sin UR / todos). Soporta filtro global de sucursal persistido en sesión.

### Catálogo de productos fertilizantes
ABM de productos filtrado a `id_actividad = 5` (fertilizantes). Permite editar los porcentajes de aporte de cada nutriente y la eficiencia del producto. La interfaz usa autosave al cambiar cualquier campo.

### Generación de papeletas en PDF
Dos reportes soportados: papeleta individual por programa y papeleta agregada de bodega por semana (con variante "pro" que incluye sectores de riego). Motor de renderizado: WeasyPrint.

## Stack técnico

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.11 |
| Framework web | FastAPI 0.111 |
| Template engine | Jinja2 3.1 |
| Interactividad | HTMX 2.0 |
| Cliente DB | PyMySQL 1.1 |
| Sesión | Starlette `SessionMiddleware` + `itsdangerous` |
| PDF | WeasyPrint 68 |
| Servidor ASGI | Uvicorn 0.30 |
| Base de datos | MySQL 8 (Cloud SQL) |
| Runtime | Google Cloud Run |
| CI/CD | Cloud Build conectado al repositorio `main` |

## Estructura del proyecto

```
fertilizaciones/
├── api/
│   ├── main.py                  # Definición de endpoints y middlewares FastAPI
│   ├── queries.py               # Acceso a datos (SQL puro con PyMySQL)
│   ├── db.py                    # Gestión de la conexión a MySQL / Cloud SQL
│   ├── pdf_service.py           # Renderizado de PDFs con WeasyPrint
│   ├── templates/               # Plantillas Jinja2
│   │   ├── base.html            # Layout general con sidebar y topbar
│   │   ├── login.html
│   │   ├── programas.html       # Listado de cuarteles con programa activo
│   │   ├── matriz.html          # Matriz semana × producto
│   │   ├── unidades_listado.html
│   │   ├── unidades.html        # Formulario de cálculo de UR
│   │   ├── unidades_preview.html
│   │   ├── productos.html       # ABM de fertilizantes
│   │   ├── parametros.html      # Configuración de vigores y factores
│   │   ├── papeleta.html        # PDF papeleta individual
│   │   ├── papeleta_bodega.html # PDF agregado por semana
│   │   └── papeleta_bodega_pro.html
│   └── static/
│       ├── style.css            # Hoja de estilos única (OKLCH + sistema propio)
│       └── logolh.png
├── sql/                         # Scripts de migración y mantenimiento
├── docs/
│   └── ARCHITECTURE.md          # Documentación técnica detallada
├── Dockerfile
├── requirements.txt
├── .dockerignore
├── .gitignore
├── .env                         # No versionado; contiene credenciales locales
└── README.md
```

## Variables de entorno

La aplicación lee las siguientes variables. El comportamiento varía según el entorno:

| Variable | Local | Cloud Run | Descripción |
|---|---|---|---|
| `MYSQL_USER` | sí | sí | Usuario MySQL |
| `MYSQL_PASSWORD` | sí | sí | Contraseña MySQL |
| `MYSQL_DB` | sí | sí | Nombre de la base de datos |
| `MYSQL_HOST` | sí | no | Host MySQL (se usa solo sin socket) |
| `MYSQL_PORT` | opcional | no | Puerto MySQL (default 3306) |
| `INSTANCE_CONNECTION_NAME` | no | sí | Formato `proyecto:región:instancia` |
| `K_SERVICE` | no | automática | Inyectada por Cloud Run; el código la usa como detector de runtime |
| `SESSION_SECRET_KEY` | sí | sí | Clave para firmar cookies de sesión. En producción debe provenir de Secret Manager |

Cuando el runtime es Cloud Run (`K_SERVICE` presente) y `INSTANCE_CONNECTION_NAME` está definido, `api/db.py` conecta por Unix socket en `/cloudsql/<instance>`. En cualquier otro caso usa `host`/`port`.

Ejemplo de `.env` para desarrollo local:

```
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=fsoto
MYSQL_PASSWORD=...
MYSQL_DB=lahornilla_operaciones
SESSION_SECRET_KEY=desarrollo-cambiar-en-produccion
```

## Desarrollo local

### Requisitos previos

- Python 3.11
- Acceso a una instancia MySQL con las tablas del proyecto
- Opcionalmente, Cloud SQL Auth Proxy si se usa la base en Cloud SQL

### Instalación

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -r requirements.txt
```

### Ejecución

```bash
uvicorn api.main:app --reload --port 8080
```

La aplicación queda disponible en `http://localhost:8080`. El redirect por defecto lleva al login.

### Uso con Cloud SQL Auth Proxy

Para desarrollar contra la instancia real en GCP:

```bash
cloud-sql-proxy gestion-la-hornilla:us-central1:gestion-la-hornilla
```

Una vez levantado el proxy en `127.0.0.1:3306`, el `.env` apunta ahí y la aplicación se conecta de forma transparente.

## Despliegue en Cloud Run

### Flujo automático (recomendado)

El servicio `fastapi-gestionfertilizaciones` tiene configurada entrega continua desde el repositorio de GitHub. Cualquier push a `main` dispara un build en Cloud Build que construye la imagen, la publica en Artifact Registry y despliega una nueva revisión en Cloud Run. No se requieren comandos locales para el despliegue.

### Configuración manual inicial

Al crear el servicio por primera vez o cuando se modifica la infraestructura, los siguientes pasos se realizan desde la consola de Cloud Run:

1. **Vincular la instancia Cloud SQL**: en la pestaña *Containers* del servicio, agregar la conexión a `gestion-la-hornilla:us-central1:gestion-la-hornilla`.
2. **Variables de entorno** (pestaña *Variables & Secrets*):
   - `INSTANCE_CONNECTION_NAME = gestion-la-hornilla:us-central1:gestion-la-hornilla`
   - `MYSQL_USER = fsoto`
   - `MYSQL_PASSWORD` (recomendado referenciarla desde Secret Manager)
   - `MYSQL_DB = lahornilla_operaciones`
   - `SESSION_SECRET_KEY` (recomendado Secret Manager)
3. **Permisos**: la cuenta de servicio del Cloud Run debe tener el rol `Cloud SQL Client` sobre el proyecto.
4. Al guardar, Cloud Run crea una nueva revisión. Verificar en *Logs* que no aparecen errores de `Access denied` ni de socket.

### Despliegue manual por CLI

Solo como referencia; el flujo habitual es el automático.

```bash
gcloud run deploy fastapi-gestionfertilizaciones \
  --source . \
  --region us-central1 \
  --add-cloudsql-instances=gestion-la-hornilla:us-central1:gestion-la-hornilla \
  --set-env-vars INSTANCE_CONNECTION_NAME=gestion-la-hornilla:us-central1:gestion-la-hornilla,MYSQL_USER=fsoto,MYSQL_DB=lahornilla_operaciones \
  --set-secrets MYSQL_PASSWORD=mysql-pass:latest,SESSION_SECRET_KEY=ferti-session-key:latest
```

## Autenticación

Mecanismo basado en sesión con cookies firmadas:

- Tabla de usuarios: `z_usuarios_test` con columnas `id`, `usuario`, `nombre`, `apellido`, `contraseña` (comparación en texto plano contra la columna).
- La cookie se llama `ferti_session`, tiene duración de 12 horas y se firma con `SESSION_SECRET_KEY`.
- El middleware `AuthMiddleware` bloquea todo acceso a rutas no públicas. Las rutas públicas son: `/login`, `/logout`, `/health`, `/`, `/docs`, `/openapi.json`, `/redoc`, además de los prefijos `/static`, `/papeleta`, `/registro-semanal` (estos dos últimos generan PDFs para sistemas internos).

Al iniciar sesión, la app almacena en la sesión: `user_id`, `user_usuario`, `user_name`, `user_initials`. El filtro global de sucursal usa la misma sesión.

**Deuda de seguridad conocida**: las contraseñas están almacenadas en texto plano. Se debe migrar a hashing (`bcrypt` o `argon2`) antes de abrir la aplicación a usuarios externos.

## Base de datos

La aplicación opera contra 19 tablas más 1 vista en la base `lahornilla_operaciones` (Cloud SQL) o `lahornilla_LH_Operaciones` (datacenter legacy). Ambas comparten esquema pero difieren en algunos detalles puntuales documentados en [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Grupos principales:

- **Hechos (FACT)**: programas por cuartel, productos por programa, unidades requeridas.
- **Dimensiones (DIM)**: cuarteles (CECO), sucursales, variedades, portainjertos, temporadas, semanas, productos, nutrientes, unidades de medida, colaboradores, vigores, factores agronómicos.
- **Auxiliares**: `PIVOT_AREATECNICA_RIEGO_SECTORCUARTEL`, `DIM_AREATECNICA_RIEGO_SECTOR`, vista `VISTA_FERTILIZACIONES_ESTIMACION_BASE`.
- **Usuarios**: `z_usuarios_test`.

Detalle completo del modelo de datos, JOINs y decisiones de diseño en la documentación de arquitectura.

## Documentación adicional

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — arquitectura técnica, endpoints, modelo de datos, flujos de negocio, cálculos y gotchas conocidos.
- `sql/migrate_to_gcp.sql` — migración inicial de esquema al ambiente GCP.
- `sql/migrar_desde_dc.sql` — migración de datos del datacenter a Cloud SQL.
- `sql/migrar_temporada_3_a_9.sql` — reasignación masiva de temporada sobre los registros migrados.

## Repositorio

`https://github.com/FrancSCL/fastapi-gestionfertilizaciones`
