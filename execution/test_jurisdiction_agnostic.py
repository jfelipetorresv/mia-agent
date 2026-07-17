"""
Mia · test_jurisdiction_agnostic.py — gate de la REGLA DURA: Mia es AGNÓSTICA DE JURISDICCIÓN.

Mia NO es colombiana: se adapta al despacho que la instala (Colombia, México, España…). El
conocimiento de país vive en `jurisdiction/packs/{code}/`, nunca en el código.

OJO — "agnóstico" NO significa lo mismo en todas las capas, y este gate protege la diferencia:

  · ANONIMIZADOR (confidencialidad) → "ENMASCARAR TODO, SIEMPRE". No sabe ni acepta la
    jurisdicción del despacho: aplica base universal + TODOS los packs instalados + respaldos por
    rol. Un despacho español enmascara un NIT colombiano, porque su cliente puede ser colombiano
    y el secreto profesional manda sobre la precisión del análisis. Aquí el sesgo es
    sobre-enmascarar; una fuga es un daño irreversible a un cliente real.
  · CORPUS y WAKE-GATE del correo (calidad/atención) → SIN CONTAGIO, sigue vigente. A un despacho
    español NO se le siembra derecho colombiano ni 'tutela' le despierta la vigilancia. Aquí
    equivocarse solo hace ruido: no filtra nada.

Los cuatro sentidos que se prueban:

  (a) CERO REGRESIÓN para el despacho colombiano — cédula, NIT, radicado, teléfono +57,
      tutela/desacato, remitentes .gov.co.
  (b) COBERTURA UNIVERSAL del anonimizador (enmascarar todo) + SIN CONTAGIO donde toca (corpus,
      wake-gate).
  (c) FAIL-CLOSED — sin pack, con pack inexistente, con pack ROTO (regex inválido, JSON basura),
      con un pack que declara un `role` con regex ESTRECHO, o con la capa de jurisdicción caída,
      el anonimizador SIGUE anonimizando y el wake-gate SIGUE despertando. Nunca texto crudo.
  (d) SIN PERILLA — la API pública del anonimizador no acepta jurisdicción, y una degradación
      transitoria de los packs no se queda cacheada.

OFFLINE (sin DB, sin red, sin Ollama — el NER va apagado con run_ner=False).

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_jurisdiction_agnostic.py
"""
from __future__ import annotations
import hashlib
import inspect
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))  # para `import mia.*`

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.security import anonymize                      # noqa: E402
from mia.connectors.mailbox import base as mailbox      # noqa: E402
from mia.jurisdiction import pack as pack_mod           # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def _markers() -> list[str]:
    return [m for m, _p in anonymize._structured_patterns()]


def _clear_caches() -> None:
    """Las tablas van cacheadas por código; tras mover PACKS_DIR hay que invalidar."""
    anonymize._structured_patterns.cache_clear()
    anonymize._direccion_re.cache_clear()
    anonymize._stop_cap.cache_clear()
    mailbox._urgency_re.cache_clear()
    mailbox._institutional_senders.cache_clear()


def mh(**kw):
    """MailHeader mínimo (mismo helper que test_mailbox)."""
    base = dict(provider="google", external_id="m1", subject="", sender="", sender_name="")
    base.update(kw)
    return mailbox.MailHeader(**base)


# Texto con la PII colombiana canónica (el mismo juego que cubre test_gold_cases).
_CO_TEXT = (
    "El señor identificado con cédula 79.484.321, la sociedad con NIT 900.123.456-7, "
    "radicado 11001310300320180012300, correo juan.perez@example.com, celular 310 555 1234, "
    "cuenta de ahorros 12345678, ver https://ejemplo.com/expediente."
)


# Datos de un cliente COLOMBIANO — el caso que un despacho de otro país también debe enmascarar.
_PII_CO = {
    "cédula": "79.484.321",
    "NIT": "900.123.456-7",
    "radicado": "11001310300320180012300",
}
# Datos de un cliente ESPAÑOL — el caso que un despacho colombiano también debe enmascarar.
_PII_ES = {
    "DNI": "12345678Z",
    "teléfono agrupado": "615 55 12 34",
    "teléfono con guiones": "615-55-12-34",
}


# ── (a) CERO REGRESIÓN · despacho colombiano ──────────────────────────────────
def co_no_regression() -> None:
    print("\n-- (a) despacho colombiano: cero regresión --")

    # La tabla es UNA sola para todo el mundo (no hay variante por jurisdicción). Los tipos
    # colombianos siguen ahí, en su orden, y ahora convive con ellos el respaldo pan-hispano
    # (DOCUMENTO + el TELEFONO internacional, que el `role` del pack YA NO suprime).
    esperado = ["URL", "EMAIL", "RADICADO", "NIT", "CEDULA", "DOCUMENTO", "CUENTA",
                "TELEFONO", "TELEFONO"]
    check("la tabla conserva los 7 tipos colombianos de hoy, en el mismo orden relativo, "
          "y suma los respaldos por rol (DOCUMENTO + TELEFONO internacional)",
          _markers() == esperado)

    r = anonymize.anonymize_text(_CO_TEXT, run_ner=False)
    crudos = ["79.484.321", "900.123.456-7", "11001310300320180012300",
              "juan.perez@example.com", "310 555 1234", "ejemplo.com"]
    check("co: ningún dato colombiano crudo sobrevive", not any(c in r.text for c in crudos))
    check("co: marcadores tipados de Colombia presentes (CEDULA/NIT/RADICADO)",
          "[[CEDULA_1]]" in r.text and "[[NIT_1]]" in r.text and "[[RADICADO_1]]" in r.text)
    check("co: contains_pii sobre el texto anonimizado es False",
          anonymize.contains_pii(r.text) is False)
    check("co: contains_pii detecta la cédula colombiana en crudo",
          anonymize.contains_pii("cédula 79.484.321") is True)

    # Dirección colombiana (Carrera/Kra viene del pack) → sigue marcándose como sospecha.
    check("co: la dirección con 'Carrera' sigue marcada como sospecha (prefijo del pack)",
          any(s["tipo"] == "sospecha_direccion" for s in
              anonymize.scan_suspects("Domicilio en la Carrera 7 # 12-34 de la ciudad")))

    # Las FECHAS se conservan a propósito (caducidad/prescripción se calculan con ellas): el
    # respaldo de teléfono agrupado es laxo y no puede comérselas.
    fechas = ("El auto del 16-07-2026, notificado el 2026-07-16, radicado el 01/02/2023 "
              "conforme a la Ley 1437 de 2011 y al Decreto 1077 de 2015.")
    r_f = anonymize.anonymize_text(fechas, run_ner=False)
    check("co: las fechas y los números de norma NO se enmascaran (el respaldo de teléfono "
          "agrupado no se las come)", r_f.text == fechas)

    # Wake-gate del correo: léxico y remitentes colombianos intactos.
    for codes in (["co"], None):
        etiqueta = "co" if codes else "por defecto"
        check(f"{etiqueta}: 'tutela' y 'desacato' siguen despertando la vigilancia",
              mailbox.mail_looks_urgent(mh(subject="Acción de tutela en su contra"), codes)
              and mailbox.mail_looks_urgent(mh(subject="Incidente de desacato"), codes))
        check(f"{etiqueta}: remitente .gov.co institucional sigue despertando",
              mailbox.mail_looks_urgent(mh(sender="notificaciones@ramajudicial.gov.co"), codes)
              and mailbox.mail_looks_urgent(mh(sender="x@procuraduria.gov.co"), codes))
        check(f"{etiqueta}: correo trivial sigue sin despertar (no hay ruido nuevo)",
              mailbox.mail_looks_urgent(mh(subject="Almuerzo del viernes",
                                           sender="amigo@gmail.com"), codes) is False)


# ── (b) COBERTURA UNIVERSAL del anonimizador · SIN CONTAGIO donde toca ────────
def universal_masking() -> None:
    """Decisión de producto "enmascarar todo, siempre": el anonimizador NO depende de la
    jurisdicción del despacho. Un bufete español atiende clientes colombianos; el secreto
    profesional manda sobre la precisión del análisis. Ojo — esto es lo CONTRARIO del criterio
    del corpus y del wake-gate, que sí son por-jurisdicción (ver `no_colombian_bias`)."""
    print("\n-- (b) anonimizador: enmascarar TODO, siempre --")

    # Despacho NO colombiano (español) con un cliente colombiano: sus datos SE ENMASCARAN.
    txt_co_en_es = (f"Cliente colombiano: cédula {_PII_CO['cédula']}, "
                    f"NIT {_PII_CO['NIT']}, radicado {_PII_CO['radicado']}.")
    r = anonymize.anonymize_text(txt_co_en_es, run_ner=False)
    for etiqueta, valor in _PII_CO.items():
        check(f"despacho no-colombiano: la {etiqueta} de un cliente colombiano SE ENMASCARA "
              f"(el dato del cliente no deja de serlo por ser de otro país)",
              valor not in r.text)
    check("despacho no-colombiano: los datos colombianos reciben su marcador tipado",
          "[[CEDULA_1]]" in r.text and "[[NIT_1]]" in r.text and "[[RADICADO_1]]" in r.text)

    # Despacho colombiano con un cliente español: sus datos SE ENMASCARAN (simétrico).
    txt_es_en_co = (f"Cliente español: DNI {_PII_ES['DNI']}, "
                    f"teléfono {_PII_ES['teléfono agrupado']}, y también "
                    f"{_PII_ES['teléfono con guiones']}.")
    r2 = anonymize.anonymize_text(txt_es_en_co, run_ner=False)
    for etiqueta, valor in _PII_ES.items():
        check(f"despacho colombiano: el {etiqueta} de un cliente español SE ENMASCARA",
              valor not in r2.text)
    check("teléfonos con separadores: contains_pii los detecta en crudo (antes se filtraban)",
          all(anonymize.contains_pii(f"llámame al {t}") is True
              for t in ("615 55 12 34", "615-55-12-34", "91 123 45 67")))

    check("no queda PII estructurada tras anonimizar el texto mixto CO+ES",
          anonymize.contains_pii(r.text) is False
          and anonymize.contains_pii(r2.text) is False)


def no_colombian_bias() -> None:
    """SIN CONTAGIO — sigue vigente donde equivocarse NO filtra datos: corpus y wake-gate.
    Que el ANONIMIZADOR enmascare de más es correcto; que el wake-gate despierte con 'tutela' en
    Madrid, o que se le siembre derecho colombiano a un despacho español, NO lo es."""
    print("\n-- (b2) corpus y wake-gate: sin contagio colombiano --")

    # El léxico colombiano no contamina el wake-gate de otro foro.
    check("es: 'tutela'/'desacato' (léxico colombiano) NO despiertan la vigilancia",
          mailbox.mail_looks_urgent(mh(subject="Consulta sobre tutela"), ["es"]) is False
          and mailbox.mail_looks_urgent(mh(subject="tema de desacato"), ["es"]) is False)
    check("es: los remitentes .gov.co NO cuentan como institucionales",
          mailbox.mail_looks_urgent(mh(sender="notificaciones@ramajudicial.gov.co"),
                                    ["es"]) is False)
    check("es: el léxico PAN-HISPANO sí despierta (audiencia, plazo, vencimiento)",
          mailbox.mail_looks_urgent(mh(subject="Audiencia el martes"), ["es"])
          and mailbox.mail_looks_urgent(mh(subject="Vence el plazo"), ["es"]))
    check("es: la bandera de importancia alta despierta en cualquier jurisdicción",
          mailbox.mail_looks_urgent(mh(importance="high"), ["es"]) is True)

    # Corpus semilla colombiano: opt-in del pack.
    check("solo el pack 'co' declara baseline_corpus_seed (opt-in del corpus colombiano)",
          pack_mod.load_pack("co").baseline_corpus_seed is True
          and pack_mod.load_pack("es").baseline_corpus_seed is False
          and pack_mod.generic_pack().baseline_corpus_seed is False)


def idempotencia() -> None:
    """IDEMPOTENCIA con DOBLE ENMASCARADO. Requisito del módulo, y ahora más delicado: con
    "enmascarar todo, siempre" conviven DOS patrones para el mismo rol (el del pack de país y el
    respaldo pan-hispano). Hay que probar que (1) el segundo no mastica el marcador que dejó el
    primero, (2) `AnonSession` da marcadores CONSISTENTES (mismo valor → mismo marcador) y
    (3) re-anonimizar no altera el texto — si no, la pantalla de revisión degradaría el caso."""
    print("\n-- (b3) idempotencia y marcadores consistentes con doble enmascarado --")

    txt = ("Contacto: maria.lopez@bufete.es, DNI 12345678Z, teléfono +34 612 345 678, "
           "cuenta corriente 98765432, cédula 79.484.321, NIT 900.123.456-7, "
           "radicado 11001310300320180012300, celular 310 555 1234, móvil 615 55 12 34.")
    una = anonymize.anonymize_text(txt, run_ner=False)
    dos = anonymize.anonymize_text(una.text, run_ner=False)
    check("la anonimización es idempotente (re-anonimizar no altera el texto)",
          dos.text == una.text)
    check("sin PII estructurada restante tras anonimizar",
          anonymize.contains_pii(una.text) is False)
    check("el doble enmascarado no deja marcadores anidados ni rotos "
          "(p. ej. [[TELEFONO_[[...]]]])",
          "[[[" not in una.text and "]]]" not in una.text)

    # Consistencia: el MISMO valor, escrito dos veces (y con separación distinta), recibe el
    # MISMO marcador — es lo que hace que el caso de oro siga siendo un examen legible.
    sess = anonymize.AnonSession()
    a = anonymize.anonymize_text("La cédula 79.484.321 del demandante.", session=sess,
                                 run_ner=False)
    b = anonymize.anonymize_text("Otra vez la cédula 79.484.321 y la cédula 79484321.",
                                 session=sess, run_ner=False)
    check("mismo valor en dos textos de la misma sesión → MISMO marcador",
          "[[CEDULA_1]]" in a.text and a.text.count("[[CEDULA_1]]") == 1
          and b.text.count("[[CEDULA_1]]") == 2 and "[[CEDULA_2]]" not in b.text)

    # El número PELADO adopta el marcador del patrón MÁS ESPECÍFICO que ya lo tipificó: sin esto,
    # el respaldo laxo de teléfono le pondría [[TELEFONO_n]] a una cédula ya vista como
    # [[CEDULA_1]] y la misma entidad quedaría con dos marcadores.
    r_pelado = anonymize.anonymize_text(
        "La cédula 79.484.321 aparece; más abajo 79484321 se repite como cuantía.",
        run_ner=False)
    check("el número pelado adopta el marcador del dato ya tipificado (no acuña [[TELEFONO_n]] "
          "para una cédula que ya es [[CEDULA_1]])",
          r_pelado.text.count("[[CEDULA_1]]") == 2 and "TELEFONO" not in r_pelado.text)

    # …pero un valor CON palabra clave se identifica a sí mismo y CONSERVA su tipo, aunque otro
    # dato de la sesión comparta sus dígitos por pura coincidencia.
    r_kw = anonymize.anonymize_text("DNI 12345678Z y cuenta de ahorros 12345678.", run_ner=False)
    check("un valor con palabra clave conserva SU tipo aunque coincidan los dígitos "
          "(la cuenta no se vuelve documento)",
          "[[DOCUMENTO_1]]" in r_kw.text and "[[CUENTA_1]]" in r_kw.text)


# Hash de la tabla COMPLETA de patrones estructurados (marcador, patrón, flags), con los packs
# realmente instalados. Cambiarlo exige revisar el diff regex por regex — ver `regex_drift_guard`.
_TABLA_HASH = "386ba0aba94a26efa0f2e8ed83d8eb098233b97974b4e25efc3a9b3361b6ccb6"


def _tabla_hash() -> str:
    payload = json.dumps([[m, p.pattern, p.flags] for m, p in anonymize._structured_patterns()],
                         ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def regex_drift_guard() -> None:
    """GUARDIÁN DE DERIVA. Fija el hash de la tabla COMPLETA (marcador, patrón, flags). Cualquier
    cambio de un regex —de un pack o del código— rompe este check a propósito: el anonimizador es
    el gate de confidencialidad y un `\\b` perdido no puede colarse sin que nadie lo vea.

    Si lo rompiste a sabiendas: revisa el diff regex por regex, comprueba que NO reduce cobertura
    (mide contra `_PII_CO` y `_PII_ES`), y recién ahí actualiza `_TABLA_HASH`. Para verlo:
        .venv\\Scripts\\python.exe execution\\test_jurisdiction_agnostic.py --hash
    """
    print("\n-- (b4) guardián de deriva de regex --")

    got = _tabla_hash()
    check(f"la tabla de patrones no cambió sin revisión consciente (hash {got[:12]}…)",
          got == _TABLA_HASH)


def corpus_seed_optin() -> None:
    """El corpus semilla colombiano NO se siembra sin opt-in explícito del pack. Se verifica sin
    DB: el gate corta ANTES de tocar el SAT-Graph (si no cortara, reventaría por falta de pool)."""
    print("\n-- (b5) corpus semilla: opt-in del pack, sin DB --")
    import asyncio
    from mia.rag.ingest_corpus import ingest_baseline_corpus

    async def _seed(juris):
        return await ingest_baseline_corpus(None, jurisdiction=juris)

    for juris, etiqueta in ((None, "sin jurisdicción"), ("es", "despacho español"),
                            ("mx", "despacho mexicano"), ("generic", "modo genérico")):
        out = asyncio.run(_seed(juris))
        check(f"{etiqueta}: NO se siembra corpus colombiano (0 normas + motivo explícito)",
              out["norms"] == 0 and out["jurisprudence"] == 0 and out["relations"] == 0
              and bool(out.get("skipped")))


# ── (c) FAIL-CLOSED · sin pack / pack roto ────────────────────────────────────
def fail_closed() -> None:
    print("\n-- (c) fail-closed: sin pack, pack roto, capa caída --")

    # Un texto pan-hispano con PII que NINGÚN pack de país necesita para detectarse.
    txt = ("Contacto: maria.lopez@bufete.es, con DNI 12345678Z, teléfono +34 612 345 678, "
           "cuenta corriente 98765432, web https://bufete.es/casos")

    r = anonymize.anonymize_text(txt, run_ner=False)
    check("NO deja pasar el texto crudo (email/teléfono/web ocultos)",
          "maria.lopez@bufete.es" not in r.text
          and "+34 612 345 678" not in r.text
          and "https://bufete.es/casos" not in r.text)
    check("el documento de identidad local (DNI) se oculta", "12345678Z" not in r.text)

    # Pack ROTO: regex inválido + JSON basura. La cobertura NO puede caer a cero.
    tmp = Path(tempfile.mkdtemp(prefix="mia_packs_"))
    original = pack_mod.PACKS_DIR
    try:
        roto = tmp / "zz"
        roto.mkdir()
        (roto / "meta.json").write_text(json.dumps({"code": "zz", "name": "Roto"}),
                                        encoding="utf-8")
        # regex sin cerrar el paréntesis → re.error al compilar.
        (roto / "id_formats.json").write_text(json.dumps({
            "malo": {"marker": "MALO", "role": "document", "order": 5, "regex": "(((["},
            "_note": "clave de documentación: no es un formato",
        }), encoding="utf-8")
        (roto / "pii_hints.json").write_text("{ esto no es JSON válido ", encoding="utf-8")
        (roto / "mail_signals.json").write_text(json.dumps({
            "urgency_terms": ["(sin cerrar"], "institutional_sender_domains": ["juzgado.zz"],
        }), encoding="utf-8")

        pack_mod.PACKS_DIR = tmp
        _clear_caches()

        marcadores = _markers()
        check("pack roto: el regex inválido se descarta (no entra a la tabla)",
              "MALO" not in marcadores)
        check("pack roto: la base universal SIGUE en pie (URL/EMAIL/CUENTA)",
              {"URL", "EMAIL", "CUENTA"} <= set(marcadores))
        check("pack roto: el respaldo por rol cubre el hueco (DOCUMENTO/TELEFONO)",
              "DOCUMENTO" in marcadores and "TELEFONO" in marcadores)

        r = anonymize.anonymize_text(txt, run_ner=False)
        check("pack roto: SIGUE anonimizando — no se filtra texto crudo",
              "maria.lopez@bufete.es" not in r.text and "12345678Z" not in r.text
              and "+34 612 345 678" not in r.text)

        check("pack roto: pii_hints con JSON inválido no lanza; la sospecha sigue viva",
              any(s["tipo"] == "sospecha_direccion"
                  for s in anonymize.scan_suspects("Vive en la Calle 100 No. 15-20")))
        check("pack roto: el término de urgencia inválido se descarta y el léxico base sigue",
              mailbox.mail_looks_urgent(mh(subject="Audiencia mañana"), ["zz"]) is True)
        # Un archivo corrupto NO puede llevarse por delante los archivos VÁLIDOS del mismo pack:
        # `pii_hints.json` es JSON basura, pero `mail_signals.json` es legible y debe aplicarse.
        check("pack roto: un archivo corrupto no anula los archivos válidos del mismo pack "
              "(los dominios institucionales legibles sí se aplican)",
              mailbox.mail_looks_urgent(mh(sender="a@juzgado.zz"), ["zz"]) is True)
        check("pack roto: load_pack no lanza ante un JSON corrupto (fail-soft en el cargador)",
              pack_mod.load_pack("zz").pii_hints == {})

        # PACKS_DIR vacío de packs válidos → el defecto (None = todos los instalados) no puede
        # quedarse sin red.
        vacio = Path(tempfile.mkdtemp(prefix="mia_packs_vacio_"))
        try:
            pack_mod.PACKS_DIR = vacio
            _clear_caches()
            marcadores_none = _markers()
            check("sin NINGÚN pack instalado: el defecto conserva la red completa "
                  "(URL/EMAIL/CUENTA/DOCUMENTO/TELEFONO)",
                  {"URL", "EMAIL", "CUENTA", "DOCUMENTO", "TELEFONO"} <= set(marcadores_none))
            r_none = anonymize.anonymize_text(txt, run_ner=False)
            check("sin NINGÚN pack instalado: sigue anonimizando (no deja pasar crudo)",
                  "maria.lopez@bufete.es" not in r_none.text and "12345678Z" not in r_none.text)
        finally:
            shutil.rmtree(vacio, ignore_errors=True)
    finally:
        pack_mod.PACKS_DIR = original
        _clear_caches()
        shutil.rmtree(tmp, ignore_errors=True)


def role_declarado_no_suprime_respaldo() -> None:
    """LA FUGA QUE ESTE TEST NO CUBRÍA (revisión adversarial).

    El camino ya probado era el pack con regex INVÁLIDO ('((('): ese se descarta al compilar, así
    que su `role` nunca contaba como "cubierto" y el respaldo entraba igual. El camino ROTO era
    otro: un pack con un regex VÁLIDO pero ESTRECHO que declara `role: "document"`. Compilaba, su
    rol contaba como cubierto, y eso SUPRIMÍA el respaldo pan-hispano DOCUMENTO entero → cédulas y
    DNIs salían CRUDOS hacia la IA externa. Bastaba un typo de `role` en un pack nuevo.

    El arreglo: los respaldos por rol se aplican SIEMPRE. Un pack SUMA, nunca RESTA."""
    print("\n-- (c2) un pack con `role` declarado NO puede apagar el respaldo --")

    tmp = Path(tempfile.mkdtemp(prefix="mia_packs_role_"))
    original = pack_mod.PACKS_DIR
    try:
        p = tmp / "zz"
        p.mkdir()
        (p / "meta.json").write_text(json.dumps({"code": "zz", "name": "Estrecho"}),
                                     encoding="utf-8")
        # Regex VÁLIDO (compila) pero que solo cubre un formato propio y estrechísimo. Declara
        # `role: "document"` y `role: "phone"` — antes, esto bastaba para apagar los respaldos.
        (p / "id_formats.json").write_text(json.dumps({
            "codigo_zz": {"marker": "CODIGOZZ", "role": "document", "order": 5,
                          "regex": r"\bZZ-\d{4}\b"},
            "beeper_zz": {"marker": "BEEPERZZ", "role": "phone", "order": 6,
                          "regex": r"\bBP\d{3}\b"},
        }), encoding="utf-8")
        pack_mod.PACKS_DIR = tmp
        _clear_caches()

        marcadores = _markers()
        check("pack con `role` declarado y regex válido: sus patrones SÍ entran",
              "CODIGOZZ" in marcadores and "BEEPERZZ" in marcadores)
        check("pack con `role` declarado: NO apaga los respaldos por rol "
              "(DOCUMENTO y TELEFONO siguen en la tabla) — ESTA ERA LA FUGA",
              "DOCUMENTO" in marcadores and "TELEFONO" in marcadores)

        txt = ("Contacto: DNI 12345678Z, cédula 79.484.321, teléfono +34 612 345 678, "
               "móvil 615 55 12 34, ficha ZZ-4821, busca BP771.")
        r = anonymize.anonymize_text(txt, run_ner=False)
        for etiqueta, valor in (("DNI español", "12345678Z"),
                                ("cédula colombiana", "79.484.321"),
                                ("teléfono internacional", "+34 612 345 678"),
                                ("teléfono agrupado", "615 55 12 34")):
            check(f"pack con `role` declarado: el {etiqueta} NO se filtra", valor not in r.text)
        check("pack con `role` declarado: sus propios formatos también se enmascaran "
              "(el pack SUMA precisión sobre el respaldo)",
              "ZZ-4821" not in r.text and "BP771" not in r.text)
        check("pack con `role` declarado: contains_pii sobre el resultado es False",
              anonymize.contains_pii(r.text) is False)
    finally:
        pack_mod.PACKS_DIR = original
        _clear_caches()
        shutil.rmtree(tmp, ignore_errors=True)

    # Capa de jurisdicción CAÍDA por completo (load_pack revienta) → base universal + respaldos.
    original_load = pack_mod.load_pack

    def _boom(_code):
        raise RuntimeError("capa de jurisdicción caída (simulado)")

    try:
        pack_mod.load_pack = _boom
        _clear_caches()
        marcadores = _markers()
        check("capa de jurisdicción caída: no lanza y conserva la red base",
              {"URL", "EMAIL", "CUENTA", "DOCUMENTO", "TELEFONO"} <= set(marcadores))
        r = anonymize.anonymize_text(txt, run_ner=False)
        check("capa de jurisdicción caída: SIGUE anonimizando (fail-closed, no texto crudo)",
              "maria.lopez@bufete.es" not in r.text and "12345678Z" not in r.text)
        check("capa de jurisdicción caída: el wake-gate no queda mudo (léxico base)",
              mailbox.mail_looks_urgent(mh(subject="Vence el plazo hoy"), ["co"]) is True)
    finally:
        pack_mod.load_pack = original_load
        _clear_caches()


def sin_perilla() -> None:
    """SIN PERILLA — el anonimizador no acepta jurisdicción, y no cachea una degradación.

    Antes, el juego de patrones se resolvía desde la config del despacho: una jurisdicción mal
    resuelta (DB caída, 'generic' ambiguo, jurisdicción sin elegir) le quitaba cobertura a un
    cliente real. La perilla se eliminó de raíz — no hay forma de fallar al girarla si no existe.
    Un `jurisdictions=` olvidado en un llamador viejo debe REVENTAR (TypeError), nunca aceptarse
    e ignorarse en silencio: aceptarlo sería una trampa para el próximo que lea el código."""
    print("\n-- (d) sin perilla: la API no acepta jurisdicción; el caché no fija degradaciones --")

    for fn_name in ("scan_pii", "contains_pii", "scan_suspects", "anonymize_text",
                    "anonymize_bundle"):
        params = inspect.signature(getattr(anonymize, fn_name)).parameters
        check(f"{fn_name}(): la API pública ya NO expone `jurisdictions`",
              "jurisdictions" not in params)

    for fn_name in ("scan_pii", "contains_pii", "anonymize_text"):
        try:
            getattr(anonymize, fn_name)("texto", jurisdictions=["es"])
            ok = False   # lo aceptó e ignoró en silencio: la trampa que queremos evitar
        except TypeError:
            ok = True
        check(f"{fn_name}(jurisdictions=...): REVIENTA ruidosamente, no lo ignora en silencio",
              ok)

    check("gold_cases ya no resuelve la jurisdicción para anonimizar "
          "(`_tenant_jurisdictions` eliminado)",
          not hasattr(__import__("mia.api.routes.gold_cases", fromlist=["x"]),
                      "_tenant_jurisdictions"))

    # CACHÉ: una degradación TRANSITORIA no puede congelarse para toda la vida del proceso. Un
    # hipo de I/O al leer los packs dejaría a un despacho colombiano operando la sesión entera
    # sin RADICADO ni NIT — sin que nadie lo note.
    _clear_caches()
    original_load = pack_mod.load_pack
    hipo = {"on": True}          # el "hipo" dura mientras esté encendido, luego el I/O se cura

    def _flaky(code):
        if hipo["on"]:
            raise RuntimeError("hipo de I/O transitorio (simulado)")
        return original_load(code)

    try:
        pack_mod.load_pack = _flaky
        degradada = _markers()
        check("hipo transitorio de I/O: la tabla degrada (pierde los patrones del pack) pero "
              "conserva base + respaldos",
              "RADICADO" not in degradada
              and {"URL", "EMAIL", "CUENTA", "DOCUMENTO", "TELEFONO"} <= set(degradada))
        mudo = mailbox.mail_looks_urgent(mh(subject="Acción de tutela"), ["co"])
        check("hipo transitorio de I/O: el wake-gate pierde el léxico del pack "
              "('tutela' no despierta) pero conserva el léxico base",
              mudo is False
              and mailbox.mail_looks_urgent(mh(subject="Vence el plazo"), ["co"]) is True)

        # El I/O se cura. NADIE reinicia el proceso ni limpia caché a mano: si la degradación se
        # hubiera cacheado (lru_cache), el despacho seguiría sin RADICADO/NIT toda la sesión.
        hipo["on"] = False
        recuperada = _markers()
        check("la degradación NO se cacheó: la tabla RECUPERA sola la cobertura "
              "(RADICADO/NIT/CEDULA vuelven sin reiniciar el proceso)",
              {"RADICADO", "NIT", "CEDULA"} <= set(recuperada))
        check("la degradación NO se cacheó: el wake-gate recupera solo el léxico del pack "
              "('tutela' vuelve a despertar)",
              mailbox.mail_looks_urgent(mh(subject="Acción de tutela"), ["co"]) is True)
    finally:
        pack_mod.load_pack = original_load
        _clear_caches()


def main() -> int:
    co_no_regression()
    universal_masking()
    no_colombian_bias()
    idempotencia()
    regex_drift_guard()
    corpus_seed_optin()
    fail_closed()
    role_declarado_no_suprime_respaldo()
    sin_perilla()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Agnosticismo de jurisdicción OK — cero regresión en Colombia; el anonimizador "
              "enmascara TODO siempre (sin perilla de jurisdicción); corpus y wake-gate sin "
              "contagio; fail-closed verificado.")
        return 0
    print("Agnosticismo de jurisdicción FAIL.")
    return 1


if __name__ == "__main__":
    if "--hash" in sys.argv:
        # Ayuda para actualizar `_TABLA_HASH` DESPUÉS de revisar el diff de regex a conciencia.
        print(f"hash actual de la tabla de patrones:\n{_tabla_hash()}")
        raise SystemExit(0)
    raise SystemExit(main())
