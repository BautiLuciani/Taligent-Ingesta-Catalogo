"""Pruebas sin IA de revisar_key (semana 6, paso 0): qué key usa el sistema de verdad."""
from verificar_entorno import mostrar_key, revisar_key

KEY_ENV = "sk-ant-api03-AAAAAAAAAAAAAAAAAAAA-1111"
KEY_WINDOWS = "sk-ant-usr-BBBBBBBBBBBBBBBBBBBBBB-2222"

fallas = 0


def probar(nombre, condicion):
    global fallas
    print(("OK   " if condicion else "FALLA") + " " + nombre)
    if not condicion:
        fallas += 1


ok, msj = revisar_key(None, KEY_ENV)
probar("solo .env -> OK", ok and "sale del .env" in msj)

ok, msj = revisar_key(KEY_ENV, KEY_ENV)
probar("Windows igual al .env -> OK", ok and "no molesta" in msj)

ok, msj = revisar_key(KEY_WINDOWS, KEY_ENV)
probar("Windows distinta -> ERROR", not ok and "le gana al .env" in msj)
probar("el error dice cómo borrarla", "SetEnvironmentVariable" in msj)
probar("el error no muestra ninguna key entera", KEY_WINDOWS not in msj and KEY_ENV not in msj)
probar("el error muestra las últimas 4 de cada una", "2222" in msj and "1111" in msj)

ok, msj = revisar_key(KEY_WINDOWS, None)
probar(".env sin key pero Windows con una -> ERROR", not ok and "el .env no tiene" in msj)

ok, msj = revisar_key(None, None)
probar("sin ninguna key -> ERROR", not ok and "falta ANTHROPIC_API_KEY" in msj)

ok, msj = revisar_key(None, "")
probar("key vacía en el .env -> ERROR", not ok)

probar("mostrar_key de una key corta no la muestra", mostrar_key("abc") == "(3 caracteres)")

print()
print("Resultado: todo OK" if fallas == 0 else f"Resultado: {fallas} FALLAS")
