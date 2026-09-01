"""Mia · memory.atajos — atajos de despacho para la conversación vacía (Meta E · Mitad 2).

QUÉ ES: un texto reproducible y determinista, listo para PRE-LLENAR el cuadro de mensaje del
abogado (consent-first — NUNCA se auto-envía; el abogado siempre revisa y pulsa enviar). Hay
tres tipos:

  · Atajo de GUÍA: reproduce el título y el "cuándo aplica" de una guía activa del despacho.
  · Atajo de AGENTE (persona): EMBEBE literalmente una de las `summon_phrases` existentes de
    la persona, así que `agents.personas.detect_persona()` la reconoce SIN que este módulo
    toque un solo bit de esa resolución (misma función ya gateada de siempre).
  · Atajo PROPIO: lo escribió el abogado. No deriva de nada; vive entero en `shortcut_prefs`.

LA CAPA DE PREFERENCIAS (bloque D7, punto 18 de la bitácora 2026-08-19)
======================================================================
Los dos primeros tipos siguen DERIVÁNDOSE SOLOS (esa es su gracia: aparecen sin configurar
nada). Encima de esa derivación va la tabla `shortcut_prefs` (migración 062), que guarda lo
que el despacho decidió sobre cada atajo:

    fijar      el atajo entra siempre, aunque el reparto automático lo dejara fuera
    ocultar    el atajo no vuelve a aparecer, sin tener que borrar la guía ni el agente
    renombrar  cambia el nombre VISIBLE; el texto que se pre-llena no se toca
    agregar    un atajo propio, escrito a mano

Si el despacho no toca nada, la tabla queda vacía y el resultado es idéntico al de antes.

EL CUPO, SIN DESCARTES EN SILENCIO
==================================
`MAX_SHORTCUTS` (6) es el cupo de la fila. Regla: **lo fijado nunca se descarta**. Los fijados
entran todos y los automáticos ocupan lo que sobre; si el abogado fija más de seis, la fila
crece y no entra ningún automático — y eso se le DICE en la pantalla de atajos
(`estado_atajos` devuelve el conteo exacto para que el aviso no sea una suposición).

PUREZA: `build_playbook_shortcut` / `build_persona_shortcut` / `componer_atajos` no tocan la DB
ni tienen efectos (mismo input → mismo texto, byte a byte). El resto lee o escribe la DB.

FAIL-OPEN: `list_shortcuts` nunca lanza; ante cualquier error de DB devuelve lista vacía
(mostrar atajos es una ayuda, no un candado — patrón agents.personas.PersonaService). Las
funciones de escritura SÍ lanzan `AtajoError` con mensaje en llano: ahí el abogado pulsó
«guardar» y merece saber que no se guardó.
"""
from __future__ import annotations

import uuid
import logging
from typing import Any, Optional

from ..db import pool

logger = logging.getLogger("mia.memory.atajos")

# Cuántos atajos como máximo se ofrecen en la conversación vacía (frontend: hasta 6 chips).
MAX_SHORTCUTS = 6

# Cupo GARANTIZADO para los agentes del despacho dentro de `MAX_SHORTCUTS`.
# Por qué: antes se anexaban las guías primero y se cortaba al final, así que con 6 o más guías
# activas los agentes NO salían NUNCA — el despacho los configuraba en su pantalla y no volvía a
# verlos en la conversación vacía, que es justo donde más los usaría. Este cupo se reserva ANTES
# del corte. No agranda la lista: si no hay agentes, las guías se quedan con los 6 cupos.
RESERVED_FOR_AGENTS = 2

# Cuántas guías se EXAMINAN (no cuántas se muestran). Antes se leían solo `limit` guías, así que
# una guía poco usada no podía fijarse: no llegaba siquiera a la lista. Se examina un tramo
# amplio para que fijar funcione sobre cualquier guía activa razonable del despacho.
DERIVED_SCAN = 200

# Topes de lo que el abogado escribe. El nombre visible es una etiqueta de un botón, no un
# párrafo; el texto es una instrucción para Mia, no un escrito.
MAX_LABEL = 48
MAX_TEXTO = 2000
# Tope de atajos propios por despacho. Sin tope, la pantalla se vuelve un cajón de sastre.
MAX_PROPIOS = 20

FUENTES = ("guia", "agente", "propio")


class AtajoError(ValueError):
    """Error de negocio con el mensaje YA redactado para el abogado (§G, sin jerga)."""


# ── Textos derivados (puros) ────────────────────────────────────────────────
def build_playbook_shortcut(row: dict) -> str:
    """Texto reproducible de una guía: 'Aplica la guía del despacho "X": <cuándo aplica>.
    Marca [VERIFICAR] lo que no puedas confirmar.' Puro y determinista (mismo `row` → mismo
    texto, byte a byte)."""
    title = str(row.get("title") or "").strip()
    applies_when = str(row.get("applies_when") or "").strip()
    texto = f'Aplica la guía del despacho "{title}"'
    if applies_when:
        texto += f": {applies_when}"
    texto += ". Marca [VERIFICAR] lo que no puedas confirmar."
    return texto


def build_persona_shortcut(persona: dict) -> Optional[str]:
    """Texto reproducible de un agente (persona): EMBEBE literalmente una de sus
    `summon_phrases` (la más larga — mismo criterio de especificidad que
    `agents.personas.detect_persona`) para que esa función la reconozca sin ningún cambio en
    su resolución. None si la persona no tiene ninguna frase de invocación utilizable.

    Puro y determinista (mismo `persona` → mismo texto, byte a byte)."""
    phrases = [str(p).strip() for p in (persona.get("summon_phrases") or []) if str(p).strip()]
    if not phrases:
        return None
    phrase = max(phrases, key=len)  # la más larga: la más específica, igual que detect_persona
    description = str(persona.get("description") or "").strip()
    texto = f"Quiero que trabajes {phrase} en este asunto."
    if description:
        texto += f" {description}"
    return texto


def clave(source: str, source_id: Optional[str]) -> str:
    """Identificador estable de un atajo dentro del despacho: 'guia:<id>', 'agente:<id>' o
    'propio:<id de la fila>'. Es lo que viaja en la URL del endpoint y en el `key` de React."""
    return f"{source}:{source_id}" if source_id else source


def partir_clave(valor: str) -> tuple[str, str]:
    """'guia:<uuid>' → ('guia', '<uuid>'). Lanza AtajoError si no es una clave válida.

    El identificador tiene que ser un UUID, y se comprueba AQUÍ. Las tres columnas que lo
    reciben son de tipo `uuid`, así que un identificador con cualquier otra forma no llegaba
    a rebotar en la validación sino en la base, como `InvalidTextRepresentation`: eso no es
    un `AtajoError`, caía en el `except Exception` del router y el abogado recibía un 502 con
    «intenta de nuevo» —una invitación a repetir algo que nunca va a funcionar— más un
    `logger.exception` que ensucia el registro como si el servicio se hubiera caído.
    Validado aquí, es un 422 con el motivo correcto. (La inyección ya estaba cerrada por el
    tipado y los parámetros ligados; esto arregla el mensaje y el ruido, no un agujero.)
    """
    fuente, _, ident = str(valor or "").partition(":")
    ident = ident.strip()
    if fuente not in FUENTES or not ident:
        raise AtajoError("Ese atajo no existe o ya no está disponible.")
    try:
        uuid.UUID(ident)
    except (ValueError, AttributeError, TypeError):
        raise AtajoError("Ese atajo no existe o ya no está disponible.") from None
    return fuente, ident


# ── Composición del cupo (pura) ─────────────────────────────────────────────
def componer_atajos(
    guias: list[dict],
    agentes: list[dict],
    propios: list[dict],
    limit: int = MAX_SHORTCUTS,
) -> list[dict]:
    """Decide QUÉ atajos se ven y en qué orden. Pura: mismas listas → misma salida.

    Entrada: los tres grupos ya con sus preferencias aplicadas (ocultos fuera, nombre visible
    resuelto, `fijado` puesto). Salida: la lista final para la conversación vacía.

    REGLA: lo fijado nunca se descarta. Primero entran TODOS los fijados (por `position`, luego
    por antigüedad); con los cupos que sobren se reparte lo automático — atajos propios sin
    fijar primero (existen porque alguien los escribió), después guías y agentes con la reserva
    histórica de `RESERVED_FOR_AGENTS`. Si los fijados ya llenan o desbordan el cupo, no entra
    ningún automático (y la pantalla de atajos lo dice con el número exacto).
    """
    fijados = [a for a in (propios + guias + agentes) if a.get("fijado")]
    fijados.sort(key=lambda a: (int(a.get("orden") or 0), str(a.get("desde") or ""), a["label"]))

    libre = max(0, limit - len(fijados))
    propios_auto = [a for a in propios if not a.get("fijado")][:libre]
    libre -= len(propios_auto)

    guias_auto = [a for a in guias if not a.get("fijado")]
    agentes_auto = [a for a in agentes if not a.get("fijado")]
    reserva = max(0, min(RESERVED_FOR_AGENTS, len(agentes_auto), libre))
    n_guias = max(0, min(len(guias_auto), libre - reserva))
    n_agentes = max(0, min(len(agentes_auto), libre - n_guias))
    return fijados + propios_auto + guias_auto[:n_guias] + agentes_auto[:n_agentes]


# ── Lectura ─────────────────────────────────────────────────────────────────
async def _leer(conn, limit_scan: int) -> tuple[list[dict], list[dict], list[dict]]:
    """Lee guías activas, agentes habilitados y preferencias, y aplica unas sobre otros.

    Devuelve (guias, agentes, propios), cada elemento con la forma pública de un atajo más su
    estado: `oculto`, `fijado`, `renombrado`, `orden`, `desde`.
    """
    pb_rows = await (await conn.execute(
        "SELECT id, title, applies_when FROM playbooks WHERE status = 'active' "
        "ORDER BY usage_count DESC, created_at LIMIT %s", (limit_scan,),
    )).fetchall()
    persona_rows = await (await conn.execute(
        "SELECT id, name, description, summon_phrases FROM personas "
        "WHERE enabled = true ORDER BY lower(name)"
    )).fetchall()
    pref_rows = await (await conn.execute(
        "SELECT id, source, source_id, label, texto, pinned, hidden, position, created_at "
        "FROM shortcut_prefs ORDER BY position, created_at"
    )).fetchall()

    prefs: dict[str, dict] = {}
    propios: list[dict] = []
    for r in pref_rows:
        pref = {
            "id": str(r[0]), "source": r[1], "source_id": str(r[2]) if r[2] else None,
            "label": r[3] or "", "texto": r[4] or "", "pinned": bool(r[5]),
            "hidden": bool(r[6]), "orden": int(r[7] or 0), "desde": str(r[8]),
        }
        if pref["source"] == "propio":
            propios.append({
                "clave": clave("propio", pref["id"]), "kind": "propio", "id": pref["id"],
                "label": pref["label"], "texto": pref["texto"],
                "label_original": "", "oculto": pref["hidden"], "fijado": pref["pinned"],
                "renombrado": False, "orden": pref["orden"], "desde": pref["desde"],
            })
        elif pref["source_id"]:
            prefs[clave(pref["source"], pref["source_id"])] = pref

    def _derivado(kind: str, ident: str, label: str, texto: str) -> dict:
        k = clave(kind, ident)
        pref = prefs.get(k)
        visible = (pref or {}).get("label") or label
        return {
            "clave": k, "kind": kind, "id": ident,
            "label": visible, "texto": texto,
            "label_original": label,
            "oculto": bool(pref and pref["hidden"]),
            "fijado": bool(pref and pref["pinned"]),
            "renombrado": bool(pref and pref["label"] and pref["label"] != label),
            "orden": (pref or {}).get("orden", 0),
            "desde": (pref or {}).get("desde", ""),
        }

    guias = [_derivado("guia", str(r[0]), r[1] or "", build_playbook_shortcut(
        {"title": r[1], "applies_when": r[2]})) for r in pb_rows]

    agentes: list[dict] = []
    for r in persona_rows:
        texto = build_persona_shortcut(
            {"name": r[1], "description": r[2], "summon_phrases": r[3]})
        if texto:
            agentes.append(_derivado("agente", str(r[0]), r[1] or "", texto))

    # Los propios ocultos existen (el abogado los escribió y luego los apartó): se devuelven
    # aquí para que la pantalla de atajos pueda mostrarlos y volverlos a encender.
    return guias, agentes, propios


def _publico(a: dict) -> dict:
    """La forma mínima que consume la conversación vacía (sin el estado de gestión)."""
    return {"kind": a["kind"], "id": a["id"], "label": a["label"], "texto": a["texto"],
            "clave": a["clave"], "fijado": bool(a.get("fijado"))}


async def list_shortcuts(tenant_id: str, limit: int = MAX_SHORTCUTS) -> list[dict]:
    """Atajos que se muestran en la conversación vacía, ya con las preferencias del despacho
    aplicadas (ocultos fuera, fijados siempre dentro, nombres renombrados).

    Determinista: para el mismo estado de la base de datos, el mismo orden y el mismo texto
    siempre. FAIL-OPEN: cualquier error de lectura → lista vacía (nunca rompe la pantalla).
    """
    try:
        async with pool.tenant_connection(tenant_id) as conn:
            guias, agentes, propios = await _leer(conn, DERIVED_SCAN)
    except Exception:  # noqa: BLE001 — mostrar atajos es una ayuda, no un candado
        logger.warning("atajos: no se pudieron cargar (tenant=%s)", tenant_id, exc_info=True)
        return []

    visibles = componer_atajos(
        [a for a in guias if not a["oculto"]],
        [a for a in agentes if not a["oculto"]],
        [a for a in propios if not a["oculto"]],
        limit,
    )
    return [_publico(a) for a in visibles]


async def estado_atajos(tenant_id: str, limit: int = MAX_SHORTCUTS) -> dict:
    """TODO lo que necesita la pantalla de atajos: cada atajo con su estado (incluidos los
    ocultos, que ahí sí se ven para poder volver a encenderlos) y el conteo real del cupo.

    El conteo NO es decorativo: es lo que sostiene el aviso honesto de la pantalla cuando el
    abogado fija más atajos de los que caben cómodamente en la fila.
    """
    async with pool.tenant_connection(tenant_id) as conn:
        guias, agentes, propios = await _leer(conn, DERIVED_SCAN)

    visibles = componer_atajos(
        [a for a in guias if not a["oculto"]],
        [a for a in agentes if not a["oculto"]],
        [a for a in propios if not a["oculto"]],
        limit,
    )
    claves_visibles = {a["clave"] for a in visibles}
    for a in guias + agentes + propios:
        a["en_conversacion"] = a["clave"] in claves_visibles

    fijados = sum(1 for a in guias + agentes + propios if a["fijado"] and not a["oculto"])
    return {
        "atajos": guias + agentes + propios,
        "cupo": {
            "maximo": limit,
            "fijados": fijados,
            "mostrados": len(visibles),
            "automaticos": len(visibles) - fijados,
            "desbordado": fijados > limit,
        },
    }


# ── Escritura ───────────────────────────────────────────────────────────────
def _limpiar_label(valor: Any, obligatorio: bool) -> str:
    label = str(valor or "").strip()
    if obligatorio and not label:
        raise AtajoError("Ponle un nombre al atajo para poder reconocerlo.")
    if len(label) > MAX_LABEL:
        raise AtajoError(f"El nombre del atajo no puede pasar de {MAX_LABEL} caracteres.")
    return label


def _limpiar_texto(valor: Any, obligatorio: bool) -> str:
    texto = str(valor or "").strip()
    if obligatorio and not texto:
        raise AtajoError("Escribe lo que quieres pedirme cuando pulses este atajo.")
    if len(texto) > MAX_TEXTO:
        raise AtajoError(f"El texto del atajo no puede pasar de {MAX_TEXTO} caracteres.")
    return texto


async def guardar_preferencia(
    tenant_id: str,
    valor_clave: str,
    *,
    label: Any = None,
    fijado: Optional[bool] = None,
    oculto: Optional[bool] = None,
) -> dict:
    """Fija, oculta o renombra UN atajo. Sirve para los tres tipos: sobre un derivado crea o
    actualiza su preferencia; sobre uno propio actualiza la fila que ya existe.

    Los campos que llegan como None no se tocan (actualización parcial). Fijar y ocultar son
    excluyentes: fijar algo oculto lo desoculta, y ocultar algo fijado lo desfija — así el
    abogado nunca queda con un atajo que dice estar fijado y no aparece.
    """
    fuente, ident = partir_clave(valor_clave)
    if fijado and oculto:
        raise AtajoError("Un atajo no puede estar fijado y oculto a la vez.")
    if fijado:
        oculto = False
    if oculto:
        fijado = False

    nuevo_label = None if label is None else _limpiar_label(label, obligatorio=(fuente == "propio"))

    async with pool.tenant_connection(tenant_id) as conn:
        if fuente == "propio":
            sets: list[str] = []
            params: list[Any] = []
            if nuevo_label is not None:
                sets.append("label = %s")
                params.append(nuevo_label)
            if fijado is not None:
                sets.append("pinned = %s")
                params.append(fijado)
            if oculto is not None:
                sets.append("hidden = %s")
                params.append(oculto)
            if not sets:
                raise AtajoError("No hay ningún cambio que guardar.")
            sets.append("updated_at = now()")
            params += [ident]
            row = await (await conn.execute(
                f"UPDATE shortcut_prefs SET {', '.join(sets)} "
                "WHERE id = %s AND source = 'propio' RETURNING id", params,
            )).fetchone()
            if not row:
                raise AtajoError("Ese atajo ya no existe.")
            return {"clave": clave("propio", ident)}

        # Derivado: alta o actualización de su preferencia (una por atajo y despacho).
        await conn.execute(
            "INSERT INTO shortcut_prefs (tenant_id, source, source_id, label, pinned, hidden) "
            "VALUES (app_current_tenant(), %s, %s, %s, %s, %s) "
            "ON CONFLICT (tenant_id, source, source_id) WHERE source_id IS NOT NULL DO UPDATE "
            # Los tres van con cast explícito: cuando el valor llega NULL (campo que no se
            # toca), Postgres no puede deducir el tipo de un parámetro suelto dentro de
            # COALESCE y la sentencia falla con «could not determine data type».
            "SET label  = COALESCE(%s::text,    shortcut_prefs.label), "
            "    pinned = COALESCE(%s::boolean, shortcut_prefs.pinned), "
            "    hidden = COALESCE(%s::boolean, shortcut_prefs.hidden), "
            "    updated_at = now()",
            (fuente, ident, nuevo_label or "", bool(fijado), bool(oculto),
             nuevo_label, fijado, oculto),
        )
    return {"clave": clave(fuente, ident)}


async def crear_propio(tenant_id: str, label: Any, texto: Any) -> dict:
    """Crea un atajo escrito por el abogado. Nace FIJADO: existe porque alguien lo quiso, así
    que no tiene que competir por cupo con los que Mia deriva sola."""
    nombre = _limpiar_label(label, obligatorio=True)
    cuerpo = _limpiar_texto(texto, obligatorio=True)
    async with pool.tenant_connection(tenant_id) as conn:
        cuantos = (await (await conn.execute(
            "SELECT count(*) FROM shortcut_prefs WHERE source = 'propio'")).fetchone())[0]
        if cuantos >= MAX_PROPIOS:
            raise AtajoError(
                f"Ya tienes {MAX_PROPIOS} atajos propios. Borra alguno para agregar otro.")
        row = await (await conn.execute(
            "INSERT INTO shortcut_prefs (tenant_id, source, label, texto, pinned) "
            "VALUES (app_current_tenant(), 'propio', %s, %s, true) RETURNING id",
            (nombre, cuerpo),
        )).fetchone()
    return {"clave": clave("propio", str(row[0])), "id": str(row[0]),
            "label": nombre, "texto": cuerpo}


async def actualizar_propio(tenant_id: str, ident: str, label: Any, texto: Any) -> dict:
    """Cambia el nombre y el texto de un atajo propio."""
    nombre = _limpiar_label(label, obligatorio=True)
    cuerpo = _limpiar_texto(texto, obligatorio=True)
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "UPDATE shortcut_prefs SET label = %s, texto = %s, updated_at = now() "
            "WHERE id = %s AND source = 'propio' RETURNING id", (nombre, cuerpo, ident),
        )).fetchone()
    if not row:
        raise AtajoError("Ese atajo ya no existe.")
    return {"clave": clave("propio", ident), "id": ident, "label": nombre, "texto": cuerpo}


async def reordenar(tenant_id: str, claves: list[str]) -> dict:
    """Fija el ORDEN de los atajos fijados, en el orden en que llegan las claves.

    El orden solo decide entre los FIJADOS: `componer_atajos` los coloca primero, ordenados
    por `position`, y lo automático se reparte después con lo que sobre del cupo. Reordenar un
    atajo que no está fijado guarda su posición igual —no se pierde— pero no cambia nada de lo
    que se ve hasta que lo fijen. La pantalla lo dice; aquí no se inventa una regla distinta.

    Sobre un derivado sin preferencia previa se crea la fila (esa es la única forma de
    guardarle una posición) SIN fijarlo ni ocultarlo: reordenar no puede tener el efecto
    lateral de fijar algo que el abogado no fijó. Pero solo si la guía o el agente EXISTEN:
    sin esa comprobación, este endpoint creaba una fila por cada identificador recibido —la
    tabla no tiene clave foránea a propósito (ver la 062) ni tope de filas—, así que un
    cliente autenticado podía inflar `shortcut_prefs` indefinidamente con preferencias de
    atajos que no existen y que nadie lee jamás.

    Las posiciones se numeran desde 1 en el orden recibido. Una clave repetida se toma una
    sola vez, en su primera aparición; una clave que ya no existe hace fallar la operación
    ENTERA en vez de reordenar a medias: media reordenación es peor que ninguna, porque deja
    la fila en un orden que el abogado no pidió y no puede explicarse. Eso se cumple de
    verdad porque `pool.tenant_connection` abre TRANSACCIÓN: si una clave falla a mitad, lo
    ya escrito se deshace con ella.
    """
    if not isinstance(claves, list) or not claves:
        raise AtajoError("No recibí ningún atajo que ordenar.")
    if len(claves) > 200:
        raise AtajoError("Son demasiados atajos para ordenar de una vez.")

    vistos: list[tuple[str, str]] = []
    ya: set[str] = set()
    for valor in claves:
        fuente, ident = partir_clave(str(valor))  # valida el formato y levanta AtajoError
        k = f"{fuente}:{ident}"
        if k in ya:
            continue
        ya.add(k)
        vistos.append((fuente, ident))

    async with pool.tenant_connection(tenant_id) as conn:
        for pos, (fuente, ident) in enumerate(vistos, start=1):
            if fuente == "propio":
                row = await (await conn.execute(
                    "UPDATE shortcut_prefs SET position = %s, updated_at = now() "
                    "WHERE id = %s AND source = 'propio' RETURNING id", (pos, ident),
                )).fetchone()
                if not row:
                    raise AtajoError("Uno de los atajos que intentas ordenar ya no existe.")
            else:
                # La guía o el agente tienen que EXISTIR en este despacho. Ambas consultas
                # van bajo RLS, así que una fila de otro despacho no cuenta como existente:
                # el mismo candado sirve para el aislamiento y para la basura.
                tabla = "playbooks" if fuente == "guia" else "personas"
                existe = await (await conn.execute(
                    f"SELECT 1 FROM {tabla} WHERE id = %s::uuid", (ident,))).fetchone()
                if not existe:
                    raise AtajoError(
                        "Uno de los atajos que intentas ordenar ya no existe.")
                await conn.execute(
                    "INSERT INTO shortcut_prefs (tenant_id, source, source_id, position) "
                    "VALUES (app_current_tenant(), %s, %s, %s) "
                    "ON CONFLICT (tenant_id, source, source_id) WHERE source_id IS NOT NULL "
                    "DO UPDATE SET position = %s, updated_at = now()",
                    (fuente, ident, pos, pos),
                )
    return {"ok": True, "ordenados": len(vistos)}


async def eliminar(tenant_id: str, valor_clave: str) -> dict:
    """Borra un atajo propio; sobre uno derivado, borra sus preferencias y lo devuelve a como
    Mia lo propone sola (nombre original, sin fijar, sin ocultar)."""
    fuente, ident = partir_clave(valor_clave)
    async with pool.tenant_connection(tenant_id) as conn:
        if fuente == "propio":
            row = await (await conn.execute(
                "DELETE FROM shortcut_prefs WHERE id = %s AND source = 'propio' RETURNING id",
                (ident,),
            )).fetchone()
            if not row:
                raise AtajoError("Ese atajo ya no existe.")
        else:
            await conn.execute(
                "DELETE FROM shortcut_prefs WHERE source = %s AND source_id = %s",
                (fuente, ident),
            )
    return {"ok": True}
