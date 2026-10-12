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
                              "marca", "fragmento_marca", "premisas", "pasaje_contradictorio")}
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
            "subtipos_sin_respaldo": [], "discordancias_sin_resolver": 0, "fuga_senal": False,
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
                   extra_hook=None) -> dict:
    """Entradas COMPLETAS del veredicto global (17 casos, todas sus R evaluadas, todas las filas y
    comparativas). Sin modificaciones, aprueba: es el control de las puertas I1/I2/P4."""
    inv = metricas.inventario_esperado(IDS_C)
    ms = []
    for cid, esp in inv["casos"].items():
        for r in range(esp["R"]):
            ms.append(metricas.metricas_corrida(_corrida(
                case_id=cid, estrato=esp["estrato"], repeticion=r + 1, evaluada=True,
                hechos=[{"id": "h1", "decisivo": True, "cubierto": True, "disponible": True},
                        {"id": "h2", "decisivo": False, "cubierto": True, "disponible": True}],
                puntos=[{"id": "p1", "tipo": "conclusion", "disponible": True, "resolucion": "resuelto"}])))
    casos = metricas.agregar_casos(ms)
    if discordancias:
        casos[P.CASOS_A_CANONICOS[0]]["discordancias_sin_resolver"] = discordancias
    if transformar_casos:
        transformar_casos(casos)
    estratos = metricas.agregar_estratos(casos)
    absolutos = metricas.evaluar_absolutos(
        casos=casos, estratos=estratos, kappa_real=kappa_real or {"exigido": False, "kappa_float": None},
        kappa_reservado={"cuenta_como_minimo": True, "kappa_float": 0.9},
        circuito={"circuito_utilizable": True}, evaluacion_completa=True)
    comparativas = []
    for m in P.METRICAS_COMPARATIVAS:
        for u, conf in P.UNIDADES_INFERENCIA.items():
            cs = [c for c in casos if casos[c]["estrato"] in conf["estratos"]]
            comparativas.append(metricas.comparar_metrica(metrica=m, unidad=u, base=casos, nuevo=casos,
                                                          casos=cs, semilla=LLAVE, base_corridas={},
                                                          nuevo_corridas={}))
    if comparativas_hook:
        comparativas_hook(comparativas)

    def _version(tok):
        return {cid: {"corridas": [{"tokens": tok, "intentos_fallidos": [], "inferencias": 5,
                                    "tokens_codex": 0} for _ in range(esp["R"])],
                      "aprobacion": {"tokens": 0, "intentos_fallidos": [], "tokens_codex": 0}}
                for cid, esp in inv["casos"].items()}
    techo = metricas.techo_cuota(_version(100), _version(tokens_nuevo))
    dec_b = {cid: {"h1": Fraction(1)} for cid in casos}
    extra = metricas.filas_comparativas_obligatorias(
        base=casos, nuevo=casos, decisivos_base=dec_b, decisivos_nuevo=decisivos_nuevo or dec_b,
        techo=techo, comparativas=comparativas, atribuciones=list(atribuciones))
    if extra_hook:
        extra = extra_hook(extra)
    if quitar_caso:
        casos.pop(quitar_caso)
    return dict(inventario=inv, casos=casos, absolutos=absolutos, comparativas=comparativas,
                techo=techo, filas_extra=extra)


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
    ok = vj.evaluar_exigencias(_res(), tipo="reservado", discordancias=0)
    check("N5 control: un circuito que cumple todo es utilizable", ok["circuito_utilizable"])
    r = vj.evaluar_exigencias(_res(solo_codex=10, solo_codex_descartados=3), tipo="reservado", discordancias=0)
    check("N5 la mayoría descarta el 30 % de los defectos vistos solo por Codex → no se usa",
          not r["circuito_utilizable"] and not r["exigencias"]["descarte_mayoria_solo_codex"]["cumple"]
          and r["exigencias"]["sensibilidad_final"]["cumple"])
    r = vj.evaluar_exigencias(_res(perdidos=6), tipo="reservado", discordancias=0)
    check("N5 sensibilidad final 0,94 < 0,95 → no se usa",
          not r["circuito_utilizable"] and not r["exigencias"]["sensibilidad_final"]["cumple"])
    r = vj.evaluar_exigencias(_res(fp=5), tipo="reservado", discordancias=0)
    check("N5 falsos positivos finales 0,125 > 0,10 → no se usa", not r["circuito_utilizable"])
    res = _res()
    res[0] = {**res[0], "estado": "no_evaluada_codex"}
    check("N5 una salida sin evaluar impide usar el circuito",
          not vj.evaluar_exigencias(res, tipo="reservado", discordancias=0)["circuito_utilizable"])
    check("N5 el conjunto de ajuste nunca habilita el circuito",
          not vj.evaluar_exigencias(_res(), tipo="ajuste", discordancias=0)["circuito_utilizable"])
    res = _res()
    for x in res[:2]:
        x["detectado_final"] = False
    check("N5 cláusula falsa breve con sensibilidad 0,80 < 0,90 → no se usa",
          not vj.evaluar_exigencias(res, tipo="reservado", discordancias=0)["exigencias"]["sensibilidad_clausula_breve"]["cumple"])
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
            "usage": {"output_tokens": 3}, "is_error": False}), "")
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
    vacio = metricas.veredicto_global(inventario=inv, casos={}, absolutos=[], comparativas=[],
                                      techo={"resultado": "cumple"}, filas_extra=[])
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

    def _no_concluyente(cs):
        cs[0]["veredicto"] = "no_concluyente"
    check("I1 «no_concluyente» sin recibo de extensión → no certificable",
          veredicto_de(comparativas_hook=_no_concluyente)["veredicto"] == "no_certificable")

    def _con_recibo(final):
        def _h(cs):
            cs[0]["veredicto"] = "no_concluyente"
            cs[0]["diferencia_por_caso"] = {P.CASOS_A_CANONICOS[0]: -0.01}
            cs[0]["extension"] = {"casos": [P.CASOS_A_CANONICOS[0]], "corridas_por_caso": 5,
                                  "veredicto_final": final}
        return _h
    check("I1 «no_concluyente» con recibo válido y final no concluyente → aprueba la fila",
          veredicto_de(comparativas_hook=_con_recibo("no_concluyente"))["veredicto"] == "aprueba")
    check("I1 recibo con regresión tras la extensión → reprueba",
          veredicto_de(comparativas_hook=_con_recibo("regresion"))["veredicto"] == "reprueba")

    def _quitar_extra(extra):
        return [f for f in extra if f["fila"] != "decisivos_estables_perdidos"]
    check("I2 falta la fila de decisivos estables → no certificable",
          veredicto_de(extra_hook=_quitar_extra)["veredicto"] == "no_certificable")
    check("I2 cuota 100 → 120 sin mejora atribuida → reprueba (no aprueba)",
          veredicto_de(tokens_nuevo=120)["veredicto"] == "reprueba")

    def _mejora(cs):
        cs[0]["veredicto"] = "mejora"
    b = banco_completo(tokens_nuevo=120, comparativas_hook=_mejora)
    subidas = b["techo"]["subidas_que_exigen_mejora_atribuible"]
    atr = [{"subida": s_, "metrica": b["comparativas"][0]["metrica"], "unidad": b["comparativas"][0]["unidad"],
            "nodo": "legal_analysis"} for s_ in subidas]
    check("I2 control: la misma subida con mejora atribuida por nodo aprueba",
          veredicto_de(tokens_nuevo=120, comparativas_hook=_mejora, atribuciones=atr)["veredicto"] == "aprueba")
    check("I2 una atribución a una métrica sin «mejora» no cuenta",
          veredicto_de(tokens_nuevo=120, atribuciones=atr)["veredicto"] == "reprueba")

    base = banco_completo()
    nuevo = {k: dict(v) for k, v in base["casos"].items()}
    nuevo["V3"]["cobertura_hechos_materiales"] = Fraction(1, 2)
    extra = metricas.filas_comparativas_obligatorias(
        base=base["casos"], nuevo=nuevo, decisivos_base={"V3": {"h1": Fraction(1)}},
        decisivos_nuevo={"V3": {"h1": Fraction(0)}}, techo=base["techo"],
        comparativas=base["comparativas"], atribuciones=[])
    rojas = {f["fila"] for f in extra if f["cumple"] is False}
    check("I2 un caso que pierde 0,5 de cobertura y un decisivo estable que cae son filas rojas",
          rojas == {"perdida_por_caso:cobertura_hechos_materiales", "decisivos_estables_perdidos"})
    v = metricas.veredicto_global(**{**base, "filas_extra": extra})
    check("I2 … y el veredicto global las incorpora (reprueba)", v["veredicto"] == "reprueba")


# ════════════════════════════════════════════════════════════════════════════════════════
# I5 · todo intento de juez se registra de forma duradera, con control PREVIO de cuota
# ════════════════════════════════════════════════════════════════════════════════════════
def _rb():
    import run_banco04 as rb
    return rb


def control_prueba(techo_claude=10_000_000, techo_codex=10_000_000, salida=None):
    import tempfile as _tf
    rb = _rb()
    salida = Path(salida or _tf.mkdtemp(prefix="banco04-ledger-"))
    ledger = rb.LedgerJuicio(salida, "v-prueba", nuevo_contador=lambda: rb.ContadorCuota(
        techo_claude=techo_claude, techo_codex=techo_codex, reserva_juicio_claude=0,
        reserva_juicio_codex=0))
    return jueces.ControlCuotaJueces(ledger=ledger, etapa="validacion", prefijo="prueba"), salida


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

    ctl, sal = control_prueba()
    visto: list = []

    def _mira_ledger(cmd, kw):
        visto.extend(_ledger(sal))
        visto.append(ctl.ledger.contador().claude_total)
        return _ok(cmd, kw)
    jueces.ClaudeJuezRunner(exe=r"C:\x\claude.exe", ejecutar=_Captura(_mira_ledger), control=ctl)("p" * 30, {})
    cota = jueces.cota_intento("p" * 30)
    check("I5 el intento queda escrito `en_curso` con su cota ANTES de lanzar y el contador ya lo cuenta",
          len(visto) == 2 and visto[0]["estado"] == "en_curso" and visto[0]["cota_reservada"] == cota
          and visto[1] == cota)

    def _timeout(cmd, kw):
        raise subprocess.TimeoutExpired(cmd, 1)
    ctl, sal = control_prueba()
    resp = jueces.ClaudeJuezRunner(exe=r"C:\x\claude.exe", ejecutar=_Captura(_timeout), control=ctl)("p" * 30, {})
    led = _ledger(sal)
    c = ctl.ledger.contador()
    check("I5 un timeout NO devuelve consumo vacío: cuenta su cota y el techo deja de ser certificable",
          resp.error == "timeout" and led[0]["timeout"] is True and led[0]["consumo"]["claude_conocido"] == cota
          and c.claude_total == cota and not c.cota_calculable)

    def _revienta(cmd, kw):
        raise RuntimeError("caída")
    ctl, sal = control_prueba()
    lanzo = raises(lambda: jueces.CodexJuezRunner(launcher=(Path("codex.exe"),), ejecutar=_Captura(_revienta),
                                                  control=ctl)("q" * 30, {}), RuntimeError)
    led = _ledger(sal)
    check("I5 una excepción a mitad de llamada también deja el intento registrado (Codex, con cota)",
          lanzo and len(led) == 1 and led[0]["consumo"]["codex_conocido"] == jueces.cota_intento("q" * 30)
          and ctl.ledger.contador().codex_total == jueces.cota_intento("q" * 30))
    check("I5 … y el intento se CIERRA (estado final y lista publicada `consumo_jueces`)",
          led[0]["estado"] == "cerrado" and len(ctl.intentos) == 1
          and ctl.intentos[0]["estado"] == "desconocido_acotado")
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
    r = vj.evaluar_exigencias(_res(n_def=30, perdidos=0), tipo="reservado", discordancias=1)
    check("I6 30 defectos, todo lo demás en verde y 1 discordancia → el circuito NO se usa",
          not r["circuito_utilizable"] and not r["exigencias"]["discordancias_sin_resolver"]["cumple"])
    check("I6 control: sin discordancias el mismo circuito sí se usa",
          vj.evaluar_exigencias(_res(n_def=30), tipo="reservado", discordancias=0)["circuito_utilizable"])
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
    print("\nI9 · registro canónico de uso del reservado")
    import inspect
    import tempfile as _tf
    import banco04_validar_jueces as vj
    man = {"artefactos": [{"id": "mut-reservado", "tipo": "mutaciones_reservadas",
                           "sha256_cifrado": "a" * 64, "sha256_claro": "b" * 64},
                          {"id": "mut-ajuste", "tipo": "mutaciones_ajuste",
                           "sha256_cifrado": "c" * 64, "sha256_claro": "d" * 64}]}
    ident = vj.identidad_sellada_reservado(man)
    with _tf.TemporaryDirectory() as d:
        env = {vj.ENV_CUSTODIA: d}
        marca = vj.marcar_uso_unico(ident, env)
        check("I9 la marca vive bajo MIA_BANCO04_CUSTODIA/registro-uso y lleva la identidad sellada",
              marca.parent == Path(d) / vj.SUBDIR_REGISTRO_USO and ident in marca.name and marca.is_file())
        check("I9 un segundo uso del mismo reservado se rechaza",
              raises(lambda: vj.marcar_uso_unico(ident, env), vj.ReservadoYaUsado))
        check("I9 la identidad no depende del operador: mismo manifiesto, misma marca",
              vj.ruta_registro_uso(vj.identidad_sellada_reservado(json.loads(json.dumps(man))), env) == marca)
    check("I9 sin MIA_BANCO04_CUSTODIA no hay registro (falla cerrado)",
          raises(lambda: vj.ruta_registro_uso(ident, {}), SystemExit))
    check("I9 ni la función ni la línea de órdenes permiten elegir el directorio del registro",
          "registro_dir" not in inspect.signature(vj.marcar_uso_unico).parameters
          and "--registro-uso" not in inspect.getsource(vj.main))
    otro = json.loads(json.dumps(man))
    otro["artefactos"][0]["sha256_claro"] = "e" * 64
    check("I9 otro contenido sellado = otra identidad", vj.identidad_sellada_reservado(otro) != ident)
    fuente = inspect.getsource(vj.main)
    check("I9 la marca se escribe ANTES de juzgar y no se borra si falla",
          fuente.index("marcar_uso_unico(") < fuente.index("validar_circuito(")
          and "unlink" not in inspect.getsource(vj))


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
              gate_c11, gate_cotejo, gate_i1_i2, gate_i5, gate_i6, gate_i7, gate_i9, gate_i3, gate_cus):
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
