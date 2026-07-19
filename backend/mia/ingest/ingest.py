"""
Mia · ingest — Paso 6 del Módulo 0.

Lee un archivo de texto/markdown, lo trocea, lo embebe (voyage-law-2 vía LiteLLM)
y lo inserta como `document` + `chunks` bajo un tenant/matter, respetando RLS.

Uso (con PYTHONPATH=backend y el python de .venv):
  python -m mia.ingest.ingest --tenant <uuid> --matter <uuid> --file <ruta>

Requiere VOYAGE_API_KEY en .env.
"""
from __future__ import annotations
import argparse
import asyncio
import sys
from pathlib import Path

from .. import embeddings
from ..db import pool

# psycopg async requiere SelectorEventLoop en Windows (Modo B); el Proactor no sirve.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def chunk_text(text: str, size: int = 1200, overlap: int = 150) -> list[str]:
    text = text.strip()
    if not text:
        return []
    out: list[str] = []
    i = 0
    step = max(1, size - overlap)
    while i < len(text):
        out.append(text[i:i + size])
        i += step
    return out


def _folio_at(spans: list[tuple[int, int, int]], pos: int) -> int | None:
    """Folio (página) del offset `pos` según `spans` (ORDENADOS por char_inicio).

    Devuelve el folio del span que CONTIENE `pos`; si `pos` cae en un hueco (una nota OCR
    intercalada o el "\\n" entre páginas) arrastra el folio de la última página iniciada
    antes de `pos`; si `pos` es anterior a toda página (p. ej. la nota global de honestidad)
    devuelve None. Nunca inventa un folio que no se pueda determinar."""
    current: int | None = None
    for folio, s, e in spans:
        if s > pos:
            break
        current = folio
        if pos < e:
            return folio
    return current


def chunk_text_with_folios(text: str, offset_map: list[tuple[int, int, int]],
                           size: int = 1200, overlap: int = 150,
                           ) -> list[tuple[str, int | None]]:
    """Hermana de `chunk_text` (misma partición EXACTA de caracteres) que además ancla cada
    chunk a su folio. `offset_map` es la lista `(folio, char_inicio, char_fin)` que produce
    `extract`, medida sobre ESTE MISMO `text`. Un chunk que cruza páginas hereda el folio de
    su offset de INICIO (decisión simple y defendible). Sin mapa (fuentes sin páginas) el
    folio es None → folio_ancla NULL. Devuelve `[(chunk, folio|None), ...]`."""
    text = text.strip()
    if not text:
        return []
    spans = sorted(offset_map or [], key=lambda t: t[1])
    out: list[tuple[str, int | None]] = []
    i = 0
    step = max(1, size - overlap)
    while i < len(text):
        out.append((text[i:i + size], _folio_at(spans, i)))
        i += step
    return out


async def ingest_file(tenant_id: str, matter_id: str, path: Path) -> int:
    chunks = chunk_text(path.read_text(encoding="utf-8"))
    if not chunks:
        raise RuntimeError(f"Archivo vacío: {path}")
    vectors = embeddings.embed_texts(chunks)
    async with pool.tenant_connection(tenant_id) as conn:
        doc_id = (await (await conn.execute(
            "INSERT INTO documents(tenant_id, matter_id, filename, mime) "
            "VALUES (%s,%s,%s,%s) RETURNING id",
            (tenant_id, matter_id, path.name, "text/plain"),
        )).fetchone())[0]
        for ord_, (content, vec) in enumerate(zip(chunks, vectors)):
            await conn.execute(
                "INSERT INTO chunks(tenant_id, document_id, ord, content, embedding, procedencia) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (tenant_id, doc_id, ord_, content, vec, "documento"),
            )
    return len(chunks)


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingesta de un documento a Mia (tenant-scoped).")
    ap.add_argument("--tenant", required=True, help="UUID del tenant")
    ap.add_argument("--matter", required=True, help="UUID del asunto (matter)")
    ap.add_argument("--file", required=True, type=Path, help="Ruta del archivo a ingerir")
    args = ap.parse_args()

    async def _run() -> None:
        await pool.open_pool()
        try:
            n = await ingest_file(args.tenant, args.matter, args.file)
            print(f"[OK] {n} chunks ingeridos de {args.file.name}")
        finally:
            await pool.close_pool()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
