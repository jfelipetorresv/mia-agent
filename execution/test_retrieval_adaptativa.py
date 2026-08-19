"""
Mia · test_retrieval_adaptativa.py — gate de la LECTURA ADAPTATIVA del expediente.

El problema que cierra: con 743.600 caracteres indexados Mia leía 8 fragmentos
(≈9.600 caracteres, el 1,3% del material) porque el tamaño de lectura era el literal
`top_k=8`. Al mismo tiempo el presupuesto de recorte del nodo que consume esos
fragmentos era ~50 veces mayor: había sitio de sobra y nadie lo usaba.

Lo que se verifica:

  A · PLAN (puro, offline — sin DB, sin red, sin LLM)
     a1. Corpus pequeño ⇒ se pide poco; corpus grande ⇒ se pide mucho.
     a2. NUNCA por debajo del piso histórico de 8, ni con corpus mínimo, ni con
         presupuesto ridículo, ni con la pregunta más trivial.
     a3. El techo se DERIVA del presupuesto real y jamás lo desborda: lo planificado
         deja sitio al prompt del sistema y a la respuesta por construcción.
     a4. La complejidad de la pregunta mueve la lectura en la dirección correcta.

  B · CALIDAD (puro)
     b1. Dedup: fragmentos idénticos y casi idénticos no se repiten.
     b2. Solape: la repetición literal entre fragmentos contiguos (la ingesta corta con
         150 caracteres de solape) se recorta sin inventar ni perder texto.
     b3. Diversidad: no salen todos del mismo documento habiendo varios, y el corte
         nunca devuelve menos material del pedido habiendo material disponible.

  C · BASE VIVA (DB real, RLS de verdad)
     c1. `matter_chunk_stats` cuenta el material real del asunto y aísla por despacho.
     c2. `retrieve_rrf` devuelve `document_id` y `ord` (sin ellos no hay dedup por
         pieza, ni tope por documento, ni vecinos).
     c3. hnsw.ef_search: NO se toca por debajo de 40 y SÍ se fija por encima — con
         `candidates` alto y ef_search por defecto el recall se degrada EN SILENCIO.
     c4. Pedir mucho sobre un asunto grande devuelve mucho (el literal 8 ya no manda).
     c5. `expand_neighbors` trae los fragmentos contiguos y respeta el asunto.

Limpia sus datos al terminar. Exit 0 = PASS · 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_retrieval_adaptativa.py
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
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

from mia import config, embeddings                           # noqa: E402
from mia.agents import context_recovery as cr                # noqa: E402
from mia.agents import graph as graph_mod                    # noqa: E402
from mia.agents import retrieval                             # noqa: E402
from mia.agents.graph import MatterGraphBuilder              # noqa: E402
from mia.db import pool                                      # noqa: E402
from mia.memory.trace_capture import TraceCapture            # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres",
    password=os.getenv("PG_PASSWORD", ""),
)
TENANT_NAMES = ("ADAPT_TEST_A", "ADAPT_TEST_B")

# Presupuesto real del nodo consumidor: el MISMO que usan los shrink del grafo.
BUDGET = graph_mod._retrieval_budget_tokens()

Q_TRIVIAL = "hechos"
Q_MEDIA = "¿Se configuró la caducidad de la acción según el expediente?"
Q_EXHAUSTIVA = ("Compara todos los contratos del expediente, sus anexos y otrosíes, y "
                "enumera cada obligación incumplida con su fecha y su folio, "
                "íntegramente y sin omitir ninguna pieza")


# ─────────────────────────────────────────────────────────────────────────────
# A · el plan de lectura (puro)
# ─────────────────────────────────────────────────────────────────────────────
def _stats(n_chunks: int, avg_chars: int = 1200) -> dict:
    return {"n_chunks": n_chunks, "n_documents": max(1, n_chunks // 10),
            "total_chars": n_chunks * avg_chars, "avg_chars": float(avg_chars)}


def test_plan() -> None:
    print("\nA · plan de lectura (puro, offline)")

    pequeno = retrieval.plan_reading(_stats(10), Q_MEDIA, BUDGET)
    grande = retrieval.plan_reading(_stats(620), Q_MEDIA, BUDGET)

    # a1 · corpus pequeño pide poco, corpus grande pide mucho.
    check("a1 · corpus pequeño (10 fragmentos) no pide más de lo que existe",
          pequeno.top_k <= 10)
    check("a1 · corpus grande (620 fragmentos) pide MUCHO más que el literal de antes",
          grande.top_k > 8 * 4)
    check("a1 · corpus grande lee una fracción REAL del material (>10%)",
          grande.top_k / 620.0 > 0.10)

    # a2 · piso histórico intocable.
    casos_piso = [
        ("corpus mínimo", retrieval.plan_reading(_stats(1), Q_TRIVIAL, BUDGET)),
        ("presupuesto ridículo", retrieval.plan_reading(_stats(620), Q_TRIVIAL, 10)),
        ("pregunta vacía", retrieval.plan_reading(_stats(620), "", BUDGET)),
        ("fragmentos gigantes", retrieval.plan_reading(_stats(620, 90000), Q_TRIVIAL,
                                                       BUDGET)),
    ]
    check("a2 · nunca se pide menos que el piso histórico de 8 (%s)" % ", ".join(
        f"{n}={p.top_k}" for n, p in casos_piso),
        all(p.top_k >= 8 for _, p in casos_piso)
        and config.MIA_RETRIEVAL_MIN_TOP_K == 8)

    # a2 bis · `plan_reading` es PÚBLICA: no puede romperse ni martillear la base si la
    # llaman sin el gate de intake que hoy le garantiza stats y presupuesto.
    sin_presupuesto = retrieval.plan_reading(_stats(620), Q_MEDIA, None)
    sin_material = retrieval.plan_reading({}, Q_EXHAUSTIVA, BUDGET)
    sin_stats = retrieval.plan_reading(None, Q_EXHAUSTIVA, BUDGET)
    check("a2 · sin presupuesto declarado no rompe: planifica el piso (%d)"
          % sin_presupuesto.top_k,
          sin_presupuesto.top_k == config.MIA_RETRIEVAL_MIN_TOP_K)
    check("a2 · sin material medido pide el PISO, no el techo (%d fragmentos, %d "
          "candidatos)" % (sin_material.top_k, sin_material.candidates),
          sin_material.top_k == config.MIA_RETRIEVAL_MIN_TOP_K
          and sin_material.candidates == config.MIA_RETRIEVAL_MIN_CANDIDATES
          and sin_stats == sin_material)

    # a3 · el techo se deriva del presupuesto y NO lo desborda.
    desbordes = []
    for n in (5, 50, 620, 5000):
        for avg in (400, 1200, 4000):
            for q in (Q_TRIVIAL, Q_MEDIA, Q_EXHAUSTIVA):
                for budget in (BUDGET, BUDGET // 4, 400):
                    p = retrieval.plan_reading(_stats(n, avg), q, budget)
                    # Lo planificado (por encima del piso) tiene que caber en el
                    # presupuesto del nodo. El piso es un mínimo irrenunciable: si ni
                    # 8 fragmentos caben, los shrink del grafo son quien recorta.
                    planificado = p.top_k * (avg / 4.0)
                    if p.top_k > 8 and planificado > budget:
                        desbordes.append((n, avg, budget, p.top_k))
    check("a3 · el plan NUNCA desborda el presupuesto del nodo (%d combinaciones)"
          % (4 * 3 * 3 * 3), not desbordes)
    check("a3 · el techo deja margen para el prompt y la respuesta (cobertura < 100%)",
          all(retrieval.plan_reading(_stats(5000), q, BUDGET).target_tokens
              <= BUDGET * config.MIA_RETRIEVAL_MAX_COVERAGE_FRACTION
              for q in (Q_TRIVIAL, Q_MEDIA, Q_EXHAUSTIVA))
          and config.MIA_RETRIEVAL_MAX_COVERAGE_FRACTION < 1.0)
    check("a3 · el presupuesto sale de context_recovery, no de un número inventado",
          BUDGET == min(cr.budget_for(n, config.MIA_CONTEXT_WINDOW)
                        for n in graph_mod.RETRIEVAL_BUDGET_NODES) and BUDGET > 0)

    # a4 · la pregunta mueve la lectura.
    triv = retrieval.plan_reading(_stats(5000), Q_TRIVIAL, BUDGET)
    media = retrieval.plan_reading(_stats(5000), Q_MEDIA, BUDGET)
    exh = retrieval.plan_reading(_stats(5000), Q_EXHAUSTIVA, BUDGET)
    check("a4 · pregunta exhaustiva ⇒ se lee más que una trivial (%d > %d > %d)"
          % (exh.top_k, media.top_k, triv.top_k),
          exh.top_k >= media.top_k >= triv.top_k and exh.top_k > triv.top_k)
    check("a4 · la heurística es determinista (misma pregunta ⇒ mismo plan)",
          retrieval.question_complexity(Q_EXHAUSTIVA)
          == retrieval.question_complexity(Q_EXHAUSTIVA)
          and retrieval.plan_reading(_stats(620), Q_MEDIA, BUDGET) == grande)
    check("a4 · las notas del despacho escalan con la misma señal, con tope propio",
          exh.knowledge_top_k >= triv.knowledge_top_k
          and exh.knowledge_top_k <= config.MIA_KNOWLEDGE_MAX_TOP_K
          and triv.knowledge_top_k >= config.MIA_KNOWLEDGE_MIN_TOP_K)

    # colchón y candidatos coherentes
    check("a4 · se piden más filas de las que se entregan (colchón para dedup)",
          grande.fetch_k >= grande.top_k and grande.candidates >= grande.fetch_k)


# ─────────────────────────────────────────────────────────────────────────────
# B · calidad de lo recuperado (puro)
# ─────────────────────────────────────────────────────────────────────────────
CUERPO = " ".join(
    f"La cláusula {i} del contrato de obra fija la obligación {i} a cargo del "
    f"contratista y su plazo de cumplimiento." for i in range(40))
# "Casi idéntico" REALISTA: el mismo texto con una palabra distinta — lo que produce un
# documento reingresado con una corrección menor, no un texto ampliado.
CASI = CUERPO.replace("cláusula 7 ", "estipulación séptima ")
DISTINTO = " ".join(
    f"El perito rindió su dictamen {i} sobre la avería del equipo y estimó el daño "
    f"emergente correspondiente." for i in range(40))
# CITA ENTRE PIEZAS: un escrito transcribe LITERALMENTE otra pieza del expediente. La
# pieza citada es un documento propio, corto, con SU archivo y SU folio. Si el dedup la
# borra por estar "contenida" en quien la cita, el abogado pierde la fuente primaria y
# solo puede anclar al documento que la reproduce. Es material distinto, no repetición.
PIEZA_CITADA = ("La resolución 118 declaró el incumplimiento del contratista y ordenó "
                "hacer efectiva la cláusula penal pecuniaria pactada en el contrato.")
ESCRITO_QUE_CITA = ("En sus alegatos la parte transcribe la pieza así: " + PIEZA_CITADA
                    + " " + CUERPO)


def _row(i: int, content: str, doc: str, ord_: int, score: float,
         filename: str | None = None, folio: str | None = None) -> dict:
    return {"id": f"c{i}", "content": content, "score": score,
            "filename": filename or f"{doc}.pdf", "folio_ancla": folio,
            "document_id": doc, "ord": ord_}


def test_calidad() -> None:
    print("\nB · calidad de lo recuperado (puro, offline)")

    # b1 · duplicado exacto y casi-duplicado.
    rows = [
        _row(1, CUERPO, "docA", 0, 0.9),
        _row(2, CUERPO, "docB", 0, 0.8),                       # idéntico literal
        _row(3, CASI, "docC", 0, 0.7),                         # casi idéntico
        _row(4, CUERPO[:len(CUERPO) // 2], "docA", 5, 0.65),   # contenido, MISMA pieza
        _row(5, DISTINTO, "docD", 0, 0.6),                     # material genuino
    ]
    out = retrieval.dedupe_chunks(rows)
    ids = [r["id"] for r in out]
    check("b1 · el duplicado exacto se elimina", "c2" not in ids)
    check("b1 · el casi-duplicado se elimina", "c3" not in ids)
    check("b1 · el fragmento ya contenido en otro de la MISMA pieza se elimina",
          "c4" not in ids)
    check("b1 · sobrevive el mejor rankeado y el material distinto", ids == ["c1", "c5"])
    check("b1 · no se muta la entrada", rows[0]["content"] == CUERPO)

    # b1 bis · el caso que de verdad duele: DOS PIEZAS DISTINTAS donde una contiene a la
    # otra porque la transcribe. Borrar la citada es perder una pieza entera del
    # expediente CON SU FOLIO — el abogado ya no puede anclar a la fuente primaria, solo
    # al documento que la cita. El solape que hay que eliminar es el que creó la ingesta
    # (fragmentos contiguos de la MISMA pieza), no la cita entre documentos.
    citada = [
        _row(30, ESCRITO_QUE_CITA, "docEscrito", 0, 0.9, "alegatos.pdf", "40"),
        _row(31, PIEZA_CITADA, "docResolucion", 0, 0.5, "resolucion_118.pdf", "12"),
    ]
    out_cita = retrieval.dedupe_chunks(citada)
    ids_cita = [r["id"] for r in out_cita]
    fuente = next((r for r in out_cita if r["id"] == "c31"), None)
    check("b1 · la fuente primaria NO se pierde porque otro documento la transcriba (%s)"
          % ids_cita, ids_cita == ["c30", "c31"])
    check("b1 · y llega con SU archivo y SU folio, no con los de quien la cita",
          fuente is not None and fuente["filename"] == "resolucion_118.pdf"
          and fuente["folio_ancla"] == "12")
    check("b1 · dentro de la MISMA pieza el fragmento contenido sí se descarta",
          [r["id"] for r in retrieval.dedupe_chunks([
              _row(40, ESCRITO_QUE_CITA, "docEscrito", 0, 0.9),
              _row(41, PIEZA_CITADA, "docEscrito", 7, 0.5)])] == ["c40"])

    # b2 · solape entre contiguos (lo que la ingesta creó: overlap=150).
    a_txt = "AAA " * 300 + "COLA-COMPARTIDA-" * 12
    b_txt = "COLA-COMPARTIDA-" * 12 + "BBB " * 300
    solapados = [_row(10, a_txt, "docS", 0, 0.9), _row(11, b_txt, "docS", 1, 0.8)]
    out = retrieval.dedupe_chunks(solapados)
    segundo = next(r for r in out if r["id"] == "c11")
    check("b2 · los dos fragmentos contiguos se conservan", len(out) == 2)
    check("b2 · la repetición literal se recorta del segundo",
          not segundo["content"].startswith("COLA-COMPARTIDA-"))
    check("b2 · el texto NUEVO del segundo queda intacto",
          segundo["content"].startswith("BBB") and "BBB " * 300 in segundo["content"])
    check("b2 · nada se recorta cuando no hay solape real",
          retrieval.dedupe_chunks(
              [_row(20, "AAA " * 200, "docT", 0, 0.9),
               _row(21, "BBB " * 200, "docT", 1, 0.8)])[1]["content"].startswith("BBB"))

    # b3 · diversidad. Escenario realista: una pieza larga (una sentencia) monopoliza el
    # ranking y las demás piezas del expediente quedan fuera del prompt.
    dominante = [_row(100 + i, f"Fragmento singular número {i} " + "x" * 40 * i,
                      "docGrande", i, 1.0 - i * 0.01) for i in range(20)]
    otras = [_row(200 + i, f"Pieza distinta del expediente {i} " + "y" * 40 * i,
                  f"docChico{i % 3}", i // 3, 0.4 - i * 0.001) for i in range(9)]
    sel = retrieval.enforce_document_diversity(dominante + otras, top_k=10,
                                               max_per_document=4)
    por_doc: dict[str, int] = {}
    for r in sel:
        por_doc[r["document_id"]] = por_doc.get(r["document_id"], 0) + 1
    check("b3 · se entrega exactamente lo pedido", len(sel) == 10)
    check("b3 · NO salen todos del mismo documento habiendo varios (%s)" % por_doc,
          len(por_doc) > 1 and por_doc["docGrande"] <= 4)
    check("b3 · sin el tope, los 10 habrían salido de la misma pieza",
          all(r["document_id"] == "docGrande" for r in (dominante + otras)[:10]))
    check("b3 · con un solo documento el tope no se aplica (no hay diversidad que ganar)",
          len(retrieval.enforce_document_diversity(dominante, top_k=10,
                                                   max_per_document=4)) == 10)
    relleno = retrieval.enforce_document_diversity(dominante + otras[:1], top_k=10,
                                                   max_per_document=4)
    check("b3 · sin alternativas suficientes se RELLENA: nunca menos material del pedido",
          len(relleno) == 10)
    check("b3 · el tope es un REPARTO, no un límite duro: el relleno lo supera a "
          "propósito (%d de la misma pieza)"
          % sum(1 for r in relleno if r["document_id"] == "docGrande"),
          sum(1 for r in relleno if r["document_id"] == "docGrande") > 4)
    check("b3 · una fila corrupta no tumba el reparto",
          len(retrieval.enforce_document_diversity(
              [dominante[0], None, otras[0]], top_k=3, max_per_document=4)) == 2)
    check("b3 · lo devuelto sale ordenado por relevancia",
          [r["score"] for r in sel] == sorted((r["score"] for r in sel), reverse=True))
    check("b3 · sin material devuelve vacío, no explota",
          retrieval.enforce_document_diversity([], 10, 4) == []
          and retrieval.dedupe_chunks([]) == [])

    # ef_search: la trampa silenciosa
    check("c3 · ef_search NO se toca por debajo del default de pgvector (40)",
          retrieval.ef_search_for(20) is None and retrieval.ef_search_for(40) is None)
    check("c3 · ef_search SÍ se fija en cuanto se piden más de 40 candidatos",
          retrieval.ef_search_for(41) is not None
          and retrieval.ef_search_for(200) >= 200
          and retrieval.ef_search_for(5000) <= retrieval.PGVECTOR_MAX_EF_SEARCH)


# ─────────────────────────────────────────────────────────────────────────────
# C · base viva
# ─────────────────────────────────────────────────────────────────────────────
N_CHUNKS = 90          # asunto "grande" del tenant A (repartido en 3 piezas)
CHUNK_CHARS = 1200


def _vlit(axis: int) -> str:
    v = [0.0] * config.EMBED_DIM
    v[axis % config.EMBED_DIM] = 1.0
    return retrieval._vector_literal(v)


QVEC = [0.0] * config.EMBED_DIM
QVEC[0] = 1.0
TRACE_DIR = tempfile.mkdtemp(prefix="mia_adapt_")


class EmbedCounter:
    """embed_texts falso (determinista) que además cuenta las llamadas a Voyage."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, texts):
        self.calls += 1
        return [list(QVEC) for _ in texts]


EMBED = EmbedCounter()
embeddings.embed_texts = EMBED  # graph.py resuelve el atributo al llamar


def _state(tenant: str, matter: str, msg: str) -> dict:
    return {"tenant_id": tenant, "matter_id": matter,
            "messages": [{"role": "user", "content": msg}],
            "documents": [], "metadata": {}}


def seed() -> dict:
    with psycopg.connect(autocommit=True, **PG) as s:
        s.execute("DELETE FROM tenants WHERE name = ANY(%s)", (list(TENANT_NAMES),))
        a = s.execute("INSERT INTO tenants(name) VALUES ('ADAPT_TEST_A') "
                      "RETURNING id").fetchone()[0]
        b = s.execute("INSERT INTO tenants(name) VALUES ('ADAPT_TEST_B') "
                      "RETURNING id").fetchone()[0]
        ma = s.execute("INSERT INTO matters(tenant_id,title) VALUES (%s,'Asunto grande') "
                       "RETURNING id", (a,)).fetchone()[0]
        mb = s.execute("INSERT INTO matters(tenant_id,title) VALUES (%s,'Asunto B') "
                       "RETURNING id", (b,)).fetchone()[0]
        docs = []
        for k in range(3):
            docs.append(s.execute(
                "INSERT INTO documents(tenant_id,matter_id,filename) "
                "VALUES (%s,%s,%s) RETURNING id",
                (a, ma, f"pieza_{k}.pdf")).fetchone()[0])
        for i in range(N_CHUNKS):
            doc = docs[i % 3]
            ord_ = i // 3
            # Contenido único por fragmento (el dedup no debe comerse material real) y
            # con el término de la consulta para que también entre por full-text.
            texto = (f"Fragmento {i} de la pieza {i % 3}. caducidad accion reparacion. "
                     + f"cuerpo{i} " * 200)[:CHUNK_CHARS]
            s.execute("INSERT INTO chunks(tenant_id,document_id,ord,content,embedding) "
                      "VALUES (%s,%s,%s,%s,%s::vector)",
                      (a, doc, ord_, texto, _vlit(0 if i % 2 == 0 else 1)))
        db = s.execute("INSERT INTO documents(tenant_id,matter_id,filename) "
                       "VALUES (%s,%s,'ajeno.pdf') RETURNING id",
                       (b, mb)).fetchone()[0]
        s.execute("INSERT INTO chunks(tenant_id,document_id,ord,content,embedding) "
                  "VALUES (%s,%s,0,%s,%s::vector)",
                  (b, db, "SECRETO_B caducidad accion reparacion del otro despacho.",
                   _vlit(0)))
        # Asunto sin un solo documento: verifica que el gate "no hay nada que
        # recuperar" sobrevive al cambio (cero llamadas a embeddings).
        mv = s.execute("INSERT INTO matters(tenant_id,title) VALUES (%s,'Asunto vacío') "
                       "RETURNING id", (b,)).fetchone()[0]
    return {"a": str(a), "b": str(b), "ma": str(ma), "mb": str(mb), "mv": str(mv)}


def cleanup() -> None:
    with psycopg.connect(autocommit=True, **PG) as s:
        s.execute("DELETE FROM tenants WHERE name = ANY(%s)", (list(TENANT_NAMES),))
    shutil.rmtree(TRACE_DIR, ignore_errors=True)


async def db_flow(ids: dict) -> dict:
    obs: dict = {}
    await pool.open_pool()
    try:
        obs["stats_a"] = await retrieval.matter_chunk_stats(ids["a"], ids["ma"])
        obs["stats_b"] = await retrieval.matter_chunk_stats(ids["b"], ids["mb"])
        # AISLAMIENTO: el despacho B no puede medir el asunto de A.
        obs["stats_cruzado"] = await retrieval.matter_chunk_stats(ids["b"], ids["ma"])

        plan = retrieval.plan_reading(obs["stats_a"], Q_EXHAUSTIVA, BUDGET)
        obs["plan"] = plan
        obs["docs"] = await graph_mod._read_matter_adaptive(
            ids["a"], ids["ma"], Q_EXHAUSTIVA, QVEC, plan)
        # Camino SELECTIVO: el mismo asunto con un presupuesto estrecho (un modelo de
        # ventana pequeña) debe leer menos, no romperse.
        plan_estrecho = retrieval.plan_reading(obs["stats_a"], Q_TRIVIAL, 6000)
        obs["plan_estrecho"] = plan_estrecho
        obs["docs_estrecho"] = await graph_mod._read_matter_adaptive(
            ids["a"], ids["ma"], Q_TRIVIAL, QVEC, plan_estrecho)

        # ef_search real contra la base viva, en la misma forma que lo hace retrieve_rrf.
        # `current_setting(..., true)` y no SHOW: pgvector no DEFINE el parámetro hasta
        # que su módulo se carga en el backend, y SHOW sobre un parámetro no definido
        # lanza. Se consulta DESPUÉS de una operación vectorial para que el módulo esté
        # cargado y el valor sea el que realmente usará el índice.
        async with pool.tenant_connection(ids["a"]) as conn:
            await retrieval._apply_ef_search(conn, 20)
            await conn.execute("SELECT '[1,0,0]'::vector <=> '[0,1,0]'::vector")
            obs["ef_bajo"] = (await (await conn.execute(
                "SELECT current_setting('hnsw.ef_search', true)")).fetchone())[0]
        async with pool.tenant_connection(ids["a"]) as conn:
            await retrieval._apply_ef_search(conn, 300)
            await conn.execute("SELECT '[1,0,0]'::vector <=> '[0,1,0]'::vector")
            obs["ef_alto"] = (await (await conn.execute(
                "SELECT current_setting('hnsw.ef_search', true)")).fetchone())[0]
            # y la consulta real sigue funcionando con el parámetro puesto
            obs["rrf_con_ef"] = len(await (await conn.execute(
                retrieval._RRF_SQL,
                {"qvec": retrieval._vector_literal(QVEC), "qtext": Q_MEDIA,
                 "matter": ids["ma"], "cand": 300, "k": retrieval.RRF_K,
                 "topk": 60})).fetchall())

        anclas = [d for d in obs["docs"] if d.get("ord") == 5][:1]
        obs["anclas"] = anclas
        if anclas:
            obs["vecinos"] = await retrieval.expand_neighbors(
                ids["a"], ids["ma"], anclas, radius=1)
        else:
            obs["vecinos"] = []
        # AISLAMIENTO: pedir vecinos del asunto de A desde B no devuelve nada de A.
        obs["vecinos_cruzado"] = await retrieval.expand_neighbors(
            ids["b"], ids["ma"], anclas, radius=1) if anclas else []

        # d · el NODO real de principio a fin (no solo sus piezas).
        builder = MatterGraphBuilder(trace_capture=TraceCapture(TRACE_DIR))
        obs["intake_a"] = await builder.intake_node(_state(ids["a"], ids["ma"],
                                                           Q_EXHAUSTIVA))
        obs["embed_calls_a"] = EMBED.calls
        EMBED.calls = 0
        # Asunto SIN material indexado: el gate se conserva (cero llamadas a Voyage).
        obs["intake_vacio"] = await builder.intake_node(_state(ids["b"], ids["mv"],
                                                               Q_EXHAUSTIVA))
        obs["embed_calls_vacio"] = EMBED.calls
    finally:
        await pool.close_pool()
    return obs


def test_db(obs: dict) -> None:
    print("\nC · base viva (DB real, RLS activo)")
    sa, sb, sx = obs["stats_a"], obs["stats_b"], obs["stats_cruzado"]
    check("c1 · el conteo del material es REAL (no un EXISTS): %d fragmentos, %d piezas"
          % (sa["n_chunks"], sa["n_documents"]),
          sa["n_chunks"] == N_CHUNKS and sa["n_documents"] == 3)
    check("c1 · el tamaño medio del fragmento se mide, no se supone",
          900 < sa["avg_chars"] <= CHUNK_CHARS)
    check("c1 · AISLAMIENTO: otro despacho no puede medir este asunto",
          sx["n_chunks"] == 0 and sb["n_chunks"] == 1)

    docs = obs["docs"]
    check("c2 · cada fragmento trae su pieza y su posición (document_id + ord)",
          bool(docs) and all(d.get("document_id") and isinstance(d.get("ord"), int)
                             for d in docs))
    check("c2 · sigue trayendo su procedencia (archivo) y el folio sin inventarlo",
          all("filename" in d and "folio_ancla" in d for d in docs)
          and all(d["folio_ancla"] is None for d in docs))

    check("c3 · con pocos candidatos NO se toca el índice (%s)" % obs["ef_bajo"],
          obs["ef_bajo"] == "40")
    check("c3 · con muchos candidatos se fija ef_search en la base (%s)" % obs["ef_alto"],
          int(obs["ef_alto"]) >= 300)
    check("c3 · la consulta real corre con ef_search puesto y devuelve filas",
          obs["rrf_con_ef"] > 0)

    plan = obs["plan"]
    check("c4 · el asunto grande se lee de verdad: %d fragmentos de %d (antes: 8)"
          % (len(docs), N_CHUNKS), len(docs) > 8 and len(docs) <= plan.top_k)
    check("c4 · se lee una fracción sustancial del asunto (>25%%): %.0f%%"
          % (100.0 * len(docs) / N_CHUNKS), len(docs) / float(N_CHUNKS) > 0.25)
    por_doc: dict[str, int] = {}
    for d in docs:
        por_doc[d["document_id"]] = por_doc.get(d["document_id"], 0) + 1
    check("c4 · el material llega de varias piezas del expediente (%d)" % len(por_doc),
          len(por_doc) >= 2)
    check("c4 · no se repite ningún fragmento",
          len({d["id"] for d in docs}) == len(docs))

    estrecho, pe = obs["docs_estrecho"], obs["plan_estrecho"]
    check("c4 · con presupuesto estrecho se lee MENOS del mismo asunto (%d < %d)"
          % (len(estrecho), len(docs)), 8 <= len(estrecho) < len(docs))
    check("c4 · el camino estrecho respeta su propio plan y su reparto por pieza",
          len(estrecho) <= pe.top_k
          and max((sum(1 for d in estrecho if d["document_id"] == k)
                   for k in {d["document_id"] for d in estrecho}), default=0)
          <= pe.max_per_document)

    vec = obs["vecinos"]
    ords = sorted(d["ord"] for d in vec)
    check("c5 · los vecinos contiguos se traen (ords %s)" % ords,
          len(vec) >= 2 and ords == list(range(min(ords), min(ords) + len(ords))))
    check("c5 · AISLAMIENTO: otro despacho no obtiene vecinos de este asunto",
          len(obs["vecinos_cruzado"]) == len(obs["anclas"]))
    check("c5 · los vecinos están APAGADOS por defecto (opt-in por instalación)",
          config.MIA_RETRIEVAL_NEIGHBOR_RADIUS == 0)

    print("\nD · el nodo real de principio a fin")
    intake = obs["intake_a"]
    ndocs = len(intake.get("documents") or [])
    check("d1 · el turno real lee el expediente adaptativamente (%d fragmentos)" % ndocs,
          ndocs > 8)
    check("d2 · el contexto del turno DICE LA VERDAD sobre cuánto se leyó",
          ("recuperados en este turno: %d." % ndocs)
          in graph_mod._matter_context_for(intake))
    check("d3 · la metadata del turno coincide con lo realmente leído",
          intake["metadata"].get("retrieved") == ndocs)
    check("d4 · un solo embedding de la consulta en todo el turno",
          obs["embed_calls_a"] == 1)
    vacio = obs["intake_vacio"]
    check("d5 · asunto SIN material: cero documentos y CERO llamadas a embeddings",
          (vacio.get("documents") or []) == [] and obs["embed_calls_vacio"] == 0)
    check("d6 · el contexto de un asunto vacío sigue siendo honesto",
          "recuperados en este turno: 0." in graph_mod._matter_context_for(vacio))


def main() -> int:
    print("=" * 74)
    print("test_retrieval_adaptativa · lectura adaptativa del expediente")
    print("presupuesto del nodo consumidor: %d tokens (ventana %d)"
          % (BUDGET, config.MIA_CONTEXT_WINDOW))
    print("=" * 74)
    test_plan()
    test_calidad()
    ids = seed()
    try:
        obs = asyncio.run(db_flow(ids))
        test_db(obs)
    finally:
        cleanup()
    fallos = [n for n, ok in _results if not ok]
    print("\n" + "=" * 74)
    print("%d/%d comprobaciones OK" % (len(_results) - len(fallos), len(_results)))
    if fallos:
        print("FALLA:")
        for n in fallos:
            print("  - " + n)
    print("=" * 74)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
