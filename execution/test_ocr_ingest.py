"""
Mia · test_ocr_ingest.py — gate del bloque 3a (OCR local de PDFs escaneados).

Verifica OFFLINE (sin DB, sin red; el OCR real SÍ corre — es local por diseño) que el
pipeline de ingesta lea PDFs escaneados con reconocimiento óptico local, con honestidad
total y fail-soft en todos los bordes. El PDF escaneado se fabrica EN EL TEST: se renderiza
texto español a imagen con PyMuPDF y se inserta como página-imagen (sin capa de texto y sin
fixtures binarios commiteados).

Cubre:
  (a) PDF de texto normal NO pasa por OCR (ni anotación).
  (b) PDF escaneado → OCR extrae el texto esperado (aserción tolerante) + anotación de honestidad.
  (c) PDF mixto (texto + escaneado) → ambas partes, en orden.
  (d) Límite de páginas → truncado anotado.
  (e) OCR ausente (motor None) → fail-soft con anotación, sin reventar.
  (f) Página corrupta (OCR lanza) → no tumba el documento.
  (g) `extract_text` conserva el contrato str para los llamadores viejos.

Exit 0 = PASS · 1 = FAIL.   .venv\\Scripts\\python.exe execution\\test_ocr_ingest.py
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

if sys.platform == "win32":
    # La consola cp1252 no imprime acentos/flechas — el gate no debe caerse por un print.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

_results: list = []


def check(name: str, ok) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── Fábrica de PDFs sintéticos (en memoria, sin fixtures binarios) ───────────────
def _text_page(doc, fitz, lines: list[str]) -> None:
    """Agrega una página CON capa de texto real (no candidata a OCR)."""
    page = doc.new_page(width=595, height=842)
    y = 100
    for ln in lines:
        page.insert_text((60, y), ln, fontsize=13)
        y += 26


def _scanned_page(doc, fitz, lines: list[str]) -> None:
    """Agrega una página ESCANEADA: el texto se rasteriza a imagen y se inserta como
    imagen en una página SIN capa de texto (get_text vacío, get_images no vacío)."""
    tmp = fitz.open()
    tp = tmp.new_page(width=595, height=842)
    y = 100
    for ln in lines:
        tp.insert_text((60, y), ln, fontsize=15)
        y += 30
    pix = tp.get_pixmap(dpi=160)
    img_bytes = pix.tobytes("png")
    tmp.close()
    page = doc.new_page(width=595, height=842)
    page.insert_image(fitz.Rect(0, 0, 595, 842), stream=img_bytes)


def _build_pdf(build) -> bytes:
    import fitz
    doc = fitz.open()
    build(doc, fitz)
    data = doc.tobytes()
    doc.close()
    return data


def run_gate() -> None:
    import fitz  # noqa: F401 — asegura que PyMuPDF está disponible

    from mia.ingest import extract, ocr

    # Frases jurídicas en español para las páginas escaneadas.
    SCAN_A = ["El contrato de seguro se rige por el articulo 1077",
              "del Codigo de Comercio de Colombia."]
    SCAN_B = ["La caducidad de la accion opero el 14 de marzo de 2024",
              "conforme al articulo 1081 ibidem."]

    # ── (a) PDF de texto normal NO pasa por OCR ──────────────────────────────────
    pdf_text = _build_pdf(lambda d, f: _text_page(d, f, [
        "PRIMERO. El demandante celebro un contrato de obra publica.",
        "SEGUNDO. La aseguradora expidio la poliza de cumplimiento.",
        "TERCERO. Se declaro el siniestro dentro del termino legal."]))
    txt_a, meta_a = extract.extract_text_detailed("demanda.pdf", pdf_text)
    check("3a-01 · PDF de texto normal: OCR no interviene (ocr_pages == 0)",
          meta_a["ocr_pages"] == 0 and meta_a["total_pages"] == 1)
    check("3a-02 · PDF de texto normal: SIN anotación de OCR y con el texto real",
          extract.OCR_HONESTY_NOTE not in txt_a
          and extract.OCR_UNAVAILABLE_NOTE not in txt_a
          and "contrato de obra publica" in txt_a)

    # ── (b) PDF escaneado → OCR real extrae el texto + anotación de honestidad ────
    pdf_scan = _build_pdf(lambda d, f: _scanned_page(d, f, SCAN_A))
    txt_b, meta_b = extract.extract_text_detailed("escaneado.pdf", pdf_scan)
    low_b = txt_b.lower()
    check("3a-03 · PDF escaneado: OCR leyó la página (ocr_pages == 1)",
          meta_b["ocr_pages"] == 1 and meta_b["total_pages"] == 1)
    check("3a-04 · PDF escaneado: anotación de honestidad PRESENTE y al inicio",
          txt_b.startswith(extract.OCR_HONESTY_NOTE))
    # Aserción tolerante a errores menores de OCR: palabras clave, no igualdad exacta.
    hits_b = sum(w in low_b for w in ("contrato", "seguro", "1077", "codigo", "comercio"))
    check(f"3a-05 · PDF escaneado: OCR recuperó el contenido jurídico ({hits_b}/5 claves)",
          hits_b >= 4)

    # ── (c) PDF mixto → texto + OCR, EN ORDEN ────────────────────────────────────
    def _mixed(d, f):
        _text_page(d, f, ["ENCABEZADO CON CAPA DE TEXTO NATIVA marcador_alpha."])
        _scanned_page(d, f, SCAN_B)
    pdf_mixed = _build_pdf(_mixed)
    txt_c, meta_c = extract.extract_text_detailed("mixto.pdf", pdf_mixed)
    low_c = txt_c.lower()
    check("3a-06 · PDF mixto: solo la página escaneada pasó por OCR (ocr_pages == 1 de 2)",
          meta_c["ocr_pages"] == 1 and meta_c["total_pages"] == 2)
    idx_native = low_c.find("marcador_alpha")
    idx_ocr = low_c.find("caducidad") if "caducidad" in low_c else low_c.find("2024")
    check("3a-07 · PDF mixto: capa nativa y OCR presentes, en orden de página (nativa antes)",
          idx_native != -1 and idx_ocr != -1 and idx_native < idx_ocr)

    # ── (d) Límite de páginas → truncado anotado ─────────────────────────────────
    def _four_scans(d, f):
        for lines in (SCAN_A, SCAN_B, SCAN_A, SCAN_B):
            _scanned_page(d, f, lines)
    pdf_four = _build_pdf(_four_scans)
    orig_max = extract.MAX_OCR_PAGES
    extract.MAX_OCR_PAGES = 2  # override para no OCR-ear 4 páginas reales en el gate
    try:
        txt_d, meta_d = extract.extract_text_detailed("largo.pdf", pdf_four)
    finally:
        extract.MAX_OCR_PAGES = orig_max
    check("3a-08 · Límite: solo se leen MAX_OCR_PAGES páginas (2) y truncated=True",
          meta_d["ocr_pages"] == 2 and meta_d["truncated"] is True
          and meta_d["total_pages"] == 4)
    check("3a-09 · Límite: la anotación de truncado apunta a la página 3 (1-based)",
          extract._ocr_truncation_note(3) in txt_d)

    # ── (e) OCR ausente (motor None) → fail-soft con anotación ───────────────────
    real_get = ocr.get_ocr_engine
    ocr.get_ocr_engine = lambda: None  # simula librería no instalada (ImportError capturado)
    try:
        txt_e, meta_e = extract.extract_text_detailed("escaneado.pdf", pdf_scan)
    finally:
        ocr.get_ocr_engine = real_get
    check("3a-10 · OCR ausente: fail-soft — no revienta y ocr_pages == 0",
          meta_e["ocr_pages"] == 0)
    check("3a-11 · OCR ausente: anotación honesta de que este servidor no tiene OCR",
          extract.OCR_UNAVAILABLE_NOTE in txt_e)

    # ── (f) Página corrupta (OCR lanza) → no tumba el documento ──────────────────
    def _two_scans(d, f):
        _scanned_page(d, f, SCAN_A)
        _scanned_page(d, f, SCAN_B)
    pdf_two = _build_pdf(_two_scans)
    real_ocr_fn = ocr.ocr_image_png
    _calls = {"n": 0}

    def _flaky(engine, png):
        _calls["n"] += 1
        if _calls["n"] == 1:
            raise RuntimeError("página corrupta")  # la 1ª página revienta el OCR
        return real_ocr_fn(engine, png)            # la 2ª lee normal

    ocr.ocr_image_png = _flaky
    try:
        txt_f, meta_f = extract.extract_text_detailed("una_dañada.pdf", pdf_two)
    finally:
        ocr.ocr_image_png = real_ocr_fn
    low_f = txt_f.lower()
    check("3a-12 · Página corrupta: el documento sobrevive (ocr_pages == 1 de las 2)",
          meta_f["ocr_pages"] == 1 and meta_f["total_pages"] == 2)
    check("3a-13 · Página corrupta: la página sana SÍ se leyó (contenido presente)",
          ("caducidad" in low_f) or ("2024" in low_f) or ("1081" in low_f))

    # ── (g) extract_text conserva el contrato str (llamadores viejos) ────────────
    r_text = extract.extract_text("demanda.pdf", pdf_text)
    r_scan = extract.extract_text("escaneado.pdf", pdf_scan)
    check("3a-14 · extract_text sigue devolviendo str (retrocompatibilidad de llamadores)",
          isinstance(r_text, str) and isinstance(r_scan, str) and len(r_scan) > 0)
    check("3a-15 · extract_text sobre escaneo trae la anotación de honestidad embebida",
          extract.OCR_HONESTY_NOTE in r_scan)
    # Tipo no soportado sigue lanzando ValueError (contrato intacto).
    raised = False
    try:
        extract.extract_text("hoja.xlsx", b"x")
    except ValueError:
        raised = True
    check("3a-16 · tipo no soportado sigue lanzando ValueError (contrato intacto)", raised)


if __name__ == "__main__":
    run_gate()
    passed = sum(1 for _, ok in _results if ok)
    print(f"\n{passed}/{len(_results)} checks PASS")
    if all(ok for _, ok in _results):
        print("OCR ingest OK — bloque 3a verificado (lectura óptica local de PDFs "
              "escaneados: honestidad + fail-soft + orden de páginas).")
        sys.exit(0)
    sys.exit(1)
