"""
Mia · barreras_harness.py — tres principios del harness de litigio de Lexia, portados.

Los tres NACEN COMO AVISO (regla de implantación de Mia: una barrera nueva registra y
reporta; solo sube a muro cuando demuestre no dar falsos positivos). Ninguna función de
este módulo edita el borrador, retira una cita ni tumba el turno: todas devuelven un dict
serializable que viaja en `metadata["verification"]` hasta la pantalla del abogado, o
None cuando no hay nada que decir.

Los detectores deciden por ROL y por ESTRUCTURA —el `estado` que el verificador ya asignó
a cada cita, los campos nombrados de una fuente, los bloques que un diff marcó como
cambiados— nunca por la presencia de una subcadena mágica en el texto. La búsqueda por
texto se usa solo para LOCALIZAR algo cuyo rol ya se decidió antes.

═══ §19 · «Corregir es redactar» ══════════════════════════════════════════════════
Un gate que corre una sola vez no es un gate: aplicar las correcciones de la primera
pasada introdujo siete errores nuevos en un escrito real, y una reincidencia apareció
justo en el texto reescrito para corregir el hallazgo anterior. El texto nuevo que entra
al corregir es exactamente igual de sospechoso que el original.
  → `segunda_pasada()`: diff por párrafo entre la versión anterior y la corregida, y
    lectura del informe del verificador ACOTADA a los pasajes que cambiaron, con doble
    alcance: (a) ¿la corrección quedó bien? (b) ¿el cambio introdujo un defecto nuevo?

═══ §21 · «Barrido de patrón» ═════════════════════════════════════════════════════
Ante un defecto señalado con UN ejemplo, se barre el documento entero por el patrón en
una pasada. Pipe mostró un pasaje; el barrido encontró 32. Corregir hallazgo por hallazgo
costó cuatro versiones completas en otra corrida.
  → `barrido_de_patron()`: de cada defecto señalado (por el gate o por el abogado) deriva
    un descriptor estructural y cuenta TODAS sus ocurrencias en el documento completo.

═══ §23 · «Verificar el contenido, no el continente» ══════════════════════════════
17 de 36 fuentes de un paquete traían un texto que no era de la norma que decían citar,
con toda la cadena de verificación en verde: se cotejaba el hash del archivo —que
coincidía— y jamás el texto. Y una providencia se citó como «sentencia de 2013» porque el
contrato del paquete no pedía radicado, sala ni ponente.
  → `revisar_fuentes()`: coteja el PASAJE de cada fuente contra el contenido del que dice
    salir por similitud calibrada (umbral 75 %, configurable) y exige un bloque de
    identificación mínima (tipo · número/radicado · fecha) antes de que la fuente entre al
    redactor. En modo AVISO informa; con `exigir=True` marca cuáles quedarían fuera y con
    qué razón honesta.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Any, Optional

from .. import config

# ── vocabulario común ───────────────────────────────────────────────────────────

#: Estados que el verificador (`verification.annotate_draft`) asigna a una cita y que
#: significan DEFECTO. Es la decisión por rol: aquí no se mira el texto de la cita para
#: saber si está mal, se mira la etiqueta que el muro determinista ya le puso.
ESTADOS_DEFECTUOSOS: frozenset = frozenset({"anotada", "marcada", "omitida", "quemada"})

#: Estados que significan que la cita quedó RESUELTA (respaldo real o sello del despacho).
ESTADOS_SANOS: frozenset = frozenset({"respaldada", "sellada"})

_TOKEN_RE = re.compile(r"[0-9a-záéíóúüñ]+", re.IGNORECASE)


def _normalizar(texto: Any) -> str:
    """Minúsculas sin tildes: el cotejo no puede depender de la acentuación del OCR."""
    raw = str(texto or "")
    desc = unicodedata.normalize("NFD", raw)
    return "".join(ch for ch in desc if unicodedata.category(ch) != "Mn").lower()


def _tokens(texto: Any) -> list[str]:
    return _TOKEN_RE.findall(_normalizar(texto))


def _contiene_tokens(pajar: list[str], aguja: list[str]) -> bool:
    """¿La secuencia `aguja` aparece CONTIGUA en `pajar`?

    Contigua y por tokens, no por subcadena: así «Ley 14» no puede casar dentro de
    «Ley 1437» ni «artículo 5» dentro de «artículo 50`.
    """
    if not aguja or len(aguja) > len(pajar):
        return False
    primero = aguja[0]
    n = len(aguja)
    for i, tok in enumerate(pajar):
        if tok == primero and pajar[i:i + n] == aguja:
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# §19 · CORREGIR ES REDACTAR — la segunda pasada acotada a lo que cambió
# ═══════════════════════════════════════════════════════════════════════════════

#: Un párrafo por debajo de esto es un título, una firma o un renglón suelto: cambiarlo no
#: abre la puerta a un defecto de cita. Se cuenta igual como pasaje modificado (el abogado
#: quiere saber qué se movió) pero no arrastra ruido al conteo de defectos.
PARRAFO_MIN_CHARS = 40


def _parrafos(texto: str) -> list[str]:
    """Bloques del documento separados por línea en blanco, sin vacíos."""
    return [p.strip() for p in re.split(r"\n\s*\n", str(texto or "")) if p.strip()]


def pasajes_modificados(antes: str, despues: str) -> list[dict]:
    """Los pasajes que cambiaron entre dos versiones del mismo escrito.

    Diff a nivel de PÁRRAFO (basta para acotar el gate y no depende de que el modelo
    respete la puntuación). Devuelve una lista de `{"tipo", "antes", "despues"}` donde
    `tipo` ∈ reescrito | agregado | eliminado. PURA y sin efectos.
    """
    a = _parrafos(antes)
    b = _parrafos(despues)
    cambios: list[dict] = []
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        viejo = "\n\n".join(a[i1:i2])
        nuevo = "\n\n".join(b[j1:j2])
        tipo = {"replace": "reescrito", "insert": "agregado", "delete": "eliminado"}[op]
        cambios.append({"tipo": tipo, "antes": viejo, "despues": nuevo})
    return cambios


def _citas_por_estado(informe: Optional[dict]) -> list[dict]:
    """Las citas clasificadas de un informe del verificador, con su estado (rol)."""
    if not isinstance(informe, dict):
        return []
    salida: list[dict] = []
    for entrada in informe.get("detalle") or []:
        if not isinstance(entrada, dict):
            continue
        cita = str(entrada.get("cita") or "").strip()
        estado = str(entrada.get("estado") or "").strip()
        if cita and estado:
            salida.append({"cita": cita, "estado": estado})
    return salida


def _localizadas_en(citas: list[dict], texto: str) -> dict[str, str]:
    """De las citas ya clasificadas, cuáles caen dentro de `texto` → {cita: estado}.

    El ROL (defecto o no) viene del `estado`; aquí solo se LOCALIZA la cita, y por
    secuencia contigua de tokens, nunca por subcadena cruda.
    """
    pajar = _tokens(texto)
    if not pajar:
        return {}
    ubicadas: dict[str, str] = {}
    for c in citas:
        if _contiene_tokens(pajar, _tokens(c["cita"])):
            ubicadas[_normalizar(c["cita"])] = c["estado"]
    return ubicadas


def segunda_pasada(texto_antes: str, informe_antes: Optional[dict],
                   texto_despues: str, informe_despues: Optional[dict]) -> Optional[dict]:
    """§19 · Segunda vuelta del gate ACOTADA a los pasajes reescritos, con doble alcance.

    - `corregidos`: citas que estaban defectuosas en el pasaje viejo y salen sanas del
      pasaje nuevo → la corrección quedó bien.
    - `introducidos`: citas defectuosas que están en el pasaje NUEVO y no estaban en el
      viejo → el propio arreglo trajo el defecto. Es lo que §19 vino a cazar.
    - `persisten`: seguían mal antes y siguen mal después del cambio.

    Devuelve None cuando no cambió nada (no hay segunda pasada que reportar). AVISO: no
    edita el texto ni bloquea el turno. PURA y sin efectos.
    """
    cambios = pasajes_modificados(texto_antes, texto_despues)
    if not cambios:
        return None
    viejo = "\n\n".join(c["antes"] for c in cambios)
    nuevo = "\n\n".join(c["despues"] for c in cambios)

    antes_map = _localizadas_en(_citas_por_estado(informe_antes), viejo)
    despues_map = _localizadas_en(_citas_por_estado(informe_despues), nuevo)

    def _etiqueta(clave: str, fuente: list[dict]) -> str:
        for c in fuente:
            if _normalizar(c["cita"]) == clave:
                return c["cita"]
        return clave

    citas_antes = _citas_por_estado(informe_antes)
    citas_despues = _citas_por_estado(informe_despues)

    # «Introducido» significa NUEVO EN EL DOCUMENTO, no nuevo en este párrafo: una cita que
    # ya venía defectuosa en otro pasaje y que la reescritura simplemente movió aquí no la
    # introdujo la corrección. El alcance de los pasajes acota QUÉ se mira; la pregunta de
    # si el defecto es nuevo se responde contra el documento anterior COMPLETO.
    defectuosas_antes = {_normalizar(c["cita"]) for c in citas_antes
                         if c["estado"] in ESTADOS_DEFECTUOSOS}

    corregidos: list[str] = []
    persisten: list[dict] = []
    introducidos: list[dict] = []

    for clave, estado in despues_map.items():
        if estado not in ESTADOS_DEFECTUOSOS:
            continue
        etiqueta = _etiqueta(clave, citas_despues)
        if clave in defectuosas_antes:
            persisten.append({"cita": etiqueta, "estado": estado})
        else:
            introducidos.append({"cita": etiqueta, "estado": estado})

    for clave, estado in antes_map.items():
        if estado not in ESTADOS_DEFECTUOSOS:
            continue
        nuevo_estado = despues_map.get(clave)
        if nuevo_estado is None or nuevo_estado in ESTADOS_SANOS:
            corregidos.append(_etiqueta(clave, citas_antes))

    n = len(cambios)
    plural = "pasaje" if n == 1 else "pasajes"
    partes = [f"Volví a verificar los {n} {plural} que cambiaron."]
    if corregidos:
        partes.append(
            f"La corrección quedó bien en {len(corregidos)}: "
            + ", ".join(corregidos[:5])
            + (" y otras." if len(corregidos) > 5 else "."))
    if introducidos:
        refs = ", ".join(d["cita"] for d in introducidos[:5])
        partes.append(
            f"El cambio introdujo {len(introducidos)} problema"
            f"{'' if len(introducidos) == 1 else 's'} que antes no estaba"
            f"{'' if len(introducidos) == 1 else 'n'} ahí: {refs}"
            + (" y otros." if len(introducidos) > 5 else "."))
    if persisten:
        partes.append(
            f"Y {len(persisten)} sigue"
            f"{'' if len(persisten) == 1 else 'n'} sin respaldo pese al cambio: "
            + ", ".join(d["cita"] for d in persisten[:5])
            + (" y otros." if len(persisten) > 5 else "."))
    if not (corregidos or introducidos or persisten):
        partes.append("Ninguna cita quedó sin respaldo en el texto nuevo.")

    return {
        "estado": "aviso",
        "pasajes": n,
        "detalle_pasajes": [{"tipo": c["tipo"]} for c in cambios[:20]],
        "corregidos": corregidos,
        "introducidos": introducidos,
        "persisten": persisten,
        "aviso": " ".join(partes),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# §21 · BARRIDO DE PATRÓN — un defecto señalado se barre en todo el documento
# ═══════════════════════════════════════════════════════════════════════════════

#: Tope de patrones distintos que se barren por turno. Barrer es barato (una pasada de
#: tokens por patrón) pero el informe al abogado tiene que seguir siendo legible.
MAX_PATRONES = 5

#: Cuántas ocurrencias se ejemplifican en el informe. El CONTEO es completo; lo que se
#: capa es la serialización.
MAX_EJEMPLOS = 8

_MOTIVO_RE = re.compile(r"[«\"“']([^«»\"”']{4,120})[»\"”']")


def descriptor_de_defecto(defecto: Any) -> Optional[dict]:
    """Deriva el descriptor de patrón de UN defecto señalado. PURA.

    Un descriptor YA formado (el que devuelve `descriptores_del_motivo`) se acepta tal cual:
    así el barrido tiene un solo camino para el defecto del gate y el del abogado.

    Dos clases, ambas estructurales:
      · `cita`  — el defecto viene del verificador: `{"cita": ..., "estado": ...}`. El
        patrón es la secuencia de tokens de la referencia; se busca contigua.
      · `expresion` — el defecto lo señaló el ABOGADO en prosa y entrecomilló el pasaje
        («no vuelvas a escribir "salvo mejor criterio"»). El patrón es lo entrecomillado.
    Cualquier otra forma devuelve None: no se inventa un patrón que nadie señaló.
    """
    if isinstance(defecto, dict):
        if defecto.get("clase") and defecto.get("tokens"):
            return defecto  # ya es un descriptor
        cita = str(defecto.get("cita") or "").strip()
        if cita:
            toks = _tokens(cita)
            if not toks:
                return None
            return {"clase": "cita", "patron": cita, "tokens": toks,
                    "estado": str(defecto.get("estado") or "")}
        texto = str(defecto.get("texto") or "").strip()
    else:
        texto = str(defecto or "").strip()
    if not texto:
        return None
    entrecomillado = _MOTIVO_RE.search(texto)
    if not entrecomillado:
        return None
    frase = entrecomillado.group(1).strip()
    toks = _tokens(frase)
    if not toks:
        return None
    return {"clase": "expresion", "patron": frase, "tokens": toks, "estado": ""}


def descriptores_del_motivo(motivo: str, *, max_patrones: int = MAX_PATRONES) -> list[dict]:
    """Todos los pasajes que el abogado entrecomilló en su motivo de rechazo."""
    salida: list[dict] = []
    vistos: set[str] = set()
    for m in _MOTIVO_RE.finditer(str(motivo or "")):
        d = descriptor_de_defecto({"texto": f'"{m.group(1)}"'})
        if d and tuple(d["tokens"]) not in vistos:
            vistos.add(tuple(d["tokens"]))
            salida.append(d)
        if len(salida) >= max_patrones:
            break
    return salida


def barrer(texto: str, descriptor: dict) -> list[str]:
    """Todas las ocurrencias del patrón en el documento COMPLETO, por párrafo. PURA.

    Devuelve el párrafo (recortado) de cada ocurrencia. El conteo es el largo de la lista.
    """
    aguja = list(descriptor.get("tokens") or [])
    if not aguja:
        return []
    hallazgos: list[str] = []
    for parrafo in _parrafos(texto):
        pajar = _tokens(parrafo)
        if _contiene_tokens(pajar, aguja):
            hallazgos.append(parrafo.strip()[:200])
    return hallazgos


def barrido_de_patron(texto: str, defectos: Any,
                      *, max_patrones: int = MAX_PATRONES) -> Optional[dict]:
    """§21 · Ante un defecto señalado, barre el escrito entero por ese patrón.

    `defectos` puede ser la lista `detalle` del informe del verificador (se filtra por
    ROL: solo los estados defectuosos) o una lista de descriptores en prosa del abogado.

    Devuelve None cuando no hay defecto señalado o cuando ningún patrón aparece más de
    una vez —barrer y encontrar solo el ejemplo que ya se señaló no es noticia—. AVISO:
    señala TODAS las ocurrencias, no reescribe ninguna. PURA y sin efectos.
    """
    if not texto or not defectos:
        return None
    descriptores: list[dict] = []
    vistos: set[tuple] = set()
    for d in defectos:
        if isinstance(d, dict) and d.get("estado") and \
                d.get("estado") not in ESTADOS_DEFECTUOSOS and d.get("cita"):
            continue  # decisión por rol: una cita sana no señala ningún patrón
        desc = descriptor_de_defecto(d)
        if not desc:
            continue
        clave = tuple(desc["tokens"])
        if clave in vistos:
            continue
        vistos.add(clave)
        descriptores.append(desc)
        if len(descriptores) >= max_patrones:
            break
    if not descriptores:
        return None

    patrones: list[dict] = []
    total_extra = 0
    for desc in descriptores:
        hallazgos = barrer(texto, desc)
        if len(hallazgos) <= 1:
            continue  # solo el ejemplo ya conocido: no hay patrón que reportar
        total_extra += len(hallazgos) - 1
        patrones.append({
            "clase": desc["clase"],
            "patron": desc["patron"],
            "ocurrencias": len(hallazgos),
            "ejemplos": hallazgos[:MAX_EJEMPLOS],
        })
    if not patrones:
        return None

    if len(patrones) == 1:
        p = patrones[0]
        aviso = (
            f"Encontré este mismo problema en {p['ocurrencias'] - 1} lugar"
            f"{'' if p['ocurrencias'] - 1 == 1 else 'es'} más del escrito "
            f"(«{p['patron']}»). Te los dejo señalados todos, no solo el primero.")
    else:
        aviso = (
            f"Los problemas señalados se repiten: barrí el escrito completo y encontré "
            f"{total_extra} ocurrencia{'' if total_extra == 1 else 's'} más de "
            f"{len(patrones)} patrones distintos. Te las dejo señaladas todas, no solo "
            "las primeras.")

    return {"estado": "aviso", "patrones": patrones,
            "ocurrencias_adicionales": total_extra, "aviso": aviso}


# ═══════════════════════════════════════════════════════════════════════════════
# §23 · VERIFICAR EL CONTENIDO, NO EL CONTINENTE
# ═══════════════════════════════════════════════════════════════════════════════

#: Campos que componen la identificación mínima de una fuente. Se leen por NOMBRE de
#: campo (rol), nunca adivinando dentro de la cadena de la referencia: la regla se le
#: exige a quien puede cumplirla, y quien puede llenar estos campos es la ficha, no el
#: parser. Cada entrada es (etiqueta_para_el_abogado, alias aceptados).
CAMPOS_IDENTIFICACION: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tipo", ("tipo", "clase", "tipo_norma", "tipo_providencia", "especie")),
    ("numero", ("numero", "número", "radicado", "num", "numero_norma",
                "numero_providencia", "expediente")),
    ("fecha", ("fecha", "anio", "año", "year", "fecha_expedicion", "fecha_providencia")),
)

#: De dónde puede salir el PASAJE que la fuente dice citar, y de dónde el CONTENIDO del
#: que ese pasaje debería provenir. Si no hay contenido, el cotejo no es posible y se
#: dice —«no verificable» no es lo mismo que «verificado».
_CLAVES_PASAJE = ("pasaje", "excerpt", "extracto", "cita_textual")
_CLAVES_CONTENIDO = ("content", "contenido", "texto", "texto_completo", "full_text")


def _campo(src: dict, alias: tuple[str, ...]) -> str:
    """El primer alias con valor no vacío, mirando también el sub-dict `metadata`."""
    fuentes: list[dict] = [src]
    meta = src.get("metadata")
    if isinstance(meta, dict):
        fuentes.append(meta)
    ident = src.get("identificacion")
    if isinstance(ident, dict):
        fuentes.insert(0, ident)
    for cont in fuentes:
        for a in alias:
            v = cont.get(a)
            if v not in (None, "", [], {}):
                return str(v).strip()
    return ""


def identificacion(src: dict) -> dict:
    """El bloque de identificación mínima de una fuente y qué le falta. PURA.

    Devuelve `{"tipo","numero","fecha","faltan":[...]}`. Una providencia citada como
    «sentencia de 2013», sin radicado, no puede volver a colarse en silencio.
    """
    if not isinstance(src, dict):
        return {"tipo": "", "numero": "", "fecha": "",
                "faltan": [n for n, _ in CAMPOS_IDENTIFICACION]}
    bloque: dict = {}
    faltan: list[str] = []
    for nombre, alias in CAMPOS_IDENTIFICACION:
        valor = _campo(src, alias)
        bloque[nombre] = valor
        if not valor:
            faltan.append(nombre)
    bloque["faltan"] = faltan
    return bloque


def similitud(pasaje: str, contenido: str) -> float:
    """Cuánto del PASAJE aparece, en orden, dentro del CONTENIDO. 0.0–1.0. PURA.

    Por tokens y con los bloques comunes de `difflib` —conserva el orden, así que un
    pasaje que solo comparte vocabulario suelto con la fuente no pasa—. Es la
    comprobación que el hash no puede hacer: el sello prueba que el archivo no cambió,
    no que diga lo que dice decir.
    """
    a = _tokens(pasaje)
    b = _tokens(contenido)
    if not a:
        return 0.0
    if not b:
        return 0.0
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    comunes = sum(bloque.size for bloque in matcher.get_matching_blocks())
    return min(1.0, comunes / len(a))


def revisar_fuentes(sources: Optional[list], *,
                    umbral: Optional[float] = None,
                    exigir: Optional[bool] = None) -> Optional[dict]:
    """§23 · Coteja TEXTO contra fuente y exige identificación mínima. PURA y fail-soft.

    - `pasaje_no_coincide`: el texto que la fuente dice citar no está en el contenido del
      que dice salir (similitud por debajo del umbral). Es el defecto de las 17/36.
    - `sin_identificacion`: falta tipo, número/radicado o fecha. Con `exigir=True` la
      fuente queda marcada como EXCLUIDA con su razón honesta; en modo AVISO (default)
      entra igual y solo se informa.
    - `no_verificables`: la fuente no trae contenido contra el cual cotejar. Se dice; no
      se cuenta como verificada ni como defecto.

    Devuelve cobertura incluso sin hallazgos; None solo si no hay fuentes.
    """
    filas = [s for s in (sources or []) if isinstance(s, dict)]
    if not filas:
        return None
    umbral_real = float(config.MIA_FUENTE_SIMILITUD_UMBRAL if umbral is None else umbral)
    exigir_real = bool(config.MIA_FUENTE_IDENTIFICACION_EXIGIR if exigir is None else exigir)

    no_coincide: list[dict] = []
    sin_id: list[dict] = []
    no_verificables: list[str] = []
    verificadas = 0

    for src in filas:
        ref = str(src.get("referencia") or src.get("titulo") or "").strip() or "(sin referencia)"
        ident = identificacion(src)
        if ident["faltan"]:
            faltan_txt = ", ".join(ident["faltan"])
            sin_id.append({
                "referencia": ref,
                "faltan": ident["faltan"],
                "razon": (f"No se puede identificar la fuente: falta {faltan_txt}. "
                          "Una providencia sin número ni fecha no es citable."),
                "excluida": exigir_real,
            })
        pasaje = _campo(src, _CLAVES_PASAJE)
        contenido = _campo(src, _CLAVES_CONTENIDO)
        if not pasaje or not contenido:
            no_verificables.append(ref)
            continue
        sim = similitud(pasaje, contenido)
        if sim < umbral_real:
            no_coincide.append({
                "referencia": ref,
                "similitud": round(sim, 3),
                "razon": ("El texto que esta fuente aporta no corresponde a la norma o "
                          "providencia que dice citar. El sello del archivo coincide; el "
                          "contenido, no."),
                "excluida": exigir_real,
            })
        else:
            verificadas += 1

    partes: list[str] = []
    if no_coincide:
        partes.append(
            f"{len(no_coincide)} de las {len(filas)} fuentes traen un texto que no "
            "corresponde a la norma que dicen citar: "
            + ", ".join(d["referencia"] for d in no_coincide[:5])
            + ("." if len(no_coincide) <= 5 else " y otras."))
    if sin_id:
        partes.append(
            f"{len(sin_id)} no se pueden identificar por completo (falta tipo, número o "
            "fecha): " + ", ".join(d["referencia"] for d in sin_id[:5])
            + ("." if len(sin_id) <= 5 else " y otras."))
    if no_verificables:
        partes.append(f"{len(no_verificables)} fuentes no tienen original textual para cotejar; su contenido sigue sin verificar.")
    if no_coincide or sin_id:
        partes.append("Verifica esas fuentes antes de apoyarte en ellas."
                      if not exigir_real else "Esas fuentes no entraron al escrito.")

    return {
        "estado": ("exigido" if exigir_real else "aviso") if no_coincide or sin_id else "cobertura",
        "cobertura_completa": verificadas == len(filas) and not sin_id,
        "no_verificables_total": len(no_verificables),
        "umbral": umbral_real,
        "total": len(filas),
        "verificadas": verificadas,
        "pasaje_no_coincide": no_coincide,
        "sin_identificacion": sin_id,
        "no_verificables": no_verificables[:20],
        "aviso": " ".join(partes),
    }


def filtrar_fuentes(sources: Optional[list], revision: Optional[dict]) -> list[dict]:
    """Las fuentes que SÍ entran al redactor, según la revisión de `revisar_fuentes`.

    En modo AVISO (default) devuelve la lista tal cual: la barrera nace informando. Con
    `exigir` activo retira las fuentes marcadas como excluidas, cada una con su razón ya
    escrita en el informe.
    """
    filas = [s for s in (sources or []) if isinstance(s, dict)]
    if not isinstance(revision, dict) or revision.get("estado") != "exigido":
        return filas
    fuera = {
        str(d.get("referencia") or "")
        for grupo in ("pasaje_no_coincide", "sin_identificacion")
        for d in (revision.get(grupo) or [])
        if isinstance(d, dict) and d.get("excluida")
    }
    if not fuera:
        return filas
    return [s for s in filas
            if str(s.get("referencia") or s.get("titulo") or "").strip() not in fuera]
