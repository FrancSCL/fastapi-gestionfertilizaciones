import os
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import Response, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .queries import (
    get_programa, get_productos, get_sectores,
    get_programas_semana, get_semanas_disponibles, get_productos_multiples, get_sectores_multiples,
    get_temporadas, get_sucursales,
    listar_cuarteles_con_programas, agrupar_por_sucursal,
    get_cuartel_info, get_semanas_cuartel, get_productos_asignados, build_matriz,
    get_vigores, get_factores_all, get_estimaciones_cuartel,
    get_ur_cuartel, calcular_unidades, save_unidades_requeridas,
    save_vigor, save_factor,
    get_programas_cuartel, get_productos_disponibles,
    agregar_producto_semanas, update_dosis, eliminar_producto_cuartel,
    get_productos_lista, get_unidades_lista, save_producto, update_producto_nutrientes,
    validar_login,
)
from .pdf_service import build_pdf, build_pdf_bodega

app = FastAPI(title="LH Fertilizaciones")

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


# ══ AUTH MIDDLEWARE ═══════════════════════════════════════════════════════════

PUBLIC_PATHS = {"/login", "/logout", "/health", "/", "/docs", "/openapi.json", "/redoc"}
PUBLIC_PREFIXES = ("/static", "/papeleta", "/registro-semanal")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        is_public = (
            path in PUBLIC_PATHS
            or any(path.startswith(p) for p in PUBLIC_PREFIXES)
        )
        if is_public or request.session.get("user_id"):
            return await call_next(request)
        return RedirectResponse(url=f"/login?next={path}", status_code=303)


class ContextMiddleware(BaseHTTPMiddleware):
    """Inyecta sucursal activa + listado de sucursales en request.state para los templates."""
    async def dispatch(self, request: Request, call_next):
        suc = request.session.get("id_sucursal")
        request.state.id_sucursal_activa = int(suc) if suc else None
        tmp = request.session.get("id_temporada")
        request.state.id_temporada_activa = int(tmp) if tmp else None
        if not hasattr(app.state, "sucursales_cache") or not app.state.sucursales_cache:
            try:
                app.state.sucursales_cache = get_sucursales()
            except Exception:
                app.state.sucursales_cache = []
        request.state.sucursales_all = app.state.sucursales_cache
        if not hasattr(app.state, "temporadas_cache") or not app.state.temporadas_cache:
            try:
                app.state.temporadas_cache = get_temporadas()
            except Exception:
                app.state.temporadas_cache = []
        request.state.temporadas_all = app.state.temporadas_cache
        return await call_next(request)


# Orden de add_middleware: el primero agregado es el mas interior.
# Ejecucion entrante: Session -> Auth -> Context -> endpoint
app.add_middleware(ContextMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET_KEY", "dev-insecure-change-me"),
    session_cookie="ferti_session",
    max_age=60 * 60 * 12,  # 12h
    same_site="lax",
    https_only=False,
)


def _id_sucursal(request: Request, query_value: int | None) -> int | None:
    """Prioridad: query param explicito > sucursal en sesion > None."""
    if query_value is not None:
        return query_value
    s = request.session.get("id_sucursal")
    return int(s) if s else None


def _id_temporada(request: Request, query_value: int | None) -> int | None:
    """Prioridad: query param explicito > temporada en sesion > None."""
    if query_value is not None:
        return query_value
    t = request.session.get("id_temporada")
    return int(t) if t else None


@app.get("/health")
def health():
    return {"status": "ok"}


# ══ LOGIN / LOGOUT ════════════════════════════════════════════════════════════

@app.get("/login", response_class=HTMLResponse)
def web_login(request: Request, next: str = "/app/programas"):
    if request.session.get("user_id"):
        return RedirectResponse(url=next or "/app/programas", status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "next": next, "error": None, "usuario": ""},
    )


@app.post("/login", response_class=HTMLResponse)
def do_login(
    request: Request,
    usuario: str = Form(...),
    contrasena: str = Form(...),
    next: str = Form("/app/programas"),
):
    user = validar_login(usuario.strip(), contrasena)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "next": next,
                "error": "Usuario o contraseña incorrectos.",
                "usuario": usuario,
            },
            status_code=401,
        )
    nombre = user.get("nombre") or ""
    apellido = user.get("apellido") or ""
    request.session["user_id"] = user["id"]
    request.session["user_usuario"] = user["usuario"]
    request.session["user_name"] = (nombre + " " + apellido).strip() or user["usuario"]
    request.session["user_initials"] = ((nombre[:1] + apellido[:1]).upper() or user["usuario"][:2].upper())
    destino = next if next and next.startswith("/") else "/app/programas"
    return RedirectResponse(url=destino, status_code=303)


@app.get("/logout")
def do_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.post("/set-sucursal")
def set_sucursal(
    request: Request,
    id_sucursal: str = Form(""),
    next: str = Form("/app/programas"),
):
    if not id_sucursal or id_sucursal in ("none", "0"):
        request.session.pop("id_sucursal", None)
    else:
        try:
            request.session["id_sucursal"] = int(id_sucursal)
        except ValueError:
            pass
    destino = next if next and next.startswith("/") else "/app/programas"
    return RedirectResponse(url=destino, status_code=303)


@app.post("/set-temporada")
def set_temporada(
    request: Request,
    id_temporada: str = Form(""),
    next: str = Form("/app/programas"),
):
    if not id_temporada or id_temporada in ("none", "0"):
        request.session.pop("id_temporada", None)
    else:
        try:
            request.session["id_temporada"] = int(id_temporada)
        except ValueError:
            pass
    destino = next if next and next.startswith("/") else "/app/programas"
    return RedirectResponse(url=destino, status_code=303)


def _id_responsable(request: Request) -> int:
    return int(request.session.get("user_id") or 0)


# ══ WEB APP ═══════════════════════════════════════════════════════════════════

@app.get("/app", include_in_schema=False)
def app_root():
    return RedirectResponse(url="/app/programas")


@app.get("/app/programas", response_class=HTMLResponse)
def web_programas(request: Request, temporada: int | None = None, sucursal: int | None = None):
    temporadas = get_temporadas()
    id_suc = _id_sucursal(request, sucursal)
    id_temp = _id_temporada(request, temporada)
    cuarteles = listar_cuarteles_con_programas(id_temporada=id_temp, id_sucursal=id_suc)
    grupos = agrupar_por_sucursal(cuarteles)
    semanas = get_semanas_disponibles(id_temporada=id_temp, id_sucursal=id_suc)
    return templates.TemplateResponse(
        "programas.html",
        {
            "request": request,
            "active_page": "programas",
            "temporadas": temporadas,
            "sucursales": get_sucursales(),
            "grupos": grupos,
            "total_cuarteles": len(cuarteles),
            "filtro_temporada": id_temp,
            "filtro_sucursal": id_suc,
            "semanas": semanas,
        },
    )


@app.get("/app/matriz", response_class=HTMLResponse)
def web_matriz_root():
    return RedirectResponse(url="/app/programas")


@app.get("/app/matriz/{id_cuartel}", response_class=HTMLResponse)
def web_matriz(request: Request, id_cuartel: int, temporada: int | None = None):
    cuartel = get_cuartel_info(id_cuartel)
    if not cuartel:
        raise HTTPException(status_code=404, detail="Cuartel no encontrado")

    temporadas = get_temporadas()
    id_temp = _id_temporada(request, temporada) or (temporadas[0]["id"] if temporadas else None)

    semanas_rows = get_semanas_cuartel(id_cuartel, id_temporada=id_temp)
    ids_prog = [s["id_programa"] for s in semanas_rows]
    productos_rows = get_productos_asignados(ids_prog)
    matriz = build_matriz(semanas_rows, productos_rows)
    ur = get_ur_cuartel(id_cuartel, id_temp)

    return templates.TemplateResponse(
        "matriz.html",
        {
            "request": request,
            "active_page": "matriz",
            "cuartel": cuartel,
            "matriz": matriz,
            "ur": ur,
            "temporadas": temporadas,
            "filtro_temporada": id_temp,
        },
    )


# ── Unidades Requeridas ──────────────────────────────────────────────────────

@app.get("/app/unidades-requeridas", response_class=HTMLResponse)
def web_listado_ur(
    request: Request,
    temporada: int | None = None,
    sucursal: int | None = None,
    estado: str = "sin_ur",
):
    if estado not in ("con_ur", "sin_ur", "todos"):
        estado = "sin_ur"
    id_suc = _id_sucursal(request, sucursal)
    id_temp = _id_temporada(request, temporada)
    cuarteles = listar_cuarteles_con_programas(
        id_temporada=id_temp, id_sucursal=id_suc, filtro_ur=estado
    )
    return templates.TemplateResponse(
        "unidades_listado.html",
        {
            "request": request,
            "active_page": "unidades-req",
            "temporadas": get_temporadas(),
            "sucursales": get_sucursales(),
            "grupos": agrupar_por_sucursal(cuarteles),
            "total_cuarteles": len(cuarteles),
            "filtro_temporada": id_temp,
            "filtro_sucursal": id_suc,
            "filtro_estado": estado,
        },
    )


@app.get("/app/unidades/{id_cuartel}", response_class=HTMLResponse)
def web_unidades(request: Request, id_cuartel: int, temporada: int | None = None):
    cuartel = get_cuartel_info(id_cuartel)
    if not cuartel:
        raise HTTPException(status_code=404, detail="Cuartel no encontrado")

    temporadas = get_temporadas()
    id_temp = _id_temporada(request, temporada)
    estimaciones = get_estimaciones_cuartel(id_cuartel)

    return templates.TemplateResponse(
        "unidades.html",
        {
            "request": request,
            "active_page": "programas",
            "cuartel": cuartel,
            "temporadas": temporadas,
            "vigores": get_vigores(),
            "estimaciones": estimaciones,
            "filtro_temporada": id_temp,
        },
    )


@app.get("/app/unidades/{id_cuartel}/preview", response_class=HTMLResponse)
def preview_unidades(
    request: Request,
    id_cuartel: int,
    id_estimacion: str,
    id_vigor: int,
):
    estimaciones = get_estimaciones_cuartel(id_cuartel)
    est = next((e for e in estimaciones if str(e["id_estimacion"]) == id_estimacion), None)
    if not est:
        return HTMLResponse("")

    vigores = get_vigores()
    vigor = next((v for v in vigores if v["id"] == id_vigor), None)
    if not vigor:
        return HTMLResponse("")

    factores = get_factores_all()
    unidades = calcular_unidades(
        float(est["ton_estimadas"]),
        float(vigor["factor"]),
        est["especie"],
        factores,
    )

    return templates.TemplateResponse(
        "unidades_preview.html",
        {"request": request, "unidades": unidades, "estimacion": est, "vigor": vigor},
    )


@app.post("/app/unidades/{id_cuartel}")
def crear_unidades(
    request: Request,
    id_cuartel: int,
    id_estimacion: str = Form(...),
    id_vigor: int = Form(...),
    id_temporada: int = Form(...),
):
    estimaciones = get_estimaciones_cuartel(id_cuartel)
    est = next((e for e in estimaciones if str(e["id_estimacion"]) == id_estimacion), None)
    if not est:
        raise HTTPException(status_code=400, detail="Estimación no encontrada")

    vigores = get_vigores()
    vigor = next((v for v in vigores if v["id"] == id_vigor), None)
    if not vigor:
        raise HTTPException(status_code=400, detail="Vigor no encontrado")

    factores = get_factores_all()
    save_unidades_requeridas(
        id_cuartel=id_cuartel,
        id_temporada=id_temporada,
        id_vigor=id_vigor,
        id_responsable=_id_responsable(request),
        especie=est["especie"],
        ton_estimadas=float(est["ton_estimadas"]),
        vigor_factor=float(vigor["factor"]),
        factores=factores,
    )
    return RedirectResponse(url=f"/app/matriz/{id_cuartel}?temporada={id_temporada}", status_code=303)


# ── Edición de matriz ────────────────────────────────────────────────────────

@app.get("/app/matriz/{id_cuartel}/productos-disponibles", response_class=HTMLResponse)
def productos_disponibles_fragment(request: Request, id_cuartel: int, temporada: int | None = None):
    productos = get_productos_disponibles(id_cuartel, temporada)
    return templates.TemplateResponse(
        "fragment_productos_select.html",
        {"request": request, "productos": productos, "id_cuartel": id_cuartel, "temporada": temporada},
    )


@app.post("/app/matriz/{id_cuartel}/agregar-producto")
def agregar_producto(
    id_cuartel: int,
    id_producto: int = Form(...),
    temporada: int | None = Form(None),
):
    ids_prog = get_programas_cuartel(id_cuartel, temporada)
    agregar_producto_semanas(ids_prog, id_producto)
    url = f"/app/matriz/{id_cuartel}" + (f"?temporada={temporada}" if temporada else "")
    return RedirectResponse(url=url, status_code=303)


@app.post("/app/matriz/{id_cuartel}/eliminar-producto")
def eliminar_producto(
    id_cuartel: int,
    id_producto: int = Form(...),
    temporada: int | None = Form(None),
):
    ids_prog = get_programas_cuartel(id_cuartel, temporada)
    eliminar_producto_cuartel(ids_prog, id_producto)
    url = f"/app/matriz/{id_cuartel}" + (f"?temporada={temporada}" if temporada else "")
    return RedirectResponse(url=url, status_code=303)


@app.post("/app/matriz/{id_cuartel}/dosis", response_class=HTMLResponse)
def guardar_dosis(
    id_cuartel: int,
    id_programa: str = Form(...),
    id_producto: int = Form(...),
    dosis: float = Form(...),
):
    update_dosis(id_programa, id_producto, dosis)
    return HTMLResponse(f'<span class="celda-saved">{dosis:.0f}</span>', status_code=200)


# ── Parámetros ────────────────────────────────────────────────────────────────

@app.get("/app/parametros", response_class=HTMLResponse)
def web_parametros(request: Request):
    return templates.TemplateResponse(
        "parametros.html",
        {
            "request": request,
            "active_page": "parametros",
            "vigores": get_vigores(),
            "factores": get_factores_all(),
        },
    )


@app.post("/app/parametros/vigor")
def post_vigor(
    id: int | None = Form(None),
    vigor: str = Form(...),
    factor: float = Form(...),
):
    save_vigor(id, vigor, factor)
    return RedirectResponse(url="/app/parametros", status_code=303)


@app.post("/app/parametros/factor/{id_factor}")
def post_factor(
    id_factor: int,
    factor_uva: float = Form(0),
    factor_cereza: float = Form(0),
    factor_ciruela: float = Form(0),
    factor_nectarin: float = Form(0),
    factor_durazno: float = Form(0),
    factor_damasco: float = Form(0),
):
    save_factor(
        id_factor,
        factor_uva=factor_uva,
        factor_cereza=factor_cereza,
        factor_ciruela=factor_ciruela,
        factor_nectarin=factor_nectarin,
        factor_durazno=factor_durazno,
        factor_damasco=factor_damasco,
    )
    return RedirectResponse(url="/app/parametros", status_code=303)


@app.get("/app/parametros/productos", response_class=HTMLResponse)
def web_productos(request: Request):
    return templates.TemplateResponse(
        "productos.html",
        {
            "request": request,
            "active_page": "productos",
            "productos": get_productos_lista(),
            "unidades": get_unidades_lista(),
        },
    )


@app.post("/app/parametros/productos")
def crear_producto(
    nombre_comercial: str = Form(...),
    id_unidad: int = Form(...),
    codigo_softland: int | None = Form(None),
    eficiencia: float = Form(100),
    n: float = Form(0),
    k: float = Form(0),
    p: float = Form(0),
    mg: float = Form(0),
    b: float = Form(0),
    ca: float = Form(0),
    zn: float = Form(0),
    mn: float = Form(0),
):
    save_producto(nombre_comercial, id_unidad, codigo_softland,
                  n, k, p, mg, b, ca, zn, mn, eficiencia)
    return RedirectResponse(url="/app/parametros/productos", status_code=303)


@app.post("/app/parametros/productos/{id_producto}/nutrientes")
def editar_nutrientes(
    id_producto: str,
    eficiencia: float = Form(100),
    n: float = Form(0),
    k: float = Form(0),
    p: float = Form(0),
    mg: float = Form(0),
    b: float = Form(0),
    ca: float = Form(0),
    zn: float = Form(0),
    mn: float = Form(0),
):
    update_producto_nutrientes(id_producto, n, k, p, mg, b, ca, zn, mn, eficiencia)
    return RedirectResponse(url="/app/parametros/productos", status_code=303)


# ══ API DE PAPELETAS ══════════════════════════════════════════════════════════

@app.get("/papeleta/{id_programa}")
def generar_papeleta(id_programa: str):
    programa = get_programa(id_programa)
    if not programa:
        raise HTTPException(status_code=404, detail=f"Programa '{id_programa}' no encontrado")

    productos = get_productos(id_programa)
    if not productos:
        raise HTTPException(status_code=404, detail="El programa no tiene productos registrados")

    sectores = get_sectores(programa["id_cuartel"])
    pdf_bytes = build_pdf(programa, productos, sectores)

    filename = f"papeleta_{programa['etiqueta_semana']}_{id_programa[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/registro-semanal/{etiqueta_semana}")
def generar_papeleta_bodega(etiqueta_semana: str, pro: bool = False):
    programas = get_programas_semana(etiqueta_semana)
    if not programas:
        raise HTTPException(status_code=404, detail=f"No hay programas para la semana '{etiqueta_semana}'")

    ids_programa = [p["id"] for p in programas]
    ids_cuartel  = list({p["id_cuartel"] for p in programas})

    productos_rows = get_productos_multiples(ids_programa)
    sectores_rows  = get_sectores_multiples(ids_cuartel)

    productos_map: dict = {}
    for row in productos_rows:
        productos_map.setdefault(row["id_programa"], []).append(row)

    sectores_map: dict = {}
    for row in sectores_rows:
        sectores_map.setdefault(row["id_cuartel"], []).append(row)

    pdf_bytes = build_pdf_bodega(etiqueta_semana, programas, productos_map, sectores_map, pro=pro)

    suffix   = "_pro" if pro else ""
    filename = f"bodega_{etiqueta_semana}{suffix}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
