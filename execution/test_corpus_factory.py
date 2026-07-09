"""
Mia · test_corpus_factory.py — gate del Data Factory del corpus jurídico (rag/corpus_factory).

Ejercita los adaptadores y la orquestación SIN RED: el cliente HTTP se inyecta como un fake
que devuelve HTML de fixture (realista). Cubre parseo, validación de identidad fail-closed,
detección del shell vacío de la SPA, segmentación de normas grandes, gate de ToS, ingesta
idempotente a la DB real y dry_run.

Limpieza por marcador: todo lo insertado lleva issuing_body 'CF_TEST%' (normas) o court
'CF_TEST_COURT' (jurisprudencia); se limpia antes y después con conexión admin (postgres).

Salida: exit 0 = PASS · exit 1 = FAIL.

    .venv\\Scripts\\python.exe execution\\test_corpus_factory.py
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

import psycopg
from dotenv import load_dotenv

# psycopg async no corre sobre ProactorEventLoop (Windows nativo, Modo B).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.db import pool                                          # noqa: E402
from mia.jurisdiction.pack import PACKS_DIR                      # noqa: E402
from mia.rag.corpus_factory import (                            # noqa: E402
    FuncionPublicaAdapter, CorteConstitucionalAdapter, SuinJuriscolAdapter, segment_norm,
    ingest_catalog, MAX_NORM_CHARS,
)

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── conexión admin (postgres) para limpiar marcadores ───────────────────────
PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)


def clean_markers() -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM jurisprudence WHERE court LIKE 'CF_TEST%'")
        c.execute("DELETE FROM legal_norms WHERE issuing_body LIKE 'CF_TEST%'")


def count_norms(where: str, params: tuple) -> int:
    with psycopg.connect(autocommit=True, **PG) as c:
        row = c.execute(f"SELECT count(*) FROM legal_norms WHERE {where}", params).fetchone()
    return row[0]


# ── fake HTTP (sin red) ──────────────────────────────────────────────────────
class _FakeResponse:
    def __init__(self, text: str, *, status_code: int = 200,
                 encoding: str = "utf-8", content: bytes | None = None) -> None:
        self.text = text
        self.status_code = status_code
        self.encoding = encoding
        self.content = content if content is not None else text.encode(encoding, "replace")


class _FakeHttp:
    """Cliente async de mentira: responde por URL exacta; 404 si no la conoce."""

    def __init__(self, routes: dict) -> None:
        self._routes = routes

    async def get(self, url: str, **_kwargs) -> _FakeResponse:
        return self._routes.get(url) or _FakeResponse("", status_code=404)

    async def aclose(self) -> None:
        pass


# ── fixtures HTML ────────────────────────────────────────────────────────────
FP_OK_HTML = (
    "<html><head><title>LEY 1564 DE 2012 - Gestor Normativo</title></head>"
    "<body><nav>menú lateral</nav>"
    "<div id='contenido'><h1>LEY 1564 DE 2012</h1>"
    "<p>Por la cual se expide el Código General del Proceso y se dictan otras disposiciones.</p>"
    "<p>ARTÍCULO 1. Objeto. Este código regula la actividad procesal.</p></div>"
    "<script>var x = 1;</script></body></html>"
)

FP_WRONG_HTML = (
    "<html><head><title>LEY 99 DE 1993 - Ambiente</title></head>"
    "<body><div><h1>LEY 99 DE 1993</h1>"
    "<p>Por la cual se crea el Ministerio del Medio Ambiente.</p></div></body></html>"
)

# Providencia Word-HTML válida: >20KB, contiene 'C-590/05'.
CC_OK_HTML = (
    "<html><head><title>Sentencia C-590/05</title></head><body>"
    "<p>Sentencia C-590/05</p>"
    "<p>Referencia: expediente D-5428. Demanda de inconstitucionalidad contra el art. 185.</p>"
    "<p>Magistrado Ponente: JAIME CÓRDOBA TRIVIÑO</p>"
    "<p>Bogotá D.C., 8 de junio de 2005.</p>"
    "<h2>CONSIDERACIONES DE LA CORTE</h2>"
    "<p>La Corte considera que la acción de tutela procede contra providencias judiciales. "
    + ("Fundamento jurídico de relleno. " * 800) + "</p></body></html>"
)

# Providencia con basura tras "Magistrado Ponente:" (reproduce el defecto verificado
# 2026-07-08: la heurística vieja capturaba el párrafo siguiente en minúsculas) y una fecha
# distinta a la real (31 de marzo vs. la real 22 de enero) — sirve para probar que el
# catálogo verificado PREFIERE sobre lo extraído.
CC_GARBAGE_MP_HTML = (
    "<html><head><title>Sentencia T-025/04</title></head><body>"
    "<p>Sentencia T-025/04</p>"
    "<p>Referencia: expediente T-653010 y otros acumulados.</p>"
    "<p>Magistrado Ponente: renden y justifican como transmisión instrumental de la "
    "constitución y por tanto surgen deberes específicos de protección</p>"
    "<p>Bogotá D.C., 31 de marzo de 2004.</p>"
    "<h2>CONSIDERACIONES DE LA CORTE</h2>"
    "<p>La Corte considera que existe un estado de cosas inconstitucional. "
    + ("Fundamento jurídico de relleno. " * 800) + "</p></body></html>"
)

# Providencia con MP en forma abreviada "M.P.:" (abandonada) — sin catálogo, el fallback debe
# devolver magistrado_ponente vacío (mejor vacío que basura); la fecha sigue siendo parseable.
CC_DIRTY_MP_HTML = (
    "<html><head><title>Sentencia T-025/04</title></head><body>"
    "<p>Sentencia T-025/04</p>"
    "<p>Referencia: expediente T-653010 y otros acumulados.</p>"
    "<p>M.P.: Manuel José Cepeda Espinosa</p>"
    "<p>Bogotá D.C., 22 de enero de 2004.</p>"
    "<h2>CONSIDERACIONES DE LA CORTE</h2>"
    "<p>La Corte considera que existe un estado de cosas inconstitucional. "
    + ("Fundamento jurídico de relleno. " * 800) + "</p></body></html>"
)

# Shell vacío de la SPA: minúsculo, sin el número.
CC_SHELL_HTML = "<html><head><title>Corte Constitucional</title></head><body><div id='app'></div></body></html>"

# SUIN-Juriscol: el <meta> declara charset=utf-16 pero los bytes reales son utf-8 (gotcha
# verificado 2026-07-08). El fixture se codifica como utf-8 para probar que el adaptador
# ignora el charset declarado y decodifica siempre como utf-8.
SUIN_OK_HTML = (
    "<html><head><meta http-equiv='Content-Type' content='text/html; charset=utf-16'>"
    "<title>LEY 84 DE 1873</title></head>"
    "<body><div><h1>LEY 84 DE 1873</h1>"
    "<p>Código Civil de los Estados Unidos de Colombia.</p>"
    "<p>ARTÍCULO 1. Objeto de prueba.</p></div></body></html>"
)

SUIN_WRONG_HTML = (
    "<html><head><meta http-equiv='Content-Type' content='text/html; charset=utf-16'>"
    "<title>LEY 57 DE 1887</title></head>"
    "<body><div><h1>LEY 57 DE 1887</h1>"
    "<p>Régimen Político y Municipal.</p></div></body></html>"
)


# ── pack de prueba 'cftest' (para las corridas de ingest_catalog contra DB) ──
CFTEST_DIR = PACKS_DIR / "cftest"
FP_BASE = "http://cf.test/norma.php"
FP_CFTEST_HTML = (
    "<html><head><title>LEY CFTEST 1 DE 2099</title></head>"
    "<body><div><h1>LEY CFTEST 1 DE 2099</h1>"
    "<p>Norma sintética de prueba del Data Factory.</p>"
    "<p>ARTÍCULO 1. Objeto de prueba.</p></div></body></html>"
)


def write_cftest_pack() -> None:
    CFTEST_DIR.mkdir(parents=True, exist_ok=True)
    cfg = {
        "version": 1,
        "sources": [
            {"code": "funcionpublica", "name": "CF test FP", "kind": "norms",
             "base_url": FP_BASE, "tos_ok": True, "tos_basis": "prueba", "verified": True},
            {"code": "blocked", "name": "CF fuente bloqueada", "kind": "norms",
             "base_url": "http://cf.test/blocked", "tos_ok": False, "tos_basis": "",
             "verified": False},
        ],
        "catalog": {
            "norms": [
                {"source": "funcionpublica", "source_id": "777", "norm_type": "ley",
                 "norm_number": "Ley CFTEST 1 de 2099", "issuing_body": "CF_TEST_BODY",
                 "title": "Norma de prueba CFTEST", "effective_date": "2099-01-01",
                 "practice_areas": ["prueba"]},
                {"source": "blocked", "source_id": "888", "norm_type": "ley",
                 "norm_number": "Ley CFTEST bloqueada de 2099", "issuing_body": "CF_TEST_BODY",
                 "title": "No debe entrar", "effective_date": "2099-01-01"},
            ],
            "jurisprudence": [],
        },
    }
    (CFTEST_DIR / "corpus_sources.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def remove_cftest_pack() -> None:
    if CFTEST_DIR.is_dir():
        shutil.rmtree(CFTEST_DIR, ignore_errors=True)


# ── gate ─────────────────────────────────────────────────────────────────────
async def run_gate() -> None:
    fp_cfg = {"code": "funcionpublica", "base_url": "http://fp.test/norma.php"}
    cc_cfg = {"code": "corteconstitucional", "base_url": "http://cc.test/relatoria"}

    # === 1 · FuncionPublica parsea HTML válido y devuelve dict completo ===
    fp_http = _FakeHttp({"http://fp.test/norma.php?i=48425": _FakeResponse(FP_OK_HTML)})
    fp = FuncionPublicaAdapter(fp_cfg, http=fp_http)
    entry = {"source_id": "48425", "norm_type": "ley", "norm_number": "Ley 1564 de 2012",
             "issuing_body": "Congreso de la República", "title": "Código General del Proceso",
             "effective_date": "2012-07-12", "practice_areas": ["procesal"]}
    norm = await fp.fetch_norm(entry)
    md = (norm or {}).get("metadata", {})
    fetched_ok = True
    try:
        datetime.fromisoformat(md.get("fetched_at", ""))
    except Exception:
        fetched_ok = False
    check("FuncionPublica: parsea HTML de fixture y devuelve dict válido",
          norm is not None
          and norm["title"] == "Código General del Proceso"
          and bool(norm["full_text"]) and "Código General del Proceso" in norm["full_text"]
          and len(md.get("content_sha256", "")) == 64
          and md.get("source_url", "").startswith("http://fp.test")
          and md.get("ingesta") == "corpus_factory"
          and md.get("verified_source") is True
          and fetched_ok)

    # === 2 · Validación de identidad rechaza texto de OTRA ley -> None ===
    fp_wrong = FuncionPublicaAdapter(
        fp_cfg, http=_FakeHttp({"http://fp.test/norma.php?i=48425": _FakeResponse(FP_WRONG_HTML)}))
    wrong = await fp_wrong.fetch_norm(entry)
    check("FuncionPublica: identidad no confirmada (otra ley) -> None (fail-closed)",
          wrong is None)

    # === 3 · SuinJuriscol parsea bytes utf-8 aunque el <meta> declare charset=utf-16 ===
    suin_cfg = {"code": "suin", "base_url": "http://suin.test/viewDocument.asp"}
    suin_http = _FakeHttp({"http://suin.test/viewDocument.asp?id=1827111":
                           _FakeResponse(SUIN_OK_HTML, encoding="utf-8")})
    suin = SuinJuriscolAdapter(suin_cfg, http=suin_http)
    suin_entry = {"source_id": "1827111", "norm_type": "ley", "norm_number": "Ley 84 de 1873",
                  "issuing_body": "Congreso de los Estados Unidos de Colombia",
                  "title": "Código Civil", "effective_date": "1873-05-26",
                  "practice_areas": ["civil"]}
    suin_norm = await suin.fetch_norm(suin_entry)
    check("SuinJuriscol: decodifica utf-8 pese al charset=utf-16 declarado y valida identidad",
          suin_norm is not None
          and suin_norm["title"] == "Código Civil"
          and "Código Civil" in suin_norm["full_text"]
          and len(suin_norm["metadata"].get("content_sha256", "")) == 64
          and suin_norm["metadata"].get("source") == "suin")

    # === 4 · SuinJuriscol: identidad no confirmada (otra ley) -> None ===
    suin_wrong = SuinJuriscolAdapter(
        suin_cfg,
        http=_FakeHttp({"http://suin.test/viewDocument.asp?id=1827111":
                        _FakeResponse(SUIN_WRONG_HTML, encoding="utf-8")}))
    suin_wrong_result = await suin_wrong.fetch_norm(suin_entry)
    check("SuinJuriscol: identidad no confirmada (otra ley) -> None (fail-closed)",
          suin_wrong_result is None)

    # === 5 · CorteConstitucional parsea Word-HTML: extrae MP y decision_number ===
    cc_url = "http://cc.test/relatoria/2005/C-590-05.htm"
    cc_http = _FakeHttp({cc_url: _FakeResponse(CC_OK_HTML, encoding="cp1252")})
    cc = CorteConstitucionalAdapter(cc_cfg, http=cc_http)
    ruling = await cc.fetch_ruling({"tipo": "C", "numero": "590", "anio": 2005})
    check("CorteConstitucional: parsea providencia, extrae MP y decision_number correcto",
          ruling is not None
          and ruling["decision_number"] == "C-590 de 2005"
          and ruling["court"] == "Corte Constitucional"
          and (ruling.get("magistrado_ponente") or "").upper().startswith("JAIME")
          and ruling["metadata"].get("full_text_omitted") is True)

    # === 6 · Shell vacío de la SPA -> None ===
    cc_shell = CorteConstitucionalAdapter(
        cc_cfg, http=_FakeHttp({cc_url: _FakeResponse(CC_SHELL_HTML, encoding="cp1252")}))
    shell = await cc_shell.fetch_ruling({"tipo": "C", "numero": "590", "anio": 2005})
    check("CorteConstitucional: shell vacío de la SPA -> None", shell is None)

    # === 5b · El catálogo verificado PREFIERE sobre HTML con basura (MP y fecha) ===
    cc_url_t025 = "http://cc.test/relatoria/2004/T-025-04.htm"
    cc_garbage_http = _FakeHttp({cc_url_t025: _FakeResponse(CC_GARBAGE_MP_HTML, encoding="cp1252")})
    cc_override = CorteConstitucionalAdapter(cc_cfg, http=cc_garbage_http)
    entry_verified = {"tipo": "T", "numero": "025", "anio": 2004,
                      "magistrado_ponente": "Manuel José Cepeda Espinosa",
                      "decision_date": "2004-01-22"}
    ruling_override = await cc_override.fetch_ruling(entry_verified)
    check("CorteConstitucional: catálogo verificado (magistrado_ponente/decision_date) "
          "PREFIERE sobre lo extraído del HTML con basura",
          ruling_override is not None
          and ruling_override["magistrado_ponente"] == "Manuel José Cepeda Espinosa"
          and ruling_override["decision_date"] == date(2004, 1, 22)
          and "decision_date_approx" not in ruling_override["metadata"])

    # === 5c · Sin catálogo y sin patrón limpio "Magistrado Ponente:" (M.P. abreviado
    # abandonado) -> magistrado_ponente vacío, mejor vacío que basura ===
    cc_dirty_http = _FakeHttp({cc_url_t025: _FakeResponse(CC_DIRTY_MP_HTML, encoding="cp1252")})
    cc_fallback = CorteConstitucionalAdapter(cc_cfg, http=cc_dirty_http)
    ruling_fallback = await cc_fallback.fetch_ruling({"tipo": "T", "numero": "025", "anio": 2004})
    check("CorteConstitucional: sin catálogo y sin patrón limpio de MP -> "
          "magistrado_ponente vacío (mejor vacío que basura)",
          ruling_fallback is not None
          and ruling_fallback.get("magistrado_ponente") is None
          and ruling_fallback["decision_date"] == date(2004, 1, 22))

    # === 7 · Segmentación de norma grande (>500k): SIN rango de artículos en el label
    # (defecto verificado 2026-07-08: la regex agarraba artículos CITADOS dentro del texto,
    # no encabezados reales, produciendo rangos falsos/invertidos como "arts. 370–292") ===
    big = "".join(f"ARTÍCULO {i}. " + ("x" * 1000) + " " for i in range(1, 700))
    big_norm = {"norm_type": "decreto", "norm_number": "Decreto 410 de 1971",
                "issuing_body": "Presidencia", "title": "Código de Comercio",
                "effective_date": date(1971, 3, 27), "full_text": big, "metadata": {}}
    segs = segment_norm(big_norm)
    total = len(segs)
    check("Segmentación: norma >500k se parte en >=2 segmentos, cada uno <=límite, "
          "label '{base} (parte i de N)' SIN rango de artículos",
          len(big) > MAX_NORM_CHARS and len(segs) >= 2
          and all(len(s["full_text"]) <= MAX_NORM_CHARS for s in segs)
          and all(s["norm_number"] == f"Decreto 410 de 1971 (parte {i + 1} de {total})"
                  for i, s in enumerate(segs))
          and all("arts" not in s["norm_number"].lower() for s in segs)
          and all(s["metadata"].get("segment") == i + 1 for i, s in enumerate(segs))
          and all(s["metadata"].get("segments_total") == total for s in segs)
          and all(s["metadata"].get("parent_norm") == "Decreto 410 de 1971" for s in segs))

    # === tests contra la DB real (con fake http) ===
    write_cftest_pack()
    fake = _FakeHttp({f"{FP_BASE}?i=777": _FakeResponse(FP_CFTEST_HTML)})
    await pool.open_pool()
    try:
        # === 8 · dry_run NO escribe ===
        clean_markers()
        before = count_norms("issuing_body LIKE 'CF_TEST%%'", ())
        dr = await ingest_catalog(jurisdiction="cftest", http=fake, only="norms",
                                  dry_run=True, pause=0.0)
        after = count_norms("issuing_body LIKE 'CF_TEST%%'", ())
        check("dry_run: reporta normas pero NO escribe en la base",
              before == 0 and after == 0 and dr["norms"] >= 1)

        # === 9 · Gate ToS + ingesta idempotente ===
        clean_markers()
        s1 = await ingest_catalog(jurisdiction="cftest", http=fake, only="norms", pause=0.0)
        c1 = count_norms("issuing_body LIKE 'CF_TEST%%'", ())
        s2 = await ingest_catalog(jurisdiction="cftest", http=fake, only="norms", pause=0.0)
        c2 = count_norms("issuing_body LIKE 'CF_TEST%%'", ())
        blocked_cnt = count_norms("title = %s", ("No debe entrar",))
        check("Gate ToS: fuente tos_ok=false se salta entera (nada insertado)",
              s1["skipped_tos"] >= 1 and blocked_cnt == 0)
        check("Ingesta idempotente: dos corridas no duplican filas",
              c1 == 1 and c2 == 1 and s1["norms"] == 1 and s2["norms"] == 1)
    finally:
        clean_markers()
        await pool.close_pool()
        remove_cftest_pack()


def main() -> int:
    print("== Data Factory del corpus jurídico (corpus_factory) ==")
    clean_markers()
    remove_cftest_pack()
    try:
        asyncio.run(run_gate())
    finally:
        clean_markers()
        remove_cftest_pack()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("corpus_factory OK — Data Factory verificado.")
        return 0
    print("corpus_factory FAIL — HALT: no avanzar.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
