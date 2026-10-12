"""Mia · eval.banco04.ceguera — lo que el juez NO puede ver (§8.3, §10.2.8).

A los jueces nunca les llega: versión, SHA, hash de prompt, política, modelo, esfuerzo, número
de corrida, señales deterministas ni la existencia de una comparación. Antes de enviar el texto:
  · se retiran los avisos de costo y de cambio de motor (por su PLANTILLA EXACTA o por el literal
    que la corrida persistió), los recibos internos que la corrida declare, los UUID canónicos,
    los hashes hexadecimales largos y las marcas de tiempo de máquina (ISO con hora y segundos);
  · el AVISO DE ALCANCE de la aplicación NO se borra en silencio ni se reescribe: se EXTRAE del
    texto y viaja como contexto separado, con el mismo rótulo en las dos versiones.

Lo que NUNCA se toca: fechas jurídicas, anclas `[doc n]`, números de radicado o de norma, y la
frase con que MIA misma limita su diagnóstico («leí X de Y fragmentos…»). Por eso no hay un
regex laxo de alcance: retirar la parte (b) de un `limitada_expresa` lo convertiría en
`definitiva`, justo en los casos para los que existe §7.

Los ids de candidato salen de HMAC-SHA256 sobre una llave custodiada (patrón de
`provider_benchmark._blind_side`), y el orden de juicio se baraja con la misma llave.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..provider_benchmark import sha256_json
from .segmentos import normalizar_saltos

ROTULO_AVISO_ALCANCE = (
    "AVISO DE ALCANCE AÑADIDO POR LA APLICACIÓN (contexto; no forma parte del texto juzgado)")

# Plantilla EXACTA de `agents.graph._aviso_de_alcance` (las cifras son variables).
_AVISO_ALCANCE_RE = re.compile(
    r"De este expediente leí \d+ de \d+ fragmentos \(\d+%\)\. Reparto la lectura por todas "
    r"las piezas y vuelvo sobre los ejes del caso, pero un dato puntual —una fecha, una "
    r"cláusula suelta— puede haber quedado fuera\. Si el asunto depende de un dato así, "
    r"indícame dónde buscarlo o pregúntame por él directamente\.")
# Plantillas EXACTAS de `agent.llm.aviso_cambio_de_motor` (aviso de costo / cambio de motor).
_AVISO_MOTOR_RE = re.compile(
    r"(?:El trabajo era demasiado grande para tu suscripción y no alcanzó a responder|"
    r"Tu suscripción no pudo atender esta consulta)\. Para no dejarte sin respuesta lo resolví "
    r"con crédito de pago, y eso tiene un costo que verás en el consumo de este turno\. Tu "
    r"suscripción se usa primero siempre; el crédito solo entra cuando ella se queda corta\.")
_SUGERENCIA_MOTOR_RE = re.compile(
    r"Revisa los límites y condiciones de tu plan antes de volver a intentar un trabajo de "
    r"este tamaño\. También puedes elegir otra conexión en Configuración\.")
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_HEX_LARGO_RE = re.compile(r"\b[0-9a-fA-F]{32,}\b")
_MARCA_TIEMPO_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b")

# Claves que jamás pueden aparecer en el paquete del juez (en ningún nivel).
CLAVES_PROHIBIDAS: frozenset[str] = frozenset({
    "version", "versión", "sha", "git_sha", "commit", "prompt_version_hash", "prompt_hash",
    "hash_prompt", "politica", "política", "policy", "model", "modelo", "effort", "esfuerzo",
    "repeticion", "repetición", "repetition", "corrida", "run", "run_id", "score",
    "senales", "señales", "signals", "comparacion", "comparación", "brazo", "arm", "case_id",
    "matter_id", "elapsed_ms", "usage", "model_fallbacks", "verification", "recall_enterrado",
    "jurisdiction_leak", "false_block", "abstention", "provenance", "semilla", "seed",
})
ESQUEMA_PAQUETE = "banco04-paquete-juez/v1.3"   # v1.3: jurisdicciones configuradas (I7, §12.5)
CLAVES_PAQUETE: tuple[str, ...] = (
    "esquema_paquete", "candidate_id", "mensaje_abogado", "expediente", "mapa_docs",
    "fuentes_corpus", "jurisdicciones_configuradas", "contexto_aviso_alcance", "segmentos",
)


@dataclass
class TextoCegado:
    texto: str
    retirados: list[dict] = field(default_factory=list)  # [{tipo, literal}] — solo para auditoría
    aviso_alcance: str | None = None


def _retirar(texto: str, patron: re.Pattern, tipo: str, retirados: list[dict]) -> str:
    def _sub(m: re.Match) -> str:
        retirados.append({"tipo": tipo, "literal": m.group(0)})
        return ""
    return patron.sub(_sub, texto)


def _retirar_literal(texto: str, literal: str, tipo: str, retirados: list[dict]) -> str:
    if literal and literal in texto:
        retirados.append({"tipo": tipo, "literal": literal, "veces": texto.count(literal)})
        texto = texto.replace(literal, "")
    return texto


def cegar_texto(texto: str, *, aviso_alcance: str | None = None,
                avisos_motor: Iterable[str] = (), recibos: Iterable[str] = ()) -> TextoCegado:
    """Retira los rastros de §8.3 y EXTRAE el aviso de alcance de la aplicación.

    `aviso_alcance`: el literal que la aplicación persistió (`alcance_lectura.aviso`), si lo hay.
    `avisos_motor` / `recibos`: literales persistidos por la corrida que deben retirarse.
    """
    texto = normalizar_saltos(texto)
    retirados: list[dict] = []
    extraidos: list[str] = []
    if aviso_alcance and aviso_alcance in texto:
        extraidos.append(aviso_alcance)
        texto = texto.replace(aviso_alcance, "")
    for m in list(_AVISO_ALCANCE_RE.finditer(texto)):
        extraidos.append(m.group(0))
    texto = _AVISO_ALCANCE_RE.sub("", texto)
    for literal in avisos_motor:
        texto = _retirar_literal(texto, literal, "aviso_motor", retirados)
    for literal in recibos:
        texto = _retirar_literal(texto, literal, "recibo_interno", retirados)
    texto = _retirar(texto, _AVISO_MOTOR_RE, "aviso_motor", retirados)
    texto = _retirar(texto, _SUGERENCIA_MOTOR_RE, "aviso_motor", retirados)
    texto = _retirar(texto, _UUID_RE, "uuid", retirados)
    texto = _retirar(texto, _HEX_LARGO_RE, "hash", retirados)
    texto = _retirar(texto, _MARCA_TIEMPO_RE, "marca_tiempo", retirados)
    aviso = aviso_alcance if aviso_alcance else None
    if extraidos and not aviso:
        aviso = extraidos[0]
    for literal in extraidos:
        retirados.append({"tipo": "aviso_alcance_extraido", "literal": literal})
    return TextoCegado(texto=texto, retirados=retirados, aviso_alcance=aviso)


def candidate_id(llave: bytes, etiqueta_version: str, case_id: str, repeticion: int,
                 diagnostico: str, borrador: str) -> str:
    """Id ciego del candidato: HMAC sobre la llave custodiada. No revela versión ni corrida."""
    if not isinstance(llave, (bytes, bytearray)) or len(llave) < 16:
        raise ValueError("la llave de ceguera debe ser bytes de al menos 16 de longitud")
    huella = sha256_json([diagnostico, borrador])
    msg = f"{etiqueta_version}:{case_id}:{int(repeticion)}:{huella}".encode("utf-8")
    return hmac.new(bytes(llave), msg, hashlib.sha256).hexdigest()[:24]


def clave_orden(llave: bytes, ident: str) -> str:
    return hmac.new(bytes(llave), f"orden:{ident}".encode("utf-8"), hashlib.sha256).hexdigest()


def barajar(idents: Iterable[str], llave: bytes) -> list[str]:
    """Orden de juicio barajado de forma determinista con la llave (sin `random`)."""
    return sorted(idents, key=lambda i: clave_orden(llave, i))


def construir_paquete(*, candidate: str, segmentos: list[dict], mensaje_abogado: str,
                      expediente: list[dict], mapa_docs: list[dict],
                      fuentes_corpus: list[dict], aviso_alcance: str | None,
                      jurisdicciones_configuradas: list[str]) -> dict[str, Any]:
    """Paquete que recibe el juez. Allowlist estricta de claves (nada más entra).

    I7 (protocolo v1.3, §12.5): las jurisdicciones CONFIGURADAS del despacho van como contexto
    permitido (lista vacía = ningún ordenamiento configurado): una norma con pasaje puede ser de
    un ordenamiento no configurado y entonces es fuga (§5.7). Igual en validación y medición."""
    if not isinstance(jurisdicciones_configuradas, list) or not all(
            isinstance(j, str) for j in jurisdicciones_configuradas):
        raise ValueError("jurisdicciones_configuradas debe ser una lista de códigos (vacía = ninguna)")
    return {
        "esquema_paquete": ESQUEMA_PAQUETE,
        "candidate_id": candidate,
        "mensaje_abogado": mensaje_abogado,
        "expediente": expediente,
        "mapa_docs": mapa_docs,
        "fuentes_corpus": fuentes_corpus,
        "jurisdicciones_configuradas": sorted(jurisdicciones_configuradas),
        "contexto_aviso_alcance": {"rotulo": ROTULO_AVISO_ALCANCE, "texto": aviso_alcance},
        "segmentos": segmentos,
    }


def _claves(valor: Any, ruta: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(valor, dict):
        for k, v in valor.items():
            yield f"{ruta}/{k}", str(k)
            yield from _claves(v, f"{ruta}/{k}")
    elif isinstance(valor, list):
        for i, v in enumerate(valor):
            yield from _claves(v, f"{ruta}[{i}]")


def _cadenas(valor: Any) -> Iterable[str]:
    if isinstance(valor, str):
        yield valor
    elif isinstance(valor, dict):
        for v in valor.values():
            yield from _cadenas(v)
    elif isinstance(valor, list):
        for v in valor:
            yield from _cadenas(v)


def auditar_paquete(paquete: dict, prohibidos: Iterable[str] = ()) -> list[str]:
    """Violaciones de ceguera del paquete. Vacío = ciego. El juez se niega a enviar si no.

    `prohibidos`: literales de la corrida que no pueden aparecer en NINGÚN texto del paquete
    (SHA de versión, hash de prompt, nombre de la política, alias de modelo, etiqueta de versión…).
    """
    violaciones: list[str] = []
    if set(paquete) != set(CLAVES_PAQUETE):
        violaciones.append(f"claves_de_primer_nivel:{sorted(set(paquete) ^ set(CLAVES_PAQUETE))}")
    for ruta, clave in _claves(paquete):
        if clave.lower() in CLAVES_PROHIBIDAS:
            violaciones.append(f"clave_prohibida:{ruta}")
    juzgado = [s.get("texto", "") for s in paquete.get("segmentos") or [] if isinstance(s, dict)]
    aviso = (paquete.get("contexto_aviso_alcance") or {}).get("texto") or ""
    for texto in juzgado + [aviso]:
        for nombre, patron in (("uuid", _UUID_RE), ("hash", _HEX_LARGO_RE),
                               ("marca_tiempo", _MARCA_TIEMPO_RE), ("aviso_motor", _AVISO_MOTOR_RE)):
            if patron.search(texto):
                violaciones.append(f"rastro_{nombre}_en_texto_juzgado")
    for texto in juzgado:
        if _AVISO_ALCANCE_RE.search(texto):
            violaciones.append("aviso_de_alcance_dentro_del_texto_juzgado")
    cadenas = list(_cadenas(paquete))
    for literal in prohibidos:
        if literal and any(literal in c for c in cadenas):
            violaciones.append(f"literal_prohibido_presente:{literal[:12]}…")
    return sorted(set(violaciones))


class CegueraRota(RuntimeError):
    """El paquete del juez no es ciego: no se envía (falla cerrado)."""


def preparar_candidato(*, llave: bytes, etiqueta_version: str, case_id: str, repeticion: int,
                       diagnostico: str, borrador: str, mensaje_abogado: str,
                       expediente: list[dict], mapa_docs: list[dict], fuentes_corpus: list[dict],
                       jurisdicciones_configuradas: list[str],
                       aviso_alcance: str | None = None, avisos_motor: Iterable[str] = (),
                       recibos: Iterable[str] = (), prohibidos: Iterable[str] = ()) -> tuple[dict, dict]:
    """Cegado → segmentación → paquete → auditoría. Devuelve (paquete_para_juez, privado).

    `privado` NUNCA va al juez: guarda el mapeo candidato → (versión, caso, corrida), lo
    retirado y la posición de cada segmento en su sección (para localizar defectos plantados)."""
    from .segmentos import segmentar_salida, tokens_con_posicion

    d = cegar_texto(diagnostico, aviso_alcance=aviso_alcance, avisos_motor=avisos_motor,
                    recibos=recibos)
    b = cegar_texto(borrador, aviso_alcance=aviso_alcance, avisos_motor=avisos_motor,
                    recibos=recibos)
    aviso = aviso_alcance or d.aviso_alcance or b.aviso_alcance
    cid = candidate_id(llave, etiqueta_version, case_id, repeticion, diagnostico, borrador)
    segs = segmentar_salida(d.texto, b.texto)
    paquete = construir_paquete(
        candidate=cid,
        segmentos=[{"id": s.id, "texto": s.texto, "tokens": tokens_con_posicion(s.texto)}
                   for s in segs],
        mensaje_abogado=mensaje_abogado, expediente=expediente, mapa_docs=mapa_docs,
        fuentes_corpus=fuentes_corpus, aviso_alcance=aviso,
        jurisdicciones_configuradas=jurisdicciones_configuradas)
    prohibidos = [p for p in prohibidos if p] + ([etiqueta_version] if len(etiqueta_version) >= 4 else [])
    violaciones = auditar_paquete(paquete, prohibidos)
    if violaciones:
        raise CegueraRota(f"{case_id}#{repeticion}: {violaciones}")
    privado = {
        "candidate_id": cid, "etiqueta_version": etiqueta_version, "case_id": case_id,
        "repeticion": int(repeticion), "retirados": d.retirados + b.retirados,
        "texto_cegado": {"diagnostico": d.texto, "borrador": b.texto},
        "segmentos": [s.as_dict() for s in segs],
    }
    return paquete, privado
