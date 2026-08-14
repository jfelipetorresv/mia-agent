"""Derivación documental común para MIA.

Este módulo separa tres cosas que no deben confundirse:

* el original (bytes + SHA-256), que es la fuente probatoria;
* una representación Markdown estructural, útil para recuperación y embeddings;
* los fragmentos que se entregan a un modelo, que siempre se pueden volver a
  ubicar en una sección y nunca se tratan como instrucciones.

AnyDoc es opcional en tiempo de importación y está fijado en ``pyproject.toml``.
Si el wheel no está disponible, la ingesta conserva el extractor existente. PDF
se excluye deliberadamente: PyMuPDF/OCR es quien conserva los folios de Mia.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import io
import multiprocessing
import re
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..agents.untrusted import fence_block
from ..memory.tokens import estimate_tokens

try:  # optional at runtime: local devs may use the pre-AnyDoc environment
    import anydoc as _anydoc  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised by minimal installations
    _anydoc = None


ANYDOC_VERSION = ""
if _anydoc is not None:
    try:
        ANYDOC_VERSION = importlib.metadata.version("firecrawl-anydoc")
    except importlib.metadata.PackageNotFoundError:
        ANYDOC_VERSION = "unknown"

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")
_FENCE = re.compile(r"^\s*(```+|~~~+)")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_PARA_SPLIT = re.compile(r"\n\s*\n")

# These are limits for *derived context*, not a license to silently drop evidence.
# A source over the document limit is rejected by the caller; an oversized section
# is split at paragraph/row boundaries below.
MAX_SOURCE_BYTES = 50 * 1024 * 1024
MAX_DERIVED_CHARS = 8_000_000
MAX_TABLE_CELLS_PER_CHUNK = 2_000
MAX_CHUNK_TOKENS = 512
MAX_ARCHIVE_ENTRIES = 10_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
MAX_ARCHIVE_ENTRY_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_COMPRESSION_RATIO = 200
ANYDOC_CONVERSION_TIMEOUT_S = 45.0

SUPPORTED_ANYDOC_EXTENSIONS = frozenset({
    ".doc", ".docx", ".docm", ".odt", ".rtf", ".ppt", ".pptx", ".pptm",
    ".pps", ".ppsx", ".xls", ".xlsx", ".xlsm", ".xlsb", ".ods", ".odp",
    ".epub", ".csv",
})

_ZIP_FORMAT_ROOT = {
    ".docx": "word/", ".docm": "word/",
    ".pptx": "ppt/", ".pptm": "ppt/", ".ppsx": "ppt/",
    ".xlsx": "xl/", ".xlsm": "xl/", ".xlsb": "xl/",
}
_OOXML_MAIN_CONTENT_TYPE = {
    ".docx": "wordprocessingml.document.main+xml",
    ".docm": "ms-word.document.macroenabled.main+xml",
    ".pptx": "presentationml.presentation.main+xml",
    ".pptm": "ms-powerpoint.presentation.macroenabled.main+xml",
    ".ppsx": "presentationml.slideshow.main+xml",
    ".xlsx": "spreadsheetml.sheet.main+xml",
    ".xlsm": "ms-excel.sheet.macroenabled.main+xml",
    ".xlsb": "ms-excel.sheet.binary.macroenabled.main",
}
_ODF_MIME = {
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".odp": "application/vnd.oasis.opendocument.presentation",
    ".epub": "application/epub+zip",
}
_CFB_EXTENSIONS = frozenset({".doc", ".ppt", ".pps", ".xls"})
_GENERIC_DECLARED_MIMES = frozenset({"", "application/octet-stream", "binary/octet-stream"})
_MIME_BY_EXTENSION = {
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document",),
    ".docm": ("application/vnd.ms-word.document.macroenabled.12",),
    ".odt": (_ODF_MIME[".odt"],),
    ".rtf": ("application/rtf", "text/rtf"),
    ".ppt": ("application/vnd.ms-powerpoint",),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation",),
    ".pptm": ("application/vnd.ms-powerpoint.presentation.macroenabled.12",),
    ".pps": ("application/vnd.ms-powerpoint",),
    ".ppsx": ("application/vnd.openxmlformats-officedocument.presentationml.slideshow",),
    ".xls": ("application/vnd.ms-excel",),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",),
    ".xlsm": ("application/vnd.ms-excel.sheet.macroenabled.12",),
    ".xlsb": ("application/vnd.ms-excel.sheet.binary.macroenabled.12",),
    ".ods": (_ODF_MIME[".ods"],), ".odp": (_ODF_MIME[".odp"],),
    ".epub": (_ODF_MIME[".epub"],), ".csv": ("text/csv", "text/plain"),
}


class AnyDocSafetyError(ValueError):
    """Archivo rechazado antes del parser por firma o presupuesto de recursos."""

    def __init__(self, message: str, *, code: str = "resourceLimit", limit: int | None = None,
                 part: str | None = None):
        super().__init__(message)
        self.code, self.limit, self.part = code, limit, part


class AnyDocConversionError(RuntimeError):
    """Fallo/timeout aislado del conversor, con campos que conserva ``extract.py``."""

    def __init__(self, message: str, *, code: str = "conversion", limit: int | None = None,
                 part: str | None = None):
        super().__init__(message)
        self.code, self.limit, self.part = code, limit, part


def _validate_zip(filename: str, data: bytes, extension: str) -> None:
    if not data.startswith(b"PK"):
        raise AnyDocSafetyError(
            f"La firma del archivo no corresponde a {extension}", code="mimeMismatch")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise AnyDocSafetyError("El contenedor tiene demasiadas partes",
                                        limit=MAX_ARCHIVE_ENTRIES)
            total = 0
            names = set()
            for info in infos:
                normalized = info.filename.replace("\\", "/")
                if normalized.startswith("/") or ".." in normalized.split("/"):
                    raise AnyDocSafetyError("El contenedor contiene una ruta insegura",
                                            code="unsafeArchive", part=info.filename)
                if info.flag_bits & 0x1:
                    raise AnyDocSafetyError("El contenedor está cifrado",
                                            code="encrypted", part=info.filename)
                if info.file_size > MAX_ARCHIVE_ENTRY_BYTES:
                    raise AnyDocSafetyError("Una parte descomprimida supera el límite",
                                            limit=MAX_ARCHIVE_ENTRY_BYTES, part=info.filename)
                total += info.file_size
                if total > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                    raise AnyDocSafetyError("El contenido descomprimido supera el límite",
                                            limit=MAX_ARCHIVE_UNCOMPRESSED_BYTES)
                ratio = info.file_size / max(1, info.compress_size)
                if info.file_size > 1_000_000 and ratio > MAX_ARCHIVE_COMPRESSION_RATIO:
                    raise AnyDocSafetyError("La compresión del contenedor es insegura",
                                            limit=MAX_ARCHIVE_COMPRESSION_RATIO,
                                            part=info.filename)
                names.add(normalized)
            required_root = _ZIP_FORMAT_ROOT.get(extension)
            if required_root and (
                "[Content_Types].xml" not in names
                or not any(name.startswith(required_root) for name in names)
            ):
                raise AnyDocSafetyError(
                    f"El contenido no corresponde a {extension}", code="mimeMismatch")
            expected_content_type = _OOXML_MAIN_CONTENT_TYPE.get(extension)
            if expected_content_type:
                manifest_info = archive.getinfo("[Content_Types].xml")
                if manifest_info.file_size > 2 * 1024 * 1024:
                    raise AnyDocSafetyError(
                        "El manifiesto del contenedor supera el límite",
                        limit=2 * 1024 * 1024, part="[Content_Types].xml")
                manifest = archive.read(manifest_info).decode("utf-8", errors="replace").lower()
                if expected_content_type not in manifest:
                    raise AnyDocSafetyError(
                        f"El tipo interno no corresponde a {extension}", code="mimeMismatch")
            expected_mime = _ODF_MIME.get(extension)
            if expected_mime:
                try:
                    actual = archive.read("mimetype").decode("ascii", errors="strict").strip()
                except (KeyError, UnicodeDecodeError):
                    raise AnyDocSafetyError(
                        f"El contenido no corresponde a {extension}", code="mimeMismatch")
                if actual != expected_mime:
                    raise AnyDocSafetyError(
                        f"El contenido no corresponde a {extension}", code="mimeMismatch")
    except zipfile.BadZipFile as exc:
        raise AnyDocSafetyError("El contenedor está dañado", code="malformed") from exc


def validate_office_source(filename: str, data: bytes, declared_mime: str | None = None) -> None:
    """Valida tamaño, MIME declarado y firma real antes de AnyDoc o cualquier fallback."""
    extension = Path(filename or "").suffix.lower()
    if len(data) > MAX_SOURCE_BYTES:
        raise AnyDocSafetyError("El documento supera el límite local de 50 MiB",
                                limit=MAX_SOURCE_BYTES)
    declared = (declared_mime or "").split(";", 1)[0].strip().lower()
    accepted = _MIME_BY_EXTENSION.get(extension, ())
    if declared not in _GENERIC_DECLARED_MIMES and accepted and declared not in accepted:
        raise AnyDocSafetyError("El tipo declarado no coincide con la extensión",
                                code="mimeMismatch")
    if extension in _ZIP_FORMAT_ROOT or extension in _ODF_MIME:
        _validate_zip(filename, data, extension)
    elif extension in _CFB_EXTENSIONS and not data.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        raise AnyDocSafetyError(
            f"La firma del archivo no corresponde a {extension}", code="mimeMismatch")
    elif extension == ".rtf" and not data.lstrip().startswith(b"{\\rtf"):
        raise AnyDocSafetyError("La firma del archivo no corresponde a .rtf",
                                code="mimeMismatch")
    elif extension == ".csv" and b"\x00" in data[:8192]:
        raise AnyDocSafetyError("El contenido no corresponde a texto CSV",
                                code="mimeMismatch")


def _convert_worker(connection) -> None:
    """Proceso hijo persistente: el arranque se amortiza entre conversiones."""
    while True:
        try:
            request = connection.recv()
        except EOFError:
            break
        if request is None:
            break
        data, fmt = request
        try:
            markdown = (_anydoc.to_markdown_bytes(data, fmt)
                        if fmt else _anydoc.to_markdown_bytes(data))
            connection.send({"ok": True, "markdown": str(markdown)})
        except BaseException as exc:  # solo datos serializables, nunca traceback
            connection.send({
                "ok": False,
                "message": str(exc),
                "code": getattr(exc, "code", None) or exc.__class__.__name__.replace("Error", ""),
                "limit": getattr(exc, "limit", None),
                "part": getattr(exc, "part", None),
            })
    connection.close()


_WORKER_LOCK = threading.Lock()
_WORKER_PROCESS = None
_WORKER_CONNECTION = None


def _stop_worker() -> None:
    global _WORKER_PROCESS, _WORKER_CONNECTION
    process, connection = _WORKER_PROCESS, _WORKER_CONNECTION
    _WORKER_PROCESS = _WORKER_CONNECTION = None
    if connection is not None:
        try:
            connection.close()
        except OSError:
            pass
    if process is not None:
        if process.is_alive():
            process.terminate()
        process.join(timeout=2)
        if process.is_alive() and hasattr(process, "kill"):
            process.kill()
            process.join(timeout=1)


def _ensure_worker():
    global _WORKER_PROCESS, _WORKER_CONNECTION
    if _WORKER_PROCESS is not None and _WORKER_PROCESS.is_alive():
        return _WORKER_CONNECTION
    _stop_worker()
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=True)
    process = context.Process(target=_convert_worker, args=(child,), daemon=True)
    process.start()
    child.close()
    _WORKER_PROCESS, _WORKER_CONNECTION = process, parent
    return parent


def _convert_with_timeout(data: bytes, fmt: str | None) -> str:
    # Una conexión por proceso exige serializar sus mensajes. La conversión ya
    # corre desde ``to_thread`` en rutas async, de modo que este lock no bloquea
    # el event loop. El worker se conserva para no pagar ~0,5 s de spawn por archivo.
    with _WORKER_LOCK:
        connection = _ensure_worker()
        try:
            connection.send((data, fmt))
            if not connection.poll(ANYDOC_CONVERSION_TIMEOUT_S):
                _stop_worker()
                raise AnyDocConversionError(
                    "La conversión superó el tiempo permitido",
                    code="timeout", limit=int(ANYDOC_CONVERSION_TIMEOUT_S),
                )
            payload = connection.recv()
        except (EOFError, OSError, BrokenPipeError) as exc:
            _stop_worker()
            raise AnyDocConversionError(
                "El conversor local terminó sin respuesta", code="workerUnavailable") from exc
    if not payload.get("ok"):
        raise AnyDocConversionError(
            payload.get("message") or "AnyDoc no pudo convertir el documento",
            code=payload.get("code") or "conversion",
            limit=payload.get("limit"), part=payload.get("part"),
        )
    return str(payload["markdown"])


@dataclass(frozen=True)
class DerivedDocument:
    """Serializable contract for a derived document.

    ``folio_map`` belongs to the source extractor and is intentionally empty for
    AnyDoc office output. A PDF citation is therefore never authorized by this
    module; it must come from ``extract.py``.
    """

    source_sha256: str
    source_format: str
    parser: str
    parser_version: str
    markdown: str
    blocks: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...] = ()
    confidence: str = "structural"
    assets_count: int = 0
    folio_map: tuple[tuple[int, int, int], ...] = ()
    source_file: str = ""

    def metadata(self) -> dict[str, Any]:
        """Return compact runtime metadata; never duplicate document bodies.

        The canonical Markdown remains the derived artifact returned to the
        extraction caller. Chunks are recomputed from that text. Persisting the
        full Markdown and every block inside metadata would double memory and
        inflate any later prompt/trace serialization.
        """
        return {
            "source_sha256": self.source_sha256,
            "source_format": self.source_format,
            "parser": self.parser,
            "parser_version": self.parser_version,
            "source_file": self.source_file,
            "warnings": list(self.warnings),
            "confidence": self.confidence,
            "assets_count": self.assets_count,
            "block_count": len(self.blocks),
            "table_block_count": sum(1 for block in self.blocks
                                      if block.get("content_kind") == "table"),
            "folio_map": [list(span) for span in self.folio_map],
        }


def anydoc_available() -> bool:
    """Whether the pinned Python binding is importable in this process."""
    return _anydoc is not None


def is_anydoc_candidate(filename: str) -> bool:
    """Return true for supported non-PDF office/document formats."""
    return Path(filename or "").suffix.lower() in SUPPORTED_ANYDOC_EXTENSIONS


def _format_for(filename: str) -> str | None:
    suffix = Path(filename or "").suffix.lower().lstrip(".")
    # AnyDoc's format enum aliases container variants. Its Python binding accepts
    # the canonical extension string, but CSV needs an explicit name.
    aliases = {
        "docm": "docx", "pptm": "pptx", "pps": "ppt", "ppsx": "pptx",
        "xlsm": "xlsx", "xlsb": "xlsx",
    }
    return aliases.get(suffix, suffix or None)


def _plain_text_markdown(text: str) -> str:
    """Minimal canonicalization for text/Markdown without changing evidence."""
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _heading_path(headings: list[str]) -> str | None:
    return " > ".join(h for h in headings if h) or None


def _split_table_rows(text: str, max_tokens: int) -> list[str]:
    """Split a Markdown table without cutting a row in half."""
    lines = text.splitlines()
    table_start = next((i for i, line in enumerate(lines) if _TABLE_ROW.match(line)), None)
    if table_start is None:
        return []
    # Keep the heading/preamble attached to the first table chunk. A table is
    # contiguous rows after that point; non-table prose after rows is retained
    # with the final group rather than silently discarded.
    prefix = lines[:table_start]
    out: list[str] = []
    current: list[str] = []
    cells = 0
    for line in lines[table_start:]:
        if not _TABLE_ROW.match(line) and line.strip():
            if current:
                current.append(line)
            else:
                prefix.append(line)
            continue
        row_cells = max(1, line.count("|") - 1)
        if current and (cells + row_cells > MAX_TABLE_CELLS_PER_CHUNK
                        or estimate_tokens("\n".join(current + [line])) > max_tokens):
            out.append("\n".join(prefix + current) if not out else "\n".join(current))
            prefix = []
            current, cells = [], 0
        current.append(line)
        cells += row_cells
    if current:
        out.append("\n".join(prefix + current) if not out else "\n".join(current))
    return out


def _hard_split(text: str, max_tokens: int) -> list[str]:
    max_chars = max(1, max_tokens * 4)
    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]


def _split_section(text: str, max_tokens: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if estimate_tokens(text) <= max_tokens:
        return [text]
    table_chunks = _split_table_rows(text, max_tokens)
    if table_chunks:
        return table_chunks
    out: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for paragraph in _PARA_SPLIT.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        paragraph_tokens = estimate_tokens(paragraph)
        if paragraph_tokens > max_tokens:
            if current:
                out.append("\n\n".join(current))
                current, current_tokens = [], 0
            out.extend(_hard_split(paragraph, max_tokens))
        elif current and current_tokens + paragraph_tokens > max_tokens:
            out.append("\n\n".join(current))
            current, current_tokens = [paragraph], paragraph_tokens
        else:
            current.append(paragraph)
            current_tokens += paragraph_tokens
    if current:
        out.append("\n\n".join(current))
    return out


def chunk_markdown(markdown: str, source_file: str = "", *,
                   max_tokens: int = MAX_CHUNK_TOKENS) -> list[dict[str, Any]]:
    """Chunk Markdown by headings, paragraphs and table rows.

    The heading path is metadata, not prompt text. Each chunk contains a stable
    ordinal and offsets into the exact canonical Markdown string (before any
    prompt fencing), enabling deterministic re-location and benchmark metrics.
    """
    canonical = _plain_text_markdown(markdown)
    if not canonical:
        return []
    sections: list[tuple[str | None, str, int]] = []
    headings: list[str | None] = [None] * 6
    buffer: list[str] = []
    section_start = 0
    offset = 0
    in_fence = False
    for line in canonical.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        if _FENCE.match(stripped):
            in_fence = not in_fence
        match = None if in_fence else _HEADING.match(stripped)
        if match:
            body = "".join(buffer).strip()
            if body:
                sections.append((_heading_path(headings), body, section_start))
            level = len(match.group(1))
            headings[level - 1] = match.group(2).strip()
            for idx in range(level, 6):
                headings[idx] = None
            buffer = [line]
            section_start = offset
        else:
            buffer.append(line)
        offset += len(line)
    body = "".join(buffer).strip()
    if body:
        sections.append((_heading_path(headings), body, section_start))

    chunks: list[dict[str, Any]] = []
    ordinal = 0
    search_from = 0
    for heading_path, section, _section_start in sections:
        for piece in _split_section(section, max_tokens):
            start = canonical.find(piece, search_from)
            if start < 0:  # defensive: should be impossible for exact slices
                start = search_from
            end = start + len(piece)
            chunks.append({
                "text": piece,
                "heading_path": heading_path,
                "position": ordinal,
                "source_file": source_file,
                "start": start,
                "end": end,
                "token_estimate": estimate_tokens(piece),
                "content_kind": "table" if any(_TABLE_ROW.match(x)
                                                 for x in piece.splitlines()) else "text",
            })
            ordinal += 1
            search_from = end
    return chunks


def prompt_chunk(chunk: dict[str, Any], *, source: str = "") -> str:
    """Fence a derived chunk as data before it enters any model context."""
    label = "DOCUMENTO"
    origin = source or str(chunk.get("source_file") or "")
    return fence_block(label, chunk.get("text", ""), index=chunk.get("position"),
                       source=origin)


def derive_office_document(filename: str, data: bytes,
                           declared_mime: str | None = None) -> DerivedDocument | None:
    """Convert an office document with the pinned local AnyDoc binding.

    ``None`` means the binding is unavailable or the format is outside the
    AnyDoc activation set. Conversion errors are deliberately propagated to the
    caller so it can use the established extractor and record the warning.
    """
    if not is_anydoc_candidate(filename):
        return None
    # Va ANTES de comprobar si AnyDoc está instalado: un DOCX grande o con firma
    # falsa nunca puede evadir las cotas cayendo al extractor de respaldo.
    validate_office_source(filename, data, declared_mime)
    if _anydoc is None:
        return None
    fmt = _format_for(filename)
    markdown = _plain_text_markdown(_convert_with_timeout(data, fmt))
    if len(markdown) > MAX_DERIVED_CHARS:
        raise ValueError("La representación Markdown supera el límite local de 8 millones de caracteres")
    blocks = tuple(chunk_markdown(markdown, filename))
    return DerivedDocument(
        source_sha256=hashlib.sha256(data).hexdigest(),
        source_format=fmt or "unknown",
        parser="anydoc",
        parser_version=ANYDOC_VERSION,
        markdown=markdown,
        blocks=blocks,
        warnings=(),
        confidence="structural",
        assets_count=0,
        source_file=filename,
    )


def serialize_chunks(chunks: Iterable[dict[str, Any]]) -> list[str]:
    """Compatibility view for legacy embedding callers."""
    return [str(chunk.get("text", "")) for chunk in chunks if chunk.get("text")]
