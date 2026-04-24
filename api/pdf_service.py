import math
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

TEMPLATES_DIR = Path(__file__).parent / "templates"
PESO_ENVASE_KG = 25.0
SECTOR_COLORS = ["sector-a", "sector-b", "sector-c", "sector-d"]

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def _fmt(val, decimals=1) -> str:
    if val is None:
        return "0"
    return f"{float(val):,.{decimals}f}"


def _sacos_label(total: float) -> str:
    n = math.ceil(total / PESO_ENVASE_KG)
    return f"{n} sacos"


def build_pdf(programa: dict, productos: list, sectores: list) -> bytes:
    sup = float(programa.get("sup_productiva") or 0)

    # ── Enriquecer productos ──────────────────────────────────────────────────
    enriched_productos = []
    for p in productos:
        p = dict(p)
        dosis = float(p.get("dosis_ha") or 0)
        total = dosis * sup

        p["dosis_fmt"]  = _fmt(dosis, 0)
        p["total_fmt"]  = _fmt(total, 0)
        p["total_raw"]  = total
        p["sacos_label"] = _sacos_label(total)
        p["un_n_fmt"]   = _fmt(p.get("unidades_n"), 2)
        p["un_k_fmt"]   = _fmt(p.get("unidades_k"), 2)
        p["un_p_fmt"]   = _fmt(p.get("unidades_p"), 2)

        pct_n = round(float(p.get("pct_n") or 0) * 100)
        pct_p = round(float(p.get("pct_p") or 0) * 100)
        pct_k = round(float(p.get("pct_k") or 0) * 100)
        p["analisis"] = f"{pct_n} – {pct_p} – {pct_k}"

        enriched_productos.append(p)

    # ── Totales globales ──────────────────────────────────────────────────────
    total_kg_global  = sum(p["total_raw"] for p in enriched_productos)
    total_sacos_global = math.ceil(total_kg_global / PESO_ENVASE_KG)

    # ── Plan por sector × producto ────────────────────────────────────────────
    plan_rows = []
    for i, sector in enumerate(sectores):
        color = SECTOR_COLORS[i % len(SECTOR_COLORS)]
        sec_sup = float(sector.get("superficie") or 0)
        for p in enriched_productos:
            dosis = float(p.get("dosis_ha") or 0)
            sec_total = dosis * sec_sup
            plan_rows.append({
                "semana_label":   programa.get("etiqueta_semana") or str(programa.get("semana_calendario", "")),
                "sector_nombre":  sector["sector_nombre"],
                "sector_idx":     i + 1,
                "cuartel_nombre": programa["cuartel_nombre"],
                "variedad":       programa.get("variedad") or "",
                "sup_fmt":        _fmt(sec_sup, 2),
                "producto":       p["nombre_comercial"],
                "dosis_fmt":      _fmt(dosis, 0),
                "total_fmt":      _fmt(sec_total, 0),
                "sacos_label":    _sacos_label(sec_total),
                "color":          color,
            })

    # ── Totales por sector ────────────────────────────────────────────────────
    total_ha_sectores = sum(float(s.get("superficie") or 0) for s in sectores)
    total_kg_sectores = sum(
        float(p.get("dosis_ha") or 0) * float(s.get("superficie") or 0)
        for s in sectores
        for p in enriched_productos
    )
    total_sacos_sectores = math.ceil(total_kg_sectores / PESO_ENVASE_KG)

    # ── Número de orden y período ─────────────────────────────────────────────
    semana_label = programa.get("etiqueta_semana") or str(programa.get("semana_calendario", ""))
    numero_orden = f"N° {semana_label}-{programa['id'][:6].upper()}"

    fi = programa.get("sem_fecha_inicio")
    ft = programa.get("sem_fecha_fin")
    periodo = ""
    if fi and ft:
        periodo = f"{fi.strftime('%d/%m/%Y')} → {ft.strftime('%d/%m/%Y')}"
    elif fi:
        periodo = fi.strftime("%d/%m/%Y")

    # ── Render ────────────────────────────────────────────────────────────────
    template = _env.get_template("papeleta.html")
    html_str = template.render(
        programa=programa,
        productos=enriched_productos,
        sectores=sectores,
        plan_rows=plan_rows,
        numero_orden=numero_orden,
        semana_label=semana_label,
        periodo=periodo,
        fecha_emision=date.today().strftime("%d/%m/%Y"),
        sup_fmt=_fmt(sup, 2),
        total_kg_fmt=_fmt(total_kg_global, 0),
        total_sacos=total_sacos_global,
        total_ha_sectores=_fmt(total_ha_sectores, 2),
        total_kg_sectores=_fmt(total_kg_sectores, 0),
        total_sacos_sectores=total_sacos_sectores,
    )

    return HTML(string=html_str, base_url=str(TEMPLATES_DIR)).write_pdf()


def _bodega_secciones(programas: list, productos_map: dict, sectores_map: dict, pro: bool) -> tuple[list, dict]:
    """
    Arma la estructura de secciones para las papeletas de bodega.
    Retorna (secciones, resumen_global).
    """
    from collections import defaultdict

    grupos: dict[str, list] = defaultdict(list)
    for prog in programas:
        grupos[prog["variedad"]].append(prog)

    resumen_global: dict[str, dict] = {}   # { prod_name: {total, sacos} }
    secciones = []

    for variedad, progs in grupos.items():

        # Productos únicos de esta variedad (orden de aparición)
        prod_set: list[str] = []
        seen: set[str] = set()
        for prog in progs:
            for p in productos_map.get(prog["id"], []):
                nm = p["nombre_comercial"]
                if nm not in seen:
                    prod_set.append(nm)
                    seen.add(nm)
                if nm not in resumen_global:
                    resumen_global[nm] = {"total": 0.0, "sacos": 0}

        rows = []
        total_var: dict[str, float] = {p: 0.0 for p in prod_set}

        for prog in progs:
            id_cuartel  = prog["id_cuartel"]
            sup_total   = float(prog.get("sup_productiva") or 0)
            sectores    = sectores_map.get(id_cuartel, [])
            prods_prog  = {
                p["nombre_comercial"]: float(p["dosis_ha"] or 0)
                for p in productos_map.get(prog["id"], [])
            }

            if not sectores:
                sectores = [{"sector_nombre": "—", "superficie": sup_total}]

            n_sec = len(sectores)
            sub_cuartel: dict[str, float] = {p: 0.0 for p in prod_set}

            for i, sec in enumerate(sectores):
                sec_sup = float(sec.get("superficie") or 0)
                cantidades = {}
                for prod_name in prod_set:
                    dosis = prods_prog.get(prod_name, 0.0)
                    total = dosis * sec_sup
                    cantidades[prod_name] = {
                        "total_fmt": _fmt(total, 1),
                        "sacos":     math.ceil(total / PESO_ENVASE_KG) if total > 0 else 0,
                    } if dosis > 0 else None
                    sub_cuartel[prod_name] += total

                rows.append({
                    "type":      "sector",
                    "cuartel":   prog["cuartel_nombre"],
                    "etapa":     prog.get("etapa") or "—",
                    "rowspan":   n_sec if i == 0 else 0,
                    "is_first":  i == 0,
                    "sector":    sec["sector_nombre"],
                    "sup_fmt":   _fmt(sec_sup, 2),
                    "cantidades": cantidades,
                })

            # acumular en variedad y global
            for prod_name, val in sub_cuartel.items():
                total_var[prod_name] += val
                resumen_global[prod_name]["total"] += val
                resumen_global[prod_name]["sacos"] += math.ceil(val / PESO_ENVASE_KG) if val > 0 else 0

            # fila subtotal por cuartel (solo versión pro)
            if pro and n_sec > 1:
                rows.append({
                    "type":    "subtotal_cuartel",
                    "cuartel": prog["cuartel_nombre"],
                    "cantidades": {
                        p: {
                            "total_fmt": _fmt(sub_cuartel[p], 1),
                            "sacos":     math.ceil(sub_cuartel[p] / PESO_ENVASE_KG) if sub_cuartel[p] > 0 else 0,
                        } if sub_cuartel[p] > 0 else None
                        for p in prod_set
                    },
                })

        # fila total variedad (solo pro)
        total_var_row = None
        if pro:
            total_var_row = {
                p: {
                    "total_fmt": _fmt(total_var[p], 1),
                    "sacos":     math.ceil(total_var[p] / PESO_ENVASE_KG) if total_var[p] > 0 else 0,
                } if total_var[p] > 0 else None
                for p in prod_set
            }

        secciones.append({
            "variedad":      variedad,
            "productos":     prod_set,
            "rows":          rows,
            "total_var_row": total_var_row,
        })

    return secciones, resumen_global


def _agg(d: dict, key: str, kg: float) -> None:
    e = d.setdefault(key, {"kg": 0.0, "sacos": 0})
    e["kg"] += kg
    e["sacos"] = math.ceil(e["kg"] / PESO_ENVASE_KG) if e["kg"] > 0 else 0


def build_pdf_campo(
    rows: list,
    orfanos: list,
    sucursal: dict,
    semana: dict,
    supervisor: str = "",
) -> bytes:
    """Papeleta semanal organizada por caseta → equipo → sector → cuartel.

    rows:     filas planas de get_papeleta_campo_rows()
    orfanos:  filas planas de get_cuarteles_huerfanos()
    sucursal: {id, sucursal}
    semana:   {etiqueta_semana, fecha_inicio, fecha_fin, temporada}
    """
    from collections import OrderedDict

    # Estructura anidada: casetas[].equipos[].sectores[].cuarteles[].productos[]
    casetas = OrderedDict()
    totales_campo: dict = {}
    productos_campo: dict = {}  # agregado para tabla cabecera del PDF
    especies_set = set()
    etapas_set = set()
    fecha_ini_min = None
    fecha_term_max = None

    for r in rows:
        kc = (r["id_caseta"], r["caseta"])
        ke = (r["id_equipo"], r["equipo"])
        ks = (r["id_sector"], r["sector"])
        kcu = (r["id_cuartel"], r["cuartel"], r["variedad"], r["etapa"] or "—")

        caseta = casetas.setdefault(kc, {
            "nombre": r["caseta"],
            "equipos": OrderedDict(),
            "total_kg": 0.0,
        })
        equipo = caseta["equipos"].setdefault(ke, {
            "nombre": r["equipo"],
            "sectores": OrderedDict(),
        })
        sector = equipo["sectores"].setdefault(ks, {
            "nombre": r["sector"],
            "cuarteles": OrderedDict(),
            "sup_total": 0.0,
            "totales": {},
        })
        cuartel = sector["cuarteles"].setdefault(kcu, {
            "nombre": r["cuartel"],
            "variedad": r["variedad"],
            "especie": r.get("especie") or "—",
            "etapa": r["etapa"] or "—",
            "sup_sector": float(r["sup_sector_cuartel"] or 0),
            "productos": [],
        })

        dosis = float(r["dosis_ha"] or 0)
        sup = float(r["sup_sector_cuartel"] or 0)
        kg = dosis * sup
        sacos = math.ceil(kg / PESO_ENVASE_KG) if kg > 0 else 0

        pct_n = round(float(r.get("pct_n") or 0) * 100)
        pct_p = round(float(r.get("pct_p") or 0) * 100)
        pct_k = round(float(r.get("pct_k") or 0) * 100)
        npk = f"{pct_n}-{pct_p}-{pct_k}"

        cuartel["productos"].append({
            "nombre": r["producto"],
            "npk": npk,
            "dosis_fmt": _fmt(dosis, 1),
            "kg_fmt": _fmt(kg, 1),
            "sacos": sacos,
            "kg": kg,
        })

        _agg(sector["totales"], r["producto"], kg)
        _agg(totales_campo, r["producto"], kg)
        caseta["total_kg"] += kg

        # Productos agregados a cabecera con NPK (primera vez por producto)
        if r["producto"] not in productos_campo:
            productos_campo[r["producto"]] = {
                "nombre": r["producto"],
                "npk": npk,
                "kg_total": 0.0,
            }
        productos_campo[r["producto"]]["kg_total"] += kg

        if r.get("especie"):
            especies_set.add(r["especie"])
        if r.get("etapa"):
            etapas_set.add(r["etapa"])
        fi = r.get("fecha_inicio")
        ft = r.get("fecha_termino")
        if fi and (fecha_ini_min is None or fi < fecha_ini_min):
            fecha_ini_min = fi
        if ft and (fecha_term_max is None or ft > fecha_term_max):
            fecha_term_max = ft

    # Sumar superficie del sector (unica por sector, no repetir por producto)
    for _, cas in casetas.items():
        for _, eq in cas["equipos"].items():
            for _, sec in eq["sectores"].items():
                sec["sup_total"] = sum(c["sup_sector"] for c in sec["cuarteles"].values())
                # Formatear totales del sector
                sec["totales_list"] = [
                    {"nombre": k, "kg_fmt": _fmt(v["kg"], 1), "sacos": v["sacos"]}
                    for k, v in sorted(sec["totales"].items())
                ]

    # Convertir OrderedDicts a listas para el template
    casetas_list = []
    for _, cas in casetas.items():
        equipos_list = []
        for _, eq in cas["equipos"].items():
            sectores_list = []
            for _, sec in eq["sectores"].items():
                cuarteles_list = list(sec["cuarteles"].values())
                for c in cuarteles_list:
                    c["sup_sector_fmt"] = _fmt(c["sup_sector"], 2)
                sectores_list.append({
                    "nombre": sec["nombre"],
                    "sup_fmt": _fmt(sec["sup_total"], 2),
                    "n_cuarteles": len(cuarteles_list),
                    "cuarteles": cuarteles_list,
                    "totales": sec["totales_list"],
                })
            equipos_list.append({
                "nombre": eq["nombre"],
                "sectores": sectores_list,
            })
        casetas_list.append({
            "nombre": cas["nombre"],
            "equipos": equipos_list,
            "total_kg_fmt": _fmt(cas["total_kg"], 1),
        })

    # Orfanos: agrupar por cuartel
    orfanos_grouped = OrderedDict()
    for r in orfanos:
        k = (r["id_cuartel"], r["cuartel"], r["variedad"], r["etapa"] or "—", float(r["sup_productiva"] or 0))
        bucket = orfanos_grouped.setdefault(k, {
            "nombre": r["cuartel"],
            "variedad": r["variedad"],
            "etapa": r["etapa"] or "—",
            "sup_fmt": _fmt(float(r["sup_productiva"] or 0), 2),
            "sup": float(r["sup_productiva"] or 0),
            "productos": [],
        })
        if r["producto"]:
            dosis = float(r["dosis_ha"] or 0)
            kg = dosis * bucket["sup"]
            bucket["productos"].append({
                "nombre": r["producto"],
                "dosis_fmt": _fmt(dosis, 1),
                "kg_fmt": _fmt(kg, 1),
                "sacos": math.ceil(kg / PESO_ENVASE_KG) if kg > 0 else 0,
            })
            _agg(totales_campo, r["producto"], kg)
    orfanos_list = list(orfanos_grouped.values())

    # Totales del campo ordenados alfabeticamente
    totales_campo_list = [
        {"nombre": k, "kg_fmt": _fmt(v["kg"], 1), "sacos": v["sacos"]}
        for k, v in sorted(totales_campo.items())
    ]
    total_kg_campo = sum(v["kg"] for v in totales_campo.values())
    total_sacos_campo = sum(v["sacos"] for v in totales_campo.values())

    # Periodo y numero de orden
    fi = semana.get("fecha_inicio") if semana else None
    ft = semana.get("fecha_fin") if semana else None
    periodo = ""
    if fi and ft:
        periodo = f"{fi.strftime('%d/%m/%Y')} – {ft.strftime('%d/%m/%Y')}"

    # Rango real segun fechas de los programas (puede diferir del rango de la semana)
    periodo_prog = ""
    if fecha_ini_min and fecha_term_max:
        periodo_prog = f"{fecha_ini_min.strftime('%d/%m/%Y')} – {fecha_term_max.strftime('%d/%m/%Y')}"

    # Numero de orden: SEM + ano + sucursal
    etiqueta = semana.get("etiqueta_semana", "") if semana else ""
    num_orden = f"{etiqueta} / {sucursal.get('sucursal', '')}" if sucursal else etiqueta

    # Productos de cabecera con sacos calculados
    productos_cabecera = []
    for p in sorted(productos_campo.values(), key=lambda x: x["nombre"]):
        kg = p["kg_total"]
        productos_cabecera.append({
            "nombre": p["nombre"],
            "npk": p["npk"],
            "kg_fmt": _fmt(kg, 1),
            "sacos": math.ceil(kg / PESO_ENVASE_KG) if kg > 0 else 0,
        })

    # Especie / etapa resumidas
    especies_txt = ", ".join(sorted(especies_set)) if especies_set else "—"
    etapas_txt = ", ".join(sorted(etapas_set)) if etapas_set else "—"

    template = _env.get_template("papeleta_campo.html")
    html_str = template.render(
        sucursal=sucursal or {"sucursal": "—"},
        semana=semana or {},
        periodo=periodo,
        periodo_prog=periodo_prog,
        num_orden=num_orden,
        supervisor=supervisor or "",
        casetas=casetas_list,
        orfanos=orfanos_list,
        productos_cabecera=productos_cabecera,
        especies_txt=especies_txt,
        etapas_txt=etapas_txt,
        totales_campo=totales_campo_list,
        total_kg_campo_fmt=_fmt(total_kg_campo, 1),
        total_sacos_campo=total_sacos_campo,
        fecha_emision=date.today().strftime("%d/%m/%Y"),
    )
    return HTML(string=html_str, base_url=str(TEMPLATES_DIR)).write_pdf()


def build_pdf_bodega(etiqueta_semana: str, programas: list, productos_map: dict, sectores_map: dict, pro: bool = False) -> bytes:
    """
    Registro semanal para bodega.
    pro=False → versión estándar (una fila por sector, rowspan por cuartel)
    pro=True  → versión extendida (+ subtotales por cuartel, total variedad, resumen global)
    """
    secciones, resumen_global = _bodega_secciones(programas, productos_map, sectores_map, pro)

    meta    = programas[0] if programas else {}
    fi      = meta.get("sem_fecha_inicio")
    ft      = meta.get("sem_fecha_fin")
    periodo = ""
    if fi and ft:
        periodo = f"{fi.strftime('%d/%m/%Y')} → {ft.strftime('%d/%m/%Y')}"
    elif fi:
        periodo = fi.strftime("%d/%m/%Y")

    from datetime import date
    tmpl_name = "papeleta_bodega_pro.html" if pro else "papeleta_bodega.html"
    template  = _env.get_template(tmpl_name)
    html_str  = template.render(
        etiqueta_semana=etiqueta_semana,
        periodo=periodo,
        fecha_emision=date.today().strftime("%d/%m/%Y"),
        secciones=secciones,
        resumen_global=resumen_global,
    )
    return HTML(string=html_str, base_url=str(TEMPLATES_DIR)).write_pdf()
