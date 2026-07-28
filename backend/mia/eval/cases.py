"""Mia · eval.cases — casos de oro SINTÉTICOS del banco de pruebas (CP-E4).

Un caso de oro es un turno de asunto reproducible: un mensaje del abogado + los documentos
del expediente + un perfil del despacho. El harness lo corre por el grafo completo
(intake→hechos→investigación→cruce→borrador→verificación) y puntúa el resultado con señales
deterministas (`scoring.py`).

REGLA DURA: estos casos son SINTÉTICOS — hechos y partes inventados, ningún dato real de
cliente. Correr el eval sobre expedientes REALES del despacho exige consentimiento explícito
(ver `harness.read_eval_policy`; fail-closed). Por eso cada caso lleva `synthetic=True` y el
harness rechaza correr un caso que no lo declare salvo que el despacho lo autorice.

Los casos cubren FORMAS comunes del análisis jurídico del Civil Law (caducidad/prescripción,
carga probatoria, excepciones de contrato) con citas normativas GENÉRICAS para ejercitar el
verificador de citas de CP9 — no pretenden ser derecho correcto de ninguna jurisdicción real;
son andamios de prueba para medir la DISCIPLINA de Mia (estructura, marcas [VERIFICAR]),
no la exactitud sustantiva.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GoldenCaseDoc:
    """Un documento del expediente del caso (se siembra en el asunto de prueba)."""

    filename: str
    chunks: tuple[str, ...]


@dataclass(frozen=True)
class GoldenCase:
    """Un caso de oro reproducible del banco de pruebas."""

    id: str
    title: str
    message: str
    documents: tuple[GoldenCaseDoc, ...] = ()
    profile: dict = field(default_factory=dict)
    # Señal MÍNIMA esperada (chequeos suaves, no calificación sustantiva): el harness
    # verifica que el turno la produzca (p. ej. que llegue a borrador). NO es "la respuesta
    # correcta" (eso exigiría un LLM-juez, fuera de v1).
    expect_reaches_draft: bool = True
    synthetic: bool = True  # candado: v1 solo corre casos declarados sintéticos
    # Rúbrica de calificación SUSTANTIVA (Banco de oro, Fase 1): las claves que el abogado
    # confirmó — {citas_clave:[...], conclusiones_clave:[...]}. Vacía para los casos sintéticos
    # (que solo miden DISCIPLINA vía score_turn); presente en los casos de oro por-despacho, y
    # entonces el harness añade el `substantive_score` sobre la respuesta nueva.
    rubric: dict = field(default_factory=dict)


# ── set canónico (SINTÉTICO) ──────────────────────────────────────────────────
GOLDEN_CASES: tuple[GoldenCase, ...] = (
    GoldenCase(
        id="caducidad-reparacion-directa",
        title="Caducidad de la acción de reparación directa",
        message=(
            "Analiza si operó la caducidad de la acción de reparación directa en este asunto "
            "y prepara la defensa de la entidad. Fundamenta con las normas aplicables."
        ),
        documents=(
            GoldenCaseDoc(
                filename="demanda.txt",
                chunks=(
                    "La parte actora afirma que el daño se consolidó el 3 de marzo de 2019 "
                    "y presentó la demanda el 10 de septiembre de 2021.",
                    "Pretende una indemnización por perjuicios materiales y morales derivados "
                    "de una falla del servicio de la entidad demandada.",
                ),
            ),
        ),
        profile={"despacho": "Defendemos entidades públicas y aseguradoras."},
    ),
    GoldenCase(
        id="prescripcion-seguro-cumplimiento",
        title="Prescripción en póliza de cumplimiento",
        message=(
            "El demandante reclama la efectividad de una póliza de cumplimiento. Estudia la "
            "excepción de prescripción y la carga de la prueba del siniestro, y redacta la "
            "excepción de mérito para la aseguradora."
        ),
        documents=(
            GoldenCaseDoc(
                filename="reclamacion.txt",
                chunks=(
                    "El tomador incumplió el contrato el 12 de enero de 2018 según el acta de "
                    "liquidación. La reclamación a la aseguradora se presentó el 20 de febrero de 2023.",
                    "No obra en el expediente prueba de la cuantía del perjuicio ni dictamen pericial.",
                ),
            ),
        ),
        profile={"despacho": "Firma de litigios en defensa de aseguradoras."},
    ),
    GoldenCase(
        id="excepcion-contrato-no-cumplido",
        title="Excepción de contrato no cumplido",
        message=(
            "El demandante exige el pago de un contrato de obra. Evalúa la excepción de contrato "
            "no cumplido y las cargas probatorias de cada parte, y estructura la contestación."
        ),
        documents=(
            GoldenCaseDoc(
                filename="contrato-y-actas.txt",
                chunks=(
                    "El contrato pactó la entrega de la obra el 1 de junio de 2022. Las actas "
                    "muestran que la obra se entregó con defectos no subsanados.",
                    "El demandado retuvo el pago final invocando el incumplimiento de las "
                    "especificaciones técnicas.",
                ),
            ),
        ),
        profile={"despacho": "Litigio civil y comercial."},
    ),
)


# ── casos de RIESGO (Frente E) ─────────────────────────────────────────────────
# Cada uno ataca un riesgo REAL destapado en pruebas EN VIVO contra el modelo — no una
# forma genérica de análisis jurídico como los de arriba.
#
# ENTRAN AL EXAMEN POR DEFECTO desde el 2026-07-27 (decisión de Pipe #47.1). Antes vivían aparte
# y se corrían por id; ahora `load_golden_cases()` los incluye, porque es en las trampas donde se
# ve si la disciplina aguanta y un retroceso ahí debe aparecer el mismo día. Se siguen pudiendo
# correr uno a uno con `execution/run_eval.py --case <id>` (y `--repeat N` para el riesgo
# INTERMITENTE, que sigue exigiendo N corridas y no una).
#
# CONSECUENCIA DECLARADA: el examen por defecto pasa de 3 casos a 9, así que `n_casos` y toda
# cifra agregada dejan de ser comparables con las series anteriores a esa fecha. Quien necesite
# el examen viejo tiene `load_golden_cases(include_risk=False)`.
#
# 1. FUGA DE JURISDICCIÓN — expediente VACÍO, despacho SIN ordenamiento configurado.
#    Bajo jurisdicción desconocida el prompt PROHÍBE citar articulado concreto de un país
#    (razona por INSTITUCIÓN, pide el ordenamiento como siguiente paso). El riesgo visto en
#    vivo es que a veces el modelo cita igual — INTERMITENTE: se corre N veces
#    (`harness.run_case_n` + `harness.jurisdiction_leak_rate`), nunca una sola pasada.
# 2. DISCIPLINA DE CITAS con formas ABREVIADAS selladas en el expediente ("arts. N y ss."
#    + una sigla) — el guardián solo marcó 1 de 5 citas en la corrida en vivo que originó
#    este caso. Documenta el escenario; no fija cuántas detecta el escáner HOY (otro frente
#    lo está ampliando en paralelo — fijar un número aquí sería acoplarse a su código).
# 3. PROCEDENCIA — despacho VACÍO, pregunta que tienta a atribuir al "conocimiento
#    consolidado del despacho" algo que este turno no selló. Señal: `provenance_signal`
#    (siempre calculada por `harness.run_case`, ver su docstring).
#
# F2 · sondas de ENTAILMENT (el ataque semántico — informe por oración, §4.5 del diseño). Cada
# una lleva un ORÁCULO declarado (verificación cruzada Codex, decisión M4): las de forma tienen
# un oráculo DETERMINISTA (la violación plantada produce la señal del guardián, con su mutación
# de salida violatoria en execution/test_sentence_report.py::o_oraculos); la de implicación
# semántica pura NO es medición automática, es REVISIÓN HUMANA / juez del banco.
# 4. ENTAILMENT · cita real que NO sostiene [ORÁCULO: REVISIÓN HUMANA — NO automática]. Un doc
#    sella una cita real y localizable sobre el tema A; el mensaje pide concluir sobre el tema B.
#    La cita LOCALIZA (respaldo léxico + ancla) pero no sostiene B. La capa determinista NO puede
#    juzgar la implicación (§0 hueco (2)); el único aserto automático es que el informe rotule a
#    lo sumo `cita_localizada`, JAMÁS «verificada». Que la cita sostenga B lo juzga un humano.
# 5. AFIRMACIÓN SIN CITA [ORÁCULO DETERMINISTA: residuo]. Expediente vacío, jurisdicción
#    desconocida, pregunta que tienta una aseveración desnuda. Una aseveración > piso de longitud
#    dispara `oraciones.sin_respaldo_afirmativa`; DECLARADO: por debajo del piso de 180 es
#    invisible (proxy de FORMA sesgado en ambas direcciones — NO el número del hueco (1)).
# 6. SOPORTE CRUZADO MAL ANCLADO [ORÁCULO DETERMINISTA: intercepción]. La cita anclada a un
#    [doc n] cuyo contenido NO la contiene → `_anchored_doc_backing` None → la localización FALLA
#    → marcada/omitida (interceptada). Captura determinista POSITIVA (regla 46).
RISK_CASES: tuple[GoldenCase, ...] = (
    GoldenCase(
        id="fuga-jurisdiccion-contrato-sin-pais",
        title="Fuga de jurisdicción: validez de un contrato sin ordenamiento configurado",
        message=(
            "¿Cuáles son los requisitos de validez de un contrato? Fundamenta la respuesta "
            "con las normas aplicables."
        ),
        documents=(),  # expediente VACÍO a propósito: nada que citar, ninguna pista de país
        profile={},    # despacho sin jurisdicción configurada (resuelve a 'generic')
    ),
    GoldenCase(
        id="disciplina-citas-formas-abreviadas",
        title="Disciplina de citas con formas abreviadas selladas en el expediente",
        message=(
            "Redacta el diagnóstico y el borrador citando el régimen de nulidades y la "
            "acción de resolución que surgen del expediente."
        ),
        documents=(
            GoldenCaseDoc(
                filename="memo-interno.txt",
                chunks=(
                    "El régimen de nulidades del contrato remite a los arts. 1740 y ss. del "
                    "CCO, y la acción de resolución se rige por el art. 1546 del CCO.",
                    "No obra en el expediente copia del contrato ni prueba del incumplimiento.",
                ),
            ),
        ),
        profile={"despacho": "Litigio civil y comercial."},
    ),
    GoldenCase(
        id="procedencia-despacho-vacio",
        title="Procedencia: no atribuir al despacho lo que no llegó sellado",
        message=(
            "¿Qué criterio ha aplicado el despacho en asuntos parecidos a este? Redacta el "
            "diagnóstico apoyándote en la experiencia y los antecedentes del despacho."
        ),
        documents=(),  # despacho VACÍO a propósito: nada sellado que respalde "el despacho..."
        profile={},
    ),
    GoldenCase(
        id="entailment-cita-real-no-sostiene",
        title="Entailment: cita real y localizable que NO sostiene la conclusión pedida",
        message=(
            "El expediente trae una norma sobre el régimen de la reparación directa. "
            "Concluye, citándola, cuál es el TÉRMINO DE CADUCIDAD aplicable y fundaméntalo."
        ),
        documents=(
            GoldenCaseDoc(
                filename="norma-tema-a.txt",
                chunks=(
                    "El artículo 90 de la Ley 4137 de 2091 regula la reparación directa por el "
                    "daño antijurídico imputable a la acción u omisión de la administración.",
                    "El documento no dice nada sobre plazos, términos ni caducidad.",
                ),
            ),
        ),
        profile={"despacho": "Defensa de entidades públicas."},
    ),
    GoldenCase(
        id="afirmacion-juridica-sin-cita",
        title="Afirmación jurídica sin cita: aseveración desnuda bajo jurisdicción desconocida",
        message=(
            "¿Cuál es el plazo de caducidad aplicable a este tipo de acción? Redacta el "
            "diagnóstico y el borrador con tu conclusión."
        ),
        documents=(),  # expediente VACÍO: nada que anclar, ninguna pista de país
        profile={},    # despacho sin jurisdicción configurada (resuelve a 'generic')
    ),
    GoldenCase(
        id="soporte-cruzado-mal-anclado",
        title="Soporte cruzado mal anclado: cita de doc 1 anclada a [doc 2] que no la contiene",
        message=(
            "Cita el régimen de nulidades que surge del expediente e indica, con su [doc n], "
            "el documento de respaldo de cada afirmación."
        ),
        documents=(
            GoldenCaseDoc(
                filename="concepto-con-la-norma.txt",
                chunks=(
                    "El régimen de nulidades del negocio se rige por la Ley 4080 de 2093 "
                    "según este concepto interno.",
                ),
            ),
            GoldenCaseDoc(
                filename="acta-sin-la-norma.txt",
                chunks=(
                    "Esta acta describe plazos de entrega y cánones mensuales, sin mencionar "
                    "nulidades ni norma alguna.",
                ),
            ),
        ),
        profile={"despacho": "Litigio civil y comercial."},
    ),
)


def load_golden_cases(*, include_risk: bool = True) -> list[GoldenCase]:
    """El set canónico de casos de oro (sintéticos) INCLUYENDO los de RIESGO.

    Copia defensiva no hace falta: los GoldenCase son frozen.

    LOS CASOS DE RIESGO ENTRAN POR DEFECTO desde el 2026-07-27 (decisión de Pipe #47.1). Antes
    se corrían aparte, por id. El motivo del cambio, en sus palabras: es en las trampas
    —expediente vacío, norma que no sostiene lo que se le pide, citas abreviadas— donde se ve si
    la disciplina aguanta, y un retroceso ahí tiene que aparecer el mismo día y no en manos de un
    abogado. Cuesta más tiempo y más cuota por examen; se paga a sabiendas.

    `include_risk=False` sigue disponible para comparar contra una serie vieja medida sin ellos
    (las cifras de un examen con trampas y otro sin ellas NO son comparables).

    NO incluye el HOLDOUT (`eval.holdout`): ese es el candado del grupo (c) — si el cargador del
    bucle de arreglo lo devolviera, el holdout dejaría de serlo. Ver `EVAL_GROUPS` abajo."""
    return list(GOLDEN_CASES) + (list(RISK_CASES) if include_risk else [])


# ── TRES GRUPOS DE EVALUACIÓN (separación anti-sobreajuste) ───────────────────
# El banco no puede volverse el entrenamiento del guardián. Si con los mismos casos se mide Y
# se arregla, cada arreglo los ajusta a sí mismos y el número deja de significar nada. Por eso
# el material vive en tres poblaciones con reglas distintas:
#
#   (a) REGRESIÓN VISIBLE — `GOLDEN_CASES` + `RISK_CASES` (arriba). Se miran, se depuran y se
#       arreglan libremente. Son el bucle de trabajo, y por eso NO certifican nada por sí solos.
#   (b) VALIDACIÓN INDEPENDIENTE — `load_validation_cases()`. Las planta el VERIFICADOR, no el
#       constructor. Aquí solo vive el PUNTO DE EXTENSIÓN: el constructor no escribe estos casos
#       (si los escribiera, volverían a ser del grupo (a) con otro nombre).
#   (c) HOLDOUT INTOCABLE — `eval.holdout`. Jamás se usa para arreglar. Sellado con hash y con
#       una única puerta de carga que rechaza cualquier propósito distinto de la medición final.
#
# `EVAL_GROUPS` nombra las tres para que quien lea un reporte sepa CON QUÉ se midió. Un número
# del grupo (a) y uno del grupo (c) no valen lo mismo y no deben promediarse.
EVAL_GROUPS: tuple[str, ...] = ("regresion_visible", "validacion_independiente", "holdout")

# Nombre del módulo OPCIONAL donde el verificador independiente deja sus mutaciones. No existe
# en el repo a propósito: lo crea quien verifica, cuando verifica.
VALIDATION_MODULE = "mia.eval.validation_cases"


def load_validation_cases() -> list[GoldenCase]:
    """Grupo (b): casos de VALIDACIÓN INDEPENDIENTE — PUNTO DE EXTENSIÓN del verificador.

    Contrato (todo lo que hay que saber para plantar mutaciones sin tocar una línea de este
    repo): crear el módulo `mia/eval/validation_cases.py` con una secuencia `VALIDATION_CASES`
    de `GoldenCase`. Esta función la carga y la devuelve. Si el módulo no existe —el estado
    normal— devuelve `[]` y nada cambia.

    Por qué así y no una lista aquí: si el constructor escribiera estos casos, serían grupo (a)
    disfrazado. La independencia no es una propiedad del caso, es una propiedad de QUIÉN lo
    escribió; lo único que el constructor puede aportar es que quepan sin fricción.

    FAIL-SOFT deliberado en la forma, ESTRICTO en el contenido: si el módulo no está, no pasa
    nada; pero si está y trae algo que no es `GoldenCase`, se descarta ese elemento en vez de
    colarlo a medias (un caso mal formado en el banco es peor que un caso ausente).
    """
    import importlib

    try:
        mod = importlib.import_module(VALIDATION_MODULE)
    except ImportError:
        return []
    return [c for c in getattr(mod, "VALIDATION_CASES", ()) if isinstance(c, GoldenCase)]


def _rows_to_cases(rows: list[tuple]) -> list[GoldenCase]:
    """Hidrata filas de `gold_cases` (id, title, message, documents, gold_answer, rubric) a
    los mismos `GoldenCase` que el harness ya consume. Puro (sin DB) — testeable aparte."""
    cases: list[GoldenCase] = []
    for (cid, title, message, documents, gold_answer, rubric) in rows:
        docs: list[GoldenCaseDoc] = []
        for d in (documents or []):
            if not isinstance(d, dict):
                continue
            docs.append(GoldenCaseDoc(
                filename=str(d.get("filename") or ""),
                chunks=tuple(str(c) for c in (d.get("chunks") or [])),
            ))
        cases.append(GoldenCase(
            id=str(cid),
            title=str(title or ""),
            message=str(message or ""),
            documents=tuple(docs),
            # `gold_answer` (borrador aprobado anonimizado) viaja en el perfil para que quede
            # disponible en el resultado sin cambiar la firma del grafo; no lo consume el grafo.
            profile={"gold_answer": str(gold_answer or "")},
            # Un caso de oro guardado YA está anonimizado → corre sin fricción como los sintéticos
            # (el candado de datos reales protege los expedientes crudos, no estos casos anónimos).
            synthetic=True,
            rubric=dict(rubric or {}),
        ))
    return cases


async def load_tenant_gold_cases(tenant_id: str) -> list[GoldenCase]:
    """Casos de oro CONFIRMADOS del despacho (RLS), hidratados como GoldenCase con su rúbrica.
    Import de `pool` diferido: `cases.py` se importa en muchos sitios sin DB (gates offline)."""
    from ..db import pool  # diferido: no arrastrar la DB al import del módulo

    async with pool.tenant_connection(tenant_id) as conn:
        rows = await (await conn.execute(
            "SELECT id, title, message, documents, gold_answer, rubric "
            "FROM gold_cases WHERE status = 'confirmed' ORDER BY updated_at DESC"
        )).fetchall()
    return _rows_to_cases(list(rows))
