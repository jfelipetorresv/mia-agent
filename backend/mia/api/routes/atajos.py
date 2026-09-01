"""Mia · api.routes.atajos — atajos de despacho para la conversación vacía (Meta E · Mitad 2).

`GET /api/atajos` -> los atajos que se muestran. El abogado pulsa uno y el frontend PRE-LLENA
el cuadro de mensaje con su texto reproducible — consent-first, nunca se auto-envía; el
abogado revisa y decide.

El resto del router es la capa EDITABLE (bloque D7, punto 18 de la bitácora 2026-08-19): la
derivación automática se conserva intacta y encima el despacho puede fijar, ocultar,
renombrar y agregar atajos propios.

    GET    /api/atajos            los que se ven ahora (lo que consume la conversación vacía)
    GET    /api/atajos/catalogo   todos, con su estado, + el conteo real del cupo
    POST   /api/atajos            crea un atajo propio {label, texto}
    PATCH  /api/atajos/{clave}    fija / oculta / renombra un atajo (parcial)
    PUT    /api/atajos/orden      reordena los atajos fijados {claves: [...]}
    PUT    /api/atajos/{clave}    reescribe un atajo propio {label, texto}
    DELETE /api/atajos/{clave}    borra un atajo propio · devuelve un derivado a su estado
                                  automático

`clave` es 'guia:<id>', 'agente:<id>' o 'propio:<id>'.

Auth: el JWT middleware fija `request.state.tenant_id`; TODA lectura y escritura pasa por RLS
(pool.tenant_connection), así que un despacho no puede ver ni tocar los atajos de otro.
§G: los mensajes de error van en llano, sin jerga.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...memory.atajos import (AtajoError, actualizar_propio, crear_propio, eliminar,
                              estado_atajos, guardar_preferencia, list_shortcuts,
                              partir_clave, reordenar)

router = APIRouter(prefix="/atajos", tags=["atajos"])
logger = logging.getLogger("mia.api.atajos")


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


class AtajoPropioBody(BaseModel):
    """Un atajo escrito por el abogado: cómo se llama el botón y qué me pide al pulsarlo."""

    label: str = Field(min_length=1, max_length=48)
    texto: str = Field(min_length=1, max_length=2000)


class OrdenBody(BaseModel):
    """El orden completo, de la primera a la última clave."""

    claves: list[str] = Field(min_length=1, max_length=200)


class PreferenciaBody(BaseModel):
    """Cambio parcial sobre un atajo: lo que llega como null no se toca."""

    label: str | None = None
    fijado: bool | None = None
    oculto: bool | None = None


@router.get("")
async def obtener_atajos(request: Request):
    """Los atajos que se muestran ahora mismo en la conversación vacía."""
    tid = _tenant(request)
    return {"atajos": await list_shortcuts(tid)}


@router.get("/catalogo")
async def obtener_catalogo(request: Request):
    """Todo lo que necesita la pantalla de atajos: cada atajo con su estado (incluidos los
    ocultos, que ahí sí se ven para poder encenderlos de nuevo) y el conteo del cupo."""
    tid = _tenant(request)
    try:
        return await estado_atajos(tid)
    except Exception:  # noqa: BLE001
        logger.exception("catalogo de atajos falló (tenant=%s)", tid)
        raise HTTPException(
            status_code=502,
            detail="No pude cargar tus atajos en este momento. Intenta de nuevo.",
        )


@router.post("")
async def crear_atajo(body: AtajoPropioBody, request: Request):
    """Agrega un atajo propio. Nace fijado: existe porque el abogado lo quiso."""
    tid = _tenant(request)
    try:
        return await crear_propio(tid, body.label, body.texto)
    except AtajoError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:  # noqa: BLE001
        logger.exception("crear atajo falló (tenant=%s)", tid)
        raise HTTPException(
            status_code=502,
            detail="No pude guardar el atajo en este momento. Intenta de nuevo.",
        )


@router.patch("/{clave}")
async def cambiar_atajo(clave: str, body: PreferenciaBody, request: Request):
    """Fija, oculta o renombra un atajo (cualquiera de los tres tipos)."""
    tid = _tenant(request)
    try:
        return await guardar_preferencia(
            tid, clave, label=body.label, fijado=body.fijado, oculto=body.oculto)
    except AtajoError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:  # noqa: BLE001
        logger.exception("cambiar atajo falló (tenant=%s clave=%s)", tid, clave)
        raise HTTPException(
            status_code=502,
            detail="No pude guardar el cambio en este momento. Intenta de nuevo.",
        )


@router.put("/orden")
async def ordenar_atajos(body: OrdenBody, request: Request):
    """Guarda el orden de los atajos. Va declarada ANTES de `PUT /{clave}`: si no, «orden»
    entra como una clave más y la reordenación nunca llega aquí."""
    tid = _tenant(request)
    try:
        return await reordenar(tid, body.claves)
    except AtajoError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:  # noqa: BLE001
        logger.exception("ordenar atajos falló (tenant=%s)", tid)
        raise HTTPException(
            status_code=502,
            detail="No pude guardar el orden en este momento. Intenta de nuevo.",
        )


@router.put("/{clave}")
async def reescribir_atajo(clave: str, body: AtajoPropioBody, request: Request):
    """Reescribe un atajo propio (nombre y texto). Los derivados no se reescriben aquí: su
    texto sale de la guía o del agente, y ahí es donde se cambia."""
    tid = _tenant(request)
    try:
        fuente, ident = partir_clave(clave)
        if fuente != "propio":
            raise AtajoError(
                "Este atajo lo preparo yo a partir de tu guía o de tu ayudante: puedo "
                "cambiarle el nombre visible, pero lo que me pide se edita en la guía o en "
                "el ayudante.")
        return await actualizar_propio(tid, ident, body.label, body.texto)
    except AtajoError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:  # noqa: BLE001
        logger.exception("reescribir atajo falló (tenant=%s clave=%s)", tid, clave)
        raise HTTPException(
            status_code=502,
            detail="No pude guardar el atajo en este momento. Intenta de nuevo.",
        )


@router.delete("/{clave}")
async def borrar_atajo(clave: str, request: Request):
    """Borra un atajo propio; sobre un derivado, lo devuelve a como lo propongo yo sola."""
    tid = _tenant(request)
    try:
        return await eliminar(tid, clave)
    except AtajoError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:  # noqa: BLE001
        logger.exception("borrar atajo falló (tenant=%s clave=%s)", tid, clave)
        raise HTTPException(
            status_code=502,
            detail="No pude borrar el atajo en este momento. Intenta de nuevo.",
        )
