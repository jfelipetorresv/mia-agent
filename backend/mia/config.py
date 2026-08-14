"""Mia · config — carga .env y expone la configuración del backend."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ancla del estado de INSTANCIA (.env, mia-data). Tres modos, en orden de precedencia:
# 1. MIA_APP_DIR (env): la cáscara de escritorio (Fase 4) le dice al motor dónde vive
#    su instancia — también útil para tests. Manda siempre que venga.
# 2. Empaquetado (PyInstaller expone sys.frozen): __file__ vive DENTRO del bundle y no
#    hay repo → el estado va a la carpeta de datos de la app del usuario.
# 3. Desarrollo (default, sin cambios): la raíz del repo (backend/mia/config.py -> mia/).
_app_dir = os.getenv("MIA_APP_DIR", "").strip()
if _app_dir:
    PROJECT_ROOT = Path(_app_dir).resolve()
    # Fallo ruidoso, no silencioso: si la cáscara pasó una ruta sin .env, el motor
    # arrancaría con TODOS los defaults (DATABASE_URL vacío, etc.) y el síntoma
    # aguas abajo ("JWT_SECRET faltante") no diría la causa real.
    if not (PROJECT_ROOT / ".env").exists():
        print(
            f"[mia.config] AVISO: MIA_APP_DIR={PROJECT_ROOT} no contiene un .env — "
            "el motor arranca con valores por defecto.",
            file=sys.stderr,
        )
elif getattr(sys, "frozen", False):
    PROJECT_ROOT = (Path(os.getenv("LOCALAPPDATA") or Path.home()) / "Mia").resolve()
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def optional_capabilities() -> dict[str, dict[str, object]]:
    """Capacidades pesadas presentes en ESTA distribución, sin importarlas.

    El manifiesto del bundle es declarativo, pero nunca manda sobre la realidad:
    si falta el módulo, ``available`` queda False. En desarrollo, donde no hay
    manifiesto, la detección por ``find_spec`` sigue siendo honesta.
    """
    manifest_path = os.getenv("MIA_BUNDLE_MANIFEST", "").strip()
    manifest: dict = {}
    manifest_valid = False
    if manifest_path:
        try:
            raw = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            manifest = raw if isinstance(raw, dict) else {}
            manifest_valid = isinstance(raw, dict)
        except (OSError, ValueError, TypeError):
            manifest = {}
    declared = manifest.get("capabilities") if isinstance(manifest.get("capabilities"), dict) else {}

    def capability(name: str, modules: tuple[str, ...], absent: str) -> dict[str, object]:
        installed = all(importlib.util.find_spec(module) is not None for module in modules)
        # En desarrollo (sin manifiesto) detectamos el entorno. En un bundle,
        # un manifiesto ausente/corrupto nunca habilita por accidente algo que
        # simplemente quedo arrastrado por el empaquetador.
        expected = bool(declared.get(name, installed)) if not manifest_path or manifest_valid else False
        available = installed and expected
        return {
            "available": available,
            "included": expected,
            "reason": "" if available else absent,
        }

    return {
        "ocr": capability(
            "ocr", ("rapidocr_onnxruntime",),
            "La lectura óptica no está incluida; los PDF con texto siguen funcionando.",
        ),
        "voice": capability(
            "voice", ("sherpa_onnx", "av"),
            "El componente de voz no está incluido en esta instalación.",
        ),
    }

PG_DB = os.getenv("PG_DB", "mia")

# Entorno de despliegue (auditoría de seguridad 2026-07): "dev" (default, laptop
# del despacho / Modo B) o "production" (si algún día hubiera un servidor expuesto).
# En producción se endurecen automáticamente: docs del API apagadas, exp obligatorio
# en el JWT.
MIA_ENV = os.getenv("MIA_ENV", "dev").strip().lower()
IS_PRODUCTION = MIA_ENV in ("prod", "production")

# Conexión de la app: rol mia_app (RLS SÍ aplica). NUNCA el superusuario.
DATABASE_URL = os.getenv("DATABASE_URL", "")

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALG = os.getenv("JWT_ALG", "HS256")
# Vigencia del token de sesión (días). 7 por defecto; bajar en producción si se
# despliega expuesto a internet (no hay revocación de tokens en v1).
JWT_TTL_DAYS = int(os.getenv("MIA_JWT_TTL_DAYS", "7"))

# Orígenes permitidos para CORS (auditoría 2026-07): coma-separados en .env.
# Default: solo el frontend local. En producción DEBE ser el dominio real del
# frontend (nunca "*": las respuestas llevan credenciales).
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "MIA_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")
    if o.strip()
]

EMBED_MODEL = os.getenv("EMBED_MODEL", "voyage-law-2")
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")

# --- Gateway LLM (LiteLLM proxy, decisión #3) ---
# Todo el tráfico LLM pasa por el proxy OpenAI-compatible (Modo B: localhost:4000).
# Los nombres de modelo son los alias de litellm_config.yaml (claude-haiku, claude-sonnet).
LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "http://localhost:4000")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "sk-mia-local")
# CP-S3 · OpenRouter: acceso a decenas de modelos con UNA clave, como red de respaldo
# en la nube (política "nube"). OPCIONAL: sin clave, el proveedor no se ofrece y las
# cadenas de fallback quedan como estaban. La clave la pasa LiteLLM al upstream
# (litellm_config.yaml lee os.environ/OPENROUTER_API_KEY). Costo de pago → poner tope
# de gasto en el panel de OpenRouter al crearla (regla de operación segura).
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
# Modelo de razonamiento principal del agente (alias del gateway). Configurable
# por despacho/entorno. compression y verification tienen su propio modelo fijo
# en agent/llm.py (decisión #7) y NO usan esta variable.
MIA_MODEL = os.getenv("MIA_MODEL", "claude-sonnet")
# Ventana de contexto del modelo principal (tokens). La usa el ContextCompressor
# (2c) para el umbral del 55%. Default 200k (claude-sonnet); configurable por entorno.
MIA_CONTEXT_WINDOW = int(os.getenv("MIA_CONTEXT_WINDOW", "200000"))

# --- Lectura adaptativa del expediente (recuperación) ---------------------------
# El tamaño de lectura del expediente DEJA de ser un literal y se DERIVA en cada turno
# de tres señales: cuánto material hay indexado en el asunto, cuánto cabe en el
# presupuesto real del nodo que va a consumirlo (agents/context_recovery.budget_for
# sobre MIA_CONTEXT_WINDOW) y qué tan exigente es la pregunta. Estas constantes son los
# DIALES de esa derivación, no el tamaño en sí. Ninguna depende de país, corte, moneda
# ni idioma: son proporciones y conteos.
#
# Fracción del presupuesto del nodo que la recuperación puede llegar a ocupar. El resto
# queda para el prompt del sistema, la consulta del abogado y la respuesta. Es el margen
# que impide que "leer más" desemboque en un CONTEXT_TOO_LONG en cada turno.
#
# DECISIÓN DEL DUEÑO (2026-07-20): con 0.35 el gasto de IA por turno subía entre 11 y 20
# veces frente al literal de 8 que había antes. Se baja a 0.22 — ~7 veces más lectura que
# antes en vez de ~20, conservando la promesa que el gate `a1` de test_retrieval_adaptativa
# custodia: en un expediente grande Mia lee una FRACCIÓN REAL del material (>10%), no una
# muestra simbólica. Se probó 0.15 y rompía justo esa promesa: recorta el gasto, pero
# devuelve el producto al problema que este bloque vino a resolver.
# Se ajusta AQUÍ y no en MIA_RETRIEVAL_MAX_TOP_K a propósito: un techo bajo hace que los
# tres niveles de exigencia saturen en el mismo valor y la lectura vuelva a ser, de hecho,
# un número fijo.
# Valor PROVISIONAL: el rediseño acordado es la lectura agéntica (ver HANDOFF.md), donde el
# modelo pide más material cuando le falta y nadie tiene que fijar una proporción.
MIA_RETRIEVAL_COVERAGE_FRACTION = float(
    os.getenv("MIA_RETRIEVAL_COVERAGE_FRACTION", "0.22"))
# Tope duro de la fracción anterior una vez aplicado el multiplicador de complejidad.
# Garantía estructural: COVERAGE * complejidad nunca supera esto, así el plan de lectura
# no puede desbordar por diseño el presupuesto del nodo.
MIA_RETRIEVAL_MAX_COVERAGE_FRACTION = float(
    os.getenv("MIA_RETRIEVAL_MAX_COVERAGE_FRACTION", "0.80"))
# Piso histórico: lo que Mia leía ANTES de la lectura adaptativa. Nunca se pide menos.
MIA_RETRIEVAL_MIN_TOP_K = int(os.getenv("MIA_RETRIEVAL_MIN_TOP_K", "8"))
# Riel de seguridad (no es el límite principal: el límite principal es el presupuesto).
# Acota el coste por turno — los mismos fragmentos entran a varios nodos del grafo.
#
# DECISIÓN DEL DUEÑO (2026-07-20). Medido con los defaults reales, un techo de 160
# multiplicaba el gasto de IA por turno entre 11 y 20 veces frente al literal de 8 que
# había antes. Se le presentaron los números y respondió que la forma correcta no es
# elegir un techo, sino que el modelo PIDA más material cuando le falte —como hacen las
# herramientas agénticas de código—, porque así una pregunta trivial cuesta poco y una
# difícil lee lo que necesite, sin que nadie adivine un número. Tiene razón: ver la nota
# de "lectura agéntica" en HANDOFF.md, que es el rediseño pendiente.
# El recorte de gasto se aplicó en MIA_RETRIEVAL_COVERAGE_FRACTION, no aquí: este riel se
# deja holgado a propósito para que siga siendo lo que dice ser —una red de seguridad— y no
# el límite operativo. Un riel que muerde en todos los casos aplasta la adaptabilidad.
MIA_RETRIEVAL_MAX_TOP_K = int(os.getenv("MIA_RETRIEVAL_MAX_TOP_K", "128"))
# ── PISO DE COBERTURA POR PIEZA (sesión 53) ──────────────────────────────────
# El defecto que corrige, medido en el piloto con expediente real: Mia leyó 128 de 574
# fragmentos y NO vio las fechas que necesitaba para sostener la prescripción. No fue un
# fallo del ranking sino su consecuencia natural: un ranking global concentra la lectura
# en las piezas que más se parecen a la pregunta, y una pieza ENTERA puede quedar en cero
# — precisamente la que guarda el dato que nadie pensó en preguntar. `max_per_document`
# evita que UNA pieza acapare; nada garantizaba que las demás aparecieran.
#
# Regla: ninguna pieza del expediente se queda sin leer si hay sitio. Los fragmentos de
# cobertura salen del MISMO presupuesto (se recorta la cola de la lista principal): esto
# reparte la lectura, no la agranda — ni un token ni un dólar de más por turno.
#
# Determinista y sin modelo: una consulta por pieza huérfana, con el vector del turno. No
# necesita herramientas, así que funciona BAJO SUSCRIPCIÓN, que es donde la lectura
# agéntica no puede correr (ese fue el hallazgo que dejó N-2 sin decidir).
MIA_RETRIEVAL_DOC_FLOOR = int(os.getenv("MIA_RETRIEVAL_DOC_FLOOR", "2"))
# Cuánto del top_k puede dedicarse, como máximo, a cubrir piezas huérfanas. El resto
# sigue siendo del ranking: la cobertura no puede comerse la relevancia.
MIA_RETRIEVAL_COVERAGE_RESERVE_FRACTION = float(
    os.getenv("MIA_RETRIEVAL_COVERAGE_RESERVE_FRACTION", "0.25"))
# Por debajo de esta fracción del expediente leída, el turno DECLARA su alcance al abogado.
# Ninguna técnica de recuperación garantiza haber visto un dato puntual —para eso habría que
# leerlo todo, y no cabe en la ventana—, así que el límite se dice en vez de esconderse: es
# la misma disciplina del muro de citas aplicada a la lectura. 0.95 y no 1.0 porque llegar al
# último fragmento por dedup o por tope por pieza no es leer de menos.
MIA_ALCANCE_AVISO_UMBRAL = float(os.getenv("MIA_ALCANCE_AVISO_UMBRAL", "0.95"))
# Se piden más filas de las que se van a entregar porque el dedup y el tope por documento
# descartan algunas: sin este colchón, "leer 100" acababa entregando 70.
MIA_RETRIEVAL_OVERFETCH = float(os.getenv("MIA_RETRIEVAL_OVERFETCH", "1.5"))
# Candidatos por lista (vector y full-text) antes de fusionar con RRF, como múltiplo de
# lo que se va a entregar. Más candidatos = mejor fusión, más trabajo en la base.
MIA_RETRIEVAL_CANDIDATE_MULTIPLIER = float(
    os.getenv("MIA_RETRIEVAL_CANDIDATE_MULTIPLIER", "3.0"))
MIA_RETRIEVAL_MIN_CANDIDATES = int(os.getenv("MIA_RETRIEVAL_MIN_CANDIDATES", "20"))
MIA_RETRIEVAL_MAX_CANDIDATES = int(os.getenv("MIA_RETRIEVAL_MAX_CANDIDATES", "600"))
# Cuánto del total entregado puede salir de UN mismo documento (0 < f <= 1). Evita que
# los N fragmentos sean todos de la misma pieza habiendo varias relevantes.
MIA_RETRIEVAL_MAX_PER_DOCUMENT_FRACTION = float(
    os.getenv("MIA_RETRIEVAL_MAX_PER_DOCUMENT_FRACTION", "0.5"))
# Solape con el que la ingesta corta los fragmentos (ingest: size=1200, overlap=150).
# El dedup lo usa para recortar la repetición literal entre fragmentos contiguos.
MIA_RETRIEVAL_OVERLAP_CHARS = int(os.getenv("MIA_RETRIEVAL_OVERLAP_CHARS", "150"))
# Similitud (Jaccard sobre n-gramas de palabras) a partir de la cual dos fragmentos se
# consideran el mismo material y solo sobrevive el mejor rankeado.
MIA_RETRIEVAL_DEDUP_SIMILARITY = float(
    os.getenv("MIA_RETRIEVAL_DEDUP_SIMILARITY", "0.85"))
# Vecinos contiguos por fragmento recuperado (ord-r .. ord+r). 0 = apagado (default):
# la función existe y está probada, pero se enciende por instalación tras medirla.
MIA_RETRIEVAL_NEIGHBOR_RADIUS = int(os.getenv("MIA_RETRIEVAL_NEIGHBOR_RADIUS", "0"))
# Notas del despacho: tope al escalado por complejidad. La sección tiene además su
# propio presupuesto DURO (KNOWLEDGE_BUDGET_FRACTION) que este número no puede violar.
MIA_KNOWLEDGE_MIN_TOP_K = int(os.getenv("MIA_KNOWLEDGE_MIN_TOP_K", "4"))
MIA_KNOWLEDGE_MAX_TOP_K = int(os.getenv("MIA_KNOWLEDGE_MAX_TOP_K", "10"))


def _env_flag(name: str, default: str = "0") -> bool:
    """Bandera booleana de .env, tolerante con la forma en que la escriba un humano."""
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on", "si", "sí")


# --- Lectura AGÉNTICA del expediente (opt-in · APAGADA por defecto) --------------
# Todo lo de arriba ADIVINA cuánto leer ANTES de leer: deriva un número de tres señales
# y lo pide de una vez. Funciona, pero obliga a fijar una proporción (COVERAGE) que es un
# compromiso entre la pregunta trivial (paga de más) y la difícil (lee de menos).
#
# DECISIÓN DEL DUEÑO (2026-07-20): "no se puede establecer como funciona Claude code o
# codex? al fin y al cabo su motor sera uno de ellos". Esas herramientas no adivinan:
# exponen la búsqueda como HERRAMIENTA y el modelo la invoca hasta tener lo suficiente.
# Así la pregunta fácil cuesta poco porque el modelo no pide más, y la difícil lee lo que
# necesite — el coste se ajusta solo y nadie fija una proporción.
#
# APAGADA POR DEFECTO y sin excepción: es código nuevo en el corazón del turno. Con la
# bandera en 0 el turno es EXACTAMENTE el de hoy — `intake_node` ni siquiera construye el
# bucle (una sola guarda `if config.MIA_AGENTIC_READING:` en el punto de llamada).
MIA_AGENTIC_READING = _env_flag("MIA_AGENTIC_READING")
# Tope duro de AMPLIACIONES por turno (rondas en las que el modelo pide más material).
# La primera lectura NO cuenta: sigue siendo la de `plan_reading` (arrancar con las manos
# vacías desperdicia un turno entero en pedir lo que ya sabemos que hace falta).
# 0 desactiva el bucle aunque la bandera esté encendida.
#
# ESTE NÚMERO Y `MAX_TOP_K` FIJAN EL TECHO DE LECTURA DEL CAMINO AGÉNTICO:
#     SEED_TOP_K + MAX_EXPANSIONS × MAX_TOP_K
# y ese techo TIENE que alcanzar `MIA_RETRIEVAL_MAX_TOP_K`, que es todo lo que el camino
# clásico puede llegar a leer. Si se queda corto, encender la bandera deja de cambiar
# CUÁNDO se lee y pasa a recortar cuánto se PUEDE llegar a leer: en un asunto grande eso
# no es ahorro, es ver menos expediente. Con 8 + 4 × 30 = 128 = MIA_RETRIEVAL_MAX_TOP_K
# los dos caminos alcanzan el mismo material y la única diferencia vuelve a ser el CUÁNDO.
# El gate `e7` de test_lectura_agentica custodia la relación y se pone rojo si alguien baja
# cualquiera de los tres números (o si sube el riel clásico sin subir estos).
#
# POR QUÉ 4 RONDAS DE 30 Y NO 10 DE 12, que darían el mismo techo aritmético: en cada ronda
# se reenvía la conversación ENTERA, así que el coste del bucle crece con el CUADRADO de las
# rondas. Con 10×12 el presupuesto del bucle lo corta antes de llegar al techo, que pasa a
# existir solo en la multiplicación — comprobado poniéndolo a propósito: `e7` se pone rojo.
# Pocas rondas grandes llegan al mismo material por mucho menos. La cifra exacta del peor
# caso con estos valores la imprime la sección E del gate en cada corrida; no se copia aquí
# para que no envejezca.
MIA_AGENTIC_READING_MAX_EXPANSIONS = int(
    os.getenv("MIA_AGENTIC_READING_MAX_EXPANSIONS", "4"))
# Presupuesto del BUCLE, como fracción del presupuesto del nodo consumidor. Es el techo de
# la conversación de lectura, contando lo que de verdad se envía: en CADA ronda se reenvía
# el historial completo, y eso es lo que se acumula contra este número (ver `agentic_expand`
# — contar solo el material nuevo dejaba el presupuesto acotando una cifra que no era la
# que se pagaba). Al agotarse se sigue con lo que haya: el bucle se corta, el turno JAMÁS
# se cae.
MIA_AGENTIC_READING_BUDGET_FRACTION = float(
    os.getenv("MIA_AGENTIC_READING_BUDGET_FRACTION", "0.50"))
# Tope de fragmentos que puede traer UNA ampliación (el modelo propone, esto acota). Es el
# otro factor del techo: ver la nota de MIA_AGENTIC_READING_MAX_EXPANSIONS. No es lo que se
# pide por defecto — eso es DEFAULT_TOP_K, que sigue en 8.
MIA_AGENTIC_READING_MAX_TOP_K = int(os.getenv("MIA_AGENTIC_READING_MAX_TOP_K", "30"))
# Cuántos pedir cuando el modelo no dice cuántos.
MIA_AGENTIC_READING_DEFAULT_TOP_K = int(
    os.getenv("MIA_AGENTIC_READING_DEFAULT_TOP_K", "8"))
# ARRANQUE CORTO · con la bandera ENCENDIDA la primera lectura deja de derivarse del
# presupuesto y arranca cerca del piso histórico; las AMPLIACIONES hacen el resto.
#
# Es la pieza SIN LA CUAL el bucle sería solo coste añadido: sin ella la pregunta fácil
# leía el plan adaptativo COMPLETO y encima pagaba la llamada del bucle para oír
# "suficiente" — lo peor de los dos mundos. Con ella, la fácil lee el piso y no paga
# ampliaciones; la difícil arranca igual de corta y sube pidiendo.
# CUIDADO con leer esto como "ahorro" a secas: el ahorro solo se materializa cuando el
# modelo se da por satisfecho pronto. Si amplía en todas las rondas, el turno acaba
# leyendo el techo (128) y cuesta MÁS que la lectura clásica de esa misma pregunta —
# porque leyó más material, no porque desperdicie. Las dos cifras, la buena y la mala,
# están medidas en test_lectura_agentica, sección E, y se recalculan al correr el gate.
# Nunca puede quedar por encima de lo que habría leído el plan adaptativo (se acota con
# él en `plan_reading`) ni por debajo del piso `MIA_RETRIEVAL_MIN_TOP_K`.
MIA_AGENTIC_READING_SEED_TOP_K = int(
    os.getenv("MIA_AGENTIC_READING_SEED_TOP_K", str(MIA_RETRIEVAL_MIN_TOP_K)))
# `task` con el que se llama al modelo del bucle (elige la CADENA de proveedores en
# agent/llm.py). Se deja configurable y no cableado porque el coste del bucle depende de
# esto: una instalación puede apuntarlo a una tarea auxiliar barata sin tocar código. Un
# task desconocido cae a la cadena de 'main' (resolve_fallback_chain), nunca falla.
# MEDIDO, no supuesto: en la política 'suscripcion' (la de por defecto) la cadena empieza
# por un alias `cli-*`, y `llm._invoke` DESCARTA las herramientas en esos aliases. El
# modelo nunca ve la herramienta, no puede pedir nada y el bucle no amplía jamás.
# Eso ya NO degrada en silencio: `retrieval.agentic_reading_available()` lo detecta ANTES
# de gastar la llamada y el turno se va por el camino clásico entero (lectura adaptativa
# de siempre + cero llamadas del bucle). Ver esa función.
MIA_AGENTIC_READING_TASK = os.getenv("MIA_AGENTIC_READING_TASK", "main").strip() or "main"
# VISTA COMPACTA de rondas viejas · la otra mitad del coste del bucle, aparte del techo de
# lectura. Cada ronda reenvía la conversación ENTERA (ver `agentic_expand`), y lo que más
# pesa de eso es el material YA LEÍDO de rondas anteriores — que el modelo YA EVALUÓ una
# vez y ya decidió que no le alcanzaba. Volver a mandárselo completo en la ronda 3, 4... no
# le da información nueva: solo cobra otra vez el mismo texto. A partir de la ronda en que
# un fragmento deja de ser NUEVO se resume a archivo · folio · estas primeras palabras —
# sigue sellado (`<<<DOC n>>>`), solo más corto. La ronda 1 (la semilla de `plan_reading`)
# NUNCA se compacta: es lo primero que el modelo lee y sostiene toda la decisión inicial.
# 0 apaga la compactación (cada ronda vuelve a ir completa, el comportamiento de antes de
# medir esto). MEDIDO en test_lectura_agentica, sección H (h4): con el peor caso de la
# sección E (el modelo pide MAX_TOP_K en las 4 rondas) el ahorro ronda a ronda crece con
# el tamaño real de los fragmentos —con los fragmentos CORTOS de la propia suite (pensados
# para que corra rápido) es modesto; con el largo PROMEDIO del corpus de calibración
# (`avg_chars` en `STATS`, 1199 caracteres) la ronda 3 baja cerca de un tercio, y en ese
# escenario la vista compacta es la diferencia entre que el presupuesto corte el bucle a
# medio camino (menos fragmentos que el techo) o que complete las 4 rondas y alcance el
# mismo techo que el camino clásico. Las cifras exactas las imprime la sección H en cada
# corrida — no se copian aquí para que no envejezcan.
MIA_AGENTIC_READING_COMPACT_WORDS = int(
    os.getenv("MIA_AGENTIC_READING_COMPACT_WORDS", "30"))

# ── CUÁNDO ENCENDER `MIA_AGENTIC_READING`, en llano ──────────────────────────────
# QUÉ CAMBIA DE VERDAD, sin titular bonito. Encendida, la primera lectura arranca en el
# piso y el modelo pide el resto. Eso NO es un ahorro garantizado: es un ahorro
# CONDICIONADO a que el modelo se dé por satisfecho pronto.
#   · Modelo que dice "suficiente" de entrada (pregunta puntual): MEDIDO 4,3 veces más
#     barato que leer de golpe el plan adaptativo.
#   · Modelo que amplía en TODAS las rondas (el peor caso): MEDIDO 3,6 veces más CARO que
#     la lectura clásica de esa misma pregunta puntual (con la vista compacta puesta; sin
#     ella era 3,7). No es desperdicio — acabó leyendo 128 fragmentos donde la clásica
#     leía 55 — pero se paga.
#   · El TECHO es el mismo por los dos caminos (128 fragmentos): la bandera nunca recorta
#     cuánto expediente puede llegar a ver Mia, solo cambia CUÁNDO lo pide.
# Las tres cifras salen de la sección E de execution/test_lectura_agentica.py y se
# recalculan solas al correr el gate; si alguien mueve los topes, cambian.
#
# ENCENDERLA conviene cuando se cumplen las TRES:
#   1. El motor del despacho admite herramientas. Hoy: políticas 'nube', 'openrouter' o
#      'soberano' con un modelo que hable tool-calling — o `MIA_AGENTIC_READING_TASK`
#      apuntado a una tarea cuya cadena NO empiece por un alias `cli-*`. Con la política
#      'suscripcion' tal cual, encenderla no hace nada: el propio sistema lo detecta y
#      sigue por el camino clásico sin cobrar de más, pero tampoco se gana nada.
#   2. Los asuntos son GRANDES (cientos de fragmentos) Y la mayoría de preguntas del día
#      a día NO necesita el expediente entero. Ahí el plan adaptativo lee mucho en CADA
#      turno y el arranque corto se lo ahorra. En un asunto de 20 fragmentos el plan ya
#      lee poco y el bucle solo añade una llamada. Y ojo con la otra mitad de la
#      condición: si en un asunto grande casi toda pregunta acaba necesitándolo todo, la
#      bandera no ahorra nada — paga rondas de conversación para llegar al mismo sitio.
#   3. La mezcla de preguntas del despacho es desigual: muchas puntuales ("qué fecha
#      tiene el auto") y algunas de análisis. El bucle cobra la llamada extra en TODAS
#      para ahorrar lectura en las puntuales; si todas las preguntas son de análisis
#      profundo, el balance se estrecha.
# DEJARLA APAGADA cuando: el motor es la suscripción por CLI; los asuntos son pequeños;
# se quiere el comportamiento exacto y auditado de hoy (apagada, el turno es byte por
# byte el de siempre); o no se ha medido nada todavía. Es el default y no hay prisa.
# CÓMO SABER SI VALIÓ LA PENA: la traza `agentic_reading` de cada turno lleva ampliaciones
# pedidas, fragmentos nuevos y motivo del corte. Si el corte es casi siempre 'suficiente'
# con 0 ampliaciones, el despacho está pagando una llamada por turno para leer el piso:
# eso puede ser justo lo que se quiere (ahorro) o señal de que el arranque es demasiado
# corto para sus asuntos — súbase `MIA_AGENTIC_READING_SEED_TOP_K` antes que apagarla.

# Política de modelo POR DEFECTO. `quality_adaptive` está disponible y recomendado en la
# activación para el razonamiento jurídico complejo; "suscripcion" se conserva como default
# operativo para no cambiar costo ni latencia a tenants existentes. Valores: "suscripcion" (CLI de
# Claude Code del abogado, sin billing por API) · "nube" (API Anthropic vía proxy) ·
# "soberano" (todo local en Ollama) · "openrouter" (CP-OR: la propia cuenta de OpenRouter
# del abogado como motor principal, con su clave/crédito; exige OPENROUTER_API_KEY). El
# default aplica cuando el tenant no configuró `tenant_settings.config['model_policy']`;
# agent/llm.py la resuelve por request/job.
MIA_MODEL_POLICY = os.getenv("MIA_MODEL_POLICY", "suscripcion").strip().lower()
# Modelo que el CLI de la suscripción usa por defecto cuando la tarea no trae hint.
# "sonnet": calidad alta y mucho más rápido escribiendo documentos extensos que el
# modelo grande default del plan (medido 2026-07-01: el default excedió los 300s en un
# borrador legal completo; sonnet lo produce en ~1-2 min). Aliases: sonnet/opus/haiku.
MIA_CLI_MODEL = os.getenv("MIA_CLI_MODEL", "sonnet").strip().lower()

# --- Memoria del agente en ejecución (Módulo 5) ---
# $MIA_HOME: carpeta donde vive la identidad por despacho (SOUL.md por tenant) y otra
# memoria en ejecución del agente. Es estado de INSTANCIA por despacho (como las API
# keys), no se commitea: default bajo mia-data/ (gitignored). Configurable por entorno
# (.env trae MIA_HOME=.\mia-data). Una ruta RELATIVA se ancla a PROJECT_ROOT para no
# depender del directorio de trabajo (igual criterio que mia-data/traces de 2d). Se lee
# como atributo en cada uso, así los tests pueden apuntarlo a un tempdir reasignando
# config.MIA_HOME.
MIA_HOME = Path(os.getenv("MIA_HOME", "mia-data"))
if not MIA_HOME.is_absolute():
    MIA_HOME = (PROJECT_ROOT / MIA_HOME).resolve()

# --- Conectores de calendario y correo (CP-P3, Ola 2) ---
# Llaves de la APP OAuth de cada proveedor. Son de la INSTALACIÓN (una app registrada
# por despliegue de Mia en Azure AD / Google Cloud), no de un despacho: cada abogado
# CONSIENTE y obtiene su propio token (ese sí por-tenant, en tenant_oauth_tokens). Sin
# estas llaves, el conector del proveedor simplemente no se ofrece (degradación con
# gracia). El client_secret es un secreto de instalación → va en .env, nunca al git.
MS_OAUTH_CLIENT_ID = os.getenv("MS_OAUTH_CLIENT_ID", "")
MS_OAUTH_CLIENT_SECRET = os.getenv("MS_OAUTH_CLIENT_SECRET", "")
GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
# URL de callback donde el proveedor devuelve el `code` de consentimiento. Debe
# coincidir EXACTA con la registrada en Azure/Google. Default: backend local (Modo B).
MAILBOX_OAUTH_REDIRECT_URI = os.getenv(
    "MAILBOX_OAUTH_REDIRECT_URI", "http://localhost:8000/api/mailbox/oauth/callback")


def mailbox_oauth_client(provider: str) -> tuple[str, str]:
    """(client_id, client_secret) de la app OAuth del proveedor, o ('','') si no hay."""
    if provider == "microsoft":
        return MS_OAUTH_CLIENT_ID, MS_OAUTH_CLIENT_SECRET
    if provider == "google":
        return GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET
    return "", ""


def validate_runtime_config() -> None:
    """Falla al arrancar si faltan secretos críticos (evita JWT vacío en producción)."""
    if not JWT_SECRET or len(JWT_SECRET) < 32:
        raise RuntimeError(
            "JWT_SECRET debe estar definido en .env y tener al menos 32 caracteres."
        )
    if IS_PRODUCTION and any(o == "*" for o in CORS_ORIGINS):
        raise RuntimeError(
            "MIA_CORS_ORIGINS no puede ser '*' en producción: las respuestas del "
            "API llevan credenciales. Lista los dominios exactos del frontend."
        )


def obsidian_vault_allowlist() -> list[Path]:
    """Raíces permitidas para sync de Obsidian (evita lectura arbitraria del filesystem)."""
    raw = os.getenv("OBSIDIAN_VAULT_ALLOWLIST", "") or os.getenv("OBSIDIAN_VAULT_PATH", "")
    roots = [Path(p.strip()).resolve() for p in raw.split(";") if p.strip()]
    return roots


def resolve_obsidian_vault(vault_path: str) -> Path:
    """Resuelve y valida una ruta de vault contra el allowlist."""
    vault = Path(vault_path).expanduser().resolve()
    if not vault.is_dir():
        raise ValueError(f"La ruta del vault no existe o no es un directorio: {vault}")
    allowlist = obsidian_vault_allowlist()
    if not allowlist:
        raise ValueError(
            "OBSIDIAN_VAULT_PATH u OBSIDIAN_VAULT_ALLOWLIST debe estar configurado en .env"
        )
    for root in allowlist:
        try:
            vault.relative_to(root)
            return vault
        except ValueError:
            continue
    raise ValueError("La ruta del vault no está dentro de las carpetas permitidas.")


def litellm_embed_model() -> str:
    """Nombre del modelo de embeddings con prefijo de proveedor para LiteLLM."""
    return EMBED_MODEL if "/" in EMBED_MODEL else f"voyage/{EMBED_MODEL}"
