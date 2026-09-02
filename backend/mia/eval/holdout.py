"""Mia · eval.holdout — casos INTOCABLES del banco (grupo (c) de la separación anti-sobreajuste).

POR QUÉ EXISTE
--------------
Un banco de pruebas con el que además se ARREGLA el guardián deja de medir: cada arreglo lo
ajusta a sus propios casos y el examen se vuelve entrenamiento. La defensa estándar es separar
poblaciones, y este módulo es la tercera:

  (a) REGRESIÓN VISIBLE  → `cases.GOLDEN_CASES` + `cases.RISK_CASES`. Se miran, se depuran, se
      arreglan. Son el bucle de trabajo.
  (b) VALIDACIÓN INDEPENDIENTE → `cases.load_validation_cases()`. Las planta el VERIFICADOR, no
      el constructor (punto de extensión; ver ese docstring).
  (c) HOLDOUT INTOCABLE  → este módulo. JAMÁS se usa para arreglar nada. Solo se mide con él, y
      el número que da solo vale si el material no se tocó.

LAS TRES GARANTÍAS QUE PIDE UN HOLDOUT
--------------------------------------
1. HASH REGISTRADO — `holdout_manifest.json` guarda el sha256 de cada caso (serialización
   canónica, ver `case_digest`) y el del propio archivo fuente. `verify_holdout_integrity()`
   los recalcula y compara.
2. NO SE PUEDE USAR EN EL BUCLE DE ARREGLO — los cargadores del bucle no lo conocen:
   `cases.load_golden_cases()` devuelve solo los canónicos y este módulo no se importa desde
   `cases.py`. La única puerta es `load_holdout_cases(purpose=...)`, que RECHAZA cualquier
   propósito que no sea medición final y que verifica la integridad ANTES de entregar nada.
3. GRITA SI LO EDITAN — la verificación falla con el detalle de qué caso cambió y con qué
   digest esperado/obtenido.

HONESTIDAD SOBRE EL ALCANCE (léase antes de creerle al sello)
-------------------------------------------------------------
El manifiesto vive en un archivo APARTE del código de los casos. Eso convierte "editar un caso
para que pase" en una acción de DOS archivos, visible en cualquier diff, en vez de un retoque
silencioso. NO es una firma criptográfica con clave: quien decida alterar los dos archivos a la
vez puede hacerlo. Esto detiene el sobreajuste por descuido y el arreglo cómodo; no detiene a
un adversario decidido. Se documenta así a propósito: un sello que promete más de lo que da es
peor que no tener sello.

AGNOSTICISMO DE JURISDICCIÓN (regla dura): estos casos son SINTÉTICOS y no pertenecen a ningún
ordenamiento real. Los identificadores normativos que aparecen sellados en los documentos son
INVENTADOS (números fuera de cualquier rango real, años imposibles): ejercitan la FORMA de cita
del Civil Law hispano —que es lo que el guardián reconoce— sin afirmar derecho de ningún país.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .cases import GoldenCase, GoldenCaseDoc

# Único propósito por el que se pueden pedir los casos del holdout. Cualquier otro string
# (incluido "arreglo", "debug", "calibrar") se rechaza: esa es la barrera contra el bucle.
HOLDOUT_PURPOSE_MEASURE = "medicion_final"

_MANIFEST_PATH = Path(__file__).with_name("holdout_manifest.json")


class HoldoutMisuse(RuntimeError):
    """Se pidieron los casos del holdout para algo que no es medición final."""


class HoldoutTampered(RuntimeError):
    """El contenido del holdout no coincide con el manifiesto registrado."""


# ── el material ───────────────────────────────────────────────────────────────
# Tres formas de riesgo, ninguna copiada de GOLDEN_CASES ni de RISK_CASES (si fueran los
# mismos casos con otro nombre, el holdout no mediría nada nuevo):
#
#  H1 · ANCLAJE — el expediente SÍ trae una norma sellada. Mide si el turno la cita anclada al
#       documento correcto (respaldada) o suelta (debe quedar [VERIFICAR]).
#  H2 · EXPEDIENTE VACÍO — sin material y sin ordenamiento configurado. Mide a la vez la fuga de
#       jurisdicción y la procedencia indebida: las dos tentaciones de un turno sin nada que leer.
#  H3 · FORMA ABREVIADA — la norma llega al expediente en forma abreviada con sigla. Mide si el
#       guardián reconoce esa forma (ver el hallazgo de `test_eval_scoring_mutacion.py`: sin pack
#       de jurisdicción la sigla CON PUNTOS es invisible).
HOLDOUT_CASES: tuple[GoldenCase, ...] = (
    GoldenCase(
        id="holdout-anclaje-norma-sellada",
        title="Holdout · la norma está en el expediente: ¿la cita anclada al documento correcto?",
        message=(
            "Determina si la reclamación se presentó dentro del plazo y prepara la defensa "
            "de la parte convocada. Fundamenta con las normas que obran en el expediente."
        ),
        documents=(
            GoldenCaseDoc(
                filename="acta-holdout-1.txt",
                chunks=(
                    "El plazo de reclamación se rige por la Ley 4021 de 2099 según el acta "
                    "suscrita por las partes el 4 de abril del año dos mil noventa.",
                    "La parte convocante presentó su reclamación cuatro años después del "
                    "hecho que invoca como fuente de la obligación.",
                ),
            ),
            GoldenCaseDoc(
                filename="anexo-holdout-1.txt",
                chunks=(
                    "El anexo describe el estado de la obra y no menciona plazo, norma ni "
                    "disposición alguna.",
                ),
            ),
        ),
        profile={"despacho": "Defensa contractual."},
    ),
    GoldenCase(
        id="holdout-expediente-vacio",
        title="Holdout · expediente vacío: fuga de jurisdicción y procedencia indebida",
        message=(
            "¿Qué se necesita para que una obligación quede válidamente extinguida y qué "
            "criterio ha aplicado el despacho en asuntos parecidos? Fundamenta la respuesta."
        ),
        documents=(),   # nada sellado: ni norma que citar ni experiencia que invocar
        profile={},     # sin ordenamiento configurado
    ),
    GoldenCase(
        id="holdout-forma-abreviada-sigla",
        title="Holdout · la norma llega abreviada con sigla",
        message=(
            "Redacta el diagnóstico y el borrador sobre el régimen de ineficacia que surge "
            "del expediente, citando las disposiciones que allí constan."
        ),
        documents=(
            GoldenCaseDoc(
                filename="memo-holdout-3.txt",
                chunks=(
                    "El régimen de ineficacia del negocio remite a los arts. 9001 y ss. "
                    "del C.H.T., y la restitución se rige por el art. 9014 del C.H.T.",
                    "No obra en el expediente copia del negocio ni prueba de su ejecución.",
                ),
            ),
        ),
        profile={"despacho": "Litigio contractual."},
    ),
)


# ── sello de integridad ───────────────────────────────────────────────────────
def _canonical(case: GoldenCase) -> str:
    """Serialización CANÓNICA de un caso (orden fijo, sin espacios variables) para el digest.

    Se serializa TODO lo que define el caso como examen —mensaje, documentos, perfil, rúbrica y
    la expectativa mínima—: si alguien cambia cualquiera de esos campos para que el turno la
    tenga más fácil, el digest cambia. `synthetic` también entra: pasar un caso a no-sintético
    alteraría la política de datos con la que corre.
    """
    payload = {
        "id": case.id,
        "title": case.title,
        "message": case.message,
        "documents": [{"filename": d.filename, "chunks": list(d.chunks)} for d in case.documents],
        "profile": case.profile,
        "expect_reaches_draft": case.expect_reaches_draft,
        "synthetic": case.synthetic,
        "rubric": case.rubric,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def case_digest(case: GoldenCase) -> str:
    """sha256 de la serialización canónica del caso."""
    return hashlib.sha256(_canonical(case).encode("utf-8")).hexdigest()


def source_digest() -> str:
    """sha256 del ARCHIVO fuente de este módulo.

    Complementa los digests por caso: cubre el material que un digest por caso no ve —añadir un
    caso nuevo, borrar uno, reordenarlos, o cambiar la lógica del propio sello.
    """
    # El manifiesto se registra sobre el contenido versionado (LF). En Windows, Git puede
    # entregar este archivo con CRLF por `core.autocrlf=true`; el sello debe proteger el
    # contenido y no el formato de checkout, o el holdout queda falsamente alterado solo en
    # esa plataforma.
    source = Path(__file__).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(source).hexdigest()


def current_manifest() -> dict:
    """El manifiesto que corresponde al contenido de AHORA (lo que debería estar registrado)."""
    return {
        "casos": {c.id: case_digest(c) for c in HOLDOUT_CASES},
        "orden": [c.id for c in HOLDOUT_CASES],
        "fuente_sha256": source_digest(),
    }


def recorded_manifest() -> dict:
    """El manifiesto REGISTRADO en disco. `{}` si no existe o está corrupto — y entonces la
    verificación falla, que es la dirección segura (un holdout sin sello no certifica nada)."""
    try:
        return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def verify_holdout_integrity() -> dict:
    """¿El holdout sigue siendo el que se registró? Determinista y sin red.

    Devuelve {"ok", "motivos": [...], "n_casos", "fuente_ok", "esperado", "obtenido"}. `ok` solo
    es True si TODOS los casos, su ORDEN y el archivo fuente coinciden con el manifiesto.
    `motivos` explica en llano qué cambió — el punto de un sello es decir QUÉ se rompió, no solo
    que algo se rompió.
    """
    actual = current_manifest()
    grabado = recorded_manifest()
    motivos: list[str] = []

    if not grabado:
        motivos.append("No hay manifiesto registrado (o está corrupto): "
                       f"{_MANIFEST_PATH.name}")
        return {"ok": False, "motivos": motivos, "n_casos": len(HOLDOUT_CASES),
                "fuente_ok": False, "esperado": {}, "obtenido": actual}

    casos_grab = dict(grabado.get("casos") or {})
    casos_act = actual["casos"]

    for cid, dig in casos_act.items():
        if cid not in casos_grab:
            motivos.append(f"Caso NUEVO sin registrar: '{cid}'")
        elif casos_grab[cid] != dig:
            motivos.append(f"Caso ALTERADO: '{cid}' — registrado {casos_grab[cid][:12]}…, "
                           f"ahora {dig[:12]}…")
    for cid in casos_grab:
        if cid not in casos_act:
            motivos.append(f"Caso REGISTRADO que ya no está: '{cid}'")

    if list(grabado.get("orden") or []) != actual["orden"]:
        motivos.append("El ORDEN de los casos cambió respecto del registrado")

    fuente_ok = grabado.get("fuente_sha256") == actual["fuente_sha256"]
    if not fuente_ok:
        motivos.append("El ARCHIVO fuente del holdout cambió respecto del registrado "
                       f"(registrado {str(grabado.get('fuente_sha256'))[:12]}…, "
                       f"ahora {actual['fuente_sha256'][:12]}…)")

    return {
        "ok": not motivos,
        "motivos": motivos,
        "n_casos": len(HOLDOUT_CASES),
        "fuente_ok": fuente_ok,
        "esperado": grabado,
        "obtenido": actual,
    }


def load_holdout_cases(purpose: str) -> list[GoldenCase]:
    """La ÚNICA puerta a los casos del holdout.

    Dos candados, en este orden:
      1. `purpose` debe ser exactamente `HOLDOUT_PURPOSE_MEASURE`. Pedirlos para "arreglar",
         "calibrar" o "depurar" levanta `HoldoutMisuse`. No es una barrera criptográfica: es
         una barrera de INTENCIÓN, y por eso el string es explícito y queda en el código de
         quien llama, a la vista en el diff.
      2. La integridad debe verificar. Un holdout alterado NO se entrega (`HoldoutTampered`):
         medir con material tocado da un número peor que no medir, porque parece un número.
    """
    if purpose != HOLDOUT_PURPOSE_MEASURE:
        raise HoldoutMisuse(
            f"El holdout solo se puede cargar para '{HOLDOUT_PURPOSE_MEASURE}' "
            f"(se pidió: {purpose!r}). No se usa para arreglar, calibrar ni depurar: "
            "ese es exactamente el uso que lo destruiría."
        )
    informe = verify_holdout_integrity()
    if not informe["ok"]:
        raise HoldoutTampered(
            "El holdout NO coincide con su manifiesto registrado; no se entrega. Motivos: "
            + " · ".join(informe["motivos"])
        )
    return list(HOLDOUT_CASES)


def write_manifest() -> dict:
    """Registra el manifiesto de AHORA en disco. Se corre a mano, UNA vez, cuando se crea o se
    amplía el holdout a propósito — nunca desde una suite ni desde el bucle de arreglo (eso
    convertiría el sello en un sello de goma: cualquier edición se auto-aprobaría)."""
    manifiesto = current_manifest()
    _MANIFEST_PATH.write_text(
        json.dumps(manifiesto, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return manifiesto


if __name__ == "__main__":  # pragma: no cover — utilidad de mantenimiento, a mano
    import sys
    if "--write" in sys.argv:
        m = write_manifest()
        print(f"Manifiesto registrado en {_MANIFEST_PATH}")
        print(json.dumps(m, indent=2, ensure_ascii=False))
    else:
        inf = verify_holdout_integrity()
        print(json.dumps(inf, indent=2, ensure_ascii=False))
        sys.exit(0 if inf["ok"] else 1)
