"""
Mia · test_profile_full.py — gate del Bloque C · C2: Perfil del despacho editable y unificado.

Hasta C2 había DOS fuentes desconectadas: las respuestas de la entrevista (archivo por
tenant, fuente canónica del SOUL.md) y `firm_profiles` (editada por el PUT /api/profile
legado, solo llegaba al mensaje del nodo draft). Este gate ejercita GET/PUT
/api/profile/full, `derive_firm_profile` y la no-regresión del PUT legado, contra la DB
real (migraciones 004 + 007), con el LLM y los embeddings sin tocar (esta pantalla no los
usa) — molde calcado de execution/test_playbook_versions.py / execution/test_ux.py.

  1. GET sin onboarding -> 200, responses={}, completed=False (nunca 500).
  2. PUT con responses -> SOUL.md + responses.json en disco; summary en llano.
  3. Merge: PUT que manda solo una clave NO borra las demás.
  4. derive_firm_profile: determinista, mapeos correctos, omite vacíos, CSV -> lista.
  5. Tras PUT con extras, firm_profiles refleja los derivados + extras.
  6. Fallo simulado del upsert -> 200 con warning, y el SOUL.md SÍ quedó escrito.
  7. jurisdictions persistidas en tenant_settings.config.
  8. PUT legado /api/profile sigue funcionando (no regresión).
  9. Aislamiento: tenant B no ve responses de A.
 10. §G anti-jerga en los textos visibles (summary, warnings, errores).

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_profile_full.py
"""
from __future__ import annotations
import asyncio
import os
import sys
import tempfile
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

import init_knowledge_stores                          # noqa: E402  (migración 004 · tenant_settings)
import init_profiles                                   # noqa: E402  (migración 007 · firm_profiles)
from mia import config                                 # noqa: E402
from mia.memory.profile_manager import ProfileManager  # noqa: E402
from mia.onboarding.soul_interview import (            # noqa: E402
    derive_firm_profile, load_responses, responses_path, soul_path,
)

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


PG = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
          dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""))

FORBIDDEN = ("hitl", "langgraph", "pgvector", "tenant_id", "chunk", "embedding", "playbook")


def make_tenant(label: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id", (f"PROFILE_FULL_TEST {label}",)
        ).fetchone()[0])


def cleanup(tenants: list[str]) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id = ANY(%s)", (tenants,))


def firm_profile_row(tid: str) -> dict | None:
    with psycopg.connect(autocommit=True, row_factory=psycopg.rows.dict_row, **PG) as c:
        return c.execute(
            "SELECT name, lawyer_name, tp_number, jurisdiction, practice_areas, preferred_sources, "
            "tools FROM firm_profiles WHERE tenant_id=%s::uuid", (tid,)
        ).fetchone()


def run_derive_checks() -> None:
    # ── 4 · derive_firm_profile: pura, determinista, mapeos, omite vacíos, CSV -> lista ──
    responses = {
        "identity.name": {"firm": "Fajardo & Asociados", "lawyer": "María Fajardo"},
        "jurisdiction.base": ["Colombia", "Panamá"],
        "jurisdiction.practice_areas": "Civil, Comercial , Laboral",
        "memory.tools_that_survived": ["Correo", "Calendario"],
    }
    d1 = derive_firm_profile(responses)
    d2 = derive_firm_profile(responses)
    check("derive_firm_profile es determinista (2 llamadas -> mismo dict)", d1 == d2)
    check("derive_firm_profile mapea name/lawyer_name de identity.name",
          d1.get("name") == "Fajardo & Asociados" and d1.get("lawyer_name") == "María Fajardo")
    check("derive_firm_profile mapea jurisdiction de jurisdiction.base",
          d1.get("jurisdiction") == "Colombia, Panamá")
    check("derive_firm_profile: practice_areas string con comas -> lista recortada",
          d1.get("practice_areas") == ["Civil", "Comercial", "Laboral"])
    check("derive_firm_profile mapea tools de memory.tools_that_survived",
          d1.get("tools") == ["Correo", "Calendario"])
    check("derive_firm_profile con lista de practice_areas -> tal cual (recortada)",
          derive_firm_profile({"jurisdiction.practice_areas": [" Civil ", "", "Seguros"]})
          .get("practice_areas") == ["Civil", "Seguros"])
    check("derive_firm_profile({}) -> {} (nada que derivar, sin pisar con vacíos)",
          derive_firm_profile({}) == {})
    check("derive_firm_profile NO deriva tp_number/preferred_sources/hard_nos/rhythm (extras/legacy)",
          not any(k in d1 for k in ("tp_number", "preferred_sources", "voice_adjectives",
                                    "banned_words", "hard_nos", "rhythm")))


def run_checks(client, auth_a, tid_a, auth_b, tid_b) -> None:
    visible: list[str] = []

    # ── 1 · GET sin onboarding ────────────────────────────────────────────────
    r = client.get("/api/profile/full", headers=auth_a)
    check("GET /api/profile/full sin onboarding -> 200, sin 500",
          r.status_code == 200)
    body = r.json()
    check("GET sin onboarding -> responses={} y completed=False",
          body.get("responses") == {} and body.get("completed") is False)
    visible.append(r.text)

    r = client.get("/api/profile/full", headers={"Authorization": "Bearer no-es-un-token"})
    check("GET /api/profile/full sin sesión válida -> 401", r.status_code == 401)

    # ── 2 · PUT con responses -> SOUL.md + responses.json en disco ───────────
    r = client.put("/api/profile/full", headers=auth_a, json={
        "responses": {
            "identity.name": {"firm": "Fajardo & Asociados", "lawyer": "María Fajardo"},
            "identity.location": {"country": "Colombia", "city": "Bogotá"},
        }
    })
    check("PUT /api/profile/full con responses -> 200 ok", r.status_code == 200 and r.json().get("ok") is True)
    check("PUT devuelve summary en lenguaje llano ('Así entendí a tu despacho')",
          "Así entendí a tu despacho" in r.json().get("summary", ""))
    visible.append(r.text)

    soul_text = soul_path(tid_a).read_text(encoding="utf-8")
    check("SOUL.md quedó escrito en disco con el nombre del despacho",
          soul_path(tid_a).exists() and "Fajardo & Asociados" in soul_text)
    saved = load_responses(tid_a)
    check("responses.json quedó escrito en disco con lo mandado",
          saved.get("identity.name", {}).get("firm") == "Fajardo & Asociados")
    check("responses_path(tenant) apunta al archivo real que se acaba de leer",
          responses_path(tid_a).exists())

    # ── 3 · Merge: PUT que manda solo una clave NO borra las demás ───────────
    r = client.put("/api/profile/full", headers=auth_a, json={
        "responses": {"jurisdiction.practice_areas": ["Civil", "Seguros"]}
    })
    check("segundo PUT (solo practice_areas) -> 200", r.status_code == 200)
    visible.append(r.text)
    saved2 = load_responses(tid_a)
    check("el merge NO borró identity.name puesto en el PUT anterior",
          saved2.get("identity.name", {}).get("firm") == "Fajardo & Asociados")
    check("el merge NO borró identity.location puesto en el PUT anterior",
          saved2.get("identity.location", {}).get("city") == "Bogotá")
    check("el merge SÍ aplicó la clave nueva (practice_areas)",
          saved2.get("jurisdiction.practice_areas") == ["Civil", "Seguros"])

    # ── 5 · Tras PUT con extras, firm_profiles refleja derivados + extras ────
    r = client.put("/api/profile/full", headers=auth_a, json={
        "responses": {"memory.tools_that_survived": ["Correo", "Calendario"]},
        "extras": {"tp_number": "123.456", "preferred_sources": ["Superintendencia Financiera"]},
    })
    check("PUT con extras -> 200", r.status_code == 200)
    visible.append(r.text)
    row = firm_profile_row(tid_a)
    check("firm_profiles existe tras el PUT (best-effort corrió)", row is not None)
    check("firm_profiles.name refleja el derivado de identity.name",
          row is not None and row.get("name") == "Fajardo & Asociados")
    check("firm_profiles.tp_number refleja el extra del body",
          row is not None and row.get("tp_number") == "123.456")
    check("firm_profiles.preferred_sources refleja el extra del body",
          row is not None and row.get("preferred_sources") == ["Superintendencia Financiera"])
    check("firm_profiles.practice_areas refleja el derivado más reciente",
          row is not None and set(row.get("practice_areas") or []) == {"Civil", "Seguros"})
    check("firm_profiles.tools refleja el derivado de memory.tools_that_survived",
          row is not None and set(row.get("tools") or []) == {"Correo", "Calendario"})

    # una llamada posterior que NO manda extras no debe borrar los extras ya guardados
    r = client.put("/api/profile/full", headers=auth_a, json={
        "responses": {"jurisdiction.client_type": ["Aseguradoras"]}
    })
    check("PUT sin extras -> 200", r.status_code == 200)
    row2 = firm_profile_row(tid_a)
    check("un PUT posterior sin `extras` NO borra el tp_number ya guardado",
          row2 is not None and row2.get("tp_number") == "123.456")
    check("un PUT posterior sin `extras` NO borra preferred_sources ya guardado",
          row2 is not None and row2.get("preferred_sources") == ["Superintendencia Financiera"])

    # ── 6 · Fallo simulado del upsert -> 200 con warning, SOUL.md sí se escribió ──
    original_upsert = ProfileManager.upsert_firm_profile

    async def _raise_upsert(self, tenant_id, data):
        raise RuntimeError("fallo simulado de la parte auxiliar")

    ProfileManager.upsert_firm_profile = _raise_upsert
    try:
        r = client.put("/api/profile/full", headers=auth_a, json={
            "responses": {"identity.voice": "Técnico y directo"}
        })
    finally:
        ProfileManager.upsert_firm_profile = original_upsert
    check("PUT con el upsert auxiliar roto -> sigue 200 (no rompe la respuesta)",
          r.status_code == 200)
    check("PUT con el upsert auxiliar roto -> trae `warning`", bool(r.json().get("warning")))
    visible.append(r.text)
    soul_after_failure = soul_path(tid_a).read_text(encoding="utf-8")
    check("el SOUL.md SÍ quedó escrito aunque la parte auxiliar falló",
          "Técnico y directo" in soul_after_failure)
    check("responses.json también quedó escrito aunque la parte auxiliar falló",
          load_responses(tid_a).get("identity.voice") == "Técnico y directo")

    # ── validación de forma ───────────────────────────────────────────────────
    r = client.put("/api/profile/full", headers=auth_a, json={"responses": "no-es-un-dict"})
    check("PUT con responses que no es dict -> 422 en llano, no 500", r.status_code == 422)
    visible.append(r.text)

    r = client.put("/api/profile/full", headers=auth_a, json={
        "responses": {"identity.voice": "x" * 250_000}
    })
    check("PUT con responses gigante (>200KB) -> 422 en llano, no 500", r.status_code == 422)
    visible.append(r.text)

    # ── 7 · jurisdictions persistidas en tenant_settings.config ──────────────
    r = client.put("/api/profile/full", headers=auth_a, json={"jurisdictions": ["co", "pa"]})
    check("PUT con jurisdictions -> 200", r.status_code == 200)
    visible.append(r.text)
    with psycopg.connect(autocommit=True, **PG) as c:
        cfg = c.execute(
            "SELECT config->'jurisdictions' FROM tenant_settings WHERE tenant_id=%s::uuid", (tid_a,)
        ).fetchone()[0]
    check("tenant_settings.config.jurisdictions quedó con los códigos mandados",
          cfg == ["co", "pa"])
    r = client.get("/api/profile/full", headers=auth_a)
    check("GET /api/profile/full refleja las jurisdicciones guardadas",
          set(r.json().get("jurisdictions", [])) == {"co", "pa"})
    visible.append(r.text)

    # ── 8 · PUT legado /api/profile sigue funcionando (no regresión) ─────────
    r = client.get("/api/profile", headers=auth_a)
    check("GET /api/profile (legado) -> 200", r.status_code == 200)
    r = client.put("/api/profile", headers=auth_a, json={"name": "Lexia Abogados", "jurisdiction": "colombia"})
    check("PUT /api/profile (legado) -> 200 sigue funcionando", r.status_code == 200
          and r.json().get("name") == "Lexia Abogados")
    visible.append(r.text)

    # ── 8b · Un PUT /full posterior NO anula lo sembrado por el flujo legado ─
    # (hallazgo capa 2 sesión 41). Escenario real: un despacho pobló firm_profiles con
    # la pantalla vieja (PUT legado) pero su entrevista (responses) NO trae esos campos
    # — el estado "dos fuentes desconectadas" que motiva C2. Se usa el tenant B, que en
    # este punto no tiene ninguna respuesta de entrevista: lo derivado es {} y NO debe
    # anular con NULL lo que el flujo legado ya guardó. (En el tenant A, cuyas responses
    # SÍ traen nombre/áreas, lo derivado de la fuente canónica manda — por diseño.)
    r = client.put("/api/profile", headers=auth_b,
                   json={"name": "Despacho Legado B", "practice_areas": ["Seguros", "Civil"],
                         "tools": ["Correo"]})
    check("PUT legado siembra name/practice_areas/tools (tenant sin entrevista)",
          r.status_code == 200)
    r = client.put("/api/profile/full", headers=auth_b,
                   json={"extras": {"tp_number": "TP-999"}})
    check("PUT /full solo-extras -> 200", r.status_code == 200)
    with psycopg.connect(**PG) as conn:
        row = conn.execute(
            "SELECT name, practice_areas, tools, tp_number FROM firm_profiles WHERE tenant_id=%s::uuid",
            (tid_b,),
        ).fetchone()
    check("PUT /full NO anula name sembrado por el flujo legado", row is not None and row[0] == "Despacho Legado B")
    check("PUT /full NO anula practice_areas/tools del flujo legado",
          row is not None and row[1] == ["Seguros", "Civil"] and row[2] == ["Correo"])
    check("PUT /full sí aplica los extras enviados", row is not None and row[3] == "TP-999")

    # ── 9 · Aislamiento: tenant B no ve responses de A ───────────────────────
    r = client.get("/api/profile/full", headers=auth_b)
    check("GET /api/profile/full de B -> responses vacías (no ve las de A)",
          r.status_code == 200 and r.json().get("responses") == {})
    r = client.put("/api/profile/full", headers=auth_b, json={
        "responses": {"identity.name": {"firm": "Otro Despacho", "lawyer": "Otro Abogado"}}
    })
    check("PUT de B -> 200", r.status_code == 200)
    check("las respuestas de A siguen intactas tras el PUT de B",
          load_responses(tid_a).get("identity.name", {}).get("firm") == "Fajardo & Asociados")
    check("B tiene su PROPIO archivo de respuestas, distinto del de A",
          soul_path(tid_a) != soul_path(tid_b)
          and load_responses(tid_b).get("identity.name", {}).get("firm") == "Otro Despacho")

    # ── 10 · §G — sin jerga técnica en los textos visibles ───────────────────
    blob = " ".join(visible).lower()
    leaked = [w for w in FORBIDDEN if w in blob]
    check(f"§G: respuestas sin jerga técnica (fugas: {leaked or 'ninguna'})", not leaked)


def main() -> int:
    print("== Bloque C · C2 · perfil del despacho editable y unificado ==")
    if not os.getenv("PG_PASSWORD") or not config.JWT_SECRET:
        print("  [FAIL] PG_PASSWORD o JWT_SECRET vacío en .env")
        return 1

    init_knowledge_stores.apply()   # 004 · tenant_settings
    init_profiles.apply()           # 007 · firm_profiles

    run_derive_checks()

    import jwt
    from fastapi.testclient import TestClient
    from mia.api.main import app

    tid_a = make_tenant("A")
    tid_b = make_tenant("B")
    tok_a = jwt.encode({"tenant_id": tid_a}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    tok_b = jwt.encode({"tenant_id": tid_b}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    auth_a = {"Authorization": f"Bearer {tok_a}"}
    auth_b = {"Authorization": f"Bearer {tok_b}"}

    original_home = config.MIA_HOME
    try:
        with tempfile.TemporaryDirectory() as tmp:
            config.MIA_HOME = Path(tmp)
            with TestClient(app) as client:
                run_checks(client, auth_a, tid_a, auth_b, tid_b)
    finally:
        config.MIA_HOME = original_home
        cleanup([tid_a, tid_b])

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Bloque C · C2 OK.")
        return 0
    print("Bloque C · C2 FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
