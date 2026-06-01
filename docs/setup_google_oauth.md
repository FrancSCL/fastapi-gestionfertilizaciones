# Setup Google OAuth — Fertilizaciones

## 1. Crear el cliente OAuth en Google Cloud Console

1. Entrar a [console.cloud.google.com](https://console.cloud.google.com) con la cuenta `fsoto@lahornilla.cl` (super admin de Workspace ideal).
2. Seleccionar el proyecto **gestion-la-hornilla** (el mismo donde corre Cloud Run).
3. Menú lateral → **APIs y servicios** → **Pantalla de consentimiento de OAuth**.
   - Tipo de usuario: **Interno** (Workspace La Hornilla). Esto solo permite cuentas @lahornilla.cl, ningún Gmail externo puede pasar la pantalla.
   - Nombre de la app: `Fertilizaciones La Hornilla`
   - Correo de soporte: `fsoto@lahornilla.cl`
   - Dominio autorizado: `lahornilla.cl`
   - Logo (opcional): subir el `static/logolh.png`
   - **Guardar y continuar** en cada paso (Scopes, Resumen).
4. Menú lateral → **APIs y servicios** → **Credenciales** → **+ CREAR CREDENCIALES** → **ID de cliente de OAuth**.
   - Tipo de aplicación: **Aplicación web**
   - Nombre: `Fertilizaciones Cloud Run`
   - **Orígenes de JavaScript autorizados** (no obligatorio para este flujo, pero útil):
     - `https://fastapi-gestionfertilizaciones-927498545444.us-central1.run.app`
   - **URI de redireccionamiento autorizados**:
     - `https://fastapi-gestionfertilizaciones-927498545444.us-central1.run.app/login/google/callback`
   - Crear.
5. Anotar el **CLIENT ID** y **CLIENT SECRET** que aparecen en el modal.

## 2. Cargar las credenciales en Cloud Run

En Cloud Run, editar la revisión del servicio y agregar dos variables de entorno:

```
GOOGLE_CLIENT_ID=<el client id que terminaba en .apps.googleusercontent.com>
GOOGLE_CLIENT_SECRET=<el secret>
```

Comando equivalente con gcloud:
```bash
gcloud run services update fastapi-gestionfertilizaciones \
  --region=us-central1 \
  --set-env-vars GOOGLE_CLIENT_ID=...,GOOGLE_CLIENT_SECRET=...
```

## 3. Verificar emails en la BD

La columna `z_usuarios_test.email` fue poblada con `usuario@lahornilla.cl` para los 19 usuarios actuales. Si el correo real de alguien NO coincide con ese patrón, hay que actualizarlo desde el módulo **Parámetros → Usuarios** (columna Email).

Ejemplos a verificar manualmente:
- ¿`jose.quiroga@lahornilla.cl` o `jquiroga@lahornilla.cl`?
- ¿`juan.romero@lahornilla.cl` o `jcromero@lahornilla.cl`?

Si el correo real es `nombre.apellido@lahornilla.cl`, hay que actualizarlo. El sistema **solo loguea a quien coincida exactamente con la fila de BD**; cualquier otro recibe el error "Tu correo no está registrado".

## 4. Probar el flujo

1. Hacer push de la branch `feature/google-oauth` a `main` (o merge).
2. Esperar el deploy automático en Cloud Run.
3. Abrir `https://fastapi-gestionfertilizaciones-927498545444.us-central1.run.app/login`.
4. Click en **"Iniciar sesión con Google"**.
5. Aceptar el consentimiento con una cuenta @lahornilla.cl.
6. Debería caer directo en `/app/programas`.

## 5. Rollback

Si algo falla, el backup está en branch `backup/pre-google-oauth`:
```bash
git checkout main
git reset --hard backup/pre-google-oauth
git push origin main --force-with-lease
```
