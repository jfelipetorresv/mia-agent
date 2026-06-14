"""Mia · connectors.obsidian_sync — indexador incremental del vault de Obsidian (Módulo 3c).

Escanea un vault de Obsidian, detecta archivos nuevos/cambiados/borrados por hash sha256
(vs. el último hash guardado en `obsidian_file_hashes`), trocea respetando los encabezados
markdown, embebe (voyage-law-2) y los persiste en `knowledge_chunks` (decisión #17): tabla
SEPARADA de documents/chunks porque el conocimiento del despacho no pertenece a un asunto.

Aislamiento: TODA operación de DB por-tenant pasa por `pool.tenant_connection(tenant_id)`
(RLS activo, fail-closed). Embeddings vía `embeddings.embed_texts` (librería LiteLLM, NO el
proxy chat — decisión #17 C2 / Riesgo #4).
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

from .. import embeddings
from ..db import pool
from ..memory.tokens import estimate_tokens

SOURCE = "obsidian"
MAX_CHUNK_TOKENS = 512        # tamaño máx por chunk (estimado ~4 chars/token)
EMBED_BATCH = 128             # máx chunks por llamada de embedding

_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
_PARA_SPLIT = re.compile(r"\n\s*\n")


class ObsidianSync:
    """Sincroniza un vault de Obsidian con `knowledge_chunks` (incremental por hash)."""

    # ── entry point ──────────────────────────────────────────────────────────
    async def sync(self, vault_path, tenant_id: str) -> dict:
        """Indexa los .md nuevos/cambiados, borra los que ya no existen. Devuelve
        {indexed, skipped, deleted, errors}."""
        vault = Path(vault_path)
        stats = {"indexed": 0, "skipped": 0, "deleted": 0, "errors": 0}

        files = self._scan_vault(vault)
        current = {self._rel(vault, f) for f in files}
        stored = await self._get_stored_hashes(tenant_id)
        new_hashes: dict[str, str] = {}

        for f in files:
            rel = self._rel(vault, f)
            try:
                h = self._hash_file(f)
                new_hashes[rel] = h
                if stored.get(rel) == h:
                    stats["skipped"] += 1
                    continue
                content = f.read_text(encoding="utf-8")
                chunks = self._chunk_document(content, rel)
                vectors = await self._embed_chunks([c["text"] for c in chunks])
                await self._upsert_chunks(tenant_id, rel, chunks, vectors)
                stats["indexed"] += 1
            except Exception:
                stats["errors"] += 1
                # no guardamos el hash de un archivo que falló → reintenta la próxima vez
                new_hashes.pop(rel, None)

        stats["deleted"] = await self._delete_removed(tenant_id, current)
        await self._save_hashes(tenant_id, new_hashes)
        return stats

    # ── escaneo del vault ────────────────────────────────────────────────────
    def _scan_vault(self, vault_path) -> list[Path]:
        """Todos los .md del vault (recursivo). Excluye carpetas que empiecen con '.'
        (p. ej. .obsidian) y archivos que empiecen con '_' (plantillas/borradores)."""
        vault = Path(vault_path)
        if not vault.is_dir():
            return []
        out: list[Path] = []
        for p in sorted(vault.rglob("*.md")):
            rel = p.relative_to(vault)
            if any(part.startswith(".") for part in rel.parts):
                continue                       # .obsidian/ y similares
            if p.name.startswith("_"):
                continue                       # _template.md, _draft.md
            out.append(p)
        return out

    @staticmethod
    def _rel(vault: Path, f: Path) -> str:
        """Ruta relativa al vault, con separadores '/' (estable entre SO)."""
        return f.relative_to(vault).as_posix()

    # ── hashing ──────────────────────────────────────────────────────────────
    def _hash_file(self, path) -> str:
        """sha256 del contenido del archivo (hex)."""
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    # ── chunking respetando encabezados ──────────────────────────────────────
    def _chunk_document(self, content: str, filepath: str) -> list[dict]:
        """Trocea respetando H1/H2/H3: cada encabezado inicia un chunk nuevo. Si el bloque
        bajo un encabezado supera MAX_CHUNK_TOKENS, se divide por párrafos (overlap 0).
        Cada chunk: {text, heading_path, position, source_file}."""
        chunks: list[dict] = []
        pos = 0
        for heading_path, body in self._split_by_headings(content):
            body = body.strip()
            if not body:
                continue
            for piece in self._split_to_size(body):
                chunks.append({
                    "text": piece,
                    "heading_path": heading_path or None,
                    "position": pos,
                    "source_file": filepath,
                })
                pos += 1
        return chunks

    def _split_by_headings(self, content: str) -> list[tuple[str, str]]:
        """Parte el documento en segmentos (heading_path, cuerpo). Un encabezado H1/H2/H3
        cierra el segmento previo e inicia uno nuevo (la línea del encabezado va en el
        cuerpo nuevo). El preámbulo antes del primer encabezado tiene heading_path ''."""
        segments: list[tuple[str, str]] = []
        h1 = h2 = h3 = None
        cur_path = ""
        buf: list[str] = []
        for line in content.splitlines():
            m = _HEADING.match(line)
            if m:
                if buf:
                    segments.append((cur_path, "\n".join(buf)))
                    buf = []
                level, text = len(m.group(1)), m.group(2).strip()
                if level == 1:
                    h1, h2, h3 = text, None, None
                elif level == 2:
                    h2, h3 = text, None
                else:
                    h3 = text
                cur_path = " > ".join(p for p in (h1, h2, h3) if p)
                buf.append(line)
            else:
                buf.append(line)
        if buf:
            segments.append((cur_path, "\n".join(buf)))
        return segments

    def _split_to_size(self, body: str) -> list[str]:
        """Si el bloque cabe en MAX_CHUNK_TOKENS, lo deja entero; si no, lo divide por
        párrafos (empacando hasta el límite). Un párrafo aislado más grande que el límite
        se parte por caracteres."""
        if estimate_tokens(body) <= MAX_CHUNK_TOKENS:
            return [body]
        out: list[str] = []
        cur: list[str] = []
        cur_tok = 0
        for para in _PARA_SPLIT.split(body):
            para = para.strip()
            if not para:
                continue
            ptok = estimate_tokens(para)
            if ptok > MAX_CHUNK_TOKENS:
                if cur:
                    out.append("\n\n".join(cur))
                    cur, cur_tok = [], 0
                out.extend(self._hard_split(para))
                continue
            if cur and cur_tok + ptok > MAX_CHUNK_TOKENS:
                out.append("\n\n".join(cur))
                cur, cur_tok = [], 0
            cur.append(para)
            cur_tok += ptok
        if cur:
            out.append("\n\n".join(cur))
        return out

    @staticmethod
    def _hard_split(text: str) -> list[str]:
        max_chars = MAX_CHUNK_TOKENS * 4   # ~4 chars/token
        return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]

    # ── embeddings (librería LiteLLM, batches de 128) ────────────────────────
    async def _embed_chunks(self, texts: list[str]) -> list[list[float]]:
        """Embebe los textos en batches de EMBED_BATCH vía embeddings.embed_texts
        (voyage-law-2). NO usa call_llm: los embeddings van por la librería, no el proxy
        chat (decisión #17 C2 / Riesgo #4)."""
        if not texts:
            return []
        vectors: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH):
            batch = texts[i:i + EMBED_BATCH]
            vectors.extend(embeddings.embed_texts(batch))
        return vectors

    # ── persistencia en knowledge_chunks (RLS por tenant) ────────────────────
    async def _upsert_chunks(self, tenant_id: str, filepath: str,
                             chunks: list[dict], vectors: list[list[float]]) -> None:
        """Upsert de los chunks de un archivo en knowledge_chunks. Re-indexa en sitio
        (ON CONFLICT) y borra los chunks sobrantes si el archivo encogió."""
        async with pool.tenant_connection(tenant_id) as conn:
            for chunk, vec in zip(chunks, vectors):
                await conn.execute(
                    "INSERT INTO knowledge_chunks "
                    "  (tenant_id, source, source_path, chunk_index, heading_path, content, embedding) "
                    "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (tenant_id, source, source_path, chunk_index) DO UPDATE SET "
                    "  heading_path = EXCLUDED.heading_path, content = EXCLUDED.content, "
                    "  embedding = EXCLUDED.embedding, updated_at = now()",
                    (tenant_id, SOURCE, filepath, chunk["position"],
                     chunk["heading_path"], chunk["text"], vec),
                )
            # el archivo pudo encoger: elimina los chunks con índice >= nuevos.
            await conn.execute(
                "DELETE FROM knowledge_chunks WHERE tenant_id = %s::uuid AND source = %s "
                "AND source_path = %s AND chunk_index >= %s",
                (tenant_id, SOURCE, filepath, len(chunks)),
            )

    async def _delete_removed(self, tenant_id: str, current_files: Iterable[str]) -> int:
        """Borra de knowledge_chunks los chunks cuyo source_path ya no existe en el vault.
        Devuelve el número de ARCHIVOS eliminados."""
        current = list(current_files)
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT DISTINCT source_path FROM knowledge_chunks "
                "WHERE tenant_id = %s::uuid AND source = %s",
                (tenant_id, SOURCE),
            )).fetchall()
            stored_paths = {r[0] for r in rows}
            removed = sorted(stored_paths - set(current))
            if removed:
                await conn.execute(
                    "DELETE FROM knowledge_chunks WHERE tenant_id = %s::uuid AND source = %s "
                    "AND source_path = ANY(%s)",
                    (tenant_id, SOURCE, removed),
                )
        return len(removed)

    # ── hashes (RLS por tenant) ──────────────────────────────────────────────
    async def _get_stored_hashes(self, tenant_id: str) -> dict[str, str]:
        """{vault_path_relativo: sha256} guardados para el tenant."""
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT vault_path, file_hash FROM obsidian_file_hashes WHERE tenant_id = %s::uuid",
                (tenant_id,),
            )).fetchall()
        return {r[0]: r[1] for r in rows}

    async def _save_hashes(self, tenant_id: str, hashes: dict[str, str]) -> None:
        """Persiste el set de hashes vigente: upsert de los actuales + borra los de archivos
        que ya no están (mantiene la tabla en espejo con el vault)."""
        async with pool.tenant_connection(tenant_id) as conn:
            for vault_path, file_hash in hashes.items():
                await conn.execute(
                    "INSERT INTO obsidian_file_hashes (tenant_id, vault_path, file_hash) "
                    "VALUES (%s::uuid, %s, %s) "
                    "ON CONFLICT (tenant_id, vault_path) DO UPDATE SET "
                    "  file_hash = EXCLUDED.file_hash, last_indexed = now()",
                    (tenant_id, vault_path, file_hash),
                )
            await conn.execute(
                "DELETE FROM obsidian_file_hashes WHERE tenant_id = %s::uuid "
                "AND NOT (vault_path = ANY(%s))",
                (tenant_id, list(hashes.keys()) or [""]),
            )
