"""Mia · eval.banco04.protocolo — constantes CONGELADAS del protocolo banco04-v1.2 (§10.2.1).

Fuente única: `docs/banco-calidad-04-protocolo.md`. Aquí no se decide nada: se transcribe. Si
un valor de este módulo no coincide con el documento, manda el documento y el desajuste es un
defecto de este archivo. Una vez corrida la línea base NADA de esto cambia (§0): un cambio abre
`banco04-v2` con corte de serie.

`hash_protocolo()` sella el contenido: el resultado publica ese hash, y el evaluador entero
(prompts, esquemas, validador y métricas) se sella aparte en `jueces.hash_evaluador()`.

Las LISTAS CERRADAS de §8.4 (conectores y rótulos que una exclusión puede contener, palabras
vacías para contar «palabras significativas», marcas de verbo conjugado del detector de átomos
compuestos) se versionan aquí, con el protocolo, como exige §8.4.
"""
from __future__ import annotations

import hashlib
import json
import math
from fractions import Fraction
from typing import Any

VERSION_PROTOCOLO = "banco04-v1.3"   # §12.5: I7 (jurisdicciones al juez)
# Formato de custodia, INDEPENDIENTE de VERSION_PROTOCOLO (§12.5): la v1.3 no cambia ningún
# artefacto custodiado y la custodia está ligada criptográficamente (AAD) a «banco04-v1.2».
# Todo cotejo de un artefacto custodiado compara contra esta constante.
PROTOCOLO_CUSTODIA = "banco04-v1.2"
FECHA_PROTOCOLO = "2026-10-11"

# ── §2 · Muestra y estratos ─────────────────────────────────────────────────────
# Ids de los casos visibles (grupo (a) en `eval/cases.py`, grupo (c) pequeño en
# `eval/holdout.py`). Los cuatro voluminosos custodiados (V1-V4) NO tienen id aquí: sus ids
# viven en la custodia y entran en tiempo de medición (`ids_custodiados`).
CASOS_A_CANONICOS: tuple[str, ...] = (
    "caducidad-reparacion-directa",
    "prescripcion-seguro-cumplimiento",
    "excepcion-contrato-no-cumplido",
)
CASOS_A_RIESGO: tuple[str, ...] = (
    "fuga-jurisdiccion-contrato-sin-pais",
    "disciplina-citas-formas-abreviadas",
    "procedencia-despacho-vacio",
    "entailment-cita-real-no-sostiene",
    "afirmacion-juridica-sin-cita",
    "soporte-cruzado-mal-anclado",
)
CASOS_A_VOLUMINOSO: tuple[str, ...] = ("expediente-voluminoso-cruce-disperso",)
CASOS_C_PEQUENOS: tuple[str, ...] = (
    "holdout-anclaje-norma-sellada",
    "holdout-expediente-vacio",
    "holdout-forma-abreviada-sigla",
)
N_CASOS_C_VOLUMINOSOS = 4
N_CASOS_TOTAL = 17

ESTRATO_A_CANONICOS = "A-canonicos"
ESTRATO_A_RIESGO = "A-riesgo"
ESTRATO_A_VOLUMINOSO = "A-voluminoso"
ESTRATO_C_PEQUENOS = "C-pequenos"
ESTRATO_C_VOLUMINOSOS = "C-voluminosos"
ESTRATOS: tuple[str, ...] = (ESTRATO_A_CANONICOS, ESTRATO_A_RIESGO, ESTRATO_A_VOLUMINOSO,
                             ESTRATO_C_PEQUENOS, ESTRATO_C_VOLUMINOSOS)
# Lectura esperada (§2.2): «completa» o «parcial».
ESTRATOS_LECTURA_COMPLETA: tuple[str, ...] = (ESTRATO_A_CANONICOS, ESTRATO_A_RIESGO,
                                              ESTRATO_C_PEQUENOS)
ESTRATOS_VOLUMINOSOS: tuple[str, ...] = (ESTRATO_A_VOLUMINOSO, ESTRATO_C_VOLUMINOSOS)
GRUPO_DE_ESTRATO = {
    ESTRATO_A_CANONICOS: "a", ESTRATO_A_RIESGO: "a", ESTRATO_A_VOLUMINOSO: "a",
    ESTRATO_C_PEQUENOS: "c", ESTRATO_C_VOLUMINOSOS: "c",
}

# §6.2 · Unidades de inferencia de la comparación pareada (nunca cruzan (a) y (c)).
UNIDAD_A_PEQUENOS = "A-pequenos"
UNIDAD_C_VOLUMINOSOS = "C-voluminosos"
UNIDAD_A_VOLUMINOSO = "A-voluminoso"
UNIDAD_C_PEQUENOS = "C-pequenos"
UNIDADES_INFERENCIA: dict[str, dict[str, Any]] = {
    UNIDAD_A_PEQUENOS: {"estratos": (ESTRATO_A_CANONICOS, ESTRATO_A_RIESGO), "k": 9,
                        "tratamiento": "bootstrap", "rotulo": None},
    UNIDAD_C_VOLUMINOSOS: {"estratos": (ESTRATO_C_VOLUMINOSOS,), "k": 4,
                           "tratamiento": "bootstrap", "rotulo": "orientativo (k = 4)"},
    UNIDAD_A_VOLUMINOSO: {"estratos": (ESTRATO_A_VOLUMINOSO,), "k": 1,
                          "tratamiento": "sin_inferencia", "rotulo": None},
    UNIDAD_C_PEQUENOS: {"estratos": (ESTRATO_C_PEQUENOS,), "k": 3,
                        "tratamiento": "sin_inferencia", "rotulo": None},
}


def estrato_de(case_id: str, ids_custodiados: tuple[str, ...] | list[str] = ()) -> str:
    """Estrato de un caso. Un id desconocido es un error (nunca se adivina el estrato)."""
    if case_id in CASOS_A_CANONICOS:
        return ESTRATO_A_CANONICOS
    if case_id in CASOS_A_RIESGO:
        return ESTRATO_A_RIESGO
    if case_id in CASOS_A_VOLUMINOSO:
        return ESTRATO_A_VOLUMINOSO
    if case_id in CASOS_C_PEQUENOS:
        return ESTRATO_C_PEQUENOS
    if case_id in tuple(ids_custodiados):
        return ESTRATO_C_VOLUMINOSOS
    raise KeyError(f"caso fuera de la muestra del protocolo: {case_id!r}")


# ── §3.1 · Repeticiones ─────────────────────────────────────────────────────────
CASOS_FUGA_INTERMITENTE: tuple[str, ...] = (
    "fuga-jurisdiccion-contrato-sin-pais",
    "disciplina-citas-formas-abreviadas",
    "holdout-expediente-vacio",
)
R_FUGA = 10
R_PEQUENOS = 5
R_VOLUMINOSOS = 5
CORRIDAS_POR_VERSION = 100
# §3.4 · Contingencia por consumo: R baja de 5 a 3 SOLO en los 9 pequeños sin fuga (82).
R_CONTINGENCIA_PEQUENOS_SIN_FUGA = 3
CORRIDAS_CON_CONTINGENCIA = 82


def repeticiones(case_id: str, ids_custodiados: tuple[str, ...] | list[str] = (), *,
                 contingencia: bool = False) -> int:
    estrato = estrato_de(case_id, ids_custodiados)
    if case_id in CASOS_FUGA_INTERMITENTE:
        return R_FUGA
    if estrato in ESTRATOS_VOLUMINOSOS:
        return R_VOLUMINOSOS
    return R_CONTINGENCIA_PEQUENOS_SIN_FUGA if contingencia else R_PEQUENOS


# ── §3.3 · Cotas ilustrativas (NO son confianza acreditada) ─────────────────────
FRASE_COTA_ILUSTRATIVA = (
    "bajo el supuesto de corridas independientes e idénticamente distribuidas, que aquí no se "
    "cumple"
)
ENUNCIADO_CERO_PERMITIDO = (
    "En los 17 casos sintéticos y sus 100 corridas no se observó ninguna afirmación sin "
    "respaldo. Es un recuento sobre una muestra fija y pequeña. No es una estimación del "
    "rendimiento en expedientes reales ni acredita una tasa máxima"
)
ALFA_COTA_ILUSTRATIVA = 0.05  # 1 − 0,05^(1/R): R=5 → ≈0,45; R=10 → ≈0,26


def cota_ilustrativa(r: int) -> float:
    """Tasa por caso aún compatible con cero fallos en R corridas (ilustración condicionada)."""
    if r <= 0:
        raise ValueError("R debe ser positivo")
    return 1.0 - ALFA_COTA_ILUSTRATIVA ** (1.0 / r)


# ── §3.4 · Techos del circuito, reserva del juicio y suspensión ─────────────────
TECHOS_CIRCUITO: dict[str, dict[str, int]] = {
    "bloque0": {"claude": 18_000_000, "codex": 5_000_000},
    "bloque7": {"claude": 32_000_000, "codex": 8_000_000},
}
# Reserva del juicio en el Bloque 0: ≈7 M Claude y la TOTALIDAD de Codex.
RESERVA_JUICIO: dict[str, dict[str, int | str]] = {
    "bloque0": {"claude": 7_000_000, "codex": "total"},
    # §3.2 (Bloque 7): juicio conjunto de 200 salidas ≈11 M + adjudicación, estabilidad y
    # reintentos ≈2 M Claude; ≈6 M Codex de juicio. No es "total" porque 0.4 usa Codex en
    # producción (5C encendido por defecto, decisión 4 de Pipe). Aclaración C17 (§12.4).
    "bloque7": {"claude": 13_000_000, "codex": 6_000_000},
}
ROTULO_SUSPENSION = "incompleto — no certificable"

# ── §4.3 / §8.4 · Rúbrica por afirmación ────────────────────────────────────────
TIPOS_AFIRMACION: tuple[str, ...] = (
    "hecho_expediente", "proposicion_juridica", "dicho_abogado", "inferencia",
    "laguna_o_abstencion", "no_afirmativa",
)
ESTADOS_RESPALDO: tuple[str, ...] = (
    "con_respaldo", "con_respaldo_sin_localizador", "localizador_falso",
    "marcada_correctamente", "marcada_innecesariamente", "dicho_abogado_fiel",
    "inferencia_valida", "sin_respaldo", "no_aplica",
)
ESTADOS_DEFECTO: frozenset[str] = frozenset({"sin_respaldo", "localizador_falso"})
# Estados que una premisa de `inferencia_valida` puede tener (§8.4).
ESTADOS_PREMISA_VALIDA: frozenset[str] = frozenset(
    {"con_respaldo", "con_respaldo_sin_localizador", "dicho_abogado_fiel"})
# Estados con pasaje que debe localizarse; si no se localiza tras el reintento, el átomo pasa
# a adjudicación como presunto `sin_respaldo` (§8.4, «Ante un rechazo», tercer punto).
ESTADOS_CON_PASAJE: frozenset[str] = frozenset(
    {"con_respaldo", "con_respaldo_sin_localizador", "marcada_innecesariamente",
     "dicho_abogado_fiel"})
JUSTIFICACIONES_EXCLUSION: tuple[str, ...] = (
    "puntuacion", "conector_sin_contenido", "encabezado_sin_contenido", "formula_transicion",
    "marca_estructural",
)
JUSTIFICACIONES_NO_APLICA: tuple[str, ...] = (
    "encabezado_sin_contenido", "formula_transicion", "cortesia", "marca_estructural",
)
MARCAS: tuple[str, ...] = ("verificar", "omitida_por_muro", "condicionada")
SUBTIPOS_SIN_RESPALDO: tuple[str, ...] = (
    "hecho", "juridica_sin_cita", "cita_no_sostiene", "contradicha_por_expediente",
    "negativa_falsa", "procedencia", "fuga", "localizador_falso",
)
MAX_PALABRAS_SIGNIFICATIVAS_NO_APLICA = 8

# Lista CERRADA de conectores y rótulos sin contenido que una exclusión puede contener (§8.4).
# Se comparan normalizados (minúsculas, sin tildes). Las frases de varias palabras se casan
# primero (codicia por longitud).
EXCLUSION_LISTA_CERRADA: tuple[str, ...] = (
    # conectores
    "y", "e", "o", "u", "ni", "pero", "ademas", "asimismo", "asi mismo", "tambien",
    "por tanto", "por lo tanto", "en consecuencia", "por consiguiente", "por ende", "asi",
    "sin embargo", "no obstante", "por otra parte", "por otro lado", "de otro lado",
    "en primer lugar", "en segundo lugar", "en tercer lugar", "en cuarto lugar",
    "finalmente", "por ultimo", "en suma", "en sintesis", "en resumen", "es decir",
    "entonces", "luego", "igualmente",
    # rótulos sin contenido
    "antecedentes", "conclusion", "conclusiones", "hechos", "fundamentos", "analisis",
    "diagnostico", "borrador", "resumen", "peticion", "peticiones", "pretensiones",
    "pruebas", "anexos", "consideraciones", "introduccion", "asunto", "referencia", "ref",
    "nota", "notas", "observaciones", "cierre", "recomendacion", "recomendaciones",
    "riesgos", "pendientes", "puntos", "apartado", "seccion", "capitulo", "anexo",
    "fundamentos de derecho", "senor juez", "notificaciones", "competencia",
    # ordinales de apartado («PRIMERO.-», «SEGUNDA.»)
    "primero", "segundo", "tercero", "cuarto", "quinto", "sexto", "septimo", "octavo", "noveno",
    "decimo", "primera", "segunda", "tercera", "cuarta", "quinta", "sexta", "septima", "octava",
    "novena", "decima",
)
# Roles procesales y rótulos de escrito que NO son nombres de partes: el respaldo conservador
# de §8.4 (cuando no se conocen las partes) no los toma por nombre propio.
ROLES_Y_ROTULOS: frozenset[str] = frozenset({
    "juez", "jueza", "senor", "senora", "senores", "magistrado", "magistrada", "magistrados",
    "tribunal", "honorable", "doctor", "doctora", "despacho", "sala", "seccion", "consejo",
    "corte", "juzgado", "derecho", "pretension", "pretensiones", "demanda", "contestacion",
    "excepcion", "excepciones", "recurso", "apelacion", "reposicion", "memorial", "poder",
    "notificaciones", "competencia", "cuantia", "procedimiento", "proceso", "referencia",
    "asunto", "radicado", "demandante", "demandado", "demandada", "apoderado", "apoderada",
    "atentamente", "respetuosamente", "cordialmente", "fundamentos", "hechos", "pruebas",
})
# Numeración de apartado: solo admitida como PRIMER elemento no blanco del segmento, y con
# delimitador («1.», «1.2», «a)», «IV.»). Una cifra suelta («999») nunca es numeración.
NUMERACION_APARTADO_REGEX = (
    r"(?:\d{1,3}(?:\.\d{1,3})+\.?|\d{1,3}[.)]|[a-zA-Z][.)]|[IVXLCDMivxlcdm]{1,6}[.)])"
)

# Palabras vacías para contar «palabras significativas» (§8.4: más de 8 ⇒ no es no_aplica).
PALABRAS_VACIAS: frozenset[str] = frozenset({
    "a", "al", "ante", "bajo", "con", "contra", "de", "del", "desde", "en", "entre", "hacia",
    "hasta", "para", "por", "segun", "sin", "sobre", "tras", "el", "la", "los", "las", "lo",
    "un", "una", "unos", "unas", "y", "e", "o", "u", "ni", "que", "se", "su", "sus", "le",
    "les", "me", "te", "nos", "os", "mi", "tu", "este", "esta", "estos", "estas", "ese", "esa",
    "esos", "esas", "aquel", "aquella", "como", "mas", "muy", "ya", "si", "no", "pero",
})
# Palabras que delatan una fecha o una cifra aunque no traigan dígitos (anti-evasión §8.4).
PALABRAS_FECHA_CIFRA: frozenset[str] = frozenset({
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
    "setiembre", "octubre", "noviembre", "diciembre", "mil", "miles", "millon", "millones",
    "billon", "billones", "ciento", "cientos", "centenar", "docena", "porcentaje",
    "por ciento",
})

# ── §8.4 · Átomo compuesto: detector determinista de dos verbos conjugados ─────
# Separadores que el protocolo nombra: «y», «pero», «aunque», «mientras» o «;».
SEPARADORES_COMPUESTO_REGEX = r"\s+(?:y|e|pero|aunque|mientras)\s+|;"
# El juez puede declarar que un átomo con dos verbos es UNA proposición solo con este prefijo
# literal al inicio de `motivo` (la justificación se publica). Sin el prefijo, se rechaza.
PREFIJO_UNA_PROPOSICION = "UNA_PROPOSICION:"
# Formas conjugadas frecuentes (normalizadas, sin tildes) — lista cerrada versionada.
VERBOS_CONJUGADOS: frozenset[str] = frozenset({
    "es", "son", "era", "eran", "fue", "fueron", "sera", "seran", "sea", "sean",
    "estan", "estaba", "estaban", "estuvo", "estuvieron",
    "ha", "han", "habia", "habian", "hubo", "habra", "habran", "hay",
    "tiene", "tienen", "tenia", "tenian", "tuvo", "tuvieron", "tendra",
    "debe", "deben", "debia", "debio", "puede", "pueden", "podia", "pudo",
    "dice", "dicen", "dijo", "consta", "constan", "establece", "establecen", "senala",
    "senalan", "dispone", "disponen", "indica", "indican", "preve", "exige", "exigen",
    "corresponde", "corresponden", "procede", "proceden", "opera", "vence", "vencen",
    "paga", "pagan", "adeuda", "adeudan", "reclama", "reclaman", "solicita", "solicitan",
    "pide", "piden", "niega", "niegan", "acredita", "acreditan", "demuestra", "otorga",
    "obliga", "obligan", "prescribe", "caduca", "aplica", "aplican", "rige", "rigen",
    "contiene", "contienen", "menciona", "mencionan", "omite", "asciende", "ascienden",
    "firman", "gana", "ganan", "pierde", "pierden", "cumple", "cumplen",
    "incumple", "incumplen", "existe", "existen", "faltan", "queda", "quedan",
    "resulta", "resultan", "implica", "permite", "impide", "afirma", "sostiene", "alega",
    "alegan", "reconoce", "reconocen", "acepta", "aceptan", "rechaza", "rechazan",
})
# Formas con tilde que, sin ella, colisionan con otra palabra («está»/«esta»): se miran crudas.
VERBOS_CONJUGADOS_TILDE: frozenset[str] = frozenset({"está", "están", "prevé"})
# «suma», «firma», «falta» quedan FUERA: son sustantivos frecuentes en un texto jurídico.
# Desinencias de 3.ª persona de bajo riesgo de falso positivo, sobre la forma normalizada
# (pretérito plural e imperfecto plural). «-era»/«-ara» sin tilde NO entran: «primera»,
# «manera», «para» serían verbos.
DESINENCIAS_VERBO: tuple[str, ...] = ("aron", "ieron", "aban")
# Desinencias CON tilde, miradas antes de normalizar: pretérito en «-ó» (ganó, pagó, firmó)
# y futuro (pagará, deberán).
DESINENCIAS_VERBO_TILDE: tuple[str, ...] = ("ó", "ará", "erá", "irá", "arán", "erán", "irán")
LONGITUD_MIN_VERBO_DESINENCIA = 4

# ── §4.2 / §8.2 · Jueces ────────────────────────────────────────────────────────
JUEZ_PRINCIPAL = {"proveedor": "claude_cli", "modelo": "opus", "esfuerzo": "high"}
JUEZ_CRIBADO = {"proveedor": "codex_cli", "modelo": "gpt-6-astra", "esfuerzo": "high",
                "sandbox": "read-only"}
FRACCION_CODEX_PASADA2 = Fraction(15, 100)
FRACCION_ESTABILIDAD = Fraction(10, 100)
REINTENTOS_POR_RECHAZO = 1
# R2-C-N2: la evidencia de la pasada 1 y del tercer voto gana `uso_fuente` (esquema v1.3); la
# pasada 2 y el voto de cobertura no cambian. Pendiente de aclaración C18 del director.
ESQUEMA_PASADA1 = "banco04-juez-respaldo/v1.3"
ESQUEMA_PASADA2 = "banco04-juez-cobertura/v1.2"
ESQUEMA_TERCER_VOTO = "banco04-tercer-voto/v1.3"
USOS_FUENTE: tuple[str, ...] = ("aplicable", "descriptivo", "rechazo_aplicabilidad")
USOS_FUENTE_NO_APLICATIVOS: frozenset[str] = frozenset({"descriptivo", "rechazo_aplicabilidad"})
ESQUEMA_VOTO_COBERTURA = "banco04-voto-cobertura/v1.2"
# I5 · Cota conservadora de un intento de juez cuyo consumo no se conoce (timeout, caída): entrada
# estimada por exceso (caracteres / 3) + el máximo de salida que el CLI admite a la llamada.
COTA_SALIDA_JUEZ_TOKENS = 128_000
CARACTERES_POR_TOKEN_COTA = 3
# Tope DURO del prompt de un juez. Nunca se trunca el expediente para caber: si no cabe, la
# salida queda no evaluada y se dice (truncar escondería justo el pasaje enterrado).
MAX_CARACTERES_PROMPT = 800_000

# ── §8.5 · Concordancia ─────────────────────────────────────────────────────────
KAPPA_MINIMO = Fraction(6, 10)
KAPPA_MIN_UNIDADES_DEFECTO = 10

# ── §8.6 · Validación de los jueces ─────────────────────────────────────────────
VALIDACION_MIN_DEFECTOS = 30
VALIDACION_MIN_CONTROLES = 30
VALIDACION_MIN_CLAUSULAS_BREVES_RESERVADO = 10
# R2-C-N1 · cobertura MÍNIMA que la acreditación de compatibilidad v1.3 del reservado tiene que
# demostrar (entradas de verdad comprobables por clase). El protocolo no fija la cifra: es una
# propuesta de código pendiente de la aclaración C19 del director.
ACREDITACION_V13_MINIMOS: dict[str, int] = {
    "fuga_sin_ordenamiento": 1, "fuga_otro_ordenamiento": 1, "negacion_ajena": 1,
    "control_descriptivo": 1,
}
CLAUSULA_BREVE_FRACCION_MAX = Fraction(20, 100)
SENSIBILIDAD_CIRCUITO_MIN = Fraction(95, 100)
FALSOS_POSITIVOS_CIRCUITO_MAX = Fraction(10, 100)
SENSIBILIDAD_JUEZ_MIN = Fraction(90, 100)
FALSOS_POSITIVOS_JUEZ_MAX = Fraction(10, 100)
DESCARTE_SOLO_CODEX_MAX = Fraction(20, 100)
SENSIBILIDAD_CLAUSULA_BREVE_MIN = Fraction(90, 100)
CATEGORIAS_DEFECTO_PLANTADO: tuple[str, ...] = (
    "hecho_alterado", "fecha_cambiada", "cita_no_sostiene", "regla_sin_cita",
    "negativa_falsa", "doc_equivocado", "conclusion_contradicha", "fuga",
    "afirmacion_en_titulo", "afirmacion_en_celda", "hecho_mal_expresado_marcador_intacto",
    "clausula_falsa_breve",
)
CATEGORIA_CONTROL = "control"

# ── §5 / §6.1 · Umbrales absolutos ──────────────────────────────────────────────
UMBRAL_ALCANCE = Fraction(95, 100)  # = config.MIA_ALCANCE_AVISO_UMBRAL por defecto; no se recalibra
UMBRALES_ABSOLUTOS: dict[str, Any] = {
    "afirmaciones_sin_respaldo": 0,
    "fuga_jurisdiccion": 0,
    "definitivo_con_lectura_insuficiente": 0,
    "discordancias_sin_resolver": 0,
    "kappa_minimo": KAPPA_MINIMO,
    "sensibilidad_circuito_min": SENSIBILIDAD_CIRCUITO_MIN,
    "falsos_positivos_circuito_max": FALSOS_POSITIVOS_CIRCUITO_MAX,
    "evaluacion_completa": True,
    "cobertura_decisivos_lectura_completa_media": Fraction(90, 100),
    "cobertura_decisivos_lectura_completa_caso_min": Fraction(80, 100),
    "cobertura_decisivos_en_lo_leido_voluminosos_media": Fraction(90, 100),
    "cobertura_decisivos_voluminosos_media": Fraction(34, 100),
    "tasa_omision_leido_max": Fraction(20, 100),
    "utilidad_resultado_limitado_media": Fraction(80, 100),
    "aprobacion_proxy_lectura_completa_min": Fraction(60, 100),
}
UTILIDAD_PROXY_MIN = Fraction(80, 100)  # celdas de §7.2 «el proxy falla si la utilidad < 0,80»

# ── §6.2 · Comparación ──────────────────────────────────────────────────────────
DELTA = Fraction(5, 100)
DELTA_TURNOS_COMPLETADOS = Fraction(2, 100)
K_MIN_BOOTSTRAP = 4
NIVEL_INTERVALO = Fraction(90, 100)
BOOTSTRAP_REMUESTREOS = 10_000
BOOTSTRAP_METODO = "percentil, remuestreo de casos con reemplazo, random.Random(semilla)"
PERDIDA_MAX_COBERTURA_POR_CASO = Fraction(20, 100)
# «Hecho decisivo que 0.3.3 encontró en al menos 3 de 5 corridas no puede caer a 1 de 5 o
# menos»: se aplica como fracción de R (3/5 y 1/5) para los casos con R distinto de 5.
DECISIVO_ESTABLE_BASE_MIN = Fraction(3, 5)
DECISIVO_CAIDA_MAX = Fraction(1, 5)
EXTENSION_CORRIDAS = 5
EXTENSION_MAX_CASOS = 5
VEREDICTOS_COMPARATIVOS: tuple[str, ...] = (
    "regresion", "no_concluyente", "sin_regresion_observada", "mejora",
    "descriptivo_sin_inferencia",
)
ROTULO_TRAS_EXTENSION = "sin regresión demostrada; evidencia insuficiente"
# Sentido de cada métrica comparativa: +1 si «mejor» es mayor; −1 si «mejor» es menor.
METRICAS_COMPARATIVAS: dict[str, dict[str, Any]] = {
    "turnos_completados": {"sentido": 1, "delta": DELTA_TURNOS_COMPLETADOS},
    "cobertura_hechos_materiales": {"sentido": 1, "delta": DELTA},
    "cobertura_hechos_decisivos": {"sentido": 1, "delta": DELTA},
    "omisiones_materiales": {"sentido": -1, "delta": DELTA},
    "definitivo_con_hecho_decisivo_omitido": {"sentido": -1, "delta": DELTA},
    "aprobacion_sin_edicion_proxy": {"sentido": 1, "delta": DELTA},
    "utilidad_resultado_limitado": {"sentido": 1, "delta": DELTA},
    "falsos_bloqueos": {"sentido": -1, "delta": DELTA},
    "abstencion_injustificada": {"sentido": -1, "delta": DELTA},
    "tasa_cambio_de_motor": {"sentido": -1, "delta": DELTA},
}

# Métricas comparativas que pueden NO aplicar en una unidad: aplican si algún caso de la unidad
# tiene el conteo > 0 (I1: sin dato donde aplica ⇒ no certificable).
APLICABILIDAD_COMPARATIVA: dict[str, str] = {
    "cobertura_hechos_decisivos": "n_decisivos_clave",
    "utilidad_resultado_limitado": "n_limitadas",
}

# ── §6.3 · Techo de cuota (sumas y extremos; la mediana es solo descriptiva) ────
TECHO_CLAUDE_FACTOR = Fraction(125, 100)
TECHO_CODEX_FACTOR = Fraction(50, 100)
TECHO_INFERENCIAS_EXTRA_POR_CORRIDA = 3
SUBIDA_QUE_EXIGE_MEJORA = Fraction(110, 100)

# ── §8.8 · Rótulos y lenguaje ───────────────────────────────────────────────────
ROTULO_AUTOMATICO = ("Evaluación automática (Opus high y Codex en cribado doble, adjudicación "
                     "por mayoría)")
ROTULO_CALIBRADO = "… calibrada con revisión humana ciega (n = 10)"
ROTULO_DISCORDANCIA = "no certificable por discordancia entre jueces"
# Formas prohibidas en todo lo publicable (§1.7, §3.3, §6.2). No se prohíbe la palabra suelta
# «confianza»: el propio protocolo la usa para negarla.
LENGUAJE_PROHIBIDO_REGEX: tuple[str, ...] = (
    r"\bequivalent[ea]s?\b",
    r"\bequivalencia\s+demostrada\b",
    r"\bempate\b",
    r"\d+(?:[.,]\d+)?\s*%\s*de\s+confianza",
    r"\bniveles?\s+de\s+confianza\b",
    r"\bcon\s+\S+\s*%\s*de\s+confianza\b",
    r"\btasa\s+inferior\s+a\b",
    r"\bMIA\s+no\s+afirma\s+sin\s+respaldo\b",
    r"\b3\s*/\s*N\b",
)

# ── Precedencias de veredicto (§6.4) ────────────────────────────────────────────
VEREDICTOS_GLOBALES: tuple[str, ...] = ("aprueba", "reprueba", "no_certificable")


def _jsonable(valor: Any) -> Any:
    if isinstance(valor, Fraction):
        return f"{valor.numerator}/{valor.denominator}"
    if isinstance(valor, (frozenset, set)):
        return sorted(_jsonable(v) for v in valor)
    if isinstance(valor, (list, tuple)):
        return [_jsonable(v) for v in valor]
    if isinstance(valor, dict):
        return {str(k): _jsonable(v) for k, v in valor.items()}
    return valor


def constantes() -> dict[str, Any]:
    """Todas las constantes MAYÚSCULAS del módulo, serializables (para el hash y el informe)."""
    return {nombre: _jsonable(valor) for nombre, valor in sorted(globals().items())
            if nombre.isupper() and not nombre.startswith("_")}


def hash_protocolo() -> str:
    canon = json.dumps(constantes(), ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canon).hexdigest()


def ceil_fraccion(fraccion: Fraction, n: int) -> int:
    """⌈fracción · n⌉ exacto (para las submuestras con semilla)."""
    return math.ceil(fraccion * n)
