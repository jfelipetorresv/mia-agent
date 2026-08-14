"""Mia · eval.spend_guard — TOPE DE GASTO fail-closed del banco de pruebas (Frente A).

El problema que cierra este módulo: el eval (`execution/run_eval.py` → `eval.harness`)
corre el GRAFO COMPLETO contra el modelo VIVO, pero nunca fijaba el scope de uso
(`metrics.usage.set_usage_scope`). Consecuencia doble:
  1. las llamadas reales del banco NO quedaban registradas (ni un centavo en `turn_usage`);
  2. la rama de reserva de presupuesto de `agent/llm.call_llm` solo entra si HAY scope, así
     que el banco podía gastar sin NINGÚN techo.

Este módulo aporta el techo propio del eval, con TRES granularidades:
  · por CORRIDA   — `--max-usd` (default `DEFAULT_RUN_LIMIT_USD`), en memoria del guardián;
  · por SESIÓN    — `SESSION_LIMIT_USD` (USD 30, autorizado por el dueño del producto),
                    PERSISTENTE entre corridas de la misma sesión (fichero de saldo);
  · GLOBAL        — `GLOBAL_LIMIT_USD`, techo duro de seguridad sobre todas las sesiones.

────────────────────────────────────────────────────────────────────────────────
DÓNDE SE ENGANCHA (y por qué AHÍ y no en `call_llm`)
────────────────────────────────────────────────────────────────────────────────
El dinero NO se gasta en `call_llm`: se gasta en CADA INTENTO que sale a la red. Una sola
llamada a `call_llm` puede facturar varios intentos, porque `agent.llm._call_with_retries`
reintenta hasta `MAX_RETRIES` veces DENTRO de un alias y luego `call_llm` SALTA al siguiente
alias de la cadena — que puede ser más caro (la política 'suscripcion' arranca en
`cli-claude`, GRATIS, con `claude-sonnet`, PAGADO, detrás). Envolver `call_llm` y reservar
UNA vez dejaba varios intentos cobrables bajo una sola reserva, sin cota demostrable de
exceso sobre el tope.

Por eso la envoltura va sobre `agent.llm._invoke`, que es el punto ÚNICO donde se despacha
UN intento (CLI de la suscripción o proxy LiteLLM) y donde el alias ya está resuelto de
forma exacta. Un intento = una reserva = una liquidación.

COTA DE EXCESO (invariante G, demostrada en `execution/test_eval_spend_guard.py`):
  gasto_final  ≤  tope_efectivo  +  Σ_{intentos en vuelo} max(0, coste_real − estimación)
Con la corrida secuencial del banco hay UN intento en vuelo a la vez, así que la cota es
`tope_efectivo + (coste_real − estimación) de UN intento`.

R1 — POR QUÉ LA SUBESTIMACIÓN ES CERO (y no "pequeña"). La versión anterior reservaba con
`metrics.usage.estimated_call_cost`, que es una ESTIMACIÓN de producción, no una cota: supone
~4 caracteres por token de entrada y una salida "típica" (8 192 tokens para `main`, 4 096 para
el resto). Como el grafo NUNCA pasa `max_tokens` a `call_llm` (cero ocurrencias medidas), una
sola llamada podía devolver hasta 64 000 tokens de salida: se midió un intento de
`task=delegation_triage` estimado en USD 0.0915 cuyo coste real era USD 0.9900 —una
subestimación de USD 0.8985 frente a un margen de cierre de USD 0.25—, así que la afirmación
"el tope nominal no se pasa nunca" era FALSA. Ahora el guardián hace dos cosas:

  1. ACOTA la salida. Todo intento que pase por aquí sale con
     `max_tokens = EVAL_MAX_OUTPUT_TOKENS` si venía sin tope o con uno mayor. El proveedor NO
     puede devolver más, así que el techo de salida deja de ser una suposición.
  2. RESERVA CON UNA COTA SUPERIOR, no con una estimación (`upper_bound_call_cost`):
       · entrada — 1 token por CARÁCTER del payload (ningún tokenizador BPE produce más de un
         token por carácter), más un colchón fijo por el andamiaje del protocolo;
       · salida  — el techo de tokens del punto 1;
       · tarifa  — la MÁS CARA del catálogo (`_WORST_RATES`), no la del alias pedido, porque
         el alias servido que vuelve en `resp.model` puede ser otro.
     Coste real ≤ reserva SIEMPRE ⇒ subestimación máxima = 0 (`worst_case_underestimate_usd`).

Con eso, el margen de cierre deja de ser una constante a ojo: `CLOSEOUT_RESERVE_USD` se
DERIVA del propio techo de tokens (`required_closeout_margin_usd` = subestimación máxima +
un intento completo en el techo). Invariante G, ahora verdadero y medible: mientras el
guardián reserve con `upper_bound_call_cost`, el tope NOMINAL no se pasa nunca.

EMBEDDINGS. `embeddings.embed_texts` (Voyage, `voyage-law-2`) es red PAGADA y jamás pasaba
por `call_llm`: el banco los generaba al sembrar cada caso y el grafo los volvía a generar
por consulta, todo por fuera del tope. Ahora también se envuelve, con su propia tarifa
(`EMBED_PRICES_PER_MTOK` — vive aquí y no en `metrics.usage`, que solo tarifa LLM).

R2 — EL EMBEDDING TAMBIÉN SE RESERVA POR INTENTO. `embeddings.embed_texts` llama a
`litellm.embedding(..., num_retries=2)`: hasta TRES intentos facturables bajo una sola
reserva — el mismo defecto que ya se cerró para el LLM enganchando por intento. Bajo guardián,
`_guarded_embed_texts` sustituye `litellm.embedding` por una envoltura que fuerza
`num_retries=0` (los reintentos los hace el guardián) y RESERVA CADA INTENTO por separado,
hasta `EMBED_MAX_ATTEMPTS`. La política de reintentos que quería `embeddings.py` se conserva
intacta; lo que cambia es quién los cuenta.

────────────────────────────────────────────────────────────────────────────────
Invariantes (cada uno con su prueba de mutación en el gate)
────────────────────────────────────────────────────────────────────────────────
  A. CORTA ANTES, NO DESPUÉS. Antes de cada intento se ESTIMA su coste y se proyecta contra
     los tres topes. Si la proyección se pasa, el intento NO se hace (`SpendLimitExceeded`).
  B. MARGEN DE CIERRE. `CLOSEOUT_RESERVE_USD` es intocable: el tope EFECTIVO es
     `limite - margen`, para que al cortar quede saldo para el cierre limpio.
  C. FAIL-CLOSED. Si el saldo acumulado no se puede leer o escribir (fichero corrupto,
     saldo NEGATIVO o no finito, bloqueo imposible), NO se gasta: `SpendControlUnavailable`.
     Nunca fail-open. (Deliberadamente al revés que `policy.budget.enforce_budget`, que es
     fail-open a propósito porque es la guardia de un turno HTTP del abogado; aquí no hay
     abogado esperando, hay una tarjeta de crédito.)
  D. INCIERTO SE COBRA. Si el intento muere a mitad, la reserva NO se libera.
  E. ATÓMICO DE VERDAD. Leer el gasto de la corrida, comprobar los tres topes, reservar en
     el fichero y SUMAR al contador de la corrida ocurren TODO dentro del mismo `self._lock`
     (y el fichero, además, bajo cerrojo entre procesos). No hay ventana entre leer y sumar.
  F. STICKY. Un guardián que ya cortó NO vuelve a autorizar.
  G. COTA DE EXCESO demostrada (arriba).
  H. LA PARADA NO SE PUEDE TRAGAR. `SpendLimitExceeded` y `SpendControlUnavailable` heredan
     de `BaseException` (como `KeyboardInterrupt`): los ~19 `except Exception` de
     `agents/graph.py` NO pueden comérselas y hacer pasar una corrida CORTADA por completa.
  I. MODO HERMÉTICO — SE CIERRA EL MUNDO, NO SE ENUMERAN HUECOS (R7). Ver abajo.
  J. TODA PARADA DEL GUARDIÁN DERIVA DE `SpendGuardHalt` (S1). No solo el corte por dinero:
     también "no hay tope activo", "juez no gobernado" y "una ruta no se pudo clasificar".
     `guard_exception_audit()` recorre el módulo y delata cualquier excepción propia que NO
     derive de `SpendGuardHalt`, para que la próxima que alguien añada no se pueda colar por
     un `except Exception` y hacer pasar una corrida BLOQUEADA por completa (con código 0).

────────────────────────────────────────────────────────────────────────────────
MODO HERMÉTICO — el registro de rutas de gasto (R7)
────────────────────────────────────────────────────────────────────────────────
Tres rondas enumerando huecos de uno en uno (juez, Pinecone, NotebookLM, MCP, subprocesos…)
produjeron un hueco nuevo en cada ronda. Enumerar no converge. Así que se invierte la carga
de la prueba: durante una corrida del banco, TODA ruta capaz de gastar dinero o salir a la
red está en uno de estos tres estados, sin cuarta opción:

  · GOBERNADA  — pasa por el guardián (reserva antes, liquida después);
  · DESACTIVADA— devuelve un valor vacío de un camino YA soportado y fail-soft del producto;
  · DECLARADA  — hueco conocido, imposible de gobernar desde aquí, escrito en el código.

`SPEND_ROUTES` es ese registro. `ensure_installed()` lo recorre, aplica el estado y COMPRUEBA
que quedó aplicado; si una entrada no se puede aplicar —import roto, atributo renombrado,
firma cambiada— la corrida NO ARRANCA (`SpendRouteUnavailable`, que es un `SpendGuardHalt`).
Fail-closed de arranque, no aviso. Consecuencia buscada: la próxima ruta que alguien añada al
producto sin clasificarla hace fallar el banco en vez de gastar en silencio.

Aliases GRATIS (`FREE_ALIASES`, cadenas `cli-*`, motor local) tienen coste marginal cero:
el tope no los estorba (ni reserva ni comprueba), pero SÍ se cuentan sus tokens y su
duración — medir es gratis y el banco necesita el dato.

────────────────────────────────────────────────────────────────────────────────
INSTALACIÓN PERMANENTE (nunca se desinstala)
────────────────────────────────────────────────────────────────────────────────
`ensure_installed()` envuelve `agent.llm._invoke` y `embeddings.embed_texts` UNA vez por
proceso y NO las desenvuelve jamás. La envoltura solo ACTÚA si hay un guardián en el
ContextVar del contexto actual; si no lo hay, delega tal cual, así que producción queda
intacta aunque el parche esté puesto para siempre.

Por qué sin `uninstall`: la versión anterior desinstalaba al salir del bloque y ponía el
original en None. Un módulo que hiciera `from ... import call_llm` DURANTE la ventana
(import diferido, primera vez) capturaba la envoltura, no quedaba en la lista de re-enlace,
y al desinstalar su referencia apuntaba a una envoltura con original None → `TypeError` en
PRODUCCIÓN para siempre hasta reiniciar el proceso. Alcanzable de verdad por la ruta HTTP
`gold-cases:evaluate`, que corre el banco DENTRO del proceso de la API. Sin desinstalación
no hay ventana, no hay original None y no hay forma de romper producción.
`install()` se conserva como envoltorio idempotente y compatible: instala y NO revierte.
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterator, Optional

logger = logging.getLogger("mia.eval.spend_guard")

# ── Topes por defecto ─────────────────────────────────────────────────────────
DEFAULT_RUN_LIMIT_USD = 5.0      # una corrida del banco (--max-usd lo sobre-escribe)
SESSION_LIMIT_USD = 30.0         # sesión de pruebas — autorizado por el dueño del producto
GLOBAL_LIMIT_USD = 100.0         # techo duro de seguridad sobre TODAS las sesiones

# ── Techo de tokens del eval y cota superior de coste (R1) ───────────────────
# Todo intento que pase por el guardián sale con este `max_tokens` si venía sin tope o con uno
# mayor. Es el mismo número que `metrics.usage.estimated_call_cost` ya suponía para la tarea
# principal, así que no encoge la respuesta del caso típico; lo que hace es CERRAR el techo,
# que antes estaba abierto hasta los 64 000 tokens que admite el modelo.
EVAL_MAX_OUTPUT_TOKENS = 8_192
# La tarifa más cara del catálogo (USD por 1M de tokens: entrada, salida). Se reserva con ella
# y no con la del alias pedido, porque `_alias_and_cost` liquida con el alias SERVIDO
# (`resp.model`), que puede ser más caro que el pedido.
_WORST_RATES = (3.00, 15.00)

# ── CACHÉ DE PROMPT: la escritura se factura MÁS CARA que la entrada normal (A1) ──────
# `agent/llm._messages_with_cache` marca el prefijo estable del system para el prefix caching
# de Anthropic con `cache_control: {"type": "ephemeral", "ttl": "1h"}` (llm.py ~L516-522).
# Tarifa vigente de Anthropic sobre el precio de ENTRADA del modelo:
#   · escritura de caché de 1 h  → 2.00x   (la que usa MIA)
#   · escritura de caché de 5 min→ 1.25x
#   · lectura de caché           → 0.10x   (ABARATA: nunca encarece)
# Estos tres números son la razón por la que el coste no se puede seguir calculando con
# `metrics.usage.cost_usd`, que tarifa TODO el prompt a la tarifa de entrada normal.
CACHE_WRITE_MULTIPLIER_1H = 2.00
CACHE_WRITE_MULTIPLIER_5M = 1.25
CACHE_READ_MULTIPLIER = 0.10
# Con qué multiplicador se LIQUIDA una escritura de caché. MIA solo emite `ttl: "1h"`, así que
# 2.00x es el valor exacto, no una aproximación; si algún día se emitieran bloques de 5 min,
# seguiría siendo la cota alta de los dos (nunca se sub-factura).
CACHE_WRITE_MULTIPLIER = CACHE_WRITE_MULTIPLIER_1H

# ¿CÓMO VIENEN LOS CAMPOS? (medido en el LiteLLM instalado, no supuesto —
# `litellm/llms/anthropic/chat/transformation.py::calculate_usage`, L810-856):
#     prompt_tokens = input_tokens + cache_read_input_tokens      ← la LECTURA va DENTRO
#     cache_creation_input_tokens                                  ← la ESCRITURA va FUERA
#     total_tokens  = prompt_tokens + completion_tokens            ← la escritura NO se cuenta
# De ahí los dos defectos que cierra A1, en direcciones OPUESTAS:
#   · la LECTURA se cobraba a 1.00x cuando cuesta 0.10x  → se SOBRE-facturaba;
#   · la ESCRITURA se cobraba a 0.00x cuando cuesta 2.00x → se SUB-facturaba, y eso es lo que
#     impedía certificar el tope (una sub-facturación rompe la cota, una sobre-facturación no).
_CACHE_READ_INSIDE_PROMPT_TOKENS = True
# Colchón de entrada: el andamiaje del protocolo (roles, delimitadores, plantilla de tools)
# añade tokens que no están en el payload que se serializa aquí.
_PROMPT_OVERHEAD_TOKENS = 1_024


def ceiling_attempt_output_usd() -> float:
    """Coste de la SALIDA de un intento que agota el techo de tokens, a la tarifa más cara."""
    return round(EVAL_MAX_OUTPUT_TOKENS * _WORST_RATES[1] / 1_000_000.0, 6)


def worst_case_underestimate_usd() -> float:
    """Cuánto puede subestimarse UN intento cobrable. CERO, por construcción de
    `upper_bound_call_cost` (cota superior, no estimación) — ver R1 en el encabezado.

    No es una constante decorativa: `execution/test_eval_spend_guard.py` la comprueba contra
    el PEOR caso medible (payload máximo, salida a tope, alias servido más caro que el pedido)
    y la mutación que devuelve el estimador de producción a la rama de reserva la pone roja.
    """
    return 0.0


def required_closeout_margin_usd() -> float:
    """Margen de cierre MÍNIMO exigible, derivado del techo de tokens (no elegido a ojo).

    Tiene dos sumandos, uno por cada trabajo del margen (invariante B):
      · absorber la subestimación máxima de un intento en vuelo → `worst_case_underestimate_usd`;
      · dejar saldo para cerrar limpio → un intento completo agotando el techo de salida.
    """
    return round(worst_case_underestimate_usd() + ceiling_attempt_output_usd(), 6)


# Margen intocable para el cierre limpio. DERIVADO (ver arriba): USD 0.12288 con el techo
# actual. Antes era 0.25 "a ojo" y resultó ser MENOR que la subestimación real de un intento
# (USD 0.8985 medidos), o sea que no cumplía el trabajo que decía cumplir.
CLOSEOUT_RESERVE_USD = required_closeout_margin_usd()

LEDGER_ENV = "MIA_EVAL_SPEND_LEDGER"
SESSION_ENV = "MIA_EVAL_SESSION_ID"
_LOCK_TIMEOUT_S = 10.0
_LOCK_STALE_S = 60.0

# Tarifa de EMBEDDINGS (USD por 1M de tokens). Vive aquí y no en `metrics.usage`
# (`PRICES_PER_MTOK` tarifa LLM de chat, con precio de entrada Y de salida; un embedding solo
# tiene entrada). Fuente: tarifa pública de Voyage AI para `voyage-law-2`. Un modelo de
# embeddings desconocido usa la tarifa más CARA conocida: mejor sobre-reservar que abrir hueco.
EMBED_PRICES_PER_MTOK: dict[str, float] = {
    "voyage-law-2": 0.12,
    "voyage-3": 0.06,
    "voyage-3-lite": 0.02,
}
UNKNOWN_EMBED_RATE = 0.12
# S4 — COTA, no promedio. La versión anterior usaba 4 caracteres por token, que es la MEDIA de
# un texto en prosa, no un techo: un texto denso en símbolos, en otro alfabeto o troceado por
# el tokenizador produce más tokens que chars/4, y con eso la "reserva" de embeddings era una
# conjetura (el auditor calculó un peor caso de USD 89 con 1 char/token). Para el LLM ya se
# hizo lo correcto (`upper_bound_call_cost`: 1 token por CARÁCTER es cota dura para cualquier
# tokenizador de sub-palabras, porque ningún token cubre menos de un carácter). Aquí igual:
# UN TOKEN POR CARÁCTER. Sobre-reserva en el caso típico —y se devuelve al liquidar—, pero el
# peor caso deja de existir como incógnita.
_EMBED_CHARS_PER_TOKEN = 1
# Intentos facturables que puede hacer UNA llamada a `embeddings.embed_texts`: el primero más
# los `num_retries=2` que pide `backend/mia/embeddings.py`. Bajo guardián los hace el guardián,
# reservando cada uno (R2).
EMBED_MAX_ATTEMPTS = 3


class SpendGuardHalt(BaseException):
    """Base de las paradas del tope. Hereda de `BaseException` A PROPÓSITO (invariante H).

    Una parada por dinero es del mismo rango que `KeyboardInterrupt`: NO es un error del
    turno que un nodo pueda absorber y seguir. `agents/graph.py` tiene ~19 `except Exception`
    alrededor de llamadas al modelo; con `Exception` como base, un corte caía en uno de ellos,
    el guardián quedaba sticky pero `summary.corte` salía None y la corrida CORTADA se
    reportaba COMPLETA con código de salida 0. Heredando de `BaseException` eso es imposible.
    """


class SpendLimitExceeded(SpendGuardHalt):
    """El intento siguiente habría pasado un tope: NO se hizo. `str(e)` va en llano."""


class SpendControlUnavailable(SpendGuardHalt):
    """No se pudo verificar el saldo acumulado, así que NO se gasta (fail-closed)."""


class EvalGuardMissing(SpendGuardHalt):
    """Se intentó correr algo del banco SIN tope de gasto activo (fail-closed, D1).

    S1 — deriva de `SpendGuardHalt` (o sea, de `BaseException`) como todas las paradas de este
    módulo. Antes era una `Exception` corriente: el `except Exception` genérico de
    `harness.run_suite` la trataba como "un caso que falló", la corrida seguía con
    `corte=None` y `run_eval.exit_code_for` devolvía 0. Una corrida BLOQUEADA no puede
    reportarse como completa por ninguna puerta, ni por ésta ni por la siguiente que alguien
    abra: `guard_exception_audit()` vigila que no vuelva a pasar.
    """


class UngovernedJudge(SpendGuardHalt):
    """Se suministró un juez sustantivo, y el juez arbitrario NO se acepta (S5).

    Ver `harness.run_case`: la marca `governed_judge` era una BANDERA BURLABLE (un juez podía
    hacer N peticiones HTTP pagadas y luego una llamada gobernada solo para "aprobar" el
    chequeo de evidencia). Como no se puede demostrar desde aquí que un callable ajeno solo
    salga por las capas envueltas, el juez arbitrario se rechaza en vez de fingir que se
    gobierna. Deriva de `SpendGuardHalt` por lo mismo que `EvalGuardMissing`.
    """


class SpendRouteUnavailable(SpendGuardHalt):
    """Una ruta del registro `SPEND_ROUTES` no se pudo clasificar ni aplicar (R7).

    Es el invariante que hace HERMÉTICO el modo hermético: si al activar el guardián una ruta
    conocida no queda GOBERNADA, DESACTIVADA ni DECLARADA —porque el import falla, el
    atributo cambió de nombre o la sustitución no se sostuvo—, la corrida NO ARRANCA. Fail
    closed de arranque, no un aviso en el log que nadie lee.
    """


def guard_exception_audit() -> list[str]:
    """Excepciones definidas en ESTE módulo que NO derivan de `SpendGuardHalt` (S1).

    Devuelve sus nombres; vacío es lo correcto. Existe para que el gate lo compruebe: la
    lección de S1 es que el defecto "una corrida frenada se reporta como completa" no vive en
    una puerta concreta, sino en cualquier excepción del guardián que un `except Exception`
    pueda tragarse. En vez de tapar la puerta de hoy, se prohíbe la clase entera de defecto.
    """
    culpables = []
    for nombre, obj in list(globals().items()):
        if (isinstance(obj, type) and issubclass(obj, BaseException)
                and obj.__module__ == __name__ and not issubclass(obj, SpendGuardHalt)):
            culpables.append(nombre)
    return sorted(culpables)


# ── ¿La política de modelo ACTIVA es enteramente gratis? (R4) ────────────────
def alias_is_free(alias: str) -> bool:
    """Un alias de coste MARGINAL cero: la suscripción del abogado (`cli-*`) o el motor local."""
    from ..metrics import usage as usage_metrics

    a = str(alias or "")
    return a in usage_metrics.FREE_ALIASES or a.startswith("cli-") or a == "mia-local"


def paid_embeddings_configured() -> bool:
    """¿Puede FACTURAR un embedding en esta instalación? (S3)

    `embeddings.embed_texts` es el único generador de embeddings del producto y su primera
    línea es `if not config.VOYAGE_API_KEY: raise`. O sea: SIN clave no sale a la red y no
    factura ni un centavo (la corrida se degrada, pero no gasta); CON clave, cada llamada
    factura contra Voyage. Por eso la clave es la respuesta exacta, no una aproximación.
    """
    from .. import config

    return bool(str(getattr(config, "VOYAGE_API_KEY", "") or "").strip())


def free_policy_audit() -> dict:
    """¿Es esta corrida ENTERAMENTE GRATIS? Modelo Y embeddings (R4 + S3).

    Es la condición —la única— que habilita `harness.run_case(..., allow_unguarded=True)`. Ese
    escape se pidió para el caso legítimo en que el tope no aporta nada porque nada puede
    facturar; tal como estaba, permitía correr grafo, LLM y Voyage SIN NINGÚN techo con
    cualquier política — el propio código lo admitía ("Nada limitará lo que gaste").

    S3 — La versión anterior solo miraba la cadena de aliases del MODELO, y por eso la promesa
    "enteramente gratis" era FALSA: bajo política 'soberano' (LLM local, gratis) los
    EMBEDDINGS de Voyage seguían facturando sin tope — sembrar un caso genera embeddings
    pagados, y el propio log lo admitía en letra pequeña ("OJO — los EMBEDDINGS sí facturan").
    Un parámetro que promete gratis tiene que ser verdad o no debe existir; ahora la promesa
    cubre AMBAS fuentes de coste y con clave de embeddings configurada se rechaza.

    Mira TODAS las cadenas de la política activa (no solo la de `main`), porque un turno del
    grafo toca varias tareas y basta con que una caiga en un alias pagado para que el escape
    deje de ser gratis.
    """
    from ..agent import llm as llm_mod

    chains = llm_mod._active_chains()
    aliases = sorted({a for chain in chains.values() for a in chain})
    pagados = [a for a in aliases if not alias_is_free(a)]
    embeddings_pagados = paid_embeddings_configured()
    facturan = list(pagados)
    if embeddings_pagados:
        facturan.append(f"embeddings:{embed_alias()} (VOYAGE_API_KEY configurada)")
    return {
        "policy": llm_mod.get_model_policy(),
        "aliases": aliases,
        "aliases_que_facturan": pagados,
        "embeddings_facturan": embeddings_pagados,
        "lo_que_factura": facturan,
        "entirely_free": not facturan,
    }


# ── Fichero de saldo (sesión + global), atómico ───────────────────────────────
def default_ledger_path() -> Path:
    override = os.getenv(LEDGER_ENV, "").strip()
    if override:
        return Path(override)
    from .. import config
    return Path(config.MIA_HOME) / "eval-runs" / "spend_ledger.json"


def default_session_id(source: str = "cli") -> str:
    """Id de la sesión de gasto por defecto.

    Dos decisiones de producto viven en esta función:

    1) EL BANCO DEL ABOGADO NO ES EL BANCO DE LAS PRUEBAS (D6). La corrida in-app
       (`gold-cases:evaluate`, que corre DENTRO del proceso de la API con el tenant REAL del
       despacho) y la corrida de línea de comandos usan sesiones de gasto DISTINTAS por
       defecto (`inapp-…` vs `cli-…`). Así una tanda de pruebas desde la terminal no puede
       agotar el saldo que necesita el examen que el abogado lanza desde la aplicación, ni al
       revés. El gasto de PRUEBAS nunca debe poder bloquear un turno real de un abogado.

    2) LA SESIÓN CADUCA (D8). El id lleva la FECHA. Antes existía una única sesión 'default'
       sin ciclo de vida: si agotaba sus USD 30 quedaba bloqueada PARA SIEMPRE, también días
       después, salvo que alguien supiera pasar `--session-id`. El tope de USD 30 es "por
       sesión de pruebas de un día", no "para toda la eternidad".

    `MIA_EVAL_SESSION_ID` sigue mandando por encima de todo (para fijar una sesión propia).
    """
    override = os.getenv(SESSION_ENV, "").strip()
    if override:
        return override
    src = (source or "cli").strip() or "cli"
    return f"{src}-{date.today():%Y%m%d}"


def _pid_alive(pid: int) -> Optional[bool]:
    """¿Sigue vivo ese proceso? True/False, o None si NO se puede afirmar.

    None es la respuesta importante: el cerrojo solo se rompe cuando se puede DEMOSTRAR que
    su dueño murió. Ante la duda no se rompe (fail-closed).
    """
    if pid <= 0:
        return None
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            ERROR_INVALID_PARAMETER = 87
            STILL_ACTIVE = 259
            k32.OpenProcess.restype = wintypes.HANDLE
            handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not handle:
                return False if ctypes.get_last_error() == ERROR_INVALID_PARAMETER else None
            try:
                code = wintypes.DWORD()
                if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return None
                return code.value == STILL_ACTIVE
            finally:
                k32.CloseHandle(handle)
        except Exception:  # noqa: BLE001 — no poder comprobarlo NO autoriza a romper
            return None
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True          # existe, es de otro usuario
    except OSError:
        return None


def _lock_owner_pid(lock: Path) -> Optional[int]:
    try:
        data = json.loads(lock.read_text(encoding="utf-8"))
        pid = int(data.get("pid", 0))
        return pid if pid > 0 else None
    except Exception:  # noqa: BLE001 — cerrojo sin dueño legible = dueño desconocido
        return None


@contextmanager
def _ledger_lock(path: Path) -> Iterator[None]:
    """Cerrojo exclusivo entre procesos e hilos sobre el fichero de saldo.

    `O_CREAT|O_EXCL` es atómico en Windows y POSIX. El cerrojo GUARDA EL PID de su dueño.

    Ruptura de cerrojos huérfanos (D5): un cerrojo viejo solo se rompe si además se puede
    DEMOSTRAR que su dueño murió (`_pid_alive` → False). Romper por reloj era un agujero
    real: un proceso solo PAUSADO (depurador, suspensión del portátil, GC largo) perdía su
    cerrojo a los 60 s y dos procesos escribían snapshots distintos del saldo. Si el dueño
    sigue vivo —o no se puede afirmar que murió— se espera; agotado `_LOCK_TIMEOUT_S` es
    FAIL-CLOSED: no se gasta.
    """
    lock = path.with_suffix(path.suffix + ".lock")
    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SpendControlUnavailable(
            f"no se pudo preparar la carpeta del saldo del eval ({lock.parent}): {exc}") from exc
    deadline = time.monotonic() + _LOCK_TIMEOUT_S
    fd = None
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            try:
                os.write(fd, json.dumps({"pid": os.getpid(), "ts": time.time()}).encode("utf-8"))
            except OSError:  # pragma: no cover — el cerrojo vale aunque no se pueda anotar
                pass
            break
        # En Windows, abrir un cerrojo que otro hilo está BORRANDO justo en ese instante
        # (borrado pendiente) da PermissionError, no FileExistsError. Tratarlo como error
        # fatal hacía fallar una llamada legítima bajo concurrencia normal —medido: ~1 de
        # cada 4 corridas de 40 llamadas—, así que ambos son "ocupado, reintenta".
        except (FileExistsError, PermissionError) as exc:
            if lock.is_dir():
                # No es contención: ahí no se puede crear un cerrojo NUNCA. Fail-closed ya.
                raise SpendControlUnavailable(
                    f"no se puede crear el cerrojo del saldo del eval ({lock} es un "
                    f"directorio); no se gasta") from exc
            try:
                age = time.time() - lock.stat().st_mtime
                if age > _LOCK_STALE_S:
                    owner = _lock_owner_pid(lock)
                    if owner is not None and _pid_alive(owner) is False:
                        logger.warning(
                            "cerrojo del saldo del eval huérfano (pid %s muerto): se rompe", owner)
                        lock.unlink()
                        continue
                    # Vivo, o imposible de comprobar: NO se rompe. Se espera al timeout.
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise SpendControlUnavailable(
                    "no se pudo tomar el cerrojo del saldo del eval; no se gasta") from exc
            time.sleep(0.01)
        except OSError as exc:
            raise SpendControlUnavailable(
                f"no se pudo tomar el cerrojo del saldo del eval: {exc}") from exc
    try:
        yield
    finally:
        try:
            os.close(fd)
            lock.unlink()
        except OSError:  # pragma: no cover — el cerrojo huérfano vence solo
            logger.warning("no se pudo soltar el cerrojo del saldo del eval (%s)", lock)


def _empty_ledger() -> dict:
    return {"version": 1, "sessions": {}, "global": {"spent_usd": 0.0, "calls": 0}}


def _sane_amount(value: Any, what: str, path: Path) -> float:
    """Un saldo tiene que ser un número finito y NO NEGATIVO. Si no, fail-closed (D7).

    Un `spent_usd` negativo (fichero editado, corrupción, un `settle` mal aplicado por una
    versión antigua) SUBE el techo efectivo: con saldo −999999 el guardián autorizaba una
    reserva de USD 500 sin pestañear. Un saldo incoherente no es "cero", es un control de
    gasto que no se puede verificar — y eso ya tiene respuesta en este módulo: no se gasta.
    """
    try:
        amount = float(value)
    except (TypeError, ValueError) as exc:
        raise SpendControlUnavailable(
            f"{what} del eval no es numérico ({path}). No se gasta.") from exc
    if not math.isfinite(amount):
        raise SpendControlUnavailable(
            f"{what} del eval no es un número finito ({path}). No se gasta.")
    if amount < 0:
        raise SpendControlUnavailable(
            f"{what} del eval es NEGATIVO (USD {amount:.6f}, {path}): un saldo negativo sube "
            "el techo efectivo del tope. No se gasta hasta que se corrija.")
    return amount


def _read_ledger(path: Path) -> dict:
    """Lee el saldo. Ausente = cero (primera corrida). ILEGIBLE o INCOHERENTE = fail-closed."""
    if not path.exists():
        return _empty_ledger()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SpendControlUnavailable(
            f"el saldo acumulado del eval no se puede leer ({path}): {exc}. No se gasta."
        ) from exc
    if not isinstance(data, dict) or not isinstance(data.get("sessions"), dict):
        raise SpendControlUnavailable(
            f"el saldo acumulado del eval tiene un formato inesperado ({path}). No se gasta.")
    g = data.get("global")
    if not isinstance(g, dict):
        raise SpendControlUnavailable(
            f"el saldo global del eval tiene un formato inesperado ({path}). No se gasta.")
    g["spent_usd"] = _sane_amount(g.get("spent_usd", 0.0), "el saldo global", path)
    return data


def _write_ledger(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        raise SpendControlUnavailable(
            f"no se pudo anotar el gasto del eval ({path}): {exc}. No se gasta.") from exc


def _session_row(data: dict, session_id: str, path: Path) -> dict:
    row = data["sessions"].get(session_id)
    if not isinstance(row, dict):
        row = {"spent_usd": 0.0, "calls": 0}
        data["sessions"][session_id] = row
    row["spent_usd"] = _sane_amount(
        row.get("spent_usd", 0.0), f"el saldo de la sesión '{session_id}'", path)
    return row


def read_spend(path: Optional[Path] = None, session_id: Optional[str] = None) -> dict:
    """Saldo acumulado (sesión y global) sin reservar nada. Fail-closed al leer."""
    path = Path(path) if path else default_ledger_path()
    session_id = session_id or default_session_id()
    with _ledger_lock(path):
        data = _read_ledger(path)
        row = _session_row(data, session_id, path)
        return {
            "session_id": session_id,
            "session_usd": round(float(row["spent_usd"]), 6),
            "global_usd": round(float(data["global"].get("spent_usd", 0.0)), 6),
        }


# ── Contadores por caso ───────────────────────────────────────────────────────
@dataclass
class CaseUsage:
    """Telemetría de UN caso del banco: qué costó y cuánto tardó en el modelo."""
    case_id: str = ""
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    llm_seconds: float = 0.0
    models: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "llm_seconds": round(self.llm_seconds, 3),
            "models": dict(self.models),
        }


@dataclass
class Reservation:
    """Saldo apartado para UN INTENTO cobrable, a la espera de liquidarse al coste real."""
    estimate: float
    alias: str = ""


# ── El guardián ───────────────────────────────────────────────────────────────
class EvalSpendGuard:
    """Tope de gasto del banco: reserva antes de cada intento, liquida después, corta en seco.

    Uso normal (lo hace `eval.harness`):

        guard = EvalSpendGuard(run_limit_usd=2.0, source="cli")
        with install(), guard.activate():
            with guard.case("mi_caso"):
                ...   # cualquier intento del modelo o embedding de este contexto va gobernado
    """

    def __init__(self, *, run_limit_usd: float = DEFAULT_RUN_LIMIT_USD,
                 session_limit_usd: float = SESSION_LIMIT_USD,
                 global_limit_usd: float = GLOBAL_LIMIT_USD,
                 closeout_reserve_usd: float = CLOSEOUT_RESERVE_USD,
                 session_id: Optional[str] = None,
                 source: str = "inapp",
                 ledger_path: Optional[Path | str] = None) -> None:
        self.run_limit_usd = float(run_limit_usd)
        self.session_limit_usd = float(session_limit_usd)
        self.global_limit_usd = float(global_limit_usd)
        self.closeout_reserve_usd = max(0.0, float(closeout_reserve_usd))
        # `source` decide la SESIÓN de gasto por defecto: la corrida in-app del despacho y la
        # de la terminal no comparten bolsillo (ver `default_session_id`). El default es
        # 'inapp' porque el llamador que NO dice nada es el harness dentro del proceso de la
        # API; `run_eval.py` pasa 'cli' explícitamente.
        self.source = (source or "inapp").strip() or "inapp"
        self.session_id = session_id or default_session_id(self.source)
        self.ledger_path = Path(ledger_path) if ledger_path else default_ledger_path()

        # RLock: `_stop` se llama DESDE dentro de la sección crítica de `check_and_reserve`
        # (la comprobación, la reserva y la suma al contador son UNA sola sección — D5).
        self._lock = threading.RLock()
        self.run_spent_usd = 0.0
        self.calls = 0
        self.total_tokens = 0
        self.llm_seconds = 0.0
        self.stop_reason: Optional[str] = None
        self.cases: list[CaseUsage] = []
        # Gasto que este guardián NO puede gobernar (callbacks externos que no pasan por las
        # capas envueltas). Se REPORTA, no se esconde (D1c).
        self.untracked: list[dict] = []
        self._case_var: ContextVar[Optional[CaseUsage]] = ContextVar(
            f"mia_eval_case_{id(self)}", default=None)

    # -- activación / caso ----------------------------------------------------
    @contextmanager
    def activate(self) -> Iterator["EvalSpendGuard"]:
        ensure_installed()   # activar un guardián SIEMPRE implica que las capas están envueltas
        self._declare_known_routes()
        token = _active_guard.set(self)
        try:
            yield self
        finally:
            _active_guard.reset(token)

    @contextmanager
    def case(self, case_id: str) -> Iterator[CaseUsage]:
        usage = CaseUsage(case_id=case_id)
        with self._lock:
            self.cases.append(usage)
        token = self._case_var.set(usage)
        try:
            yield usage
        finally:
            self._case_var.reset(token)

    def current_case(self) -> Optional[CaseUsage]:
        return self._case_var.get()

    # -- topes ----------------------------------------------------------------
    def _effective(self, limit: float) -> float:
        """Tope EFECTIVO: el nominal menos el margen intocable de cierre."""
        return max(0.0, limit - self.closeout_reserve_usd)

    def _stop(self, reason: str) -> None:
        with self._lock:
            if self.stop_reason is None:
                self.stop_reason = reason
        raise SpendLimitExceeded(reason)

    def note_untracked(self, what: str, detail: str) -> None:
        """Anota que hubo (o pudo haber) gasto FUERA del tope. Ruidoso a propósito.

        Es el canal por el que las rutas DESACTIVADAS y DECLARADAS del registro llegan al
        reporte: queda en el log, en `snapshot()["gasto_no_gobernado"]` y en el fichero que se
        persiste. Un hueco declarado es auditable; uno silencioso, no.
        """
        entry = {"que": what, "detalle": detail}
        with self._lock:
            if entry in self.untracked:
                return  # ya declarado: una ruta que se toca 40 veces se declara UNA
            self.untracked.append(entry)
        logger.warning("GASTO NO GOBERNADO por el tope del eval — %s: %s", what, detail)

    def _declare_known_routes(self) -> None:
        """Vuelca el REGISTRO de rutas al reporte de la corrida (R7).

        Se declaran al ACTIVAR, se hayan tocado o no: un hueco que solo aparece en el reporte
        cuando se usó es un hueco que el lector del reporte no sabe que existe. Las GOBERNADAS
        no ensucian el aviso de "gasto fuera del tope" —están dentro—, pero sí viajan en
        `snapshot()["rutas_de_gasto"]`, que es el inventario completo y auditable.
        """
        for route in SPEND_ROUTES:
            if route.estado != GOBERNADA:
                self.note_untracked(route.name, f"[{route.estado}] {route.por_que}")

    def check_and_reserve(self, estimate: float, *, alias: str) -> Optional[Reservation]:
        """Aparta saldo antes de UN INTENTO pagado. None si el intento es gratis.

        Corta ANTES de gastar: si la proyección (gastado + estimado) supera cualquiera de los
        tres topes efectivos, levanta `SpendLimitExceeded` y el intento no se hace.

        ATÓMICO (D5): leer `run_spent_usd`, comprobar los tres topes, reservar en el fichero y
        SUMAR al contador de la corrida ocurren dentro de UNA sola sección crítica. Antes se
        leía bajo cerrojo, se SOLTABA, se reservaba y solo después se sumaba: dos llamadas
        concurrentes de la misma corrida podían leer ambas saldo suficiente y pasarse de
        `--max-usd`.
        """
        with self._lock:
            if self.stop_reason is not None:
                # STICKY: un guardián que ya cortó no vuelve a autorizar (invariante F).
                raise SpendLimitExceeded(self.stop_reason)
            estimate = float(estimate or 0.0)
            if estimate <= 0:
                return None  # gratis: el tope no estorba (pero los tokens SÍ se cuentan)

            projected_run = self.run_spent_usd + estimate
            if projected_run > self._effective(self.run_limit_usd):
                self._stop(
                    f"tope de la CORRIDA alcanzado: el intento siguiente (~USD {estimate:.4f} en "
                    f"{alias}) llevaría el gasto a USD {projected_run:.4f}, por encima del tope "
                    f"útil de USD {self._effective(self.run_limit_usd):.4f} "
                    f"(tope USD {self.run_limit_usd:.2f} menos USD "
                    f"{self.closeout_reserve_usd:.2f} de margen de cierre). No se hizo la "
                    "llamada.")

            # Sesión y global viven en el fichero de saldo: se comprueban y reservan bajo
            # cerrojo entre procesos, DENTRO de la misma sección crítica de este guardián.
            with _ledger_lock(self.ledger_path):
                data = _read_ledger(self.ledger_path)
                row = _session_row(data, self.session_id, self.ledger_path)
                session_spent = float(row["spent_usd"])
                global_spent = float(data["global"].get("spent_usd", 0.0))

                if session_spent + estimate > self._effective(self.session_limit_usd):
                    self._stop(
                        f"tope de la SESIÓN '{self.session_id}' alcanzado: el intento siguiente "
                        f"(~USD {estimate:.4f}) llevaría la sesión a USD "
                        f"{session_spent + estimate:.4f}, por encima del tope útil de USD "
                        f"{self._effective(self.session_limit_usd):.4f} (tope USD "
                        f"{self.session_limit_usd:.2f} menos margen de cierre). "
                        "No se hizo la llamada.")
                if global_spent + estimate > self._effective(self.global_limit_usd):
                    self._stop(
                        f"TECHO GLOBAL alcanzado: el intento siguiente (~USD {estimate:.4f}) "
                        f"llevaría el gasto total del banco a USD "
                        f"{global_spent + estimate:.4f}, por encima del techo útil de USD "
                        f"{self._effective(self.global_limit_usd):.4f}. No se hizo la llamada.")

                row["spent_usd"] = session_spent + estimate
                row["calls"] = int(row.get("calls", 0) or 0) + 1
                data["global"]["spent_usd"] = global_spent + estimate
                data["global"]["calls"] = int(data["global"].get("calls", 0) or 0) + 1
                _write_ledger(self.ledger_path, data)

            # DENTRO del mismo lock que la lectura y la reserva (invariante E).
            self.run_spent_usd = projected_run
            return Reservation(estimate=estimate, alias=alias)

    def settle(self, reservation: Optional[Reservation], actual_usd: Optional[float]) -> None:
        """Ajusta la reserva al coste REAL. `actual_usd=None` = final incierto: se COBRA lo
        estimado (invariante D — un corte dudoso nunca abre un hueco de sobregasto)."""
        if reservation is None:
            return
        if actual_usd is None:
            return  # la reserva se queda cobrada tal cual
        delta = float(actual_usd) - reservation.estimate
        if abs(delta) < 1e-9:
            return
        with self._lock:
            try:
                with _ledger_lock(self.ledger_path):
                    data = _read_ledger(self.ledger_path)
                    row = _session_row(data, self.session_id, self.ledger_path)
                    row["spent_usd"] = max(0.0, float(row["spent_usd"]) + delta)
                    data["global"]["spent_usd"] = max(
                        0.0, float(data["global"].get("spent_usd", 0.0)) + delta)
                    _write_ledger(self.ledger_path, data)
            except SpendControlUnavailable:
                # No poder AJUSTAR a la baja no es motivo para romper una respuesta ya obtenida:
                # el saldo queda con la reserva (conservador). Si el delta era al alza, el
                # próximo check_and_reserve volverá a fallar en la lectura y cortará:
                # fail-closed.
                logger.warning(
                    "no se pudo liquidar la reserva del eval; queda cobrada la estimación")
                return
            self.run_spent_usd = max(0.0, self.run_spent_usd + delta)

    # -- telemetría -----------------------------------------------------------
    def note_call(self, *, alias: str, prompt_tokens: int, completion_tokens: int,
                  total_tokens: int, cost_usd: float, seconds: float) -> None:
        with self._lock:
            self.calls += 1
            self.total_tokens += int(total_tokens or 0)
            self.llm_seconds += float(seconds or 0.0)
        usage = self.current_case()
        if usage is not None:
            usage.calls += 1
            usage.prompt_tokens += int(prompt_tokens or 0)
            usage.completion_tokens += int(completion_tokens or 0)
            usage.total_tokens += int(total_tokens or 0)
            usage.cost_usd += float(cost_usd or 0.0)
            usage.llm_seconds += float(seconds or 0.0)
            usage.models[alias] = int(usage.models.get(alias, 0)) + 1

    def snapshot(self) -> dict:
        """Estado del tope, apto para el reporte y para imprimir en llano."""
        with self._lock:
            snap = {
                "session_id": self.session_id,
                "source": self.source,
                "run_spent_usd": round(self.run_spent_usd, 6),
                "run_limit_usd": round(self.run_limit_usd, 4),
                "session_limit_usd": round(self.session_limit_usd, 4),
                "global_limit_usd": round(self.global_limit_usd, 4),
                "closeout_reserve_usd": round(self.closeout_reserve_usd, 4),
                "calls": self.calls,
                "total_tokens": self.total_tokens,
                "llm_seconds": round(self.llm_seconds, 3),
                "stopped": self.stop_reason is not None,
                "stop_reason": self.stop_reason,
                "gasto_no_gobernado": list(self.untracked),
                # Inventario COMPLETO del modo hermético (R7): cada ruta capaz de gastar, con
                # su estado. Lo que no está aquí no existe para el banco — y si aparece algo
                # nuevo sin clasificar, `ensure_installed` no deja arrancar la corrida.
                "rutas_de_gasto": [
                    {"ruta": r.name, "estado": r.estado, "por_que": r.por_que}
                    for r in SPEND_ROUTES],
            }
            try:
                acc = read_spend(self.ledger_path, self.session_id)
                snap["session_spent_usd"] = acc["session_usd"]
                snap["global_spent_usd"] = acc["global_usd"]
            except SpendControlUnavailable as exc:
                # Honestidad: si el saldo no se puede leer, se dice — no se inventa un número.
                snap["session_spent_usd"] = None
                snap["global_spent_usd"] = None
                snap["ledger_error"] = str(exc)
        return snap


# ── Envolturas (instalación PERMANENTE) ───────────────────────────────────────
_active_guard: ContextVar[Optional[EvalSpendGuard]] = ContextVar(
    "mia_eval_spend_guard", default=None)

_install_lock = threading.Lock()
_embed_patch_lock = threading.Lock()
_installed = False
_original_invoke: Any = None
_original_embed_texts: Any = None
_original_pinecone_notes: Any = None
_original_consult_notebook: Any = None
_original_mcp_consult: Any = None
_original_hub_invoke_result: Any = None

# Estados posibles de una ruta de gasto. NO HAY UN CUARTO (R7).
GOBERNADA = "GOBERNADA"      # pasa por el guardián: reserva antes, liquida después
DESACTIVADA = "DESACTIVADA"  # devuelve un vacío de un camino ya soportado y fail-soft
DECLARADA = "DECLARADA"      # hueco conocido que no se puede gobernar desde aquí


def active_guard() -> Optional[EvalSpendGuard]:
    return _active_guard.get()


def _alias_and_cost(resp: Any, chain_alias: str) -> tuple[str, int, int, int, float]:
    """Alias servido y coste REAL de una respuesta. Sin `usage` legible → tokens 0.

    A1 — el coste sale de `real_call_cost`, que desglosa la caché de prompt (escritura al
    doble, lectura a la décima parte), no de `metrics.usage.cost_usd`, que tarifa todo el
    prompt a la entrada normal y por eso no veía ni un centavo de las escrituras de caché.
    """
    from ..metrics import usage as usage_metrics

    alias = chain_alias
    served = getattr(resp, "model", None)
    if isinstance(served, str) and served in usage_metrics.PRICES_PER_MTOK:
        alias = served
    u = getattr(resp, "usage", None)

    def _int(v: Any) -> int:
        try:
            return int(v or 0)
        except (TypeError, ValueError):
            return 0

    prompt = _int(getattr(u, "prompt_tokens", 0))
    completion = _int(getattr(u, "completion_tokens", 0))
    # Se reutiliza el extractor de PRODUCCIÓN (`metrics.usage._cache_tokens`) a propósito: ya
    # cubre las DOS formas en que LiteLLM expone la caché (passthrough de Anthropic y estilo
    # OpenAI en `prompt_tokens_details.cached_tokens`). Duplicarlo aquí crearía dos verdades.
    cache_read, cache_creation = usage_metrics._cache_tokens(u)
    # La ESCRITURA de caché no está en `total_tokens` (LiteLLM no la suma): se añade para que
    # la telemetría del banco no reporte menos tokens de los que de verdad se facturaron.
    total = (_int(getattr(u, "total_tokens", 0)) or (prompt + completion)) + cache_creation
    return alias, prompt, completion, total, real_call_cost(
        alias, prompt, completion, cache_read, cache_creation)


def upper_bound_call_cost(alias: str, messages: Any, *, max_tokens: Optional[int] = None,
                          tools: Any = None) -> float:
    """COTA SUPERIOR del coste de UN intento cobrable. No es una estimación (R1).

    `metrics.usage.estimated_call_cost` es una estimación de producción y puede quedarse corta
    (se midió una subestimación de USD 0.8985 en un solo intento). Aquí no se estima: se acota.
      · entrada — UN TOKEN POR CARÁCTER del payload serializado. Ningún tokenizador de sub-
        palabras emite más de un token por carácter, así que `tokens_reales ≤ caracteres`; se
        suma `_PROMPT_OVERHEAD_TOKENS` por el andamiaje del protocolo.
      · salida  — el techo `max_tokens` con el que se va a hacer la llamada (`_guarded_invoke`
        lo impone), nunca más de `EVAL_MAX_OUTPUT_TOKENS`.
      · tarifa  — `_WORST_RATES`, la más cara del catálogo: la liquidación usa el alias SERVIDO
        (`resp.model`), que puede no ser el pedido.
    Aliases gratis siguen costando 0: el tope no los estorba.
    """
    from ..metrics import usage as usage_metrics

    if alias in usage_metrics.FREE_ALIASES or str(alias).startswith("cli-"):
        return 0.0
    try:
        payload = json.dumps({"messages": messages, "tools": tools or []},
                             ensure_ascii=False, default=str)
        prompt_tokens = len(payload) + _PROMPT_OVERHEAD_TOKENS
    except Exception:  # noqa: BLE001 — si no se puede medir, se acota por arriba, no por abajo
        prompt_tokens = 1_000_000
    completion_tokens = min(int(max_tokens or EVAL_MAX_OUTPUT_TOKENS), EVAL_MAX_OUTPUT_TOKENS)
    in_rate, out_rate = _WORST_RATES
    # A1 — LA ENTRADA SE RESERVA AL PRECIO DE ESCRITURA DE CACHÉ. El prefijo estable del prompt
    # sale marcado para el prefix caching de 1 h, y esa ESCRITURA se factura al DOBLE de la
    # entrada normal. Como cada token del prompt acaba en exactamente uno de los tres cubos
    # —entrada normal (1.00x), lectura de caché (0.10x) o escritura de caché (2.00x)— el peor
    # caso posible es "todo el prompt es escritura", o sea `prompt_tokens * in_rate * 2.00`.
    # Sigue siendo una COTA SUPERIOR y no una sobre-reserva ciega: la lectura ABARATA, así que
    # una corrida con caché caliente liquida MUY por debajo de esta reserva y se devuelve el
    # sobrante en `settle()`; lo que no puede volver a pasar es que el coste real supere lo
    # reservado, que es lo único que rompe el tope.
    return round((prompt_tokens * in_rate * CACHE_WRITE_MULTIPLIER
                  + completion_tokens * out_rate) / 1_000_000.0, 6)


def real_call_cost(alias: str, prompt_tokens: int, completion_tokens: int,
                   cache_read_tokens: int = 0, cache_creation_tokens: int = 0) -> float:
    """Coste REAL de un intento, con la caché de prompt DESGLOSADA (A1).

    `metrics.usage.cost_usd` tarifa todo el prompt a la entrada normal, lo que es correcto para
    el panel del abogado pero falso para el banco: no ve `cache_creation_input_tokens` (que
    cuesta el DOBLE) y cobra `cache_read_input_tokens` a precio completo (cuesta la DÉCIMA
    parte). Se liquida aquí, en el guardián, y no allí, para no cambiar ni una semántica del
    código de producción — ver el bloque de constantes de arriba para el porqué de cada factor.

    Ojo a la ARITMÉTICA de los campos (medida en LiteLLM, no supuesta): la lectura ya está
    DENTRO de `prompt_tokens`, así que hay que restarla para no cobrarla dos veces; la
    escritura está FUERA, así que hay que sumarla o no se cobra nunca.
    """
    from ..metrics import usage as usage_metrics

    in_rate, out_rate = usage_metrics.PRICES_PER_MTOK.get(
        alias, usage_metrics.UNKNOWN_ALIAS_RATES)
    read = max(0, int(cache_read_tokens or 0))
    creation = max(0, int(cache_creation_tokens or 0))
    # Entrada NO cacheada = lo que queda de `prompt_tokens` al sacarle la lectura.
    normal_in = max(0, int(prompt_tokens or 0) - (read if _CACHE_READ_INSIDE_PROMPT_TOKENS else 0))
    usd = (normal_in * in_rate
           + read * in_rate * CACHE_READ_MULTIPLIER
           + creation * in_rate * CACHE_WRITE_MULTIPLIER
           + int(completion_tokens or 0) * out_rate) / 1_000_000.0
    return round(usd, 8)


def _reserva_no_gastada(exc: BaseException) -> bool:
    """¿Se puede DEMOSTRAR que este fallo no llegó a facturar nada? (A2)

    Delega en `agent.error_classifier.provider_never_reached` —el clasificador que ya existe—
    en vez de inventar aquí una segunda taxonomía de errores de red. Si el clasificador no se
    puede importar o revienta, la respuesta es NO: se cobra la reserva. Un fallo del control de
    gasto nunca puede terminar en "devuélvele el dinero" (mismo criterio fail-closed que el
    resto del módulo).
    """
    try:
        from ..agent.error_classifier import provider_never_reached

        return bool(provider_never_reached(exc))
    except Exception:  # noqa: BLE001 — no poder demostrarlo NO autoriza a devolver
        logger.warning("no se pudo clasificar el fallo del proveedor: se cobra la reserva",
                       exc_info=True)
        return False


def _capped_kwargs(kwargs: dict) -> dict:
    """`kwargs` con la salida ACOTADA a `EVAL_MAX_OUTPUT_TOKENS` (R1).

    El grafo nunca pasa `max_tokens` (cero ocurrencias), así que sin esto el techo de salida de
    un intento del banco era el del modelo (64 000 tokens) y la reserva no podía ser fiel.
    Devuelve un diccionario NUEVO: `call_llm` reutiliza el suyo entre reintentos del alias.
    """
    current = kwargs.get("max_tokens")
    try:
        current = int(current) if current is not None else None
    except (TypeError, ValueError):
        current = None
    if current is not None and current <= EVAL_MAX_OUTPUT_TOKENS:
        return kwargs
    return {**kwargs, "max_tokens": EVAL_MAX_OUTPUT_TOKENS}


def _guarded_invoke(client: Any, alias: str, kwargs: dict, task: Any = None,
                    quality_escalation: Any = None) -> Any:
    """UN intento cobrable de `agent.llm`, gobernado por el guardián ACTIVO (si lo hay).

    Este es el punto donde se gasta el dinero de verdad: `_call_with_retries` lo llama una vez
    por INTENTO (reintentos dentro del alias) y `call_llm` recorre la cadena de aliases. Una
    reserva por intento, con el alias EXACTO que se va a facturar, es lo que le pone cota al
    exceso (invariante G) y lo que hace que un salto de `cli-claude` (gratis) a
    `claude-sonnet` (pagado) quede reservado y contado.
    """
    guard = _active_guard.get()
    if guard is None:
        # Sin guardián en el contexto: producción intacta. El parche es global, el efecto no.
        if quality_escalation is None:
            return _original_invoke(client, alias, kwargs, task)
        return _original_invoke(client, alias, kwargs, task, quality_escalation)

    # R1 — la llamada se ACOTA y se reserva con la cota superior de lo que puede costar ya
    # acotada. Estimar (lo de antes) dejaba hasta 64 000 tokens de salida sin reservar.
    kwargs = _capped_kwargs(kwargs)
    estimate = upper_bound_call_cost(alias, kwargs.get("messages") or [],
                                     max_tokens=kwargs.get("max_tokens"),
                                     tools=kwargs.get("tools"))

    # Corta ANTES: si esto levanta, el intento NO se hace.
    reservation = guard.check_and_reserve(estimate, alias=alias)

    started = time.perf_counter()
    try:
        if quality_escalation is None:
            resp = _original_invoke(client, alias, kwargs, task)
        else:
            resp = _original_invoke(client, alias, kwargs, task, quality_escalation)
    except BaseException as exc:
        # A2 — INCIERTO se cobra (invariante D), pero NO-ENVIADO se devuelve.
        # Una corrida cuyas 10 llamadas murieron ANTES de conectar cobró USD 0.5785 sin gastar
        # un centavo real: más que la corrida que sí funcionó. Es fail-safe, pero quema el
        # presupuesto de la sesión por nada, y con `--repeat 10` eso se multiplica por diez.
        # `provider_never_reached` sólo dice True cuando se puede DEMOSTRAR que el proveedor no
        # recibió la petición; el final dudoso (timeout de lectura, conexión reseteada a mitad)
        # sigue cobrándose exactamente igual que antes, que es la parte que protege.
        no_gastado = reservation is not None and _reserva_no_gastada(exc)
        guard.settle(reservation, 0.0 if no_gastado else None)
        guard.note_call(alias=alias, prompt_tokens=0, completion_tokens=0, total_tokens=0,
                        cost_usd=0.0 if no_gastado
                        else (reservation.estimate if reservation else 0.0),
                        seconds=time.perf_counter() - started)
        raise
    seconds = time.perf_counter() - started
    served_alias, prompt, completion, total, actual = _alias_and_cost(resp, alias)
    if reservation is not None and total == 0:
        # Sin tokens legibles no se puede afirmar un coste menor: se cobra lo estimado.
        actual = reservation.estimate
    guard.settle(reservation, actual)
    guard.note_call(alias=served_alias, prompt_tokens=prompt, completion_tokens=completion,
                    total_tokens=total, cost_usd=actual, seconds=seconds)
    return resp


def embed_alias() -> str:
    """Alias tarifable del modelo de embeddings activo (`voyage-law-2` por defecto)."""
    from .. import config
    model = str(config.litellm_embed_model() or "")
    return model.split("/")[-1] or "voyage-law-2"


def estimated_embed_cost(texts: list[str], alias: Optional[str] = None) -> float:
    """Coste estimado de embeber estos textos, con la tarifa de `EMBED_PRICES_PER_MTOK`."""
    alias = alias or embed_alias()
    rate = EMBED_PRICES_PER_MTOK.get(alias, UNKNOWN_EMBED_RATE)
    chars = sum(len(str(t or "")) for t in (texts or []))
    tokens = max(1, (chars + _EMBED_CHARS_PER_TOKEN - 1) // _EMBED_CHARS_PER_TOKEN)
    return round(tokens * rate / 1_000_000.0, 8)


def _embed_tokens(texts: Any) -> int:
    chars = sum(len(str(t or "")) for t in (texts or []))
    return max(1, (chars + _EMBED_CHARS_PER_TOKEN - 1) // _EMBED_CHARS_PER_TOKEN)


def _guarded_embed_texts(texts: list[str]) -> Any:
    """`embeddings.embed_texts` bajo el tope, cubriendo TODOS sus intentos (D1b + R2).

    Voyage es red PAGADA y nunca pasó por `call_llm`: el banco embebía los chunks de cada caso
    al sembrarlo y el grafo volvía a embeber cada consulta, todo por fuera del techo.

    R2 — UNA reserva no bastaba: `embeddings.embed_texts` llama a `litellm.embedding` con
    `num_retries=2`, o sea hasta TRES intentos FACTURABLES bajo una única reserva (el mismo
    defecto que se cerró para el LLM enganchando en `_invoke`). Aquí se cierra con la variante
    que el llamador no tiene que conocer:

      1. se RESERVA EL PEOR CASO por adelantado (`EMBED_MAX_ATTEMPTS` × estimación), de modo
         que el corte sigue ocurriendo ANTES de gastar (invariante A) aunque haya reintentos;
      2. mientras dura la llamada se sustituye `litellm.embedding` por una envoltura que fuerza
         `num_retries=0` —los reintentos los hace ella, contándolos— y así se sabe cuántos
         intentos FACTURABLES hubo de verdad;
      3. al terminar se DEVUELVE lo no usado (`settle` al coste de los intentos reales).

    La política de reintentos de `embeddings.py` no cambia (sigue habiendo hasta 3); cambia
    quién los cuenta y que ninguno queda sin reservar.

    Si la llamada NO pasó por `litellm.embedding` (LiteLLM ausente, o `embed_texts` cambiado al
    SDK `voyageai` que su propio docstring contempla como respaldo), no se puede afirmar cuántos
    intentos hubo: se COBRA el peor caso —nunca se devuelve un dinero que no se puede probar
    que no se gastó— y el hecho se DECLARA en `gasto_no_gobernado`.
    """
    guard = _active_guard.get()
    if guard is None:
        return _original_embed_texts(texts)
    alias = embed_alias()
    estimate = estimated_embed_cost(texts, alias)

    # (1) Corta ANTES, reservando el PEOR caso: hasta `EMBED_MAX_ATTEMPTS` intentos cobrables.
    reservation = guard.check_and_reserve(estimate * EMBED_MAX_ATTEMPTS, alias=alias)
    intentos = {"n": 0}
    started = time.perf_counter()

    try:
        import litellm  # import diferido, igual que en `embeddings.embed_texts`
    except Exception:  # noqa: BLE001
        litellm = None  # type: ignore[assignment]

    def guarded_embedding(*args: Any, **kwargs: Any) -> Any:
        # (2) Los reintentos internos de LiteLLM se apagan: los hace esta envoltura, que sí
        # sabe contarlos. Sin esto, tres llamadas facturadas se veían como una.
        kwargs["num_retries"] = 0
        ultimo: Optional[BaseException] = None
        for intento in range(EMBED_MAX_ATTEMPTS):
            intentos["n"] += 1
            try:
                return _original_litellm_embedding(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 — transitorio: se reintenta, ya reservado
                ultimo = exc
                logger.warning("embeddings: intento %d/%d falló (%s)",
                               intento + 1, EMBED_MAX_ATTEMPTS, exc)
        raise ultimo  # type: ignore[misc]

    # El parche de `litellm.embedding` es global al proceso: se serializa para que dos hilos
    # que embeban a la vez no se pisen la referencia original.
    with _embed_patch_lock:
        _original_litellm_embedding = getattr(litellm, "embedding", None) if litellm else None
        if _original_litellm_embedding is not None:
            litellm.embedding = guarded_embedding
        try:
            vectors = _original_embed_texts(texts)
        except BaseException:
            # Final incierto: la reserva del PEOR caso se queda cobrada (invariante D).
            #
            # A-MEN (asimetría CONSCIENTE, declarada 2026-07-21) — a diferencia del LLM
            # (`_guarded_invoke`, que usa `provider_never_reached` para DEVOLVER la reserva cuando
            # se demuestra que el proveedor no llegó a recibir la petición), aquí toda falla —de
            # red o no— se COBRA por el peor caso reservado. Es deliberado y va en la dirección
            # SEGURA (nunca se devuelve de más, jamás abre un hueco de sobregasto): no se aplica
            # la distinción no-conecto/incierto por dos razones. (1) `embed_texts` envuelve una
            # cadena propia (LiteLLM con su reintento interno, o el respaldo por SDK `voyageai`),
            # así que la excepción que sale aquí no es la de UN intento físico aislado —que es la
            # precondición para que `provider_never_reached` sea fiable— sino la del último de
            # hasta `EMBED_MAX_ATTEMPTS`; y (2) el ahorro sería marginal (la tarifa de embeddings
            # es ~25x más barata por token que el LLM). Si algún día se quisiera cerrar también
            # aquí, habría que forzar `num_retries=0` en la envoltura interna (ya se hace) y
            # clasificar el fallo de CADA intento por separado, como en el LLM.
            guard.settle(reservation, None)
            guard.note_call(alias=alias, prompt_tokens=0, completion_tokens=0, total_tokens=0,
                            cost_usd=reservation.estimate if reservation else 0.0,
                            seconds=time.perf_counter() - started)
            raise
        finally:
            if _original_litellm_embedding is not None:
                litellm.embedding = _original_litellm_embedding

    # (3) Se devuelve lo NO usado: solo se cobran los intentos que de verdad ocurrieron.
    if intentos["n"] > 0:
        cobrado = round(estimate * intentos["n"], 8)
    else:
        cobrado = round(estimate * EMBED_MAX_ATTEMPTS, 8)
        guard.note_untracked(
            "embeddings.embed_texts",
            "la llamada NO pasó por litellm.embedding (LiteLLM ausente o respaldo por SDK), "
            "así que no se pudo contar cuántos intentos se facturaron: se cobra el PEOR CASO "
            f"({EMBED_MAX_ATTEMPTS} intentos) y no se devuelve nada.")
    guard.settle(reservation, cobrado if reservation else None)
    tokens = _embed_tokens(texts) * max(1, intentos["n"])
    guard.note_call(alias=alias, prompt_tokens=tokens, completion_tokens=0, total_tokens=tokens,
                    cost_usd=cobrado if reservation else 0.0,
                    seconds=time.perf_counter() - started)
    return vectors


async def _guarded_pinecone_notes(tenant_id: str, query_vec: Any, **kwargs: Any) -> list:
    """Pinecone secundario: DESACTIVADO mientras hay guardián activo (R6).

    Es una ruta de red que factura por lectura y no pasa por ninguna capa envuelta. Como el
    store es opt-in y `retrieve_knowledge_rrf` la trata como fail-soft (devolver [] es un
    camino normal, ver su docstring), apagarla durante el banco no rompe el turno: solo lo deja
    con el corpus de pgvector. El hecho queda DECLARADO en el reporte.
    """
    guard = _active_guard.get()
    if guard is None:
        return await _original_pinecone_notes(tenant_id, query_vec, **kwargs)
    _note_route(guard, "agents.retrieval.pinecone_secondary_notes")
    return []


async def _guarded_consult_notebook(tenant_id: str, question: str, *args: Any,
                                    **kwargs: Any) -> Optional[str]:
    """NotebookLM del abogado: DESACTIVADO mientras hay guardián activo (R6).

    Lanza un subproceso con el CLI del abogado (su cuota, no la de este tope). El llamador
    (`agents.graph._notebooklm_context`) ya trata None como "sigue solo con el corpus local".
    """
    guard = _active_guard.get()
    if guard is None:
        return await _original_consult_notebook(tenant_id, question, *args, **kwargs)
    _note_route(guard, "connectors.notebooklm.consult_notebook")
    return None


async def _guarded_mcp_consult(tenant_id: str, question: str, *args: Any,
                               **kwargs: Any) -> Optional[str]:
    """Consulta a los servidores MCP del despacho: DESACTIVADA bajo guardián (R7).

    `mcp.turn.consult` LANZA los servidores MCP que el despacho conectó (subprocesos y red
    hacia sistemas de terceros) y da varias vueltas de tool-calling. Las llamadas al modelo de
    esas vueltas sí caen bajo el tope (van por `call_llm`), pero lo que hacen las HERRAMIENTAS
    del servidor externo no: puede ser una API de pago del despacho, y ni siquiera sabemos
    cuál. El llamador (`agents.graph._mcp_context`) ya trata None como "el turno sigue con el
    corpus local": apagarla es un camino soportado, no una mutilación.
    """
    guard = _active_guard.get()
    if guard is None:
        return await _original_mcp_consult(tenant_id, question, *args, **kwargs)
    _note_route(guard, "mcp.turn.consult")
    return None


def _guarded_hub_invoke_result(self: Any, key: str, prompt: str, tenant_id: str) -> Any:
    """Delegación a CLIs externos por subproceso: DESACTIVADA bajo guardián (R7).

    `agents.graph` delega en CLIs de agentes (`AgentHub.invoke_result` → `subprocess`, ver
    graph.py ~L939). Un CLI externo consume la cuota o la tarjeta del despacho por una vía que
    este tope no ve ni puede medir. El llamador ya degrada fail-soft ante `not res.ok` ("el
    turno CONTINÚA sin el ayudante"), así que devolver un resultado NO-ok es exactamente un
    camino de producción soportado.
    """
    guard = _active_guard.get()
    if guard is None:
        return _original_hub_invoke_result(self, key, prompt, tenant_id)
    _note_route(guard, "gateway.agent_hub.AgentHub.invoke_result")
    from ..gateway import agent_hub as hub_mod

    return hub_mod.InvokeResult(
        hub_mod.STATUS_NOT_INSTALLED,
        "Ese asistente no está disponible ahora mismo. Mia sigue con el expediente y el "
        "corpus del despacho.",
        detail="DESACTIVADO por el tope de gasto del banco de pruebas (modo hermético)")


# ── EL REGISTRO DE RUTAS DE GASTO (R7) ───────────────────────────────────────
@dataclass(frozen=True)
class SpendRoute:
    """Una ruta capaz de gastar dinero o salir a la red, con su estado y su porqué.

    `module`/`attr`/`wrapper`/`original` solo aplican a GOBERNADA y DESACTIVADA: son la
    sustitución que `ensure_installed` aplica Y COMPRUEBA. `attr` admite `Clase.metodo`.
    Una entrada DECLARADA no sustituye nada — es un hueco escrito a mano, que es la única
    forma honesta de tener un hueco.
    """
    name: str
    estado: str
    por_que: str
    module: Optional[str] = None
    attr: Optional[str] = None
    wrapper: Optional[str] = None
    original: Optional[str] = None


SPEND_ROUTES: tuple[SpendRoute, ...] = (
    SpendRoute(
        name="agent.llm._invoke", estado=GOBERNADA,
        module="agent.llm", attr="_invoke",
        wrapper="_guarded_invoke", original="_original_invoke",
        por_que="punto ÚNICO donde se despacha UN intento cobrable del modelo. Reserva con "
                "cota superior antes y liquida al coste real después."),
    SpendRoute(
        name="embeddings.embed_texts", estado=GOBERNADA,
        module="embeddings", attr="embed_texts",
        wrapper="_guarded_embed_texts", original="_original_embed_texts",
        por_que="Voyage es red PAGADA y nunca pasó por call_llm. Reserva el peor caso "
                "(EMBED_MAX_ATTEMPTS intentos, 1 token por carácter) y devuelve lo no usado."),
    SpendRoute(
        name="agents.retrieval.pinecone_secondary_notes", estado=DESACTIVADA,
        module="agents.retrieval", attr="pinecone_secondary_notes",
        wrapper="_guarded_pinecone_notes", original="_original_pinecone_notes",
        por_que="consulta Pinecone con su propio cliente (factura por lectura) y no pasa por "
                "las capas envueltas. Es un store SECUNDARIO opt-in y fail-soft: devolver [] "
                "es un camino soportado."),
    SpendRoute(
        name="connectors.notebooklm.consult_notebook", estado=DESACTIVADA,
        module="connectors.notebooklm", attr="consult_notebook",
        wrapper="_guarded_consult_notebook", original="_original_consult_notebook",
        por_que="lanza un subproceso con el CLI de NotebookLM del abogado (su cuota, fuera de "
                "este tope). El enriquecimiento es fail-soft: devolver None es un camino "
                "soportado."),
    SpendRoute(
        name="mcp.turn.consult", estado=DESACTIVADA,
        module="mcp.turn", attr="consult",
        wrapper="_guarded_mcp_consult", original="_original_mcp_consult",
        por_que="levanta los servidores MCP del despacho (subprocesos + red a terceros) y da "
                "vueltas de tool-calling; lo que cobren esas herramientas no lo ve este tope. "
                "graph._mcp_context ya trata None como 'sigue con el corpus local'."),
    SpendRoute(
        name="gateway.agent_hub.AgentHub.invoke_result", estado=DESACTIVADA,
        module="gateway.agent_hub", attr="AgentHub.invoke_result",
        wrapper="_guarded_hub_invoke_result", original="_original_hub_invoke_result",
        por_que="delegación a CLIs de agentes externos por subproceso (graph.py ~L939): "
                "consume la cuota del despacho por una vía que este tope no puede medir. El "
                "llamador ya degrada fail-soft ante un resultado NO-ok."),
    SpendRoute(
        name="agent.subscription_llm (CLIs de la suscripción)", estado=DECLARADA,
        por_que="los aliases 'cli-*' salen por subproceso al CLI de la suscripción del "
                "abogado. Pasan por agent.llm._invoke, así que el guardián los CUENTA (tokens "
                "y duración), pero su coste en USD es 0 por definición: lo que consumen es la "
                "CUOTA de la suscripción, que no se puede medir en dólares desde aquí. Hueco "
                "declarado a propósito: no es dinero de la tarjeta, es cuota del plan."),
)


def route_by_name(name: str) -> Optional[SpendRoute]:
    for r in SPEND_ROUTES:
        if r.name == name:
            return r
    return None


def _note_route(guard: "EvalSpendGuard", name: str) -> None:
    route = route_by_name(name)
    if route is not None:
        guard.note_untracked(route.name, f"[{route.estado}] {route.por_que}")


def _resolve_target(module: str, attr: str) -> tuple[Any, str]:
    """(dueño, nombre_del_atributo) de una entrada del registro. `attr` admite `Clase.metodo`."""
    import importlib

    root = __name__.split(".")[0]                       # 'mia'
    owner: Any = importlib.import_module(f"{root}.{module}")
    parts = attr.split(".")
    for p in parts[:-1]:
        owner = getattr(owner, p)
    return owner, parts[-1]


def ensure_installed() -> None:
    """Aplica el REGISTRO de rutas y COMPRUEBA que quedó aplicado. Fail-closed (R7).

    UNA vez por proceso, y PARA SIEMPRE: no existe la operación inversa a propósito (ver el
    encabezado). Desinstalar abría una ventana en la que un import diferido capturaba la
    envoltura y se quedaba con ella apuntando a un original None → `TypeError` en producción
    hasta reiniciar el proceso. Todas las envolturas delegan tal cual si no hay guardián en el
    ContextVar, así que producción queda intacta aunque el parche esté puesto para siempre.

    Lo NUEVO (modo hermético): esto ya no es una lista de `try/except` que anota los huecos que
    no pudo tapar. Cualquier entrada del registro que no se pueda aplicar —módulo que no
    importa, atributo renombrado, sustitución que no se sostiene— levanta
    `SpendRouteUnavailable` y la corrida NO ARRANCA. Si el producto crece una ruta nueva y
    nadie la clasifica, lo que se rompe es el banco, no la tarjeta.
    """
    global _installed
    with _install_lock:
        if _installed:
            return
        for route in SPEND_ROUTES:
            if route.estado == DECLARADA:
                continue
            if route.estado not in (GOBERNADA, DESACTIVADA):
                raise SpendRouteUnavailable(
                    f"la ruta de gasto '{route.name}' tiene un estado desconocido "
                    f"('{route.estado}'): solo existen {GOBERNADA}, {DESACTIVADA} y "
                    f"{DECLARADA}. No se corre el banco.")
            wrapper = globals().get(route.wrapper or "")
            if not callable(wrapper):
                raise SpendRouteUnavailable(
                    f"la ruta de gasto '{route.name}' declara la envoltura "
                    f"'{route.wrapper}', que no existe en spend_guard. No se corre el banco.")
            try:
                owner, name = _resolve_target(route.module or "", route.attr or "")
                original = getattr(owner, name)
            except Exception as exc:  # noqa: BLE001 — no poder clasificarla NO autoriza a correr
                raise SpendRouteUnavailable(
                    f"la ruta de gasto '{route.name}' no se pudo resolver "
                    f"({type(exc).__name__}: {exc}). Una ruta que no se puede clasificar en "
                    f"{GOBERNADA}/{DESACTIVADA}/{DECLARADA} podría gastar sin techo, así que "
                    "el banco NO arranca.") from exc
            if original is wrapper:
                # Ya envuelta (una pasada anterior de esta misma función). Volver a guardar el
                # "original" aquí guardaría LA ENVOLTURA como original: la envoltura se
                # llamaría a sí misma y el proceso moriría por recursión infinita en la
                # primera llamada al modelo. Idempotencia por ruta, no solo por proceso.
                continue
            globals()[route.original or ""] = original
            setattr(owner, name, wrapper)
            if getattr(owner, name) is not wrapper:
                # Un descriptor, un __setattr__ propio o un módulo congelado pueden aceptar el
                # setattr y no aplicarlo. Aplicar sin comprobar es exactamente la clase de
                # silencio que este modo existe para eliminar.
                raise SpendRouteUnavailable(
                    f"la ruta de gasto '{route.name}' se intentó dejar en {route.estado} pero "
                    "la sustitución NO quedó aplicada. No se corre el banco.")
        _installed = True


@contextmanager
def install() -> Iterator[None]:
    """Compatibilidad: instala (idempotente) y NO revierte al salir.

    Se conserva la forma de contexto porque el harness la usa como `with install(), ...`, pero
    ya no hay desinstalación: las envolturas quedan puestas el resto del proceso. Es inofensivo
    — sin guardián en el ContextVar, TODAS delegan en el original tal cual.
    """
    ensure_installed()
    yield
