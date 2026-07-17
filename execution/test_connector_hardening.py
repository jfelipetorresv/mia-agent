"""
Mia · test_connector_hardening.py — gate de CP-S3 (endurecimiento de conectores y
streaming + proveedor OpenRouter — cierre de la Ola 1).

Verifica OFFLINE (sin DB, sin red, sin LLM):
  A. Streaming: el turno se CORTA cuando el navegador se desconecta (kill-on-
     disconnect) y el SSE lleva latido (ping) configurado.
  B. Conectores: el subproceso de un CLI externo recibe un entorno SANEADO — sin
     las claves de la instalación; solo rutas del SO + MIA_HOME.
  C. Validación de IDs: require_uuid rechaza ids mal formados con 400 antes de la DB.
  D. Tripwire de secretos: una credencial pegada en un campo que no es para claves
     se detecta y se rechaza (sin filtrar el secreto al mensaje de error).
  E. OpenRouter: entra en la cadena de la política 'nube' SOLO con clave configurada;
     nunca en 'suscripcion'/'soberano'; el alias existe en litellm_config.yaml.

Exit 0 = PASS · 1 = FAIL.   .venv\\Scripts\\python.exe execution\\test_connector_hardening.py
"""
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

_results: list = []


def check(name: str, ok) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


async def run_gate() -> None:
    from mia.api.routes import stream as stream_mod
    from mia.api.routes._common import require_uuid
    from mia.gateway.agent_hub import AgentHub, sanitize_subprocess_env, _ENV_ALLOWLIST
    from mia.security import assert_no_stray_secret, contains_secret
    from mia.agent import llm
    from mia import config
    from fastapi import HTTPException

    # ── A · streaming kill-on-disconnect + heartbeat ─────────────────────────
    class _FakeGraph:
        def __init__(self, n):
            self.consumed = 0
            self._n = n

        async def astream(self, turn_input, cfg, stream_mode="updates"):
            for i in range(self._n):
                self.consumed += 1
                yield {"intake": {}}  # nodo benigno (no toca DB, no es interrupt)

    # Desconexión tras el 2º chunk: el bucle debe romperse y NO consumir los 10.
    state = {"calls": 0}

    async def _disconnect_after_2():
        state["calls"] += 1
        return state["calls"] > 2

    g = _FakeGraph(10)
    events = [ev async for ev in stream_mod._stream_turn_events(
        g, {}, {}, "t-1", "m-1", _disconnect_after_2)]
    check("s3-01 · el turno se CORTA al desconectarse el navegador (no consume todo)",
          g.consumed <= 3 and g.consumed < 10)
    check("s3-02 · antes de cortar sí emitió avance (no muere en silencio)",
          len(events) >= 1)

    # Nunca desconectado: consume el stream completo (regresión: no rompe de más).
    g2 = _FakeGraph(4)

    async def _never():
        return False

    evs2 = [ev async for ev in stream_mod._stream_turn_events(
        g2, {}, {}, "t-1", "m-1", _never)]
    check("s3-03 · sin desconexión el turno consume el stream completo",
          g2.consumed == 4 and len(evs2) == 4)
    check("s3-04 · el SSE tiene latido (ping) configurado",
          isinstance(stream_mod.SSE_PING_SECONDS, int) and stream_mod.SSE_PING_SECONDS > 0)

    # Revisión capa 2 (bloqueante): al cortar por desconexión se BORRA el checkpoint
    # a medias, para que el asunto no quede atascado (409 engañoso en el próximo turno).
    class _FakeCheckpointer:
        def __init__(self):
            self.deleted = []

        async def adelete_thread(self, thread_id):
            self.deleted.append(thread_id)

    cfg_thread = {"configurable": {"thread_id": "t-1:m-1"}}
    state["calls"] = 0
    cp_cut = _FakeCheckpointer()
    _ = [ev async for ev in stream_mod._stream_turn_events(
        _FakeGraph(10), {}, cfg_thread, "t-1", "m-1", _disconnect_after_2,
        checkpointer=cp_cut)]
    check("s3-04b · al cortar por desconexión se limpia el checkpoint a medias",
          cp_cut.deleted == ["t-1:m-1"])
    cp_full = _FakeCheckpointer()
    _ = [ev async for ev in stream_mod._stream_turn_events(
        _FakeGraph(3), {}, cfg_thread, "t-1", "m-1", _never, checkpointer=cp_full)]
    check("s3-04c · sin desconexión NO se borra el checkpoint (el turno vive)",
          cp_full.deleted == [])

    # ── B · entorno saneado del subproceso ───────────────────────────────────
    hostile_env = {
        "PATH": "/usr/bin", "SystemRoot": "C:/Windows", "MIA_HOME": "D:/mia",
        "ANTHROPIC_API_KEY": "sk-ant-secreta", "VOYAGE_API_KEY": "pa-secreta",
        "PG_PASSWORD": "clavedb", "DATABASE_URL": "postgres://u:p@h/db",
        "JWT_SECRET": "jwtsecreto", "TELEGRAM_BOT_TOKEN": "123:AAsecreto",
        "OPENROUTER_API_KEY": "sk-or-secreta",
    }
    clean = sanitize_subprocess_env(hostile_env)
    check("s3-05 · el entorno saneado conserva PATH/SystemRoot/MIA_HOME",
          clean.get("PATH") == "/usr/bin" and "SystemRoot" in clean
          and clean.get("MIA_HOME") == "D:/mia")
    secret_names = ("ANTHROPIC_API_KEY", "VOYAGE_API_KEY", "PG_PASSWORD",
                    "DATABASE_URL", "JWT_SECRET", "TELEGRAM_BOT_TOKEN", "OPENROUTER_API_KEY")
    check("s3-06 · NINGUNA clave de la instalación se hereda al subproceso",
          all(n not in clean for n in secret_names))
    check("s3-07 · fuerza PYTHONUNBUFFERED=1", clean.get("PYTHONUNBUFFERED") == "1")

    # invoke() pasa el entorno saneado al runner (integración).
    captured = {}

    def _recorder(args, *, cwd=None, timeout=None, env=None):
        captured["env"] = env
        return (0, "salida", "")

    import tempfile, os as _os
    binp = _os.path.join(tempfile.mkdtemp(), "fake.exe")
    open(binp, "w").close()
    hub = AgentHub(runner=_recorder,
                   env={"MIA_ANTIGRAVITY_BIN": binp, "PATH": "/usr/bin",
                        "ANTHROPIC_API_KEY": "sk-ant-secreta"})
    hub.invoke_antigravity("investiga", "t-1")
    check("s3-08 · invoke() entrega al runner el entorno saneado (sin claves)",
          captured["env"] is not None and "ANTHROPIC_API_KEY" not in captured["env"]
          and captured["env"].get("PATH") == "/usr/bin")

    # ── C · validación de IDs ────────────────────────────────────────────────
    good = "00000000-0000-0000-0000-000000000001"
    check("s3-09 · require_uuid acepta un UUID válido (lo devuelve)",
          require_uuid(good, "propuesta") == good)
    for bad in ("../../etc/passwd", "1 OR 1=1", "abc", ""):
        try:
            require_uuid(bad, "propuesta")
            ok = False
        except HTTPException as exc:
            ok = exc.status_code == 400
        check(f"s3-10 · require_uuid rechaza id inválido con 400: {bad!r}", ok)

    # ── D · tripwire de secretos ─────────────────────────────────────────────
    for label, val in [("sk- prefix", "sk-abc123def456ghi789jkl"),
                       ("pinecone pcsk_", "pcsk_ABCDEFGH1234567890abcd"),
                       ("telegram", "123456789:AAHf9x_zzQwErTy012345678901234567890abcd"),
                       ("jwt", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.abc123def456ghijk"),
                       ("connstr", "postgres://mia:ClaveSecreta@host/db")]:
        check(f"s3-11 · contains_secret detecta {label}", contains_secret(val))
    for benign in ("Índice mia-legal", "artículo 90 responsabilidad", "api_key del despacho", ""):
        check(f"s3-12 · contains_secret NO marca texto de negocio: {benign!r}",
              not contains_secret(benign))

    # assert_no_stray_secret: la clave en su campo designado pasa; en otro, lanza.
    try:
        assert_no_stray_secret(
            {"pinecone": {"api_key": "pcsk_ABCDEFGH1234567890abcd", "index_name": "mia-legal"}},
            allow_paths=("pinecone.api_key",))
        allowed_ok = True
    except ValueError:
        allowed_ok = False
    check("s3-13 · la clave en su campo designado (allow_paths) NO dispara el tripwire",
          allowed_ok)

    try:
        assert_no_stray_secret({"index_name": "pcsk_ABCDEFGH1234567890abcd"})
        stray_raised = False
        err = ""
    except ValueError as exc:
        stray_raised = True
        err = str(exc)
    check("s3-14 · una clave en un campo NO designado dispara el tripwire", stray_raised)
    check("s3-15 · el error del tripwire NO filtra el secreto ni su forma",
          "pcsk_" not in err and "ABCDEFGH" not in err and "index_name" in err)

    # ── E · OpenRouter en la política 'nube' ─────────────────────────────────
    check("s3-16 · config expone OPENROUTER_API_KEY", hasattr(config, "OPENROUTER_API_KEY"))
    yaml_txt = (ROOT / "litellm_config.yaml").read_text(encoding="utf-8")
    check("s3-17 · litellm_config.yaml define el alias openrouter-sonnet",
          "openrouter-sonnet" in yaml_txt and "os.environ/OPENROUTER_API_KEY" in yaml_txt)

    saved_key = config.OPENROUTER_API_KEY
    saved_client = llm._client
    try:
        # CON clave + OPT-IN del despacho: openrouter entra en main/curator de 'nube'.
        config.OPENROUTER_API_KEY = "sk-or-de-prueba"
        tok = llm.set_model_policy("nube")
        or_tok = llm.set_openrouter_allowed(True)
        try:
            chain_main = llm.resolve_fallback_chain("main")
            chain_cur = llm.resolve_fallback_chain("curator")
        finally:
            llm.reset_openrouter_allowed(or_tok)
            llm.reset_model_policy(tok)
        check("s3-18 · con clave + opt-in, 'nube' incluye openrouter en main y curator",
              llm.OPENROUTER_ALIAS in chain_main and llm.OPENROUTER_ALIAS in chain_cur)
        check("s3-19 · openrouter va ANTES del modelo local (respaldo de nube primero)",
              chain_main.index(llm.OPENROUTER_ALIAS) < chain_main.index("mia-local"))

        # Revisión capa 2 (H3, confidencialidad): con clave pero SIN opt-in del
        # despacho, NO se enruta a OpenRouter (los datos del cliente no salen a un
        # tercero por el mero hecho de que exista una clave global).
        tok = llm.set_model_policy("nube")
        or_tok = llm.set_openrouter_allowed(False)
        try:
            chain_no_optin = llm.resolve_fallback_chain("main")
        finally:
            llm.reset_openrouter_allowed(or_tok)
            llm.reset_model_policy(tok)
        check("s3-18b · con clave pero SIN opt-in del despacho, 'nube' NO usa openrouter",
              llm.OPENROUTER_ALIAS not in chain_no_optin)

        # 'soberano' NUNCA usa openrouter (aunque haya clave + opt-in): es la muralla de
        # confidencialidad — con esa política NADA sale del equipo del despacho.
        tok = llm.set_model_policy("soberano")
        or_tok = llm.set_openrouter_allowed(True)
        try:
            c_sob = llm.resolve_fallback_chain("main")
        finally:
            llm.reset_openrouter_allowed(or_tok)
            llm.reset_model_policy(tok)
        check("s3-20 · 'soberano' no usa openrouter aunque haya clave + opt-in",
              llm.OPENROUTER_ALIAS not in c_sob)

        # 'suscripcion' SÍ lo usa como overflow ("más uso"). La sesión 47 (b582541,
        # decisión de Pipe "Ambas") extendió el respaldo de 'nube' a 'suscripcion': cuando
        # la suscripción no alcanza, el trabajo sigue por OpenRouter en vez de degradar.
        # El test fijaba la regla vieja (CP-S3, solo 'nube') y quedó desactualizado.
        # Lo que se protege sigue intacto y se comprueba abajo: sin opt-in NO se enruta.
        tok = llm.set_model_policy("suscripcion")
        or_tok = llm.set_openrouter_allowed(True)
        try:
            c_sus = llm.resolve_fallback_chain("main")
        finally:
            llm.reset_openrouter_allowed(or_tok)
            llm.reset_model_policy(tok)
        check("s3-20b · 'suscripcion' usa openrouter como overflow con clave + opt-in",
              llm.OPENROUTER_ALIAS in c_sus
              and c_sus.index(llm.OPENROUTER_ALIAS) < c_sus.index("mia-local"))

        # Y el consentimiento manda también aquí: sin opt-in del despacho, la suscripción
        # NO enruta a un tercero por el mero hecho de que exista una clave.
        tok = llm.set_model_policy("suscripcion")
        or_tok = llm.set_openrouter_allowed(False)
        try:
            c_sus_no = llm.resolve_fallback_chain("main")
        finally:
            llm.reset_openrouter_allowed(or_tok)
            llm.reset_model_policy(tok)
        check("s3-20c · 'suscripcion' SIN opt-in no usa openrouter (consentimiento, regla 2)",
              llm.OPENROUTER_ALIAS not in c_sus_no)

        # SIN clave: 'nube' queda como antes (no aparece un alias con auth muerta).
        config.OPENROUTER_API_KEY = ""
        tok = llm.set_model_policy("nube")
        or_tok = llm.set_openrouter_allowed(True)
        try:
            chain_nokey = llm.resolve_fallback_chain("main")
        finally:
            llm.reset_openrouter_allowed(or_tok)
            llm.reset_model_policy(tok)
        check("s3-21 · sin clave, 'nube' NO incluye openrouter (cadena intacta)",
              llm.OPENROUTER_ALIAS not in chain_nokey and "claude-sonnet" in chain_nokey
              and "mia-local" in chain_nokey)

        # Revisión capa 2 (H2): openrouter sin saldo/clave inválida (AUTH) NO mata la
        # cadena — se salta al modelo local, que responde. Cliente falso programado
        # por alias (mismo patrón que test_llm_fallback).
        from types import SimpleNamespace
        config.OPENROUTER_API_KEY = "sk-or-de-prueba"
        llm.time.sleep = lambda *_a, **_k: None  # sin backoff real

        class _FakeCompletions:
            def __init__(self, script):
                self.script = script
                self.calls = []

            def create(self, **kwargs):
                model = kwargs["model"]
                self.calls.append(model)
                out = self.script[model]
                if isinstance(out, BaseException):
                    raise out
                return out

        def _http(status, msg=""):
            e = Exception(msg or f"http {status}")
            e.status_code = status
            return e

        def _ok(text):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=text))], usage=None)

        fc = _FakeCompletions({
            "claude-sonnet": _http(429, "rate limit"),          # saltable → siguiente
            llm.OPENROUTER_ALIAS: _http(402, "payment required"),  # AUTH: NO debe matar
            "mia-local": _ok("respuesta local tras saltar openrouter"),
        })
        llm._client = SimpleNamespace(chat=SimpleNamespace(completions=fc))
        tok = llm.set_model_policy("nube")
        or_tok = llm.set_openrouter_allowed(True)
        try:
            resp = llm.call_llm([{"role": "user", "content": "hola"}], task="main")
        finally:
            llm.reset_openrouter_allowed(or_tok)
            llm.reset_model_policy(tok)
        check("s3-22 · openrouter sin saldo (AUTH/402) NO mata la cadena: cae a mia-local",
              resp.choices[0].message.content == "respuesta local tras saltar openrouter"
              and fc.calls[-1] == "mia-local" and llm.OPENROUTER_ALIAS in fc.calls)
    finally:
        config.OPENROUTER_API_KEY = saved_key
        llm._client = saved_client


if __name__ == "__main__":
    asyncio.run(run_gate())
    passed = sum(1 for _, ok in _results if ok)
    print(f"\n{passed}/{len(_results)} checks PASS")
    if all(ok for _, ok in _results):
        print("conectores y streaming OK — CP-S3 verificado (kill-on-disconnect + "
              "entorno saneado + IDs validados + tripwire + OpenRouter opcional).")
        sys.exit(0)
    sys.exit(1)
