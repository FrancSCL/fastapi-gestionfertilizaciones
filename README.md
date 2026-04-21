# FastAPI — Gestión de Fertilizaciones

Plataforma web para planificar, calcular y hacer seguimiento de programas de fertilización por cuartel productivo a lo largo de la temporada.

## Funcionalidades

- Matriz de productos × semana con edición en línea y recálculo en tiempo real.
- Cálculo automático de Unidades Requeridas (UR) por cuartel a partir de toneladas estimadas, vigor y factor de especie.
- Resumen por producto con aporte de nutrientes (N, P, K, Mg, Ca, B, Zn, Mn) en kg/ha y kg/superficie productiva.
- Gestión de cuarteles por estado: pendientes de UR, con UR creada y en programación.
- Totales automáticos en kilogramos por hectárea y por superficie productiva.
- Generación de papeletas y reportes en PDF (WeasyPrint).

## Stack

- FastAPI (Python 3.11)
- Jinja2 para renderizado server-side
- HTMX para interactividad sin SPA
- MySQL (PyMySQL)
- WeasyPrint para PDFs
- Docker / Cloud Run para despliegue

## Estructura

```
api/
  main.py          # Endpoints FastAPI
  queries.py       # Queries a MySQL
  db.py            # Conexión / pool
  templates/       # Plantillas Jinja2
  static/          # CSS y assets
sql/               # Scripts SQL
Dockerfile
requirements.txt
```

## Variables de entorno

Crear un archivo `.env` con:

```
MYSQL_HOST=...
MYSQL_PORT=3306
MYSQL_USER=...
MYSQL_PASSWORD=...
MYSQL_DB=...
```

## Desarrollo local

```bash
python -m venv .venv
source .venv/bin/activate    # o .venv\Scripts\activate en Windows
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8080
```

La app queda disponible en `http://localhost:8080`.

## Despliegue en Cloud Run

```bash
# Build y push de la imagen
gcloud builds submit --tag gcr.io/PROJECT_ID/fastapi-gestionfertilizaciones

# Deploy
gcloud run deploy fastapi-gestionfertilizaciones \
  --image gcr.io/PROJECT_ID/fastapi-gestionfertilizaciones \
  --platform managed \
  --region southamerica-west1 \
  --allow-unauthenticated \
  --set-env-vars MYSQL_HOST=...,MYSQL_USER=...,MYSQL_PASSWORD=...,MYSQL_DB=...
```

El `Dockerfile` expone el puerto `8080` y ejecuta `uvicorn` en `0.0.0.0:8080`, compatible con el contrato de Cloud Run.
