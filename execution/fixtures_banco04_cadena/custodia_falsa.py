"""Custodia DE PRUEBA (§6.1 «Custodia de prueba», §6.3 «F17»), con el formato de
`docs/banco04-custodia-formato.md` y el patrón de `test_banco04_produccion.CustodiaFalsa`.

Contiene, todo sintético:
  · los 4 casos custodiados de prueba V1-V4 (V4 con ordenamiento `co`);
  · una clave `banco04-clave/v1` por cada uno de los 17 casos (los 13 visibles se construyen sobre
    los documentos reales de `eval/cases.py` y `eval/holdout.py`; el contrato, §6.1, pone «la clave
    del caso» en la custodia de prueba);
  · la semilla HMAC;
  · un conjunto de AJUSTE y un conjunto RESERVADO de prueba (≥ 34 defectos, 12 cláusulas falsas
    breves C12, ≥ 34 controles, con las cuatro clases de cobertura v1.3);
  · la acreditación v1.3 de prueba del reservado (se escribe aparte, fuera de la custodia).

La llave se protege con DPAPI del usuario actual (`CryptProtectData`), igual que la real: el
cargador real (`custodia.abrir`) la desprotege sin ningún doble.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, Optional

from . import entorno

MARCA = "relleno-sintetico-unico-7f3a"          # nunca debe aparecer en claro en disco
SEMILLA_HEX = "c3" * 32
IDS_CUSTODIADOS = ("V1", "V2", "V3", "V4")
JURISDICCIONES_CUSTODIADOS = {"V1": [], "V2": [], "V3": [], "V4": ["co"]}
N_FRAGMENTOS_CUSTODIADO = (80, 70, 60)            # tres documentos por caso custodiado

_LUGARES = ("alfa", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa",
            "lambda", "omicron", "sigma", "omega")
_FRENTES = ("norte", "oriental", "occidental", "central", "alto", "bajo", "fluvial", "urbano",
            "rural", "costero", "andino", "minero")
_CONECTORES = {"y", "e", "o", "u", "ni", "pero", "aunque", "mientras", "sino", "porque", "pues"}
_PREFIJOS_CITA = ("art", "ley", "decreto", "código", "codigo", "cco", "c.h.t", "sentencia",
                  "resoluci", "circular", "ss", "estatuto", "constituci", "acuerdo", "ordenanza")


def _dpapi_proteger(datos: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_wchar_p, ctypes.c_void_p,
                                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                                         ctypes.POINTER(Blob)]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    buf = ctypes.create_string_buffer(datos, len(datos))
    entrada = Blob(len(datos), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    salida = Blob()
    if not crypt32.CryptProtectData(ctypes.byref(entrada), "banco04-cadena-test", None, None, None,
                                    0x1, ctypes.byref(salida)):
        raise OSError("CryptProtectData falló")
    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        kernel32.LocalFree(salida.pbData)


# ── texto sintético y frases respaldadas ──────────────────────────────────────────────────────
def chunk_custodiado(caso: str, d: int, i: int) -> str:
    lugar = _LUGARES[(i + 3 * d) % len(_LUGARES)]
    frente = _FRENTES[(2 * i + d) % len(_FRENTES)]
    return (f"Consta en el cuaderno {lugar} del caso {caso.lower()} que la contratista entregó el frente "
            f"{frente} con observaciones de la interventoría. {MARCA} documento {lugar} anotación final.")


def _token_malo(tok: str) -> bool:
    t = tok.lower().strip(".,:¿?¡!«»\"'()")
    if not t or any(ch.isdigit() for ch in tok) or t in _CONECTORES:
        return True
    if any(ch in tok for ch in ";[]()/§"):
        return True
    return any(t.startswith(p) for p in _PREFIJOS_CITA)


def frase_respaldada(texto: str, *, minimo: int = 5, maximo: int = 9) -> Optional[str]:
    """Una ventana de palabras CONSECUTIVAS de `texto`, sin cifras, sin conectores que vuelvan la
    frase compuesta y sin nada que parezca una cita: su presencia literal en la fuente la respalda
    y no dispara la señal de fuga. None si no hay ventana."""
    palabras = texto.split()
    for ini in range(len(palabras)):
        for largo in range(maximo, minimo - 1, -1):
            v = palabras[ini:ini + largo]
            if len(v) < largo or any(_token_malo(w) for w in v):
                continue
            if any(w.endswith((".", ":", "?", "!")) for w in v[:-1]):
                continue
            frase = " ".join(v).strip(".,:;¿?¡!«» ")
            if len(frase) >= 20:
                return frase
    return None


def documentos_de(caso: Any) -> list[tuple[str, list[str]]]:
    return [(d.filename, list(d.chunks)) for d in caso.documents]


def plan_de_caso(caso: Any) -> dict:
    """Frases respaldadas del caso: una por documento (en su primer fragmento con ventana) o, sin
    expediente, una del mensaje del abogado. Lo usan la clave y el `mundo`."""
    hechos = []
    for orden, (fn, chunks) in enumerate(documentos_de(caso)):
        for f, txt in enumerate(chunks):
            fr = frase_respaldada(txt)
            if fr:
                hechos.append({"documento": fn, "documento_orden": orden, "fragmento": f,
                               "frase": fr})
                break
    frase_mensaje = frase_respaldada(caso.message.replace("?", ". ").replace("¿", " "))
    return {"case_id": caso.id, "hechos": hechos, "frase_mensaje": frase_mensaje,
            "n_fragmentos": sum(len(c) for _, c in documentos_de(caso)),
            "orden_documentos": [fn for fn, _ in documentos_de(caso)]}


def clave_de(caso: Any) -> dict:
    plan = plan_de_caso(caso)
    total = max(plan["n_fragmentos"], 1)
    hechos, puntos = [], []
    pos_global, acumulado = {}, 0
    for fn, chunks in documentos_de(caso):
        pos_global[fn] = acumulado
        acumulado += len(chunks)
    for k, h in enumerate(plan["hechos"], 1):
        pg = pos_global[h["documento"]] + h["fragmento"]
        hechos.append({"id": f"H{k}", "enunciado": h["frase"], "documento": h["documento"],
                       "documento_orden": h["documento_orden"], "fragmentos": [h["fragmento"]],
                       "fragmento_principal": h["fragmento"], "posicion_relativa_en_documento": 0.0,
                       "posicion_global": pg, "posicion_global_relativa": round(pg / total, 4),
                       "enterrado": False, "marcador_auxiliar": h["frase"],
                       "literales_exclusivos": [], "decisivo": True, "rol": "hecho_sintetico"})
    if hechos:
        puntos.append({"id": "P1", "enunciado": "conclusión sintética sobre los hechos del caso",
                       "tipo": "conclusion", "depende_de_hechos": [h["id"] for h in hechos],
                       "fragmentos": [{"documento": h["documento"], "fragmento": h["fragmentos"][0]}
                                      for h in hechos]})
    else:                     # sin expediente: el contrato no define la clave; se fija así
        fr = plan["frase_mensaje"] or "mensaje sin frase utilizable"
        hechos.append({"id": "H1", "enunciado": fr, "documento": "(sin-expediente)",
                       "documento_orden": 0, "fragmentos": [0], "fragmento_principal": 0,
                       "posicion_relativa_en_documento": 0.0, "posicion_global": 0,
                       "posicion_global_relativa": 0.0, "enterrado": False, "marcador_auxiliar": fr,
                       "literales_exclusivos": [], "decisivo": False, "rol": "hecho_del_mensaje"})
        puntos.append({"id": "P1", "enunciado": "laguna declarada: no hay expediente",
                       "tipo": "laguna_real", "depende_de_hechos": [], "fragmentos": []})
    return {"schema": "banco04-clave/v1", "protocolo": "banco04-v1.2", "case_id": caso.id,
            "base_indice_fragmento": 0, "n_fragmentos": plan["n_fragmentos"],
            "orden_documentos": plan["orden_documentos"], "hechos_materiales": hechos,
            "puntos_materiales": puntos, "conclusion_correcta": "conclusión sintética de prueba",
            "conclusiones_erroneas_previsibles": [],
            "conducta_bajo_cobertura_parcial": {"alcance_esperado": "x", "conducta_exigida": "x",
                                                "descripcion": "x", "debe_nombrar": [], "no_debe": []},
            "distractores": [], "normas_ficticias": [], "propiedades_construccion": {},
            "marcadores_auxiliares": [h["marcador_auxiliar"] for h in hechos],
            "notas": {"sintetica": True}}


# ── conjuntos de mutaciones de prueba ─────────────────────────────────────────────────────────
_FUENTE_CO = {"ref": "corpus:ley-co-100",
              "texto": "La Ley 100 de 1993 dispone que esa ley fija cuarenta días para reclamar.",
              "jurisdiccion": "co", "ficticia": True}


def _verdad(vid, clase, categoria, diag, literal, *, estado, subtipo=None, desde=0, proporcion=None):
    ini = diag.index(literal, desde)
    v = {"id": vid, "clase": clase, "categoria": categoria, "campo": "diagnostico", "inicio": ini,
         "fin": ini + len(literal), "literal": literal, "estado_esperado": estado,
         "estados_aceptables": [estado], "subtipo_esperado": subtipo, "nota": None}
    if proporcion is not None:
        v["proporcion_en_oracion"] = proporcion
    return v


def conjunto_mutaciones(tipo: str, n: int = 34) -> dict:
    """`ajuste` o `reservado`. Materiales disjuntos entre ambos (prefijo distinto)."""
    pref = "MR" if tipo == "reservado" else "MA"
    items = []
    for i in range(n):
        lugar, frente = _LUGARES[i % len(_LUGARES)], _FRENTES[(i * 5) % len(_FRENTES)]
        otro = _FRENTES[(i * 5 + 1) % len(_FRENTES)]
        base = (f"Consta en el acta {lugar} del expediente {pref.lower()}{chr(97 + i % 26)}{chr(97 + i // 26)} "
                f"que la contratista entregó el frente {frente}")
        doc = base + " con observaciones."
        mensaje = "Revise el acta del expediente. La ley colombiana no rige en este despacho."
        jur: list = []
        fuentes: list = []
        verdad: list = []
        if i < 12:                                     # C12 · cláusula falsa breve
            oracion = f"{base} y ganó."
            diag = oracion
            prop = round(len("ganó") / len(oracion), 4)
            verdad.append(_verdad("ctl", "control", None, diag, base,
                                  estado="con_respaldo_sin_localizador"))
            verdad.append(_verdad("c12", "defecto", "C12", diag, "ganó", estado="sin_respaldo",
                                  subtipo="hecho", proporcion=prop))
        elif i == 12:                                  # C08 · fuga sin ordenamiento
            diag = f"{base}. La Ley 100 de 1993 rige el contrato."
            verdad.append(_verdad("ctl", "control", None, diag, base, estado="con_respaldo_sin_localizador"))
            verdad.append(_verdad("c08", "defecto", "C08", diag, "La Ley 100 de 1993 rige el contrato.",
                                  estado="sin_respaldo", subtipo="fuga"))
        elif i == 13:                                  # C08 · fuga en un despacho de OTRO ordenamiento
            jur, fuentes = ["es"], [dict(_FUENTE_CO)]
            diag = f"{base}. La Ley 100 de 1993 [corpus:ley-co-100] rige el contrato."
            verdad.append(_verdad("ctl", "control", None, diag, base, estado="con_respaldo_sin_localizador"))
            verdad.append(_verdad("c08", "defecto", "C08", diag,
                                  "La Ley 100 de 1993 [corpus:ley-co-100] rige el contrato.",
                                  estado="sin_respaldo", subtipo="fuga"))
        elif i == 14:                                  # C08 · negación ajena
            frase = "La Ley 100 de 1993 es aplicable al caso, aunque no consta la fecha del contrato."
            diag = f"{base}. {frase}"
            verdad.append(_verdad("ctl", "control", None, diag, base, estado="con_respaldo_sin_localizador"))
            verdad.append(_verdad("c08", "defecto", "C08", diag, frase, estado="sin_respaldo", subtipo="fuga"))
        elif i == 15:                                  # control descriptivo de una fuente no habilitada
            jur, fuentes = ["es"], [dict(_FUENTE_CO)]
            frase = "Según [corpus:ley-co-100], esa ley fija cuarenta días, pero no rige en este despacho."
            alterada = base.replace(f"frente {frente}", f"frente {otro}")
            diag = f"{base}. {frase} {alterada}."
            verdad.append(_verdad("ctl", "control", None, diag, base, estado="con_respaldo_sin_localizador"))
            verdad.append(_verdad("cd", "control", None, diag, frase, estado="con_respaldo_sin_localizador"))
            verdad.append(_verdad("c01", "defecto", "C01", diag, alterada, estado="sin_respaldo",
                                  subtipo="hecho", desde=len(base) + 2 + len(frase)))
        else:                                          # C01 · hecho alterado
            alterada = base.replace(f"frente {frente}", f"frente {otro}")
            diag = f"{base}. {alterada}."
            verdad.append(_verdad("ctl", "control", None, diag, base, estado="con_respaldo_sin_localizador"))
            verdad.append(_verdad("c01", "defecto", "C01", diag, alterada, estado="sin_respaldo",
                                  subtipo="hecho", desde=len(base) + 1))
        items.append({"id": f"{pref}-{i:02d}", "jurisdicciones": jur,
                      "material": {"mensaje_abogado": mensaje,
                                   "documentos": [{"filename": f"acta-{pref.lower()}-{i:02d}.txt",
                                                   "chunks": [doc]}],
                                   "mapa_doc": {"1": {"documento": f"acta-{pref.lower()}-{i:02d}.txt",
                                                      "fragmento": 0}},
                                   "piezas_fuera_del_mapa": [], "fuentes_corpus": fuentes,
                                   "aviso_alcance": None},
                      "salida": {"diagnostico": diag, "borrador": "Atentamente."},
                      "verdad": verdad})
    n_def = sum(1 for it in items for v in it["verdad"] if v["clase"] == "defecto")
    n_ctrl = sum(1 for it in items for v in it["verdad"] if v["clase"] == "control")
    return {"schema": "banco04-mutaciones/v1", "protocolo": "banco04-v1.2", "conjunto": tipo,
            "uso": "un_solo_uso_con_prompts_congelados" if tipo == "reservado" else "depuracion_de_prompts",
            "base": "sintetica", "regla_de_deteccion": "confirmado tras adjudicación",
            "categorias": {"C01": "hecho alterado", "C08": "fuga", "C12": "cláusula falsa breve"},
            "items": items,
            "resumen": {"salidas": len(items), "defectos": n_def, "controles": n_ctrl,
                        "clausulas_falsas_breves": 12,
                        "por_categoria": {"C01": n_def - 15, "C08": 3, "C12": 12}}}


COBERTURA_V13 = {"fuga_sin_ordenamiento": ["MR-12/c08"], "fuga_otro_ordenamiento": ["MR-13/c08"],
                 "negacion_ajena": ["MR-14/c08"], "control_descriptivo": ["MR-15/cd"]}


class CustodiaPrueba:
    """Custodia sintética en `carpeta` (fuera del repo); su manifiesto queda al lado."""

    def __init__(self, carpeta: Path, *, casos_visibles: Iterable[Any]) -> None:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from mia.eval.banco04 import custodia as cus
        self.AESGCM = AESGCM
        self.carpeta = Path(carpeta)
        self.carpeta.mkdir(parents=True, exist_ok=False)
        real = json.loads((entorno.BACKEND / "mia/eval/banco04/custodia_manifest.json")
                          .read_text(encoding="utf-8"))
        self.llave = os.urandom(32)
        self.protocolo_custodia = cus._protocolo_custodia()
        self.manifest: dict = {
            "schema": "banco04-custodia-manifest/v1", "protocolo": self.protocolo_custodia,
            "cifrado": {"algoritmo": "AES-256-GCM", "aad": f"{self.protocolo_custodia}|<id>",
                        "llave": {"archivo": "llave.dpapi", "longitud_bytes": 32,
                                  "proteccion": "Windows DPAPI ámbito usuario CRYPTPROTECT_UI_FORBIDDEN",
                                  "sha256_blob_dpapi": ""}},
            "artefactos": [], "esquemas": real["esquemas"], "invariantes_semanticas": []}
        blob = _dpapi_proteger(self.llave)
        (self.carpeta / "llave.dpapi").write_bytes(blob)
        self.manifest["cifrado"]["llave"]["sha256_blob_dpapi"] = hashlib.sha256(blob).hexdigest()
        from mia.eval.cases import GoldenCase, GoldenCaseDoc
        self.custodiados = []
        for cid in IDS_CUSTODIADOS:
            docs = [{"filename": f"{cid.lower()}-pieza-{d}.txt",
                     "chunks": [chunk_custodiado(cid, d, i) for i in range(n)]}
                    for d, n in enumerate(N_FRAGMENTOS_CUSTODIADO)]
            caso = {"schema": "banco04-caso/v1", "protocolo": self.protocolo_custodia, "id": cid,
                    "title": f"caso custodiado de prueba {cid}",
                    "message": "Determina si la reclamación de la contratista procede según el expediente.",
                    "jurisdicciones": JURISDICCIONES_CUSTODIADOS[cid], "profile": {}, "synthetic": True,
                    "expect_reaches_draft": True, "recall_markers": [], "rubric": {}, "documents": docs,
                    "n_fragmentos": sum(N_FRAGMENTOS_CUSTODIADO), "semilla_relleno": 1}
            self.escribir(cid, "caso", caso, "banco04-caso/v1")
            self.custodiados.append(GoldenCase(
                id=cid, title=caso["title"], message=caso["message"],
                documents=tuple(GoldenCaseDoc(filename=d["filename"], chunks=tuple(d["chunks"]))
                                for d in docs), synthetic=True))
        self.casos_visibles = list(casos_visibles)
        for c in [*self.custodiados, *self.casos_visibles]:
            self.escribir(f"clave-{c.id}", "clave", clave_de(c), "banco04-clave/v1")
        self.escribir("mut-ajuste", "mutaciones_ajuste", conjunto_mutaciones("ajuste"),
                      "banco04-mutaciones/v1")
        self.escribir("mut-reservado", "mutaciones_reservadas", conjunto_mutaciones("reservado"),
                      "banco04-mutaciones/v1")
        self.escribir("semilla", "semilla", {
            "schema": "banco04-semilla/v1", "protocolo": self.protocolo_custodia,
            "algoritmo": "HMAC-SHA256", "hmac_key_hex": SEMILLA_HEX, "usos": [],
            "creada": "2026-10-12"}, "banco04-semilla/v1")
        self.ruta_manifiesto = self.carpeta.parent / f"manifest-{self.carpeta.name}.json"
        self.ruta_manifiesto.write_text(json.dumps(self.manifest, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def canonico(obj) -> bytes:
        return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def escribir(self, id_: str, tipo: str, obj: Any, esquema: Optional[str]) -> None:
        claro = self.canonico(obj)
        nonce = os.urandom(12)
        raw = nonce + self.AESGCM(self.llave).encrypt(nonce, claro,
                                                       f"{self.protocolo_custodia}|{id_}".encode())
        archivo = f"{id_}.bin"
        (self.carpeta / archivo).write_bytes(raw)
        self.manifest["artefactos"].append({
            "id": id_, "tipo": tipo, "archivo": archivo,
            "sha256_claro": hashlib.sha256(claro).hexdigest(),
            "sha256_cifrado": hashlib.sha256(raw).hexdigest(), "bytes_claro": len(claro),
            "formato_claro": "json-canonico-utf8", "esquema": esquema})

    def sha256_manifiesto(self) -> str:
        return entorno.sha256_archivo(self.ruta_manifiesto)

    def abrir(self):
        from mia.eval.banco04 import custodia as cus
        return cus.abrir(cus.PROPOSITO_MEDICION, environ={cus.ENV_CUSTODIA: str(self.carpeta)},
                         manifest_path=self.ruta_manifiesto, repo_root=entorno.ROOT)

    def acreditacion_v13(self, hash_combinado: str) -> dict:
        import banco04_validar_jueces as vj
        man = json.loads(self.ruta_manifiesto.read_text(encoding="utf-8"))
        return {"schema": vj.FORMATO_ACREDITACION,
                "protocolo": __import__("mia.eval.banco04.protocolo", fromlist=["x"]).VERSION_PROTOCOLO,
                "autor": "autor-independiente-de-pruebas", "autor_independiente": True,
                "fecha": "2026-10-12", "hash_evaluador": hash_combinado,
                "identidad_reservado": vj.identidad_sellada_reservado(man),
                "artefactos": {x["id"]: x["sha256_claro"] for x in man["artefactos"]
                               if x["tipo"] in vj.TIPOS_ACREDITADOS},
                "veredicto": "compatible", "cobertura": json.loads(json.dumps(COBERTURA_V13))}

    def identidad_reservado(self) -> str:
        import banco04_validar_jueces as vj
        return vj.identidad_sellada_reservado(json.loads(self.ruta_manifiesto.read_text(encoding="utf-8")))


def casos_visibles() -> list:
    from mia.eval import cases as cases_mod, holdout
    return (list(cases_mod.load_golden_cases()) + list(cases_mod.load_large_cases())
            + list(holdout.load_holdout_cases(holdout.HOLDOUT_PURPOSE_MEASURE)))


def texto_sin_citas(texto: str) -> bool:
    from mia.eval.banco04 import evaluador_congelado as EV
    return not EV.scan_citations(texto, EV.compile_patterns(None))


_RE_DIGITO = re.compile(r"\d")
