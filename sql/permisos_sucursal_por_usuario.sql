-- ============================================================
-- Permisos de sucursales por usuario (rol = 'user')
-- ============================================================
-- Los usuarios con rol = 'admin' NO necesitan filas aqui: ven todas.
-- Los usuarios con rol = 'user' ven solo las sucursales listadas.
-- Si un user no tiene filas, ve todo igual (default permisivo para
-- no dejar gente sin acceso por accidente).
-- ============================================================
-- Ids de sucursales productivas:
--   2 = SAN MANUEL
--   3 = SANTA VICTORIA
--   4 = CULLIPEUMO
--   5 = CAMPO CHOCALAN
--   7 = SANTA INES
--   8 = MAITEN GIGANTE
--   9 = HOSPITAL
--   27 = CAMPO ITAHUE
-- ============================================================

CREATE TABLE IF NOT EXISTS z_usuario_sucursal (
  id_usuario  INT NOT NULL,
  id_sucursal INT NOT NULL,
  PRIMARY KEY (id_usuario, id_sucursal),
  KEY idx_usuario (id_usuario)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

SET SQL_SAFE_UPDATES = 0;

-- Ejemplo: asignar SAN MANUEL (2) y HOSPITAL (9) a user1
-- INSERT IGNORE INTO z_usuario_sucursal (id_usuario, id_sucursal)
-- SELECT id, 2 FROM z_usuarios_test WHERE usuario = 'user1';
-- INSERT IGNORE INTO z_usuario_sucursal (id_usuario, id_sucursal)
-- SELECT id, 9 FROM z_usuarios_test WHERE usuario = 'user1';

-- Verificacion
SELECT u.usuario, u.rol, s.id AS id_sucursal, s.sucursal
FROM z_usuarios_test u
LEFT JOIN z_usuario_sucursal us ON us.id_usuario = u.id
LEFT JOIN DIM_GENERAL_SUCURSAL s ON s.id = us.id_sucursal
ORDER BY u.id, s.sucursal;

SET SQL_SAFE_UPDATES = 1;
