from .db import get_connection


# ── Web app: listados para filtros ───────────────────────────────────────────

def get_temporadas() -> list:
    sql = "SELECT id, temporada FROM DIM_GENERAL_TEMPORADA ORDER BY id DESC"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()


SUCURSALES_VISIBLES = (2, 3, 4, 5, 7, 8, 9, 27)


def get_sucursales() -> list:
    ph = ",".join(["%s"] * len(SUCURSALES_VISIBLES))
    sql = f"SELECT id, sucursal FROM DIM_GENERAL_SUCURSAL WHERE id IN ({ph}) ORDER BY sucursal"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, SUCURSALES_VISIBLES)
            return cur.fetchall()


def listar_cuarteles_con_programas(
    id_temporada: int | None = None,
    id_sucursal: int | None = None,
    id_especie: int | None = None,
    id_variedad: int | None = None,
    filtro_ur: str = "con_ur",  # 'con_ur', 'sin_ur', 'todos'
) -> list:
    """Lista cuarteles con programas, incluyendo flag de si tienen UR para la temporada."""
    ur_cond = "AND ur.id_temporada = %s" if id_temporada else ""
    suc_ph = ",".join(["%s"] * len(SUCURSALES_VISIBLES))
    where = [f"suc.id IN ({suc_ph})"]
    if id_temporada:
        where.append("prog.id_temporada = %s")
    if id_sucursal:
        where.append("suc.id = %s")
    if id_especie:
        where.append("var.id_especie = %s")
    if id_variedad:
        where.append("ceco.id_variedad = %s")
    where_sql = "WHERE " + " AND ".join(where)

    having_clause = {
        "con_ur": "HAVING tiene_ur = 1",
        "sin_ur": "HAVING tiene_ur = 0",
        "todos":  "",
    }.get(filtro_ur, "HAVING tiene_ur = 1")

    final_params = (
        ([id_temporada] if id_temporada else [])
        + list(SUCURSALES_VISIBLES)
        + ([id_temporada] if id_temporada else [])
        + ([id_sucursal] if id_sucursal else [])
        + ([id_especie] if id_especie else [])
        + ([id_variedad] if id_variedad else [])
    )

    sql = f"""
        SELECT
            ceco.id                     AS id_cuartel,
            ceco.descripcion_ceco       AS cuartel,
            var.id                      AS id_variedad,
            var.variedad                AS variedad,
            esp.id                      AS id_especie,
            esp.especie                 AS especie,
            port.portainjerto           AS portainjerto,
            ceco.sup_productiva         AS sup_productiva,
            suc.id                      AS id_sucursal,
            suc.sucursal                AS sucursal,
            COUNT(prog.id)              AS num_programas,
            MAX(CASE WHEN ur.id IS NOT NULL THEN 1 ELSE 0 END) AS tiene_ur
        FROM FACT_AREATECNICA_FERTILIZACION_PROGRAMA prog
        JOIN DIM_GENERAL_CECO             ceco ON ceco.id = prog.id_cuartel
        JOIN DIM_GENERAL_SUCURSAL         suc  ON suc.id  = ceco.id_sucursal
        LEFT JOIN DIM_GENERAL_VARIEDAD    var  ON var.id  = ceco.id_variedad
        LEFT JOIN DIM_GENERAL_ESPECIE     esp  ON esp.id  = var.id_especie
        LEFT JOIN DIM_GENERAL_PORTAINJERTO port ON port.id = ceco.portainjerto
        LEFT JOIN FACT_AREATECNICA_FERTILIZACION_UNIDADESREQUERIDAS ur
                  ON ur.id_cuartel = ceco.id {ur_cond}
        {where_sql}
        GROUP BY ceco.id, ceco.descripcion_ceco, var.id, var.variedad,
                 esp.id, esp.especie, port.portainjerto,
                 ceco.sup_productiva, suc.id, suc.sucursal
        {having_clause}
        ORDER BY suc.sucursal, ceco.descripcion_ceco
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, final_params)
            return cur.fetchall()


def get_especies(id_sucursal: int | None = None) -> list:
    """Solo especies con al menos un cuartel productivo (sup_productiva > 0).
    Si se pasa id_sucursal, ademas se acotan a esa sucursal."""
    where = ["c.sup_productiva > 0"]
    params: list = []
    if id_sucursal:
        where.append("c.id_sucursal = %s")
        params.append(id_sucursal)
    where_sql = " AND ".join(where)
    sql = f"""
        SELECT DISTINCT e.id, e.especie
        FROM DIM_GENERAL_ESPECIE e
        JOIN DIM_GENERAL_VARIEDAD v ON v.id_especie = e.id
        JOIN DIM_GENERAL_CECO     c ON c.id_variedad = v.id
        WHERE {where_sql}
        ORDER BY e.especie
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def get_variedades(id_especie: int | None = None,
                   id_sucursal: int | None = None) -> list:
    """Solo variedades con al menos un cuartel productivo, opcionalmente filtradas
    por especie y/o sucursal."""
    where = ["c.sup_productiva > 0"]
    params: list = []
    if id_especie:
        where.append("v.id_especie = %s")
        params.append(id_especie)
    if id_sucursal:
        where.append("c.id_sucursal = %s")
        params.append(id_sucursal)
    where_sql = " AND ".join(where)
    sql = f"""
        SELECT DISTINCT v.id, v.variedad, v.id_especie
        FROM DIM_GENERAL_VARIEDAD v
        JOIN DIM_GENERAL_CECO c ON c.id_variedad = v.id
        WHERE {where_sql}
        ORDER BY v.variedad
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def agrupar_por_sucursal(cuarteles: list) -> list:
    """Transforma lista plana de cuarteles en grupos por sucursal."""
    grupos: dict = {}
    for c in cuarteles:
        key = c["id_sucursal"]
        if key not in grupos:
            grupos[key] = {
                "id_sucursal": c["id_sucursal"],
                "sucursal": c["sucursal"],
                "cuarteles": [],
            }
        grupos[key]["cuarteles"].append(c)
    return list(grupos.values())


# ── Matriz de cuartel (semanas x productos) ──────────────────────────────────

def get_cuartel_info(id_cuartel: int) -> dict | None:
    sql = """
        SELECT
            ceco.id,
            ceco.descripcion_ceco   AS nombre,
            ceco.sup_productiva,
            suc.sucursal,
            var.variedad,
            port.portainjerto
        FROM DIM_GENERAL_CECO ceco
        JOIN DIM_GENERAL_SUCURSAL suc ON suc.id = ceco.id_sucursal
        LEFT JOIN DIM_GENERAL_VARIEDAD var ON var.id = ceco.id_variedad
        LEFT JOIN DIM_GENERAL_PORTAINJERTO port ON port.id = ceco.portainjerto
        WHERE ceco.id = %s
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_cuartel,))
            return cur.fetchone()


def get_semanas_cuartel(id_cuartel: int, id_temporada: int | None = None) -> list:
    """Todas las semanas (programas) del cuartel/temporada, sin importar productos."""
    where = ["prog.id_cuartel = %s"]
    params: list = [id_cuartel]
    if id_temporada:
        where.append("prog.id_temporada = %s")
        params.append(id_temporada)
    sql = f"""
        SELECT
            prog.id                 AS id_programa,
            prog.etapa,
            sem.id                  AS id_semana,
            sem.etiqueta_semana,
            sem.semana_calendario,
            sem.fecha_inicio        AS sem_fecha_inicio,
            sem.fecha_fin           AS sem_fecha_fin
        FROM FACT_AREATECNICA_FERTILIZACION_PROGRAMA prog
        JOIN DIM_GENERAL_SEMANASTEMPORADA sem ON sem.id = prog.semana
        WHERE {' AND '.join(where)}
        ORDER BY sem.fecha_inicio
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def get_productos_asignados(ids_programa: list) -> list:
    if not ids_programa:
        return []
    ph = ",".join(["%s"] * len(ids_programa))
    sql = f"""
        SELECT
            pp.id_fertilizacion     AS id_programa,
            prod.id                 AS id_producto,
            prod.nombre_comercial,
            uni.abreviatura         AS unidad,
            pp.cantidad_producto    AS dosis_ha,
            COALESCE(prod.precio_usd, 0) AS precio_usd,
            COALESCE(nut.n,  0)     AS n_pct,
            COALESCE(nut.k,  0)     AS k_pct,
            COALESCE(nut.p,  0)     AS p_pct,
            COALESCE(nut.mg, 0)     AS mg_pct,
            COALESCE(nut.b,  0)     AS b_pct,
            COALESCE(nut.ca, 0)     AS ca_pct,
            COALESCE(nut.zn, 0)     AS zn_pct,
            COALESCE(nut.mn, 0)     AS mn_pct
        FROM FACT_AREATECNICA_FERTILIZACION_PRODUCTOSPROGRAMA pp
        JOIN DIM_AREATECNICA_FITO_PRODUCTO prod ON prod.id = pp.id_producto
        LEFT JOIN DIM_AREATECNICA_FITO_PRODUCTONUTRIENTES nut ON nut.id_producto = prod.id
        LEFT JOIN DIM_GENERAL_UNIDAD uni ON uni.id = prod.id_unidad
        WHERE pp.id_fertilizacion IN ({ph})
        ORDER BY prod.nombre_comercial
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, ids_programa)
            return cur.fetchall()


_NUTRIENTES = ["N", "K", "P", "Mg", "B", "Ca", "Zn", "Mn"]
_NUT_COL = {"N": "n_pct", "K": "k_pct", "P": "p_pct", "Mg": "mg_pct",
            "B": "b_pct", "Ca": "ca_pct", "Zn": "zn_pct", "Mn": "mn_pct"}


def build_matriz(semanas_rows: list, productos_rows: list) -> dict:
    """Construye matriz: siempre muestra semanas, productos solo si hay."""
    # map id_programa -> semana
    semanas_por_prog = {}
    for s in semanas_rows:
        semanas_por_prog[s["id_programa"]] = {
            "id": s["id_semana"],
            "etiqueta": s["etiqueta_semana"],
            "numero": s["semana_calendario"],
            "fecha_inicio": s["sem_fecha_inicio"],
            "fecha_fin": s["sem_fecha_fin"],
            "id_programa": s["id_programa"],
            "etapa": s["etapa"],
        }

    semanas_list = sorted(semanas_por_prog.values(), key=lambda x: x["fecha_inicio"])

    # productos únicos + celdas + % nutrientes por producto
    productos: dict = {}
    celdas: dict = {}
    for r in productos_rows:
        p_id = r["id_producto"]
        if p_id not in productos:
            productos[p_id] = {
                "id": p_id,
                "nombre": r["nombre_comercial"],
                "unidad": r["unidad"],
                "precio_usd": float(r.get("precio_usd") or 0),
                "pct": {nut: float(r[_NUT_COL[nut]] or 0) for nut in _NUTRIENTES},
            }
        celdas[(r["id_programa"], p_id)] = float(r["dosis_ha"]) if r["dosis_ha"] is not None else 0.0

    productos_list = sorted(productos.values(), key=lambda x: x["nombre"])

    # filas = semanas, celdas = una por producto (0 si no asignado)
    filas = []
    for sem in semanas_list:
        fila = {"semana": sem, "celdas": []}
        total_kg = 0.0
        for prod in productos_list:
            val = celdas.get((sem["id_programa"], prod["id"]))
            fila["celdas"].append(val)
            if val:
                total_kg += val
        fila["total_kg"] = total_kg
        filas.append(fila)

    # totales kg/ha por producto
    totales_prod = []
    for prod in productos_list:
        t = sum((celdas.get((s["id_programa"], prod["id"])) or 0) for s in semanas_list)
        totales_prod.append(round(t, 2))

    # unidades por nutriente × producto (solo filas visibles con aporte > 0 en alguno)
    unidades_por_nut: dict = {}
    for nut in _NUTRIENTES:
        fila_nut = []
        any_val = False
        for prod, total_kg in zip(productos_list, totales_prod):
            pct = prod["pct"][nut]
            units = round(total_kg * pct, 2) if pct > 0 else 0.0
            fila_nut.append(units)
            if units > 0:
                any_val = True
        if any_val:
            unidades_por_nut[nut] = fila_nut

    # totales aportados globales (suma across productos)
    totales_aporte = {nut: round(sum(unidades_por_nut.get(nut, [])), 2) for nut in _NUTRIENTES}

    # costos USD por producto
    costos_prod = []
    for prod, total_kg in zip(productos_list, totales_prod):
        precio = float(prod.get("precio_usd") or 0)
        costos_prod.append(round(total_kg * precio, 2))
    costo_ha_total = round(sum(costos_prod), 2)

    return {
        "semanas": semanas_list,
        "productos": productos_list,
        "filas": filas,
        "totales_prod": totales_prod,
        "costos_prod": costos_prod,
        "costo_ha_total": costo_ha_total,
        "unidades_por_nut": unidades_por_nut,
        "totales_aporte": totales_aporte,
    }


# ── Unidades Requeridas ──────────────────────────────────────────────────────

_ESPECIE_A_COL = {
    "uva": "factor_uva",
    "cereza": "factor_cereza",
    "cerezo": "factor_cereza",
    "ciruela": "factor_ciruela",
    "nectarin": "factor_nectarin",
    "durazno": "factor_durazno",
    "damasco": "factor_damasco",
}

_FERTILIZANTE_A_COL = {
    "N":  "unidades_N",
    "K":  "unidades_K",
    "P":  "unidades_P",
    "Mg": "unidades_Mg",
    "B":  "unidades_B",
    "Ca": "unidades_Ca",
    "Zn": "unidades_Zn",
    "Mn": "unidades_Mn",
}


def _col_especie(especie: str) -> str:
    e = especie.lower().strip()
    for k, v in _ESPECIE_A_COL.items():
        if k in e:
            return v
    return "factor_uva"


def get_vigores() -> list:
    sql = "SELECT id, vigor, factor FROM DIM_AREATECNICA_FERTILIZACION_VIGOR ORDER BY factor"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()


def get_factores_all() -> list:
    sql = """SELECT id, fertilizante, factor_uva, factor_cereza, factor_ciruela,
                    factor_nectarin, factor_durazno, factor_damasco
             FROM DIM_AREATECNICA_FERTILIZANTESFACTOR ORDER BY id"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()


def get_estimaciones_cuartel(id_cuartel: int) -> list:
    sql = """
        SELECT id_estimacion, ton_estimadas, ton_ha, especie, id_especie,
               sup_productiva, hora_registro
        FROM VISTA_FERTILIZACIONES_ESTIMACION_BASE
        WHERE id_cuartel = %s
        ORDER BY hora_registro DESC
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_cuartel,))
            return cur.fetchall()


def get_ur_cuartel(id_cuartel: int, id_temporada: int | None = None) -> dict | None:
    where = ["id_cuartel = %s"]
    params: list = [id_cuartel]
    if id_temporada:
        where.append("id_temporada = %s")
        params.append(id_temporada)
    sql = f"""
        SELECT * FROM FACT_AREATECNICA_FERTILIZACION_UNIDADESREQUERIDAS
        WHERE {' AND '.join(where)}
        ORDER BY hora_registro DESC LIMIT 1
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()


def calcular_unidades(ton_estimadas: float, vigor_factor: float,
                      especie: str, factores: list,
                      ajuste_agronomico: dict | None = None) -> dict:
    """UR por nutriente. Por regla de gerencia, el vigor solo afecta al N;
    el resto de los nutrientes se calculan sin ajustar por vigor.

    Si `ajuste_agronomico` viene poblado (dict con claves N,K,P,Mg,B,Ca,Zn,Mn),
    cada UR se multiplica por su factor correspondiente (default 1.0).
    """
    col = _col_especie(especie)
    resultado = {}
    aj = ajuste_agronomico or {}
    for f in factores:
        fert = f["fertilizante"]
        factor_esp = float(f[col] or 0)
        vigor = vigor_factor if (fert or "").upper() == "N" else 1.0
        ajuste = float(aj.get(fert, aj.get((fert or "").upper(), 1.0)))
        resultado[fert] = round(ton_estimadas * vigor * factor_esp * ajuste, 2)
    return resultado


def save_unidades_requeridas(id_cuartel: int, id_temporada: int, id_vigor: int,
                              id_responsable: int, especie: str,
                              ton_estimadas: float, vigor_factor: float,
                              factores: list) -> None:
    import uuid
    from datetime import datetime
    # Si hay ajuste agronomico cargado para el cuartel/temporada, aplicarlo
    ajuste = get_analisis_agronomico(id_cuartel, id_temporada)
    aj_dict = None
    if ajuste:
        aj_dict = {nut: float(ajuste.get(f"factor_{nut.lower()}", 1.0))
                   for nut in ("N", "K", "P", "Mg", "B", "Ca", "Zn", "Mn")}
    unidades = calcular_unidades(ton_estimadas, vigor_factor, especie, factores, aj_dict)

    sql = """
        INSERT INTO FACT_AREATECNICA_FERTILIZACION_UNIDADESREQUERIDAS
            (id, id_responsable, hora_registro, id_cuartel, id_vigor, factor_agronomico,
             id_temporada, unidades_N, unidades_K, unidades_P, unidades_Mg,
             unidades_B, unidades_Ca, unidades_Zn, unidades_Mn)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    vals = (
        str(uuid.uuid4()),
        id_responsable,
        datetime.now(),
        id_cuartel,
        id_vigor,
        1.0,
        id_temporada,
        unidades.get("N", 0),
        unidades.get("K", 0),
        unidades.get("P", 0),
        unidades.get("Mg", 0),
        unidades.get("B", 0),
        unidades.get("Ca", 0),
        unidades.get("Zn", 0),
        unidades.get("Mn", 0),
    )
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, vals)
        conn.commit()


# ── Análisis agronómico (factores por cuartel/temporada/nutriente) ──────────

_FACTORES_NUT = ("n", "k", "p", "mg", "b", "ca", "zn", "mn")


def _factor_or_default(v) -> float:
    """Convierte v a float. None / '' -> 1.0 (sin ajuste). El 0 explicito se
    respeta (significa anular el nutriente). NO usar `v or 1.0` porque 0 es
    falsy en Python y se pierde la intencion del usuario."""
    if v is None or v == "":
        return 1.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 1.0


def get_analisis_agronomico(id_cuartel: int, id_temporada: int) -> dict | None:
    sql = """
        SELECT * FROM FACT_AREATECNICA_FERTILIZACION_ANALISISAGRONOMICO
        WHERE id_cuartel = %s AND id_temporada = %s
        LIMIT 1
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_cuartel, id_temporada))
            return cur.fetchone()


def tiene_ajuste_agronomico(id_cuartel: int, id_temporada: int) -> bool:
    """True si existe un registro con al menos un factor != 1.0."""
    fila = get_analisis_agronomico(id_cuartel, id_temporada)
    if not fila:
        return False
    for nut in _FACTORES_NUT:
        v = _factor_or_default(fila.get(f"factor_{nut}"))
        if abs(v - 1.0) > 0.0001:
            return True
    return False


def save_analisis_agronomico(id_cuartel: int, id_temporada: int,
                             factores: dict, id_responsable: int) -> None:
    """UPSERT del registro de ajuste agronomico para el cuartel/temporada.
    factores = {'n': 0.8, 'k': 1.0, ...} (faltantes -> 1.0)."""
    import uuid
    from datetime import datetime
    valores = {nut: _factor_or_default(factores.get(nut)) for nut in _FACTORES_NUT}

    sql_check = """
        SELECT id FROM FACT_AREATECNICA_FERTILIZACION_ANALISISAGRONOMICO
        WHERE id_cuartel = %s AND id_temporada = %s LIMIT 1
    """
    sql_update = """
        UPDATE FACT_AREATECNICA_FERTILIZACION_ANALISISAGRONOMICO
           SET factor_n=%s, factor_k=%s, factor_p=%s, factor_mg=%s,
               factor_b=%s, factor_ca=%s, factor_zn=%s, factor_mn=%s,
               id_responsable=%s, hora_registro=%s
         WHERE id = %s
    """
    sql_insert = """
        INSERT INTO FACT_AREATECNICA_FERTILIZACION_ANALISISAGRONOMICO
            (id, id_cuartel, id_temporada, id_responsable, hora_registro,
             factor_n, factor_k, factor_p, factor_mg,
             factor_b, factor_ca, factor_zn, factor_mn)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_check, (id_cuartel, id_temporada))
            existing = cur.fetchone()
            now = datetime.now()
            vals_fact = (
                valores["n"], valores["k"], valores["p"], valores["mg"],
                valores["b"], valores["ca"], valores["zn"], valores["mn"],
            )
            if existing:
                cur.execute(sql_update, (*vals_fact, id_responsable, now, existing["id"]))
            else:
                cur.execute(sql_insert, (
                    str(uuid.uuid4()), id_cuartel, id_temporada, id_responsable, now,
                    *vals_fact,
                ))
        conn.commit()


def recalcular_ur_con_ajuste(id_cuartel: int, id_temporada: int) -> bool:
    """Aplica los factores agronomicos vigentes a la UR existente del cuartel/temporada
    (multiplica los valores ya guardados). Asume que la UR actual está SIN aplicar el
    nuevo ajuste; para reaplicar conviene primero revertir el ajuste anterior."""
    ajuste = get_analisis_agronomico(id_cuartel, id_temporada)
    if not ajuste:
        return False
    ur = get_ur_cuartel(id_cuartel, id_temporada)
    if not ur:
        return False

    sql = """
        UPDATE FACT_AREATECNICA_FERTILIZACION_UNIDADESREQUERIDAS
           SET unidades_N=%s, unidades_K=%s, unidades_P=%s, unidades_Mg=%s,
               unidades_B=%s, unidades_Ca=%s, unidades_Zn=%s, unidades_Mn=%s
         WHERE id = %s
    """
    nuevos = []
    for nut, col_ur in [
        ("n", "unidades_N"), ("k", "unidades_K"), ("p", "unidades_P"),
        ("mg", "unidades_Mg"), ("b", "unidades_B"), ("ca", "unidades_Ca"),
        ("zn", "unidades_Zn"), ("mn", "unidades_Mn"),
    ]:
        valor_actual = float(ur.get(col_ur) or 0)
        factor = _factor_or_default(ajuste.get(f"factor_{nut}"))
        nuevos.append(round(valor_actual * factor, 2))
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (*nuevos, ur["id"]))
        conn.commit()
    return True


def listar_cuarteles_con_ajustes(
    id_temporada: int,
    id_sucursal: int | None = None,
    id_especie: int | None = None,
    id_variedad: int | None = None,
) -> list:
    """Lista cuarteles que tienen programa en la temporada + factores agronomicos
    (si existen, sino 1.0 default). Una fila por cuartel."""
    suc_ph = ",".join(["%s"] * len(SUCURSALES_VISIBLES))
    where = [f"suc.id IN ({suc_ph})", "prog.id_temporada = %s"]
    params: list = list(SUCURSALES_VISIBLES) + [id_temporada]
    if id_sucursal:
        where.append("suc.id = %s")
        params.append(id_sucursal)
    if id_especie:
        where.append("var.id_especie = %s")
        params.append(id_especie)
    if id_variedad:
        where.append("ceco.id_variedad = %s")
        params.append(id_variedad)
    where_sql = "WHERE " + " AND ".join(where)
    sql = f"""
        SELECT
            ceco.id                       AS id_cuartel,
            ceco.descripcion_ceco         AS cuartel,
            COALESCE(var.variedad, '—')   AS variedad,
            COALESCE(esp.especie, '—')    AS especie,
            ceco.sup_productiva           AS sup_productiva,
            suc.id                        AS id_sucursal,
            suc.sucursal                  AS sucursal,
            COALESCE(aa.factor_n,  1.0)   AS factor_n,
            COALESCE(aa.factor_p,  1.0)   AS factor_p,
            COALESCE(aa.factor_k,  1.0)   AS factor_k,
            COALESCE(aa.factor_mg, 1.0)   AS factor_mg,
            COALESCE(aa.factor_b,  1.0)   AS factor_b,
            COALESCE(aa.factor_ca, 1.0)   AS factor_ca,
            COALESCE(aa.factor_zn, 1.0)   AS factor_zn,
            COALESCE(aa.factor_mn, 1.0)   AS factor_mn,
            aa.hora_registro              AS ajuste_hora
        FROM FACT_AREATECNICA_FERTILIZACION_PROGRAMA prog
        JOIN DIM_GENERAL_CECO             ceco ON ceco.id = prog.id_cuartel
        JOIN DIM_GENERAL_SUCURSAL         suc  ON suc.id  = ceco.id_sucursal
        LEFT JOIN DIM_GENERAL_VARIEDAD    var  ON var.id  = ceco.id_variedad
        LEFT JOIN DIM_GENERAL_ESPECIE     esp  ON esp.id  = var.id_especie
        LEFT JOIN FACT_AREATECNICA_FERTILIZACION_ANALISISAGRONOMICO aa
                  ON aa.id_cuartel = ceco.id AND aa.id_temporada = %s
        {where_sql}
        GROUP BY ceco.id, ceco.descripcion_ceco, var.variedad, esp.especie,
                 ceco.sup_productiva, suc.id, suc.sucursal,
                 aa.factor_n, aa.factor_p, aa.factor_k, aa.factor_mg,
                 aa.factor_b, aa.factor_ca, aa.factor_zn, aa.factor_mn,
                 aa.hora_registro
        ORDER BY suc.sucursal, ceco.descripcion_ceco
    """
    final_params = [id_temporada] + params
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, final_params)
            return cur.fetchall()


def get_descuento_bodega_semana(
    etiqueta_semana: str,
    id_sucursal: int | None = None,
    id_temporada: int | None = None,
) -> list:
    """Devuelve los movimientos de bodega para una semana especifica.
    Una fila por (sucursal, cuartel, producto) con cantidad total = dosis_ha * sup_productiva.
    Solo incluye productos con dosis > 0."""
    suc_ph = ",".join(["%s"] * len(SUCURSALES_VISIBLES))
    where = [f"suc.id IN ({suc_ph})", "sem.etiqueta_semana = %s", "pp.cantidad_producto > 0"]
    params: list = list(SUCURSALES_VISIBLES) + [etiqueta_semana]
    if id_sucursal:
        where.append("suc.id = %s")
        params.append(id_sucursal)
    if id_temporada:
        where.append("prog.id_temporada = %s")
        params.append(id_temporada)
    where_sql = "WHERE " + " AND ".join(where)
    sql = f"""
        SELECT
            sem.etiqueta_semana,
            sem.fecha_inicio,
            sem.fecha_fin,
            suc.id                       AS id_sucursal,
            suc.sucursal                 AS sucursal,
            ceco.id                      AS id_cuartel,
            ceco.descripcion_ceco        AS cuartel,
            COALESCE(var.variedad, '—')  AS variedad,
            ceco.sup_productiva          AS sup_productiva,
            prod.id                      AS id_producto,
            prod.nombre_comercial        AS producto,
            prod.codigo_softland         AS codigo_softland,
            COALESCE(uni.abreviatura, '') AS unidad,
            pp.cantidad_producto         AS dosis_ha,
            ROUND(pp.cantidad_producto * ceco.sup_productiva, 2) AS cantidad_total
        FROM FACT_AREATECNICA_FERTILIZACION_PROGRAMA prog
        JOIN FACT_AREATECNICA_FERTILIZACION_PRODUCTOSPROGRAMA pp ON pp.id_fertilizacion = prog.id
        JOIN DIM_AREATECNICA_FITO_PRODUCTO prod ON prod.id = pp.id_producto
        LEFT JOIN DIM_GENERAL_UNIDAD uni ON uni.id = prod.id_unidad
        JOIN DIM_GENERAL_CECO        ceco ON ceco.id = prog.id_cuartel
        JOIN DIM_GENERAL_SUCURSAL    suc  ON suc.id  = ceco.id_sucursal
        JOIN DIM_GENERAL_SEMANASTEMPORADA sem ON sem.id = prog.semana
        LEFT JOIN DIM_GENERAL_VARIEDAD var ON var.id = ceco.id_variedad
        {where_sql}
        ORDER BY suc.sucursal, ceco.descripcion_ceco, prod.nombre_comercial
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def get_adquisiciones_consolidado(
    id_temporada: int,
    id_semana_desde: int | None = None,
    id_semana_hasta: int | None = None,
    id_sucursal: int | None = None,
) -> list:
    """Resumen agregado de productos a comprar para un rango de semanas.
    Una fila por producto con la suma de (dosis_ha * sup_productiva) en el rango."""
    suc_ph = ",".join(["%s"] * len(SUCURSALES_VISIBLES))
    where = [f"suc.id IN ({suc_ph})", "pp.cantidad_producto > 0", "prog.id_temporada = %s"]
    params: list = list(SUCURSALES_VISIBLES) + [id_temporada]
    if id_semana_desde and id_semana_hasta:
        where.append(
            "sem.fecha_inicio BETWEEN "
            "(SELECT fecha_inicio FROM DIM_GENERAL_SEMANASTEMPORADA WHERE id = %s) "
            "AND "
            "(SELECT fecha_inicio FROM DIM_GENERAL_SEMANASTEMPORADA WHERE id = %s)"
        )
        params.extend([id_semana_desde, id_semana_hasta])
    elif id_semana_desde:
        where.append("sem.fecha_inicio >= (SELECT fecha_inicio FROM DIM_GENERAL_SEMANASTEMPORADA WHERE id = %s)")
        params.append(id_semana_desde)
    elif id_semana_hasta:
        where.append("sem.fecha_inicio <= (SELECT fecha_inicio FROM DIM_GENERAL_SEMANASTEMPORADA WHERE id = %s)")
        params.append(id_semana_hasta)
    if id_sucursal:
        where.append("suc.id = %s")
        params.append(id_sucursal)
    where_sql = "WHERE " + " AND ".join(where)
    sql = f"""
        SELECT
            prod.id                       AS id_producto,
            prod.nombre_comercial         AS producto,
            prod.codigo_softland          AS codigo_softland,
            COALESCE(uni.abreviatura, '') AS unidad,
            COALESCE(prod.precio_usd, 0)  AS precio_usd,
            ROUND(SUM(pp.cantidad_producto * ceco.sup_productiva), 2) AS cantidad_total
        FROM FACT_AREATECNICA_FERTILIZACION_PROGRAMA prog
        JOIN FACT_AREATECNICA_FERTILIZACION_PRODUCTOSPROGRAMA pp ON pp.id_fertilizacion = prog.id
        JOIN DIM_AREATECNICA_FITO_PRODUCTO prod ON prod.id = pp.id_producto
        LEFT JOIN DIM_GENERAL_UNIDAD uni ON uni.id = prod.id_unidad
        JOIN DIM_GENERAL_CECO        ceco ON ceco.id = prog.id_cuartel
        JOIN DIM_GENERAL_SUCURSAL    suc  ON suc.id  = ceco.id_sucursal
        JOIN DIM_GENERAL_SEMANASTEMPORADA sem ON sem.id = prog.semana
        {where_sql}
        GROUP BY prod.id, prod.nombre_comercial, prod.codigo_softland, uni.abreviatura, prod.precio_usd
        ORDER BY prod.nombre_comercial
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def get_semanas_temporada(id_temporada: int) -> list:
    """Todas las semanas de una temporada ordenadas por fecha (no solo las con programa)."""
    sql = """
        SELECT id, etiqueta_semana, semana_calendario, anio_calendario,
               fecha_inicio, fecha_fin
        FROM DIM_GENERAL_SEMANASTEMPORADA
        WHERE temporada = %s
        ORDER BY fecha_inicio
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (str(id_temporada),))
            return cur.fetchall()


def get_cuarteles_con_ajuste_temporada(id_temporada: int) -> set:
    """Set de id_cuartel que tienen al menos un factor != 1.0 para la temporada."""
    sql = """
        SELECT id_cuartel FROM FACT_AREATECNICA_FERTILIZACION_ANALISISAGRONOMICO
        WHERE id_temporada = %s
          AND (factor_n  <> 1.0 OR factor_k  <> 1.0 OR factor_p  <> 1.0
            OR factor_mg <> 1.0 OR factor_b  <> 1.0 OR factor_ca <> 1.0
            OR factor_zn <> 1.0 OR factor_mn <> 1.0)
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_temporada,))
            return {r["id_cuartel"] for r in cur.fetchall()}


# ── Parámetros: CRUD vigor y factores ────────────────────────────────────────

def save_vigor(id: int | None, vigor: str, factor: float) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            if id:
                cur.execute(
                    "UPDATE DIM_AREATECNICA_FERTILIZACION_VIGOR SET vigor=%s, factor=%s WHERE id=%s",
                    (vigor, factor, id)
                )
            else:
                cur.execute(
                    "INSERT INTO DIM_AREATECNICA_FERTILIZACION_VIGOR (vigor, factor) VALUES (%s, %s)",
                    (vigor, factor)
                )
        conn.commit()


def save_factor(id: int, **kwargs) -> None:
    cols = ["factor_uva", "factor_cereza", "factor_ciruela",
            "factor_nectarin", "factor_durazno", "factor_damasco"]
    sets = ", ".join(f"{c}=%s" for c in cols)
    vals = [float(kwargs.get(c, 0)) for c in cols]
    vals.append(id)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE DIM_AREATECNICA_FERTILIZANTESFACTOR SET {sets} WHERE id=%s", vals)
        conn.commit()


# ── Productos (CRUD) ──────────────────────────────────────────────────────────

def get_productos_lista(id_actividad: str = '5') -> list:
    """Lista productos filtrados por id_actividad (default '5' = FERTILIZANTE)."""
    sql = """
        SELECT
            p.id,
            p.nombre_comercial,
            p.codigo_softland,
            COALESCE(p.precio_usd, 0) AS precio_usd,
            p.id_actividad,
            p.id_objetivo,
            p.id_modo_accion,
            p.reingreso,
            p.id_unidad,
            u.abreviatura   AS unidad,
            pn.eficiencia_fertilizante,
            COALESCE(pn.n,  0) AS n,
            COALESCE(pn.k,  0) AS k,
            COALESCE(pn.p,  0) AS p,
            COALESCE(pn.mg, 0) AS mg,
            COALESCE(pn.b,  0) AS b,
            COALESCE(pn.ca, 0) AS ca,
            COALESCE(pn.zn, 0) AS zn,
            COALESCE(pn.mn, 0) AS mn,
            COALESCE(pn.fe, 0) AS fe
        FROM DIM_AREATECNICA_FITO_PRODUCTO p
        LEFT JOIN DIM_GENERAL_UNIDAD u ON u.id = p.id_unidad
        LEFT JOIN DIM_AREATECNICA_FITO_PRODUCTONUTRIENTES pn ON pn.id_producto = p.id
        WHERE p.id_actividad = %s
        ORDER BY p.nombre_comercial
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_actividad,))
            return cur.fetchall()


def get_unidades_lista() -> list:
    sql = "SELECT id, abreviatura, nombre AS unidad FROM DIM_GENERAL_UNIDAD ORDER BY abreviatura"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()


def update_producto_general(id_producto: str,
                            nombre_comercial: str | None = None,
                            id_unidad: int | None = None,
                            codigo_softland: int | None = None,
                            _codigo_softland_set: bool = False,
                            precio_usd: float | None = None,
                            id_objetivo: str | None = None,
                            id_modo_accion: str | None = None,
                            reingreso: int | None = None) -> None:
    """Actualiza campos generales del producto en DIM_AREATECNICA_FITO_PRODUCTO.
    Util para productos que NO tienen fila de nutrientes (ej ABONO).
    Construye un UPDATE dinamico con los campos efectivamente recibidos."""
    sets = []
    vals: list = []
    if nombre_comercial is not None and nombre_comercial.strip():
        sets.append("nombre_comercial = %s"); vals.append(nombre_comercial.strip())
    if id_unidad is not None:
        sets.append("id_unidad = %s"); vals.append(id_unidad)
    if _codigo_softland_set:
        sets.append("codigo_softland = %s"); vals.append(codigo_softland)
    if precio_usd is not None:
        sets.append("precio_usd = %s"); vals.append(precio_usd)
    if id_objetivo is not None:
        sets.append("id_objetivo = %s"); vals.append(id_objetivo or '')
    if id_modo_accion is not None:
        sets.append("id_modo_accion = %s"); vals.append(id_modo_accion or None)
    if reingreso is not None:
        sets.append("reingreso = %s"); vals.append(reingreso)
    if not sets:
        return
    vals.append(id_producto)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE DIM_AREATECNICA_FITO_PRODUCTO SET {', '.join(sets)} WHERE id = %s",
                vals,
            )
        conn.commit()


def get_ingredientes_activos() -> list:
    """Catalogo completo de ingredientes activos (DIM_PROD_IA)."""
    sql = "SELECT id, ia AS nombre FROM DIM_PROD_IA WHERE ia IS NOT NULL AND ia <> '' ORDER BY ia"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()


def crear_ingrediente_activo(nombre: str) -> dict:
    """Crea un nuevo IA en DIM_PROD_IA. Retorna {id, nombre} o {error}.
    Es case-insensitive: si ya existe uno con el mismo nombre, lo devuelve."""
    import uuid as _uuid
    nombre = (nombre or "").strip()
    if not nombre:
        return {"error": "El nombre no puede estar vacio."}
    if len(nombre) > 100:
        return {"error": "El nombre no puede tener mas de 100 caracteres."}
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, ia AS nombre FROM DIM_PROD_IA WHERE LOWER(ia) = LOWER(%s) LIMIT 1",
                (nombre,),
            )
            existente = cur.fetchone()
            if existente:
                return {"id": existente["id"], "nombre": existente["nombre"], "duplicado": True}
            nuevo_id = _uuid.uuid4().hex[:8]
            cur.execute(
                "INSERT INTO DIM_PROD_IA (id, ia) VALUES (%s, %s)",
                (nuevo_id, nombre),
            )
        conn.commit()
    return {"id": nuevo_id, "nombre": nombre}


def get_actividades_producto() -> list:
    """Catalogo completo de actividades/tipos de producto (DIM_PROD_ACTIVIDAD)."""
    sql = "SELECT id, actividad_producto AS nombre FROM DIM_PROD_ACTIVIDAD ORDER BY actividad_producto"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()


def get_ias_de_producto(id_producto: str) -> list:
    """Lista de IAs asignados a un producto: id_ia, nombre, porcentaje, base."""
    sql = """
        SELECT pi.id, pi.id_ia, ia.ia AS nombre,
               pi.porcentaje, pi.base_comparacion
        FROM PIVOT_PROD_IA pi
        LEFT JOIN DIM_PROD_IA ia ON ia.id = pi.id_ia
        WHERE pi.id_prod = %s
        ORDER BY ia.ia
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_producto,))
            return cur.fetchall()


def save_ias_de_producto(id_producto: str, ias: list) -> None:
    """Reemplaza los IAs de un producto. `ias` = lista de dicts:
        {'id_ia': str, 'porcentaje': float, 'base_comparacion': 'p/p'|'p/v'}
    Se borran los existentes y se insertan los nuevos en una sola transaccion."""
    import uuid as _uuid
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM PIVOT_PROD_IA WHERE id_prod = %s", (id_producto,))
            for item in ias:
                id_ia = (item.get("id_ia") or "").strip()
                if not id_ia:
                    continue
                pct = float(item.get("porcentaje") or 0)
                base = item.get("base_comparacion") or "p/p"
                cur.execute(
                    """INSERT INTO PIVOT_PROD_IA (id, id_prod, id_ia, porcentaje, base_comparacion)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (str(_uuid.uuid4())[:25], id_producto, id_ia, pct, base),
                )
        conn.commit()


def get_objetivos() -> list:
    sql = """
        SELECT id, objetivo_producto AS nombre
        FROM DIM_PROD_OBJETIVO
        WHERE objetivo_producto IS NOT NULL AND objetivo_producto <> ''
        ORDER BY objetivo_producto
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()


def get_modos_accion() -> list:
    sql = """
        SELECT id, moa AS nombre
        FROM DIM_PROD_MODOACCION
        WHERE moa IS NOT NULL AND moa <> ''
        ORDER BY moa
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()


def existe_producto_por_nombre(nombre_comercial: str,
                               excluir_id: str | None = None,
                               id_actividad: str = '5') -> bool:
    """True si ya existe un producto del mismo tipo (id_actividad) con el mismo
    nombre normalizado (trim + lower). `excluir_id` permite ignorar el propio
    producto al editarlo."""
    sql = """
        SELECT 1 FROM DIM_AREATECNICA_FITO_PRODUCTO
        WHERE id_actividad = %s
          AND TRIM(LOWER(nombre_comercial)) = TRIM(LOWER(%s))
          AND (%s IS NULL OR id <> %s)
        LIMIT 1
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_actividad, nombre_comercial, excluir_id, excluir_id))
            return cur.fetchone() is not None


def contar_uso_producto(id_producto: str) -> int:
    """Cantidad de filas en PRODUCTOSPROGRAMA que usan el producto."""
    sql = """
        SELECT COUNT(*) AS n FROM FACT_AREATECNICA_FERTILIZACION_PRODUCTOSPROGRAMA
        WHERE id_producto = %s
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_producto,))
            return int(cur.fetchone()["n"])


def eliminar_producto(id_producto: str) -> tuple[bool, int]:
    """Elimina un producto y sus nutrientes asociados.
    Si el producto esta en uso (filas en PRODUCTOSPROGRAMA), no borra y
    retorna (False, cantidad_en_uso). Si todo bien retorna (True, 0)."""
    en_uso = contar_uso_producto(id_producto)
    if en_uso > 0:
        return False, en_uso
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM DIM_AREATECNICA_FITO_PRODUCTONUTRIENTES WHERE id_producto = %s",
                (id_producto,),
            )
            cur.execute(
                "DELETE FROM DIM_AREATECNICA_FITO_PRODUCTO WHERE id = %s",
                (id_producto,),
            )
        conn.commit()
    return True, 0


def save_producto(nombre_comercial: str, id_unidad: int, codigo_softland: int | None,
                  n: float, k: float, p: float, mg: float,
                  b: float, ca: float, zn: float, mn: float,
                  eficiencia: float, precio_usd: float | None = None,
                  id_objetivo: str | None = None,
                  id_modo_accion: str | None = None,
                  reingreso: int | None = None,
                  fe: float = 0.0,
                  id_actividad: str = '5') -> str:
    """Crea un producto. Para id_actividad='5' (FERTILIZANTE) inserta tambien
    la fila de nutrientes. Para otros tipos (ej ABONO id='48') no crea
    nutrientes — la composicion se maneja por ingredientes activos en
    PIVOT_PROD_IA.

    Retorna el id del producto creado."""
    import uuid as _uuid
    id_prod = str(_uuid.uuid4())[:25]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO DIM_AREATECNICA_FITO_PRODUCTO
                   (id, nombre_comercial, id_unidad, codigo_softland, precio_usd,
                    id_actividad, id_objetivo, id_modo_accion, reingreso)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    id_prod, nombre_comercial, id_unidad, codigo_softland or None,
                    precio_usd or 0,
                    id_actividad,
                    id_objetivo or '',
                    id_modo_accion or None,
                    reingreso,
                ),
            )
            # Solo fertilizantes tienen fila de nutrientes
            if id_actividad == '5':
                id_nut = str(_uuid.uuid4())
                cur.execute(
                    """INSERT INTO DIM_AREATECNICA_FITO_PRODUCTONUTRIENTES
                       (id, id_producto, eficiencia_fertilizante, n, k, p, mg, b, ca, zn, mn, fe)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (id_nut, id_prod, eficiencia, n, k, p, mg, b, ca, zn, mn, fe),
                )
        conn.commit()
    return id_prod


def update_producto_nutrientes(id_producto: str, n: float, k: float, p: float,
                               mg: float, b: float, ca: float, zn: float, mn: float,
                               eficiencia: float,
                               precio_usd: float | None = None,
                               id_objetivo: str | None = None,
                               id_modo_accion: str | None = None,
                               reingreso: int | None = None,
                               fe: float = 0.0,
                               nombre_comercial: str | None = None,
                               id_unidad: int | None = None,
                               codigo_softland: int | None = None,
                               _codigo_softland_set: bool = False) -> None:
    """Actualiza nutrientes + eficiencia. Si vienen los demas params, actualiza
    los campos correspondientes en DIM_AREATECNICA_FITO_PRODUCTO en la misma
    transaccion.

    Fe se guarda como info del producto pero no participa en calculos de UR.

    `codigo_softland` puede ser None intencional (limpiar el campo). Para
    distinguirlo de "no enviado", se pasa adicionalmente _codigo_softland_set=True.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE DIM_AREATECNICA_FITO_PRODUCTONUTRIENTES
                   SET n=%s, k=%s, p=%s, mg=%s, b=%s, ca=%s, zn=%s, mn=%s, fe=%s,
                       eficiencia_fertilizante=%s
                   WHERE id_producto=%s""",
                (n, k, p, mg, b, ca, zn, mn, fe, eficiencia, id_producto),
            )
            # Construir UPDATE dinamico del PRODUCTO con los campos que vinieron
            sets = []
            vals: list = []
            if precio_usd is not None:
                sets.append("precio_usd = %s"); vals.append(precio_usd)
            if id_objetivo is not None:
                sets.append("id_objetivo = %s"); vals.append(id_objetivo or '')
            if id_modo_accion is not None:
                sets.append("id_modo_accion = %s"); vals.append(id_modo_accion or None)
            if reingreso is not None:
                sets.append("reingreso = %s"); vals.append(reingreso)
            if nombre_comercial is not None and nombre_comercial.strip():
                sets.append("nombre_comercial = %s"); vals.append(nombre_comercial.strip())
            if id_unidad is not None:
                sets.append("id_unidad = %s"); vals.append(id_unidad)
            if _codigo_softland_set:
                sets.append("codigo_softland = %s"); vals.append(codigo_softland)
            if sets:
                vals.append(id_producto)
                cur.execute(
                    f"UPDATE DIM_AREATECNICA_FITO_PRODUCTO SET {', '.join(sets)} WHERE id = %s",
                    vals,
                )
        conn.commit()


# ── Edición de matriz ────────────────────────────────────────────────────────

def get_programas_cuartel(id_cuartel: int, id_temporada: int | None = None) -> list:
    where = ["id_cuartel = %s"]
    params: list = [id_cuartel]
    if id_temporada:
        where.append("id_temporada = %s")
        params.append(id_temporada)
    sql = f"SELECT id FROM FACT_AREATECNICA_FERTILIZACION_PROGRAMA WHERE {' AND '.join(where)}"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return [r["id"] for r in cur.fetchall()]


_SIGLA_ORDEN = [("n", "N"), ("p", "P"), ("k", "K"),
                ("mg", "Mg"), ("b", "B"), ("ca", "Ca"),
                ("zn", "Zn"), ("mn", "Mn")]


def get_productos_disponibles(id_cuartel: int, id_temporada: int | None = None) -> list:
    """Productos NO asignados al cuartel + string de nutrientes principales."""
    ids_prog = get_programas_cuartel(id_cuartel, id_temporada)
    if not ids_prog:
        return []
    ph = ",".join(["%s"] * len(ids_prog))
    sql = f"""
        SELECT
            p.id,
            p.nombre_comercial,
            p.id_actividad,
            COALESCE(pn.n, 0)  AS n,
            COALESCE(pn.p, 0)  AS p,
            COALESCE(pn.k, 0)  AS k,
            COALESCE(pn.mg, 0) AS mg,
            COALESCE(pn.b, 0)  AS b,
            COALESCE(pn.ca, 0) AS ca,
            COALESCE(pn.zn, 0) AS zn,
            COALESCE(pn.mn, 0) AS mn
        FROM DIM_AREATECNICA_FITO_PRODUCTO p
        LEFT JOIN DIM_AREATECNICA_FITO_PRODUCTONUTRIENTES pn ON pn.id_producto = p.id
        WHERE p.id_actividad IN ('5', '48')
          AND p.id NOT IN (
            SELECT DISTINCT id_producto
            FROM FACT_AREATECNICA_FERTILIZACION_PRODUCTOSPROGRAMA
            WHERE id_fertilizacion IN ({ph})
        )
        ORDER BY p.id_actividad DESC, p.nombre_comercial
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, ids_prog)
            rows = cur.fetchall()

    # Agregar string compacto de nutrientes por producto
    for r in rows:
        siglas = [sigla for col, sigla in _SIGLA_ORDEN if float(r.get(col) or 0) > 0]
        r["sigla_nut"] = "".join(siglas) if siglas else ""
    return rows


def agregar_producto_semanas(ids_programa: list, id_producto: int) -> None:
    if not ids_programa:
        return
    import uuid as _uuid
    check_sql = """
        SELECT 1 FROM FACT_AREATECNICA_FERTILIZACION_PRODUCTOSPROGRAMA
        WHERE id_fertilizacion = %s AND id_producto = %s LIMIT 1
    """
    insert_sql = """
        INSERT INTO FACT_AREATECNICA_FERTILIZACION_PRODUCTOSPROGRAMA
            (id, id_fertilizacion, id_producto, cantidad_producto,
             unidades_n, unidades_k, unidades_p, unidades_mg,
             unidades_b, unidades_ca, unidades_zn, unidades_mn)
        VALUES (%s, %s, %s, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            for id_prog in ids_programa:
                cur.execute(check_sql, (id_prog, id_producto))
                if cur.fetchone():
                    continue
                cur.execute(insert_sql, (str(_uuid.uuid4())[:45], id_prog, id_producto))
        conn.commit()


def update_dosis(id_programa: str, id_producto: int, dosis: float) -> None:
    sql = """
        UPDATE FACT_AREATECNICA_FERTILIZACION_PRODUCTOSPROGRAMA
        SET cantidad_producto = %s
        WHERE id_fertilizacion = %s AND id_producto = %s
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (dosis, id_programa, id_producto))
        conn.commit()


def get_semanas_disponibles_cuartel(id_cuartel: int, id_temporada: int) -> list:
    """Semanas de la temporada que aun no estan en el programa del cuartel."""
    sql = """
        SELECT sem.id, sem.etiqueta_semana, sem.semana_calendario,
               sem.anio_calendario, sem.fecha_inicio, sem.fecha_fin
        FROM DIM_GENERAL_SEMANASTEMPORADA sem
        WHERE sem.temporada = %s
          AND NOT EXISTS (
              SELECT 1
              FROM FACT_AREATECNICA_FERTILIZACION_PROGRAMA prog
              WHERE prog.id_cuartel = %s
                AND prog.id_temporada = %s
                AND CAST(prog.semana AS UNSIGNED) = sem.id
          )
        ORDER BY sem.fecha_inicio
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (str(id_temporada), id_cuartel, id_temporada))
            return cur.fetchall()


def agregar_semana_programa(id_cuartel: int, id_temporada: int, id_semana: int,
                             etapa: str, id_responsable: int) -> tuple[str, bool]:
    """Crea una fila en PROGRAMA y replica los productos ya existentes en otras
    semanas del mismo cuartel/temporada con dosis 0.

    Retorna (id_programa, created) — created=False si la combinacion
    (cuartel, semana, temporada) ya existia."""
    from datetime import datetime
    id_programa = f"{id_cuartel}{id_semana}"

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Si ya existe la semana en el programa, no insertar
            cur.execute(
                """SELECT id FROM FACT_AREATECNICA_FERTILIZACION_PROGRAMA
                   WHERE id_cuartel = %s AND id_temporada = %s
                     AND CAST(semana AS UNSIGNED) = %s
                   LIMIT 1""",
                (id_cuartel, id_temporada, id_semana),
            )
            existing = cur.fetchone()
            if existing:
                return existing["id"], False

            # Obtener fechas de la semana
            cur.execute(
                "SELECT fecha_inicio, fecha_fin FROM DIM_GENERAL_SEMANASTEMPORADA WHERE id = %s",
                (id_semana,),
            )
            sem = cur.fetchone()
            if not sem:
                raise ValueError(f"Semana {id_semana} no existe")
            fi, ff = sem["fecha_inicio"], sem["fecha_fin"]

            # INSERT en PROGRAMA
            cur.execute(
                """INSERT INTO FACT_AREATECNICA_FERTILIZACION_PROGRAMA
                   (id, id_responsable, id_temporada, id_cuartel, hora_registro,
                    semana, fecha_inicio, fecha_termino, etapa)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    id_programa,
                    id_responsable,
                    id_temporada,
                    id_cuartel,
                    datetime.now(),
                    str(id_semana),
                    fi,
                    ff,
                    etapa,
                ),
            )

            # Replicar productos ya asignados al cuartel con dosis 0
            cur.execute(
                """SELECT DISTINCT pp.id_producto
                   FROM FACT_AREATECNICA_FERTILIZACION_PRODUCTOSPROGRAMA pp
                   JOIN FACT_AREATECNICA_FERTILIZACION_PROGRAMA prog
                     ON prog.id = pp.id_fertilizacion
                   WHERE prog.id_cuartel = %s AND prog.id_temporada = %s
                     AND prog.id <> %s""",
                (id_cuartel, id_temporada, id_programa),
            )
            productos = [r["id_producto"] for r in cur.fetchall()]

            if productos:
                import uuid as _uuid
                for pid in productos:
                    cur.execute(
                        """INSERT INTO FACT_AREATECNICA_FERTILIZACION_PRODUCTOSPROGRAMA
                           (id, id_fertilizacion, id_producto, cantidad_producto,
                            unidades_n, unidades_k, unidades_p, unidades_mg,
                            unidades_b, unidades_ca, unidades_zn, unidades_mn)
                           VALUES (%s, %s, %s, 0, 0, 0, 0, 0, 0, 0, 0, 0)""",
                        (str(_uuid.uuid4())[:45], id_programa, pid),
                    )
        conn.commit()
    return id_programa, True


def eliminar_semana_programa(id_programa: str) -> None:
    """Elimina una fila de PROGRAMA y todas sus dosis asociadas en PRODUCTOSPROGRAMA."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM FACT_AREATECNICA_FERTILIZACION_PRODUCTOSPROGRAMA WHERE id_fertilizacion = %s",
                (id_programa,),
            )
            cur.execute(
                "DELETE FROM FACT_AREATECNICA_FERTILIZACION_PROGRAMA WHERE id = %s",
                (id_programa,),
            )
        conn.commit()


def eliminar_producto_cuartel(ids_programa: list, id_producto: int) -> int:
    if not ids_programa:
        return 0
    ph = ",".join(["%s"] * len(ids_programa))
    sql = f"""
        DELETE FROM FACT_AREATECNICA_FERTILIZACION_PRODUCTOSPROGRAMA
        WHERE id_producto = %s AND id_fertilizacion IN ({ph})
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_producto, *ids_programa))
            deleted = cur.rowcount
        conn.commit()
    return deleted


def get_programa(id_programa: str) -> dict | None:
    sql = """
        SELECT
            prog.id,
            prog.semana              AS id_semana,
            sem.semana_calendario,
            sem.etiqueta_semana,
            sem.fecha_inicio         AS sem_fecha_inicio,
            sem.fecha_fin            AS sem_fecha_fin,
            prog.fecha_inicio,
            prog.fecha_termino,
            prog.hora_registro,
            prog.etapa,
            temp.temporada,
            CONCAT(col.nombre, ' ', col.apellido) AS responsable,
            ceco.id                 AS id_cuartel,
            ceco.descripcion_ceco   AS cuartel_nombre,
            ceco.sup_productiva,
            suc.id                  AS id_sucursal,
            suc.sucursal,
            var.variedad,
            port.portainjerto       AS portainjerto_nombre
        FROM FACT_AREATECNICA_FERTILIZACION_PROGRAMA prog
        JOIN DIM_GENERAL_TEMPORADA         temp ON temp.id  = prog.id_temporada
        JOIN DIM_GENERAL_COLABORADOR       col  ON col.id   = prog.id_responsable
        JOIN DIM_GENERAL_CECO              ceco ON ceco.id  = prog.id_cuartel
        JOIN DIM_GENERAL_SUCURSAL          suc  ON suc.id   = ceco.id_sucursal
        JOIN DIM_GENERAL_SEMANASTEMPORADA  sem  ON sem.id   = prog.semana
        LEFT JOIN DIM_GENERAL_VARIEDAD     var  ON var.id   = ceco.id_variedad
        LEFT JOIN DIM_GENERAL_PORTAINJERTO port ON port.id  = ceco.portainjerto
        WHERE prog.id = %s
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_programa,))
            return cur.fetchone()


def get_productos(id_programa: str) -> list:
    sql = """
        SELECT
            pp.id_producto,
            pp.cantidad_producto            AS dosis_ha,
            pp.unidades_n,
            pp.unidades_k,
            pp.unidades_p,
            pp.unidades_mg,
            pp.unidades_b,
            pp.unidades_ca,
            pp.unidades_zn,
            pp.unidades_mn,
            prod.nombre_comercial,
            uni.abreviatura                 AS unidad,
            COALESCE(pn.n,  0)              AS pct_n,
            COALESCE(pn.k,  0)              AS pct_k,
            COALESCE(pn.p,  0)              AS pct_p,
            COALESCE(pn.mg, 0)              AS pct_mg
        FROM FACT_AREATECNICA_FERTILIZACION_PRODUCTOSPROGRAMA pp
        JOIN  DIM_AREATECNICA_FITO_PRODUCTO       prod ON prod.id       = pp.id_producto
        LEFT JOIN DIM_GENERAL_UNIDAD              uni  ON uni.id        = prod.id_unidad
        LEFT JOIN DIM_AREATECNICA_FITO_PRODUCTONUTRIENTES pn
                                                       ON pn.id_producto = pp.id_producto
        WHERE pp.id_fertilizacion = %s
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_programa,))
            return cur.fetchall()


def get_sectores(id_cuartel: int) -> list:
    sql = """
        SELECT
            s.nombre    AS sector_nombre,
            psc.superficie
        FROM PIVOT_AREATECNICA_RIEGO_SECTORCUARTEL psc
        JOIN DIM_AREATECNICA_RIEGO_SECTOR s ON s.id = psc.id_sector
        WHERE psc.id_cuartel = %s
        ORDER BY s.nombre
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_cuartel,))
            return cur.fetchall()


# ── Bodega (por semana) ───────────────────────────────────────────────────────

def get_semanas_disponibles(
    id_temporada: int | None = None,
    id_sucursal: int | None = None,
) -> list:
    """Retorna las etiquetas de semana que tienen programas, opcionalmente filtrado."""
    suc_ph = ",".join(["%s"] * len(SUCURSALES_VISIBLES))
    where = [f"suc.id IN ({suc_ph})"]
    params: list = list(SUCURSALES_VISIBLES)

    if id_temporada:
        where.append("prog.id_temporada = %s")
        params.append(id_temporada)
    if id_sucursal:
        where.append("suc.id = %s")
        params.append(id_sucursal)

    sql = f"""
        SELECT DISTINCT
            sem.id                AS id,
            sem.etiqueta_semana,
            sem.semana_calendario,
            sem.fecha_inicio,
            sem.fecha_fin
        FROM FACT_AREATECNICA_FERTILIZACION_PROGRAMA prog
        JOIN DIM_GENERAL_CECO             ceco ON ceco.id = prog.id_cuartel
        JOIN DIM_GENERAL_SUCURSAL         suc  ON suc.id  = ceco.id_sucursal
        JOIN DIM_GENERAL_SEMANASTEMPORADA sem  ON sem.id  = prog.semana
        WHERE {' AND '.join(where)}
        ORDER BY sem.fecha_inicio ASC
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def get_programas_semana(etiqueta_semana: str) -> list:
    sql = """
        SELECT
            prog.id,
            sem.id               AS id_semana,
            sem.etiqueta_semana,
            sem.fecha_inicio     AS sem_fecha_inicio,
            sem.fecha_fin        AS sem_fecha_fin,
            temp.temporada,
            ceco.id              AS id_cuartel,
            ceco.descripcion_ceco AS cuartel_nombre,
            ceco.sup_productiva,
            suc.sucursal,
            COALESCE(var.variedad, '—') AS variedad,
            prog.etapa
        FROM FACT_AREATECNICA_FERTILIZACION_PROGRAMA prog
        JOIN DIM_GENERAL_TEMPORADA        temp ON temp.id  = prog.id_temporada
        JOIN DIM_GENERAL_CECO             ceco ON ceco.id  = prog.id_cuartel
        JOIN DIM_GENERAL_SUCURSAL         suc  ON suc.id   = ceco.id_sucursal
        JOIN DIM_GENERAL_SEMANASTEMPORADA sem  ON sem.id   = prog.semana
        LEFT JOIN DIM_GENERAL_VARIEDAD    var  ON var.id   = ceco.id_variedad
        WHERE sem.etiqueta_semana = %s
        ORDER BY var.variedad, ceco.descripcion_ceco
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (etiqueta_semana,))
            return cur.fetchall()


def get_productos_multiples(ids_programa: list) -> list:
    if not ids_programa:
        return []
    placeholders = ','.join(['%s'] * len(ids_programa))
    sql = f"""
        SELECT
            pp.id_fertilizacion  AS id_programa,
            pp.cantidad_producto AS dosis_ha,
            prod.nombre_comercial
        FROM FACT_AREATECNICA_FERTILIZACION_PRODUCTOSPROGRAMA pp
        JOIN DIM_AREATECNICA_FITO_PRODUCTO prod ON prod.id = pp.id_producto
        WHERE pp.id_fertilizacion IN ({placeholders})
        ORDER BY prod.nombre_comercial
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, ids_programa)
            return cur.fetchall()


def get_sectores_multiples(ids_cuartel: list) -> list:
    if not ids_cuartel:
        return []
    placeholders = ','.join(['%s'] * len(ids_cuartel))
    sql = f"""
        SELECT
            psc.id_cuartel,
            s.nombre    AS sector_nombre,
            psc.superficie
        FROM PIVOT_AREATECNICA_RIEGO_SECTORCUARTEL psc
        JOIN DIM_AREATECNICA_RIEGO_SECTOR s ON s.id = psc.id_sector
        WHERE psc.id_cuartel IN ({placeholders})
        ORDER BY psc.id_cuartel, s.nombre
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, ids_cuartel)
            return cur.fetchall()


# ══ Papeleta por campo (caseta → equipo → sector → cuarteles) ═════════════════

def get_casetas_con_programa(etiqueta_semana: str, id_sucursal: int) -> list:
    """Casetas del campo que tienen al menos un cuartel con programa esta semana.
    Util para poblar el dropdown de 'Papeleta por caseta'."""
    sql = """
        SELECT DISTINCT cas.id, cas.caseta
        FROM DIM_AREATECNICA_RIEGO_CASETA cas
        JOIN DIM_AREATECNICA_RIEGO_EQUIPO eq ON eq.id_caseta = cas.id
        JOIN DIM_AREATECNICA_RIEGO_SECTOR s  ON s.id_equipo  = eq.id
        JOIN PIVOT_AREATECNICA_RIEGO_SECTORCUARTEL psc ON psc.id_sector = s.id
        JOIN FACT_AREATECNICA_FERTILIZACION_PROGRAMA prog ON prog.id_cuartel = psc.id_cuartel
        JOIN DIM_GENERAL_SEMANASTEMPORADA sem ON sem.id = prog.semana
        WHERE cas.id_sucursal = %s AND sem.etiqueta_semana = %s
        ORDER BY cas.caseta
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_sucursal, etiqueta_semana))
            return cur.fetchall()


def get_caseta_info(id_caseta: int) -> dict | None:
    """Devuelve {id, caseta, id_sucursal} o None."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, caseta, id_sucursal FROM DIM_AREATECNICA_RIEGO_CASETA WHERE id = %s",
                (id_caseta,),
            )
            return cur.fetchone()


def get_papeleta_campo_rows(etiqueta_semana: str, id_sucursal: int) -> list:
    """Trae todos los registros planos para armar la papeleta jerarquica por campo.
    Una fila = (caseta, equipo, sector, cuartel con sup del sector, producto con dosis).
    Incluye N-P-K del producto y especie del cuartel para cumplir formato auditoria.
    """
    sql = """
        SELECT
            cas.id                AS id_caseta,
            cas.caseta            AS caseta,
            eq.id                 AS id_equipo,
            eq.equipo             AS equipo,
            s.id                  AS id_sector,
            s.nombre              AS sector,
            ceco.id               AS id_cuartel,
            ceco.descripcion_ceco AS cuartel,
            COALESCE(var.variedad, '—') AS variedad,
            COALESCE(esp.especie, '—')  AS especie,
            prog.etapa,
            prog.fecha_inicio,
            prog.fecha_termino,
            psc.superficie        AS sup_sector_cuartel,
            prod.id               AS id_producto,
            prod.nombre_comercial AS producto,
            pp.cantidad_producto  AS dosis_ha,
            COALESCE(pn.n, 0)     AS pct_n,
            COALESCE(pn.p, 0)     AS pct_p,
            COALESCE(pn.k, 0)     AS pct_k
        FROM DIM_AREATECNICA_RIEGO_CASETA cas
        JOIN DIM_AREATECNICA_RIEGO_EQUIPO eq ON eq.id_caseta = cas.id
        JOIN DIM_AREATECNICA_RIEGO_SECTOR s  ON s.id_equipo  = eq.id
        JOIN PIVOT_AREATECNICA_RIEGO_SECTORCUARTEL psc ON psc.id_sector = s.id
        JOIN FACT_AREATECNICA_FERTILIZACION_PROGRAMA prog ON prog.id_cuartel = psc.id_cuartel
        JOIN DIM_GENERAL_SEMANASTEMPORADA sem ON sem.id = prog.semana
        JOIN DIM_GENERAL_CECO ceco ON ceco.id = prog.id_cuartel
        LEFT JOIN DIM_GENERAL_VARIEDAD var ON var.id = ceco.id_variedad
        LEFT JOIN DIM_GENERAL_ESPECIE  esp ON esp.id = var.id_especie
        JOIN FACT_AREATECNICA_FERTILIZACION_PRODUCTOSPROGRAMA pp ON pp.id_fertilizacion = prog.id
        JOIN DIM_AREATECNICA_FITO_PRODUCTO prod ON prod.id = pp.id_producto
        LEFT JOIN DIM_AREATECNICA_FITO_PRODUCTONUTRIENTES pn ON pn.id_producto = prod.id
        WHERE cas.id_sucursal = %s
          AND sem.etiqueta_semana = %s
        ORDER BY cas.caseta, eq.equipo, s.nombre, ceco.descripcion_ceco, prod.nombre_comercial
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_sucursal, etiqueta_semana))
            return cur.fetchall()


def get_cuarteles_huerfanos(etiqueta_semana: str, id_sucursal: int) -> list:
    """Cuarteles con programa en la semana pero sin sector de riego asignado.
    Retorna una fila por (cuartel, producto)."""
    sql = """
        SELECT
            ceco.id               AS id_cuartel,
            ceco.descripcion_ceco AS cuartel,
            COALESCE(var.variedad, '—') AS variedad,
            ceco.sup_productiva,
            prog.etapa,
            prod.nombre_comercial AS producto,
            pp.cantidad_producto  AS dosis_ha
        FROM FACT_AREATECNICA_FERTILIZACION_PROGRAMA prog
        JOIN DIM_GENERAL_CECO ceco ON ceco.id = prog.id_cuartel
        JOIN DIM_GENERAL_SEMANASTEMPORADA sem ON sem.id = prog.semana
        LEFT JOIN DIM_GENERAL_VARIEDAD var ON var.id = ceco.id_variedad
        LEFT JOIN PIVOT_AREATECNICA_RIEGO_SECTORCUARTEL psc ON psc.id_cuartel = ceco.id
        LEFT JOIN FACT_AREATECNICA_FERTILIZACION_PRODUCTOSPROGRAMA pp ON pp.id_fertilizacion = prog.id
        LEFT JOIN DIM_AREATECNICA_FITO_PRODUCTO prod ON prod.id = pp.id_producto
        WHERE ceco.id_sucursal = %s
          AND sem.etiqueta_semana = %s
          AND psc.id_sector IS NULL
        ORDER BY ceco.descripcion_ceco, prod.nombre_comercial
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (id_sucursal, etiqueta_semana))
            return cur.fetchall()


def get_sucursal_info(id_sucursal: int) -> dict | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, sucursal FROM DIM_GENERAL_SUCURSAL WHERE id = %s", (id_sucursal,))
            return cur.fetchone()


def get_semana_info(etiqueta_semana: str) -> dict | None:
    sql = """
        SELECT etiqueta_semana, semana_calendario, fecha_inicio, fecha_fin, temporada
        FROM DIM_GENERAL_SEMANASTEMPORADA
        WHERE etiqueta_semana = %s
        LIMIT 1
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (etiqueta_semana,))
            return cur.fetchone()


# ══ AUTH ═══════════════════════════════════════════════════════════════════════

def get_sucursal_de_cuartel(id_cuartel: int) -> int | None:
    """Lookup rapido id_cuartel -> id_sucursal. Para validar permisos."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id_sucursal FROM DIM_GENERAL_CECO WHERE id = %s", (id_cuartel,))
            r = cur.fetchone()
            return r["id_sucursal"] if r else None


def get_sucursales_permitidas(id_usuario: int) -> list:
    """Lista de id_sucursal autorizados para el usuario. Tolerante a que la
    tabla z_usuario_sucursal aun no exista (retorna [])."""
    import pymysql
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "SELECT id_sucursal FROM z_usuario_sucursal WHERE id_usuario = %s",
                    (id_usuario,),
                )
                return [r["id_sucursal"] for r in cur.fetchall()]
            except pymysql.err.ProgrammingError as e:
                # 1146 = tabla no existe
                if e.args and e.args[0] == 1146:
                    return []
                raise


# ── Gestion de usuarios (super_admin) ────────────────────────────────────────

def listar_usuarios() -> list:
    """Lista todos los usuarios con su rol y email."""
    sql = """
        SELECT id, usuario, nombre, apellido, COALESCE(rol, 'user') AS rol,
               COALESCE(email, '') AS email
        FROM z_usuarios_test
        ORDER BY rol DESC, usuario
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()


def listar_usuarios_con_sucursales() -> list:
    """Usuarios + lista de id_sucursal asignados (solo para roles 'user')."""
    users = listar_usuarios()
    if not users:
        return []
    ids = [u["id"] for u in users]
    ph = ",".join(["%s"] * len(ids))
    sql = f"SELECT id_usuario, id_sucursal FROM z_usuario_sucursal WHERE id_usuario IN ({ph})"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, ids)
            asign = cur.fetchall()
    sucs_por_user = {}
    for a in asign:
        sucs_por_user.setdefault(a["id_usuario"], []).append(a["id_sucursal"])
    for u in users:
        u["sucursales"] = sorted(sucs_por_user.get(u["id"], []))
    return users


def actualizar_rol_usuario(id_usuario: int, nuevo_rol: str) -> None:
    """Cambia rol. Acepta 'user', 'admin', 'super_admin'."""
    if nuevo_rol not in ("user", "admin", "super_admin"):
        raise ValueError("rol invalido")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE z_usuarios_test SET rol = %s WHERE id = %s",
                (nuevo_rol, id_usuario),
            )
        conn.commit()


def set_sucursales_usuario(id_usuario: int, ids_sucursal: list) -> None:
    """Reemplaza el set de sucursales asignadas al usuario."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM z_usuario_sucursal WHERE id_usuario = %s",
                (id_usuario,),
            )
            for sid in ids_sucursal:
                try:
                    sid_int = int(sid)
                except (ValueError, TypeError):
                    continue
                cur.execute(
                    "INSERT INTO z_usuario_sucursal (id_usuario, id_sucursal) VALUES (%s, %s)",
                    (id_usuario, sid_int),
                )
        conn.commit()


def crear_usuario(usuario: str, nombre: str, apellido: str,
                   email: str, rol: str = "user") -> int:
    """Crea un usuario nuevo. Login es por Google OAuth, asi que la clave queda
    vacia. Retorna id."""
    if rol not in ("user", "admin", "super_admin"):
        rol = "user"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO z_usuarios_test (usuario, nombre, apellido, `contraseña`, rol, email) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (usuario.strip(), nombre.strip(), apellido.strip(), "", rol, email.strip().lower()),
            )
            new_id = cur.lastrowid
        conn.commit()
    return new_id


def actualizar_email_usuario(id_usuario: int, email: str) -> None:
    """Actualiza el correo de un usuario (usado para matchear con Google OAuth)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE z_usuarios_test SET email = %s WHERE id = %s",
                (email.strip().lower(), id_usuario),
            )
        conn.commit()


def resetear_password(id_usuario: int, nueva: str) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE z_usuarios_test SET `contraseña` = %s WHERE id = %s",
                (nueva, id_usuario),
            )
        conn.commit()


def cambiar_password_propia(id_usuario: int, actual: str, nueva: str) -> bool:
    """Cambia la propia clave validando la actual. Retorna True si se cambio."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM z_usuarios_test WHERE id = %s AND `contraseña` = %s",
                (id_usuario, actual),
            )
            if not cur.fetchone():
                return False
            cur.execute(
                "UPDATE z_usuarios_test SET `contraseña` = %s WHERE id = %s",
                (nueva, id_usuario),
            )
        conn.commit()
    return True


def eliminar_usuario(id_usuario: int) -> None:
    """Borra usuario y sus asignaciones de sucursal."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM z_usuario_sucursal WHERE id_usuario = %s", (id_usuario,))
            cur.execute("DELETE FROM z_usuarios_test WHERE id = %s", (id_usuario,))
        conn.commit()


def existe_usuario_nombre(usuario: str, excluir_id: int | None = None) -> bool:
    sql = "SELECT 1 FROM z_usuarios_test WHERE usuario = %s"
    params: list = [usuario.strip()]
    if excluir_id:
        sql += " AND id <> %s"
        params.append(excluir_id)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql + " LIMIT 1", params)
            return cur.fetchone() is not None


def get_usuario_por_email(email: str) -> dict | None:
    """Busca usuario por email para flujo OAuth. Tolerante a columna inexistente."""
    import pymysql
    sql = """
        SELECT id, usuario, nombre, apellido, COALESCE(rol, 'user') AS rol, email
        FROM z_usuarios_test
        WHERE LOWER(email) = LOWER(%s)
        LIMIT 1
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(sql, (email.strip(),))
                return cur.fetchone()
            except pymysql.err.OperationalError as e:
                # 1054 = Unknown column 'email' (tabla aun sin migrar)
                if e.args and e.args[0] == 1054:
                    return None
                raise


def validar_login(usuario: str, contrasena: str) -> dict | None:
    """Valida credenciales. Tolerante a que la columna `rol` aun no exista
    (default 'user')."""
    sql_con_rol = """
        SELECT id, usuario, nombre, apellido, COALESCE(rol, 'user') AS rol
        FROM z_usuarios_test
        WHERE usuario = %s AND `contraseña` = %s
        LIMIT 1
    """
    sql_sin_rol = """
        SELECT id, usuario, nombre, apellido
        FROM z_usuarios_test
        WHERE usuario = %s AND `contraseña` = %s
        LIMIT 1
    """
    import pymysql
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(sql_con_rol, (usuario, contrasena))
                return cur.fetchone()
            except pymysql.err.OperationalError as e:
                # 1054 = Unknown column. Cae aqui si la columna `rol` no existe.
                if e.args and e.args[0] == 1054:
                    cur.execute(sql_sin_rol, (usuario, contrasena))
                    row = cur.fetchone()
                    if row is not None:
                        row["rol"] = "user"
                    return row
                raise
