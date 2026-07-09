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

    # ── (h) M2 · página descomunal → salto anotado, sin RAM sin límite ───────────
    def _giant_scanned_page(doc, fitz, lines: list[str]) -> None:
        """Página con MediaBox de 200×200 pulgadas (a 220 dpi rasterizaría a ~1.9 GB)."""
        tmp = fitz.open()
        tp = tmp.new_page(width=595, height=842)
        y = 100
        for ln in lines:
            tp.insert_text((60, y), ln, fontsize=15)
            y += 30
        img_bytes = tp.get_pixmap(dpi=120).tobytes("png")
        tmp.close()
        side = 200 * 72  # 200 pulgadas en puntos PDF
        page = doc.new_page(width=side, height=side)
        page.insert_image(fitz.Rect(0, 0, side, side), stream=img_bytes)

    def _text_plus_giant(d, f):
        _text_page(d, f, ["PRIMERO. Nota con capa de texto real folio_control_nueve."])
        _giant_scanned_page(d, f, SCAN_A)
    pdf_giant = _build_pdf(_text_plus_giant)
    txt_g, meta_g = extract.extract_text_detailed("giant.pdf", pdf_giant)
    check("3a-17 · M2: la página descomunal se SALTA con anotación honesta (no revienta la RAM)",
          extract._ocr_too_large_note(2) in txt_g and meta_g["ocr_pages"] == 0)
    check("3a-18 · M2: la página de texto sobrevive y el documento tiene cuerpo (has_body)",
          "folio_control_nueve" in txt_g and meta_g["has_body"] is True
          and meta_g["total_pages"] == 2)

    # ── (i) M3 · solo-nota (OCR presente pero no leyó nada) → has_body False ──────
    real_ocr_fn2 = ocr.ocr_image_png
    ocr.ocr_image_png = lambda engine, png: ""   # el motor corre pero no reconoce texto
    try:
        txt_i, meta_i = extract.extract_text_detailed("escaneado.pdf", pdf_scan)
    finally:
        ocr.ocr_image_png = real_ocr_fn2
    check("3a-19 · M3: OCR sin texto → has_body False y SIN nota de honestidad (no 'usó OCR')",
          meta_i["has_body"] is False and extract.OCR_HONESTY_NOTE not in txt_i)

    # ── (i') M3 · motor ausente sobre escaneo puro → has_body False + ocr_unavailable ─
    real_get2 = ocr.get_ocr_engine
    ocr.get_ocr_engine = lambda: None
    try:
        txt_u, meta_u = extract.extract_text_detailed("escaneado.pdf", pdf_scan)
    finally:
        ocr.get_ocr_engine = real_get2
    check("3a-20 · M3: sin motor sobre escaneo puro → has_body False y ocr_unavailable True",
          meta_u["has_body"] is False and meta_u["ocr_unavailable"] is True)

    # ── (j) MEN1 · marcador POR SEGMENTO cerca del contenido OCR de una página lejana ─
    def _far_scan(d, f):
        _text_page(d, f, ["Pagina uno con bastante texto de relleno juridico de prueba uno."])
        _text_page(d, f, ["Pagina dos con bastante texto de relleno juridico de prueba dos."])
        _text_page(d, f, ["Pagina tres con bastante texto de relleno juridico de prueba tres."])
        _scanned_page(d, f, SCAN_A)
    pdf_far = _build_pdf(_far_scan)
    txt_j, meta_j = extract.extract_text_detailed("far.pdf", pdf_far)
    low_j = txt_j.lower()
    idx_seg = txt_j.find(extract.OCR_SEGMENT_NOTE)
    idx_cont = low_j.find("1077") if "1077" in low_j else low_j.find("contrato")
    check("3a-21 · MEN1: el marcador por segmento está PRESENTE (además de la nota global)",
          idx_seg != -1 and txt_j.startswith(extract.OCR_HONESTY_NOTE) and meta_j["ocr_pages"] == 1)
    check("3a-22 · MEN1: el marcador precede INMEDIATAMENTE al contenido OCR lejano (<300 chars)",
          idx_cont != -1 and 0 < (idx_cont - idx_seg) < 300)

    # ── (k) MEN2 · página con capa escueta + escaneo → se CONSERVA la capa (no se pisa) ─
    def _layer_plus_ocr_page(d, f):
        tmp = f.open()
        tp = tmp.new_page(width=595, height=842)
        y = 100
        for ln in SCAN_A:
            tp.insert_text((60, y), ln, fontsize=15)
            y += 30
        img_bytes = tp.get_pixmap(dpi=160).tobytes("png")
        tmp.close()
        page = d.new_page(width=595, height=842)
        page.insert_image(f.Rect(0, 0, 595, 842), stream=img_bytes)
        page.insert_text((60, 800), "folio_capa_nativa_siete", fontsize=11)  # capa escueta real
    pdf_k = _build_pdf(_layer_plus_ocr_page)
    txt_k, meta_k = extract.extract_text_detailed("portada.pdf", pdf_k)
    low_k = txt_k.lower()
    idx_layer = low_k.find("folio_capa_nativa_siete")
    idx_ocr_k = low_k.find("1077") if "1077" in low_k else low_k.find("contrato")
    check("3a-23 · MEN2: la capa nativa escueta se CONSERVA junto al texto OCR (no se descarta)",
          idx_layer != -1 and idx_ocr_k != -1 and meta_k["ocr_pages"] == 1)
    check("3a-24 · MEN2: la capa original va ANTES del texto OCR (orden capa→OCR)",
          idx_layer != -1 and idx_ocr_k != -1 and idx_layer < idx_ocr_k)

    # ── (l) MEN3 · no-egress: el OCR real no abre NINGÚN socket de red (confidencialidad) ─
    import socket
    _orig_socket, _orig_conn = socket.socket, socket.create_connection

    def _block_net(*a, **k):
        raise AssertionError("el OCR intentó abrir un socket de red")

    socket.socket = _block_net
    socket.create_connection = _block_net
    try:
        txt_l, meta_l = extract.extract_text_detailed("escaneado.pdf", pdf_scan)
        net_ok = (meta_l["ocr_pages"] == 1
                  and any(w in txt_l.lower() for w in ("contrato", "1077", "codigo")))
    except AssertionError:
        net_ok = False
    finally:
        socket.socket = _orig_socket
        socket.create_connection = _orig_conn
    check("3a-25 · MEN3: no-egress — el OCR real corrió sin abrir ningún socket de red", net_ok)

    # ── (m) M1 · la variante async delega en to_thread y da el MISMO resultado ───
    import asyncio
    txt_as, meta_as = asyncio.run(extract.extract_text_detailed_async("escaneado.pdf", pdf_scan))
    check("3a-26 · M1: extract_text_detailed_async devuelve el mismo resultado (delega a hilo)",
          meta_as["ocr_pages"] == 1 and extract.OCR_HONESTY_NOTE in txt_as)


if __name__ == "__main__":
    run_gate()
    passed = sum(1 for _, ok in _results if ok)
    print(f"\n{passed}/{len(_results)} checks PASS")
    if all(ok for _, ok in _results):
        print("OCR ingest OK — bloque 3a verificado (lectura óptica local de PDFs "
              "escaneados: honestidad + fail-soft + orden de páginas).")
        sys.exit(0)
    sys.exit(1)
