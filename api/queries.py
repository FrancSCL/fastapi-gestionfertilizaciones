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
    )

    sql = f"""
        SELECT
            ceco.id                     AS id_cuartel,
            ceco.descripcion_ceco       AS cuartel,
            var.variedad                AS variedad,
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
        LEFT JOIN DIM_GENERAL_PORTAINJERTO port ON port.id = ceco.portainjerto
        LEFT JOIN FACT_AREATECNICA_FERTILIZACION_UNIDADESREQUERIDAS ur
                  ON ur.id_cuartel = ceco.id {ur_cond}
        {where_sql}
        GROUP BY ceco.id, ceco.descripcion_ceco, var.variedad, port.portainjerto,
                 ceco.sup_productiva, suc.id, suc.sucursal
        {having_clause}
        ORDER BY suc.sucursal, ceco.descripcion_ceco
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, final_params)
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

    return {
        "semanas": semanas_list,
        "productos": productos_list,
        "filas": filas,
        "totales_prod": totales_prod,
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
                      especie: str, factores: list) -> dict:
    col = _col_especie(especie)
    resultado = {}
    for f in factores:
        fert = f["fertilizante"]
        factor_esp = float(f[col] or 0)
        resultado[fert] = round(ton_estimadas * vigor_factor * factor_esp, 2)
    return resultado


def save_unidades_requeridas(id_cuartel: int, id_temporada: int, id_vigor: int,
                              id_responsable: int, especie: str,
                              ton_estimadas: float, vigor_factor: float,
                              factores: list) -> None:
    import uuid
    from datetime import datetime
    unidades = calcular_unidades(ton_estimadas, vigor_factor, especie, factores)

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

def get_productos_lista() -> list:
    sql = """
        SELECT
            p.id,
            p.nombre_comercial,
            p.codigo_softland,
            u.abreviatura   AS unidad,
            pn.eficiencia_fertilizante,
            COALESCE(pn.n,  0) AS n,
            COALESCE(pn.k,  0) AS k,
            COALESCE(pn.p,  0) AS p,
            COALESCE(pn.mg, 0) AS mg,
            COALESCE(pn.b,  0) AS b,
            COALESCE(pn.ca, 0) AS ca,
            COALESCE(pn.zn, 0) AS zn,
            COALESCE(pn.mn, 0) AS mn
        FROM DIM_AREATECNICA_FITO_PRODUCTO p
        LEFT JOIN DIM_GENERAL_UNIDAD u ON u.id = p.id_unidad
        LEFT JOIN DIM_AREATECNICA_FITO_PRODUCTONUTRIENTES pn ON pn.id_producto = p.id
        WHERE p.id_actividad = 5
        ORDER BY p.nombre_comercial
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()


def get_unidades_lista() -> list:
    sql = "SELECT id, abreviatura, nombre AS unidad FROM DIM_GENERAL_UNIDAD ORDER BY abreviatura"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()


def save_producto(nombre_comercial: str, id_unidad: int, codigo_softland: int | None,
                  n: float, k: float, p: float, mg: float,
                  b: float, ca: float, zn: float, mn: float,
                  eficiencia: float) -> None:
    import uuid as _uuid
    id_prod = str(_uuid.uuid4())[:25]
    id_nut  = str(_uuid.uuid4())
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO DIM_AREATECNICA_FITO_PRODUCTO
                   (id, nombre_comercial, id_unidad, codigo_softland, id_actividad)
                   VALUES (%s, %s, %s, %s, 5)""",
                (id_prod, nombre_comercial, id_unidad, codigo_softland or None),
            )
            cur.execute(
                """INSERT INTO DIM_AREATECNICA_FITO_PRODUCTONUTRIENTES
                   (id, id_producto, eficiencia_fertilizante, n, k, p, mg, b, ca, zn, mn)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (id_nut, id_prod, eficiencia, n, k, p, mg, b, ca, zn, mn),
            )
        conn.commit()


def update_producto_nutrientes(id_producto: str, n: float, k: float, p: float,
                               mg: float, b: float, ca: float, zn: float, mn: float,
                               eficiencia: float) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE DIM_AREATECNICA_FITO_PRODUCTONUTRIENTES
                   SET n=%s, k=%s, p=%s, mg=%s, b=%s, ca=%s, zn=%s, mn=%s,
                       eficiencia_fertilizante=%s
                   WHERE id_producto=%s""",
                (n, k, p, mg, b, ca, zn, mn, eficiencia, id_producto),
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


def get_productos_disponibles(id_cuartel: int, id_temporada: int | None = None) -> list:
    """Productos que NO están ya en ningún programa del cuartel para la temporada."""
    ids_prog = get_programas_cuartel(id_cuartel, id_temporada)
    if not ids_prog:
        return []
    ph = ",".join(["%s"] * len(ids_prog))
    sql = f"""
        SELECT id, nombre_comercial
        FROM DIM_AREATECNICA_FITO_PRODUCTO
        WHERE id_actividad = 5
          AND id NOT IN (
            SELECT DISTINCT id_producto
            FROM FACT_AREATECNICA_FERTILIZACION_PRODUCTOSPROGRAMA
            WHERE id_fertilizacion IN ({ph})
        )
        ORDER BY nombre_comercial
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, ids_prog)
            return cur.fetchall()


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
            sem.etiqueta_semana,
            sem.semana_calendario,
            sem.fecha_inicio,
            sem.fecha_fin
        FROM FACT_AREATECNICA_FERTILIZACION_PROGRAMA prog
        JOIN DIM_GENERAL_CECO             ceco ON ceco.id = prog.id_cuartel
        JOIN DIM_GENERAL_SUCURSAL         suc  ON suc.id  = ceco.id_sucursal
        JOIN DIM_GENERAL_SEMANASTEMPORADA sem  ON sem.id  = prog.semana
        WHERE {' AND '.join(where)}
        ORDER BY sem.fecha_inicio DESC
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


# ══ AUTH ═══════════════════════════════════════════════════════════════════════

def validar_login(usuario: str, contrasena: str) -> dict | None:
    sql = """
        SELECT id, usuario, nombre, apellido
        FROM z_usuarios_test
        WHERE usuario = %s AND `contraseña` = %s
        LIMIT 1
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (usuario, contrasena))
            return cur.fetchone()
