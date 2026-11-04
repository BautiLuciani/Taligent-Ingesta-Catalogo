"""Gráfico de carriles del paso 8: qué tanda corrió cada fichador y cuándo, con 1 fichador y con 3.

Lee salida/medicion_fichas_1.json y salida/medicion_fichas_3.json (las deja medir_paralelo.py) y arma
salida/carriles.svg: una fila por fichador, cada tanda como una barra del color de su proveedor, y las dos corridas
una arriba de la otra en la MISMA escala de tiempo. Sin dependencias: un SVG es texto y se abre en el navegador.

Correr: python carriles.py      (gratis, instantáneo)
"""
import json
import sys
from pathlib import Path

CARPETA_SALIDA = Path(__file__).parent / "salida"
COLORES = {"P03": "#2a78d6", "P07": "#2e9e6b", "P01": "#d9822b", "P05": "#b04fc4", "P09": "#d24a5a"}
NOMBRES = {"P03": "Litoral", "P07": "Limpieza Hogar Sur", "P01": "Lab. Andes", "P05": "Dermalab", "P09": "Natural Vida"}
ANCHO, IZQUIERDA, ALTO_CARRIL = 1100, 110, 34


def dibujar(mediciones: dict[int, dict]) -> str:
    """Arma el SVG. mediciones: {fichadores: la medición de esa corrida (con 'tandas', cada una con su 'fichador')}."""
    maximo = max(t["fin"] for m in mediciones.values() for t in m["tandas"])
    escala = (ANCHO - IZQUIERDA - 30) / maximo
    partes, y = [], 30
    partes.append(f'<text x="{IZQUIERDA}" y="{y}" font-size="18" font-weight="bold">Fichas en paralelo: '
                  'cada barra es una tanda de 10 productos</text>')
    y += 20
    for fichadores, medicion in sorted(mediciones.items()):
        y += 30
        partes.append(f'<text x="{IZQUIERDA}" y="{y}" font-size="15" font-weight="bold">{fichadores} fichador'
                      f'{"es" if fichadores > 1 else ""} a la vez: {medicion["segundos"]:.0f} s · '
                      f'US$ {medicion["costo_usd"]:.3f}</text>')
        y += 12
        for carril in range(1, fichadores + 1):
            partes.append(f'<text x="{IZQUIERDA - 10}" y="{y + 22}" font-size="13" text-anchor="end">fichador {carril}</text>')
            partes.append(f'<rect x="{IZQUIERDA}" y="{y + 2}" width="{ANCHO - IZQUIERDA - 30}" height="{ALTO_CARRIL - 4}" '
                          'fill="#f2f2f2"/>')
            for tanda in (t for t in medicion["tandas"] if t["fichador"] == carril):
                x, ancho = IZQUIERDA + tanda["inicio"] * escala, max(1.0, (tanda["fin"] - tanda["inicio"]) * escala)
                partes.append(f'<rect x="{x:.1f}" y="{y + 4}" width="{ancho:.1f}" height="{ALTO_CARRIL - 8}" rx="3" '
                              f'fill="{COLORES.get(tanda["proveedor_id"], "#888")}" stroke="white"/>')
                if ancho > 38:
                    partes.append(f'<text x="{x + ancho / 2:.1f}" y="{y + 22}" font-size="11" fill="white" '
                                  f'text-anchor="middle">{tanda["proveedor_id"]} {tanda["desde"]}</text>')
            y += ALTO_CARRIL
    # Eje de tiempo (cada 60 s) y leyenda
    y += 10
    for segundo in range(0, int(maximo) + 1, 60):
        x = IZQUIERDA + segundo * escala
        partes.append(f'<line x1="{x:.1f}" y1="{y}" x2="{x:.1f}" y2="{y + 6}" stroke="#555"/>')
        partes.append(f'<text x="{x:.1f}" y="{y + 20}" font-size="11" text-anchor="middle">{segundo} s</text>')
    y += 45
    x = IZQUIERDA
    for proveedor_id, color in COLORES.items():
        partes.append(f'<rect x="{x}" y="{y - 11}" width="14" height="14" fill="{color}"/>')
        partes.append(f'<text x="{x + 20}" y="{y}" font-size="12">{proveedor_id} {NOMBRES[proveedor_id]}</text>')
        x += 190
    alto = y + 20
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{ANCHO}" height="{alto}" viewBox="0 0 {ANCHO} {alto}" '
            f'font-family="Segoe UI, Arial, sans-serif"><rect width="100%" height="100%" fill="white"/>'
            + "".join(partes) + "</svg>")


def main():
    mediciones = {}
    for fichadores in (1, 3):
        ruta = CARPETA_SALIDA / f"medicion_fichas_{fichadores}.json"
        if not ruta.exists():
            sys.exit(f"✖ Falta salida/{ruta.name}: corré primero python medir_paralelo.py")
        medicion = json.loads(ruta.read_text(encoding="utf-8"))
        if any("fichador" not in t for t in medicion["tandas"]):
            sys.exit(f"✖ salida/{ruta.name} es de antes del paso 8 (no dice qué fichador corrió cada tanda): "
                     "corré python medir_paralelo.py")
        mediciones[fichadores] = medicion
    ruta = CARPETA_SALIDA / "carriles.svg"
    ruta.write_text(dibujar(mediciones), encoding="utf-8")
    print(f"Gráfico en salida/{ruta.name} (abrilo con el navegador)")


if __name__ == "__main__":
    main()