"""
Mia · test_cambio_de_motor_aviso.py — gate: la suscripción se apalanca, el crédito se avisa.

DECISIÓN DE PRODUCTO QUE ESTO CUSTODIA (Pipe, sesión 52): MIA se vende corriendo sobre la
suscripción que el abogado YA paga; si la suscripción no alcanza, la cadena puede acudir a
crédito de API o a OpenRouter. Eso es deliberado. Lo que NO puede pasar es que ocurra en
silencio: en el piloto con un expediente real la suscripción expiró tres veces (300s cada una,
15 minutos tirados), el turno se resolvió con crédito de tarjeta —USD 0,57— y nada en pantalla
lo mencionó. Un cargo que el abogado no esperaba es un cargo que no autorizó.

Qué se verifica (sin red, sin modelo):

  1. SALTO RÁPIDO: ante timeout de un alias de la suscripción NO se gastan los reintentos. El
     reintento manda el MISMO prompt gigante, así que por construcción vuelve a expirar; lo que
     el defecto costaba eran 15 minutos de espera antes de hacer lo que iba a hacer igual.
  2. Los timeouts de OTROS proveedores conservan su reintento (ahí sí suele ser transitorio).
  3. El cambio de motor queda REGISTRADO, con desde/hacia/motivo.
  4. El aviso solo aparece cuando el abogado va a PAGAR: de suscripción a un motor de pago sí;
     entre motores de nube no (no cambia quién paga); a motor local tampoco (no cuesta dinero).
  5. El aviso dice qué pasó, que hay costo, y que la suscripción se usa primero SIEMPRE.
  6. Trae la sugerencia del plan Max (petición expresa de Pipe).
  7. §G: ni un alias técnico, ni un nombre de proveedor, ni la palabra 'fallback' en lo que lee
     el abogado.

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_cambio_de_motor_aviso.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia.agent import llm  # noqa: E402
from mia.agent.error_classifier import LLMErrorKind  # noqa: E402

_results: list[tuple[str, bool]] = []
_ultimo_error: list[str] = []


def check(nombre: str, ok: bool, detalle: str = "") -> None:
    _results.append((nombre, ok))
    marca = "[OK]  " if ok else "[FAIL]"
    linea = f"  {marca} {nombre}"
    if not ok and detalle:
        linea += f" — {detalle}"
    print(linea)


class _ClienteQueExpira:
    """Doble del cliente: cuenta los intentos y siempre expira."""

    def __init__(self) -> None:
        self.intentos = 0

    def __call__(self, *a, **kw):
        self.intentos += 1
        raise TimeoutError("El CLI 'claude' no respondió en 300s (timeout).")


def _correr_un_alias(alias: str, next_alias: str | None, max_retries: int = 3):
    """Llama al ejecutor de UN alias con un cliente que siempre expira, y devuelve
    (intentos, saltó)."""
    cliente = _ClienteQueExpira()
    original = llm._invoke_metered
    llm._invoke_metered = lambda client, al, kwargs, task: cliente()  # type: ignore[assignment]
    salto = False
    try:
        llm._call_with_retries(  # type: ignore[attr-defined]
            client=None, kwargs={}, max_retries=max_retries, task="main",
            alias=alias, next_alias=next_alias,
        )
    except llm._FallbackNeeded:  # type: ignore[attr-defined]
        salto = True
    except Exception as exc:  # noqa: BLE001
        salto = False
        _ultimo_error.append(f"{type(exc).__name__}: {exc}")
    finally:
        llm._invoke_metered = original  # type: ignore[assignment]
    return cliente.intentos, salto


def _correr_turno_sse(fallar: bool, registrar: bool) -> list[dict]:
    """Ejerce el cuerpo real del SSE del turno con un grafo de mentira: sin DB, sin modelo.

    `registrar` simula que la cadena de motores saltó de la suscripción a un motor de pago
    DENTRO del turno (que es donde ocurre de verdad); `fallar` simula que el turno revienta
    después de haber gastado ese crédito."""
    import asyncio

    from mia.agent import llm as _llm
    from mia.api.routes import stream as _stream

    async def eventos():
        yield {"event": "thinking", "data": '{"message": "trabajando"}'}
        if registrar:
            _llm._registrar_cambio_de_motor("main", "cli-claude", "claude-sonnet", "timeout")
        if fallar:
            raise RuntimeError("el turno reventó después de gastar crédito")
        yield {"event": "awaiting_review", "data": '{"message": "listo"}'}

    async def consumir():
        return [ev async for ev in _stream.turno_sse("hola", eventos, "t", "m")]

    return asyncio.run(consumir())


def _gate_circuit_breaker() -> None:
    """Ejerce call_llm COMPLETO (cadena real de la política 'suscripcion') con un doble que
    hace expirar la suscripción y responder la nube. Verifica que dentro del MISMO turno la
    suscripción solo paga el timeout una vez, y que el turno siguiente vuelve a intentarla."""

    class _Resp:
        choices: list = []
        usage = None

    invocaciones: list[str] = []

    def _doble(client, alias, kwargs, task):
        invocaciones.append(alias)
        if alias.startswith("cli-"):
            raise TimeoutError("El CLI 'claude' no respondió en 300s (timeout).")
        return _Resp()

    original_metered = llm._invoke_metered
    original_client = llm._get_client
    llm._invoke_metered = _doble  # type: ignore[assignment]
    llm._get_client = lambda: None  # type: ignore[assignment]
    try:
        with llm.recolectar_cambios_de_motor() as cambios:
            # Nodo 1 del grafo: la suscripción expira y se salta a la nube.
            llm.call_llm([{"role": "user", "content": "hola"}], task="main")
            tras_nodo_1 = list(invocaciones)
            # Nodos 2 y 3 del mismo turno: la suscripción NO debe volver a intentarse.
            llm.call_llm([{"role": "user", "content": "hola"}], task="main")
            llm.call_llm([{"role": "user", "content": "hola"}], task="main")
        check("el primer nodo intentó la suscripción y saltó a la nube",
              tras_nodo_1 == ["cli-claude", "claude-sonnet"], str(tras_nodo_1))
        cli_total = invocaciones.count("cli-claude")
        check("los nodos siguientes del turno NO volvieron a pagar el timeout",
              cli_total == 1, f"cli-claude se intentó {cli_total} veces en el turno")
        check("cada nodo saltado quedó registrado para el aviso de costo",
              len(cambios) == 3, f"{len(cambios)} cambios")

        # Turno NUEVO: el breaker murió con el anterior y la suscripción va primero otra vez.
        invocaciones.clear()
        with llm.recolectar_cambios_de_motor():
            llm.call_llm([{"role": "user", "content": "hola"}], task="main")
        check("el turno siguiente vuelve a intentar la suscripción primero",
              invocaciones and invocaciones[0] == "cli-claude", str(invocaciones))

        # Sin contexto de turno (scripts/tests que llaman directo): comportamiento intacto.
        invocaciones.clear()
        llm.call_llm([{"role": "user", "content": "hola"}], task="main")
        llm.call_llm([{"role": "user", "content": "hola"}], task="main")
        check("sin turno activo no hay breaker (cada llamada intenta la suscripción)",
              invocaciones.count("cli-claude") == 2, str(invocaciones))
    finally:
        llm._invoke_metered = original_metered  # type: ignore[assignment]
        llm._get_client = original_client  # type: ignore[assignment]


def _gate_enganche_backend() -> None:
    import json

    from mia.api.routes import stream as _stream

    normales = _correr_turno_sse(fallar=False, registrar=True)
    eventos = [e["event"] for e in normales]
    check("el turno emite el aviso de costo", _stream.AVISO_DE_COSTO_EVENT in eventos,
          str(eventos))
    check("y lo emite AL FINAL, después del resultado del turno",
          eventos and eventos[-1] == _stream.AVISO_DE_COSTO_EVENT, str(eventos))
    if _stream.AVISO_DE_COSTO_EVENT in eventos:
        data = json.loads(normales[-1]["data"])
        check("el evento lleva el texto que lee el abogado",
              "costo" in data.get("message", "").lower())
        check("y la recomendación del plan Max",
              "max" in (data.get("sugerencia") or "").lower())

    sin_cambio = [e["event"] for e in _correr_turno_sse(fallar=False, registrar=False)]
    check("un turno que NO cambió de motor no dice nada",
          _stream.AVISO_DE_COSTO_EVENT not in sin_cambio, str(sin_cambio))

    roto = [e["event"] for e in _correr_turno_sse(fallar=True, registrar=True)]
    check("si el turno falla DESPUÉS de gastar crédito, el aviso sale igual",
          "error" in roto and _stream.AVISO_DE_COSTO_EVENT in roto, str(roto))

    # El cierre del borrador también razona: mismo envoltorio, mismo aviso.
    hitl = (ROOT / "backend" / "mia" / "api" / "routes" / "hitl.py").read_text(encoding="utf-8")
    check("la aprobación del borrador usa el mismo envoltorio", "turno_sse(" in hitl)


def _gate_enganche_frontend() -> None:
    fe = ROOT / "frontend" / "app"
    comp = (fe / "_components" / "AvisoDeCosto.tsx")
    check("existe el componente del aviso", comp.exists())
    if not comp.exists():
        return
    texto_comp = comp.read_text(encoding="utf-8")
    # §G: el componente NO redacta — muestra lo que manda el backend. Si redactara, habría
    # dos textos que auditar y solo uno cubierto por los checks de arriba.
    check("el componente no inventa su propio texto para el abogado",
          "crédito" not in texto_comp.lower() or "aviso.message" in texto_comp)

    for pantalla in ("asuntos/[id]/page.tsx", "proyectos/[id]/page.tsx"):
        src = (fe / pantalla).read_text(encoding="utf-8")
        check(f"{pantalla} atiende el evento", '"aviso_de_costo"' in src)
        check(f"{pantalla} lo pinta", "<AvisoDeCosto" in src)

    revisar = (fe / "asuntos" / "[id]" / "revisar" / "page.tsx").read_text(encoding="utf-8")
    check("la revisión del borrador no pierde el aviso al volver al asunto",
          '"aviso_de_costo"' in revisar and "depositarAvisoDeCosto" in revisar)
    asunto = (fe / "asuntos" / "[id]" / "page.tsx").read_text(encoding="utf-8")
    check("y el asunto lo recoge al volver", "recogerAvisoDeCosto" in asunto)


def main() -> int:  # noqa: C901
    print("== gate: la suscripción se apalanca, el crédito se avisa ==")

    # Sin dormir de verdad entre reintentos (el gate no puede tardar minutos).
    original_sleep = llm.time.sleep
    llm.time.sleep = lambda s: None  # type: ignore[assignment]
    try:
        print("\n1 · salto rápido ante timeout de la suscripción")
        with llm.recolectar_cambios_de_motor() as cambios:
            intentos, salto = _correr_un_alias("cli-claude", "claude-sonnet", max_retries=3)
        check("saltó de motor", salto)
        check("NO gastó los reintentos: un solo intento y salta",
              intentos == 1, f"{intentos} intentos")
        check("quedó registrado el cambio", len(cambios) == 1, f"{len(cambios)}")
        if cambios:
            c = cambios[0]
            check("el registro dice desde/hacia/motivo",
                  c["desde"] == "cli-claude" and c["hacia"] == "claude-sonnet"
                  and c["motivo"] == LLMErrorKind.TIMEOUT.value, str(c))

        print("\n2 · los timeouts de otros proveedores conservan su reintento")
        with llm.recolectar_cambios_de_motor():
            intentos_nube, salto_nube = _correr_un_alias("claude-sonnet", "mia-local",
                                                         max_retries=3)
        check("el motor de nube sí reintenta antes de saltar",
              intentos_nube == 4, f"{intentos_nube} intentos (esperados 4 = 1 + 3)")
        check("y al final también salta", salto_nube)

        print("\n3 · sin próximo motor no se salta a la nada")
        with llm.recolectar_cambios_de_motor():
            intentos_solo, _ = _correr_un_alias("cli-claude", None, max_retries=1)
        check("sin motor siguiente, el salto rápido no se dispara",
              intentos_solo >= 2, f"{intentos_solo} intentos")

        print("\n3-bis · circuit-breaker: el turno no paga el mismo timeout dos veces")
        # El defecto que esto custodia (sesión 56): el salto rápido evitaba los reintentos
        # dentro de UNA llamada, pero cada nodo del grafo volvía a intentar la suscripción
        # y volvía a esperar 300s — 2-3 nodos ≈ 13 minutos antes de caer al respaldo.
        _gate_circuit_breaker()
    finally:
        llm.time.sleep = original_sleep  # type: ignore[assignment]

    print("\n4 · el aviso aparece solo cuando el abogado va a pagar")
    check("sin cambios no hay aviso", llm.aviso_cambio_de_motor([]) is None)
    check("None no revienta", llm.aviso_cambio_de_motor(None) is None)
    a = llm.aviso_cambio_de_motor(
        [{"task": "main", "desde": "cli-claude", "hacia": "claude-sonnet", "motivo": "timeout"}])
    check("de la suscripción a un motor de pago SÍ avisa", a is not None)
    check("entre motores de nube NO avisa (no cambia quién paga)",
          llm.aviso_cambio_de_motor(
              [{"desde": "claude-sonnet", "hacia": "openrouter-main", "motivo": "timeout"}]) is None)
    check("al motor local NO avisa (no cuesta dinero)",
          llm.aviso_cambio_de_motor(
              [{"desde": "cli-claude", "hacia": "mia-local", "motivo": "timeout"}]) is None)
    check("entre motores de la propia suscripción NO avisa",
          llm.aviso_cambio_de_motor(
              [{"desde": "cli-claude", "hacia": "cli-claude-haiku", "motivo": "timeout"}]) is None)

    print("\n5 · qué dice el aviso")
    assert a is not None
    texto = f"{a['aviso']} {a['sugerencia']}"
    check("dice que hay un costo", "costo" in a["aviso"].lower())
    check("dice que la suscripción se usa primero siempre",
          "primero" in a["aviso"].lower())
    check("explica que fue por el tamaño del trabajo", a["por_tiempo"] is True
          and "grande" in a["aviso"].lower())
    check("cuenta cuántas veces pasó", a["veces"] == 1)

    print("\n6 · la sugerencia del plan Max (petición expresa de Pipe)")
    check("sugiere el plan Max", "max" in a["sugerencia"].lower())
    check("y explica el beneficio en llano (cabe en lo que ya pagas)",
          "ya pagas" in a["sugerencia"].lower())

    print("\n7 · §G — nada técnico en lo que lee el abogado")
    prohibido = ["fallback", "cli-claude", "claude-sonnet", "openrouter", "alias", "timeout",
                 "api", "token", "litellm", "proveedor"]
    filtrados = [p for p in prohibido if p in texto.lower()]
    check("ni jerga ni nombres de motor en el texto del abogado",
          not filtrados, f"aparece: {', '.join(filtrados)}")

    print("\n8 · la recomendación del plan Max también en la INSTALACIÓN")
    # Pipe: el aviso no puede llegar solo cuando ya se gastó crédito; al elegir el motor, el
    # abogado tiene que leer que para expedientes grandes le conviene un plan Max.
    activar = (ROOT / "frontend" / "app" / "activar" / "page.tsx").read_text(encoding="utf-8")
    check("la pantalla de activación existe y ofrece la suscripción",
          'title="Mi suscripción"' in activar)
    check("recomienda el plan Max al elegir el motor", "plan Max" in activar)
    # Se exige el CONCEPTO, no una redacción literal: el texto se ha reescrito dos veces por
    # claridad y un check atado a las palabras exactas lo rompe cada vez sin que nada haya
    # empeorado. Lo sustantivo es que diga que con Max no se paga aparte.
    beneficio = any(f in activar for f in ("ya pagas", "sin costo extra", "sin cargos"))
    check("y explica el beneficio en llano (con Max no se paga aparte)", beneficio)
    check("nombra el problema que evita (el expediente que no cabe)",
          "no me cabe" in activar or "no cabe" in activar or "a medias" in activar)
    check("lo dice donde se elige la suscripción, no en otra pantalla suelta",
          activar.index("plan Max") > activar.index('title="Mi suscripción"')
          and activar.index("plan Max") - activar.index('title="Mi suscripción"') < 1200)
    # §G también aquí: la pantalla la lee un abogado, no un ingeniero.
    trozo = activar[activar.index('title="Mi suscripción"'):][:1200].lower()
    jerga = [p for p in ("api", "token", "fallback", "litellm", "endpoint") if p in trozo]
    check("sin jerga técnica en ese texto", not jerga, f"aparece: {', '.join(jerga)}")

    print("\n9 · el aviso LLEGA A LA PANTALLA (enganche, sesión 53)")
    # El defecto que esto custodia: en la sesión 52 el aviso quedó calculado y probado, pero
    # nadie lo emitía. Un aviso que no sale de la memoria del proceso no avisa a nadie.
    _gate_enganche_backend()

    print("\n10 · y la pantalla lo PINTA")
    _gate_enganche_frontend()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
