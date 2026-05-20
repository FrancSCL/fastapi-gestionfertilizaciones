-- ============================================================
-- Tabla de ajuste agronomico por cuartel/temporada/nutriente
-- ============================================================
-- factor = 1.0 -> sin ajuste (default)
-- factor = 0.8 -> aplicar 80%
-- factor = 1.2 -> aplicar 120%
-- ============================================================

CREATE TABLE IF NOT EXISTS FACT_AREATECNICA_FERTILIZACION_ANALISISAGRONOMICO (
  id              VARCHAR(45) NOT NULL,
  id_cuartel      INT NOT NULL,
  id_temporada    INT NOT NULL,
  id_responsable  INT NOT NULL,
  hora_registro   DATETIME NOT NULL,
  factor_n        FLOAT NOT NULL DEFAULT 1.0,
  factor_k        FLOAT NOT NULL DEFAULT 1.0,
  factor_p        FLOAT NOT NULL DEFAULT 1.0,
  factor_mg       FLOAT NOT NULL DEFAULT 1.0,
  factor_b        FLOAT NOT NULL DEFAULT 1.0,
  factor_ca       FLOAT NOT NULL DEFAULT 1.0,
  factor_zn       FLOAT NOT NULL DEFAULT 1.0,
  factor_mn       FLOAT NOT NULL DEFAULT 1.0,
  PRIMARY KEY (id),
  UNIQUE KEY uk_cuartel_temp (id_cuartel, id_temporada),
  KEY idx_temporada (id_temporada)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
