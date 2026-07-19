"""Mia · ingest.extract — extrae texto de PDF / Word / texto plano (Fase 3 backend).

PDF → PyMuPDF (`fitz`); Word `.docx` → `python-docx`; `.txt`/`.md` → utf-8. Import perezoso
de las librerías pesadas: solo se cargan al subir un documento de ese tipo.

Fallback de OCR LOCAL (bloque 3a): en litigio la mayoría de expedientes reales son PDF
ESCANEADOS (imagen sin capa de texto). Antes MIA quedaba CIEGA ante ellos SIN AVISAR.
Ahora, página a página, si un PDF trae páginas escaneadas se rasterizan y se leen con
reconocimiento óptico local (`ocr.py`) — el documento nunca sale del servidor. El texto
leído por OCR se marca con honestidad para que el abogado y el propio motor lo sepan al
citar. Todo es fail-soft: ni el límite, ni una página corrupta, ni la ausencia del motor
tumban la ingesta.

Las funciones de extracción son SÍNCRONAS y CPU-pesadas (el OCR puede tardar minutos). Los
llamadores dentro de un event loop DEBEN usar las variantes `*_async` (delegan a
`asyncio.to_thread`) para no congelar el loop — ver revisión adversarial M1.
"""
from __future__ import annotations

import asyncio
import io
import time

from . import ocr

# ── Parámetros del fallback de OCR (constantes de módulo → testeables por override) ──
# Una página es CANDIDATA a OCR si su texto extraíble tiene menos de este número de
# caracteres alfanuméricos Y la página contiene imágenes (típico de un escaneo).
MIN_ALNUM_PER_PAGE = 40
# Rasterización de la página antes del OCR: dpi y escala de grises (menos ruido, más rápido).
OCR_DPI = 220
# Cota de RAM por página (M2): una página con MediaBox descomunal (p. ej. 200×200 pulgadas)
# rasterizaría a un pixmap de gigabytes. Se limita el ÁREA en píxeles del raster; si a
# `OCR_DPI` se supera el presupuesto, se baja el dpi efectivo proporcionalmente hasta caber.
# 25 megapíxeles ≈ una hoja A2 a 220 dpi — holgado para cualquier folio real.
OCR_MAX_MEGAPIXELS = 25.0
# Piso de dpi: si ni siquiera a este dpi la página cabe en el presupuesto, se salta anotando
# (una página que a 72 dpi aún pasa de 25 Mpx no es un folio: es un plano o un póster).
OCR_MIN_DPI = 72
# Cuerpo real mínimo (alfanuméricos) para considerar que el documento SÍ tiene contenido
# legible (M3). Por debajo de esto el "texto" son solo anotaciones → has_body=False.
_MIN_BODY_ALNUM = 10
# Fail-soft: tope de páginas leídas por OCR por documento. Las siguientes se omiten y se anota.
MAX_OCR_PAGES = 150
# Fail-soft: presupuesto de tiempo de OCR por documento (segundos). Corte honesto al superarlo.
# NOTA (M2): el corte por tiempo es ENTRE páginas; una página individual descomunal no se
# corta a mitad de OCR (no hay una forma barata de hacerlo con rapidocr) — por eso la cota de
# dimensiones de arriba evita que una sola página consuma toda la RAM/tiempo.
OCR_TIME_BUDGET_S = 600.0

# Anotaciones EN LLANO (sin jerga técnica, a propósito — las lee el abogado).
OCR_HONESTY_NOTE = ("[Este documento se leyó con reconocimiento óptico (era un escaneo); "
                    "puede contener errores de lectura.]")
OCR_UNAVAILABLE_NOTE = "[Documento escaneado: este servidor no tiene lectura óptica instalada]"
# Marcador POR SEGMENTO (MEN1): se intercala antes de cada bloque contiguo de páginas leídas
# por OCR, para que el troceo (1200 chars) arrastre la advertencia CERCA del contenido óptico
# (no solo en el chunk 0). Se MANTIENE además la nota global al inicio del documento.
OCR_SEGMENT_NOTE = "[Texto leído por reconocimiento óptico — puede contener errores:]"


def _ocr_truncation_note(first_omitted_page: int) -> str:
    return (f"[Páginas {first_omitted_page}+ sin leer: el documento escaneado supera el "
            f"límite de lectura óptica]")


def _ocr_too_large_note(page_num: int) -> str:
    return f"[Página {page_num} sin leer: demasiado grande para la lectura óptica]"


def _alnum_count(text: str) -> int:
    return sum(1 for c in text if c.isalnum())


def extract_text(filename: str, data: bytes) -> str:
    """Devuelve el texto plano de un documento subido. Lanza si el tipo no es soportado.

    Contrato retrocompatible: SIEMPRE devuelve `str` (los llamadores viejos no cambian).
    Para PDFs escaneados el texto ya viene con la anotación de honestidad de OCR.

    SÍNCRONA y CPU-pesada: dentro de un event loop usar `extract_text_async`."""
    text, _meta = extract_text_detailed(filename, data)
    return text


def extract_text_detailed(filename: str, data: bytes) -> tuple[str, dict]:
    """Como `extract_text` pero devuelve además metadata de OCR para quien la quiera.

    Retorna `(texto, meta)` con:
      - `ocr_pages` (int): páginas donde corrió OCR (0 ⇒ no hubo lectura óptica).
      - `total_pages` (int).
      - `truncated` (bool): se cortó por tope de páginas/tiempo.
      - `has_body` (bool): el documento tiene CUERPO legible más allá de las anotaciones
        (M3). False cuando el texto útil queda vacío/casi vacío — p. ej. un escaneo sin
        motor de OCR, o un OCR que no leyó nada. Los ingestores lo usan para NO guardar un
        placeholder como si fuera un documento válido.
      - `ocr_unavailable` (bool): el documento parecía escaneado pero este servidor no tiene
        motor de OCR, y por eso quedó sin cuerpo. Distingue el mensaje al abogado.

    SÍNCRONA y CPU-pesada: dentro de un event loop usar `extract_text_detailed_async`."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return _extract_pdf(data)
    if name.endswith(".docx"):
        import docx
        d = docx.Document(io.BytesIO(data))
        text = "\n".join(p.text for p in d.paragraphs).strip()
        # .docx no tiene paginado estable → sin folios (mapa vacío ⇒ folio NULL). Nunca inventar.
        return text, {"ocr_pages": 0, "total_pages": 0, "truncated": False,
                      "has_body": _alnum_count(text) >= _MIN_BODY_ALNUM,
                      "ocr_unavailable": False, "folio_map": []}
    if name.endswith((".txt", ".md")):
        text = data.decode("utf-8", errors="replace").strip()
        # texto plano sin páginas → sin folios (mapa vacío ⇒ folio NULL). Nunca inventar.
        return text, {"ocr_pages": 0, "total_pages": 0, "truncated": False,
                      "has_body": _alnum_count(text) >= _MIN_BODY_ALNUM,
                      "ocr_unavailable": False, "folio_map": []}
    raise ValueError(f"Tipo de documento no soportado: {filename} (usa PDF, Word .docx, .txt o .md)")


async def extract_text_async(filename: str, data: bytes) -> str:
    """Variante async de `extract_text`: corre la extracción (CPU-pesada, hasta minutos con
    OCR) en un hilo para NO bloquear el event loop (M1). Úsala en todo call site async."""
    text, _meta = await extract_text_detailed_async(filename, data)
    return text


async def extract_text_detailed_async(filename: str, data: bytes) -> tuple[str, dict]:
    """Variante async de `extract_text_detailed`: delega en `asyncio.to_thread` para que el
    OCR (que puede tardar minutos) no congele el event loop, SSE, health ni a los demás
    tenants (revisión adversarial M1)."""
    return await asyncio.to_thread(extract_text_detailed, filename, data)


def _dpi_for_budget(page, base_dpi: int) -> int:
    """DPI efectivo para rasterizar `page` sin pasar del presupuesto de RAM (M2).

    Devuelve `base_dpi` si el raster ya cabe; si no, el mayor dpi que sí cabe (que puede
    quedar por DEBAJO de `OCR_MIN_DPI` → el llamador la saltará por descomunal)."""
    rect = page.rect
    # Área del raster en píxeles a base_dpi (los puntos PDF son 1/72 de pulgada).
    px = (rect.width / 72.0 * base_dpi) * (rect.height / 72.0 * base_dpi)
    megapx = px / 1_000_000.0
    if megapx <= 0 or megapx <= OCR_MAX_MEGAPIXELS:
        return base_dpi
    # Los píxeles crecen con dpi²; escala el dpi por la raíz del cociente para caber justo.
    factor = (OCR_MAX_MEGAPIXELS / megapx) ** 0.5
    return int(base_dpi * factor)


def _assemble_body(page_texts: list[str], ocr_flags: list[bool],
                   toolarge_flags: list[bool], total_pages: int,
                   ) -> tuple[str, bool, list[tuple[int, int, int]]]:
    """Une las páginas EN ORDEN, decide si el documento tiene cuerpo real y construye el
    MAPA DE FOLIOS del cuerpo ensamblado.

    MEN1: antes de cada bloque CONTIGUO de páginas leídas por OCR intercala el marcador de
    segmento, de modo que el troceo posterior lo arrastre cerca del contenido óptico aunque
    esté en la página 200. Las páginas saltadas por descomunales dejan su anotación honesta.

    Devuelve `(cuerpo, has_real_text, folio_map)`:
      - `has_real_text` ignora las anotaciones (M3).
      - `folio_map`: lista de `(folio, char_inicio, char_fin)` con `folio` 1-based = número de
        página del PDF, y offsets MEDIDOS SOBRE EL MISMO cuerpo que se devuelve (contando los
        `\n` de unión y las notas OCR/descomunal que se intercalan). Así el troceo posterior
        NO se desalinea: los caracteres del mapa son EXACTAMENTE los del cuerpo emitido. Las
        notas intercaladas NO llevan folio (quedan como huecos → chunk con folio None)."""
    out: list[str] = []                       # partes emitidas EN ORDEN (notas + segmentos)
    folio_by_part: dict[int, int] = {}        # índice de parte → folio (solo las páginas)
    real_chars = 0
    prev_was_ocr = False
    for i in range(total_pages):
        if toolarge_flags[i]:
            out.append(_ocr_too_large_note(i + 1))
            prev_was_ocr = False
            continue
        seg = page_texts[i]
        if ocr_flags[i]:
            if not prev_was_ocr:
                out.append(OCR_SEGMENT_NOTE)   # abre un nuevo bloque de páginas OCR
            prev_was_ocr = True
        else:
            prev_was_ocr = False
        if seg and seg.strip():
            folio_by_part[len(out)] = i + 1    # esta parte es el folio (página) i+1
            out.append(seg)
            real_chars += _alnum_count(seg)
    parts = [p for p in out if p]              # `out` nunca trae partes vacías → índices == out
    joined = "\n".join(parts)
    body = joined.strip()
    # `body` recorta espacios de los extremos de `joined`: descuenta lo comido al frente para
    # que los offsets queden relativos al cuerpo DEVUELTO (el mismo que se trocea).
    lead = len(joined) - len(joined.lstrip())
    blen = len(body)
    folio_map: list[tuple[int, int, int]] = []
    pos = 0
    for k, p in enumerate(parts):
        if k in folio_by_part:
            s = max(0, pos - lead)
            e = min(blen, pos + len(p) - lead)
            if e > s:
                folio_map.append((folio_by_part[k], s, e))
        pos += len(p) + 1                      # +1 por el "\n" de unión (sobra tras la última)
    return body, real_chars >= _MIN_BODY_ALNUM, folio_map


def _extract_pdf(data: bytes) -> tuple[str, dict]:
    """Extrae texto de un PDF, página a página, con fallback de OCR local para escaneos.

    PDFs mixtos (páginas de texto + páginas escaneadas) se manejan página a página: la
    página de texto conserva su capa; la escaneada se lee por OCR — y el resultado se une
    EN ORDEN de páginas."""
    import fitz  # PyMuPDF

    with fitz.open(stream=data, filetype="pdf") as doc:
        total_pages = doc.page_count
        # 1) Extracción normal por página + detección de candidatas a OCR.
        page_texts: list[str] = []
        candidates: list[int] = []
        for i in range(total_pages):
            page = doc[i]
            t = page.get_text()
            page_texts.append(t)
            if _alnum_count(t) < MIN_ALNUM_PER_PAGE and page.get_images():
                candidates.append(i)

        # 2) Sin candidatas → documento con capa de texto: camino normal, sin OCR.
        # Se ensambla por `_assemble_body` (todas las flags en False) para que el mapa de
        # folios se mida sobre EXACTAMENTE el mismo cuerpo que luego se trocea.
        if not candidates:
            no_flags = [False] * total_pages
            body, has_body, folio_map = _assemble_body(page_texts, no_flags, no_flags,
                                                       total_pages)
            return body, {"ocr_pages": 0, "total_pages": total_pages, "truncated": False,
                          "has_body": has_body, "ocr_unavailable": False,
                          "folio_map": folio_map}

        # 3) Hay escaneo. ¿Tenemos motor de OCR en este servidor?
        engine = ocr.get_ocr_engine()
        if engine is None:
            # Fail-soft: degradar con honestidad. La ingesta NUNCA revienta por falta de OCR.
            no_flags = [False] * total_pages
            body, has_body, folio_map = _assemble_body(page_texts, no_flags, no_flags,
                                                       total_pages)
            text = (OCR_UNAVAILABLE_NOTE + ("\n" + body if body else "")).strip()
            # La nota se antepone al cuerpo: corre el mapa de folios por su longitud para que
            # los offsets sigan midiendo sobre el `text` devuelto (el mismo que se trocea).
            shift = (len(OCR_UNAVAILABLE_NOTE) + 1) if body else 0
            folio_map = [(f, s + shift, e + shift) for (f, s, e) in folio_map]
            # ocr_unavailable solo si SIN motor el documento quedó sin cuerpo legible (M3):
            # un mixto (texto + escaneo) sí tiene cuerpo aunque falte el OCR.
            return text, {"ocr_pages": 0, "total_pages": total_pages, "truncated": False,
                          "has_body": has_body, "ocr_unavailable": not has_body,
                          "folio_map": folio_map}

        # 4) OCR de las páginas candidatas, con límites de páginas y de tiempo (fail-soft).
        ocr_pages = 0
        truncated = False
        first_omitted: int | None = None
        ocr_flags = [False] * total_pages       # página que aportó texto por OCR
        toolarge_flags = [False] * total_pages  # página saltada por descomunal (M2)
        deadline = time.monotonic() + OCR_TIME_BUDGET_S
        for i in candidates:
            if ocr_pages >= MAX_OCR_PAGES or time.monotonic() > deadline:
                truncated = True
                first_omitted = i + 1  # número de página 1-based donde se cortó
                break
            page = doc[i]
            # M2: acota el raster antes de crearlo. Si ni al piso de dpi cabe, se salta.
            dpi = _dpi_for_budget(page, OCR_DPI)
            if dpi < OCR_MIN_DPI:
                toolarge_flags[i] = True
                continue
            try:
                pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
                png = pix.tobytes("png")
                ocr_txt = ocr.ocr_image_png(engine, png)
            except Exception:
                # Una página que falle el OCR NO tumba el documento: se deja lo que hubiera.
                continue
            ocr_pages += 1
            if ocr_txt:
                # MEN2: si la página traía capa de texto legítima (una portada con logo),
                # NO se descarta: se CONCATENA (capa original primero, luego el OCR).
                layer = page_texts[i].strip()
                page_texts[i] = (layer + "\n" + ocr_txt) if layer else ocr_txt
                ocr_flags[i] = True

        used_ocr = any(ocr_flags)  # MEN2: "usó OCR" solo si alguna página aportó texto óptico
        body, has_body, folio_map = _assemble_body(page_texts, ocr_flags, toolarge_flags,
                                                   total_pages)

        parts: list[str] = []
        if used_ocr:
            parts.append(OCR_HONESTY_NOTE)      # honestidad: nota global al inicio (MEN1)
        if body:
            parts.append(body)
        if truncated and first_omitted is not None:
            parts.append(_ocr_truncation_note(first_omitted))
        text = "\n".join(parts).strip()
        # Si la nota global se antepuso al cuerpo, corre el mapa de folios por su longitud
        # (todas las notas empiezan por "[", no hay strip al frente) para que los offsets
        # sigan alineados con el `text` devuelto que luego se trocea.
        shift = (len(OCR_HONESTY_NOTE) + 1) if (used_ocr and body) else 0
        folio_map = [(f, s + shift, e + shift) for (f, s, e) in folio_map]
        return text, {"ocr_pages": ocr_pages, "total_pages": total_pages,
                      "truncated": truncated, "has_body": has_body,
                      "ocr_unavailable": False, "folio_map": folio_map}
