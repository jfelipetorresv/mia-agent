"""
Mia · test_welcome_keys.py — gate de F3 (bienvenida + activación de llaves, sesión 44).

Verifica con DB REAL y LLM/Voyage FAKE por monkeypatch (sin red):

  (s) GET /api/welcome/status — público (sin Bearer) con campos no sensibles
      (instalado, hay_usuario, faltan_llaves, motor_detectado) simulando
      DB "virgen" (hay_usuario=false) y "con usuario" (true); con Bearer
      enriquece con datos reales del tenant (onboarding_completo, política).
  (i) `_instalado()` — MIA_APP_DIR / IS_PRODUCTION / sys.frozen, cada uno
      basta por sí solo.
  (a) 401 sin token en /api/welcome/keys y /api/welcome/keys/test.
  (w) POST /api/welcome/keys — escritura atómica que PRESERVA el resto del
      `.env` (comentarios, orden, secretos existentes: JWT_SECRET, PG_*,
      LITELLM_*) y agrega/actualiza SOLO las claves pedidas; hot-reload EN
      CALIENTE SOLO de la clave de búsqueda (config.VOYAGE_API_KEY, in-process);
      `respaldo` (Anthropic) y `openrouter` son DIFERIDAS (las lee el proxy al
      arrancar): NO tocan config ni os.environ en vivo, solo el `.env`, y se
      avisa en llano "cierra y reabre Mia"; string vacío ignorado sin bloquear la
      clave hermana; longitud excesiva → mensaje en llano (no 422 en inglés);
      faltan_llaves se calcula del `.env` en disco; idempotencia.
  (r) Rechazo de clave con salto de línea (no persiste, no llama al proveedor).
  (t) POST /api/welcome/keys/test — ping fake OK / error en llano SIN
      filtrar la clave ni la traza técnica en la respuesta.
  (g) §G: ninguna respuesta trae jerga técnica (tenant/api/endpoint/backend/
      voyage/anthropic/openrouter/embeddings/env…).

Limpia sus datos y restaura todo estado global mutado (config.PROJECT_ROOT,
config.VOYAGE_API_KEY/OPENROUTER_API_KEY, os.environ, litellm.embedding/
completion) en `finally`. HALT si falla (CLAUDE.md §G). Exit 0 = PASS · 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_welcome_keys.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import sys
import tempfile
import time
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

import init_profiles  # noqa: E402
import init_users  # noqa: E402
import init_welcome  # noqa: E402
from mia import config  # noqa: E402
from mia.api.routes import welcome as welcome_mod  # noqa: E402

PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"),
    port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"),
    user="postgres",
    password=os.getenv("PG_PASSWORD", ""),
)

_results: list[tuple[str, bool]] = []

# §G: ninguna respuesta puede traer jerga técnica. Base = el mismo criterio de
# test_setup_wizard.py (_FORBIDDEN_RE), extendido con los términos propios de
# este feature (proveedores/llaves) que §G también prohíbe nombrar.
_FORBIDDEN_RE = re.compile(
    r"\b(tenant|cli|api|endpoint|backend|jsonb|winget|rls|"
    r"voyage|anthropic|openrouter|embedding|embeddings|env)\b",
    re.IGNORECASE,
)


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def sb() -> psycopg.Connection:
    return psycopg.connect(autocommit=True, **PG)


def cleanup(tenant_ids: list[str]) -> None:
    if not tenant_ids:
        return
    with sb() as c:
        c.execute("DELETE FROM tenants WHERE id = ANY(%s::uuid[])", (tenant_ids,))


def collect_strings(obj, out: list[str]) -> None:
    """Recolecta todos los strings de una respuesta JSON (recursivo) para
    auditar §G sobre TODO el texto que la respuesta pudo mostrarle al abogado."""
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            collect_strings(v, out)


class FakeLLM:
    """Simula litellm.embedding/litellm.completion (sin red). El gate NO llama
    a Voyage ni a Anthropic de verdad — solo prueba el pegamento del endpoint."""

    def __init__(self) -> None:
        self.should_fail = False
        self.embed_calls: list[dict] = []
        self.completion_calls: list[dict] = []
        self._orig_embedding = None
        self._orig_completion = None

    def install(self) -> None:
        import litellm

        self._orig_embedding = litellm.embedding
        self._orig_completion = litellm.completion
        litellm.embedding = self._fake_embedding
        litellm.completion = self._fake_completion

    def restore(self) -> None:
        import litellm

        if self._orig_embedding is not None:
            litellm.embedding = self._orig_embedding
        if self._orig_completion is not None:
            litellm.completion = self._orig_completion

    def _fake_embedding(self, *, model, input, api_key, timeout=None, num_retries=None):
        self.embed_calls.append({"model": model, "api_key": api_key})
        if self.should_fail:
            raise RuntimeError(f"simulated upstream failure api_key={api_key}")
        return SimpleNamespace(data=[{"embedding": [0.0] * 8}])

    def _fake_completion(self, *, model, messages, api_key, max_tokens=None,
                          timeout=None, num_retries=None):
        self.completion_calls.append({"model": model, "api_key": api_key})
        if self.should_fail:
            raise RuntimeError(f"simulated upstream failure api_key={api_key}")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])


def check_instalado() -> None:
    """`_instalado()` es OR puro: cualquiera de los tres basta por sí solo."""
    orig_app_dir = os.environ.get("MIA_APP_DIR")
    orig_prod = config.IS_PRODUCTION
    try:
        os.environ.pop("MIA_APP_DIR", None)
        config.IS_PRODUCTION = False
        if hasattr(sys, "frozen"):
            delattr(sys, "frozen")
        check("i1 · sin MIA_APP_DIR/producción/frozen → no instalado",
              welcome_mod._instalado() is False)

        os.environ["MIA_APP_DIR"] = str(ROOT)
        check("i2 · MIA_APP_DIR presente → instalado", welcome_mod._instalado() is True)
        os.environ.pop("MIA_APP_DIR", None)

        config.IS_PRODUCTION = True
        check("i3 · IS_PRODUCTION → instalado", welcome_mod._instalado() is True)
        config.IS_PRODUCTION = False

        sys.frozen = True
        check("i4 · sys.frozen (empaquetado) → instalado", welcome_mod._instalado() is True)
        delattr(sys, "frozen")
    finally:
        if orig_app_dir is not None:
            os.environ["MIA_APP_DIR"] = orig_app_dir
        else:
            os.environ.pop("MIA_APP_DIR", None)
        config.IS_PRODUCTION = orig_prod
        if hasattr(sys, "frozen"):
            delattr(sys, "frozen")


def run_checks(client, fake: FakeLLM, tenants: list[str]) -> None:
    stamp = int(time.time() * 1000)

    # ── (s) /welcome/status público, campos no sensibles, simulando hay_usuario ──
    orig_hay_usuario = welcome_mod._hay_usuario

    async def _no_hay_usuario() -> bool:
        return False

    async def _si_hay_usuario() -> bool:
        return True

    try:
        welcome_mod._hay_usuario = _no_hay_usuario
        r_virgen = client.get("/api/welcome/status")
        body_virgen = r_virgen.json()
        check("s1 · GET /welcome/status SIN Bearer → 200 (es público)",
              r_virgen.status_code == 200)
        check("s2 · DB 'virgen' simulada → hay_usuario=false",
              body_virgen.get("hay_usuario") is False)
        check("s3 · estructura completa (instalado/faltan_llaves/motor_detectado/política)",
              {"instalado", "hay_usuario", "faltan_llaves", "onboarding_completo",
               "motor_detectado", "politica"} <= set(body_virgen))
        check("s4 · sin sesión: onboarding_completo por defecto = false (no revela despacho)",
              body_virgen.get("onboarding_completo") is False)

        welcome_mod._hay_usuario = _si_hay_usuario
        r_con_usuario = client.get("/api/welcome/status")
        check("s5 · con usuario simulado → hay_usuario=true",
              r_con_usuario.json().get("hay_usuario") is True)
    finally:
        welcome_mod._hay_usuario = orig_hay_usuario

    # ── registro real: valida el enriquecimiento CON sesión ──
    ra = client.post("/api/auth/register", json={
        "email": f"welcome-{stamp}-a@example.com", "password": "Password-12345",
        "firm_name": "Welcome Test A"})
    assert ra.status_code == 201, "registro falló"
    tenant_a = ra.json()["tenant_id"]
    tenants.append(tenant_a)
    auth_a = {"Authorization": f"Bearer {ra.json()['token']}"}

    r_auth = client.get("/api/welcome/status", headers=auth_a)
    body_auth = r_auth.json()
    check("s6 · con Bearer válido → 200 y datos reales del tenant nuevo",
          r_auth.status_code == 200 and body_auth["onboarding_completo"] is False
          and body_auth["politica"] == "suscripcion")
    # Camino REAL (sin monkeypatch): tras registrar, la función SECURITY DEFINER
    # `mia_any_tenant_exists` ve el despacho pese al RLS FORCE de `tenants`.
    check("s6b · hay_usuario REAL = true tras registrar (SECURITY DEFINER supera RLS)",
          body_auth["hay_usuario"] is True)

    # Simula onboarding completado (monkeypatch, mismo criterio que Detectors de
    # test_setup_wizard.py) y una política distinta persistida en tenant_settings.
    orig_soul_status = welcome_mod.soul_status
    try:
        welcome_mod.soul_status = lambda tid: {"completed": True}
        with sb() as c:
            c.execute("UPDATE tenant_settings SET config = jsonb_set(config, '{model_policy}', "
                      "'\"nube\"') WHERE tenant_id = %s::uuid", (tenant_a,))
        r_after = client.get("/api/welcome/status", headers=auth_a).json()
        check("s7 · onboarding_completo/política reflejan el estado real del tenant",
              r_after["onboarding_completo"] is True and r_after["politica"] == "nube")
    finally:
        welcome_mod.soul_status = orig_soul_status

    # ── (a) 401 sin token ──
    check("a1 · POST /welcome/keys sin token → 401",
          client.post("/api/welcome/keys", json={"busqueda": "pa-x"}).status_code == 401)
    check("a2 · POST /welcome/keys/test sin token → 401",
          client.post("/api/welcome/keys/test",
                      json={"tipo": "busqueda", "clave": "pa-x"}).status_code == 401)

    # ── (w) escritura atómica: .env temporal con secretos preexistentes ──
    tmp_dir = Path(tempfile.mkdtemp(prefix="mia-welcome-gate-"))
    env_path = tmp_dir / ".env"
    original_env_text = (
        "# .env de prueba — no tocar los secretos de abajo\n"
        "JWT_SECRET=no-debe-cambiar-nunca-1234567890\n"
        "PG_PASSWORD=tampoco-debe-cambiar\n"
        "LITELLM_API_KEY=sk-mia-no-debe-cambiar\n"
        "\n"
        "VOYAGE_API_KEY=\n"
        "MIA_ENV=prod\n"
    )
    env_path.write_text(original_env_text, encoding="utf-8")

    orig_project_root = config.PROJECT_ROOT
    orig_voyage = config.VOYAGE_API_KEY
    orig_openrouter = config.OPENROUTER_API_KEY
    orig_environ_voyage = os.environ.get("VOYAGE_API_KEY")
    orig_environ_openrouter = os.environ.get("OPENROUTER_API_KEY")
    orig_environ_anthropic = os.environ.get("ANTHROPIC_API_KEY")

    clave_busqueda = "pa-buenaclavedebusqueda1234567890"
    clave_respaldo = "sk-ant-buenaclavederespaldo1234567890"

    all_response_strings: list[str] = []

    try:
        config.PROJECT_ROOT = tmp_dir

        # ── (p3) status lee faltan_llaves del .env EN DISCO (no de os.environ) ──
        # .env semilla del tmp: VOYAGE_API_KEY= vacío y sin ANTHROPIC → ambas faltan.
        st_virgen = client.get("/api/welcome/status", headers=auth_a).json()
        check("p3a · DB virgen (.env con VOYAGE vacío) → faltan_llaves.busqueda = true",
              st_virgen["faltan_llaves"]["busqueda"] is True
              and st_virgen["faltan_llaves"]["respaldo"] is True)

        # snapshots ANTES de escribir: las claves diferidas NO deben tocar el proceso.
        anthropic_env_before = os.environ.get("ANTHROPIC_API_KEY")
        openrouter_env_before = os.environ.get("OPENROUTER_API_KEY")
        openrouter_config_before = getattr(config, "OPENROUTER_API_KEY", None)

        r_write = client.post("/api/welcome/keys", headers=auth_a,
                              json={"busqueda": clave_busqueda, "respaldo": clave_respaldo})
        body_write = r_write.json()
        collect_strings(body_write, all_response_strings)
        check("w1 · POST /welcome/keys guarda busqueda+respaldo → 200",
              r_write.status_code == 200 and body_write["guardado"] == {
                  "busqueda": True, "respaldo": True})
        check("w2 · aviso FUERTE en llano: cerrar y reabrir Mia para activar el motor",
              bool(body_write.get("aviso"))
              and "cierra Mia" in body_write["aviso"]
              and "vuelve a abrirla" in body_write["aviso"])

        written = env_path.read_text(encoding="utf-8")
        check("w3 · preserva comentarios/orden/secretos existentes intactos",
              "# .env de prueba — no tocar los secretos de abajo" in written
              and "JWT_SECRET=no-debe-cambiar-nunca-1234567890" in written
              and "PG_PASSWORD=tampoco-debe-cambiar" in written
              and "LITELLM_API_KEY=sk-mia-no-debe-cambiar" in written
              and "MIA_ENV=prod" in written)
        check("w4 · VOYAGE_API_KEY actualizado con la clave nueva",
              f"VOYAGE_API_KEY={clave_busqueda}" in written)
        check("w5 · ANTHROPIC_API_KEY agregado (no existía) con la clave nueva",
              f"ANTHROPIC_API_KEY={clave_respaldo}" in written)
        check("w6 · sin líneas duplicadas de las claves tocadas",
              written.count("VOYAGE_API_KEY=") == 1
              and written.count("ANTHROPIC_API_KEY=") == 1)
        check("w7 · escritura atómica: no queda archivo .tmp a medias",
              not any(p.name.startswith(".env.") and p.name.endswith(".tmp")
                      for p in tmp_dir.iterdir()))

        check("w8 · hot-reload: config.VOYAGE_API_KEY cambia EN MEMORIA sin reiniciar",
              config.VOYAGE_API_KEY == clave_busqueda
              and os.environ.get("VOYAGE_API_KEY") == clave_busqueda)
        check("w9 · respaldo DIFERIDO: no toca config ni os.environ del proceso vivo "
              "(el proxy la lee al abrir Mia)",
              not hasattr(config, "ANTHROPIC_API_KEY")
              and os.environ.get("ANTHROPIC_API_KEY") == anthropic_env_before)

        # ── (p3) tras escribir, status refleja lo guardado leyendo el .env ──
        st_tras = client.get("/api/welcome/status", headers=auth_a).json()
        check("p3b · tras guardar, faltan_llaves se lee del .env: busqueda/respaldo = false",
              st_tras["faltan_llaves"]["busqueda"] is False
              and st_tras["faltan_llaves"]["respaldo"] is False)

        # ── idempotencia: repetir la misma escritura no cambia nada más ──
        r_write2 = client.post("/api/welcome/keys", headers=auth_a,
                               json={"busqueda": clave_busqueda, "respaldo": clave_respaldo})
        written2 = env_path.read_text(encoding="utf-8")
        check("w10 · idempotente: repetir la escritura deja el .env estable",
              r_write2.status_code == 200 and written2 == written)

        # ── openrouter es DIFERIDA: NO hot-recarga config/os.environ; solo .env + aviso ──
        clave_or = "sk-or-v1-buenaclavedeproveedor1234567890"
        r_or = client.post("/api/welcome/keys", headers=auth_a, json={"openrouter": clave_or})
        body_or = r_or.json()
        collect_strings(body_or, all_response_strings)
        written_or = env_path.read_text(encoding="utf-8")
        check("w11 · openrouter DIFERIDA: se escribe al .env pero NO se hot-recarga en "
              "el proceso (config/os.environ intactos)",
              r_or.status_code == 200
              and f"OPENROUTER_API_KEY={clave_or}" in written_or
              and getattr(config, "OPENROUTER_API_KEY", None) == openrouter_config_before
              and os.environ.get("OPENROUTER_API_KEY") == openrouter_env_before)
        check("w11b · guardar openrouter también avisa FUERTE (cerrar y reabrir Mia) [M1]",
              bool(body_or.get("aviso"))
              and "cierra Mia" in body_or["aviso"]
              and "vuelve a abrirla" in body_or["aviso"])

        # ── (m4) string vacío se IGNORA sin bloquear la clave hermana válida ──
        clave_busqueda2 = "pa-otrabusquedavalida0987654321"
        r_empty = client.post("/api/welcome/keys", headers=auth_a,
                              json={"busqueda": clave_busqueda2, "respaldo": "   "})
        body_empty = r_empty.json()
        collect_strings(body_empty, all_response_strings)
        check("m4a · campo vacío/solo-espacios ignorado; la clave hermana válida sí se guarda",
              r_empty.status_code == 200
              and body_empty["guardado"] == {"busqueda": True}
              and f"VOYAGE_API_KEY={clave_busqueda2}" in env_path.read_text(encoding="utf-8"))
        # todas vacías/ausentes → error en llano (no rompe con la clave hermana porque no hay)
        r_all_empty = client.post("/api/welcome/keys", headers=auth_a,
                                  json={"busqueda": "", "respaldo": "  "})
        body_all_empty = r_all_empty.json()
        collect_strings(body_all_empty, all_response_strings)
        check("m4b · todas las claves vacías → 400 con mensaje en llano",
              r_all_empty.status_code == 400
              and isinstance(body_all_empty.get("detail"), str)
              and body_all_empty["detail"])

        # ── (m5) longitud excesiva → 400 con mensaje en llano (NO 422 técnico en inglés) ──
        r_long = client.post("/api/welcome/keys", headers=auth_a,
                             json={"busqueda": "pa-" + ("a" * 500)})
        body_long = r_long.json()
        collect_strings(body_long, all_response_strings)
        detail_long = body_long.get("detail")
        english_422 = isinstance(detail_long, list)  # Pydantic 422 devuelve lista de errores
        english_words = isinstance(detail_long, str) and (
            "String should" in detail_long or "at most" in detail_long
            or "ensure this value" in detail_long)
        check("m5 · clave larguísima → 400 en español llano (no 422 en inglés de Pydantic)",
              r_long.status_code == 400 and isinstance(detail_long, str)
              and not english_422 and not english_words and "largo" in detail_long)

        # ── (r) rechazo de clave con salto de línea: NO persiste, NO llama al proveedor ──
        before_bad = env_path.read_text(encoding="utf-8")
        r_bad = client.post("/api/welcome/keys", headers=auth_a,
                            json={"busqueda": "pa-mala\nclave-inyectada=1"})
        collect_strings(r_bad.json(), all_response_strings)
        check("r1 · clave con salto de línea → 400, rechazada",
              r_bad.status_code == 400)
        check("r2 · el .env NO cambió con la clave rechazada",
              env_path.read_text(encoding="utf-8") == before_bad)

        # ── (t) /welcome/keys/test: ping fake OK y error en llano ──
        fake.should_fail = False
        r_test_ok = client.post("/api/welcome/keys/test", headers=auth_a,
                                json={"tipo": "busqueda", "clave": clave_busqueda})
        collect_strings(r_test_ok.json(), all_response_strings)
        check("t1 · test-key OK (fake) → {ok: true}", r_test_ok.json() == {"ok": True})

        fake.should_fail = True
        r_test_fail = client.post("/api/welcome/keys/test", headers=auth_a,
                                  json={"tipo": "busqueda", "clave": clave_busqueda})
        body_fail = r_test_fail.json()
        collect_strings(body_fail, all_response_strings)
        check("t2 · test-key error (fake) → ok:false + motivo en llano",
              body_fail.get("ok") is False and isinstance(body_fail.get("motivo"), str)
              and body_fail["motivo"])
        check("t3 · el error NUNCA filtra la clave ni el traceback simulado",
              clave_busqueda not in body_fail["motivo"]
              and "RuntimeError" not in body_fail["motivo"]
              and "api_key" not in body_fail["motivo"])

        r_test_respaldo = client.post("/api/welcome/keys/test", headers=auth_a,
                                      json={"tipo": "respaldo", "clave": clave_respaldo})
        collect_strings(r_test_respaldo.json(), all_response_strings)
        check("t4 · test-key de respaldo también responde en llano sin filtrar nada",
              r_test_respaldo.json().get("ok") is False
              and clave_respaldo not in (r_test_respaldo.json().get("motivo") or ""))
        fake.should_fail = False

        # ── (t5) CP-OR · test-key tipo:"openrouter": ping fake OK y error en llano ──
        # El probador de OpenRouter llama litellm.completion (mismo camino que respaldo),
        # así que el FakeLLM lo cubre sin red. Verifica el enrutado del nuevo `tipo`.
        r_test_or = client.post("/api/welcome/keys/test", headers=auth_a,
                                json={"tipo": "openrouter", "clave": clave_or})
        collect_strings(r_test_or.json(), all_response_strings)
        check("t5a · test-key openrouter OK (fake completion) → {ok: true}",
              r_test_or.json() == {"ok": True})

        fake.should_fail = True
        r_test_or_fail = client.post("/api/welcome/keys/test", headers=auth_a,
                                     json={"tipo": "openrouter", "clave": clave_or})
        body_or_fail = r_test_or_fail.json()
        collect_strings(body_or_fail, all_response_strings)
        check("t5b · test-key openrouter error (fake) → ok:false + motivo en llano sin filtrar clave/traza",
              body_or_fail.get("ok") is False and isinstance(body_or_fail.get("motivo"), str)
              and body_or_fail["motivo"]
              and clave_or not in body_or_fail["motivo"]
              and "RuntimeError" not in body_or_fail["motivo"]
              and "api_key" not in body_or_fail["motivo"])
        fake.should_fail = False

        # clave con salto de línea en /keys/test: rechazo SIN llamar al proveedor
        calls_before = len(fake.embed_calls)
        r_test_bad = client.post("/api/welcome/keys/test", headers=auth_a,
                                 json={"tipo": "busqueda", "clave": "pa-mala\notra=1"})
        collect_strings(r_test_bad.json(), all_response_strings)
        check("r3 · /keys/test también rechaza clave con salto de línea sin llamar al proveedor",
              r_test_bad.json().get("ok") is False
              and len(fake.embed_calls) == calls_before)

    finally:
        config.PROJECT_ROOT = orig_project_root
        config.VOYAGE_API_KEY = orig_voyage
        config.OPENROUTER_API_KEY = orig_openrouter
        for var, val in (("VOYAGE_API_KEY", orig_environ_voyage),
                         ("OPENROUTER_API_KEY", orig_environ_openrouter),
                         ("ANTHROPIC_API_KEY", orig_environ_anthropic)):
            if val is not None:
                os.environ[var] = val
            else:
                os.environ.pop(var, None)
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # ── (g) §G sobre TODO el texto de las respuestas recolectadas ──
    joined = " ".join(all_response_strings)
    check("g1 · §G: ninguna respuesta de /welcome/* trae jerga técnica",
          not _FORBIDDEN_RE.search(joined))


def main() -> int:
    print("== F3 · bienvenida + activación de llaves (welcome) ==")
    if not os.getenv("PG_PASSWORD") or not config.JWT_SECRET:
        print("  [FAIL] PG_PASSWORD o JWT_SECRET vacío en .env")
        return 1
    init_profiles.apply()
    init_users.apply()
    init_welcome.apply()

    logging.disable(logging.CRITICAL)  # el gate no necesita ruido de logger.exception (fail-soft)

    check_instalado()

    fake = FakeLLM()
    fake.install()
    from fastapi.testclient import TestClient
    from mia.api.main import app

    tenants: list[str] = []
    try:
        with TestClient(app) as client:
            run_checks(client, fake, tenants)
    finally:
        fake.restore()
        logging.disable(logging.NOTSET)
        cleanup(tenants)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Bienvenida/llaves OK — F3 backend verificado (status público + llaves autenticadas + §G).")
        return 0
    print("Bienvenida/llaves FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
