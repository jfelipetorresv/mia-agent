"""
Mia · test_agent_hub.py — gate del Módulo 1e (Agent Hub).

Offline (subprocess mockeado; NO requiere CLIs instalados) + una parte contra la
DB real para la config por tenant. Verifica:
  1. list_available() sin crashes y con detección correcta.
  2. CLI no disponible → error descriptivo, sin lanzar excepción (runner no se llama).
  3. Rutas con espacio se pasan intactas al subprocess (args en lista, shell=False).
  4. Fallos del runner (exit≠0, excepción, timeout) → string de error, nunca propaga.
  5. Config por tenant persiste en DB, aislada por RLS; default todos deshabilitados.
  6. Seam de delegación del grafo: OFF por defecto; solo dispara con señal + habilitado.

    .venv\\Scripts\\python.exe execution\\test_agent_hub.py
"""
from __future__ import annotations
import asyncio
import os
import shutil
import subprocess
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
try:
    sys.stdout.reconfigure(encoding="utf-8")  # cp1252: evitar crash al imprimir
except Exception:
    pass

import mia.gateway.agent_hub as ah                  # noqa: E402
from mia.gateway import hub_config                  # noqa: E402
from mia.gateway.agent_hub import AgentHub          # noqa: E402
from mia.db import pool                             # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


PG = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
          dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""))


def setup_data():
    with psycopg.connect(autocommit=True, **PG) as c:
        a = c.execute("INSERT INTO tenants(name) VALUES('A test 1e') RETURNING id").fetchone()[0]
        b = c.execute("INSERT INTO tenants(name) VALUES('B test 1e') RETURNING id").fetchone()[0]
    return str(a), str(b)


def cleanup(a, b):
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id = ANY(%s)", ([a, b],))


# ── offline: detección + invocación ────────────────────────────────────────
def test_detection_and_invoke():
    orig_which = ah.shutil.which

    # which=None → todos no instalados; invocar un no instalado degrada con gracia.
    ah.shutil.which = lambda *a, **k: None
    called = {"n": 0}

    def rec(args, *, cwd=None, timeout=None):
        called["n"] += 1
        return (0, "x", "")

    try:
        hub = AgentHub(env={}, runner=rec)
        avail = hub.list_available()
        check("list_available() devuelve los 5 conectores", len(avail) == 5)
        check("list_available() no crashea y marca installed=bool",
              all(isinstance(v["installed"], bool) for v in avail.values()))
        check("con which=None todos no instalados", all(not v["installed"] for v in avail.values()))

        out = hub.invoke_openclaw("investiga", "t-1")
        check("no instalado → '[no disponible]'", out.startswith("[no disponible]"))
        check("no instalado → el runner NO se llama", called["n"] == 0)
        check("no instalado → no lanza excepción (llegamos aquí)", True)
    finally:
        ah.shutil.which = orig_which

    # which selectivo: solo hermes instalado.
    ah.shutil.which = lambda name: "/fake/hermes" if name == "hermes" else None
    try:
        hub = AgentHub(env={})
        avail = hub.list_available()
        check("detección selectiva: hermes instalado", avail["hermes"]["installed"])
        check("detección selectiva: claude_code NO", not avail["claude_code"]["installed"])
        check("display_name en español, sin marca",
              avail["hermes"]["display_name"] == "Asistente de investigación jurídica")
        check("id público es slug neutro (sin marca)", avail["hermes"]["slug"] == "investigacion")
        check("list_available no filtra binario a marca en display",
              all("hermes" not in v["display_name"].lower() and "claude" not in v["display_name"].lower()
                  for v in avail.values()))
    finally:
        ah.shutil.which = orig_which

    # los 5 métodos nombrados existen.
    hub = AgentHub()
    check("existen los 5 métodos invoke_*",
          all(callable(getattr(hub, f"invoke_{k}", None))
              for k in ("hermes", "claude_code", "codex", "antigravity", "openclaw")))


# ── offline: rutas con espacio + fallos del runner ─────────────────────────
def test_space_path_and_failures():
    tmp = tempfile.mkdtemp()
    spdir = os.path.join(tmp, "Mia Super Agent")   # ← espacio a propósito
    os.makedirs(spdir, exist_ok=True)
    binp = os.path.join(spdir, "fakeagent.exe")
    open(binp, "w").close()
    project_with_space = str(ROOT)  # "...\Mia-Super Agent\mia"

    captured = {}

    def recorder(args, *, cwd=None, timeout=None):
        captured.update(args=args, cwd=cwd, timeout=timeout)
        return (0, "salida del agente", "")

    try:
        hub = AgentHub(env={"MIA_ANTIGRAVITY_BIN": binp}, runner=recorder, cwd=project_with_space)
        out = hub.invoke_antigravity("investiga esto", "t-1")
        check("override por env detecta el binario (ruta con espacio)", out == "salida del agente")
        check("la ruta con espacio va INTACTA como primer arg (1 elemento)",
              captured["args"][0] == binp and " " in captured["args"][0])
        check("args en lista: prompt como elemento aparte", captured["args"][-1] == "investiga esto")
        check("cwd con espacio se pasa intacto", captured["cwd"] == project_with_space and " " in captured["cwd"])
        check("timeout = 120s", captured["timeout"] == 120)

        # exit != 0
        hub_exit = AgentHub(env={"MIA_ANTIGRAVITY_BIN": binp}, runner=lambda a, **k: (1, "", "explotó"))
        out = hub_exit.invoke_antigravity("x", "t")
        check("exit≠0 → '[error]' con código, sin excepción", out.startswith("[error]") and "código 1" in out)

        # excepción del runner
        def raiser(a, **k):
            raise OSError("kaboom")
        out = AgentHub(env={"MIA_ANTIGRAVITY_BIN": binp}, runner=raiser).invoke_antigravity("x", "t")
        check("excepción del runner → '[error]', no propaga", out.startswith("[error]") and "kaboom" in out)

        # timeout
        def timeouter(a, **k):
            raise subprocess.TimeoutExpired(cmd=a, timeout=120)
        out = AgentHub(env={"MIA_ANTIGRAVITY_BIN": binp}, runner=timeouter).invoke_antigravity("x", "t")
        check("timeout → '[error] no respondió', no propaga", out.startswith("[error]") and "no respondió" in out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── DB: config por tenant + RLS + seam de delegación ───────────────────────
async def db_tests(a, b):
    await pool.open_pool()
    try:
        obs = {}
        obs["default_empty"] = (await hub_config.get_hub_config(a)) == {}
        obs["default_disabled"] = (await hub_config.is_enabled(a, "hermes")) is False

        await hub_config.set_enabled(a, "hermes", True)
        obs["enabled_after_set"] = await hub_config.is_enabled(a, "hermes")
        obs["map_has_hermes"] = (await hub_config.get_hub_config(a)).get("hermes") is True

        # RLS: B no ve la config de A.
        obs["b_isolated"] = (await hub_config.is_enabled(b, "hermes")) is False
        obs["b_map_empty"] = (await hub_config.get_hub_config(b)) == {}

        # disable + coexistencia de un segundo agente.
        await hub_config.set_enabled(a, "hermes", False)
        obs["disabled_after"] = (await hub_config.is_enabled(a, "hermes")) is False
        await hub_config.set_enabled(a, "codex", True)
        cfg = await hub_config.get_hub_config(a)
        obs["coexist"] = cfg.get("codex") is True and cfg.get("hermes") is False

        # seam de delegación del grafo.
        from mia.agents.graph import MatterGraphBuilder
        gb = MatterGraphBuilder()
        obs["delegate_noop"] = (await gb._maybe_delegate({"tenant_id": a, "metadata": {}})) is None
        st = {"tenant_id": a, "metadata": {"delegate": {"agent": "hermes", "prompt": "x"}}, "messages": []}
        obs["delegate_gated"] = (await gb._maybe_delegate(st)) is None  # hermes deshabilitado

        await hub_config.set_enabled(a, "hermes", True)

        class FakeHub:
            def invoke(self, key, prompt, tenant_id):
                return f"DELEGADO:{key}:{prompt}"

        gb2 = MatterGraphBuilder(agent_hub=FakeHub())
        obs["delegate_fires"] = (await gb2._maybe_delegate(st)) == "DELEGADO:hermes:x"
        return obs
    finally:
        await pool.close_pool()


# ── HTTP: endpoints de settings (PASO 3) ───────────────────────────────────
def api_checks(a):
    import jwt
    from fastapi.testclient import TestClient
    from mia import config
    from mia.api.main import app

    H = {"Authorization": f"Bearer {jwt.encode({'tenant_id': a}, config.JWT_SECRET, algorithm=config.JWT_ALG)}"}
    out = {}
    with TestClient(app) as client:
        r = client.get("/settings/agents", headers=H)
        out["list_status"] = r.status_code
        agentes = r.json().get("agentes", [])
        out["count"] = len(agentes)
        out["shape_ok"] = all({"id", "nombre", "instalado", "habilitado"} <= set(x) for x in agentes)
        brands = ("hermes", "claude", "codex", "antigravity", "openclaw")
        out["no_brand"] = all(not any(brnd in (x["nombre"] + x["id"]).lower() for brnd in brands) for x in agentes)
        # enable → habilitado True
        out["enable_status"] = client.post("/settings/agents/investigacion/enable", headers=H).status_code
        ag = {x["id"]: x for x in client.get("/settings/agents", headers=H).json()["agentes"]}
        out["enabled_true"] = ag["investigacion"]["habilitado"] is True
        # disable → habilitado False
        out["disable_status"] = client.post("/settings/agents/investigacion/disable", headers=H).status_code
        ag2 = {x["id"]: x for x in client.get("/settings/agents", headers=H).json()["agentes"]}
        out["disabled_false"] = ag2["investigacion"]["habilitado"] is False
        # desconocido → 404 ; sin token → 401
        out["unknown_status"] = client.post("/settings/agents/noexiste/enable", headers=H).status_code
        out["notoken_status"] = client.get("/settings/agents").status_code
    return out


def main() -> int:
    print("== Módulo 1e · Agent Hub ==")
    test_detection_and_invoke()
    test_space_path_and_failures()

    a, b = setup_data()
    try:
        obs = asyncio.run(db_tests(a, b))
        api = api_checks(a)
    finally:
        cleanup(a, b)

    check("default: config vacía (todos deshabilitados)", obs["default_empty"])
    check("default: is_enabled() = False", obs["default_disabled"])
    check("enable persiste en DB (is_enabled True)", obs["enabled_after_set"])
    check("el mapa de config refleja el agente habilitado", obs["map_has_hermes"])
    check("RLS: tenant B no ve la config de A (is_enabled False)", obs["b_isolated"])
    check("RLS: tenant B ve su config vacía", obs["b_map_empty"])
    check("disable persiste (is_enabled False)", obs["disabled_after"])
    check("varios agentes coexisten en el jsonb", obs["coexist"])
    check("delegación OFF por defecto (sin señal → None)", obs["delegate_noop"])
    check("delegación gated: señal pero agente deshabilitado → None", obs["delegate_gated"])
    check("delegación dispara con señal + habilitado", obs["delegate_fires"])

    # PASO 3 · endpoints de settings
    check("GET /settings/agents responde 200", api["list_status"] == 200)
    check("lista los 5 conectores con forma {id,nombre,instalado,habilitado}",
          api["count"] == 5 and api["shape_ok"])
    check("nombres/ids SIN marca de CLI (§G)", api["no_brand"])
    check("POST enable (por slug) habilita → habilitado True", api["enable_status"] == 200 and api["enabled_true"])
    check("POST disable deshabilita → habilitado False", api["disable_status"] == 200 and api["disabled_false"])
    check("agente desconocido → 404", api["unknown_status"] == 404)
    check("sin token → 401", api["notoken_status"] == 401)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
