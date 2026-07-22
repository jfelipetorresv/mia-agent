"""Gate del TOPE DE GASTO fail-closed del banco de pruebas (Frente A). Exit 0 = PASS.

No toca la DB ni el modelo REAL: sustituye el ÚNICO punto donde el banco gasta dinero
—`agent.llm._invoke`, un intento cobrable— por un doble.

Por qué el doble está en `_invoke` y no en `call_llm` (esto es la mitad del gate):
`call_llm` NO es una unidad de facturación. Por dentro reintenta hasta `MAX_RETRIES` veces
en el mismo alias y luego SALTA al siguiente alias de la cadena, que puede ser más caro.
Un doble puesto en `call_llm` no puede, por construcción, reproducir un reintento, un
fallback ni una sobrefacturación: la versión anterior de este gate devolvía siempre un coste
IDÉNTICO a la estimación, así que era incapaz de ver el riesgo real. El doble de aquí
(`FakeProvider`) corre POR DEBAJO de la maquinaria real de reintentos y fallback de
`agent.llm`, y puede:
  · fallar con un error transitorio (500) tantas veces como se quiera → reintentos REALES;
  · agotar un alias y hacer que la cadena salte al siguiente, más caro → fallback REAL;
  · reportar MÁS tokens de los estimados → sobrefacturación REAL.

Cada invariante se prueba con un check que se puede ver ROJO: la mutación está documentada
en el bloque de arriba de cada grupo.
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))

results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── dobles ────────────────────────────────────────────────────────────────────
class ServerBoom(Exception):
    """Error TRANSITORIO del proveedor (500). `error_classifier` lo ve SERVER_ERROR:
    reintentable dentro del alias y saltable al siguiente. Es la palanca que permite a este
    gate reproducir reintentos y fallback de verdad."""
    status_code = 500


class FakeProvider:
    """Doble de `agent.llm._invoke`: UN intento cobrable contra UN alias.

    `fail_aliases`/`fail_times` provocan errores transitorios (reintentos + fallback reales).
    `token_factor` deja que el intento reporte MÁS tokens de los que se estimaron: sin esto
    ninguna prueba podría ver una subestimación (era el defecto del gate anterior).
    """

    def __init__(self, *, fail_aliases: tuple = (), fail_times: int = 0,
                 token_factor: float = 1.0, boom: bool = False,
                 peor_caso: bool = False, served_alias: str | None = None,
                 cache_mode: str | None = None, raise_exc: BaseException | None = None) -> None:
        self.attempts: list[str] = []      # alias de CADA intento, en orden
        self.max_tokens_vistos: list = []  # el max_tokens con el que llegó CADA intento
        self.fail_aliases = set(fail_aliases)
        self.fail_times = int(fail_times)
        self._failed: dict[str, int] = {}
        self.token_factor = float(token_factor)
        self.boom = boom
        # PEOR CASO REAL (R1): el intento devuelve lo MÁXIMO que físicamente puede devolver —
        # un token por carácter de entrada y la salida agotando el `max_tokens` con el que se
        # hizo la llamada— y encima lo sirve el alias más CARO del catálogo. Es el escenario
        # que la cota tiene que aguantar; con `token_factor` no se podía expresar.
        self.peor_caso = peor_caso
        self.served_alias = served_alias
        # A1 — CACHÉ DE PROMPT. Reproduce la aritmética EXACTA de LiteLLM, que es la mitad del
        # defecto (`llms/anthropic/chat/transformation.py::calculate_usage`, medido):
        #   'creation' → la ESCRITURA va FUERA de `prompt_tokens` y FUERA de `total_tokens`;
        #                por eso se cobraba a CERO y el tope no se podía certificar.
        #   'read'     → la LECTURA va DENTRO de `prompt_tokens`; por eso se cobraba a precio
        #                completo cuando en realidad cuesta la décima parte.
        self.cache_mode = cache_mode
        # A2 — el fallo exacto que el proveedor levanta, para distinguir "no se llegó a
        # conectar" (se devuelve la reserva) de "no sabemos si procesó" (se cobra).
        self.raise_exc = raise_exc

    @property
    def calls(self) -> int:
        return len(self.attempts)

    def __call__(self, client, alias, kwargs, task=None):
        self.attempts.append(alias)
        self.max_tokens_vistos.append(kwargs.get("max_tokens"))
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.boom:
            raise RuntimeError("el proveedor murió a mitad")
        if alias in self.fail_aliases and self._failed.get(alias, 0) < self.fail_times:
            self._failed[alias] = self._failed.get(alias, 0) + 1
            raise ServerBoom(f"{alias}: 500 transitorio")
        if self.peor_caso:
            payload = json.dumps({"messages": kwargs.get("messages"), "tools": []},
                                 ensure_ascii=False, default=str)
            p = len(payload)                        # 1 token por CARÁCTER: el techo teórico
            c = int(kwargs.get("max_tokens") or 64_000)   # sin tope: lo que admite el modelo
        else:
            p, c = bound_tokens(kwargs.get("messages"), kwargs.get("max_tokens"))
            p = max(1, int(p * self.token_factor))
            c = max(1, int(c * self.token_factor))
        prompt_tokens, cache_read, cache_creation, total = p, 0, 0, p + c
        if self.cache_mode == "creation":
            # TODO el prompt se escribe a caché: fuera de prompt_tokens y de total_tokens.
            prompt_tokens, cache_creation, total = 0, p, c
        elif self.cache_mode == "read":
            # TODO el prompt se sirve de caché: la lectura YA está dentro de prompt_tokens.
            cache_read = p
        return SimpleNamespace(
            model=self.served_alias or alias,
            usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=c,
                                  total_tokens=total,
                                  cache_read_input_tokens=cache_read,
                                  cache_creation_input_tokens=cache_creation),
            choices=[SimpleNamespace(finish_reason="stop",
                                     message=SimpleNamespace(content="ok"))])


def big_messages(n: int = 40_000) -> list[dict]:
    """Mensajes lo bastante grandes para que la ESTIMACIÓN sea un coste apreciable."""
    return [{"role": "user", "content": "x" * n}]


def bound_tokens(messages=None, max_tokens=None) -> tuple[int, int]:
    """Los tokens que la COTA SUPERIOR del guardián reserva para estos mensajes.

    El doble los devuelve tal cual, de modo que para `claude-sonnet` (la tarifa más cara, que
    es con la que se reserva) el coste REAL del intento es exactamente la reserva. Así los
    escenarios de este gate siguen razonando con un único número por intento.
    """
    from mia.eval import spend_guard
    payload = json.dumps({"messages": messages if messages is not None else big_messages(),
                          "tools": []}, ensure_ascii=False, default=str)
    return (len(payload) + spend_guard._PROMPT_OVERHEAD_TOKENS,
            min(int(max_tokens or spend_guard.EVAL_MAX_OUTPUT_TOKENS),
                spend_guard.EVAL_MAX_OUTPUT_TOKENS))


def bound(messages=None, alias: str = "claude-sonnet") -> float:
    """Lo que el guardián RESERVA de verdad por un intento: su COTA SUPERIOR (R1).

    El gate usaba `estimated_call_cost` —la estimación de producción— para calcular los topes
    de sus escenarios. Eso ya no es lo que el guardián reserva: desde R1 reserva
    `upper_bound_call_cost` sobre la llamada ya ACOTADA a `EVAL_MAX_OUTPUT_TOKENS`.
    """
    from mia.eval import spend_guard
    return spend_guard.upper_bound_call_cost(
        alias, messages if messages is not None else big_messages(),
        max_tokens=spend_guard.EVAL_MAX_OUTPUT_TOKENS)


@contextmanager
def provider(fake):
    """Pone `fake` DEBAJO de la envoltura permanente del guardián.

    Se cambia `spend_guard._original_invoke` (el original que la envoltura delega), no
    `llm._invoke`: la instalación es PERMANENTE y pisar `llm._invoke` desactivaría el tope,
    que es justo lo que hay que ejercitar.
    """
    from mia.eval import spend_guard
    spend_guard.ensure_installed()
    prev = spend_guard._original_invoke
    spend_guard._original_invoke = fake
    try:
        yield
    finally:
        spend_guard._original_invoke = prev


@contextmanager
def embedder(fake):
    from mia.eval import spend_guard
    spend_guard.ensure_installed()
    prev = spend_guard._original_embed_texts
    spend_guard._original_embed_texts = fake
    try:
        yield
    finally:
        spend_guard._original_embed_texts = prev


def guard_for(tmp: Path, name: str, **kw):
    from mia.eval import spend_guard
    kw.setdefault("run_limit_usd", 10.0)
    kw.setdefault("session_limit_usd", 30.0)
    kw.setdefault("global_limit_usd", 100.0)
    kw.setdefault("closeout_reserve_usd", 0.0)
    return spend_guard.EvalSpendGuard(session_id="s-test", ledger_path=tmp / f"{name}.json", **kw)


def run_calls(guard, fake, n: int, messages=None, **kwargs) -> list[BaseException]:
    """Hace `n` llamadas por la maquinaria REAL de `call_llm`; devuelve lo que levantó."""
    from mia.agent import llm as llm_mod
    errs: list[BaseException] = []
    model = kwargs.pop("model", "claude-sonnet")
    with provider(fake), guard.activate():
        for _ in range(n):
            try:
                llm_mod.call_llm(messages if messages is not None else big_messages(),
                                 task="main", model=model, **kwargs)
            except BaseException as exc:  # noqa: BLE001 — el gate ANALIZA la excepción
                errs.append(exc)
    return errs


def _tmpdir_desechable(prefix: str) -> Path:
    """Directorio de trabajo DESECHABLE, en el temporal del SISTEMA (A4 · A-MAY2).

    Ronda 3 (Codex): el helper se EXTRAJO a `execution/_tmp_desechable.py` para que los otros
    gates (test_eval_harness) reutilicen la MISMA regla fail-before-create en vez de repetir
    `mkdtemp`/`TemporaryDirectory` sin limpieza y sin la guarda de "nunca dentro del repo". Aquí
    se conserva el nombre local y se delega. La regla: NUNCA dentro del repo (HALT antes de crear
    nada si el temporal del sistema resuelve ahí — protegía a-71/a-72) y limpieza por `atexit`.
    """
    from _tmp_desechable import tmpdir_desechable

    return tmpdir_desechable(prefix, repo_root=ROOT)


def main() -> None:
    from mia.agent import error_classifier as err_clf
    from mia.agent import llm as llm_mod
    from mia.eval import spend_guard
    from mia.metrics import usage as usage_metrics

    tmp = _tmpdir_desechable("mia-spend-guard-")
    # Backoff a cero: este gate ejercita CUÁNTOS intentos hay, no cuánto se espera entre ellos.
    llm_mod.retry_delay = lambda kind, attempt: 0.0

    est = bound()
    check("a-0 · la RESERVA de una llamada grande es > 0 (si no, el gate no probaría nada)",
          est > 0.001)

    # ═══ 1. Corta ANTES de exceder ═══════════════════════════════════════════
    # MUTACIÓN: en `check_and_reserve`, cambiar `projected_run > self._effective(...)` por
    # `self.run_spent_usd > self.run_limit_usd` (comprobar DESPUÉS en vez de ANTES) →
    # caen a-1 y a-2 (se hacen todas las llamadas y ninguna levanta).
    # A1 — `cache_mode="creation"` es lo que hace que RESERVA y LIQUIDACIÓN vuelvan a ser EL
    # MISMO número, que es la premisa con la que están calibrados los escenarios de topes de
    # aquí abajo (ver `bound_tokens`). Y no es un truco: es el caso REAL y típico de MIA —
    # `agent/llm._messages_with_cache` marca el prefijo de TODA llamada a la API de Anthropic,
    # así que la primera llamada de cada corrida escribe el prompt entero a la caché de 1 h y
    # lo paga al doble. Sin caché (`cache_mode=None`) el intento liquida por DEBAJO de la
    # reserva —la cota funcionando— y harían falta más llamadas para cortar.
    g = guard_for(tmp, "run", run_limit_usd=est * 2.5)
    fake = FakeProvider(cache_mode="creation")
    errs = run_calls(g, fake, 5)
    check("a-1 · una corrida que EXCEDE el tope de corrida CORTA (no hace todas las llamadas)",
          fake.calls == 2 and len(errs) == 3)
    check("a-2 · el corte es SpendLimitExceeded y el intento que se pasaba NO se hizo",
          all(isinstance(e, spend_guard.SpendLimitExceeded) for e in errs))
    check("a-3 · el motivo del corte queda registrado y es legible",
          g.stop_reason is not None and "CORRIDA" in g.stop_reason)
    check("a-4 · STICKY: tras cortar, el guardián no vuelve a autorizar",
          g.snapshot()["stopped"] is True)

    # ═══ 2. Margen de cierre ═════════════════════════════════════════════════
    # MUTACIÓN: en `_effective`, devolver `limit` (ignorar el margen) → cae a-5.
    g = guard_for(tmp, "closeout", run_limit_usd=est * 2.5, closeout_reserve_usd=est)
    fake = FakeProvider()
    run_calls(g, fake, 5)
    check("a-5 · el margen de cierre queda intocado (se corta antes de agotar el tope)",
          fake.calls == 1 and g.run_spent_usd <= (est * 2.5) - est)

    # ═══ 3. Tope de SESIÓN, persistente entre corridas ═══════════════════════
    # MUTACIÓN: en `check_and_reserve`, no escribir el saldo (`_write_ledger`) → cae a-7.
    ledger = tmp / "sesion.json"
    mk = lambda sid, **kw: spend_guard.EvalSpendGuard(  # noqa: E731
        run_limit_usd=100.0, session_limit_usd=est * 2.5, global_limit_usd=1000.0,
        closeout_reserve_usd=0.0, session_id=sid, ledger_path=ledger, **kw)
    g1, f1 = mk("s-persistente"), FakeProvider(cache_mode="creation")
    run_calls(g1, f1, 2)
    g2, f2 = mk("s-persistente"), FakeProvider(cache_mode="creation")
    errs2 = run_calls(g2, f2, 2)
    check("a-6 · la primera corrida de la sesión sí gasta", f1.calls == 2)
    check("a-7 · el tope de SESIÓN persiste entre corridas distintas (la 2a ya no gasta)",
          f2.calls == 0 and len(errs2) == 2
          and all(isinstance(e, spend_guard.SpendLimitExceeded) for e in errs2)
          and "SESIÓN" in (g2.stop_reason or ""))

    # ═══ 4. Techo GLOBAL (cruza sesiones) ════════════════════════════════════
    # MUTACIÓN: quitar la comprobación de `global_spent` → cae a-8.
    ledger_g = tmp / "global.json"
    ga = spend_guard.EvalSpendGuard(run_limit_usd=100.0, session_limit_usd=100.0,
                                    global_limit_usd=est * 2.5, closeout_reserve_usd=0.0,
                                    session_id="sesion-A", ledger_path=ledger_g)
    fa = FakeProvider(cache_mode="creation")
    run_calls(ga, fa, 2)
    gb = spend_guard.EvalSpendGuard(run_limit_usd=100.0, session_limit_usd=100.0,
                                    global_limit_usd=est * 2.5, closeout_reserve_usd=0.0,
                                    session_id="sesion-B", ledger_path=ledger_g)
    fb = FakeProvider(cache_mode="creation")
    run_calls(gb, fb, 2)
    check("a-8 · el techo GLOBAL corta aunque la SESIÓN sea otra (y su sesión está a cero)",
          fa.calls == 2 and fb.calls == 0 and "GLOBAL" in (gb.stop_reason or ""))

    # ═══ 5. FAIL-CLOSED al leer el saldo ═════════════════════════════════════
    # MUTACIÓN: en `_read_ledger`, devolver `_empty_ledger()` en el `except` en vez de
    # levantar `SpendControlUnavailable` (fail-OPEN) → caen a-9 y a-10.
    corrupto = tmp / "corrupto.json"
    corrupto.write_text("{esto no es json", encoding="utf-8")
    g = spend_guard.EvalSpendGuard(run_limit_usd=100.0, session_id="s-test",
                                   closeout_reserve_usd=0.0, ledger_path=corrupto)
    fake = FakeProvider()
    errs = run_calls(g, fake, 2)
    check("a-9 · saldo ILEGIBLE: NO se hace ninguna llamada al modelo", fake.calls == 0)
    check("a-10 · saldo ilegible levanta SpendControlUnavailable (fail-closed, no fail-open)",
          len(errs) == 2 and all(isinstance(e, spend_guard.SpendControlUnavailable)
                                 for e in errs))

    truncado = tmp / "truncado.json"
    truncado.write_text(json.dumps({"version": 1, "sessions": {}}), encoding="utf-8")
    g = spend_guard.EvalSpendGuard(run_limit_usd=100.0, session_id="s-test",
                                   closeout_reserve_usd=0.0, ledger_path=truncado)
    fake = FakeProvider()
    errs = run_calls(g, fake, 1)
    check("a-11 · saldo con formato inesperado (sin 'global') también es fail-closed",
          fake.calls == 0 and len(errs) == 1
          and isinstance(errs[0], spend_guard.SpendControlUnavailable))

    nodir = tmp / "no-escribible.json"
    (tmp / "no-escribible.json.lock").mkdir(parents=True, exist_ok=True)  # cerrojo imposible
    g = spend_guard.EvalSpendGuard(run_limit_usd=100.0, session_id="s-test",
                                   closeout_reserve_usd=0.0, ledger_path=nodir)
    fake = FakeProvider()
    errs = run_calls(g, fake, 1)
    check("a-12 · si el cerrojo del saldo no se puede tomar, NO se gasta",
          fake.calls == 0 and len(errs) == 1
          and isinstance(errs[0], spend_guard.SpendControlUnavailable))

    # ═══ 6. Aliases GRATIS: no estorbar, pero SÍ contar ══════════════════════
    # MUTACIÓN: en `note_call`, no sumar tokens al caso → cae a-14.
    check("a-13 · un alias gratis estima coste 0",
          usage_metrics.estimated_call_cost("cli-claude", big_messages(), None, task="main") == 0)
    g = guard_for(tmp, "gratis", run_limit_usd=0.0001)
    fake = FakeProvider()
    with g.case("caso-gratis"):
        errs = run_calls(g, fake, 3, model="cli-claude")
    cu = g.cases[0].as_dict()
    p_est, c_est = bound_tokens()
    check("a-14 · el tope NO estorba a lo gratis pero los tokens SÍ se cuentan",
          fake.calls == 3 and not errs and cu["total_tokens"] == 3 * (p_est + c_est)
          and cu["cost_usd"] == 0.0 and cu["calls"] == 3)

    # ═══ 7. Incierto se cobra ════════════════════════════════════════════════
    # MUTACIÓN: en la rama `except BaseException` de `_guarded_invoke`, llamar
    # `guard.settle(reservation, 0.0)` (liberar) → cae a-15 (el saldo volvería a 0).
    g = guard_for(tmp, "incierto", run_limit_usd=100.0)
    fake = FakeProvider(boom=True)
    errs = run_calls(g, fake, 1)
    check("a-15 · un intento que muere a mitad se COBRA por lo estimado (no abre hueco)",
          errs and abs(g.run_spent_usd - est) < 1e-9)

    # ═══ 8. Liquidación al coste real ════════════════════════════════════════
    # MUTACIÓN: en `settle`, hacer `return` antes de aplicar el delta → cae a-16.
    g = guard_for(tmp, "settle", run_limit_usd=100.0)
    fake = FakeProvider(token_factor=0.001)
    run_calls(g, fake, 1)
    check("a-16 · la reserva se ajusta al coste REAL cuando resulta más barata",
          0 < g.run_spent_usd < est)

    # ═══ 9. D2 — CADA INTENTO se reserva y se liquida por separado ═══════════
    # MUTACIÓN: envolver `agent.llm.call_llm` en vez de `agent.llm._invoke` (una reserva por
    # llamada en vez de por intento) → caen a-24, a-25 y a-26: los reintentos y el intento
    # del alias caro quedarían facturados bajo UNA sola reserva.
    print("\n-- D2: un intento = una reserva (reintentos y fallback REALES) --")
    g = guard_for(tmp, "reintentos", run_limit_usd=100.0)
    fake = FakeProvider(fail_aliases=("claude-sonnet",), fail_times=2, cache_mode="creation")
    with g.case("c-reintentos"):
        errs = run_calls(g, fake, 1)
    # 2 intentos fallidos (cobrados por la reserva, invariante D) + 1 bueno.
    check("a-24 · los REINTENTOS dentro de un alias son 3 intentos cobrables, no 1: el "
          "guardián los ve todos y reserva por cada uno",
          not errs and fake.calls == 3 and g.calls == 3
          and abs(g.run_spent_usd - 3 * est) < 1e-6)

    # Fallback de un alias GRATIS a uno PAGADO dentro de UNA llamada: el intento gratis no
    # reserva nada; el pagado sí, con su alias EXACTO. (Sustituye —y supera— al viejo check
    # de "estimar el alias más caro de la cadena": ya no hace falta adivinar el peor caso
    # por adelantado, porque cada intento se reserva con el precio que de verdad se factura.)
    cadena = llm_mod.resolve_fallback_chain("main", None)
    g = guard_for(tmp, "fallback", run_limit_usd=100.0)
    fake = FakeProvider(fail_aliases=(cadena[0],), fail_times=99, cache_mode="creation")
    with g.case("c-fallback"):
        run_calls(g, fake, 1, model=None)
    servidos = fake.attempts
    check("a-25 · un salto del alias GRATIS al PAGADO dentro de una sola llamada queda "
          "reservado y contado con el alias que de verdad cobra",
          cadena[0] in servidos and "claude-sonnet" in servidos
          and abs(g.run_spent_usd - est) < 1e-6
          and g.cases[0].as_dict()["models"].get("claude-sonnet") == 1)

    # ═══ 9bis. R1 — COTA con el margen REAL y el PEOR caso REAL ══════════════
    # El gate anterior se daba un margen de cierre igual a CINCO estimaciones y un proveedor
    # que facturaba 5× lo estimado: demostraba una cota cómoda, no la de producción. Aquí el
    # margen es el de producción (`CLOSEOUT_RESERVE_USD`, derivado del techo de tokens) y el
    # proveedor devuelve el MÁXIMO físicamente posible (un token por carácter de entrada, la
    # salida agotando `max_tokens`) servido por el alias más caro del catálogo.
    # MUTACIÓN: en `_guarded_invoke`, volver a reservar con
    # `usage_metrics.estimated_call_cost(...)` (la estimación de producción) → caen a-19b,
    # a-26 y a-26b: el intento se subestima y el tope NOMINAL se pasa.
    print("\n-- R1: el techo de tokens, la cota superior y el margen DERIVADO --")
    check("a-19b · el margen de cierre es DERIVADO del techo de tokens, no una constante a "
          f"ojo (CLOSEOUT_RESERVE_USD={spend_guard.CLOSEOUT_RESERVE_USD:.5f} >= "
          f"{spend_guard.required_closeout_margin_usd():.5f})",
          abs(spend_guard.CLOSEOUT_RESERVE_USD
              - spend_guard.required_closeout_margin_usd()) < 1e-9
          and spend_guard.CLOSEOUT_RESERVE_USD > 0)

    # El caso MEDIDO por el verificador: task=delegation_triage, 64 000 tokens de salida,
    # coste real USD 0.9900 frente a una estimación de USD 0.0915 (subestimación +0.8985).
    g = guard_for(tmp, "peorcaso", run_limit_usd=100.0,
                  closeout_reserve_usd=spend_guard.CLOSEOUT_RESERVE_USD)
    peor = FakeProvider(peor_caso=True, served_alias="claude-sonnet")
    # Se espía la reserva REAL que hace el guardián (no la que este gate calcularía por su
    # cuenta): lo que hay que demostrar es que ESA reserva cubre el coste real del intento.
    reservas: list[float] = []
    _car = g.check_and_reserve

    def spy_reserve(estimate, *, alias):
        reservas.append(float(estimate))
        return _car(estimate, alias=alias)

    g.check_and_reserve = spy_reserve
    with provider(peor), g.activate():
        llm_mod.call_llm(big_messages(), task="delegation_triage", model="claude-haiku")
    g.check_and_reserve = _car
    reserva = reservas[0] if reservas else 0.0
    subestimacion = g.run_spent_usd - reserva
    check(f"a-26 · PEOR CASO REAL (el que se midió en +0.8985): la salida sale ACOTADA a "
          f"{spend_guard.EVAL_MAX_OUTPUT_TOKENS} tokens (no 64 000) y el coste real "
          f"({g.run_spent_usd:.4f}) NO supera la reserva ({reserva:.4f}): subestimación "
          f"{subestimacion:+.4f} <= 0",
          peor.max_tokens_vistos == [spend_guard.EVAL_MAX_OUTPUT_TOKENS]
          and subestimacion <= 1e-9
          and abs(spend_guard.worst_case_underestimate_usd()) < 1e-12)

    # Y la cota agregada, con el margen de PRODUCCIÓN y el peor caso en TODOS los intentos.
    tope_nominal = est * 6
    g = guard_for(tmp, "cota", run_limit_usd=tope_nominal,
                  closeout_reserve_usd=spend_guard.CLOSEOUT_RESERVE_USD)
    peor = FakeProvider(peor_caso=True, served_alias="claude-sonnet")
    run_calls(g, peor, 20)
    check(f"a-26b · COTA con el margen de PRODUCCIÓN (USD "
          f"{spend_guard.CLOSEOUT_RESERVE_USD:.5f}) y coste real máximo en cada intento: el "
          f"gasto ({g.run_spent_usd:.4f}) no pasa del tope NOMINAL ({tope_nominal:.4f}) y la "
          f"corrida se corta",
          peor.calls >= 1 and g.run_spent_usd <= tope_nominal + 1e-9
          and g.stop_reason is not None
          and all(mt == spend_guard.EVAL_MAX_OUTPUT_TOKENS for mt in peor.max_tokens_vistos))

    # ═══ 10. D4 — la parada NO se puede tragar ═══════════════════════════════
    # MUTACIÓN: hacer que `SpendGuardHalt` herede de `Exception` → cae a-27 (y con ella la
    # posibilidad de que un `except Exception` del grafo se coma el corte).
    print("\n-- D4: el corte atraviesa los 'except Exception' --")
    check("a-27 · SpendLimitExceeded NO es una Exception (hereda de BaseException, como "
          "KeyboardInterrupt): ningún `except Exception` puede tragársela",
          issubclass(spend_guard.SpendLimitExceeded, BaseException)
          and not issubclass(spend_guard.SpendLimitExceeded, Exception)
          and not issubclass(spend_guard.SpendControlUnavailable, Exception))

    g = guard_for(tmp, "tragar", run_limit_usd=est * 0.5)
    fake = FakeProvider()
    tragada = False
    with provider(fake), g.activate():
        try:
            try:
                llm_mod.call_llm(big_messages(), task="main", model="claude-sonnet")
            except Exception:  # noqa: BLE001 — imita los ~19 de agents/graph.py
                tragada = True
        except spend_guard.SpendLimitExceeded:
            pass
    check("a-28 · un `except Exception` alrededor de call_llm (el patrón exacto de "
          "graph.py:775) NO se come el corte", tragada is False and fake.calls == 0)

    # ═══ 11. D3 — instalación PERMANENTE, sin ventana que rompa producción ═══
    # MUTACIÓN: reintroducir un `uninstall()` que ponga `_original_invoke = None` → cae a-29.
    print("\n-- D3: la envoltura no se desinstala nunca --")
    spend_guard.ensure_installed()
    # SONDA DEL VERIFICADOR, en el mismo orden que la suya: un módulo captura la envoltura
    # TARDE (dentro de la ventana), se SALE del `with install()`, y producción sigue llamando
    # por esa referencia capturada. Con la versión anterior (uninstall → `_original = None`)
    # eso reventaba con TypeError para siempre hasta reiniciar el proceso.
    with spend_guard.install():
        captura_tardia = llm_mod._invoke          # captura DENTRO de la ventana
        original_dentro = spend_guard._original_invoke
    # AQUÍ está la mutación que hay que poder ver: al salir del bloque el original tiene que
    # seguir siendo el de verdad. Se comprueba ANTES de que ningún doble lo sustituya.
    check("a-29 · al SALIR del `with install()` el original sigue puesto (NUNCA None) y la "
          "envoltura sigue instalada: no hay ventana de desinstalación",
          llm_mod._invoke is spend_guard._guarded_invoke
          and spend_guard._original_invoke is not None
          and spend_guard._original_invoke is original_dentro)
    fake = FakeProvider()
    with provider(fake):
        resp = captura_tardia(None, "claude-sonnet", {"messages": big_messages()}, "main")
    check("a-30 · sonda del verificador: la referencia capturada TARDE sigue funcionando tras "
          "salir del `with` (antes: TypeError para siempre por original=None)",
          resp is not None and fake.calls == 1)
    check("a-31 · `install()` es idempotente y NO revierte (no hay ventana de desinstalación)",
          llm_mod._invoke is spend_guard._guarded_invoke)

    fake = FakeProvider()
    with provider(fake):
        resp = llm_mod.call_llm(big_messages(), task="main", model="claude-sonnet")
    check("a-19 · sin guardián en el contexto la envoltura delega (no toca producción)",
          fake.calls == 1 and resp is not None)

    # La cobertura de los módulos que importaron `call_llm` POR VALOR ya no depende de
    # re-enlazar nada: `_invoke` es privado de `agent.llm` y nadie lo importa, así que
    # cualquier ruta que acabe en `call_llm` cae bajo el tope. Se verifica por COMPORTAMIENTO.
    # MUTACIÓN: mover la envoltura a `call_llm` y quitar la de `_invoke` → cae a-18.
    import mia.memory.aprendido as aprendido
    g = guard_for(tmp, "porvalor", run_limit_usd=100.0)
    fake = FakeProvider()
    with provider(fake), g.activate():
        aprendido.call_llm(big_messages(), task="main", model="claude-sonnet")
    check("a-18 · una ruta que importó call_llm POR VALOR (memory.aprendido) queda bajo el "
          "tope sin re-enlazar nada", g.calls == 1 and g.run_spent_usd > 0)

    # ═══ 12. D1b — los EMBEDDINGS también cuentan y también topan ════════════
    # MUTACIÓN: en `ensure_installed`, no envolver `embeddings.embed_texts` → caen a-32/a-33.
    print("\n-- D1: embeddings bajo el tope --")
    from mia import embeddings as embeddings_mod
    textos = ["y" * 40_000]
    est_emb = spend_guard.estimated_embed_cost(textos)
    check("a-32 · embeber textos tiene una tarifa propia y estima > 0 (voyage-law-2 no está "
          "en PRICES_PER_MTOK: la tarifa vive en spend_guard)",
          est_emb > 0 and spend_guard.embed_alias() in spend_guard.EMBED_PRICES_PER_MTOK)

    llamadas_emb = {"n": 0}

    def fake_embed(ts):
        llamadas_emb["n"] += 1
        return [[0.0] * 4 for _ in ts]

    g = guard_for(tmp, "emb", run_limit_usd=est_emb * 7)
    errs = []
    with embedder(fake_embed), g.activate():
        for _ in range(3):
            try:
                embeddings_mod.embed_texts(textos)
            except BaseException as exc:  # noqa: BLE001
                errs.append(exc)
    check("a-33 · los EMBEDDINGS se reservan y el tope los CORTA igual que al modelo",
          llamadas_emb["n"] == 2 and len(errs) == 1
          and all(isinstance(e, spend_guard.SpendLimitExceeded) for e in errs)
          and abs(g.run_spent_usd - 2 * spend_guard.EMBED_MAX_ATTEMPTS * est_emb) < 1e-6)
    check("a-33a · un embedding que NO pasó por litellm (respaldo por SDK) se cobra al PEOR "
          "caso y se DECLARA: no se devuelve un dinero que no se puede probar que no se gastó",
          any(u["que"] == "embeddings.embed_texts"
              for u in g.snapshot()["gasto_no_gobernado"]))

    # ── R2: los REINTENTOS del embedding, de verdad ──────────────────────────
    # El doble anterior hacía UNA llamada y no podía ver los `num_retries=2` que
    # `embeddings.embed_texts` le pide a LiteLLM: hasta TRES intentos FACTURABLES bajo una
    # sola reserva. Aquí el doble se pone DEBAJO, en `litellm.embedding`, y falla dos veces
    # de verdad — así los tres intentos existen y se pueden contar.
    # MUTACIÓN: en `_guarded_embed_texts`, reservar `estimate` en vez de
    # `estimate * EMBED_MAX_ATTEMPTS` → cae a-33d (la llamada se autoriza y acaba gastando
    # 3× por encima del tope).
    import litellm  # noqa: E402 — el gate lo dobla, no lo usa

    from mia import config as mia_config
    prev_key = mia_config.VOYAGE_API_KEY
    prev_embedding = litellm.embedding
    lite = {"n": 0, "num_retries": []}

    def fake_litellm_embedding(*a, **kw):
        lite["n"] += 1
        lite["num_retries"].append(kw.get("num_retries"))
        if lite["n"] < 3:                       # dos fallos transitorios: REINTENTA de verdad
            raise RuntimeError("voyage: 500 transitorio")
        return SimpleNamespace(
            data=[{"embedding": [0.0] * mia_config.EMBED_DIM} for _ in kw["input"]])

    try:
        mia_config.VOYAGE_API_KEY = "clave-de-prueba"
        litellm.embedding = fake_litellm_embedding
        # Aquí NO se dobla `embed_texts`: corre el de PRODUCCIÓN, con su num_retries=2.
        g = guard_for(tmp, "emb-retry", run_limit_usd=est_emb * 10)
        with g.activate():
            embeddings_mod.embed_texts(textos)
        check("a-33b · el doble de embeddings REINTENTA de verdad: 3 intentos FACTURABLES en "
              "una sola llamada a embed_texts (antes el gate solo veía 1)", lite["n"] == 3)
        check("a-33c · los 3 intentos van con num_retries=0: los reintentos los hace el "
              "guardián, que reserva cada uno (LiteLLM ya no factura por su cuenta)",
              lite["num_retries"] == [0, 0, 0])
        check(f"a-33e · los 3 intentos quedan COBRADOS (USD {g.run_spent_usd:.8f} == 3 × "
              f"{est_emb:.8f}) y lo no usado del peor caso se devuelve",
              abs(g.run_spent_usd - 3 * est_emb) < 1e-9)

        lite["n"] = 0
        lite["num_retries"] = []
        tope_emb = est_emb * 2.5     # da para 2 intentos, NO para los 3 del peor caso
        g = guard_for(tmp, "emb-peor", run_limit_usd=tope_emb)
        errs = []
        with g.activate():
            try:
                embeddings_mod.embed_texts(textos)
            except BaseException as exc:  # noqa: BLE001
                errs.append(exc)
        check("a-33d · una llamada que PUEDE reintentar 3 veces se corta ANTES si el tope no "
              "da para el peor caso: 0 intentos facturados, nada por encima del tope",
              lite["n"] == 0 and len(errs) == 1
              and isinstance(errs[0], spend_guard.SpendLimitExceeded)
              and g.run_spent_usd <= tope_emb + 1e-9)
    finally:
        litellm.embedding = prev_embedding
        mia_config.VOYAGE_API_KEY = prev_key

    # ═══ 13. D1a — run_case NO corre sin tope ════════════════════════════════
    # MUTACIÓN: quitar el `raise EvalGuardMissing` de `run_case` → cae a-34.
    from mia.eval import harness
    from mia.eval.cases import GoldenCase, GoldenCaseDoc

    caso = GoldenCase(id="x", title="X", message="m",
                      documents=(GoldenCaseDoc("d.txt", ("hola",)),))
    levanto = False
    try:
        asyncio.run(harness.run_case("00000000-0000-0000-0000-000000000000", caso,
                                     tenant_allow_real=False))
    except spend_guard.EvalGuardMissing:
        levanto = True
    except BaseException:  # noqa: BLE001 — cualquier otra cosa = NO fue fail-closed
        levanto = False
    check("a-34 · run_case SIN guardián activo NO corre: levanta EvalGuardMissing "
          "(antes caía a _null_case y corría igual, evadiendo el tope entero)", levanto)
    check("a-35 · `_null_case` (el camino silencioso sin tope) ya no existe",
          not hasattr(harness, "_null_case"))

    # D1c — el hueco de un callback libre se DECLARA, no se esconde.
    g = guard_for(tmp, "untracked", run_limit_usd=1.0)
    g.note_untracked("substantive_judge", "no pasó por las capas envueltas")
    check("a-36 · el gasto que el tope NO gobierna queda declarado en el snapshot "
          "(auditable, no silencioso)",
          g.snapshot()["gasto_no_gobernado"]
          and g.snapshot()["gasto_no_gobernado"][0]["que"] == "substantive_judge")

    # ═══ 13bis. S5 — el juez ARBITRARIO se rechaza, con HTTP DE VERDAD ════════
    # El gate anterior "probaba" este hueco llamando `note_untracked` a mano: nunca hubo una
    # petición HTTP, así que no podía ver el riesgo. Aquí el juez sale a la red de verdad
    # contra un servidor local, y lo que se demuestra es que NO LLEGA A SALIR.
    # MUTACIÓN: quitar el `raise UngovernedJudge` de `run_case` → cae a-49 (el servidor recibe
    # la petición: el juez gastó fuera del tope y la corrida siguió).
    print("\n-- S5: el juez arbitrario no corre (HTTP real que nunca se hace) --")
    import http.server
    import urllib.request

    golpes: list[str] = []

    class _Juez(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            golpes.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"veredicto":"solido","explicacion_llana":"ok"}')

        def log_message(self, *a):  # silencio
            return

    servidor = http.server.HTTPServer(("127.0.0.1", 0), _Juez)
    puerto = servidor.server_address[1]
    hilo_srv = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo_srv.start()
    try:
        def juez_http(draft, diagnosis, rubric):
            """Juez REAL por HTTP directo: no pasa por call_llm ni por embed_texts."""
            with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/juzgar", timeout=5) as r:
                return json.loads(r.read().decode("utf-8"))

        caso_rubrica = GoldenCase(id="j", title="J", message="m",
                                  documents=(GoldenCaseDoc("d.txt", ("hola",)),),
                                  rubric={"citas_clave": ["Ley 1"], "conclusiones_clave": []})
        g = guard_for(tmp, "juez", run_limit_usd=1.0)
        bloqueado = None
        with g.activate():
            try:
                asyncio.run(harness.run_case("00000000-0000-0000-0000-000000000000",
                                             caso_rubrica, tenant_allow_real=True,
                                             substantive_judge=juez_http))
            except BaseException as exc:  # noqa: BLE001
                bloqueado = exc
        check("a-49 · un juez que sale por HTTP DIRECTO no se ejecuta: la corrida levanta "
              "UngovernedJudge y el servidor del juez NO recibió NINGUNA petición",
              isinstance(bloqueado, spend_guard.UngovernedJudge) and golpes == [])

        # S5 — el defecto que quedaba: la acreditación era una BANDERA que el propio juez podía
        # ponerse. Un juez podía hacer N peticiones HTTP pagadas y UNA llamada gobernada para
        # que el contador subiera y el chequeo de evidencia lo aprobara. La bandera se retiró:
        # ahora NO hay forma de acreditar un juez arbitrario, así que ninguno corre.
        # MUTACIÓN: reintroducir `governed_judge`/`is_governed_judge` y volver a aceptar a los
        # marcados en `run_case` → cae a-50 (el servidor del juez vuelve a recibir peticiones).
        marcado = juez_http
        marcado.__mia_spend_governed__ = True     # la acreditación de antes, puesta a mano
        con_marca = None
        with g.activate():
            try:
                asyncio.run(harness.run_case("00000000-0000-0000-0000-000000000000",
                                             caso_rubrica, tenant_allow_real=True,
                                             substantive_judge=marcado))
            except BaseException as exc:  # noqa: BLE001
                con_marca = exc
        check("a-50 · S5: la marca burlable ya no acredita nada — el MISMO juez HTTP con el "
              "atributo de acreditación puesto a mano también se rechaza, y el servidor sigue "
              "sin recibir NADA",
              isinstance(con_marca, spend_guard.UngovernedJudge) and golpes == []
              and not hasattr(spend_guard, "governed_judge")
              and not hasattr(spend_guard, "is_governed_judge"))
    finally:
        servidor.shutdown()
        servidor.server_close()

    # ═══ 13ter. R4 — allow_unguarded solo con política ENTERAMENTE GRATIS ═════
    # MUTACIÓN: quitar la comprobación de `free_policy_audit` en `run_case` → cae a-51 (la
    # política 'nube', que factura en todos sus aliases, correría sin ningún tope).
    print("\n-- R4: el escape sin tope no es un bypass general --")
    caso_simple = GoldenCase(id="u", title="U", message="m",
                             documents=(GoldenCaseDoc("d.txt", ("hola",)),))
    tok = llm_mod.set_model_policy("nube")
    try:
        auditoria = spend_guard.free_policy_audit()
        rechazo = None
        try:
            asyncio.run(harness.run_case("00000000-0000-0000-0000-000000000000", caso_simple,
                                         tenant_allow_real=True, allow_unguarded=True))
        except BaseException as exc:  # noqa: BLE001
            rechazo = exc
        check("a-51 · allow_unguarded=True con una política que FACTURA ('nube') se RECHAZA "
              f"con mensaje claro (aliases pagados: {auditoria['aliases_que_facturan']})",
              isinstance(rechazo, spend_guard.EvalGuardMissing)
              and "NADA puede facturar" in str(rechazo)
              and auditoria["entirely_free"] is False)
    finally:
        llm_mod.reset_model_policy(tok)

    # ── S3: "enteramente gratis" tiene que incluir los EMBEDDINGS ─────────────
    # El defecto reproducido: bajo política 'soberano' el LLM es local (gratis), así que la
    # auditoría anterior decía "entirely_free" y `allow_unguarded=True` pasaba — pero SEMBRAR
    # un caso genera embeddings de Voyage, que FACTURAN sin ningún tope. El propio log lo
    # admitía en letra pequeña. Ahora la promesa cubre las dos fuentes de coste.
    # MUTACIÓN: quitar `embeddings_facturan` de `free_policy_audit` (volver a mirar solo los
    # aliases del modelo) → cae a-52b, y a-52c pasa a permitir una corrida sin tope que gasta.
    from mia import config as cfg_mod
    prev_voyage = cfg_mod.VOYAGE_API_KEY
    tok = llm_mod.set_model_policy("soberano")
    try:
        cfg_mod.VOYAGE_API_KEY = "clave-de-embeddings-de-pago"
        aud_pagada = spend_guard.free_policy_audit()
        check("a-52b · S3: con LLM local (gratis) pero clave de EMBEDDINGS configurada, la "
              f"auditoría dice que NO es enteramente gratis ({aud_pagada['lo_que_factura']})",
              aud_pagada["entirely_free"] is False
              and aud_pagada["aliases_que_facturan"] == []
              and aud_pagada["embeddings_facturan"] is True)

        rechazo_emb = None
        try:
            asyncio.run(harness.run_case("00000000-0000-0000-0000-000000000000", caso_simple,
                                         tenant_allow_real=True, allow_unguarded=True))
        except BaseException as exc:  # noqa: BLE001
            rechazo_emb = exc
        check("a-52c · S3: y por eso allow_unguarded=True se RECHAZA con política 'soberano' "
              "si los embeddings pueden facturar (antes se aceptaba y sembraba gastando)",
              isinstance(rechazo_emb, spend_guard.EvalGuardMissing))

        cfg_mod.VOYAGE_API_KEY = ""
        aud_gratis = spend_guard.free_policy_audit()
        check("a-52 · con TODO gratis de verdad ('soberano' + sin clave de embeddings) la "
              f"auditoría sí la deja pasar (aliases: {aud_gratis['aliases']})",
              aud_gratis["entirely_free"] is True
              and aud_gratis["aliases_que_facturan"] == []
              and aud_gratis["embeddings_facturan"] is False)
    finally:
        cfg_mod.VOYAGE_API_KEY = prev_voyage
        llm_mod.reset_model_policy(tok)

    # ═══ 13quater. R7 — MODO HERMÉTICO: el registro de rutas de gasto ═════════
    # Tres rondas enumerando huecos de uno en uno produjeron un hueco nuevo en cada ronda.
    # Aquí no se enumera: se cierra el mundo. Toda ruta capaz de gastar está GOBERNADA,
    # DESACTIVADA o DECLARADA, y una que no se pueda clasificar impide ARRANCAR la corrida.
    print("\n-- R7: modo hermético (registro de rutas, fail-closed de arranque) --")
    from mia.agents import retrieval as retrieval_mod
    from mia.connectors import notebooklm as notebooklm_mod
    from mia.gateway import agent_hub as hub_mod
    from mia.mcp import turn as mcp_turn_mod

    estados = {r.name: r.estado for r in spend_guard.SPEND_ROUTES}
    check("a-53 · el registro clasifica TODA ruta capaz de gastar en uno de los tres estados, "
          f"sin cuarta opción ({len(spend_guard.SPEND_ROUTES)} rutas: {sorted(set(estados.values()))})",
          all(e in (spend_guard.GOBERNADA, spend_guard.DESACTIVADA, spend_guard.DECLARADA)
              for e in estados.values())
          and estados.get("agent.llm._invoke") == spend_guard.GOBERNADA
          and estados.get("embeddings.embed_texts") == spend_guard.GOBERNADA
          and all(r.por_que.strip() for r in spend_guard.SPEND_ROUTES))

    # Las rutas que se DESACTIVAN, con espías DEBAJO de la envoltura (patrón de `provider`):
    # así se ve si la ruta REAL —la que sale a la red o lanza un subproceso— se alcanza o no.
    # MUTACIÓN: quitar del registro la entrada de `mcp.turn.consult` (o la de
    # `AgentHub.invoke_result`) → cae a-54: la consulta MCP levanta los servidores del despacho
    # y la delegación lanza el CLI externo, ambos gastando fuera del tope.
    llegadas: list[str] = []

    async def spy_pinecone(tenant_id, query_vec, **kw):
        llegadas.append("pinecone")
        return [{"id": "x"}]

    async def spy_nlm(tenant_id, question, *a, **kw):
        llegadas.append("notebooklm")
        return "material"

    async def spy_mcp(tenant_id, question, *a, **kw):
        llegadas.append("mcp")
        return "material de un servidor MCP"

    def spy_hub(self, key, prompt, tenant_id):
        llegadas.append("agent_hub")
        return hub_mod.InvokeResult(hub_mod.STATUS_OK, "salida del CLI externo")

    prevs = (spend_guard._original_pinecone_notes, spend_guard._original_consult_notebook,
             spend_guard._original_mcp_consult, spend_guard._original_hub_invoke_result)
    spend_guard._original_pinecone_notes = spy_pinecone
    spend_guard._original_consult_notebook = spy_nlm
    spend_guard._original_mcp_consult = spy_mcp
    spend_guard._original_hub_invoke_result = spy_hub
    try:
        g = guard_for(tmp, "rutas", run_limit_usd=1.0)
        hub = hub_mod.AgentHub()
        with g.activate():
            declaradas = {u["que"] for u in g.snapshot()["gasto_no_gobernado"]}
            inventario = g.snapshot()["rutas_de_gasto"]
            notas = asyncio.run(retrieval_mod.pinecone_secondary_notes("t", [0.0] * 4))
            nlm = asyncio.run(notebooklm_mod.consult_notebook("t", "pregunta"))
            mcp_res = asyncio.run(mcp_turn_mod.consult("t", "pregunta"))
            hub_res = hub.invoke_result("claude", "haz algo", "t")
        con_guardian = list(llegadas)
        # Y sin guardián, producción intacta: las rutas reales SÍ se alcanzan.
        asyncio.run(retrieval_mod.pinecone_secondary_notes("t", [0.0] * 4))
        asyncio.run(notebooklm_mod.consult_notebook("t", "pregunta"))
        asyncio.run(mcp_turn_mod.consult("t", "pregunta"))
        hub.invoke_result("claude", "haz algo", "t")
        sin_guardian = list(llegadas)
    finally:
        (spend_guard._original_pinecone_notes, spend_guard._original_consult_notebook,
         spend_guard._original_mcp_consult, spend_guard._original_hub_invoke_result) = prevs

    desactivadas = {r.name for r in spend_guard.SPEND_ROUTES
                    if r.estado == spend_guard.DESACTIVADA}
    check("a-53b · las rutas no gobernadas se DECLARAN al activar el tope, se hayan tocado o "
          "no, y el inventario COMPLETO viaja al reporte (un hueco silencioso no es "
          "aceptable; uno declarado sí)",
          desactivadas.issubset(declaradas)
          and len(inventario) == len(spend_guard.SPEND_ROUTES)
          and all(i["estado"] and i["por_que"] for i in inventario))
    check("a-54 · las CUATRO rutas desactivadas no se alcanzan bajo el tope — incluidas las "
          "dos que nadie había listado: la consulta MCP (levanta servidores del despacho) y "
          "la delegación a CLIs externos por subproceso (graph.py ~L939)",
          con_guardian == [] and notas == [] and nlm is None and mcp_res is None
          and hub_res.ok is False)
    check("a-54b · sin guardián, producción intacta: las mismas cuatro rutas SÍ llegan a la "
          "red/al subproceso (la desactivación es del banco, no del producto)",
          sorted(sin_guardian) == ["agent_hub", "mcp", "notebooklm", "pinecone"])

    # El invariante que hace hermético el modo: una ruta que NO se puede clasificar impide
    # ARRANCAR. Se simula lo que pasaría si alguien renombrara un atributo del producto.
    # MUTACIÓN: en `ensure_installed`, volver al `try/except` que solo ANOTABA el hueco →
    # cae a-54c (la corrida arrancaría con una ruta capaz de gastar sin envolver).
    prev_routes, prev_installed = spend_guard.SPEND_ROUTES, spend_guard._installed
    try:
        spend_guard.SPEND_ROUTES = prev_routes + (
            spend_guard.SpendRoute(
                name="modulo.inexistente.gasta", estado=spend_guard.GOBERNADA,
                module="agents.retrieval", attr="esta_funcion_no_existe",
                wrapper="_guarded_invoke", original="_original_invoke",
                por_que="ruta nueva que alguien añadió sin clasificar"),)
        spend_guard._installed = False
        arranque = None
        try:
            with guard_for(tmp, "hermetico").activate():
                pass
        except BaseException as exc:  # noqa: BLE001
            arranque = exc
    finally:
        spend_guard.SPEND_ROUTES = prev_routes
        spend_guard._installed = prev_installed
    check("a-54c · una ruta del registro que NO se puede aplicar (atributo renombrado, import "
          "roto) impide ARRANCAR la corrida: SpendRouteUnavailable, no un aviso en el log",
          isinstance(arranque, spend_guard.SpendRouteUnavailable)
          and isinstance(arranque, spend_guard.SpendGuardHalt)
          and "el banco no arranca" in str(arranque).lower())

    # ═══ 13quinquies. S1 — NINGUNA parada del guardián se puede tragar ════════
    # El defecto reproducido por el auditor: una corrida BLOQUEADA por un juez no gobernado
    # salía con código de EXITO, porque `UngovernedJudge` era una `Exception` corriente que el
    # `except Exception` genérico de `run_suite` trataba como "un caso que falló". Es la MISMA
    # clase de defecto que ya se cerró para `SpendLimitExceeded`, reaparecida en otra puerta.
    # En vez de tapar la puerta de hoy, se prohíbe la clase entera.
    # MUTACIÓN: hacer que `UngovernedJudge` (o `EvalGuardMissing`) herede de `Exception` →
    # caen a-57 y a-58.
    print("\n-- S1: toda parada del guardián deriva de SpendGuardHalt --")
    check("a-57 · NINGUNA excepción de spend_guard escapa a SpendGuardHalt — el check recorre "
          "el módulo, así que la próxima que alguien añada tampoco podrá colarse",
          spend_guard.guard_exception_audit() == [])
    check("a-58 · y en concreto: las cinco paradas conocidas son BaseException, no Exception",
          all(issubclass(e, spend_guard.SpendGuardHalt) and not issubclass(e, Exception)
              for e in (spend_guard.SpendLimitExceeded, spend_guard.SpendControlUnavailable,
                        spend_guard.EvalGuardMissing, spend_guard.UngovernedJudge,
                        spend_guard.SpendRouteUnavailable)))

    # Y el CABLEADO: una corrida bloqueada por un juez no gobernado tiene que salir con código
    # distinto de cero. Se ejerce `run_suite` DE VERDAD (el camino del auditor: run_case
    # levanta → el `except` de run_suite → corte → exit_code_for).
    # MUTACIÓN: en `run_suite`, volver a capturar solo `SpendLimitExceeded`/
    # `SpendControlUnavailable` en vez de `SpendGuardHalt` → cae a-59: la parada atraviesa
    # run_suite, no llega a `summary.corte`, y `_main` la deja sin código de salida propio.
    import run_eval as run_eval_mod  # noqa: E402 — mismo intérprete, sin subproceso

    rep_juez = asyncio.run(_halt_wiring_probe(tmp))
    check("a-59 · CABLEADO REAL de S1: una corrida BLOQUEADA por un juez no gobernado llega a "
          "summary.corte y sale con código 2 — jamás con 0 (era exactamente el defecto "
          "reproducido por el auditor con exit code 0)",
          bool((rep_juez.get("summary") or {}).get("corte"))
          and any("UngovernedJudge" in (c.get("error") or "")
                  and c.get("detenido_por_tope") is True
                  for c in rep_juez.get("cases", []))
          and run_eval_mod.exit_code_for(rep_juez) == 2)

    halt_visto = {}
    codigo = _blocked_main_exit_code(halt_visto)
    check("a-60 · una parada del guardián FUERA del bucle de casos (p. ej. una ruta que no se "
          f"puede clasificar: el banco ni arranca) sale con código {codigo} != 0 y con el "
          "motivo impreso, no con un traceback ni con un cero tranquilizador",
          codigo == run_eval_mod.EXIT_BLOQUEADA and codigo != 0)

    # ═══ 14. D5 — atomicidad de verdad ═══════════════════════════════════════
    # MUTACIÓN: en `check_and_reserve`, sacar `self.run_spent_usd = projected_run` fuera del
    # `with self._lock` (como estaba: leer, soltar, reservar, sumar) → cae a-37.
    print("\n-- D5: atomicidad y cerrojos --")
    ledger_c = tmp / "concurrencia.json"
    n_hilos, por_hilo = 8, 5
    fakes = [FakeProvider() for _ in range(n_hilos)]
    guards = [spend_guard.EvalSpendGuard(run_limit_usd=1000.0, session_limit_usd=1000.0,
                                         global_limit_usd=1000.0, closeout_reserve_usd=0.0,
                                         session_id="s-conc", ledger_path=ledger_c)
              for _ in range(n_hilos)]
    barrera = threading.Barrier(n_hilos)

    def worker(i: int) -> None:
        barrera.wait()
        with guards[i].activate():
            for _ in range(por_hilo):
                try:
                    llm_mod.call_llm(big_messages(), task="main", model="claude-sonnet")
                except BaseException:  # noqa: BLE001
                    pass

    with provider(fakes[0]):
        hilos = [threading.Thread(target=worker, args=(i,)) for i in range(n_hilos)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
    total_anotado = spend_guard.read_spend(ledger_c, "s-conc")["session_usd"]
    esperado = sum(gg.run_spent_usd for gg in guards)
    check("a-17 · entre PROCESOS/hilos el saldo anotado == suma de lo gastado (atómico)",
          fakes[0].calls == n_hilos * por_hilo and abs(total_anotado - esperado) < 1e-6)

    # MISMO guardián, muchos hilos: el tope POR CORRIDA no se puede pasar.
    ledger_s = tmp / "conc-misma-corrida.json"
    tope = est * 4.5
    g = spend_guard.EvalSpendGuard(run_limit_usd=tope, session_limit_usd=1000.0,
                                   global_limit_usd=1000.0, closeout_reserve_usd=0.0,
                                   session_id="s-misma", ledger_path=ledger_s)
    # `cache_mode="creation"` (reserva == liquidación) para que un sobregasto no se pueda
    # esconder detrás de la devolución del sobrante: aquí lo que se mide es si el tope aguanta.
    fake = FakeProvider(cache_mode="creation")
    barrera2 = threading.Barrier(6)

    def worker2() -> None:
        # El ContextVar del guardián NO se hereda al crear un Thread: cada hilo lo activa.
        with g.activate():
            barrera2.wait()
            for _ in range(4):
                try:
                    llm_mod.call_llm(big_messages(), task="main", model="claude-sonnet")
                except BaseException:  # noqa: BLE001
                    pass

    with provider(fake):
        hs = [threading.Thread(target=worker2) for _ in range(6)]
        for h in hs:
            h.start()
        for h in hs:
            h.join()
    # El aserto es el TOPE, no el número exacto de intentos: con 6 hilos compitiendo por el
    # mismo saldo, cuántos entran antes del corte depende del planificador. Fijarlo en `== 4`
    # hacía este check FLAKY —se le vio dar rojo con 5 intentos y USD 1.2307, o sea con el tope
    # perfectamente respetado—, y un rojo espurio en el gate del dinero durante una corrida de
    # USD 30 cuesta la corrida entera. Lo que sí se exige, y es lo que mata la mutación de D5:
    # que el gasto NO pase del tope, que el guardián CORTARA de verdad, y que no pasaran los 24
    # intentos pedidos (si pasaran todos, no habría habido tope).
    check(f"a-37 · el tope POR CORRIDA aguanta 6 hilos concurrentes de la MISMA corrida "
          f"(gastado {g.run_spent_usd:.4f} <= tope {tope:.4f}, pasaron {fake.calls} de 24 "
          "intentos y el guardián cortó)",
          g.run_spent_usd <= tope + 1e-9 and g.stop_reason is not None
          and 0 < fake.calls < 24)

    # Ruptura del cerrojo: SOLO con dueño demostrablemente muerto.
    # MUTACIÓN: volver a romper el cerrojo por edad sin comprobar el PID → cae a-39.
    import os as _os
    import time as _time
    viejo = spend_guard._LOCK_STALE_S
    viejo_to = spend_guard._LOCK_TIMEOUT_S
    try:
        spend_guard._LOCK_STALE_S = 0.0
        spend_guard._LOCK_TIMEOUT_S = 0.3
        # (a) dueño MUERTO (pid imposible) → el cerrojo huérfano se rompe y se puede gastar.
        led_muerto = tmp / "lock-muerto.json"
        led_muerto.parent.mkdir(parents=True, exist_ok=True)
        (tmp / "lock-muerto.json.lock").write_text(
            json.dumps({"pid": 999_999_999, "ts": _time.time() - 3600}), encoding="utf-8")
        g = spend_guard.EvalSpendGuard(run_limit_usd=100.0, closeout_reserve_usd=0.0,
                                       session_id="s-lock", ledger_path=led_muerto)
        fake = FakeProvider()
        errs = run_calls(g, fake, 1)
        check("a-38 · un cerrojo huérfano cuyo dueño está DEMOSTRADAMENTE muerto sí se rompe",
              fake.calls == 1 and not errs)

        # (b) dueño VIVO (este mismo proceso) y cerrojo viejo → NO se rompe: fail-closed.
        led_vivo = tmp / "lock-vivo.json"
        (tmp / "lock-vivo.json.lock").write_text(
            json.dumps({"pid": _os.getpid(), "ts": _time.time() - 3600}), encoding="utf-8")
        g = spend_guard.EvalSpendGuard(run_limit_usd=100.0, closeout_reserve_usd=0.0,
                                       session_id="s-lock", ledger_path=led_vivo)
        fake = FakeProvider()
        errs = run_calls(g, fake, 1)
        check("a-39 · un cerrojo VIEJO cuyo dueño sigue VIVO (proceso pausado) NO se rompe "
              "por reloj: fail-closed, no se gasta",
              fake.calls == 0 and len(errs) == 1
              and isinstance(errs[0], spend_guard.SpendControlUnavailable))
    finally:
        spend_guard._LOCK_STALE_S = viejo
        spend_guard._LOCK_TIMEOUT_S = viejo_to

    # ═══ 15. D7 — saldo negativo o incoherente = fail-closed ═════════════════
    # MUTACIÓN: en `_sane_amount`, quitar la comprobación de signo → cae a-40.
    print("\n-- D7/D8/D6: saldo, sesiones y bolsillos --")
    envenenado = tmp / "negativo.json"
    envenenado.write_text(json.dumps(
        {"version": 1, "sessions": {"s-test": {"spent_usd": -999999.0, "calls": 0}},
         "global": {"spent_usd": 0.0, "calls": 0}}), encoding="utf-8")
    g = spend_guard.EvalSpendGuard(run_limit_usd=1.0, session_limit_usd=1.0,
                                   global_limit_usd=1.0, closeout_reserve_usd=0.0,
                                   session_id="s-test", ledger_path=envenenado)
    fake = FakeProvider()
    errs = run_calls(g, fake, 1)
    check("a-40 · un saldo NEGATIVO no sube el techo: fail-closed y NO se gasta "
          "(sonda del verificador: -999999 autorizaba una reserva de USD 500)",
          fake.calls == 0 and len(errs) == 1
          and isinstance(errs[0], spend_guard.SpendControlUnavailable))

    inf = tmp / "infinito.json"
    inf.write_text(json.dumps(
        {"version": 1, "sessions": {}, "global": {"spent_usd": 1e999, "calls": 0}}),
        encoding="utf-8")
    g = spend_guard.EvalSpendGuard(run_limit_usd=1.0, closeout_reserve_usd=0.0,
                                   session_id="s-test", ledger_path=inf)
    fake = FakeProvider()
    errs = run_calls(g, fake, 1)
    check("a-41 · un saldo no finito también es fail-closed",
          fake.calls == 0 and isinstance(errs[0], spend_guard.SpendControlUnavailable))

    # ═══ 16. D6/D8 — bolsillos separados y sesión con ciclo de vida ══════════
    # MUTACIÓN: devolver "default" en `default_session_id` → caen a-42 y a-43.
    from datetime import date
    prev_env = _os.environ.pop(spend_guard.SESSION_ENV, None)
    try:
        cli_sid = spend_guard.default_session_id("cli")
        inapp_sid = spend_guard.default_session_id("inapp")
        check("a-42 · D6: la corrida de CLI y la corrida in-app NO comparten bolsillo "
              f"({cli_sid} != {inapp_sid})", cli_sid != inapp_sid)
        check("a-43 · D8: la sesión por defecto lleva la FECHA (caduca; agotar el tope no "
              "bloquea para siempre)", f"{date.today():%Y%m%d}" in cli_sid
              and cli_sid != "default")
        check("a-44 · el guardián que crea el harness por defecto es el bolsillo in-app",
              spend_guard.EvalSpendGuard().session_id == inapp_sid)
        _os.environ[spend_guard.SESSION_ENV] = "mi-sesion"
        check("a-45 · MIA_EVAL_SESSION_ID sigue mandando por encima",
              spend_guard.default_session_id("cli") == "mi-sesion")
    finally:
        _os.environ.pop(spend_guard.SESSION_ENV, None)
        if prev_env is not None:
            _os.environ[spend_guard.SESSION_ENV] = prev_env

    import run_eval  # noqa: E402 — mismo intérprete, sin subproceso
    check("a-46 · run_eval crea su guardián en el bolsillo 'cli' (no en el del abogado)",
          run_eval._make_guard(SimpleNamespace(max_usd=None, session_id=None)).source == "cli")

    # ═══ 17. D4b — CABLEADO REAL de punta a punta ════════════════════════════
    # MUTACIÓN: en `run_suite`, cambiar `corte=corte` por `corte=None` → cae a-47 (antes
    # a-22/a-23 llamaban a build_report a mano con el corte escrito a mano, así que el
    # cableado real NUNCA se ejercía y la mutación dejaba la suite en verde).
    print("\n-- D4b: el cableado real del corte (run_suite -> reporte -> código de salida) --")
    report, espia = asyncio.run(_suite_wiring_probe(tmp, est))
    # ── R5: el eval NO consume el presupuesto MENSUAL del despacho ────────────
    # MUTACIÓN: en `agent/llm.py`, quitar `and not is_eval` de la rama de reserva → cae a-55
    # (una corrida del banco vuelve a descontar del saldo del mes del abogado).
    reservas_eval = [r for r in espia["reserve"] if r["tenant"] == "t"]
    check("a-55 · R5: con scope de EVAL (source='eval') NO se reserva presupuesto mensual del "
          f"despacho — reserve_call_sync no se llamó ni una vez con el tenant del eval "
          f"({len(reservas_eval)} llamadas)", reservas_eval == [])
    # MUTACIÓN de control: cambiar `not is_eval` por `True` (nunca reservar) → cae a-56, que
    # es lo que impide "arreglar" R5 rompiendo la protección de producción.
    reservas_prod = [r for r in espia["reserve"] if r["tenant"] == "tenant-real"]
    check("a-56 · R5 no rompió producción: un turno NORMAL (source='api') sigue reservando el "
          "presupuesto mensual exactamente igual — una reserva y su liquidación",
          len(reservas_prod) == 1 and reservas_prod[0]["usd"] > 0
          and reservas_prod[0]["model"] == "claude-sonnet"
          and len([f for f in espia["finish"] if f["tenant"] == "tenant-real"]) == 1)

    check("a-47 · CABLEADO REAL: un corte en run_suite llega a summary.corte, a spend.stopped "
          "y al código de salida 2 — una corrida CORTADA jamás sale con 0",
          (report.get("summary") or {}).get("corte")
          and (report.get("spend") or {}).get("stopped") is True
          and run_eval.exit_code_for(report) == 2)
    check("a-48 · una corrida COMPLETA sí sale con 0 (el check anterior no pasa por serlo "
          "todo verde)",
          run_eval.exit_code_for({"summary": {"corte": None}, "spend": {"stopped": False}}) == 0)

    # ═══ 18. Reporte y persistencia ══════════════════════════════════════════
    saved_dir = harness.persist_report(report, base_dir=str(tmp / "runs"))
    saved = json.loads((saved_dir / "summary.json").read_text(encoding="utf-8"))
    check("a-23 · el reporte PARCIAL con el motivo del corte se persiste en disco",
          bool(saved["summary"]["corte"]) and saved["spend"]["stopped"] is True)

    rep = harness.build_report("r", [
        {"case_id": "c1", "elapsed_ms": 1200.0, "reached_draft": True,
         "usage": {"cost_usd": 0.5, "total_tokens": 100}}],
        spend={"stopped": True}, corte="por tope")
    check("a-22 · el reporte lleva coste, duración y el motivo del corte (auditable)",
          rep["summary"]["costo_total_usd"] == 0.5
          and rep["summary"]["tokens_totales"] == 100
          and rep["summary"]["duracion_total_ms"] == 1200.0
          and rep["summary"]["corte"] == "por tope")

    # ═══ 19. LA COTA FINAL, MEDIDA (no razonada) ═════════════════════════════
    # Un número: cuánto puede excederse el tope NOMINAL en el peor caso, con TODAS las rutas
    # que siguen vivas contadas (modelo + embeddings), y con margen de cierre CERO para que el
    # número no se esconda detrás del colchón.
    # MUTACIÓN: devolver `_EMBED_CHARS_PER_TOKEN = 4` (la regla de dedo de antes) → cae a-61:
    # el coste REAL de los embeddings pasa a ser 4× lo reservado y el tope nominal se supera.
    print("\n-- COTA FINAL: exceso medido sobre el tope nominal, con todas las rutas --")
    cota = _measured_overshoot(tmp)
    print(f"   tope nominal USD {cota['tope_nominal']:.4f}")
    print(f"   modelo      : facturado USD {cota['facturado_modelo']:.6f} · exceso "
          f"USD {cota['exceso_modelo']:+.8f} ({cota['intentos_modelo']} intentos)")
    print(f"   embeddings  : facturado USD {cota['facturado_embeddings']:.6f} · contado por el "
          f"guardián USD {cota['contado_embeddings']:.6f} · exceso "
          f"USD {cota['exceso_embeddings']:+.8f} ({cota['intentos_embedding']} intentos)")
    print(f"   caché 1h    : facturado USD {cota['facturado_cache']:.6f} · exceso "
          f"USD {cota['exceso_cache']:+.8f} ({cota['intentos_cache']} intentos, TODO el prompt "
          "escrito a caché al DOBLE de la entrada)")
    print(f"   COTA FINAL  : exceso máximo sobre el tope nominal = USD {cota['exceso']:+.8f}")
    check(f"a-61 · COTA FINAL MEDIDA: lo que el PROVEEDOR factura no pasa del tope NOMINAL por "
          f"ninguna de las dos rutas vivas — exceso máximo USD {cota['exceso']:+.8f} <= 0, con "
          "modelo y embeddings en su PEOR caso real y sin margen de cierre que lo tape",
          cota["exceso"] <= 1e-9 and cota["corto"] is True
          and cota["intentos_modelo"] >= 1 and cota["intentos_embedding"] >= 1)
    check("a-62 · y lo que el guardián CONTÓ por los embeddings cubre lo que el proveedor "
          "facturó de verdad (la reserva de S4 es una COTA, no un promedio: 1 token por "
          "CARÁCTER). Con la regla de dedo de 4 chars/token esto se rompe 4 a 1.",
          cota["contado_embeddings"] >= cota["facturado_embeddings"] - 1e-9)

    # ═══ 20. A1 · LA CACHÉ DE PROMPT SE TARIFA ═══════════════════════════════
    # MUTACIÓN: poner `CACHE_WRITE_MULTIPLIER = 1.0` en spend_guard → caen a-63 y a-65 (la
    # escritura deja de valer el doble y la reserva deja de ser cota).
    # MUTACIÓN de control: `CACHE_READ_MULTIPLIER = 1.0` → cae a-64 (la lectura deja de abaratar
    # y el tope se vuelve inútil por sobre-reserva permanente).
    print("\n-- A1: la ESCRITURA de caché se factura al DOBLE; la LECTURA abarata --")
    msgs_cache = big_messages(20_000)
    p_tok, c_tok = bound_tokens(msgs_cache, spend_guard.EVAL_MAX_OUTPUT_TOKENS)
    in_rate, out_rate = spend_guard._WORST_RATES
    reserva = spend_guard.upper_bound_call_cost(
        "claude-sonnet", msgs_cache, max_tokens=spend_guard.EVAL_MAX_OUTPUT_TOKENS)
    reserva_sin_cache = round((p_tok * in_rate + c_tok * out_rate) / 1_000_000.0, 6)
    esperada = round((p_tok * in_rate * spend_guard.CACHE_WRITE_MULTIPLIER
                      + c_tok * out_rate) / 1_000_000.0, 6)
    check(f"a-63 · la RESERVA cuenta el peor caso de ESCRITURA de caché (x"
          f"{spend_guard.CACHE_WRITE_MULTIPLIER:.2f} sobre la entrada): USD {reserva:.6f}, no "
          f"USD {reserva_sin_cache:.6f} como antes de A1",
          abs(reserva - esperada) < 1e-9 and reserva > reserva_sin_cache)

    # Las tres liquidaciones del MISMO intento, según dónde caiga el prompt.
    coste_normal = spend_guard.real_call_cost("claude-sonnet", p_tok, c_tok, 0, 0)
    coste_lectura = spend_guard.real_call_cost("claude-sonnet", p_tok, c_tok, p_tok, 0)
    coste_escritura = spend_guard.real_call_cost("claude-sonnet", 0, c_tok, 0, p_tok)
    print(f"   mismo intento · entrada normal USD {coste_normal:.6f} · todo LECTURA "
          f"USD {coste_lectura:.6f} · todo ESCRITURA USD {coste_escritura:.6f}")
    check("a-64 · la LECTURA de caché ABARATA (x0.10), no encarece: liquidar el mismo intento "
          "servido desde caché cuesta MENOS que la entrada normal",
          coste_lectura < coste_normal)
    check("a-65 · la ESCRITURA de caché ENCARECE y ya no se liquida a cero: el mismo intento "
          "escrito a caché cuesta más que la entrada normal, y sigue por DEBAJO de la reserva",
          coste_escritura > coste_normal and coste_escritura <= reserva + 1e-9)
    check("a-66 · la sub-facturación máxima de un intento sigue siendo CERO con la caché en su "
          f"peor caso: reserva USD {reserva:.6f} >= coste real USD {coste_escritura:.6f}",
          spend_guard.worst_case_underestimate_usd() == 0.0
          and max(coste_normal, coste_lectura, coste_escritura) <= reserva + 1e-9)
    check("a-67 · COTA con caché, MEDIDA de punta a punta: con TODO el prompt escrito a caché "
          f"el proveedor no pasa del tope nominal — exceso USD {cota['exceso_cache']:+.8f} <= 0",
          cota["exceso_cache"] <= 1e-9 and cota["intentos_cache"] >= 1)

    # ═══ 21. A2 · UN FALLO DE RED QUE NO LLEGÓ A CONECTAR NO SE COBRA ════════
    # MUTACIÓN: en `_guarded_invoke`, volver a `guard.settle(reservation, None)` siempre → cae
    # a-68 (la corrida que no gastó nada vuelve a quemar presupuesto de sesión).
    # MUTACIÓN de control: devolver siempre la reserva (`0.0` sin mirar la excepción) → cae
    # a-69, que es lo que impide "arreglar" A2 abriendo un hueco de sobregasto.
    print("\n-- A2: no-enviado se DEVUELVE; incierto se sigue cobrando --")

    class SinConexion(Exception):
        """Lo que levanta httpx cuando NO se llegó a abrir el socket."""

    SinConexion.__name__ = "ConnectError"

    class LecturaCortada(Exception):
        """La petición SALIÓ y la respuesta no llegó: nadie sabe si el proveedor la procesó."""

    g_red = guard_for(tmp, "a2-red", run_limit_usd=10.0)
    errs_red = run_calls(g_red, FakeProvider(
        raise_exc=SinConexion("[Errno 111] Connection refused")), 3, messages=msgs_cache)
    saldo_red = spend_guard.read_spend(g_red.ledger_path, g_red.session_id)
    print(f"   no-enviado : {len(errs_red)} llamadas fallidas · corrida USD "
          f"{g_red.run_spent_usd:.6f} · sesión USD {saldo_red['session_usd']:.6f}")
    check("a-68 · A2: las llamadas que murieron ANTES de conectar (DNS/conexión rechazada) "
          "DEVUELVEN la reserva: ni la corrida ni la sesión quedan con gasto, y el saldo del "
          "libro vuelve a cero",
          len(errs_red) == 3 and g_red.run_spent_usd < 1e-9
          and saldo_red["session_usd"] < 1e-9 and saldo_red["global_usd"] < 1e-9)

    g_inc = guard_for(tmp, "a2-incierto", run_limit_usd=10.0)
    errs_inc = run_calls(g_inc, FakeProvider(
        raise_exc=LecturaCortada("read timeout: la respuesta nunca llegó")), 3,
        messages=msgs_cache)
    saldo_inc = spend_guard.read_spend(g_inc.ledger_path, g_inc.session_id)
    print(f"   incierto   : {len(errs_inc)} llamadas fallidas · corrida USD "
          f"{g_inc.run_spent_usd:.6f} · sesión USD {saldo_inc['session_usd']:.6f}")
    check("a-69 · A2 no abrió un hueco: un final INCIERTO (timeout de lectura — la petición "
          "salió y no sabemos si se procesó) se sigue cobrando por lo estimado, invariante D "
          "intacto",
          len(errs_inc) == 3 and g_inc.run_spent_usd > 0
          and saldo_inc["session_usd"] > 0)
    check("a-70 · y la distinción la hace el clasificador que YA existía, no una taxonomía "
          "nueva: `provider_never_reached` separa los dos casos y ante la duda dice NO",
          err_clf.provider_never_reached(SinConexion("[Errno 111] Connection refused")) is True
          and err_clf.provider_never_reached(
              LecturaCortada("read timeout: la respuesta nunca llegó")) is False
          and err_clf.provider_never_reached(RuntimeError("algo raro pasó")) is False)

    # ═══ 22. A4 · LAS PRUEBAS NO ENSUCIAN EL ESTADO REAL ═════════════════════
    # MUTACIÓN: devolver `tmp = Path(tempfile.mkdtemp(prefix=...))` sin `dir=` ni comprobación
    # → cae a-71 en cuanto el temporal del sistema resuelva dentro del repo (que es como
    # aparecieron los `mia-spend-guard-*` en la raíz).
    print("\n-- A4: el gate trabaja en un desechable, nunca en el estado real --")
    libro_real = spend_guard.default_ledger_path().resolve()
    check("a-71 · A4: el directorio de trabajo del gate está FUERA del repo y es desechable",
          ROOT not in tmp.resolve().parents and tmp.resolve() != ROOT,
          )
    check("a-72 · A4: ningún guardián de este gate apunta al libro de saldos REAL "
          f"({libro_real})",
          g_red.ledger_path.resolve() != libro_real
          and g_inc.ledger_path.resolve() != libro_real
          and ROOT not in g_red.ledger_path.resolve().parents)

    failed = [name for name, ok in results if not ok]
    print(f"\nEval spend guard: {len(results)-len(failed)}/{len(results)} PASS")
    if failed:
        print("FALLARON: " + ", ".join(failed))
        raise SystemExit(1)


async def _halt_wiring_probe(tmp: Path) -> dict:
    """Corre `harness.run_suite` DE VERDAD con un juez no gobernado (el camino del auditor).

    Sin DB ni grafo: se doblan solo las fronteras externas. Lo que se ejerce es el CABLEADO —
    `run_case` levanta `UngovernedJudge` → el `except SpendGuardHalt` de `run_suite` → `corte`
    → `build_report` → `summary.corte` → `exit_code_for`. El auditor reprodujo justamente que
    ese camino terminaba en exit code 0.
    """
    from mia.agent import llm as llm_mod
    from mia.eval import harness, spend_guard
    from mia.eval.cases import GoldenCase, GoldenCaseDoc
    from mia.metrics import usage as usage_metrics

    casos = [GoldenCase(id="j1", title="J1", message="m",
                        documents=(GoldenCaseDoc("d.txt", ("hola",)),),
                        rubric={"citas_clave": ["Ley 1"], "conclusiones_clave": []})]

    def juez_cualquiera(draft, diagnosis, rubric):
        return {"veredicto": "solido", "explicacion_llana": "ok"}

    async def fake_policy(tenant_id):
        return {"allow_real_data": True}

    async def fake_model_policy(tenant_id):
        return "suscripcion"

    async def fake_or(tenant_id):
        return False

    async def fake_flush():
        return None

    orig = (harness.read_eval_policy, llm_mod.model_policy_for,
            llm_mod.openrouter_allowed_for, usage_metrics.flush_pending)
    harness.read_eval_policy = fake_policy
    llm_mod.model_policy_for = fake_model_policy
    llm_mod.openrouter_allowed_for = fake_or
    usage_metrics.flush_pending = fake_flush
    guard = spend_guard.EvalSpendGuard(
        run_limit_usd=10.0, session_limit_usd=1000.0, global_limit_usd=1000.0,
        closeout_reserve_usd=0.0, session_id="s-halt", ledger_path=tmp / "halt.json")
    try:
        return await harness.run_suite("t", casos, run_id="halt",
                                       substantive_judge=juez_cualquiera, guard=guard)
    finally:
        (harness.read_eval_policy, llm_mod.model_policy_for,
         llm_mod.openrouter_allowed_for, usage_metrics.flush_pending) = orig


def _blocked_main_exit_code(visto: dict) -> int:
    """Código de salida de `run_eval.main()` cuando el guardián para FUERA del bucle de casos.

    Se hace que `_main` levante la parada más grave del modo hermético (una ruta que no se
    puede clasificar) y se comprueba que `main()` la convierte en salida distinta de cero con
    el motivo impreso — en vez de dejar escapar un `BaseException` como traceback pelado.
    """
    import run_eval as run_eval_mod
    from mia.eval import spend_guard

    prev = run_eval_mod._main

    def boom() -> int:
        visto["llamado"] = True
        raise spend_guard.SpendRouteUnavailable(
            "la ruta de gasto 'x' no se pudo resolver. No se corre el banco.")

    run_eval_mod._main = boom
    try:
        return run_eval_mod.main()
    finally:
        run_eval_mod._main = prev


def _measured_overshoot(tmp: Path) -> dict:
    """LA COTA FINAL, MEDIDA: ¿cuánto puede FACTURAR el proveedor por encima del tope NOMINAL?

    No es un razonamiento. Se mide lo que el PROVEEDOR cobra —no lo que el guardián cree que
    va cobrando— contra el tope NOMINAL, con margen de cierre CERO para que el número no se
    esconda detrás del colchón. Y se mide cada fuente POR SEPARADO: mezcladas, la más cara tapa
    a la otra y la prueba deja de ver el defecto de la barata (fue exactamente lo que pasó con
    la primera versión de esta medición, que daba verde con la cota de embeddings rota).

      · modelo     — proveedor `peor_caso=True`: un token por CARÁCTER de entrada, la salida
                     agotando el `max_tokens` de la llamada, y SERVIDO por el alias más caro
                     del catálogo (`claude-sonnet`) aunque se pidiera el barato (`claude-haiku`).
                     El guardián liquida al coste real, así que `run_spent_usd` ES lo facturado.
      · embeddings — cada intento factura el texto entero a UN TOKEN POR CARÁCTER (el techo que
                     la cota de S4 tiene que aguantar) y se agotan los `EMBED_MAX_ATTEMPTS`
                     intentos de verdad. Aquí lo facturado se cuenta APARTE del contador del
                     guardián: si la reserva se quedara corta (la regla de dedo de 4 chars por
                     token), el guardián no se enteraría — pero la tarjeta sí.
    """
    from types import SimpleNamespace

    from mia import config as cfg_mod
    from mia import embeddings as embeddings_mod
    from mia.agent import llm as llm_mod
    from mia.eval import spend_guard

    import litellm

    tope_nominal = 1.0

    def nuevo_guard(nombre: str):
        return spend_guard.EvalSpendGuard(
            run_limit_usd=tope_nominal, session_limit_usd=1000.0, global_limit_usd=1000.0,
            closeout_reserve_usd=0.0, session_id=f"s-cota-{nombre}",
            ledger_path=tmp / f"cota-{nombre}.json")

    # ── Fase A: SOLO el modelo, en su peor caso ──────────────────────────────
    gm = nuevo_guard("modelo")
    peor_modelo = FakeProvider(peor_caso=True, served_alias="claude-sonnet")
    with provider(peor_modelo), gm.activate():
        for _ in range(500):
            try:
                llm_mod.call_llm(big_messages(), task="delegation_triage", model="claude-haiku")
            except BaseException:  # noqa: BLE001 — el corte es el final esperado
                break

    # ── Fase B: SOLO los embeddings, en su peor caso ─────────────────────────
    ge = nuevo_guard("emb")
    textos = ["z" * 200_000]
    alias_emb = spend_guard.embed_alias()
    rate = spend_guard.EMBED_PRICES_PER_MTOK.get(alias_emb, spend_guard.UNKNOWN_EMBED_RATE)
    facturado_emb = {"usd": 0.0}
    intentos_emb = {"n": 0}

    def peor_litellm_embedding(*a, **kw):
        intentos_emb["n"] += 1
        # Lo que el proveedor cobra DE VERDAD en el peor caso: un token por carácter.
        facturado_emb["usd"] += sum(len(t) for t in kw["input"]) * rate / 1_000_000.0
        if intentos_emb["n"] % spend_guard.EMBED_MAX_ATTEMPTS != 0:
            raise RuntimeError("voyage: 500 transitorio")   # fuerza los 3 intentos
        return SimpleNamespace(
            data=[{"embedding": [0.0] * cfg_mod.EMBED_DIM} for _ in kw["input"]])

    prev_key, prev_emb = cfg_mod.VOYAGE_API_KEY, litellm.embedding
    try:
        cfg_mod.VOYAGE_API_KEY = "clave-de-prueba"
        litellm.embedding = peor_litellm_embedding
        with ge.activate():
            for _ in range(500):
                try:
                    embeddings_mod.embed_texts(textos)
                except BaseException:  # noqa: BLE001
                    break
    finally:
        litellm.embedding = prev_emb
        cfg_mod.VOYAGE_API_KEY = prev_key

    # ── Fase C: el modelo con la CACHÉ DE PROMPT en su peor caso (A1) ────────
    # Es la fase que F0 no tenía y por la que el auditor no certificaba el tope: TODO el prompt
    # se ESCRIBE a caché de 1 h, que se factura al DOBLE de la entrada normal y que LiteLLM
    # deja FUERA de `prompt_tokens` — así que antes de A1 esto se liquidaba a coste CERO de
    # entrada y el guardián creía estar gastando mucho menos de lo que la tarjeta pagaba.
    gc = nuevo_guard("cache")
    peor_cache = FakeProvider(peor_caso=True, cache_mode="creation",
                              served_alias="claude-sonnet")
    with provider(peor_cache), gc.activate():
        for _ in range(500):
            try:
                llm_mod.call_llm(big_messages(), task="delegation_triage", model="claude-haiku")
            except BaseException:  # noqa: BLE001
                break
    # El guardián liquida al coste real (`real_call_cost`), así que `run_spent_usd` ES lo
    # facturado — mismo razonamiento que la fase A, ahora con la escritura de caché contada.
    facturado_cache = gc.run_spent_usd
    exc_cache = round(facturado_cache - tope_nominal, 8)

    exc_modelo = round(gm.run_spent_usd - tope_nominal, 8)
    exc_emb = round(facturado_emb["usd"] - tope_nominal, 8)
    return {
        "tope_nominal": tope_nominal,
        "facturado_modelo": gm.run_spent_usd,
        "exceso_modelo": exc_modelo,
        "facturado_embeddings": facturado_emb["usd"],
        "contado_embeddings": ge.run_spent_usd,
        "exceso_embeddings": exc_emb,
        "facturado_cache": facturado_cache,
        "exceso_cache": exc_cache,
        "intentos_cache": peor_cache.calls,
        "exceso": max(exc_modelo, exc_emb, exc_cache),
        "corto": (gm.stop_reason is not None and ge.stop_reason is not None
                  and gc.stop_reason is not None),
        "intentos_modelo": peor_modelo.calls,
        "intentos_embedding": intentos_emb["n"],
    }


async def _suite_wiring_probe(tmp: Path, est: float) -> dict:
    """Corre `harness.run_suite` DE VERDAD con un tope ridículo, sin DB ni grafo.

    Se doblan solo las fronteras externas (política del despacho, persistencia de métricas) y
    `run_case`, que aquí hace UNA llamada al modelo por la envoltura real — suficiente para
    que el guardián corte de verdad y para que el corte recorra el camino real:
    `SpendLimitExceeded` → el `except` de `run_suite` → `corte=corte` → `build_report` →
    `summary.corte` → `exit_code_for`. Lo que este gate NO ejerce es el interior de `run_case`
    (DB + grafo): eso lo cubre `execution/test_eval_harness.py` contra la DB real.
    """
    from mia.agent import llm as llm_mod
    from mia.eval import harness, spend_guard
    from mia.eval.cases import GoldenCase, GoldenCaseDoc
    from mia.metrics import usage as usage_metrics
    from mia.policy import budget as policy_budget

    casos = [GoldenCase(id=f"w{i}", title=f"W{i}", message="m",
                        documents=(GoldenCaseDoc("d.txt", ("hola",)),)) for i in range(3)]

    async def fake_run_case(tenant_id, case, **kw):
        llm_mod.call_llm(big_messages(), task="main", model="claude-sonnet")
        return {"case_id": case.id, "title": case.title, "reached_draft": True,
                "score": {"ok": True}, "elapsed_ms": 1.0, "usage": None}

    async def fake_policy(tenant_id):
        return {"allow_real_data": False}

    async def fake_model_policy(tenant_id):
        return "suscripcion"

    async def fake_or(tenant_id):
        return False

    async def fake_flush():
        return None

    # R5 — el presupuesto MENSUAL del despacho ya NO se dobla a un no-op: se ESPÍA. Anularlo
    # era precisamente lo que ocultaba la fuga (una corrida del banco consumiendo el saldo del
    # mes del abogado, que la ruta HTTP `gold-cases:evaluate` corre con el TENANT REAL). El
    # espía deja ver si `reserve_call_sync` se llama o no, que es el hecho en disputa; y como
    # con la corrección NO se llama con scope de eval, tampoco toca la DB.
    espia: dict = {"reserve": [], "finish": []}

    def spy_reserve(tenant_id, estimated_usd, *, model=None, task=None):
        espia["reserve"].append({"tenant": tenant_id, "usd": estimated_usd, "model": model})
        return "hold-espia"

    def spy_finish(tenant_id, hold_id, actual):
        espia["finish"].append({"tenant": tenant_id, "hold": hold_id, "actual": actual})

    orig = (harness.run_case, harness.read_eval_policy, llm_mod.model_policy_for,
            llm_mod.openrouter_allowed_for, usage_metrics.flush_pending,
            policy_budget.reserve_call_sync, policy_budget.finish_call_sync)
    harness.run_case = fake_run_case
    harness.read_eval_policy = fake_policy
    llm_mod.model_policy_for = fake_model_policy
    llm_mod.openrouter_allowed_for = fake_or
    usage_metrics.flush_pending = fake_flush
    policy_budget.reserve_call_sync = spy_reserve
    policy_budget.finish_call_sync = spy_finish
    guard = spend_guard.EvalSpendGuard(
        run_limit_usd=est * 1.5, session_limit_usd=1000.0, global_limit_usd=1000.0,
        closeout_reserve_usd=0.0, session_id="s-wiring",
        ledger_path=tmp / "wiring.json")
    try:
        with provider(FakeProvider()):
            report = await harness.run_suite("t", casos, run_id="wiring", guard=guard)

        # Y el CONTROL de la prueba: el MISMO camino con un scope de PRODUCCIÓN tiene que
        # seguir reservando presupuesto mensual exactamente igual que antes del cambio.
        scope_prod = usage_metrics.set_usage_scope("tenant-real", "matter-1", source="api")
        try:
            with provider(FakeProvider()):
                llm_mod.call_llm(big_messages(), task="main", model="claude-sonnet")
        finally:
            usage_metrics.reset_usage_scope(scope_prod)
        return report, espia
    finally:
        (harness.run_case, harness.read_eval_policy, llm_mod.model_policy_for,
         llm_mod.openrouter_allowed_for, usage_metrics.flush_pending,
         policy_budget.reserve_call_sync, policy_budget.finish_call_sync) = orig


if __name__ == "__main__":
    main()
