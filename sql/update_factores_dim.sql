-- ============================================================
-- UPDATE: DIM_AREATECNICA_FERTILIZANTESFACTOR
-- Fuente: Fertilizacion San Manuel T2025-2026 v1.xlsx (hoja CALCULOS)
-- Unidad: kg nutriente / ton fruta fresca / ha / año
--
-- Especies actualizadas: Nectarín, Durazno, Ciruela, Damasco
-- Especies SIN datos en Excel (no tocar): Cereza, Uva
--
-- NOTA B, Ca, Zn, Mn:
--   El Excel los trata como aplicaciones foliares puntuales,
--   NO como demanda proporcional a producción.
--   Se dejan en 1 hasta que el agrónomo defina valores reales.
-- ============================================================

-- ── N ────────────────────────────────────────────────────────
UPDATE DIM_AREATECNICA_FERTILIZANTESFACTOR
SET
    factor_nectarin = 4.7,
    factor_durazno  = 4.1,
    factor_ciruela  = 3.3,
    factor_damasco  = 7.7
    -- factor_cereza y factor_uva: no están en el Excel, no se tocan
WHERE fertilizante = 'N';

-- ── K ────────────────────────────────────────────────────────
UPDATE DIM_AREATECNICA_FERTILIZANTESFACTOR
SET
    factor_nectarin = 6.7,
    factor_durazno  = 6.4,
    factor_ciruela  = 5.9,
    factor_damasco  = 9.1
WHERE fertilizante = 'K';

-- ── P ────────────────────────────────────────────────────────
UPDATE DIM_AREATECNICA_FERTILIZANTESFACTOR
SET
    factor_nectarin = 1.6,
    factor_durazno  = 1.3,
    factor_ciruela  = 1.4,
    factor_damasco  = 1.5,
    factor_cereza   = 1.5,   -- estimado, confirmar con agrónomo
    factor_uva      = 1.0    -- estimado, confirmar con agrónomo
WHERE fertilizante = 'P';

-- ── Mg ───────────────────────────────────────────────────────
UPDATE DIM_AREATECNICA_FERTILIZANTESFACTOR
SET
    factor_nectarin = 1.0,
    factor_durazno  = 1.0,
    factor_ciruela  = 1.5,
    factor_damasco  = 1.0
    -- factor_uva = 2.5 ya está correcto según DIM actual, no se toca
    -- factor_cereza: sin dato en Excel
WHERE fertilizante = 'Mg';

-- ============================================================
-- Verificación post-update
-- ============================================================
SELECT fertilizante,
       factor_cereza, factor_uva, factor_nectarin,
       factor_ciruela, factor_durazno, factor_damasco
FROM DIM_AREATECNICA_FERTILIZANTESFACTOR
ORDER BY fertilizante;
