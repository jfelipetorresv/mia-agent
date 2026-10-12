"""Mia · eval.banco04.custodia — cargador de la custodia del banco 0.4 (§2.3 y §10.2 ítem 3).

Lee la carpeta de custodia (casos voluminosos V1-V4, claves de respuesta, conjuntos de mutaciones,
semilla HMAC) SOLO con el propósito de medición, verifica CADA hash contra el manifiesto del
repositorio (`custodia_manifest.json`) y FALLA CERRADO ante cualquier discrepancia. El formato
(AES-256-GCM, llave protegida con DPAPI de usuario) está en `docs/banco04-custodia-formato.md`.

Reglas que este módulo hace cumplir:
  · propósito: solo `PROPOSITO_MEDICION` (mismo string que el del holdout visible, barrera de
    INTENCIÓN: no es criptográfica). Otro propósito → `CustodiaPropositoInvalido` ANTES de
    mirar el entorno o el disco.
  · ubicación: la carpeta SOLO sale de `MIA_BANCO04_CUSTODIA`. No hay ruta por defecto: sin la
    variable, o con una carpeta que falte, se detiene. Una carpeta DENTRO del repositorio se
    rechaza (P6: ningún archivo de custodia bajo el repo).
  · hashes: sha256 del archivo cifrado y del blob DPAPI se comprueban al ABRIR (todos los
    artefactos, aunque no se vayan a usar); el sha256 en claro, la autenticación GCM (con el
    id del artefacto como AAD), la reserialización canónica, el esquema y las invariantes
    semánticas, al ENTREGAR cada artefacto.
  · lo descifrado vive solo en memoria: nunca se escribe a disco ni bajo el repo ni bajo
    `MIA_HOME`; `cerrar()` (o salir del `with`) lo suelta (§2.3: «se borran al terminar»).

Límite declarado (§2.3): DPAPI de usuario no protege frente a un proceso del mismo usuario de
Windows, y los hashes delatan una alteración, NO una lectura.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from ctypes import wintypes
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

PROPOSITO_MEDICION = "medicion_final"
ENV_CUSTODIA = "MIA_BANCO04_CUSTODIA"


def _protocolo_custodia() -> str:
    """Versión PROPIA de la custodia (`protocolo.PROTOCOLO_CUSTODIA`): la AAD y el manifiesto están
    ligados a ella (v1.2) aunque el protocolo avance. Si la constante no existe, FALLA CERRADO."""
    try:
        from .protocolo import PROTOCOLO_CUSTODIA
    except ImportError as exc:
        raise CustodiaError("protocolo.PROTOCOLO_CUSTODIA no existe: la custodia no se abre sin su "
                            "versión declarada (fail-closed).") from exc
    if not isinstance(PROTOCOLO_CUSTODIA, str) or not PROTOCOLO_CUSTODIA:
        raise CustodiaError("protocolo.PROTOCOLO_CUSTODIA no es una versión válida.")
    return PROTOCOLO_CUSTODIA
ESQUEMA_MANIFIESTO = "banco04-custodia-manifest/v1"
_MANIFEST_PATH = Path(__file__).with_name("custodia_manifest.json")
_REPO_ROOT = Path(__file__).resolve().parents[4]   # banco04 → eval → mia → backend → repo
_LLAVE_BYTES = 32
_NONCE_BYTES = 12
_TAG_BYTES = 16


class CustodiaError(RuntimeError):
    """La custodia no se pudo abrir o un artefacto no verifica: se detiene (fail-closed)."""


class CustodiaPropositoInvalido(CustodiaError):
    """Se pidió la custodia para algo que no es medición."""


# ── utilidades ────────────────────────────────────────────────────────────────
def _sha256(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _canonico(obj: Any) -> bytes:
    """Serialización canónica del manifiesto: la que define el hash en claro de los JSON."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _dentro_de(hijo: Path, padre: Path) -> bool:
    try:
        hijo.relative_to(padre)
        return True
    except ValueError:
        return False


# ── DPAPI (Windows, ámbito del usuario actual) ────────────────────────────────
class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


_CRYPTPROTECT_UI_FORBIDDEN = 0x1


def desproteger_dpapi(blob: bytes) -> bytes:
    """`CryptUnprotectData` en ámbito de usuario, sin entropía adicional y sin UI.

    Solo descifra el mismo usuario de Windows en la misma máquina (§2.3)."""
    if os.name != "nt":
        raise CustodiaError("DPAPI solo existe en Windows: la custodia no se puede abrir aquí.")
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p, ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DATA_BLOB)]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    buf = ctypes.create_string_buffer(blob, len(blob))
    entrada = _DATA_BLOB(len(blob), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    salida = _DATA_BLOB()
    if not crypt32.CryptUnprotectData(ctypes.byref(entrada), None, None, None, None,
                                      _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(salida)):
        raise CustodiaError("DPAPI no pudo descifrar la llave (otro usuario/máquina o blob alterado).")
    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        kernel32.LocalFree(salida.pbData)


# ── manifiesto ────────────────────────────────────────────────────────────────
def cargar_manifiesto(ruta: Path | None = None) -> dict:
    ruta = Path(ruta or _MANIFEST_PATH)
    try:
        manifiesto = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CustodiaError(f"No se pudo leer el manifiesto de la custodia ({ruta}): {exc}") from exc
    if manifiesto.get("schema") != ESQUEMA_MANIFIESTO or manifiesto.get("protocolo") != _protocolo_custodia():
        raise CustodiaError("El manifiesto no es el de este protocolo (schema/protocolo).")
    arts = manifiesto.get("artefactos")
    if not isinstance(arts, list) or not arts:
        raise CustodiaError("El manifiesto no lista artefactos.")
    ids = [a.get("id") for a in arts]
    if len(set(ids)) != len(ids) or not all(isinstance(i, str) and i for i in ids):
        raise CustodiaError("El manifiesto tiene ids de artefacto repetidos o vacíos.")
    for a in arts:
        archivo = str(a.get("archivo") or "")
        if (not archivo or archivo != Path(archivo).name or "/" in archivo or "\\" in archivo
                or archivo in (".", "..")):
            raise CustodiaError(f"Nombre de archivo no permitido en el manifiesto: {archivo!r}")
        for campo in ("sha256_claro", "sha256_cifrado", "tipo"):
            if not a.get(campo):
                raise CustodiaError(f"Artefacto {a.get('id')!r} sin {campo} en el manifiesto.")
    cif = manifiesto.get("cifrado") or {}
    llave = cif.get("llave") or {}
    if cif.get("algoritmo") != "AES-256-GCM" or not llave.get("archivo") or not llave.get(
            "sha256_blob_dpapi"):
        raise CustodiaError("El manifiesto no describe el cifrado esperado (AES-256-GCM + llave DPAPI).")
    return manifiesto


# ── la custodia abierta ───────────────────────────────────────────────────────
class Custodia:
    """Custodia abierta y verificada. Entrega los artefactos descifrados, solo en memoria."""

    def __init__(self, carpeta: Path, manifiesto: dict, llave: bytes) -> None:
        self._carpeta = carpeta
        self._m = manifiesto
        self._llave: Optional[bytearray] = bytearray(llave)
        self._arts = {a["id"]: a for a in manifiesto["artefactos"]}
        self._claro: dict[str, bytes] = {}
        self._objs: dict[str, Any] = {}

    # -- ciclo de vida -------------------------------------------------------------
    def __enter__(self) -> "Custodia":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.cerrar()

    def cerrar(self) -> None:
        """Suelta lo descifrado y la llave (§2.3: las piezas descifradas se borran al terminar)."""
        self._claro.clear()
        self._objs.clear()
        if self._llave is not None:
            for i in range(len(self._llave)):
                self._llave[i] = 0
        self._llave = None

    @property
    def cerrada(self) -> bool:
        return self._llave is None

    # -- artefactos ----------------------------------------------------------------
    def ids(self, tipo: Optional[str] = None) -> list[str]:
        return [i for i, a in self._arts.items() if tipo is None or a["tipo"] == tipo]

    def artefacto(self, id_: str) -> bytes:
        """Bytes en claro del artefacto, tras autenticar GCM y comprobar su sha256."""
        if self._llave is None:
            raise CustodiaError("La custodia está cerrada.")
        a = self._arts.get(id_)
        if a is None:
            raise CustodiaError(f"Artefacto desconocido: {id_!r}")
        if id_ in self._claro:
            return self._claro[id_]
        raw = _leer(self._carpeta / a["archivo"], a["id"])
        if _sha256(raw) != a["sha256_cifrado"]:
            raise CustodiaError(f"{id_}: el archivo cifrado no coincide con el manifiesto.")
        if len(raw) < _NONCE_BYTES + _TAG_BYTES:
            raise CustodiaError(f"{id_}: archivo cifrado demasiado corto.")
        aad = f"{_protocolo_custodia()}|{id_}".encode("utf-8")
        try:
            from cryptography.exceptions import InvalidTag
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            claro = AESGCM(bytes(self._llave)).decrypt(raw[:_NONCE_BYTES], raw[_NONCE_BYTES:], aad)
        except InvalidTag as exc:
            raise CustodiaError(f"{id_}: falló la autenticación GCM (contenido, id o llave "
                                "alterados).") from exc
        if _sha256(claro) != a["sha256_claro"]:
            raise CustodiaError(f"{id_}: el contenido descifrado no coincide con su sha256 en claro.")
        self._claro[id_] = claro
        return claro

    def objeto(self, id_: str) -> Any:
        """JSON del artefacto, validado: reserialización canónica, esquema e invariantes."""
        if id_ in self._objs:
            return self._objs[id_]
        obj = self._objeto_crudo(id_)
        _invariantes(self, id_, self._arts[id_]["tipo"], obj)
        self._objs[id_] = obj
        return obj

    def _objeto_crudo(self, id_: str) -> Any:
        """Como `objeto`, sin las invariantes entre artefactos (evita la recursión ajuste↔reservado)."""
        a = self._arts.get(id_)
        if a is None:
            raise CustodiaError(f"Artefacto desconocido: {id_!r}")
        esquema = a.get("esquema")
        if not esquema:
            raise CustodiaError(f"{id_}: no es un artefacto JSON (sin esquema).")
        claro = self.artefacto(id_)
        if claro[:3] == b"\xef\xbb\xbf" or claro.endswith(b"\n"):
            raise CustodiaError(f"{id_}: BOM o salto final: no es la serialización canónica.")
        try:
            obj = json.loads(claro.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise CustodiaError(f"{id_}: no es JSON UTF-8 válido: {exc}") from exc
        if _canonico(obj) != claro:
            raise CustodiaError(f"{id_}: la reserialización canónica no da los mismos bytes.")
        _validar_esquema(id_, obj, (self._m.get("esquemas") or {}).get(esquema))
        return obj

    # -- registros de la medición (cifrado con la MISMA llave y algoritmo de la custodia) ----------
    def cifrar_registro(self, id_: str, datos: bytes) -> bytes:
        """Cifra un REGISTRO producido durante la medición (salida cruda de un caso custodiado)
        con la llave de la custodia: AES-256-GCM, `nonce(12) || ct || tag(16)` y
        AAD `banco04-v1.2|registro|<id>` (otro id o otro contenido no autentica). §2.3: las
        salidas crudas del estrato custodiado no se guardan en claro; al repo solo van hashes."""
        if self._llave is None:
            raise CustodiaError("La custodia está cerrada.")
        if not id_ or not isinstance(datos, (bytes, bytearray)):
            raise CustodiaError("cifrar_registro exige un id y bytes.")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = os.urandom(_NONCE_BYTES)
        aad = f"{_protocolo_custodia()}|registro|{id_}".encode("utf-8")
        return nonce + AESGCM(bytes(self._llave)).encrypt(nonce, bytes(datos), aad)

    def descifrar_registro(self, id_: str, raw: bytes) -> bytes:
        if self._llave is None:
            raise CustodiaError("La custodia está cerrada.")
        if len(raw) < _NONCE_BYTES + _TAG_BYTES:
            raise CustodiaError(f"registro {id_}: demasiado corto.")
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        try:
            return AESGCM(bytes(self._llave)).decrypt(
                raw[:_NONCE_BYTES], raw[_NONCE_BYTES:], f"{_protocolo_custodia()}|registro|{id_}".encode("utf-8"))
        except InvalidTag as exc:
            raise CustodiaError(f"registro {id_}: falló la autenticación GCM.") from exc

    # -- accesos de alto nivel -----------------------------------------------------
    def casos(self) -> list:
        """Los casos V1-V4 como `GoldenCase` (`rubric` y `recall_markers` vacíos a propósito)."""
        from ..cases import GoldenCase, GoldenCaseDoc

        salida = []
        for id_ in self.ids("caso"):
            o = self.objeto(id_)
            salida.append(GoldenCase(
                id=o["id"], title=o["title"], message=o["message"],
                documents=tuple(GoldenCaseDoc(filename=d["filename"], chunks=tuple(d["chunks"]))
                                for d in o["documents"]),
                profile=dict(o["profile"]), expect_reaches_draft=bool(o["expect_reaches_draft"]),
                synthetic=True, rubric={}, recall_markers=()))
        return salida

    def jurisdicciones(self) -> dict[str, list[str]]:
        """Ordenamiento configurado por caso. `[]` = despacho sin ordenamiento (`generic`).
        El runner lo lleva a `tenant_settings.config['jurisdictions']` del despacho efímero."""
        return {self.objeto(i)["id"]: list(self.objeto(i)["jurisdicciones"]) for i in self.ids("caso")}

    def clave(self, case_id: str) -> dict:
        for id_ in self.ids("clave"):
            o = self.objeto(id_)
            if o["case_id"] == case_id:
                return o
        raise CustodiaError(f"No hay clave de respuesta custodiada para {case_id!r}")

    def mutaciones(self, conjunto: str) -> dict:
        """`ajuste` (depurar prompts) o `reservado` (UN solo uso con todo congelado, §8.6)."""
        for id_ in self.ids("mutaciones_ajuste") + self.ids("mutaciones_reservadas"):
            o = self.objeto(id_)
            if o["conjunto"] == conjunto:
                return o
        raise CustodiaError(f"No hay conjunto de mutaciones {conjunto!r}")

    def semilla_hmac(self) -> bytes:
        ids = self.ids("semilla")
        if len(ids) != 1:
            raise CustodiaError("La custodia debe tener exactamente una semilla.")
        return bytes.fromhex(self.objeto(ids[0])["hmac_key_hex"])


def _leer(ruta: Path, id_: str) -> bytes:
    try:
        return ruta.read_bytes()
    except OSError as exc:
        raise CustodiaError(f"{id_}: falta el archivo de custodia ({ruta.name}): {exc}") from exc


def _validar_esquema(id_: str, obj: Any, esquema: Optional[Mapping]) -> None:
    if not esquema:
        raise CustodiaError(f"{id_}: el manifiesto no trae el esquema para validar.")
    try:
        import jsonschema
    except ImportError as exc:                       # sin validador no se entrega nada
        raise CustodiaError("jsonschema no está instalado: no se puede validar la custodia.") from exc
    try:
        jsonschema.Draft202012Validator(esquema).validate(obj)
    except jsonschema.ValidationError as exc:
        raise CustodiaError(f"{id_}: no cumple su esquema: {exc.message[:200]}") from exc
    except jsonschema.SchemaError as exc:
        raise CustodiaError(f"{id_}: el esquema del manifiesto es inválido: {exc.message[:200]}") from exc


# ── invariantes semánticas del manifiesto ─────────────────────────────────────
def _invariantes(c: Custodia, id_: str, tipo: str, obj: Mapping) -> None:
    if tipo == "caso":
        _inv_caso(id_, obj)
    elif tipo == "clave":
        _inv_clave(c, id_, obj)
    elif tipo in ("mutaciones_ajuste", "mutaciones_reservadas"):
        _inv_mutaciones(c, id_, tipo, obj)


def _inv_caso(id_: str, o: Mapping) -> None:
    total = sum(len(d["chunks"]) for d in o["documents"])
    if o["n_fragmentos"] != total:
        raise CustodiaError(f"{id_}: n_fragmentos ({o['n_fragmentos']}) ≠ suma de fragmentos ({total}).")
    if o["recall_markers"]:
        raise CustodiaError(f"{id_}: recall_markers debe ir vacío (viven en la clave).")


def _inv_clave(c: Custodia, id_: str, o: Mapping) -> None:
    # solo las claves de los V1-V4 se cruzan con su caso custodiado
    caso_id = id_[len("clave-"):] if id_.startswith("clave-") else None
    if caso_id not in c._arts:
        return
    caso = c.objeto(caso_id)
    if o["case_id"] != caso["id"]:
        raise CustodiaError(f"{id_}: case_id {o['case_id']!r} no coincide con el caso {caso['id']!r}.")
    if o["n_fragmentos"] != caso["n_fragmentos"]:
        raise CustodiaError(f"{id_}: n_fragmentos no coincide con el caso.")
    por_doc = {d["filename"]: len(d["chunks"]) for d in caso["documents"]}
    if list(o["orden_documentos"]) != [d["filename"] for d in caso["documents"]]:
        raise CustodiaError(f"{id_}: orden_documentos no coincide con el del caso.")
    chunks = {d["filename"]: list(d["chunks"]) for d in caso["documents"]}
    for h in o["hechos_materiales"]:
        n = por_doc.get(h["documento"])
        if n is None or any(f >= n for f in h["fragmentos"]):
            raise CustodiaError(f"{id_}: el hecho {h['id']!r} apunta a un documento o fragmento "
                                "que no existe en el caso.")
        invariantes_rangos_hecho(id_, h, chunks[h["documento"]])


def invariantes_rangos_hecho(id_: str, h: Mapping, chunks: list) -> None:
    """R2-A-N2: cada rango de un hecho es un intervalo VÁLIDO de un fragmento que el hecho declara:
    0 ≤ inicio < fin ≤ len(texto del fragmento). Invertido, vacío o fuera del fragmento → la clave
    no se entrega. Pura."""
    frs = set(h.get("fragmentos") or [])
    for r in h.get("rangos") or []:
        f, a, b = r.get("fragmento"), r.get("inicio"), r.get("fin")
        if not all(isinstance(x, int) and not isinstance(x, bool) for x in (f, a, b)):
            raise CustodiaError(f"{id_}: rango no entero en el hecho {h.get('id')!r}.")
        if f not in frs or not 0 <= f < len(chunks):
            raise CustodiaError(f"{id_}: rango de un fragmento que el hecho {h.get('id')!r} no declara.")
        if not 0 <= a < b <= len(chunks[f]):
            raise CustodiaError(f"{id_}: rango [{a}, {b}) inválido para el fragmento {f} "
                                f"({len(chunks[f])} caracteres) del hecho {h.get('id')!r}.")


def fuentes_de_otro_ordenamiento(item: Mapping) -> list[str]:
    """Refs de las fuentes del corpus del ítem que DECLARAN un ordenamiento fuera de los
    configurados del ítem (la «norma respaldada pero no habilitada» de §12.5). Pura."""
    jur = list(item.get("jurisdicciones") or [])
    return [str(f.get("ref")) for f in (item.get("material") or {}).get("fuentes_corpus") or []
            if isinstance(f, Mapping) and f.get("jurisdiccion") and f["jurisdiccion"] not in jur]


def c08_admisible(item: Mapping) -> bool:
    """R2-C-N1: una fuga (C08) cabe en un ítem SIN ordenamiento configurado (`jurisdicciones ==
    []`) o en un despacho configurado para OTRO ordenamiento, siempre que el material traiga la
    fuente no habilitada (ordenamiento declarado ∉ jurisdicciones): sin ella no hay forma de
    comprobar que la mutación es una fuga y no un respaldo legítimo. Pura."""
    return item.get("jurisdicciones") == [] or bool(fuentes_de_otro_ordenamiento(item))


def invariantes_mutaciones_obj(o: Mapping, *, reservado: bool) -> None:
    """Invariantes de un conjunto de mutaciones (spans, C08, mínimos del reservado). Pura."""
    for it in o["items"]:
        por_campo: dict[str, list[tuple[int, int]]] = {}
        for v in it["verdad"]:
            texto = it["salida"][v["campo"]]
            if not (0 <= v["inicio"] < v["fin"] <= len(texto)) or texto[v["inicio"]:v["fin"]] != v["literal"]:
                raise CustodiaError(f"{it['id']}/{v['id']}: salida[campo][inicio:fin] ≠ literal.")
            por_campo.setdefault(v["campo"], []).append((v["inicio"], v["fin"]))
            if v.get("categoria") == "C08" and not c08_admisible(it):
                raise CustodiaError(f"{it['id']}/{v['id']}: C08 solo en items sin ordenamiento "
                                    "configurado o con una fuente de OTRO ordenamiento (R2-C-N1).")
        for campo, spans in por_campo.items():
            spans.sort()
            for (a0, a1), (b0, _b1) in zip(spans, spans[1:]):
                if b0 < a1:
                    raise CustodiaError(f"{it['id']}: spans solapados en {campo}.")
    if reservado:
        verdad = [v for it in o["items"] for v in it["verdad"]]
        defectos = sum(1 for v in verdad if v["clase"] == "defecto")
        controles = sum(1 for v in verdad if v["clase"] == "control")
        c12 = sum(1 for v in verdad if v.get("categoria") == "C12"
                  and float(v.get("proporcion_en_oracion", 1.0)) < 0.20)
        if defectos < 30 or controles < 30 or c12 < 10:
            raise CustodiaError("el reservado no cumple los mínimos (≥30 defectos, ≥30 controles, "
                                f"≥10 C12 con proporción < 0,20): {defectos}/{controles}/{c12}.")


def _inv_mutaciones(c: Custodia, id_: str, tipo: str, o: Mapping) -> None:
    invariantes_mutaciones_obj(o, reservado=(tipo == "mutaciones_reservadas"))
    # ajuste y reservado: material DISJUNTO (ningún fragmento de expediente compartido)
    otro = "mutaciones_reservadas" if tipo == "mutaciones_ajuste" else "mutaciones_ajuste"
    for id2 in c.ids(otro):
        o2 = c._objeto_crudo(id2)
        def piezas(obj: Mapping) -> set[str]:
            return {x for it in obj["items"] for d in it["material"]["documentos"] for x in d["chunks"]}
        if piezas(o) & piezas(o2):
            raise CustodiaError(f"{id_} y {id2} comparten material: deben ser disjuntos.")


# ── puerta de entrada ─────────────────────────────────────────────────────────
def abrir(proposito: str, *, environ: Optional[Mapping[str, str]] = None,
          repo_root: Optional[Path] = None, manifest_path: Optional[Path] = None,
          desproteger: Optional[Callable[[bytes], bytes]] = None) -> Custodia:
    """Abre la custodia para MEDIR. Cualquier discrepancia levanta `CustodiaError`."""
    if proposito != PROPOSITO_MEDICION:
        raise CustodiaPropositoInvalido(
            f"La custodia solo se abre para '{PROPOSITO_MEDICION}' (se pidió {proposito!r}): "
            "no se usa para arreglar, calibrar ni depurar.")
    entorno = os.environ if environ is None else environ
    ruta = (entorno.get(ENV_CUSTODIA) or "").strip()
    if not ruta:
        raise CustodiaError(f"{ENV_CUSTODIA} no está definida: no hay ruta por defecto.")
    carpeta = Path(ruta).expanduser()
    if not carpeta.is_dir():
        raise CustodiaError(f"La carpeta de custodia no existe: {carpeta}")
    carpeta = carpeta.resolve()
    repo = Path(repo_root or _REPO_ROOT).resolve()
    if carpeta == repo or _dentro_de(carpeta, repo):
        raise CustodiaError("La carpeta de custodia está bajo el repositorio: debe quedar FUERA "
                            "(§2.3).")
    manifiesto = cargar_manifiesto(manifest_path)
    meta = manifiesto["cifrado"]["llave"]
    blob = _leer(carpeta / meta["archivo"], "llave")
    if _sha256(blob) != meta["sha256_blob_dpapi"]:
        raise CustodiaError("El blob DPAPI de la llave no coincide con el manifiesto.")
    llave = (desproteger or desproteger_dpapi)(blob)
    if len(llave) != int(meta.get("longitud_bytes", _LLAVE_BYTES)) or len(llave) != _LLAVE_BYTES:
        raise CustodiaError("La llave descifrada no mide 32 bytes (AES-256).")
    # TODOS los archivos cifrados deben estar y coincidir con el manifiesto, se usen o no.
    for a in manifiesto["artefactos"]:
        raw = _leer(carpeta / a["archivo"], a["id"])
        if _sha256(raw) != a["sha256_cifrado"]:
            raise CustodiaError(f"{a['id']}: el archivo cifrado no coincide con el manifiesto.")
    return Custodia(carpeta, manifiesto, llave)
