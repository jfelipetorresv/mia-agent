"""Mia · agents.context_recovery — recorte de material por nodo ante CONTEXT_TOO_LONG (CP1).

Cierra el Riesgo #33: los nodos `analysis`/`draft` arman prompts monolíticos de 2 mensajes
[system, user], y `ContextCompressor` (pensado para HISTORIALES: protege first=5/last=30)
los devuelve intactos → el reintento tras CONTEXT_TOO_LONG fallaba exactamente igual.

Estos helpers son PUROS (sin LLM, sin DB, sin red) y deterministas: reconstruyen el
MATERIAL pesado del prompt (documentos del expediente, diagnóstico, playbooks) bajo un
presupuesto de tokens, usando el estimador offline de `memory/tokens.py`. Cada nodo pasa
a `graph._llm` un callable `shrink` que rearma su prompt reducido con estos helpers; el
contrato una-sola-compresión-por-turno (TurnLLMState) se mantiene en `_llm`.
"""
from __future__ import annotations

from ..memory.tokens import estimate_tokens

# ── Presupuestos por nodo ────────────────────────────────────────────────────────
# Fracción de la ventana del modelo destinada al MATERIAL pesado del user prompt del
# nodo (el resto queda para system/SOUL, la consulta del abogado y la respuesta).
NODE_BUDGET_FRACTION: dict[str, float] = {
    "facts": 0.60,      # documentos del expediente embebidos en el user de facts (CP9)
    "research": 0.40,   # hechos del especialista en el user de research (CP9)
    "analysis": 0.60,   # documentos del expediente embebidos en el user de analysis
    "draft": 0.50,      # diagnóstico (+ perfil/playbooks) en el user de draft
}
DEFAULT_BUDGET_FRACTION = 0.50

# Coherente con memory/tokens.py (~4 caracteres por token, heurística offline).
_CHARS_PER_TOKEN = 4

# Contenido mínimo "útil" que SIEMPRE conserva un documento tras el recorte.
MIN_DOC_TOKENS = 50

# Marcadores visibles en el prompt reducido (transparencia hacia el modelo; el abogado
# nunca los ve — §G: viven dentro del prompt, no en la UI).
DOC_TRUNCATED_MARKER = ("\n[... documento recortado por límite de contexto — "
                        "ver expediente completo]")
TEXT_CUT_MARKER = "[... sección recortada ...]"
PLAYBOOKS_TRIMMED_MARKER = ("[... playbooks recortados por límite de contexto — "
                            "se conserva solo el índice ...]")
KNOWLEDGE_TRIMMED_MARKER = ("[... conocimiento del despacho recortado por límite de "
                            "contexto — el expediente se conserva ...]")


def budget_for(node: str, window: int) -> int:
    """Presupuesto de tokens de MATERIAL para `node` dada la ventana del modelo.

    Nodo desconocido → DEFAULT_BUDGET_FRACTION (conservador). Siempre ≥ 1.
    """
    frac = NODE_BUDGET_FRACTION.get(node, DEFAULT_BUDGET_FRACTION)
    return max(1, int(window * frac))


def shrink_documents(docs: list[dict], budget_tokens: int) -> list[dict]:
    """Reduce los documentos recuperados a un presupuesto de tokens (Riesgo #33).

    Estrategia en dos pasos:
      1. Reduce la CANTIDAD a la mitad (8→4), conservando el orden del ranking RRF
         (los primeros son los más relevantes). Nunca deja 0 documentos.
      2. Trunca el `content` de cada superviviente al presupuesto proporcional
         (budget/n, con piso MIN_DOC_TOKENS) y marca los truncados con
         DOC_TRUNCATED_MARKER.

    No muta los dicts de entrada (devuelve copias). Con `docs` vacío devuelve [].
    """
    if not docs:
        return []
    kept = docs[: max(1, len(docs) // 2)]
    per_doc_tokens = max(budget_tokens // len(kept), MIN_DOC_TOKENS)
    out: list[dict] = []
    for d in kept:
        nd = dict(d)
        content = str(nd.get("content") or "")
        if estimate_tokens(content) > per_doc_tokens:
            keep_chars = max(per_doc_tokens * _CHARS_PER_TOKEN - len(DOC_TRUNCATED_MARKER),
                             MIN_DOC_TOKENS * _CHARS_PER_TOKEN)
            nd["content"] = content[:keep_chars].rstrip() + DOC_TRUNCATED_MARKER
        out.append(nd)
    return out


def shrink_text(text: str, budget_tokens: int, protect_tail: bool = False) -> str:
    """Trunca `text` al presupuesto de tokens (estimación offline).

    - `protect_tail=False`: conserva el INICIO y corta el final (con TEXT_CUT_MARKER).
    - `protect_tail=True`: conserva sobre todo el FINAL (para el diagnóstico: la
      conclusión/recomendación va al final) recortando el MEDIO — queda 1/3 de cabeza
      + TEXT_CUT_MARKER + 2/3 de cola.

    Un texto que ya cabe en el presupuesto se devuelve intacto.
    """
    text = text or ""
    if estimate_tokens(text) <= budget_tokens:
        return text
    max_chars = max(budget_tokens * _CHARS_PER_TOKEN - len(TEXT_CUT_MARKER) - 2,
                    _CHARS_PER_TOKEN * 8)
    if protect_tail:
        head_chars = max_chars // 3
        tail_chars = max_chars - head_chars
        return (text[:head_chars].rstrip() + "\n" + TEXT_CUT_MARKER + "\n"
                + text[-tail_chars:].lstrip())
    return text[:max_chars].rstrip() + "\n" + TEXT_CUT_MARKER
