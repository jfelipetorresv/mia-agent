"""Mia · agents.comentarios — comentarios anclados sobre un borrador (estilo Docs).

El abogado marca un pasaje del borrador y escribe qué quiere cambiar AHÍ. Mia corrige
únicamente esos pasajes y deja el resto del documento idéntico. Este módulo es la parte
PURA de esa mecánica (sin DB, sin LLM, sin efectos):

  1. `anclar`      — vuelve a encontrar cada pasaje comentado dentro del borrador vigente
                     (por texto exacto y contexto, nunca por offsets: el texto es el ancla).
  2. `instruccion` — el bloque de prompt que ordena tocar SOLO esos pasajes.
  3. `resoluciones`— tras la corrección, qué quedó en cada pasaje comentado y qué MÁS se
                     movió sin que el abogado lo pidiera (AVISO honesto, nunca bloqueo).

La detección de "qué más se movió" reutiliza `barreras_harness.pasajes_modificados`
(diff por párrafo, §19), que es la misma maquinaria que alimenta la segunda pasada del
gate de citas. Corregir es redactar: una corrección por comentarios es exactamente el
caso que la segunda pasada existe para verificar.
"""
from __future__ import annotations

import difflib
import re
from typing import Any, Optional

from . import barreras_harness

#: Tope de comentarios por ronda. Más que esto no es "corrige este punto": es rehacer el
#: escrito, y para eso ya está el rechazo con motivo.
MAX_COMENTARIOS = 20
#: Longitud máxima de cada campo que viaja del navegador al prompt.
MAX_INSTRUCCION = 1000
MAX_PASAJE = 2000
#: Por debajo de esta similitud no se da por ubicado un pasaje: se declara no ubicado y
#: el abogado lo ve como tal. Un ancla equivocada es peor que un ancla ausente.
UMBRAL_APROXIMADO = 0.82


def _parrafos(texto: str) -> list[str]:
    """Mismo troceo que el diff del harness: bloques separados por línea en blanco."""
    return [p.strip() for p in re.split(r"\n\s*\n", str(texto or "")) if p.strip()]


def _norm(texto: Any) -> str:
    return re.sub(r"\s+", " ", str(texto or "")).strip().lower()


def _limpio(valor: Any, tope: int) -> str:
    return re.sub(r"\s+", " ", str(valor or "")).strip()[:tope]


def _similitud(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, _norm(a), _norm(b), autojunk=False).ratio()


def normalizar_entrada(comentarios: Any) -> list[dict]:
    """Sanea lo que llega del navegador y descarta lo que no es un comentario.

    Un comentario sin pasaje citado o sin instrucción no dice nada: se descarta en
    silencio en vez de mandarle ruido al redactor.
    """
    salida: list[dict] = []
    for i, c in enumerate(comentarios or []):
        if not isinstance(c, dict):
            continue
        pasaje = _limpio(c.get("texto_citado"), MAX_PASAJE)
        instruccion = _limpio(c.get("instruccion"), MAX_INSTRUCCION)
        if not pasaje or not instruccion:
            continue
        try:
            idx = int(c.get("parrafo_indice"))
        except (TypeError, ValueError):
            idx = -1
        salida.append({
            "id": _limpio(c.get("id"), 64) or f"c{i + 1}",
            "texto_citado": pasaje,
            "parrafo_indice": idx,
            "contexto_antes": _limpio(c.get("contexto_antes"), 200),
            "contexto_despues": _limpio(c.get("contexto_despues"), 200),
            "instruccion": instruccion,
        })
        if len(salida) >= MAX_COMENTARIOS:
            break
    return salida


def anclar(comentarios: Any, texto: str) -> list[dict]:
    """Ubica cada comentario dentro de `texto` y devuelve la lista anclada.

    Estrategia, en orden (el TEXTO manda; el índice es solo una pista):
      1. `exacto`      — el pasaje citado está en el párrafo que indicó el navegador.
      2. `desplazado`  — está literalmente en otro párrafo (el documento se movió).
      3. `contexto`    — el párrafo que mejor casa con «contexto_antes + pasaje + después».
      4. `aproximado`  — el párrafo más parecido al pasaje, si supera el umbral.
      5. `no_ubicado`  — nada de lo anterior. Se conserva el comentario y se declara.

    PURA y sin efectos.
    """
    limpios = normalizar_entrada(comentarios)
    parrafos = _parrafos(texto)
    anclados: list[dict] = []
    for c in limpios:
        idx = c["parrafo_indice"]
        aguja = _norm(c["texto_citado"])
        metodo = "no_ubicado"
        resuelto: Optional[int] = None

        if 0 <= idx < len(parrafos) and aguja and aguja in _norm(parrafos[idx]):
            resuelto, metodo = idx, "exacto"
        else:
            literales = [i for i, p in enumerate(parrafos) if aguja and aguja in _norm(p)]
            if literales:
                # El más cercano al índice original: si el pasaje se repite, gana el que
                # el abogado tenía delante.
                resuelto = min(literales, key=lambda i: abs(i - idx) if idx >= 0 else i)
                metodo = "desplazado"

        if resuelto is None and parrafos:
            ventana = " ".join(x for x in (c["contexto_antes"], c["texto_citado"],
                                           c["contexto_despues"]) if x)
            mejor_i, mejor_r = -1, 0.0
            for i, p in enumerate(parrafos):
                r = max(_similitud(ventana, p), _similitud(c["texto_citado"], p))
                if r > mejor_r:
                    mejor_i, mejor_r = i, r
            if mejor_i >= 0 and mejor_r >= UMBRAL_APROXIMADO:
                resuelto = mejor_i
                metodo = "contexto" if (c["contexto_antes"] or c["contexto_despues"]) \
                    else "aproximado"

        anclados.append({
            **c,
            "parrafo_resuelto": resuelto,
            "pasaje_original": parrafos[resuelto] if resuelto is not None else "",
            "ubicado": resuelto is not None,
            "metodo": metodo,
        })
    return anclados


def instruccion_de_correccion(texto: str, anclados: list[dict]) -> str:
    """El bloque de prompt del re-draft por comentarios.

    Ordena EXPLÍCITAMENTE tocar solo los pasajes comentados y devolver el resto idéntico.
    Los comentarios que no se pudieron ubicar viajan igual, marcados como generales: se
    prefiere que el redactor los atienda con criterio a perder la instrucción del abogado.
    """
    ubicados = [c for c in anclados if c.get("ubicado")]
    sueltos = [c for c in anclados if not c.get("ubicado")]
    partes = [
        "El abogado revisó este borrador y dejó comentarios sobre pasajes concretos.",
        "",
        "Borrador vigente (es la base; NO lo rehagas):",
        str(texto or ""),
        "",
        "Comentarios del abogado:",
    ]
    for i, c in enumerate(ubicados, start=1):
        partes.append(
            f"{i}. Pasaje comentado (párrafo {int(c['parrafo_resuelto']) + 1}):\n"
            f"«{c['pasaje_original'] or c['texto_citado']}»\n"
            f"   Instrucción: {c['instruccion']}"
        )
    for j, c in enumerate(sueltos, start=len(ubicados) + 1):
        partes.append(
            f"{j}. Pasaje comentado (no lo encontré tal cual en esta versión):\n"
            f"«{c['texto_citado']}»\n"
            f"   Instrucción: {c['instruccion']}"
        )
    partes += [
        "",
        "Reglas de esta corrección, sin excepción:",
        "- Modifica ÚNICAMENTE los pasajes comentados, cada uno según su instrucción.",
        "- Todo lo demás del documento se conserva IDÉNTICO, palabra por palabra: no "
        "reordenes, no reescribas, no 'mejores' párrafos que nadie te pidió cambiar.",
        "- Devuelve el documento COMPLETO (con los pasajes corregidos en su sitio y el "
        "resto tal cual), no solo los fragmentos.",
        "- Si una instrucción no se puede cumplir sin respaldo en el expediente o en las "
        "fuentes, no la inventes: deja el pasaje y dilo en el propio texto con [VERIFICAR].",
    ]
    return "\n".join(partes)


def _cambio_legible(antes: str, despues: str) -> str:
    """Una línea en castellano llano sobre qué pasó con el pasaje."""
    if not despues.strip():
        return "Quedó eliminado."
    if _norm(antes) == _norm(despues):
        return "Quedó igual."
    ratio = _similitud(antes, despues)
    if ratio >= 0.9:
        return "Cambió en detalles de redacción."
    if ratio >= 0.5:
        return "Se reescribió en parte."
    return "Se reescribió por completo."


def cambios_por_parrafo(antes: str, despues: str) -> list[dict]:
    """El diff del harness, pero abierto párrafo a párrafo.

    `barreras_harness.pasajes_modificados` agrupa párrafos contiguos en un solo bloque:
    perfecto para acotar el gate de citas, inservible aquí, porque un bloque que mezcla
    el párrafo comentado con el de al lado esconde justamente el aviso que se busca
    («también cambié X, que no me pediste»). Aquí cada párrafo responde por sí mismo.
    """
    a = _parrafos(antes)
    b = _parrafos(despues)
    salida: list[dict] = []
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        if op == "replace":
            # Se emparejan por posición dentro del bloque; los sobrantes de cada lado
            # quedan como agregado o eliminado.
            n = max(i2 - i1, j2 - j1)
            for k in range(n):
                viejo = a[i1 + k] if i1 + k < i2 else ""
                nuevo = b[j1 + k] if j1 + k < j2 else ""
                tipo = ("reescrito" if viejo and nuevo
                        else "eliminado" if viejo else "agregado")
                salida.append({"tipo": tipo, "antes": viejo, "despues": nuevo})
        elif op == "insert":
            for k in range(j1, j2):
                salida.append({"tipo": "agregado", "antes": "", "despues": b[k]})
        else:  # delete
            for k in range(i1, i2):
                salida.append({"tipo": "eliminado", "antes": a[k], "despues": ""})
    return salida


def resoluciones(antes: str, despues: str, anclados: list[dict]) -> dict:
    """Qué pasó con cada comentario y qué MÁS se movió sin pedirlo.

    Devuelve `{"comentarios": [...], "avisos": [...], "resumen": "..."}`:
      - `comentarios`: por cada uno, el pasaje nuevo, si cambió y en qué cambió.
      - `avisos`: pasajes que cambiaron y NO tenían comentario — honestidad, no bloqueo.

    PURA y sin efectos.
    """
    cambios = cambios_por_parrafo(antes, despues)
    # El diff agrupado del harness sigue siendo el que alimenta la segunda pasada del gate
    # (§19); aquí solo se comprueba que ambos vean lo mismo cuando no hubo cambios.
    hubo_cambios = bool(barreras_harness.pasajes_modificados(antes, despues))
    nuevos = _parrafos(despues)
    viejos = _parrafos(antes)

    # Mapa de párrafos viejos comentados (por texto normalizado) para cruzar con el diff.
    comentados_norm = {
        _norm(c.get("pasaje_original") or c.get("texto_citado")): c
        for c in anclados if (c.get("pasaje_original") or c.get("texto_citado"))
    }

    def _pasaje_nuevo(c: dict) -> str:
        """El párrafo resultante para un comentario: el del diff, o el mismo si no cambió."""
        original = c.get("pasaje_original") or ""
        if original:
            for ch in cambios:
                if _norm(original) in _norm(ch["antes"]):
                    return ch["despues"]
            # No aparece en ningún cambio → sigue idéntico en el texto nuevo.
            if any(_norm(original) == _norm(p) for p in nuevos):
                return original
        idx = c.get("parrafo_resuelto")
        if isinstance(idx, int) and 0 <= idx < len(nuevos):
            return nuevos[idx]
        return ""

    salida_com: list[dict] = []
    for c in anclados:
        original = c.get("pasaje_original") or ""
        nuevo = _pasaje_nuevo(c)
        atendido = bool(original) and _norm(original) != _norm(nuevo)
        salida_com.append({
            "id": c.get("id"),
            "instruccion": c.get("instruccion"),
            "texto_citado": c.get("texto_citado"),
            "ubicado": bool(c.get("ubicado")),
            "pasaje_antes": original or c.get("texto_citado") or "",
            "pasaje_despues": nuevo,
            "atendido": atendido,
            "cambio": _cambio_legible(original, nuevo) if original else
                      ("Lo apliqué donde correspondía." if nuevo else
                       "No encontré ese pasaje en esta versión; revísalo tú."),
        })

    avisos: list[dict] = []
    for ch in cambios:
        viejo_txt = ch.get("antes") or ""
        # Un cambio es "pedido" si alguno de los párrafos viejos que toca estaba comentado.
        pedido = any(clave and clave in _norm(viejo_txt) for clave in comentados_norm)
        if pedido:
            continue
        if ch["tipo"] == "agregado" and not viejo_txt:
            texto_aviso = ch.get("despues") or ""
        else:
            texto_aviso = viejo_txt
        if not texto_aviso.strip():
            continue
        avisos.append({
            "tipo": ch["tipo"],
            "antes": viejo_txt,
            "despues": ch.get("despues") or "",
        })

    atendidos = sum(1 for c in salida_com if c["atendido"])
    n = len(salida_com)
    if not hubo_cambios:
        return {"comentarios": salida_com, "avisos": [],
                "resumen": "El borrador quedó exactamente igual: no cambié nada."}
    resumen = (f"Apliqué {atendidos} de {n} comentario{'' if n == 1 else 's'}."
               if n else "No había comentarios que aplicar.")
    if avisos:
        resumen += (f" También cambié {len(avisos)} pasaje"
                    f"{'' if len(avisos) == 1 else 's'} que no me pediste: revísalo"
                    f"{'' if len(avisos) == 1 else 's'} antes de aprobar.")
    elif n:
        resumen += " El resto del documento quedó igual."
    # `viejos` participa del contrato de la función (documento base no vacío); se usa aquí
    # para no prometer "el resto quedó igual" sobre un documento que no existía.
    if not viejos:
        resumen = "No había un borrador previo sobre el que comentar."
    return {"comentarios": salida_com, "avisos": avisos, "resumen": resumen}
