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
"""
from __future__ import annotations

import io
import time

from . import ocr

# ── Parámetros del fallback de OCR (constantes de módulo → testeables por override) ──
# Una página es CANDIDATA a OCR si su texto extraíble tiene menos de este número de
# caracteres alfanuméricos Y la página contiene imágenes (típico de un escaneo).
MIN_ALNUM_PER_PAGE = 40
# Rasterización de la página antes del OCR: dpi y escala de grises (menos ruido, más rápido).
OCR_DPI = 220
# Fail-soft: tope de páginas leídas por OCR por documento. Las siguientes se omiten y se anota.
MAX_OCR_PAGES = 150
# Fail-soft: presupuesto de tiempo de OCR por documento (segundos). Corte honesto al superarlo.
OCR_TIME_BUDGET_S = 600.0

# Anotaciones EN LLANO (sin jerga técnica, a propósito — las lee el abogado).
OCR_HONESTY_NOTE = ("[Este documento se leyó con reconocimiento óptico (era un escaneo); "
                    "puede contener errores de lectura.]")
OCR_UNAVAILABLE_NOTE = "[Documento escaneado: este servidor no tiene lectura óptica instalada]"


def _ocr_truncation_note(first_omitted_page: int) -> str:
    return (f"[Páginas {first_omitted_page}+ sin leer: el documento escaneado supera el "
            f"límite de lectura óptica]")


def _alnum_count(text: str) -> int:
    return sum(1 for c in text if c.isalnum())


def extract_text(filename: str, data: bytes) -> str:
    """Devuelve el texto plano de un documento subido. Lanza si el tipo no es soportado.

    Contrato retrocompatible: SIEMPRE devuelve `str` (los llamadores viejos no cambian).
    Para PDFs escaneados el texto ya viene con la anotación de honestidad de OCR."""
    text, _meta = extract_text_detailed(filename, data)
    return text


def extract_text_detailed(filename: str, data: bytes) -> tuple[str, dict]:
    """Como `extract_text` pero devuelve además metadata de OCR para quien la quiera.

    Retorna `(texto, {"ocr_pages": int, "total_pages": int, "truncated": bool})`.
    `ocr_pages > 0` ⇒ el documento se leyó (en parte) con reconocimiento óptico."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return _extract_pdf(data)
    if name.endswith(".docx"):
        import docx
        d = docx.Document(io.BytesIO(data))
        text = "\n".join(p.text for p in d.paragraphs).strip()
        return text, {"ocr_pages": 0, "total_pages": 0, "truncated": False}
    if name.endswith((".txt", ".md")):
        text = data.decode("utf-8", errors="replace").strip()
        return text, {"ocr_pages": 0, "total_pages": 0, "truncated": False}
    raise ValueError(f"Tipo de documento no soportado: {filename} (usa PDF, Word .docx, .txt o .md)")


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
        if not candidates:
            text = "\n".join(page_texts).strip()
            return text, {"ocr_pages": 0, "total_pages": total_pages, "truncated": False}

        # 3) Hay escaneo. ¿Tenemos motor de OCR en este servidor?
        engine = ocr.get_ocr_engine()
        if engine is None:
            # Fail-soft: degradar con honestidad. La ingesta NUNCA revienta por falta de OCR.
            body = "\n".join(page_texts).strip()
            text = (OCR_UNAVAILABLE_NOTE + ("\n" + body if body else "")).strip()
            return text, {"ocr_pages": 0, "total_pages": total_pages, "truncated": False}

        # 4) OCR de las páginas candidatas, con límites de páginas y de tiempo (fail-soft).
        ocr_pages = 0
        truncated = False
        first_omitted: int | None = None
        deadline = time.monotonic() + OCR_TIME_BUDGET_S
        for i in candidates:
            if ocr_pages >= MAX_OCR_PAGES or time.monotonic() > deadline:
                truncated = True
                first_omitted = i + 1  # número de página 1-based donde se cortó
                break
            try:
                pix = doc[i].get_pixmap(dpi=OCR_DPI, colorspace=fitz.csGRAY)
                png = pix.tobytes("png")
                ocr_txt = ocr.ocr_image_png(engine, png)
            except Exception:
                # Una página que falle el OCR NO tumba el documento: se deja lo que hubiera.
                continue
            ocr_pages += 1
            if ocr_txt:
                page_texts[i] = ocr_txt

        body = "\n".join(page_texts).strip()
        parts: list[str] = []
        if ocr_pages > 0:
            parts.append(OCR_HONESTY_NOTE)      # honestidad: prepende que hubo lectura óptica
        if body:
            parts.append(body)
        if truncated and first_omitted is not None:
            parts.append(_ocr_truncation_note(first_omitted))
        text = "\n".join(parts).strip()
        return text, {"ocr_pages": ocr_pages, "total_pages": total_pages, "truncated": truncated}
