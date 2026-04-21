"""
Genera PDFs de prueba para papeleta_bodega y papeleta_bodega_pro
sin necesidad de conectarse a la base de datos.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import date
from api.pdf_service import build_pdf_bodega

# ── DATOS FALSOS REALISTAS ────────────────────────────────────────────────────

programas = [
    # ARRA 15 — 3 cuarteles
    {"id": "p001", "variedad": "ARRA 15", "cuartel_nombre": "ARRA 15 C 16 HO",
     "id_cuartel": 1, "sup_productiva": 2.60, "sucursal": "HO", "etapa": "Postcosecha",
     "etiqueta_semana": "S-18-2026", "sem_fecha_inicio": date(2026, 4, 27), "sem_fecha_fin": date(2026, 5, 3)},
    {"id": "p002", "variedad": "ARRA 15", "cuartel_nombre": "ARRA 15 C 17 HO",
     "id_cuartel": 2, "sup_productiva": 2.30, "sucursal": "HO", "etapa": "Postcosecha",
     "etiqueta_semana": "S-18-2026", "sem_fecha_inicio": date(2026, 4, 27), "sem_fecha_fin": date(2026, 5, 3)},
    {"id": "p003", "variedad": "ARRA 15", "cuartel_nombre": "ARRA 15 C 18 HO",
     "id_cuartel": 3, "sup_productiva": 3.10, "sucursal": "HO", "etapa": "Postcosecha",
     "etiqueta_semana": "S-18-2026", "sem_fecha_inicio": date(2026, 4, 27), "sem_fecha_fin": date(2026, 5, 3)},
    # AUTUMN CRISP — 2 cuarteles
    {"id": "p004", "variedad": "AUTUMN CRISP", "cuartel_nombre": "AUTUMN CRISP C 1 HO",
     "id_cuartel": 4, "sup_productiva": 3.30, "sucursal": "HO", "etapa": "Cuaja",
     "etiqueta_semana": "S-18-2026", "sem_fecha_inicio": date(2026, 4, 27), "sem_fecha_fin": date(2026, 5, 3)},
    {"id": "p005", "variedad": "AUTUMN CRISP", "cuartel_nombre": "AUTUMN CRISP C 4 HO",
     "id_cuartel": 5, "sup_productiva": 6.60, "sucursal": "HO", "etapa": "Cuaja",
     "etiqueta_semana": "S-18-2026", "sem_fecha_inicio": date(2026, 4, 27), "sem_fecha_fin": date(2026, 5, 3)},
    # CAKE BELLA — 2 cuarteles
    {"id": "p006", "variedad": "CAKE BELLA", "cuartel_nombre": "CAKE BELLA B 1 A SM",
     "id_cuartel": 6, "sup_productiva": 3.30, "sucursal": "SM", "etapa": "Fruto 10mm",
     "etiqueta_semana": "S-18-2026", "sem_fecha_inicio": date(2026, 4, 27), "sem_fecha_fin": date(2026, 5, 3)},
    {"id": "p007", "variedad": "CAKE BELLA", "cuartel_nombre": "CAKE BELLA C 28 IT",
     "id_cuartel": 7, "sup_productiva": 6.96, "sucursal": "IT", "etapa": "Fruto 10mm",
     "etiqueta_semana": "S-18-2026", "sem_fecha_inicio": date(2026, 4, 27), "sem_fecha_fin": date(2026, 5, 3)},
    # SANTINA — 2 cuarteles
    {"id": "p008", "variedad": "SANTINA", "cuartel_nombre": "SANTINA 1 CHOLQUI",
     "id_cuartel": 8, "sup_productiva": 5.00, "sucursal": "CH", "etapa": "Endurecimiento",
     "etiqueta_semana": "S-18-2026", "sem_fecha_inicio": date(2026, 4, 27), "sem_fecha_fin": date(2026, 5, 3)},
    {"id": "p009", "variedad": "SANTINA", "cuartel_nombre": "SANTINA 2SAM IT",
     "id_cuartel": 9, "sup_productiva": 5.63, "sucursal": "IT", "etapa": "Endurecimiento",
     "etiqueta_semana": "S-18-2026", "sem_fecha_inicio": date(2026, 4, 27), "sem_fecha_fin": date(2026, 5, 3)},
]

productos_map = {
    # ARRA 15 — urea + muriato K + ac fosforico
    "p001": [{"nombre_comercial": "UREA",        "dosis_ha": 50},
             {"nombre_comercial": "MURIATO DE K", "dosis_ha": 50}],
    "p002": [{"nombre_comercial": "UREA",        "dosis_ha": 50},
             {"nombre_comercial": "MURIATO DE K", "dosis_ha": 50}],
    "p003": [{"nombre_comercial": "UREA",        "dosis_ha": 50},
             {"nombre_comercial": "MURIATO DE K", "dosis_ha": 50},
             {"nombre_comercial": "AC FOSFORICO", "dosis_ha": 20}],
    # AUTUMN CRISP — urea + nitrato K
    "p004": [{"nombre_comercial": "UREA",          "dosis_ha": 60},
             {"nombre_comercial": "NITRATO DE K",   "dosis_ha": 40}],
    "p005": [{"nombre_comercial": "UREA",          "dosis_ha": 60},
             {"nombre_comercial": "NITRATO DE K",   "dosis_ha": 40},
             {"nombre_comercial": "SULFATO DE MG",  "dosis_ha": 30}],
    # CAKE BELLA
    "p006": [{"nombre_comercial": "UREA",           "dosis_ha": 50},
             {"nombre_comercial": "NITRATO DE K",    "dosis_ha": 50},
             {"nombre_comercial": "AC FOSFORICO",    "dosis_ha": 20}],
    "p007": [{"nombre_comercial": "UREA",           "dosis_ha": 50},
             {"nombre_comercial": "NITRATO DE K",    "dosis_ha": 50},
             {"nombre_comercial": "AC FOSFORICO",    "dosis_ha": 20}],
    # SANTINA
    "p008": [{"nombre_comercial": "NITRATO CALCIO SOLUBLE", "dosis_ha": 100},
             {"nombre_comercial": "AC FOSFORICO",            "dosis_ha": 15}],
    "p009": [{"nombre_comercial": "NITRATO CALCIO SOLUBLE", "dosis_ha": 100}],
}

sectores_map = {
    # ARRA 15 C 16 HO — 2 sectores
    1: [{"sector_nombre": "EP/1", "superficie": 1.30},
        {"sector_nombre": "EP/2", "superficie": 1.30}],
    # ARRA 15 C 17 HO — 2 sectores
    2: [{"sector_nombre": "EP/3", "superficie": 1.15},
        {"sector_nombre": "EP/4", "superficie": 1.15}],
    # ARRA 15 C 18 HO — 3 sectores
    3: [{"sector_nombre": "EP/5", "superficie": 1.03},
        {"sector_nombre": "EP/6", "superficie": 1.03},
        {"sector_nombre": "EP/7", "superficie": 1.04}],
    # AUTUMN CRISP C 1 HO — 1 sector
    4: [{"sector_nombre": "EP/8", "superficie": 3.30}],
    # AUTUMN CRISP C 4 HO — 2 sectores
    5: [{"sector_nombre": "EP/9",  "superficie": 3.30},
        {"sector_nombre": "EP/10", "superficie": 3.30}],
    # CAKE BELLA B 1 A SM — sin sectores (usa sup total)
    # CAKE BELLA C 28 IT — 2 sectores
    7: [{"sector_nombre": "EP/1", "superficie": 3.48},
        {"sector_nombre": "EP/2", "superficie": 3.48}],
    # SANTINA 1 CHOLQUI — 1 sector
    8: [{"sector_nombre": "EP/1", "superficie": 5.00}],
    # SANTINA 2SAM IT — 2 sectores
    9: [{"sector_nombre": "EP/3", "superficie": 2.81},
        {"sector_nombre": "EP/4", "superficie": 2.82}],
}

# ── GENERAR ───────────────────────────────────────────────────────────────────

out_dir = os.path.join(os.path.dirname(__file__), "sql")

print("Generando versión estándar...")
pdf_std = build_pdf_bodega("S-18-2026", programas, productos_map, sectores_map, pro=False)
path_std = os.path.join(out_dir, "test_bodega_standard.pdf")
with open(path_std, "wb") as f:
    f.write(pdf_std)
print(f"  OK: {path_std}")

print("Generando versión pro...")
pdf_pro = build_pdf_bodega("S-18-2026", programas, productos_map, sectores_map, pro=True)
path_pro = os.path.join(out_dir, "test_bodega_pro.pdf")
with open(path_pro, "wb") as f:
    f.write(pdf_pro)
print(f"  OK: {path_pro}")

print("Listo.")
