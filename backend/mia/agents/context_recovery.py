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

from . import untrusted
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


# ── Peso del SELLADO (lo que se renderiza, no la suma cruda de los contenidos) ──
# Los documentos NUNCA llegan al prompt "pelados": `untrusted.render_documents` antepone
# una cabecera y envuelve cada extracto en su sello `<<<DOC n · archivo · folio>>> …
# <<<FIN DOC n>>>`. Repartir el presupuesto ignorando ese peso hacía que lo RENDERIZADO
# superara siempre el tope, el llamador volviera a recortar y el resultado se quedara en
# la mitad del cupo (medido en la Sala: 35.184 de 70.000 = 50%). Aquí el peso del sellado
# se DESCUENTA antes de repartir, calculándolo con las mismas funciones que lo imprimen
# (no con un número copiado a mano, que se desincronizaría al primer cambio de formato).
_DOCS_HEADER_TOKENS = estimate_tokens(untrusted.DOCUMENTS_HEADER + "\n")

# Tokens que gasta el propio aviso de recorte dentro del contenido conservado.
_DOC_MARKER_TOKENS = estimate_tokens(DOC_TRUNCATED_MARKER)

# Mínimo que ocupa un extracto conservado: el contenido mínimo útil que este módulo ya
# declara (MIN_DOC_TOKENS) MÁS su marcador de recorte. Es la unidad con la que se decide
# CUÁNTOS extractos caben — no un número nuevo.
_DOC_FLOOR_TOKENS = MIN_DOC_TOKENS + _DOC_MARKER_TOKENS


def _as_doc(d) -> dict:
    """Normaliza al shape mínimo: un elemento que no sea dict (vía distinta al RRF) se
    renderiza igual y no revienta el recorte."""
    return d if isinstance(d, dict) else {"content": str(d)}


def _seal_tokens(doc: dict, index: int) -> int:
    """Tokens del SELLO de un bloque (apertura + cierre + sus saltos de línea).

    El rótulo de procedencia (`archivo · folio N`) forma parte de la línea de apertura y
    pesa distinto en cada extracto, así que se mide extracto a extracto. `index` se pasa
    al máximo posible: un número de más ancho nunca subestima el sello.
    """
    head, tail = untrusted.fence_markers("DOC", index=index,
                                         source=untrusted.document_origin(doc))
    # +1 token cubre los 4 saltos de línea del bloque (2 propios + 2 de separación).
    return estimate_tokens(head) + estimate_tokens(tail) + 1


def _priority_order(docs: list[dict]) -> list[int]:
    """Índices de `docs` en ORDEN DE PRIORIDAD para sobrevivir al recorte.

    Por qué existe: los fragmentos que el modelo PIDIÓ expresamente (lectura adaptativa)
    se añaden AL FINAL de la lista. Un recorte que se queda con el principio los tira
    primero — la aportación del modelo era lo primero en caer y la función se anulaba a sí
    misma. Aquí la supervivencia se decide por RELEVANCIA (`score` del RRF, que es
    comparable entre consultas porque es un rango recíproco), con la posición de llegada
    como desempate estable.

    Fail-soft deliberado: si UN solo extracto no trae `score` numérico, no hay señal
    comparable para todos y se conserva el orden de llegada tal cual. Un documento que el
    abogado adjuntó a mano no trae score, y degradarlo por eso sería exactamente el error
    contrario (lo que entrega el abogado es lo más fidedigno que hay).
    """
    try:
        scores = [float(d.get("score")) for d in docs]  # type: ignore[arg-type]
    except (AttributeError, TypeError, ValueError):
        return list(range(len(docs)))
    return sorted(range(len(docs)), key=lambda i: (-scores[i], i))


def _fit_to_budget(items: list[dict], budget_tokens: int) -> list[dict]:
    """Ajusta `items` (ya normalizados) a `budget_tokens` YA RENDERIZADOS.

    Dos pasos, los dos gobernados por el presupuesto:
      1. SELECCIÓN: se conservan extractos mientras la suma de sus mínimos quepa, en orden
         de prioridad. Nada de mitades: si caben todos, quedan todos.
      2. REPARTO max-min del contenido: cada extracto recibe primero su mínimo; el resto
         del cupo se reparte entre los que se quedaron cortos, empezando por los que menos
         necesitan. Así un extracto pequeño no acapara cupo que no usa y los grandes se
         llevan todo lo que sobra — el resultado renderizado se acerca al tope en vez de
         quedarse en la mitad.
    """
    n_total = len(items)
    budget = max(1, budget_tokens)
    avail = max(1, budget - _DOCS_HEADER_TOKENS)
    sizes = [estimate_tokens(str(d.get("content") or "")) for d in items]
    seals = [_seal_tokens(d, n_total) for d in items]

    # 1 · selección POR PRESUPUESTO (nunca 0 extractos: el primero de la prioridad entra
    #     siempre). Se sigue recorriendo tras un extracto que no cabe —los sellos pesan
    #     distinto según el rótulo— porque descartar la cola entera por uno caro
    #     desperdiciaría cupo.
    keep: list[int] = []
    used = 0
    for i in _priority_order(items):
        cost = min(sizes[i], _DOC_FLOOR_TOKENS) + seals[i]
        if keep and used + cost > avail:
            continue
        keep.append(i)
        used += cost
    kept_idx = sorted(keep)  # el ORDEN DE LLEGADA se conserva en la salida (ver abajo)

    # 2 · reparto max-min del contenido bajo el cupo ya descontado de sellos.
    content_budget = max(len(kept_idx), avail - sum(seals[i] for i in kept_idx))
    alloc = {i: min(sizes[i], _DOC_FLOOR_TOKENS) for i in kept_idx}
    rem = max(0, content_budget - sum(alloc.values()))
    hungry = sorted((i for i in kept_idx if sizes[i] > alloc[i]),
                    key=lambda i: sizes[i] - alloc[i])
    left = len(hungry)
    for i in hungry:
        if rem <= 0 or left <= 0:
            break
        extra = min(sizes[i] - alloc[i], rem // left)
        alloc[i] += extra
        rem -= extra
        left -= 1

    out: list[dict] = []
    for i in kept_idx:
        nd = dict(items[i])
        content = str(nd.get("content") or "")
        if sizes[i] > alloc[i]:
            keep_chars = max(alloc[i] * _CHARS_PER_TOKEN - len(DOC_TRUNCATED_MARKER),
                             MIN_DOC_TOKENS * _CHARS_PER_TOKEN)
            nd["content"] = content[:keep_chars].rstrip() + DOC_TRUNCATED_MARKER
        out.append(nd)
    return out


# Pasadas máximas del apriete del presupuesto cuando el material YA cabía (ver abajo).
_MAX_TIGHTEN_PASSES = 6


def shrink_documents(docs: list[dict], budget_tokens: int) -> list[dict]:
    """Reduce los documentos recuperados a un presupuesto de tokens (Riesgo #33).

    El presupuesto es de lo RENDERIZADO (cabecera + sellos + contenido), no de la suma
    cruda de los contenidos: `_fit_to_budget` descuenta el peso del sellado antes de
    repartir, así que lo que sale ocupa una fracción alta del cupo en vez de la mitad.

    Qué se conserva y en qué orden:
      - CUÁNTOS: los que quepan (no "la mitad"). Con presupuesto de sobra no se descarta
        ninguno; lo único que se recorta entonces es el LARGO de los más extensos.
      - CUÁLES: los más relevantes por `score` (`_priority_order`) — así lo que el modelo
        pidió en la lectura adaptativa deja de ser lo primero en caer.
      - EN QUÉ ORDEN SALEN: en el de llegada. Reordenar la salida cambiaría a qué pieza
        apunta cada `[doc n]`, y ese número es el ancla de las citas; la prioridad decide
        quién sobrevive, nunca quién es el [doc 1].

    Apriete del presupuesto: esta función se invoca ANTE UN DESBORDAMIENTO, así que
    devolver el material intacto rara vez sirve de rescate. Si con el presupuesto del nodo
    no hubo NADA que recortar, el desbordamiento venía de otra parte del prompt y se
    aprieta el presupuesto a la mitad hasta que sí recorte (tope `_MAX_TIGHTEN_PASSES`).
    Con material ya mínimo —extractos por debajo del mínimo útil— no se fuerza nada: ahí
    no queda nada que recuperar y machacarlos solo degradaría la evidencia sin liberar
    espacio. En ese caso el prompt se reduce por las otras palancas del nodo (conocimiento
    del despacho, playbooks), no por los documentos.

    No muta los dicts de entrada (devuelve copias). Con `docs` vacío devuelve [].
    """
    if not docs:
        return []
    items = [_as_doc(d) for d in docs]
    budget = max(1, budget_tokens)
    out = _fit_to_budget(items, budget)
    passes = 0
    while out == items and passes < _MAX_TIGHTEN_PASSES and budget > 1:
        budget = max(1, budget // 2)
        out = _fit_to_budget(items, budget)
        passes += 1
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
