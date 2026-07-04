"""
Mia · test_missions.py — gate del tablero de misión por expediente (CP-E5 · Ola 5).

OFFLINE (puro, sin DB) — guardas de la descomposición (missions/decompose.py):
  · _PROCEDURAL_RE marca términos/plazos; _sanitize fuerza is_procedural aunque el modelo no;
  · _sanitize acota a MAX_MILESTONES, corrige actor inválido, descarta títulos vacíos/no-dict;
  · _extract_json_array tolera ``` y prosa alrededor;
  · propose_milestones fail-soft: modelo que revienta → plantilla genérica; objetivo vacío →
    plantilla; JSON válido → parseado y saneado (con la guarda procesal aplicada).

DB (RLS · fail-closed · aislamiento) — missions/service.py:
  · create_mission con auto_decompose persiste los hitos 'queued' en orden (seq);
  · propiedad del expediente: crear con un expediente AJENO → MissionError (RLS fail-closed);
  · CRUD de misión e hitos (editar, avanzar a 'done', añadir, borrar) y progreso;
  · topes MAX_MISSIONS_PER_MATTER / MAX_MILESTONES_PER_MISSION;
  · AISLAMIENTO: el despacho B no ve/edita/borra la misión ni los hitos del despacho A.

Salida: exit 0 = PASS · exit 1 = FAIL.

    .venv\\Scripts\\python.exe execution\\test_missions.py
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

import init_missions                                    # noqa: E402
from mia.db import pool                                 # noqa: E402
from mia.missions import decompose                      # noqa: E402
from mia.missions import service as msvc                # noqa: E402
from mia.missions.service import MissionError, MissionService  # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)


def make_tenants() -> tuple[str, str]:
    with psycopg.connect(autocommit=True, **PG) as c:
        a = c.execute("INSERT INTO tenants(name) VALUES('A test cpe5') RETURNING id").fetchone()[0]
        b = c.execute("INSERT INTO tenants(name) VALUES('B test cpe5') RETURNING id").fetchone()[0]
    return str(a), str(b)


def make_matter(tenant_id: str, title: str = "Expediente de prueba") -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        mid = c.execute(
            "INSERT INTO matters(tenant_id, title, description) VALUES(%s, %s, %s) RETURNING id",
            (tenant_id, title, "Demanda de prueba CP-E5"),
        ).fetchone()[0]
    return str(mid)


def drop_tenants(*ids: str) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        for tid in ids:
            c.execute("DELETE FROM tenants WHERE id = %s", (tid,))


# ── OFFLINE ──────────────────────────────────────────────────────────────────
def offline_checks() -> None:
    print("\n-- offline: guardas de descomposición (procesal, saneo, parseo, fail-soft) --")

    # A · GUARDA PROCESAL: el regex marca términos/plazos.
    check("procesal: 'plazo' se detecta", bool(decompose._PROCEDURAL_RE.search("Vencido el plazo")))
    check("procesal: 'término' se detecta", bool(decompose._PROCEDURAL_RE.search("dentro del término")))
    check("procesal: 'radicar' se detecta", bool(decompose._PROCEDURAL_RE.search("Radicar la contestación")))
    check("procesal: 'caducidad' se detecta", bool(decompose._PROCEDURAL_RE.search("excepción de caducidad")))
    check("procesal: texto neutro NO se marca",
          not decompose._PROCEDURAL_RE.search("Revisar los documentos del caso"))

    # B · _sanitize: fuerza is_procedural, corrige actor, acota, descarta basura.
    dirty = [
        {"title": "Contestar dentro del término", "detail": "x", "actor": "mia", "is_procedural": False},
        {"title": "Analizar la demanda", "detail": "leer", "actor": "raro"},
        {"title": "", "detail": "sin título — se descarta"},
        "no soy dict",
        {"detail": "sin título — se descarta también"},
    ]
    san = decompose._sanitize(dirty)
    check("saneo: descarta no-dicts y títulos vacíos (quedan 2)", len(san) == 2)
    check("saneo: fuerza is_procedural aunque el modelo diga False (texto menciona término)",
          san[0]["is_procedural"] is True)
    check("saneo: actor inválido → 'abogado'", san[1]["actor"] == "abogado")
    check("saneo: actor válido se conserva", san[0]["actor"] == "mia")
    # Tope MAX_MILESTONES.
    many = [{"title": f"Hito {i}", "detail": "d"} for i in range(20)]
    check("saneo: acota a MAX_MILESTONES",
          len(decompose._sanitize(many)) == decompose.MAX_MILESTONES)

    # C · _extract_json_array tolera cercas y prosa.
    fenced = 'Claro, aquí está:\n```json\n[{"title":"A","detail":"d"}]\n```\nEso es todo.'
    parsed = decompose._extract_json_array(fenced)
    check("parseo: extrae el arreglo JSON entre prosa y ```",
          isinstance(parsed, list) and parsed and parsed[0]["title"] == "A")
    check("parseo: texto sin arreglo → None", decompose._extract_json_array("no hay json") is None)

    # D · propose_milestones fail-soft (monkeypatch de llm.call_llm).
    from mia.agent import llm as _llm

    class _FakeResp:
        def __init__(self, content):
            self.choices = [type("C", (), {"message": type("M", (), {"content": content})()})()]

    orig = _llm.call_llm
    try:
        # D.1 · modelo revienta → plantilla genérica.
        _llm.call_llm = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("modelo caído"))
        res = asyncio.run(decompose.propose_milestones("preparar la contestación"))
        check("fail-soft: modelo caído → plantilla genérica (no vacía)", len(res) >= 3)
        check("fail-soft: la plantilla trae claves esperadas",
              all(set(("title", "detail", "actor", "is_procedural")) <= set(x) for x in res))

        # D.2 · JSON válido con un hito procesal mal marcado → se corrige.
        good = ('[{"title":"Analizar la demanda","detail":"leer el libelo","actor":"mia",'
                '"is_procedural":false},'
                '{"title":"Radicar la contestación","detail":"presentar el escrito",'
                '"actor":"abogado","is_procedural":false}]')
        _llm.call_llm = lambda *a, **k: _FakeResp(good)
        res = asyncio.run(decompose.propose_milestones("preparar la contestación",
                                                       matter_title="Zurich vs X"))
        check("parseo real: 2 hitos del modelo", len(res) == 2)
        check("parseo real: 'Radicar' se marca procesal pese al false del modelo",
              res[1]["is_procedural"] is True)
        check("parseo real: hito neutro NO se marca procesal", res[0]["is_procedural"] is False)

        # D.3 · objetivo vacío → plantilla.
        _llm.call_llm = lambda *a, **k: _FakeResp("[]")
        res = asyncio.run(decompose.propose_milestones("   "))
        check("fail-soft: objetivo vacío → plantilla genérica", len(res) >= 3)
    finally:
        _llm.call_llm = orig


# ── DB ────────────────────────────────────────────────────────────────────────
# Stub determinista de la propuesta (no depende del LLM vivo en la regresión).
_STUB = [
    {"title": "Analizar la demanda", "detail": "Leer el libelo y las pruebas.",
     "actor": "mia", "is_procedural": False},
    {"title": "Contestar dentro del término", "detail": "Preparar la contestación.",
     "actor": "abogado", "is_procedural": True},
    {"title": "Revisar y radicar", "detail": "Revisar el escrito final.",
     "actor": "abogado", "is_procedural": True},
]


async def db_checks(a: str, b: str, matter_a: str, matter_b: str) -> None:
    print("\n-- db: creación+descomposición, propiedad, CRUD, topes, aislamiento --")
    await pool.open_pool()
    # Monkeypatch de la propuesta a un stub determinista para toda la sección DB.
    orig = decompose.propose_milestones

    async def _fake_propose(objective, *, matter_title="", matter_description=""):
        return [dict(x) for x in _STUB]

    decompose.propose_milestones = _fake_propose
    try:
        await _db_checks(a, b, matter_a, matter_b)
    finally:
        decompose.propose_milestones = orig
        await pool.close_pool()


async def _db_checks(a: str, b: str, matter_a: str, matter_b: str) -> None:
    svc = MissionService()

    # Crear misión con descomposición automática.
    mission = await svc.create_mission(
        a, matter_a, title="Preparar la contestación",
        objective="Contestar la demanda de Zurich con excepciones de fondo.")
    check("crear: la misión se crea con título y objetivo",
          mission.title == "Preparar la contestación" and mission.status == "active")
    check("crear: auto-descompone en 3 hitos 'queued' en orden",
          len(mission.milestones) == 3 and [m.seq for m in mission.milestones] == [0, 1, 2]
          and all(m.status == "queued" for m in mission.milestones))
    check("crear: el hito procesal quedó marcado (is_procedural)",
          mission.milestones[1].is_procedural is True)
    check("crear: progreso 0/3 en to_public",
          mission.to_public()["progress"] == {"done": 0, "total": 3})

    # PROPIEDAD del expediente: crear con expediente AJENO (de B) → MissionError.
    owned_err = False
    try:
        await svc.create_mission(a, matter_b, title="x", objective="y", auto_decompose=False)
    except MissionError:
        owned_err = True
    check("propiedad: crear misión con expediente de otro despacho → MissionError", owned_err)

    # Avanzar un hito a 'done' y verificar progreso.
    m0 = mission.milestones[0]
    upd = await svc.update_milestone(a, m0.id, status="done")
    check("hito: avanzar a 'done' se refleja",
          any(x.id == m0.id and x.status == "done" for x in upd.milestones))
    check("hito: progreso pasa a 1/3", upd.to_public()["progress"] == {"done": 1, "total": 3})

    # Añadir un hito manual.
    with_added = await svc.add_milestone(a, mission.id, title="Reunir pruebas adicionales",
                                         detail="Solicitar documentos", actor="abogado")
    check("hito: añadir manual crece el tablero a 4", len(with_added.milestones) == 4)
    added = [x for x in with_added.milestones if x.title == "Reunir pruebas adicionales"][0]

    # Editar la misión (resultado esperado) y su estado.
    edited = await svc.update_mission(a, mission.id, outcome="Contestación radicada a tiempo")
    check("misión: editar el resultado esperado", edited.outcome == "Contestación radicada a tiempo")

    # Borrar el hito añadido.
    after_del = await svc.delete_milestone(a, added.id)
    check("hito: borrar lo quita (vuelve a 3)", len(after_del.milestones) == 3)

    # Re-descomponer añadiendo al final.
    recomp = await svc.decompose_mission(a, mission.id, replace=False)
    check("re-descomponer (append): crece el tablero", len(recomp.milestones) == 6)
    # Re-descomponer reemplazando.
    recomp2 = await svc.decompose_mission(a, mission.id, replace=True)
    check("re-descomponer (replace): vuelve a 3", len(recomp2.milestones) == 3)

    # Listar por expediente.
    listed = await svc.list_missions(a, matter_a)
    check("listar: 1 misión para el expediente de A", len(listed) == 1 and listed[0].id == mission.id)

    # AISLAMIENTO RLS: B no ve/edita/borra la misión de A.
    check("RLS: B no VE la misión de A (get → None)",
          await svc.get_mission(b, mission.id) is None)
    check("RLS: B no lista la misión de A por su propio expediente (vacío)",
          (await svc.list_missions(b, matter_b)) == [])
    b_edit_blocked = False
    try:
        await svc.update_mission(b, mission.id, title="Hackeada")
    except MissionError:
        b_edit_blocked = True
    check("RLS: B no EDITA la misión de A (MissionError)", b_edit_blocked)
    b_ms_blocked = False
    try:
        await svc.update_milestone(b, recomp2.milestones[0].id, status="done")
    except MissionError:
        b_ms_blocked = True
    check("RLS: B no EDITA un hito de A (MissionError)", b_ms_blocked)
    b_del_blocked = False
    try:
        await svc.delete_mission(b, mission.id)
    except MissionError:
        b_del_blocked = True
    check("RLS: B no BORRA la misión de A (MissionError)", b_del_blocked)
    check("RLS: la misión de A sigue intacta tras los intentos de B",
          (await svc.get_mission(a, mission.id)) is not None)

    # TOPE de misiones por expediente.
    async def _fill_missions() -> bool:
        current = len(await svc.list_missions(a, matter_a))
        for i in range(current, msvc.MAX_MISSIONS_PER_MATTER):
            await svc.create_mission(a, matter_a, title=f"M{i}", objective="o",
                                     auto_decompose=False)
        try:
            await svc.create_mission(a, matter_a, title="UnaMas", objective="o",
                                     auto_decompose=False)
            return False
        except MissionError:
            return True
    check("tope: MAX_MISSIONS_PER_MATTER bloquea crear otra", await _fill_missions())

    # TOPE de hitos por misión.
    tope_mission = await svc.create_mission(b, matter_b, title="Tope hitos", objective="o",
                                            auto_decompose=False)

    async def _fill_milestones() -> bool:
        for i in range(msvc.MAX_MILESTONES_PER_MISSION):
            await svc.add_milestone(b, tope_mission.id, title=f"H{i}")
        try:
            await svc.add_milestone(b, tope_mission.id, title="UnoMas")
            return False
        except MissionError:
            return True
    check("tope: MAX_MILESTONES_PER_MISSION bloquea añadir otro", await _fill_milestones())

    # Borrar la misión (CASCADE de hitos).
    await svc.delete_mission(a, mission.id)
    check("borrar: la misión desaparece", await svc.get_mission(a, mission.id) is None)


def main() -> int:
    init_missions.apply()   # idempotente: tablas missions + mission_milestones (migración 024)

    offline_checks()
    a, b = make_tenants()
    try:
        matter_a = make_matter(a, "Zurich vs Banco Popular")
        matter_b = make_matter(b, "Seguros del Estado vs CNE")
        asyncio.run(db_checks(a, b, matter_a, matter_b))
    finally:
        drop_tenants(a, b)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Tablero de misión OK — CP-E5 verificado.")
        return 0
    print("Tablero de misión FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
