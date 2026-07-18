"""
Mia · test_playbook_health.py — gate del Meta E (Mitad 1): salud de las guías del despacho.

Ejercita, contra la DB real (migración 044), el chequeo determinista de salud de una guía
(memory/playbook_health.py + api/routes/playbook_health.py), reusando SIN TOCARLO el escáner
de citas ya gateado (agents.verification.annotate_draft, CP9). Molde calcado de
execution/test_playbook_versions.py (TestClient + JWT, tenants propios con limpieza en
finally). Cubre:

  1. Migración 044 idempotente (aplicar dos veces no falla) y el CHECK de health_status
     rechaza un valor fuera de ('sano', 'revisar', 'sin_revisar').
  2. check_content_health: 'sano' sin citas, 'sano' con cita ya marcada [VERIFICAR],
     'revisar' con cita sin marcar ni respaldo.
  3. POST /api/playbooks/{id}/health persiste health_status/health_checked_at/health_report
     y lo devuelve EN LLANO ("N citas sin verificar de M").
  4. GET /api/playbooks/health/summary agrega los conteos de las guías activas.
  5. GET /api/playbooks ya trae health_status por guía (para el badge de la pantalla).
  6. FAIL-OPEN: si el escáner de citas explota, el chequeo persiste 'sin_revisar' con nota
     y NO rompe el flujo (nunca 500 hacia el abogado).
  7. Guía inexistente/ajena -> 404 en llano.
  8. RLS: el despacho B no ve ni puede revisar la salud de una guía del despacho A.
  9. §G: ninguna respuesta visible usa jerga técnica (embedding, chunk, tenant, pgvector,
     playbook, persona, canonical_prompt, RLS).

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_playbook_health.py
"""
from __future__ import annotations
import asyncio
import os
import sys
import uuid as _uuid
from pathlib import Path

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

import init_playbooks                    # noqa: E402  (migración 005)
import init_playbook_health              # noqa: E402  (migración 044)
from mia import config                    # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


PG = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
          dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""))

# §G del proyecto (jerga que NUNCA debe llegar a una respuesta visible del abogado).
FORBIDDEN = ("embedding", "chunk", "tenant", "pgvector", "playbook", "persona",
             "canonical_prompt", "rls")


def make_tenant(label: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id", (f"PBH_TEST {label}",)
        ).fetchone()[0])


def cleanup(tenants: list[str]) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id = ANY(%s)", (tenants,))


def seed_playbook(tid: str, *, title: str, content: str, applies_when: str = "w") -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO playbooks (tenant_id, title, summary, applies_when, content) "
            "VALUES (%s::uuid, %s, %s, %s, %s) RETURNING id",
            (tid, title, "s", applies_when, content)).fetchone()[0])


def get_health_row(playbook_id: str) -> tuple:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(
            "SELECT health_status, health_checked_at, health_report FROM playbooks "
            "WHERE id=%s::uuid", (playbook_id,)).fetchone()


def run_checks(client, auth_a, tid_a, auth_b, tid_b) -> None:
    visible: list[str] = []

    # ── 1 · migración idempotente + CHECK ────────────────────────────────────
    try:
        init_playbook_health.apply()
        init_playbook_health.apply()
        check("044 se puede aplicar dos veces sin error (idempotente)", True)
    except Exception:
        check("044 se puede aplicar dos veces sin error (idempotente)", False)

    pid_check = seed_playbook(tid_a, title="Semilla CHECK", content="contenido cualquiera")
    try:
        with psycopg.connect(autocommit=True, **PG) as c:
            c.execute("UPDATE playbooks SET health_status = %s WHERE id = %s::uuid",
                      ("inventado", pid_check))
        check("CHECK health_status rechaza un valor fuera de la lista", False)
    except psycopg.errors.CheckViolation:
        check("CHECK health_status rechaza un valor fuera de la lista", True)
    except psycopg.Error as e:
        check(f"CHECK health_status rechaza un valor fuera de la lista (error inesperado: {e})",
              False)

    # default recién creada = 'sin_revisar'
    row0 = get_health_row(pid_check)
    check("una guía recién creada nace con health_status='sin_revisar'", row0[0] == "sin_revisar")
    check("una guía recién creada nace con health_checked_at=NULL", row0[1] is None)

    # ── 2 · check_content_health (unidad, sin DB) ────────────────────────────
    from mia.memory.playbook_health import check_content_health, HEALTH_SANO, HEALTH_REVISAR

    r_sin_citas = check_content_health("Este procedimiento consiste en revisar el expediente "
                                        "y presentar el escrito dentro del término legal.")
    check("sin citas jurídicas -> 'sano'", r_sin_citas["status"] == HEALTH_SANO
          and r_sin_citas["citas"] == 0)

    r_marcada = check_content_health("Se aplica el artículo 164 del CPACA [VERIFICAR] "
                                      "para el cómputo del término.")
    check("cita YA marcada [VERIFICAR] -> 'sano' (0 anotadas)",
          r_marcada["status"] == HEALTH_SANO and r_marcada["citas"] == 1
          and r_marcada["anotadas"] == 0)

    r_sin_marcar = check_content_health("Se aplica el artículo 164 del CPACA "
                                         "para el cómputo del término.")
    check("cita SIN marcar ni respaldo -> 'revisar' (1 anotada)",
          r_sin_marcar["status"] == HEALTH_REVISAR and r_sin_marcar["anotadas"] == 1)
    check("el mensaje de 'revisar' está en llano (§G)",
          "sin verificar" in r_sin_marcar["mensaje"].lower())

    # ── 3 · POST /api/playbooks/{id}/health persiste y responde en llano ────
    pid_sano = seed_playbook(tid_a, title="Guía sana", content="Sin citas que verificar aquí.")
    r = client.post(f"/api/playbooks/{pid_sano}/health", headers=auth_a)
    check("POST .../health sobre guía sin citas -> 200 'sano'",
          r.status_code == 200 and r.json().get("health_status") == "sano")
    visible.append(r.text)
    row_sano = get_health_row(pid_sano)
    check("se persistió health_status='sano' en la fila", row_sano[0] == "sano")
    check("se persistió health_checked_at (no NULL)", row_sano[1] is not None)
    check("se persistió health_report con detalle serializable",
          isinstance(row_sano[2], dict) and "mensaje" in row_sano[2])

    pid_revisar = seed_playbook(
        tid_a, title="Guía por revisar",
        content="El plazo corre según el artículo 164 del CPACA y la Sentencia C-355 de 2006, "
                "ninguna marcada.")
    r = client.post(f"/api/playbooks/{pid_revisar}/health", headers=auth_a)
    check("POST .../health sobre guía con citas sin marcar -> 200 'revisar'",
          r.status_code == 200 and r.json().get("health_status") == "revisar")
    visible.append(r.text)
    check("el mensaje de la API está en llano (formato 'N ... de M')",
          "de 2" in r.json().get("mensaje", "") or "de 1" in r.json().get("mensaje", ""))

    # re-chequear la misma guía después de "arreglarla" -> pasa a sano
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("UPDATE playbooks SET content = %s WHERE id = %s::uuid",
                  ("Ya no quedan citas jurídicas en este texto.", pid_revisar))
    r = client.post(f"/api/playbooks/{pid_revisar}/health", headers=auth_a)
    check("re-chequear tras editar el contenido refleja el nuevo estado ('sano')",
          r.status_code == 200 and r.json().get("health_status") == "sano")
    visible.append(r.text)

    # ── 4 · GET /api/playbooks/health/summary ────────────────────────────────
    r = client.get("/api/playbooks/health/summary", headers=auth_a)
    check("GET .../health/summary -> 200 con las tres claves", r.status_code == 200
          and {"sano", "revisar", "sin_revisar"} <= set(r.json().keys()))
    visible.append(r.text)
    # pid_check sigue 'sin_revisar' (nunca se llamó su /health); pid_sano y pid_revisar 'sano'
    check("el resumen cuenta al menos una guía 'sin_revisar' (la que nunca se chequeó)",
          r.json()["sin_revisar"] >= 1)
    check("el resumen cuenta al menos dos guías 'sano'", r.json()["sano"] >= 2)

    # ── 5 · GET /api/playbooks ya trae health_status por fila ────────────────
    r = client.get("/api/playbooks", headers=auth_a)
    item = next((it for it in r.json() if it["id"] == pid_sano), None)
    check("GET /api/playbooks trae health_status por guía (para el badge)",
          item is not None and item.get("health_status") == "sano")
    visible.append(r.text)

    r = client.get(f"/api/playbooks/{pid_sano}", headers=auth_a)
    check("GET /api/playbooks/{id} (detalle) también trae health_status",
          r.json().get("health_status") == "sano")
    visible.append(r.text)

    # ── 6 · FAIL-OPEN: el escáner de citas explota -> 'sin_revisar', nunca 500 ──
    import mia.agents.verification as verification_mod
    _orig_annotate = verification_mod.annotate_draft

    def _boom(*_a, **_kw):
        raise RuntimeError("escáner forzado a fallar (prueba FAIL-OPEN)")

    pid_boom = seed_playbook(tid_a, title="Guía que hace explotar el escáner",
                             content="cualquier contenido")
    verification_mod.annotate_draft = _boom
    try:
        r = client.post(f"/api/playbooks/{pid_boom}/health", headers=auth_a)
        check("FAIL-OPEN: el chequeo NO devuelve 500 aunque el escáner explote",
              r.status_code == 200)
        check("FAIL-OPEN: el resultado queda 'sin_revisar'",
              r.json().get("health_status") == "sin_revisar")
        visible.append(r.text)
    finally:
        verification_mod.annotate_draft = _orig_annotate
    row_boom = get_health_row(pid_boom)
    check("FAIL-OPEN: se persistió 'sin_revisar' en la fila (no se quedó a medias)",
          row_boom[0] == "sin_revisar")

    # ── 7 · guía inexistente/ajena -> 404 en llano ───────────────────────────
    r = client.post(f"/api/playbooks/{_uuid.uuid4()}/health", headers=auth_a)
    check("POST .../health sobre id inexistente -> 404", r.status_code == 404)
    visible.append(r.text)

    r = client.post("/api/playbooks/no-es-un-uuid/health", headers=auth_a)
    check("POST .../health con id malformado -> 404, no 500", r.status_code in (404, 422))
    visible.append(r.text)

    # ── 8 · RLS: B no ve ni puede revisar una guía de A ──────────────────────
    r = client.post(f"/api/playbooks/{pid_sano}/health", headers=auth_b)
    check("RLS vía API: B intentando revisar una guía de A -> 404 (no la ve)",
          r.status_code == 404)
    visible.append(r.text)

    APP_PW = os.getenv("PG_APP_PASSWORD", "")
    PG_APP = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
                  dbname=os.getenv("PG_DB", "mia"), user="mia_app", password=APP_PW)
    with psycopg.connect(**PG_APP) as appconn:
        with appconn.transaction(force_rollback=True):
            appconn.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tid_b),))
            n_cross = appconn.execute(
                "SELECT count(*) FROM playbooks WHERE id = %s::uuid", (pid_sano,)
            ).fetchone()[0]
    check("RLS: tenant B ve 0 filas de la guía de A directamente en la tabla", n_cross == 0)

    r = client.get("/api/playbooks/health/summary", headers=auth_b)
    check("RLS: el resumen de salud de B no cuenta las guías de A",
          r.status_code == 200 and r.json().get("sano", 0) == 0
          and r.json().get("revisar", 0) == 0)

    # ── 9 · §G — sin jerga técnica ────────────────────────────────────────────
    blob = " ".join(visible).lower()
    leaked = [w for w in FORBIDDEN if w in blob]
    check(f"§G: respuestas sin jerga técnica (fugas: {leaked or 'ninguna'})", not leaked)


def main() -> int:
    print("== Meta E (Mitad 1) · salud de las guías del despacho ==")
    if not os.getenv("PG_PASSWORD") or not config.JWT_SECRET:
        print("  [FAIL] PG_PASSWORD o JWT_SECRET vacío en .env")
        return 1

    init_playbooks.apply()          # 005
    init_playbook_health.apply()    # 044

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
        print("Meta E (Mitad 1) OK.")
        return 0
    print("Meta E (Mitad 1) FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
