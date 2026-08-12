"""
Mia · test_agent_playbooks.py — gate del Bloque C (C1): agentes jurídicos con guías vinculadas.

Ejercita la migración 030 + los vínculos persona→guía en PersonaService, la inyección en el
turno de ASUNTO (graph._prepare_playbooks) y en el modo ASISTENTE (assistant/core), la
entrevista kind='agente' y el gate HITL, contra la DB real, con el LLM y los embeddings
MOCKEADOS (sin red). Molde de execution/test_personas.py + execution/test_playbook_versions.py.

Cubre (spec C1.h):
  1. init_persona_playbooks idempotente; tabla con RLS enable+force.
  2. RLS: el tenant B no ve los vínculos de A (rol mia_app + set_config, force_rollback).
  3. set/get vínculos: orden estable, dedupe, tope 8, id inexistente, uuid malformado (en llano).
  4. API: POST/PUT persona con playbook_ids; la respuesta los incluye; 422 en llano.
  5. turn_context/resolve_for_turn cargan los vínculos; si la query falla → FAIL-OPEN.
  6. _prepare_playbooks: vinculadas activas primero (tope 3) + score; sin persona == baseline;
     archivada vinculada NO se activa.
  7. Asistente: bloque 'Guías que este rol prioriza' con presupuesto; sin vínculos == baseline;
     el bloque va DESPUÉS de la voz.
  8. Entrevista agente: ask→ask→ask→draft, clips, fallback, MIN/MAX, suggested_playbook_ids.
  9. GATE HITL: entrevista de agente completa SIN guardar → 0 filas nuevas.
 10. §G — sin jerga técnica en lo que ve el abogado.

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_agent_playbooks.py
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import psycopg
from dotenv import load_dotenv

# psycopg async no corre sobre ProactorEventLoop (Windows nativo, Modo B).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import init_personas                     # noqa: E402  (migración 023)
import init_playbooks                     # noqa: E402  (migración 005)
import init_playbook_versions             # noqa: E402  (migración 029)
import init_persona_playbooks             # noqa: E402  (migración 030)
from mia import config, embeddings         # noqa: E402
from mia.agent import llm                  # noqa: E402
from mia.db import pool                     # noqa: E402
from mia.agents import graph               # noqa: E402
from mia.agents import personas as pmod    # noqa: E402
from mia.agents.personas import (          # noqa: E402
    Persona, PersonaError, PersonaService,
)
from mia.assistant.core import (           # noqa: E402
    AssistantService, PERSONA_PLAYBOOKS_HEADER, PERSONA_PB_BUDGET_CHARS,
    PERSONA_PB_TRIMMED_NOTE, build_assistant_system, ASSISTANT_INSTRUCTIONS,
)

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── mocks (sin red) ──────────────────────────────────────────────────────────
def _fake_embed(texts):
    return [[0.2] + [0.0] * (config.EMBED_DIM - 1) for _ in texts]


_llm_queue: list[object] = []


def _fake_call_llm(messages, *, task=None, model=None, **kw):
    item = _llm_queue.pop(0) if _llm_queue else {"action": "ask", "question": "¿Algo más?"}
    if item == "RAISE":
        raise RuntimeError("stub: fallo simulado del proveedor LLM")
    content = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5, total_tokens=10))


embeddings.embed_texts = _fake_embed
llm.call_llm = _fake_call_llm

PG = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
          dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""))

FORBIDDEN = ("hitl", "langgraph", "pgvector", "tenant_id", "chunk", "embedding", "playbook",
             "sync engine")


def make_tenants() -> tuple[str, str]:
    with psycopg.connect(autocommit=True, **PG) as c:
        a = c.execute("INSERT INTO tenants(name) VALUES('A test c1') RETURNING id").fetchone()[0]
        b = c.execute("INSERT INTO tenants(name) VALUES('B test c1') RETURNING id").fetchone()[0]
    return str(a), str(b)


def drop_tenants(*ids: str) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        for tid in ids:
            c.execute("DELETE FROM tenants WHERE id = %s", (tid,))


def seed_playbook(tid: str, title: str, summary: str, applies_when: str, content: str,
                  status: str = "active") -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO playbooks (tenant_id, title, summary, applies_when, content, status) "
            "VALUES (%s::uuid, %s, %s, %s, %s, %s) RETURNING id",
            (tid, title, summary, applies_when, content, status)).fetchone()[0])


def seed_persona(tid: str, name: str, summon: list[str] | None = None) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO personas (tenant_id, name, role_prompt, summon_phrases) "
            "VALUES (%s::uuid, %s, %s, %s) RETURNING id",
            (tid, name, f"Actúas como {name}.", summon or [])).fetchone()[0])


def db_counts() -> dict[str, int]:
    out = {}
    with psycopg.connect(autocommit=True, **PG) as c:
        for t in ("personas", "persona_playbooks", "playbooks"):
            out[t] = c.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    return out


# ── OFFLINE: _select_with_persona puro (sin DB) ───────────────────────────────
def offline_checks() -> None:
    print("\n-- offline: prioridad de guías vinculadas (pura) + render del bloque --")
    pa, l1, l2 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    rows = [
        {"id": pa, "title": "caducidad de la acción", "summary": "cómputo", "applies_when": "x"},
        {"id": l1, "title": "protocolo interno", "summary": "orden", "applies_when": "cierre"},
        {"id": l2, "title": "manual redacción", "summary": "estilo", "applies_when": "revisión"},
    ]
    query = "caducidad de la acción en el proceso"

    st_no = {}
    base = graph._select_playbook_ids(rows, query)
    check("offline: sin agente == selección por score de siempre",
          graph._select_with_persona(st_no, rows, query) == base)

    st = {"persona": {"playbook_ids": [l1, l2]}}
    check("offline: vinculadas activas van PRIMERO y se completa por score (tope 3)",
          graph._select_with_persona(st, rows, query) == [l1, l2, pa])

    ghost = str(uuid.uuid4())
    st_ghost = {"persona": {"playbook_ids": [l1, ghost, l2]}}
    check("offline: una vinculada que NO está activa se salta (no rompe el orden)",
          graph._select_with_persona(st_ghost, rows, query) == [l1, l2, pa])

    st_all = {"persona": {"playbook_ids": [l1, l2, pa]}}
    check("offline: si las vinculadas llenan el tope, el score no agrega más",
          graph._select_with_persona(st_all, rows, query) == [l1, l2, pa])

    # Render del bloque del asistente: presupuesto y nota de recorte.
    from mia.assistant.core import _render_persona_playbooks
    big = [(f"Guía {i}", "Z" * 4000) for i in range(6)]
    block = _render_persona_playbooks(big)
    check("offline: el bloque respeta el tope de 16000 chars", 0 < len(block) <= PERSONA_PB_BUDGET_CHARS)
    check("offline: el bloque lleva el encabezado en llano", PERSONA_PLAYBOOKS_HEADER in block)
    check("offline: al agotar el presupuesto marca '(material recortado)'",
          PERSONA_PB_TRIMMED_NOTE in block)
    one = _render_persona_playbooks([("G", "Z" * 9000)])
    check("offline: una guía gigante se recorta (no entra completa)", ("Z" * 4001) not in one)
    check("offline: sin guías el bloque es vacío", _render_persona_playbooks([]) == "")
    # Estrés de FRONTERA (hallazgo capa 2 sesión 41): combinaciones que caen justo al filo
    # del presupuesto — el bloque final, CON la nota de recorte incluida, jamás supera el
    # tope duro. Se barren varios tamaños para cubrir el peor caso del off-by-one.
    frontera_ok = True
    for extra in range(0, 60):
        guides = [(f"G{i}", "Z" * 3900) for i in range(4)] + [("Gfin", "Z" * (3800 + extra)), ("Gmas", "Z" * 4000)]
        b = _render_persona_playbooks(guides)
        if len(b) > PERSONA_PB_BUDGET_CHARS:
            frontera_ok = False
            break
    check("offline: en la frontera exacta el bloque + nota nunca supera el tope duro", frontera_ok)


# ── ASYNC (servicio bajo prueba, pool abierto) ────────────────────────────────
async def async_checks(a: str, b: str, seeded: dict) -> None:
    await pool.open_pool()
    try:
        await _async_checks(a, b, seeded)
    finally:
        await pool.close_pool()


async def _async_checks(a: str, b: str, seeded: dict) -> None:
    print("\n-- async: set/get vínculos, resolve_for_turn, _prepare_playbooks, asistente --")
    huge = "guía estratégica " * 10000
    limited = graph._budget_active_playbooks(huge, 2000)
    check("playbooks activos: presupuesto duro ≤8% de la ventana",
          graph.estimate_tokens(limited)
          <= int(2000 * graph.PLAYBOOK_ACTIVE_BUDGET_FRACTION))
    svc = PersonaService()
    pA = seeded["persona_a"]
    pl1, pl2, pl3 = seeded["pl1"], seeded["pl2"], seeded["pl3"]

    # 3 · set/get vínculos: orden estable + dedupe.
    await svc.set_linked_playbooks(a, pA, [pl1, pl2])
    check("vínculos: get devuelve el orden fijado", await svc.get_linked_playbook_ids(a, pA) == [pl1, pl2])
    await svc.set_linked_playbooks(a, pA, [pl2, pl1])
    check("vínculos: reemplaza y respeta el nuevo orden",
          await svc.get_linked_playbook_ids(a, pA) == [pl2, pl1])
    await svc.set_linked_playbooks(a, pA, [pl1, pl1, pl2])
    check("vínculos: dedupe preservando el orden", await svc.get_linked_playbook_ids(a, pA) == [pl1, pl2])

    # tope 8 → PersonaError en llano.
    tope_err = ""
    try:
        await svc.set_linked_playbooks(a, pA, [str(uuid.uuid4()) for _ in range(9)])
    except PersonaError as e:
        tope_err = str(e)
    check("vínculos: tope de 8 → PersonaError en llano",
          "máximo 8" in tope_err and "playbook" not in tope_err.lower())

    # id inexistente → PersonaError en llano (y no pisa los vínculos previos).
    inx_err = ""
    try:
        await svc.set_linked_playbooks(a, pA, [str(uuid.uuid4())])
    except PersonaError as e:
        inx_err = str(e)
    check("vínculos: id inexistente → PersonaError 'ya no existe' en llano",
          "ya no existe" in inx_err.lower() and "playbook" not in inx_err.lower())
    check("vínculos: tras el error, los vínculos previos quedan intactos",
          await svc.get_linked_playbook_ids(a, pA) == [pl1, pl2])

    # uuid malformado → PersonaError (no excepción cruda).
    mal_err = ""
    try:
        await svc.set_linked_playbooks(a, pA, ["no-es-un-uuid"])
    except PersonaError as e:
        mal_err = str(e)
    except Exception as e:  # noqa: BLE001
        mal_err = f"CRUDA:{e}"
    check("vínculos: uuid malformado → PersonaError (nunca excepción cruda)",
          "ya no existe" in mal_err.lower())

    # 5 · turn_context / resolve_for_turn cargan los vínculos.
    resolved = await svc.resolve_for_turn(a, "cualquier cosa", explicit_id=pA)
    check("resolve_for_turn: por id explícito trae los vínculos",
          resolved is not None and list(resolved.playbook_ids) == [pl1, pl2])
    check("turn_context: incluye playbook_ids", resolved.turn_context().get("playbook_ids") == [pl1, pl2])
    pubvals = " ".join(str(v) for k, v in resolved.to_public().items() if k != "playbook_ids")
    check("to_public: expone playbook_ids", "playbook_ids" in resolved.to_public())

    # FAIL-OPEN: si la carga de vínculos revienta, la persona resuelve igual (sin vínculos).
    original = svc._load_links

    async def _boom(*args, **kw):
        raise RuntimeError("simulado: falla la query de vínculos")

    svc._load_links = _boom  # type: ignore[method-assign]
    try:
        failopen = await svc.resolve_for_turn(a, "cualquier cosa", explicit_id=pA)
    finally:
        svc._load_links = original  # type: ignore[method-assign]
    check("FAIL-OPEN: la persona resuelve aunque la carga de vínculos falle",
          failopen is not None and list(failopen.playbook_ids) == [])

    # 6 · _prepare_playbooks: vinculadas activas primero (tope 3) + score; archivada NO.
    pk_pa = seeded["pk_pa"]          # activo, puntúa con la consulta
    pk_l1, pk_l2 = seeded["pk_l1"], seeded["pk_l2"]   # vinculadas, no puntúan
    pk_arch = seeded["pk_arch"]      # vinculada pero archivada
    q_msg = "Analiza la prescripcion extintiva quinquenal en este asunto."
    state_p = {
        "tenant_id": a,
        "messages": [{"role": "user", "content": q_msg}],
        "persona": {"playbook_ids": [pk_l1, pk_l2, pk_arch]},
    }
    _, _, activated = await graph._prepare_playbooks(state_p, "")
    check("_prepare_playbooks: [vinculada, vinculada, top-score] respetando el tope 3",
          activated == [pk_l1, pk_l2, pk_pa])
    check("_prepare_playbooks: la guía archivada vinculada NO se activa", pk_arch not in activated)

    state_np = {"tenant_id": a, "messages": [{"role": "user", "content": q_msg}]}
    _, _, act_np = await graph._prepare_playbooks(state_np, "")
    check("_prepare_playbooks: sin agente == solo por score (baseline)", act_np == [pk_pa])

    state_all = {
        "tenant_id": a,
        "messages": [{"role": "user", "content": q_msg}],
        "persona": {"playbook_ids": [pk_l1, pk_l2, pk_pa]},
    }
    _, _, act_all = await graph._prepare_playbooks(state_all, "")
    check("_prepare_playbooks: 3 vinculadas activas llenan el tope, sin score extra",
          act_all == [pk_l1, pk_l2, pk_pa])

    # 7 · Asistente: bloque de guías priorizadas, presupuesto, orden vs la voz.
    asvc = AssistantService()
    gbig = seeded["g_block"]   # lista de ids de guías activas con contenido grande
    g_arch = seeded["g_block_arch"]
    persona_block = Persona(
        id=pA, name="Litigante", title="Estratega", role_prompt="Actúas como litigante.",
        tone="firme", focus_areas=("defensa",), model_tier="estandar",
        summon_phrases=("como litigante",), description="d", enabled=True,
        playbook_ids=tuple(gbig + [g_arch]))
    block = await asvc._persona_playbooks_block(a, persona_block)
    check("asistente: el bloque trae el encabezado 'Guías que este rol prioriza'",
          PERSONA_PLAYBOOKS_HEADER in block)
    check("asistente: el bloque respeta el presupuesto duro (≤16000)", len(block) <= PERSONA_PB_BUDGET_CHARS)
    check("asistente: una guía gigante vinculada se recorta (no entra completa)",
          ("Z" * 4001) not in block)
    check("asistente: la guía archivada vinculada NO entra al bloque",
          "GuiaArchivadaC1" not in block)

    persona_novoice = Persona(
        id=pA, name="Litigante", title="", role_prompt="Actúas como litigante.", tone="",
        focus_areas=(), model_tier="estandar", summon_phrases=(), description="", enabled=True,
        playbook_ids=())
    block_none = await asvc._persona_playbooks_block(a, persona_novoice)
    check("asistente: sin vínculos → sin bloque", block_none == "")
    sys_base = build_assistant_system(a, persona_novoice)
    sys_same = build_assistant_system(a, persona_novoice, "")
    check("asistente: sin bloque, el system es idéntico al de antes", sys_base == sys_same)
    check("asistente: sin vínculos el system NO trae el encabezado del bloque",
          PERSONA_PLAYBOOKS_HEADER not in sys_base)

    sys_with = build_assistant_system(a, persona_block, block)
    i_voice = sys_with.find("Rol para este turno")
    i_block = sys_with.find(PERSONA_PLAYBOOKS_HEADER)
    i_instr = sys_with.find(ASSISTANT_INSTRUCTIONS[:40])
    check("asistente: el bloque va DESPUÉS de la voz y ANTES de la instrucción del asistente",
          -1 < i_voice < i_block < i_instr)

    seeded["failopen_note"] = mal_err  # para el anti-jerga


# ── SYNC: RLS de persona_playbooks (rol mia_app) ──────────────────────────────
def rls_checks(a: str, b: str, seeded: dict) -> None:
    print("\n-- sync: RLS de persona_playbooks (mia_app) --")
    # 1 · tabla con RLS enable/force (idempotente: aplicar de nuevo no rompe).
    init_persona_playbooks.apply()
    with psycopg.connect(autocommit=True, **PG) as c:
        rls = c.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname='persona_playbooks'"
        ).fetchone()
    check("migración 030: persona_playbooks con RLS enable+force", rls == (True, True))

    APP_PW = os.getenv("PG_APP_PASSWORD", "")
    PG_APP = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
                  dbname=os.getenv("PG_DB", "mia"), user="mia_app", password=APP_PW)
    # A ya tiene vínculos (async los dejó en [pl1, pl2]). B no debe ver ninguna fila de A.
    with psycopg.connect(**PG_APP) as appconn:
        with appconn.transaction(force_rollback=True):
            appconn.execute("SELECT set_config('app.tenant_id', %s, true)", (str(b),))
            n_cross = appconn.execute(
                "SELECT count(*) FROM persona_playbooks WHERE persona_id = %s::uuid",
                (seeded["persona_a"],)).fetchone()[0]
    check("RLS: el tenant B ve 0 vínculos del agente de A", n_cross == 0)
    with psycopg.connect(**PG_APP) as appconn:
        with appconn.transaction(force_rollback=True):
            appconn.execute("SELECT set_config('app.tenant_id', %s, true)", (str(a),))
            n_own = appconn.execute(
                "SELECT count(*) FROM persona_playbooks WHERE persona_id = %s::uuid",
                (seeded["persona_a"],)).fetchone()[0]
    check("RLS: el tenant A sí ve sus propios vínculos", n_own == 2)


# ── API (TestClient): POST/PUT persona + entrevista agente + gate HITL ─────────
def api_checks(a: str, b: str, seeded: dict) -> None:
    print("\n-- api: persona con guías, entrevista de agente, gate HITL --")
    import jwt
    from fastapi.testclient import TestClient
    from mia.api.main import app

    tok_a = jwt.encode({"tenant_id": a}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    auth_a = {"Authorization": f"Bearer {tok_a}"}
    visible: list[str] = []          # SOLO texto humano (preguntas, valores de borrador, detail)
    pl1, pl2 = seeded["pl1"], seeded["pl2"]
    pa_api = seeded["pa_api"]         # guía activa que casa con el agente propuesto
    arch_api = seeded["arch_api"]     # guía archivada — nunca debe sugerirse

    with TestClient(app) as client:
        # 4 · POST persona con playbook_ids → respuesta los incluye.
        r = client.post("/api/personas", headers=auth_a, json={
            "name": "AgenteC1-post", "role_prompt": "Actúas como especialista.",
            "playbook_ids": [pl1, pl2]})
        ok_post = r.status_code == 200 and r.json().get("playbook_ids") == [pl1, pl2]
        check("API POST persona con guías → 200 y la respuesta incluye playbook_ids", ok_post)
        pid_post = r.json().get("id")

        # PUT reemplaza los vínculos.
        r = client.put(f"/api/personas/{pid_post}", headers=auth_a, json={
            "name": "AgenteC1-post", "role_prompt": "Actúas como especialista.",
            "playbook_ids": [pl2]})
        check("API PUT persona → reemplaza los vínculos (queda [pl2])",
              r.status_code == 200 and r.json().get("playbook_ids") == [pl2])

        # 422 en llano: tope 8.
        r = client.post("/api/personas", headers=auth_a, json={
            "name": "AgenteC1-tope", "role_prompt": "x",
            "playbook_ids": [str(uuid.uuid4()) for _ in range(9)]})
        check("API POST con >8 guías → 422 en llano",
              r.status_code == 422 and "máximo 8" in r.json().get("detail", ""))
        visible.append(r.json().get("detail", ""))

        # 422 en llano: guía inexistente.
        r = client.post("/api/personas", headers=auth_a, json={
            "name": "AgenteC1-inx", "role_prompt": "x", "playbook_ids": [str(uuid.uuid4())]})
        check("API POST con guía inexistente → 422 en llano",
              r.status_code == 422 and "ya no existe" in r.json().get("detail", "").lower())
        visible.append(r.json().get("detail", ""))

        # 8 · Entrevista de agente: ask→ask→ask→draft con clips y suggested_playbook_ids.
        _llm_queue.clear()
        transcript: list[dict] = []
        for i in range(3):
            _llm_queue.append({"action": "ask", "question": f"Pregunta de diseño {i + 1}"})
            r = client.post("/api/guides/interview", headers=auth_a,
                            json={"kind": "agente", "messages": transcript})
            body = r.json()
            check(f"entrevista agente turno {i + 1}: sigue preguntando (done=False)",
                  r.status_code == 200 and body.get("done") is False and bool(body.get("question")))
            visible.append(str(body.get("question", "")))
            transcript.append({"role": "assistant", "content": body["question"]})
            transcript.append({"role": "user", "content": f"Respuesta {i + 1} del abogado."})

        # 4ª ronda (3 preguntas hechas, dentro de 3-6): el LLM propone el borrador del agente,
        # con campos deliberadamente largos para probar los recortes server-side.
        _llm_queue.append({
            "action": "draft",
            "name": "N" * 100, "title": "T" * 200,
            "role_prompt": "caducidad de la reparación directa. " + "R" * 6000,
            "tone": "O" * 200,
            "focus_areas": [f"area-{i}" for i in range(10)],
            "summon_phrases": [f"frase {i}" for i in range(8)],
            "description": "D" * 3000,
            "explanation": "Ya hay material suficiente para diseñar el agente.",
        })
        r = client.post("/api/guides/interview", headers=auth_a,
                        json={"kind": "agente", "messages": transcript})
        body = r.json()
        check("entrevista agente: a las 3 preguntas el LLM propone el borrador (done=True)",
              r.status_code == 200 and body.get("done") is True)
        draft = body.get("draft", {})
        check("entrevista agente: el borrador tiene el shape de un agente",
              set(draft.keys()) == {"name", "title", "role_prompt", "tone", "focus_areas",
                                    "summon_phrases", "description"})
        check("entrevista agente: recortes server-side (name≤64, title≤120, tone≤160, role≤6000, desc≤2000)",
              len(draft.get("name", "")) == 64 and len(draft.get("title", "")) == 120
              and len(draft.get("tone", "")) == 160 and len(draft.get("role_prompt", "")) == 6000
              and len(draft.get("description", "")) == 2000)
        check("entrevista agente: focus_areas≤8 y summon_phrases≤6",
              len(draft.get("focus_areas", [])) == 8 and len(draft.get("summon_phrases", [])) == 6)
        check("entrevista agente: suggested_playbook_ids presentes (lista)",
              isinstance(body.get("suggested_playbook_ids"), list))
        sug = body.get("suggested_playbook_ids", [])
        check("entrevista agente: sugiere la guía activa que casa con el agente", pa_api in sug)
        check("entrevista agente: NUNCA sugiere una guía archivada", arch_api not in sug)
        visible.append(str(draft.get("name", "")))
        visible.append(str(draft.get("role_prompt", ""))[:80])

        # fallback ante JSON inválido (dentro de 3-6) → pregunta de respaldo, jamás 500.
        _llm_queue.clear()
        _llm_queue.append("esto no es json {{{")
        cuatro = []
        for i in range(4):
            cuatro.append({"role": "assistant", "content": f"P{i + 1}"})
            cuatro.append({"role": "user", "content": f"R{i + 1}"})
        r = client.post("/api/guides/interview", headers=auth_a,
                        json={"kind": "agente", "messages": cuatro})
        check("entrevista agente: JSON inválido → 200 con pregunta de respaldo (nunca 500)",
              r.status_code == 200 and r.json().get("done") is False and bool(r.json().get("question")))
        visible.append(str(r.json().get("question", "")))

        # <3 preguntas: aunque el LLM proponga borrador, se fuerza una pregunta.
        _llm_queue.clear()
        _llm_queue.append({"action": "draft", "name": "X", "role_prompt": "y"})
        r = client.post("/api/guides/interview", headers=auth_a,
                        json={"kind": "agente", "messages": []})
        check("entrevista agente: <3 preguntas fuerza una pregunta (ignora el borrador del LLM)",
              r.status_code == 200 and r.json().get("done") is False)
        visible.append(str(r.json().get("question", "")))

        # ≥6 preguntas: se fuerza el borrador de respaldo determinista (shape de agente).
        _llm_queue.clear()
        _llm_queue.append({"action": "ask", "question": "¿Sigo?"})
        seis = []
        for i in range(6):
            seis.append({"role": "assistant", "content": f"P{i + 1}"})
            seis.append({"role": "user", "content": f"Respuesta agente {i + 1}"})
        r = client.post("/api/guides/interview", headers=auth_a,
                        json={"kind": "agente", "messages": seis})
        body = r.json()
        check("entrevista agente: a las 6 preguntas se fuerza el borrador (shape de agente)",
              r.status_code == 200 and body.get("done") is True
              and set(body.get("draft", {}).keys()) == {"name", "title", "role_prompt", "tone",
                                                          "focus_areas", "summon_phrases", "description"})
        visible.append(str(body.get("draft", {}).get("role_prompt", "")))

        # 9 · GATE HITL: una entrevista de agente completa SIN guardar → 0 filas nuevas.
        antes = db_counts()
        _llm_queue.clear()
        gate_tr: list[dict] = []
        for i in range(3):
            _llm_queue.append({"action": "ask", "question": f"Pregunta gate {i + 1}"})
        _llm_queue.append({
            "action": "draft", "name": "Agente gate", "title": "t", "role_prompt": "rol",
            "tone": "", "focus_areas": [], "summon_phrases": [], "description": "",
            "explanation": "listo"})
        for _ in range(4):
            r = client.post("/api/guides/interview", headers=auth_a,
                            json={"kind": "agente", "messages": gate_tr})
            body = r.json()
            if body.get("done"):
                break
            gate_tr.append({"role": "assistant", "content": body["question"]})
            gate_tr.append({"role": "user", "content": "Respuesta del gate."})
        despues = db_counts()
        check(f"GATE HITL: entrevista de agente sin guardar → 0 filas nuevas "
              f"(antes={antes}, despues={despues})", antes == despues)

    # 10 · §G — sin jerga técnica en el texto humano acumulado.
    blob = " ".join(visible).lower()
    leaked = [w for w in FORBIDDEN if w in blob]
    check(f"§G: textos visibles sin jerga técnica (fugas: {leaked or 'ninguna'})", not leaked)


def seed_data(a: str, b: str, seeded: dict) -> None:
    """Siembra playbooks y una persona por tenant (sync superusuario). Guarda ids en `seeded`."""
    # Persona de A (para vínculos/RLS/resolve).
    seeded["persona_a"] = seed_persona(a, "AgenteVinculos", summon=["como agente"])
    seed_persona(b, "AgenteB")   # B tiene la suya (no debe cruzar)

    # Guías simples para los checks de set/get (no necesitan puntuar).
    seeded["pl1"] = seed_playbook(a, "Guia interna archivo", "orden del expediente", "cierre", "c1")
    seeded["pl2"] = seed_playbook(a, "Manual de redaccion", "estilo del despacho", "revisión", "c2")
    seeded["pl3"] = seed_playbook(a, "Protocolo de citas", "verificación", "control", "c3")

    # Guías para _prepare_playbooks: PA puntúa con la consulta (tokens ÚNICOS, para que NINGUNA
    # otra guía sembrada casé con la consulta); L1/L2 no; ARCH archivada.
    seeded["pk_pa"] = seed_playbook(
        a, "Prescripcion extintiva quinquenal singular", "computo del termino prescriptivo",
        "prescripcion extintiva quinquenal", "cuerpo PA")
    seeded["pk_l1"] = seed_playbook(a, "Nota de archivo fisico", "orden", "cierre administrativo", "cuerpo L1")
    seeded["pk_l2"] = seed_playbook(a, "Formato de memorial", "plantilla", "presentación", "cuerpo L2")
    seeded["pk_arch"] = seed_playbook(a, "Guia vieja archivada prep", "obsoleta", "nunca", "cuerpo ARCH",
                                      status="archived")

    # Guías con contenido grande para el bloque del asistente (6 activas + 1 archivada).
    seeded["g_block"] = [
        seed_playbook(a, f"Material de referencia {i}", "resumen", "cuando aplique", "Z" * 4000)
        for i in range(6)
    ]
    seeded["g_block_arch"] = seed_playbook(
        a, "GuiaArchivadaC1", "resumen", "cuando aplique", "Z" * 4000, status="archived")

    # Guías para la sugerencia de la entrevista de agente: PA_API casa; ARCH_API nunca.
    seeded["pa_api"] = seed_playbook(
        a, "Caducidad reparacion directa accion termino computo proceso",
        "cómputo de la caducidad", "reparación directa", "cuerpo PA_API")
    seeded["arch_api"] = seed_playbook(
        a, "Caducidad reparacion directa ARCHIVADA", "cómputo", "reparación directa",
        "cuerpo ARCH_API", status="archived")


def main() -> int:
    print("== Bloque C · C1 · agentes jurídicos con guías vinculadas ==")
    if not os.getenv("PG_PASSWORD") or not config.JWT_SECRET:
        print("  [FAIL] PG_PASSWORD o JWT_SECRET vacío en .env")
        return 1

    init_personas.apply()             # 023
    init_playbooks.apply()            # 005
    init_playbook_versions.apply()    # 029 (lo importa test_guide_interview)
    init_persona_playbooks.apply()    # 030

    offline_checks()

    a, b = make_tenants()
    seeded: dict = {}
    try:
        seed_data(a, b, seeded)
        asyncio.run(async_checks(a, b, seeded))
        rls_checks(a, b, seeded)
        api_checks(a, b, seeded)
    finally:
        drop_tenants(a, b)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Bloque C · C1 OK — agentes con guías vinculadas verificados.")
        return 0
    print("Bloque C · C1 FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
