"""
Mia · test_projects.py — gate del Bloque A (evolución de producto): PROYECTOS.

Ejercita, contra la DB real (migración 028), la superficie /api/matters con kind=
'asunto'|'proyecto' y los archivos que Mia produce dentro de un proyecto (outputs),
con el LLM y los embeddings MOCKEADOS (sin red). Molde calcado de
execution/test_matter_folder.py (event loop policy, .env, tenants propios con
limpieza en finally, TestClient + JWT). Cubre:

  1. Crear proyecto/asunto; GET /api/matters sin param NO trae proyectos; ?kind=proyecto
     los trae; ?kind=todos trae ambos; kind inválido al crear -> 422.
  2. Outputs: crear -> aparece en la lista y tiene chunks (consultable); dedupe por
     sha256 (segundo POST igual no duplica); descarga .docx con bytes y content-type
     correctos; outputs en un asunto -> 422; doc_id malformado -> 404; AISLAMIENTO:
     el tenant B no puede leer/descargar un output del tenant A (404).
  3. Turno de proyecto vía stream (LLM stubbeado): recibe 'reply' y NO deja
     pending_review=true; turno de asunto sigue emitiendo 'awaiting_review'
     (no-regresión del flujo HITL).
  4. Guardián de citas en un PROYECTO: la respuesta pasa SIEMPRE por la verificación
     antes de llegar al abogado (norma sin respaldo y referencia a un documento
     inexistente salen marcadas), la memoria del proyecto guarda el texto ya marcado,
     y el respaldo sale del material que el abogado suministró.
  5. Ordenamiento aplicable: el derecho bajo el que trabaja el despacho llega al prompt
     de un PROYECTO (que nunca corre investigación) y a los especialistas del asunto que
     hablan antes de ella; sin configurar, Mia sigue sin poder nombrar articulado de
     ningún país; si la configuración no se puede leer, el turno no se cae.
  6. Anti-jerga (§G) en todas las respuestas visibles al abogado.

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_projects.py
"""
from __future__ import annotations
import asyncio
import os
import sys
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

# La consola de PowerShell es cp1252: forzar utf-8 evita un crash al imprimir.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import init_projects_multifolder                # noqa: E402  (migración 028)
from mia import config, embeddings               # noqa: E402
from mia.agent import llm                         # noqa: E402
from mia.agents.state import thread_id_for        # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── mocks (sin red) ──────────────────────────────────────────────────────────
# H6: se capturan las llamadas (embeddings + LLM) para poder inspeccionar, turno a
# turno, exactamente qué texto vio cada uno — sin esto no hay forma de comprobar desde
# afuera que la memoria conversacional llegó al prompt del segundo turno.
_embed_calls: list[list[str]] = []
_llm_calls: list[list[dict]] = []


def _fake_embed(texts):
    _embed_calls.append(list(texts))
    return [[0.1] + [0.0] * (config.EMBED_DIM - 1) for _ in texts]


def _fake_call_llm(messages, *, task=None, model=None, **kw):
    _llm_calls.append(messages)
    sysmsg = messages[0]["content"] if messages and isinstance(messages[0], dict) else ""
    if "PROYECTO" in sysmsg and "Tarea de este turno" in sysmsg:
        # A propósito SIN marcas: es lo que el guardián de citas tiene que atrapar en un
        # proyecto (una norma afirmada sin respaldo y una referencia a un documento que no
        # existe). Si el gate fuera solo texto de prompt, esto llegaría tal cual al abogado.
        content = ("RESPUESTA DEL PROYECTO: aquí tienes el análisis pedido. Conforme a la "
                   "Ley 1437 de 2011 procede la acción, según consta en [doc 9].")
    elif "Redacta el borrador" in sysmsg:
        content = "BORRADOR: contestación de la demanda. [VERIFICAR fecha del hecho]"
    elif "Incorpora al borrador" in sysmsg:
        content = "BORRADOR CORREGIDO con las indicaciones."
    else:
        content = "DIAGNÓSTICO: el eje es la caducidad de la acción."
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=20, total_tokens=32))


embeddings.embed_texts = _fake_embed
llm.call_llm = _fake_call_llm

PG = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
          dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""))

FORBIDDEN = ("hitl", "langgraph", "pgvector", "tenant_id", "chunk", "embedding", "sync engine")


def make_tenant(name: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id", (name,)).fetchone()[0])


def cleanup(tenants: list[str], threads: list[str]) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        for th in threads:
            for t in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                c.execute(f"DELETE FROM {t} WHERE thread_id=%s", (th,))
        c.execute("DELETE FROM tenants WHERE id = ANY(%s)", (tenants,))


def count_chunks(doc_id: str) -> int:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(
            "SELECT count(*) FROM chunks WHERE document_id=%s::uuid", (doc_id,)).fetchone()[0]


def count_docs_by_sha(matter_id: str, sha256: str) -> int:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(
            "SELECT count(*) FROM documents WHERE matter_id=%s::uuid AND origin='mia' AND sha256=%s",
            (matter_id, sha256)).fetchone()[0]


def pending_review_of(matter_id: str) -> bool:
    with psycopg.connect(autocommit=True, **PG) as c:
        row = c.execute(
            "SELECT pending_review FROM matters WHERE id=%s::uuid", (matter_id,)).fetchone()
    return bool(row[0]) if row else False


def run_checks(client, auth_a, tid_a, auth_b, tid_b) -> list[str]:
    threads: list[str] = []
    visible: list[str] = []

    # ── 1 · kind en la creación y el listado ─────────────────────────────────
    r = client.post("/api/matters", headers=auth_a, json={"name": "Asunto normal"})
    check("crear sin kind -> 201 default 'asunto'",
          r.status_code == 201 and r.json().get("kind") == "asunto")
    asunto_id = r.json()["id"]
    visible.append(r.text)

    r = client.post("/api/matters", headers=auth_a,
                    json={"name": "Proyecto de prueba", "kind": "proyecto"})
    check("crear kind='proyecto' -> 201", r.status_code == 201 and r.json().get("kind") == "proyecto")
    proyecto_id = r.json()["id"]
    visible.append(r.text)
    threads += [thread_id_for(tid_a, asunto_id), thread_id_for(tid_a, proyecto_id)]

    r = client.post("/api/matters", headers=auth_a, json={"name": "Malo", "kind": "invalido"})
    check("crear kind inválido -> 422", r.status_code == 422)

    r = client.get("/api/matters", headers=auth_a)
    ids = {it["id"] for it in r.json()}
    check("GET /api/matters sin param NO trae el proyecto (compat)",
          asunto_id in ids and proyecto_id not in ids)
    visible.append(r.text)

    r = client.get("/api/matters", headers=auth_a, params={"kind": "proyecto"})
    ids_p = {it["id"] for it in r.json()}
    check("GET /api/matters?kind=proyecto trae SOLO el proyecto",
          proyecto_id in ids_p and asunto_id not in ids_p)
    visible.append(r.text)

    r = client.get("/api/matters", headers=auth_a, params={"kind": "todos"})
    ids_t = {it["id"] for it in r.json()}
    check("GET /api/matters?kind=todos trae ambos", asunto_id in ids_t and proyecto_id in ids_t)
    visible.append(r.text)

    r = client.get(f"/api/matters/{proyecto_id}", headers=auth_a)
    check("GET /api/matters/{id} de un proyecto expone kind='proyecto'",
          r.status_code == 200 and r.json().get("kind") == "proyecto")
    visible.append(r.text)

    # ── 2 · outputs (archivos producidos por Mia dentro del proyecto) ────────
    contenido = ("Memo de análisis: el proyecto reúne tres fuentes conectadas sobre "
                "la cláusula de indemnización de perjuicios. " * 5)
    r = client.post(f"/api/matters/{proyecto_id}/outputs", headers=auth_a,
                    json={"title": "Memo de análisis", "content": contenido})
    check("POST /outputs -> 201 con id", r.status_code == 201 and "id" in r.json())
    out_id = r.json()["id"]
    visible.append(r.text)

    r = client.get(f"/api/matters/{proyecto_id}/outputs", headers=auth_a)
    outs = r.json().get("outputs", [])
    check("GET /outputs -> aparece el archivo recién creado",
          r.status_code == 200 and any(o["id"] == out_id and o["title"] == "Memo de análisis"
                                       for o in outs))
    visible.append(r.text)
    check("el output tiene chunks (consultable después por el RAG)", count_chunks(out_id) >= 1)

    r_dup = client.post(f"/api/matters/{proyecto_id}/outputs", headers=auth_a,
                        json={"title": "Otro nombre, mismo contenido", "content": contenido})
    check("POST /outputs con el MISMO contenido -> 'duplicado' sin re-crear",
          r_dup.status_code == 200 and r_dup.json().get("status") == "duplicado"
          and r_dup.json().get("id") == out_id)
    visible.append(r_dup.text)
    import hashlib
    sha = hashlib.sha256(contenido.encode("utf-8")).hexdigest()
    check("dedupe: solo hay UNA fila con esa huella en el proyecto",
          count_docs_by_sha(proyecto_id, sha) == 1)

    r = client.get(f"/api/matters/{proyecto_id}/outputs/{out_id}.docx", headers=auth_a)
    check("GET /outputs/{id}.docx -> 200 con bytes y content-type correcto",
          r.status_code == 200 and len(r.content) > 0
          and "wordprocessingml.document" in r.headers.get("content-type", ""))

    # título/contenido fuera de rango -> 422 (Field min/max_length)
    r = client.post(f"/api/matters/{proyecto_id}/outputs", headers=auth_a,
                    json={"title": "", "content": "algo"})
    check("POST /outputs con title vacío -> 422", r.status_code == 422)

    # outputs en un ASUNTO -> 422 llano
    r = client.post(f"/api/matters/{asunto_id}/outputs", headers=auth_a,
                    json={"title": "No debería crearse", "content": "contenido cualquiera"})
    check("POST /outputs en un ASUNTO -> 422", r.status_code == 422)
    visible.append(r.text)
    r = client.get(f"/api/matters/{asunto_id}/outputs", headers=auth_a)
    check("GET /outputs en un ASUNTO -> 422", r.status_code == 422)

    # doc_id malformado -> 404
    r = client.get(f"/api/matters/{proyecto_id}/outputs/no-es-un-uuid.docx", headers=auth_a)
    check("GET /outputs/{doc_id malformado}.docx -> 404", r.status_code == 404)
    visible.append(r.text)

    # AISLAMIENTO: el tenant B, en SU PROPIO proyecto, no puede leer el output de A.
    r = client.post("/api/matters", headers=auth_b,
                    json={"name": "Proyecto de B", "kind": "proyecto"})
    proyecto_b = r.json()["id"]
    threads.append(thread_id_for(tid_b, proyecto_b))
    r = client.get(f"/api/matters/{proyecto_b}/outputs/{out_id}.docx", headers=auth_b)
    check("AISLAMIENTO: B no puede descargar el output de A -> 404", r.status_code == 404)
    visible.append(r.text)
    r = client.get(f"/api/matters/{proyecto_id}", headers=auth_b)
    check("AISLAMIENTO: B no ve el proyecto de A -> 401", r.status_code == 401)

    # ── 3 · turno de PROYECTO vía stream: 'reply', sin pending_review ────────
    # Durante ESTE turno el despacho declara un ordenamiento ('zz', inventado: lo que se
    # prueba es el cableado, no un país). Un proyecto nunca corre investigación, que era
    # el único punto donde el ordenamiento quedaba escrito en el turno; si el arreglo no
    # estuviera, el especialista del proyecto no lo vería ni con el despacho configurado.
    from mia.agents import research as _research_mod                        # noqa: E402
    _resolve_original = _research_mod.resolve_jurisdictions_for

    async def _ordenamiento_declarado(_tenant):
        return ["zz"]

    _research_mod.resolve_jurisdictions_for = _ordenamiento_declarado
    try:
        with client.stream("GET", f"/api/matters/{proyecto_id}/stream",
                           params={"message": "Resume las fuentes conectadas"}, headers=auth_a) as s:
            ct = s.headers.get("content-type", "")
            body_p = "".join(s.iter_text())
    finally:
        _research_mod.resolve_jurisdictions_for = _resolve_original
    check("proyecto: stream -> text/event-stream", "text/event-stream" in ct)
    check("proyecto: stream emite 'reply' con la respuesta",
          '"reply":' in body_p and "RESPUESTA DEL PROYECTO" in body_p)
    check("proyecto: stream NUNCA emite 'awaiting_review'", "awaiting_review" not in body_p)
    check("proyecto: pending_review sigue false tras el turno", pending_review_of(proyecto_id) is False)
    visible.append(body_p)

    # ── 3b · guardián de citas TAMBIÉN en proyectos ──────────────────────────
    # Lo que el abogado RECIBE ya viene marcado. El texto se emite una sola vez y
    # completo (no hay escritura palabra por palabra), así que si el evento saliera del
    # paso anterior a la verificación, estas tres comprobaciones fallarían.
    check("guardián: la norma afirmada sin respaldo llega MARCADA al abogado",
          "Ley 1437 de 2011 [VERIFICAR]" in body_p)
    check("guardián: la referencia a un documento inexistente llega MARCADA",
          "[doc 9] [VERIFICAR]" in body_p)
    check("guardián: el informe de citas viaja con la respuesta",
          '"verificacion":' in body_p and '"citas":' in body_p)

    def _work_calls() -> list[list[dict]]:
        # work_node es el ÚNICO nodo del grafo de proyecto que llama al LLM (intake solo
        # embebe) — su system trae siempre "PROYECTO" + "Tarea de este turno" (prompt_builder).
        return [m for m in _llm_calls if m and isinstance(m[0], dict)
                and "PROYECTO" in m[0].get("content", "")
                and "Tarea de este turno" in m[0].get("content", "")]

    # El ordenamiento del despacho VIAJÓ por el turno real (API → grafo compilado →
    # checkpoint → especialista del proyecto). Sin esto, el especialista trabajaría bajo
    # la instrucción restrictiva —sin poder nombrar norma de ningún país— aunque el
    # despacho tuviera su ordenamiento configurado: la regresión que este check cierra.
    from mia.agent import prompt_builder as _pb                             # noqa: E402
    _sys_work = _work_calls()[0][0]["content"] if _work_calls() else ""
    check("ordenamiento: el turno REAL del proyecto lo lleva hasta el especialista",
          "ZZ" in _sys_work)
    check("ordenamiento: con el despacho configurado el proyecto NO queda restringido",
          _pb.JURISDICTION_UNKNOWN not in _sys_work)

    # ── H6: memoria conversacional CORTA del proyecto (turno 2 recuerda el turno 1) ──
    with client.stream("GET", f"/api/matters/{proyecto_id}/stream",
                       params={"message": "Ahora acórtalo"}, headers=auth_a) as s:
        body_p2 = "".join(s.iter_text())
    check("H6 turno 2: stream emite 'reply'", '"reply":' in body_p2)
    visible.append(body_p2)

    work_calls = _work_calls()
    check("H6: hay dos llamadas al LLM de 'work' (una por turno)", len(work_calls) == 2)
    turno2_user = work_calls[-1][1]["content"] if len(work_calls) == 2 else ""
    check("H6: el prompt del turno 2 trae el bloque de conversación reciente",
          "Conversación reciente de este proyecto" in turno2_user)
    check("H6: el turno 2 CONTIENE la reply del turno 1 (memoria real, no solo el rótulo)",
          "RESPUESTA DEL PROYECTO" in turno2_user)
    # La memoria guarda el texto VERIFICADO. Si guardara el crudo, en el turno siguiente
    # Mia leería sus propias citas sin marca y las daría por buenas.
    check("guardián: la memoria del proyecto conserva el texto YA marcado",
          "Ley 1437 de 2011 [VERIFICAR]" in turno2_user)
    check("H6: el turno 2 también trae el mensaje del abogado del turno 1",
          "Resume las fuentes conectadas" in turno2_user)
    check("H6: el mensaje ACTUAL del turno 2 sigue presente y separado del historial",
          "Mensaje del abogado:\nAhora acórtalo" in turno2_user)

    # ── H6: la consulta de retrieval del intake queda LIMPIA (sin el historial) ──
    check("H6: intake sigue embebiendo SOLO el mensaje del turno (sin 'Conversación reciente')",
          bool(_embed_calls) and "Conversación reciente de este proyecto" not in _embed_calls[-1][0]
          and "Ahora acórtalo" in _embed_calls[-1][0])

    # ── no-regresión: el turno de ASUNTO sigue con HITL (awaiting_review) ────
    with client.stream("GET", f"/api/matters/{asunto_id}/stream",
                       params={"message": "¿Caducó la acción?"}, headers=auth_a) as s:
        body_a = "".join(s.iter_text())
    check("no-regresión: asunto sigue emitiendo 'awaiting_review'", "awaiting_review" in body_a)
    check("no-regresión: asunto marca pending_review=true", pending_review_of(asunto_id) is True)
    visible.append(body_a)

    # ── 4 · §G — sin jerga técnica en lo que ve el abogado ───────────────────
    blob = " ".join(visible).lower()
    leaked = [w for w in FORBIDDEN if w in blob]
    check(f"§G: respuestas sin jerga técnica (fugas: {leaked or 'ninguna'})", not leaked)

    return threads


def run_guard_checks() -> None:
    """Guardián de citas en PROYECTOS, sin DB ni red: cableado del grafo y respaldo.

    Comprueba dos cosas que el turno por SSE no puede distinguir por sí solo:
      · que la respuesta NO pueda llegar al final sin pasar por la verificación, y
      · de dónde sale el "respaldada" de un proyecto (que no tiene investigación
        propia): del material que el abogado suministró y Mia leyó en el turno.
    """
    from mia.agents import verification                                  # noqa: E402
    from mia.agents.graph import (PROJECT_VERIFICATION_NODE, MatterGraphBuilder,
                                  _project_material_sources)             # noqa: E402

    drawable = MatterGraphBuilder().build_project(checkpointer=None).get_graph()
    nodes = set(drawable.nodes)
    edges = {(e.source, e.target) for e in drawable.edges}
    check("guardián: el grafo de proyecto tiene el paso de verificación de citas",
          PROJECT_VERIFICATION_NODE in nodes)
    check("guardián: la respuesta del proyecto SIEMPRE pasa por la verificación",
          ("work", PROJECT_VERIFICATION_NODE) in edges
          and not any(s == "work" and t != PROJECT_VERIFICATION_NODE for s, t in edges))

    # ── de dónde sale el respaldo (un proyecto no tiene investigación propia) ──
    docs = [{"content": "El demandante invoca la Ley 1437 de 2011 y la Resolución 123 "
                        "de la entidad demandada.",
             "filename": "demanda.pdf", "folio_ancla": "3"}]
    notas = [{"content": "Criterio interno del despacho: ver el artículo 90 de la "
                         "Constitución Política.",
              "source_path": "criterios/responsabilidad.md"}]
    fuentes = _project_material_sources({"documents": docs, "knowledge": notas},
                                        verification.compile_patterns(None))
    refs = {f["referencia"] for f in fuentes}
    check("respaldo: la norma que aparece en el expediente del proyecto cuenta como fuente",
          "Ley 1437 de 2011" in refs)
    check("respaldo: las notas del despacho también cuentan",
          "artículo 90 de la Constitución Política" in refs)
    check("respaldo: la fuente dice de qué pieza salió",
          any(f["referencia"] == "Ley 1437 de 2011" and f["titulo"] == "demanda.pdf · folio 3"
              for f in fuentes))
    # Anti "falso respaldada": una referencia que termina en número suelto respaldaría por
    # prefijo a otra distinta ("Resolución 123" cubriría "Resolución 1234"). Se descarta:
    # marcar de más es inofensivo, dar por confirmado lo que no lo está no.
    check("respaldo: una referencia que termina en número suelto NO respalda a nadie",
          "Resolución 123" not in refs)

    # Bucle de realimentación (auditoría 2026-08-14): las notas que la PROPIA Mia
    # escribió en el vault ({vault}/Mia/) vuelven por el sync como "nota del despacho".
    # Jamás pueden respaldar una cita: una cita generada en el turno T se respaldaría
    # (y sellaría) a sí misma en T+n. Mutación: la misma nota bajo carpeta del abogado sí cuenta.
    nota_mia = [{"content": "Concepto consolidado: aplica la Ley 599 de 2000.",
                 "source_path": "Mia/conceptos/penal.md"}]
    fuentes_mia = _project_material_sources({"documents": [], "knowledge": nota_mia},
                                            verification.compile_patterns(None))
    check("respaldo: una nota escrita por Mia (Mia/) NO cuenta como fuente",
          not fuentes_mia)
    nota_abogado = [{"content": "Concepto consolidado: aplica la Ley 599 de 2000.",
                     "source_path": "criterios/penal.md"}]
    fuentes_abogado = _project_material_sources({"documents": [], "knowledge": nota_abogado},
                                                verification.compile_patterns(None))
    check("respaldo: la misma nota en carpeta del abogado SÍ cuenta (mutación)",
          any(f["referencia"] == "Ley 599 de 2000" for f in fuentes_abogado))

    texto = ("Aplica la Ley 1437 de 2011 y también la Ley 99 de 1993, además del "
             "artículo 90 de la Constitución Política.")
    anotado, informe = verification.annotate_draft(texto, sources=fuentes)
    check("respaldo: lo que consta en el material del proyecto NO se marca",
          "Ley 1437 de 2011 [VERIFICAR]" not in anotado
          and "Constitución Política [VERIFICAR]" not in anotado)
    check("respaldo: lo que Mia afirma sin estar en ese material SÍ se marca",
          "Ley 99 de 1993 [VERIFICAR]" in anotado)
    check("respaldo: el informe cuadra (2 confirmadas, 1 por confirmar)",
          informe["respaldadas"] == 2 and informe["anotadas"] == 1)

    # ── el texto se ENTREGA desde la verificación, nunca desde el paso anterior ──
    # No hay escritura palabra por palabra: la respuesta sale completa y una sola vez.
    # Si el evento se emitiera del paso anterior, el abogado leería las citas sin
    # revisar y todo lo de arriba sería decorativo.
    from mia.api.routes import delegation as _dele, stream as _st          # noqa: E402

    class _FakeGraph:
        async def astream(self, *_a, **_kw):
            yield {"work": {"reply": "CRUDO: la Ley 1437 de 2011 aplica."}}
            yield {PROJECT_VERIFICATION_NODE: {
                "reply": "MARCADO: la Ley 1437 de 2011 [VERIFICAR] aplica.",
                "metadata": {"verification": {"citas": 1, "anotadas": 1}}}}

    async def _nunca_desconectado() -> bool:
        return False

    async def _recoger() -> list[dict]:
        return [ev async for ev in _st._stream_project_events(
            _FakeGraph(), {}, {"configurable": {"thread_id": "t"}}, "t", "m",
            _nunca_desconectado)]

    eventos = asyncio.run(_recoger())
    replies = [e for e in eventos if e["event"] == "reply"]
    check("entrega: se emite UNA sola respuesta y es la verificada",
          len(replies) == 1 and "MARCADO" in replies[0]["data"]
          and "CRUDO" not in replies[0]["data"])
    check("entrega: mientras verifica, la pantalla lo dice en lenguaje del oficio",
          any(e["event"] == "thinking" and "verificando" in e["data"] for e in eventos))
    # El camino de REANUDAR tras la pausa del ayudante externo usa el MISMO traductor:
    # un solo arreglo cubre los dos caminos (no hay lógica duplicada que parchear).
    check("entrega: reanudar tras la pausa del ayudante pasa por el mismo traductor",
          _dele._stream_project_events is _st._stream_project_events)


def run_jurisdiction_checks() -> None:
    """El ORDENAMIENTO del despacho llega al prompt de un PROYECTO. Sin DB ni red.

    Un proyecto no tiene especialista de investigación, que era el único punto del turno
    donde el ordenamiento del despacho quedaba escrito. Resultado: un despacho con su
    ordenamiento perfectamente configurado se quedaba sin poder citar SU propia norma en
    proyectos (el prompt entraba en la rama restrictiva, que prohíbe nombrar articulado
    de cualquier país). Aquí se comprueba el arreglo por los dos lados: con ordenamiento
    configurado el proyecto puede citarlo, sin configurar sigue restringido, y si la
    configuración no se puede leer el turno no se cae.

    El código de ordenamiento de la prueba es inventado a propósito ('zz'): lo que se
    prueba es el cableado, no un país — Mia se adapta al despacho que la instala.
    """
    from mia.agent import prompt_builder as pb                              # noqa: E402
    from mia.agents import graph as _graph, research as _research           # noqa: E402
    from mia.agents import retrieval as _retr                               # noqa: E402
    from mia.jurisdiction import pack as _pack                              # noqa: E402

    DECLARADO = "zz"          # sin pack instalado: se respeta la declaración del despacho
    builder = _graph.MatterGraphBuilder()

    async def _sin_documentos(*_a, **_kw):
        return {"n_chunks": 0}

    async def _sin_notas(*_a, **_kw):
        return False

    async def _sin_delegacion(*_a, **_kw):
        return None

    original = (_retr.matter_chunk_stats, _retr.knowledge_exists,
                _research.resolve_jurisdictions_for)
    _retr.matter_chunk_stats = _sin_documentos
    _retr.knowledge_exists = _sin_notas
    builder._plan_delegation = _sin_delegacion

    estado = {"tenant_id": "t-juris", "matter_id": "m-juris", "metadata": {},
              "messages": [{"role": "user", "content": "¿Procede la acción?"}]}

    def _intake(st: dict) -> dict:
        return asyncio.run(builder.intake_node(st))

    def _prompt(salida: dict, nodo: str) -> str:
        return pb.build_graph_system({**estado, **salida}, nodo)

    try:
        # ── despacho CON su ordenamiento configurado ──────────────────────────
        async def _declarado(_tenant):
            return [DECLARADO]

        _research.resolve_jurisdictions_for = _declarado
        salida = _intake(dict(estado))
        check("ordenamiento: el primer paso del turno lo resuelve y lo deja en el estado",
              salida.get("jurisdictions") == [DECLARADO])
        prompt_proyecto = _prompt(salida, "work")
        check("ordenamiento: un PROYECTO de un despacho configurado ya NO cae en la rama "
              "restrictiva",
              pb.JURISDICTION_UNKNOWN not in prompt_proyecto)
        check("ordenamiento: lo que el despacho declaró llega al prompt del proyecto",
              DECLARADO.upper() in prompt_proyecto)
        # El flujo de ASUNTO tenía el mismo agujero en los especialistas que corren ANTES
        # de la investigación (hechos): hablaban restringidos aunque el despacho estuviera
        # configurado.
        check("ordenamiento: los especialistas del asunto previos a la investigación "
              "también lo reciben",
              all(pb.JURISDICTION_UNKNOWN not in _prompt(salida, n)
                  for n in ("facts", "analysis", "draft")))

        # ── despacho SIN configurar → sigue restringido (correcto por defecto) ──
        async def _sin_declarar(_tenant):
            return [_pack.GENERIC_CODE]

        _research.resolve_jurisdictions_for = _sin_declarar
        salida_sin = _intake(dict(estado))
        check("ordenamiento: sin configurar, el proyecto sigue sin poder nombrar "
              "articulado de ningún país",
              pb.JURISDICTION_UNKNOWN in _prompt(salida_sin, "work"))

        # ── la resolución falla (base caída, configuración ilegible) ───────────
        async def _revienta(_tenant):
            raise RuntimeError("configuración ilegible")

        _research.resolve_jurisdictions_for = _revienta
        salida_rota = _intake(dict(estado))
        check("ordenamiento: si la resolución falla el turno del abogado NO se cae",
              salida_rota.get("jurisdictions") == [_pack.GENERIC_CODE])
        check("ordenamiento: y falla hacia la rama restrictiva (jamás se adivina un país)",
              pb.JURISDICTION_UNKNOWN in _prompt(salida_rota, "work"))

        # ── una sola resolución por turno ─────────────────────────────────────
        consultas: list[str] = []

        async def _cuenta(tenant):
            consultas.append(tenant)
            return [DECLARADO]

        _research.resolve_jurisdictions_for = _cuenta
        _intake({**estado, "jurisdictions": [DECLARADO]})
        check("ordenamiento: si el estado ya lo trae no se vuelve a consultar la "
              "configuración del despacho",
              consultas == [])
    finally:
        (_retr.matter_chunk_stats, _retr.knowledge_exists,
         _research.resolve_jurisdictions_for) = original


def main() -> int:
    print("== Bloque A · Proyectos (kind='proyecto' + outputs + turno sin HITL) ==")
    if not os.getenv("PG_PASSWORD") or not config.JWT_SECRET:
        print("  [FAIL] PG_PASSWORD o JWT_SECRET vacío en .env")
        return 1

    init_projects_multifolder.apply()   # idempotente: columnas/CHECK de la migración 028

    import jwt
    from fastapi.testclient import TestClient
    from mia.api.main import app

    tid_a = make_tenant("A test proyectos")
    tid_b = make_tenant("B test proyectos")
    tok_a = jwt.encode({"tenant_id": tid_a}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    tok_b = jwt.encode({"tenant_id": tid_b}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    auth_a = {"Authorization": f"Bearer {tok_a}"}
    auth_b = {"Authorization": f"Bearer {tok_b}"}
    threads: list[str] = []
    run_guard_checks()          # sin DB ni red: cableado del guardián de citas + respaldo
    run_jurisdiction_checks()   # sin DB ni red: el ordenamiento del despacho llega al prompt
    try:
        with TestClient(app) as client:
            threads = run_checks(client, auth_a, tid_a, auth_b, tid_b)
    finally:
        cleanup([tid_a, tid_b], threads)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Bloque A · Proyectos OK.")
        return 0
    print("Bloque A · Proyectos FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
