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
    get_temporadas, get_sucursales, get_especies, get_variedades,
    listar_cuarteles_con_programas, agrupar_por_sucursal,
    get_cuartel_info, get_semanas_cuartel, get_productos_asignados, build_matriz,
    get_vigores, get_factores_all, get_estimaciones_cuartel,
    get_ur_cuartel, calcular_unidades, save_unidades_requeridas,
    get_analisis_agronomico, save_analisis_agronomico, recalcular_ur_con_ajuste,
    tiene_ajuste_agronomico, get_cuarteles_con_ajuste_temporada,
    listar_cuarteles_con_ajustes,
    get_descuento_bodega_semana,
    save_vigor, save_factor,
    get_programas_cuartel, get_productos_disponibles,
    agregar_producto_semanas, update_dosis, eliminar_producto_cuartel,
    get_semanas_disponibles_cuartel, agregar_semana_programa, eliminar_semana_programa,
    get_productos_lista, get_unidades_lista, save_producto, update_producto_nutrientes,
    get_papeleta_campo_rows, get_cuarteles_huerfanos, get_sucursal_info, get_semana_info,
    validar_login, get_sucursales_permitidas,
)
from .pdf_service import build_pdf, build_pdf_bodega, build_pdf_campo

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
        if not hasattr(app.state, "sucursales_cache") or not app.state.sucursales_cache:
            try:
                app.state.sucursales_cache = get_sucursales()
            except Exception:
                app.state.sucursales_cache = []
        # Filtrar segun permisos: None = sin restriccion (admin)
        permitidas = request.session.get("user_sucursales")
        if permitidas is None:
            request.state.sucursales_all = app.state.sucursales_cache
        else:
            permitidas_set = set(permitidas)
            request.state.sucursales_all = [
                s for s in app.state.sucursales_cache if s["id"] in permitidas_set
            ]
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
    """Prioridad: query param explicito > sucursal en sesion > None.

    Si el usuario tiene restriccion (user no-admin con sucursales asignadas),
    valida que el id resultante este permitido; si no lo esta cae a la primera
    permitida. Si no eligio ninguna y tiene permisos, fuerza la primera.
    """
    if query_value is not None:
        candidato = query_value
    else:
        s = request.session.get("id_sucursal")
        candidato = int(s) if s else None

    permitidas = request.session.get("user_sucursales")
    if permitidas is None:
        return candidato  # admin, sin restriccion
    permitidas_set = set(permitidas)
    if not permitidas_set:
        return candidato  # user sin sucursales asignadas: no restringir (no romper)
    if candidato is not None and candidato in permitidas_set:
        return candidato
    # candidato fuera del set o sin candidato -> primera permitida
    return next(iter(sorted(permitidas_set)))


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
    user_rol = user.get("rol") or "user"
    request.session["user_rol"] = user_rol
    # Sucursales permitidas: None para admin (sin restriccion), lista para user
    if user_rol == "admin":
        request.session["user_sucursales"] = None
    else:
        request.session["user_sucursales"] = get_sucursales_permitidas(user["id"])
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
            id_int = int(id_sucursal)
            permitidas = request.session.get("user_sucursales")
            # Si tiene restriccion y no esta en el set, ignorar
            if permitidas is None or id_int in set(permitidas):
                request.session["id_sucursal"] = id_int
        except ValueError:
            pass
    destino = next if next and next.startswith("/") else "/app/programas"
    return RedirectResponse(url=destino, status_code=303)


def _id_responsable(request: Request) -> int:
    return int(request.session.get("user_id") or 0)


def _es_admin(request: Request) -> bool:
    return (request.session.get("user_rol") or "user") == "admin"


def _require_admin(request: Request) -> None:
    if not _es_admin(request):
        raise HTTPException(status_code=403, detail="Acceso restringido a administradores.")


# ══ WEB APP ═══════════════════════════════════════════════════════════════════

@app.get("/app", include_in_schema=False)
def app_root():
    return RedirectResponse(url="/app/programas")


def _to_int(v):
    """Convierte string vacio o None a None, sino a int."""
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


@app.get("/app/programas", response_class=HTMLResponse)
def web_programas(
    request: Request,
    temporada: str | None = None,
    sucursal: str | None = None,
    especie: str | None = None,
    variedad: str | None = None,
):
    # Tolerar query params vacios (?variedad= que mande el form al limpiar)
    temporada_id = _to_int(temporada)
    sucursal_id = _to_int(sucursal)
    especie_id = _to_int(especie)
    variedad_id = _to_int(variedad)

    temporadas = get_temporadas()
    id_suc = _id_sucursal(request, sucursal_id)

    # Especies y variedades acotadas a la sucursal activa
    especies_disponibles = get_especies(id_sucursal=id_suc)
    variedades_de_especie = get_variedades(id_especie=especie_id, id_sucursal=id_suc)

    # Si la variedad seleccionada no esta en el filtro actual, descartarla
    if variedad_id:
        ids_validos = {v["id"] for v in variedades_de_especie}
        if variedad_id not in ids_validos:
            variedad_id = None

    # Si la especie seleccionada no esta en las disponibles, descartarla
    if especie_id:
        ids_esp_validos = {e["id"] for e in especies_disponibles}
        if especie_id not in ids_esp_validos:
            especie_id = None
            variedad_id = None
            variedades_de_especie = get_variedades(id_sucursal=id_suc)

    cuarteles = listar_cuarteles_con_programas(
        id_temporada=temporada_id,
        id_sucursal=id_suc,
        id_especie=especie_id,
        id_variedad=variedad_id,
    )

    # Marcar cuarteles con ajuste agronomico activo para mostrar icono
    id_temp_para_ajustes = temporada_id or (temporadas[0]["id"] if temporadas else None)
    cuarteles_con_ajuste = (
        get_cuarteles_con_ajuste_temporada(id_temp_para_ajustes)
        if id_temp_para_ajustes else set()
    )
    for c in cuarteles:
        c["tiene_ajuste"] = c["id_cuartel"] in cuarteles_con_ajuste

    grupos = agrupar_por_sucursal(cuarteles)
    semanas = get_semanas_disponibles(id_temporada=temporada_id, id_sucursal=id_suc)
    return templates.TemplateResponse(
        "programas.html",
        {
            "request": request,
            "active_page": "programas",
            "temporadas": temporadas,
            "sucursales": get_sucursales(),
            "especies": especies_disponibles,
            "variedades": variedades_de_especie,
            "grupos": grupos,
            "programas": cuarteles,
            "total_cuarteles": len(cuarteles),
            "filtro_temporada": temporada_id,
            "filtro_sucursal": id_suc,
            "filtro_especie": especie_id,
            "filtro_variedad": variedad_id,
            "semanas": semanas,
        },
    )


@app.get("/app/matriz", response_class=HTMLResponse)
def web_matriz_root():
    return RedirectResponse(url="/app/programas")


@app.get("/app/matriz/{id_cuartel}", response_class=HTMLResponse)
def web_matriz(
    request: Request,
    id_cuartel: int,
    temporada: int | None = None,
    err: str | None = None,
):
    cuartel = get_cuartel_info(id_cuartel)
    if not cuartel:
        raise HTTPException(status_code=404, detail="Cuartel no encontrado")

    temporadas = get_temporadas()
    id_temp = temporada or (temporadas[0]["id"] if temporadas else None)

    semanas_rows = get_semanas_cuartel(id_cuartel, id_temporada=temporada)
    ids_prog = [s["id_programa"] for s in semanas_rows]
    productos_rows = get_productos_asignados(ids_prog)
    matriz = build_matriz(semanas_rows, productos_rows)
    ur = get_ur_cuartel(id_cuartel, id_temp)
    analisis = get_analisis_agronomico(id_cuartel, id_temp) if id_temp else None

    errores = {
        "semana_duplicada": "Esa semana ya estaba en el programa. No se duplicó.",
    }
    alert_msg = errores.get(err) if err else None

    return templates.TemplateResponse(
        "matriz.html",
        {
            "request": request,
            "active_page": "matriz",
            "cuartel": cuartel,
            "matriz": matriz,
            "ur": ur,
            "analisis": analisis,
            "temporadas": temporadas,
            "filtro_temporada": temporada,
            "alert_msg": alert_msg,
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
    cuarteles = listar_cuarteles_con_programas(
        id_temporada=temporada, id_sucursal=id_suc, filtro_ur=estado
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
            "filtro_temporada": temporada,
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
            "filtro_temporada": temporada,
        },
    )


def _aplicar_ajuste_y_regenerar_ur(
    request: Request,
    id_cuartel: int,
    id_temporada: int,
    factores: dict,
) -> None:
    """Upsert del ajuste y, si ya hay UR para ese cuartel/temporada, la regenera."""
    save_analisis_agronomico(
        id_cuartel=id_cuartel,
        id_temporada=id_temporada,
        factores=factores,
        id_responsable=_id_responsable(request),
    )
    ur = get_ur_cuartel(id_cuartel, id_temporada)
    if ur:
        estimaciones = get_estimaciones_cuartel(id_cuartel)
        if estimaciones:
            est = estimaciones[0]
            vigores = get_vigores()
            vigor = next((v for v in vigores if v["id"] == ur.get("id_vigor")), None)
            if vigor:
                save_unidades_requeridas(
                    id_cuartel=id_cuartel,
                    id_temporada=id_temporada,
                    id_vigor=ur["id_vigor"],
                    id_responsable=_id_responsable(request),
                    especie=est["especie"],
                    ton_estimadas=float(est["ton_estimadas"]),
                    vigor_factor=float(vigor["factor"]),
                    factores=get_factores_all(),
                )


@app.get("/app/ajuste-agronomico", response_class=HTMLResponse)
def web_ajuste_agronomico(
    request: Request,
    temporada: str | None = None,
    sucursal: str | None = None,
    especie: str | None = None,
    variedad: str | None = None,
    cuartel: int | None = None,
):
    temporada_id = _to_int(temporada)
    sucursal_id = _to_int(sucursal)
    especie_id = _to_int(especie)
    variedad_id = _to_int(variedad)

    temporadas = get_temporadas()
    id_temp = temporada_id or (temporadas[0]["id"] if temporadas else None)
    id_suc = _id_sucursal(request, sucursal_id)

    especies_disponibles = get_especies(id_sucursal=id_suc)
    variedades_de_especie = get_variedades(id_especie=especie_id, id_sucursal=id_suc)

    if id_temp:
        filas = listar_cuarteles_con_ajustes(
            id_temporada=id_temp,
            id_sucursal=id_suc,
            id_especie=especie_id,
            id_variedad=variedad_id,
        )
    else:
        filas = []

    return templates.TemplateResponse(
        "ajuste_agronomico.html",
        {
            "request": request,
            "active_page": "ajuste-agronomico",
            "temporadas": temporadas,
            "especies": especies_disponibles,
            "variedades": variedades_de_especie,
            "filas": filas,
            "filtro_temporada": id_temp,
            "filtro_sucursal": id_suc,
            "filtro_especie": especie_id,
            "filtro_variedad": variedad_id,
            "cuartel_destacado": cuartel,
        },
    )


@app.post("/app/ajuste-agronomico/{id_cuartel}")
def post_ajuste_agronomico_fila(
    request: Request,
    id_cuartel: int,
    temporada: int = Form(...),
    factor_n: float = Form(1.0),
    factor_p: float = Form(1.0),
    factor_k: float = Form(1.0),
    factor_mg: float = Form(1.0),
    factor_b: float = Form(1.0),
    factor_ca: float = Form(1.0),
    factor_zn: float = Form(1.0),
    factor_mn: float = Form(1.0),
):
    """Autosave por fila desde la tabla de ajuste agronomico. Responde 204."""
    _aplicar_ajuste_y_regenerar_ur(
        request,
        id_cuartel,
        temporada,
        {
            "n": factor_n, "k": factor_k, "p": factor_p, "mg": factor_mg,
            "b": factor_b, "ca": factor_ca, "zn": factor_zn, "mn": factor_mn,
        },
    )
    return HTMLResponse(status_code=204)


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
    id_producto: list[str] = Form(...),
    temporada: int | None = Form(None),
):
    # id_producto en BD es varchar(25) (UUID), no int
    ids_prog = get_programas_cuartel(id_cuartel, temporada)
    for pid in id_producto:
        agregar_producto_semanas(ids_prog, pid)
    url = f"/app/matriz/{id_cuartel}" + (f"?temporada={temporada}" if temporada else "")
    return RedirectResponse(url=url, status_code=303)


@app.post("/app/matriz/{id_cuartel}/eliminar-producto")
def eliminar_producto(
    id_cuartel: int,
    id_producto: str = Form(...),
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
    id_producto: str = Form(...),
    dosis: float = Form(...),
):
    update_dosis(id_programa, id_producto, dosis)
    return HTMLResponse(f'<span class="celda-saved">{dosis:.0f}</span>', status_code=200)


@app.get("/app/matriz/{id_cuartel}/semanas-disponibles", response_class=HTMLResponse)
def semanas_disponibles_fragment(
    request: Request,
    id_cuartel: int,
    temporada: int | None = None,
):
    temporadas = get_temporadas()
    id_temp = temporada or (temporadas[0]["id"] if temporadas else None)
    semanas = get_semanas_disponibles_cuartel(id_cuartel, id_temp) if id_temp else []
    return templates.TemplateResponse(
        "fragment_semanas_select.html",
        {
            "request": request,
            "id_cuartel": id_cuartel,
            "id_temporada": id_temp,
            "semanas": semanas,
        },
    )


@app.post("/app/matriz/{id_cuartel}/agregar-semana")
def agregar_semana(
    request: Request,
    id_cuartel: int,
    id_semana: int = Form(...),
    etapa: str = Form("PRECOSECHA"),
    temporada: int = Form(...),
):
    _, created = agregar_semana_programa(
        id_cuartel=id_cuartel,
        id_temporada=temporada,
        id_semana=id_semana,
        etapa=etapa,
        id_responsable=_id_responsable(request),
    )
    err_qs = "" if created else "&err=semana_duplicada"
    return RedirectResponse(
        url=f"/app/matriz/{id_cuartel}?temporada={temporada}{err_qs}",
        status_code=303,
    )


@app.post("/app/matriz/{id_cuartel}/eliminar-semana")
def eliminar_semana(
    id_cuartel: int,
    id_programa: str = Form(...),
    temporada: int | None = Form(None),
):
    eliminar_semana_programa(id_programa)
    url = f"/app/matriz/{id_cuartel}" + (f"?temporada={temporada}" if temporada else "")
    return RedirectResponse(url=url, status_code=303)


# ── Parámetros ────────────────────────────────────────────────────────────────

@app.get("/app/parametros", response_class=HTMLResponse)
def web_parametros(request: Request):
    _require_admin(request)
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
    request: Request,
    id: int | None = Form(None),
    vigor: str = Form(...),
    factor: float = Form(...),
):
    _require_admin(request)
    save_vigor(id, vigor, factor)
    return RedirectResponse(url="/app/parametros", status_code=303)


@app.post("/app/parametros/factor/{id_factor}")
def post_factor(
    request: Request,
    id_factor: int,
    factor_uva: float = Form(0),
    factor_cereza: float = Form(0),
    factor_ciruela: float = Form(0),
    factor_nectarin: float = Form(0),
    factor_durazno: float = Form(0),
    factor_damasco: float = Form(0),
):
    _require_admin(request)
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
    _require_admin(request)
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
    request: Request,
    nombre_comercial: str = Form(...),
    id_unidad: int = Form(...),
    codigo_softland: int | None = Form(None),
    precio_usd: float = Form(0),
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
    _require_admin(request)
    # UI envia 0-100, BD guarda fracciones 0-1
    save_producto(nombre_comercial, id_unidad, codigo_softland,
                  n/100, k/100, p/100, mg/100, b/100, ca/100, zn/100, mn/100,
                  eficiencia/100, precio_usd=precio_usd)
    return RedirectResponse(url="/app/parametros/productos", status_code=303)


@app.post("/app/parametros/productos/{id_producto}/nutrientes")
def editar_nutrientes(
    request: Request,
    id_producto: str,
    eficiencia: float = Form(100),
    precio_usd: float = Form(0),
    n: float = Form(0),
    k: float = Form(0),
    p: float = Form(0),
    mg: float = Form(0),
    b: float = Form(0),
    ca: float = Form(0),
    zn: float = Form(0),
    mn: float = Form(0),
):
    _require_admin(request)
    # UI envia 0-100, BD guarda fracciones 0-1
    update_producto_nutrientes(
        id_producto,
        n/100, k/100, p/100, mg/100, b/100, ca/100, zn/100, mn/100,
        eficiencia/100,
        precio_usd=precio_usd,
    )
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


@app.get("/app/descuento-bodega", response_class=HTMLResponse)
def web_descuento_bodega(
    request: Request,
    temporada: str | None = None,
    sucursal: str | None = None,
    semana: str | None = None,
):
    temporada_id = _to_int(temporada)
    sucursal_id = _to_int(sucursal)

    temporadas = get_temporadas()
    id_temp = temporada_id or (temporadas[0]["id"] if temporadas else None)
    id_suc = _id_sucursal(request, sucursal_id)

    semanas = get_semanas_disponibles(id_temporada=id_temp, id_sucursal=id_suc)
    etiqueta_semana = semana or (semanas[0]["etiqueta_semana"] if semanas else None)

    filas = []
    resumen = []
    if etiqueta_semana:
        filas = get_descuento_bodega_semana(
            etiqueta_semana=etiqueta_semana,
            id_sucursal=id_suc,
            id_temporada=id_temp,
        )
        agg: dict = {}
        for f in filas:
            k = (f["id_producto"], f["producto"], f.get("codigo_softland"), f.get("unidad") or "")
            agg[k] = agg.get(k, 0.0) + float(f["cantidad_total"] or 0)
        resumen = [
            {
                "id_producto": k[0],
                "producto": k[1],
                "codigo_softland": k[2],
                "unidad": k[3],
                "cantidad_total": round(v, 2),
            }
            for k, v in sorted(agg.items(), key=lambda x: x[0][1])
        ]

    return templates.TemplateResponse(
        "descuento_bodega.html",
        {
            "request": request,
            "active_page": "descuento-bodega",
            "temporadas": temporadas,
            "semanas": semanas,
            "filas": filas,
            "resumen": resumen,
            "filtro_temporada": id_temp,
            "filtro_sucursal": id_suc,
            "filtro_semana": etiqueta_semana,
        },
    )


@app.get("/app/descuento-bodega/excel")
def descargar_descuento_bodega_excel(
    request: Request,
    temporada: str | None = None,
    sucursal: str | None = None,
    semana: str = "",
):
    if not semana:
        raise HTTPException(status_code=400, detail="Falta el parametro 'semana'")
    temporada_id = _to_int(temporada)
    sucursal_id = _to_int(sucursal)
    id_suc = _id_sucursal(request, sucursal_id)

    filas = get_descuento_bodega_semana(
        etiqueta_semana=semana,
        id_sucursal=id_suc,
        id_temporada=temporada_id,
    )

    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    HDR_FILL = PatternFill("solid", fgColor="2d5a1f")
    HDR_FONT = Font(bold=True, color="FFFFFF", size=10)
    ZEBRA = PatternFill("solid", fgColor="F4FAF1")
    THIN = Side(style="thin", color="C5D9BB")
    BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Detalle"

    headers = [
        "Semana", "Fecha inicio", "Fecha fin",
        "Sucursal", "Cuartel (CECO id)", "Cuartel", "Variedad",
        "Sup. ha", "Producto", "Cód. Softland", "Unidad",
        "Dosis kg/ha", "Cantidad total",
    ]
    ws1.append(headers)
    for cell in ws1[1]:
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = Alignment(horizontal="left", vertical="center")
        cell.border = BORDER

    for i, f in enumerate(filas, start=2):
        ws1.append([
            f["etiqueta_semana"],
            f["fecha_inicio"],
            f["fecha_fin"],
            f["sucursal"],
            f["id_cuartel"],
            f["cuartel"],
            f["variedad"],
            float(f["sup_productiva"] or 0),
            f["producto"],
            f["codigo_softland"] or "",
            f["unidad"],
            float(f["dosis_ha"] or 0),
            float(f["cantidad_total"] or 0),
        ])
        if i % 2 == 0:
            for cell in ws1[i]:
                cell.fill = ZEBRA
        for cell in ws1[i]:
            cell.border = BORDER

    widths = [16, 12, 12, 22, 18, 32, 22, 9, 32, 16, 8, 13, 14]
    for col_idx, w in enumerate(widths, start=1):
        ws1.column_dimensions[ws1.cell(row=1, column=col_idx).column_letter].width = w
    ws1.freeze_panes = "A2"

    # Hoja 2: resumen consolidado
    ws2 = wb.create_sheet("Resumen bodega")
    agg: dict = {}
    for f in filas:
        k = (f["producto"], f.get("codigo_softland"), f.get("unidad") or "")
        agg[k] = agg.get(k, 0.0) + float(f["cantidad_total"] or 0)

    ws2.append(["Producto", "Cód. Softland", "Unidad", "Cantidad total"])
    for cell in ws2[1]:
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = Alignment(horizontal="left", vertical="center")
        cell.border = BORDER

    for i, (k, v) in enumerate(sorted(agg.items()), start=2):
        ws2.append([k[0], k[1] or "", k[2], round(v, 2)])
        if i % 2 == 0:
            for cell in ws2[i]:
                cell.fill = ZEBRA
        for cell in ws2[i]:
            cell.border = BORDER

    widths2 = [32, 16, 10, 14]
    for col_idx, w in enumerate(widths2, start=1):
        ws2.column_dimensions[ws2.cell(row=1, column=col_idx).column_letter].width = w
    ws2.freeze_panes = "A2"

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    safe_sem = semana.replace(" ", "_").replace("/", "-")
    filename = f"descuento_bodega_{safe_sem}.xlsx"
    return Response(
        content=buf.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/papeleta-campo/{etiqueta_semana}/{id_sucursal}")
def generar_papeleta_campo(request: Request, etiqueta_semana: str, id_sucursal: int):
    sucursal = get_sucursal_info(id_sucursal)
    if not sucursal:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")

    semana = get_semana_info(etiqueta_semana)
    if not semana:
        raise HTTPException(status_code=404, detail=f"Semana '{etiqueta_semana}' no encontrada")

    rows = get_papeleta_campo_rows(etiqueta_semana, id_sucursal)
    orfanos = get_cuarteles_huerfanos(etiqueta_semana, id_sucursal)

    supervisor = request.session.get("user_name", "") if hasattr(request, "session") else ""

    pdf_bytes = build_pdf_campo(
        rows=rows,
        orfanos=orfanos,
        sucursal=sucursal,
        semana=semana,
        supervisor=supervisor,
    )

    safe_suc = sucursal["sucursal"].replace(" ", "_")
    safe_sem = etiqueta_semana.replace(" ", "_")
    filename = f"papeleta_{safe_suc}_{safe_sem}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
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
