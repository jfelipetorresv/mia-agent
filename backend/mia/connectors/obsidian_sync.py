"""Mia · connectors.obsidian_sync — indexador incremental del vault de Obsidian (Módulo 3c).

Escanea un vault de Obsidian, detecta archivos nuevos/cambiados/borrados por hash sha256
(vs. el último hash guardado en `obsidian_file_hashes`), trocea respetando los encabezados
markdown, embebe (voyage-law-2) y los persiste en `knowledge_chunks` (decisión #17): tabla
SEPARADA de documents/chunks porque el conocimiento del despacho no pertenece a un asunto.

INGESTA CONSCIENTE DE LA ESTRUCTURA (migración 039). Un vault no es una carpeta de PDFs: es
un segundo cerebro donde la ESTRUCTURA carga tanta información como el texto. Se parsea:

  1) el frontmatter YAML → metadatos consultables (`frontmatter` jsonb) + dos campos
     normalizados que la recuperación puede filtrar (`doc_status`, `doc_type`). Antes de 039
     el YAML entraba como texto literal dentro del primer chunk: basura para el embedding.
  2) los `[[wikilinks]]` → `links` jsonb POR CHUNK, con el motivo del vínculo cuando el vault
     lo declara (campos inline de Dataview `clave:: [[destino]]`, o claves del frontmatter).
     No se construye un grafo: el enlace se guarda donde aparece y se consulta con `@>`.

DEGRADAR CON GRACIA ES EL REQUISITO, NO EL EXTRA. El vault que se conecta es el que el
despacho YA tiene — no uno que van a rehacer para Mia. Aquí no hay esquema obligatorio:
  · sin frontmatter        → se ingiere EXACTAMENTE igual que antes de 039 (cero regresión);
  · campos desconocidos    → se conservan crudos en `frontmatter`, no rompen nada;
  · YAML mal formado       → el documento se ingiere como texto plano (comportamiento previo)
                             y se registra; JAMÁS tumba la sincronización del vault entero;
  · sin PyYAML instalado   → todo el vault degrada al comportamiento previo, sin excepción.
Los nombres de campo de un vault concreto NO son un estándar: se aceptan variantes razonables
(ver `_FIELD_ALIASES`) y lo que no se entiende se conserva sin interpretarse.

Agnosticismo (regla dura): frontmatter y wikilinks son de Obsidian, no de una jurisdicción.
Nada en este módulo conoce un país. Las variantes de `_FIELD_ALIASES` son de IDIOMA (es/en),
que es el idioma del dueño del vault, no su jurisdicción.

Aislamiento: TODA operación de DB por-tenant pasa por `pool.tenant_connection(tenant_id)`
(RLS activo, fail-closed). Embeddings vía `embeddings.embed_texts` (librería LiteLLM, NO el
proxy chat — decisión #17 C2 / Riesgo #4).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime, time
from pathlib import Path
from typing import Iterable

try:                     # PyYAML llega con el runtime del API; si faltara, el vault se
    import yaml          # ingiere como texto plano (comportamiento previo a 039) en vez
except ImportError:      # de romper la sincronización. Fail-soft, no fail-hard.
    yaml = None          # type: ignore[assignment]

from .. import embeddings
from ..db import pool
from ..memory.tokens import estimate_tokens
from .pinecone_connector import pinecone_scope_for_tenant

logger = logging.getLogger("mia.connectors.obsidian_sync")

SOURCE = "obsidian"
MAX_CHUNK_TOKENS = 512        # tamaño máx por chunk (estimado ~4 chars/token)
EMBED_BATCH = 128             # máx chunks por llamada de embedding

MAX_FRONTMATTER_BYTES = 8192  # tope del frontmatter serializado por documento (ver _sanitize)
MAX_LINKS_PER_CHUNK = 200     # tope de enlaces por chunk: un MOC gigante no infla la fila
MAX_FIELD_CHARS = 2000        # tope por valor de frontmatter (una nota no es un almacén)

_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
_PARA_SPLIT = re.compile(r"\n\s*\n")

# ── frontmatter ──────────────────────────────────────────────────────────────
# Obsidian solo reconoce frontmatter si el archivo ARRANCA con '---' en su primera línea;
# se cierra con '---' o '...' (YAML). Un '---' más abajo es una regla horizontal, no metadatos.
_FM_OPEN = re.compile(r"^---[ \t]*$")
_FM_CLOSE = re.compile(r"^(?:---|\.\.\.)[ \t]*$")

# Variantes de nombre que SÍ interpretamos. No es un esquema obligatorio: es un diccionario de
# sinónimos observados en vaults reales (es/en). Lo que no está aquí NO se pierde — se conserva
# crudo en `frontmatter` y sigue siendo consultable con `frontmatter @> '{...}'`.
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "doc_status": ("status", "estado", "state", "stage", "etapa", "madurez", "maturity"),
    "doc_type": ("type", "tipo", "kind", "clase", "category", "categoria", "categoría"),
}

# Vocabulario CERRADO de estado. Solo se normaliza lo que se entiende SIN adivinar; cualquier
# otra palabra deja doc_status en NULL (= "no sé"), que NO es lo mismo que 'borrador'. Incluye
# la convención de jardín digital (seedling/budding/evergreen), muy común en vaults reales.
_STATUS_VERIFICADO = frozenset({
    "verificado", "verificada", "verified", "final", "finalizado", "aprobado", "approved",
    "publicado", "published", "done", "listo", "revisado", "reviewed", "evergreen", "maduro",
})
_STATUS_BORRADOR = frozenset({
    "borrador", "draft", "wip", "work-in-progress", "in-progress", "en progreso",
    "en-progreso", "incompleto", "incomplete", "idea", "seedling", "budding", "semilla",
    "pendiente", "todo", "sin revisar", "unreviewed",
})

# ── wikilinks ────────────────────────────────────────────────────────────────
# Captura [[destino]], [[destino|alias]], [[destino#sección]] y el embed ![[destino]].
_WIKILINK = re.compile(r"!?\[\[([^\[\]\n]+?)\]\]")
# Campo inline de Dataview: `clave:: valor` (con o sin viñeta/negrita). Es la ÚNICA convención
# de Obsidian en la que el vault DECLARA por qué dos notas se tocan; de ahí sale `rel`.
_INLINE_FIELD = re.compile(r"^\s*(?:[-*+]\s+)?\*{0,2}([^:\n\[\]|]{1,40}?)\*{0,2}\s*::\s*(.+)$")
_FENCE = re.compile(r"^\s*(?:```|~~~)")
_INLINE_CODE = re.compile(r"`[^`\n]*`")
# Adjuntos: `![[diagrama.png]]` es una imagen incrustada, no una relación entre ideas.
_MEDIA_EXT = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".pdf", ".mp3", ".mp4",
    ".wav", ".m4a", ".mov", ".webm", ".ogg", ".excalidraw", ".canvas", ".zip",
})


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

        Antes de trocear separa el frontmatter (039): el YAML deja de ser texto del chunk y
        pasa a metadatos. Un documento SIN frontmatter recorre exactamente el mismo camino que
        antes de 039 y produce los mismos chunks — esa es la garantía de cero regresión.

        Cada chunk: {text, heading_path, position, source_file, frontmatter, doc_status,
        doc_type, links}. `heading_path` (la miga de pan) se conserva intacto."""
        meta, body_text = self._parse_frontmatter(content, filepath)
        fm_links = self._links_from_frontmatter(meta)

        chunks: list[dict] = []
        pos = 0
        for heading_path, body in self._split_by_headings(body_text):
            body = body.strip()
            if not body:
                continue
            for piece in self._split_to_size(body):
                chunks.append({
                    "text": piece,
                    "heading_path": heading_path or None,
                    "position": pos,
                    "source_file": filepath,
                    "frontmatter": meta,
                    "doc_status": self._normalize_status(meta),
                    "doc_type": self._normalize_type(meta),
                    # Los enlaces se guardan DONDE APARECEN, que es donde se recuperan.
                    "links": self._links_from_text(piece),
                })
                pos += 1

        # Los enlaces declarados en el frontmatter no viven en ningún cuerpo: van al primer
        # chunk del documento, que es el que lo representa. Si el documento no tiene cuerpo
        # (solo frontmatter) no hay chunk donde ponerlos y se pierden: correcto — un documento
        # sin texto no aporta nada que recuperar.
        if chunks and fm_links:
            chunks[0]["links"] = self._dedupe_links(fm_links + chunks[0]["links"])
        return chunks

    # ── frontmatter (039) ────────────────────────────────────────────────────
    def _parse_frontmatter(self, content: str, filepath: str = "") -> tuple[dict, str]:
        """Separa el frontmatter YAML del cuerpo. Devuelve (metadatos, cuerpo).

        Fail-soft por documento y en TODOS los caminos: si no hay frontmatter, si el YAML está
        roto, si no es un mapa (`- una: lista` al inicio) o si PyYAML no está instalado, se
        devuelve ({}, content) — es decir, EXACTAMENTE lo que hacía el indexador antes de 039:
        el documento se ingiere como texto plano. Un vault con una nota rota se sincroniza
        entero; solo esa nota pierde sus metadatos, y queda registrado."""
        raw = self._split_frontmatter_block(content)
        if raw is None:
            return {}, content                      # sin frontmatter: camino previo a 039
        yaml_text, body = raw
        if yaml is None:
            logger.warning("obsidian: PyYAML no está disponible; %s se ingiere como texto "
                           "plano (sin metadatos)", filepath or "<nota>")
            return {}, content
        try:
            data = yaml.safe_load(yaml_text)
        except Exception as exc:                    # YAMLError y cualquier sorpresa del loader
            logger.warning("obsidian: frontmatter mal formado en %s (%s); la nota se ingiere "
                           "como texto plano, la sincronización continúa",
                           filepath or "<nota>", exc.__class__.__name__)
            return {}, content
        if not isinstance(data, dict):
            # `---\n- a\n- b\n---` es YAML VÁLIDO pero no son metadatos de nota. No inventamos
            # un esquema: se trata como texto, igual que antes.
            logger.info("obsidian: el frontmatter de %s no es un mapa de campos; se ingiere "
                        "como texto plano", filepath or "<nota>")
            return {}, content
        return self._sanitize_frontmatter(data, filepath), body

    @staticmethod
    def _split_frontmatter_block(content: str) -> tuple[str, str] | None:
        """(yaml_text, cuerpo) si el documento abre con un bloque '---' cerrado; None si no.

        Solo cuenta el '---' de la PRIMERA línea (regla de Obsidian). Sin línea de cierre no
        hay frontmatter: un documento que empieza con una regla horizontal se queda intacto."""
        if not content.startswith("---"):
            return None                             # atajo barato: el 99% de las notas
        lines = content.splitlines(keepends=True)
        if not lines or not _FM_OPEN.match(lines[0].rstrip("\r\n")):
            return None
        for i in range(1, len(lines)):
            if _FM_CLOSE.match(lines[i].rstrip("\r\n")):
                return "".join(lines[1:i]), "".join(lines[i + 1:])
        return None                                 # abre y nunca cierra → no es frontmatter

    def _sanitize_frontmatter(self, data: dict, filepath: str = "") -> dict:
        """Convierte el YAML a JSON guardable: claves str, fechas a ISO, tipos raros a texto.

        Se conserva TODO el frontmatter, no solo los campos que entendemos — los campos
        desconocidos de hoy son las consultas de mañana, y descartarlos sería volver a decidir
        por el despacho qué estructura le vale. Solo se aplican topes de tamaño (una nota no
        es un almacén) y, si aun así no cabe, se descarta el frontmatter completo antes que
        guardar un jsonb desbocado."""
        out: dict = {}
        for key, value in data.items():
            k = str(key).strip()
            if k:
                out[k] = self._json_safe(value)
        if len(json.dumps(out, ensure_ascii=False).encode("utf-8")) > MAX_FRONTMATTER_BYTES:
            logger.warning("obsidian: frontmatter de %s supera %d bytes; se ingiere sin "
                           "metadatos", filepath or "<nota>", MAX_FRONTMATTER_BYTES)
            return {}
        return out

    def _json_safe(self, value, depth: int = 0):
        """Valor YAML → valor JSON. Las fechas (que YAML sí tipa) van a ISO; lo que no sepamos
        representar va a str, nunca a excepción."""
        if value is None or isinstance(value, bool) or isinstance(value, int):
            return value
        if isinstance(value, float):
            return value if value == value and abs(value) != float("inf") else str(value)
        if isinstance(value, str):
            return value[:MAX_FIELD_CHARS]
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        if depth >= 4:                              # frontmatter anidado hasta el absurdo
            return str(value)[:MAX_FIELD_CHARS]
        if isinstance(value, (list, tuple, set)):
            return [self._json_safe(v, depth + 1) for v in list(value)[:100]]
        if isinstance(value, dict):
            return {str(k).strip(): self._json_safe(v, depth + 1)
                    for k, v in list(value.items())[:100] if str(k).strip()}
        return str(value)[:MAX_FIELD_CHARS]

    @staticmethod
    def _field(meta: dict, canonical: str):
        """Primer valor del frontmatter cuyo nombre coincide con alguna variante conocida.
        La comparación ignora mayúsculas, guiones y guiones bajos: `Doc-Type`, `doc_type` y
        `tipo` llegan al mismo sitio. El nombre canónico cuenta como variante de sí mismo."""
        def norm(s: str) -> str:
            return re.sub(r"[\s_\-]+", "", str(s)).strip().lower()

        wanted = {norm(a) for a in (canonical, *_FIELD_ALIASES[canonical])}
        for key, value in meta.items():
            if norm(key) in wanted and value not in (None, "", [], {}):
                return value
        return None

    def _normalize_status(self, meta: dict) -> str | None:
        """'verificado' | 'borrador' | None. None = el vault no lo dice o lo dice con una
        palabra que no sabemos mapear.

        NO ADIVINAR ES LA FUNCIÓN. Mapear un estado desconocido a 'borrador' descartaría en
        silencio criterio bueno del despacho; mapearlo a 'verificado' le daría el peso del
        criterio verificado a una nota a medias. Ante la duda, None: que decida quien recupere
        (el valor crudo sigue en `frontmatter` para el que quiera hilar más fino)."""
        value = self._field(meta, "doc_status")
        if isinstance(value, (list, tuple)):        # `estado: [borrador]`
            value = value[0] if value else None
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            return None
        word = re.sub(r"[\s_\-]+", " ", str(value)).strip().lower().lstrip("#")
        if word in _STATUS_VERIFICADO:
            return "verificado"
        if word in _STATUS_BORRADOR:
            return "borrador"
        return None

    def _normalize_type(self, meta: dict) -> str | None:
        """Tipo declarado, en minúsculas. Sin vocabulario cerrado: cada vault nombra sus
        tipos y no nos toca a nosotros decirle cuáles valen."""
        value = self._field(meta, "doc_type")
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            return None
        word = str(value).strip().lstrip("#").strip()
        return word.lower()[:100] or None

    # ── wikilinks (039) ──────────────────────────────────────────────────────
    def _links_from_text(self, text: str) -> list[dict]:
        """`[[wikilinks]]` de un fragmento, con el motivo del vínculo cuando se declara.

        Cada enlace: {"to", "to_key", "rel"}.
          · to     — el destino tal como lo escribió el autor (sin '#sección' ni '|alias').
          · to_key — clave de unión normalizada (nombre de la nota, minúsculas, sin '.md' ni
                     carpetas) para casar el enlace con `source_path` sin que quien recupere
                     tenga que reimplementar esta normalización.
          · rel    — POR QUÉ se tocan las dos notas, si el vault lo declara con un campo
                     inline de Dataview (`fundamenta:: [[X]]`). None si es un enlace suelto:
                     no se inventa un motivo que el autor no escribió.

        Lo que se ignora A PROPÓSITO: el alias de `[[nota|alias]]` (es texto de presentación,
        no dice nada de la relación), el '#sección' del destino (el enlace es a la nota), los
        enlaces dentro de bloques de código (son ejemplos, no relaciones) y los adjuntos de
        medios (`![[diagrama.png]]` es una imagen, no una idea)."""
        out: list[dict] = []
        for line in self._strip_code(text).splitlines():
            m = _INLINE_FIELD.match(line)
            rel, scan = (None, line)
            if m:
                candidate = m.group(1).strip().lower()
                # Un campo inline sin destino enlazado no es una relación; y una clave vacía
                # tampoco. `rel` solo existe si acompaña a wikilinks en la misma línea.
                if candidate and _WIKILINK.search(m.group(2)):
                    rel, scan = candidate[:60], m.group(2)
            for raw in _WIKILINK.findall(scan):
                link = self._make_link(raw, rel)
                if link:
                    out.append(link)
        return self._dedupe_links(out)

    def _links_from_frontmatter(self, meta: dict) -> list[dict]:
        """Enlaces declarados en el frontmatter (`fundamento: "[[X]]"`, `related: [[[A]], [[B]]]`).
        La CLAVE del campo es el motivo del vínculo — es la otra forma en que un vault declara
        por qué dos notas se tocan, y sale gratis."""
        out: list[dict] = []
        for key, value in meta.items():
            rel = str(key).strip().lower()[:60] or None
            for text in self._flatten_strings(value):
                for raw in _WIKILINK.findall(text):
                    link = self._make_link(raw, rel)
                    if link:
                        out.append(link)
        return self._dedupe_links(out)

    def _flatten_strings(self, value, depth: int = 0) -> list[str]:
        if isinstance(value, str):
            return [value]
        if depth >= 3:
            return []
        if isinstance(value, (list, tuple)):
            return [s for v in value for s in self._flatten_strings(v, depth + 1)]
        if isinstance(value, dict):
            return [s for v in value.values() for s in self._flatten_strings(v, depth + 1)]
        return []

    @staticmethod
    def _make_link(raw: str, rel: str | None) -> dict | None:
        """'carpeta/Nota Uno#Sección|alias' → {"to": "carpeta/Nota Uno", "to_key": "nota uno",
        "rel": rel}. None si el destino no es una nota (adjunto) o queda vacío.

        Un destino inexistente ('[[Nota Que No Existe]]') se conserva igual: el enlace roto ES
        información sobre el vault, y resolverlo no es trabajo de la ingesta."""
        target = raw.split("|", 1)[0]          # se descarta el alias: es presentación
        target = target.split("#", 1)[0]       # el enlace es a la nota, no a la sección
        target = target.split("^", 1)[0].strip()
        if not target:
            return None                        # '[[|solo alias]]' o '[[#solo sección]]'
        key = target.replace("\\", "/").rsplit("/", 1)[-1].strip()
        suffix = Path(key).suffix.lower()
        if suffix in _MEDIA_EXT:
            return None                        # adjunto, no una nota
        if suffix == ".md":
            key = key[:-3]
        key = key.strip().lower()
        if not key:
            return None
        return {"to": target[:300], "to_key": key[:300], "rel": rel}

    @staticmethod
    def _dedupe_links(links: list[dict]) -> list[dict]:
        """Sin repetidos (mismo destino + mismo motivo), en orden de aparición y con tope."""
        seen: set[tuple[str, str | None]] = set()
        out: list[dict] = []
        for link in links:
            k = (link["to_key"], link["rel"])
            if k in seen:
                continue
            seen.add(k)
            out.append(link)
            if len(out) >= MAX_LINKS_PER_CHUNK:
                break
        return out

    @staticmethod
    def _strip_code(text: str) -> str:
        """Quita bloques cercados y código inline ANTES de buscar enlaces. Un `[[ejemplo]]`
        dentro de un bloque de código es documentación, no una relación del vault. Solo afecta
        a la extracción de enlaces: el texto del chunk se guarda completo, sin tocar."""
        out: list[str] = []
        fenced = False
        for line in text.splitlines():
            if _FENCE.match(line):
                fenced = not fenced
                continue
            out.append("" if fenced else _INLINE_CODE.sub(" ", line))
        return "\n".join(out)

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
    async def _embed_chunks(self, texts: list[str]) -> list[list[float] | None]:
        """Embebe los textos en batches de EMBED_BATCH vía embeddings.embed_texts
        (voyage-law-2). NO usa call_llm: los embeddings van por la librería, no el proxy
        chat (decisión #17 C2 / Riesgo #4)."""
        if not texts:
            return []
        vectors: list[list[float] | None] = []
        for i in range(0, len(texts), EMBED_BATCH):
            batch = texts[i:i + EMBED_BATCH]
            vectors.extend(embeddings.embed_texts_optional(batch))
        return vectors

    # ── persistencia en knowledge_chunks (RLS por tenant) ────────────────────
    async def _upsert_chunks(self, tenant_id: str, filepath: str,
                             chunks: list[dict], vectors: list[list[float] | None]) -> None:
        """Upsert de los chunks de un archivo en knowledge_chunks. Re-indexa en sitio
        (ON CONFLICT) y borra los chunks sobrantes si el archivo encogió.

        Los campos de estructura (039) se escriben SIEMPRE, también en el UPDATE: si una nota
        pasa de 'borrador' a 'verificado', o se le quita un enlace, la fila re-indexada tiene
        que reflejarlo. Un chunk sin frontmatter escribe '{}' / '[]' — los mismos valores que
        el DEFAULT de la migración, así que un vault de texto plano queda idéntico a antes."""
        async with pool.tenant_connection(tenant_id) as conn:
            for chunk, vec in zip(chunks, vectors):
                await conn.execute(
                    "INSERT INTO knowledge_chunks "
                    "  (tenant_id, source, source_path, chunk_index, heading_path, content, "
                    "   embedding, frontmatter, links, doc_status, doc_type) "
                    "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s) "
                    "ON CONFLICT (tenant_id, source, source_path, chunk_index) DO UPDATE SET "
                    "  heading_path = EXCLUDED.heading_path, content = EXCLUDED.content, "
                    "  embedding = EXCLUDED.embedding, frontmatter = EXCLUDED.frontmatter, "
                    "  links = EXCLUDED.links, doc_status = EXCLUDED.doc_status, "
                    "  doc_type = EXCLUDED.doc_type, updated_at = now()",
                    (tenant_id, SOURCE, filepath, chunk["position"],
                     chunk["heading_path"], chunk["text"], vec,
                     json.dumps(chunk.get("frontmatter") or {}, ensure_ascii=False),
                     json.dumps(chunk.get("links") or [], ensure_ascii=False),
                     chunk.get("doc_status"), chunk.get("doc_type")),
                )
            # el archivo pudo encoger: elimina los chunks con índice >= nuevos.
            pruned = await (await conn.execute(
                "DELETE FROM knowledge_chunks WHERE tenant_id = %s::uuid AND source = %s "
                "AND source_path = %s AND chunk_index >= %s RETURNING chunk_index",
                (tenant_id, SOURCE, filepath, len(chunks)),
            )).fetchall()
        await self._pinecone_mirror_upsert(tenant_id, filepath, chunks, vectors,
                                           pruned_indices=[r[0] for r in pruned])

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
            deleted_rows: list[tuple] = []
            if removed:
                deleted_rows = await (await conn.execute(
                    "DELETE FROM knowledge_chunks WHERE tenant_id = %s::uuid AND source = %s "
                    "AND source_path = ANY(%s) RETURNING source_path, chunk_index",
                    (tenant_id, SOURCE, removed),
                )).fetchall()
        if deleted_rows:
            ids = [f"{SOURCE}:{path}:{idx}" for path, idx in deleted_rows]
            await self._pinecone_mirror_delete(tenant_id, ids)
        return len(removed)

    # ── espejo en Pinecone (store SECUNDARIO opt-in, Módulo A) ───────────────
    async def _pinecone_mirror_upsert(self, tenant_id: str, filepath: str,
                                      chunks: list[dict], vectors: list[list[float] | None],
                                      *, pruned_indices: list[int]) -> None:
        """Espeja el upsert (y la poda por encogimiento) de ESTA nota en Pinecone. Id
        determinista `{SOURCE}:{filepath}:{chunk_index}`: un re-sync hace upsert en
        sitio, nunca duplica. FAIL-SOFT total (mismo patrón que `wiki_notes` /
        `_notebooklm_context`): knowledge_chunks YA quedó escrito arriba; si Pinecone
        no está configurado (Noop) o la llamada falla, el sync del vault sigue igual."""
        try:
            async with pinecone_scope_for_tenant(tenant_id) as pc:
                if not pc.is_configured:
                    return
                if chunks:
                    vectors_pc = []
                    for chunk, vec in zip(chunks, vectors):
                        if vec is None:
                            continue
                        metadata = {
                            "content": (chunk["text"] or "")[:2000],
                            "source": SOURCE,
                            "source_path": filepath,
                        }
                        if chunk.get("heading_path"):
                            metadata["heading_path"] = chunk["heading_path"]
                        vectors_pc.append({
                            "id": f"{SOURCE}:{filepath}:{chunk['position']}",
                            "values": vec,
                            "metadata": metadata,
                        })
                    await pc.upsert(tenant_id, vectors_pc)
                if pruned_indices:
                    ids = [f"{SOURCE}:{filepath}:{idx}" for idx in pruned_indices]
                    await pc.delete(tenant_id, ids)
        except Exception:  # noqa: BLE001 — Pinecone es opcional, jamás tumba el sync
            logger.warning("pinecone: upsert omitido para %s (tenant=%s)",
                           filepath, tenant_id, exc_info=True)

    async def _pinecone_mirror_delete(self, tenant_id: str, ids: list[str]) -> None:
        """Espeja en Pinecone el borrado de chunks cuyas notas desaparecieron del vault.
        FAIL-SOFT total — ver `_pinecone_mirror_upsert`."""
        try:
            async with pinecone_scope_for_tenant(tenant_id) as pc:
                if not pc.is_configured:
                    return
                await pc.delete(tenant_id, ids)
        except Exception:  # noqa: BLE001 — Pinecone es opcional, jamás tumba el sync
            logger.warning("pinecone: delete omitido para %d ids (tenant=%s)",
                           len(ids), tenant_id, exc_info=True)

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
