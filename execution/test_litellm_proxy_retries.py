"""Mia · test_litellm_proxy_retries.py — GATE DE INTEGRACIÓN del R3-CRÍTICO (Codex, ronda 3).

Codex reprodujo que el PROXY LiteLLM reintenta por su cuenta: las dos configs versionadas no
traían `router_settings`, y LiteLLM 1.74.8 hereda `num_retries=2`, así que su router hacía 3
POST al proveedor ante UN fallo transitorio. MIA ya reintenta y hace fallback en agent/llm.py,
y CADA intento suyo queda RESERVADO en el tope de gasto — pero un reintento del PROXY se
esconde tras una sola reserva (hasta 12 llamadas al proveedor con 4 reservas) y un intento
facturado cuya respuesta se pierde desaparece del libro. Regla: UNA petición física por intento.

Este gate cubre, de más barato a más caro:
  1. ESTÁTICO (PyYAML, parse fiel — el mismo que hace LiteLLM): las dos configs pinean
     router_settings.num_retries == 0. (check_env_pins.py lo repite con un escáner stdlib en el
     tramo rápido; aquí se valida con el parser de verdad.)
  2. R3-ALTO (valores conocidos): el presupuesto MENSUAL liquida con cost_usd_cached (6,15), no
     con la tarifa plana (6,00). Fila sin caché: idéntica.
  3. R3-MENOR (valores conocidos): metrics.record() suma la escritura de caché al total VISIBLE
     (1,85M = 1,60M + 0,25M). El coste ya estaba bien; es el total lo que engañaba.
  4. VIVO (Codex lo pidió): se levanta una instancia EFÍMERA de litellm (binario de
     .venv-litellm) apuntando a un upstream local que CUENTA los POST y FALLA. Se demuestra en
     DOS montajes con el MISMO rig:
       · CONTROL (num_retries=2): el upstream recibe 3 POST → el rig SÍ ve los reintentos del
         proxy (sin esto, "1 POST" sería un verde ciego — no probaría nada).
       · FIX (router_settings del repo, num_retries=0): el upstream recibe EXACTAMENTE 1 POST.

Mutación (R3-CRÍTICO): quitar num_retries de una config → el check 1 (estático) se pone ROJO —
y también el vivo, porque el montaje FIX lee router_settings del repo y pasaría a amplificar.

    .venv\\Scripts\\python.exe execution\\test_litellm_proxy_retries.py

Nota de entorno: NO toca el proxy de :4000 (usa un puerto efímero propio). Levanta su
instancia con el binario de .venv-litellm y la env de BD SANEADA (igual que run_litellm_clean).
"""
from __future__ import annotations

import http.server
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))

from _tmp_desechable import tmpdir_desechable  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


CONFIGS = [
    ("litellm_config.yaml", ROOT / "litellm_config.yaml"),
    ("packaging/litellm_config.installer.yaml",
     ROOT / "packaging" / "litellm_config.installer.yaml"),
]


# ═══ 1. ESTÁTICO: router_settings.num_retries == 0 en ambas configs ══════════════
def static_pin_checks() -> dict:
    print("\n-- 1. estático: router_settings.num_retries == 0 (parse fiel con PyYAML) --")
    repo_router = None
    for name, path in CONFIGS:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        router = data.get("router_settings")
        val = router.get("num_retries") if isinstance(router, dict) else None
        ok = isinstance(router, dict) and val == 0
        check(f"pin · {name}: router_settings.num_retries == 0 (leído: {val!r})", ok)
        if name == "litellm_config.yaml":
            repo_router = router if isinstance(router, dict) else {}
    return repo_router if isinstance(repo_router, dict) else {}


# ═══ 2. R3-ALTO: el presupuesto mensual liquida con cost_usd_cached ══════════════
def budget_settle_checks() -> None:
    print("\n-- 2. R3-ALTO: el presupuesto MENSUAL liquida con cost_usd_cached (valores "
          "conocidos) --")
    from mia.agent import llm as llm_mod
    from mia.metrics import usage as usage_metrics
    from mia.policy import budget as policy_budget

    # claude-sonnet = 3.00/15.00 por Mtok. Valores elegidos para el ejemplo de Codex:
    #   prompt=1.0M, completion=0.2M  → cost_usd plano  = 3.00 + 3.00 = 6.00
    #   + cache_creation=0.025M (escritura 2.00x)       → cost_usd_cached = 6.00 + 0.15 = 6.15
    resp = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=200_000,
                              total_tokens=1_200_000,
                              cache_read_input_tokens=0, cache_creation_input_tokens=25_000),
        choices=[SimpleNamespace(finish_reason="stop",
                                 message=SimpleNamespace(content="ok"))])

    capturado: dict = {}
    orig_reserve = policy_budget.reserve_call_sync
    orig_finish = policy_budget.finish_call_sync
    # R5-1: la reserva/liquidación del tope MENSUAL vive DENTRO de `_invoke_metered` (R4-CRÍTICO),
    # que `_call_with_retries` invoca por intento. Mockear `_call_with_retries` (como hacía la
    # herencia R3-ALTO) SALTABA la liquidación real → capturado['actual']=None y el check ciego.
    # Se mockea un nivel MÁS ABAJO — `_invoke` (el POST físico) — para que `_invoke_metered`
    # corra de verdad: reserva → _invoke (falso) → liquida con cost_usd_cached del usage REAL.
    orig_invoke = llm_mod._invoke
    orig_client = llm_mod._get_client
    token = usage_metrics.set_usage_scope("00000000-0000-0000-0000-000000000000",
                                          None, "api")
    try:
        policy_budget.reserve_call_sync = lambda tenant, est, **kw: "hold-r3"
        policy_budget.finish_call_sync = (
            lambda tenant, hold, actual: capturado.__setitem__("actual", actual))
        llm_mod._invoke = lambda *a, **k: resp
        llm_mod._get_client = lambda: None
        llm_mod.call_llm([{"role": "user", "content": "x" * 4000}],
                         task="main", model="claude-sonnet")
    finally:
        policy_budget.reserve_call_sync = orig_reserve
        policy_budget.finish_call_sync = orig_finish
        llm_mod._invoke = orig_invoke
        llm_mod._get_client = orig_client
        usage_metrics.reset_usage_scope(token)

    plano = usage_metrics.cost_usd("claude-sonnet", 1_000_000, 200_000)
    cacheado = usage_metrics.cost_usd_cached("claude-sonnet", 1_000_000, 200_000, 0, 25_000)
    check(f"referencia: cost_usd plano = {plano:.2f} (== 6.00) y cost_usd_cached = "
          f"{cacheado:.2f} (== 6.15) — difieren en la escritura de caché",
          abs(plano - 6.00) < 1e-9 and abs(cacheado - 6.15) < 1e-9)
    check(f"la liquidación mensual usó cost_usd_cached = {capturado.get('actual')} (== 6.15), "
          f"NO la tarifa plana 6.00 (mutación: volver a cost_usd → llega 6.00 → ROJO)",
          capturado.get("actual") is not None
          and abs(capturado["actual"] - 6.15) < 1e-9)

    # Fila SIN caché: la liquidación mensual queda IDÉNTICA a la tarifa plana de siempre.
    resp_sin = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=200_000,
                              total_tokens=1_200_000,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0),
        choices=[SimpleNamespace(finish_reason="stop",
                                 message=SimpleNamespace(content="ok"))])
    capturado2: dict = {}
    token = usage_metrics.set_usage_scope("00000000-0000-0000-0000-000000000000", None, "api")
    try:
        policy_budget.reserve_call_sync = lambda tenant, est, **kw: "hold-r3b"
        policy_budget.finish_call_sync = (
            lambda tenant, hold, actual: capturado2.__setitem__("actual", actual))
        llm_mod._invoke = lambda *a, **k: resp_sin
        llm_mod._get_client = lambda: None
        llm_mod.call_llm([{"role": "user", "content": "x" * 4000}],
                         task="main", model="claude-sonnet")
    finally:
        policy_budget.reserve_call_sync = orig_reserve
        policy_budget.finish_call_sync = orig_finish
        llm_mod._invoke = orig_invoke
        llm_mod._get_client = orig_client
        usage_metrics.reset_usage_scope(token)
    check(f"fila SIN caché: la liquidación queda idéntica a la tarifa plana "
          f"({capturado2.get('actual')} == 6.00)",
          capturado2.get("actual") is not None
          and abs(capturado2["actual"] - 6.00) < 1e-9)


# ═══ 3. R3-MENOR: metrics.record() suma la escritura de caché al total VISIBLE ═══
def record_total_checks() -> None:
    print("\n-- 3. R3-MENOR: metrics.record() suma la escritura de caché al total VISIBLE "
          "(valores conocidos) --")
    from mia.metrics import usage as usage_metrics

    usage_metrics.drain()  # limpia cualquier residuo del check anterior
    # total_tokens del proveedor = prompt+completion = 1.60M (LiteLLM NO suma la escritura);
    # cache_creation = 0.25M → el total VISIBLE debe ser 1.85M.
    u = SimpleNamespace(prompt_tokens=1_400_000, completion_tokens=200_000,
                        total_tokens=1_600_000,
                        cache_read_input_tokens=0, cache_creation_input_tokens=250_000)
    token = usage_metrics.set_usage_scope("00000000-0000-0000-0000-000000000000", None, "api")
    try:
        usage_metrics.record("claude-sonnet", "main", u, stop_reason="stop")
    finally:
        usage_metrics.reset_usage_scope(token)
    rows = usage_metrics.drain()
    row = rows[0] if rows else {}
    check(f"total VISIBLE = {row.get('total_tokens')} (== 1_850_000 = 1.60M + 0.25M de "
          f"escritura); mutación: no sumar cache_creation → 1_600_000 → ROJO",
          row.get("total_tokens") == 1_850_000)
    check("la escritura de caché queda registrada aparte (cache_creation_tokens == 250_000)",
          row.get("cache_creation_tokens") == 250_000)

    # Fila SIN caché: el total VISIBLE es exactamente prompt+completion (no cambia nada).
    usage_metrics.drain()
    u2 = SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=200_000,
                         total_tokens=1_200_000,
                         cache_read_input_tokens=0, cache_creation_input_tokens=0)
    token = usage_metrics.set_usage_scope("00000000-0000-0000-0000-000000000000", None, "api")
    try:
        usage_metrics.record("claude-sonnet", "main", u2)
    finally:
        usage_metrics.reset_usage_scope(token)
    rows2 = usage_metrics.drain()
    check(f"fila SIN caché: total VISIBLE = {rows2[0].get('total_tokens') if rows2 else None} "
          f"(== 1_200_000 = prompt+completion, intacto)",
          rows2 and rows2[0].get("total_tokens") == 1_200_000)


# ═══ 4. VIVO: una petición física → exactamente una al proveedor (ante fallo) ════
def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _CountingUpstream(http.server.BaseHTTPRequestHandler):
    """Upstream FALSO estilo OpenAI: cuenta CADA POST a .../chat/completions y responde 500
    (fallo transitorio, que es lo que dispararía un reintento del router)."""

    def do_POST(self):  # noqa: N802
        if self.path.rstrip("/").endswith("chat/completions"):
            self.server.post_count += 1  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length:
            self.rfile.read(length)
        self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error":{"message":"boom transitorio","type":"server_error"}}')

    def log_message(self, *a):  # silencio
        return


def _write_ephemeral_config(tmp: Path, upstream_port: int, router_settings: dict) -> Path:
    cfg = {
        "model_list": [{
            "model_name": "probe",
            "litellm_params": {
                "model": "openai/probe-model",
                "api_base": f"http://127.0.0.1:{upstream_port}",
                "api_key": "sk-probe-no-real",
            },
        }],
        "litellm_settings": {"drop_params": True},
    }
    if router_settings:
        cfg["router_settings"] = router_settings
    path = tmp / f"litellm-probe-{upstream_port}.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return path


def _scrubbed_env() -> dict:
    env = dict(os.environ)
    for k in ("DATABASE_URL", "DIRECT_URL", "PG_DB", "PGPASSWORD", "PG_PASSWORD",
              "PG_APP_PASSWORD", "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_USER",
              "POSTGRES_PASSWORD", "DATABASE_HOST", "DATABASE_PORT", "DATABASE_USERNAME",
              "DATABASE_PASSWORD", "DATABASE_NAME", "DATABASE_SCHEMA"):
        env.pop(k, None)
    env["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _wait_ready(port: int, proc: subprocess.Popen, timeout: float = 75.0) -> bool:
    """Espera a que el proxy responda en /health/liveliness. Si el proceso muere, corta ya."""
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/health/liveliness"
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.6)
    return False


@contextmanager
def _ephemeral_stack(tmp: Path, router_settings: dict, tag: str):
    """Levanta el upstream contador + una instancia EFÍMERA de litellm (num_retries según
    `router_settings`) y CEDE `(proxy_port, upstream)`; `(None, upstream)` si no arrancó (para
    que el check lo vea ROJO, nunca verde ciego). Limpia proxy y upstream al salir. Compartido
    por la vía urllib (sección 4) y la vía del CLIENTE real de MIA (sección 5, R5-2), para que
    ambas ejerciten EXACTAMENTE el mismo montaje."""
    litellm_exe = ROOT / ".venv-litellm" / "Scripts" / "litellm.exe"
    upstream = http.server.HTTPServer(("127.0.0.1", 0), _CountingUpstream)
    upstream.post_count = 0  # type: ignore[attr-defined]
    up_port = upstream.server_address[1]
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    proc = None
    try:
        if not litellm_exe.exists():
            print(f"    (no existe {litellm_exe})")
            yield None, upstream
            return
        proxy_port = _free_port()
        cfg_path = _write_ephemeral_config(tmp, up_port, router_settings)
        proc = subprocess.Popen(
            [str(litellm_exe), "--config", str(cfg_path), "--host", "127.0.0.1",
             "--port", str(proxy_port)],
            cwd=str(tmp), env=_scrubbed_env(),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            # Sin ventana de consola en Windows (orden de Pipe 2026-08-24); 0 en otros SO.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if not _wait_ready(proxy_port, proc):
            print(f"    [{tag}] el proxy efímero NO arrancó a tiempo (puerto {proxy_port})")
            yield None, upstream
            return
        yield proxy_port, upstream
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except Exception:
                proc.kill()
        upstream.shutdown()
        upstream.server_close()


def _one_request_upstream_posts(tmp: Path, router_settings: dict, tag: str) -> int | None:
    """Levanta upstream + proxy efímero, hace UNA petición urllib DIRECTA (ajena a la capa
    cliente de MIA), devuelve cuántos POST llegaron al upstream. None si el proxy no arrancó."""
    with _ephemeral_stack(tmp, router_settings, tag) as (proxy_port, upstream):
        if proxy_port is None:
            return None
        body = json.dumps({"model": "probe",
                           "messages": [{"role": "user", "content": "hola"}]}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{proxy_port}/chat/completions", data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=30).read()
        except urllib.error.HTTPError:
            pass   # se ESPERA un error (el upstream siempre da 500); lo que importa es el conteo
        except Exception as exc:  # noqa: BLE001
            print(f"    [{tag}] la petición al proxy falló de forma inesperada: {exc!r}")
        time.sleep(0.5)   # deja que el proxy termine cualquier reintento en vuelo
        return upstream.post_count  # type: ignore[attr-defined]


def _client_layer_posts(tmp: Path, make_client, tag: str) -> int | None:
    """Como `_one_request_upstream_posts` pero la petición la hace un CLIENTE OpenAI construido
    por `make_client(proxy_port)` y despachado por `llm._invoke` (la vía REAL de MIA). El proxy
    efímero SIEMPRE va con num_retries=0, así que la ÚNICA fuente posible de amplificación es la
    capa cliente (el `max_retries` del SDK) — que es justo lo que la vía urllib no puede ver
    (R5-2). Devuelve los POST al upstream; None si el proxy no arrancó."""
    from mia.agent import llm as llm_mod
    with _ephemeral_stack(tmp, {"num_retries": 0}, tag) as (proxy_port, upstream):
        if proxy_port is None:
            return None
        try:
            client = make_client(proxy_port)
            # `_invoke` con un alias NO "cli-*" hace `client.chat.completions.create(**kwargs)`:
            # el mismísimo camino de producción para un alias de proxy.
            llm_mod._invoke(client, "probe",
                            {"model": "probe",
                             "messages": [{"role": "user", "content": "hola"}]})
        except Exception:  # noqa: BLE001 — se ESPERA error (upstream 500); importa el conteo
            pass
        time.sleep(0.5)   # deja que cualquier reintento del cliente termine en vuelo
        return upstream.post_count  # type: ignore[attr-defined]


def live_checks(repo_router: dict) -> None:
    print("\n-- 4. vivo: instancia efímera de litellm contra un upstream que cuenta y falla --")
    tmp = tmpdir_desechable("mia-litellm-probe-")

    # CONTROL: num_retries=2 (lo que LiteLLM heredaría SIN el pin). El rig TIENE que ver 3 POST;
    # si no, el montaje no está ejercitando los reintentos del proxy y el check FIX sería ciego.
    control = _one_request_upstream_posts(tmp, {"num_retries": 2}, "control")
    print(f"    control (num_retries=2): POST al upstream = {control}")
    check("CONTROL: con num_retries=2 el proxy reintenta y el upstream recibe 3 POST — el rig "
          "SÍ observa la amplificación (sin esto, el FIX sería un verde ciego)",
          control == 3)

    # FIX: router_settings del REPO (num_retries=0). Una petición → EXACTAMENTE un POST.
    fix = _one_request_upstream_posts(tmp, repo_router, "fix")
    print(f"    fix (router_settings del repo, num_retries={repo_router.get('num_retries')}): "
          f"POST al upstream = {fix}")
    check("FIX: con router_settings del repo (num_retries=0) UNA petición produce EXACTAMENTE "
          "UN POST al proveedor, incluso ante fallo (el proxy NO reintenta por su cuenta)",
          fix == 1)


# ═══ 5. VIVO · CAPA CLIENTE: el cliente REAL de MIA no amplifica (R5-2) ══════════
def client_layer_checks() -> None:
    """La sección 4 golpea LiteLLM con urllib DIRECTO: es CIEGA a la capa cliente de MIA. Mutar
    `_get_client` a max_retries=2 la deja verde (reproducido en la ronda 4) porque urllib no usa
    el SDK. Aquí el proxy efímero va con num_retries=0 (no reintenta él), de modo que el ÚNICO
    origen posible de POST extra es el `max_retries` del cliente OpenAI:

      · CONTROL: un cliente construido A PROPÓSITO con max_retries=2 → el upstream recibe 3 POST
        (prueba que el rig SÍ ve los reintentos de la capa cliente; sin esto el FIX sería ciego).
      · FIX: el cliente REAL del repo (`llm._get_client`, max_retries=0) apuntado al proxy
        efímero → EXACTAMENTE 1 POST ante el mismo fallo.

    Mutación (R5-2): poner max_retries=2 en `_get_client` → el FIX pasa a 3 POST → ROJO."""
    print("\n-- 5. vivo · capa cliente: el cliente REAL de MIA no reintenta (proxy num_retries=0) --")
    tmp = tmpdir_desechable("mia-litellm-client-")

    import mia.config as mia_config
    from mia.agent import llm as llm_mod
    from openai import OpenAI

    def _make_control(port: int):
        # CONTROL: max_retries=2 EXPLÍCITO (no pasa por _get_client). Demuestra que el montaje
        # observa los reintentos del SDK; si no viera 3, el FIX sería un verde ciego.
        return OpenAI(base_url=f"http://127.0.0.1:{port}", api_key="sk-probe-no-real",
                      max_retries=2)

    control = _client_layer_posts(tmp, _make_control, "control-cliente")
    print(f"    control (cliente max_retries=2): POST al upstream = {control}")
    check("CONTROL: un cliente con max_retries=2 reintenta y el upstream recibe 3 POST — el rig "
          "SÍ observa la amplificación de la CAPA CLIENTE (sin esto, el FIX sería verde ciego)",
          control == 3)

    # FIX: el cliente REAL del repo (`_get_client`, max_retries=0) apuntado al proxy efímero.
    # Se reescribe config.LITELLM_* y se resetea el singleton `_client` para que se reconstruya
    # contra el proxy de prueba; se restaura todo en finally (no toca el proxy real de :4000).
    def _make_real(port: int):
        llm_mod._client = None
        mia_config.LITELLM_BASE_URL = f"http://127.0.0.1:{port}"
        mia_config.LITELLM_API_KEY = "sk-probe-no-real"
        return llm_mod._get_client()

    orig_base = mia_config.LITELLM_BASE_URL
    orig_key = mia_config.LITELLM_API_KEY
    orig_client = llm_mod._client
    try:
        fix = _client_layer_posts(tmp, _make_real, "fix-cliente")
    finally:
        mia_config.LITELLM_BASE_URL = orig_base
        mia_config.LITELLM_API_KEY = orig_key
        llm_mod._client = orig_client
    print(f"    fix (cliente REAL del repo, max_retries=0): POST al upstream = {fix}")
    check("FIX: el cliente REAL de MIA (_get_client, max_retries=0) apuntado al proxy hace "
          "EXACTAMENTE 1 POST ante el fallo — la capa cliente NO reintenta por su cuenta "
          "(mutación: max_retries=2 en _get_client → 3 POST → ROJO)",
          fix == 1)


def main() -> int:
    repo_router = static_pin_checks()
    budget_settle_checks()
    record_total_checks()
    live_checks(repo_router)
    client_layer_checks()

    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Gate de integración del proxy OK — R3-CRÍTICO (una petición física = una al "
              "proveedor) verificado.")
        return 0
    print("Gate de integración del proxy FAIL — HALT: el proxy podría reintentar por su cuenta.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
