"""
Mia · test_despacho_atajos.py — gate del Meta E (Mitad 2): atajos de despacho.

Ejercita, contra la DB real (playbooks 005 + personas 023), `GET /api/atajos`
(memory/atajos.py + api/routes/atajos.py): el "un clic -> encargo listo" de guías activas y
agentes habilitados del despacho. Molde calcado de execution/test_playbook_versions.py /
execution/test_agent_playbooks.py (TestClient + JWT, tenants propios con limpieza en
finally). Cubre:

  1. Seed de 2 guías activas + 1 agente con summon_phrases -> GET /api/atajos trae los 3,
     guías ordenadas por uso (usage_count desc), agentes por nombre.
  2. Determinismo: dos llamadas seguidas devuelven el mismo texto byte a byte.
  3. ROUND-TRIP real: detect_persona(texto_del_atajo, [ese agente]) — SIN tocar la función ya
     gateada de agents/personas.py — resuelve exactamente a ese agente, probando que el atajo
     SÍ dispara la persona.
  4. El atajo de una guía reproduce su "cuándo aplica" y la disciplina [VERIFICAR].
  5. Un agente deshabilitado y una guía archivada NO aparecen en los atajos.
  6. Nunca más de 6 atajos (tope de la pantalla).
  7. RLS: el despacho B no ve ni un atajo del despacho A.
  8. §G: ninguna respuesta visible usa jerga técnica (embedding, chunk, tenant, pgvector,
     playbook, persona, canonical_prompt, RLS) — ni siquiera en el campo `kind` ('guia' /
     'agente', nunca 'playbook' / 'persona').

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_despacho_atajos.py
"""
from __future__ import annotations
import asyncio
import os
import sys
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

import init_playbooks    # noqa: E402  (migración 005)
import init_personas     # noqa: E402  (migración 023)
from mia import config    # noqa: E402

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
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id", (f"ATJ_TEST {label}",)
        ).fetchone()[0])


def cleanup(tenants: list[str]) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id = ANY(%s)", (tenants,))


def seed_playbook(tid: str, *, title: str, applies_when: str, usage_count: int = 0) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO playbooks (tenant_id, title, summary, applies_when, content, "
            "usage_count, status) VALUES (%s::uuid, %s, %s, %s, %s, %s, 'active') "
            "RETURNING id",
            (tid, title, "s", applies_when, "contenido de prueba", usage_count)
        ).fetchone()[0])


def archive_playbook(pid: str) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("UPDATE playbooks SET status = 'archived' WHERE id = %s::uuid", (pid,))


def seed_persona(tid: str, *, name: str, description: str, summon_phrases: list[str],
                 enabled: bool = True) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO personas (tenant_id, name, role_prompt, description, "
            "summon_phrases, enabled) VALUES (%s::uuid, %s, %s, %s, %s, %s) RETURNING id",
            (tid, name, "Voz de prueba para el gate.", description, summon_phrases, enabled)
        ).fetchone()[0])


def run_checks(client, auth_a, tid_a, auth_b, tid_b) -> None:
    visible: list[str] = []

    # ── 1 · seed: 2 guías activas + 1 agente ─────────────────────────────────
    pb1 = seed_playbook(tid_a, title="Contestación de demanda ordinaria",
                       applies_when="cuando el despacho contesta una demanda civil",
                       usage_count=5)
    pb2 = seed_playbook(tid_a, title="Recurso de reposición",
                       applies_when="cuando se impugna un auto interlocutorio",
                       usage_count=2)
    summon_phrases = ["como estratega procesal", "modo estratega"]
    ag_id = seed_persona(
        tid_a, name="Estratega",
        description="Enfoca el asunto desde la defensa procesal del cliente.",
        summon_phrases=summon_phrases)

    r1 = client.get("/api/atajos", headers=auth_a)
    check("GET /api/atajos -> 200", r1.status_code == 200)
    visible.append(r1.text)
    atajos1 = r1.json().get("atajos", [])
    check("trae los 2 guías + 1 agente (3 atajos)", len(atajos1) == 3)

    kinds = {a["kind"] for a in atajos1}
    check("los tipos son 'guia'/'agente' (nunca la jerga técnica de la tabla)",
          kinds <= {"guia", "agente"})

    guia_items = [a for a in atajos1 if a["kind"] == "guia"]
    check("las guías vienen ordenadas por uso (usage_count desc)",
          [g["label"] for g in guia_items] ==
          ["Contestación de demanda ordinaria", "Recurso de reposición"])

    agente_item = next((a for a in atajos1 if a["kind"] == "agente"), None)
    check("el atajo del agente existe y trae su texto reproducible",
          agente_item is not None and isinstance(agente_item.get("texto"), str))

    # ── 2 · determinismo byte a byte ──────────────────────────────────────────
    r2 = client.get("/api/atajos", headers=auth_a)
    atajos2 = r2.json().get("atajos", [])
    check("GET /api/atajos es determinista (mismo input DB -> mismo texto byte a byte)",
          atajos1 == atajos2)

    # ── 3 · ROUND-TRIP: detect_persona reconoce el atajo (función ya gateada) ──
    from mia.agents.personas import Persona, detect_persona

    persona_obj = Persona(
        id=ag_id, name="Estratega", title="", role_prompt="Voz de prueba para el gate.",
        tone="", focus_areas=(), model_tier="estandar",
        summon_phrases=tuple(summon_phrases),
        description="Enfoca el asunto desde la defensa procesal del cliente.", enabled=True,
    )
    resolved = detect_persona(agente_item["texto"], [persona_obj])
    check("ROUND-TRIP: detect_persona resuelve al agente a partir del texto del atajo "
          "(el atajo SÍ dispara la persona reusando la función ya gateada)",
          resolved is not None and resolved.id == ag_id)

    # una frase de invocación que NO aparece en el atajo -> no debe casar por accidente
    otro = Persona(
        id="00000000-0000-0000-0000-000000000000", name="Otro", title="",
        role_prompt="x", tone="", focus_areas=(), model_tier="estandar",
        summon_phrases=("frase que no aparece en ningún atajo",), description="", enabled=True,
    )
    check("detect_persona NO resuelve a un agente cuya frase no está en el texto",
          detect_persona(agente_item["texto"], [otro]) is None)

    # ── 4 · el atajo de guía reproduce 'cuándo aplica' + disciplina [VERIFICAR] ─
    guia_ataj = next(a for a in atajos1 if a["label"] == "Contestación de demanda ordinaria")
    check("el atajo de guía reproduce el 'cuándo aplica' de esa guía",
          "cuando el despacho contesta una demanda civil" in guia_ataj["texto"])
    check("el atajo de guía instruye marcar [VERIFICAR] lo no confirmado",
          "[VERIFICAR]" in guia_ataj["texto"])
    check("el atajo de guía nombra el título entre comillas",
          '"Contestación de demanda ordinaria"' in guia_ataj["texto"])

    # ── 5 · deshabilitado/archivado no aparecen ──────────────────────────────
    ag_disabled = seed_persona(
        tid_a, name="Deshabilitada", description="No debe aparecer en los atajos.",
        summon_phrases=["modo oculto"], enabled=False)
    archive_playbook(pb2)
    r3 = client.get("/api/atajos", headers=auth_a)
    atajos3 = r3.json().get("atajos", [])
    check("un agente deshabilitado NO aparece en los atajos",
          not any(a["id"] == ag_disabled for a in atajos3))
    check("una guía archivada NO aparece en los atajos",
          not any(a["id"] == pb2 for a in atajos3))
    visible.append(r3.text)

    # ── 6 · tope de 6 atajos + cupo garantizado del agente ───────────────────
    # Se siembran 6 guías más (7 activas en total, más que el tope): antes esto tapaba al
    # agente por completo — las guías llenaban la lista y el corte final lo descartaba, así
    # que el despacho configuraba sus agentes y no volvía a verlos en la conversación vacía.
    for i in range(6):
        seed_playbook(tid_a, title=f"Guía adicional {i}", applies_when="w",
                     usage_count=100 + i)
    r4 = client.get("/api/atajos", headers=auth_a)
    atajos4 = r4.json().get("atajos", [])
    check("nunca trae más de 6 atajos (tope de la pantalla)", len(atajos4) <= 6)
    check("con más guías activas que cupos, el agente del despacho SIGUE apareciendo",
          any(a["id"] == ag_id for a in atajos4))
    check("los cupos se aprovechan completos (6 atajos, no menos)", len(atajos4) == 6)
    # 1 agente habilitado -> 1 cupo reservado, los otros 5 son de las guías más usadas
    # (usage_count 105..101 = "Guía adicional 5".."Guía adicional 1").
    check("las guías que entran son las más usadas, en orden de uso",
          [a["label"] for a in atajos4 if a["kind"] == "guia"] ==
          [f"Guía adicional {i}" for i in (5, 4, 3, 2, 1)])
    r4b = client.get("/api/atajos", headers=auth_a)
    check("el reparto guías/agentes es determinista (misma lista byte a byte)",
          atajos4 == r4b.json().get("atajos", []))
    visible.append(r4.text)

    # ── 7 · RLS: B no ve ni un atajo de A ─────────────────────────────────────
    r5 = client.get("/api/atajos", headers=auth_b)
    check("RLS: el despacho B no ve los atajos del despacho A (lista vacía)",
          r5.status_code == 200 and r5.json().get("atajos") == [])
    visible.append(r5.text)

    with psycopg.connect(autocommit=True, **PG) as c:
        n_cross = c.execute(
            "SELECT count(*) FROM playbooks WHERE id = ANY(%s::uuid[])", ([pb1, pb2],)
        ).fetchone()[0]
    check("(sanity) las guías de A existen realmente en la tabla", n_cross == 2)

    # ── 8 · §G — sin jerga técnica ────────────────────────────────────────────
    blob = " ".join(visible).lower()
    leaked = [w for w in FORBIDDEN if w in blob]
    check(f"§G: respuestas sin jerga técnica (fugas: {leaked or 'ninguna'})", not leaked)


def main() -> int:
    print("== Meta E (Mitad 2) · atajos de despacho ==")
    if not os.getenv("PG_PASSWORD") or not config.JWT_SECRET:
        print("  [FAIL] PG_PASSWORD o JWT_SECRET vacío en .env")
        return 1

    init_playbooks.apply()    # 005
    init_personas.apply()     # 023

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
        print("Meta E (Mitad 2) OK.")
        return 0
    print("Meta E (Mitad 2) FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
