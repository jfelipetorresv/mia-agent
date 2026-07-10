"""
Mia · test_playbook_versions.py — gate del Bloque B (evolución de producto): B0 + B4.

Ejercita, contra la DB real (migración 029), el CRUD completo de playbooks + historial de
versiones y la gobernanza de propuestas aprendidas, con el LLM y los embeddings MOCKEADOS
(sin red). Molde calcado de execution/test_playbooks_protected.py / execution/test_ux.py
(TestClient + JWT, tenants propios con limpieza en finally). Cubre:

  1. CRUD completo por API: crear (origin), listar (?status=), detalle, editar (PUT),
     archivar/restaurar, historial de versiones + restaurar una versión.
  2. RLS/aislamiento de playbook_versions entre 2 tenants (0 filas cruzadas).
  3. `protected` sigue editable por PUT manual, pero `apply` automático sigue
     respetando 409 (no-regresión de H.6).
  4. PUT hace snapshot del estado ANTERIOR (no del nuevo) en playbook_versions.
  5. archive saca del índice (get_index) y restore lo devuelve.
  6. restore de versión hace snapshot del estado ACTUAL antes de restaurar.
  7. origin llega a metadata y a la lista (POST + import ya no dejan el playbook "huérfano"
     de procedencia).
  8. apply de propuesta con content/title editados por el abogado.
  9. source_matters correcto (derivado de trace_ids) y fail-open ante datos corruptos.
 10. anti-jerga §G en todos los textos visibles.

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_playbook_versions.py
"""
from __future__ import annotations
import asyncio
import os
import sys
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

import init_playbook_versions                           # noqa: E402  (migración 029)
import init_playbooks                                    # noqa: E402  (migración 005)
import init_playbooks_protected                         # noqa: E402  (migración 014)
import init_feedback                                     # noqa: E402  (migración 006)
from mia import config, embeddings                        # noqa: E402
from mia.agent import llm                                 # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── mocks (sin red) ──────────────────────────────────────────────────────────
def _fake_embed(texts):
    return [[0.2] + [0.0] * (config.EMBED_DIM - 1) for _ in texts]


def _fake_call_llm(messages, *, task=None, model=None, **kw):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="CONTENIDO_MOCK"))],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2))


embeddings.embed_texts = _fake_embed
llm.call_llm = _fake_call_llm

PG = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
          dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""))

FORBIDDEN = ("hitl", "langgraph", "pgvector", "tenant_id", "chunk", "embedding", "sync engine")


def make_tenant(label: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id", (f"PBV_TEST {label}",)
        ).fetchone()[0])


def cleanup(tenants: list[str]) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id = ANY(%s)", (tenants,))


def make_matter(tid: str, title: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO matters (tenant_id, title, kind) VALUES (%s::uuid, %s, 'asunto') "
            "RETURNING id", (tid, title)).fetchone()[0])


def seed_proposal(tid: str, *, ptype: str, target_playbook_id: str | None,
                  suggested_content: str, rationale: str = "prueba",
                  trace_ids: list[str] | None = None) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO feedback_proposals (tenant_id, proposal_type, target_playbook_id, "
            "suggested_content, rationale, trace_ids, status) "
            "VALUES (%s::uuid, %s, %s, %s, %s, %s, 'pending') RETURNING id",
            (tid, ptype, target_playbook_id, suggested_content, rationale, trace_ids)
        ).fetchone()[0])


def playbook_versions_count(tid: str, playbook_id: str) -> int:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(
            "SELECT count(*) FROM playbook_versions WHERE tenant_id=%s::uuid AND playbook_id=%s::uuid",
            (tid, playbook_id)).fetchone()[0]


def run_checks(client, auth_a, tid_a, auth_b, tid_b) -> None:
    visible: list[str] = []

    # ── 1 · crear (origin) ────────────────────────────────────────────────────
    r = client.post("/api/playbooks", headers=auth_a, json={
        "title": "Prescripción en póliza de cumplimiento", "summary": "cómputo de 5 años",
        "applies_when": "seguros de cumplimiento estatal", "content": "El término corre desde…",
        "origin": "entrevista"})
    check("crear playbook con origin -> 201", r.status_code == 201 and r.json().get("origin") == "entrevista")
    pid = r.json()["id"]
    visible.append(r.text)

    r = client.post("/api/playbooks", headers=auth_a, json={
        "title": "Origen inválido", "summary": "s", "applies_when": "w", "content": "c",
        "origin": "inventado"})
    check("crear playbook con origin inválido -> 422", r.status_code == 422)
    visible.append(r.text)

    r = client.post("/api/playbooks", headers=auth_a, json={
        "title": "Sin origin explícito", "summary": "s", "applies_when": "w", "content": "c"})
    check("crear sin origin -> default 'manual'", r.status_code == 201 and r.json().get("origin") == "manual")
    pid_manual = r.json()["id"]
    visible.append(r.text)

    # ── 1b · crear con título repetido -> 409 (nunca sobrescribe en silencio) ────
    r = client.post("/api/playbooks", headers=auth_a, json={
        "title": "Sin origin explícito", "summary": "otra cosa", "applies_when": "w2",
        "content": "contenido nuevo que NO debe pisar el original"})
    check("crear con título ya usado (activo) -> 409, no 201", r.status_code == 409)
    visible.append(r.text)
    r = client.get(f"/api/playbooks/{pid_manual}", headers=auth_a)
    check("el playbook original NO fue pisado por el intento de creación duplicada",
          r.json().get("content") == "c")

    r = client.post("/api/playbooks", headers=auth_a, json={
        "title": "Título para archivar y repetir", "summary": "s", "applies_when": "w",
        "content": "contenido original"})
    pid_to_archive = r.json()["id"]
    client.post(f"/api/playbooks/{pid_to_archive}/archive", headers=auth_a)
    r = client.post("/api/playbooks", headers=auth_a, json={
        "title": "Título para archivar y repetir", "summary": "s2", "applies_when": "w2",
        "content": "contenido que intenta colarse en la fila archivada"})
    check("crear con título de una guía ARCHIVADA -> también 409 (no aterriza oculta)",
          r.status_code == 409)
    visible.append(r.text)

    # ── 2 · listar (?status=) gana origin/protected/status ───────────────────
    r = client.get("/api/playbooks", headers=auth_a)
    item = next((it for it in r.json() if it["id"] == pid), None)
    check("GET /api/playbooks (default activos) trae origin/protected/status",
          item is not None and item.get("origin") == "entrevista"
          and item.get("protected") is False and item.get("status") == "active")
    visible.append(r.text)

    # ── 3 · detalle (con content) ────────────────────────────────────────────
    r = client.get(f"/api/playbooks/{pid}", headers=auth_a)
    check("GET /api/playbooks/{id} -> 200 con content", r.status_code == 200
          and r.json().get("content", "").startswith("El término corre"))
    visible.append(r.text)

    r = client.get("/api/playbooks/no-es-un-uuid", headers=auth_a)
    check("GET /api/playbooks/{uuid malformado} -> 404", r.status_code == 404)
    visible.append(r.text)

    import uuid as _uuid
    r = client.get(f"/api/playbooks/{_uuid.uuid4()}", headers=auth_a)
    check("GET /api/playbooks/{uuid inexistente} -> 404", r.status_code == 404)

    # ── 4 · PUT hace snapshot del estado ANTERIOR (no del nuevo) ─────────────
    check("versions antes del PUT = 0", playbook_versions_count(tid_a, pid) == 0)
    r = client.put(f"/api/playbooks/{pid}", headers=auth_a,
                   json={"summary": "cómputo de 5 años (actualizado)"})
    check("PUT /api/playbooks/{id} -> 200 con el cambio aplicado",
          r.status_code == 200 and r.json().get("summary") == "cómputo de 5 años (actualizado)")
    visible.append(r.text)
    check("PUT crea exactamente una versión", playbook_versions_count(tid_a, pid) == 1)

    r = client.get(f"/api/playbooks/{pid}/versions", headers=auth_a)
    versions = r.json().get("versions", [])
    check("GET /versions -> 1 versión con el summary VIEJO (snapshot anterior)",
          len(versions) == 1)
    visible.append(r.text)
    ver_id = versions[0]["id"]
    check("la versión registra changed_by='abogado'", versions[0]["changed_by"] == "abogado")

    # snapshot content check: la versión debe traer el summary ANTERIOR al cambio
    with psycopg.connect(autocommit=True, **PG) as c:
        snap_summary = c.execute(
            "SELECT summary FROM playbook_versions WHERE id=%s::uuid", (ver_id,)).fetchone()[0]
    check("la versión guardó el summary ANTERIOR ('cómputo de 5 años', sin '(actualizado)')",
          snap_summary == "cómputo de 5 años")

    # segundo PUT -> segunda versión
    r = client.put(f"/api/playbooks/{pid}", headers=auth_a, json={"content": "Contenido V3"})
    check("segundo PUT -> 200", r.status_code == 200 and r.json().get("content") == "Contenido V3")
    check("segundo PUT crea una SEGUNDA versión", playbook_versions_count(tid_a, pid) == 2)

    r = client.put(f"/api/playbooks/{_uuid.uuid4()}", headers=auth_a, json={"content": "x"})
    check("PUT sobre un id inexistente -> 404", r.status_code == 404)

    # título editado de más de 200 chars -> se recorta, nunca 500 (StringDataRightTruncation)
    titulo_largo = "T" * 250
    r = client.put(f"/api/playbooks/{pid}", headers=auth_a, json={"title": titulo_largo})
    check("PUT con título > 200 chars -> 200 (recortado), no 500",
          r.status_code == 200 and len(r.json().get("title", "")) == 200)
    visible.append(r.text)

    # ── 5 · archivar saca del índice (get_index) / restore lo devuelve ───────
    r = client.post(f"/api/playbooks/{pid}/archive", headers=auth_a)
    check("POST /archive -> 200", r.status_code == 200)
    visible.append(r.text)

    r = client.get("/api/playbooks", headers=auth_a)
    ids_activos = {it["id"] for it in r.json()}
    check("archivado NO aparece en la lista por defecto (?status=activos)", pid not in ids_activos)

    r = client.get("/api/playbooks", headers=auth_a, params={"status": "todos"})
    ids_todos = {it["id"] for it in r.json()}
    check("archivado SÍ aparece con ?status=todos", pid in ids_todos)
    row_todos = next(it for it in r.json() if it["id"] == pid)
    check("archivado muestra status='archived'", row_todos["status"] == "archived")

    def _index_has(tenant: str, title: str) -> bool:
        # Mismo filtro EXACTO que PlaybookManager.get_index() (status='active') — en
        # sync psycopg (superusuario) para no mezclar el pool async con el loop de
        # TestClient (rompe: "future belongs to a different loop").
        with psycopg.connect(autocommit=True, **PG) as c:
            n = c.execute(
                "SELECT count(*) FROM playbooks WHERE tenant_id=%s::uuid AND status='active' "
                "AND title=%s", (tenant, title)).fetchone()[0]
        return n > 0

    check("get_index() YA NO incluye el playbook archivado (status != 'active')",
          not _index_has(tid_a, "Prescripción en póliza de cumplimiento"))

    r = client.post(f"/api/playbooks/{pid}/restore", headers=auth_a)
    check("POST /restore -> 200", r.status_code == 200)
    visible.append(r.text)
    r = client.get("/api/playbooks", headers=auth_a)
    check("restaurado vuelve a aparecer en la lista por defecto",
          pid in {it["id"] for it in r.json()})

    r = client.post(f"/api/playbooks/{_uuid.uuid4()}/archive", headers=auth_a)
    check("archive sobre id inexistente -> 404", r.status_code == 404)

    # ── 6 · restaurar una VERSIÓN hace snapshot del estado ACTUAL antes ──────
    versions_before = playbook_versions_count(tid_a, pid)  # 2
    r = client.post(f"/api/playbooks/{pid}/versions/{ver_id}/restore", headers=auth_a)
    check("POST /versions/{id}/restore -> 200", r.status_code == 200)
    check("restore de versión trae de vuelta el summary de esa versión",
          r.json().get("summary") == "cómputo de 5 años")
    visible.append(r.text)
    check("restore de versión crea una NUEVA versión (snapshot del estado previo al restore)",
          playbook_versions_count(tid_a, pid) == versions_before + 1)

    r = client.get(f"/api/playbooks/{pid}/versions", headers=auth_a)
    latest = max(r.json()["versions"], key=lambda v: v["created_at"])
    check("la versión más reciente tras el restore quedó como 'abogado' (acción manual)",
          latest["changed_by"] == "abogado")

    # versión de OTRO playbook -> 404 (no cruza playbooks)
    r = client.post(f"/api/playbooks/{pid_manual}/versions/{ver_id}/restore", headers=auth_a)
    check("restore de una versión que NO pertenece a ese playbook -> 404", r.status_code == 404)

    # ── 6b · restaurar una versión cuyo título choca con OTRA guía -> 409 en llano
    # (nunca un 500 técnico) — reproduce exactamente el escenario del hallazgo: C se
    # renombra (queda un snapshot con el título viejo), otra guía D toma ese título
    # libre, y restaurar en C la versión con el título viejo debe rechazarse con 409.
    r = client.post("/api/playbooks", headers=auth_a, json={
        "title": "T-conflicto-restore-A", "summary": "s", "applies_when": "w", "content": "c"})
    pid_c = r.json()["id"]
    r = client.put(f"/api/playbooks/{pid_c}", headers=auth_a,
                   json={"title": "T-conflicto-restore-A-renombrada"})
    check("renombrar C -> 200 (deja un snapshot con el título viejo)", r.status_code == 200)
    r = client.get(f"/api/playbooks/{pid_c}/versions", headers=auth_a)
    ver_titulo_viejo = next(v for v in r.json()["versions"]
                            if v["title"] == "T-conflicto-restore-A")
    r = client.post("/api/playbooks", headers=auth_a, json={
        "title": "T-conflicto-restore-A", "summary": "s", "applies_when": "w", "content": "c"})
    check("D toma el título que C dejó libre -> 201", r.status_code == 201)
    r = client.post(f"/api/playbooks/{pid_c}/versions/{ver_titulo_viejo['id']}/restore",
                    headers=auth_a)
    check("restaurar en C la versión con el título que ahora tiene D -> 409 en llano (no 500)",
          r.status_code == 409 and "ya existe" in r.json().get("detail", "").lower())
    visible.append(r.text)

    # ── 7 · protected editable por PUT manual, pero apply automático 409 ────
    def _seed_protected() -> str:
        # INSERT directo (sync, superusuario) — evita mezclar el pool async con el
        # loop de TestClient; embedding queda NULL (no lo necesita este gate).
        with psycopg.connect(autocommit=True, **PG) as c:
            return str(c.execute(
                "INSERT INTO playbooks (tenant_id, title, summary, applies_when, content, protected) "
                "VALUES (%s::uuid, %s, %s, %s, %s, true) RETURNING id",
                (tid_a, "Semilla protegida", "s0", "w0", "contenido semilla")).fetchone()[0])

    pid_prot = _seed_protected()

    r = client.put(f"/api/playbooks/{pid_prot}", headers=auth_a,
                   json={"content": "Editado a mano por el abogado"})
    check("PUT manual SÍ edita un playbook protegido", r.status_code == 200
          and r.json().get("content") == "Editado a mano por el abogado")
    visible.append(r.text)

    prop_id_prot = seed_proposal(tid_a, ptype="improve_playbook", target_playbook_id=pid_prot,
                                 suggested_content="contenido que NO debe aplicarse")
    r = client.post(f"/api/proposals/{prop_id_prot}/apply", headers=auth_a)
    check("apply automático sobre playbook protegido sigue devolviendo 409 (no-regresión H.6)",
          r.status_code == 409)
    visible.append(r.text)
    check("el contenido protegido no cambió por el intento de apply",
          playbook_versions_count(tid_a, pid_prot) == 1)  # solo la versión del PUT manual

    # ── 8 · apply de propuesta con content/title editados ────────────────────
    prop_id_improve = seed_proposal(tid_a, ptype="improve_playbook", target_playbook_id=pid_manual,
                                    suggested_content="sugerencia original de Mia")
    r = client.post(f"/api/proposals/{prop_id_improve}/apply", headers=auth_a,
                    json={"content": "Contenido corregido por el abogado antes de aplicar"})
    check("apply improve_playbook con content editado -> 200 applied",
          r.status_code == 200 and r.json().get("status") == "applied")
    visible.append(r.text)
    r = client.get(f"/api/playbooks/{pid_manual}", headers=auth_a)
    check("el playbook quedó con el CONTENIDO EDITADO (no el original de Mia)",
          r.json().get("content") == "Contenido corregido por el abogado antes de aplicar")
    check("apply improve_playbook hizo snapshot a versions (changed_by='mia')",
          playbook_versions_count(tid_a, pid_manual) >= 1)
    with psycopg.connect(autocommit=True, **PG) as c:
        last_changed_by = c.execute(
            "SELECT changed_by FROM playbook_versions WHERE tenant_id=%s::uuid AND playbook_id=%s::uuid "
            "ORDER BY created_at DESC LIMIT 1", (tid_a, pid_manual)).fetchone()[0]
    check("la versión del apply automático quedó marcada 'mia'", last_changed_by == "mia")

    # apply improve_playbook con TÍTULO editado también -> se honra (antes se descartaba
    # en silencio: el content editado surtía efecto pero el title no).
    prop_id_improve_title = seed_proposal(tid_a, ptype="improve_playbook",
                                          target_playbook_id=pid_manual,
                                          suggested_content="otra sugerencia de Mia")
    r = client.post(f"/api/proposals/{prop_id_improve_title}/apply", headers=auth_a,
                    json={"content": "Contenido v2", "title": "Sin origin explícito (renombrada)"})
    check("apply improve_playbook con title editado -> 200 applied", r.status_code == 200)
    r = client.get(f"/api/playbooks/{pid_manual}", headers=auth_a)
    check("apply improve_playbook con title editado SÍ renombra la guía (antes se ignoraba)",
          r.json().get("title") == "Sin origin explícito (renombrada)")
    visible.append(r.text)

    # apply con proposal_id malformado (no-UUID) -> 404 en llano, nunca 500
    r = client.post("/api/proposals/no-es-un-uuid/apply", headers=auth_a)
    check("apply con proposal_id malformado -> 404 en llano, no 500", r.status_code == 404)
    visible.append(r.text)

    prop_id_new = seed_proposal(tid_a, ptype="new_playbook", target_playbook_id=None,
                                suggested_content="Alegar la excepción de contrato no cumplido "
                                                   "cuando el asegurado incumplió primero.")
    r = client.post(f"/api/proposals/{prop_id_new}/apply", headers=auth_a,
                    json={"title": "Excepción de contrato no cumplido"})
    check("apply new_playbook con title editado -> 200 applied", r.status_code == 200)
    r = client.get("/api/playbooks", headers=auth_a)
    check("el nuevo playbook usa el TÍTULO EDITADO (nunca 'Sugerencia {id}')",
          any(it["title"] == "Excepción de contrato no cumplido" for it in r.json()))
    check("NINGÚN playbook se llama 'Sugerencia ...' tras aplicar",
          not any(it["title"].startswith("Sugerencia ") for it in r.json()))
    visible.append(r.text)
    with psycopg.connect(autocommit=True, **PG) as c:
        emb_new = c.execute(
            "SELECT embedding FROM playbooks WHERE tenant_id=%s::uuid "
            "AND title='Excepción de contrato no cumplido'", (tid_a,)).fetchone()[0]
    check("el playbook 'aprendido' (new_playbook) nace CON embedding, no NULL",
          emb_new is not None)

    prop_id_new2 = seed_proposal(tid_a, ptype="new_playbook", target_playbook_id=None,
                                 suggested_content="Recurso de reposición contra el auto que "
                                                    "rechaza la excepción de caducidad procesal.")
    r = client.post(f"/api/proposals/{prop_id_new2}/apply", headers=auth_a)  # sin body
    check("apply new_playbook SIN título editado -> igual 200 (título derivado)",
          r.status_code == 200)
    r = client.get("/api/playbooks", headers=auth_a)
    check("el título derivado NO es 'Sugerencia {id}' (deriva de la sugerencia)",
          not any(it["title"].startswith("Sugerencia ") for it in r.json()))
    visible.append(r.text)

    # ── 9 · source_matters (correcto + fail-open) ────────────────────────────
    m1 = make_matter(tid_a, "Reclamación póliza todo riesgo — Constructora ABC")
    m2 = make_matter(tid_a, "Arbitraje EPM vs. Aseguradora — cumplimiento")
    ts = "2026-07-09T10:00:00+00:00"
    trace_ids = [f"{tid_a}:{m1}:{ts}", f"{tid_a}:{m2}:{ts}"]
    prop_sm = seed_proposal(tid_a, ptype="new_playbook", target_playbook_id=None,
                            suggested_content="Patrón detectado en varios asuntos.",
                            trace_ids=trace_ids)
    r = client.get("/api/proposals", headers=auth_a)
    row = next(p for p in r.json() if p["id"] == prop_sm)
    check("source_matters trae los títulos de los asuntos de origen",
          set(row["source_matters"]) == {
              "Reclamación póliza todo riesgo — Constructora ABC",
              "Arbitraje EPM vs. Aseguradora — cumplimiento"})
    visible.append(r.text)

    # fail-open: trace_ids corruptos / matter inexistente -> [] sin 500
    bad_trace = ["no-tiene-suficientes-partes", f"{tid_a}:no-es-uuid:{ts}",
                f"{tid_a}:{'00000000-0000-0000-0000-000000000000'}:{ts}"]
    prop_bad = seed_proposal(tid_a, ptype="flag_gap", target_playbook_id=None,
                             suggested_content="Brecha detectada.", trace_ids=bad_trace)
    r = client.get("/api/proposals", headers=auth_a)
    check("GET /api/proposals sigue en 200 con trace_ids corruptos (fail-open)",
          r.status_code == 200)
    row_bad = next(p for p in r.json() if p["id"] == prop_bad)
    check("source_matters de trace_ids corruptos -> lista vacía (fail-open, sin 500)",
          row_bad["source_matters"] == [])
    visible.append(r.text)

    prop_none = seed_proposal(tid_a, ptype="flag_gap", target_playbook_id=None,
                              suggested_content="Sin trazas.", trace_ids=None)
    r = client.get("/api/proposals", headers=auth_a)
    row_none = next(p for p in r.json() if p["id"] == prop_none)
    check("source_matters con trace_ids=NULL -> lista vacía", row_none["source_matters"] == [])

    # ── 10 · RLS: playbook_versions de A invisible para B ────────────────────
    # Patrón EXACTO de test_rls.py: rol `mia_app` (NOSUPERUSER/NOBYPASSRLS) + GUC
    # app.tenant_id, en sync psycopg (nunca mezclar el pool async con el loop de
    # TestClient — rompe con "future belongs to a different loop").
    APP_PW = os.getenv("PG_APP_PASSWORD", "")
    PG_APP = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
                  dbname=os.getenv("PG_DB", "mia"), user="mia_app", password=APP_PW)
    with psycopg.connect(**PG_APP) as appconn:
        with appconn.transaction(force_rollback=True):
            appconn.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tid_b),))
            n_cross = appconn.execute(
                "SELECT count(*) FROM playbook_versions WHERE playbook_id = %s::uuid",
                (pid,)).fetchone()[0]
    check("RLS: tenant B ve 0 filas de playbook_versions del playbook de A", n_cross == 0)

    r = client.get(f"/api/playbooks/{pid}/versions", headers=auth_b)
    check("RLS vía API: B consultando versions de un playbook de A -> lista vacía o 404",
          r.status_code == 404 or r.json().get("versions") == [])

    # ── 11 · §G — sin jerga técnica ───────────────────────────────────────────
    blob = " ".join(visible).lower()
    leaked = [w for w in FORBIDDEN if w in blob]
    check(f"§G: respuestas sin jerga técnica (fugas: {leaked or 'ninguna'})", not leaked)


def main() -> int:
    print("== Bloque B · B0+B4 · playbooks (CRUD+versiones) y gobernanza de propuestas ==")
    if not os.getenv("PG_PASSWORD") or not config.JWT_SECRET:
        print("  [FAIL] PG_PASSWORD o JWT_SECRET vacío en .env")
        return 1

    init_playbooks.apply()             # 005
    init_playbooks_protected.apply()   # 014
    init_feedback.apply()              # 006
    init_playbook_versions.apply()     # 029

    import jwt
    from fastapi.testclient import TestClient
    from mia.api.main import app

    tid_a = make_tenant("A")
    tid_b = make_tenant("B")
    tok_a = jwt.encode({"tenant_id": tid_a}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    tok_b = jwt.encode({"tenant_id": tid_b}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    auth_a = {"Authorization": f"Bearer {tok_a}"}
    auth_b = {"Authorization": f"Bearer {tok_b}"}
    try:
        with TestClient(app) as client:
            run_checks(client, auth_a, tid_a, auth_b, tid_b)
    finally:
        cleanup([tid_a, tid_b])

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Bloque B · B0+B4 OK.")
        return 0
    print("Bloque B · B0+B4 FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
