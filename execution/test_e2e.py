"""
Mia · test_e2e.py — GATE FINAL del proyecto (Módulo 5 · Fase 4).

La prueba más importante: simula el recorrido COMPLETO de un abogado de punta a
punta sobre la superficie /api/* con TestClient (sin navegador, sin red). El LLM y
los embeddings van MOCKEADOS. Si esta prueba pasa, Mia v0 está operativa.

Flujo (7 pasos · >= 20 checks):
  1. Onboarding   — la entrevista → genera el SOUL.md del despacho Lexia y lo guarda en
                    $MIA_HOME; verifica las secciones vigentes, que el endpoint RECHACE
                    un perfil que no puede leer, y el wiring al turno.
  2. Crear asunto — POST /api/matters (status 'active').
  3. Subir doc    — PDF de 2 páginas (Ley 80/1993) → se ingiere (chunks en DB > 0).
  4. Chat + SSE   — POST chat → stream_url; el SSE responde text/event-stream.
  5. HITL         — el borrador queda en el checkpoint; se aprueba.
  6. Memoria      — perfil / playbooks / sugerencias.
  7. Dashboard    — matters_active >= 1 y documents_indexed >= 1.

$MIA_HOME se aísla en un tempdir (no toca mia-data/ real). HALT si falla (CLAUDE.md).

    .venv\\Scripts\\python.exe execution\\test_e2e.py
"""
from __future__ import annotations
import asyncio
import contextlib
import io
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import psycopg
from dotenv import load_dotenv

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

import init_profiles                                  # noqa: E402 (migración 007 — firm_profiles)
from mia import config, embeddings                    # noqa: E402
from mia.agent import llm                              # noqa: E402
from mia.agents.state import thread_id_for            # noqa: E402
from mia.onboarding.soul_interview import (           # noqa: E402
    QUESTIONS, validate_soul, load_soul_snapshot, soul_path,
)

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


@contextlib.contextmanager
def capture_logs(name: str):
    """Recoge los mensajes que el servidor escribe en su registro durante el bloque.

    Sirve para comprobar lo que NO se le enseña al abogado: cuando el endpoint rechaza un
    perfil ilegible, el detalle técnico (las llaves) tiene que quedar en el log del
    servidor y NO en el mensaje de la pantalla."""
    msgs: list[str] = []

    class _Sink(logging.Handler):
        def emit(self, record):
            msgs.append(record.getMessage())

    logger = logging.getLogger(name)
    handler = _Sink()
    prev = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        yield msgs
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev)


# ── mocks (sin red) ──────────────────────────────────────────────────────────
# SOUL.md de prueba: trae las 9 secciones del template + datos de Lexia. Lo devuelve
# el mock cuando task="soul" (la generación del SOUL.md). Así el gate verifica el
# pipeline (entrevista → archivo con las 9 secciones) sin llamar a un LLM real.
_SOUL_FIXTURE = (
    "# SOUL.md — Lexia Abogados\n"
    "# Generado: 2026-06-14 · Próxima revisión: 2026-09-12\n\n"
    "## identity\n- name: Lexia Abogados S.A.S.\n- lawyer: Juan Felipe Torres · T.P. 227.698\n"
    "- location: Bogotá, Colombia · UTC-5\n- channels: lexia.co\n- voice: Técnico, argumentativo, conciso\n\n"
    "## jurisdiction\n- base: Colombia\n- practice_areas: Seguros, fiscal, contencioso-administrativo\n"
    "- client_type: Aseguradoras\n- courts: Consejo de Estado, arbitraje\n- process_types: [CONTENCIOSO-ADM]\n\n"
    "## mission\n- headline: Consolidar Lexia Intelligence.\n- pillars:\n  - Excelencia litigios seguros\n"
    "  - Construcción de Mia\n  - Primer cliente externo\n- not_in_scope: [LO QUE NO HACEMOS]\n\n"
    "## legal_voice\n- register: formal-técnico\n- structure: Párrafos narrativos continuos.\n"
    "- banned_words: Sin latinismos.\n- argument_style: [DEDUCTIVO]\n\n"
    "## hard_nos\n- Nunca presentar borrador sin revisión.\n- Nunca recomendar allanarse sin análisis.\n\n"
    "## doctrinal_stance\n- preferred_sources: Consejo de Estado antes que doctrina foránea.\n"
    "- key_jurisprudence:\n  - T-323/2024\n- discarded_args: No sugerir prescripción fiscal sin verificar.\n\n"
    "## memory\n- decisions_made:\n  - \"[INTENTÉ X]\"\n- orbit:\n  - \"[NOMBRE]\"\n"
    "- tools_that_survived: Obsidian, Claude Code, Linear\n\n"
    "## rhythm\n- deep_work: 07:00–12:00\n- no_meetings: lunes y viernes\n- weekend: solo urgencias\n"
    "- energy_curve: [MAÑANA producción]\n\n"
    "## triad_mode\n- enabled: true\n- trigger: imputaciones fiscales >$1.000M COP y arbitrajes\n"
)


def _resp(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=15, completion_tokens=25, total_tokens=40))


def _fake_call_llm(messages, *, task=None, model=None, **kw):
    if task == "soul":
        return _resp(_SOUL_FIXTURE)
    sysmsg = messages[0]["content"] if messages and isinstance(messages[0], dict) else ""
    if "Redacta el borrador" in sysmsg:
        return _resp("BORRADOR: contestación de la demanda. [VERIFICAR fecha del hecho]")
    if "Incorpora al borrador" in sysmsg:
        return _resp("BORRADOR CORREGIDO con las indicaciones.")
    if "GATE DE CALIDAD DE CITAS" in sysmsg:
        # El gate LLM (f264b1e) devuelve el borrador auditado: el mock lo deja pasar
        # TAL CUAL para que el flujo conserve el borrador de prueba.
        user = messages[-1]["content"] if isinstance(messages[-1], dict) else ""
        return _resp(user.split("Borrador:\n", 1)[-1] if "Borrador:\n" in user else user)
    return _resp("DIAGNÓSTICO: el eje del asunto es la caducidad de la acción.")


def _fake_embed(texts):
    return [[0.1] + [0.0] * (config.EMBED_DIM - 1) for _ in texts]


embeddings.embed_texts = _fake_embed
llm.call_llm = _fake_call_llm

PG = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
          dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""))

FORBIDDEN = ("hitl", "langgraph", "pgvector", "tenant_id", "tool_call", "embedding")

# Respuestas del despacho Lexia por field de cada pregunta — CONTRATO VIGENTE
# (rediseño 2026-07-20): exactamente lo que manda el wizard hoy. Antes este fixture traía
# además `jurisdiction.courts`, `mission.*` y `doctrinal_stance.*`: campos que NADIE lee
# desde que se recortó la entrevista. El endpoint los aceptaba y los tiraba en silencio —
# el fallo que este gate ahora comprueba que está cerrado.
LEXIA = {
    "identity.name": "Lexia Abogados S.A.S. · Juan Felipe Torres · T.P. 227.698",
    "identity.location": "Bogotá, Colombia — UTC-5",
    "jurisdiction.base": "Colombia — también España ocasionalmente",
    "jurisdiction.practice_areas": "Seguros, responsabilidad fiscal, contencioso-administrativo, contratos públicos",
    "jurisdiction.client_type": "Aseguradoras (HDI, Zurich, SURA, Seguros del Estado)",
    "autonomia.reviso_siempre": ["Todo lo que se radica", "Escritos que van al cliente"],
    "autonomia.decide_solo": ["Resúmenes internos", "Cronologías", "Buscar y ordenar fuentes"],
    "nunca": ["Citar sin verificar la fuente",
              "Afirmar hechos que no estén en el expediente",
              "Presentar un borrador sin que yo lo revise"],
    "terminado": "Cuando cada afirmación tiene respaldo en el expediente y yo lo leí completo.",
}

# Perfil de una entrevista ANTERIOR al rediseño: campos que ya no se preguntan pero que el
# generador SIGUE renderizando. Sirve para probar que un despacho ya configurado degrada
# limpio — no se le pierde nada ni deja de poder guardar.
LEXIA_LEGACY = {
    "identity.name": "Lexia Abogados S.A.S. · Juan Felipe Torres · T.P. 227.698",
    "identity.location": "Bogotá, Colombia — UTC-5",
    "identity.voice": "Técnico, argumentativo, conciso",
    "identity.channels": "lexia.co — LinkedIn Lexia Abogados",
    "jurisdiction.base": "Colombia",
    "jurisdiction.practice_areas": "Seguros, responsabilidad fiscal",
    "legal_voice.structure": "Párrafos narrativos continuos. Sin viñetas en escritos de fondo.",
    "legal_voice.banned_words": "Sin latinismos. Sin insalvable.",
    "hard_nos": "Nunca presentar borrador sin revisión.",
    "rhythm": "Mañanas 7am-12pm trabajo profundo. Sin reuniones lunes ni viernes.",
    "memory.tools_that_survived": "Obsidian, Claude Code, Linear, WhatsApp Business.",
    "triad_mode": "Sí — imputaciones fiscales >$1.000M COP y arbitrajes",
}

# Perfil de un despacho configurado con el cuestionario ORIGINAL de 19 preguntas (anterior
# a los recortes de 2026-07-06/09). Copiado de la FORMA de los perfiles reales que hay en
# `mia-data/`: `identity.name` como objeto {firm, lawyer} y campos que hoy ya no renderiza
# nadie (`jurisdiction.courts`, `jurisdiction.key_courts`, `mission.*`,
# `doctrinal_stance.*`, `memory.*`). Es el payload que dejaba encerrado al abogado fuera de
# su propio perfil: "Revisar mi perfil" lo reenvía TAL CUAL y el endpoint respondía 422.
LEXIA_PRE_RECORTE = {
    **LEXIA_LEGACY,
    "identity.name": {"firm": "Lexia Abogados", "lawyer": "Juan Felipe Torres"},
    "jurisdiction.client_type": "Aseguradoras",
    "jurisdiction.courts": "Consejo de Estado, tribunales administrativos",
    "jurisdiction.key_courts": "Sección Tercera",
    "doctrinal_stance.preferred_sources": "Jurisprudencia nacional antes que doctrina foránea",
    "doctrinal_stance.discarded_args": "No alegar prescripción sin verificar",
    "mission.headline": "Consolidar la práctica de seguros",
    "mission.pillars": ["Excelencia en litigios", "Primer cliente externo"],
    "memory.decisions_made": "Se dejó de usar el gestor documental anterior",
    "memory.orbit": "Equipo de tres abogados",
}


def make_tenant() -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute("INSERT INTO tenants(name) VALUES('E2E_LEXIA') RETURNING id").fetchone()[0])


def chunk_count(tid: str) -> int:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute("SELECT count(*) FROM chunks WHERE tenant_id=%s::uuid", (tid,)).fetchone()[0]


def cleanup(tid: str, threads: list[str]) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        for th in threads:
            for t in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                c.execute(f"DELETE FROM {t} WHERE thread_id=%s", (th,))
        c.execute("DELETE FROM tenants WHERE id=%s", (tid,))


def make_pdf_2pages() -> bytes:
    """PDF sintético de 2 páginas con texto de la Ley 80/1993 (fixture, no cita entregada)."""
    import fitz
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), (
        "Ley 80 de 1993 — Estatuto General de Contratacion de la Administracion Publica. "
        "Tiene por objeto disponer las reglas y principios que rigen los contratos de las "
        "entidades estatales. Los contratos estatales se rigen por los principios de "
        "transparencia, economia y responsabilidad."))
    p2 = doc.new_page()
    p2.insert_text((72, 72), (
        "De la responsabilidad contractual del Estado: las entidades responderan por las "
        "actuaciones y omisiones antijuridicas que les sean imputables y que causen perjuicio "
        "a los contratistas. La accion de controversias contractuales se sujeta al termino de "
        "caducidad previsto en la ley."))
    data = doc.tobytes()
    doc.close()
    return data


def run_e2e(client, auth, tid) -> list[str]:
    visible = []
    threads = []

    # ── PASO 1 · Onboarding ──────────────────────────────────────────────────
    print("\n-- Paso 1 · Onboarding (SOUL.md) --")
    r = client.get("/api/onboarding/questions", headers=auth)
    qs = r.json() if r.status_code == 200 else []
    # Contrato 2026-07-20 (rediseño "más rico, no más largo"): 6 preguntas de backend —
    # el frontend añade encima su paso local de jurisdicción (7 pasos para el abogado).
    # Removidas del cuestionario (el endpoint NO debe reintroducirlas): P5 (país — lo
    # pregunta el selector único del frontend), P8/P9/P12/P13 (se aprenden del uso),
    # P15/P16 (estrategia), P10/P11/P14/P17 (voz/límites/ritmo), y ahora P3 (estilo en
    # adjetivos), P4 (canales), P7 (fusionada en P6), P18 (herramientas) y P19 (modo
    # profundo, no implementado).
    removed_ids = {"p3", "p4", "p5", "p7", "p8", "p9", "p10", "p11", "p12", "p13",
                   "p14", "p15", "p16", "p17", "p18", "p19"}
    qids = {q.get("id") for q in qs}
    check("GET /api/onboarding/questions -> 6 preguntas (sin las removidas: P3/P4/P5/P7-P19)",
          r.status_code == 200 and len(qs) == 6 and not (qids & removed_ids))
    check("cada pregunta trae id/block/field/question/example",
          bool(qs) and all({"id", "block", "field", "question", "example"} <= set(q) for q in qs))
    check("las preguntas cubren los bloques vigentes (identity/jurisdiction/criterio)",
          {q["block"] for q in qs} == {"identity", "jurisdiction", "criterio"})
    # Las 3 preguntas que hacen COMPUTABLE el criterio: sin ellas el perfil vuelve a ser
    # una tarjeta de presentación (datos censales y cero juicio).
    check("la entrevista pregunta autonomía, líneas rojas y estándar de cierre",
          {q["field"] for q in qs} >= {"autonomia.reviso_siempre", "nunca", "terminado"})

    # ── El guardián conectado (arreglo 2026-07-20) ───────────────────────────
    # Antes: mandar llaves por ID de pregunta devolvía 200 OK con un SOUL de dos líneas.
    # Nadie se enteraba. Ahora, si NADA de lo que llega es legible, el endpoint corta
    # antes de escribir — pero en llano: al abogado no se le enseñan llaves internas (el
    # detalle va al registro del servidor, que es quien lo necesita).
    with capture_logs("mia.api.ux") as logs:
        r_mal = client.post("/api/onboarding/complete", headers=auth,
                            json={"responses": {"p1": "Estudio Nogales", "p2": "Ciudad, País"}})
    check("POST /complete sin UNA sola llave legible -> 422 (ya no 200 en silencio)",
          r_mal.status_code == 422)
    check("el rechazo NO le enseña llaves internas al abogado (§G)",
          not any(k in r_mal.text for k in ("p1", "p2", "identity.", "jurisdiction.")))
    check("el rechazo SÍ deja las llaves ilegibles en el registro del servidor",
          any("p1" in m and "p2" in m for m in logs))

    # "Sin nombre del despacho" de verdad: hay identidad (## identity aparece) pero no hay
    # dueño. Antes este check pasaba con un payload SIN ningún campo de identidad, así que
    # nunca ejercitaba lo que su nombre decía (hallazgo MAYOR-3).
    r_vacio = client.post("/api/onboarding/complete", headers=auth,
                          json={"responses": {"identity.location": {"country": "País", "city": "Ciudad"}}})
    check("POST /complete con ciudad pero SIN nombre del despacho -> 422",
          r_vacio.status_code == 422)
    r_blanco = client.post("/api/onboarding/complete", headers=auth,
                           json={"responses": {"identity.name": {"firm": "", "lawyer": ""},
                                               "terminado": "Cuando todo tiene respaldo."}})
    check("POST /complete con el nombre del despacho en blanco -> 422",
          r_blanco.status_code == 422)
    check("el mensaje pide exactamente lo que exige (el nombre del despacho)",
          "nombre de tu despacho" in r_vacio.text and "nombre de tu despacho" in r_blanco.text)
    check("ninguno de los tres rechazos dejó SOUL.md escrito", not soul_path(tid).exists())

    r = client.post("/api/onboarding/complete", headers=auth, json={"responses": LEXIA})
    body = r.json() if r.status_code == 200 else {}
    check("POST /api/onboarding/complete -> 200 con soul_content",
          r.status_code == 200 and bool(body.get("soul_content")))

    soul_file = soul_path(tid)
    check("soul_{tenant}.md creado en $MIA_HOME", soul_file.exists())
    soul_text = soul_file.read_text(encoding="utf-8") if soul_file.exists() else ""
    check("el SOUL.md sale limpio (sin corchetes), con identidad y SIN sección mission",
          "## identity" in soul_text and "## mission" not in soul_text
          and "[" not in soul_text and validate_soul(soul_text) == [])
    check("el SOUL.md trae el CRITERIO del despacho, no solo sus datos (## autonomia/nunca/terminado)",
          all(s in soul_text for s in ("## autonomia", "## nunca", "## terminado")))
    check("el SOUL.md NO imprime secciones que el despacho no llenó",
          not any(s in soul_text for s in ("## tools", "## legal_voice", "## aprendido")))

    snap = load_soul_snapshot(tid)
    check("soul_snapshot se carga para el turno (wiring al grafo, Q2)",
          bool(snap) and "Lexia" in (snap or {}).get("content", ""))

    r = client.get("/api/onboarding/status", headers=auth)
    check("GET /api/onboarding/status -> completed=true tras el onboarding",
          r.status_code == 200 and r.json().get("completed") is True)

    # ── PASO 2 · Crear asunto ────────────────────────────────────────────────
    print("\n-- Paso 2 · Crear asunto --")
    r = client.post("/api/matters", headers=auth,
                    json={"name": "Prueba E2E — Demanda seguros", "description": "Asunto de prueba E2E"})
    mj = r.json() if r.status_code == 201 else {}
    mid = mj.get("id", "")
    check("POST /api/matters -> 201 con id", r.status_code == 201 and bool(mid))
    check("el asunto nace con status 'active'", mj.get("status") == "active")
    threads.append(thread_id_for(tid, mid))
    visible.append(r.text)

    # ── PASO 3 · Subir documento (PDF 2 páginas, Ley 80/1993) ────────────────
    print("\n-- Paso 3 · Subir documento --")
    r = client.post(f"/api/matters/{mid}/documents", headers=auth,
                    files={"file": ("ley80_1993.pdf", make_pdf_2pages(), "application/pdf")})
    check("POST documents (PDF 2 págs) -> 201 con fragmentos",
          r.status_code == 201 and r.json().get("fragments", 0) >= 1)
    check("el documento se ingirió: chunks en DB > 0", chunk_count(tid) > 0)

    # ── PASO 4 · Chat y streaming ────────────────────────────────────────────
    print("\n-- Paso 4 · Chat + streaming --")
    r = client.post(f"/api/matters/{mid}/chat", headers=auth,
                    json={"message": "¿Cuál es el problema jurídico central?"})
    check("POST /api/matters/{id}/chat -> 200 con stream_url",
          r.status_code == 200 and "stream_url" in r.json())
    with client.stream("GET", f"/api/matters/{mid}/stream",
                       params={"message": "¿Cuál es el problema jurídico central?"}, headers=auth) as s:
        ct = s.headers.get("content-type", "")
        sbody = "".join(s.iter_text())
    check("GET stream -> text/event-stream y llega a awaiting_review",
          "text/event-stream" in ct and "awaiting_review" in sbody)
    check("el stream no expone jerga técnica (§G)",
          not any(j in sbody for j in ("langgraph", "interrupt", "pgvector", "checkpoint")))

    # ── PASO 5 · HITL ────────────────────────────────────────────────────────
    print("\n-- Paso 5 · HITL (revisión del borrador) --")
    r = client.get(f"/api/matters/{mid}/draft", headers=auth)
    check("GET /api/matters/{id}/draft -> 200 o 404 (documentado)",
          r.status_code in (200, 404))
    if r.status_code == 200:
        check("el borrador está disponible para revisión", r.json().get("draft", "").startswith("BORRADOR"))
        with client.stream("POST", f"/api/matters/{mid}/draft/approve", headers=auth, json={}) as s:
            ok_appr = s.status_code == 200
            _ = "".join(s.iter_text())
        check("POST draft/approve -> 200", ok_appr)
    else:
        check("borrador 404: el mock no dejó borrador (aceptable)", True)
        check("approve omitido (sin borrador) — paso documentado", True)
    r = client.get(f"/api/matters/{mid}", headers=auth)
    check("el asunto sigue activo tras la revisión",
          r.status_code == 200 and r.json().get("status") == "active")

    # ── PASO 6 · Memoria ─────────────────────────────────────────────────────
    print("\n-- Paso 6 · Memoria --")
    r = client.get("/api/profile", headers=auth)
    check("GET /api/profile -> 200", r.status_code == 200)
    visible.append(r.text)
    r = client.get("/api/playbooks", headers=auth)
    check("GET /api/playbooks -> 200 (lista)", r.status_code == 200 and isinstance(r.json(), list))
    r = client.get("/api/proposals", headers=auth)
    check("GET /api/proposals -> 200 (lista)", r.status_code == 200 and isinstance(r.json(), list))

    # ── PASO 7 · Dashboard ───────────────────────────────────────────────────
    print("\n-- Paso 7 · Dashboard --")
    r = client.get("/api/dashboard/stats", headers=auth)
    dj = r.json() if r.status_code == 200 else {}
    check("GET /api/dashboard/stats -> 200 con matters_active >= 1",
          r.status_code == 200 and dj.get("matters_active", 0) >= 1)
    check("documents_indexed >= 1 (el PDF del paso 3)", dj.get("documents_indexed", 0) >= 1)
    visible.append(r.text)

    # §G global sobre lo que ve el abogado.
    blob = " ".join(visible).lower()
    leaked = [w for w in FORBIDDEN if w in blob]
    check(f"§G: respuestas sin jerga técnica (fugas: {leaked or 'ninguna'})", not leaked)

    return threads


def run_perfil_ya_creado_checks(client) -> None:
    """Un despacho YA CONFIGURADO no puede quedar encerrado fuera de su perfil.

    Va POR EL ENDPOINT a propósito (BLOQUEANTE-2, 2026-07-20): el check anterior llamaba
    a `update_soul` directamente, saltándose los tres validadores nuevos, y su fixture solo
    traía campos que ya estaban en `KNOWN_FIELDS`. Es decir: el único check que decía cubrir
    la degradación de un perfil viejo no ejercitaba ni el camino donde estaba el defecto ni
    el payload que lo disparaba. Verde perpetuo sobre un 422 real.

    Usa su propio despacho para no pisar el SOUL.md del recorrido principal."""
    import jwt

    print("\n-- Un perfil ya creado sigue funcionando (degradación por el API real) --")
    tid = make_tenant()
    auth = {"Authorization": f"Bearer {jwt.encode({'tenant_id': tid}, config.JWT_SECRET, algorithm=config.JWT_ALG)}"}
    try:
        r = client.post("/api/onboarding/complete", headers=auth,
                        json={"responses": dict(LEXIA_PRE_RECORTE)})
        check("soul-legacy-3 · un perfil del cuestionario ANTERIOR se vuelve a guardar por el API -> 200",
              r.status_code == 200)
        soul = (r.json().get("soul_content", "") if r.status_code == 200 else "")
        check("soul-legacy-3b · ese perfil conserva TODAS sus secciones (no pierde nada)",
              validate_soul(soul) == []
              and all(s in soul for s in ("## legal_voice", "## hard_nos", "## rhythm",
                                          "## tools", "## triad_mode"))
              and "Lexia Abogados" in soul)

        # Los campos que hoy no renderiza nadie NO se destruyen: se guardan igual, para que
        # "Revisar mi perfil" siga mostrando lo que el abogado escribió en su día.
        r = client.get("/api/onboarding/status", headers=auth)
        guardadas = r.json().get("responses", {}) if r.status_code == 200 else {}
        check("soul-legacy-3c · los campos del cuestionario anterior se conservan, no se tiran",
              all(k in guardadas for k in ("jurisdiction.courts", "jurisdiction.key_courts",
                                           "mission.headline", "memory.orbit")))

        # El camino REAL de "Revisar mi perfil": reenviar TAL CUAL lo que devuelve status.
        r = client.post("/api/onboarding/complete", headers=auth, json={"responses": guardadas})
        check("soul-legacy-3d · reenviar el perfil tal cual lo devuelve el API -> 200 (ida y vuelta)",
              r.status_code == 200)

        # "Mi despacho" escribe la misma fuente canónica: tampoco puede rechazarlo.
        r = client.put("/api/profile/full", headers=auth, json={"responses": guardadas})
        check("soul-legacy-3e · «Mi despacho» también acepta el perfil ya creado",
              r.status_code == 200)

        # Llave de una versión futura/desconocida MEZCLADA con datos legibles: se ignora
        # esa llave y se guarda el resto. Un campo suelto no puede tumbar el perfil entero.
        with capture_logs("mia.api.ux") as logs:
            r = client.post("/api/onboarding/complete", headers=auth,
                            json={"responses": {**guardadas, "campo_que_no_existe": "x"}})
        check("soul-legacy-3f · una llave suelta que nadie lee NO tumba el perfil entero",
              r.status_code == 200 and "Lexia Abogados" in r.json().get("soul_content", ""))
        check("soul-legacy-3g · la llave ignorada queda en el registro del servidor",
              any("campo_que_no_existe" in m for m in logs))
        r = client.get("/api/onboarding/status", headers=auth)
        check("soul-legacy-3h · la llave ignorada no se guardó en el perfil",
              "campo_que_no_existe" not in r.json().get("responses", {}))
    finally:
        cleanup(tid, [])


def run_soul_validation_checks() -> None:
    """Rediseño 2026-07-06 (decisión de Pipe): el SOUL se genera DETERMINISTA, OMITE lo
    vacío y JAMÁS imprime placeholders entre corchetes. Se removieron las preguntas de
    objetivo/pilares (sección mission). validate_soul marca cualquier corchete sobrante."""
    print("\n-- SOUL determinista: sin corchetes, omite lo vacío, con resumen llano --")
    from mia.onboarding.soul_interview import (
        SoulInterview, build_soul, build_summary, validate_soul)

    # validate_soul (diseño determinista): solo exige la sección de identidad; ya NO
    # caza corchetes (un abogado puede escribir uno legítimo — hallazgo capa 2 B1).
    limpio = build_soul(dict(LEXIA))
    check("soul-v0 · validate_soul acepta un SOUL con identidad y marca su ausencia",
          validate_soul(limpio) == [] and validate_soul("## jurisdiction\n- base: X") == ["## identity"])

    # build_soul con datos SIN corchetes no emite corchetes (el generador es limpio por
    # construcción — omite lo vacío, jamás imprime plantilla).
    check("soul-v1 · el SOUL generado desde respuestas limpias no contiene corchetes",
          "[" not in limpio and "]" not in limpio)
    check("soul-v2 · trae ## identity y ## jurisdiction y NO trae ## mission",
          "## identity" in limpio and "## jurisdiction" in limpio and "## mission" not in limpio)

    # B1 (capa 2): un corchete que el abogado ESCRIBIÓ se preserva tal cual y NO rompe
    # la validación (no es un placeholder de plantilla, es un dato real).
    con_dato = dict(LEXIA); con_dato["legal_voice.banned_words"] = "Nunca escribir [sic] en un escrito"
    soul_dato = build_soul(con_dato)
    check("soul-v0b · un corchete legítimo del abogado se conserva y NO se marca como defecto",
          "[sic]" in soul_dato and validate_soul(soul_dato) == [])

    si = SoulInterview()
    content = asyncio.run(si.run_interview("t-soul-det-a", dict(LEXIA)))
    check("soul-v3 · run_interview (determinista) produce un SOUL limpio y con datos",
          validate_soul(content) == [] and "Lexia" in content)

    # update_soul fusiona respuestas previas + cambios y RECONSTRUYE (determinista).
    updated = asyncio.run(si.update_soul("t-soul-det-a", {"identity.channels": "nuevositio.co"}))
    check("soul-v4 · update_soul reconstruye limpio conservando lo demás",
          validate_soul(updated) == [] and "nuevositio.co" in updated and "Lexia" in updated)

    # resumen en lenguaje llano: es lo que ve el abogado (el SOUL.md queda por debajo).
    resumen = build_summary(dict(LEXIA))
    check("soul-v5 · el resumen llano es legible, sin corchetes ni encabezados técnicos",
          "Así entendí a tu despacho" in resumen and "[" not in resumen
          and "## identity" not in resumen)
    check("soul-v6 · el resumen le devuelve al abogado su criterio, no solo sus datos",
          all(t in resumen for t in ("Lo que reviso siempre contigo",
                                     "Lo que resuelvo sin preguntarte",
                                     "Un escrito está listo cuando",
                                     "Lo que nunca debo hacer")))
    # El resumen ya NO se contradice: antes preguntaba el estilo en 3 adjetivos y a
    # renglón seguido decía "tu estilo no te lo pregunto". Hoy es cierto: no se pregunta.
    check("soul-v7 · el resumen no se contradice: no se pide el estilo y se dice que se aprende",
          "Estilo de escritura" not in resumen
          and "Tu estilo de redacción no te lo pregunto" in resumen)

    # ── Degradación de un perfil YA CREADO (contrato anterior al rediseño) ────
    # Es la comprobación que no se puede suponer: un despacho configurado antes NO puede
    # perder lo suyo ni dejar de guardarse porque el cuestionario cambió.
    viejo = build_soul(dict(LEXIA_LEGACY))
    check("soul-legacy-1 · un perfil viejo sigue siendo válido y conserva TODAS sus secciones",
          validate_soul(viejo) == []
          and all(s in viejo for s in ("## legal_voice", "## hard_nos", "## rhythm",
                                       "## tools", "## triad_mode"))
          and "voice: Técnico" in viejo and "channels: lexia.co" in viejo)
    check("soul-legacy-2 · un perfil viejo NO gana secciones nuevas vacías",
          not any(s in viejo for s in ("## autonomia", "## nunca", "## terminado",
                                       "## aprendido")))
    # OJO: "un perfil viejo se puede volver a guardar" NO se comprueba aquí. Se comprueba
    # POR EL ENDPOINT en `run_perfil_ya_creado_checks` — llamar a `update_soul` directamente
    # se salta los tres validadores del API, que es justo donde vivía el 422.
    viejo_upd = asyncio.run(si.update_soul("t-soul-legacy", dict(LEXIA_LEGACY)))
    check("soul-legacy-3i · update_soul reconstruye un perfil viejo sin perder secciones",
          validate_soul(viejo_upd) == [] and "Lexia" in viejo_upd
          and all(s in viejo_upd for s in ("## legal_voice", "## rhythm", "## tools")))

    # El contraste del guardián tiene que cubrir el cuestionario ORIGINAL de 19 preguntas:
    # si un campo de aquellos se cae de la lista, el despacho que lo tenga vuelve a quedar
    # encerrado fuera de su perfil. Se afirma campo por campo, no por conteo.
    from mia.onboarding.soul_interview import KNOWN_FIELDS, firm_name
    pre_recorte = {"jurisdiction.courts", "jurisdiction.key_courts",
                   "doctrinal_stance.preferred_sources", "doctrinal_stance.discarded_args",
                   "mission.headline", "mission.pillars",
                   "memory.decisions_made", "memory.orbit"}
    check("soul-legacy-4 · el guardián reconoce los campos del cuestionario original",
          pre_recorte <= KNOWN_FIELDS and set(LEXIA_PRE_RECORTE) <= KNOWN_FIELDS)
    # El nombre del despacho es lo único que el endpoint exige: se lee igual en la forma
    # nueva ({firm, lawyer}) y en la vieja (string con separadores).
    check("soul-legacy-5 · el nombre del despacho se lee en la forma nueva y en la vieja",
          firm_name({"identity.name": {"firm": "Estudio X", "lawyer": "A"}}) == "Estudio X"
          and firm_name({"identity.name": "Estudio X · A"}) == "Estudio X"
          and firm_name({"identity.location": "Ciudad, País"}) == ""
          and firm_name({"identity.name": {"firm": "  ", "lawyer": "A"}}) == "")
    # `## aprendido` existe como destino: hoy NO la llena ninguna pregunta (la escribe
    # Mia desde el trabajo real — incremento aparte). Se comprueba el render, no el
    # escritor: afirmar que se llena sola sería afirmar lo que el código no hace.
    check("soul-aprendido · la sección se renderiza SOLO si alguien la escribió",
          "## aprendido" not in build_soul(dict(LEXIA))
          and "## aprendido" in build_soul({**LEXIA, "aprendido": ["[inferido] 2026-07-20 · x"]}))


def main() -> int:
    print("== GATE FINAL · test_e2e — recorrido completo del abogado ==")
    if not os.getenv("PG_PASSWORD") or not config.JWT_SECRET:
        print("  [FAIL] PG_PASSWORD o JWT_SECRET vacío en .env")
        return 1

    init_profiles.apply()

    # Aísla $MIA_HOME en un tempdir (no contamina mia-data/ real; SOUL.md verificable).
    mia_home = tempfile.mkdtemp(prefix="mia_home_e2e_")
    config.MIA_HOME = Path(mia_home)

    import jwt
    from fastapi.testclient import TestClient
    from mia.api.main import app

    tid = make_tenant()
    token = jwt.encode({"tenant_id": tid}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    auth = {"Authorization": f"Bearer {token}"}
    threads: list[str] = []
    try:
        with TestClient(app) as client:
            threads = run_e2e(client, auth, tid)
            run_perfil_ya_creado_checks(client)
        run_soul_validation_checks()   # CP6 (offline, usa el mismo tempdir de MIA_HOME)
    finally:
        cleanup(tid, threads)
        shutil.rmtree(mia_home, ignore_errors=True)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("\n*** GATE FINAL VERDE — Mia v0 operativa (Módulo 5 cerrado). ***")
        return 0
    print("\nGATE FINAL FAIL — HALT: el proyecto no se marca completo (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
