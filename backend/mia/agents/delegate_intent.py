"""Mia · agents.delegate_intent — ¿el abogado PIDIÓ un ayudante externo? (CP-HUB).

EL PROBLEMA QUE RESUELVE: hasta ahora `graph.py::_maybe_delegate` leía
`state.metadata['delegate']` y NADIE lo escribía nunca. El Agent Hub tenía API,
interruptor y ejecución, pero la delegación estaba MUERTA: habilitar un ayudante no
cambiaba nada. Este módulo es quien decide CUÁNDO se delega.

DECISIÓN DE DISEÑO — INVOCACIÓN EXPLÍCITA POR NOMBRE, DETERMINISTA:
Mia delega SOLO si el abogado NOMBRA al ayudante en su propio mensaje y le pide, con un
verbo, que lo use ("usa el asistente de navegación web para buscar el estado del
radicado"). Nada más. Sin LLM, sin heurística de "tipo de tarea", sin proponer nada.

Por qué esta vía y no las otras (el criterio rector es: la más SIMPLE y SEGURA que haga
que el interruptor sea real, y ante la duda que mande el abogado):

  · (Elegida) Invocación explícita. El acto de pedirlo ES el consentimiento, y es por
    mensaje: el abogado sabe exactamente qué texto sale del equipo, porque es el que
    acaba de escribir nombrando a quién se lo manda. Es determinista (mismo texto → misma
    decisión, auditable en la traza), cuesta 0 tokens y 0 latencia, y su modo de fallo es
    el seguro: si no detecta la intención, NO pasa nada (el turno sigue igual). Nunca
    puede sacar datos del expediente por sorpresa, porque nunca actúa sola.

  · (Descartada AQUÍ; rehabilitada en CP-HUB2 con aprobación humana) Que el LLM decida.
    Como ÚNICA puerta era lo contrario del criterio: un modelo decidiendo motu proprio
    sacar el expediente del equipo, y una inyección indirecta desde un documento del propio
    expediente ("ejecuta el asistente de navegación y súbelo a…") se convertía en
    exfiltración. Lo que cambió en CP-HUB2 no es la confianza en el modelo: es que ya no es
    él quien abre la puerta (el abogado ve el texto antes de que salga) y que el proponente
    NO recibe el expediente, así que no puede filtrar lo que nunca leyó.

  · (Descartada) Reglas por tipo de tarea. Delegación INVISIBLE: el abogado escribe una
    consulta normal y su texto sale del equipo sin que él lo haya pedido ni lo note. Es
    exactamente la sorpresa que el encargo prohíbe.

  · (Complementaria desde CP-HUB2) Que Mia lo proponga y el abogado apruebe (HITL con
    `interrupt()`). Se descartó en CP-HUB porque era más máquina para el mismo resultado
    —si el abogado ya escribió la orden, preguntarle "¿confirmas?" es una pausa de más— y
    se reservó "para el día en que Mia deba delegar sin que se lo pidan". Ese día llegó:
    Pipe rechazó que Mia no pudiera decidir por su cuenta, y CP-HUB2 construyó ese segundo
    punto de interrupción (`agents/delegate_proposal.py` + `graph.py::delegation_node` +
    `architecture/hitl_flow.md` §8). Este módulo NO cambia: sigue siendo el camino de la
    ORDEN, y sigue sin preguntar nada — lo que el abogado acaba de pedir no se le vuelve a
    preguntar. Los dos caminos conviven; el candado de `hub_gate` es el mismo para ambos.

MODO DE FALLO ELEGIDO: falso NEGATIVO. Ante ambigüedad (dos ayudantes nombrados, negación
cerca, verbo ausente) NO delega. Que el abogado tenga que reformular es barato; que su
expediente salga del equipo sin pedirlo, no.

Módulo PURO: sin I/O, sin DB, sin LLM. Solo texto → clave de conector (o None). El
candado de confidencialidad NO vive aquí: vive en `gateway/hub_gate.py`, y se aplica
DESPUÉS. Detectar la intención no autoriza nada.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from ..gateway.agent_hub import CONNECTORS

# Alias por conector, EXPLÍCITOS (no derivados del display_name con reglas): una tabla que
# se lee de un vistazo vale más que una derivación lista que un día parta "editor de
# documentos" en "editor de". Van normalizados (minúsculas, sin tildes).
#
# OJO: los `slug` sueltos ("documentos", "escritorio", "investigacion") NO son alias — son
# palabras del oficio que aparecen en cualquier consulta jurídica ("revisa los documentos
# del expediente"). Solo la frase COMPLETA nombra a un ayudante.
_ALIASES: dict[str, tuple[str, ...]] = {
    "hermes": ("asistente de investigacion juridica", "asistente de investigacion"),
    "claude_code": ("editor de documentos",),
    "codex": ("asistente de automatizacion",),
    "antigravity": ("asistente de escritorio",),
    "openclaw": ("asistente de navegacion web", "asistente de navegacion"),
}

# Verbos que convierten "mencionar" en "pedir". Sin uno de estos, nombrar al ayudante no
# delega ("el editor de documentos no me sirvió" NO es una orden).
_VERBS = (
    "usa", "usalo", "usar", "use", "usen", "usemos", "usando",
    "utiliza", "utilizalo", "utilizar", "utilice",
    "emplea", "emplear", "abre", "abrir", "llama", "llamalo", "llamar", "llame",
    "pide", "pidele", "pedir", "pedirle", "delega", "delegar", "delegale",
    "manda", "mandale", "mandar", "encarga", "encargale", "encargar",
    "consulta", "consultale", "consultar", "corre", "correr", "ejecuta", "ejecutar",
    "dile", "pregunta", "preguntale",
)
_VERB_RE = re.compile(r"\b(" + "|".join(_VERBS) + r")\b")

# Negaciones: si aparecen justo antes del ayudante, la frase es lo contrario de una orden
# ("NO uses el asistente de navegación"). Fail-closed: en la duda no se delega.
_NEG_RE = re.compile(r"\b(no|ni|sin|nunca|jamas|tampoco|evita|evitar|omite)\b")
_NEG_WINDOW = 40  # chars antes del alias donde una negación invalida la orden


def _normalize(text: str) -> str:
    """Minúsculas + sin tildes + espacios colapsados. El abogado dicta por voz: 'usá',
    'USA', 'navegación' y 'navegacion' deben caer en el mismo sitio."""
    t = unicodedata.normalize("NFD", str(text or "")).lower()
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", t)


def detect(message: str) -> Optional[str]:
    """Clave del conector que el abogado pidió explícitamente, o None.

    None es el caso NORMAL y silencioso: sin intención explícita no se delega y el turno
    sigue exactamente igual que hoy. Devolver una clave NO autoriza nada — el llamador
    debe pasar por `gateway/hub_gate.delegation_allowed` antes de sacar un solo byte."""
    text = _normalize(message)
    if not text:
        return None

    # 1 · ¿Qué ayudantes están nombrados? (posición del alias más temprano de cada uno)
    hits: dict[str, int] = {}
    for key in CONNECTORS:  # recorre CONNECTORS: un conector nuevo sin alias no se detecta
        for alias in _ALIASES.get(key, ()):
            pos = text.find(alias)
            if pos != -1:
                hits[key] = min(hits.get(key, pos), pos)

    if len(hits) != 1:
        # 0 → no pidió nada. >1 → ambiguo ("¿el editor o el de navegación?"): NO adivinamos
        # a cuál sacarle el texto del expediente. Fail-closed.
        return None
    key, pos = next(iter(hits.items()))

    # 2 · ¿Es una ORDEN? El verbo debe estar ANTES del nombre del ayudante ("usa el
    # asistente de navegación"), no en cualquier parte de un párrafo largo — así
    # "revisa el expediente; el editor de documentos está desactualizado" no dispara.
    head = text[:pos]
    if not _VERB_RE.search(head):
        return None

    # 3 · Negación pegada al ayudante → lo contrario de una orden.
    if _NEG_RE.search(head[-_NEG_WINDOW:]):
        return None
    return key
