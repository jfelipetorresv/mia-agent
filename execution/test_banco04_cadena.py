"""
Mia · test_banco04_cadena.py — pruebas de PUNTA A PUNTA de la cadena del banco 0.4
(contrato `docs/banco04-cadena-contrato.md`, banco04-cadena/v9, §6; protocolo banco04-v1.3 y la
propuesta v1.4 de «Separar calidad y cuota»). Ajustada a v9 el 2026-10-13: dos veredictos (CALIDAD y
CUOTA por intervalo, §3.1 y §4.5), `PruebaPuerta` con relajaciones separadas, instantáneas de prueba
fuera de `backend/` (`instantaneas_dir=`), E2E-19.

Autor independiente de pruebas. Estas pruebas son la BARRERA: se escriben antes de la cadena y
quien la implemente no puede editarlas. Cada prueba entra por los PUNTOS DE ENTRADA REALES
(`run_banco04.main`, `banco04_validar_jueces.main`, `banco04_juzgar.main`, `banco04_decidir.main`,
`banco04_medir_codex.main`, `puerta.decidir`, `puerta.medir_linea_base`), nunca por funciones
internas: así se prueba la alcanzabilidad desde `main`. Lo que todavía no existe queda en ROJO con
el motivo (módulo o interfaz ausente); nada se salta.

Bloques:
  0   autocontrol de los fixtures (único bloque verde hoy por diseño: no toca piezas nuevas)
  A   alcanzabilidad estática (firmas de la puerta, metricas.py sin conclusiones, sin puerta trasera)
  V   regla de vinculación de la negación (§3.6, V1-V9): señal vendorizada y de punta a punta
  E   E2E-1 … E2E-18 sobre el esqueleto (§6.1-§6.2)
  F17 fixture completo (§6.3) que con `_prueba` tiene que dar `aprueba`
  S   familia S (S01-S23): mutación semántica regenerada desde `main`
  I   familia I (I01-I15): edición incoherente del crudo → código exacto
  INV familia inversa: mutar derivados no cambia el veredicto
  EXT recorrido positivo de la extensión (F17-ext) y sus variantes
  R13 contraejemplos de la estimación de Codex (10 + 1.000 ⇒ 1.263, redondeos)
  E2E-19 veredicto de CUOTA separado y por intervalo (§4.5: 1, 2, 3, 3b, 3c, 3d, 3e, 4, 5, 6, 7, 7b, 8)
  P   perímetro: nada se escribe bajo `backend/`

Offline: no llama proveedores (dobles en memoria), no toca la base 55432 ni la custodia real ni el
registro de uso real. E2E-1 y las tres mutaciones del esqueleto con base de datos exigen el clúster
aislado 55448: sin él terminan en ROJO con «clúster aislado no disponible», nunca en verde.

Exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_banco04_cadena.py
    .venv\\Scripts\\python.exe execution\\test_banco04_cadena.py --solo E2E-3,S01      (por tramos)
"""
from __future__ import annotations

import inspect
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "execution"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from fixtures_banco04_cadena import entorno  # noqa: E402

_ARGS = sys.argv[1:]
_MODO_BD = "--modo-bd" in _ARGS
if _MODO_BD:
    entorno.preparar_proceso(env_real=Path(_ARGS[_ARGS.index("--modo-bd") + 1]))
else:
    entorno.preparar_proceso()

from fixtures_banco04_cadena import autocontrol  # noqa: E402
from fixtures_banco04_cadena import custodia_falsa as CF  # noqa: E402
from fixtures_banco04_cadena import dobles, firmas  # noqa: E402
from fixtures_banco04_cadena import escenario as ESC  # noqa: E402
from fixtures_banco04_cadena.escenario import PuntoDeEntradaAusente, codigos, condiciones, valores  # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ════════════════════════════════════════════════════════════════════════════════════════
# Vocabulario cerrado (§3.8) y conjuntos de motivos
# ════════════════════════════════════════════════════════════════════════════════════════
VOCABULARIO = frozenset("""
cadena_ilegible custodia_no_coincide identidad_version arbol_sucio corridas_con_dobles
evaluador_no_congelado base_no_comparable_reproducir perimetro_parche muestra_incompleta repeticiones
texto_ausente caso_digest_no_coincide jurisdiccion_no_coincide ledger_incompleto ledger_sin_contexto
juicio_incompleto juicio_contradictorio paquete_no_coincide rep_sha256_no_coincide decision_r_no_coincide
plan_aprobaciones_no_coincide codex_piloto_sin_estimacion codex_sin_permiso cadenas_no_coinciden
discordancias_sin_resolver incoherencia_matriz negativa_correcta_contradictoria kappa_reservado kappa_real
circuito_no_utilizable validacion_reservada_ausente reservado_retirado falsos_bloqueos_sin_dato
informe_del_muro_ausente cambio_de_motor_contradictorio sin_dato par_faltante no_concluyente_sin_extension
extension_sin_causa extension_no_coincide extension_incompleta submuestra_incompleta
techo_sin_aprobacion atribucion_mapa_no_coincide telemetria_contradictoria instantaneas_de_prueba
telemetria_acreditada_no_coincide circuito_suspendido llamada_tras_desconocido_sin_autorizacion
reanudacion_invalida identidad_efectiva_ausente acreditacion_ambigua acreditacion_snapshot_distinto
no_enviado_contradictorio seq_incoherente estimacion_codex_no_reproducible entrada_no_permitida
entrada_inaccesible
""".split())
# §6.1 E: motivos esperados del esqueleto (sin `_prueba`) y F: prohibidos.
E_ESQUELETO = frozenset({"muestra_incompleta", "corridas_con_dobles", "arbol_sucio",
                         "validacion_reservada_ausente", "sin_dato", "par_faltante"})
F_ESQUELETO = frozenset({"cadena_ilegible", "custodia_no_coincide", "identidad_version", "evaluador_no_congelado",
                         "base_no_comparable_reproducir", "perimetro_parche", "repeticiones", "texto_ausente",
                         "caso_digest_no_coincide", "jurisdiccion_no_coincide", "ledger_incompleto",
                         "ledger_sin_contexto", "juicio_incompleto", "juicio_contradictorio",
                         "paquete_no_coincide", "rep_sha256_no_coincide", "decision_r_no_coincide",
                         "plan_aprobaciones_no_coincide", "telemetria_contradictoria",
                         "telemetria_acreditada_no_coincide", "acreditacion_ambigua",
                         "acreditacion_snapshot_distinto", "identidad_efectiva_ausente",
                         "llamada_tras_desconocido_sin_autorizacion", "seq_incoherente",
                         "no_enviado_contradictorio", "reanudacion_invalida", "circuito_suspendido",
                         "no_concluyente_sin_extension", "extension_sin_causa", "extension_no_coincide",
                         "extension_incompleta", "entrada_no_permitida", "entrada_inaccesible",
                         "consumo_desconocido_sin_cota"})
# §3.8 v7: `consumo_desconocido_sin_cota` es SOLO código de parada en ejecución y causa del máximo ∞
# de la cuota; NUNCA motivo de calidad (por eso no está en VOCABULARIO y `vocab_ok` lo rechaza).
CODIGO_SOLO_PARADA = "consumo_desconocido_sin_cota"
AVISO_ESTIMADA = ("Cuota estimada: el consumo real está en el intervalo publicado y cruza el umbral; la cifra "
                  "puntual es una estimación empírica no garantizada y no certifica el techo")
CUOTA_TOKENS = ("claude_", "codex_", "inferencia", "atribu", "C25", "techo", "tokens_por_operacion")
CALIDAD_TOKENS = ("afirmaciones", "fuga", "cobertura", "kappa", "discordancias", "definitivo", "omision",
                  "utilidad", "aprobacion_sin_edicion", "turnos", "falsos_bloqueos", "cambio_de_motor",
                  "abstencion", "decisivos", "alcance")
CODIGOS_CALIDAD = frozenset({"discordancias_sin_resolver", "incoherencia_matriz", "negativa_correcta_contradictoria",
                             "kappa_reservado", "kappa_real", "circuito_no_utilizable", "sin_dato", "par_faltante"})
CASO = "caducidad-reparacion-directa"           # PR:35, A-canónicos (esqueleto, §6.1)
CASO_VOL = "expediente-voluminoso-cruce-disperso"
VERS_ESQ = ("base-esq", "nuevo-esq")
REF_PIPE = "aprobacion-pipe-chat-2026-10-12-prueba"     # referencia de prueba de la aprobación de Pipe
CLAVES_TIEMPO = ("utc", "fecha", "timestamp", "generado", "registrada", "duracion", "segundos", "_ms")


def vocab_ok(v) -> bool:
    """Todo código emitido pertenece al vocabulario cerrado (no vacío si no certifica)."""
    if not isinstance(v, dict):
        return False
    cs = codigos(v)
    if v.get("veredicto") == "no_certificable" and not cs:
        return False
    return cs <= VOCABULARIO


def cuota(v) -> dict:
    return ((v or {}).get("cuota") or {}) if isinstance(v, dict) else {}


def cuota_estimada(v, ids=()) -> bool:
    """§4.5: `estimada`, `resultado: null`, el aviso literal, alguna condición `estimada` y los
    intentos sin cota indicados en `intentos_sin_cota`."""
    c = cuota(v)
    return (c.get("estado") == "estimada" and c.get("resultado") is None and c.get("aviso") == AVISO_ESTIMADA
            and any(x.get("estado") == "estimada" for x in c.get("condiciones") or [])
            and set(ids) <= set(c.get("intentos_sin_cota") or []))


def cuota_certificada(v, resultado: str) -> bool:
    c = cuota(v)
    conds = c.get("condiciones") or []
    if not (c.get("estado") == "certificada" and c.get("resultado") == resultado and conds):
        return False
    if resultado == "cumple":
        return all(x.get("estado") == "certificada_cumple" for x in conds)
    return any(x.get("estado") == "certificada_excede" for x in conds)


def sin_motivo_de_cuota(v) -> bool:
    """La calidad no lleva ningún motivo por consumo (§3.1, §3.8 v7)."""
    return isinstance(v, dict) and CODIGO_SOLO_PARADA not in codigos(v)


def separacion_estricta(v) -> bool:
    """E2E-19.8: ninguna condición de cuota entre las de calidad ni al revés; la cuota existe."""
    if not isinstance(v, dict) or not cuota(v).get("condiciones"):
        return False
    cal = [str(c.get("id", "")) for c in v.get("condiciones") or []]
    cuo = [str(c.get("id", "")) for c in cuota(v).get("condiciones") or []]
    return (not [i for i in cal if any(t in i for t in CUOTA_TOKENS)]
            and not [i for i in cuo if any(t in i for t in CALIDAD_TOKENS)] and sin_motivo_de_cuota(v))


def frase(caso_id: str = CASO) -> str:
    caso = next(c for c in CF.casos_visibles() if c.id == caso_id)
    return CF.plan_de_caso(caso)["hechos"][0]["frase"]


def sin_tiempo(x):
    if isinstance(x, dict):
        return {k: sin_tiempo(v) for k, v in x.items() if not any(t in k.lower() for t in CLAVES_TIEMPO)}
    if isinstance(x, list):
        return [sin_tiempo(v) for v in x]
    return x


# ════════════════════════════════════════════════════════════════════════════════════════
# Memo de escenarios (cada uno se construye una sola vez; su fallo se reporta en cada prueba)
# ════════════════════════════════════════════════════════════════════════════════════════
_MEMO: dict = {}


class EscenarioNoDisponible(RuntimeError):
    pass


def memo(nombre: str, fn):
    if nombre not in _MEMO:
        try:
            _MEMO[nombre] = ("ok", fn())
        except Exception as exc:  # noqa: BLE001
            detalle = f"{type(exc).__name__}: {exc}"
            if not isinstance(exc, (PuntoDeEntradaAusente, EscenarioNoDisponible)):
                traceback.print_exc()
            _MEMO[nombre] = ("error", detalle[:400])
    estado, valor = _MEMO[nombre]
    if estado == "error":
        raise EscenarioNoDisponible(f"{nombre} no disponible: {valor}")
    return valor


def exigir(cond: bool, motivo: str) -> None:
    if not cond:
        raise EscenarioNoDisponible(motivo)


# ════════════════════════════════════════════════════════════════════════════════════════
# Constructores de escenarios
# ════════════════════════════════════════════════════════════════════════════════════════
def construir_esqueleto(nombre: str, *, guion_base=None, guion_nuevo=None, prov_base=None, prov_nuevo=None,
                        instantanea=None, runners=None, juzgar: bool = True, decidir: bool = True,
                        medir_codex_nuevo: bool = False, versiones=VERS_ESQ,
                        reanudar_si_para: bool = False) -> dict:
    """§6.1 con `mundo=` (sin base de datos): 1 caso, 1 repetición, dos versiones, Bloque 7."""
    esc = ESC.Escenario(nombre, instantanea=instantanea, versiones=versiones)
    b, n = versiones
    out: dict = {"esc": esc}
    if medir_codex_nuevo:
        out["medir"] = esc.medir_codex(n)
    out["prod_base"] = esc.producir_y_aprobar(b, guion=guion_base, proveedores=prov_base, casos=[CASO],
                                              solo_piloto=True, custodiados=False)
    out["prod_nuevo"] = esc.producir_y_aprobar(n, guion=guion_nuevo, proveedores=prov_nuevo, casos=[CASO],
                                               solo_piloto=True, custodiados=False)
    if juzgar:
        out["cadena"] = esc.registrar_cadena(base=b, nuevo=n)
        out["juicio"] = esc.juzgar(runners)
        if out["juicio"] != 0 and reanudar_si_para:
            out["juicio_reanudado"] = esc.juzgar(runners, reanudar=REF_PIPE)
    if decidir:
        out["cli"] = esc.decidir_cli("veredicto", base=b, nuevo=n)
        out["v"] = out["cli"][1]
    return out


def esqueleto() -> dict:
    return memo("esqueleto", lambda: construir_esqueleto("esqueleto"))


ATRIBUCION = {"analisis": ["cobertura_hechos_materiales"], "redaccion": ["aprobacion_sin_edicion_proxy"]}


def construir_f17(nombre: str = "f17", *, guion_nuevo=None, prov_nuevo=None, con_codex: bool = False) -> dict:
    """§6.3 · Las dos versiones completas: 17 casos × R, aprobaciones y R9 reservado de prueba,
    todo desde los `main`. Con `_prueba`, la puerta tiene que dar `aprueba`."""
    esc = ESC.Escenario(nombre)
    out: dict = {"esc": esc}
    if con_codex:
        out["medir"] = esc.medir_codex("nuevo")
        exigir(out["medir"] == 0, f"medición previa de Codex terminó con {out['medir']}")
    p = esc.producir_y_aprobar("base")
    exigir(p == (0, 0), f"producción/aprobación de la base terminó con {p}")
    p = esc.producir_y_aprobar("nuevo", guion=guion_nuevo, proveedores=prov_nuevo, atribucion=ATRIBUCION)
    exigir(p == (0, 0), f"producción/aprobación de la nueva terminó con {p}")
    out["vj"] = esc.validar()
    exigir(out["vj"] == 0, f"la validación reservada (VJ main) terminó con {out['vj']}")
    exigir(esc.registrar_cadena() == 0, "registrar-cadena falló")
    out["juicio"] = esc.juzgar()
    exigir(out["juicio"] == 0, f"juzgar terminó con {out['juicio']}")
    out["v"] = esc.decidir(prueba=True)
    return out


def f17() -> dict:
    return memo("f17", construir_f17)


def f17_aprueba() -> dict:
    d = f17()
    exigir(d["v"].get("veredicto") == "aprueba",
           f"F17 con `_prueba` no da `aprueba` (da {d['v'].get('veredicto')}, motivos {sorted(codigos(d['v']))[:6]}): "
           "la familia no prueba nada")
    return d


def regenerar(nombre: str, *, nuevo: dict | None = None, base: dict | None = None, runners=None,
              vj_runners=None, reanudar_si_para: bool = False) -> dict:
    """Familia S: cambia el doble de la etapa y regenera DESDE `main` esa etapa y las posteriores."""
    ref = f17_aprueba()
    regen = [v for v, d in (("base", base), ("nuevo", nuevo)) if d is not None]
    esc = ESC.derivar(ref["esc"], nombre, regenerar=regen, revalidar=vj_runners is not None)
    out: dict = {"esc": esc, "ref": ref["v"]}
    for v, d in (("base", base), ("nuevo", nuevo)):
        if d is None:
            continue
        kw = dict(d)
        if v == "nuevo":
            kw.setdefault("atribucion", ATRIBUCION)
        out[f"prod_{v}"] = esc.producir_y_aprobar(v, **kw)
    if vj_runners is not None:
        out["vj"] = esc.validar(vj_runners)
    out["cadena"] = esc.registrar_cadena()
    out["juicio"] = esc.juzgar(runners)
    if out["juicio"] != 0 and reanudar_si_para:
        out["juicio_reanudado"] = esc.juzgar(runners, reanudar=REF_PIPE)
    out["v"] = esc.decidir(prueba=True)
    return out


def editar(nombre: str, fn, *, base_escenario=None) -> dict:
    """Familia I: copia F17 (ya juzgado), edita el crudo en disco SIN regenerar y decide."""
    ref = base_escenario or f17_aprueba()
    esc = ESC.copiar(ref["esc"], nombre)
    info = fn(esc)
    return {"esc": esc, "info": info, "ref": ref["v"], "v": esc.decidir(prueba=True)}


# ════════════════════════════════════════════════════════════════════════════════════════
# Utilidades de comparación (familia S)
# ════════════════════════════════════════════════════════════════════════════════════════
P1 = ("afirmaciones_sin_respaldo", "discordancias", "fuga_jurisdiccion", "kappa_salidas_reales", "kappa_real",
      "aprobacion_sin_edicion_proxy")
P2 = ("cobertura", "definitivo_con_lectura_insuficiente", "definitivo_con_hecho_decisivo_omitido",
      "definitivo_con_hecho_no_disponible", "omision", "utilidad", "abstencion_injustificada",
      "aprobacion_sin_edicion_proxy", "perdida", "decisivos_estables")
MATERIAL = P2 + ("alcance",)
TEXTO = P1 + P2 + ("alcance",)
CONSUMO = ("techo", "token", "inferencia", "extremo", "ponderado", "agregado", "codex", "claude", "atribu",
           "C25", "circuito", "presupuesto", "consumo")
JUICIO = ("evaluacion_completa", "juicio") + P1 + P2
FALLO = ("turnos_completados", "completitud", "muestra", "repeticion") + TEXTO + CONSUMO
VJ_CIERRE = ("circuito", "kappa_reservado")


def fuera_del_cierre(ref: dict, mut: dict, cierre) -> list[str]:
    """Condiciones que cambiaron (valor o estado) y cuyo id no contiene ningún token del cierre."""
    antes = {c.get("id"): (c.get("valor"), c.get("estado")) for c in (ref or {}).get("condiciones") or []}
    despues = {c.get("id"): (c.get("valor"), c.get("estado")) for c in (mut or {}).get("condiciones") or []}
    malas = []
    for k in set(antes) | set(despues):
        if antes.get(k) != despues.get(k) and not any(t in str(k) for t in cierre):
            malas.append(str(k))
    return sorted(malas)


def cambio(ref: dict, mut: dict, metrica: str, pred) -> bool:
    """Alguna condición de `metrica` cambió de valor y cumple `pred(antes, despues)`."""
    a = {c.get("id"): c.get("valor") for c in condiciones(ref, metrica)}
    d = {c.get("id"): c.get("valor") for c in condiciones(mut, metrica)}
    return any(k in a and a[k] != d[k] and pred(a[k], d[k]) for k in d)


def num(x):
    try:
        return Fraction(str(x))
    except (ValueError, TypeError, ZeroDivisionError):
        return None


def sube(a, d) -> bool:
    na, nd = num(a), num(d)
    return na is not None and nd is not None and nd > na


def baja(a, d) -> bool:
    na, nd = num(a), num(d)
    return na is not None and nd is not None and nd < na


def r4_de(esc, version: str, pred) -> list[dict]:
    return [f for f in esc.r4(version) if pred(f)]


def desconocida_sin_cota(f: dict) -> bool:
    uv = f.get("uso_validado") or {}
    return f.get("estado") == "cerrada" and uv.get("consumo_conocido") is False and \
        (f.get("cota") or {}).get("tokens_cota_superior") is None


# ════════════════════════════════════════════════════════════════════════════════════════
# A · Alcanzabilidad estática
# ════════════════════════════════════════════════════════════════════════════════════════
METRICAS_ELIMINADAS = ("veredicto_global", "validar_inventario", "atribucion_valida",
                       "filas_comparativas_obligatorias", "_motivos_recibo", "casos_para_extension")
METRICAS_INTERNAS = ("evaluar_absolutos", "consumo", "techo_cuota")
PARAMS_CONCLUSION = frozenset({"cumple", "resultado", "resultados", "R_por_caso", "r_por_caso", "usage_by_node",
                               "absolutos", "suspendido", "salidas_sin_juzgar", "otros_motivos_no_certificable",
                               "filas_extra", "techo", "atribuciones", "kappa_real", "kappa_reservado",
                               "circuito", "evaluacion_completa", "inventario", "recibo", "evaluada",
                               "decisivos_base", "decisivos_nuevo", "comparativa", "veredictos"})
# Firmas conservadas por §7.1 (las de HOY: el contrato las conserva tal cual).
METRICAS_CONSERVADAS = {
    "clasificar_alcance": None, "envio_desde_material": None, "ref_disponible": None, "disponible": None,
    "punto_disponible": None, "estado_cobertura": None, "celda": None, "senal_fuga": None,
    "metricas_corrida": None, "agregar_casos": None, "agregar_estratos": None, "bootstrap_casos": None,
    "veredicto_comparativo": None, "pares_comparativos": None, "comparar_metrica": None,
    "veredicto_tras_extension": None, "perdidas_por_caso": None, "decisivos_estables_perdidos": None,
    "texto_cota": None, "verificar_lenguaje": None, "resumen_publicable": None, "inventario_esperado": None,
    "casos_de_unidad": None, "discrepancias_marcador": None, "alcance_desde_fragmentos": None,
    "hechos_y_puntos_desde_clave": None, "candidatas_negativa_falsa": None, "rango_valido": None,
}
METRICAS_NUEVAS = {"falsos_bloqueos_corrida": ("informe", "fuentes"),
                   "cambio_de_motor_corrida": ("fallbacks", "filas_R4"), "casos_extension": None}


def a8_vj_exigencias() -> bool:
    import banco04_validar_jueces as VJ
    if "consumo" in inspect.signature(VJ.evaluar_exigencias).parameters:
        return False
    conj = CF.conjunto_mutaciones("reservado")
    items = VJ.validar_conjunto(conj)
    rn = dobles.runners()
    por = [VJ.evaluar_item(it, opus=rn["opus"], codex=rn["codex"], llave=autocontrol.LLAVE) for it in items]
    res = [x for it in por for x in it["verdades"]]
    pares = [q for it in por if it["estado"] == "evaluada" for q in it["pares_kappa"]]
    acr = {"ok": True, "motivos": []}
    ok_sin = VJ.evaluar_exigencias(res, tipo="reservado", discordancias=0, pares_kappa=pares, acreditacion=acr)
    con_disc = VJ.evaluar_exigencias(res, tipo="reservado", discordancias=1, pares_kappa=pares, acreditacion=acr)
    sin_acr = VJ.evaluar_exigencias(res, tipo="reservado", discordancias=0, pares_kappa=pares, acreditacion=None)
    conservadas = {"salidas_sin_evaluar", "discordancias_sin_resolver", "acreditacion_compatibilidad_v13",
                   "sensibilidad_final", "falsos_positivos_finales", "kappa", "sensibilidad_clausula_breve"}
    return (ok_sin.get("circuito_utilizable") is True and "consumo_certificable" not in ok_sin.get("exigencias", {})
            and conservadas <= set(ok_sin.get("exigencias", {}))
            and con_disc.get("circuito_utilizable") is False and sin_acr.get("circuito_utilizable") is False)


def bloque_a() -> None:
    print("\nA · alcanzabilidad estática (firmas, sin conclusiones como parámetro, sin puerta trasera)")
    import importlib
    for mod in ("mia.eval.banco04.telemetria", "mia.eval.banco04.registros", "mia.eval.banco04.reproduccion",
                "mia.eval.banco04.puerta", "banco04_juzgar", "banco04_decidir", "banco04_medir_codex",
                "banco04_medir_fondo_cli"):
        try:
            importlib.import_module(mod)
            ok = True
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"       {mod}: {type(exc).__name__}: {exc}")
        check(f"A1 existe el módulo de la cadena {mod} (§1.2)", ok)
    check("A1 existe el directorio de PRODUCCIÓN de instantáneas `telemetria_acreditada/` (§4.4; las pruebas no "
          "escriben en él)", entorno.DIR_INSTANTANEAS.is_dir())
    # A1b · los `main` reciben `instantaneas_dir=` y `banco04_decidir.main` recibe `_prueba=` (§4.4, §6.4.4)
    import importlib as _il
    for mod in ("run_banco04", "banco04_validar_jueces", "banco04_juzgar", "banco04_medir_codex",
                "banco04_medir_fondo_cli"):
        try:
            ps = inspect.signature(_il.import_module(mod).main).parameters
            ok = "instantaneas_dir" in ps and ps["instantaneas_dir"].kind == inspect.Parameter.KEYWORD_ONLY
        except Exception:  # noqa: BLE001
            ok = False
        check(f"A1b `{mod}.main` acepta `instantaneas_dir=` solo como parámetro de Python (keyword-only)", ok)
    try:
        ps = inspect.signature(_il.import_module("banco04_decidir").main).parameters
        ok = ("_prueba" in ps and ps["_prueba"].kind == inspect.Parameter.KEYWORD_ONLY and ps["_prueba"].default is None
              and "instantaneas_dir" not in ps)
    except Exception:  # noqa: BLE001
        ok = False
    check("A1b `banco04_decidir.main(argv, *, _prueba=None)` (§3.1) y sin `instantaneas_dir`", ok)
    # A2 · firma exacta de la puerta
    try:
        puerta = importlib.import_module("mia.eval.banco04.puerta")
        for fn, esperados in ((getattr(puerta, "decidir", None), {"dir_nuevo", "dir_base", "custodia", "cadena"}),
                              (getattr(puerta, "medir_linea_base", None), {"dir_base", "custodia", "cadena"})):
            if fn is None:
                check("A2 la puerta expone `decidir` y `medir_linea_base`", False)
                continue
            ps = inspect.signature(fn).parameters
            solo_kw = all(p.kind == inspect.Parameter.KEYWORD_ONLY for p in ps.values())
            nombres = set(ps)
            check(f"A2 `{fn.__name__}` es keyword-only con EXACTAMENTE {sorted(esperados)} + `_prueba` (§3.1)",
                  solo_kw and nombres == esperados | {"_prueba"} and ps["_prueba"].default is None
                  and all(ps[n].default is inspect.Parameter.empty for n in esperados))
        pp = getattr(puerta, "PruebaPuerta", None)
        firma_pp = dict(inspect.signature(pp).parameters) if pp is not None else {}
        esperada = {"manifiesto_custodia": None, "desproteger": None, "directorio_instantaneas": None,
                    "aceptar_dobles": False, "aceptar_arbol_sucio": False}
        check("A2 `PruebaPuerta` tiene EXACTAMENTE las relajaciones separadas de §3.1 v6 con sus valores por "
              "defecto (manifiesto, desproteger, directorio de instantáneas, aceptar_dobles, aceptar_arbol_sucio)",
              set(firma_pp) == set(esperada) and all(firma_pp[k].default == d for k, d in esperada.items()))
        rm = getattr(puerta, "RUTA_MANIFIESTO_REPO", None)
        check("A2 la puerta fija `RUTA_MANIFIESTO_REPO` = `custodia_manifest.json` del repo (§3.1 v6)",
              rm is not None and Path(rm).resolve() == (entorno.BACKEND / "mia/eval/banco04/custodia_manifest.json").resolve())
    except Exception as exc:  # noqa: BLE001
        check(f"A2 firma de la puerta (no importa: {type(exc).__name__}: {exc})", False)
    # A3 · metricas.py no recibe conclusiones
    from mia.eval.banco04 import metricas as M
    publicas = {n: f for n, f in inspect.getmembers(M, inspect.isfunction)
                if f.__module__ == M.__name__ and not n.startswith("_")}
    for n in METRICAS_ELIMINADAS:
        check(f"A3 `metricas.{n}` ya no existe (§7.1: aceptaba conclusiones o se sustituye)", not hasattr(M, n))
    for n in METRICAS_INTERNAS:
        check(f"A3 `metricas.{n}` deja de ser pública (§7.1: pasa a interna, solo la llama la puerta)", n not in publicas)
    for n, f in inspect.getmembers(M, inspect.isfunction):
        if f.__module__ == M.__name__ and "evaluar_absolutos" in n:
            prohibidos = {"kappa_real", "kappa_reservado", "circuito", "evaluacion_completa"} & set(
                inspect.signature(f).parameters)
            check(f"A3 `{n}` ya no recibe {sorted(prohibidos) or 'kappa/circuito/evaluación'} (son conclusiones, §7.1)",
                  not prohibidos)
    for n, params in METRICAS_NUEVAS.items():
        f = publicas.get(n)
        check(f"A3 `metricas.{n}` existe (§3.3 C, §3.4, §7.4)" + (f" con parámetros {params}" if params else ""),
              f is not None and (params is None or tuple(inspect.signature(f).parameters)[:len(params)] == params))
    ajenas = []
    for n, f in publicas.items():
        if n in METRICAS_CONSERVADAS or n in METRICAS_NUEVAS or n in METRICAS_ELIMINADAS or n in METRICAS_INTERNAS:
            continue                      # las eliminadas e internas ya tienen su propia prueba arriba
        malos = PARAMS_CONCLUSION & set(inspect.signature(f).parameters)
        if malos:
            ajenas.append(f"{n}({sorted(malos)})")
    check(f"A3 ninguna función pública nueva de `metricas` recibe una conclusión {ajenas[:4]}",
          not ajenas and "falsos_bloqueos_corrida" in publicas)
    # A4 · sin puerta trasera en la línea de comandos (E2E-7)
    ruta = ROOT / "execution" / "banco04_decidir.py"
    if ruta.is_file():
        src = ruta.read_text(encoding="utf-8")
        ayuda = subprocess.run([sys.executable, "-X", "utf8", str(ruta), "--help"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=120, cwd=str(ROOT), env=dict(os.environ))
        texto = (ayuda.stdout or "") + (ayuda.stderr or "")
        sub = all(s in texto for s in ("veredicto", "previa", "linea-base"))
        check("E2E-7 `banco04_decidir.py --help` lista `veredicto`, `previa` y `linea-base` y ningún flag "
              "de prueba ni de dobles (§3.1, IC-7)",
              sub and not any(t in texto.lower() for t in ("--prueba", "_prueba", "--dobles", "modo_prueba", "--test")))
        check("E2E-7 el código de `banco04_decidir.py` no construye `PruebaPuerta` ni pasa `_prueba`",
              "PruebaPuerta" not in src and "_prueba" not in src)
    else:
        check("E2E-7 existe `execution/banco04_decidir.py` (sin él no se puede probar que no tiene puerta trasera)", False)
    # A5 · el nodo se lee de `metrics.usage._node` (§4.2): el nombre queda fijado
    from mia.metrics import usage
    check("A5 `metrics.usage._node` existe y es una ContextVar (§4.2: si cambia de nombre, esta prueba "
          "se pone roja)", type(getattr(usage, "_node", None)).__name__ == "ContextVar")
    # A6 · constante de identidades retiradas (K3)
    import banco04_validar_jueces as VJ
    ret = getattr(VJ, "IDENTIDADES_RESERVADO_RETIRADAS", None)
    check("A6 `IDENTIDADES_RESERVADO_RETIRADAS` existe en VJ, es inmutable, no vacía y de identidades hex de 64 "
          "(R9, K3: el director registra el reservado retirado)",
          isinstance(ret, frozenset) and len(ret) >= 1
          and all(isinstance(x, str) and len(x) == 64 and all(c in "0123456789abcdef" for c in x) for x in ret))
    # A7 · los módulos nuevos entran en la huella del evaluador (§1.2)
    from mia.eval.banco04 import jueces
    arch = " ".join(getattr(jueces, "ARCHIVOS_EVALUADOR", ())) + " " + " ".join(
        getattr(jueces, "ARCHIVOS_EVALUADOR_REPO", ()))
    faltan = [m for m in ("telemetria.py", "registros.py", "reproduccion.py", "puerta.py", "banco04_juzgar.py",
                          "banco04_decidir.py") if m not in arch]
    check(f"A7 la huella del evaluador incluye los módulos nuevos de §1.2 (faltan {faltan})", not faltan)
    check("A7 las instantáneas de acreditación NO entran en la huella del evaluador (K13)",
          "telemetria_acreditada" not in arch and not faltan)
    # A8 · §8.6 bis: de la habilitación de VJ SOLO se retira `consumo_certificable`
    check("A8 `evaluar_exigencias` de VJ ya no recibe `consumo` ni exige `consumo_certificable`; conserva "
          "salidas sin evaluar, discordancias, acreditación v1.3, sensibilidades, falsos positivos, kappa y "
          "cláusula breve (§8.6 bis)", a8_vj_exigencias())


# ════════════════════════════════════════════════════════════════════════════════════════
# V · regla de vinculación de la negación (§3.6)
# ════════════════════════════════════════════════════════════════════════════════════════
V_TEXTOS = {
    "V1": ("La Ley 100 de 1993 es aplicable al caso y no consta la fecha del contrato", True),
    "V2": ("La Ley 100 de 1993, que no consta en el expediente, es aplicable al caso", True),
    "V3": ("No puedo verificar, por falta de fuentes, la Ley 100 de 1993", False),
    "V4": ("La Ley 100 de 1993 es aplicable al caso, aunque no consta la fecha del contrato", True),
    "V5": ("No consta que la Ley 100 de 1993 sea aplicable", False),
    "V6": ('La numeración "Ley 4137" no corresponde a ninguna ley verificable', False),
    "V7": ("La Ley 100 de 1993 no consta en el expediente pero es aplicable", True),
    "V8": ("No puedo verificar la Ley 100 de 1993 ni la Ley 200 de 1995", False),
    "V9": ("La Ley 100 de 1993, que es aplicable al caso, no consta en el expediente", True),
}


def bloque_v() -> None:
    print("\nV · §3.6 negación vinculada a la proposición de la cita (V1-V9, obligatorias)")
    from mia.eval.banco04 import evaluador_congelado as EV
    for k, (texto, fuga) in V_TEXTOS.items():
        r = EV.jurisdiction_leak_signal(texto + ".")
        check(f"{k} señal vendorizada: «{texto}» ⇒ {'FUGA' if fuga else 'sin fuga'}", r.get("leak") is fuga)
    # De punta a punta: el texto va en el borrador del mundo, los jueces NO marcan fuga, y la condición
    # `fuga_jurisdiccion` de la puerta la decide la señal (fila 2 de §3.3 B) recalculada desde R2.
    for k, (texto, fuga) in V_TEXTOS.items():
        try:
            d = memo(f"V-{k}", lambda texto=texto, k=k: construir_esqueleto(
                f"v-{k.lower()}", guion_nuevo=dobles.Guion(texto_extra_borrador={CASO: texto}),
                runners=dobles.runners(opus=dobles.Reglas(sin_fuga=True), codex=dobles.Reglas(sin_fuga=True))))
            vals = [num(x) for x in valores(d["v"], "fuga_jurisdiccion")]
            ok = bool(vals) and (any(x is not None and x > 0 for x in vals) if fuga
                                 else all(x == 0 for x in vals)) and vocab_ok(d["v"])
            check(f"{k} punta a punta (mundo → juzgar → puerta): `fuga_jurisdiccion` {'> 0' if fuga else '= 0'} "
                  f"(valores {vals})", ok)
        except EscenarioNoDisponible as exc:
            check(f"{k} punta a punta: {exc}", False)


# ════════════════════════════════════════════════════════════════════════════════════════
# E · pruebas de punta a punta sobre el esqueleto
# ════════════════════════════════════════════════════════════════════════════════════════
def e2e_1() -> None:
    print("\nE2E-1 · alcanzabilidad con base de datos (clúster aislado 55448)")
    ok, motivo, env = entorno.cluster_aislado()
    if not ok:
        check(f"E2E-1 no ejecutable: {motivo}", False)
        for m in ("sin_respaldo", "cobertura", "alcance"):
            check(f"E2E-1 mutación semántica del esqueleto ({m}) no ejecutable: {motivo}", False)
        return
    r = subprocess.run([sys.executable, "-X", "utf8", __file__, "--modo-bd", str(env)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=3600, cwd=str(ROOT))
    print(r.stdout[-6000:])
    lineas = [x for x in (r.stdout or "").splitlines() if x.startswith("RESULTADO_BD ")]
    if not lineas:
        check(f"E2E-1 el proceso con base de datos no devolvió resultados (exit {r.returncode}): "
              f"{(r.stderr or '')[-400:]}", False)
        return
    for nombre, okk in json.loads(lineas[-1][len("RESULTADO_BD "):]):
        check(nombre, okk)


def modo_bd() -> int:
    """Proceso hijo de E2E-1: esqueleto con `run_case` real (sin `mundo=`), solo `proveedores=`."""
    res: list = []

    def chk(n, ok):
        res.append((n, bool(ok)))

    def uno(nombre, runners=None, prov=None):
        esc = ESC.Escenario(nombre, versiones=VERS_ESQ)
        a = esc.producir(VERS_ESQ[0], sin_mundo=True, casos=[CASO], solo_piloto=True, custodiados=False)
        b = esc.producir(VERS_ESQ[1], sin_mundo=True, proveedores=prov, casos=[CASO], solo_piloto=True,
                         custodiados=False)
        a2 = esc.aprobar(VERS_ESQ[0], sin_mundo=True, casos=[CASO], solo_piloto=True, custodiados=False)
        b2 = esc.aprobar(VERS_ESQ[1], sin_mundo=True, proveedores=prov, casos=[CASO], solo_piloto=True,
                         custodiados=False)
        c = esc.registrar_cadena(base=VERS_ESQ[0], nuevo=VERS_ESQ[1])
        j = esc.juzgar(runners)
        code, v, _ = esc.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])
        return esc, (a, b, a2, b2, c, j, code), v
    try:
        esc, codes, v = uno("bd-esqueleto")
        filas = esc.r4(VERS_ESQ[1])
        prod = [f for f in filas if f.get("fase") == "produccion"]
        chk(f"E2E-1 pasos 1-4 desde los `main` terminan (códigos {codes})", codes[:6] == (0, 0, 0, 0, 0, 0))
        chk("E2E-1 R1 con `dobles: true`, R2 rep-01 `completo`, R11 y R12 escritos",
            (esc.r1(VERS_ESQ[1]) or {}).get("dobles") is True
            and (esc.r2(VERS_ESQ[1], CASO, 1) or {}).get("estado") == "completo"
            and (esc.dir(VERS_ESQ[1]) / "decision_r.json").is_file()
            and (esc.dir(VERS_ESQ[1]) / "aprobaciones_plan.json").is_file())
        chk("E2E-1 R4: ≥ 1 fila `produccion` cerrada, con contexto, `nodo` y consumo conocido; cero `en_curso`",
            bool(prod) and all(f.get("estado") == "cerrada" and f.get("caso_id") == CASO and f.get("nodo")
                               and (f.get("uso_validado") or {}).get("consumo_conocido") is True for f in prod)
            and not [f for f in esc.todas_r4() if f.get("estado") == "en_curso"])
        chk("E2E-1 filas R4 `aprobacion_*` y R10 completo",
            any(str(f.get("fase", "")).startswith("aprobacion_") for f in filas))
        chk("E2E-1 R8 antes de la primera fila de juez; R5 con pasada 1 de Opus y Codex",
            esc.cadena.is_file() and any(str(f.get("fase", "")).startswith("juicio_p1_codex") for f in filas))
        cs = codigos(v)
        chk(f"E2E-1 veredicto `no_certificable`, motivos ⊆ E y ninguno de F ({sorted(cs)})",
            (v or {}).get("veredicto") == "no_certificable" and "muestra_incompleta" in cs
            and "corridas_con_dobles" in cs and cs <= E_ESQUELETO and not (cs & F_ESQUELETO) and vocab_ok(v))
        chk("E2E-1 condiciones del caso RECALCULADAS, con fuentes",
            bool((v or {}).get("condiciones")) and all(c.get("fuentes") for c in v["condiciones"]))
        fr = frase()
        _, _, v1 = uno("bd-mut-respaldo", runners=dobles.runners(
            opus=dobles.Reglas(forzar_defecto=frozenset({fr[:20]})),
            codex=dobles.Reglas(forzar_defecto=frozenset({fr[:20]}))))
        chk("E2E-1 mutación semántica (sin_respaldo en Opus y Codex) ⇒ `afirmaciones_sin_respaldo` 0 → 1",
            cambio(v, v1, "afirmaciones_sin_respaldo", sube))
        _, _, v2 = uno("bd-mut-cobertura", runners=dobles.runners(opus=dobles.Reglas(no_cubiertos={CASO: True})))
        chk("E2E-1 mutación semántica (pasada 2 `cubierto=false`) ⇒ baja la cobertura de decisivos",
            cambio(v, v2, "cobertura_hechos_decisivos", baja))
        _, _, v3 = uno("bd-mut-alcance", prov=dobles.proveedores(embed=dobles.embed_degenerado))
        chk("E2E-1 mutación semántica (proveedor del grafo que recorta el material) ⇒ baja el alcance",
            cambio(v, v3, "alcance", baja))
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        chk(f"E2E-1 con base de datos: {type(exc).__name__}: {exc}", False)
    print("RESULTADO_BD " + json.dumps(res, ensure_ascii=False))
    return 0


def e2e_2_e_inversa_esqueleto() -> None:
    print("\nE2E-2 · la puerta solo lee crudos (inventario cerrado de §3.9 y derivados inertes)")
    try:
        d = esqueleto()
        esc, v = d["esc"], d["v"]
        exigir(isinstance(v, dict) and v.get("condiciones"), "el esqueleto no produjo un veredicto con condiciones")
        leidas = [Path(x.get("ruta", "")) for x in v.get("entradas_leidas") or []]
        permitidas = (esc.S, esc.custodia, entorno.BACKEND / "mia", entorno.ROOT / "execution",
                      esc.manifiesto_custodia.parent, esc.instantaneas_dir)
        fuera = [str(p) for p in leidas if not any(str(p).startswith(str(r)) for r in permitidas)]
        derivados = [str(p) for p in leidas if p.name in ("estado_banco.json", "aprobaciones_estado.json",
                                                          "VEREDICTO.json", "INFORME_LINEA_BASE.json")
                     or p.name.endswith(".derivado.json") or p.name.startswith("usage_by_node")]
        inst = esc.instantaneas_dir / f"{esc.sha_instantanea}.json"      # PruebaPuerta.directorio_instantaneas
        evid = [entorno.ROOT / e["archivo"] for ent in esc.instantanea["entradas"] for e in ent["evidencia"]]
        check(f"E2E-2 `entradas_leidas` ⊆ inventario de §3.9 (fuera: {fuera[:2]}) y sin derivados ({derivados[:2]})",
              bool(leidas) and not fuera and not derivados)
        check("E2E-2 `entradas_leidas` contiene la instantánea citada y CADA archivo de su evidencia (§3.9 punto 3)",
              str(inst) in {str(p) for p in leidas} and all(str(e) in {str(p) for p in leidas} for e in set(evid)))
        check("E2E-2 cada entrada leída lleva su sha256",
              all(len(str(x.get("sha256", ""))) == 64 for x in v.get("entradas_leidas") or []) and bool(leidas))
        editadas = mutar_derivados(esc, VERS_ESQ)
        code, v2, _ = esc.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])
        check("E2E-2 mutar estado_banco, aprobaciones_estado, *.derivado, consumo_resumen, consumo_turno, "
              "consumo_aprobacion, usage_by_node y un VEREDICTO previo deja la salida IDÉNTICA (salvo la hora)",
              bool(editadas) and comparable(v, editadas) == comparable(v2, editadas))
    except EscenarioNoDisponible as exc:
        check(f"E2E-2: {exc}", False)


def mutar_derivados(esc, versiones) -> set:
    """Edita SOLO derivados (§3.9 último párrafo, K1, familia inversa). Devuelve las rutas de crudo cuyo
    contenido cambió por un campo derivado (su sha en `entradas_leidas` cambia legítimamente)."""
    editadas: set = set()
    for ver in versiones:
        dv = esc.dir(ver)
        for nombre in ("estado_banco.json", "aprobaciones_estado.json"):
            (dv / nombre).write_text(json.dumps({"estado": "terminado", "manipulado": True}), encoding="utf-8")
        (dv / "usage_by_node.1234567890.json").write_text(json.dumps({"nodo_falso": 10 ** 9}), encoding="utf-8")
        (dv / "VEREDICTO.json").write_text(json.dumps({"veredicto": "aprueba"}), encoding="utf-8")
        for r2 in sorted(dv.glob("*/rep-??.json")):
            x = ESC.leer(r2)
            if not isinstance(x, dict):
                continue
            for it in x.get("intentos") or []:
                if isinstance(it, dict):
                    it["consumo_resumen"] = {"tokens": 1, "manipulado": True}
            res = x.get("resultado")
            if isinstance(res, dict) and "diagnosis_full" in res:
                res["false_block"] = {"falsos_bloqueos": 99}
                res["jurisdiction_leak"] = {"leak": True}
                res["abstention"] = not bool(res.get("abstention"))
                res["reached_draft"] = not bool(res.get("reached_draft"))
                res["score"] = {"manipulado": True}
            r2.write_text(json.dumps(x, ensure_ascii=False), encoding="utf-8")
            editadas.add(str(r2))
            (r2.with_name(r2.stem + ".juicio.derivado.json")).write_text(
                json.dumps({"decisiones": [], "recuento": {"afirmaciones_sin_respaldo": 0}}), encoding="utf-8")
        for r10 in sorted(dv.glob("*/aprobacion.json")) + sorted(dv.glob("*/aprob.intento-*.json")):
            x = ESC.leer(r10)
            if isinstance(x, dict):
                x["consumo_aprobacion"] = {"tokens": 1}
                x["consumo_turno_reproducido"] = {"tokens": 1}
                for it in x.get("intentos") or []:
                    if isinstance(it, dict):
                        it["consumo_turno"], it["consumo_aprobacion"] = {"tokens": 1}, {"tokens": 1}
                x["consumo_turno"] = {"tokens": 1}
                r10.write_text(json.dumps(x, ensure_ascii=False), encoding="utf-8")
                editadas.add(str(r10))
    return editadas


def comparable(v, editadas: set):
    if not isinstance(v, dict):
        return None
    w = json.loads(json.dumps(v))
    w["entradas_leidas"] = sorted(
        (e.get("ruta"), None if e.get("ruta") in editadas else e.get("sha256")) for e in w.get("entradas_leidas") or [])
    return sin_tiempo(w)


def e2e_3_4() -> None:
    print("\nE2E-3 · telemetría: un componente ausente es desconocido sin cota, nunca cero; detiene")
    try:
        d = memo("e2e3", construir_e2e3)
        esc, n = d["esc"], VERS_ESQ[1]
        filas = esc.r4(n)
        desc = [f for f in filas if f.get("fase") == "produccion" and desconocida_sin_cota(f)]
        check("E2E-3 el doble omite `output_tokens`: la fila R4 queda `consumo_conocido=false`, "
              "`componentes_ausentes=['output_tokens']` y `cota=null`",
              len(desc) == 1 and (desc[0].get("uso_validado") or {}).get("componentes_ausentes") == ["output_tokens"])
        codex_den = [f for f in filas if f.get("proveedor_cuota") == "codex" and f.get("fase") == "produccion"
                     and f.get("estado") == "no_enviado"]
        check("E2E-3 Bloque 7 con presupuesto Codex > 0: la llamada Codex siguiente se DENIEGA "
              "(`ParadaCodexProduccion`, código `consumo_desconocido_sin_cota`, no el de presupuesto) y su fila "
              "queda `no_enviado` con `t_envio_utc == null` (K15)",
              bool(codex_den) and all(f.get("motivo_codigo") == "consumo_desconocido_sin_cota"
                                      and f.get("t_envio_utc") is None and f.get("seq_envio") is None
                                      and f.get("uso_crudo") is None for f in codex_den))
        susp = ESC.archivos(esc.dir(n), "suspensiones/juicio-*.json") + ESC.archivos(esc.dir(VERS_ESQ[0]),
                                                                                    "suspensiones/juicio-*.json")
        contenido = [ESC.leer(s) or {} for s in susp]
        check("E2E-3 la siguiente llamada de juez lanza `CuotaAgotada`: `juzgar` no termina, hay una suspensión "
              "NUEVA `suspensiones/juicio-<seq>.json` con `eventos` = [id de la fila] y su fila de juez es "
              "`no_enviado`",
              d["juicio"] != 0 and any((c.get("eventos") or []) == [desc[0]["id"]] for c in contenido if desc)
              and any(f.get("estado") == "no_enviado" and str(f.get("fase", "")).startswith("juicio")
                      for f in esc.todas_r4()))
        check("E2E-3 en la puerta la CUOTA queda `estimada` (evento en la versión NUEVA, mínimo del cociente "
              "≤ 1,25), con la fila en `intentos_sin_cota` y el aviso literal; la CALIDAD no tiene ningún motivo "
              "por el evento y la denegación NO es una infracción",
              bool(desc) and cuota_estimada(d["v"], [desc[0]["id"]]) and sin_motivo_de_cuota(d["v"])
              and "llamada_tras_desconocido_sin_autorizacion" not in codigos(d["v"]) and vocab_ok(d["v"]))
    except EscenarioNoDisponible as exc:
        check(f"E2E-3: {exc}", False)
    for nombre, prov, desc_txt in (
            ("e2e3-codex-sin-usage", dobles.proveedores(con_codex=True, codex=dobles.CodexCLIDoble(eventos="ninguno")),
             "Codex sin evento `usage`"),):
        try:
            d = memo(nombre, lambda prov=prov, nombre=nombre: construir_esqueleto(
                nombre, prov_nuevo=prov, medir_codex_nuevo=True, reanudar_si_para=True,
                guion_nuevo=dobles.Guion(llamadas=dobles.LLAMADAS_POR_DEFECTO + (("legal_research", "investigacion"),))))
            filas = d["esc"].r4(VERS_ESQ[1])
            cx = [f for f in filas if f.get("proveedor_cuota") == "codex" and f.get("fase") == "produccion"]
            ids = [f["id"] for f in cx if desconocida_sin_cota(f)]
            check(f"E2E-3 variante {desc_txt}: fila desconocida sin cota, el juicio se detiene, la cuota queda "
                  "`estimada` y la calidad sin motivo por el evento",
                  bool(ids) and d.get("juicio") != 0 and cuota_estimada(d.get("v"), ids)
                  and sin_motivo_de_cuota(d.get("v")))
            # E2E-19.6 · Codex sin cota: fondo no medido y calidad intacta
            check("E2E-19.6 Codex sin cota ⇒ `cuota: estimada`, `fondo_observado_fuente = \"no_medido\"` y "
                  "calidad intacta (motivos ⊆ E del esqueleto)",
                  bool(ids) and cuota_estimada(d.get("v"), ids)
                  and all((((f.get("estimacion_empirica") or {}).get("inicial") or {}).get("componentes") or {})
                          .get("fondo_observado_fuente") == "no_medido" for f in cx if f["id"] in ids)
                  and codigos(d.get("v")) <= E_ESQUELETO)
        except EscenarioNoDisponible as exc:
            check(f"E2E-3 variante {desc_txt}: {exc}", False)
    check("E2E-3 variante `cli-codex-eval` con `None`: NO EJECUTABLE con dobles — exige el override del harness "
          "(`_eval_provider_override`) y su `subprocess` (codex_cli_adapter) no está en la lista de §6.1; "
          "probarlo llamaría al CLI real (ver informe)", False)
    # §4.4 · las ocho pruebas del registro de acreditación (producción y juez Codex)
    acreditaciones()
    # variante con cota (K7)
    try:
        d = memo("e2e3-con-cota", lambda: construir_esqueleto(
            "e2e3-con-cota", guion_nuevo=dobles.Guion(llamada_api_fallida={CASO})))
        filas = d["esc"].r4(VERS_ESQ[1])
        api = [f for f in filas if f.get("familia") == "api"]
        check("E2E-3 variante con cota: una fila `api` que falla con `max_tokens` aplicado (1) es desconocida "
              "CON cota, no detiene el juez y el techo sigue certificable (`certificada · cumple`: su máximo "
              "posible no cruza ningún umbral)",
              bool(api) and all((f.get("uso_validado") or {}).get("consumo_conocido") is False
                                and isinstance((f.get("cota") or {}).get("tokens_cota_superior"), int) for f in api)
              and d.get("juicio") == 0 and sin_motivo_de_cuota(d.get("v")) and cuota_certificada(d.get("v"), "cumple")
              and not ESC.archivos(d["esc"].dir(VERS_ESQ[1]), "suspensiones/*.json"))
    except EscenarioNoDisponible as exc:
        check(f"E2E-3 variante con cota: {exc}", False)

    print("\nE2E-4 · reanudación con autorización de Pipe (R6, §5)")
    try:
        d = memo("e2e3", construir_e2e3)
        esc = ESC.copiar(d["esc"], "e2e4")
        code = esc.juzgar(reanudar=REF_PIPE)
        rean = ESC.archivos(esc.dir(VERS_ESQ[0]), "reanudaciones/*.json") + ESC.archivos(
            esc.dir(VERS_ESQ[1]), "reanudaciones/*.json")
        ev = [x for r in rean for x in ((ESC.leer(r) or {}).get("cubre") or {}).get("eventos_desconocidos") or []]
        desc = [f["id"] for f in esc.r4(VERS_ESQ[1]) if f.get("fase") == "produccion" and desconocida_sin_cota(f)]
        check("E2E-4 una reanudación que cubre el evento deja seguir al juez (exit 0) y cubre EXACTAMENTE ese evento "
              "con `referencia_aprobacion_pipe`",
              code == 0 and sorted(ev) == sorted(desc) and bool(desc)
              and all((ESC.leer(r) or {}).get("referencia_aprobacion_pipe") == REF_PIPE for r in rean))
        v = esc.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])[1]
        check("E2E-4 con la reanudación válida la puerta acepta el orden; la reanudación nunca acredita consumo: "
              "la cuota sigue `estimada` y la calidad no tiene motivo por el evento",
              cuota_estimada(v, desc) and sin_motivo_de_cuota(v)
              and not codigos(v) & {"llamada_tras_desconocido_sin_autorizacion", "reanudacion_invalida"})
        # editar una fila cubierta invalida la reanudación
        e2 = ESC.copiar(esc, "e2e4-editada")
        f = next(x for x in e2.r4(VERS_ESQ[1]) if x["id"] in desc)
        f.pop("_ruta", None)
        f["t_fin_utc"] = "2030-01-01T00:00:00Z"
        (e2.dir(VERS_ESQ[1]) / "llamadas" / f"{f['id']}.json").write_text(json.dumps(f), encoding="utf-8")
        v2 = e2.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])[1]
        check("E2E-4 editar una fila cubierta invalida la reanudación (sus llamadas posteriores quedan sin "
              "autorización)",
              bool(codigos(v2) & {"reanudacion_invalida", "llamada_tras_desconocido_sin_autorizacion"}))
        # etapas y versiones
        e3 = ESC.copiar(d["esc"], "e2e4-etapa")
        c3 = e3.juzgar(reanudar=REF_PIPE, etapas="produccion")
        cierre_ev = max(int(y.get("seq_cierre") or 0) for y in e3.r4(VERS_ESQ[1]) if y["id"] in desc)
        check("E2E-4 una reanudación con `etapas: [produccion]` NO autoriza al juez (ningún compromiso de juez "
              "posterior al evento)",
              c3 != 0 and not [x for x in e3.todas_r4() if str(x.get("fase", "")).startswith("juicio")
                               and isinstance(x.get("seq_envio"), int) and x["seq_envio"] > cierre_ev])
        e4 = ESC.copiar(d["esc"], "e2e4-version")
        c4 = e4.juzgar(reanudar=REF_PIPE, versiones=VERS_ESQ[0])
        nuevas = [x for x in e4.r4(VERS_ESQ[1]) if str(x.get("fase", "")).startswith("juicio")]
        check("E2E-4 una reanudación con `versiones: [base]` NO autoriza la nueva (sus llamadas quedan no enviadas)",
              c4 != 0 and any(x.get("estado") == "no_enviado" for x in nuevas)
              and not [x for x in nuevas if x.get("estado") == "cerrada"
                       and x.get("seq_envio", 0) > max((y.get("seq_cierre") or 0) for y in e4.r4(VERS_ESQ[1])
                                                       if y["id"] in desc)])
        # fila de juez falsificada tras un evento no cubierto
        e5 = ESC.copiar(d["esc"], "e2e4-falsa")
        falsificar_juez_tras_evento(e5, VERS_ESQ[1], desc[0])
        v5 = e5.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])[1]
        check("E2E-4 una fila de juez falsificada posterior a un evento no cubierto ⇒ "
              "`llamada_tras_desconocido_sin_autorizacion`",
              "llamada_tras_desconocido_sin_autorizacion" in codigos(v5))
    except (EscenarioNoDisponible, StopIteration, IndexError) as exc:
        check(f"E2E-4: {type(exc).__name__}: {exc}", False)
    e2e_4_validacion()


def construir_e2e3() -> dict:
    """Producción de la nueva con Codex habilitado (R13 desde `banco04_medir_codex main`) y un doble
    del CLI de Claude que omite `output_tokens` en la llamada de redacción; después Codex."""
    prov = dobles.proveedores(claude=OmitirUnaVez(), con_codex=True)
    guion = dobles.Guion(llamadas=dobles.LLAMADAS_POR_DEFECTO + (("legal_research", "investigacion"),))
    return construir_esqueleto("e2e3", prov_nuevo=prov, guion_nuevo=guion, medir_codex_nuevo=True)


def falsificar_juez_tras_evento(esc, version: str, id_evento: str) -> None:
    filas = esc.r4(version)
    ev = next(f for f in filas if f["id"] == id_evento)
    juez = next((f for f in esc.todas_r4() if str(f.get("fase", "")).startswith("juicio")), None)
    plantilla = dict(juez or ev)
    plantilla.pop("_ruta", None)
    seq = max(int(f.get("seq_cierre") or f.get("seq_inicio") or 0) for f in esc.todas_r4()) + 10
    plantilla.update(id=f"juicio_p1_opus-{CASO}-r01-i0-falsa-{seq:06d}", fase="juicio_p1_opus", estado="cerrada",
                     seq_inicio=seq, seq_envio=seq + 1, seq_cierre=seq + 2,
                     t_envio_utc="2030-01-01T00:00:00Z", eventos_desconocidos_vistos=[], exito=True)
    (esc.dir(version) / "llamadas" / f"{plantilla['id']}.json").write_text(json.dumps(plantilla), encoding="utf-8")


def e2e_4_validacion() -> None:
    try:
        esc = ESC.Escenario("e2e4-vj")
        n_items = len(CF.conjunto_mutaciones("reservado")["items"])
        rn = dobles.runners(cli_claude=esc.cli_claude, cli_codex=esc.cli_codex,
                            opus_kw={"romper_uso": lambda i, nombre: i == 7})
        c1 = esc.validar(rn)
        susp = ESC.archivos(esc.dir("nuevo"), "suspensiones/validacion-*.json")
        c2 = esc.validar(rn, reanudar=REF_PIPE)
        reg = ESC.archivos(esc.custodia / "validacion", "*/registro.json")
        marcas = [p for p in esc.appdata.rglob("*") if p.is_file()]
        check("E2E-4 la validación (VJ) se detiene ante un evento sin cota y su reanudación continúa R9 en el primer "
              "ítem pendiente, con la MISMA identidad y SIN un segundo uso del reservado",
              c1 != 0 and bool(susp) and c2 == 0 and len(reg) == 1 and len(marcas) == 1
              and ESC.archivos(esc.dir("nuevo"), "reanudaciones/*.json") and n_items > 0)
        c3 = esc.validar(rn, reanudar=REF_PIPE + "-otra", hash_congelado="f" * 64)
        check("E2E-4 con otro `hash_evaluador`, VJ se niega a reanudar", c3 != 0)
    except (PuntoDeEntradaAusente, EscenarioNoDisponible) as exc:
        check(f"E2E-4 reanudación de la validación: {exc}", False)


def acreditaciones() -> None:
    """§4.4 · registro de acreditaciones (E2E-3 y E2E-16)."""
    esc_cli = ESC.versiones_cli()
    cl, cx = esc_cli
    juez_cl = firmas.firma(firmas.JUEZ_CLAUDE_ARGV)["sha256"]
    juez_cx = firmas.firma(firmas.JUEZ_CODEX_ARGV)["sha256"]

    def sin(inst, sha):
        inst = json.loads(json.dumps(inst))
        inst["entradas"] = [e for e in inst["entradas"] if e["firma_comando"]["sha256"] != sha]
        inst["nota"] += f" sin {sha[:8]}"
        return inst

    def caso(nombre, inst, *, runners=None, prov_nuevo=None, guion_nuevo=None):
        return memo(nombre, lambda: construir_esqueleto(nombre, instantanea=inst, runners=runners,
                                                         prov_nuevo=prov_nuevo, guion_nuevo=guion_nuevo))

    base = firmas.instantanea(cl, cx)
    filas_juez = lambda d, fase: [f for f in d["esc"].todas_r4() if f.get("fase") == fase]  # noqa: E731
    # 1 · varios eventos `usage` de Codex SIN entrada → desconocido (juez Codex)
    try:
        d = caso("acr-1", sin(base, juez_cx), runners=dobles.runners(codex_kw={"eventos_codex": "acumulados"},
                                                                    cli_claude=cl, cli_codex=cx))
        fs = filas_juez(d, "juicio_p1_codex")
        check("§4.4-1 juez Codex con varios eventos `usage` y SIN entrada para su firma ⇒ desconocido y se detiene",
              any((f.get("uso_validado") or {}).get("consumo_conocido") is False for f in fs) and d["juicio"] != 0)
    except EscenarioNoDisponible as exc:
        check(f"§4.4-1: {exc}", False)
    # 2 y 3 · incremental → suma; acumulado → último (juez Codex), y todos los eventos persisten
    for k, conducta in (("2", "incremental"), ("3", "acumulado")):
        try:
            inst = firmas.instantanea(cl, cx, eventos_codex=conducta, etiqueta=conducta)
            d = caso(f"acr-{k}", inst, runners=dobles.runners(codex_kw={"eventos_codex": "acumulados"},
                                                             cli_claude=cl, cli_codex=cx))
            fs = filas_juez(d, "juicio_p1_codex")
            ok = bool(fs)
            for f in fs:
                evs = (f.get("uso_crudo") or {}).get("eventos") or []
                tot = [int(e.get("total_tokens")) for e in evs]
                esperado = sum(tot) if conducta == "incremental" else (tot[-1] if tot else None)
                ok = ok and len(evs) == 2 and (f.get("uso_validado") or {}).get("total") == esperado \
                    and f.get("acreditacion_aplicada") is not None
            r5 = [p for p in d["esc"].S.rglob("rep-??.juicio.json")]
            persiste = any(len([ln for ln in str(ll.get("respuesta", {}).get("eventos", "")).splitlines() if ln]) >= 3
                           or len(ll.get("respuesta", {}).get("eventos") or []) >= 3
                           for p in r5 for ll in (ESC.leer(p) or {}).get("llamadas") or []
                           if ll.get("etapa", "").startswith("juicio_p1_codex"))
            check(f"§4.4-{k} entrada `{conducta}` ⇒ total = {'suma' if conducta == 'incremental' else 'último'}; "
                  "R4 guarda los dos eventos `usage` y R5 todas las líneas JSONL", ok and persiste)
        except EscenarioNoDisponible as exc:
            check(f"§4.4-{k}: {exc}", False)
    # 4 · caché ausente SIN entrada → desconocido (juez Claude)
    try:
        class OpusSinCache(dobles.JuezDoble):
            def _respuesta(self, salida, prompt, error=None):
                r = super()._respuesta(salida, prompt, error)
                for c in ("cache_creation_input_tokens", "cache_read_input_tokens"):
                    r.uso["usage"].pop(c, None)
                return r
        rn = dobles.runners(cli_claude=cl, cli_codex=cx)
        rn["opus"] = OpusSinCache("opus", memo=rn["codex"].memo, cli_version=cl)
        d = caso("acr-4", sin(base, juez_cl), runners=rn)
        fs = filas_juez(d, "juicio_p1_opus")
        check("§4.4-4 caché ausente y SIN entrada ⇒ desconocido (nunca 0) y el juicio se detiene",
              bool(fs) and (fs[0].get("uso_validado") or {}).get("consumo_conocido") is False and d["juicio"] != 0)
        # 6 · con `omitido_si_cero` de OTRA versión → desconocido
        otra = json.loads(json.dumps(base))
        for e in otra["entradas"]:
            if e["firma_comando"]["sha256"] == juez_cl:
                e["cli_version"] = cl + "-otra"
                e["conducta"] = {c: "omitido_si_cero" for c in e["conducta"]}
        otra["nota"] += " otra-version"
        rn = dobles.runners(cli_claude=cl, cli_codex=cx)
        rn["opus"] = OpusSinCache("opus", memo=rn["codex"].memo, cli_version=cl)
        d6 = caso("acr-6", otra, runners=rn)
        fs6 = filas_juez(d6, "juicio_p1_opus")
        check("§4.4-6 caché ausente con `omitido_si_cero` de OTRA versión del CLI ⇒ desconocido",
              bool(fs6) and (fs6[0].get("uso_validado") or {}).get("consumo_conocido") is False)
    except EscenarioNoDisponible as exc:
        check(f"§4.4-4/6: {exc}", False)
    # 5 y 7 · omitido_si_cero de la MISMA firma → 0 conocido; misma versión, OTRO comando → desconocido (E2E-16)
    try:
        from mia.agent import llm
        sha_a = firmas.sha_firma_claude("opus", llm._cli_effort(llm.CLI_OPUS_ALIAS, "legal_analysis", None))
        inst = firmas.instantanea(cl, cx, omitido_para={sha_a}, etiqueta="omitido-firma-a")
        escalada = getattr(llm, "QUALITY_ESCALATION_EXCEPTIONAL", "exceptional")
        guion = dobles.Guion(llamadas=(("legal_analysis", "analisis"),
                                       ("legal_analysis", "analisis_escalado", {"quality_escalation": escalada})))
        prov = dobles.proveedores(claude=dobles.ClaudeCLIDoble(
            omitir=frozenset({"cache_creation_input_tokens", "cache_read_input_tokens"})))
        d = caso("acr-5-7", inst, prov_nuevo=prov, guion_nuevo=guion)
        fs = [f for f in d["esc"].r4(VERS_ESQ[1]) if f.get("fase") == "produccion"]
        a = [f for f in fs if (f.get("firma_comando") or {}).get("sha256") == sha_a]
        b = [f for f in fs if f.get("nodo") == "analisis_escalado"]
        check("§4.4-5 caché ausente con `omitido_si_cero` de la MISMA versión y la MISMA firma ⇒ 0 conocido "
              "(y la firma de R4 es la normalizada de §4.4)",
              bool(a) and all((f.get("uso_validado") or {}).get("consumo_conocido") is True
                              and (f.get("uso_validado") or {}).get("cache_lectura") == 0 for f in a))
        check("E2E-16 / §4.4-7 misma versión, comandos distintos: la acreditación de la firma A no se aplica a "
              "la firma B (otro `--effort`) ⇒ desconocido",
              bool(b) and all((f.get("firma_comando") or {}).get("sha256") != sha_a
                              and (f.get("uso_validado") or {}).get("consumo_conocido") is False for f in b))
    except EscenarioNoDisponible as exc:
        check(f"§4.4-5/7: {exc}", False)
    # 8 · dos entradas con la misma firma y conductas distintas
    try:
        esc = ESC.Escenario("acr-8-prod", instantanea=firmas.instantanea(cl, cx, ambigua_produccion=True,
                                                                          etiqueta="ambigua-prod"),
                            versiones=VERS_ESQ)
        c = esc.producir(VERS_ESQ[0], casos=[CASO], solo_piloto=True, custodiados=False)
        check("E2E-16 / §4.4-8 una firma PREVISTA con dos entradas de conducta distinta no tiene acreditación "
              "única: el runner rechaza (exit 3) antes de producir",
              c == 3 and not list(esc.dir(VERS_ESQ[0]).glob("*/rep-??.json")))
        d = caso("acr-8-juez", firmas.instantanea(cl, cx, ambigua_juez_codex=True, etiqueta="ambigua-juez"),
                 runners=dobles.runners(codex_kw={"eventos_codex": "acumulados"}, cli_claude=cl, cli_codex=cx))
        check("E2E-16 / §4.4-8 dos entradas con la misma firma (juez Codex) y conductas distintas ⇒ "
              "`acreditacion_ambigua`", "acreditacion_ambigua" in codigos(d.get("v")))
    except (EscenarioNoDisponible, PuntoDeEntradaAusente) as exc:
        check(f"§4.4-8: {exc}", False)
    # firmas_previstas incompletas
    try:
        esc = ESC.Escenario("acr-incompleta", instantanea=firmas.instantanea(cl, cx, solo_una=True,
                                                                              etiqueta="incompleta"),
                            versiones=VERS_ESQ)
        c = esc.producir(VERS_ESQ[0], casos=[CASO], solo_piloto=True, custodiados=False)
        check("E2E-16 el runner con `firmas_previstas` sin acreditación única en la instantánea rechaza (exit 3)",
              c == 3 and not list(esc.dir(VERS_ESQ[0]).glob("*/rep-??.json")))
    except PuntoDeEntradaAusente as exc:
        check(f"E2E-16 firmas previstas incompletas: {exc}", False)
    # Codex sin `campo_identidad` acreditado
    try:
        inst = firmas.instantanea(cl, cx, campo_identidad_codex=None, etiqueta="sin-identidad-codex")
        d = memo("acr-identidad-codex", lambda: construir_esqueleto(
            "acr-identidad-codex", instantanea=inst, medir_codex_nuevo=True,
            prov_nuevo=dobles.proveedores(con_codex=True),
            guion_nuevo=dobles.Guion(llamadas=dobles.LLAMADAS_POR_DEFECTO + (("legal_research", "investigacion"),))))
        check("§4.4 Codex sin `campo_identidad` acreditado ⇒ `identidad_efectiva_ausente`",
              "identidad_efectiva_ausente" in codigos(d.get("v")))
    except EscenarioNoDisponible as exc:
        check(f"§4.4 identidad Codex: {exc}", False)


def e2e_5() -> None:
    print("\nE2E-5 · ceguera y material")
    try:
        def construir():
            rn = dobles.runners()
            return {**construir_esqueleto("e2e5", runners=rn), "rn": rn}
        d = memo("e2e5", construir)
        esc, rn = d["esc"], d["rn"]
        import hashlib
        recibidos = set()
        for r in rn.values():
            recibidos |= {hashlib.sha256(p.encode("utf-8")).hexdigest() for p in r.prompts}
        guardados = {ll.get("prompt_sha256") for p in esc.S.rglob("rep-??.juicio.json")
                     for ll in (ESC.leer(p) or {}).get("llamadas") or []}
        check("E2E-5 el `prompt_sha256` guardado en R5 es el del prompt que recibió el juez (y no sobra ninguno)",
              bool(guardados) and guardados == recibidos)
        e3 = ESC.copiar(esc, "e2e5-byte")
        r2 = e3.dir(VERS_ESQ[1]) / CASO / "rep-01.json"
        x = ESC.leer(r2)
        x["resultado"]["draft_full"] = x["resultado"]["draft_full"][:-1] + "!"
        r2.write_text(json.dumps(x, ensure_ascii=False), encoding="utf-8")
        v = e3.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])[1]
        check("E2E-5 alterar un byte del texto del R2 rompe el paquete ⇒ `no_certificable` "
              "(`paquete_no_coincide` / `rep_sha256_no_coincide`)",
              (v or {}).get("veredicto") == "no_certificable"
              and bool(codigos(v) & {"paquete_no_coincide", "rep_sha256_no_coincide"}))
    except (EscenarioNoDisponible, PuntoDeEntradaAusente, TypeError, KeyError) as exc:
        check(f"E2E-5: {type(exc).__name__}: {exc}", False)


def e2e_6() -> None:
    print("\nE2E-6 · producto intacto (§4.3)")
    diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", "HEAD", "--", "backend/mia/agent",
                           "backend/mia/metrics"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    try:
        d = f17()
        r1n, r1b = d["esc"].r1("nuevo") or {}, d["esc"].r1("base") or {}
        rutas_ok = (r1n.get("rutas_modificadas_respecto_del_producto") == []
                    and isinstance(r1b.get("rutas_modificadas_respecto_del_producto"), list)
                    and all(str(p).startswith(("backend/mia/eval/", "execution/"))
                            for p in r1b["rutas_modificadas_respecto_del_producto"]))
    except EscenarioNoDisponible as exc:
        rutas_ok = False
        print(f"       {exc}")
    check("E2E-6.1 `git diff` vacío en backend/mia/agent y backend/mia/metrics y R1 sin rutas de producto en "
          "`rutas_modificadas_respecto_del_producto`", diff.returncode == 0 and not diff.stdout.strip() and rutas_ok)
    try:
        tele = ESC.importar("mia.eval.banco04.telemetria")
        import subprocess as _sp
        import types
        from mia.agent import codex_subscription_llm as cx, llm, subscription_llm as sl
        from mia.metrics import usage
        import run_banco04 as R
        originales = (sl._to_openai_response, cx._usage, sl._build_command, cx._command, sl._sanitized_env)

        def llamar():
            cl, co = dobles.ClaudeCLIDoble(), dobles.CodexCLIDoble()
            prev = (sl.subprocess, cx.subprocess, sl._resolve_exe, cx._resolve_exe, cx._local_membership_allowed,
                    llm.resolve_fallback_chain)
            px = lambda run: types.SimpleNamespace(run=run, TimeoutExpired=_sp.TimeoutExpired,  # noqa: E731
                                                   CompletedProcess=_sp.CompletedProcess)
            try:
                sl.subprocess, cx.subprocess = px(cl), px(co)
                sl._resolve_exe = lambda: firmas.EXE_CLAUDE
                cx._resolve_exe = lambda: Path(firmas.EXE_CODEX)
                cx._local_membership_allowed = lambda: True
                llm.resolve_fallback_chain = dobles.cadena_con_codex()
                with R.politica_fija(llm):
                    n0 = len(usage._buffer)
                    a = llm.call_llm([{"role": "user", "content": "[[BANCO04 caso=x|rep=1|nodo=a]] h"}],
                                     task="legal_analysis")
                    b = llm.call_llm([{"role": "user", "content": "h"}], task="legal_research")
                    filas = [dict(f) for f in usage._buffer[n0:]]
                return a, b, filas
            finally:
                (sl.subprocess, cx.subprocess, sl._resolve_exe, cx._resolve_exe, cx._local_membership_allowed,
                 llm.resolve_fallback_chain) = prev

        def campos(r):
            return {"choices": [(c.index, c.message.content, c.finish_reason) for c in r.choices],
                    "usage": vars(r.usage) if hasattr(r.usage, "__dict__") else r.usage, "model": r.model,
                    "hint": getattr(r, "mia_model_hint", None), "effort": getattr(r, "mia_effort", None)}
        sin_env = llamar()
        with tele.instalar():
            dentro = (sl._to_openai_response, cx._usage, sl._build_command, cx._command, sl._sanitized_env)
            con_env = llamar()
        limpiar = lambda fs: [sin_tiempo({k: v for k, v in f.items() if k not in ("ts", "created_at")})  # noqa: E731
                              for f in fs]
        check("E2E-6.2 con y sin el envoltorio, `call_llm` devuelve choices, usage, model, mia_model_hint y "
              "mia_effort idénticos, y `metrics.usage.record` bufferiza la misma fila",
              campos(sin_env[0]) == campos(con_env[0]) and campos(sin_env[1]) == campos(con_env[1])
              and limpiar(sin_env[2]) == limpiar(con_env[2]) and all(x is not y for x, y in zip(dentro, originales)))
        try:
            with tele.instalar():
                raise RuntimeError("salida por excepción")
        except RuntimeError:
            pass
        check("E2E-6.3 al salir de `telemetria.instalar()`, incluso por excepción, los atributos vuelven a ser "
              "los originales (`is`)",
              all(x is y for x, y in zip((sl._to_openai_response, cx._usage, sl._build_command, cx._command,
                                          sl._sanitized_env),
                                         originales)))
    except (PuntoDeEntradaAusente, AttributeError) as exc:
        check(f"E2E-6.2/6.3: {type(exc).__name__}: {exc}", False)
    verdes = []
    for suite in ("test_gates_no_ciegos.py", "test_eval_spend_guard.py"):
        r = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "execution" / suite)], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=1200, cwd=str(ROOT), env=dict(os.environ))
        verdes.append((suite, r.returncode == 0))
    ok, motivo, env = entorno.cluster_aislado()
    if ok:
        r = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "execution" / "test_rls.py")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1200, cwd=str(ROOT),
                           env={**os.environ, "MIA_TEST_ENV_FILE": str(env)})
        verdes.append(("test_rls.py", r.returncode == 0))
    check(f"E2E-6.4 siguen verdes test_gates_no_ciegos y test_eval_spend_guard {verdes} y test_rls "
          f"({'corrido' if ok else motivo})", all(x for _, x in verdes) and ok)


def e2e_7() -> None:
    print("\nE2E-7 · sin puerta trasera")
    try:
        d = esqueleto()
        v = d["v"]
        check("E2E-7 con `dobles: true` y `aceptar_dobles` SIN relajar (esqueleto, §6.1 v6), el resultado es "
              "`no_certificable` con `corridas_con_dobles` y `modo_prueba: true`",
              (v or {}).get("veredicto") == "no_certificable" and "corridas_con_dobles" in codigos(v)
              and v.get("modo_prueba") is True)
        vpub = d["esc"].decidir(prueba=False, base=VERS_ESQ[0], nuevo=VERS_ESQ[1])
        check("E2E-7 la puerta PÚBLICA (sin `_prueba`) solo usa el `custodia_manifest.json` del repo: sustituir "
              "`custodia._MANIFEST_PATH` no tiene efecto y la custodia de prueba no abre ⇒ `custodia_no_coincide`, "
              "con `modo_prueba: false`",
              isinstance(vpub, dict) and vpub.get("veredicto") == "no_certificable"
              and "custodia_no_coincide" in codigos(vpub) and vpub.get("modo_prueba") is False)
        vsi = d["esc"].decidir(prueba=True, base=VERS_ESQ[0], nuevo=VERS_ESQ[1],
                               relajaciones={"instantaneas": False})
        check("E2E-7 R1 escritos con `instantaneas_dir=` y leídos SIN `directorio_instantaneas` ⇒ "
              "`instantaneas_de_prueba` (§3.8, §4.4 v6); otra relajación activa sigue marcando `modo_prueba`",
              "instantaneas_de_prueba" in codigos(vsi) and vsi.get("modo_prueba") is True)
        vp = d["esc"].decidir(prueba=True, base=VERS_ESQ[0], nuevo=VERS_ESQ[1])
        from mia.eval.banco04 import metricas as M
        try:
            M.resumen_publicable(vp)
            rechaza = False
        except Exception:  # noqa: BLE001
            rechaza = True
        check("E2E-7 con `_prueba` el resultado lleva `modo_prueba: true` y `resumen_publicable` se niega a "
              "publicarlo", vp.get("modo_prueba") is True and rechaza)
    except (EscenarioNoDisponible, PuntoDeEntradaAusente) as exc:
        check(f"E2E-7: {exc}", False)


def e2e_1_esqueleto_mundo() -> None:
    """El resultado de §6.1 sobre el esqueleto sin base de datos (la misma exigencia que E2E-1)."""
    print("\nE2E-1m · esqueleto con `mundo=` (sin base): archivos, R4 y motivos ⊆ E")
    try:
        d = esqueleto()
        esc, (b, n) = d["esc"], VERS_ESQ
        check(f"E2E-1m pasos 1-4 terminan (prod {d['prod_base']}, {d['prod_nuevo']}; cadena {d.get('cadena')}; "
              f"juicio {d.get('juicio')}; decidir {d['cli'][0]})",
              d["prod_base"] == (0, 0) and d["prod_nuevo"] == (0, 0) and d.get("cadena") == 0
              and d.get("juicio") == 0 and d["cli"][0] in (0, 1))
        prod = [f for f in esc.r4(n) if f.get("fase") == "produccion"]
        check("E2E-1m R4: filas `produccion` cerradas con contexto, `nodo`, consumo conocido, `origen: captura` "
              "y la firma normalizada; ninguna `en_curso`",
              bool(prod) and all(f.get("estado") == "cerrada" and f.get("caso_id") == CASO and f.get("rep") == 1
                                 and f.get("nodo") in ("analisis", "redaccion") and f.get("origen") == "captura"
                                 and (f.get("uso_validado") or {}).get("consumo_conocido") is True
                                 and len((f.get("firma_comando") or {}).get("sha256", "")) == 64 for f in prod)
              and not [f for f in esc.todas_r4() if f.get("estado") == "en_curso"])
        import ast
        arbol = ast.parse(Path(dobles.__file__).read_text(encoding="utf-8"))
        importados = [getattr(n, "module", None) or "" for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)] + [
            a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names]
        check("E2E-1m el módulo de dobles no importa `telemetria` y TODA fila R4 lleva `origen: \"captura\"` "
              "(K10)", not [m for m in importados if "telemetria" in m]
              and bool(esc.todas_r4()) and all(f.get("origen") == "captura" for f in esc.todas_r4()))
        r1 = esc.r1(n) or {}
        check("E2E-1m R1 registra `dobles: true`, `bloque: 7`, `solo_piloto`, `muestra_restringida`, "
              "`cadenas_politica`, `firmas_previstas` y `telemetria_acreditada_sha256` (§2 R1)",
              r1.get("dobles") is True and r1.get("bloque") == 7 and r1.get("solo_piloto") is True
              and r1.get("muestra_restringida") == [CASO] and isinstance(r1.get("cadenas_politica"), dict)
              and r1.get("telemetria_acreditada_sha256") == esc.sha_instantanea and r1.get("firmas_previstas")
              and r1.get("instantaneas_de_prueba") is True)
        r2 = esc.r2(n, CASO, 1) or {}
        check("E2E-1m R2 lleva `caso_digest`, `prompt_version_hash`, `jurisdicciones_fijadas = []` e "
              "`intentos[].llamadas` con los ids de R4",
              r2.get("estado") == "completo" and r2.get("caso_digest") and r2.get("prompt_version_hash")
              and r2.get("jurisdicciones_fijadas") == []
              and sorted(x for it in r2.get("intentos") or [] for x in it.get("llamadas") or [])
              == sorted(f["id"] for f in prod))
        cad = ESC.leer(esc.cadena) or {}
        juez = [f for f in esc.todas_r4() if str(f.get("fase", "")).startswith("juicio_")]
        check("E2E-1m R8 escrito por `registrar-cadena` ANTES de la primera fila de juez; filas de juez con "
              "`candidate_id`, `pasada`, `cadena_sha256` y `prompt_sha256`",
              cad.get("schema") == "banco04-cadena/v1" and bool(juez)
              and all(f.get("candidate_id") and f.get("pasada") is not None and f.get("cadena_sha256")
                      and f.get("prompt_sha256") for f in juez))
        cs = codigos(d["v"])
        check(f"E2E-1m veredicto `no_certificable`, motivos ⊆ E y ninguno de F ({sorted(cs)})",
              (d["v"] or {}).get("veredicto") == "no_certificable" and {"muestra_incompleta", "corridas_con_dobles",
                                                                        "validacion_reservada_ausente"} <= cs
              and cs <= E_ESQUELETO and not cs & F_ESQUELETO and vocab_ok(d["v"]))
        check("E2E-1m condiciones del caso recalculadas, con fuentes (ruta + sha256)",
              bool((d["v"] or {}).get("condiciones"))
              and all(c.get("fuentes") and all(len(str(x.get("sha256", ""))) == 64 for x in c["fuentes"])
                      for c in d["v"]["condiciones"] if c.get("estado") != "no_aplica"))
        # registrar-cadena es requisito: juzgar sin R8 no arranca
        e2 = ESC.Escenario("sin-cadena", versiones=VERS_ESQ)
        e2.producir_y_aprobar(b, casos=[CASO], solo_piloto=True, custodiados=False)
        c = e2.juzgar()
        check("E2E-1m `juzgar` sin `MANIFIESTO_CADENA.json` se niega y no escribe ninguna fila de juez",
              c != 0 and not [f for f in e2.todas_r4() if str(f.get("fase", "")).startswith("juicio")])
    except (EscenarioNoDisponible, PuntoDeEntradaAusente) as exc:
        check(f"E2E-1m: {exc}", False)


def e2e_8_9_12() -> None:
    print("\nE2E-8 · Codex de producción, recorrido positivo (K10)")
    try:
        d = memo("f17-codex", lambda: construir_f17(
            "f17-codex", con_codex=True,
            prov_nuevo=dobles.proveedores(con_codex=True, codex=dobles.CodexCLIDoble(tokens=10)),
            guion_nuevo=dobles.Guion(llamadas=dobles.LLAMADAS_POR_DEFECTO + (("legal_research", "investigacion"),))))
        esc = d["esc"]
        cx = [f for f in esc.r4("nuevo") if f.get("proveedor_cuota") == "codex" and f.get("fase") == "produccion"]
        check("E2E-8 filas R4 `proveedor_cuota=codex` con `uso_crudo.eventos` y consumo conocido",
              bool(cx) and all(isinstance((f.get("uso_crudo") or {}).get("eventos"), list)
                               and (f.get("uso_validado") or {}).get("consumo_conocido") is True for f in cx))
        r1 = esc.r1("nuevo") or {}
        check("E2E-8 R1 de la nueva: `puede_codex`, `cadenas_politica` con `cli-codex` en `legal_research`, y "
              "`estimacion_piloto_codex` citando R13",
              r1.get("puede_codex") is True
              and any(str(a).startswith("cli-codex") for k, al in (r1.get("cadenas_politica") or {}).items()
                      if k.startswith("legal_research|") for a in al)
              and ((r1.get("estimacion_piloto_codex") or {}).get("fuente") or {}).get("sha256"))
        cond = [c for c in d["v"].get("condiciones") or [] if "codex" in str(c.get("id", "")).lower()]
        check("E2E-8 las condiciones Codex del techo (§6.3) se calculan en la puerta y el veredicto F17-Codex "
              "(Codex ≤ 0,50× Claude) es `aprueba`",
              bool(cond) and all(c.get("estado") in ("cumple", "no_aplica") for c in cond)
              and d["v"].get("veredicto") == "aprueba")
    except EscenarioNoDisponible as exc:
        check(f"E2E-8: {exc}", False)

    print("\nE2E-9 · piloto Codex (K5)")
    try:
        esc = ESC.Escenario("e2e9", versiones=VERS_ESQ)
        g = dobles.Guion(llamadas=dobles.LLAMADAS_POR_DEFECTO + (("legal_research", "investigacion"),))
        c = esc.producir(VERS_ESQ[1], proveedores=dobles.proveedores(con_codex=True), guion=g, casos=[CASO],
                         solo_piloto=True, custodiados=False)
        check("E2E-9 sin R13, `run_banco04.main` en el Bloque 7 con `puede_codex` rechaza con exit 3 ANTES de la "
              "primera corrida", c == 3 and not list(esc.dir(VERS_ESQ[1]).glob("*/rep-??.json")))
        esc = ESC.Escenario("e2e9-con-r13", versiones=VERS_ESQ)      # R1 es exclusivo: escenario nuevo
        m = esc.medir_codex(VERS_ESQ[1])
        c2 = esc.producir(VERS_ESQ[1], proveedores=dobles.proveedores(con_codex=True), guion=g, casos=[CASO],
                          solo_piloto=True, custodiados=False)
        r13p = esc.S / f"{VERS_ESQ[1]}-medicion-codex" / "estimacion_codex.json"
        r13 = ESC.leer(r13p) or {}
        est = (esc.r1(VERS_ESQ[1]) or {}).get("estimacion_piloto_codex") or {}
        check("E2E-9 con R13, la piloto se admite con SU estimación (por clase, > 0) y no con 0, y R1 cita R13 en "
              "un solo sentido (ruta y sha256)",
              m == 0 and c2 == 0 and est.get("por_clase") == r13.get("por_clase")
              and all(int(x) > 0 for x in (r13.get("por_clase") or {"_": 0}).values())
              and (est.get("fuente") or {}).get("sha256") == entorno.sha256_archivo(r13p)
              and "consumidor" not in json.dumps(r13))
    except (PuntoDeEntradaAusente, EscenarioNoDisponible, OSError) as exc:
        check(f"E2E-9: {exc}", False)
    for nombre, fn, codigo, desc in (
            ("e2e9-sin-permiso", inyectar_codex_en_base, "codex_sin_permiso",
             "una fila R4 Codex en una versión con `puede_codex == false`"),
            ("e2e9-cadena", alias_fuera_de_cadena, "cadenas_no_coinciden",
             "una fila de producción cuyo alias no está en `cadenas_politica` de su tarea")):
        try:
            d = editar(nombre, fn)
            check(f"E2E-9 {desc} ⇒ `{codigo}`", d["v"].get("veredicto") == "no_certificable" and codigo in codigos(d["v"]))
        except EscenarioNoDisponible as exc:
            check(f"E2E-9 {desc}: {exc}", False)

    print("\nE2E-12 · medición previa de Codex (R14)")
    try:
        d = memo("e2e12", construir_e2e12)
        med = d["dir"]
        r1 = ESC.leer(med / "MANIFIESTO.json") or {}
        filas = ESC.filas_r4(med)
        sel = r1.get("seleccion_medicion") or {}
        check("E2E-12 `S/<ver>-medicion-codex/` con R1 `proposito: medicion_codex`, SIN `estimacion_piloto_codex`, "
              "con `seleccion_medicion` (k y lista preregistrados) y filas R4 `fase: medicion_codex`",
              d["code"] == 0 and r1.get("proposito") == "medicion_codex" and not r1.get("estimacion_piloto_codex")
              and sel.get("k") == 1 and set(sel.get("por_clase") or {}) == {"pequeno", "fuga", "voluminoso"}
              and bool(filas) and all(f.get("fase") == "medicion_codex" for f in filas))
        textos = [p for p in med.rglob("*.json") if any(k in (p.read_text(encoding="utf-8", errors="ignore"))
                                                        for k in ("diagnosis_full", "draft_full", "documents_map"))]
        check("E2E-12 la medición NO escribe `resultado`: ni diagnóstico, ni borrador, ni material", not textos and bool(filas))
        recibos = list(med.glob("*/rep-01.recibo.json"))
        r13 = ESC.leer(med / "estimacion_codex.json") or {}
        esperado = esperado_r13(med)
        citadas = sorted(Path(str(x.get("ruta", ""))).name for x in r13.get("filas_R4") or [])
        check(f"E2E-12 recibos `completo` por corrida preregistrada y R13 con `por_clase` = (5·max_c+3)//4 "
              f"recalculado desde las filas ({esperado}); `filas_R4` = TODAS las filas de la medición",
              bool(recibos) and all((ESC.leer(x) or {}).get("estado") == "completo" for x in recibos)
              and bool(esperado) and r13.get("por_clase") == esperado and r13.get("regla") == "(5·max_c + 3) // 4"
              and citadas == sorted(Path(f["_ruta"]).name for f in filas))
        r1m = ESC.leer(med / "MANIFIESTO.json")
        import run_banco04 as R
        check("E2E-12 R13 se liga al manifiesto de la MEDICIÓN (`manifiesto_medicion_sha256`) y ese manifiesto "
              "no cita R13 (ligadura en un solo sentido)",
              isinstance(r1m, dict) and r13.get("manifiesto_medicion_sha256") == R.manifiesto_sha256(r1m)
              and "estimacion_codex.json" not in json.dumps(r1m) and not r1m.get("estimacion_piloto_codex"))
        check("E2E-12 `run_banco04` de la versión arranca con ese R13", d["prod"] == (0, 0))
        check("E2E-12 la puerta reproduce `por_clase` desde las fuentes (sin `estimacion_codex_no_reproducible`)",
              isinstance(d.get("v"), dict) and "estimacion_codex_no_reproducible" not in codigos(d["v"])
              and vocab_ok(d["v"]))
    except (EscenarioNoDisponible, PuntoDeEntradaAusente) as exc:
        check(f"E2E-12: {exc}", False)
    variantes_r14()


def construir_e2e12() -> dict:
    esc = ESC.Escenario("e2e12", versiones=VERS_ESQ)
    code = esc.medir_codex(VERS_ESQ[1])
    g = dobles.Guion(llamadas=dobles.LLAMADAS_POR_DEFECTO + (("legal_research", "investigacion"),))
    pb = esc.producir_y_aprobar(VERS_ESQ[0], casos=[CASO], solo_piloto=True, custodiados=False)
    pn = esc.producir_y_aprobar(VERS_ESQ[1], proveedores=dobles.proveedores(con_codex=True), guion=g, casos=[CASO],
                                solo_piloto=True, custodiados=False)
    esc.registrar_cadena(base=VERS_ESQ[0], nuevo=VERS_ESQ[1])
    esc.juzgar()
    v = esc.decidir(prueba=True, base=VERS_ESQ[0], nuevo=VERS_ESQ[1])
    return {"esc": esc, "code": code, "prod": pn, "prod_base": pb, "v": v,
            "dir": esc.S / f"{VERS_ESQ[1]}-medicion-codex"}


def esperado_r13(med: Path) -> dict:
    """Regla de R13 recalculada por la prueba desde los recibos y las filas R4 de la medición."""
    filas = {f["id"]: f for f in ESC.filas_r4(med)}
    max_c: dict = {}
    for rec in med.glob("*/rep-01.recibo.json"):
        r = ESC.leer(rec) or {}
        tot = sum(int((filas[i].get("uso_validado") or {}).get("total") or 0)
                  for it in r.get("intentos") or [] for i in it.get("llamadas") or []
                  if i in filas and filas[i].get("proveedor_cuota") == "codex")
        max_c[r.get("clase")] = max(max_c.get(r.get("clase"), 0), tot)
    return {c: (5 * m + 3) // 4 for c, m in max_c.items()}


def variantes_r14() -> None:
    def med(nombre, **kw):
        esc = ESC.Escenario(nombre, versiones=VERS_ESQ)
        return esc, esc.medir_codex(VERS_ESQ[1], **kw), esc.S / f"{VERS_ESQ[1]}-medicion-codex"
    try:
        esc, code, d = med("r14-desconocida", proveedores=dobles.proveedores(
            con_codex=True, codex=dobles.CodexCLIDoble(eventos="ninguno")))
        check("E2E-12 fila fuente desconocida ⇒ sin R13 (y la medición se detiene)",
              code != 0 and not (d / "estimacion_codex.json").exists() and bool(ESC.filas_r4(d)))
        esc, code, d = med("r14-techo", max_codex=50)
        check("E2E-12 techo de la medición alcanzado ⇒ suspensión de etapa `produccion` y sin R13",
              code != 0 and not (d / "estimacion_codex.json").exists()
              and any((ESC.leer(s) or {}).get("etapa") == "produccion" for s in d.glob("suspensiones/*.json")))
        esc, code, d = med("r14-infra", guion=dobles.Guion(
            llamadas=dobles.LLAMADAS_POR_DEFECTO + (("legal_research", "investigacion"),),
            infra_antes={(c.id, 1) for c in CF.casos_visibles()} | {(i, 1) for i in CF.IDS_CUSTODIADOS}))
        check("E2E-12 una corrida con `fallo_infraestructura` ⇒ sin R13", code != 0 and not (d / "estimacion_codex.json").exists()
              and any((ESC.leer(r) or {}).get("estado") == "fallo_infraestructura" for r in d.glob("*/rep-01.recibo.json")))
    except (PuntoDeEntradaAusente, EscenarioNoDisponible, OSError) as exc:
        check(f"E2E-12 variantes: {exc}", False)
    for nombre, fn, desc in (
            ("r13-editado", lambda e: editar_json(e.S / "nuevo-medicion-codex" / "estimacion_codex.json",
                                                  lambda x: x["por_clase"].update(pequeno=1)), "R13 editado"),
            ("r13-fila-extra", fila_extra_en_medicion, "una fila R4 de la medición que no está en `R13.filas_R4`"),
            ("r13-sin-recibo", lambda e: next((e.S / "nuevo-medicion-codex").glob("*/rep-01.recibo.json")).unlink(),
             "un recibo que falta")):
        try:
            d = editar(nombre, fn, base_escenario=memo("f17-codex", _f17_codex_no_construido))
            check(f"E2E-12 {desc} ⇒ `estimacion_codex_no_reproducible`",
                  "estimacion_codex_no_reproducible" in codigos(d["v"]))
        except (EscenarioNoDisponible, StopIteration) as exc:
            check(f"E2E-12 {desc}: {exc}", False)


def _f17_codex_no_construido():
    raise EscenarioNoDisponible("F17-Codex no se construyó (lo construye E2E-8)")


def editar_json(p: Path, fn) -> None:
    x = json.loads(Path(p).read_text(encoding="utf-8"))
    fn(x)
    Path(p).write_text(json.dumps(x, ensure_ascii=False), encoding="utf-8")


def fila_extra_en_medicion(esc) -> None:
    d = esc.S / "nuevo-medicion-codex" / "llamadas"
    f = sorted(d.glob("*.json"))[0]
    x = json.loads(f.read_text(encoding="utf-8"))
    x["id"] = x["id"] + "-extra"
    for k in ("seq_inicio", "seq_envio", "seq_cierre"):
        if isinstance(x.get(k), int):
            x[k] += 10 ** 6
    (d / f"{x['id']}.json").write_text(json.dumps(x), encoding="utf-8")


def inyectar_codex_en_base(esc) -> None:
    filas = esc.r4("base")
    f = dict(next(x for x in filas if x.get("fase") == "produccion"))
    f.pop("_ruta", None)
    f.update(id=f["id"] + "-codex", alias="cli-codex", familia="codex_cli", proveedor_cuota="codex",
             uso_crudo={"eventos": [{"input_tokens": 9, "output_tokens": 1, "total_tokens": 10}]})
    for k in ("seq_inicio", "seq_envio", "seq_cierre"):
        f[k] = int(f[k]) + 10 ** 6
    (esc.dir("base") / "llamadas" / f"{f['id']}.json").write_text(json.dumps(f), encoding="utf-8")


def alias_fuera_de_cadena(esc) -> None:
    filas = esc.r4("nuevo")
    f = next(x for x in filas if x.get("fase") == "produccion" and x.get("tarea") == "legal_draft")
    ruta = Path(f.pop("_ruta"))
    f["alias"] = "cli-claude-haiku"
    ruta.write_text(json.dumps(f), encoding="utf-8")


def e2e_10() -> None:
    print("\nE2E-10 · registro de uso del reservado (K3)")
    try:
        esc = ESC.Escenario("e2e10")
        c1 = esc.validar()
        reg1 = ESC.archivos(esc.custodia / "validacion", "*/registro.json")
        e2 = ESC.copiar(esc, "e2e10-reubicado")
        shutil.rmtree(e2.custodia / "validacion", ignore_errors=True)
        shutil.rmtree(e2.custodia / "registro-uso", ignore_errors=True)
        with entorno.entorno(LOCALAPPDATA=str(entorno.nueva_carpeta("localappdata-reubicada"))):
            c2 = e2.validar(appdata=esc.appdata)
        check("E2E-10 con `LOCALAPPDATA` y `MIA_BANCO04_CUSTODIA` reubicados A LA VEZ, el segundo uso del mismo "
              "reservado se rechaza (la raíz sale de la carpeta conocida del usuario, no del entorno)",
              c1 == 0 and len(reg1) == 1 and c2 != 0 and not ESC.archivos(e2.custodia / "validacion", "*/registro.json"))
        import banco04_validar_jueces as VJ
        previo = getattr(VJ, "IDENTIDADES_RESERVADO_RETIRADAS", None)
        e3 = ESC.Escenario("e2e10-retirado")
        try:
            VJ.IDENTIDADES_RESERVADO_RETIRADAS = frozenset(previo or ()) | {e3.cus.identidad_reservado()}
            c3 = e3.validar()
        finally:
            if previo is None:
                delattr(VJ, "IDENTIDADES_RESERVADO_RETIRADAS")
            else:
                VJ.IDENTIDADES_RESERVADO_RETIRADAS = previo
        check("E2E-10 VJ rechaza una identidad incluida en `IDENTIDADES_RESERVADO_RETIRADAS` (y no escribe R9)",
              previo is not None and c3 != 0 and not ESC.archivos(e3.custodia / "validacion", "*/registro.json"))
        ref = f17_aprueba()
        e4 = ESC.copiar(ref["esc"], "e2e10-puerta")
        ident_f17 = VJ.identidad_sellada_reservado(json.loads(e4.manifiesto_custodia.read_text(encoding="utf-8")))
        try:
            VJ.IDENTIDADES_RESERVADO_RETIRADAS = frozenset(previo or ()) | {ident_f17}
            v4 = e4.decidir(prueba=True)
        finally:
            if previo is None:
                if hasattr(VJ, "IDENTIDADES_RESERVADO_RETIRADAS"):
                    delattr(VJ, "IDENTIDADES_RESERVADO_RETIRADAS")
            else:
                VJ.IDENTIDADES_RESERVADO_RETIRADAS = previo
        check("E2E-10 la puerta también rechaza el reservado retirado ⇒ `reservado_retirado`",
              "reservado_retirado" in codigos(v4))
    except (PuntoDeEntradaAusente, EscenarioNoDisponible) as exc:
        check(f"E2E-10: {exc}", False)


def e2e_11() -> None:
    print("\nE2E-11 · Bloque 0: informe de línea base de una sola versión (K11)")
    try:
        esc = ESC.Escenario("e2e11", versiones=("base-b0",), bloque=0)
        p = esc.producir_y_aprobar("base-b0", casos=[CASO], solo_piloto=True, custodiados=False)
        c = esc.registrar_cadena(base="base-b0", nuevo=None, linea_base=True)
        j = esc.juzgar()
        code, inf, ruta = esc.decidir_cli("linea-base", base="base-b0", nuevo=None)
        claves = {"schema", "version", "rotulo", "modo_prueba", "estado", "motivos", "absolutos", "matriz_7_2",
                  "por_caso", "consumo", "circuito_bloque0", "jueces", "cotas_ilustrativas", "cuota",
                  "entradas_leidas"}
        inf = inf or {}
        cad = ESC.leer(esc.cadena) or {}
        check("E2E-11 R8 del Bloque 0: `bloque: 0`, `bloque_0_linea_base: true` y una sola versión `rol: base`",
              cad.get("bloque") == 0 and cad.get("bloque_0_linea_base") is True
              and [x.get("rol") for x in cad.get("versiones") or []] == ["base"])
        check("E2E-11 `banco04_decidir linea-base` escribe INFORME_LINEA_BASE.json con el esquema de §3.5, SIN "
              "`veredicto` ni comparativas",
              p == (0, 0) and c == 0 and j == 0 and ruta.is_file() and inf.get("schema") == "banco04-linea-base/v1"
              and claves <= set(inf) and "veredicto" not in inf and "comparativas" not in inf
              and not any(k.startswith(("perdida", "decisivos_estables", "extension")) for k in inf))
        cb = inf.get("circuito_bloque0") or {}
        check("E2E-11 estado `incompleta_no_certificable` (muestra parcial), techos del Bloque 0 (18 M / 5 M) y "
              "consumo descriptivo con las tres clases",
              inf.get("estado") == "incompleta_no_certificable" and cb.get("techo_claude") == 18_000_000
              and cb.get("techo_codex") == 5_000_000
              and set((inf.get("consumo") or {}).get("clases_de_consumo") or {}) == {"conocido", "con_cota", "sin_cota"}
              and all(m.get("codigo") in VOCABULARIO for m in inf.get("motivos") or []))
        cu = inf.get("cuota") or {}
        check("E2E-11 el informe del Bloque 0 lleva el veredicto de CUOTA separado (§3.5 v7): consumo pequeño, "
              "sin intentos sin cota ⇒ `certificada`, `circuito: cumple`, con `consumo_conocido` y sin aviso",
              cu.get("estado") == "certificada" and cu.get("circuito") == "cumple"
              and "consumo_conocido" in cu and cu.get("aviso") in (None, ""))
    except (PuntoDeEntradaAusente, EscenarioNoDisponible) as exc:
        check(f"E2E-11: {exc}", False)


# ── E2E-13 · intercalación con dos procesos ───────────────────────────────────────────────
def lanzar(cfg: dict, carpeta: Path) -> subprocess.Popen:
    p = carpeta / f"cfg-{cfg['modo']}-{time.monotonic_ns()}.json"
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return subprocess.Popen([sys.executable, "-X", "utf8", str(entorno.FIXTURES / "proceso_paralelo.py"), str(p)],
                            cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")


def esperar_archivo(p: Path, t: float = 300.0) -> bool:
    t0 = time.monotonic()
    while not p.exists():
        if time.monotonic() - t0 > t:
            return False
        time.sleep(0.05)
    return True


def base_e2e13(nombre: str):
    """Base y nueva producidas y la base aprobada; la cadena registrada. Falta aprobar la nueva (A)."""
    esc = ESC.Escenario(nombre, versiones=VERS_ESQ)
    a = esc.producir_y_aprobar(VERS_ESQ[0], casos=[CASO], solo_piloto=True, custodiados=False)
    b = esc.producir(VERS_ESQ[1], casos=[CASO], solo_piloto=True, custodiados=False)
    exigir(a == (0, 0) and b == 0, f"producción previa a E2E-13 terminó con {a}, {b}")
    exigir(esc.registrar_cadena(base=VERS_ESQ[0], nuevo=VERS_ESQ[1]) == 0, "registrar-cadena falló")
    return esc


def e2e_13_15() -> None:
    print("\nE2E-13 · intercalación de dos procesos bajo el cerrojo del bloque (K7)")
    # (i) B comprometida ANTES del cierre de A → admitida
    try:
        esc = base_e2e13("e2e13-i")
        bar = entorno.nueva_carpeta("barreras-i")
        ser = esc.serializar()
        pa = lanzar({"modo": "aprobar", "escenario": ser, "version": VERS_ESQ[1], "barreras": str(bar),
                     "casos": [CASO]}, bar)
        exigir(esperar_archivo(bar / "A_en_invocacion"), "A no llegó a su invocación")
        pb = lanzar({"modo": "juzgar", "escenario": ser, "version": VERS_ESQ[1], "barreras": str(bar)}, bar)
        exigir(esperar_archivo(bar / "B_comprometida"), "B no llegó a comprometer su primera llamada")
        (bar / "A_suelta").write_text("1")
        t0 = time.monotonic()
        while time.monotonic() - t0 < 120 and not [f for f in esc.r4(VERS_ESQ[1]) if desconocida_sin_cota(f)]:
            time.sleep(0.05)
        (bar / "B_sigue").write_text("1")
        pa.wait(600), pb.wait(600)
        a = [f for f in esc.r4(VERS_ESQ[1]) if desconocida_sin_cota(f)]
        juez = sorted([f for f in esc.todas_r4() if str(f.get("fase", "")).startswith("juicio")],
                      key=lambda f: f.get("seq_inicio") or 0)
        b1 = juez[0] if juez else {}
        siguientes = [f for f in juez[1:]]
        check("E2E-13 (i) B se comprometió ANTES del cierre de A (`B.seq_envio < A.seq_cierre`), cerró con éxito y "
              "la llamada siguiente quedó `no_enviado` y se detuvo",
              bool(a) and b1.get("seq_envio") is not None and b1["seq_envio"] < a[0]["seq_cierre"]
              and b1.get("estado") == "cerrada" and b1.get("exito") is True
              and bool(siguientes) and siguientes[0].get("estado") == "no_enviado")
        v = esc.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])[1]
        check("E2E-13 (i) la puerta ACEPTA B (garantía de compromiso irrevocable): sin "
              "`llamada_tras_desconocido_sin_autorizacion` ni `seq_incoherente`; el evento de A va a la cuota "
              "(`estimada`) y no a la calidad",
              isinstance(v, dict) and not codigos(v) & {"llamada_tras_desconocido_sin_autorizacion", "seq_incoherente"}
              and cuota_estimada(v, [a[0]["id"]]) and sin_motivo_de_cuota(v))
        # (ii) manipulación: B con seq_envio posterior al cierre de A y sin reanudación
        e2 = ESC.copiar(esc, "e2e13-ii-falsa")
        falsificar_juez_tras_evento(e2, VERS_ESQ[1], a[0]["id"])
        v2 = e2.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])[1]
        check("E2E-13 (ii) una fila B con `seq_envio > A.seq_cierre` sin reanudación ⇒ "
              "`llamada_tras_desconocido_sin_autorizacion`", "llamada_tras_desconocido_sin_autorizacion" in codigos(v2))
    except (EscenarioNoDisponible, PuntoDeEntradaAusente, IndexError, KeyError, TypeError) as exc:
        check(f"E2E-13 (i)/(ii): {type(exc).__name__}: {exc}", False)
    # (ii) A cerró ANTES del control de B → B no se compromete y no es infracción
    try:
        esc = base_e2e13("e2e13-ii")
        bar = entorno.nueva_carpeta("barreras-ii")
        (bar / "A_suelta").write_text("1")
        pa = lanzar({"modo": "aprobar", "escenario": esc.serializar(), "version": VERS_ESQ[1],
                     "barreras": str(bar), "casos": [CASO]}, bar)
        pa.wait(600)
        c = esc.juzgar()
        juez = [f for f in esc.todas_r4() if str(f.get("fase", "")).startswith("juicio")]
        v = esc.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])[1]
        check("E2E-13 (ii) con el cierre de A antes del control de B: B no se compromete (fila `no_enviado`, "
              "suspensión nueva) y la puerta NO lo cuenta como infracción",
              c != 0 and bool(juez) and all(f.get("estado") == "no_enviado" for f in juez)
              and bool(ESC.archivos(esc.dir(VERS_ESQ[1]), "suspensiones/juicio-*.json")
                       + ESC.archivos(esc.dir(VERS_ESQ[0]), "suspensiones/juicio-*.json"))
              and "llamada_tras_desconocido_sin_autorizacion" not in codigos(v))
    except (EscenarioNoDisponible, PuntoDeEntradaAusente) as exc:
        check(f"E2E-13 (ii): {exc}", False)
    # (iii) orfandad tardía (y E2E-15: matar después de t_envio_utc)
    try:
        esc = base_e2e13("e2e13-iii")
        bar = entorno.nueva_carpeta("barreras-iii")
        ser = esc.serializar()
        pa = lanzar({"modo": "aprobar", "escenario": ser, "version": VERS_ESQ[1], "barreras": str(bar),
                     "casos": [CASO]}, bar)
        exigir(esperar_archivo(bar / "A_en_invocacion"), "A no llegó a su invocación")
        pb = lanzar({"modo": "juzgar", "escenario": ser, "version": VERS_ESQ[1], "barreras": str(bar)}, bar)
        exigir(esperar_archivo(bar / "B_comprometida"), "B no comprometió su primera llamada")
        pa.kill()
        pa.wait(60)
        (bar / "B_sigue").write_text("1")
        pb.wait(600)
        orf = [ESC.leer(p) or {} for p in ESC.archivos(esc.dir(VERS_ESQ[1]), "orfandades/*.json")]
        filas = {f["id"]: f for f in esc.r4(VERS_ESQ[1])}
        juez = sorted([f for f in esc.todas_r4() if str(f.get("fase", "")).startswith("juicio")],
                      key=lambda f: f.get("seq_inicio") or 0)
        b1 = juez[0] if juez else {}
        a = filas.get((orf[0] if orf else {}).get("id_fila"), {})
        check("E2E-13 (iii) orfandad tardía: el registro de orfandad de A lleva `seq_deteccion > B.seq_envio` y "
              "la puerta no exige que B lo hubiera visto",
              len(orf) == 1 and b1.get("seq_envio") is not None and orf[0].get("seq_deteccion", -1) > b1["seq_envio"])
        check("E2E-13 (iii) A cumple `seq_inicio < seq_envio < seq_deteccion` con `seq_cierre == null` "
              "(huérfana ENVIADA, clase sin cota)",
              bool(a) and a.get("seq_cierre") is None and a.get("t_envio_utc") is not None
              and a["seq_inicio"] < a["seq_envio"] < orf[0]["seq_deteccion"])
        v = esc.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])[1]
        check("E2E-13 (iii) / E2E-15 la puerta no da `seq_incoherente`; la huérfana enviada es desconocida sin "
              "cota (en `cuota.intentos_sin_cota`, cuota `estimada`) y la siguiente sección que la detecta se detiene",
              isinstance(v, dict) and "seq_incoherente" not in codigos(v) and bool(a)
              and cuota_estimada(v, [a["id"]]) and sin_motivo_de_cuota(v)
              and len(juez) >= 2 and juez[1].get("estado") == "no_enviado")
    except (EscenarioNoDisponible, PuntoDeEntradaAusente, KeyError, TypeError) as exc:
        check(f"E2E-13 (iii): {type(exc).__name__}: {exc}", False)

    print("\nE2E-15 · denegación antes de enviar (K15)")
    try:
        d = esqueleto()
        esc = ESC.copiar(d["esc"], "e2e15")
        mcode = esc.medir_codex(VERS_ESQ[1], max_codex=1)
        med = esc.S / f"{VERS_ESQ[1]}-medicion-codex"
        den = [f for f in ESC.filas_r4(med) if f.get("estado") == "no_enviado"]
        check("E2E-15 `check_and_reserve` deniega una llamada Codex sin presupuesto: fila `no_enviado`, "
              "`t_envio_utc == null`, `seq_envio == null`, `uso_crudo == null` y `seq_inicio < seq_cierre`",
              mcode != 0 and bool(den) and all(f.get("t_envio_utc") is None and f.get("seq_envio") is None
                                               and f.get("uso_crudo") is None
                                               and f["seq_inicio"] < f["seq_cierre"] for f in den))
        e2 = ESC.derivar(esc, "e2e15-juez")
        e2.registrar_cadena(base=VERS_ESQ[0], nuevo=VERS_ESQ[1])
        cj = e2.juzgar()
        v = e2.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])[1]
        check("E2E-15 lo no enviado no es consumo ni detiene: el juez sigue (exit 0), la fila no entra en "
              "`cuota.intentos_sin_cota` y la cuota no queda `estimada` por ella",
              cj == 0 and isinstance(v, dict) and sin_motivo_de_cuota(v) and bool(cuota(v).get("condiciones"))
              and not set(f["id"] for f in den) & set(cuota(v).get("intentos_sin_cota") or [])
              and cuota(v).get("estado") == "certificada")
        # huérfana NO enviada (la fila que dejaría morir entre `en_curso` y `t_envio_utc`)
        e3 = ESC.derivar(d["esc"], "e2e15-huerfana")
        fabricar_huerfana_no_enviada(e3)
        e3.registrar_cadena(base=VERS_ESQ[0], nuevo=VERS_ESQ[1])
        c3 = e3.juzgar()
        orf = ESC.archivos(e3.dir(VERS_ESQ[1]), "orfandades/*.json")
        v3 = e3.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])[1]
        check("E2E-15 una fila `en_curso` sin `t_envio_utc` de un proceso muerto queda, tras su registro de "
              "orfandad, como huérfana NO enviada: no detiene ni es consumo",
              c3 == 0 and len(orf) == 1 and isinstance(v3, dict) and sin_motivo_de_cuota(v3)
              and "seq_incoherente" not in codigos(v3) and not cuota(v3).get("intentos_sin_cota")
              and cuota(v3).get("estado") == "certificada")
        # la fila `no_enviado` que la puerta SÍ lee: la Codex denegada de la nueva en E2E-3
        e4 = ESC.copiar(memo("e2e3", construir_e2e3)["esc"], "e2e15-contradictoria")
        nos = [Path(f["_ruta"]) for f in e4.r4(VERS_ESQ[1]) if f.get("estado") == "no_enviado"]
        editar_json(nos[0], lambda x: x.update(t_envio_utc="2030-01-01T00:00:00Z"))
        v4 = e4.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])[1]
        check("E2E-15 una fila `no_enviado` editada con `t_envio_utc` ⇒ `no_enviado_contradictorio`",
              "no_enviado_contradictorio" in codigos(v4))
    except (EscenarioNoDisponible, PuntoDeEntradaAusente, IndexError, KeyError) as exc:
        check(f"E2E-15: {type(exc).__name__}: {exc}", False)


def fabricar_huerfana_no_enviada(esc) -> None:
    """La fila que deja un proceso muerto entre `en_curso` y `t_envio_utc` (el instante no es alcanzable
    con dobles: lo deja el paso 1 de §4.2, dentro del cerrojo). PID de un proceso que ya terminó."""
    p = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    pid = int(p.stdout.strip())
    plantilla = dict(next(f for f in esc.r4(VERS_ESQ[1]) if f.get("fase") == "produccion"))
    plantilla.pop("_ruta", None)
    seq = max(int(f.get("seq_cierre") or f.get("seq_inicio") or 0) for f in esc.todas_r4()) + 5
    plantilla.update(id=f"produccion-{CASO}-r01-i9-huerfana-{seq:06d}", estado="en_curso", pid=pid,
                     seq_inicio=seq, seq_envio=None, seq_cierre=None, t_envio_utc=None, uso_crudo=None,
                     exito=False, intento=9)
    (esc.dir(VERS_ESQ[1]) / "llamadas" / f"{plantilla['id']}.json").write_text(json.dumps(plantilla), encoding="utf-8")


def e2e_14() -> None:
    print("\nE2E-14 · dos ciclos completos de suspensión y reanudación (K7)")
    try:
        # v9: el evento 1 está en la versión NUEVA (numerador): su producción omite `output_tokens` una vez;
        # el evento 2 es una llamada de juez sin uso.
        esc = ESC.Escenario("e2e14", versiones=VERS_ESQ)
        a = esc.producir_y_aprobar(VERS_ESQ[0], casos=[CASO], solo_piloto=True, custodiados=False)
        b = esc.producir_y_aprobar(VERS_ESQ[1], proveedores=dobles.proveedores(claude=OmitirUnaVez()), casos=[CASO],
                                   solo_piloto=True, custodiados=False)
        exigir(a == (0, 0) and b == (0, 0), f"producción previa a E2E-14 terminó con {a}, {b}")
        exigir(esc.registrar_cadena(base=VERS_ESQ[0], nuevo=VERS_ESQ[1]) == 0, "registrar-cadena falló")
        ev_prod = [f["id"] for f in esc.r4(VERS_ESQ[1]) if f.get("fase") == "produccion" and desconocida_sin_cota(f)]
        rn = dobles.runners(cli_claude=esc.cli_claude, cli_codex=esc.cli_codex,
                            opus_kw={"romper_uso": lambda i, nombre: i == 1})
        c1 = esc.juzgar(rn)
        s1 = ESC.archivos(esc.dir(VERS_ESQ[0]), "suspensiones/juicio-*.json") + ESC.archivos(
            esc.dir(VERS_ESQ[1]), "suspensiones/juicio-*.json")
        sha_s1 = {str(p): entorno.sha256_archivo(p) for p in s1}
        c2 = esc.juzgar(rn, reanudar=REF_PIPE)
        c3 = esc.juzgar(rn, reanudar=REF_PIPE + "-2")
        susp = ESC.archivos(esc.dir(VERS_ESQ[0]), "suspensiones/juicio-*.json") + ESC.archivos(
            esc.dir(VERS_ESQ[1]), "suspensiones/juicio-*.json")
        rean = ESC.archivos(esc.dir(VERS_ESQ[0]), "reanudaciones/*.json") + ESC.archivos(
            esc.dir(VERS_ESQ[1]), "reanudaciones/*.json")
        v = esc.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])[1]
        check("E2E-14 evento 1 → s1 → r1 → evento 2 → s2 (s1 intacta, mismo sha256) → r2 → el juicio termina",
              c1 != 0 and c2 != 0 and c3 == 0 and len(s1) == 1 and len(susp) == 2 and len(rean) == 2
              and all(entorno.sha256_archivo(Path(p)) == h for p, h in sha_s1.items()))
        check("E2E-14 la puerta acepta el orden de los dos ciclos, la calidad se calcula sin motivo por los "
              "eventos y la cuota queda `estimada` (evento 1 en la NUEVA, mínimo del cociente ≤ 1,25)",
              isinstance(v, dict) and len(ev_prod) == 1 and cuota_estimada(v, ev_prod) and sin_motivo_de_cuota(v)
              and bool(v.get("condiciones"))
              and not codigos(v) & {"llamada_tras_desconocido_sin_autorizacion", "reanudacion_invalida",
                                    "circuito_suspendido", "seq_incoherente"})
        e2 = ESC.copiar(esc, "e2e14-r2-parcial")
        r2 = sorted(ESC.archivos(e2.dir(VERS_ESQ[0]), "reanudaciones/*.json")
                    + ESC.archivos(e2.dir(VERS_ESQ[1]), "reanudaciones/*.json"),
                    key=lambda p: (ESC.leer(p) or {}).get("n", 0))[-1]
        r1x = sorted(ESC.archivos(e2.dir(VERS_ESQ[0]), "reanudaciones/*.json")
                     + ESC.archivos(e2.dir(VERS_ESQ[1]), "reanudaciones/*.json"),
                     key=lambda p: (ESC.leer(p) or {}).get("n", 0))[0]
        ev1 = ((ESC.leer(r1x) or {}).get("cubre") or {}).get("eventos_desconocidos") or []
        editar_json(r2, lambda x: x["cubre"].update(eventos_desconocidos=list(ev1)))
        v2 = e2.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])[1]
        check("E2E-14 variante: r2 que cubre solo el evento 1 ⇒ la llamada posterior al evento 2 da "
              "`llamada_tras_desconocido_sin_autorizacion`", "llamada_tras_desconocido_sin_autorizacion" in codigos(v2))
        e3 = ESC.copiar(esc, "e2e14-s1-editada")
        p_s1 = Path(next(iter(sha_s1)).replace(str(esc.raiz), str(e3.raiz)))
        editar_json(p_s1, lambda x: x.update(motivo_codigo="editado"))
        v3 = e3.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])[1]
        check("E2E-14 variante: editar s1 invalida r1",
              bool(codigos(v3) & {"reanudacion_invalida", "circuito_suspendido",
                                  "llamada_tras_desconocido_sin_autorizacion"}))
        e4 = ESC.copiar(esc, "e2e14-s1-borrada")
        Path(str(p_s1).replace(str(e3.raiz), str(e4.raiz))).unlink()
        v4 = e4.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])[1]
        check("E2E-14 variante: borrar s1 invalida r1",
              bool(codigos(v4) & {"reanudacion_invalida", "circuito_suspendido",
                                  "llamada_tras_desconocido_sin_autorizacion"}))
    except (EscenarioNoDisponible, PuntoDeEntradaAusente, IndexError, StopIteration) as exc:
        check(f"E2E-14: {type(exc).__name__}: {exc}", False)


def e2e_17_18() -> None:
    print("\nE2E-17 · instantáneas inmutables (K13)")
    try:
        cl, cx = ESC.versiones_cli()
        esc = ESC.Escenario("e2e17", versiones=VERS_ESQ)
        esc.producir_y_aprobar(VERS_ESQ[0], casos=[CASO], solo_piloto=True, custodiados=False)
        otra, _ = ESC.instalar(firmas.instantanea(cl, cx, etiqueta="otra-instantanea"))
        esc.producir_y_aprobar(VERS_ESQ[1], casos=[CASO], solo_piloto=True, custodiados=False, instantanea_sha=otra)
        c = esc.registrar_cadena(base=VERS_ESQ[0], nuevo=VERS_ESQ[1])
        v = esc.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])[1] if c == 0 else None
        check("E2E-17 R1 de la base y de la nueva que citan instantáneas distintas ⇒ "
              "`acreditacion_snapshot_distinto` (o la cadena no se registra)",
              (esc.r1(VERS_ESQ[1]) or {}).get("telemetria_acreditada_sha256") == otra
              and (c != 0 or "acreditacion_snapshot_distinto" in codigos(v)))
    except (EscenarioNoDisponible, PuntoDeEntradaAusente) as exc:
        check(f"E2E-17: {exc}", False)
    try:
        cl, cx = ESC.versiones_cli()
        inst_r9 = firmas.instantanea(cl, cx, eventos_codex="incremental", etiqueta="r9-propia")
        d = memo("e2e17-r9", lambda: e2e17_r9(inst_r9))
        val = [f for f in d["esc"].todas_r4() if f.get("fase") == "validacion" and f.get("proveedor_cuota") == "codex"]
        check("E2E-17 R9 con SU PROPIA instantánea es válida: la puerta no da `acreditacion_snapshot_distinto` y "
              "sus filas de validación se interpretan con ella (incremental ⇒ suma de eventos)",
              d["v"].get("veredicto") == "aprueba" and "acreditacion_snapshot_distinto" not in codigos(d["v"])
              and bool(val) and all((f.get("uso_validado") or {}).get("total")
                                    == sum(int(e["total_tokens"]) for e in (f.get("uso_crudo") or {}).get("eventos") or [])
                                    for f in val))
    except EscenarioNoDisponible as exc:
        check(f"E2E-17 R9 con su instantánea: {exc}", False)

    print("\nE2E-18 · identidad efectiva (K8)")
    for nombre, prov, codigo, desc in (
            ("e2e18-canonico", dobles.proveedores(claude=dobles.ClaudeCLIDoble(
                canonico={**dobles.MODELO_POR_HINT, "opus": "claude-doble-opus-OTRO"})),
             "base_no_comparable_reproducir",
             "mismo alias y mismo `mia_model_hint`, pero `canonicalModel` distinto entre versiones"),
            ("e2e18-sin-modelusage", dobles.proveedores(claude=dobles.ClaudeCLIDoble(sin_model_usage=True)),
             "identidad_efectiva_ausente", "una fila Claude con éxito sin `modelUsage`")):
        try:
            d = memo(nombre, lambda prov=prov, nombre=nombre: construir_esqueleto(nombre, prov_nuevo=prov))
            filas = [f for f in d["esc"].r4(VERS_ESQ[1]) if f.get("fase") == "produccion"]
            check(f"E2E-18 {desc} ⇒ `{codigo}`",
                  bool(filas) and all(f.get("modelo_solicitado") for f in filas) and codigo in codigos(d.get("v")))
        except EscenarioNoDisponible as exc:
            check(f"E2E-18 {desc}: {exc}", False)


def e2e17_r9(inst_r9: dict) -> dict:
    ref = f17_aprueba()
    esc = ESC.derivar(ref["esc"], "e2e17-r9", revalidar=True)
    sha_r9, _ = ESC.instalar(inst_r9)
    rn = dobles.runners(cli_claude=esc.cli_claude, cli_codex=esc.cli_codex, codex_kw={"eventos_codex": "acumulados"})
    previo = esc.sha_instantanea
    esc.sha_instantanea = sha_r9           # solo para la llamada a VJ: R9 cita su propia instantánea
    try:
        c = esc.validar(rn)
    finally:
        esc.sha_instantanea = previo
    exigir(c == 0, f"VJ con su instantánea terminó con {c}")
    esc.registrar_cadena()
    esc.juzgar()
    return {"esc": esc, "v": esc.decidir(prueba=True)}


# ════════════════════════════════════════════════════════════════════════════════════════
# F17 · fixture completo
# ════════════════════════════════════════════════════════════════════════════════════════
def bloque_f17() -> None:
    print("\nF17 · fixture completo (§6.3): las dos versiones, 17 casos × R, aprobaciones y R9; con `_prueba`")
    try:
        d = f17()
        v = d["v"]
        check(f"F17 con `_prueba`, la puerta da `aprueba` (requisito previo de la familia; motivos "
              f"{sorted(codigos(v))[:5]}, filas rojas {(v or {}).get('filas_rojas', [])[:3]})",
              v.get("veredicto") == "aprueba" and not codigos(v) and v.get("modo_prueba") is True)
        check("F17 sin intentos sin cota ni cotas, la CUOTA es `certificada · cumple` y la separación calidad/cuota "
              "es estricta (E2E-19.3 sobre F17, E2E-19.8)",
              cuota_certificada(v, "cumple") and separacion_estricta(v))
        esc = d["esc"]
        from mia.eval.banco04 import protocolo as P
        n_rep = sum(1 for _ in esc.dir("nuevo").glob("*/rep-??.json")) + sum(
            1 for _ in (esc.custodia / "salidas" / "nuevo").glob("*/rep-??.json"))
        check(f"F17 la nueva tiene las {P.CORRIDAS_POR_VERSION} corridas del protocolo (R2: {n_rep}) y cada caso "
              "custodiado vive en `<custodia>/salidas` (§1.3)",
              n_rep == P.CORRIDAS_POR_VERSION
              and len(list((esc.custodia / "salidas" / "nuevo").glob("V*/rep-??.resultado.enc"))) >= 4 * P.R_VOLUMINOSOS)
        check("F17 ningún texto custodiado en claro fuera de la custodia (marca sintética ausente del árbol S)",
              not [p for p in esc.S.rglob("*") if p.is_file() and CF.MARCA.encode() in p.read_bytes()])
        check("F17 todas las condiciones de §6.1-§6.3 recalculadas y con fuentes",
              len(v.get("condiciones") or []) >= 15 and all(c.get("fuentes") for c in v["condiciones"]
                                                              if c.get("estado") != "no_aplica")
              and vocab_ok({**v, "veredicto": "aprueba"}))
        check("F17 cero filas `en_curso` y cero suspensiones en todo el bloque",
              not [f for f in esc.todas_r4() if f.get("estado") == "en_curso"]
              and not list(esc.S.rglob("suspensiones/*.json")))
    except EscenarioNoDisponible as exc:
        check(f"F17: {exc}", False)


# ════════════════════════════════════════════════════════════════════════════════════════
# S · familia semántica
# ════════════════════════════════════════════════════════════════════════════════════════
def s(nombre, desc, construir, *, veredicto, cierre, condicion=None, codigo=None, permitidos=()):
    try:
        d = memo(nombre, construir)
        ref, v = d["ref"], d["v"]
        fuera = fuera_del_cierre(ref, v, cierre)
        ok_cond = condicion(ref, v) if condicion else True
        cs = codigos(v)
        if veredicto == "reprueba":
            ok_v = v.get("veredicto") == "reprueba" and not cs
        else:
            ok_v = v.get("veredicto") == "no_certificable" and codigo in cs and cs <= {codigo, *permitidos}
        check(f"{nombre} {desc} ⇒ {veredicto}{' `' + codigo + '`' if codigo else ''} "
              f"(cambio exigido {'sí' if ok_cond else 'NO'}; fuera del cierre {fuera[:3]}; motivos {sorted(cs)[:4]})",
              ok_v and ok_cond and not fuera and vocab_ok({**v, "veredicto": v.get("veredicto")}))
    except EscenarioNoDisponible as exc:
        check(f"{nombre} {desc}: {exc}", False)


def s_cuota(nombre, desc, construir, *, esperado: str, condicion=None):
    """S08, S09, S10 (v9): la CALIDAD no cambia (`aprueba`, ninguna condición de calidad cambia) y la CUOTA
    queda `certificada · excede` o `estimada`."""
    try:
        d = memo(nombre, construir)
        ref, v = d["ref"], d["v"]
        fuera = fuera_del_cierre(ref, v, ())            # ninguna condición de CALIDAD puede cambiar
        ok_cuota = cuota_certificada(v, "excede") if esperado == "excede" else cuota_estimada(v)
        ok_cond = condicion(v) if condicion else True
        check(f"{nombre} {desc} ⇒ calidad SIN cambio (`aprueba`) y cuota "
              f"{'`certificada · excede`' if esperado == 'excede' else '`estimada`'} "
              f"(condición de cuota {'sí' if ok_cond else 'NO'}; calidad cambiada {fuera[:3]}; motivos {sorted(codigos(v))[:3]})",
              v.get("veredicto") == "aprueba" and not codigos(v) and not fuera and ok_cuota and ok_cond
              and separacion_estricta(v))
    except EscenarioNoDisponible as exc:
        check(f"{nombre} {desc}: {exc}", False)


def candidatos(esc, version: str, caso: str, reps) -> frozenset:
    """Ids ciegos que la cadena asignará (§3.2 paso 4: `preparar_candidato` con la llave = semilla_hmac):
    se calculan con las etiquetas de versión plausibles (interfaz: `etiqueta_version` = la versión)."""
    from mia.eval.banco04 import ceguera
    llave = bytes.fromhex(CF.SEMILLA_HEX)
    out = set()
    r1 = esc.r1(version) or {}
    for rep in reps:
        r2 = esc.r2(version, caso, rep) or {}
        res = r2.get("resultado") or {}
        for et in (version, r1.get("version") or version):
            out.add(ceguera.candidate_id(llave, et, caso, rep, res.get("diagnosis_full", ""), res.get("draft_full", "")))
    return frozenset(out)


def bloque_s() -> None:
    print("\nS · familia semántica: se cambia el doble y se regenera desde `main` (K10)")
    fr = frase()[:20]
    s("S01", "los dos jueces marcan `sin_respaldo` el mismo átomo",
      lambda: regenerar("s01", runners=dobles.runners(opus=dobles.Reglas(forzar_defecto=frozenset({fr})),
                                                      codex=dobles.Reglas(forzar_defecto=frozenset({fr})))),
      veredicto="reprueba", cierre=P1, condicion=lambda a, b: cambio(a, b, "afirmaciones_sin_respaldo", sube))
    s("S02", "solo Codex marca defecto y el tercer voto dice `sin_respaldo`",
      lambda: regenerar("s02", runners=dobles.runners(opus=dobles.Reglas(tercer_voto="sin_respaldo"),
                                                      codex=dobles.Reglas(forzar_defecto=frozenset({fr})))),
      veredicto="reprueba", cierre=P1, condicion=lambda a, b: cambio(a, b, "afirmaciones_sin_respaldo", sube))
    s("S03", "el tercer voto devuelve JSON inválido dos veces",
      lambda: regenerar("s03", runners=dobles.runners(opus=dobles.Reglas(tercer_voto="invalido"),
                                                      codex=dobles.Reglas(forzar_defecto=frozenset({fr})))),
      veredicto="no_certificable", codigo="juicio_incompleto", cierre=JUICIO)
    s("S04", "pasada 2: los decisivos de un caso de lectura completa quedan no cubiertos",
      lambda: regenerar("s04", runners=dobles.runners(opus=dobles.Reglas(no_cubiertos={CASO: True}))),
      veredicto="reprueba", cierre=P2,
      condicion=lambda a, b: cambio(a, b, "cobertura_hechos_decisivos", lambda x, y: num(y) is not None
                                    and num(y) < Fraction(8, 10)))
    s("S05", "pasada 2: conducta `definitiva` en corridas cuyo material da alcance < 0,95",
      construir_s05, veredicto="reprueba", cierre=P2,
      condicion=lambda a, b: cambio(a, b, "definitivo_con_lectura_insuficiente", sube))
    s("S06", "el mundo emite `entraron_tramos` reducido (alcance → 0,90) y se rejuzga con conducta definitiva",
      lambda: regenerar("s06", nuevo={"guion": dobles.Guion(fraccion_leida={CASO_VOL: 0.9})}),
      veredicto="reprueba", cierre=MATERIAL,
      condicion=lambda a, b: cambio(a, b, "definitivo_con_lectura_insuficiente", sube)
      and any(x != y for x, y in zip(valores(a, "alcance"), valores(b, "alcance"))))
    s("S07", "el mundo emite `fragmentos_en_prompt.completo=false`",
      lambda: regenerar("s07", nuevo={"guion": dobles.Guion(medicion_incompleta={CASO_VOL})}),
      veredicto="reprueba", cierre=MATERIAL,
      condicion=lambda a, b: cambio(a, b, "definitivo_con_lectura_insuficiente", sube))
    s_cuota("S08", "los proveedores dobles devuelven más `output_tokens` en un caso de la nueva",
            lambda: regenerar("s08", nuevo={"proveedores": dobles.proveedores(
                claude=dobles.ClaudeCLIDoble(factor_salida={CASO: 3}))}),
            esperado="excede",
            condicion=lambda v: any(c.get("estado") == "certificada_excede"
                                    and num((c.get("intervalo") or [None])[0]) is not None
                                    and num(c["intervalo"][0]) > Fraction(125, 100)
                                    for c in cuota(v).get("condiciones") or []
                                    if "claude_extremo_por_caso" in str(c.get("id", ""))))
    s_cuota("S09", "un proveedor doble de Claude omite `output_tokens` en una llamada de la NUEVA (el juicio se "
            "detiene y se reanuda con autorización)",
            lambda: regenerar("s09", nuevo={"proveedores": dobles.proveedores(claude=OmitirUnaVez())},
                              reanudar_si_para=True),
            esperado="estimada", condicion=lambda v: bool(cuota(v).get("intentos_sin_cota")))
    s_cuota("S10", "el mundo fija con `set_node` un nodo fuera de `atribucion_preregistrada` en las llamadas que "
            "suben más del 10 % (y menos del 25 %)",
            lambda: regenerar("s10", nuevo={"guion": dobles.Guion(nodo_forzado={CASO: "nodo_no_preregistrado"}),
                                            "proveedores": dobles.proveedores(
                                                claude=dobles.ClaudeCLIDoble(factor_salida={CASO: 1.55}))}),
            esperado="excede",
            condicion=lambda v: any(c.get("estado") == "certificada_excede" for c in cuota(v).get("condiciones") or []
                                    if any(t in str(c.get("id", "")) for t in ("atribu", "C25"))))
    s("S11", "los runners de pasada 2 hacen caer un decisivo de 3/5 en la base a 1/5 en la nueva",
      construir_s11, veredicto="reprueba", cierre=P2,
      condicion=lambda a, b: any(c.get("estado") == "no_cumple" for c in condiciones(b, "decisivos_estables")))
    s("S12", "VJ con runners que no ven los defectos plantados (sensibilidad < 0,95)",
      lambda: regenerar("s12", vj_runners=dobles.runners(opus=dobles.Reglas(ciego=True),
                                                         codex=dobles.Reglas(ciego=True))),
      veredicto="no_certificable", codigo="circuito_no_utilizable", cierre=VJ_CIERRE, permitidos=("kappa_reservado",))
    s("S13", "VJ con los estados de Codex invertidos (kappa < 0,6)",
      lambda: regenerar("s13", vj_runners=dobles.runners(codex=dobles.Reglas(invertir=True))),
      veredicto="no_certificable", codigo="kappa_reservado", cierre=VJ_CIERRE, permitidos=("circuito_no_utilizable",))
    s("S14", "el runner de Opus devuelve dos veces una salida estructuralmente inválida",
      lambda: regenerar("s14", runners=dobles.runners(opus=dobles.Reglas(p1_invalido_si=frozenset({fr})))),
      veredicto="no_certificable", codigo="juicio_incompleto", cierre=JUICIO)
    s("S15", "el borrador de un caso sin ordenamiento dice «La Ley 100 de 1993 es aplicable al caso»; los jueces "
      "no marcan fuga",
      lambda: regenerar("s15", nuevo={"guion": dobles.Guion(texto_extra_borrador={CASO: dobles.FRASE_FUGA})},
                        runners=dobles.runners(opus=dobles.Reglas(sin_fuga=True), codex=dobles.Reglas(sin_fuga=True))),
      veredicto="reprueba", cierre=TEXTO, condicion=lambda a, b: cambio(a, b, "fuga_jurisdiccion", sube))
    s("S16", "los jueces respaldan con `uso_fuente=aplicable` una fuente de un ordenamiento no configurado",
      lambda: regenerar("s16", nuevo={"guion": dobles.Guion(fuente_no_configurada={CASO})},
                        runners=dobles.runners(opus=dobles.Reglas(uso_aplicable_no_configurado=True),
                                               codex=dobles.Reglas(uso_aplicable_no_configurado=True))),
      veredicto="no_certificable", codigo="juicio_incompleto", cierre=JUICIO + TEXTO)
    s("S17", "los votos dobles confirman una negativa falsa",
      lambda: regenerar("s17", runners=dobles.runners(opus=dobles.Reglas(puntos_laguna=frozenset({CASO}),
                                                                         tercer_voto="sin_respaldo"))),
      veredicto="reprueba", cierre=P1 + P2, condicion=lambda a, b: cambio(a, b, "afirmaciones_sin_respaldo", sube))
    s("S18", "Codex marca una fuga (subtipo `fuga`) y el tercer voto la confirma",
      lambda: regenerar("s18", runners=dobles.runners(opus=dobles.Reglas(tercer_voto="sin_respaldo"),
                                                      codex=dobles.Reglas(forzar_fuga=frozenset({fr})))),
      veredicto="reprueba", cierre=P1, condicion=lambda a, b: cambio(a, b, "fuga_jurisdiccion", sube))
    s("S19", "el mundo lanza `limite_de_uso` en la rep 5 de un caso de la base",
      lambda: regenerar("s19", base={"guion": dobles.Guion(limite_de_uso={(CASO, 5)})}),
      veredicto="no_certificable", codigo="muestra_incompleta", cierre=FALLO,
      permitidos=("plan_aprobaciones_no_coincide", "techo_sin_aprobacion", "sin_dato", "par_faltante",
                  "submuestra_incompleta", "circuito_suspendido"))
    s("S20", "la aprobación de un caso de la base falla por infraestructura dos veces",
      lambda: regenerar("s20", base={"guion": dobles.Guion(aprobacion_infra={CASO})}),
      veredicto="no_certificable", codigo="techo_sin_aprobacion", cierre=CONSUMO)
    s("S21", "el mundo lanza una excepción del producto después de una llamada al modelo (`fallo_producto`)",
      lambda: regenerar("s21", nuevo={"guion": dobles.Guion(fallo_producto={(CASO, 1)})}),
      veredicto="no_certificable", codigo="texto_ausente", cierre=FALLO,
      condicion=lambda a, b: cambio(a, b, "turnos_completados", baja),
      permitidos=("plan_aprobaciones_no_coincide", "sin_dato", "par_faltante", "submuestra_incompleta"))
    s("S22", "el mundo omite `resultado.verification` en una corrida con borrador",
      lambda: regenerar("s22", nuevo={"guion": dobles.Guion(sin_verificacion={(CASO, 1)})}),
      veredicto="no_certificable", codigo="informe_del_muro_ausente", cierre=("falsos_bloqueos",),
      permitidos=("falsos_bloqueos_sin_dato", "sin_dato", "par_faltante"))
    s("S23", "el mundo emite un `model_fallbacks` cuyo `hacia` no tiene fila R4",
      lambda: regenerar("s23", nuevo={"guion": dobles.Guion(fallback_huerfano={(CASO, 1)})}),
      veredicto="no_certificable", codigo="cambio_de_motor_contradictorio", cierre=("cambio_de_motor",),
      permitidos=("sin_dato", "par_faltante"))


class OmitirUnaVez(dobles.ClaudeCLIDoble):
    def __call__(self, cmd, *a, input=None, **kw):  # noqa: A002
        r = super().__call__(cmd, *a, input=input, **kw)
        if f"caso={CASO}|rep=1|nodo=redaccion" in (input or "") and not getattr(self, "_ya", False):
            self._ya = True
            data = json.loads(r.stdout)
            data["usage"].pop("output_tokens", None)
            r.stdout = json.dumps(data)
        return r


def construir_s05() -> dict:
    """S05: la referencia es la MISMA producción (alcance < 0,95 en el voluminoso) juzgada con conducta
    `limitada_expresa`; la mutación cambia SOLO la pasada 2 a `definitiva`."""
    g = dobles.Guion(fraccion_leida={CASO_VOL: 0.5})
    ref = regenerar("s05-ref", nuevo={"guion": g},
                    runners=dobles.runners(opus=dobles.Reglas(conducta={CASO_VOL: "limitada_expresa"})))
    esc = ESC.derivar(ref["esc"], "s05")
    esc.registrar_cadena()
    esc.juzgar(dobles.runners(opus=dobles.Reglas(conducta={CASO_VOL: "definitiva"})))
    return {"esc": esc, "ref": ref["v"], "v": esc.decidir(prueba=True)}


def construir_s11() -> dict:
    ref = f17_aprueba()
    esc = ESC.derivar(ref["esc"], "s11")
    nc = candidatos(esc, "base", CASO, (4, 5)) | candidatos(esc, "nuevo", CASO, (2, 3, 4, 5))
    esc.registrar_cadena()
    esc.juzgar(dobles.runners(opus=dobles.Reglas(no_cubiertos={CASO: nc})))
    return {"esc": esc, "ref": ref["v"], "v": esc.decidir(prueba=True)}


# ════════════════════════════════════════════════════════════════════════════════════════
# I · familia incoherente
# ════════════════════════════════════════════════════════════════════════════════════════
def primera(esc, version, pred):
    for f in esc.r4(version):
        if pred(f):
            return f
    raise EscenarioNoDisponible("no hay fila R4 que editar")


def guardar_fila(esc, version, f):
    f = dict(f)
    ruta = Path(f.pop("_ruta"))
    ruta.write_text(json.dumps(f, ensure_ascii=False), encoding="utf-8")


def i01(esc):
    fichas = sorted((esc.custodia / "salidas" / "nuevo" / "V4").glob("rep-01.json"))
    exigir(bool(fichas), "no hay ficha R2 del custodiado V4")
    editar_json(fichas[0], lambda x: x.update(jurisdicciones_fijadas=[]))


def i02(esc):
    r2 = esc.r2("nuevo", CASO, 1)
    ids = [x for it in r2["intentos"] for x in it.get("llamadas") or []]
    (esc.dir("nuevo") / "llamadas" / f"{ids[0]}.json").unlink()


def i03(esc):
    """v9: fila R4 huérfana ENVIADA, con su registro de orfandad y el contexto de una corrida, que el R2
    no cita ⇒ `ledger_incompleto` (el consumo va a la cuota, nunca a la calidad)."""
    f = dict(primera(esc, "nuevo", lambda x: x.get("fase") == "produccion" and x.get("caso_id") == CASO
                     and x.get("rep") == 1))
    f.pop("_ruta")
    seq = max(int(x.get("seq_cierre") or x.get("seq_envio") or x.get("seq_inicio") or 0) for x in esc.todas_r4()) + 3
    p = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    pid = int(p.stdout.strip())
    f.update(id=f"produccion-{CASO}-r01-i1-huerfana-{seq:06d}", estado="en_curso", seq_inicio=seq, seq_envio=seq + 1,
             seq_cierre=None, uso_crudo=None, exito=False, t_envio_utc="2030-01-01T00:00:00Z", pid=pid,
             estimacion_empirica=None)
    (esc.dir("nuevo") / "llamadas" / f"{f['id']}.json").write_text(json.dumps(f), encoding="utf-8")
    orf = esc.dir("nuevo") / "orfandades"
    orf.mkdir(exist_ok=True)
    (orf / f"{seq + 2}.json").write_text(json.dumps({
        "id_fila": f["id"], "pid": pid, "t_envio_utc": f["t_envio_utc"], "seq_deteccion": seq + 2,
        "detectada_por": "prueba-I03"}), encoding="utf-8")


def i06(esc):
    f = primera(esc, "nuevo", lambda x: x.get("fase") == "produccion" and (x.get("uso_crudo") or {}).get("usage"))
    f["uso_crudo"]["usage"].pop("output_tokens", None)
    guardar_fila(esc, "nuevo", f)


def i09(esc):
    f = dict(primera(esc, "nuevo", lambda x: x.get("fase") == "produccion"))
    f.pop("_ruta")
    seq = max(int(x.get("seq_cierre") or x.get("seq_inicio") or 0) for x in esc.todas_r4()) + 3
    f.update(id=f"produccion-{CASO}-r01-i7-desconocida-{seq:06d}", seq_inicio=seq, seq_envio=seq + 1,
             seq_cierre=seq + 2, uso_crudo={"usage": {"input_tokens": 1}},
             uso_validado={**(f.get("uso_validado") or {}), "consumo_conocido": False, "total": None,
                           "componentes_ausentes": ["output_tokens"]}, intento=7)
    (esc.dir("nuevo") / "llamadas" / f"{f['id']}.json").write_text(json.dumps(f), encoding="utf-8")
    falsificar_juez_tras_evento(esc, "nuevo", f["id"])


def i10(esc):
    p = esc.dir("nuevo") / "juicio" / CASO / "rep-01.juicio.json"
    exigir(p.is_file(), f"no existe {p}")

    def fn(x):
        ll = x["llamadas"][0]
        sal = ll["respuesta"]["salida"]
        sal = json.loads(sal) if isinstance(sal, str) else sal
        sal["candidate_id"] = sal.get("candidate_id", "") + "x"
        ll["respuesta"]["salida"] = sal
    editar_json(p, fn)


def i13(esc):
    for p in esc.S.rglob("rep-??.juicio.json"):
        x = ESC.leer(p) or {}
        n = len(x.get("llamadas") or [])
        x["llamadas"] = [ll for ll in x.get("llamadas") or [] if ll.get("etapa") not in ("juicio_estabilidad",)]
        if len(x["llamadas"]) < n:
            p.write_text(json.dumps(x, ensure_ascii=False), encoding="utf-8")
            return
    raise EscenarioNoDisponible("ningún R5 visible tiene segunda pasada de estabilidad")


_RESTAURAR: list = []


def i15(esc):
    ruta = esc.instantaneas_dir / f"{esc.sha_instantanea}.json"
    datos = ruta.read_bytes()
    _RESTAURAR.append((ruta, datos))          # se restaura SIEMPRE (la comparten los demás escenarios)
    ruta.write_bytes(datos.replace(b'"presente_siempre"', b'"omitido_si_cero"', 1))


FAMILIA_I = [
    ("I01", "`jurisdicciones_fijadas` de un custodiado", i01, "jurisdiccion_no_coincide", ()),
    ("I02", "borrar una fila R4 citada por un R2", i02, "ledger_incompleto", ()),
    ("I03", "añadir una fila R4 huérfana enviada, con su registro de orfandad y el contexto de una corrida, "
            "sin citarla en el R2", i03, "ledger_incompleto", ()),
    ("I04", "`soul_sha256` en R1 de la base",
     lambda e: editar_json(e.dir("base") / "MANIFIESTO.json", lambda x: x.update(soul_sha256="0" * 64)),
     "identidad_version", ()),
    ("I05", "`hash_evaluador` en un R5",
     lambda e: editar_json(e.dir("nuevo") / "juicio" / CASO / "rep-01.juicio.json",
                           lambda x: x.update(hash_evaluador="f" * 64)), "evaluador_no_congelado", ()),
    ("I06", "fila R4 con `consumo_conocido=true` y `uso_crudo` sin `output_tokens`", i06,
     "telemetria_contradictoria", ()),
    ("I07", "R11 reescrito con `r_reducida`",
     lambda e: editar_json(e.dir("nuevo") / "decision_r.json", lambda x: x.update(decision="r_reducida")),
     "decision_r_no_coincide", ("plan_aprobaciones_no_coincide", "muestra_incompleta")),
    ("I08", "`rep` cambiado dentro de un R2",
     lambda e: editar_json(e.dir("nuevo") / CASO / "rep-02.json", lambda x: x.update(rep=3)), "repeticiones",
     ("rep_sha256_no_coincide", "muestra_incompleta", "ledger_incompleto")),
    ("I09", "fila de juez falsificada tras un evento sin cota no autorizado", i09,
     "llamada_tras_desconocido_sin_autorizacion", ("ledger_incompleto", "juicio_incompleto")),
    ("I10", "`salida` de un R5 editada sin su `crudo_sha256`", i10, "juicio_contradictorio", ()),
    ("I11", "`material_turno` de un R2 editado sin rejuzgar",
     lambda e: editar_json(e.dir("nuevo") / CASO / "rep-01.json",
                           lambda x: x["resultado"]["material_turno"]["entraron_tramos"].pop()),
     "rep_sha256_no_coincide", ()),
    ("I13", "borrar la segunda pasada de estabilidad de un elegido", i13, "submuestra_incompleta",
     ("juicio_incompleto",)),
    ("I14", "`cli_version` distinta en R1 de la base",
     lambda e: editar_json(e.dir("base") / "MANIFIESTO.json", lambda x: x.update(cli_version="9.9.9 (otra)")),
     "base_no_comparable_reproducir", ("identidad_version",)),
    ("I15", "instantánea de acreditación editada en sitio (su nombre ya no es su sha256)", i15,
     "telemetria_acreditada_no_coincide", ("telemetria_contradictoria",)),
]


def bloque_i() -> None:
    print("\nI · familia incoherente: edición del crudo sin regenerar ⇒ código EXACTO, ningún motivo de calidad")
    for nombre, desc, fn, codigo, permitidos in FAMILIA_I:
        try:
            d = editar(nombre.lower(), fn)
            v, cs = d["v"], codigos(d["v"])
            sin_calidad = not cs & CODIGOS_CALIDAD and not any(
                c.get("estado") == "no_cumple" for c in v.get("condiciones") or [])
            check(f"{nombre} {desc} ⇒ `{codigo}` (motivos {sorted(cs)[:4]})",
                  v.get("veredicto") == "no_certificable" and codigo in cs and cs <= {codigo, *permitidos}
                  and sin_calidad and vocab_ok(v))
        except (EscenarioNoDisponible, KeyError, IndexError, FileNotFoundError) as exc:
            check(f"{nombre} {desc}: {type(exc).__name__}: {exc}", False)
        finally:
            while _RESTAURAR:
                ruta, datos = _RESTAURAR.pop()
                ruta.write_bytes(datos)
    # I12 vive con la extensión (bloque EXT)


# ════════════════════════════════════════════════════════════════════════════════════════
# INV · familia inversa
# ════════════════════════════════════════════════════════════════════════════════════════
def bloque_inversa() -> None:
    print("\nINV · familia inversa: mutar solo derivados no cambia el veredicto `aprueba`")
    try:
        d = f17_aprueba()
        esc = ESC.copiar(d["esc"], "inversa")
        editadas = mutar_derivados(esc, ("base", "nuevo"))
        v = esc.decidir(prueba=True)
        check("INV `false_block`, `jurisdiction_leak`, `abstention`, `reached_draft` y `score` de R2 invertidos, y "
              "consumo_resumen, consumo_turno, consumo_aprobacion, estado_banco, aprobaciones_estado, *.derivado, "
              "usage_by_node y VEREDICTO previo manipulados ⇒ sigue `aprueba` con la misma salida",
              v.get("veredicto") == "aprueba" and comparable(v, editadas) == comparable(d["v"], editadas))
    except EscenarioNoDisponible as exc:
        check(f"INV: {exc}", False)


# ════════════════════════════════════════════════════════════════════════════════════════
# EXT · recorrido positivo de la extensión
# ════════════════════════════════════════════════════════════════════════════════════════
CASOS_EXT = ("fuga-jurisdiccion-contrato-sin-pais", "disciplina-citas-formas-abreviadas")


def construir_ext() -> dict:
    ref = f17_aprueba()
    esc = ESC.derivar(ref["esc"], "f17-ext")
    nc = set()
    for c in CASOS_EXT:
        nc |= candidatos(esc, "nuevo", c, (1, 2))
    reglas = dobles.Reglas(no_cubiertos={c: frozenset(nc) for c in CASOS_EXT})
    esc.registrar_cadena()
    j1 = esc.juzgar(dobles.runners(opus=reglas))
    subm_antes = submuestras(esc)
    code_previa, _, _ = esc.decidir_cli("previa")
    r7 = ESC.leer(esc.cadena.parent / "EXTENSION.json")
    ext = [esc.producir("base", fase="extension"), esc.producir("nuevo", fase="extension", atribucion=None)]
    j2 = esc.juzgar(dobles.runners(opus=reglas))
    v = esc.decidir(prueba=True)
    return {"esc": esc, "r7": r7, "previa": code_previa, "ext": ext, "j": (j1, j2), "v": v,
            "subm_antes": subm_antes, "subm_despues": submuestras(esc), "ref": ref["v"]}


def submuestras(esc) -> dict:
    out: dict = {}
    for p in esc.S.rglob("rep-??.juicio.json"):
        for ll in (ESC.leer(p) or {}).get("llamadas") or []:
            et = ll.get("etapa", "")
            if et in ("juicio_estabilidad", "juicio_p2_codex"):
                out.setdefault(et, set()).add(str(p.relative_to(esc.S)))
    return out


def bloque_ext() -> None:
    from mia.eval.banco04 import protocolo as P
    print("\nEXT · F17-ext: previa no concluyente → R7 → extensión en las dos versiones → veredicto")
    try:
        d = memo("f17-ext", construir_ext)
        r7 = d["r7"] or {}
        check("EXT `banco04_decidir previa` escribe R7 (exclusivo, junto a R8) con los casos de §3.4 y 5 corridas "
              "por caso", d["previa"] == 0 and set(r7.get("casos") or []) == set(CASOS_EXT)
              and r7.get("corridas_por_caso") == 5 and r7.get("schema") == "banco04-extension/v1")
        n_ext = [sum(1 for c in CASOS_EXT for r in range(1, 30)
                     if ((d["esc"].r2(ver, c, r) or {}).get("extension") is True)) for ver in ("base", "nuevo")]
        check(f"EXT `run_banco04 --fase extension` produce R+1..R+5 con `extension_sha256` en las DOS versiones "
              f"({n_ext})", d["ext"] == [0, 0] and n_ext == [10, 10])
        rot = str(d["v"].get("rotulo") or "")
        check("EXT `banco04_decidir veredicto` da `aprueba` (con el rótulo «sin regresión demostrada; evidencia "
              "insuficiente» si la métrica sigue no concluyente)",
              d["v"].get("veredicto") == "aprueba" and d["j"] == (0, 0)
              and (P.ROTULO_TRAS_EXTENSION in rot or not any(c.get("valor") == "no_concluyente"
                                                             for c in d["v"].get("comparativas") or [])))
        check("EXT las submuestras ORIGINALES no cambian tras la extensión (las mismas pasadas que antes)",
              all(d["subm_antes"].get(k, set()) <= d["subm_despues"].get(k, set()) for k in d["subm_antes"])
              and bool(d["subm_antes"]))
        e2 = ESC.copiar(d["esc"], "i12")
        editar_json(e2.cadena.parent / "EXTENSION.json", lambda x: x.update(casos=list(reversed(x["casos"]))[:1]))
        v2 = e2.decidir(prueba=True)
        check("I12 R7 editado ⇒ `extension_no_coincide`", "extension_no_coincide" in codigos(v2)
              and v2.get("veredicto") == "no_certificable")
        e3 = ESC.copiar(d["esc"], "ext-borrada")
        borrar = [p for p in e3.dir("base").glob(f"{CASOS_EXT[0]}/rep-*.json")
                  if (ESC.leer(p) or {}).get("extension") is True][:1]
        for p in borrar:
            p.unlink()
        v3 = e3.decidir(prueba=True)
        check("EXT borrar en una versión una corrida de extensión de un caso de R7 ⇒ `no_certificable` "
              "(`extension_incompleta`)", bool(borrar) and "extension_incompleta" in codigos(v3))
        e4 = ESC.copiar(f17_aprueba()["esc"], "ext-sin-causa")
        e4.cadena.parent.mkdir(parents=True, exist_ok=True)
        (e4.cadena.parent / "EXTENSION.json").write_text(json.dumps(r7, ensure_ascii=False), encoding="utf-8")
        v4 = e4.decidir(prueba=True)
        check("EXT escribir R7 sin causa ⇒ `extension_sin_causa`", "extension_sin_causa" in codigos(v4))
    except EscenarioNoDisponible as exc:
        check(f"EXT: {exc}", False)


# ════════════════════════════════════════════════════════════════════════════════════════
# R13 · contraejemplos y redondeos (K16)
# ════════════════════════════════════════════════════════════════════════════════════════
def bloque_r13() -> None:
    print("\nR13 · contraejemplo obligatorio de Astra (10 + 1.000 ⇒ 1.263) y redondeos")
    g2 = dobles.Guion(llamadas=dobles.LLAMADAS_POR_DEFECTO + (("legal_research", "investigacion"),
                                                              ("legal_research", "investigacion_2")))
    try:
        def construir():
            esc = ESC.Escenario("r13-1263", versiones=VERS_ESQ)
            code = esc.medir_codex(VERS_ESQ[1], guion=g2, proveedores=dobles.proveedores(
                con_codex=True, codex=dobles.CodexCLIDoble(totales=[10, 1000])))
            g = dobles.Guion(llamadas=dobles.LLAMADAS_POR_DEFECTO + (("legal_research", "investigacion"),))
            esc.producir_y_aprobar(VERS_ESQ[0], casos=[CASO], solo_piloto=True, custodiados=False)
            esc.producir_y_aprobar(VERS_ESQ[1], proveedores=dobles.proveedores(con_codex=True), guion=g,
                                   casos=[CASO], solo_piloto=True, custodiados=False)
            esc.registrar_cadena(base=VERS_ESQ[0], nuevo=VERS_ESQ[1])
            esc.juzgar()
            return {"esc": esc, "code": code, "v": esc.decidir(prueba=True, base=VERS_ESQ[0], nuevo=VERS_ESQ[1])}
        d = memo("r13-1263", construir)
        med = d["esc"].S / f"{VERS_ESQ[1]}-medicion-codex"
        r13 = ESC.leer(med / "estimacion_codex.json") or {}
        check("R13 una corrida de medición con dos llamadas Codex de 10 y 1.000 tokens ⇒ `por_clase` = "
              "(5·1.010+3)//4 = 1.263, y la puerta lo valida",
              d["code"] == 0 and r13.get("por_clase") and all(x == 1263 for x in r13["por_clase"].values())
              and "estimacion_codex_no_reproducible" not in codigos(d["v"]) and vocab_ok(d["v"]))
        e2 = ESC.copiar(d["esc"], "r13-13")
        p13 = e2.S / f"{VERS_ESQ[1]}-medicion-codex" / "estimacion_codex.json"
        filas = {f["id"]: f for f in ESC.filas_r4(p13.parent)}
        diez = [i for i, f in filas.items() if (f.get("uso_validado") or {}).get("total") == 10]

        def solo_diez(x):
            x["filas_R4"] = [r for r in x.get("filas_R4") or [] if any(i in r.get("ruta", "") for i in diez)]
            x["por_clase"] = {k: (5 * 10 + 3) // 4 for k in x.get("por_clase") or {}}
        editar_json(p13, solo_diez)
        v2 = e2.decidir(prueba=True, base=VERS_ESQ[0], nuevo=VERS_ESQ[1])
        check("R13 el R13 que cita SOLO la fila de 10 (`por_clase` = 13) ⇒ `estimacion_codex_no_reproducible` "
              "(las filas citadas ≠ todas las filas)", "estimacion_codex_no_reproducible" in codigos(v2))
    except (EscenarioNoDisponible, PuntoDeEntradaAusente) as exc:
        check(f"R13 10 + 1.000: {exc}", False)
    for total, esperado in ((1, 2), (4, 5), (5, 7)):
        try:
            esc = ESC.Escenario(f"r13-{total}", versiones=VERS_ESQ)
            code = esc.medir_codex(VERS_ESQ[1], proveedores=dobles.proveedores(
                con_codex=True, codex=dobles.CodexCLIDoble(totales=[total])))
            r13 = ESC.leer(esc.S / f"{VERS_ESQ[1]}-medicion-codex" / "estimacion_codex.json") or {}
            check(f"R13 redondeo `max_c` = {total} ⇒ {esperado}", code == 0 and bool(r13.get("por_clase"))
                  and all(x == esperado for x in r13["por_clase"].values()))
        except PuntoDeEntradaAusente as exc:
            check(f"R13 redondeo {total} → {esperado}: {exc}", False)
    try:
        esc = ESC.Escenario("r13-0", versiones=VERS_ESQ)
        code = esc.medir_codex(VERS_ESQ[1], guion=dobles.Guion())         # puede_codex, pero Codex no se llama
        med = esc.S / f"{VERS_ESQ[1]}-medicion-codex"
        r13 = ESC.leer(med / "estimacion_codex.json") or {}
        recibos = [ESC.leer(p) or {} for p in med.glob("*/rep-01.recibo.json")]
        check("R13 redondeo 0 ⇒ 0, y SOLO con recibos `completo`, `n_llamadas_codex == 0` y filas cerradas "
              "(un cero exige acreditar una corrida completa)",
              code == 0 and bool(recibos) and all(r.get("estado") == "completo" and r.get("n_llamadas_codex") == 0
                                                  for r in recibos)
              and r13.get("por_clase") and all(x == 0 for x in r13["por_clase"].values()))
    except PuntoDeEntradaAusente as exc:
        check(f"R13 redondeo 0 → 0: {exc}", False)


# ════════════════════════════════════════════════════════════════════════════════════════
# E2E-19 · veredicto de CUOTA separado, por intervalo (§4.5, decisión de Pipe «Separar calidad y cuota»)
# ════════════════════════════════════════════════════════════════════════════════════════
def tot(analisis: int, redaccion: int, **extra: int):
    """Total EXACTO de cada llamada por nodo (doble del CLI): la consulta suma `analisis + redaccion`."""
    tabla = {"analisis": analisis, "redaccion": redaccion, **extra}
    return lambda c, r, n: tabla.get(n)


def construir_cuota(nombre: str, *, base: dict, nuevo: dict) -> dict:
    """Esqueleto sin juicio (la CUOTA sale solo de R4, §3.3 D): consumo por llamada fijado con exactitud y
    la aprobación sin llamada al modelo, para que la consulta del caso sea exactamente la suma fijada."""
    esc = ESC.Escenario(nombre, versiones=VERS_ESQ)
    out: dict = {"esc": esc}
    for ver, cfg in ((VERS_ESQ[0], base), (VERS_ESQ[1], nuevo)):
        prov = dobles.proveedores(claude=dobles.ClaudeCLIDoble(**cfg.get("claude", {})))
        g = dobles.Guion(aprobar_sin_llamada=True, **cfg.get("guion", {}))
        out[ver] = esc.producir_y_aprobar(ver, proveedores=prov, guion=g, casos=[CASO], solo_piloto=True,
                                          custodiados=False)
    out["cadena"] = esc.registrar_cadena(base=VERS_ESQ[0], nuevo=VERS_ESQ[1])
    out["v"] = esc.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])[1]
    return out


def suma_cotas(esc, version: str) -> int:
    return sum(int((f.get("cota") or {}).get("tokens_cota_superior") or 0) for f in esc.r4(version)
               if f.get("fase") == "produccion" and isinstance((f.get("cota") or {}).get("tokens_cota_superior"), int))


def hay_intervalo(v, lo, hi) -> bool:
    for c in cuota(v).get("condiciones") or []:
        iv = c.get("intervalo") or []
        if len(iv) == 2 and num(iv[0]) is not None and num(iv[1]) is not None:
            if abs(float(iv[0]) - float(lo)) < 1e-6 and abs(float(iv[1]) - float(hi)) < 1e-6:
                return True
    return False


EXTRA_SIN_SALIDA = (("legal_edit", "extra_sin_salida"),)
OMITE_EXTRA = {"omitir_salida_si": lambda c, r, n: n == "extra_sin_salida"}


def e2e_19() -> None:
    print("\nE2E-19 · veredicto de CUOTA separado, por intervalo (§4.5)")
    casos = [
        ("19.3", "sin incertidumbre: nueva 100 = base 100 ⇒ `certificada · cumple`",
         {"claude": {"total_exacto": tot(60, 40)}}, {"claude": {"total_exacto": tot(60, 40)}},
         lambda d: cuota_certificada(d["v"], "cumple") and hay_intervalo(d["v"], 1, 1)),
        ("19.3x", "sin incertidumbre: nueva 200 frente a base 100 ⇒ `certificada · excede`",
         {"claude": {"total_exacto": tot(60, 40)}}, {"claude": {"total_exacto": tot(120, 80)}},
         lambda d: cuota_certificada(d["v"], "excede") and hay_intervalo(d["v"], 2, 2)),
        ("19.3b", "contraejemplo de Astra: nueva 100; base 10 + un intento con cota (≥ 90) ⇒ intervalo "
         "[100/(10+cota), 10] que cruza 1,25 ⇒ `estimada`, NUNCA `certificada · cumple`",
         {"claude": {"total_exacto": tot(6, 4)}, "guion": {"llamada_api_fallida": {CASO}, "api_max_tokens": 90}},
         {"claude": {"total_exacto": tot(60, 40)}},
         lambda d: (cuota_estimada(d["v"]) and not cuota_certificada(d["v"], "cumple")
                    and suma_cotas(d["esc"], VERS_ESQ[0]) >= 90
                    and hay_intervalo(d["v"], Fraction(100, 10 + suma_cotas(d["esc"], VERS_ESQ[0])), 10))),
        ("19.3c", "inverso: nueva 100 + un intento con cota (≥ 1 000); base 100 ⇒ `estimada`, NUNCA un falso "
         "`certificada · excede`",
         {"claude": {"total_exacto": tot(60, 40)}},
         {"claude": {"total_exacto": tot(60, 40)}, "guion": {"llamada_api_fallida": {CASO}, "api_max_tokens": 1000}},
         lambda d: (cuota_estimada(d["v"]) and not cuota_certificada(d["v"], "excede")
                    and hay_intervalo(d["v"], 1, Fraction(100 + suma_cotas(d["esc"], VERS_ESQ[1]), 100)))),
        ("19.3d", "solo cotas finitas que no cruzan: nueva 100; base 92 + una cota ⇒ intervalo ⊂ [·, 100/92] "
         "≤ 1,25 ⇒ `certificada · cumple` (92 y no 90: con 90 la subida máxima 1,11 cruzaría el 10 % de C25)",
         {"claude": {"total_exacto": tot(55, 37)}, "guion": {"llamada_api_fallida": {CASO}, "api_max_tokens": 5}},
         {"claude": {"total_exacto": tot(60, 40)}},
         lambda d: (cuota_certificada(d["v"], "cumple")
                    and hay_intervalo(d["v"], Fraction(100, 92 + suma_cotas(d["esc"], VERS_ESQ[0])), Fraction(100, 92)))),
        ("19.3e", "evento sin cota SOLO en el denominador: nueva 100; base 100 conocidos + un intento sin cota ⇒ "
         "cociente [0, 1] ⇒ `certificada · cumple`",
         {"claude": {"total_exacto": tot(60, 40), **OMITE_EXTRA},
          "guion": {"llamadas_extra_rep": {(CASO, 1): EXTRA_SIN_SALIDA}}},
         {"claude": {"total_exacto": tot(60, 40)}},
         lambda d: cuota_certificada(d["v"], "cumple") and hay_intervalo(d["v"], 0, 1)),
        ("19.3e-num", "el mismo evento en el NUMERADOR ⇒ `estimada`",
         {"claude": {"total_exacto": tot(60, 40)}},
         {"claude": {"total_exacto": tot(60, 40), **OMITE_EXTRA},
          "guion": {"llamadas_extra_rep": {(CASO, 1): EXTRA_SIN_SALIDA}}},
         lambda d: cuota_estimada(d["v"])),
        ("19.2", "el mínimo excede: nueva 200 conocidos + un intento sin cota; base 100 sin filas sin cota ⇒ "
         "`certificada · excede`",
         {"claude": {"total_exacto": tot(60, 40)}},
         {"claude": {"total_exacto": tot(120, 80), **OMITE_EXTRA},
          "guion": {"llamadas_extra_rep": {(CASO, 1): EXTRA_SIN_SALIDA}}},
         lambda d: cuota_certificada(d["v"], "excede") and bool(cuota(d["v"]).get("intentos_sin_cota"))),
    ]
    for k, desc, base, nuevo, pred in casos:
        try:
            d = memo(f"e2e{k}", lambda base=base, nuevo=nuevo, k=k: construir_cuota(f"e2e{k}", base=base, nuevo=nuevo))
            check(f"E2E-{k} {desc} (cuota {cuota(d.get('v')).get('estado')}/{cuota(d.get('v')).get('resultado')})",
                  isinstance(d.get("v"), dict) and pred(d) and sin_motivo_de_cuota(d["v"]) and separacion_estricta(d["v"]))
        except EscenarioNoDisponible as exc:
            check(f"E2E-{k} {desc}: {exc}", False)
    e2e_19_1_7b()
    e2e_19_4()
    e2e_19_5()
    e2e_19_7()


def construir_e19_1() -> dict:
    g = dobles.Guion(llamadas_extra_rep={(CASO, 1): (("legal_edit", "extra_sin_salida"), ("legal_edit", "extra_timeout"))},
                     tolerar_fallos_en=frozenset({"extra_timeout"}))
    cl = dobles.ClaudeCLIDoble(omitir_salida_si=lambda c, r, n: n == "extra_sin_salida",
                               timeout_si=lambda c, r, n: n == "extra_timeout")
    return regenerar("e2e19-1", nuevo={"guion": g, "proveedores": dobles.proveedores(claude=cl)},
                     reanudar_si_para=True)


def e2e_19_1_7b() -> None:
    try:
        d = memo("e2e19-1", construir_e19_1)
        esc, v = d["esc"], d["v"]
        sin = [f for f in esc.r4("nuevo") if f.get("fase") == "produccion" and f.get("caso_id") == CASO
               and f.get("rep") == 1 and f.get("nodo") in ("extra_sin_salida", "extra_timeout")]
        ids = [f["id"] for f in sin]
        check("E2E-19.1 F17 con un intento sin `output_tokens` y otro que agota el tiempo ⇒ CALIDAD `aprueba` y "
              "CUOTA `estimada`, con `consumo.conocido`, `estimacion_empirica` por intento, el aviso literal y "
              "`intentos_sin_cota`",
              len(sin) == 2 and all(desconocida_sin_cota(f) for f in sin)
              and all(isinstance((((f.get("estimacion_empirica") or {}).get("inicial") or {}).get("tokens")), int)
                      for f in sin)
              and v.get("veredicto") == "aprueba" and not codigos(v) and cuota_estimada(v, ids)
              and "conocido" in (cuota(v).get("consumo") or {}))
        dr = ESC.leer(esc.dir("nuevo") / "decision_r.json") or {}
        usadas = {x.get("fila"): x for x in dr.get("estimaciones_usadas") or []}
        check("E2E-19.7b piloto con intentos sin cota: `decision_r.json` registra `estimaciones_usadas` (fila, tokens, "
              "corte_seq, observaciones_sha256) y `corte_decision_seq`; la puerta lo reproduce sin "
              "`decision_r_no_coincide`, exige todas las R y certifica la calidad",
              set(ids) <= set(usadas) and all(isinstance(usadas[i].get("tokens"), int) and "corte_seq" in usadas[i]
                                              and usadas[i].get("observaciones_sha256") for i in ids)
              and isinstance(dr.get("corte_decision_seq"), int) and v.get("veredicto") == "aprueba"
              and "decision_r_no_coincide" not in codigos(v))
        check("E2E-19.8 separación estricta: ninguna condición de cuota en la calidad ni de calidad en la cuota, y "
              "`consumo_desconocido_sin_cota` nunca es motivo de calidad", separacion_estricta(v))
    except EscenarioNoDisponible as exc:
        check(f"E2E-19.1/7b/8: {exc}", False)


def construir_e19_4() -> dict:
    """Base y nueva con una llamada de redacción ENORME (0,4·T conocidos cada una) en su primer caso; la
    nueva omite `output_tokens` en la redacción de su segundo caso: lo conocido (0,8·T) queda bajo el tope
    T, pero con la estimación empírica (salida observada 0,4·T, misma firma) lo supera ⇒ suspensión antes
    de la tercera corrida."""
    import run_banco04 as R
    k = R.constantes_de_protocolo(R.cargar_protocolo(), 7)
    T = R.ContadorCuota(techo_claude=k["techo_claude"], techo_codex=k["techo_codex"],
                        reserva_juicio_claude=k["reserva_claude"],
                        reserva_juicio_codex=k["reserva_codex"]).tope_produccion_claude
    X = (4 * int(T)) // 10
    casos = [CASO, "prescripcion-seguro-cumplimiento", "excepcion-contrato-no-cumplido"]

    def doble(omitir_segundo: bool):
        vistos: list = []

        def idx(c):
            if c != "_" and c not in vistos:
                vistos.append(c)
            return vistos.index(c) if c in vistos else -1
        return dobles.ClaudeCLIDoble(salida_si=lambda c, r, n: X if (idx(c) == 0 and n == "redaccion") else None,
                                     omitir_salida_si=lambda c, r, n: omitir_segundo and idx(c) == 1 and n == "redaccion")
    esc = ESC.Escenario("e2e19-4", versiones=VERS_ESQ)
    out = {"esc": esc, "T": int(T), "casos": casos}
    out["base"] = esc.producir(VERS_ESQ[0], proveedores=dobles.proveedores(claude=doble(False)), casos=casos,
                               solo_piloto=True, custodiados=False)
    out["nuevo"] = esc.producir(VERS_ESQ[1], proveedores=dobles.proveedores(claude=doble(True)), casos=casos,
                                solo_piloto=True, custodiados=False)
    esc.registrar_cadena(base=VERS_ESQ[0], nuevo=VERS_ESQ[1])
    out["v"] = esc.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])[1]
    return out


def e2e_19_4() -> None:
    try:
        d = memo("e2e19-4", construir_e19_4)
        esc = d["esc"]
        conocidas = [f for f in esc.todas_r4() if f.get("fase") == "produccion"
                     and (f.get("uso_validado") or {}).get("consumo_conocido") is True]
        conocido = sum(int(f["uso_validado"]["total"]) for f in conocidas)
        r2n = list(esc.dir(VERS_ESQ[1]).glob("*/rep-01.json"))
        susp = [ESC.leer(s_) or {} for s_ in ESC.archivos(esc.dir(VERS_ESQ[1]), "suspensiones/produccion-*.json")]
        sin = [f["id"] for f in esc.r4(VERS_ESQ[1]) if desconocida_sin_cota(f)]
        check(f"E2E-19.4 suspensión conservadora: lo conocido ({conocido}) queda bajo el tope ({d['T']}), pero con la "
              "estimación empírica inicial lo supera ⇒ la nueva se suspende ANTES de su tercera corrida",
              0 < conocido < d["T"] and len(r2n) == 2 and bool(susp) and d["nuevo"] != 0 and len(sin) == 1)
        check("E2E-19.4 la misma corrida publica la cuota por intervalo: evento en la NUEVA, mínimo del cociente "
              "≤ 1,25 ⇒ `estimada`", cuota_estimada(d["v"], sin) and sin_motivo_de_cuota(d["v"]))
    except (EscenarioNoDisponible, PuntoDeEntradaAusente) as exc:
        check(f"E2E-19.4: {exc}", False)


def e2e_19_5() -> None:
    """El envoltorio no toca el entorno del CLI (§4.3, §4.5 «Entorno del CLI»)."""
    from mia.agent import subscription_llm as sl
    for valor in ("0", "15", None):
        try:
            with entorno.entorno(CLAUDE_CODE_MAX_RETRIES=valor, CLAUDE_CODE_RETRY_WATCHDOG="1"):
                cl = dobles.ClaudeCLIDoble()
                esc = ESC.Escenario(f"e2e19-5-{valor or 'ausente'}", versiones=VERS_ESQ)
                code = esc.producir(VERS_ESQ[0], proveedores=dobles.proveedores(claude=cl), casos=[CASO],
                                    solo_piloto=True, custodiados=False)
                esperado = {k: v for k, v in os.environ.items() if not sl._is_sensitive_env(k)}
            filas = [f for f in esc.r4(VERS_ESQ[0]) if f.get("familia") == "claude_cli"]
            ent = {"max_retries": esperado.get("CLAUDE_CODE_MAX_RETRIES"),
                   "retry_watchdog_definida": "CLAUDE_CODE_RETRY_WATCHDOG" in esperado,
                   "max_output_tokens": esperado.get("CLAUDE_CODE_MAX_OUTPUT_TOKENS")}
            check(f"E2E-19.5 con `CLAUDE_CODE_MAX_RETRIES` {valor if valor is not None else 'ausente'} y "
                  "`CLAUDE_CODE_RETRY_WATCHDOG=1`, el `env` que recibe `subprocess.run` es IDÉNTICO al del producto "
                  "y `entorno_cli` registra esos valores",
                  code == 0 and bool(cl.envs) and all(e == esperado for e in cl.envs)
                  and ("CLAUDE_CODE_MAX_RETRIES" in esperado) == (valor is not None)
                  and bool(filas) and all(f.get("entorno_cli") == ent for f in filas))
        except (EscenarioNoDisponible, PuntoDeEntradaAusente) as exc:
            check(f"E2E-19.5 ({valor}): {exc}", False)


def construir_e19_7() -> dict:
    """Las tres llamadas de redacción usan la MISMA firma (legal_draft). La base (antes) sale con 100; la
    nueva: 100, una SIN `output_tokens` y, DESPUÉS, una con 200."""
    llam = (("legal_draft", "r1"), ("legal_draft", "r2"), ("legal_draft", "r3"))
    esc = ESC.Escenario("e2e19-7", versiones=VERS_ESQ)
    out = {"esc": esc}
    out["base"] = esc.producir_y_aprobar(
        VERS_ESQ[0], proveedores=dobles.proveedores(claude=dobles.ClaudeCLIDoble(salida_si=lambda c, r, n: 100)),
        guion=dobles.Guion(llamadas=llam, aprobar_sin_llamada=True), casos=[CASO], solo_piloto=True, custodiados=False)
    out["nuevo"] = esc.producir_y_aprobar(
        VERS_ESQ[1], proveedores=dobles.proveedores(claude=dobles.ClaudeCLIDoble(
            salida_si=lambda c, r, n: {"r1": 100, "r3": 200}.get(n), omitir_salida_si=lambda c, r, n: n == "r2")),
        guion=dobles.Guion(llamadas=llam, aprobar_sin_llamada=True), casos=[CASO], solo_piloto=True, custodiados=False)
    esc.registrar_cadena(base=VERS_ESQ[0], nuevo=VERS_ESQ[1])
    out["v"] = esc.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])[1]
    return out


def e2e_19_7() -> None:
    try:
        d = memo("e2e19-7", construir_e19_7)
        esc, v = d["esc"], d["v"]
        filas = {f.get("nodo"): f for f in esc.r4(VERS_ESQ[1]) if f.get("fase") == "produccion"}
        u, r3 = filas.get("r2") or {}, filas.get("r3") or {}
        ini = (u.get("estimacion_empirica") or {}).get("inicial") or {}
        check("E2E-19.7 estimación INICIAL congelada: `salida_observada` = 100 (solo observaciones con "
              "`seq_cierre < corte_seq`), la fila posterior de 200 no está entre sus observaciones, y la puerta NO "
              "da `telemetria_contradictoria`; solo cambia la `estimacion_puntual_final`",
              desconocida_sin_cota(u) and (ini.get("componentes") or {}).get("salida_observada") == 100
              and ini.get("corte_seq") == u.get("seq_cierre") and r3.get("id") not in (ini.get("observaciones") or [])
              and isinstance(v, dict) and "telemetria_contradictoria" not in codigos(v)
              and any(num(c.get("estimacion_puntual_final")) is not None
                      and num(c.get("estimacion_puntual_inicial")) is not None
                      and num(c["estimacion_puntual_final"]) > num(c["estimacion_puntual_inicial"])
                      for c in cuota(v).get("condiciones") or []))
        for nombre, mut, desc in (
                ("e2e19-7-tokens", lambda x: x["estimacion_empirica"]["inicial"].update(
                    tokens=int(x["estimacion_empirica"]["inicial"]["tokens"]) + 1), "su `tokens`"),
                ("e2e19-7-obs", lambda x: x["estimacion_empirica"]["inicial"].update(
                    observaciones=list(x["estimacion_empirica"]["inicial"]["observaciones"])[:-1]),
                 "su conjunto de observaciones")):
            e2 = ESC.copiar(esc, nombre)
            ruta = next(Path(f["_ruta"]) for f in e2.r4(VERS_ESQ[1]) if f.get("id") == u.get("id"))
            editar_json(ruta, mut)
            v2 = e2.decidir_cli("veredicto", base=VERS_ESQ[0], nuevo=VERS_ESQ[1])[1]
            check(f"E2E-19.7 editar {desc} de `estimacion_empirica.inicial` ⇒ calidad `no_certificable` "
                  "(`telemetria_contradictoria`)",
                  isinstance(v2, dict) and v2.get("veredicto") == "no_certificable"
                  and "telemetria_contradictoria" in codigos(v2))
    except (EscenarioNoDisponible, PuntoDeEntradaAusente, StopIteration, KeyError, TypeError) as exc:
        check(f"E2E-19.7: {type(exc).__name__}: {exc}", False)


def bloque_perimetro() -> None:
    print("\nP · perímetro: las pruebas no escriben nada bajo backend/ (decisión del director, v6)")
    r = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "backend"], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=60)
    inst = list(entorno.dir_instantaneas_prueba().glob("*.json"))
    r1_prueba = [m for m in _MEMO.values() if m[0] == "ok" and isinstance(m[1], dict) and "esc" in m[1]
                 and any((m[1]["esc"].r1(ver) or {}).get("instantaneas_de_prueba") is True for ver in m[1]["esc"].versiones)]
    check(f"P nada bajo `backend/` tras la suite ({r.stdout.strip()[:120] or 'vacío'}); las instantáneas de prueba "
          f"viven en el directorio temporal ({len(inst)}) y algún R1 lo declara con `instantaneas_de_prueba: true`",
          r.returncode == 0 and not r.stdout.strip() and bool(inst) and bool(r1_prueba))


# ════════════════════════════════════════════════════════════════════════════════════════
# Orquestación
# ════════════════════════════════════════════════════════════════════════════════════════
BLOQUES = [
    ("0", lambda: autocontrol.correr(check)),
    ("A", bloque_a),
    ("V", bloque_v),
    ("E2E-1", e2e_1),
    ("E2E-1m", e2e_1_esqueleto_mundo),
    ("E2E-2", e2e_2_e_inversa_esqueleto),
    ("E2E-3", e2e_3_4),
    ("E2E-5", e2e_5),
    ("E2E-6", e2e_6),
    ("E2E-7", e2e_7),
    ("E2E-8", e2e_8_9_12),
    ("E2E-10", e2e_10),
    ("E2E-11", e2e_11),
    ("E2E-13", e2e_13_15),
    ("E2E-14", e2e_14),
    ("E2E-17", e2e_17_18),
    ("F17", bloque_f17),
    ("S", bloque_s),
    ("I", bloque_i),
    ("INV", bloque_inversa),
    ("EXT", bloque_ext),
    ("R13", bloque_r13),
    ("E2E-19", e2e_19),
    ("P", bloque_perimetro),
]


def main() -> int:
    if _MODO_BD:
        return modo_bd()
    solo = None
    if "--solo" in _ARGS:
        solo = [x.strip() for x in _ARGS[_ARGS.index("--solo") + 1].split(",") if x.strip()]
    t0 = time.monotonic()
    for nombre, g in BLOQUES:
        if solo and not any(nombre == x or (x.endswith("*") and nombre.startswith(x[:-1])) for x in solo):
            continue
        try:
            g()
        except Exception as exc:  # noqa: BLE001 — un bloque que revienta es un bloque ROJO
            traceback.print_exc()
            check(f"bloque {nombre} no debe lanzar excepción ({type(exc).__name__}: {exc})", False)
    fallos = [n for n, ok in _results if not ok]
    print(f"\nRESULTADO: {len(_results) - len(fallos)}/{len(_results)} PASS  ({time.monotonic() - t0:.0f} s)")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
