-- ============================================================
-- Vistas para App Casetero (Fertilizaciones) en AppSheet
-- Ejecutar en MySQL Workbench sobre la DB de producción
-- ============================================================


-- ------------------------------------------------------------
-- Vista 1: v_fertilizacion_papeletas
-- Una fila por programa. Muestra el estado más reciente
-- consultando el último registro en FACT_CONFIRMACION.
-- Usada en la vista tipo Deck de AppSheet.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW v_fertilizacion_papeletas AS
SELECT
    prog.id,
    prog.semana,
    sem.etiqueta_semana,
    sem.fecha_inicio                                AS sem_fecha_inicio,
    sem.fecha_fin                                   AS sem_fecha_fin,
    prog.fecha_inicio,
    prog.fecha_termino,
    ceco.descripcion_ceco                           AS cuartel,
    suc.sucursal,
    GROUP_CONCAT(
        DISTINCT prod.nombre_comercial
        ORDER BY prod.nombre_comercial
        SEPARATOR ', '
    )                                               AS productos,
    ultimo.id_estado
FROM FACT_AREATECNICA_FERTILIZACION_PROGRAMA prog
JOIN DIM_GENERAL_SEMANASTEMPORADA                        sem  ON sem.id             = prog.semana
JOIN DIM_GENERAL_CECO                                    ceco ON ceco.id            = prog.id_cuartel
JOIN DIM_GENERAL_SUCURSAL                                suc  ON suc.id             = ceco.id_sucursal
JOIN FACT_AREATECNICA_FERTILIZACION_PRODUCTOSPROGRAMA    pp   ON pp.id_fertilizacion = prog.id
JOIN DIM_AREATECNICA_FITO_PRODUCTO                       prod ON prod.id            = pp.id_producto
LEFT JOIN (
    -- Subconsulta: trae solo el registro más reciente por programa
    SELECT c1.id_programa, c1.id_estado
    FROM FACT_AREATECNICA_FERTILIZACION_CONFIRMACION c1
    INNER JOIN (
        SELECT id_programa, MAX(hora_registro) AS ultima_hora
        FROM FACT_AREATECNICA_FERTILIZACION_CONFIRMACION
        GROUP BY id_programa
    ) c2 ON c1.id_programa = c2.id_programa
        AND c1.hora_registro = c2.ultima_hora
) ultimo ON ultimo.id_programa = prog.id
GROUP BY
    prog.id,
    prog.semana,
    sem.etiqueta_semana,
    sem.fecha_inicio,
    sem.fecha_fin,
    prog.fecha_inicio,
    prog.fecha_termino,
    ceco.descripcion_ceco,
    suc.sucursal,
    ultimo.id_estado;


-- ------------------------------------------------------------
-- Vista 2: v_fertilizacion_productos_programa
-- Una fila por producto dentro de cada programa.
-- Usada en la vista de detalle (inline) en AppSheet.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW v_fertilizacion_productos_programa AS
SELECT
    pp.id_fertilizacion     AS id_programa,
    prod.nombre_comercial,
    pp.cantidad_producto    AS dosis,
    uni.abreviatura         AS unidad
FROM FACT_AREATECNICA_FERTILIZACION_PRODUCTOSPROGRAMA   pp
JOIN DIM_AREATECNICA_FITO_PRODUCTO                      prod ON prod.id   = pp.id_producto
LEFT JOIN DIM_GENERAL_UNIDAD                            uni  ON uni.id    = prod.id_unidad;


-- ------------------------------------------------------------
-- Vista 3: v_fertilizacion_sectores_programas
-- Una fila por sector x programa.
-- Usada en la app del casetero: agrupada por sector,
-- al expandir muestra cuartel y semana.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW v_fertilizacion_sectores_programas AS
SELECT
    sec.id                                          AS id_sector,
    sec.nombre                                      AS sector,
    prog.id                                         AS id_programa,
    prog.semana,
    prog.fecha_inicio,
    prog.fecha_termino,
    ceco.descripcion_ceco                           AS cuartel,
    suc.sucursal,
    GROUP_CONCAT(
        DISTINCT prod.nombre_comercial
        ORDER BY prod.nombre_comercial
        SEPARATOR ', '
    )                                               AS productos,
    ultimo.id_estado
FROM DIM_AREATECNICA_RIEGO_SECTOR                        sec
JOIN PIVOT_AREATECNICA_RIEGO_SECTORCUARTEL               psc  ON psc.id_sector       = sec.id
JOIN DIM_GENERAL_CECO                                    ceco ON ceco.id             = psc.id_cuartel
JOIN DIM_GENERAL_SUCURSAL                                suc  ON suc.id              = ceco.id_sucursal
JOIN FACT_AREATECNICA_FERTILIZACION_PROGRAMA             prog ON prog.id_cuartel     = ceco.id
JOIN FACT_AREATECNICA_FERTILIZACION_PRODUCTOSPROGRAMA    pp   ON pp.id_fertilizacion  = prog.id
JOIN DIM_AREATECNICA_FITO_PRODUCTO                       prod ON prod.id             = pp.id_producto
LEFT JOIN (
    SELECT c1.id_programa, c1.id_estado
    FROM FACT_AREATECNICA_FERTILIZACION_CONFIRMACION c1
    INNER JOIN (
        SELECT id_programa, MAX(hora_registro) AS ultima_hora
        FROM FACT_AREATECNICA_FERTILIZACION_CONFIRMACION
        GROUP BY id_programa
    ) c2 ON c1.id_programa = c2.id_programa
        AND c1.hora_registro = c2.ultima_hora
) ultimo ON ultimo.id_programa = prog.id
GROUP BY
    sec.id, sec.nombre,
    prog.id, prog.semana, prog.fecha_inicio, prog.fecha_termino,
    ceco.descripcion_ceco, suc.sucursal, ultimo.id_estado;


-- ------------------------------------------------------------
-- Verificación rápida
-- Descomentar y correr después de crear/actualizar las vistas
-- ------------------------------------------------------------
-- SELECT * FROM v_fertilizacion_papeletas LIMIT 20;
-- SELECT * FROM v_fertilizacion_productos_programa LIMIT 20;
-- SELECT * FROM v_fertilizacion_sectores_programas LIMIT 20;
