"""Mia · eval.banco04.segmentos — segmentación determinista del texto juzgado (§4.2.1, §10.2.7).

Regla del protocolo: TODO segmento se juzga. No hay exclusiones por forma:
  · el texto se parte primero por LÍNEAS; las filas de tabla se parten además por CELDA;
  · cada línea o celda se parte en oraciones con `verification.segment_sentences`, protegiendo
    las citas que detecta `verification.scan_citations` (ningún corte cae dentro de una cita);
  · títulos, viñetas, celdas y líneas cortas sin puntuación son segmentos como cualquier otro;
  · `verification._is_header` NO se usa para excluir nada (§4.2.1: tomaría por título «La deuda
    asciende a 999 millones»).

Una fila separadora de tabla (`|---|:---:|`) y una línea de pura puntuación también son
segmentos: el juez tiene que cubrirlos (con un átomo `no_afirmativa`/`no_aplica`).

El único carácter no blanco que puede quedar fuera de todo segmento es la barra `|` que delimita
celdas en una fila de tabla. `segmentar` lo comprueba y FALLA CERRADO si otro carácter queda
fuera (una segmentación que pierde texto escondería afirmaciones al juez).

Las posiciones se refieren al texto YA CEGADO (`ceguera.cegar_texto`) y con saltos `\\n`: es el
texto que ve el juez.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

# C11: copia vendorizada de verification.py@7b9aaa0; nunca `mia.agents.verification`.
from .evaluador_congelado import scan_citations, segment_sentences

PREFIJO_DIAGNOSTICO = "D"
PREFIJO_BORRADOR = "B"
SECCIONES = {PREFIJO_DIAGNOSTICO: "diagnostico", PREFIJO_BORRADOR: "borrador"}
_SEPARADOR_TABLA = set("|-: \t")


class SegmentacionIncompleta(RuntimeError):
    """Un carácter no blanco quedó fuera de todo segmento (falla cerrado)."""


@dataclass(frozen=True)
class Segmento:
    id: str
    seccion: str
    inicio: int          # posición en el texto de la sección (cegado, saltos \n)
    fin: int
    texto: str           # == texto_seccion[inicio:fin]; sin blancos al borde
    origen: str          # "linea" | "celda" | "separador_tabla"
    linea: int           # nº de línea (desde 1) en el texto de la sección

    def as_dict(self) -> dict:
        return asdict(self)


def normalizar_saltos(texto: str) -> str:
    return (texto or "").replace("\r\n", "\n").replace("\r", "\n")


def es_fila_tabla(linea: str) -> bool:
    s = linea.strip()
    return bool(s) and (s.startswith("|") or s.count("|") >= 2)


def es_separador_tabla(linea: str) -> bool:
    s = linea.strip()
    return es_fila_tabla(linea) and set(s) <= _SEPARADOR_TABLA and "-" in s


def _recortar(texto: str, inicio: int, fin: int) -> tuple[int, int] | None:
    while inicio < fin and texto[inicio].isspace():
        inicio += 1
    while fin > inicio and texto[fin - 1].isspace():
        fin -= 1
    return (inicio, fin) if fin > inicio else None


def _oraciones(texto: str, inicio: int, fin: int) -> list[tuple[int, int]]:
    """Oraciones de texto[inicio:fin], en posiciones absolutas del texto."""
    trozo = texto[inicio:fin]
    protegidos = [(c["start"], c["end"]) for c in scan_citations(trozo)]
    out: list[tuple[int, int]] = []
    for s, e in segment_sentences(trozo, protected_spans=protegidos):
        r = _recortar(texto, inicio + s, inicio + e)
        if r:
            out.append(r)
    return out


def _tramos_de_linea(texto: str, ini: int, fin: int) -> list[tuple[int, int, str]]:
    """(inicio, fin, origen) de los segmentos de una línea texto[ini:fin]."""
    linea = texto[ini:fin]
    if not linea.strip():
        return []
    if es_separador_tabla(linea):
        r = _recortar(texto, ini, fin)
        return [(r[0], r[1], "separador_tabla")] if r else []
    if es_fila_tabla(linea):
        out: list[tuple[int, int, str]] = []
        cortes = [ini + i for i, ch in enumerate(linea) if ch == "|"]
        limites = [ini - 1] + cortes + [fin]
        for a, b in zip(limites, limites[1:]):
            r = _recortar(texto, a + 1, b)
            if r:
                out.extend((s, e, "celda") for s, e in _oraciones(texto, r[0], r[1]))
        return out
    return [(s, e, "linea") for s, e in _oraciones(texto, ini, fin)]


def caracteres_no_cubiertos(texto: str, tramos: list[tuple[int, int]]) -> list[int]:
    """Posiciones de caracteres no blancos fuera de todo tramo, salvo la `|` de una fila de
    tabla (delimitador de celda)."""
    cubierto = bytearray(len(texto))
    for s, e in tramos:
        for i in range(max(0, s), min(len(texto), e)):
            cubierto[i] = 1
    fuera: list[int] = []
    pos = 0
    for linea in texto.split("\n"):
        tabla = es_fila_tabla(linea)
        for j, ch in enumerate(linea):
            i = pos + j
            if not ch.isspace() and not cubierto[i] and not (tabla and ch == "|"):
                fuera.append(i)
        pos += len(linea) + 1
    return fuera


def segmentar(texto: str, prefijo: str) -> list[Segmento]:
    """Segmenta el texto de UNA sección. Ids estables `D-0001`/`B-0001` en orden de aparición."""
    if prefijo not in SECCIONES:
        raise ValueError(f"prefijo desconocido: {prefijo!r}")
    texto = normalizar_saltos(texto)
    tramos: list[tuple[int, int, str, int]] = []
    pos = 0
    for n_linea, linea in enumerate(texto.split("\n"), 1):
        for s, e, origen in _tramos_de_linea(texto, pos, pos + len(linea)):
            tramos.append((s, e, origen, n_linea))
        pos += len(linea) + 1
    fuera = caracteres_no_cubiertos(texto, [(s, e) for s, e, _, _ in tramos])
    if fuera:
        muestra = "".join(texto[i] for i in fuera[:20])
        raise SegmentacionIncompleta(
            f"{len(fuera)} caracteres no blancos quedaron fuera de todo segmento: {muestra!r}")
    return [Segmento(id=f"{prefijo}-{i:04d}", seccion=SECCIONES[prefijo], inicio=s, fin=e,
                     texto=texto[s:e], origen=origen, linea=n_linea)
            for i, (s, e, origen, n_linea) in enumerate(tramos, 1)]


def segmentar_salida(diagnostico: str, borrador: str) -> list[Segmento]:
    """Segmentos del diagnóstico (D-…) seguidos de los del borrador (B-…)."""
    return segmentar(diagnostico, PREFIJO_DIAGNOSTICO) + segmentar(borrador, PREFIJO_BORRADOR)


def tokens_con_posicion(texto: str) -> list[list]:
    """Tabla de ayuda para el juez: [[inicio, "token"], …] por cada corrida no blanca.
    El fin de cada token es inicio + len(token). No forma parte del esquema de salida."""
    out: list[list] = []
    i, n = 0, len(texto)
    while i < n:
        if texto[i].isspace():
            i += 1
            continue
        j = i
        while j < n and not texto[j].isspace():
            j += 1
        out.append([i, texto[i:j]])
        i = j
    return out
