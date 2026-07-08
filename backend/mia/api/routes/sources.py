"""Mia · api.routes.sources — consulta de fuentes del corpus (Fase 1b · citas en línea).

Solo LECTURA: la pantalla del asunto pide aquí el texto de la fuente que respalda una
cita para el hover-preview y el "ver fuente". El corpus SAT-Graph es compartido entre
despachos (público), pero la búsqueda SIEMPRE se acota a las jurisdicciones del
despacho (Decisión #25 — sin acotar habría fuga de autoridad cross-jurisdicción).

§G: respuesta en llano, sin jerga. FAIL-SOFT hacia lista vacía cuando el corpus no
tiene la fuente: el frontend lo traduce a "verifícala en la fuente oficial".
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request

from ...agents.research import _norm_reference, _ruling_reference, resolve_jurisdictions_for
from ...rag.sat_graph import SATGraph

router = APIRouter(prefix="/sources", tags=["sources"])
logger = logging.getLogger("mia.api.sources")

# Recorte del extracto que viaja a la pantalla: suficiente para leer el pasaje en el
# preview; el texto íntegro se consulta en la fuente oficial al radicar.
MAX_EXCERPT_CHARS = 700


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


def _clip(text: object, limit: int = MAX_EXCERPT_CHARS) -> str:
    s = str(text or "").strip()
    return s if len(s) <= limit else s[:limit].rstrip() + " […]"


def _iso(value: object) -> str | None:
    if value is None:
        return None
    iso = getattr(value, "isoformat", None)
    return iso() if callable(iso) else str(value)


def _display_ref(ref: str) -> str:
    """La referencia para PANTALLA: 'ley 80 de 1993' → 'Ley 80 de 1993' (el corpus
    guarda el tipo en minúscula; solo se embellece aquí, sin tocar el formato que
    usan los prompts y el verificador)."""
    ref = (ref or "").strip()
    return ref[:1].upper() + ref[1:] if ref else ref


@router.get("/buscar")
async def buscar_fuentes(
    request: Request,
    q: str = Query(min_length=3, max_length=300, description="Texto de la cita a buscar"),
):
    """Fuentes del corpus que hacen match con la cita (máx 3 normas + 3 providencias).

    Devuelve {"fuentes": [...]} — lista vacía si el corpus no la tiene (honesto: la
    pantalla dice "verifícala tú", nunca inventa un respaldo).
    """
    tid = _tenant(request)
    jurisdictions = await resolve_jurisdictions_for(tid)
    try:
        sat = SATGraph()
        norms = await sat.search_norms(q, limit=3, jurisdictions=jurisdictions)
        rulings = await sat.search_jurisprudence(q, limit=3, jurisdictions=jurisdictions)
    except Exception:  # noqa: BLE001
        logger.exception("buscar_fuentes falló (tenant=%s)", tid)
        raise HTTPException(
            status_code=502,
            detail="No pude consultar el corpus en este momento. Intenta de nuevo.",
        )

    fuentes: list[dict] = []
    for n in norms:
        fuentes.append({
            "tipo": "norma",
            "referencia": _display_ref(_norm_reference(n)),
            "titulo": _clip(n.get("title"), 200),
            "extracto": _clip(n.get("summary") or n.get("full_text")),
            "organo": str(n.get("issuing_body") or "").strip() or None,
            "fecha": _iso(n.get("effective_date")),
        })
    for r in rulings:
        organo = " · ".join(p for p in (str(r.get("court") or "").strip(),
                                        str(r.get("sala") or "").strip()) if p)
        fuentes.append({
            "tipo": "providencia",
            "referencia": _display_ref(_ruling_reference(r)),
            "titulo": _clip(r.get("topic"), 200),
            "extracto": _clip(r.get("ratio_decidendi") or r.get("obiter_dicta")),
            "organo": organo or None,
            "fecha": _iso(r.get("decision_date")),
            "radicado": str(r.get("radicado") or "").strip() or None,
            "magistrado_ponente": str(r.get("magistrado_ponente") or "").strip() or None,
        })
    return {"fuentes": fuentes}
