"""Mia · memory.playbook_manager — playbooks del despacho (2b).

Un playbook es un procedimiento/estrategia con nombre (p. ej. "Caducidad en acción
de reparación directa"). Tiene dos planos de presencia en el prompt:

  · ÍNDICE — listado compacto de TODOS los playbooks (título + resumen + cuándo
    aplica). SIEMPRE presente en el prompt. Presupuesto ~3.000 tokens.
  · CONTENIDO COMPLETO — el cuerpo del playbook. Caro. Solo se trae ON-DEMAND,
    cuando un playbook se ACTIVA porque aplica al asunto actual. Por defecto el
    contenido NO entra al prompt.

Así el agente siempre "sabe que existe" un playbook (por el índice) y paga el
contenido completo solo cuando de verdad lo va a usar en el asunto.
"""
from __future__ import annotations

from dataclasses import dataclass

from .tokens import estimate_tokens

PLAYBOOK_INDEX_MAX_TOKENS = 3000


@dataclass(frozen=True)
class Playbook:
    """Un playbook. `index_entry()` es lo que va al índice (barato, siempre
    presente); `content` es el cuerpo completo (caro, on-demand)."""

    id: str
    title: str
    summary: str          # 1 línea, para el índice
    applies_when: str     # cuándo aplica, para el índice
    content: str          # cuerpo completo (solo on-demand)

    def index_entry(self) -> str:
        return f"- [{self.id}] {self.title} — {self.summary} (aplica cuando: {self.applies_when})"


class PlaybookManager:
    """Registra playbooks, expone su índice (siempre) y su contenido (on-demand).

    El conjunto ACTIVO son los playbooks que aplican al asunto actual; `reset()` lo
    limpia en la frontera de asunto.
    """

    def __init__(self, pool=None, tenant_id: str | None = None) -> None:
        self._playbooks: dict[str, Playbook] = {}
        self._active: list[str] = []  # ids activos para el asunto actual (en orden)
        # Backend de persistencia (decisión #18). Si `pool` es None, el manager es 100%
        # in-memory (comportamiento original 2b; el gate test_playbook_manager lo usa así).
        # Con `pool` (el módulo db.pool) + `tenant_id`, los métodos *_playbook async
        # leen/escriben en la tabla `playbooks` bajo RLS.
        self._pool = pool
        self._tenant_id = tenant_id

    def register(self, pb: Playbook) -> Playbook:
        """Registra un playbook y revalida el presupuesto del índice."""
        self._playbooks[pb.id] = pb
        self._check_index_budget()
        return pb

    # -- índice: SIEMPRE presente ------------------------------------------------
    def render_index(self) -> str:
        """Índice compacto de TODOS los playbooks. No depende del estado activo."""
        if not self._playbooks:
            return ""
        lines = ["## Playbooks disponibles (índice)"]
        lines += [pb.index_entry() for pb in self._playbooks.values()]
        return "\n".join(lines)

    def index_tokens(self) -> int:
        return estimate_tokens(self.render_index())

    def _check_index_budget(self) -> None:
        n = self.index_tokens()
        if n > PLAYBOOK_INDEX_MAX_TOKENS:
            raise ValueError(
                f"El índice de playbooks excede el presupuesto: {n} > "
                f"{PLAYBOOK_INDEX_MAX_TOKENS} tokens. Recorta los resúmenes o reduce playbooks."
            )

    # -- contenido completo: ON-DEMAND ------------------------------------------
    def get_content(self, playbook_id: str) -> str:
        """Cuerpo completo de un playbook. On-demand: solo cuando se pide explícito."""
        pb = self._playbooks.get(playbook_id)
        if pb is None:
            raise KeyError(f"playbook desconocido: {playbook_id}")
        return pb.content

    def activate(self, playbook_id: str) -> str:
        """Activa un playbook para el asunto actual (porque aplica) y devuelve su
        contenido. Idempotente respecto al conjunto activo."""
        content = self.get_content(playbook_id)
        if playbook_id not in self._active:
            self._active.append(playbook_id)
        return content

    def deactivate(self, playbook_id: str) -> None:
        if playbook_id in self._active:
            self._active.remove(playbook_id)

    def reset(self) -> None:
        """Limpia los playbooks activos (frontera de asunto)."""
        self._active.clear()

    @property
    def active_ids(self) -> list[str]:
        return list(self._active)

    def render_active(self) -> str:
        """Contenido COMPLETO de los playbooks activos. Vacío si no hay ninguno
        activo: por defecto el contenido no entra al prompt."""
        if not self._active:
            return ""
        blocks = []
        for pid in self._active:
            pb = self._playbooks[pid]
            blocks.append(f"## Playbook: {pb.title}\n{pb.content.strip()}")
        return "\n\n".join(blocks)

    # ── backend de DB (decisión #18) ───────────────────────────────────────────
    # Solo activos cuando se construye con PlaybookManager(pool=db.pool, tenant_id=...).
    # Con pool=None hacen fallback al comportamiento in-memory (gate 2b intacto).
    def _tid(self, tenant_id: str | None) -> str | None:
        return tenant_id or self._tenant_id

    async def register_playbook(self, pb: Playbook, tenant_id: str | None = None) -> str:
        """UPSERT del playbook en DB (ON CONFLICT tenant_id+title). Genera y guarda el
        embedding de `summary + applies_when` (voyage-law-2). Devuelve el id (uuid str).
        Sin pool/tenant → fallback in-memory (register())."""
        tid = self._tid(tenant_id)
        if self._pool is None or tid is None:
            self.register(pb)
            return pb.id
        from .. import embeddings
        vec = embeddings.embed_texts([f"{pb.summary}\n{pb.applies_when}"])[0]
        async with self._pool.tenant_connection(tid) as conn:
            row = await (await conn.execute(
                "INSERT INTO playbooks (tenant_id, title, summary, applies_when, content, embedding) "
                "VALUES (%s::uuid, %s, %s, %s, %s, %s) "
                "ON CONFLICT (tenant_id, title) DO UPDATE SET "
                "  summary = EXCLUDED.summary, applies_when = EXCLUDED.applies_when, "
                "  content = EXCLUDED.content, embedding = EXCLUDED.embedding, updated_at = now() "
                "RETURNING id",
                (tid, pb.title, pb.summary, pb.applies_when, pb.content, vec),
            )).fetchone()
        return str(row[0])

    async def get_index(self, tenant_id: str | None = None) -> str:
        """Índice compacto de los playbooks ACTIVOS del tenant (orden por uso desc).
        Sin pool/tenant → fallback in-memory (render_index())."""
        tid = self._tid(tenant_id)
        if self._pool is None or tid is None:
            return self.render_index()
        async with self._pool.tenant_connection(tid) as conn:
            rows = await (await conn.execute(
                "SELECT id, title, summary, applies_when FROM playbooks "
                "WHERE status = 'active' ORDER BY usage_count DESC, created_at"
            )).fetchall()
        if not rows:
            return ""
        lines = ["## Playbooks disponibles (índice)"]
        lines += [f"- [{r[0]}] {r[1]} — {r[2]} (aplica cuando: {r[3]})" for r in rows]
        return "\n".join(lines)

    async def get_playbook(self, title: str, tenant_id: str | None = None) -> dict | None:
        """Playbook activo por título (dict) o None."""
        tid = self._tid(tenant_id)
        if self._pool is None or tid is None:
            return None
        from psycopg.rows import dict_row
        async with self._pool.tenant_connection(tid) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT id, title, summary, applies_when, content, status, usage_count, "
                    "last_used_at FROM playbooks WHERE title = %s AND status = 'active'", (title,))
                return await cur.fetchone()

    async def mark_used(self, playbook_id: str, tenant_id: str | None = None) -> None:
        """Incrementa usage_count y fija last_used_at = now() para el playbook."""
        tid = self._tid(tenant_id)
        if self._pool is None or tid is None:
            return
        async with self._pool.tenant_connection(tid) as conn:
            await conn.execute(
                "UPDATE playbooks SET usage_count = usage_count + 1, last_used_at = now(), "
                "updated_at = now() WHERE id = %s::uuid", (str(playbook_id),))

    async def list_active(self, tenant_id: str | None = None) -> list[dict]:
        """Todos los playbooks activos del tenant (list[dict])."""
        tid = self._tid(tenant_id)
        if self._pool is None or tid is None:
            return []
        from psycopg.rows import dict_row
        async with self._pool.tenant_connection(tid) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT id, title, summary, applies_when, content, status, usage_count, "
                    "last_used_at FROM playbooks WHERE status = 'active' ORDER BY created_at")
                return await cur.fetchall()
