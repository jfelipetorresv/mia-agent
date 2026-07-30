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
    check("y explica el beneficio en llano (cabe en lo que ya pagas)",
          "ya pagas" in activar)
    check("lo dice donde se elige la suscripción, no en otra pantalla suelta",
          activar.index("plan Max") > activar.index('title="Mi suscripción"')
          and activar.index("plan Max") - activar.index('title="Mi suscripción"') < 1200)
    # §G también aquí: la pantalla la lee un abogado, no un ingeniero.
    trozo = activar[activar.index('title="Mi suscripción"'):][:1200].lower()
    jerga = [p for p in ("api", "token", "fallback", "litellm", "endpoint") if p in trozo]
    check("sin jerga técnica en ese texto", not jerga, f"aparece: {', '.join(jerga)}")

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
