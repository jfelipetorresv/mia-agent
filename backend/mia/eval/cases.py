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


def load_golden_cases() -> list[GoldenCase]:
    """El set canónico de casos de oro (sintéticos). Copia defensiva no hace falta:
    los GoldenCase son frozen."""
    return list(GOLDEN_CASES)
