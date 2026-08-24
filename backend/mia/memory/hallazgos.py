"""Mia · memory.hallazgos — disposición de hallazgos del informe de verificación (AVISO).

Principio portado del harness de litigio de Lexia (`check-disposicion-hallazgos.py`,
caso ANI vs Coviandina 2026-08-19): un gate dejó la nota N5, nadie la cerró en ningún
sentido —ni corrigiéndola ni descartándola con razón— y el escrito se radicó así. El
hallazgo no lo ignoró nadie: murió en silencio porque ningún paso exigía dejar
constancia de qué se hizo con él.

La regla del harness: todo hallazgo se cierra con «corregido» y su evidencia, o con
«descartado» y quién lo decidió. La versión de Mia es la de AVISO ESTRICTO (regla de
implantación de Pipe: toda barrera nueva nace como aviso, nunca como muro):

  - Al aprobar un borrador en el checkpoint de revisión, se calcula qué hallazgos del
    informe de verificación (`metadata["verification"]`) quedaron SIN disposición y la
    lista viaja al recibo del ledger (`legal_ledger.record_gate`, gate="human_approval",
    evidence["hallazgos_sin_disposicion"]).
  - JAMÁS se bloquea el botón de aprobar ni se añade fricción a la pantalla: la
    aprobación del abogado ES una decisión válida; lo que esta barrera evita es que sea
    una decisión SIN CONSTANCIA. El recibo dice exactamente qué quedó abierto.
  - Si algún día la revisión de la pantalla envía disposiciones explícitas
    (decision["disposiciones"]), aquí ya se descuentan; hoy no existe ese control y por
    eso todo hallazgo abierto queda registrado como sin disposición.

Este módulo es PURO (sin DB, sin red, sin efectos): quien persiste es el nodo del grafo.
Fail-soft por diseño: cualquier informe malformado produce una lista vacía o parcial,
nunca una excepción que toque el flujo de aprobación.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

#: Estados de una cita del informe (`detalle[].estado`) que constituyen un hallazgo
#: abierto. Coincide con `barreras_harness.ESTADOS_DEFECTUOSOS` (decisión por rol, no
#: por texto): lo respaldado y lo sellado no es hallazgo.
_ESTADOS_ABIERTOS: frozenset = frozenset({"marcada", "anotada", "omitida", "quemada"})

#: Verbos que SÍ son disposición (mismo vocabulario que el harness). Cualquier otro
#: verbo no cierra nada.
_CORREGIDO = re.compile(r"(?i)\bcorregid[oa]\b")
_DESCARTADO = re.compile(r"(?i)\bdescartad[oa]\b")


def _norm(texto: Any) -> str:
    raw = str(texto or "")
    desc = unicodedata.normalize("NFD", raw)
    plano = "".join(ch for ch in desc if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", plano).strip().lower()


def clave_de(tipo: str, texto: Any) -> str:
    """Clave estable de UN hallazgo: tipo + primeros 120 chars normalizados del texto.

    Es lo que una disposición futura de la pantalla tendrá que citar para cubrirlo
    (mismo espíritu que la columna «cita del hallazgo» de DISPOSICIONES.md del harness).
    """
    return f"{tipo}:{_norm(texto)[:120]}"


def hallazgos_del_informe(report: Optional[dict]) -> list[dict]:
    """Extrae los hallazgos ABIERTOS de un informe de verificación.

    Devuelve [{"tipo", "hallazgo", "clave"}...]. Cubre:
      - citas con estado marcada/anotada/omitida/quemada (detalle, cap 50) y el
        remanente que el cap dejó fuera (los contadores del informe son la verdad);
      - referencias [doc n] fantasma (docs_fantasma);
      - afirmaciones negativas confrontadas que el documento completo contradice;
      - contaminación entre expedientes;
      - el veredicto con hallazgos del gate LLM (gate_llm).
    Un informe ausente o malformado devuelve [] — la barrera es aviso, no puede romper.
    """
    if not isinstance(report, dict):
        return []
    out: list[dict] = []

    # 1 · citas defectuosas del detalle
    vistos_por_estado: dict[str, int] = {}
    for entry in report.get("detalle") or []:
        if not isinstance(entry, dict):
            continue
        estado = str(entry.get("estado") or "")
        if estado in _ESTADOS_ABIERTOS:
            vistos_por_estado[estado] = vistos_por_estado.get(estado, 0) + 1
            cita = str(entry.get("cita") or "")[:200]
            out.append({"tipo": f"cita_{estado}", "hallazgo": cita,
                        "clave": clave_de(f"cita_{estado}", cita)})

    # 1b · el detalle tiene tope (50): si el contador del informe dice que hubo MÁS,
    # el remanente también es hallazgo — sin texto, pero con constancia del número.
    contadores = {"marcada": "marcadas", "anotada": "anotadas",
                  "omitida": "omitidas", "quemada": "quemadas"}
    for estado, clave_contador in contadores.items():
        try:
            total = int(report.get(clave_contador) or 0)
        except (TypeError, ValueError):
            total = 0
        resto = total - vistos_por_estado.get(estado, 0)
        if resto > 0:
            texto = f"{resto} cita(s) más en estado {estado} fuera del detalle del informe"
            out.append({"tipo": f"cita_{estado}", "hallazgo": texto,
                        "clave": clave_de(f"cita_{estado}", texto)})

    # 2 · [doc n] fantasma
    fantasma = report.get("docs_fantasma")
    if isinstance(fantasma, dict):
        try:
            n_fantasmas = int(fantasma.get("fantasmas") or 0)
        except (TypeError, ValueError):
            n_fantasmas = 0
        if n_fantasmas > 0:
            for d in (fantasma.get("detalle") or [])[:10]:
                if isinstance(d, dict) and d.get("fuera_de_rango"):
                    cita = str(d.get("cita") or "")[:200]
                    out.append({"tipo": "doc_fantasma", "hallazgo": cita,
                                "clave": clave_de("doc_fantasma", cita)})
            if not any(h["tipo"] == "doc_fantasma" for h in out):
                texto = f"{n_fantasmas} referencia(s) [doc n] fuera de rango"
                out.append({"tipo": "doc_fantasma", "hallazgo": texto,
                            "clave": clave_de("doc_fantasma", texto)})

    # 3 · afirmaciones negativas que el documento completo contradice
    neg = report.get("afirmaciones_negativas")
    if isinstance(neg, dict):
        for caso in (neg.get("revisar") or [])[:10]:
            if isinstance(caso, dict):
                oracion = str(caso.get("oracion") or "")[:200]
                out.append({"tipo": "afirmacion_negativa", "hallazgo": oracion,
                            "clave": clave_de("afirmacion_negativa", oracion)})

    # 4 · contaminación entre expedientes
    cruce = report.get("contaminacion_expediente")
    if isinstance(cruce, dict) and cruce:
        # Estructura defensiva: se toma lo que haya de identificable.
        partes = cruce.get("partes") or cruce.get("nombres") or cruce.get("detalle")
        if isinstance(partes, list) and partes:
            for p in partes[:10]:
                texto = str(p if not isinstance(p, dict)
                            else (p.get("nombre") or p.get("parte") or p))[:200]
                out.append({"tipo": "contaminacion_expediente", "hallazgo": texto,
                            "clave": clave_de("contaminacion_expediente", texto)})
        else:
            texto = str(cruce.get("aviso") or "posible nombre de otro asunto")[:200]
            out.append({"tipo": "contaminacion_expediente", "hallazgo": texto,
                        "clave": clave_de("contaminacion_expediente", texto)})

    # 5 · gate LLM con hallazgos
    gate = report.get("gate_llm")
    if isinstance(gate, dict) and gate.get("veredicto") == "hallazgos":
        texto = str(gate.get("detalle") or "el revisor independiente dejó hallazgos")[:200]
        out.append({"tipo": "gate_llm", "hallazgo": texto,
                    "clave": clave_de("gate_llm", texto)})

    return out


def _disposicion_valida(d: Any) -> bool:
    """«corregido» exige evidencia no vacía; «descartado» exige quién lo decidió.
    Cualquier otro verbo no es disposición (misma regla que el harness)."""
    if not isinstance(d, dict):
        return False
    verbo = str(d.get("disposicion") or "")
    respaldo = str(d.get("evidencia") or d.get("quien") or d.get("respaldo") or "").strip()
    if respaldo in {"", "—", "-"}:
        return False
    return bool(_CORREGIDO.search(verbo) or _DESCARTADO.search(verbo))


def pendientes_de_disposicion(report: Optional[dict],
                              disposiciones: Any = None) -> list[dict]:
    """Hallazgos del informe que quedaron SIN disposición válida.

    `disposiciones`: lo que la decisión de la pantalla traiga (hoy: nada). Se aceptan
    dos formas: dict {clave: {...}} o lista [{"clave", "disposicion", ...}]. Un
    hallazgo queda cubierto solo si su clave tiene una disposición VÁLIDA.

    Nunca lanza: informe raro → lista vacía o parcial. El resultado va al recibo del
    ledger como evidencia; no bloquea nada.
    """
    try:
        abiertos = hallazgos_del_informe(report)
        if not abiertos:
            return []
        cubiertos: set[str] = set()
        items: list[tuple[str, Any]] = []
        if isinstance(disposiciones, dict):
            items = [(str(k), v) for k, v in disposiciones.items()]
        elif isinstance(disposiciones, list):
            items = [(str(d.get("clave") or ""), d) for d in disposiciones
                     if isinstance(d, dict)]
        for clave, d in items:
            if clave and _disposicion_valida(d):
                cubiertos.add(clave)
        return [h for h in abiertos if h["clave"] not in cubiertos]
    except Exception:  # noqa: BLE001 — barrera de AVISO: jamás rompe la aprobación
        return []
