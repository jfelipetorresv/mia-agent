"""
Mia · test_notebooklm_gate.py — candado de confidencialidad de NotebookLM (CP-NLM).

NotebookLM es nube de Google: la PREGUNTA de Mia viaja a Google. Este gate verifica
OFFLINE (sin red, sin CLI real, subprocess mockeado) que NADA salga sin autorización:

  Gate (connectors.notebooklm.gate.query_allowed):
    1. política 'soberano' → BLOQUEA aunque el opt-in esté activo (cero salida del equipo).
    2. opt-in por defecto False → BLOQUEA (regla dura: la salida a la nube es opt-in).
    3. política ≠ soberano + opt-in True → PERMITE.
    4. error leyendo la política (DB caída) → BLOQUEA (fail-closed, no fail-open).

  Entrada (connectors.notebooklm.consult_notebook):
    5. gate bloquea → devuelve None y NUNCA llama al CLI (no hay fuga).
    6. permitido + notebook + CLI ok → respuesta SELLADA como contenido externo no confiable
       (lleva el aviso de cuarentena y el sello <<<...>>>), NO texto crudo.
    7. sin notebook configurado → None (no se consulta).

  Cliente (connectors.notebooklm.client):
    8. entorno del subproceso SANEADO: una clave de instalación (ANTHROPIC_API_KEY) NO se
       hereda al CLI; args van en LISTA (shell=False → sin inyección de shell).
    9. parseo de la respuesta: JSON con 'answer' → ese texto; no-JSON → crudo; vacío → None.

HALT si falla (CLAUDE.md §G). Exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_notebooklm_gate.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import tempfile
from pathlib import Path as _Path

from mia.agent import llm
from mia.agents import untrusted
from mia.connectors import notebooklm as nlm
from mia.connectors.notebooklm import client, gate
from mia.connectors.notebooklm import setup as nlm_setup

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


class _Patch:
    """Monkeypatch temporal de atributos de módulo, restaurado al salir."""

    def __init__(self, target, **attrs):
        self.target = target
        self.attrs = attrs
        self._saved: dict = {}

    def __enter__(self):
        for k, v in self.attrs.items():
            self._saved[k] = getattr(self.target, k)
            setattr(self.target, k, v)
        return self

    def __exit__(self, *exc):
        for k, v in self._saved.items():
            setattr(self.target, k, v)


def _async(policy_result=None, policy_raises=False, optin=False):
    """Fakes async para el gate: model_policy_for_strict y notebooklm_allowed_for."""
    async def _policy(_tid):
        if policy_raises:
            raise RuntimeError("DB caída")
        return policy_result
    async def _optin(_tid):
        return optin
    return _policy, _optin


def fake_runner(recorder: dict):
    """Runner falso del subprocess: registra args/env y responde según script por sub-comando."""
    def _run(args, *, timeout, env=None):
        recorder.setdefault("calls", []).append({"args": args, "env": env})
        sub = args[1] if len(args) > 1 else ""
        if sub == "use":
            return (0, "", "")
        if sub == "ask":
            return (0, recorder.get("ask_stdout", '{"answer": "respuesta de prueba"}'), "")
        return (0, "", "")
    return _run


# ── Gate ────────────────────────────────────────────────────────────────────────
async def test_gate() -> None:
    # 1 · soberano bloquea aun con opt-in True
    p, o = _async(policy_result="soberano", optin=True)
    with _Patch(llm, model_policy_for_strict=p, notebooklm_allowed_for=o):
        allowed, reason = await gate.query_allowed("t")
        check("1 · soberano + opt-in True → BLOQUEA (cero salida del equipo)",
              allowed is False and reason == gate.REASON_SOBERANO)

    # 2 · opt-in por defecto False bloquea (política que sí permitiría salida)
    p, o = _async(policy_result="nube", optin=False)
    with _Patch(llm, model_policy_for_strict=p, notebooklm_allowed_for=o):
        allowed, reason = await gate.query_allowed("t")
        check("2 · nube + sin opt-in → BLOQUEA (la salida a la nube es opt-in)",
              allowed is False and reason == gate.REASON_NO_OPTIN)

    # 3 · nube + opt-in True → permite
    p, o = _async(policy_result="nube", optin=True)
    with _Patch(llm, model_policy_for_strict=p, notebooklm_allowed_for=o):
        allowed, reason = await gate.query_allowed("t")
        check("3 · nube + opt-in True → PERMITE", allowed is True and reason == gate.REASON_OK)

    # 3b · suscripcion + opt-in True → permite (cualquier política ≠ soberano)
    p, o = _async(policy_result="suscripcion", optin=True)
    with _Patch(llm, model_policy_for_strict=p, notebooklm_allowed_for=o):
        allowed, _ = await gate.query_allowed("t")
        check("3b · suscripcion + opt-in True → PERMITE", allowed is True)

    # 4 · error leyendo la política (DB caída) → BLOQUEA (fail-closed)
    p, o = _async(policy_raises=True, optin=True)
    with _Patch(llm, model_policy_for_strict=p, notebooklm_allowed_for=o):
        allowed, reason = await gate.query_allowed("t")
        check("4 · error de DB en la política → BLOQUEA (fail-closed, no fail-open)",
              allowed is False and reason == gate.REASON_ERROR)


# ── Entrada consult_notebook ──────────────────────────────────────────────────────
async def test_consult() -> None:
    rec: dict = {}

    # 5 · gate bloquea → None y NUNCA llama al CLI
    async def _blocked(_tid):
        return (False, gate.REASON_SOBERANO)
    with _Patch(nlm, gate=type("g", (), {"query_allowed": staticmethod(_blocked)})):
        out = await nlm.consult_notebook("t", "¿prescribió la acción?",
                                         runner=fake_runner(rec))
    check("5 · gate bloquea → consult devuelve None", out is None)
    check("5b · gate bloquea → el CLI NO se invocó (cero fuga)", "calls" not in rec)

    # 6 · permitido + notebook + CLI ok → respuesta SELLADA (no cruda)
    async def _ok(_tid):
        return (True, gate.REASON_OK)
    async def _nb(_tid):
        return "nb-123"
    rec6: dict = {}
    # El CLI no está instalado en el entorno de test: se parchea resolve_binary para
    # ejercitar el runner mockeado (el subprocess real nunca corre).
    with _Patch(client, resolve_binary=lambda env=None: sys.executable), \
         _Patch(nlm,
                gate=type("g", (), {"query_allowed": staticmethod(_ok)}),
                configured_notebook=_nb):
        out = await nlm.consult_notebook("t", "resume el caso", runner=fake_runner(rec6))
    sealed = out is not None and untrusted.UNTRUSTED_NOTICE in out and "<<<" in out
    check("6 · permitido → respuesta SELLADA como contenido externo (aviso + sello)", sealed)
    check("6b · el texto crudo de NotebookLM va dentro del sello",
          out is not None and "respuesta de prueba" in out)
    check("6c · se invocó el CLI (use + ask)",
          len(rec6.get("calls", [])) == 2
          and rec6["calls"][0]["args"][1] == "use"
          and rec6["calls"][1]["args"][1] == "ask")

    # 7 · sin notebook configurado → None
    async def _no_nb(_tid):
        return None
    rec7: dict = {}
    with _Patch(nlm,
                gate=type("g", (), {"query_allowed": staticmethod(_ok)}),
                configured_notebook=_no_nb):
        out = await nlm.consult_notebook("t", "algo", runner=fake_runner(rec7))
    check("7 · sin notebook configurado → None (no se consulta)", out is None)
    check("7b · sin notebook → el CLI NO se invocó", "calls" not in rec7)


# ── Cliente: saneo de entorno + parseo ────────────────────────────────────────────
def test_client() -> None:
    rec: dict = {}
    # env con un SECRETO de instalación + override del binario a un archivo real (sys.executable)
    dirty_env = {
        "MIA_NOTEBOOKLM_BIN": sys.executable,   # binario "instalado" (archivo real)
        "ANTHROPIC_API_KEY": "sk-ant-SECRETO",  # NO debe heredarse al CLI
        "PATH": "/usr/bin",
        "USERPROFILE": "C:/Users/x",
    }
    ans = client.ask("nb-9", 'pregunta con "comillas" y ; punto y coma',
                     runner=fake_runner(rec), env=dirty_env)
    check("8 · respuesta parseada del JSON ('answer')", ans == "respuesta de prueba")
    passed_env = rec["calls"][0]["env"]
    check("8b · el secreto de instalación NO se hereda al subproceso",
          "ANTHROPIC_API_KEY" not in passed_env)
    check("8c · args van en LISTA con el binario primero (shell=False, sin inyección)",
          isinstance(rec["calls"][1]["args"], list)
          and rec["calls"][1]["args"][0] == sys.executable)

    # 9 · parseo: no-JSON → crudo; vacío → None
    rec2: dict = {"ask_stdout": "texto plano no-json"}
    ans2 = client.ask("nb", "q", runner=fake_runner(rec2), env=dirty_env)
    check("9 · stdout no-JSON → se pasa el texto crudo", ans2 == "texto plano no-json")
    rec3: dict = {"ask_stdout": "   "}
    ans3 = client.ask("nb", "q", runner=fake_runner(rec3), env=dirty_env)
    check("9b · stdout vacío → None", ans3 is None)


# ── Instalador / conexión (máquina de estados) ────────────────────────────────────
def test_setup() -> None:
    # 10 · get_status: matriz (instalado, autenticado) → estado correcto
    with _Patch(nlm_setup, installed=lambda: False, authenticated=lambda: False):
        check("10 · sin instalar → estado 'no_instalado'",
              nlm_setup.get_status()["estado"] == "no_instalado")
    with _Patch(nlm_setup, installed=lambda: True, authenticated=lambda: False):
        s = nlm_setup.get_status()
        check("10b · instalado sin conectar → 'instalado_sin_conectar', no listo",
              s["estado"] == "instalado_sin_conectar" and s["listo"] is False)
    with _Patch(nlm_setup, installed=lambda: True, authenticated=lambda: True):
        s = nlm_setup.get_status()
        check("10c · instalado + conectado → 'conectado', listo",
              s["estado"] == "conectado" and s["listo"] is True)

    # 11 · _install_worker: secuencia de comandos correcta y shell-safe (args en lista)
    calls: list[list[str]] = []

    def _rec_runner(args, *, timeout):
        calls.append(args)
        return (0, "", "")

    tmp = _Path(tempfile.mkdtemp(prefix="mia-nlm-setup-"))
    # El worker valida bin_path() (no installed()) y escribe el marcador de completitud.
    # _installer_python se parchea para no spawnear la detección real de Python 3.12 en el test.
    with _Patch(nlm_setup, MIA_HOME=tmp, bin_path=lambda: _Path(sys.executable),
                _installer_python=lambda: sys.executable):
        nlm_setup._install_worker(_rec_runner)
    seq_ok = (
        len(calls) == 3
        and all(isinstance(a, list) for a in calls)     # shell=False → args en lista
        and calls[0][1:3] == ["-m", "venv"]             # 1) crea el venv
        and "notebooklm-py[browser]" in calls[1]        # 2) instala el CLI
        and calls[2][1:] == ["-m", "playwright", "install", "chromium"]  # 3) navegador
    )
    check("11 · instalación: venv → pip notebooklm-py[browser] → playwright chromium (shell-safe)",
          seq_ok)
    check("11b · sin error tras instalación simulada exitosa",
          nlm_setup._state.get("install_error") is None)

    # 12 · list_notebooks: parseo de `list --json` + [] si no autenticado
    _list_env: dict = {}

    def _list_runner(args, *, timeout, env=None):
        _list_env["env"] = env  # capturar el entorno para el check de saneo (MAYOR 2)
        return (0, '{"notebooks": [{"id": "nb1", "title": "Caso Pérez"}]}', "")

    import os as _os
    _os.environ["ANTHROPIC_API_KEY"] = "sk-ant-SECRETO-TEST"
    try:
        with _Patch(nlm_setup, bin_path=lambda: sys.executable, authenticated=lambda: True):
            nbs = nlm_setup.list_notebooks(runner=_list_runner)
    finally:
        _os.environ.pop("ANTHROPIC_API_KEY", None)
    check("12c · list_notebooks corre el binario con entorno saneado (secreto real eliminado)",
          isinstance(_list_env.get("env"), dict)
          and "ANTHROPIC_API_KEY" not in _list_env["env"])
    check("12 · list_notebooks parsea id+titulo del JSON",
          nbs == [{"id": "nb1", "titulo": "Caso Pérez"}])
    with _Patch(nlm_setup, bin_path=lambda: sys.executable, authenticated=lambda: False):
        check("12b · list_notebooks → [] si la cuenta no está conectada (no consulta)",
              nlm_setup.list_notebooks(runner=_list_runner) == [])

    # 13 · confirm_login sin login en curso → mensaje amable, sin crash
    res = nlm_setup.confirm_login()
    check("13 · confirm_login sin conexión en curso → no crashea y avisa",
          isinstance(res, dict) and "mensaje" in res)

    # 14 · _auth_signals_fail: detecta "no conectado" por TEXTO (no por exit code)
    check("14 · señal 'Storage file not found' → no conectado",
          nlm_setup._auth_signals_fail("xxx Storage file not found yyy"))
    check("14b · 'Storage exists' + 'fail' → no conectado",
          nlm_setup._auth_signals_fail("Storage exists: FAIL"))
    check("14c · 'AUTH_REQUIRED' → no conectado",
          nlm_setup._auth_signals_fail("error: AUTH_REQUIRED"))
    check("14d · salida limpia → conectado (sin señales)",
          not nlm_setup._auth_signals_fail("Storage exists: ok\nSID cookie: ok"))

    # 15 · verify_auth: auth check limpio + list exit 0 → True; señales o list-fail → False
    def _auth_runner(good_auth, list_code):
        def _r(args, *, timeout, env=None):
            if len(args) > 1 and args[1] == "auth":
                # exit 0 SIEMPRE (reproduce 'imprime error pero devuelve 0'); el texto decide.
                return (0, "Storage exists: ok\nSID cookie: ok" if good_auth else "AUTH_REQUIRED", "")
            return (list_code, '{"notebooks": []}', "")
        return _r

    with _Patch(nlm_setup, bin_path=lambda: _Path(sys.executable)):
        check("15 · verify_auth: auth ok + list ok → conectado",
              nlm_setup.verify_auth(runner=_auth_runner(True, 0)) is True)
        check("15b · verify_auth: auth con señal de fallo (aunque exit 0) → NO conectado",
              nlm_setup.verify_auth(runner=_auth_runner(False, 0)) is False)
        check("15c · verify_auth: auth ok pero list falla → NO conectado (bug 'conectado pero lista falla')",
              nlm_setup.verify_auth(runner=_auth_runner(True, 1)) is False)


async def _run_async() -> None:
    await test_gate()
    await test_consult()


def main() -> int:
    print("== CP-NLM · candado de confidencialidad de NotebookLM (consulta en vivo) ==")
    asyncio.run(_run_async())
    test_client()
    test_setup()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("notebooklm gate OK — la consulta a Google no sale sin política≠soberano + opt-in.")
        return 0
    print("notebooklm gate FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
