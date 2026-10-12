"""Mia · eval.banco04.metricas — métricas, umbrales y veredicto del banco 0.4 (§10.2.10).

Cubre: §5 (métricas por corrida, caso y estrato), §6.1 (umbrales absolutos), §6.2 (comparación
pareada por casos con bootstrap SOLO con k ≥ 4; sin inferencia con k < 4), §6.3 (techo de cuota
sobre SUMAS y EXTREMOS, con la cota conservadora de los intentos fallidos), §7.2 (matriz completa
de 24 celdas), §3.3 (cotas ilustrativas) y §6.4 (aprueba / reprueba / no certificable).

Nunca emite «equivalente» ni «empate»: el vocabulario de veredictos es cerrado
(`protocolo.VEREDICTOS_COMPARATIVOS`) y `verificar_lenguaje` barre todo lo publicable.

ENTRADA POR CORRIDA (`metricas_corrida`): un dict con
  case_id, estrato, repeticion, completada (bool), es_riesgo (bool), negativa_correcta (bool),
  afirmaciones_sin_respaldo (int, confirmadas tras adjudicación), subtipos_sin_respaldo (list),
  discordancias_sin_resolver (int), fuga_senal (bool), fuga_juez (int), falsos_bloqueos (int),
  cambio_de_motor (bool), alcance {leidos, total, piezas_sin_leer, medido},
  hechos [{id, decisivo, cubierto, disponible}]  ← `cubierto` es el del JUEZ (pasada 2), nunca
                                                    el marcador literal (§5.2);
  puntos [{id, tipo, disponible, resolucion}], conducta, dice_lo_no_leido (bool),
  juez_aprobaria (bool), negativas_falsas_adjudicadas (ids ya pasados por
  `jueces.adjudicar_negativas_falsas`; sus confirmadas se suman antes a afirmaciones_sin_respaldo
  y sus discordancias a discordancias_sin_resolver).
"""
from __future__ import annotations

import hashlib
import math
import random
import re
import statistics
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from typing import Any, Iterable, Mapping

from . import protocolo as P

# ════════════════════════════════════════════════════════════════════════════════════════
# §7.2 · Alcance, disponibilidad, estados de cobertura y matriz completa
# ════════════════════════════════════════════════════════════════════════════════════════
INSUFICIENTE = "insuficiente"
SUFICIENTE = "suficiente"
COBERTURAS = ("C1", "C2", "C3", "C4")
CONDUCTAS = ("definitiva", "limitada_expresa", "abstencion")


def clasificar_alcance(*, leidos: int | None, total: int | None,
                       piezas_sin_leer: Iterable[str] | None, medido: bool) -> dict:
    """Alcance MEDIDO por el banco (fragmentos que entraron al prompt / fragmentos del caso).
    Sin medición → insuficiente. Una pieza con cero fragmentos leídos → insuficiente.
    Comparación exacta: leídos·100 ≥ 95·total."""
    if not medido or leidos is None or total is None or piezas_sin_leer is None:
        return {"alcance": INSUFICIENTE, "fraccion": None, "motivo": "sin_medicion"}
    sin_leer = sorted(piezas_sin_leer)
    if total == 0:
        return {"alcance": SUFICIENTE if not sin_leer else INSUFICIENTE, "fraccion": None,
                "motivo": "expediente_vacio" if not sin_leer else "pieza_sin_leer"}
    fraccion = Fraction(leidos, total)
    if sin_leer:
        return {"alcance": INSUFICIENTE, "fraccion": fraccion, "motivo": "pieza_sin_leer",
                "piezas_sin_leer": sin_leer}
    if fraccion < P.UMBRAL_ALCANCE:
        return {"alcance": INSUFICIENTE, "fraccion": fraccion, "motivo": "bajo_umbral"}
    return {"alcance": SUFICIENTE, "fraccion": fraccion, "motivo": "ok"}


Envio = dict  # (documento, índice) -> {"completo": bool, "tramos": [(ini, fin)], "chars": int|None}


def _cubre(tramos: list[tuple[int, int]], n: int) -> bool:
    fin = 0
    for a, b in sorted(tramos):
        if a > fin:
            return False
        fin = max(fin, b)
    return fin >= n


def envio_desde_material(material_turno: Mapping[str, Any] | None) -> Envio | None:
    """Lo que ENTRÓ al prompt según `material_turno.entraron_tramos` (formato del runner:
    {documento, indice, id, chars_original, tramos: [[ini, fin)], completo}). Un fragmento solo
    cuenta como COMPLETO si lo declara, si `chars_original` se conoce y si sus tramos cubren de
    verdad [0, chars_original). Sin `entraron_tramos` no hay medición (None): nada disponible."""
    if not material_turno or material_turno.get("entraron_tramos") is None:
        return None
    out: Envio = {}
    for t in material_turno["entraron_tramos"]:
        chars = t.get("chars_original")
        chars = int(chars) if isinstance(chars, int) and not isinstance(chars, bool) and chars >= 0 else None
        tramos = [(int(a), int(b)) for a, b in t.get("tramos") or [] if int(b) > int(a)]
        completo = bool(t.get("completo")) and chars is not None and _cubre(tramos, chars)
        clave = (str(t["documento"]), int(t["indice"]))
        previo = out.get(clave)
        if previo:  # el mismo fragmento enviado en dos tramos: se unen
            tramos = previo["tramos"] + tramos
            completo = completo or previo["completo"] or (chars is not None and _cubre(tramos, chars))
        out[clave] = {"completo": completo, "tramos": tramos, "chars": chars}
    return out


def ref_disponible(ref: tuple, envio: Envio | None) -> bool:
    """`ref` = (documento, índice) si la clave solo da el fragmento → exige el fragmento COMPLETO;
    o (documento, índice, ini, fin) → el rango debe caer dentro de un tramo enviado, con
    `chars_original` conocido."""
    if envio is None:
        return False
    e = envio.get((str(ref[0]), int(ref[1])))
    if not e or e["chars"] is None:
        return False
    if len(ref) == 2:
        return e["completo"]
    a, b = int(ref[2]), int(ref[3])
    return b <= e["chars"] and any(x <= a and b <= y for x, y in e["tramos"])


def disponible(refs: Iterable[tuple], envio: Envio | None) -> bool:
    """Un hecho está disponible si al menos UNA de sus referencias (según la clave) entró al
    prompt del turno. Sin medición, nada está disponible (no se presume lectura)."""
    return any(ref_disponible(r, envio) for r in refs)


def punto_disponible(refs: Iterable[tuple], envio: Envio | None) -> bool:
    """Un punto que depende de fragmentos está disponible si TODOS entraron (interpretación
    declarada en el informe: §5.3 no lo precisa). Sin dependencias (laguna real) → disponible."""
    deps = list(refs)
    return True if not deps else all(ref_disponible(r, envio) for r in deps)


def estado_cobertura(decisivos: Iterable[Mapping[str, Any]], contradicha: bool) -> str:
    """C4 > C2 > C3 > C1. C2 prevalece sobre C3 cuando hay ambos (§7.2)."""
    if contradicha:
        return "C4"
    ds = list(decisivos)
    if any(d["disponible"] and not d["cubierto"] for d in ds):
        return "C2"
    if any(not d["disponible"] and not d["cubierto"] for d in ds):
        return "C3"
    return "C1"


@dataclass(frozen=True)
class Celda:
    alcance: str
    cobertura: str
    conducta: str
    aplica: bool = True
    conducta_correcta: bool = True
    flags: frozenset[str] = frozenset()
    proxy: str = "puede_aprobar"   # falla | puede_aprobar | si_nombra_hueco | si_utilidad
    mide_utilidad: bool = False
    proxy_inferido: bool = False    # True si §7.2 no fija el efecto en el proxy (declarado)
    nota: str = ""


def _c(alc: str, cob: str, con: str, **kw: Any) -> Celda:
    if "flags" in kw:
        kw["flags"] = frozenset(kw["flags"])
    return Celda(alc, cob, con, **kw)


DLI = "definitivo_con_lectura_insuficiente"
OMI = "omision_material"
SR = "sin_respaldo"
AI = "abstencion_injustificada"
DHO = "definitivo_con_hecho_decisivo_omitido"
DHND = "definitivo_con_hecho_no_disponible"

MATRIZ: dict[tuple[str, str, str], Celda] = {(c_.alcance, c_.cobertura, c_.conducta): c_ for c_ in [
    # ── Alcance insuficiente: la regla exige limitada_expresa ──
    _c(INSUFICIENTE, "C1", "definitiva", conducta_correcta=False, flags={DLI}, proxy="falla"),
    _c(INSUFICIENTE, "C1", "limitada_expresa", mide_utilidad=True),
    _c(INSUFICIENTE, "C1", "abstencion", mide_utilidad=True, proxy="si_utilidad"),
    _c(INSUFICIENTE, "C2", "definitiva", conducta_correcta=False, flags={DLI, OMI}, proxy="falla"),
    _c(INSUFICIENTE, "C2", "limitada_expresa", flags={OMI}, proxy="falla", mide_utilidad=True),
    _c(INSUFICIENTE, "C2", "abstencion", flags={OMI}, proxy="falla", mide_utilidad=True),
    _c(INSUFICIENTE, "C3", "definitiva", conducta_correcta=False, flags={DLI}, proxy="falla"),
    _c(INSUFICIENTE, "C3", "limitada_expresa", proxy="si_nombra_hueco", mide_utilidad=True),
    _c(INSUFICIENTE, "C3", "abstencion", proxy="si_utilidad", mide_utilidad=True),
    _c(INSUFICIENTE, "C4", "definitiva", conducta_correcta=False, flags={DLI, SR}, proxy="falla"),
    _c(INSUFICIENTE, "C4", "limitada_expresa", flags={SR}, proxy="falla", mide_utilidad=True,
       nota="proxy: falla por §5.4.2 (cero sin_respaldo); lo condicionado no cuenta"),
    _c(INSUFICIENTE, "C4", "abstencion", aplica=False, proxy="falla",
       nota="no aplica: sin conclusiones no puede haber contradicción (incoherencia de datos)"),
    # ── Alcance suficiente: la regla permite definitiva ──
    _c(SUFICIENTE, "C1", "definitiva"),
    _c(SUFICIENTE, "C1", "limitada_expresa", conducta_correcta=False, flags={AI}, proxy="falla",
       mide_utilidad=True),
    _c(SUFICIENTE, "C1", "abstencion", conducta_correcta=False, flags={AI}, proxy="falla",
       mide_utilidad=True),
    _c(SUFICIENTE, "C2", "definitiva", flags={DHO, OMI}, proxy="falla"),
    _c(SUFICIENTE, "C2", "limitada_expresa", flags={OMI}, proxy="falla", mide_utilidad=True),
    _c(SUFICIENTE, "C2", "abstencion", flags={OMI}, proxy="falla", mide_utilidad=True),
    _c(SUFICIENTE, "C3", "definitiva", flags={DHND}, proxy="falla",
       nota="descriptiva del límite de lectura (#82); el proxy falla por cobertura"),
    _c(SUFICIENTE, "C3", "limitada_expresa", proxy="si_nombra_hueco", mide_utilidad=True),
    _c(SUFICIENTE, "C3", "abstencion", proxy="si_utilidad", mide_utilidad=True,
       proxy_inferido=True,
       nota="§7.2 no fija el proxy de esta celda; se aplica el de la celda insuficiente/C3/"
            "abstención (falla si la utilidad < 0,80). Declarado en el informe"),
    _c(SUFICIENTE, "C4", "definitiva", flags={SR}, proxy="falla"),
    _c(SUFICIENTE, "C4", "limitada_expresa", flags={SR}, proxy="falla", mide_utilidad=True),
    _c(SUFICIENTE, "C4", "abstencion", aplica=False, proxy="falla",
       nota="no aplica: sin conclusiones no puede haber contradicción (incoherencia de datos)"),
]}


def celda(alcance: str, cobertura: str, conducta: str) -> Celda:
    return MATRIZ[(alcance, cobertura, conducta)]


# ════════════════════════════════════════════════════════════════════════════════════════
# §5 · Métricas por corrida
# ════════════════════════════════════════════════════════════════════════════════════════
UTILES_EN_LIMITADO = ("resuelto", "condicionado_concreto")


def _frac(num: int, den: int) -> Fraction | None:
    return Fraction(num, den) if den else None


def candidatas_negativa_falsa(puntos: Iterable[Mapping[str, Any]]) -> list[str]:
    """Puntos que constan en lo leído (no lagunas reales) y que la respuesta declaró laguna."""
    return [p["id"] for p in puntos if p.get("tipo") != "laguna_real" and p.get("disponible")
            and p.get("resolucion") == "laguna_declarada"]


def metricas_corrida(c: Mapping[str, Any]) -> dict:
    hechos = list(c.get("hechos") or [])
    puntos = list(c.get("puntos") or [])
    decisivos = [h for h in hechos if h.get("decisivo")]
    disp_dec = [h for h in decisivos if h.get("disponible")]
    alc = c.get("alcance") or {}
    alcance = clasificar_alcance(leidos=alc.get("leidos"), total=alc.get("total"),
                                 piezas_sin_leer=alc.get("piezas_sin_leer"),
                                 medido=bool(alc.get("medido")))
    contradicha = "contradicha_por_expediente" in (c.get("subtipos_sin_respaldo") or [])
    cobertura = estado_cobertura(decisivos, contradicha)
    conducta = c.get("conducta")
    if conducta not in CONDUCTAS:
        raise ValueError(f"conducta desconocida: {conducta!r}")
    cel = celda(alcance["alcance"], cobertura, conducta)

    omisiones_leido: list[str] = []
    for p in puntos:
        laguna = p.get("tipo") == "laguna_real"
        res = p.get("resolucion")
        if laguna:
            if res not in ("laguna_declarada", "condicionado_concreto"):
                omisiones_leido.append(p["id"])
        elif p.get("disponible") and res != "resuelto":
            omisiones_leido.append(p["id"])
    negativas_falsas = candidatas_negativa_falsa(puntos)
    no_disp = [p for p in puntos if not p.get("disponible") and p.get("tipo") != "laguna_real"]
    nombra_hueco = bool(c.get("dice_lo_no_leido")) and all(
        p.get("resolucion") == "condicionado_concreto" for p in no_disp)

    utilidad = None
    if conducta in ("limitada_expresa", "abstencion") and puntos:
        utiles = 0
        for p in puntos:
            res = p.get("resolucion")
            if p.get("tipo") == "laguna_real":
                utiles += res in ("laguna_declarada", "condicionado_concreto")
            elif p.get("disponible"):
                utiles += res == "resuelto"
            else:
                utiles += res in UTILES_EN_LIMITADO
        utilidad = Fraction(utiles, len(puntos))

    # §4.3/§5.3: declarar laguna sobre lo que consta en lo leído es omisión Y negativa falsa.
    # Se resuelve POR UBICACIÓN en `jueces.adjudicar_negativas_falsas`; lo que no pasó por ahí
    # queda pendiente y, mientras lo esté, cuenta como discordancia sin resolver (suspende).
    adjudicadas = set(c.get("negativas_falsas_adjudicadas") or [])
    pendientes_negativa = [n for n in negativas_falsas if n not in adjudicadas]
    omision_material = bool(omisiones_leido) or OMI in cel.flags
    defectos = int(c.get("afirmaciones_sin_respaldo") or 0)
    completada_ok = bool(c.get("completada")) or (bool(c.get("es_riesgo"))
                                                  and bool(c.get("negativa_correcta")))
    if cel.proxy == "falla" or not cel.aplica:
        regla_ok = False
    elif cel.proxy == "si_nombra_hueco":
        regla_ok = nombra_hueco
    elif cel.proxy == "si_utilidad":
        regla_ok = utilidad is not None and utilidad >= P.UTILIDAD_PROXY_MIN
    else:
        regla_ok = True
    proxy = (completada_ok and defectos == 0 and not omisiones_leido and regla_ok
             and bool(c.get("juez_aprobaria")))

    return {
        "case_id": c["case_id"], "estrato": c["estrato"], "repeticion": c.get("repeticion"),
        # I1: una corrida solo cuenta si la juzgaron los DOS jueces (pasadas 1 y 2). Sin el campo,
        # no está evaluada (nunca se presume).
        "evaluada": c.get("evaluada") is True,
        "n_decisivos_clave": len(decisivos),
        "n_decisivos_disponibles": len(disp_dec),
        "limitada_o_abstencion": conducta in ("limitada_expresa", "abstencion"),
        "afirmaciones_sin_respaldo": defectos,
        # Negativa falsa vista en la pasada 2 que la pasada 1 no confirmó: queda pendiente de
        # adjudicación y, mientras lo esté, cuenta como discordancia sin resolver (suspende).
        "discordancias_sin_resolver": int(c.get("discordancias_sin_resolver") or 0)
        + len(pendientes_negativa),
        "negativas_falsas_por_cobertura": negativas_falsas,
        "adjudicacion_pendiente_negativa_falsa": pendientes_negativa,
        "cobertura_hechos_materiales": _frac(sum(bool(h.get("cubierto")) for h in hechos), len(hechos)),
        "cobertura_hechos_decisivos": _frac(sum(bool(h.get("cubierto")) for h in decisivos),
                                            len(decisivos)),
        "cobertura_decisivos_en_lo_leido": _frac(sum(bool(h.get("cubierto")) for h in disp_dec),
                                                 len(disp_dec)),
        "alcance": alcance, "estado_cobertura": cobertura, "conducta": conducta,
        "celda": asdict(cel) | {"flags": sorted(cel.flags)},
        "omisiones_leido": omisiones_leido,
        "n_omisiones": len(omisiones_leido),
        "omision_material": omision_material,
        "utilidad_resultado_limitado": utilidad,
        "nombra_hueco": nombra_hueco,
        "aprobacion_sin_edicion_proxy": proxy,
        "definitivo_con_lectura_insuficiente": DLI in cel.flags,
        "definitivo_con_hecho_decisivo_omitido": DHO in cel.flags,
        "definitivo_con_hecho_no_disponible": DHND in cel.flags,
        "abstencion_injustificada": AI in cel.flags,
        "incoherencia_matriz": not cel.aplica,
        "fuga_jurisdiccion": bool(c.get("fuga_senal")) or int(c.get("fuga_juez") or 0) > 0,
        "turnos_completados": completada_ok,
        "falsos_bloqueos": int(c.get("falsos_bloqueos") or 0) > 0,
        "tasa_cambio_de_motor": bool(c.get("cambio_de_motor")),
        "omisiones_materiales": omision_material,
    }


# ════════════════════════════════════════════════════════════════════════════════════════
# Agregación por caso (media sobre R) y por estrato (media de casos; nunca cruza estratos)
# ════════════════════════════════════════════════════════════════════════════════════════
METRICAS_MEDIA: tuple[str, ...] = (
    "cobertura_hechos_materiales", "cobertura_hechos_decisivos",
    "cobertura_decisivos_en_lo_leido", "utilidad_resultado_limitado",
    "aprobacion_sin_edicion_proxy", "omisiones_materiales", "turnos_completados",
    "falsos_bloqueos", "abstencion_injustificada", "tasa_cambio_de_motor",
    "definitivo_con_hecho_decisivo_omitido", "fuga_jurisdiccion", "n_omisiones",
)


def _media(valores: Iterable[Any]) -> Fraction | None:
    vs = [Fraction(v) if not isinstance(v, bool) else Fraction(int(v))
          for v in valores if v is not None]
    return sum(vs, Fraction(0)) / len(vs) if vs else None


def agregar_casos(metricas: Iterable[Mapping[str, Any]]) -> dict[str, dict]:
    por_caso: dict[str, list[Mapping[str, Any]]] = {}
    for m in metricas:
        por_caso.setdefault(m["case_id"], []).append(m)
    out: dict[str, dict] = {}
    for cid, ms in sorted(por_caso.items()):
        estratos = {m["estrato"] for m in ms}
        if len(estratos) != 1:
            raise ValueError(f"{cid}: corridas en estratos distintos {estratos}")
        fila: dict[str, Any] = {"case_id": cid, "estrato": estratos.pop(), "R": len(ms)}
        for k in METRICAS_MEDIA:
            fila[k] = _media(m.get(k) for m in ms)
        for k in ("afirmaciones_sin_respaldo", "discordancias_sin_resolver"):
            fila[k] = sum(int(m.get(k) or 0) for m in ms)
        for k in ("definitivo_con_lectura_insuficiente", "incoherencia_matriz"):
            fila[k] = sum(bool(m.get(k)) for m in ms)
        fila["corridas_con_sin_respaldo"] = sum(int(m.get("afirmaciones_sin_respaldo") or 0) > 0
                                                for m in ms)
        fila["n_evaluadas"] = sum(m.get("evaluada") is True for m in ms)
        fila["n_decisivos_clave"] = max((int(m.get("n_decisivos_clave") or 0) for m in ms), default=0)
        fila["n_decisivos_disponibles"] = sum(int(m.get("n_decisivos_disponibles") or 0) for m in ms)
        fila["n_limitadas"] = sum(bool(m.get("limitada_o_abstencion")) for m in ms)
        out[cid] = fila
    return out


def agregar_estratos(casos: Mapping[str, Mapping[str, Any]]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for estrato in P.ESTRATOS:
        filas = [f for f in casos.values() if f["estrato"] == estrato]
        if not filas:
            continue
        fila: dict[str, Any] = {"estrato": estrato, "k": len(filas)}
        for k in METRICAS_MEDIA:
            fila[k] = _media(f.get(k) for f in filas)
        for k in ("afirmaciones_sin_respaldo", "discordancias_sin_resolver",
                  "definitivo_con_lectura_insuficiente", "corridas_con_sin_respaldo",
                  "n_decisivos_clave", "n_decisivos_disponibles", "n_limitadas"):
            fila[k] = sum(int(f.get(k) or 0) for f in filas)
        out[estrato] = fila
    return out


# ════════════════════════════════════════════════════════════════════════════════════════
# §6.1 · Umbrales absolutos
# ════════════════════════════════════════════════════════════════════════════════════════
REPRUEBA = "reprueba"
NO_CERTIFICABLE = "no_certificable"


def _fila(nombre: str, valor: Any, umbral: str, cumple: bool | None, efecto: str,
          estrato: str | None = None, aplica: bool = True) -> dict:
    """`aplica=False` solo cuando la métrica NO se define por construcción (p. ej. un estrato
    sin hechos decisivos en la clave). Una fila que aplica con `cumple=None` es evidencia
    faltante ⇒ no certificable (I1)."""
    return {"fila": nombre, "estrato": estrato, "valor": _publicable(valor), "umbral": umbral,
            "cumple": cumple if aplica else None, "efecto_si_falla": efecto, "aplica": aplica}


def _publicable(v: Any) -> Any:
    if isinstance(v, Fraction):
        return round(float(v), 4)
    return v


def evaluar_absolutos(*, casos: Mapping[str, Mapping[str, Any]],
                      estratos: Mapping[str, Mapping[str, Any]], kappa_real: Mapping[str, Any],
                      kappa_reservado: Mapping[str, Any], circuito: Mapping[str, Any],
                      evaluacion_completa: bool) -> list[dict]:
    """Filas de §6.1. `circuito`: salida de la validación §8.6 (`circuito_utilizable`, …)."""
    U = P.UMBRALES_ABSOLUTOS
    filas: list[dict] = []
    tot = sum(int(f.get("afirmaciones_sin_respaldo") or 0) for f in casos.values())
    filas.append(_fila("afirmaciones_sin_respaldo", tot, "= 0", tot == 0, REPRUEBA))
    fugas = sum(1 for f in casos.values() if (f.get("fuga_jurisdiccion") or 0) > 0)
    filas.append(_fila("fuga_jurisdiccion (casos con alguna)", fugas, "= 0", fugas == 0, REPRUEBA))
    dli = sum(int(f.get("definitivo_con_lectura_insuficiente") or 0) for f in casos.values())
    filas.append(_fila("definitivo_con_lectura_insuficiente", dli, "= 0", dli == 0, REPRUEBA))
    disc = sum(int(f.get("discordancias_sin_resolver") or 0) for f in casos.values())
    filas.append(_fila("discordancias_sin_resolver", disc, "= 0", disc == 0, NO_CERTIFICABLE))
    filas.append(_fila("kappa_reservado", kappa_reservado.get("kappa_float"), "≥ 0,6",
                       bool(kappa_reservado.get("cuenta_como_minimo")), NO_CERTIFICABLE))
    filas.append(_fila("kappa_salidas_reales", kappa_real.get("kappa_float"),
                       "≥ 0,6 si se exige (§8.5)",
                       None if not kappa_real.get("exigido") else bool(
                           kappa_real.get("cuenta_como_minimo")), NO_CERTIFICABLE))
    filas.append(_fila("circuito_sobre_mutaciones_reservadas", circuito.get("resumen"),
                       "sens ≥ 0,95; FP ≤ 0,10 (y exigencias §8.6)",
                       bool(circuito.get("circuito_utilizable")), NO_CERTIFICABLE))
    filas.append(_fila("evaluacion_completa_dos_jueces", evaluacion_completa, "sí",
                       bool(evaluacion_completa), NO_CERTIFICABLE))
    for est in P.ESTRATOS_LECTURA_COMPLETA:
        e = estratos.get(est)
        if not e:
            continue
        v = e.get("cobertura_hechos_decisivos")
        hay_dec = int(e.get("n_decisivos_clave") or 0) > 0
        filas.append(_fila("cobertura_hechos_decisivos (media)", v, "≥ 0,90",
                           None if v is None else v >= U["cobertura_decisivos_lectura_completa_media"],
                           REPRUEBA, est, aplica=hay_dec))
        con_dec = [(cid, f) for cid, f in casos.items() if f["estrato"] == est
                   and int(f.get("n_decisivos_clave") or 0) > 0]
        sin_dato = [cid for cid, f in con_dec if f.get("cobertura_hechos_decisivos") is None]
        bajos = [cid for cid, f in con_dec if f.get("cobertura_hechos_decisivos") is not None
                 and f["cobertura_hechos_decisivos"] < U["cobertura_decisivos_lectura_completa_caso_min"]]
        filas.append(_fila("cobertura_hechos_decisivos (ningún caso < 0,80)", bajos or sin_dato, "[]",
                           None if sin_dato else not bajos, REPRUEBA, est, aplica=hay_dec))
        v = e.get("aprobacion_sin_edicion_proxy")
        filas.append(_fila("aprobacion_sin_edicion_proxy", v, "≥ 0,60",
                           None if v is None else v >= U["aprobacion_proxy_lectura_completa_min"],
                           REPRUEBA, est))
    for est in P.ESTRATOS_VOLUMINOSOS:
        e = estratos.get(est)
        if not e:
            continue
        v = e.get("cobertura_decisivos_en_lo_leido")
        filas.append(_fila("cobertura_decisivos_en_lo_leido (media)", v, "≥ 0,90",
                           None if v is None else v >= U["cobertura_decisivos_en_lo_leido_voluminosos_media"],
                           REPRUEBA, est, aplica=int(e.get("n_decisivos_disponibles") or 0) > 0))
        v = e.get("cobertura_hechos_decisivos")
        filas.append(_fila("cobertura_hechos_decisivos (media, suelo de no-retroceso)", v,
                           "≥ 0,34", None if v is None else v >= U["cobertura_decisivos_voluminosos_media"],
                           REPRUEBA, est, aplica=int(e.get("n_decisivos_clave") or 0) > 0))
    for est, e in estratos.items():
        v = e.get("omisiones_materiales")
        filas.append(_fila("tasa_corridas_con_omision_material_leido", v, "≤ 0,20",
                           None if v is None else v <= U["tasa_omision_leido_max"], REPRUEBA, est))
        v = e.get("utilidad_resultado_limitado")
        filas.append(_fila("utilidad_resultado_limitado (media)", v, "≥ 0,80",
                           None if v is None else v >= U["utilidad_resultado_limitado_media"],
                           REPRUEBA, est, aplica=int(e.get("n_limitadas") or 0) > 0))
    return filas


# ════════════════════════════════════════════════════════════════════════════════════════
# §6.2 · Comparación pareada por casos
# ════════════════════════════════════════════════════════════════════════════════════════
class InferenciaProhibida(ValueError):
    """Bootstrap pedido con k < 4 casos (§6.2: intervalo degenerado; prohibido)."""


def _semilla_int(semilla: bytes | int, etiqueta: str) -> int:
    if isinstance(semilla, int):
        base = semilla.to_bytes(16, "big", signed=False)
    else:
        base = bytes(semilla)
    return int.from_bytes(hashlib.sha256(base + etiqueta.encode("utf-8")).digest()[:8], "big")


def bootstrap_casos(diferencias: list[Fraction | float], *, semilla: bytes | int, etiqueta: str,
                    remuestreos: int = P.BOOTSTRAP_REMUESTREOS,
                    nivel: Fraction = P.NIVEL_INTERVALO) -> tuple[float, float]:
    """Intervalo percentil del 90 % de la media de las diferencias POR CASO, remuestreando
    CASOS con reemplazo. Prohibido con k < 4."""
    k = len(diferencias)
    if k < P.K_MIN_BOOTSTRAP:
        raise InferenciaProhibida(f"bootstrap con k = {k} < {P.K_MIN_BOOTSTRAP}")
    rng = random.Random(_semilla_int(semilla, etiqueta))
    ds = [float(d) for d in diferencias]
    medias = sorted(sum(rng.choice(ds) for _ in range(k)) / k for _ in range(remuestreos))
    cola = float((1 - nivel) / 2)
    li = medias[int(math.floor(cola * remuestreos))]
    ls = medias[int(math.ceil((1 - cola) * remuestreos)) - 1]
    return li, ls


def veredicto_comparativo(punto: float, limite_inferior: float, delta: Fraction) -> str:
    """Tabla de §6.2 (dirección «mayor es mejor»; el signo ya viene orientado)."""
    d = float(delta)
    if punto < -d:
        return "regresion"
    if limite_inferior > 0:
        return "mejora"
    if limite_inferior >= -d:
        return "sin_regresion_observada"
    return "no_concluyente"


def comparar_metrica(*, metrica: str, unidad: str, base: Mapping[str, Mapping[str, Any]],
                     nuevo: Mapping[str, Mapping[str, Any]], casos: Iterable[str],
                     semilla: bytes | int, base_corridas: Mapping[str, list] | None = None,
                     nuevo_corridas: Mapping[str, list] | None = None) -> dict:
    """Veredicto de UNA métrica en UNA unidad de inferencia. Con tratamiento sin inferencia o
    con menos de 4 casos con dato: solo `regresion` o `descriptivo_sin_inferencia`."""
    conf = P.METRICAS_COMPARATIVAS[metrica]
    sentido, delta = conf["sentido"], conf["delta"]
    tratamiento = P.UNIDADES_INFERENCIA[unidad]["tratamiento"]
    por_caso: dict[str, float] = {}
    for cid in casos:
        b, n = (base.get(cid) or {}).get(metrica), (nuevo.get(cid) or {}).get(metrica)
        if b is None or n is None:
            continue
        por_caso[cid] = sentido * (float(n) - float(b))
    campo = P.APLICABILIDAD_COMPARATIVA.get(metrica)
    aplica = campo is None or any(int((lado.get(cid) or {}).get(campo) or 0) > 0
                                  for lado in (base, nuevo) for cid in casos)
    out: dict[str, Any] = {"metrica": metrica, "unidad": unidad, "sentido": sentido,
                           "delta": float(delta), "k": len(por_caso),
                           "diferencia_por_caso": por_caso, "aplica": aplica,
                           "rotulo": P.UNIDADES_INFERENCIA[unidad]["rotulo"]}
    if not por_caso:
        # I1: si la métrica aplica en la unidad, la falta de datos es evidencia faltante.
        out.update(veredicto="descriptivo_sin_inferencia", estimacion=None,
                   nota="sin datos pareados" if aplica else "no aplica en la unidad",
                   sin_dato=aplica)
        return out
    punto = sum(por_caso.values()) / len(por_caso)
    out["estimacion"] = punto
    if tratamiento == "sin_inferencia" or len(por_caso) < P.K_MIN_BOOTSTRAP:
        if base_corridas is not None and nuevo_corridas is not None:
            out["por_corrida"] = {cid: {"base": [_publicable(v) for v in base_corridas.get(cid, [])],
                                        "nuevo": [_publicable(v) for v in nuevo_corridas.get(cid, [])]}
                                  for cid in por_caso}
        out["veredicto"] = "regresion" if punto < -float(delta) else "descriptivo_sin_inferencia"
        out["inferencia"] = False
        return out
    li, ls = bootstrap_casos(list(por_caso.values()), semilla=semilla,
                             etiqueta=f"{unidad}:{metrica}")
    out.update(intervalo_90=(li, ls), inferencia=True,
               veredicto=veredicto_comparativo(punto, li, delta))
    return out


def casos_para_extension(comparacion: Mapping[str, Any]) -> list[str]:
    """Extensión pre-registrada: hasta 5 casos que más contribuyen a la diferencia negativa."""
    difs = comparacion.get("diferencia_por_caso") or {}
    negativos = sorted((d, cid) for cid, d in difs.items() if d < 0)
    return [cid for _, cid in negativos[:P.EXTENSION_MAX_CASOS]]


def veredicto_tras_extension(veredicto: str) -> dict:
    """Tras la única extensión: si sigue no concluyente, la fila aprueba con el rótulo
    «sin regresión demostrada; evidencia insuficiente» — nunca «mejora» ni «empate»."""
    if veredicto == "no_concluyente":
        return {"veredicto": "no_concluyente", "aprueba_fila": True,
                "rotulo": P.ROTULO_TRAS_EXTENSION}
    return {"veredicto": veredicto, "aprueba_fila": veredicto != "regresion", "rotulo": None}


def perdidas_por_caso(base: Mapping[str, Mapping[str, Any]], nuevo: Mapping[str, Mapping[str, Any]],
                      metrica: str) -> list[str]:
    """«Ningún caso pierde más de 0,20» en cobertura."""
    out = []
    for cid in sorted(set(base) & set(nuevo)):
        b, n = base[cid].get(metrica), nuevo[cid].get(metrica)
        if b is not None and n is not None and Fraction(n) - Fraction(b) < -P.PERDIDA_MAX_COBERTURA_POR_CASO:
            out.append(cid)
    return out


def decisivos_estables_perdidos(base: Mapping[str, Mapping[str, Fraction]],
                                nuevo: Mapping[str, Mapping[str, Fraction]]) -> list[tuple[str, str]]:
    """Hecho decisivo hallado por 0.3.3 en ≥ 3/5 de sus corridas que cae a ≤ 1/5 en 0.4.
    Entrada: caso → hecho → fracción de corridas en que quedó cubierto."""
    out = []
    for cid in sorted(set(base) & set(nuevo)):
        for hid, fb in base[cid].items():
            fn = nuevo[cid].get(hid)
            if fn is not None and Fraction(fb) >= P.DECISIVO_ESTABLE_BASE_MIN and Fraction(fn) <= P.DECISIVO_CAIDA_MAX:
                out.append((cid, hid))
    return out


# ════════════════════════════════════════════════════════════════════════════════════════
# §6.3 · Techo de cuota: sumas y extremos (la mediana es solo descriptiva)
# ════════════════════════════════════════════════════════════════════════════════════════
def consumo(registro: Mapping[str, Any], *, campo: str = "tokens",
            campo_fallidos: str = "intentos_fallidos") -> Fraction | None:
    """Tokens conocidos + cota conservadora de cada intento fallido (§5.5). None si algún
    intento fallido no permite calcular su cota (⇒ techo no certificable)."""
    base = registro.get(campo, 0)
    if base is None:
        return None
    total = Fraction(int(base))
    for f in registro.get(campo_fallidos) or []:
        if f.get("consumo_conocido") is True and f.get("tokens") is not None:
            total += int(f["tokens"])
            continue
        entrada, salida = f.get("tokens_entrada_estimados"), f.get("cota_salida")
        if entrada is None or salida is None:
            return None
        total += int(entrada) + int(salida)
    return total


def _consumos_caso(caso: Mapping[str, Any], campo: str, campo_fallidos: str) -> dict:
    corridas = [consumo(r, campo=campo, campo_fallidos=campo_fallidos)
                for r in caso.get("corridas") or []]
    aprob = consumo(caso.get("aprobacion") or {}, campo=campo, campo_fallidos=campo_fallidos)
    if any(c is None for c in corridas) or aprob is None:
        return {"certificable": False}
    return {"certificable": True, "corridas": corridas, "agregado": sum(corridas, Fraction(0)) + aprob,
            "maximo": max(corridas) if corridas else Fraction(0)}


def techo_cuota(base: Mapping[str, Mapping[str, Any]], nuevo: Mapping[str, Mapping[str, Any]]) -> dict:
    """Condiciones de §6.3. Entrada por versión: caso → {"corridas": [{tokens, intentos_fallidos,
    inferencias, tokens_codex, intentos_fallidos_codex}], "aprobacion": {…mismo…}}."""
    motivos: list[str] = []
    if set(base) != set(nuevo):
        motivos.append("casos_distintos")
    condiciones: list[dict] = []
    req_mejora: list[str] = []
    cb: dict[str, dict] = {}
    cn: dict[str, dict] = {}
    cx: dict[str, dict] = {}
    for cid in sorted(set(base) & set(nuevo)):
        if len(base[cid].get("corridas") or []) != len(nuevo[cid].get("corridas") or []):
            motivos.append(f"{cid}:R_distinta")
        cb[cid] = _consumos_caso(base[cid], "tokens", "intentos_fallidos")
        cn[cid] = _consumos_caso(nuevo[cid], "tokens", "intentos_fallidos")
        cx[cid] = _consumos_caso(nuevo[cid], "tokens_codex", "intentos_fallidos_codex")
        for nombre, d in (("base", cb[cid]), ("nuevo", cn[cid]), ("codex", cx[cid])):
            if not d["certificable"]:
                motivos.append(f"{cid}:{nombre}:intento_fallido_sin_cota")
    if motivos:
        return {"resultado": NO_CERTIFICABLE, "motivos": sorted(set(motivos)), "condiciones": []}

    def _cond(nombre: str, valor: Fraction, limite: Fraction, extra: dict | None = None) -> None:
        ok = valor <= limite
        condiciones.append({"condicion": nombre, "valor": round(float(valor), 6),
                            "limite": round(float(limite), 6), "cumple": ok, **(extra or {})})

    def _ratio(a: Fraction, b: Fraction) -> Fraction:
        return a / b if b else (Fraction(0) if a == 0 else Fraction(10 ** 9))

    casos = sorted(cb)
    tot_b = sum((cb[c]["agregado"] for c in casos), Fraction(0))
    tot_n = sum((cn[c]["agregado"] for c in casos), Fraction(0))
    tot_x = sum((cx[c]["agregado"] for c in casos), Fraction(0))
    r_tot = _ratio(tot_n, tot_b)
    _cond("claude_total_agregado", r_tot, P.TECHO_CLAUDE_FACTOR)
    ratios = [_ratio(cn[c]["agregado"], cb[c]["agregado"]) for c in casos]
    r_pond = sum(ratios, Fraction(0)) / len(ratios) if ratios else Fraction(0)
    _cond("claude_total_ponderado_por_caso", r_pond, P.TECHO_CLAUDE_FACTOR)
    for c, r in zip(casos, ratios):
        _cond("claude_extremo_por_caso", r, P.TECHO_CLAUDE_FACTOR, {"caso": c})
        rmax = _ratio(cn[c]["maximo"], cb[c]["maximo"])
        _cond("claude_extremo_entre_repeticiones", rmax, P.TECHO_CLAUDE_FACTOR, {"caso": c})
        for nombre, rr in (("caso", r), ("max_corrida", rmax)):
            if rr > P.SUBIDA_QUE_EXIGE_MEJORA:
                req_mejora.append(f"{c}:{nombre}")
    if r_tot > P.SUBIDA_QUE_EXIGE_MEJORA:
        req_mejora.append("total")
    if r_pond > P.SUBIDA_QUE_EXIGE_MEJORA:
        req_mejora.append("ponderado")
    # Inferencias: suma por caso ≤ base + 3·R; máximo por corrida ≤ base + 3.
    for c in casos:
        ib = [int(r.get("inferencias") or 0) for r in base[c]["corridas"]]
        inn = [int(r.get("inferencias") or 0) for r in nuevo[c]["corridas"]]
        R = len(inn)
        _cond("inferencias_suma_por_caso", Fraction(sum(inn)),
              Fraction(sum(ib) + P.TECHO_INFERENCIAS_EXTRA_POR_CORRIDA * R), {"caso": c})
        _cond("inferencias_maximo_por_corrida", Fraction(max(inn) if inn else 0),
              Fraction((max(ib) if ib else 0) + P.TECHO_INFERENCIAS_EXTRA_POR_CORRIDA), {"caso": c})
    # Codex (5C) frente a Claude en 0.4.
    _cond("codex_total_agregado", _ratio(tot_x, tot_n), P.TECHO_CODEX_FACTOR)
    rx = [_ratio(cx[c]["agregado"], cn[c]["agregado"]) for c in casos]
    _cond("codex_total_ponderado_por_caso", sum(rx, Fraction(0)) / len(rx) if rx else Fraction(0),
          P.TECHO_CODEX_FACTOR)
    for c, r in zip(casos, rx):
        _cond("codex_extremo_por_caso", r, P.TECHO_CODEX_FACTOR, {"caso": c})
        for i, (tx, tc) in enumerate(zip(cx[c]["corridas"], cn[c]["corridas"]), 1):
            _cond("codex_extremo_por_corrida", _ratio(tx, tc), P.TECHO_CODEX_FACTOR,
                  {"caso": c, "corrida": i})
    descriptivo = {
        "mediana_corrida_base": float(statistics.median([v for c in casos for v in cb[c]["corridas"]] or [0])),
        "mediana_corrida_nuevo": float(statistics.median([v for c in casos for v in cn[c]["corridas"]] or [0])),
        "total_base": int(tot_b), "total_nuevo": int(tot_n), "total_codex": int(tot_x),
        "nota": "la mediana y el p50 son solo descriptivos (§6.3)",
    }
    resultado = "cumple" if all(c["cumple"] for c in condiciones) else "no_cumple"
    return {"resultado": resultado, "condiciones": condiciones, "descriptivo": descriptivo,
            "subidas_que_exigen_mejora_atribuible": req_mejora, "motivos": []}


# ════════════════════════════════════════════════════════════════════════════════════════
# §3.3 · Cotas ilustrativas y lenguaje publicable
# ════════════════════════════════════════════════════════════════════════════════════════
def texto_cota(r: int) -> str:
    cota = P.cota_ilustrativa(r)
    return (f"Con R = {r} y cero fallos, siguen siendo compatibles tasas por caso de hasta "
            f"≈ {round(cota * 100)} %, {P.FRASE_COTA_ILUSTRATIVA}.")


_PROHIBIDO = [re.compile(p, re.IGNORECASE) for p in P.LENGUAJE_PROHIBIDO_REGEX]


def verificar_lenguaje(texto: str) -> list[str]:
    """Formas prohibidas presentes en un texto publicable (vacío = limpio)."""
    return [p.pattern for p in _PROHIBIDO if p.search(texto or "")]


# ════════════════════════════════════════════════════════════════════════════════════════
# §6.4 · Veredicto global
# ════════════════════════════════════════════════════════════════════════════════════════
FILAS_ABSOLUTAS_GLOBALES: tuple[str, ...] = (
    "afirmaciones_sin_respaldo", "fuga_jurisdiccion (casos con alguna)",
    "definitivo_con_lectura_insuficiente", "discordancias_sin_resolver", "kappa_reservado",
    "kappa_salidas_reales", "circuito_sobre_mutaciones_reservadas", "evaluacion_completa_dos_jueces",
)
FILAS_LECTURA_COMPLETA: tuple[str, ...] = (
    "cobertura_hechos_decisivos (media)", "cobertura_hechos_decisivos (ningún caso < 0,80)",
    "aprobacion_sin_edicion_proxy",
)
FILAS_VOLUMINOSAS: tuple[str, ...] = (
    "cobertura_decisivos_en_lo_leido (media)",
    "cobertura_hechos_decisivos (media, suelo de no-retroceso)",
)
FILAS_TODO_ESTRATO: tuple[str, ...] = (
    "tasa_corridas_con_omision_material_leido", "utilidad_resultado_limitado (media)",
)
FILAS_EXTRA_OBLIGATORIAS: tuple[str, ...] = (
    "perdida_por_caso:cobertura_hechos_materiales", "perdida_por_caso:cobertura_hechos_decisivos",
    "decisivos_estables_perdidos", "atribucion_de_subidas_de_cuota",
)


def inventario_esperado(ids_custodiados: Iterable[str], *, contingencia: bool = False,
                        extension: Mapping[str, int] | None = None) -> dict:
    """Manifiesto de lo que TIENE que existir para emitir un veredicto (I1): los 17 casos con su
    R (más la extensión pre-registrada, si la hubo), las filas absolutas por estrato, cada
    métrica comparativa en cada unidad de inferencia y las filas comparativas obligatorias."""
    ids_c = list(ids_custodiados)
    if len(ids_c) != P.N_CASOS_C_VOLUMINOSOS:
        raise ValueError(f"se esperan {P.N_CASOS_C_VOLUMINOSOS} casos custodiados, hay {len(ids_c)}")
    todos = (*P.CASOS_A_CANONICOS, *P.CASOS_A_RIESGO, *P.CASOS_A_VOLUMINOSO, *P.CASOS_C_PEQUENOS, *ids_c)
    casos = {cid: {"estrato": P.estrato_de(cid, ids_c),
                   "R": P.repeticiones(cid, ids_c, contingencia=contingencia)
                   + int((extension or {}).get(cid, 0))} for cid in todos}
    filas = {(f, None) for f in FILAS_ABSOLUTAS_GLOBALES}
    filas |= {(f, e) for e in P.ESTRATOS_LECTURA_COMPLETA for f in FILAS_LECTURA_COMPLETA}
    filas |= {(f, e) for e in P.ESTRATOS_VOLUMINOSOS for f in FILAS_VOLUMINOSAS}
    filas |= {(f, e) for e in P.ESTRATOS for f in FILAS_TODO_ESTRATO}
    comparativas = {(m, u) for m in P.METRICAS_COMPARATIVAS for u in P.UNIDADES_INFERENCIA}
    return {"casos": casos, "filas_absolutas": filas, "comparativas": comparativas,
            "filas_extra": set(FILAS_EXTRA_OBLIGATORIAS)}


def filas_comparativas_obligatorias(*, base: Mapping[str, Mapping[str, Any]] | None,
                                    nuevo: Mapping[str, Mapping[str, Any]] | None,
                                    decisivos_base: Mapping[str, Mapping[str, Fraction]] | None,
                                    decisivos_nuevo: Mapping[str, Mapping[str, Fraction]] | None,
                                    techo: Mapping[str, Any], comparativas: Iterable[Mapping[str, Any]],
                                    atribuciones: Iterable[Mapping[str, Any]] | None) -> list[dict]:
    """I2: filas de §6.2/§6.3 que antes solo se calculaban. Entrada ausente ⇒ cumple None."""
    filas: list[dict] = []
    for m in ("cobertura_hechos_materiales", "cobertura_hechos_decisivos"):
        perd = None if base is None or nuevo is None else perdidas_por_caso(base, nuevo, m)
        filas.append(_fila(f"perdida_por_caso:{m}", perd, "ningún caso pierde más de 0,20",
                           None if perd is None else not perd, REPRUEBA))
    perd = (None if decisivos_base is None or decisivos_nuevo is None
            else decisivos_estables_perdidos(decisivos_base, decisivos_nuevo))
    filas.append(_fila("decisivos_estables_perdidos", perd, "≥ 3/5 en 0.3.3 no cae a ≤ 1/5",
                       None if perd is None else not perd, REPRUEBA))
    subidas = techo.get("subidas_que_exigen_mejora_atribuible")
    if techo.get("resultado") not in ("cumple", "no_cumple") or subidas is None or atribuciones is None:
        filas.append(_fila("atribucion_de_subidas_de_cuota", subidas, "toda subida > 10 % con mejora",
                           None, REPRUEBA))
    else:
        mejoras = {(c.get("metrica"), c.get("unidad")) for c in comparativas
                   if c.get("veredicto") == "mejora"}
        por_subida = {a.get("subida"): a for a in atribuciones}
        sin = [s_ for s_ in subidas if s_ not in por_subida
               or (por_subida[s_].get("metrica"), por_subida[s_].get("unidad")) not in mejoras
               or not por_subida[s_].get("nodo")]
        filas.append(_fila("atribucion_de_subidas_de_cuota", sin, "toda subida > 10 % con mejora "
                           "atribuible por nodo", not sin, REPRUEBA))
    return filas


def _recibo_extension_valido(cmp_: Mapping[str, Any]) -> bool:
    ext = cmp_.get("extension")
    if not isinstance(ext, Mapping):
        return False
    casos = list(ext.get("casos") or [])
    return (0 < len(casos) <= P.EXTENSION_MAX_CASOS
            and set(casos) <= set(casos_para_extension(cmp_)) | set(ext.get("casos_previos") or [])
            and ext.get("corridas_por_caso") == P.EXTENSION_CORRIDAS
            and ext.get("veredicto_final") in P.VEREDICTOS_COMPARATIVOS)


def veredicto_global(*, inventario: Mapping[str, Any], casos: Mapping[str, Mapping[str, Any]],
                     absolutos: list[dict], comparativas: list[dict], techo: Mapping[str, Any],
                     filas_extra: list[dict], suspendido: bool = False, salidas_sin_juzgar: int = 0,
                     otros_motivos_no_certificable: Iterable[str] = ()) -> dict:
    """aprueba / reprueba / no_certificable contra el INVENTARIO completo (I1, I2).

    Toda ausencia aplicable (caso, corrida evaluada, fila, métrica comparativa, dato) ⇒ no
    certificable. `no_concluyente` solo vale con recibo de la extensión pre-registrada. Una sola
    fila roja reprueba. Precedencia declarada: no_certificable > reprueba > aprueba."""
    rojas: list[str] = []
    motivos: list[str] = list(otros_motivos_no_certificable)
    # 1 · casos, repeticiones y evaluación por los dos jueces
    esperados = inventario["casos"]
    for cid in sorted(set(esperados) - set(casos)):
        motivos.append(f"falta_caso:{cid}")
    for cid in sorted(set(casos) - set(esperados)):
        motivos.append(f"caso_fuera_del_inventario:{cid}")
    for cid, esp in sorted(esperados.items()):
        f = casos.get(cid)
        if f is None:
            continue
        if f.get("estrato") != esp["estrato"]:
            motivos.append(f"estrato_distinto:{cid}")
        if int(f.get("R") or 0) != esp["R"]:
            motivos.append(f"repeticiones_incompletas:{cid}:{f.get('R')}/{esp['R']}")
        if int(f.get("n_evaluadas") or 0) != esp["R"]:
            motivos.append(f"corridas_sin_evaluar:{cid}:{f.get('n_evaluadas')}/{esp['R']}")
    # 2 · filas absolutas
    presentes = {(f["fila"], f.get("estrato")) for f in absolutos}
    for fila, est in sorted(inventario["filas_absolutas"] - presentes, key=str):
        motivos.append(f"falta_fila:{fila}{'@' + est if est else ''}")
    for f in absolutos:
        nombre = f"{f['fila']}{'@' + f['estrato'] if f.get('estrato') else ''}"
        if f.get("aplica", True) and f["cumple"] is None and f["fila"] != "kappa_salidas_reales":
            motivos.append(f"sin_dato:{nombre}")
        elif f["cumple"] is False:
            (motivos if f["efecto_si_falla"] == NO_CERTIFICABLE else rojas).append(nombre)
    # 3 · comparativas
    vistas = {(c.get("metrica"), c.get("unidad")) for c in comparativas}
    for m, u in sorted(inventario["comparativas"] - vistas):
        motivos.append(f"falta_comparativa:{m}@{u}")
    for c in comparativas:
        nombre = f"comparativa:{c.get('metrica')}@{c.get('unidad')}"
        v = c.get("veredicto")
        if v not in P.VEREDICTOS_COMPARATIVOS:
            motivos.append(f"veredicto_desconocido:{nombre}")
        elif c.get("sin_dato"):
            motivos.append(f"sin_dato:{nombre}")
        elif v == "regresion":
            rojas.append(nombre)
        elif v == "no_concluyente":
            if not _recibo_extension_valido(c):
                motivos.append(f"no_concluyente_sin_recibo_de_extension:{nombre}")
            elif c["extension"]["veredicto_final"] == "regresion":
                rojas.append(nombre + ":tras_extension")
    # 4 · filas comparativas obligatorias (I2)
    vistas_extra = {f["fila"] for f in filas_extra}
    for fila in sorted(inventario["filas_extra"] - vistas_extra):
        motivos.append(f"falta_fila:{fila}")
    for f in filas_extra:
        if f["cumple"] is None:
            motivos.append(f"sin_dato:{f['fila']}")
        elif f["cumple"] is False:
            rojas.append(f["fila"])
    # 5 · techo
    if techo.get("resultado") == NO_CERTIFICABLE:
        motivos.append("techo_no_certificable")
    elif techo.get("resultado") == "no_cumple":
        rojas.append("techo_de_cuota")
    elif techo.get("resultado") != "cumple":
        motivos.append("techo_ausente")
    if suspendido:
        motivos.append(P.ROTULO_SUSPENSION)
    if salidas_sin_juzgar:
        motivos.append(f"salidas_sin_juzgar:{salidas_sin_juzgar}")
    veredicto = NO_CERTIFICABLE if motivos else (REPRUEBA if rojas else "aprueba")
    return {"veredicto": veredicto, "filas_rojas": rojas, "motivos_no_certificable": motivos,
            "rotulo": P.ROTULO_AUTOMATICO}


def resumen_publicable(veredicto: Mapping[str, Any], comparativas: Iterable[Mapping[str, Any]] = (),
                       cotas_r: Iterable[int] = (5, 10)) -> str:
    """Texto llano del resultado. Falla si contiene una forma prohibida (§1.7, §3.3, §6.2)."""
    lineas = [f"Veredicto: {veredicto['veredicto']}. {veredicto['rotulo']}."]
    if veredicto.get("filas_rojas"):
        lineas.append("Filas rojas: " + "; ".join(veredicto["filas_rojas"]) + ".")
    if veredicto.get("motivos_no_certificable"):
        lineas.append("No certificable por: " + "; ".join(veredicto["motivos_no_certificable"]) + ".")
    for c in comparativas:
        etiqueta = c.get("rotulo") or ""
        lineas.append(f"{c['metrica']} en {c['unidad']}: {c['veredicto']}"
                      + (f" ({etiqueta})" if etiqueta else "") + ".")
    for r in cotas_r:
        lineas.append(texto_cota(r))
    texto = "\n".join(lineas)
    malas = verificar_lenguaje(texto)
    if malas:
        raise ValueError(f"lenguaje prohibido en el resumen: {malas}")
    return texto


# ════════════════════════════════════════════════════════════════════════════════════════
# §5.2 · El marcador literal es SEÑAL AUXILIAR: sus discrepancias con el juez se adjudican
# ════════════════════════════════════════════════════════════════════════════════════════
def discrepancias_marcador(diagnostico: str, borrador: str, hechos: Iterable[Mapping[str, Any]],
                           cubierto_juez: Mapping[str, bool]) -> list[dict]:
    """Hechos donde el marcador literal y el juicio de cobertura no coinciden. Se listan para
    adjudicación (§8.5). La cobertura NUNCA se toma del marcador (`recall_markers_signal` solo
    busca subcadenas: `scoring.py:671-672`)."""
    from .evaluador_congelado import recall_markers_signal  # C11: copia @7b9aaa0

    out: list[dict] = []
    for h in hechos:
        marcador = h.get("marcador")
        if not marcador or h["id"] not in cubierto_juez:
            continue
        presente = bool(recall_markers_signal(diagnostico, borrador, [marcador])["encontrados"])
        if presente != bool(cubierto_juez[h["id"]]):
            out.append({"hecho": h["id"], "marcador_presente": presente,
                        "juez_cubierto": bool(cubierto_juez[h["id"]]),
                        "requiere_adjudicacion": True})
    return out


# ════════════════════════════════════════════════════════════════════════════════════════
# Puente con la clave custodiada (`banco04-clave/v1`) y con la lista de fragmentos del prompt
# ════════════════════════════════════════════════════════════════════════════════════════
def alcance_desde_fragmentos(fragmentos_por_pieza: Mapping[str, int], envio: Envio | None) -> dict:
    """Alcance MEDIDO (§7.2) sobre lo que ENTRÓ AL PROMPT (`envio_desde_material`): solo cuentan
    como leídos los fragmentos enviados COMPLETOS; un fragmento parcial no cuenta, y una pieza sin
    ningún fragmento completo es «pieza sin leer». Sin medición → insuficiente."""
    if envio is None:
        return {"leidos": None, "total": None, "piezas_sin_leer": None, "medido": False}
    total = sum(int(n) for n in fragmentos_por_pieza.values())
    leidos = sum(1 for d, n in fragmentos_por_pieza.items() for f in range(int(n))
                 if ref_disponible((d, f), envio))
    parciales = sum(1 for d, n in fragmentos_por_pieza.items() for f in range(int(n))
                    if (str(d), f) in envio and not ref_disponible((d, f), envio))
    sin_leer = sorted(d for d, n in fragmentos_por_pieza.items()
                      if int(n) > 0 and not any(ref_disponible((d, f), envio) for f in range(int(n))))
    return {"leidos": leidos, "total": total, "piezas_sin_leer": sin_leer, "medido": True,
            "parciales": parciales}


def _refs_hecho(h: Mapping[str, Any]) -> list[tuple]:
    """Referencias de un hecho: los rangos si la clave los da (`rangos`: [{fragmento, inicio,
    fin}]); si no, solo los fragmentos (y entonces se exige el fragmento completo)."""
    doc = str(h["documento"])
    if h.get("rangos"):
        return [(doc, int(r["fragmento"]), int(r["inicio"]), int(r["fin"])) for r in h["rangos"]]
    return [(doc, int(f)) for f in h["fragmentos"]]


def hechos_y_puntos_desde_clave(clave: Mapping[str, Any], salida_pasada2: Mapping[str, Any],
                                envio: Envio | None) -> dict:
    """Hechos, puntos y conducta de UNA corrida, a partir de la clave y de la pasada 2.
    `cubierto` sale del JUEZ; el marcador auxiliar solo viaja para listar discrepancias."""
    e = envio
    p2h = {h["id"]: h for h in salida_pasada2["hechos"]}
    p2p = {p["id"]: p for p in salida_pasada2["puntos"]}
    hechos, disp_h = [], {}
    for h in clave["hechos_materiales"]:
        d = disponible(_refs_hecho(h), e)
        disp_h[h["id"]] = d
        hechos.append({"id": h["id"], "decisivo": bool(h["decisivo"]),
                       "cubierto": bool(p2h[h["id"]]["cubierto"]), "disponible": d,
                       "marcador": h.get("marcador_auxiliar")})
    puntos = []
    for p in clave["puntos_materiales"]:
        frs = [(str(f["documento"]), int(f["fragmento"])) for f in p.get("fragmentos") or []]
        deps = list(p.get("depende_de_hechos") or [])
        if p["tipo"] == "laguna_real":
            d = True
        elif frs:
            d = punto_disponible(frs, e)
        else:
            d = bool(deps) and all(disp_h.get(x, False) for x in deps)
        puntos.append({"id": p["id"], "tipo": p["tipo"], "disponible": d,
                       "resolucion": p2p[p["id"]]["resolucion"]})
    c = salida_pasada2["conducta"]
    return {"hechos": hechos, "puntos": puntos, "conducta": c["clase"],
            "dice_lo_no_leido": bool(c["dice_lo_no_leido"]),
            "juez_aprobaria": salida_pasada2["aprobaria_sin_editar"]["respuesta"] == "si"}
