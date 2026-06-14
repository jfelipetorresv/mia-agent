"""Mia · ingest.extract — extrae texto de PDF / Word / texto plano (Fase 3 backend).

PDF → PyMuPDF (`fitz`); Word `.docx` → `python-docx`; `.txt`/`.md` → utf-8. Import perezoso
de las librerías pesadas: solo se cargan al subir un documento de ese tipo.
"""
from __future__ import annotations

import io


def extract_text(filename: str, data: bytes) -> str:
    """Devuelve el texto plano de un documento subido. Lanza si el tipo no es soportado."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        import fitz  # PyMuPDF
        with fitz.open(stream=data, filetype="pdf") as doc:
            return "\n".join(page.get_text() for page in doc).strip()
    if name.endswith(".docx"):
        import docx
        d = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in d.paragraphs).strip()
    if name.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="replace").strip()
    raise ValueError(f"Tipo de documento no soportado: {filename} (usa PDF, Word .docx, .txt o .md)")
