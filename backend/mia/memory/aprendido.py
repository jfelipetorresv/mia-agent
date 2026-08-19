"""Mia · memory.aprendido — la sección «## aprendido» del perfil se llena sola.

LA IDEA (paso 7 de docs/diseno-soul-onboarding.md · «más rico, no más largo»)
    La entrevista de onboarding NO se alarga nunca. La riqueza del perfil crece con el
    USO: de cada trabajo que el abogado da por bueno, Mia infiere 0..N aprendizajes de
    METODOLOGÍA del despacho (cómo estructura sus escritos, qué fuentes cita, su estilo,
    sus convenciones de entrega, las materias recurrentes) y los deposita en la sección
    `## aprendido` del SOUL.md. Cada línea queda marcada `[inferido]`, FECHADA y con su
    FUENTE (el tipo de trabajo del que salió — nunca datos del caso: sin radicados, sin
    partes, sin cifras). El abogado puede corregir o borrar cualquiera desde «Mi despacho».

CÓMO SE ESCRIBE (y por qué NO por soul_manager)
    El escritor real del perfil es `SoulInterview.update_soul(tenant, updates)`: fusiona
    con las respuestas previas y RECONSTRUYE el SOUL.md de forma determinista. `## aprendido`
    es una SECCIÓN del perfil renderizado (`build_soul` ya la emite), así que la vía correcta
    es `update_soul({"aprendido": lista_fusionada})`. `memory.soul_manager` es OTRO
    mecanismo (reglas aprobadas por HITL que aterrizan en «Preferencias aprendidas»); no se
    toca ni se usa aquí.

FAIL-SOFT ABSOLUTO
    Esta pieza cuelga de la APROBACIÓN de un borrador. Ningún fallo suyo —el modelo que
    revienta, un JSON que no se entiende, el disco que no responde— puede romper ni
    retrasar esa aprobación. Todo error se traga y se registra; el turno del abogado ya
    quedó cerrado antes de que esto corra, en segundo plano.

INFERENCIA BARATA
    Usa `call_llm(task="soul")` — una tarea AUXILIAR (barata) de las que ya existen
    (`agent/llm.py::_AUX_TASKS`). Salida ESTRICTA: un arreglo JSON de frases cortas. Si el
    modelo no devuelve ese formato exacto, se descarta en silencio (no se inventa nada).

AGNÓSTICO DE JURISDICCIÓN (regla dura): este archivo es código común. Ni una sigla, ley,
corporación o vocabulario jurídico de país concreto — solo términos genéricos de oficio.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Optional

from .. import config
from ..agent.llm import call_llm

logger = logging.getLogger("mia.memory.aprendido")

# ── Topes y forma ────────────────────────────────────────────────────────────
# Tope de entradas de la sección. Al llegar aquí NO se borra ni se trunca nada: se
# DEJA DE AÑADIR y se registra (mismo espíritu que el tope de soul_manager, que RECHAZA
# en vez de recortar la identidad por su cuenta). La sección la lee el prompt en cada
# turno, así que no puede crecer sin fin.
APRENDIDO_MAX = 40
# Cuántos aprendizajes puede aportar UNA sola aprobación (un trabajo no reescribe el
# perfil entero de golpe).
MAX_PER_INFERENCE = 5
# Una línea = un hecho. Nada de párrafos ni de volcados del caso: si el modelo se pasa
# de largo, se descarta (probable fuga de contenido en vez de un patrón de método).
MAX_INSIGHT_CHARS = 240
# Cuánto texto del trabajo se le muestra al modelo (recorte defensivo: ni prompts
# gigantes ni costo desbocado en una tarea auxiliar).
MAX_WORK_CHARS = 8000

# Marca obligatoria de toda línea que Mia infiere (la distingue de lo que el abogado
# escribió a mano). Constante: la usan el render, el dedup y el gate.
INFERIDO_MARK = "[inferido]"

# Etiquetas de FUENTE por tipo de trabajo (genéricas, sin datos del caso). El llamador
# elige cuál según de dónde salió el aprendizaje.
SOURCE_APROBADO = "un borrador que aprobaste"
SOURCE_CORREGIDO = "una corrección tuya sobre un borrador"


class RetryableLearningError(RuntimeError):
    """Fallo técnico o salida inválida: el worker durable debe reintentar."""


# ── El modelo: infiere SOLO metodología, en JSON estricto ────────────────────
_SYS = (
    "Eres el archivista silencioso de un despacho de abogados. A partir de UN trabajo que "
    "el abogado acaba de dar por bueno, infieres SOLO la METODOLOGÍA del despacho: cómo "
    "estructura sus escritos, qué tipo de fuentes cita, su estilo y tono, sus convenciones "
    "de entrega, y las materias en las que trabaja de forma recurrente.\n"
    "REGLAS ESTRICTAS:\n"
    "- Respondes EXCLUSIVAMENTE con un arreglo JSON de cadenas cortas. Nada de texto fuera "
    "del arreglo, ni explicaciones, ni Markdown.\n"
    "- Cada cadena es UN patrón general de método, en una sola frase, reutilizable en otros "
    "asuntos. Sin datos del caso: nada de nombres de partes, identificadores, expedientes, "
    "cifras, fechas ni hechos concretos. La frontera es dura: la tesis de método viaja; el "
    "caso, jamás.\n"
    "- Cada frase empieza con su vector de cosecha: 'Funciona:' (lo que el abogado dio por "
    "bueno y conviene repetir), 'Evitar:' (lo que corrigió o descartó — di qué y qué lo "
    "reemplazó) o 'Lección:' (un aprendizaje con su regla de aplicación futura). Cuando el "
    "trabajo venga de una CORRECCIÓN del abogado, prefiere 'Evitar:' y 'Lección:' — la "
    "corrección es la semilla más valiosa — pero SOLO si el patrón se repetirá en otros "
    "asuntos: una preferencia de un solo caso no se cosecha.\n"
    "- Si no ves un patrón claro y reutilizable, respondes con un arreglo vacío: []. Es "
    "mejor no aprender nada que inventar una preferencia que no existe.\n"
    "- Como máximo cinco elementos."
)


def _user_prompt(work_text: str) -> str:
    return (
        "Este es un trabajo que el abogado acaba de aprobar. Infiere la metodología de su "
        "despacho según las reglas dadas y devuelve el arreglo JSON.\n\n"
        "--- TRABAJO ---\n" + work_text[:MAX_WORK_CHARS]
    )


def _content_of(resp) -> Optional[str]:
    """Extrae el texto de la respuesta OpenAI-compatible; None si no viene bien formada."""
    try:
        content = resp.choices[0].message.content
    except (AttributeError, IndexError, TypeError):
        return None
    return content if isinstance(content, str) else None


def _strip_code_fence(s: str) -> str:
    """Tolera que el modelo envuelva el JSON en ```...``` pese a que se le pidió no hacerlo."""
    s = s.strip()
    if s.startswith("```"):
        # quita la primera línea (```/```json) y la valla de cierre
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s.strip())
    return s.strip()


def _parse_insights_checked(raw: Optional[str]) -> tuple[list[str], bool]:
    """Devuelve (insights, salida_válida); ``[]`` válido significa "sin novedades"."""
    if not isinstance(raw, str):
        return [], False
    try:
        data = json.loads(_strip_code_fence(raw))
    except (ValueError, TypeError):
        return [], False
    if not isinstance(data, list):
        return [], False
    # Una frase fuera del techo contradice el contrato y puede ser una fuga de caso.
    valid = all(isinstance(item, str) for item in data)
    if any(isinstance(item, str)
           and len(re.sub(r"\s+", " ", item).strip()) > MAX_INSIGHT_CHARS
           for item in data):
        valid = False
    out: list[str] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, str):
            continue
        v = re.sub(r"\s+", " ", item).strip()
        if not v or len(v) > MAX_INSIGHT_CHARS:
            continue
        key = _dedup_key(v)
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
        if len(out) >= MAX_PER_INFERENCE:
            break
    return out, valid


def _parse_insights(raw: Optional[str]) -> list[str]:
    """Convierte la respuesta cruda del modelo en una lista de frases de método validadas.

    ESTRICTO: si no es un arreglo JSON de cadenas, se devuelve []. Filtra vacíos, recorta
    espacios, descarta lo demasiado largo (probable volcado del caso), dedup dentro del
    lote y tope de MAX_PER_INFERENCE. Nunca lanza."""
    return _parse_insights_checked(raw)[0]


def infer_learnings(work_text: str, *, strict: bool = False) -> list[str]:
    """Pide al modelo 0..N frases de METODOLOGÍA a partir del texto del trabajo aprobado.

    SÍNCRONA (call_llm lo es): el llamador la saca a un hilo. Devuelve las frases YA
    validadas (sin la envoltura [inferido]/fecha/fuente, que añade `build_line`). FAIL-SOFT:
    cualquier fallo del modelo o del parseo devuelve [] — jamás lanza."""
    text = (work_text or "").strip()
    if not text:
        return []
    try:
        resp = call_llm(
            [{"role": "system", "content": _SYS},
             {"role": "user", "content": _user_prompt(text)}],
            task="soul", temperature=0, max_tokens=400,
        )
    except Exception as exc:  # noqa: BLE001 — solo el worker durable pide propagación
        logger.exception("aprendido: la inferencia del modelo falló (fail-soft)")
        if strict:
            raise RetryableLearningError("Falló la inferencia de aprendizaje.") from exc
        return []
    insights, valid = _parse_insights_checked(_content_of(resp))
    if strict and not valid:
        raise RetryableLearningError("El modelo devolvió un aprendizaje con formato inválido.")
    return insights


# ── Construcción y dedup de las líneas de la sección ─────────────────────────

def build_line(insight: str, *, source: str, today: Optional[date] = None) -> str:
    """Envuelve una frase de método en la línea canónica de la sección: marca [inferido],
    fecha absoluta y fuente por tipo de trabajo. La fecha y la fuente las pone el CÓDIGO
    (no el modelo), así que cada línea nace fechada y con procedencia por construcción."""
    d = (today or date.today()).strftime("%Y-%m-%d")
    return f"{INFERIDO_MARK} {d} · {insight.strip()} · fuente: {source}"


# Prefijo `[inferido] YYYY-MM-DD · ` y sufijo ` · fuente: …` para extraer el NÚCLEO de una
# línea (la frase de método) y deduplicar por él: el mismo aprendizaje re-inferido otro día
# no debe duplicarse por traer otra fecha.
_PREFIX_RE = re.compile(r"^\s*\[inferido\]\s*\d{4}-\d{2}-\d{2}\s*·\s*", re.IGNORECASE)
_SOURCE_RE = re.compile(r"\s*·\s*fuente\s*:.*$", re.IGNORECASE | re.DOTALL)


def _core(line: str) -> str:
    """La frase de método sin la envoltura [inferido]/fecha/fuente. Una línea que el
    abogado escribió a mano (sin ese formato) vuelve casi intacta — y así también se
    deduplica contra lo que Mia infiera con las mismas palabras."""
    s = _PREFIX_RE.sub("", line or "")
    s = _SOURCE_RE.sub("", s)
    return s


_VECTOR_RE = re.compile(r"^\s*(funciona|evitar|lecci[oó]n)\s*:\s*", re.IGNORECASE)


def _dedup_key(line: str) -> str:
    """Clave de dedup: núcleo normalizado — espacios colapsados, minúsculas y sin puntuación
    de borde (un punto final no vuelve distinto a un aprendizaje). El vector de cosecha
    ('Funciona:'/'Evitar:'/'Lección:') se quita ANTES: el mismo patrón bajo dos vectores, o
    una línea manual del abogado sin prefijo, siguen deduplicando. Cubre el dedup exacto y el
    normalizado; no intenta similitud semántica (fuera de alcance por decisión)."""
    core = _VECTOR_RE.sub("", _core(line))
    core = re.sub(r"\s+", " ", core).strip().lower()
    return core.strip(" .,;:!?·—-")


def merge_aprendido(existing: list[str], new_lines: list[str]) -> tuple[list[str], int, int]:
    """Fusiona líneas nuevas sobre las existentes. Devuelve (fusionadas, añadidas, no_cupieron).

    INVARIANTES:
      · NUNCA borra ni reordena nada de `existing` — una línea que el abogado corrigió a
        mano sobrevive intacta a cada inferencia futura (solo se APENDA).
      · Dedup por núcleo normalizado contra lo existente y dentro del lote nuevo.
      · Al alcanzar APRENDIDO_MAX se DEJA DE AÑADIR (no se trunca ni se borra); lo que no
        cupo se cuenta y se reporta al llamador para que lo registre."""
    kept: list[str] = [str(x) for x in (existing or []) if str(x).strip()]
    keys: set[str] = {_dedup_key(x) for x in kept}
    added = 0
    dropped = 0
    for line in new_lines:
        if not str(line).strip():
            continue
        key = _dedup_key(line)
        if key in keys:
            continue                      # ya está (exacto o re-inferido): no duplicar
        if len(kept) >= APRENDIDO_MAX:
            dropped += 1                  # tope: no se añade (y NO se borra nada existente)
            continue
        kept.append(line)
        keys.add(key)
        added += 1
    return kept, added, dropped


def _load_existing_aprendido(tenant_id: str) -> list[str]:
    """La sección `## aprendido` tal como está hoy en las respuestas del despacho (incluye
    lo que Mia infirió antes Y lo que el abogado editó a mano). Fuente para el merge."""
    from ..onboarding.soul_interview import load_responses
    val = load_responses(tenant_id).get("aprendido")
    if isinstance(val, list):
        return [str(x) for x in val if str(x).strip()]
    if isinstance(val, str) and val.strip():
        return [val.strip()]
    return []


def _learning_manifest_path(tenant_id: str, idempotency_key: str) -> Path:
    """Ruta opaca y contenida; ni tenant ni clave se usan como componentes crudos."""
    tenant_key = hashlib.sha256(str(tenant_id).encode("utf-8")).hexdigest()[:32]
    operation_key = hashlib.sha256(str(idempotency_key).encode("utf-8")).hexdigest()
    root = Path(config.MIA_HOME) / "learning-jobs" / tenant_key
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{operation_key}.json"


def _write_manifest(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# ── El enganche: se llama al APROBAR (o corregir) un borrador ─────────────────

async def learn_from_approved_draft(
    tenant_id: str,
    draft: Optional[str],
    *,
    source: str = SOURCE_APROBADO,
    interview=None,
    today: Optional[date] = None,
    strict: bool = False,
    idempotency_key: str | None = None,
) -> dict:
    """Infiere metodología del borrador aprobado y la deposita en `## aprendido` vía
    `update_soul`. Pensada para correr EN SEGUNDO PLANO, jamás en el camino de la respuesta.

    Por defecto conserva el contrato fail-soft del camino interactivo. El worker durable
    usa ``strict=True`` para que un fallo técnico se reintente y ``idempotency_key`` para
    reanudar exactamente las mismas líneas tras una caída. Un arreglo válido ``[]`` sí es
    éxito: significa que no había una regla reutilizable que aprender."""
    try:
        text = (draft or "").strip()
        if not text:
            return {"added": 0, "dropped": 0}

        manifest_path = (_learning_manifest_path(tenant_id, idempotency_key)
                         if idempotency_key else None)
        manifest: dict = {}
        if manifest_path and manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("status") == "completed":
                return dict(manifest.get("result") or {"added": 0, "dropped": 0})
        lines = [str(x) for x in (manifest.get("lines") or []) if str(x).strip()]
        if not lines and not manifest.get("inference_completed"):
            insights = await asyncio.to_thread(infer_learnings, text, strict=strict)
            lines = [build_line(i, source=source, today=today) for i in insights]
            if manifest_path:
                manifest.update(status="pending", inference_completed=True, lines=lines)
                _write_manifest(manifest_path, manifest)
        if not lines:
            result = {"added": 0, "dropped": 0}
            if manifest_path:
                manifest.update(status="completed", result=result)
                _write_manifest(manifest_path, manifest)
            return result

        existing = _load_existing_aprendido(tenant_id)
        merged, added, dropped = merge_aprendido(existing, lines)
        result = dict(manifest.get("result") or {"added": added, "dropped": dropped})
        if manifest_path and "result" not in manifest:
            # Se persiste el plan ANTES de escribir el SOUL. Si hay caída justo
            # después del update, la reentrega conserva el mismo resultado y líneas.
            manifest.update(status="pending", result=result)
            _write_manifest(manifest_path, manifest)

        if dropped:
            logger.info(
                "aprendido: la sección del despacho %s llegó al tope (%d entradas); %d "
                "aprendizaje(s) nuevo(s) no se añadieron (no se borró ni truncó nada)",
                tenant_id, APRENDIDO_MAX, dropped,
            )
        if added == 0:
            if manifest_path:
                manifest.update(status="completed", result=result)
                _write_manifest(manifest_path, manifest)
            return result

        if interview is None:
            from ..onboarding.soul_interview import SoulInterview
            interview = SoulInterview()
        await interview.update_soul(tenant_id, {"aprendido": merged})
        logger.info("aprendido: %d aprendizaje(s) añadido(s) al perfil del despacho %s",
                    added, tenant_id)
        if manifest_path:
            manifest.update(status="completed", result=result)
            _write_manifest(manifest_path, manifest)
        return result
    except Exception:  # noqa: BLE001 — el camino interactivo sigue siendo fail-soft
        logger.exception("aprendido: fallo al aprender del borrador aprobado (fail-soft, "
                         "despacho=%s)", tenant_id)
        if strict:
            raise
        return {"added": 0, "dropped": 0}
