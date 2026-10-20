"""Pruebas de cuentas.py con casos reales de los proveedores. Correr: python probar_cuentas.py"""
from cuentas import (
    calcular_digito_verificador,
    cargar_abreviaturas,
    convertir_contenido,
    convertir_numero,
    expandir_abreviaturas,
    normalizar_gtin,
)

errores = 0


def chequear(origen, obtenido, esperado):
    """Compara lo obtenido con lo esperado e imprime OK o MAL."""
    global errores
    if obtenido == esperado:
        print(f"[OK ] {origen}")
    else:
        errores += 1
        print(f"[MAL] {origen}: esperado {esperado!r}, obtenido {obtenido!r}")


print("--- calcular_digito_verificador ---")
chequear("LT-3303 Litoral, válido", calcular_digito_verificador("779346961684"), 6)
chequear("RIV-1206 Rivera, válido", calcular_digito_verificador("779713744403"), 8)
chequear("RIV-1203 Rivera, el archivo dice 2", calcular_digito_verificador("779309218906"), 9)

print("--- normalizar_gtin ---")
chequear("LT-3303 Litoral, GTIN normal", normalizar_gtin("7793469616846"), ("7793469616846", None))
chequear("RIV-1206 Rivera, con guiones", normalizar_gtin("779-7137-44403-8"), ("7797137444038", None))
chequear("IN7003 Norte, UPC de 12", normalizar_gtin("229962606567"), ("0229962606567", None))
chequear("LT-3357 Litoral, vacío", normalizar_gtin(""), (None, "gtin_faltante"))
chequear("Celda sin valor (None)", normalizar_gtin(None), (None, "gtin_faltante"))
chequear("NV-203 Natural Vida, frase", normalizar_gtin("se lo paso la semana que viene"), (None, "gtin_faltante"))
chequear("RIV-1203 Rivera, dígito mal", normalizar_gtin("7793092189062"), (None, "gtin_invalido"))
chequear("Inventado, 8 dígitos", normalizar_gtin("77934696"), (None, "gtin_invalido"))

print("--- convertir_numero ---")
chequear("LT-3303 precio con coma", convertir_numero("68,91"), 68.91)
chequear("LT-3345 contenido 0,25", convertir_numero("0,25"), 0.25)
chequear("Entero", convertir_numero("90"), 90.0)
chequear("Punto de miles (estándar)", convertir_numero("1.000"), 1000.0)
chequear("Miles y decimales", convertir_numero("1.234,56"), 1234.56)
chequear("IN7003 Norte, en inglés", convertir_numero("4.8", separador_decimal="."), 4.8)
chequear("Vacío", convertir_numero(""), None)
chequear("Basura", convertir_numero("abc"), None)

print("--- convertir_contenido ---")
chequear("LT-3345 0,25 LT", convertir_contenido(0.25, "LT"), (250, "ML"))
chequear("LT-3312 0,5 LT", convertir_contenido(0.5, "LT"), (500, "ML"))
chequear("LT-3303 90 GR", convertir_contenido(90, "GR"), (90, "G"))
chequear("GRS", convertir_contenido(125, "GRS"), (125, "G"))
chequear("LT-3450 100 UNID", convertir_contenido(100, "UNID"), (100, "UN"))
chequear("CC es ML", convertir_contenido(250, "CC"), (250, "ML"))
chequear("Minúscula con punto", convertir_contenido(200, "ml."), (200, "ML"))
chequear("IN7003 Norte 4.8 fl oz", convertir_contenido(4.8, "fl oz"), (142, "ML"))
chequear("Rivera 0,5 KG", convertir_contenido(0.5, "KG"), (500, "G"))
chequear("Redondeo .5 sube", convertir_contenido(12.5, "G"), (13, "G"))
chequear("Unidad desconocida", convertir_contenido(3, "PAQ"), (None, None))
chequear("Sin cantidad", convertir_contenido(None, "ML"), (None, None))

print("--- expandir_abreviaturas ---")
ABREV = cargar_abreviaturas()
chequear("Se leyeron las 18 del vocabulario", len(ABREV), 18)
chequear("LT-3303 BLANQ.", expandir_abreviaturas("PASTA DENTAL BLANQ.", ABREV), "PASTA DENTAL BLANQUEADORA")
chequear("LT-3333 Title Case", expandir_abreviaturas("Pasta Dental Blanq.", ABREV), "PASTA DENTAL BLANQUEADORA")
chequear("LT-3417 S/", expandir_abreviaturas("ENJUAGUE BUCAL S/ ALCOHOL", ABREV), "ENJUAGUE BUCAL SIN ALCOHOL")
chequear("LT-3447 ANTIBAC.", expandir_abreviaturas("JABON ANTIBAC.", ABREV), "JABON ANTIBACTERIAL")
chequear("SKU100140 varias juntas", expandir_abreviaturas("DESOD. AER. BRISA S/ PERF. 150CC", ABREV),
        "DESODORANTE AEROSOL BRISA SIN PERFUME 150CC")
chequear("SKU100077 dos palabras", expandir_abreviaturas("TRAT. CAP. HIGIENOL REPARACION 250GR", ABREV),
        "TRATAMIENTO CAPILAR HIGIENOL REPARACION 250GR")
chequear("SKU100679 REP/CION no se toca", expandir_abreviaturas("TRAT. CAP. NATIVA REP/CION 500GR", ABREV),
        "TRATAMIENTO CAPILAR NATIVA REP/CION 500GR")
chequear("Todo junto S/ALCOHOL", expandir_abreviaturas("S/ALCOHOL", ABREV), "SIN ALCOHOL")
chequear("Sin abreviaturas", expandir_abreviaturas("Hisopos", ABREV), "HISOPOS")

print(f"\nResultado: {'todo OK' if errores == 0 else f'{errores} con error'}")
