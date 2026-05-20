-- ============================================================
-- Roles en z_usuarios_test
-- ============================================================
-- Agrega columna `rol` con valores 'user' o 'admin'.
-- Solo los usuarios con rol = 'admin' veran y podran acceder a
-- las secciones de Parametros y Productos.
-- ============================================================

SET SQL_SAFE_UPDATES = 0;

ALTER TABLE z_usuarios_test
  ADD COLUMN rol VARCHAR(20) NOT NULL DEFAULT 'user' AFTER `contraseña`;

-- Marcar como admin a los usuarios que correspondan.
-- Editar segun los 4 usuarios que tendran acceso a configuracion.
-- Ejemplo:
UPDATE z_usuarios_test SET rol = 'admin' WHERE usuario IN ('fsoto');

-- Verificacion
SELECT id, usuario, nombre, apellido, rol FROM z_usuarios_test ORDER BY rol DESC, usuario;

SET SQL_SAFE_UPDATES = 1;
