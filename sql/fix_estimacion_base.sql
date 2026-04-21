-- ============================================================
-- Fix: VISTA_FERTILIZACIONES_ESTIMACION_BASE
-- Solo se corrigen los cálculos de ton_estimadas y ton_ha.
-- La estructura de columnas no cambia.
--
-- Cambios:
--   ton_estimadas: antes = produccion_total_kg / 1000
--                  ahora = (produccion_total_kg / rendimiento) / 1000
--   ton_ha:        antes = produccion_total_kg / 1000
--                  ahora = (produccion_total_kg / rendimiento) / 1000 / sup_productiva
--
-- Se agrega LEFT JOIN a FACT_AREAPYC_PRODUCCION_RENDIMIENTOEMBALAJE
-- (registro más reciente por cuartel) solo para el cálculo.
-- Si no hay rendimiento para el cuartel, se usa 1 (sin cambio).
-- ============================================================

CREATE OR REPLACE VIEW VISTA_FERTILIZACIONES_ESTIMACION_BASE AS
SELECT
    sub.id_estimacion,
    sub.id_cuartel,
    sub.id_administrador,
    sub.id_tipoestimacion,
    sub.hora_registro,
    sub.embalaje_kg,
    sub.industria_kg,
    sub.embalaje_cajas,
    sub.produccion_total_kg,
    ROUND(sub.produccion_total_kg / COALESCE(rend.rendimiento, 1) / 1000, 2)                      AS ton_estimadas,
    ROUND(sub.produccion_total_kg / COALESCE(rend.rendimiento, 1) / 1000, 2)                                  AS ton_ha,
    sub.cuartel,
    sub.id_sucursal,
    sub.id_variedad,
    sub.id_especie,
    sub.especie,
    sub.portainjerto,
    sub.sup_productiva,
    sub.equivalencia
FROM (
    SELECT
        e.id                                                                          AS id_estimacion,
        e.id_cuartel,
        e.id_administrador,
        e.id_tipoestimacion,
        e.hora_registro,
        COALESCE(e.embalaje_kg,    0)                                                 AS embalaje_kg,
        COALESCE(e.industria_kg,   0)                                                 AS industria_kg,
        COALESCE(e.embalaje_cajas, 0)                                                 AS embalaje_cajas,
        (CASE
            WHEN esp.especie LIKE '%erez%'
                THEN COALESCE(e.embalaje_kg, 0)
            WHEN e.id_cuartel IN (5120101, 2021501, 3010101, 3010201)
                THEN COALESCE(e.industria_kg, 0)
            ELSE COALESCE(e.embalaje_cajas, 0) * COALESCE(esp.equivalencia, 1)
        END)                                                                          AS produccion_total_kg,
        c.descripcion_ceco                                                            AS cuartel,
        c.id_sucursal,
        c.id_variedad,
        esp.id                                                                        AS id_especie,
        esp.especie,
        c.portainjerto,
        c.sup_productiva,
        esp.equivalencia,
        ROW_NUMBER() OVER (PARTITION BY e.id_cuartel ORDER BY e.hora_registro DESC)  AS rn
    FROM FACT_AREAPYC_PRODUCCION_ESTIMACIONADMINISTRADORES e
    JOIN DIM_GENERAL_CECO     c   ON c.id   = e.id_cuartel
    JOIN DIM_GENERAL_VARIEDAD v   ON v.id   = c.id_variedad
    JOIN DIM_GENERAL_ESPECIE  esp ON esp.id = v.id_especie
) sub
LEFT JOIN (
    SELECT r1.id_cuartel, r1.rendimiento
    FROM FACT_AREAPYC_PRODUCCION_RENDIMIENTOEMBALAJE r1
    INNER JOIN (
        SELECT id_cuartel, MAX(fecha) AS ultima_fecha
        FROM FACT_AREAPYC_PRODUCCION_RENDIMIENTOEMBALAJE
        GROUP BY id_cuartel
    ) r2 ON r1.id_cuartel = r2.id_cuartel
        AND r1.fecha      = r2.ultima_fecha
) rend ON rend.id_cuartel = sub.id_cuartel
WHERE sub.rn = 1;


-- ============================================================
-- Verificación
-- ============================================================
-- SELECT id_cuartel, cuartel, sup_productiva,
--        produccion_total_kg, ton_estimadas, ton_ha
-- FROM VISTA_FERTILIZACIONES_ESTIMACION_BASE
-- LIMIT 20;
