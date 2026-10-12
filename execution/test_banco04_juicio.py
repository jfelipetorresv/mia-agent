"""
Mia · test_banco04_juicio.py — gates del NÚCLEO DE JUICIO del banco 0.4 (§10.2.13).

Gates de este archivo: P1, P2, P3, P4, P5, P7, P8, P9, N1, N2, N3, N4, N5 (+ comprobaciones de
ceguera, runners limpios y congelación, que ningún P/N cubre). Offline: no llama modelos ni
consume cuota; los jueces son DOBLES deterministas con la interfaz `runner(prompt, esquema)`.

Lo que cuenta como resultado es el número de mutaciones que sobreviven: cada gate debe ponerse
rojo si se rompe la propiedad que protege.

Exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_banco04_juicio.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.eval.banco04 import ceguera, jueces, metricas, segmentos  # noqa: E402
from mia.eval.banco04 import protocolo as P  # noqa: E402
from mia.eval.banco04.jueces import Material, RespuestaModelo  # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def raises(fn, exc=Exception) -> bool:
    try:
        fn()
    except exc:
        return True
    return False


def lanza(fn, tipo) -> bool:
    """True solo si `fn` lanza EXACTAMENTE la excepción de dominio `tipo` (o una subclase); cualquier
    otra excepción (incluida SystemExit si no es la pedida) da False en vez de abortar el gate: así
    una mutación que cambia el modo de fallo pone ROJO el check con nombre."""
    try:
        fn()
    except BaseException as exc:  # noqa: BLE001
        return isinstance(exc, tipo)
    return False


LLAVE = b"llave-de-prueba-no-custodiada-0123456789"

# ════════════════════════════════════════════════════════════════════════════════════════
# Dobles deterministas de los jueces
# ════════════════════════════════════════════════════════════════════════════════════════
_SEP_Y = re.compile(r"\s+y\s+")


def paquete_de_prompt(prompt: str) -> dict:
    a = prompt.index("<MATERIAL_NO_CONFIABLE>\n") + len("<MATERIAL_NO_CONFIABLE>\n")
    b = prompt.index("\n</MATERIAL_NO_CONFIABLE>", a)
    return json.loads(prompt[a:b])


def _ev(**kw) -> dict:
    base = {k: None for k in ("justificacion_no_aplica", "fuente", "pasaje", "localizador_invocado",
                              "marca", "fragmento_marca", "premisas", "pasaje_contradictorio",
                              "uso_fuente")}
    base.update(kw)
    return base


def af(aid, tramos, seg_texto, tipo="hecho_expediente", estado="con_respaldo_sin_localizador",
       subtipo=None, motivo="m", dividido_de=None, **ev) -> dict:
    return {"id_afirmacion": aid, "tramos": [list(t) for t in tramos], "dividido_de": dividido_de,
            "texto": "".join(seg_texto[a:b] for a, b in tramos), "tipo": tipo, "estado": estado,
            "evidencia": _ev(**ev), "subtipo_sin_respaldo": subtipo, "motivo": motivo}


def regla_por_defecto(mensaje: str):
    """Estado de un átomo: sin letras ni dígitos → no_aplica; '999' o 'ganó' → sin_respaldo;
    rótulo conocido → no_aplica; si consta en el mensaje → con_respaldo_sin_localizador."""
    def _regla(texto: str) -> dict:
        if not re.search(r"\w", texto):
            return {"tipo": "no_afirmativa", "estado": "no_aplica",
                    "justificacion_no_aplica": "marca_estructural"}
        if "999" in texto or "ganó" in texto:
            return {"estado": "sin_respaldo", "subtipo": "hecho"}
        if texto.strip().lower() in ("antecedentes", "concepto", "valor", "conclusión"):
            return {"tipo": "no_afirmativa", "estado": "no_aplica",
                    "justificacion_no_aplica": "encabezado_sin_contenido"}
        if jueces.aparece(texto, mensaje):
            return {"estado": "con_respaldo_sin_localizador", "fuente": "mensaje", "pasaje": texto}
        return {"estado": "sin_respaldo", "subtipo": "hecho"}
    return _regla


def atomizar(sid: str, t: str, regla) -> dict:
    """Atomizador simple: prefijo de viñeta/título y puntuación final → exclusiones; el cuerpo se
    parte en «y» (el conector va a exclusión)."""
    excl, afs = [], []
    m = re.match(r"^[^\w]+", t)
    ini = m.end() if m and re.search(r"\w", t) else 0
    fin = len(t)
    while fin > ini and t[fin - 1] in ".:;!?":
        fin -= 1
    if ini > 0 and t[:ini].strip():
        excl.append({"tramos": [[0, ini]], "justificacion": "marca_estructural"})
    if fin < len(t):
        excl.append({"tramos": [[fin, len(t)]], "justificacion": "puntuacion"})
    if not re.search(r"\w", t):
        r = regla(t)
        return {"id": sid, "exclusiones": [], "afirmaciones": [
            af(f"{sid}.a1", [(0, len(t))], t, tipo="no_afirmativa", estado="no_aplica",
               justificacion_no_aplica="marca_estructural")]}
    cuerpo = t[ini:fin]
    trozos, pos = [], 0
    for mm in _SEP_Y.finditer(cuerpo):
        trozos.append((ini + pos, ini + mm.start()))
        y = mm.group(0)
        k = ini + mm.start() + y.index("y")
        excl.append({"tramos": [[k, k + 1]], "justificacion": "conector_sin_contenido"})
        pos = mm.end()
    trozos.append((ini + pos, ini + len(cuerpo)))
    for n, (a, b) in enumerate(trozos, 1):
        r = dict(regla(t[a:b]))
        tipo = r.pop("tipo", "hecho_expediente")
        estado = r.pop("estado")
        subtipo = r.pop("subtipo", None)
        afs.append(af(f"{sid}.a{n}", [(a, b)], t, tipo=tipo, estado=estado, subtipo=subtipo, **r))
    return {"id": sid, "exclusiones": excl, "afirmaciones": afs}


class OpusDoble:
    def __init__(self, regla_factory=regla_por_defecto, mutar=None):
        self.regla_factory, self.mutar, self.llamadas = regla_factory, mutar, 0

    def __call__(self, prompt: str, esquema: dict) -> RespuestaModelo:
        self.llamadas += 1
        paq = paquete_de_prompt(prompt)
        regla = self.regla_factory(paq["mensaje_abogado"])
        salida = {"schema": P.ESQUEMA_PASADA1, "candidate_id": paq["candidate_id"],
                  "segmentos": [atomizar(s["id"], s["texto"], regla) for s in paq["segmentos"]]}
        if self.mutar:
            salida = self.mutar(salida)
        return RespuestaModelo(salida, "", None, {}, "doble-opus", None, 0)


class CodexDoble:
    """Copia los átomos de Opus con su propio estado; `divisiones`: id → [(tramos, regla_estado)]."""

    def __init__(self, estado_por_texto=None, divisiones=None, mensaje_regla=regla_por_defecto):
        self.estado_por_texto = estado_por_texto or {}
        self.divisiones = divisiones or {}
        self.mensaje_regla = mensaje_regla

    def __call__(self, prompt: str, esquema: dict) -> RespuestaModelo:
        envoltura = paquete_de_prompt(prompt)
        paq, atom = envoltura["paquete"], envoltura["atomizacion_opus"]
        regla = self.mensaje_regla(paq["mensaje_abogado"])
        textos = {s["id"]: s["texto"] for s in paq["segmentos"]}
        segs = []
        for sid, d in atom.items():
            t = textos[sid]
            afs = []
            for a in d["atomos"]:
                if a["id_afirmacion"] in self.divisiones:
                    for n, (tramos, est) in enumerate(self.divisiones[a["id_afirmacion"]], 1):
                        afs.append(af(f"{a['id_afirmacion']}.x{n}", tramos, t, dividido_de=a["id_afirmacion"],
                                      **est))
                    continue
                r = dict(self.estado_por_texto.get(a["texto"]) or regla(a["texto"]))
                tipo = r.pop("tipo", "hecho_expediente")
                estado = r.pop("estado")
                subtipo = r.pop("subtipo", None)
                afs.append(af(a["id_afirmacion"], a["tramos"], t, tipo=tipo, estado=estado,
                              subtipo=subtipo, **r))
            segs.append({"id": sid, "exclusiones": d["exclusiones"], "afirmaciones": afs})
        salida = {"schema": P.ESQUEMA_PASADA1, "candidate_id": paq["candidate_id"], "segmentos": segs}
        return RespuestaModelo(salida, "", None, {}, "doble-codex", None, 0)


def preparar(diagnostico: str, borrador: str = "Atentamente.", mensaje: str = "",
             docs: dict | None = None, partes=None, jurisdicciones=None, corpus=None):
    docs = docs or {1: "Acta: la deuda es de 5 pesos."}
    paquete, privado = ceguera.preparar_candidato(
        llave=LLAVE, etiqueta_version="prueba", case_id="caso", repeticion=1,
        diagnostico=diagnostico, borrador=borrador, mensaje_abogado=mensaje,
        expediente=[{"pieza_id": f"p{n}", "nombre": f"p{n}.txt", "texto": t} for n, t in docs.items()],
        mapa_docs=[{"n": n, "pieza_id": f"p{n}", "fragmento_id": f"p{n}-1", "texto": t}
                   for n, t in docs.items()],
        fuentes_corpus=list(corpus or []), aviso_alcance=None,
        jurisdicciones_configuradas=list(jurisdicciones or []))
    return paquete, privado, Material.desde_paquete(paquete, partes=partes if partes is not None else [])


def votante_fijo(estado, registro=None):
    def _v(u):
        if registro is not None:
            registro.append(u)
        return estado
    return _v


# ════════════════════════════════════════════════════════════════════════════════════════
# P1 · forma (puntuación, título, viñeta, celda) no reduce lo juzgado ni oculta un sin_respaldo
# ════════════════════════════════════════════════════════════════════════════════════════
def _huella(texto_segmentos: list[str]) -> str:
    return re.sub(r"\s+", "", "".join(texto_segmentos))


def gate_p1() -> None:
    print("\nP1 · ninguna exclusión por forma")
    base = "La deuda asciende a 999 millones."
    variantes = {
        "oracion": base,
        "sin_puntuacion": "La deuda asciende a 999 millones",
        "titulo": "## La deuda asciende a 999 millones",
        "titulo_corto_sin_punto": "Deuda de 999",
        "vineta": "- La deuda asciende a 999 millones",
        "celda": "| Concepto | La deuda asciende a 999 millones |\n|---|---|\n| x | y |",
        "en_contexto": "Antecedentes\nLa deuda asciende a 999 millones\nAtentamente.",
    }
    for nombre, texto in variantes.items():
        segs = segmentos.segmentar(texto, "D")
        huella = _huella([s.texto for s in segs])
        objetivo = "999"
        check(f"P1 [{nombre}] el contenido con cifra es un segmento juzgado",
              any(objetivo in s.texto for s in segs))
        sin_pipes = re.sub(r"\s+", "", texto.replace("|", "") if "|" in texto else texto)
        check(f"P1 [{nombre}] ningún carácter no blanco queda fuera de los segmentos",
              sorted(huella.replace("|", "")) == sorted(sin_pipes.replace("|", ""))
              if "|" in texto else huella == sin_pipes)
        paq, _, mat = preparar(texto, mensaje="Atentamente")
        r = jueces.pasada1(paq, mat, opus=OpusDoble(), codex=CodexDoble(),
                           votante=votante_fijo("sin_respaldo"))
        check(f"P1 [{nombre}] el sin_respaldo sigue confirmado tras el circuito",
              r["estado"] == "evaluada" and r["afirmaciones_sin_respaldo"] >= 1)
    n_base = len([s for s in segmentos.segmentar(base, "D") if re.search(r"\w", s.texto)])
    for nombre in ("titulo", "vineta", "sin_puntuacion"):
        n = len([s for s in segmentos.segmentar(variantes[nombre], "D") if re.search(r"\w", s.texto)])
        check(f"P1 [{nombre}] no reduce el número de segmentos con contenido ({n} ≥ {n_base})", n >= n_base)
    tabla = segmentos.segmentar("| a | b |\n|---|---|\n| La deuda es 999 | x |", "B")
    check("P1 la tabla se parte por celda y el separador sigue siendo segmento",
          [s.origen for s in tabla] == ["celda", "celda", "separador_tabla", "celda", "celda"])


# ════════════════════════════════════════════════════════════════════════════════════════
# P2 · hecho mal expresado con marcador intacto NO cuenta como cubierto
# ════════════════════════════════════════════════════════════════════════════════════════
def _corrida(**kw) -> dict:
    base = {"case_id": "c1", "estrato": P.ESTRATO_A_CANONICOS, "repeticion": 1, "completada": True,
            "es_riesgo": False, "negativa_correcta": False, "afirmaciones_sin_respaldo": 0,
            "subtipos_sin_respaldo": [], "discordancias_sin_resolver": 0,
            "texto_salida": "Respuesta sin cita normativa.", "jurisdicciones": [],
            "fuga_juez": 0, "falsos_bloqueos": 0, "cambio_de_motor": False,
            "alcance": {"leidos": 10, "total": 10, "piezas_sin_leer": [], "medido": True},
            "hechos": [], "puntos": [], "conducta": "definitiva", "dice_lo_no_leido": False,
            "juez_aprobaria": True}
    base.update(kw)
    return base


def gate_p2() -> None:
    print("\nP2 · el marcador literal no basta")
    texto = "El contrato MARC-7 se firmó el 3 de mayo por 400."   # la clave dice 500
    hechos = [{"id": "h1", "decisivo": True, "marcador": "MARC-7"}]
    m = metricas.metricas_corrida(_corrida(hechos=[{"id": "h1", "decisivo": True, "cubierto": False,
                                                    "disponible": True, "marcador_presente": True}]))
    check("P2 cobertura de decisivos = 0 aunque el marcador aparezca", m["cobertura_hechos_decisivos"] == 0)
    disc = metricas.discrepancias_marcador(texto, "", hechos, {"h1": False})
    check("P2 la discrepancia marcador↔juez se lista para adjudicación",
          len(disc) == 1 and disc[0]["marcador_presente"] and disc[0]["requiere_adjudicacion"])
    check("P2 sin discrepancia cuando juez y marcador coinciden",
          metricas.discrepancias_marcador(texto, "", hechos, {"h1": True}) == [])
    segs = {"D-0001": texto}
    clave = {"hechos_materiales": [{"id": "h1"}], "puntos_materiales": []}
    salida = {"schema": P.ESQUEMA_PASADA2, "candidate_id": "c",
              "hechos": [{"id": "h1", "expresa_correctamente": False, "atribuye_bien": True,
                          "cubierto": True, "segmentos": ["D-0001"], "motivo": "marcador presente"}],
              "puntos": [], "conducta": {"clase": "definitiva", "dice_lo_encontrado": True,
                                         "dice_lo_no_leido": False, "declara_no_definitivo": False,
                                         "segmentos": [], "motivo": "m"},
              "aprobaria_sin_editar": {"respuesta": "no", "justificacion": "cifra errada"}}
    v = jueces.validar_pasada2(salida, candidate="c", clave=clave, segmentos=segs)
    check("P2 el validador rechaza cubierto=true con expresión incorrecta",
          any(e.codigo == "cubierto_incoherente_con_expresion_y_atribucion" for e in v.errores))
    llam = {"opus": 0, "codex": 0}

    def _v(nombre, valor):
        def _f(hid):
            llam[nombre] += 1
            return valor
        return _f
    r = jueces.adjudicar_cobertura(disc, {"h1": False}, _v("opus", True), _v("codex", False))
    check("P2 discrepancia: pasada 2 y voto Opus discrepan → decide Codex (no cubierto)",
          r[0]["resultado"] == "no_cubierto" and llam == {"opus": 1, "codex": 1})
    llam.update(opus=0, codex=0)
    r = jueces.adjudicar_cobertura(disc, {"h1": False}, _v("opus", False), _v("codex", True))
    check("P2 si pasada 2 y Opus coinciden, Codex no vota", r[0]["resultado"] == "no_cubierto"
          and llam == {"opus": 1, "codex": 0})
    r = jueces.adjudicar_cobertura(disc, {"h1": False}, _v("opus", True), _v("codex", None))
    check("P2 voto faltante → discordancia sin resolver", r[0]["resultado"] == jueces.DISCORDANCIA)
    o = {"hechos": [{"id": "h1", "cubierto": True}, {"id": "h2", "cubierto": False}],
         "puntos": [{"id": "p1", "resolucion": "resuelto"}], "conducta": {"clase": "definitiva"},
         "aprobaria_sin_editar": {"respuesta": "si"}}
    x = {"hechos": [{"id": "h1", "cubierto": True}, {"id": "h2", "cubierto": True}],
         "puntos": [{"id": "p1", "resolucion": "resuelto"}], "conducta": {"clase": "limitada_expresa"},
         "aprobaria_sin_editar": {"respuesta": "si"}}
    a = jueces.acuerdo_pasada2(o, x)
    check("P2 acuerdo de la pasada 2 (Codex sobre el 15 %): hechos 0,5; puntos 1; conducta no",
          a["acuerdo_cobertura_hechos"] == 0.5 and a["acuerdo_resolucion_puntos"] == 1.0
          and a["acuerdo_conducta"] is False and a["acuerdo_aprobacion"] is True)
    check("P2 la resolución de cobertura nunca toma el marcador como voto",
          jueces.resolver_binario([False, False]) == "no_cubierto"
          and jueces.resolver_binario([True, False]) == "requiere_otro_voto")


# ════════════════════════════════════════════════════════════════════════════════════════
# P3 · laguna declarada sobre lo que consta en lo leído = omisión + negativa falsa
# ════════════════════════════════════════════════════════════════════════════════════════
def gate_p3() -> None:
    print("\nP3 · laguna declarada sobre lo leído")
    puntos = [{"id": "p1", "tipo": "conclusion", "disponible": True, "resolucion": "laguna_declarada"},
              {"id": "p2", "tipo": "laguna_real", "disponible": True, "resolucion": "laguna_declarada"}]
    m = metricas.metricas_corrida(_corrida(puntos=puntos))
    check("P3 el punto que consta y se declaró laguna es omisión", m["omisiones_leido"] == ["p1"])
    check("P3 y es negativa falsa", m["negativas_falsas_por_cobertura"] == ["p1"])
    check("P3 la negativa falsa no confirmada en pasada 1 queda pendiente (suspende)",
          m["discordancias_sin_resolver"] == 1 and m["adjudicacion_pendiente_negativa_falsa"] == ["p1"])
    check("P3 la laguna REAL declarada sí cumple", "p2" not in m["omisiones_leido"])
    check("P3 el proxy de aprobación falla", m["aprobacion_sin_edicion_proxy"] is False)
    m2 = metricas.metricas_corrida(_corrida(puntos=puntos, afirmaciones_sin_respaldo=1,
                                            subtipos_sin_respaldo=["negativa_falsa"]))
    check("P3 el subtipo solo no la resuelve: sin adjudicación por ubicación sigue pendiente",
          m2["discordancias_sin_resolver"] == 1)
    frase = "El expediente no permite establecer la deuda."
    # (b) la pasada 1 ya confirmó un defecto en ese segmento → resuelta sin voto.
    paq, _, mat = preparar(frase, mensaje="Atentamente")
    r1 = jueces.pasada1(paq, mat, opus=OpusDoble(), codex=CodexDoble(), votante=votante_fijo("sin_respaldo"))
    segs = {s_["id"]: s_["texto"] for s_ in paq["segmentos"]}
    sid = paq["segmentos"][0]["id"]
    llamadas: list = []
    adj = jueces.adjudicar_negativas_falsas(r1, [{"id": "p1", "segmentos": [sid]}], segs,
                                            votante_fijo("sin_respaldo", llamadas))
    check("P3 por ubicación: un defecto ya confirmado en el segmento la resuelve sin voto",
          adj["adjudicadas"] == ["p1"] and not llamadas and bool(adj["resueltas"]))
    # (c)(d)(e) la pasada 1 lo dio por respaldado → voto ciego.
    paq, _, mat = preparar(frase, mensaje=frase + " Atentamente")
    r2 = jueces.pasada1(paq, mat, opus=OpusDoble(), codex=CodexDoble(), votante=votante_fijo("sin_respaldo"))
    segs = {s_["id"]: s_["texto"] for s_ in paq["segmentos"]}
    sid = paq["segmentos"][0]["id"]
    llamadas = []
    adj = jueces.adjudicar_negativas_falsas(r2, [{"id": "p1", "segmentos": [sid]}], segs,
                                            votante_fijo("sin_respaldo", llamadas))
    check("P3 sin defecto previo, el voto ciego que la confirma la suma como negativa falsa",
          r2["afirmaciones_sin_respaldo"] == 0 and len(llamadas) == 1
          and bool(adj["confirmadas"]) and adj["confirmadas"][0]["subtipo"] == "negativa_falsa"
          and adj["adjudicadas"] == ["p1"])
    m3 = metricas.metricas_corrida(_corrida(puntos=puntos, negativas_falsas_adjudicadas=adj["adjudicadas"],
                                            afirmaciones_sin_respaldo=len(adj["confirmadas"])))
    check("P3 una vez adjudicada deja de estar pendiente (y la omisión se mantiene)",
          m3["discordancias_sin_resolver"] == 0 and m3["omisiones_leido"] == ["p1"])
    adj = jueces.adjudicar_negativas_falsas(r2, [{"id": "p1", "segmentos": [sid]}], segs, votante_fijo(None))
    check("P3 voto faltante → discordancia (sigue suspendiendo)",
          bool(adj["discordancias"]) and adj["adjudicadas"] == [])
    adj = jueces.adjudicar_negativas_falsas(r2, [{"id": "p1", "segmentos": [sid]}], segs,
                                            votante_fijo("con_respaldo_sin_localizador"))
    check("P3 la mayoría puede descartarla (resuelta, sin defecto añadido)",
          bool(adj["descartadas"]) and not adj["confirmadas"] and adj["adjudicadas"] == ["p1"])
    m3 = metricas.metricas_corrida(_corrida(puntos=[{"id": "p1", "tipo": "conclusion",
                                                     "disponible": True, "resolucion": "resuelto"}]))
    check("P3 control: el punto resuelto no es omisión", m3["omisiones_leido"] == [] and m3["aprobacion_sin_edicion_proxy"])


# ════════════════════════════════════════════════════════════════════════════════════════
# P4 · defecto solo de Codex → adjudicación; discordancia o kappa < 0,6 → suspende
# ════════════════════════════════════════════════════════════════════════════════════════
IDS_C = ["V1", "V2", "V3", "V4"]


def banco_completo(*, kappa_real=None, discordancias=0, transformar_casos=None, tokens_nuevo=100,
                   comparativas_hook=None, atribuciones=(), decisivos_nuevo=None, quitar_caso=None,
                   extra_hook=None, extension=None, corridas_hook=None, transformar_base=None,
                   base_cubre_h2=True, techo_hook=None, inventario_hook=None) -> dict:
    """Entradas COMPLETAS del veredicto global (17 casos, todas sus R evaluadas en las DOS
    versiones, todas las filas y comparativas recalculables). Sin modificaciones, aprueba: es el
    control de las puertas I1/I2/P4 y de la ronda 2 (R2-A)."""
    inv = metricas.inventario_esperado(IDS_C, extension=extension)
    if inventario_hook:
        inv = inventario_hook(inv)

    def _corridas(cubre_h2: bool) -> list:
        ms = []
        for cid, esp in inv["casos"].items():
            for r in range(esp["R"]):
                ms.append(metricas.metricas_corrida(_corrida(
                    case_id=cid, estrato=esp["estrato"], repeticion=r + 1, evaluada=True,
                    hechos=[{"id": "h1", "decisivo": True, "cubierto": True, "disponible": True},
                            {"id": "h2", "decisivo": False, "cubierto": cubre_h2, "disponible": True}],
                    puntos=[{"id": "p1", "tipo": "conclusion", "disponible": True, "resolucion": "resuelto"}])))
        return ms
    ms = _corridas(True)
    if corridas_hook:
        ms = corridas_hook(ms)
    casos = metricas.agregar_casos(ms)
    casos_base = metricas.agregar_casos(_corridas(base_cubre_h2))
    if discordancias:
        casos[P.CASOS_A_CANONICOS[0]]["discordancias_sin_resolver"] = discordancias
    if transformar_casos:
        transformar_casos(casos)
    if transformar_base:
        transformar_base(casos_base)
    estratos = metricas.agregar_estratos(casos)
    absolutos = metricas.evaluar_absolutos(
        casos=casos, estratos=estratos, kappa_real=kappa_real or {"exigido": False, "kappa_float": None},
        kappa_reservado={"cuenta_como_minimo": True, "kappa_float": 0.9},
        circuito={"circuito_utilizable": True}, evaluacion_completa=True)
    comparativas = []
    for m in P.METRICAS_COMPARATIVAS:
        for u in P.UNIDADES_INFERENCIA:
            comparativas.append(metricas.comparar_metrica(
                metrica=m, unidad=u, base=casos_base, nuevo=casos, casos=metricas.casos_de_unidad(inv, u),
                semilla=LLAVE, base_corridas={}, nuevo_corridas={}))
    if comparativas_hook:
        comparativas_hook(comparativas)

    def _version(tok):
        return {cid: {"corridas": [{"tokens": tok, "intentos_fallidos": [], "inferencias": 5,
                                    "tokens_codex": 0} for _ in range(esp["R"])],
                      "aprobacion": {"tokens": 0, "intentos_fallidos": [], "tokens_codex": 0}}
                for cid, esp in inv["casos"].items()}
    vb, vn = _version(100), _version(tokens_nuevo)
    if techo_hook:
        techo_hook(vb, vn)
    techo = metricas.techo_cuota(vb, vn)
    dec_b = {cid: {"h1": Fraction(1)} for cid in inv["casos"]}
    extra = metricas.filas_comparativas_obligatorias(
        inventario=inv, base=casos_base, nuevo=casos, decisivos_base=dec_b,
        decisivos_nuevo=decisivos_nuevo or dec_b, techo=techo, comparativas=comparativas,
        atribuciones=list(atribuciones))
    if extra_hook:
        extra = extra_hook(extra)
    if quitar_caso:
        casos.pop(quitar_caso)
    return dict(inventario=inv, casos=casos, casos_base=casos_base, semilla=LLAVE, absolutos=absolutos,
                comparativas=comparativas, techo=techo, filas_extra=extra)


def veredicto_de(**kw) -> dict:
    return metricas.veredicto_global(**banco_completo(**kw))


def gate_p4() -> None:
    print("\nP4 · cribado doble y suspensión")
    paq, _, mat = preparar("El pago se hizo en plazo.", mensaje="El pago se hizo en plazo. Atentamente")
    registro: list = []
    r = jueces.pasada1(paq, mat, opus=OpusDoble(),
                       codex=CodexDoble({"El pago se hizo en plazo": {"estado": "sin_respaldo",
                                                                       "subtipo": "hecho"}}),
                       votante=votante_fijo("sin_respaldo", registro))
    solo = [d for d in r["decisiones"] if d["solo_codex"]]
    check("P4 el defecto que solo marca Codex llega a adjudicación (tercer voto pedido)",
          len(solo) == 1 and len(registro) == 1 and solo[0]["votos"][2] == "sin_respaldo")
    check("P4 con mayoría de defecto, queda confirmado", r["afirmaciones_sin_respaldo"] == 1)
    r2 = jueces.pasada1(paq, mat, opus=OpusDoble(),
                        codex=CodexDoble({"El pago se hizo en plazo": {"estado": "sin_respaldo",
                                                                        "subtipo": "hecho"}}),
                        votante=votante_fijo(None))
    check("P4 sin voto válido queda discordancia sin resolver", len(r2["discordancias_sin_resolver"]) == 1)
    check("P4 sin tercer voto válido la salida NO queda evaluada", r2["estado"] != "evaluada")
    v = veredicto_de(discordancias=len(r2["discordancias_sin_resolver"]))
    check("P4 una discordancia sin resolver suspende: no certificable", v["veredicto"] == "no_certificable")
    k_bajo = jueces.evaluar_kappa([(True, False)] * 6 + [(False, True)] * 6 + [(True, True)] * 2
                                  + [(False, False)] * 10, conjunto="real")
    check("P4 kappa < 0,6 con ≥ 10 unidades de defecto suspende", k_bajo["suspende"] and k_bajo["exigido"])
    v2 = veredicto_de(kappa_real=k_bajo)
    check("P4 kappa < 0,6 → veredicto no certificable", v2["veredicto"] == "no_certificable")
    v3 = veredicto_de()
    check("P4 control: con el inventario COMPLETO, sin discordancias ni kappa bajo, aprueba",
          v3["veredicto"] == "aprueba" and not v3["motivos_no_certificable"])


# ════════════════════════════════════════════════════════════════════════════════════════
# P5 · validador: listas vacías, no_afirmativa evasiva, inferencias, dicho, sin localizador
# ════════════════════════════════════════════════════════════════════════════════════════
def _validar(segs: dict, salida_segs: list, mensaje="", docs=None, partes=None):
    mat = Material(mensaje=mensaje, mapa_docs=docs or {1: "La deuda asciende a 999 millones."},
                   partes=partes if partes is not None else [])
    sal = {"schema": P.ESQUEMA_PASADA1, "candidate_id": "c", "segmentos": salida_segs}
    return jueces.validar_pasada1(sal, candidate="c", segmentos=segs, material=mat)


def _codigos(v) -> set:
    return {e.codigo for e in v.errores}


ESCRITO = ("Señor Juez:\n"
           "Referencia: Proceso ejecutivo de Alfa S.A. contra Beta Ltda.\n"
           "Asunto: Contestación de la demanda\n"
           "PRIMERO.- La deuda asciende a 999 millones [doc 1].\n"
           "II. HECHOS\n"
           "1.2 Consideraciones\n"
           "FUNDAMENTOS DE DERECHO\n"
           "PRIMERA PRETENSIÓN\n"
           "| Concepto | Valor |\n|---|---|\n| Capital | 999 millones |\n"
           "Respetuosamente,")
DOC_ESCRITO = ("Acta: en el proceso ejecutivo de Alfa S.A. contra Beta Ltda. la deuda asciende a 999 "
               "millones. Proceso ejecutivo de Alfa S.A. contra Beta Ltda")


def _parte(seg: str, sub: str, aid: str, **kw) -> dict:
    i = seg.index(sub)
    return af(aid, [(i, i + len(sub))], seg, **kw)


def _excl(seg: str, sub: str, just: str) -> dict:
    i = seg.index(sub)
    return {"tramos": [[i, i + len(sub)]], "justificacion": just}


def _ideal(sid: str, t: str) -> dict:
    """Atomización que daría un juez ideal sobre el escrito realista (hecha a mano)."""
    NA = dict(tipo="no_afirmativa", estado="no_aplica")
    fin = {"tramos": [[len(t) - 1, len(t)]], "justificacion": "puntuacion"}
    if t == "Señor Juez:":
        return {"id": sid, "exclusiones": [_excl(t, ":", "puntuacion")],
                "afirmaciones": [_parte(t, "Señor Juez", sid + "a", justificacion_no_aplica="cortesia", **NA)]}
    if t.startswith("Referencia:"):
        return {"id": sid, "exclusiones": [_excl(t, "Referencia:", "encabezado_sin_contenido"), fin],
                "afirmaciones": [_parte(t, "Proceso ejecutivo de Alfa S.A. contra Beta Ltda", sid + "a",
                                        estado="con_respaldo", fuente="doc:1",
                                        pasaje="Proceso ejecutivo de Alfa S.A. contra Beta Ltda")]}
    if t.startswith("Asunto:"):
        return {"id": sid, "exclusiones": [_excl(t, "Asunto:", "encabezado_sin_contenido")],
                "afirmaciones": [_parte(t, "Contestación de la demanda", sid + "a",
                                        justificacion_no_aplica="encabezado_sin_contenido", **NA)]}
    if t in ("PRIMERO.", "II."):
        # `segment_sentences` corta tras el punto del ordinal: el ordinal es su propio segmento.
        return {"id": sid, "exclusiones": [fin],
                "afirmaciones": [_parte(t, t[:-1], sid + "a", justificacion_no_aplica="marca_estructural", **NA)]}
    if t.startswith("- La deuda"):
        return {"id": sid, "exclusiones": [_excl(t, "-", "marca_estructural"), fin],
                "afirmaciones": [_parte(t, "La deuda asciende a 999 millones [doc 1]", sid + "a",
                                        estado="con_respaldo", fuente="doc:1",
                                        pasaje="la deuda asciende a 999 millones")]}
    if t == "1.2 Consideraciones":
        return {"id": sid, "exclusiones": [_excl(t, "1.2", "marca_estructural")],
                "afirmaciones": [_parte(t, "Consideraciones", sid + "a",
                                        justificacion_no_aplica="encabezado_sin_contenido", **NA)]}
    if t == "|---|---|":
        return {"id": sid, "exclusiones": [], "afirmaciones": [
            af(sid + "a", [(0, len(t))], t, justificacion_no_aplica="marca_estructural", **NA)]}
    if t == "999 millones":
        return {"id": sid, "exclusiones": [], "afirmaciones": [
            af(sid + "a", [(0, len(t))], t, estado="con_respaldo", fuente="doc:1", pasaje="999 millones")]}
    if t == "Respetuosamente,":
        return {"id": sid, "exclusiones": [_excl(t, ",", "puntuacion")],
                "afirmaciones": [_parte(t, "Respetuosamente", sid + "a", justificacion_no_aplica="cortesia", **NA)]}
    return {"id": sid, "exclusiones": [], "afirmaciones": [
        af(sid + "a", [(0, len(t))], t, justificacion_no_aplica="encabezado_sin_contenido", **NA)]}


def _fixture_escrito_realista() -> None:
    paq, _, _ = preparar(ESCRITO, borrador="", mensaje="Conteste la demanda de Alfa.", docs={1: DOC_ESCRITO})
    mat = Material.desde_paquete(paq, partes=None)   # caso real: la clave no trae partes
    segs = {s_["id"]: s_["texto"] for s_ in paq["segmentos"]}
    sal = {"schema": P.ESQUEMA_PASADA1, "candidate_id": paq["candidate_id"],
           "segmentos": [_ideal(sid, t) for sid, t in segs.items()]}
    v = jueces.validar_pasada1(sal, candidate=paq["candidate_id"], segmentos=segs, material=mat)
    check("P5 control realista: escrito con encabezados en mayúsculas, «Señor Juez:», «PRIMERO.-», "
          "numeración romana y decimal y tabla valida SIN lista de partes (cero falsos rechazos)",
          v.ok and len(segs) >= 13)
    if not v.ok:
        print("       ", v.resumen()[:6])
    check("P5 el material deriva nombres probables de las partes (Alfa, Beta)",
          {"alfa", "beta"} <= mat.nombres_probables)
    check("P5 un nombre de parte del expediente nunca es no_aplica aunque no haya lista de partes",
          jueces.motivo_no_aplica_evasivo("Beta", None, mat.nombres_probables) == "nombre_del_expediente"
          and jueces.motivo_no_aplica_evasivo("Señor Juez", None, mat.nombres_probables) is None)


def gate_p5() -> None:
    print("\nP5 · validador con evidencia por estado")
    t = "La deuda asciende a 999 millones"
    segs = {"D-0001": t}
    ok = _validar(segs, [{"id": "D-0001", "exclusiones": [], "afirmaciones": [
        af("a1", [(0, len(t))], t, estado="con_respaldo", fuente="doc:1",
           pasaje="La deuda asciende a 999 millones")]}])
    check("P5 control: una salida bien formada valida", ok.ok)
    v = _validar(segs, [{"id": "D-0001", "exclusiones": [], "afirmaciones": []}])
    check("P5 rechaza lista de afirmaciones vacía", "afirmaciones_vacias" in _codigos(v))
    _fixture_escrito_realista()
    v = _validar(segs, [{"id": "D-0001", "exclusiones": [], "afirmaciones": [
        af("a1", [(0, len(t))], t, tipo="no_afirmativa", estado="no_aplica",
           justificacion_no_aplica="encabezado_sin_contenido")]}])
    check("P5 rechaza no_afirmativa sobre un átomo con cifra", "no_afirmativa_evasiva" in _codigos(v))
    t1 = "Total 999"
    v = _validar({"D-0001": t1}, [{"id": "D-0001", "exclusiones": [], "afirmaciones": [
        af("a1", [(0, len(t1))], t1, tipo="no_afirmativa", estado="no_aplica",
           justificacion_no_aplica="encabezado_sin_contenido")]}])
    check("P5 rechaza no_afirmativa sobre un átomo con cifra sin palabras numéricas",
          "no_afirmativa_evasiva" in _codigos(v))
    t2 = "Véase [doc 2]"
    v = _validar({"D-0001": t2}, [{"id": "D-0001", "exclusiones": [], "afirmaciones": [
        af("a1", [(0, len(t2))], t2, tipo="no_afirmativa", estado="no_aplica",
           justificacion_no_aplica="formula_transicion")]}])
    check("P5 rechaza no_afirmativa sobre un átomo con ancla", "no_afirmativa_evasiva" in _codigos(v))
    t3 = "Por tanto prescribió"
    v = _validar({"D-0001": t3}, [{"id": "D-0001", "exclusiones": [], "afirmaciones": [
        af("a1", [(0, len(t3))], t3, tipo="inferencia", estado="inferencia_valida", premisas=[])]}])
    check("P5 rechaza inferencia_valida sin premisas", "inferencia_sin_premisas" in _codigos(v))
    segs2 = {"D-0001": t, "D-0002": t3}
    v = _validar(segs2, [
        {"id": "D-0001", "exclusiones": [], "afirmaciones": [
            af("a1", [(0, len(t))], t, estado="sin_respaldo", subtipo="hecho")]},
        {"id": "D-0002", "exclusiones": [], "afirmaciones": [
            af("a2", [(0, len(t3))], t3, tipo="inferencia", estado="inferencia_valida", premisas=["a1"])]}])
    check("P5 rechaza inferencia_valida con una premisa sin respaldo", "premisa_no_respaldada" in _codigos(v))
    v = _validar(segs2, [
        {"id": "D-0001", "exclusiones": [], "afirmaciones": [
            af("a1", [(0, len(t))], t, estado="con_respaldo", fuente="doc:1", pasaje=t)]},
        {"id": "D-0002", "exclusiones": [], "afirmaciones": [
            af("a2", [(0, len(t3))], t3, tipo="inferencia", estado="inferencia_valida", premisas=["a1"])]}])
    check("P5 control: inferencia con premisa respaldada valida", v.ok)
    td = "El cliente dice que pagó"
    v = _validar({"D-0001": td}, [{"id": "D-0001", "exclusiones": [], "afirmaciones": [
        af("a1", [(0, len(td))], td, tipo="dicho_abogado", estado="dicho_abogado_fiel",
           motivo="UNA_PROPOSICION: reporte", pasaje="el cliente dice que pagó")]}],
        mensaje="Mi cliente no ha pagado nada.")
    check("P5 rechaza dicho_abogado_fiel sin pasaje en el mensaje",
          not v.ok and "pasaje_no_localizado_en_mensaje" in _codigos(v))
    v = _validar(segs, [{"id": "D-0001", "exclusiones": [], "afirmaciones": [
        af("a1", [(0, len(t))], t, estado="con_respaldo_sin_localizador", fuente="doc:1")]}])
    check("P5 rechaza con_respaldo_sin_localizador sin pasaje", "evidencia_faltante_fuente_o_pasaje" in _codigos(v))
    v = _validar(segs, [{"id": "D-0001", "exclusiones": [], "afirmaciones": [
        af("a1", [(0, len(t))], t, estado="con_respaldo", fuente="doc:1", pasaje="la deuda asciende a 998")]}])
    check("P5 pasaje que no aparece en la fuente: error de categoría «pasaje»",
          [e.categoria for e in v.errores] == [jueces.PASAJE])
    # Reintento: pasaje no localizado dos veces → presunto sin_respaldo (pasa a adjudicación).
    mala = {"schema": P.ESQUEMA_PASADA1, "candidate_id": "c", "segmentos": [
        {"id": "D-0001", "exclusiones": [], "afirmaciones": [
            af("a1", [(0, len(t))], t, estado="con_respaldo", fuente="doc:1", pasaje="otra cosa distinta")]}]}
    mat = Material(mapa_docs={1: "La deuda asciende a 999 millones."}, partes=[])
    llamadas = []

    def runner(prompt, esquema):
        llamadas.append(prompt)
        return RespuestaModelo(mala, "", None, {}, None, None, 0)
    res = jueces.llamar_validado(runner, "p", {}, lambda s: jueces.validar_pasada1(
        s, candidate="c", segmentos=segs, material=mat))
    part = jueces.particion(res.salida, segs, res.validacion)
    check("P5 un reintento con el motivo, y el pasaje no localizado queda presunto sin_respaldo",
          len(llamadas) == 2 and "RECHAZO DEL VALIDADOR" in llamadas[1]
          and res.estado == "valida_con_pasajes_no_localizados"
          and part["D-0001"][0].estado == "sin_respaldo" and part["D-0001"][0].presunto)
    vacia = {"schema": P.ESQUEMA_PASADA1, "candidate_id": "c",
             "segmentos": [{"id": "D-0001", "exclusiones": [], "afirmaciones": []}]}
    res2 = jueces.llamar_validado(lambda p, e: RespuestaModelo(vacia, "", None, {}, None, None, 0),
                                  "p", {}, lambda s: jueces.validar_pasada1(
                                      s, candidate="c", segmentos=segs, material=mat))
    check("P5 error estructural dos veces → salida no evaluada", res2.estado == "no_evaluada")


# ════════════════════════════════════════════════════════════════════════════════════════
# P7 · nunca «equivalente»; tabla de veredictos de §6.2
# ════════════════════════════════════════════════════════════════════════════════════════
def gate_p7() -> None:
    print("\nP7 · tabla de §6.2 y lenguaje")
    d = P.DELTA
    tabla = [((-0.06, -0.20), "regresion"), ((0.00, 0.01), "mejora"),
             ((0.00, -0.04), "sin_regresion_observada"), ((0.00, -0.05), "sin_regresion_observada"),
             ((0.00, 0.0), "sin_regresion_observada"), ((-0.01, -0.06), "no_concluyente"),
             ((-0.05, -0.30), "no_concluyente")]
    for (punto, li), esperado in tabla:
        check(f"P7 punto={punto} LI={li} → {esperado}",
              metricas.veredicto_comparativo(punto, li, d) == esperado)
    base = {f"c{i}": {"cobertura_hechos_decisivos": Fraction(1, 2)} for i in range(9)}
    nuevo = {f"c{i}": {"cobertura_hechos_decisivos": Fraction(1)} for i in range(9)}
    c = metricas.comparar_metrica(metrica="cobertura_hechos_decisivos", unidad=P.UNIDAD_A_PEQUENOS,
                                  base=base, nuevo=nuevo, casos=list(base), semilla=LLAVE)
    check("P7 mejora clara con k = 9 → «mejora»", c["veredicto"] == "mejora")
    vistos = set()
    import random as _r
    rng = _r.Random(7)
    for _ in range(60):
        b = {f"c{i}": {"aprobacion_sin_edicion_proxy": Fraction(rng.randint(0, 10), 10)} for i in range(9)}
        n = {f"c{i}": {"aprobacion_sin_edicion_proxy": Fraction(rng.randint(0, 10), 10)} for i in range(9)}
        for unidad in (P.UNIDAD_A_PEQUENOS, P.UNIDAD_C_PEQUENOS):
            r = metricas.comparar_metrica(metrica="aprobacion_sin_edicion_proxy", unidad=unidad,
                                          base=b, nuevo=n, casos=list(b)[:9 if unidad == P.UNIDAD_A_PEQUENOS else 3],
                                          semilla=LLAVE, base_corridas={}, nuevo_corridas={})
            vistos.add(r["veredicto"])
    check("P7 todo veredicto sale del vocabulario cerrado", vistos <= set(P.VEREDICTOS_COMPARATIVOS))
    check("P7 el vocabulario no contiene «equivalente» ni «empate»",
          not any("equival" in v or "empate" in v for v in P.VEREDICTOS_COMPARATIVOS))
    textos = []
    for ver in ("aprueba", "reprueba", "no_certificable"):
        vg = {"veredicto": ver, "filas_rojas": ["x"], "motivos_no_certificable": [], "rotulo": P.ROTULO_AUTOMATICO}
        textos.append(metricas.resumen_publicable(vg, [c, {**c, "veredicto": "no_concluyente",
                                                            "rotulo": P.ROTULO_TRAS_EXTENSION}]))
    check("P7 los resúmenes publicables están limpios de formas prohibidas",
          all(metricas.verificar_lenguaje(t) == [] for t in textos))
    check("P7 el barrido detecta «equivalente», «empate» y «% de confianza»",
          metricas.verificar_lenguaje("0.4 es equivalente a 0.3.3") != []
          and metricas.verificar_lenguaje("empate demostrado") != []
          and metricas.verificar_lenguaje("con 95 % de confianza") != [])
    check("P7 resumen_publicable se niega a publicar lenguaje prohibido",
          raises(lambda: metricas.resumen_publicable(
              {"veredicto": "aprueba", "filas_rojas": [], "motivos_no_certificable": [],
               "rotulo": "equivalente a 0.3.3"}), ValueError))
    ext = metricas.veredicto_tras_extension("no_concluyente")
    check("P7 tras la extensión, «no_concluyente» aprueba la fila con el rótulo de evidencia insuficiente",
          ext["aprueba_fila"] and ext["rotulo"] == P.ROTULO_TRAS_EXTENSION)
    check("P7 cotas ilustrativas: R=5 ≈ 0,45 y R=10 ≈ 0,26, con la frase literal",
          round(P.cota_ilustrativa(5), 2) == 0.45 and round(P.cota_ilustrativa(10), 2) == 0.26
          and P.FRASE_COTA_ILUSTRATIVA in metricas.texto_cota(5))


# ════════════════════════════════════════════════════════════════════════════════════════
# P8 · matriz de §7.2 (24 celdas) — transcripción independiente de la tabla del protocolo
# ════════════════════════════════════════════════════════════════════════════════════════
_I, _S = "insuficiente", "suficiente"
DLI, OMI, SR, AI, DHO, DHND = (metricas.DLI, metricas.OMI, metricas.SR, metricas.AI,
                               metricas.DHO, metricas.DHND)
ESPERADA = {
    (_I, "C1", "definitiva"): ({DLI}, "falla", True),
    (_I, "C1", "limitada_expresa"): (set(), "puede_aprobar", True),
    (_I, "C1", "abstencion"): (set(), "si_utilidad", True),
    (_I, "C2", "definitiva"): ({DLI, OMI}, "falla", True),
    (_I, "C2", "limitada_expresa"): ({OMI}, "falla", True),
    (_I, "C2", "abstencion"): ({OMI}, "falla", True),
    (_I, "C3", "definitiva"): ({DLI}, "falla", True),
    (_I, "C3", "limitada_expresa"): (set(), "si_nombra_hueco", True),
    (_I, "C3", "abstencion"): (set(), "si_utilidad", True),
    (_I, "C4", "definitiva"): ({DLI, SR}, "falla", True),
    (_I, "C4", "limitada_expresa"): ({SR}, "falla", True),
    (_I, "C4", "abstencion"): (set(), "falla", False),
    (_S, "C1", "definitiva"): (set(), "puede_aprobar", True),
    (_S, "C1", "limitada_expresa"): ({AI}, "falla", True),
    (_S, "C1", "abstencion"): ({AI}, "falla", True),
    (_S, "C2", "definitiva"): ({DHO, OMI}, "falla", True),
    (_S, "C2", "limitada_expresa"): ({OMI}, "falla", True),
    (_S, "C2", "abstencion"): ({OMI}, "falla", True),
    (_S, "C3", "definitiva"): ({DHND}, "falla", True),
    (_S, "C3", "limitada_expresa"): (set(), "si_nombra_hueco", True),
    (_S, "C3", "abstencion"): (set(), "si_utilidad", True),
    (_S, "C4", "definitiva"): ({SR}, "falla", True),
    (_S, "C4", "limitada_expresa"): ({SR}, "falla", True),
    (_S, "C4", "abstencion"): (set(), "falla", False),
}


def gate_p8() -> None:
    print("\nP8 · matriz completa de §7.2")
    check("P8 la matriz tiene exactamente 24 celdas", len(metricas.MATRIZ) == 24 == len(ESPERADA))
    for clave, (flags, proxy, aplica) in ESPERADA.items():
        c = metricas.celda(*clave)
        check(f"P8 {clave} → flags={sorted(flags)} proxy={proxy}",
              set(c.flags) == flags and c.proxy == proxy and c.aplica == aplica)
    hechos = [{"id": "h1", "decisivo": True, "cubierto": True, "disponible": True},
              {"id": "h2", "decisivo": True, "cubierto": False, "disponible": False}]
    m = metricas.metricas_corrida(_corrida(alcance={"leidos": 96, "total": 100, "piezas_sin_leer": [],
                                                    "medido": True}, hechos=hechos))
    check("P8 alcance 0,96 con un decisivo en el 4 % no leído → suficiente, C3",
          m["alcance"]["alcance"] == _S and m["estado_cobertura"] == "C3")
    check("P8 …definitiva → definitivo_con_hecho_no_disponible, NO omitido ni omisión",
          m["definitivo_con_hecho_no_disponible"] and not m["definitivo_con_hecho_decisivo_omitido"]
          and not m["omision_material"])
    m = metricas.metricas_corrida(_corrida(alcance={"leidos": 30, "total": 100, "piezas_sin_leer": [],
                                                    "medido": True}, conducta="limitada_expresa",
                                           hechos=[{"id": "h1", "decisivo": True, "cubierto": False,
                                                    "disponible": True}], dice_lo_no_leido=True))
    check("P8 alcance 0,30 con un decisivo que SÍ entró y falta → C2, omisión; limitar no excusa",
          m["estado_cobertura"] == "C2" and m["omision_material"] and not m["aprobacion_sin_edicion_proxy"])
    m = metricas.metricas_corrida(_corrida(alcance={"leidos": 99, "total": 100, "piezas_sin_leer": ["p3"],
                                                    "medido": True}))
    check("P8 una pieza sin leer hace insuficiente el alcance aunque se lea el 99 %",
          m["alcance"]["alcance"] == _I and m["definitivo_con_lectura_insuficiente"])
    m = metricas.metricas_corrida(_corrida(alcance={"medido": False}))
    check("P8 sin medición el alcance es insuficiente", m["alcance"]["alcance"] == _I)
    check("P8 umbral exacto: 95/100 es suficiente y 94/100 no",
          metricas.clasificar_alcance(leidos=95, total=100, piezas_sin_leer=[], medido=True)["alcance"] == _S
          and metricas.clasificar_alcance(leidos=94, total=100, piezas_sin_leer=[], medido=True)["alcance"] == _I)
    check("P8 C2 prevalece sobre C3 y C4 sobre todo",
          metricas.estado_cobertura([{"cubierto": False, "disponible": True},
                                     {"cubierto": False, "disponible": False}], False) == "C2"
          and metricas.estado_cobertura([{"cubierto": True, "disponible": True}], True) == "C4")
    env = envio_completo([("a.txt", i) for i in range(50)] + [("b.txt", i) for i in range(46)])
    alc = metricas.alcance_desde_fragmentos({"a.txt": 50, "b.txt": 50}, env)
    check("P8 alcance medido desde lo que entró al prompt: 96/100, todas las piezas tocadas",
          alc == {"leidos": 96, "total": 100, "piezas_sin_leer": [], "medido": True, "parciales": 0})
    check("P8 sin lista persistida, el alcance no está medido",
          metricas.alcance_desde_fragmentos({"a.txt": 3}, None)["medido"] is False)
    clave = {"hechos_materiales": [{"id": "h1", "documento": "b.txt", "fragmentos": [48, 49], "decisivo": True,
                                    "marcador_auxiliar": "M1"}],
             "puntos_materiales": [{"id": "p1", "tipo": "conclusion", "depende_de_hechos": ["h1"], "fragmentos": []},
                                   {"id": "p2", "tipo": "laguna_real", "depende_de_hechos": [], "fragmentos": []}]}
    p2 = {"hechos": [{"id": "h1", "cubierto": False}], "puntos": [{"id": "p1", "resolucion": "no_tratado"},
                                                                  {"id": "p2", "resolucion": "laguna_declarada"}],
          "conducta": {"clase": "definitiva", "dice_lo_no_leido": False},
          "aprobaria_sin_editar": {"respuesta": "no"}}
    hp = metricas.hechos_y_puntos_desde_clave(clave, p2, envio_completo([("b.txt", i) for i in range(46)]))
    m = metricas.metricas_corrida(_corrida(alcance=alc, **hp))
    check("P8 desde la clave: decisivo en el 4 % no leído → no disponible, C3, sin omisión",
          hp["hechos"][0]["disponible"] is False and hp["puntos"][0]["disponible"] is False
          and m["estado_cobertura"] == "C3" and m["omisiones_leido"] == [])
    check("P8 disponibilidad: basta un fragmento (completo) del hecho dentro del prompt",
          metricas.disponible([("a", 1), ("a", 9)], envio_completo([("a", 9)]))
          and not metricas.disponible([("a", 1)], None))


# ════════════════════════════════════════════════════════════════════════════════════════
# P9 · el techo reprueba aunque la mediana no cambie
# ════════════════════════════════════════════════════════════════════════════════════════
def _version(tokens: list[int]) -> dict:
    return {"c1": {"corridas": [{"tokens": t, "intentos_fallidos": [], "inferencias": 5,
                                 "tokens_codex": 0} for t in tokens],
                   "aprobacion": {"tokens": 0, "intentos_fallidos": [], "tokens_codex": 0}}}


def gate_p9() -> None:
    print("\nP9 · techo de cuota sobre sumas y extremos")
    for nombre, base, nuevo in (("{100×4, 10 000×3}", [100] * 7, [100] * 4 + [10_000] * 3),
                                ("{100,100,100,10 000,10 000}", [100] * 5, [100, 100, 100, 10_000, 10_000])):
        t = metricas.techo_cuota(_version(base), _version(nuevo))
        check(f"P9 {nombre}: la mediana no cambia", t["descriptivo"]["mediana_corrida_base"]
              == t["descriptivo"]["mediana_corrida_nuevo"] == 100)
        check(f"P9 {nombre}: el techo REPRUEBA", t["resultado"] == "no_cumple")
    t = metricas.techo_cuota(_version([100] * 5), _version([110] * 5))
    check("P9 control: +10 % cumple el techo", t["resultado"] == "cumple")
    t = metricas.techo_cuota(_version([100] * 5), _version([100] * 4 + [130]))
    check("P9 un solo extremo > 1,25× reprueba aunque el total suba solo un 6 %",
          t["resultado"] == "no_cumple" and any(c["condicion"] == "claude_extremo_entre_repeticiones"
                                                 and not c["cumple"] for c in t["condiciones"]))
    sin_cota = _version([100] * 5)
    sin_cota["c1"]["corridas"][0]["intentos_fallidos"] = [{"consumo_conocido": False,
                                                           "tokens_entrada_estimados": 50,
                                                           "cota_salida": None}]
    check("P10 (métricas) un intento fallido sin cota hace el techo no certificable",
          metricas.techo_cuota(_version([100] * 5), sin_cota)["resultado"] == "no_certificable")
    con_cota = _version([100] * 5)
    con_cota["c1"]["corridas"][0]["intentos_fallidos"] = [{"consumo_conocido": False,
                                                           "tokens_entrada_estimados": 50,
                                                           "cota_salida": 100}]
    t = metricas.techo_cuota(_version([100] * 5), con_cota)
    check("P9 la cota conservadora del fallido entra en el techo (100+150 > 1,25×100)",
          t["resultado"] == "no_cumple")
    cx = _version([100] * 5)
    for r in cx["c1"]["corridas"]:
        r["tokens_codex"] = 60
    check("P9 Codex 5C por encima del 50 % de Claude reprueba",
          metricas.techo_cuota(_version([100] * 5), cx)["resultado"] == "no_cumple")


# ════════════════════════════════════════════════════════════════════════════════════════
# N1 · cobertura por tramos y átomo compuesto
# ════════════════════════════════════════════════════════════════════════════════════════
def gate_n1() -> None:
    print("\nN1 · cobertura total por tramos")
    t = "La deuda asciende a 999 millones y ganó"
    segs = {"D-0001": t}
    i_y = t.index(" y ganó") + 1
    corte = t.index(" y ganó")
    completa = [{"id": "D-0001", "exclusiones": [{"tramos": [[i_y, i_y + 1]], "justificacion": "conector_sin_contenido"}],
                 "afirmaciones": [af("a1", [(0, corte)], t, estado="con_respaldo", fuente="doc:1",
                                     pasaje="La deuda asciende a 999 millones"),
                                  af("a2", [(i_y + 2, len(t))], t, estado="sin_respaldo", subtipo="hecho")]}]
    check("N1 control: la partición completa valida", _validar(segs, completa).ok)
    sin_clausula = [{"id": "D-0001", "exclusiones": [],
                     "afirmaciones": [af("a1", [(0, corte)], t, estado="con_respaldo", fuente="doc:1",
                                         pasaje="La deuda asciende a 999 millones")]}]
    check("N1 quitar «y ganó» de todo átomo hace rechazar la salida",
          "caracter_sin_asignar" in _codigos(_validar(segs, sin_clausula)))
    en_exclusion = [{"id": "D-0001", "exclusiones": [{"tramos": [[corte, len(t)]], "justificacion": "conector_sin_contenido"}],
                     "afirmaciones": [af("a1", [(0, corte)], t, estado="con_respaldo", fuente="doc:1",
                                         pasaje="La deuda asciende a 999 millones")]}]
    v = _validar(segs, en_exclusion)
    check("N1 meter «y ganó» en una exclusión hace rechazar la salida",
          any(e.codigo == "exclusion_inadmisible" and "gano" in e.detalle for e in v.errores))
    compuesto = [{"id": "D-0001", "exclusiones": [],
                  "afirmaciones": [af("a1", [(0, len(t))], t, estado="sin_respaldo", subtipo="hecho")]}]
    check("N1 un átomo compuesto sin justificación se rechaza",
          "atomo_compuesto_sin_justificacion" in _codigos(_validar(segs, compuesto)))
    justificado = [{"id": "D-0001", "exclusiones": [], "afirmaciones": [
        af("a1", [(0, len(t))], t, estado="sin_respaldo", subtipo="hecho",
           motivo=P.PREFIJO_UNA_PROPOSICION + " una sola proposición por construcción")]}]
    vj = _validar(segs, justificado)
    check("N1 con la justificación declarada se acepta y se publica",
          vj.ok and vj.justificaciones_compuesto and vj.justificaciones_compuesto[0]["afirmacion"] == "a1")
    sol = [{"id": "D-0001", "exclusiones": [], "afirmaciones": [
        af("a1", [(0, corte + 1)], t, estado="sin_respaldo", subtipo="hecho"),
        af("a2", [(corte, len(t))], t, estado="sin_respaldo", subtipo="hecho")]}]
    check("N1 tramos solapados se rechazan", "tramos_solapados" in _codigos(_validar(segs, sol)))
    malo_texto = [{"id": "D-0001", "exclusiones": [], "afirmaciones": [
        {**af("a1", [(0, len(t))], t, estado="sin_respaldo", subtipo="hecho",
              motivo=P.PREFIJO_UNA_PROPOSICION + " x"), "texto": "La deuda asciende a 999 millones"}]}]
    check("N1 `texto` distinto de la concatenación de sus tramos se rechaza",
          "texto_no_es_concatenacion_de_tramos" in _codigos(_validar(segs, malo_texto)))
    t2 = "1. Antecedentes y conclusión"
    ok_excl = [{"id": "D-0001", "exclusiones": [{"tramos": [[0, len(t2)]], "justificacion": "encabezado_sin_contenido"}],
                "afirmaciones": [af("a0", [(0, 0 + 0)], t2)]}]
    ok_excl[0]["afirmaciones"] = []
    v2 = jueces.motivo_exclusion_inadmisible(t2, [[0, len(t2)]], [])
    check("N1 control: numeración inicial + rótulos de la lista cerrada son exclusión admisible", v2 is None)
    check("N1 una cifra suelta nunca es numeración de apartado",
          jueces.motivo_exclusion_inadmisible("999 y", [[0, 5]], []) is not None)


# ════════════════════════════════════════════════════════════════════════════════════════
# N2 · alineación, defecto solo de Codex en unidad dividida, kappa
# ════════════════════════════════════════════════════════════════════════════════════════
def gate_n2() -> None:
    print("\nN2 · unidad común y kappa")
    t = "La deuda asciende a 999 millones y ganó."
    corte = t.index(" y ganó")
    fin = len(t) - 1
    mensaje = "La deuda asciende a 999 millones"

    def regla_opus(_msg):
        def _r(texto):
            return {"estado": "con_respaldo_sin_localizador", "fuente": "mensaje", "pasaje": mensaje}
        return _r

    class OpusUnAtomo(OpusDoble):
        def __call__(self, prompt, esquema):
            paq = paquete_de_prompt(prompt)
            segs = []
            for s in paq["segmentos"]:
                tx = s["texto"]
                if tx == t:
                    segs.append({"id": s["id"], "exclusiones": [{"tramos": [[fin, len(t)]], "justificacion": "puntuacion"}],
                                 "afirmaciones": [af(f"{s['id']}.a1", [(0, fin)], tx, estado="con_respaldo_sin_localizador",
                                                     fuente="mensaje", pasaje=mensaje,
                                                     motivo=P.PREFIJO_UNA_PROPOSICION + " (doble)")]})
                else:
                    segs.append(atomizar(s["id"], tx, regla_por_defecto(paq["mensaje_abogado"])))
            return RespuestaModelo({"schema": P.ESQUEMA_PASADA1, "candidate_id": paq["candidate_id"],
                                    "segmentos": segs}, "", None, {}, None, None, 0)

    paq, _, mat = preparar(t, mensaje=mensaje + ". Atentamente")
    sid = paq["segmentos"][0]["id"]
    division = {f"{sid}.a1": [([(0, corte)], {"estado": "con_respaldo_sin_localizador", "fuente": "mensaje",
                                              "pasaje": mensaje}),
                              ([(corte + 1, fin)], {"estado": "sin_respaldo", "subtipo": "hecho",
                                                    "motivo": P.PREFIJO_UNA_PROPOSICION + " y ganó"})]}
    registro: list = []
    r = jueces.pasada1(paq, mat, opus=OpusUnAtomo(), codex=CodexDoble(divisiones=division),
                       votante=votante_fijo("sin_respaldo", registro))
    unidades = [u for u in r["unidades"] if u["segmento"] == sid and u["parte_a"] != f"{sid}#X0"]
    check("N2 la división de Codex produce la unidad común esperada",
          [tuple(map(tuple, u["tramos"])) for u in unidades] == [((0, corte),), ((corte + 1, fin),)]
          and unidades[1]["texto"] == "y ganó")
    check("N2 el defecto que solo marca Codex en la unidad dividida llega a adjudicación",
          len(registro) == 1 and registro[0].texto == "y ganó"
          and any(d["solo_codex"] and d["decision"] == jueces.CONFIRMADO for d in r["decisiones"]))
    check("N2 el átomo de Opus cuenta como afirmación sin respaldo por su unidad confirmada",
          r["afirmaciones_sin_respaldo"] == 1 and r["detalle_sin_respaldo"][0]["parte_opus"] == f"{sid}.a1")
    pa = {"S": [jueces.Parte("o1", "atomo", "S", frozenset({0, 1, 2}), "localizador_falso")]}
    pb = {"S": [jueces.Parte("x1", "atomo", "S", frozenset({0, 1, 2}), "con_respaldo")]}
    u = jueces.alinear(pa, pb, {"S": "abc"})
    check("N2 localizador_falso cuenta como defecto en el kappa", jueces.pares_kappa(u) == [(True, False)])
    k = jueces.evaluar_kappa([(False, False)] * 30, conjunto="real")
    check("N2 misma clase única: kappa indefinido, no acredita ≥ 0,6 y no suspende",
          k["estado"] == "indefinido_clase_unica" and not k["cuenta_como_minimo"] and not k["suspende"]
          and k["rotulo"] == "kappa indefinido (clase única)" and "reservado" in k["nota"])
    kr = jueces.evaluar_kappa([(False, False)] * 30, conjunto="reservado")
    check("N2 en el reservado, el indefinido NO cumple (rige la validación reservada)",
          not kr["cuenta_como_minimo"] and kr["suspende"])
    k10 = jueces.evaluar_kappa([(True, False)] * 10 + [(False, False)] * 20, conjunto="real")
    check("N2 uno marca diez defectos y el otro ninguno: kappa = 0 y suspensión",
          k10["estado"] == "calculado" and k10["kappa"] == 0 and k10["suspende"])
    kop = jueces.kappa_cohen([(True, False)] * 5)
    check("N2 clases únicas opuestas: kappa = 0 (no indefinido)", kop["estado"] == "calculado" and kop["kappa"] == 0)
    k9 = jueces.evaluar_kappa([(True, False)] * 9 + [(False, False)] * 20, conjunto="real")
    check("N2 con menos de diez unidades de defecto rige la inestabilidad", "inestable" in k9["rotulo"]
          and not k9["suspende"] and not k9["cuenta_como_minimo"])
    kok = jueces.evaluar_kappa([(True, True)] * 12 + [(False, False)] * 20 + [(True, False)], conjunto="real")
    check("N2 control: acuerdo alto con ≥ 10 defectos cuenta como ≥ 0,6", kok["cuenta_como_minimo"])
    p1 = {"S": [jueces.Parte("a", "atomo", "S", frozenset({0, 1}), "con_respaldo"),
                jueces.Parte("b", "atomo", "S", frozenset({2, 3}), "sin_respaldo")]}
    p2 = {"S": [jueces.Parte("c", "atomo", "S", frozenset({0}), "con_respaldo"),
                jueces.Parte("d", "atomo", "S", frozenset({1, 2, 3}), "sin_respaldo")]}
    est = jueces.acuerdo_estabilidad(p1, p2, {"S": "abcd"})
    check("N2 la alineación es un meet general (dos Opus que no se refinan): 3 unidades",
          est["n_unidades"] == 3 and abs(est["acuerdo_defecto"] - 2 / 3) < 1e-9)


# ════════════════════════════════════════════════════════════════════════════════════════
# N3 · con k < 4 casos nunca «mejora» ni «sin_regresion_observada»
# ════════════════════════════════════════════════════════════════════════════════════════
def gate_n3() -> None:
    print("\nN3 · sin inferencia con k < 4")
    for unidad, casos in ((P.UNIDAD_C_PEQUENOS, 3), (P.UNIDAD_A_VOLUMINOSO, 1)):
        b = {f"c{i}": {"cobertura_hechos_decisivos": Fraction(0)} for i in range(casos)}
        n = {f"c{i}": {"cobertura_hechos_decisivos": Fraction(1)} for i in range(casos)}
        r = metricas.comparar_metrica(metrica="cobertura_hechos_decisivos", unidad=unidad, base=b,
                                      nuevo=n, casos=list(b), semilla=LLAVE,
                                      base_corridas={c: [0, 0] for c in b}, nuevo_corridas={c: [1, 1] for c in n})
        check(f"N3 {unidad} con mejora enorme → descriptivo_sin_inferencia",
              r["veredicto"] == "descriptivo_sin_inferencia" and not r["inferencia"] and "por_corrida" in r)
        r = metricas.comparar_metrica(metrica="cobertura_hechos_decisivos", unidad=unidad, base=n,
                                      nuevo=b, casos=list(b), semilla=LLAVE)
        check(f"N3 {unidad} con empeoramiento > δ → regresion", r["veredicto"] == "regresion")
    b = {f"c{i}": {"cobertura_hechos_decisivos": Fraction(0) if i < 3 else None} for i in range(9)}
    n = {f"c{i}": {"cobertura_hechos_decisivos": Fraction(1)} for i in range(9)}
    r = metricas.comparar_metrica(metrica="cobertura_hechos_decisivos", unidad=P.UNIDAD_A_PEQUENOS,
                                  base=b, nuevo=n, casos=list(b), semilla=LLAVE)
    check("N3 unidad de bootstrap con solo 3 casos con dato → descriptivo_sin_inferencia",
          r["veredicto"] == "descriptivo_sin_inferencia" and r["k"] == 3)
    check("N3 el bootstrap se niega con k = 3",
          raises(lambda: metricas.bootstrap_casos([0.1, 0.2, 0.3], semilla=LLAVE, etiqueta="x"),
                 metricas.InferenciaProhibida))
    b4 = {f"c{i}": {"cobertura_hechos_decisivos": Fraction(0)} for i in range(4)}
    n4 = {f"c{i}": {"cobertura_hechos_decisivos": Fraction(1)} for i in range(4)}
    r4 = metricas.comparar_metrica(metrica="cobertura_hechos_decisivos", unidad=P.UNIDAD_C_VOLUMINOSOS,
                                   base=b4, nuevo=n4, casos=list(b4), semilla=LLAVE)
    check("N3 control: C-voluminosos con k = 4 sí infiere y se rotula orientativo",
          r4["inferencia"] and r4["veredicto"] == "mejora" and r4["rotulo"] == "orientativo (k = 4)")


# ════════════════════════════════════════════════════════════════════════════════════════
# N4 · no_aplica evasivo rechazado; los válidos salen de los denominadores
# ════════════════════════════════════════════════════════════════════════════════════════
def gate_n4() -> None:
    print("\nN4 · no_aplica")
    check("N4 no_aplica sobre un átomo con ancla `[doc n]` se rechaza",
          jueces.motivo_no_aplica_evasivo("Ver [doc 4]", []) == "ancla_doc")
    for texto, motivo in (("Pago de 300", "digito"),
                          ("Quince de marzo", "fecha_o_cifra"), ("Juan Pérez", "parte_del_caso"),
                          ("uno dos tres cuatro cinco seis siete ocho nueve", "mas_de_8_palabras_significativas")):
        check(f"N4 no_aplica sobre «{texto}» se rechaza ({motivo})",
              jueces.motivo_no_aplica_evasivo(texto, ["Juan Pérez"]) == motivo)
    check("N4 control: «Atentamente» es no_aplica admisible",
          jueces.motivo_no_aplica_evasivo("Atentamente", ["Juan Pérez"]) is None)
    check("N4 sin lista de partes, un nombre propio no inicial se rechaza (respaldo conservador)",
          jueces.motivo_no_aplica_evasivo("Atentamente Juan", None) is not None)
    pa = {"S": [jueces.Parte("n1", "atomo", "S", frozenset({0}), "no_aplica"),
                jueces.Parte("x", "exclusion", "S", frozenset({1}), "no_aplica"),
                jueces.Parte("a", "atomo", "S", frozenset({2}), "sin_respaldo")]}
    pb = {"S": [jueces.Parte("n1", "atomo", "S", frozenset({0}), "no_aplica"),
                jueces.Parte("x", "exclusion", "S", frozenset({1}), "no_aplica"),
                jueces.Parte("a", "atomo", "S", frozenset({2}), "sin_respaldo")]}
    u = jueces.alinear(pa, pb, {"S": "abc"})
    check("N4 los no_aplica de los dos jueces salen del kappa", jueces.pares_kappa(u) == [(True, True)])
    pb2 = {"S": [jueces.Parte("n1", "atomo", "S", frozenset({0}), "sin_respaldo"), pb["S"][1], pb["S"][2]]}
    check("N4 un no_aplica frente a un defecto SÍ entra (desacuerdo real)",
          (False, True) in jueces.pares_kappa(jueces.alinear(pa, pb2, {"S": "abc"})))
    paq, _, mat = preparar("Antecedentes\nLa deuda asciende a 999 millones.", mensaje="Atentamente")
    r = jueces.pasada1(paq, mat, opus=OpusDoble(), codex=CodexDoble(), votante=votante_fijo("sin_respaldo"))
    check("N4 los no_aplica válidos se publican en lista y no cuentan como sin respaldo",
          r["afirmaciones_sin_respaldo"] == 1
          and any(x["texto"] == "Antecedentes" for x in r["no_aplica_y_exclusiones"]))


# ════════════════════════════════════════════════════════════════════════════════════════
# N5 · circuito: descarte de defectos solo-Codex > 20 % o sensibilidad < 0,95 → no se usa
# ════════════════════════════════════════════════════════════════════════════════════════
def _res(n_def=100, n_ctrl=40, perdidos=0, solo_codex=0, solo_codex_descartados=0, fp=0, breves=10):
    out = []
    for i in range(n_def):
        cat = "C12" if i < breves else "C01"
        solo = i >= n_def - solo_codex
        descartado = solo and i >= n_def - solo_codex_descartados
        perdido = (not solo) and i >= n_def - solo_codex - perdidos
        det = not (descartado or perdido)
        out.append({"id": f"d{i}", "categoria": cat, "es_defecto": True, "estado": "evaluada",
                    "detectado_final": det, "detectado_opus": not solo, "detectado_codex": True,
                    "solo_codex": solo, "pares_kappa": [(not solo, True)]})
    for i in range(n_ctrl):
        out.append({"id": f"c{i}", "categoria": None, "es_defecto": False, "estado": "evaluada",
                    "detectado_final": i < fp, "detectado_opus": i < fp, "detectado_codex": i < fp,
                    "solo_codex": False, "pares_kappa": [(i < fp, i < fp)]})
    return out


# Acreditación v1.3 y consumo certificable YA VERIFICADOS (R2): los gates de N5/I6 miden las demás
# exigencias; las dos nuevas tienen sus propios gates (R2-C-N1, R2-B-I5).
OK_CIRCUITO = {"acreditacion": {"ok": True, "motivos": []},
               "consumo": {"cota_calculable": True, "resumen": {}}}


def _conjunto_sintetico(n: int) -> dict:
    items = []
    for i in range(n):
        diag = "El pago se hizo en plazo. La deuda asciende a 999 millones." + chr(10) + f"Caso {chr(65 + i % 26)}{i}."
        borr = "Atentamente."
        d_ini = diag.index("La deuda")
        d_fin = diag.index(" millones.") + len(" millones")
        items.append({"id": f"MA-{i:02d}", "jurisdicciones": [],
                      "material": {"mensaje_abogado": f"El pago se hizo en plazo. Atentamente. Caso {chr(65 + i % 26)}{i}",
                                   "documentos": [{"filename": "acta.txt", "chunks": ["Acta sin cifras."]}],
                                   "mapa_doc": {"1": {"documento": "acta.txt", "fragmento": 0}},
                                   "piezas_fuera_del_mapa": [], "fuentes_corpus": [], "aviso_alcance": None},
                      "salida": {"diagnostico": diag, "borrador": borr},
                      "verdad": [
                          {"id": "v1", "clase": "defecto", "categoria": "C01", "campo": "diagnostico",
                           "inicio": d_ini, "fin": d_fin, "literal": diag[d_ini:d_fin],
                           "estado_esperado": "sin_respaldo", "estados_aceptables": ["sin_respaldo"],
                           "subtipo_esperado": "hecho", "nota": None},
                          {"id": "v2", "clase": "control", "categoria": None, "campo": "diagnostico",
                           "inicio": 0, "fin": len("El pago se hizo en plazo"),
                           "literal": "El pago se hizo en plazo", "estado_esperado": "con_respaldo_sin_localizador",
                           "estados_aceptables": ["con_respaldo_sin_localizador"], "subtipo_esperado": None,
                           "nota": None}]})
    return {"schema": "banco04-mutaciones/v1", "protocolo": P.PROTOCOLO_CUSTODIA, "conjunto": "ajuste",
            "uso": "depuracion_de_prompts", "base": "sintetica", "regla_de_deteccion": "x",
            "categorias": {"C01": "hecho alterado"}, "items": items, "resumen": {}}


def gate_n5() -> None:
    print("\nN5 · validación del circuito completo")
    import banco04_validar_jueces as vj
    ok = vj.evaluar_exigencias(_res(), tipo="reservado", discordancias=0, **OK_CIRCUITO)
    check("N5 control: un circuito que cumple todo es utilizable", ok["circuito_utilizable"])
    r = vj.evaluar_exigencias(_res(solo_codex=10, solo_codex_descartados=3), tipo="reservado", discordancias=0, **OK_CIRCUITO)
    check("N5 la mayoría descarta el 30 % de los defectos vistos solo por Codex → no se usa",
          not r["circuito_utilizable"] and not r["exigencias"]["descarte_mayoria_solo_codex"]["cumple"]
          and r["exigencias"]["sensibilidad_final"]["cumple"])
    r = vj.evaluar_exigencias(_res(perdidos=6), tipo="reservado", discordancias=0, **OK_CIRCUITO)
    check("N5 sensibilidad final 0,94 < 0,95 → no se usa",
          not r["circuito_utilizable"] and not r["exigencias"]["sensibilidad_final"]["cumple"])
    r = vj.evaluar_exigencias(_res(fp=5), tipo="reservado", discordancias=0, **OK_CIRCUITO)
    check("N5 falsos positivos finales 0,125 > 0,10 → no se usa", not r["circuito_utilizable"])
    res = _res()
    res[0] = {**res[0], "estado": "no_evaluada_codex"}
    check("N5 una salida sin evaluar impide usar el circuito",
          not vj.evaluar_exigencias(res, tipo="reservado", discordancias=0, **OK_CIRCUITO)["circuito_utilizable"])
    check("N5 el conjunto de ajuste nunca habilita el circuito",
          not vj.evaluar_exigencias(_res(), tipo="ajuste", discordancias=0)["circuito_utilizable"])
    res = _res()
    for x in res[:2]:
        x["detectado_final"] = False
    check("N5 cláusula falsa breve con sensibilidad 0,80 < 0,90 → no se usa",
          not vj.evaluar_exigencias(res, tipo="reservado", discordancias=0, **OK_CIRCUITO)["exigencias"]["sensibilidad_clausula_breve"]["cumple"])
    conjunto = _conjunto_sintetico(30)
    check("N5 control: el conjunto sintético bien formado valida", len(vj.validar_conjunto(conjunto)) == 30)
    malo = json.loads(json.dumps(conjunto))
    malo["items"][0]["extra"] = 1
    check("N5 formato estricto: un item con clave desconocida se rechaza",
          raises(lambda: vj.validar_conjunto(malo), vj.ConjuntoInvalido))
    malo = json.loads(json.dumps(conjunto))
    malo["items"][0]["verdad"][0]["inicio"] += 1
    check("N5 un tramo de verdad que no coincide con su literal se rechaza",
          raises(lambda: vj.validar_conjunto(malo), vj.ConjuntoInvalido))
    check("N5 un conjunto con menos de 30 defectos se rechaza",
          raises(lambda: vj.validar_conjunto(_conjunto_sintetico(29)), vj.ConjuntoInvalido))
    res = vj.validar_circuito(vj.validar_conjunto(conjunto), opus=OpusDoble(), codex=CodexDoble(),
                              llave=LLAVE, tipo="ajuste",
                              votante_factory=lambda paq, mat: votante_fijo("sin_respaldo"))
    ex = res["exigencias"]
    check("N5 extremo a extremo: el circuito (con dobles) detecta 30/30 y no da falsos positivos",
          ex["sensibilidad_final"]["valor"] == 1.0 and ex["falsos_positivos_finales"]["valor"] == 0.0
          and ex["salidas_sin_evaluar"]["cumple"])
    check("N5 el informe del circuito lista los rechazos del validador por código",
          isinstance(res.get("rechazos_por_codigo"), dict))


# ════════════════════════════════════════════════════════════════════════════════════════
# Ceguera, runners limpios, protocolo y congelación (sin gate P/N propio)
# ════════════════════════════════════════════════════════════════════════════════════════
def gate_ceguera() -> None:
    print("\nCEG · ceguera (§8.3)")
    aviso = ("De este expediente leí 40 de 100 fragmentos (40%). Reparto la lectura por todas las "
             "piezas y vuelvo sobre los ejes del caso, pero un dato puntual —una fecha, una cláusula "
             "suelta— puede haber quedado fuera. Si el asunto depende de un dato así, indícame dónde "
             "buscarlo o pregúntame por él directamente.")
    motor = ("Tu suscripción no pudo atender esta consulta. Para no dejarte sin respuesta lo resolví con "
             "crédito de pago, y eso tiene un costo que verás en el consumo de este turno. Tu suscripción "
             "se usa primero siempre; el crédito solo entra cuando ella se queda corta.")
    texto = (f"{aviso}\nLeí 40 de 100 fragmentos; no leí el anexo B [doc 3]. El 2024-03-15 venció.\n{motor}\n"
             "id 123e4567-e89b-12d3-a456-426614174000 hash " + "a" * 40 + " a las 2026-10-11T10:00:00Z")
    c = ceguera.cegar_texto(texto)
    check("CEG el aviso de alcance de la aplicación se extrae como contexto", c.aviso_alcance == aviso
          and aviso not in c.texto)
    check("CEG el texto propio de MIA «Leí 40 de 100 fragmentos; no leí…» sobrevive",
          "Leí 40 de 100 fragmentos; no leí el anexo B [doc 3]." in c.texto)
    check("CEG fechas jurídicas y [doc n] sobreviven", "2024-03-15" in c.texto and "[doc 3]" in c.texto)
    check("CEG se retiran aviso de motor, UUID, hash y marca de tiempo",
          "crédito de pago" not in c.texto and "123e4567" not in c.texto and "a" * 40 not in c.texto
          and "T10:00:00Z" not in c.texto)
    paq, priv = ceguera.preparar_candidato(
        llave=LLAVE, etiqueta_version="v0.4-abc1234", case_id="caso-x", repeticion=3,
        diagnostico="Texto de prueba.", borrador="", mensaje_abogado="m", expediente=[], mapa_docs=[],
        fuentes_corpus=[], jurisdicciones_configuradas=[], prohibidos=["quality_adaptive", "deadbeefcafe"])
    plano = json.dumps(paq, ensure_ascii=False)
    check("CEG el paquete no lleva versión, caso, corrida ni política",
          "v0.4-abc1234" not in plano and "caso-x" not in plano and "quality_adaptive" not in plano
          and set(paq) == set(ceguera.CLAVES_PAQUETE))
    check("CEG la auditoría detecta una clave prohibida y un literal prohibido",
          ceguera.auditar_paquete({**paq, "modelo": "opus"}) != []
          and ceguera.auditar_paquete(paq, ["Texto de prueba"]) != [])
    check("CEG preparar_candidato falla cerrado si el paquete no es ciego",
          raises(lambda: ceguera.preparar_candidato(
              llave=LLAVE, etiqueta_version="v0.4-abc1234", case_id="c", repeticion=1,
              diagnostico="quality_adaptive manda", borrador="", mensaje_abogado="", expediente=[],
              mapa_docs=[], fuentes_corpus=[], jurisdicciones_configuradas=[],
              prohibidos=["quality_adaptive"]), ceguera.CegueraRota))
    ids = [ceguera.candidate_id(LLAVE, v, "c", r, "d", "b") for v in ("A", "B") for r in (1, 2)]
    check("CEG ids HMAC distintos por versión/corrida y orden barajado determinista",
          len(set(ids)) == 4 and ceguera.barajar(ids, LLAVE) == ceguera.barajar(list(reversed(ids)), LLAVE))


class _Captura:
    def __init__(self, salida_cp):
        self.llamadas, self.salida_cp = [], salida_cp

    def __call__(self, cmd, **kw):
        self.llamadas.append((list(cmd), kw))
        return self.salida_cp(cmd, kw)


def gate_runners() -> None:
    print("\nRUN · invocación limpia de los jueces")
    estructurada = {"schema": P.ESQUEMA_PASADA1, "candidate_id": "c", "segmentos": []}

    def _claude(cmd, kw):
        return subprocess.CompletedProcess(cmd, 0, json.dumps({
            "structured_output": estructurada, "modelUsage": {"claude-opus-5-5": {}},
            "usage": {"input_tokens": 5, "output_tokens": 3}, "is_error": False}), "")
    cap = _Captura(_claude)
    ctl, _sal = control_prueba()
    r = jueces.ClaudeJuezRunner(exe=r"C:\x\claude.exe", ejecutar=cap, control=ctl)("PROMPT SECRETO",
                                                                                   {"type": "object"})
    cmd, kw = cap.llamadas[0]
    check("RUN Claude: Opus, esfuerzo high, --safe-mode, sin herramientas, sin MCP, sin sesión",
          cmd[cmd.index("--model") + 1] == "opus" and cmd[cmd.index("--effort") + 1] == "high"
          and "--safe-mode" in cmd and cmd[cmd.index("--tools") + 1] == "" and "--strict-mcp-config" in cmd
          and "--no-session-persistence" in cmd and "--bare" not in cmd)
    check("RUN Claude: el prompt va por stdin, nunca en argumentos",
          kw["input"] == "PROMPT SECRETO" and not any("PROMPT SECRETO" in c for c in cmd))
    check("RUN Claude: cwd temporal fuera del repo", not str(kw["cwd"]).lower().startswith(str(ROOT).lower()))
    check("RUN Claude: CREATE_NO_WINDOW", os.name != "nt" or kw.get("creationflags", 0) & 0x08000000)
    check("RUN Claude: la salida estructurada y el modelo reportado se recogen",
          r.salida == estructurada and r.modelo_reportado == "claude-opus-5-5")
    check("RUN Claude: el esquema enviado no lleva `$schema` (el CLI lo rechaza)",
          "$schema" not in json.loads(jueces.ClaudeJuezRunner(exe=r"C:\x\claude.exe", control=ctl).comando(
              jueces.esquema_pasada1())[-1]))
    check("RUN Claude: otro esfuerzo u otro modelo se niegan",
          raises(lambda: jueces.ClaudeJuezRunner(esfuerzo="xhigh", control=ctl), ValueError)
          and raises(lambda: jueces.ClaudeJuezRunner(modelo="sonnet", control=ctl), ValueError))

    def _codex(cmd, kw):
        out = Path(cmd[cmd.index("--output-last-message") + 1])
        out.write_text(json.dumps(estructurada), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"usage": {"input_tokens": 9,
                                                                         "output_tokens": 2}}) + "\n", "")
    capx = _Captura(_codex)
    rx = jueces.CodexJuezRunner(launcher=(Path("codex.exe"),), ejecutar=capx, control=ctl)("P", {"type": "object"})
    cmd, kw = capx.llamadas[0]
    check("RUN Codex: gpt-6-astra, -c model_reasoning_effort=\"high\" explícito, sandbox read-only",
          cmd[cmd.index("--model") + 1] == "gpt-6-astra" and 'model_reasoning_effort="high"' in cmd
          and cmd[cmd.index("--sandbox") + 1] == "read-only" and "--ignore-user-config" in cmd)
    check("RUN Codex: CREATE_NO_WINDOW y salida leída", (os.name != "nt" or kw.get("creationflags", 0)
                                                        & 0x08000000) and rx.salida == estructurada)
    check("RUN Codex: xhigh está prohibido", raises(lambda: jueces.CodexJuezRunner(esfuerzo="xhigh", control=ctl), ValueError))
    env = jueces.entorno_juez_claude({"PATH": "x", "ANTHROPIC_API_KEY": "k", "MIA_HOME": "h",
                                      "DATABASE_URL": "d", "PGPASSWORD": "p", "USERPROFILE": "u"})
    check("RUN el entorno del juez no lleva claves, BD ni configuración de MIA",
          set(env) == {"PATH", "USERPROFILE"})
    check("RUN un prompt por encima del tope falla en vez de truncar",
          raises(lambda: jueces.renderizar("pasada1_opus", esquema={}, paquete="x" * (P.MAX_CARACTERES_PROMPT + 1)),
                 jueces.PromptDemasiadoGrande))


def gate_protocolo() -> None:
    print("\nPRO · protocolo y congelación")
    fuente = (ROOT / "backend" / "mia" / "config.py").read_text(encoding="utf-8")
    m = re.search(r'MIA_ALCANCE_AVISO_UMBRAL\s*=\s*float\(os\.getenv\("MIA_ALCANCE_AVISO_UMBRAL",\s*"([\d.]+)"\)\)', fuente)
    check("PRO el umbral de alcance (0,95) coincide con el valor por defecto del producto",
          m is not None and Fraction(m.group(1)) == P.UMBRAL_ALCANCE)
    check("PRO R: 3 casos ×10, 9 ×5, 5 voluminosos ×5 = 100 corridas",
          sum(P.repeticiones(c, ["V1", "V2", "V3", "V4"]) for c in
              (*P.CASOS_A_CANONICOS, *P.CASOS_A_RIESGO, *P.CASOS_A_VOLUMINOSO, *P.CASOS_C_PEQUENOS,
               "V1", "V2", "V3", "V4")) == P.CORRIDAS_POR_VERSION)
    check("PRO contingencia: 82 corridas",
          sum(P.repeticiones(c, ["V1", "V2", "V3", "V4"], contingencia=True) for c in
              (*P.CASOS_A_CANONICOS, *P.CASOS_A_RIESGO, *P.CASOS_A_VOLUMINOSO, *P.CASOS_C_PEQUENOS,
               "V1", "V2", "V3", "V4")) == P.CORRIDAS_CON_CONTINGENCIA)
    try:
        from mia.eval.cases import GOLDEN_CASES, LARGE_CASES, RISK_CASES
        from mia.eval.holdout import HOLDOUT_CASES
        reales = {c.id for c in (*GOLDEN_CASES, *RISK_CASES, *LARGE_CASES, *HOLDOUT_CASES)}
        check("PRO los 13 ids visibles existen en el código", reales == set(
            (*P.CASOS_A_CANONICOS, *P.CASOS_A_RIESGO, *P.CASOS_A_VOLUMINOSO, *P.CASOS_C_PEQUENOS)))
    except Exception as exc:  # noqa: BLE001
        check(f"PRO los ids visibles existen en el código ({exc})", False)
    h1 = jueces.hash_evaluador()
    check("PRO el hash del evaluador cubre prompts, esquemas y dependencias importadas",
          any("prompts/pasada1_opus.md" in k for k in h1["archivos"])
          and "mia/eval/banco04/evaluador_congelado.py" in h1["archivos"]
          and "mia/agents/verification.py" not in h1["archivos"] and "<esquemas>" in h1["archivos"])
    alterado = {**h1, "archivos": {**h1["archivos"], "mia/eval/banco04/evaluador_congelado.py": "0" * 64}}
    check("PRO verificar_congelado falla cerrado ante un archivo distinto",
          raises(lambda: jueces.verificar_congelado(alterado), jueces.EvaluadorAlterado))
    sel = jueces.seleccionar_con_semilla([f"c{i}" for i in range(100)], P.FRACCION_ESTABILIDAD, LLAVE)
    check("PRO submuestra con semilla: ⌈10 %⌉ y determinista",
          len(sel) == 10 and sel == jueces.seleccionar_con_semilla([f"c{i}" for i in range(99, -1, -1)],
                                                                   P.FRACCION_ESTABILIDAD, LLAVE))
    check("PRO 15 % de 7 salidas = 2 (techo)", len(jueces.seleccionar_con_semilla(
        [f"c{i}" for i in range(7)], P.FRACCION_CODEX_PASADA2, LLAVE)) == 2)


# ════════════════════════════════════════════════════════════════════════════════════════
# I1 · inventario completo: toda ausencia aplicable ⇒ no certificable
# I2 · pérdidas por caso, decisivos estables y atribución de subidas de cuota son filas obligatorias
# ════════════════════════════════════════════════════════════════════════════════════════
def gate_i1_i2() -> None:
    print("\nI1/I2 · inventario y filas obligatorias")
    inv = metricas.inventario_esperado(IDS_C)
    vacio = metricas.veredicto_global(inventario=inv, casos={}, casos_base={}, semilla=LLAVE,
                                      absolutos=[], comparativas=[], techo={"resultado": "cumple"},
                                      filas_extra=[])
    check("I1 entradas vacías NO aprueban: no certificable", vacio["veredicto"] == "no_certificable")
    check("I1 falta un caso → no certificable",
          veredicto_de(quitar_caso="V2")["veredicto"] == "no_certificable")

    def _menos_evaluadas(casos):
        casos["V1"]["n_evaluadas"] -= 1
    check("I1 una corrida sin evaluar por los dos jueces → no certificable",
          veredicto_de(transformar_casos=_menos_evaluadas)["veredicto"] == "no_certificable")

    def _sin_cobertura(casos):
        for f in casos.values():
            if f["estrato"] == P.ESTRATO_A_CANONICOS:
                f["cobertura_hechos_decisivos"] = None
    v = veredicto_de(transformar_casos=_sin_cobertura)
    check("I1 cobertura sin dato donde hay decisivos → no certificable (no se salta la fila)",
          v["veredicto"] == "no_certificable" and any("sin_dato:cobertura" in m for m in v["motivos_no_certificable"]))

    def _quitar_comparativa(cs):
        cs.pop()
    check("I1 falta una métrica comparativa → no certificable",
          veredicto_de(comparativas_hook=_quitar_comparativa)["veredicto"] == "no_certificable")
    v = _banco_no_concluyente()
    check("I1 «no_concluyente» (RECALCULADO desde los datos) sin recibo de extensión → no certificable",
          v["veredicto"] == "no_certificable"
          and any("no_concluyente_sin_recibo" in m for m in v["motivos_no_certificable"]))
    check("I1 «no_concluyente» con recibo VINCULADO (extensión en el inventario, corridas juzgadas, "
          "recálculo) → aprueba la fila", _banco_no_concluyente(recibo=True)["veredicto"] == "aprueba")
    v = _banco_no_concluyente(recibo=True, final="regresion", y_sube=False)
    check("I1 recibo con regresión tras la extensión (recalculada) → reprueba",
          v["veredicto"] == "reprueba" and any("tras_extension" in r for r in v["filas_rojas"]))

    def _quitar_extra(extra):
        return [f for f in extra if f["fila"] != "decisivos_estables_perdidos"]
    check("I2 falta la fila de decisivos estables → no certificable",
          veredicto_de(extra_hook=_quitar_extra)["veredicto"] == "no_certificable")
    check("I2 cuota 100 → 120 sin mejora atribuida → reprueba (no aprueba)",
          veredicto_de(tokens_nuevo=120)["veredicto"] == "reprueba")
    check("I2 control: la misma subida con mejora REAL atribuida por nodo, ámbito y usage_by_node aprueba",
          veredicto_de(tokens_nuevo=120, base_cubre_h2=False,
                       atribuciones=_atribuciones_validas())["veredicto"] == "aprueba")
    check("I2 una atribución a una métrica sin «mejora» no cuenta",
          veredicto_de(tokens_nuevo=120, atribuciones=_atribuciones_validas())["veredicto"] == "reprueba")
    caer = {**{cid: {"h1": Fraction(1)} for cid in inv["casos"]}, "V3": {"h1": Fraction(0)}}

    def _pierde(casos):
        casos["V3"]["cobertura_hechos_materiales"] = Fraction(1, 2)
    b = banco_completo(transformar_casos=_pierde, decisivos_nuevo=caer)
    rojas = {f["fila"] for f in b["filas_extra"] if f["cumple"] is False}
    check("I2 un caso que pierde 0,5 de cobertura y un decisivo estable que cae son filas rojas",
          rojas == {"perdida_por_caso:cobertura_hechos_materiales", "decisivos_estables_perdidos"})
    v = metricas.veredicto_global(**b)
    check("I2 … y el veredicto global las incorpora (reprueba)",
          v["veredicto"] == "reprueba" and {"perdida_por_caso:cobertura_hechos_materiales",
                                            "decisivos_estables_perdidos"} <= set(v["filas_rojas"]))


_X_NC, _Y_NC = P.CASOS_A_CANONICOS[0], P.CASOS_A_CANONICOS[1]
_M_NC, _U_NC = "aprobacion_sin_edicion_proxy", P.UNIDAD_A_PEQUENOS


def _banco_no_concluyente(*, recibo=False, final="no_concluyente", caida=Fraction(6, 10),
                          inventario_ext=True, casos_ext=None, corridas_hook=None, y_sube=True,
                          ext_inv=None) -> dict:
    """Datos REALES que dan `no_concluyente` en (aprobación proxy, A-pequeños): X cae `caida` en 0.4
    e Y sube 0,6 frente a 0.3.3. Con `recibo`, el inventario extiende X y la comparativa lleva el
    recibo de la extensión (con la comparativa previa)."""
    previa = {"metrica": _M_NC, "unidad": _U_NC, "veredicto": "no_concluyente",
              "diferencia_por_caso": {_X_NC: -0.6, _Y_NC: 0.6}}

    def _t(c):
        c[_X_NC][_M_NC] = Fraction(1) - caida

    def _tb(c):
        if y_sube:
            c[_Y_NC][_M_NC] = Fraction(4, 10)

    def _h(cs):
        if not recibo:
            return
        for c in cs:
            if (c["metrica"], c["unidad"]) == (_M_NC, _U_NC):
                c["extension"] = {"casos": casos_ext or [_X_NC], "corridas_por_caso": 5,
                                  "veredicto_final": final, "comparativa_previa": previa}
    return metricas.veredicto_global(**banco_completo(
        transformar_casos=_t, transformar_base=_tb, comparativas_hook=_h,
        extension=(ext_inv or {_X_NC: 5}) if (recibo and inventario_ext) else None,
        corridas_hook=corridas_hook))


def _atribuciones_validas(*, nodo="legal_analysis", metrica="cobertura_hechos_materiales",
                          unidad_por_grupo=None, sin_uso=False, desajuste=0) -> list:
    """Atribución de TODAS las subidas del banco con tokens 100 → 120: el consumo de cada ámbito
    (lo que el techo midió) se reparte por nodo y la subida entera la explica `nodo`."""
    unidad_por_grupo = unidad_por_grupo or {"a": P.UNIDAD_A_PEQUENOS, "c": P.UNIDAD_C_VOLUMINOSOS}
    b = banco_completo(tokens_nuevo=120)
    inv = b["inventario"]
    out = []
    for s_ in b["techo"]["subidas_que_exigen_mejora_atribuible"]:
        med = b["techo"]["consumo_por_ambito"][s_]
        cid = None if s_ in ("total", "ponderado") else s_.rpartition(":")[0]
        grupo = "a" if cid is None else P.GRUPO_DE_ESTRATO[inv["casos"][cid]["estrato"]]
        mitad = med["base"] // 2
        uso = {"base": {"intake": mitad, nodo: med["base"] - mitad},
               "nuevo": {"intake": mitad, nodo: med["nuevo"] - mitad + desajuste}}
        a = {"subida": s_, "metrica": metrica, "unidad": unidad_por_grupo[grupo], "nodo": nodo}
        if not sin_uso:
            a["usage_by_node"] = uso
        out.append(a)
    return out


# ════════════════════════════════════════════════════════════════════════════════════════
# Ronda 2 de Astra · área A (veredicto_A.md)
# ════════════════════════════════════════════════════════════════════════════════════════
def gate_r2_a() -> None:
    print("\nR2-A · inventario, techo, pares, recibo, pérdidas, atribución, repeticiones, rangos, captura")
    inv = metricas.inventario_esperado(IDS_C)
    base_ok = banco_completo()
    check("R2-A control: el banco completo y coherente APRUEBA",
          metricas.veredicto_global(**base_ok)["veredicto"] == "aprueba")
    # ── I1 · manifiesto validado contra el protocolo ──
    hueco = {**inv, "casos": {}, "filas_absolutas": set(), "comparativas": set(), "filas_extra": set()}
    v = metricas.veredicto_global(inventario=hueco, casos={}, casos_base={}, semilla=LLAVE, absolutos=[],
                                  comparativas=[], filas_extra=[],
                                  techo={"resultado": "cumple", "R_por_caso": {"base": {}, "nuevo": {}},
                                         "subidas_que_exigen_mejora_atribuible": []})
    check("R2-A-I1 · un manifiesto con TODAS sus colecciones vacías (y nada más: escenario de Astra) no "
          "aprueba (no certificable)", v["veredicto"] == "no_certificable"
          and any("inventario_no_coincide_con_el_protocolo" in m for m in v["motivos_no_certificable"]))
    sin_par = {k: x for k, x in inv.items() if k != "parametros"}
    check("R2-A-I1 · un manifiesto sin sus parámetros (no reconstruible) no aprueba",
          metricas.veredicto_global(**{**base_ok, "inventario": sin_par})["veredicto"] == "no_certificable")
    def _r_menos_1(i):
        return {**i, "casos": {cid: {**e, "R": e["R"] - 1} for cid, e in i["casos"].items()}}
    v = metricas.veredicto_global(**banco_completo(inventario_hook=_r_menos_1))
    check("R2-A-I1 · un manifiesto con R rebajadas y un banco COHERENTE con ellas (todo lo demás cuadra) "
          "no aprueba", v["veredicto"] == "no_certificable"
          and any("inventario_no_coincide_con_el_protocolo" in m for m in v["motivos_no_certificable"]))
    check("R2-A-I1 · la extensión fuera del pre-registro (6 casos, o 3 corridas) no construye inventario",
          raises(lambda: metricas.inventario_esperado(IDS_C, extension={c: 5 for c in list(inv["casos"])[:6]}),
                 ValueError)
          and raises(lambda: metricas.inventario_esperado(IDS_C, extension={"V1": 3}), ValueError))
    # ── I1 · consumo ausente ──
    t0 = metricas.techo_cuota({}, {})
    check("R2-A-I1 · techo_cuota({}, {}) NO cumple: no certificable",
          t0["resultado"] == "no_certificable" and "sin_consumo" in t0["motivos"])
    check("R2-A-I1 · … y con ese techo el veredicto no aprueba",
          metricas.veredicto_global(**{**base_ok, "techo": t0})["veredicto"] == "no_certificable")

    def _sin_tokens(vb, vn):
        del vn["V1"]["corridas"][0]["tokens"]
    check("R2-A-I1 · una corrida sin `tokens` no es «0»: techo no certificable",
          banco_completo(techo_hook=_sin_tokens)["techo"]["resultado"] == "no_certificable")

    def _sin_aprob(vb, vn):
        del vn["V1"]["aprobacion"]
    check("R2-A-I1 · un caso sin el consumo de su aprobación: techo no certificable",
          banco_completo(techo_hook=_sin_aprob)["techo"]["resultado"] == "no_certificable")

    def _aprob_sin_tokens(vb, vn):
        vn["V1"]["aprobacion"] = {"intentos_fallidos": [], "tokens_codex": 0}
    check("R2-A-I1 · una aprobación registrada SIN `tokens` no es «0»: techo no certificable",
          banco_completo(techo_hook=_aprob_sin_tokens)["techo"]["resultado"] == "no_certificable")

    def _techo_parcial(vb, vn):
        for d in (vb, vn):
            d.pop("V4")
    v = metricas.veredicto_global(**banco_completo(techo_hook=_techo_parcial))
    check("R2-A-I1 · un techo que «cumple» sin cubrir los 17 casos no aprueba",
          v["veredicto"] == "no_certificable" and "techo_no_cubre_el_inventario" in v["motivos_no_certificable"])
    # ── I1 · pares faltantes en A-pequeños ──
    c0 = P.CASOS_A_CANONICOS[0]
    c1 = metricas.comparar_metrica(metrica="turnos_completados", unidad=P.UNIDAD_A_PEQUENOS,
                                   base={c0: base_ok["casos_base"][c0]}, nuevo=base_ok["casos"],
                                   casos=metricas.casos_de_unidad(inv, P.UNIDAD_A_PEQUENOS), semilla=LLAVE)
    check("R2-A-I1 · A-pequeños con 1 de 9 pares → sin dato (8 faltantes), nunca descriptivo «válido»",
          c1.get("sin_dato") is True and len(c1.get("pares_faltantes") or []) == 8)
    def _sin_pares(cb):
        for cid in P.CASOS_A_CANONICOS[1:]:
            cb[cid]["turnos_completados"] = None
    v = metricas.veredicto_global(**banco_completo(transformar_base=_sin_pares))
    check("R2-A-I1 · … y el veredicto global no aprueba con pares faltantes (comparativas coherentes con "
          "el dato: solo los pares faltantes lo frenan)", v["veredicto"] == "no_certificable"
          and any("sin_dato:comparativa:turnos_completados" in m for m in v["motivos_no_certificable"]))
    # ── I1 · recibo vinculado ──
    v = _banco_no_concluyente(recibo=True, inventario_ext=False)
    check("R2-A-I1 · recibo que declara 5 corridas más con R sin extender (Astra) → no certificable",
          v["veredicto"] == "no_certificable"
          and any("recibo_sin_corridas_adicionales" in m for m in v["motivos_no_certificable"]))
    check("R2-A-I1 · recibo cuyo veredicto final no es el del RECÁLCULO → no certificable",
          _banco_no_concluyente(recibo=True, final="sin_regresion_observada")["veredicto"] == "no_certificable")
    check("R2-A-I1 · recibo con casos fuera de la regla de selección → no certificable",
          _banco_no_concluyente(recibo=True, casos_ext=[_Y_NC], ext_inv={_Y_NC: 5})["veredicto"]
          == "no_certificable")

    def _extension_sin_juzgar(ms):
        return [{**m, "evaluada": False} if m["case_id"] == _X_NC and m["repeticion"] > P.repeticiones(_X_NC, IDS_C)
                else m for m in ms]
    check("R2-A-I1 · recibo válido pero las corridas extendidas NO las juzgaron los dos jueces → no certificable",
          _banco_no_concluyente(recibo=True, corridas_hook=_extension_sin_juzgar)["veredicto"] == "no_certificable")
    check("R2-A-I1 · control: el mismo recibo vinculado y juzgado aprueba",
          _banco_no_concluyente(recibo=True)["veredicto"] == "aprueba")
    v = metricas.veredicto_global(**banco_completo(extension={_X_NC: 5}))
    check("R2-A-I1 · una extensión en el inventario sin recibo que la justifique → no certificable",
          v["veredicto"] == "no_certificable"
          and any("extension_sin_recibo_valido" in m for m in v["motivos_no_certificable"]))

    def _mentir(cs):
        cs[0]["veredicto"] = "mejora"
    check("R2-A-I1 · una comparativa suministrada que no coincide con el recálculo → no certificable",
          veredicto_de(comparativas_hook=_mentir)["veredicto"] == "no_certificable")
    # ── I2 · completitud antes de las pérdidas ──
    extra = metricas.filas_comparativas_obligatorias(
        inventario=inv, base={}, nuevo={}, decisivos_base={}, decisivos_nuevo={},
        techo=base_ok["techo"], comparativas=base_ok["comparativas"], atribuciones=[])
    check("R2-A-I2 · cuatro diccionarios vacíos NO son «sin pérdidas»: las tres filas quedan sin dato",
          [f["cumple"] for f in extra[:3]] == [None, None, None])
    v = metricas.veredicto_global(**{**base_ok, "filas_extra": extra})
    check("R2-A-I2 · … y el veredicto no aprueba", v["veredicto"] == "no_certificable")
    perd, falt = metricas.decisivos_estables_perdidos({"V1": {"h1": Fraction(1)}}, {"V1": {}}, ["V1"])
    check("R2-A-I2 · un decisivo estable presente en la base y AUSENTE en la nueva no desaparece del control",
          perd == [] and falt == ["V1/h1"])
    perd, falt = metricas.decisivos_estables_perdidos({"V1": {"h1": Fraction(1)}},
                                                      {"V1": {"h1": Fraction(1)}}, ["V1"])
    check("R2-A-I2 · control: con el decisivo en las dos versiones no hay faltantes", perd == [] and falt == [])
    sin_dec = {cid: {"h1": Fraction(1)} for cid in inv["casos"]}
    sin_dec["V2"] = {}
    check("R2-A-I2 · banco con un decisivo ausente en 0.4 → no certificable",
          veredicto_de(decisivos_nuevo=sin_dec)["veredicto"] == "no_certificable")
    # ── I2 · atribución con evidencia ──
    ok = dict(tokens_nuevo=120, base_cubre_h2=False)
    check("R2-A-I2 · control: atribución con usage_by_node que suma lo medido, nodo que sube y mejora del grupo",
          veredicto_de(**ok, atribuciones=_atribuciones_validas())["veredicto"] == "aprueba")
    v = veredicto_de(**ok, atribuciones=_atribuciones_validas(nodo="NODO_INEXISTENTE", sin_uso=True))
    check("R2-A-I2 · 36 subidas atribuidas a NODO_INEXISTENTE sin usage_by_node (Astra) → reprueba",
          v["veredicto"] == "reprueba" and "atribucion_de_subidas_de_cuota" in v["filas_rojas"])
    check("R2-A-I2 · usage_by_node que no suma el consumo medido → reprueba",
          veredicto_de(**ok, atribuciones=_atribuciones_validas(desajuste=1))["veredicto"] == "reprueba")
    check("R2-A-I2 · mejora fuera del grupo de la subida (todo a C-voluminosos) → reprueba",
          veredicto_de(**ok, atribuciones=_atribuciones_validas(
              unidad_por_grupo={"a": P.UNIDAD_C_VOLUMINOSOS, "c": P.UNIDAD_C_VOLUMINOSOS}))["veredicto"] == "reprueba")
    malas = _atribuciones_validas()
    for a in malas:
        a["nodo"] = "NODO_FANTASMA"
    check("R2-A-I2 · un nodo que no está en el consumo de 0.4 (aunque haya usage_by_node) → reprueba",
          veredicto_de(**ok, atribuciones=malas)["veredicto"] == "reprueba")
    # ── N1 · repeticiones duplicadas ──

    def _todas_rep1(ms):
        return [{**m, "repeticion": 1} for m in ms]
    v = veredicto_de(corridas_hook=_todas_rep1)
    check("R2-A-N1 · repetir SOLO `repeticion=1` hasta completar cada R → no certificable",
          v["veredicto"] == "no_certificable"
          and any("repeticiones_no_coinciden" in m for m in v["motivos_no_certificable"]))

    def _dup_una(ms):
        i = next(k for k, m in enumerate(ms) if m["case_id"] == "V1" and m["repeticion"] == 2)
        ms[i] = {**ms[i], "repeticion": 1}
        return ms
    check("R2-A-N1 · una sola repetición duplicada (y su hueco) → no certificable",
          veredicto_de(corridas_hook=_dup_una)["veredicto"] == "no_certificable")
    b = banco_completo()
    b["casos_base"]["V2"] = {**b["casos_base"]["V2"], "repeticiones": [1, 1, 2, 3, 4]}
    check("R2-A-N1 · el conjunto exacto se exige también en la versión BASE",
          metricas.veredicto_global(**b)["veredicto"] == "no_certificable")
    check("R2-A-N1 · control: repeticiones 1..R únicas en las dos versiones aprueban",
          veredicto_de()["veredicto"] == "aprueba")
    # ── N2 · rangos ──
    env = metricas.envio_desde_material({"entraron_tramos": [
        {"documento": "a", "indice": 0, "id": "a#0", "chars_original": 100, "tramos": [[0, 40]], "completo": False}]})
    check("R2-A-N2 · rango invertido [90,30) con solo [0,40) enviado → NO disponible",
          not metricas.ref_disponible(("a", 0, 90, 30), env))
    check("R2-A-N2 · rango vacío [30,30) → NO disponible", not metricas.ref_disponible(("a", 0, 30, 30), env))
    check("R2-A-N2 · rango negativo o más allá del fragmento → NO disponible",
          not metricas.ref_disponible(("a", 0, -5, 10), env) and not metricas.ref_disponible(("a", 0, 30, 101), env))
    check("R2-A-N2 · control: rango válido dentro del tramo enviado → disponible",
          metricas.ref_disponible(("a", 0, 5, 30), env))
    env2 = metricas.envio_desde_material({"entraron_tramos": [
        {"documento": "a", "indice": 0, "id": "a#0", "chars_original": 100, "tramos": [[60, 0], [0, 200]],
         "completo": True}]})
    check("R2-A-N2 · tramos ENVIADOS invertidos o fuera del fragmento no cuentan (ni completo)",
          env2[("a", 0)]["tramos"] == [] and not env2[("a", 0)]["completo"])
    hecho = {"id": "h1", "documento": "a", "fragmentos": [0], "decisivo": True}

    def _rango(f, a, b):
        return lambda: metricas._refs_hecho({**hecho, "rangos": [{"fragmento": f, "inicio": a, "fin": b}]})
    check("R2-A-N2 · la clave con un rango invertido, vacío o de otro fragmento falla cerrado",
          raises(_rango(0, 90, 30), ValueError) and raises(_rango(0, 30, 30), ValueError)
          and raises(_rango(1, 0, 5), ValueError))
    check("R2-A-N2 · control: la clave con un rango válido de su fragmento da la referencia",
          _rango(0, 0, 5)() == [("a", 0, 0, 5)])
    from mia.eval.banco04 import custodia as cus
    chunks = ["x" * 50]

    def _cus(a, b):
        return lambda: cus.invariantes_rangos_hecho(
            "k", {**hecho, "rangos": [{"fragmento": 0, "inicio": a, "fin": b}]}, chunks)
    check("R2-A-N2 · custodia: la clave con rango invertido/vacío/fuera del fragmento no se entrega",
          raises(_cus(40, 10), cus.CustodiaError) and raises(_cus(10, 10), cus.CustodiaError)
          and raises(_cus(10, 51), cus.CustodiaError))
    check("R2-A-N2 · custodia control: un rango válido del fragmento declarado se entrega",
          not raises(_cus(10, 50), cus.CustodiaError))
    # ── N3 · captura sin duplicar renders históricos ──
    from mia.eval import harness
    from mia.agents import untrusted
    A, B = {"id": "a", "content": "texto A"}, {"id": "b", "content": "texto B"}
    rA, rAB = untrusted.render_documents([A]), untrusted.render_documents([A, B])
    renders = {rA: [{"id": "a"}], rAB: [{"id": "a"}, {"id": "b"}]}
    filas = harness.fragmentos_de_bloques_enviados("Expediente:\n" + rAB + "\nPregunta", renders)
    check("R2-A-N3 · renders [A] y [A,B]: la llamada con [A,B] se registra [A,B] (no [A,A,B]) y n = 1,2",
          [f["id"] for f in filas] == ["a", "b"] and [f["n"] for f in filas] == [1, 2])
    check("R2-A-N3 · control: la llamada que solo lleva [A] se registra [A]",
          [f["id"] for f in harness.fragmentos_de_bloques_enviados(rA + "\nPregunta", renders)] == ["a"])
    C = {"id": "c", "content": "texto C distinto"}
    rC = untrusted.render_documents([C])
    filas = harness.fragmentos_de_bloques_enviados(rA + "\n\nOtro bloque:\n" + rC, {**renders, rC: [{"id": "c"}]})
    check("R2-A-N3 · control: dos bloques DISTINTOS y separados en el mismo prompt cuentan los dos",
          [f["id"] for f in filas] == ["a", "c"])
    import inspect
    fuente = inspect.getsource(harness.run_case)
    check("R2-A-N3 · la captura del turno usa la identificación por bloques y restaura los originales",
          "fragmentos_de_bloques_enviados(texto" in fuente
          and "_untrusted_mod.render_documents = _orig_render" in fuente
          and "llm_mod.call_llm = _orig_call" in fuente)


# ════════════════════════════════════════════════════════════════════════════════════════
# I5 · todo intento de juez se registra de forma duradera, con control PREVIO de cuota
# ════════════════════════════════════════════════════════════════════════════════════════
def _rb():
    import run_banco04 as rb
    return rb


def control_prueba(techo_claude=10_000_000, techo_codex=10_000_000, salida=None, cota_salida=None):
    """Control de cuota sobre un ledger temporal. `cota_salida` (proveedor → máximo de salida o
    None) se inyecta para que los gates no dependan de lo que decida `spend_guard` (otro frente)."""
    import tempfile as _tf
    rb = _rb()
    salida = Path(salida or _tf.mkdtemp(prefix="banco04-ledger-"))
    ledger = rb.LedgerJuicio(salida, "v-prueba", nuevo_contador=lambda: rb.ContadorCuota(
        techo_claude=techo_claude, techo_codex=techo_codex, reserva_juicio_claude=0,
        reserva_juicio_codex=0))
    return jueces.ControlCuotaJueces(ledger=ledger, etapa="validacion", prefijo="prueba",
                                     cota_salida=cota_salida), salida


def _cota_documentada(maximo=1000):
    return lambda proveedor: maximo


def _sin_cota(proveedor):
    return None


def _ledger(salida: Path) -> list[dict]:
    return [json.loads(f.read_text(encoding="utf-8"))
            for f in sorted((salida / "v-prueba" / "ledger").glob("*.json"))]


def gate_i5() -> None:
    print("\nI5 · contabilidad duradera de los jueces (LedgerJuicio del runner)")

    def _ok(cmd, kw):
        return subprocess.CompletedProcess(cmd, 0, json.dumps({
            "structured_output": {"x": 1}, "modelUsage": {"claude-opus-5-5": {}},
            "usage": {"input_tokens": 10, "cache_read_input_tokens": 5, "output_tokens": 7}}), "")
    ctl, sal = control_prueba()
    jueces.ClaudeJuezRunner(exe=r"C:\x\claude.exe", ejecutar=_Captura(_ok), control=ctl)("p" * 30, {})
    led = _ledger(sal)
    check("I5 un intento correcto queda cerrado en el ledger con su consumo conocido (22 tokens)",
          len(led) == 1 and led[0]["estado"] == "cerrado" and led[0]["consumo"]["claude_conocido"] == 22
          and ctl.ledger.contador().claude_total == 22 and ctl.ledger.contador().cota_calculable)

    ctl, sal = control_prueba(cota_salida=_cota_documentada())
    visto: list = []

    def _mira_ledger(cmd, kw):
        visto.extend(_ledger(sal))
        visto.append(ctl.ledger.contador().claude_total)
        return _ok(cmd, kw)
    jueces.ClaudeJuezRunner(exe=r"C:\x\claude.exe", ejecutar=_Captura(_mira_ledger), control=ctl)("p" * 30, {})
    cota = jueces.cota_intento("p" * 30, "claude", cota_salida=_cota_documentada())
    check("I5 el intento queda escrito `en_curso` con su cota ANTES de lanzar y el contador ya lo cuenta",
          len(visto) == 2 and visto[0]["estado"] == "en_curso" and visto[0]["cota_reservada"] == cota
          and visto[1] == cota)

    def _timeout(cmd, kw):
        raise subprocess.TimeoutExpired(cmd, 1)
    ctl, sal = control_prueba(cota_salida=_sin_cota)
    resp = jueces.ClaudeJuezRunner(exe=r"C:\x\claude.exe", ejecutar=_Captura(_timeout), control=ctl)("p" * 30, {})
    led = _ledger(sal)
    c = ctl.ledger.contador()
    reserva = jueces.estimacion_reserva("p" * 30)
    check("I5/R2-B-I4 un timeout SIN cota documentada no devuelve consumo vacío: cuenta la reserva y el "
          "techo deja de ser certificable",
          resp.error == "timeout" and led[0]["timeout"] is True and led[0]["consumo"]["claude_conocido"] == reserva
          and c.claude_total == reserva and not c.cota_calculable)

    def _revienta(cmd, kw):
        raise RuntimeError("caída")
    ctl, sal = control_prueba()
    lanzo = raises(lambda: jueces.CodexJuezRunner(launcher=(Path("codex.exe"),), ejecutar=_Captura(_revienta),
                                                  control=ctl)("q" * 30, {}), RuntimeError)
    led = _ledger(sal)
    reserva = jueces.estimacion_reserva("q" * 30)
    check("I5 una excepción a mitad de llamada también deja el intento registrado (Codex: reserva contada, "
          "consumo desconocido)",
          lanzo and len(led) == 1 and led[0]["consumo"]["codex_conocido"] == reserva
          and ctl.ledger.contador().codex_total == reserva and not ctl.ledger.contador().cota_calculable)
    check("I5 … y el intento se CIERRA (estado final y lista publicada `consumo_jueces`)",
          led[0]["estado"] == "cerrado" and len(ctl.intentos) == 1
          and ctl.intentos[0]["estado"] == "desconocido")
    cap = _Captura(_ok)
    ctl, sal = control_prueba(techo_claude=1000)
    check("I5 control PREVIO: si el intento superaría el techo, no se llama al modelo ni se reserva",
          raises(lambda: jueces.ClaudeJuezRunner(exe=r"C:\x\claude.exe", ejecutar=cap, control=ctl)("p", {}),
                 jueces.CuotaAgotada) and cap.llamadas == [] and _ledger(sal) == [])
    ctl, sal = control_prueba(techo_codex=5)
    ctl.ledger.iniciar(id_="previo-codex", etapa="validacion", proveedor="codex", cota_tokens=5)
    ctl.ledger.cerrar("previo-codex", codex_conocido=5)
    check("I5 control PREVIO de AMBOS proveedores: Codex en su techo bloquea también al juez Opus",
          raises(lambda: jueces.ClaudeJuezRunner(exe=r"C:\x\claude.exe", ejecutar=cap, control=ctl)("p", {}),
                 jueces.CuotaAgotada) and cap.llamadas == [])
    check("I5 los runners reales no existen sin control de cuota",
          raises(lambda: jueces.ClaudeJuezRunner(exe=r"C:\x\claude.exe", control=None), ValueError)
          and raises(lambda: jueces.CodexJuezRunner(launcher=(Path("codex.exe"),), control=None), ValueError))
    ctl, sal = control_prueba()
    jueces.ClaudeJuezRunner(exe=r"C:\x\claude.exe", ejecutar=_Captura(_ok), control=ctl)("p", {})
    otro, _ = control_prueba(salida=sal)
    check("I5 el ledger es duradero: otro proceso (otro LedgerJuicio) ve el consumo",
          otro.ledger.contador().claude_total == 22)
    import banco04_validar_jueces as vj
    import inspect
    check("I5 la validación de jueces usa el LedgerJuicio del runner (sin contador propio)",
          "LedgerJuicio" in inspect.getsource(vj.control_de_cuota)
          and not hasattr(vj, "cargar_contador_lectura"))


# ════════════════════════════════════════════════════════════════════════════════════════
# I3/C8 · disponibilidad por tramos enviados (formato `entraron_tramos` del runner)
# ════════════════════════════════════════════════════════════════════════════════════════
def envio_completo(pares, chars=100):
    return metricas.envio_desde_material({"entraron_tramos": [
        {"documento": d, "indice": i, "id": f"{d}#{i}", "chars_original": chars,
         "tramos": [[0, chars]], "completo": True} for d, i in pares]})


def gate_i3() -> None:
    print("\nI3/C8 · disponibilidad por tramos")
    env = metricas.envio_desde_material({"entraron_tramos": [
        {"documento": "a", "indice": 0, "id": "a#0", "chars_original": 100, "tramos": [[0, 100]], "completo": True},
        {"documento": "a", "indice": 1, "id": "a#1", "chars_original": 100, "tramos": [[0, 40]], "completo": False},
        {"documento": "a", "indice": 2, "id": "a#2", "chars_original": None, "tramos": [[0, 100]], "completo": True},
        {"documento": "a", "indice": 3, "id": "a#3", "chars_original": 100, "tramos": [[0, 60]], "completo": True},
        {"documento": "b", "indice": 0, "id": "b#0", "chars_original": 50, "tramos": [[0, 10]], "completo": False},
    ]})
    check("I3 fragmento completo con chars_original conocido → disponible", metricas.ref_disponible(("a", 0), env))
    check("I3 fragmento PARCIAL y la clave solo da el fragmento → NO disponible",
          not metricas.ref_disponible(("a", 1), env))
    check("I3 «completo» sin chars_original conocido → NO disponible", not metricas.ref_disponible(("a", 2), env))
    check("I3 «completo» cuyos tramos no cubren el fragmento → NO disponible (no se cree la etiqueta)",
          not metricas.ref_disponible(("a", 3), env))
    check("I3 rango de la clave dentro de un tramo enviado → disponible",
          metricas.ref_disponible(("a", 1, 5, 30), env))
    check("I3 rango que se sale del tramo enviado → NO disponible",
          not metricas.ref_disponible(("a", 1, 30, 50), env))
    check("I3 rango dentro de un tramo enviado pero sin chars_original conocido → NO disponible",
          not metricas.ref_disponible(("a", 2, 5, 30), env))
    check("I3 sin `entraron_tramos` no hay medición: nada disponible",
          metricas.envio_desde_material({"entraron": ["a#0"]}) is None
          and not metricas.disponible([("a", 0)], None))
    alc = metricas.alcance_desde_fragmentos({"a": 4, "b": 1}, env)
    check("I3 el alcance solo cuenta fragmentos completos y una pieza solo con parciales queda sin leer",
          alc["leidos"] == 1 and alc["parciales"] == 4 and alc["piezas_sin_leer"] == ["b"]
          and metricas.clasificar_alcance(**{k: alc[k] for k in ("leidos", "total", "piezas_sin_leer", "medido")})
          ["alcance"] == "insuficiente")
    clave = {"hechos_materiales": [{"id": "h1", "documento": "a", "fragmentos": [1], "decisivo": True,
                                    "marcador_auxiliar": "M"},
                                   {"id": "h2", "documento": "a", "fragmentos": [1], "decisivo": True,
                                    "rangos": [{"fragmento": 1, "inicio": 5, "fin": 30}], "marcador_auxiliar": "N"}],
             "puntos_materiales": [{"id": "p1", "tipo": "conclusion", "depende_de_hechos": [],
                                    "fragmentos": [{"documento": "a", "fragmento": 1}]}]}
    p2 = {"hechos": [{"id": "h1", "cubierto": False}, {"id": "h2", "cubierto": False}],
          "puntos": [{"id": "p1", "resolucion": "no_tratado"}],
          "conducta": {"clase": "definitiva", "dice_lo_no_leido": False}, "aprobaria_sin_editar": {"respuesta": "no"}}
    hp = metricas.hechos_y_puntos_desde_clave(clave, p2, env)
    check("I3 desde la clave: solo-fragmento parcial → no disponible; con rango dentro del tramo → disponible",
          [h["disponible"] for h in hp["hechos"]] == [False, True] and hp["puntos"][0]["disponible"] is False)


# ════════════════════════════════════════════════════════════════════════════════════════
# I6 · discordancias sin resolver impiden usar el circuito
# ════════════════════════════════════════════════════════════════════════════════════════
def gate_i6() -> None:
    print("\nI6 · discordancias en la validación del circuito")
    import banco04_validar_jueces as vj
    r = vj.evaluar_exigencias(_res(n_def=30, perdidos=0), tipo="reservado", discordancias=1, **OK_CIRCUITO)
    check("I6 30 defectos, todo lo demás en verde y 1 discordancia → el circuito NO se usa",
          not r["circuito_utilizable"] and not r["exigencias"]["discordancias_sin_resolver"]["cumple"])
    check("I6 control: sin discordancias el mismo circuito sí se usa",
          vj.evaluar_exigencias(_res(n_def=30), tipo="reservado", discordancias=0, **OK_CIRCUITO)["circuito_utilizable"])
    check("I6 las discordancias son obligatorias en la firma (no hay valor por defecto)",
          raises(lambda: vj.evaluar_exigencias(_res(), tipo="reservado"), TypeError))
    conjunto = _conjunto_sintetico(30)
    # Opus: control respaldado; Codex: lo marca sin respaldo; tercer voto válido pero distinto
    # (localizador_falso) → tres estados distintos con defecto ⇒ discordancia en cada salida.
    res = vj.validar_circuito(conjunto["items"], opus=OpusDoble(),
                              codex=CodexDoble({"El pago se hizo en plazo": {"estado": "sin_respaldo",
                                                                             "subtipo": "hecho"}}),
                              llave=LLAVE, tipo="ajuste",
                              votante_factory=lambda paq, mat: votante_fijo("localizador_falso"))
    ex = res["exigencias"]["discordancias_sin_resolver"]
    check("I6 extremo a extremo: las 30 discordancias (con voto válido) llegan contadas a las exigencias",
          ex["valor"] == 30 and ex["cumple"] is False and not res["resumen"]["no_evaluadas"])


# ════════════════════════════════════════════════════════════════════════════════════════
# I7 · norma con pasaje de un ordenamiento no configurado ⇒ fuga
# ════════════════════════════════════════════════════════════════════════════════════════
def gate_i7() -> None:
    print("\nI7 · jurisdicciones configuradas en el material del juez")
    t = "El plazo es de 40 días [corpus:norma-x]"
    corpus = [{"ref": "corpus:norma-x", "texto": "El plazo es de 40 días.", "jurisdiccion": "co"}]

    def _salida(paq, estado, subtipo=None, fuente="corpus:norma-x"):
        segs = {s_["id"]: s_["texto"] for s_ in paq["segmentos"]}
        out = []
        for sid, tx in segs.items():
            if tx == t:
                kw = {"fuente": fuente, "pasaje": "El plazo es de 40 días"} if estado != "sin_respaldo" else {}
                out.append({"id": sid, "exclusiones": [], "afirmaciones": [
                    af(sid + "a", [(0, len(tx))], tx, tipo="proposicion_juridica", estado=estado,
                       subtipo=subtipo, **kw)]})
            else:
                out.append(atomizar(sid, tx, regla_por_defecto("Atentamente")))
        return {"schema": P.ESQUEMA_PASADA1, "candidate_id": paq["candidate_id"], "segmentos": out}, segs
    for jur, esperado in (([], False), (["co"], True)):
        paq, _, mat = preparar(t, corpus=corpus, jurisdicciones=jur, mensaje="Atentamente")
        sal, segs = _salida(paq, "con_respaldo")
        v = jueces.validar_pasada1(sal, candidate=paq["candidate_id"], segmentos=segs, material=mat)
        check(f"I7 norma con pasaje en el corpus, jurisdicciones={jur}: "
              f"{'respalda' if esperado else 'NO respalda (rechazo)'}",
              v.ok == esperado and (esperado or "respaldo_en_ordenamiento_no_configurado" in _codigos(v)))
    paq, _, mat = preparar(t, corpus=corpus, jurisdicciones=[], mensaje="Atentamente")
    sal, segs = _salida(paq, "sin_respaldo", subtipo="fuga")
    v = jueces.validar_pasada1(sal, candidate=paq["candidate_id"], segmentos=segs, material=mat)
    check("I7 la misma norma no habilitada clasificada `sin_respaldo/fuga` valida", v.ok)
    m = metricas.metricas_corrida(_corrida(fuga_juez=1))
    check("I7 una fuga confirmada por los jueces cuenta en `fuga_jurisdiccion`", m["fuga_jurisdiccion"] is True)
    grab = OpusGrabador()
    jueces.pasada1(paq, mat, opus=grab, codex=CodexDoble(), votante=votante_fijo("sin_respaldo"))
    check("I7 las jurisdicciones configuradas llegan al prompt del juez (lista vacía incluida)",
          paquete_de_prompt(grab.prompts[0])["jurisdicciones_configuradas"] == []
          and "jurisdicciones_configuradas" in jueces.cargar_prompt("pasada1_opus")
          and "jurisdicciones_configuradas" in jueces.cargar_prompt("pasada1_codex")
          and "jurisdicciones_configuradas" in jueces.cargar_prompt("tercer_voto"))
    check("I7 el paquete exige declarar las jurisdicciones (no hay valor por defecto)",
          raises(lambda: ceguera.preparar_candidato(llave=LLAVE, etiqueta_version="prueba", case_id="c",
                                                    repeticion=1, diagnostico="x", borrador="",
                                                    mensaje_abogado="", expediente=[], mapa_docs=[],
                                                    fuentes_corpus=[]), TypeError))
    check("I7 protocolo en v1.3", P.VERSION_PROTOCOLO == "banco04-v1.3")



def gate_cus() -> None:
    print("\nCUS · versión de custodia independiente del protocolo (§12.5)")
    import banco04_validar_jueces as vj
    conj = _conjunto_sintetico(30)
    check("CUS los conjuntos custodiados se cotejan contra PROTOCOLO_CUSTODIA (v1.2), no contra la v1.3",
          P.PROTOCOLO_CUSTODIA == "banco04-v1.2" and P.PROTOCOLO_CUSTODIA != P.VERSION_PROTOCOLO
          and len(vj.validar_conjunto(conj)) == 30)
    for otra in (P.VERSION_PROTOCOLO, "banco04-v1.1"):
        malo = {**conj, "protocolo": otra}
        check(f"CUS un conjunto que declara otra versión de custodia ({otra}) falla cerrado",
              raises(lambda: vj.validar_conjunto(malo), vj.ConjuntoInvalido))


# ════════════════════════════════════════════════════════════════════════════════════════
# I9 · uso único del reservado: registro canónico, ligado a la identidad sellada
# ════════════════════════════════════════════════════════════════════════════════════════
def gate_i9() -> None:
    print("\nI9 · registro canónico de uso del reservado (raíz permanente, R2-C-I9)")
    import inspect
    import tempfile as _tf
    import banco04_validar_jueces as vj
    man = {"artefactos": [{"id": "mut-reservado", "tipo": "mutaciones_reservadas",
                           "sha256_cifrado": "a" * 64, "sha256_claro": "b" * 64},
                          {"id": "mut-ajuste", "tipo": "mutaciones_ajuste",
                           "sha256_cifrado": "c" * 64, "sha256_claro": "d" * 64}]}
    ident = vj.identidad_sellada_reservado(man)
    huellas = ["h-item-1", "h-item-2"]
    with _tf.TemporaryDirectory() as d:
        d = Path(d)
        perm, cus1, cus2, perm2 = d / "perfil", d / "custodia-1", d / "custodia-2", d / "perfil-2"
        env1 = {vj.ENV_RAIZ_PERMANENTE: str(perm), vj.ENV_CUSTODIA: str(cus1)}
        env2 = {vj.ENV_RAIZ_PERMANENTE: str(perm), vj.ENV_CUSTODIA: str(cus2)}
        env3 = {vj.ENV_RAIZ_PERMANENTE: str(perm2), vj.ENV_CUSTODIA: str(cus1)}
        try:
            marca = vj.marcar_uso_unico(ident, env1, huellas=huellas)
        except Exception:  # noqa: BLE001 — la primera marca tiene que poder escribirse
            marca = None
        check("I9 la marca vive en la raíz PERMANENTE (%LOCALAPPDATA%/MIA-banco04-registro-uso) con la "
              "identidad sellada", marca is not None and marca.parent == perm / vj.DIR_REGISTRO_PERMANENTE
              and ident in marca.name and marca.is_file())
        check("I9 un segundo uso del mismo reservado se rechaza",
              lanza(lambda: vj.marcar_uso_unico(ident, env1, huellas=huellas), vj.ReservadoYaUsado))
        check("R2-C-I9 · REUBICACIÓN: la misma identidad con OTRA MIA_BANCO04_CUSTODIA se rechaza",
              lanza(lambda: vj.marcar_uso_unico(ident, env2, huellas=huellas), vj.ReservadoYaUsado))
        check("R2-C-I9 · la ruta del registro no cambia con MIA_BANCO04_CUSTODIA",
              marca is not None and vj.ruta_registro_uso(ident, env1) == vj.ruta_registro_uso(ident, env2) == marca)
        check("R2-C-I9 · cambiar SOLO la raíz permanente tampoco basta (la marca secundaria de la custodia)",
              lanza(lambda: vj.marcar_uso_unico(ident, env3, huellas=huellas), vj.ReservadoYaUsado))
        otro = json.loads(json.dumps(man))
        otro["artefactos"][0]["sha256_claro"] = "e" * 64
        ident2 = vj.identidad_sellada_reservado(otro)
        check("R2-C-I9 · un reservado «nuevo» que reutiliza material ya usado se rechaza (huellas)",
              lanza(lambda: vj.marcar_uso_unico(ident2, env1, huellas=["h-item-2", "h-item-9"]),
                    vj.ReservadoYaUsado))
        check("R2-C-I9 · control: otra identidad con material nuevo sí se marca",
              not lanza(lambda: vj.marcar_uso_unico(ident2, env1, huellas=["h-item-7"]), BaseException))
        dentro = {vj.ENV_RAIZ_PERMANENTE: str(cus1 / "x"), vj.ENV_CUSTODIA: str(cus1)}
        check("R2-C-I9 · la raíz permanente no puede quedar DENTRO de la custodia (que se reubica)",
              lanza(lambda: vj.ruta_registro_uso(ident, dentro), SystemExit))
    check("I9 sin raíz permanente (LOCALAPPDATA) no hay registro (falla cerrado)",
          raises(lambda: vj.ruta_registro_uso(ident, {vj.ENV_CUSTODIA: "C:/x"}), SystemExit))
    check("I9 ni la función ni la línea de órdenes permiten elegir el directorio del registro",
          "registro_dir" not in inspect.signature(vj.marcar_uso_unico).parameters
          and "--registro-uso" not in inspect.getsource(vj.main))
    recifrado = json.loads(json.dumps(man))
    recifrado["artefactos"][0]["sha256_cifrado"] = "f" * 64
    recifrado["artefactos"][0]["id"] = "mut-reservado-bis"
    check("R2-C-I9 · la identidad es la del CONTENIDO: re-cifrar o renombrar no fabrica otro reservado",
          vj.identidad_sellada_reservado(recifrado) == ident)
    check("I9 otro contenido sellado = otra identidad", ident2 != ident)
    fuente = inspect.getsource(vj.main)
    check("I9 la marca se escribe ANTES de juzgar y no se borra si falla",
          fuente.index("marcar_uso_unico(") < fuente.index("validar_circuito(")
          and "unlink" not in inspect.getsource(vj))


# ════════════════════════════════════════════════════════════════════════════════════════
# Ronda 2 de Astra · área B, parte de este frente (veredicto_B.md: I4, N1, I5)
# ════════════════════════════════════════════════════════════════════════════════════════
def gate_r2_b() -> None:
    print("\nR2-B · cota sin fabricar, telemetría completa y contador compartido")
    import inspect
    import tempfile as _tf
    import banco04_validar_jueces as vj
    from mia.eval import spend_guard
    # ── I4 ──
    check("R2-B-I4 · Codex sin cota documentada ⇒ cota DESCONOCIDA (None), nunca una genérica",
          jueces.cota_salida_juez("codex") is None and jueces.cota_intento("x" * 30, "codex") is None)
    original = spend_guard.cota_salida_cli
    try:
        spend_guard.cota_salida_cli = lambda alias: (5000, "doble") if alias == jueces.ALIAS_CLI_JUEZ_CLAUDE else (None, "")
        con = jueces.cota_intento("x" * 30, "claude")
        spend_guard.cota_salida_cli = lambda alias: (None, "sin dato")
        sin = jueces.cota_intento("x" * 30, "claude")
    finally:
        spend_guard.cota_salida_cli = original
    check("R2-B-I4 · Claude: la cota es la de spend_guard.cota_salida_cli (entrada + 5000) y, si esta "
          "devuelve None, la cota es desconocida",
          con == 10 + 5000 and sin is None)
    check("R2-B-I4 · cota_intento no usa ninguna cota propia (COTA_SALIDA_JUEZ_TOKENS solo en la reserva)",
          "COTA_SALIDA_JUEZ_TOKENS" not in inspect.getsource(jueces.cota_intento)
          and "COTA_SALIDA_JUEZ_TOKENS" not in inspect.getsource(jueces.cota_salida_juez))

    def _timeout(cmd, kw):
        raise subprocess.TimeoutExpired(cmd, 1)
    ctl, sal = control_prueba(cota_salida=_cota_documentada(1000))
    jueces.ClaudeJuezRunner(exe=r"C:\x\claude.exe", ejecutar=_Captura(_timeout), control=ctl)("p" * 30, {})
    c = ctl.ledger.contador()
    check("R2-B-I4 · con cota DOCUMENTADA, el intento fallido cuenta su cota y el techo sigue certificable",
          c.claude_total == 10 + 1000 and c.cota_calculable and ctl.intentos[0]["estado"] == "fallido_acotado")
    ctl, sal = control_prueba(cota_salida=_sin_cota)
    jueces.ClaudeJuezRunner(exe=r"C:\x\claude.exe", ejecutar=_Captura(_timeout), control=ctl)("p" * 30, {})
    check("R2-B-I4 · SIN cota documentada, el mismo fallo deja el techo NO certificable",
          not ctl.ledger.contador().cota_calculable and ctl.intentos[0]["estado"] == "desconocido")
    # ── N1 ──
    tc = jueces.tokens_conocidos
    check("R2-B-N1 · `{cache_read_input_tokens: 0}` NO es consumo conocido (Astra)",
          tc("claude", {"cache_read_input_tokens": 0}) is None)
    check("R2-B-N1 · faltando la entrada o la salida, o con valores inválidos, no hay consumo conocido",
          tc("claude", {"input_tokens": 10}) is None and tc("claude", {"output_tokens": 10}) is None
          and tc("claude", {"input_tokens": 10, "output_tokens": -1}) is None
          and tc("claude", {"input_tokens": True, "output_tokens": 1}) is None
          and tc("claude", {"input_tokens": 1, "output_tokens": 1, "cache_read_input_tokens": "5"}) is None)
    check("R2-B-N1 · control: entrada + salida válidas (y caché válida) suman",
          tc("claude", {"input_tokens": 10, "output_tokens": 7, "cache_read_input_tokens": 5}) == 22
          and tc("claude", {"input_tokens": 10, "output_tokens": 7}) == 17)
    check("R2-B-N1 · Codex: sin prompt_tokens y completion_tokens válidos no hay consumo (total solo no basta)",
          tc("codex", {"prompt_tokens": None, "completion_tokens": None, "total_tokens": 50}) is None
          and tc("codex", {"prompt_tokens": 3, "completion_tokens": None}) is None
          and tc("codex", {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 9}) == 9
          and tc("codex", {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": None}) == 5)

    def _parcial(cmd, kw):
        return subprocess.CompletedProcess(cmd, 0, json.dumps({
            "structured_output": {"x": 1}, "usage": {"cache_read_input_tokens": 0}}), "")
    ctl, sal = control_prueba(cota_salida=_sin_cota)
    jueces.ClaudeJuezRunner(exe=r"C:\x\claude.exe", ejecutar=_Captura(_parcial), control=ctl)("p" * 30, {})
    led = _ledger(sal)
    check("R2-B-N1 · extremo a extremo: una respuesta con telemetría parcial se cierra como consumo "
          "DESCONOCIDO (no como 0 conocido) y el techo deja de ser certificable",
          led[0]["timeout"] is True and ctl.intentos[0]["estado"] == "desconocido"
          and not ctl.ledger.contador().cota_calculable)
    # ── I5 ──
    cap = _Captura(lambda cmd, kw: subprocess.CompletedProcess(cmd, 0, json.dumps({
        "structured_output": {"x": 1}, "usage": {"input_tokens": 1, "output_tokens": 1}}), ""))
    check("R2-B-I5 · tras un consumo sin cota no se lanza NINGÚN juez más (ni Opus ni Codex)",
          raises(lambda: jueces.ClaudeJuezRunner(exe=r"C:\x\claude.exe", ejecutar=cap, control=ctl)("p", {}),
                 jueces.CuotaAgotada)
          and raises(lambda: jueces.CodexJuezRunner(launcher=(Path("codex.exe"),), ejecutar=cap,
                                                    control=ctl)("p", {}), jueces.CuotaAgotada)
          and cap.llamadas == [])
    from types import SimpleNamespace as _NS

    class _LedgerFalso:
        """Ledger cuyo `iniciar` NO controla nada: aísla la defensa propia de ControlCuotaJueces
        (independiente de que `motivo_juicio`, del otro frente, también se niegue)."""
        def __init__(self, calculable):
            self.calculable, self.iniciados = calculable, []

        def contador(self):
            return _NS(cota_calculable=self.calculable, claude_total=0, codex_total=0,
                       techo_claude=10 ** 9, techo_codex=10 ** 9)

        def iniciar(self, **kw):
            self.iniciados.append(kw)

        def cerrar(self, *a, **kw):
            pass
    falso = _LedgerFalso(False)
    ctl_f = jueces.ControlCuotaJueces(ledger=falso, etapa="validacion", prefijo="f", cota_salida=_sin_cota)
    falso_ok = _LedgerFalso(True)
    ctl_fok = jueces.ControlCuotaJueces(ledger=falso_ok, etapa="validacion", prefijo="f", cota_salida=_sin_cota)
    check("R2-B-I5 · defensa PROPIA del control: con el contador no calculable no se reserva ni se lanza "
          "(aunque el ledger no lo impida); con contador calculable sí",
          raises(lambda: ctl_f.antes("claude", "p"), jueces.CuotaAgotada) and falso.iniciados == []
          and not raises(lambda: ctl_fok.antes("codex", "p"), Exception) and len(falso_ok.iniciados) == 1)
    ctl_ok, _ = control_prueba(cota_salida=_sin_cota)
    jueces.ClaudeJuezRunner(exe=r"C:\x\claude.exe", ejecutar=cap, control=ctl_ok)("p", {})
    jueces.ClaudeJuezRunner(exe=r"C:\x\claude.exe", ejecutar=cap, control=ctl_ok)("p", {})
    check("R2-B-I5 · control: con consumo conocido el circuito sigue (dos llamadas)", len(cap.llamadas) == 2)
    with _tf.TemporaryDirectory() as d:
        d = Path(d)
        def _cc(**kw):
            base = dict(salida=d, version="0.4", bloque=0, prefijo="v", salida_custodia=d / "c",
                        versiones=("0.4",))
            return lambda: vj.control_de_cuota(**{**base, **kw})
        check("R2-B-I5 · control_de_cuota EXIGE la salida custodiada",
              lanza(_cc(salida_custodia=None), SystemExit))
        check("R2-B-I5 · control_de_cuota EXIGE las versiones del bloque, incluida la propia",
              lanza(_cc(versiones=()), SystemExit) and lanza(_cc(versiones=("0.3.3",)), SystemExit))
        check("R2-B-I5 · en el Bloque 7 suman las DOS versiones (una sola no basta)",
              lanza(_cc(bloque=7, versiones=("0.4",)), SystemExit))
        check("R2-B-I5 · control: Bloque 0 con su versión y la salida custodiada se construye",
              not lanza(_cc(), BaseException))
        ctl7 = vj.control_de_cuota(salida=d, version="0.4", bloque=7, prefijo="v",
                                   salida_custodia=d / "c", versiones=("0.4", "0.3.3"))
        check("R2-B-I5 · control: Bloque 7 con las DOS versiones y la salida custodiada usa el LedgerJuicio "
              "compartido", ctl7.ledger.versiones == ("0.4", "0.3.3")
              and ctl7.ledger.salida_custodia == d / "c" and type(ctl7.ledger).__name__ == "LedgerJuicio")
        # consumo de la versión hermana (0.3.3) en el MISMO techo: lo ve el control de la 0.4
        rb = _rb()
        rb.registrar_consumo_externo(d, "0.3.3", id_="otro-0001", etapa="juicio", claude_conocido=777)
        check("R2-B-I5 · el contador del circuito suma lo gastado por la OTRA versión del bloque",
              ctl7.ledger.contador().claude_total >= 777)
    fuente = inspect.getsource(vj.main)
    check("R2-B-I5 · la línea de órdenes exige --salida-custodia y --versiones-contador",
          '"--salida-custodia", required=True' in fuente and '"--versiones-contador", required=True' in fuente)
    res = _res(n_def=30)
    sin_consumo = vj.evaluar_exigencias(res, tipo="reservado", discordancias=0,
                                        acreditacion={"ok": True, "motivos": []}, consumo=None)
    no_cert = vj.evaluar_exigencias(res, tipo="reservado", discordancias=0,
                                    acreditacion={"ok": True, "motivos": []},
                                    consumo={"cota_calculable": False, "resumen": {}})
    check("R2-B-I5 · circuito_utilizable EXIGE consumo certificable (sin contador o con consumo sin cota → no)",
          not sin_consumo["circuito_utilizable"] and not no_cert["circuito_utilizable"]
          and not no_cert["exigencias"]["consumo_certificable"]["cumple"])
    check("R2-B-I5 · control: con consumo certificable el mismo circuito se usa",
          vj.evaluar_exigencias(res, tipo="reservado", discordancias=0, **OK_CIRCUITO)["circuito_utilizable"])
    conjunto = _conjunto_sintetico(30)
    check("R2-B-I5 · el reservado no se juzga con runners SIN el contador compartido",
          raises(lambda: vj.validar_circuito(conjunto["items"], opus=OpusDoble(), codex=CodexDoble(),
                                             llave=LLAVE, tipo="reservado"), ValueError))
    ctl_d, _ = control_prueba(cota_salida=_sin_cota)
    opus, codex = OpusDoble(), CodexDoble()
    opus.control = codex.control = ctl_d
    ctl_d.ledger.iniciar(id_="previo-0001", etapa="validacion", proveedor="codex", cota_tokens=10)
    ctl_d.ledger.cerrar("previo-0001", timeout=True)
    r = vj.validar_circuito(conjunto["items"], opus=opus, codex=codex, llave=LLAVE, tipo="reservado",
                            control=ctl_d, acreditacion={"ok": True, "motivos": []},
                            votante_factory=lambda paq, mat: votante_fijo("sin_respaldo"))
    check("R2-B-I5 · extremo a extremo: con un intento de consumo desconocido en el contador, el circuito NO "
          "es utilizable", not r["circuito_utilizable"] and not r["exigencias"]["consumo_certificable"]["cumple"])


# ════════════════════════════════════════════════════════════════════════════════════════
# Ronda 2 de Astra · área C (veredicto_C.md: N1, N2, N3, N4)
# ════════════════════════════════════════════════════════════════════════════════════════
def _con_frase(item: dict, frase: str, vid: str, clase: str, categoria, *, estado="sin_respaldo") -> dict:
    """Añade `frase` al diagnóstico del ítem y su entrada de verdad (offsets exactos)."""
    diag = item["salida"]["diagnostico"] + " " + frase
    ini = diag.index(frase)
    item["salida"]["diagnostico"] = diag
    item["verdad"].append({"id": vid, "clase": clase, "categoria": categoria, "campo": "diagnostico",
                           "inicio": ini, "fin": ini + len(frase), "literal": frase,
                           "estado_esperado": estado, "estados_aceptables": [estado],
                           "subtipo_esperado": "fuga" if clase == "defecto" else None, "nota": None})
    return item


_FUENTE_CO = {"ref": "corpus:ley-co-100", "texto": "La Ley 100 de 1993 fija un plazo de 40 días.",
              "jurisdiccion": "co", "ficticia": True}


def _reservado_v13() -> dict:
    c = _conjunto_sintetico(30)
    c["conjunto"] = "reservado"
    it = c["items"]
    _con_frase(it[0], "La Ley 100 de 1993 rige el contrato.", "c08", "defecto", "C08")
    it[1]["jurisdicciones"] = ["es"]
    it[1]["material"]["fuentes_corpus"] = [dict(_FUENTE_CO)]
    _con_frase(it[1], "La Ley 100 de 1993 [corpus:ley-co-100] rige el contrato.", "c08", "defecto", "C08")
    _con_frase(it[2], "La Ley 100 de 1993 es aplicable al caso, aunque no consta la fecha del contrato.",
               "c08", "defecto", "C08")
    it[3]["jurisdicciones"] = ["es"]
    it[3]["material"]["fuentes_corpus"] = [dict(_FUENTE_CO)]
    _con_frase(it[3], "Según [corpus:ley-co-100], esa ley fija 40 días, pero no rige en este despacho.",
               "cd", "control", None, estado="con_respaldo_sin_localizador")
    return c


def _manifiesto_v13() -> dict:
    return {"artefactos": [{"id": "V1", "tipo": "caso", "sha256_claro": "1" * 64},
                           {"id": "clave-V1", "tipo": "clave", "sha256_claro": "2" * 64},
                           {"id": "mut-ajuste", "tipo": "mutaciones_ajuste", "sha256_claro": "3" * 64},
                           {"id": "mut-reservado", "tipo": "mutaciones_reservadas", "sha256_claro": "4" * 64},
                           {"id": "semilla", "tipo": "semilla", "sha256_claro": "5" * 64}]}


def _acreditacion_v13(man: dict, **cambios) -> dict:
    import banco04_validar_jueces as vj
    a = {"schema": vj.FORMATO_ACREDITACION, "protocolo": P.VERSION_PROTOCOLO, "autor": "autor-independiente",
         "autor_independiente": True, "fecha": "2026-10-12", "hash_evaluador": "e" * 64,
         "identidad_reservado": vj.identidad_sellada_reservado(man),
         "artefactos": {x["id"]: x["sha256_claro"] for x in man["artefactos"] if x["tipo"] != "semilla"},
         "veredicto": "compatible",
         "cobertura": {"fuga_sin_ordenamiento": ["MA-00/c08"], "fuga_otro_ordenamiento": ["MA-01/c08"],
                       "negacion_ajena": ["MA-02/c08"], "control_descriptivo": ["MA-03/cd"]}}
    a.update(cambios)
    return a


def _salida_p1(paq: dict, objetivo: str, estado: str, **ev) -> tuple[dict, dict]:
    segs = {s_["id"]: s_["texto"] for s_ in paq["segmentos"]}
    out = []
    for sid, tx in segs.items():
        if tx == objetivo:
            out.append({"id": sid, "exclusiones": [], "afirmaciones": [
                af(sid + "a", [(0, len(tx))], tx, tipo="proposicion_juridica", estado=estado,
                   subtipo="fuga" if estado == "sin_respaldo" else None, **ev)]})
        else:
            out.append(atomizar(sid, tx, regla_por_defecto("Atentamente")))
    return {"schema": P.ESQUEMA_PASADA1, "candidate_id": paq["candidate_id"], "segmentos": out}, segs


def gate_r2_c() -> None:
    print("\nR2-C · acreditación v1.3, describir ≠ aplicar, congelación del validador, negación por cláusula")
    import banco04_validar_jueces as vj
    from mia.eval.banco04 import custodia as cus
    from mia.eval.banco04 import evaluador_congelado as ev
    # ── N1 · C08 en un despacho configurado para OTRO ordenamiento ──
    aj = _reservado_v13()
    aj["conjunto"] = "ajuste"
    check("R2-C-N1 · C08 en un despacho configurado para OTRO ordenamiento (con la fuente no habilitada) "
          "es un ítem válido", not raises(lambda: vj.validar_conjunto(aj), vj.ConjuntoInvalido))
    malo = json.loads(json.dumps(aj))
    malo["items"][1]["material"]["fuentes_corpus"] = []
    check("R2-C-N1 · … pero C08 en un despacho configurado SIN fuente de otro ordenamiento se rechaza",
          raises(lambda: vj.validar_conjunto(malo), vj.ConjuntoInvalido)
          and raises(lambda: cus.invariantes_mutaciones_obj(malo, reservado=False), cus.CustodiaError))
    check("R2-C-N1 · custodia acepta la misma C08 de otro ordenamiento (mismo criterio que el validador)",
          not raises(lambda: cus.invariantes_mutaciones_obj(aj, reservado=False), Exception))
    # ── N1 · acreditación de compatibilidad v1.3 ──
    res = _reservado_v13()
    man = _manifiesto_v13()
    hev = {"combinado": "e" * 64}
    ok = vj.verificar_acreditacion(_acreditacion_v13(man), manifiesto=man, items=res["items"], hash_evaluador=hev)
    check("R2-C-N1 · control: acreditación del autor independiente, ligada a hashes y evaluador v1.3, con "
          "las cuatro clases comprobables → válida", ok["ok"] and ok["motivos"] == []
          and all(n == 1 for n in ok["cobertura_verificada"].values()))
    malas = {
        "sin acreditación": None,
        "evaluador distinto del v1.3 en ejecución": _acreditacion_v13(man, hash_evaluador="0" * 64),
        "hash de una clave distinto": _acreditacion_v13(man, artefactos={
            **_acreditacion_v13(man)["artefactos"], "clave-V1": "9" * 64}),
        "falta un artefacto (caso)": _acreditacion_v13(man, artefactos={
            k: v_ for k, v_ in _acreditacion_v13(man)["artefactos"].items() if k != "V1"}),
        "otra identidad de reservado": _acreditacion_v13(man, identidad_reservado="0" * 64),
        "protocolo v1.2": _acreditacion_v13(man, protocolo="banco04-v1.2"),
        "autor no independiente": _acreditacion_v13(man, autor_independiente=False),
        "sin fuga de OTRO ordenamiento (solo jurisdicciones == [])": _acreditacion_v13(man, cobertura={
            **_acreditacion_v13(man)["cobertura"], "fuga_otro_ordenamiento": ["MA-00/c08"]}),
        "sin negación ajena": _acreditacion_v13(man, cobertura={
            **_acreditacion_v13(man)["cobertura"], "negacion_ajena": []}),
        "sin control descriptivo": _acreditacion_v13(man, cobertura={
            **_acreditacion_v13(man)["cobertura"], "control_descriptivo": ["MA-00/v2"]}),
        "referencia inexistente": _acreditacion_v13(man, cobertura={
            **_acreditacion_v13(man)["cobertura"], "fuga_sin_ordenamiento": ["MA-99/c08"]}),
    }
    rechazadas = [k for k, a in malas.items()
                  if not vj.verificar_acreditacion(a, manifiesto=man, items=res["items"], hash_evaluador=hev)["ok"]]
    check(f"R2-C-N1 · acreditación inválida en cada vínculo → rechazada ({len(rechazadas)}/{len(malas)})",
          rechazadas == list(malas))
    nada = vj.evaluar_exigencias(_res(n_def=30), tipo="reservado", discordancias=0, acreditacion=None,
                                 consumo={"cota_calculable": True, "resumen": {}})
    mala = vj.evaluar_exigencias(_res(n_def=30), tipo="reservado", discordancias=0, consumo={
        "cota_calculable": True, "resumen": {}}, acreditacion=vj.verificar_acreditacion(
            malas["sin negación ajena"], manifiesto=man, items=res["items"], hash_evaluador=hev))
    check("R2-C-N1 · sin acreditación válida el circuito NO se habilita aunque todo lo demás cumpla (Astra: "
          "v1.2, 30/30, 10 C12, sin C08)", not nada["circuito_utilizable"] and not mala["circuito_utilizable"]
          and not nada["exigencias"]["acreditacion_compatibilidad_v13"]["cumple"])
    check("R2-C-N1 · control: con la acreditación verificada sí se habilita",
          vj.evaluar_exigencias(_res(n_def=30), tipo="reservado", discordancias=0, acreditacion=ok,
                                consumo={"cota_calculable": True, "resumen": {}})["circuito_utilizable"])
    import inspect
    fuente = inspect.getsource(vj.main)
    check("R2-C-N1 · la línea de órdenes rechaza el reservado sin --acreditacion-v13 y la verifica ANTES de "
          "marcar el uso", "acreditacion_v13 is None" in fuente
          and fuente.index("verificar_acreditacion(") < fuente.index("marcar_uso_unico(")
          < fuente.index("validar_circuito("))
    # ── N2 · describir/rechazar ≠ aplicar ──
    t = "La Ley 100 de 1993 fija un plazo de 40 días [corpus:ley-co-100]"
    paq, _, mat = preparar(t, corpus=[_FUENTE_CO], jurisdicciones=["es"], mensaje="Atentamente")
    kw = {"fuente": "corpus:ley-co-100", "pasaje": "La Ley 100 de 1993 fija un plazo de 40 días"}
    resultados = {}
    for uso in ("descriptivo", "rechazo_aplicabilidad", "aplicable", None):
        sal, segs = _salida_p1(paq, t, "con_respaldo", uso_fuente=uso, **kw)
        v = jueces.validar_pasada1(sal, candidate=paq["candidate_id"], segmentos=segs, material=mat)
        resultados[uso] = (v.ok, _codigos(v))
    check("R2-C-N2 · una transcripción DESCRIPTIVA fiel de una fuente no habilitada queda respaldada",
          resultados["descriptivo"][0] and resultados["rechazo_aplicabilidad"][0])
    check("R2-C-N2 · la MISMA fuente usada como derecho aplicable (o sin declarar el uso) se rechaza",
          not resultados["aplicable"][0] and not resultados[None][0]
          and "respaldo_en_ordenamiento_no_configurado" in resultados["aplicable"][1]
          and "respaldo_en_ordenamiento_no_configurado" in resultados[None][1])
    sal, segs = _salida_p1(paq, t, "sin_respaldo")
    check("R2-C-N2 · control: la aplicación clasificada `sin_respaldo/fuga` valida",
          jueces.validar_pasada1(sal, candidate=paq["candidate_id"], segmentos=segs, material=mat).ok)
    paq2, _, mat2 = preparar(t, corpus=[_FUENTE_CO], jurisdicciones=["co"], mensaje="Atentamente")
    sal, segs = _salida_p1(paq2, t, "con_respaldo", **kw)
    check("R2-C-N2 · control: con el ordenamiento configurado, la fuente respalda sin declarar el uso",
          jueces.validar_pasada1(sal, candidate=paq2["candidate_id"], segmentos=segs, material=mat2).ok)
    sal, segs = _salida_p1(paq, t, "con_respaldo", uso_fuente="inventado", **kw)
    check("R2-C-N2 · `uso_fuente` fuera de su enumeración se rechaza",
          not jueces.validar_pasada1(sal, candidate=paq["candidate_id"], segmentos=segs, material=mat).ok)
    check("R2-C-N2 · el esquema y los prompts declaran `uso_fuente` (esquema v1.3) y ya no dicen «no puede "
          "respaldar nada»",
          "uso_fuente" in json.dumps(jueces.esquema_pasada1()) and "uso_fuente" in json.dumps(jueces.esquema_tercer_voto())
          and all("uso_fuente" in jueces.cargar_prompt(n) and "no puede respaldar nada" not in jueces.cargar_prompt(n)
                  for n in ("pasada1_opus", "pasada1_codex", "tercer_voto"))
          and P.ESQUEMA_PASADA1.endswith("/v1.3"))
    # ── N3 · el validador entra en la congelación ──
    h0 = jueces.hash_evaluador()
    check("R2-C-N3 · execution/banco04_validar_jueces.py está en el hash del evaluador",
          "execution/banco04_validar_jueces.py" in h0["archivos"])
    import tempfile as _tf
    original = jueces._RAIZ_REPO
    with _tf.TemporaryDirectory() as d:
        copia = Path(d) / "execution" / "banco04_validar_jueces.py"
        copia.parent.mkdir(parents=True)
        texto = (ROOT / "execution" / "banco04_validar_jueces.py").read_text(encoding="utf-8")
        copia.write_text(texto.replace("int(discordancias) == 0", "int(discordancias) <= 1"), encoding="utf-8")
        try:
            jueces._RAIZ_REPO = Path(d)
            alterado = raises(lambda: jueces.verificar_congelado(h0["combinado"]), jueces.EvaluadorAlterado)
            copia.write_text(texto, encoding="utf-8")
            igual = not raises(lambda: jueces.verificar_congelado(h0["combinado"]), Exception)
        finally:
            jueces._RAIZ_REPO = original
    check("R2-C-N3 · relajar una exigencia del validador invalida la congelación (EvaluadorAlterado)", alterado)
    check("R2-C-N3 · control: el validador intacto conserva la huella congelada", igual)
    # ── N4 · negación asociada a la cita (copia vendorizada) ──
    mala_frase = "La Ley 100 de 1993 es aplicable al caso, aunque no consta la fecha del contrato."
    buena_frase = "No consta que la Ley 100 de 1993 sea aplicable."
    check("R2-C-N4 · «… es aplicable al caso, aunque no consta la fecha…» ⇒ FUGA (la negación es de otra cosa)",
          ev.jurisdiction_leak_signal(mala_frase)["leak"] is True)
    check("R2-C-N4 · «No consta que la Ley 100 de 1993 sea aplicable» ⇒ sin fuga",
          ev.jurisdiction_leak_signal(buena_frase)["leak"] is False)
    check("R2-C-N4 · control N-1: «la numeración Ley 4137 no corresponde a ninguna ley…» sigue sin fuga, y la "
          "cita afirmada sin negación sigue siendo fuga",
          not ev.jurisdiction_leak_signal('La numeración "Ley 4137" no corresponde a ninguna ley verificable.')["leak"]
          and ev.jurisdiction_leak_signal("La Ley 100 de 1993 es aplicable al caso.")["leak"])
    m_mala = metricas.metricas_corrida(_corrida(texto_salida=mala_frase, jurisdicciones=[]))
    m_buena = metricas.metricas_corrida(_corrida(texto_salida=buena_frase, jurisdicciones=[]))
    check("R2-C-N4 · metricas usa la copia vendorizada: la oración con negación ajena cuenta como fuga y la "
          "negada no", m_mala["fuga_jurisdiccion"] is True and m_buena["fuga_jurisdiccion"] is False)
    check("R2-C-N4 · con ordenamiento configurado la señal determinista no aplica (§5.7)",
          metricas.metricas_corrida(_corrida(texto_salida=mala_frase, jurisdicciones=["co"]))["fuga_jurisdiccion"] is False)
    check("R2-C-N4 · metricas no acepta una señal de fuga precalculada por el producto",
          raises(lambda: metricas.metricas_corrida({**_corrida(), "fuga_senal": False}), ValueError))
    from mia.eval import scoring
    check("R2-C-N4 · DECLARADO: el defecto PERSISTE en el producto (scoring.py no se toca)",
          scoring.jurisdiction_leak_signal(mala_frase)["leak"] is False)


# ════════════════════════════════════════════════════════════════════════════════════════
# C11 · evaluador congelado: nada de eval/banco04 importa la segmentación del producto
# ════════════════════════════════════════════════════════════════════════════════════════
import ast as _ast  # noqa: E402

_PROHIBIDOS_IMPORT = ("agents.verification", "eval.scoring")


def _import_malo(nombre: str, nivel: int) -> bool:
    segs = [x for x in nombre.split(".") if x]
    if any(a == "agents" and b == "verification" for a, b in zip(segs, segs[1:])):
        return True
    if "scoring" in segs:
        i = segs.index("scoring")
        return (i > 0 and segs[i - 1] == "eval") or (i == 0 and nivel >= 2)
    return False


def imports_prohibidos(carpeta: Path) -> list[str]:
    """Imports de `mia.agents.verification` (o de `mia.eval.scoring`, que lo importa) en los
    módulos de `eval/banco04`, en cualquier forma: absoluta, relativa o `from … import verification`."""
    malos = []
    for f in sorted(carpeta.glob("*.py")):
        arbol = _ast.parse(f.read_text(encoding="utf-8"))
        for n in _ast.walk(arbol):
            if isinstance(n, _ast.Import):
                for a in n.names:
                    if _import_malo(a.name, 0):
                        malos.append(f"{f.name}:{n.lineno}:{a.name}")
            elif isinstance(n, _ast.ImportFrom):
                mod = n.module or ""
                completos = [mod] + [f"{mod}.{a.name}" if mod else a.name for a in n.names]
                if any(_import_malo(c, n.level) for c in completos):
                    malos.append(f"{f.name}:{n.lineno}:{'.' * n.level}{mod}")
    return malos


def gate_c11() -> None:
    print("\nC11 · evaluador vendorizado (decisión del director)")
    carpeta = ROOT / "backend" / "mia" / "eval" / "banco04"
    malos = imports_prohibidos(carpeta)
    check(f"C11 ningún módulo de eval/banco04 importa mia.agents.verification ni eval.scoring ({malos})",
          malos == [])
    import tempfile as _tf
    with _tf.TemporaryDirectory() as d:
        dd = Path(d)
        for nombre, linea in (("a.py", "from ...agents.verification import _normalize\n"),
                              ("b.py", "import mia.agents.verification as v\n"),
                              ("c.py", "from ...agents import verification\n"),
                              ("d.py", "from ..scoring import recall_markers_signal\n")):
            (dd / nombre).write_text(linea, encoding="utf-8")
        check("C11 el detector reconoce las cuatro formas de reintroducir el import",
              len(imports_prohibidos(dd)) == 4)
    from mia.eval.banco04 import evaluador_congelado as ev
    cab = (carpeta / "evaluador_congelado.py").read_text(encoding="utf-8")[:3000]
    check("C11 la copia declara commit 7b9aaa0 y el sha256 de cada archivo de origen",
          ev.ORIGEN_COMMIT == "7b9aaa0" and "7b9aaa0" in cab
          and all(re.fullmatch(r"[0-9a-f]{64}", h) and h in cab for h in ev.ORIGEN_SHA256.values()))
    check("C11 segmentos y jueces usan las funciones de la copia, no las del producto",
          segmentos.segment_sentences is ev.segment_sentences and jueces.scan_citations is ev.scan_citations
          and jueces._normalize is ev._normalize)
    h = jueces.hash_evaluador()["archivos"]
    check("C11 el hash del evaluador se calcula sobre la copia, no sobre verification.py",
          "mia/eval/banco04/evaluador_congelado.py" in h and "mia/agents/verification.py" not in h)


# ════════════════════════════════════════════════════════════════════════════════════════
# Cotejo del autor independiente (V1-V5) sobre la validación de los jueces
# ════════════════════════════════════════════════════════════════════════════════════════
class OpusGrabador(OpusDoble):
    def __init__(self):
        super().__init__()
        self.prompts = []

    def __call__(self, prompt, esquema):
        self.prompts.append(prompt)
        return super().__call__(prompt, esquema)


def gate_cotejo() -> None:
    print("\nV · correcciones del cotejo independiente")
    import banco04_validar_jueces as vj
    # V1 · defecto final = CONFIRMADO y estado final de defecto
    check("V1 estado final: confirmado por mayoría → el estado de defecto más votado",
          jueces.estado_final(["con_respaldo", "sin_respaldo", "sin_respaldo"], jueces.CONFIRMADO) == "sin_respaldo"
          and jueces.estado_final(["localizador_falso", "sin_respaldo"], jueces.CONFIRMADO) == "localizador_falso"
          and jueces.estado_final(["sin_respaldo", "con_respaldo", "con_respaldo"], jueces.DESCARTADO) == "con_respaldo")
    raro = {"decision": jueces.CONFIRMADO, "estado_final": "con_respaldo"}
    check("V1 una decisión CONFIRMADO con estado final no defectuoso NO es defecto",
          not jueces.es_defecto_confirmado(raro)
          and jueces.recuento({}, [{**raro, "parte_opus": "x", "segmento": "S", "solo_codex": False}])
          ["afirmaciones_sin_respaldo"] == 0)
    conjunto = _conjunto_sintetico(30)
    item = conjunto["items"][0]
    original = jueces.adjudicar
    try:
        jueces.adjudicar = lambda unidades, votante: [
            {**d, "estado_final": "con_respaldo"} for d in original(unidades, votante)]
        r = vj.evaluar_item(item, opus=OpusDoble(), codex=CodexDoble(), llave=LLAVE,
                            votante_factory=lambda paq, mat: votante_fijo("sin_respaldo"))
    finally:
        jueces.adjudicar = original
    defecto = [v for v in r["verdades"] if v["es_defecto"]][0]
    check("V1 la validación no cuenta como detectado un CONFIRMADO cuyo estado final no es defecto",
          defecto["estado"] == "evaluada" and defecto["detectado_final"] is False)
    r = vj.evaluar_item(item, opus=OpusDoble(), codex=CodexDoble(), llave=LLAVE,
                        votante_factory=lambda paq, mat: votante_fijo("sin_respaldo"))
    check("V1 control: con estado final de defecto sí cuenta como detectado",
          [v for v in r["verdades"] if v["es_defecto"]][0]["detectado_final"] is True)
    # V2 · offsets comprobados sobre el texto cegado; conjunto rechazado si se pierde un literal
    crudo = "Uno.\r\nLa deuda asciende a 999 millones."
    lit = "La deuda asciende a 999 millones"
    ini = crudo.index(lit)
    ceg = ceguera.cegar_texto(crudo).texto
    span = vj.reubicar(ceg, ini, ini + len(lit), lit)
    check("V2 offsets calculados antes de normalizar saltos: se comprueba y se reubica",
          span is not None and ceg[span[0]:span[1]] == lit and span[0] != ini)
    check("V2 si el literal no sobrevive al cegado, reubicar devuelve None",
          vj.reubicar("texto sin el literal", 0, 5, "123e4567-e89b-12d3-a456-426614174000") is None)
    malo = json.loads(json.dumps(conjunto))
    it0 = malo["items"][0]
    uuid = "123e4567-e89b-12d3-a456-426614174000"
    it0["salida"]["diagnostico"] += f" Pieza {uuid}."
    k = it0["salida"]["diagnostico"].index(uuid)
    it0["verdad"].append({"id": "v3", "clase": "control", "categoria": None, "campo": "diagnostico",
                          "inicio": k, "fin": k + len(uuid), "literal": uuid,
                          "estado_esperado": "no_aplica", "estados_aceptables": ["no_aplica"],
                          "subtipo_esperado": None, "nota": None})
    check("V2 un conjunto con un literal que el cegado borra se RECHAZA antes de juzgar",
          raises(lambda: vj.comprobar_cegado(vj.validar_conjunto(malo)), vj.ConjuntoInvalido)
          and raises(lambda: vj.validar_circuito(malo["items"], opus=OpusDoble(), codex=CodexDoble(),
                                                 llave=LLAVE, tipo="ajuste"), vj.ConjuntoInvalido))
    res = vj.validar_circuito(conjunto["items"], opus=OpusDoble(), codex=CodexDoble(), llave=LLAVE,
                              tipo="ajuste", votante_factory=lambda paq, mat: votante_fijo("sin_respaldo"))
    check("V2 el informe publica cuántos literales sobreviven al cegado",
          res["cegado"]["literales"] == 60 and res["cegado"]["sobreviven_al_cegado"] == 60)
    # V3 · corpus: el ref completo se conserva y se normaliza igual en los dos lados
    material = {"mensaje_abogado": "m", "documentos": [{"filename": "a.txt", "chunks": ["x"]}],
                "mapa_doc": {}, "piezas_fuera_del_mapa": [], "aviso_alcance": None,
                "fuentes_corpus": [{"ref": "corpus:ley-ficticia-77", "texto": "El plazo ficticio es de 40 días.",
                                    "ficticia": True}]}
    exp, mapa, fuentes = vj.material_para_juez(material)
    check("V3 el material del juez conserva el ref de corpus completo", fuentes[0]["ref"] == "corpus:ley-ficticia-77")
    check("V3 la clave de corpus se normaliza igual en todas sus formas",
          {jueces.clave_corpus(x) for x in ("x", "corpus:x", "[corpus:x]", "corpus:corpus:x",
                                            "[corpus:corpus:x]")} == {"x"})
    t = "El plazo ficticio es de 40 días [corpus:ley-ficticia-77]"
    paq, _ = ceguera.preparar_candidato(llave=LLAVE, etiqueta_version="prueba", case_id="c", repeticion=1,
                                        diagnostico=t, borrador="", mensaje_abogado="m", expediente=exp,
                                        mapa_docs=mapa, fuentes_corpus=fuentes,
                                        jurisdicciones_configuradas=[])
    mat = Material.desde_paquete(paq, partes=[])
    segs = {s_["id"]: s_["texto"] for s_ in paq["segmentos"]}
    sid, tx = next(iter(segs.items()))
    for fuente in ("corpus:ley-ficticia-77", "corpus:corpus:ley-ficticia-77", "[corpus:ley-ficticia-77]"):
        sal = {"schema": P.ESQUEMA_PASADA1, "candidate_id": paq["candidate_id"], "segmentos": [
            {"id": sid, "exclusiones": [], "afirmaciones": [
                af("a1", [(0, len(tx))], tx, estado="con_respaldo", fuente=fuente,
                   pasaje="El plazo ficticio es de 40 días")]}]}
        for s2 in list(segs)[1:]:
            sal["segmentos"].append({"id": s2, "exclusiones": [], "afirmaciones": [
                af(s2 + "a", [(0, len(segs[s2]))], segs[s2], tipo="no_afirmativa", estado="no_aplica",
                   justificacion_no_aplica="marca_estructural")]})
        v = jueces.validar_pasada1(sal, candidate=paq["candidate_id"], segmentos=segs, material=mat)
        check(f"V3 un control respaldado en corpus no se rechaza (fuente {fuente!r})", v.ok)
    # I7 (revoca V4/C13) · la jurisdicción configurada SÍ entra al material del juez
    jur = json.loads(json.dumps(conjunto["items"][0]))
    jur["jurisdicciones"] = ["co"]
    grab = OpusGrabador()
    vj.evaluar_item(jur, opus=grab, codex=CodexDoble(), llave=LLAVE,
                    votante_factory=lambda paq, mat: votante_fijo("sin_respaldo"))
    paq_visto = paquete_de_prompt(grab.prompts[0])
    check("I7 las jurisdicciones configuradas del ítem llegan al juez como contexto (y el mensaje va intacto)",
          paq_visto["jurisdicciones_configuradas"] == ["co"]
          and paq_visto["esquema_paquete"] == ceguera.ESQUEMA_PAQUETE
          and paq_visto["mensaje_abogado"] == jur["material"]["mensaje_abogado"])
    # V5 · invariantes del manifiesto
    c08 = json.loads(json.dumps(conjunto))
    c08["items"][0]["verdad"][0]["categoria"] = "C08"
    check("V5 control: C08 en un ítem sin jurisdicción es válido", len(vj.validar_conjunto(c08)) == 30)
    c08["items"][0]["jurisdicciones"] = ["co"]
    check("V5 C08 en un ítem con jurisdicción se rechaza", raises(lambda: vj.validar_conjunto(c08), vj.ConjuntoInvalido))
    reservado = json.loads(json.dumps(conjunto))
    reservado["conjunto"] = "reservado"
    check("V5 ajuste y reservado con el mismo material se rechazan (huella_material)",
          raises(lambda: vj.validar_conjunto(conjunto, otro=reservado), vj.ConjuntoInvalido))
    distinto = json.loads(json.dumps(reservado))
    for it in distinto["items"]:
        it["material"]["mensaje_abogado"] += " (reservado)"
    check("V5 control: materiales disjuntos se aceptan",
          len(vj.validar_conjunto(conjunto, otro=distinto)) == 30)


def main() -> int:
    for g in (gate_p1, gate_p2, gate_p3, gate_p4, gate_p5, gate_p7, gate_p8, gate_p9,
              gate_n1, gate_n2, gate_n3, gate_n4, gate_n5, gate_ceguera, gate_runners, gate_protocolo,
              gate_c11, gate_cotejo, gate_i1_i2, gate_i5, gate_i6, gate_i7, gate_i9, gate_i3, gate_cus,
              gate_r2_a, gate_r2_b, gate_r2_c):
        try:
            g()
        except Exception as exc:  # noqa: BLE001 — un gate que revienta es un gate ROJO
            import traceback
            traceback.print_exc()
            check(f"{g.__name__} no debe lanzar excepción ({type(exc).__name__}: {exc})", False)
    fallos = [n for n, ok in _results if not ok]
    print(f"\nRESULTADO: {len(_results) - len(fallos)}/{len(_results)} PASS")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
