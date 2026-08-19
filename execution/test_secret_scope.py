"""
Mia · test_secret_scope.py — gate de CP-S2 (aislamiento fail-closed de secretos +
redacción de logs — Ola 1 · blindaje de confidencialidad).

Verifica OFFLINE (sin DB, sin red):
  A. Scope de secretos por tenant: sin scope → UnscopedSecretError (NUNCA lee el
     entorno); con scope → solo los secretos de ESE tenant; scopes anidados se
     restauran; el scope viaja a través de async/to_thread (ContextVar).
  B. Redacción: cada familia de credencial del stack de Mia queda enmascarada
     (claves sk-/pa-/pcsk_/AIza, token de bot de Telegram, JWT, NOMBRE=valor,
     campos JSON, headers Authorization, postgres://user:pass@, llave privada,
     query strings) y el texto normal queda intacto.
  C. RedactingFormatter: redacta mensaje Y traceback (exc_info) en el flujo real
     de logging; install_redacting_logging cubre handlers existentes y es
     idempotente.
  D. No desactivable: no existe flag de runtime; mutar el entorno tras el import
     no cambia nada (la redacción no consulta el entorno).

Exit 0 = PASS · 1 = FAIL.       .venv\\Scripts\\python.exe execution\\test_secret_scope.py
"""
import asyncio
import io
import logging
import os
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
    from mia.security import (
        RedactingFormatter,
        UnscopedSecretError,
        current_scoped_tenant,
        get_tenant_secret,
        install_redacting_logging,
        mask_secret,
        redact_text,
        secrets_from_tenant_config,
        tenant_secret_scope,
    )
    from mia.security import redact as redact_mod

    # ── A · scope fail-closed ────────────────────────────────────────────────
    try:
        get_tenant_secret("pinecone_api_key")
        raised = False
    except UnscopedSecretError:
        raised = True
    check("s2-01 · sin scope activo, get_tenant_secret lanza UnscopedSecretError", raised)

    os.environ["PINECONE_API_KEY"] = "clave-global-que-jamas-debe-salir"
    try:
        with tenant_secret_scope("t-A", {"pinecone_api_key": "clave-del-despacho-A"}):
            val = get_tenant_secret("pinecone_api_key")
        check("s2-02 · con scope devuelve la clave DEL TENANT, no la del entorno",
              val == "clave-del-despacho-A")
        with tenant_secret_scope("t-A", {}):
            missing = get_tenant_secret("pinecone_api_key", "def")
        check("s2-03 · con scope pero sin ese secreto -> default (no cae al entorno)",
              missing == "def")
    finally:
        os.environ.pop("PINECONE_API_KEY", None)

    with tenant_secret_scope("t-A", {"k": "va"}):
        with tenant_secret_scope("t-B", {"k": "vb"}):
            inner = (current_scoped_tenant(), get_tenant_secret("k"))
        outer = (current_scoped_tenant(), get_tenant_secret("k"))
    check("s2-04 · scopes anidados: el interior gana y al salir se restaura",
          inner == ("t-B", "vb") and outer == ("t-A", "va"))
    check("s2-05 · al salir del último scope no queda tenant activo",
          current_scoped_tenant() is None)

    async def _in_task():
        with tenant_secret_scope("t-task", {"k": "v-task"}):
            return await asyncio.to_thread(get_tenant_secret, "k")

    check("s2-06 · el scope viaja por await y asyncio.to_thread (ContextVar)",
          await _in_task() == "v-task")

    cfg = {"pinecone": {"api_key": "pk-123456789012345678", "index_name": "mia-legal",
                        "status": "active", "stats": {"total_vector_count": 7}},
           "obsidian_vault_path": "D:/vault"}
    secrets = secrets_from_tenant_config(cfg, tenant_id="tenant-a")
    check("s2-07 · secrets_from_tenant_config extrae SOLO secretos (clave+índice)",
          secrets == {"pinecone_api_key": "pk-123456789012345678",
                      "pinecone_index_name": "mia-legal"})
    check("s2-08 · config vacía/None -> scope vacío (sin semilla del entorno)",
          secrets_from_tenant_config(None, tenant_id="tenant-a") == {}
          and secrets_from_tenant_config({}, tenant_id="tenant-a") == {})

    # ── B · redacción por familias ───────────────────────────────────────────
    check("s2-09 · mask_secret preserva prefijo/sufijo en tokens largos y oculta cortos",
          mask_secret("sk-mia-local-123456789012345") == "sk-mia...2345"
          and mask_secret("corta") == "***" and mask_secret("") == "***")
    check("s2-09b · floor 24 (capa 2 · H5): un secreto de 18-23 chars se oculta ENTERO",
          mask_secret("pa-abcdefghij123456") == "***"
          and mask_secret("pcsk_ABCDEFGH12345678") == "***")
    cases = {
        "sk- (LiteLLM/OpenAI/Anthropic)": ("error con sk-abc123def456ghi789", "abc123def456"),
        "pa- (Voyage)": ("VOYAGE key pa-abcdefghij1234567890", "abcdefghij1234567890"),
        "pcsk_ (Pinecone)": ("pinecone pcsk_AbCdEfGh123456789", "AbCdEfGh123456789"),
        "AIza (Google)": ("g AIzaSyA1234567890abcdefghijklmnopqrst", "SyA1234567890abcdefghijklmnopqrst"),
        "telegram bot en URL": ("GET https://api.telegram.org/bot123456789:AAHf9x_zzQwErTy012345678901234/getUpdates",
                                "AAHf9x_zzQwErTy"),
        "telegram token suelto": ("token=123456789:AAHf9x_zzQwErTy012345678901234abc", "AAHf9x_zzQwErTy"),
        "JWT": ("Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0LTEifQ.abc123def456ghi789", "eyJzdWIiOiJ0LTEifQ"),
        "ENV assign": ("PG_PASSWORD=SuperSecreta2026!xyz arrancando", "SuperSecreta2026!xyz"),
        "campo JSON": ('config {"api_key": "clave-secreta-json-123456"}', "clave-secreta-json-123456"),
        "Authorization header": ("headers {'Authorization': 'Bearer tok_abcdef123456789012'}", "tok_abcdef123456789012"),
        "postgres connstr": ("postgresql://mia_app:MiClaveDB99@127.0.0.1:5432/mia", "MiClaveDB99"),
        "conninfo libpq (capa 2 · H3)": ("connection failed: host=db user=mia_app "
                                         "password=MiClaveDB99 sslmode=require", "MiClaveDB99"),
        "query string": ("GET /cb?code=4/abc-defghi_jkl&state=x", "4/abc-defghi_jkl"),
    }
    for label, (raw, secret_part) in cases.items():
        red = redact_text(raw)
        check(f"s2-10 · redacta {label}", secret_part not in red)
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow…\n-----END RSA PRIVATE KEY-----"
    check("s2-11 · redacta bloques de llave privada PEM completos",
          "MIIEow" not in redact_text(pem))
    normal = ("El artículo 90 de la CP y la Sentencia C-333 de 1996; el término venció "
              "el 14 de marzo (folio 12). matter_id=7 no es un secreto de 4 chars: ok.")
    check("s2-12 · el texto jurídico normal queda INTACTO", redact_text(normal) == normal)
    biz = '{"key": "articulo-90-responsabilidad"} y código=ABC-1234 del radicado'
    check("s2-12b · campos de negocio genéricos NO se redactan (capa 2 · H6)",
          redact_text(biz) == biz)
    check("s2-13 · idempotente: redactar dos veces no re-rompe la máscara",
          redact_text(redact_text("clave sk-abc123def456ghi789"))
          == redact_text("clave sk-abc123def456ghi789"))
    n_familias = len(redact_mod._PREFIX_PATTERNS) + 9  # prefijos + 9 familias contextuales
    check(f"s2-14 · cobertura de ~40 patrones (hoy: {n_familias})", n_familias >= 38)

    # ── C · flujo real de logging ────────────────────────────────────────────
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(RedactingFormatter("%(levelname)s %(name)s: %(message)s"))
    lg = logging.getLogger("mia.test.s2")
    lg.addHandler(handler)
    lg.setLevel(logging.INFO)
    lg.propagate = False
    try:
        lg.warning("fallo con la clave sk-abc123def456ghi789jkl012 del proveedor")
        try:
            raise RuntimeError(
                "httpx error en https://api.telegram.org/bot123456789:AAHf9x_zzQwErTy012345678901234/sendMessage")
        except RuntimeError:
            lg.exception("turno falló (chat_id=%s)", 42)
    finally:
        lg.removeHandler(handler)
    logged = buf.getvalue()
    check("s2-15 · el formatter redacta el mensaje del log",
          "abc123def456" not in logged and "sk-abc" in logged
          and "del proveedor" in logged)
    check("s2-16 · el formatter redacta el TRACEBACK (exc_info) — el caso Telegram",
          "AAHf9x_zzQwErTy" not in logged and "RuntimeError" in logged
          and "chat_id=42" in logged)

    # Revisión capa 2 (H1): install debe ENVOLVER (no reemplazar) los formatters
    # REALES de uvicorn — sus subclases inyectan campos propios (levelprefix,
    # client_addr…) y reconstruirlas como Formatter plano rompía cada registro
    # del servidor Y apagaba la redacción en los access logs.
    import uvicorn.logging as uvlog

    root = logging.getLogger()
    plain = logging.StreamHandler(io.StringIO())
    plain.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(plain)

    uv_buf = io.StringIO()
    uv_handler = logging.StreamHandler(uv_buf)
    uv_handler.setFormatter(uvlog.DefaultFormatter("%(levelprefix)s %(message)s",
                                                   use_colors=False))
    uv_logger = logging.getLogger("uvicorn.error.s2test")
    uv_logger.addHandler(uv_handler)
    uv_logger.setLevel(logging.INFO)
    uv_logger.propagate = False

    acc_buf = io.StringIO()
    acc_handler = logging.StreamHandler(acc_buf)
    acc_handler.setFormatter(uvlog.AccessFormatter(
        '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
        use_colors=False))
    acc_logger = logging.getLogger("uvicorn.access.s2test")
    acc_logger.addHandler(acc_handler)
    acc_logger.setLevel(logging.INFO)
    acc_logger.propagate = False

    brace_buf = io.StringIO()
    brace_handler = logging.StreamHandler(brace_buf)
    brace_handler.setFormatter(logging.Formatter("{message}", style="{"))
    brace_logger = logging.getLogger("mia.test.s2brace")
    brace_logger.addHandler(brace_handler)
    brace_logger.setLevel(logging.INFO)
    brace_logger.propagate = False

    try:
        install_redacting_logging()
        before = plain.formatter
        install_redacting_logging()
        check("s2-17 · install envuelve todos los handlers existentes",
              type(plain.formatter).__name__ == "_RedactingWrapper"
              and type(uv_handler.formatter).__name__ == "_RedactingWrapper")
        check("s2-18 · install es idempotente (no re-envuelve lo ya envuelto)",
              plain.formatter is before)

        uv_logger.info("Uvicorn running con clave sk-abc123def456ghi789")
        uv_out = uv_buf.getvalue()
        check("s2-17b · el DefaultFormatter de uvicorn SIGUE funcionando y redacta (H1)",
              "INFO" in uv_out and "Uvicorn running" in uv_out
              and "abc123def456" not in uv_out)

        acc_logger.info('%s - "%s %s HTTP/%s" %s', "127.0.0.1:5000", "GET",
                        "/cb?token=SECRETTOKEN1234567890123456", "1.1", 200)
        acc_out = acc_buf.getvalue()
        check("s2-17c · el AccessFormatter de uvicorn formatea y redacta la URL (H1)",
              "127.0.0.1:5000" in acc_out and "GET" in acc_out
              and "SECRETTOKEN" not in acc_out)

        brace_logger.info("clave sk-abc123def456ghi789 con style llaves")
        brace_out = brace_buf.getvalue()
        check("s2-17d · un formatter style='{' no crashea el install y redacta",
              "style llaves" in brace_out and "abc123def456" not in brace_out)
    finally:
        root.removeHandler(plain)
        uv_logger.removeHandler(uv_handler)
        acc_logger.removeHandler(acc_handler)
        brace_logger.removeHandler(brace_handler)

    # ── D · no desactivable en runtime ───────────────────────────────────────
    os.environ["MIA_REDACT_SECRETS"] = "false"
    os.environ["HERMES_REDACT_SECRETS"] = "false"
    try:
        still = redact_text("clave sk-abc123def456ghi789")
        check("s2-19 · mutar el entorno NO apaga la redacción (no hay interruptor)",
              "abc123def456" not in still)
    finally:
        os.environ.pop("MIA_REDACT_SECRETS", None)
        os.environ.pop("HERMES_REDACT_SECRETS", None)
    check("s2-20 · el módulo no expone flag de deshabilitación",
          not any(n for n in vars(redact_mod)
                  if "ENABLED" in n.upper() or "DISABLE" in n.upper()))

    # ── E · cableado (el entrypoint y el puente instalan la redacción) ───────
    main_src = (ROOT / "backend" / "mia" / "api" / "main.py").read_text(encoding="utf-8")
    bridge_src = (ROOT / "backend" / "mia" / "channels" / "telegram_bridge.py").read_text(encoding="utf-8")
    check("s2-21 · api/main.py instala la redacción (import + lifespan)",
          main_src.count("install_redacting_logging()") >= 2)
    check("s2-22 · el puente de Telegram instala la redacción",
          "install_redacting_logging()" in bridge_src)


if __name__ == "__main__":
    asyncio.run(run_gate())
    passed = sum(1 for _, ok in _results if ok)
    print(f"\n{passed}/{len(_results)} checks PASS")
    if all(ok for _, ok in _results):
        print("secretos y logs OK — CP-S2 verificado (scope fail-closed por tenant + "
              "redacción de credenciales siempre encendida).")
        sys.exit(0)
    sys.exit(1)
