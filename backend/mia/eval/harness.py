"""Mia · eval.harness — correr el banco de pruebas y persistir la corrida (CP-E4).

Corre casos de oro por el GRAFO COMPLETO de asunto (headless, sin HTTP) y puntúa cada uno
con `scoring.score_turn`. Reusa exactamente el motor de producción: `initial_state` →
`build_matter_graph` → `astream` hasta el interrupt de HITL (donde el borrador y el informe
de verificación de citas YA existen) → `aget_state` para leer el estado. NO aprueba el
borrador (no toca HITL): solo mide lo que Mia produjo.

CANDADO DE DATOS REALES (regla dura, decisión de Pipe): un caso NO sintético (p. ej. sobre un
expediente real del despacho) SOLO corre si el despacho lo autorizó explícitamente
(`tenant_settings.config['eval']['allow_eval_real_data']`, default False, fail-closed). Sin
autorización → `EvalConsentError`. Los casos canónicos de `cases.py` son sintéticos y corren
sin fricción.

SEPARACIÓN: el harness siembra los asuntos de prueba BAJO el `tenant_id` que recibe (RLS) y
corre; el CICLO DE VIDA del tenant de prueba y la limpieza de checkpoints los maneja el
llamador (`execution/run_eval.py` o el gate) con conexión admin.
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

from .. import config, embeddings
from ..agents.checkpointer import open_checkpointer
from ..agents.graph import build_matter_graph
from ..agents.state import initial_state, thread_id_for
from ..db import pool
from .cases import GoldenCase, load_golden_cases
from .scoring import score_turn

logger = logging.getLogger("mia.eval.harness")

_DRAFT_PREVIEW_CHARS = 1200  # cuánto borrador se guarda en la corrida (evita ficheros enormes)


class EvalConsentError(Exception):
    """Se intentó correr un caso NO sintético sin la autorización del despacho
    (`allow_eval_real_data`). `str(e)` es apto para mostrarse en llano."""


# ── política de eval por despacho (candado de datos reales) ───────────────────
async def read_eval_policy(tenant_id: str) -> dict:
    """Política de eval del despacho, leída de `tenant_settings.config['eval']` (RLS).
    `allow_real_data` (default False, fail-closed): si es False, el harness rechaza correr
    casos NO sintéticos. Un fallo de lectura → False (nunca abre el candado por un hipo)."""
    try:
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT config->'eval'->>'allow_eval_real_data' "
                "FROM tenant_settings WHERE tenant_id = %s::uuid",
                (tenant_id,),
            )).fetchone()
        allow = bool(row and str(row[0] or "").strip().lower() in ("true", "1", "yes", "on"))
    except Exception:  # noqa: BLE001 — un fallo de DB NO habilita datos reales: fail-closed
        logger.exception("read_eval_policy: no se pudo leer la política de eval (tenant=%s)",
                         tenant_id)
        allow = False
    return {"allow_real_data": allow}


# ── siembra del asunto de prueba (bajo RLS, como la app) ──────────────────────
async def _seed_case_matter(tenant_id: str, case: GoldenCase) -> str:
    """Crea un asunto de prueba con los documentos del caso (documents+chunks) bajo RLS.
    Devuelve el matter_id.

    Los chunks se insertan CON su `embedding` (igual que la ingesta de producción,
    `routes/ux.py`): `matter_has_chunks` y `retrieve_rrf` FILTRAN por `embedding IS NOT NULL`,
    así que sin el vector intake recuperaría 0 documentos y Mia redactaría A CIEGAS — el eval
    dejaría de ejercitar la recuperación del expediente (hallazgo capa 2, M1). Con el embedding,
    intake recupera la evidencia del caso como en un turno real."""
    async with pool.tenant_connection(tenant_id) as conn:
        mid = (await (await conn.execute(
            "INSERT INTO matters(tenant_id, title) VALUES (%s::uuid, %s) RETURNING id",
            (tenant_id, f"[eval] {case.title}"),
        )).fetchone())[0]
        for doc in case.documents:
            did = (await (await conn.execute(
                "INSERT INTO documents(tenant_id, matter_id, filename) "
                "VALUES (%s::uuid, %s::uuid, %s) RETURNING id",
                (tenant_id, str(mid), doc.filename),
            )).fetchone())[0]
            # Embeddings de los chunks del documento (en un hilo: embed_texts es síncrono,
            # como en intake). Vacío/fallo → se inserta sin vector (el turno sigue).
            texts = list(doc.chunks)
            vectors = await asyncio.to_thread(embeddings.embed_texts, texts) if texts else []
            for i, content in enumerate(texts):
                vec = vectors[i] if i < len(vectors) else None
                await conn.execute(
                    "INSERT INTO chunks(tenant_id, document_id, ord, content, embedding) "
                    "VALUES (%s::uuid, %s::uuid, %s, %s, %s)",
                    (tenant_id, str(did), i, content, vec),
                )
    return str(mid)


# ── correr UN caso por el grafo completo ──────────────────────────────────────
async def run_case(tenant_id: str, case: GoldenCase, *, tenant_allow_real: Optional[bool] = None) -> dict:
    """Corre un caso de oro por el grafo y devuelve su resultado puntuado.

    Candado: un caso NO sintético exige `allow_eval_real_data` del despacho. Se puede pasar
    `tenant_allow_real` ya resuelto (para no releer la política por caso); si es None, se lee.
    """
    if not case.synthetic:
        allow = tenant_allow_real
        if allow is None:
            allow = (await read_eval_policy(tenant_id))["allow_real_data"]
        if not allow:
            raise EvalConsentError(
                "Este caso usa datos reales del despacho. Debes autorizar el uso de datos "
                "reales en las pruebas (Configuración) antes de correrlo.")

    matter_id = await _seed_case_matter(tenant_id, case)
    cfg = {"configurable": {"thread_id": thread_id_for(tenant_id, matter_id)}}
    inp = initial_state(tenant_id, matter_id, case.message,
                        profile_snapshot=case.profile or None)

    started = time.perf_counter()
    async with open_checkpointer() as cp:
        graph = build_matter_graph(cp)
        # astream hasta el interrupt de HITL: el borrador y la verificación ya están hechos.
        async for _ in graph.astream(inp, cfg, stream_mode="updates"):
            pass
        st = await graph.aget_state(cfg)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

    values = st.values if st is not None else {}
    md = dict(values.get("metadata") or {})
    draft = values.get("draft") or ""
    diagnosis = str(md.get("diagnosis") or "")
    # Se usa el INFORME del verificador del grafo (calculado sobre el borrador ANTES de
    # anotarlo): para cuando llegamos al HITL el borrador ya trae las [VERIFICAR] insertadas,
    # así que re-escanearlo perdería la señal de disciplina. `sources` se pasa como respaldo
    # para el caso sin informe.
    sources = md.get("research_sources")
    score = score_turn(draft, diagnosis, md, sources=sources,
                       verification_report=md.get("verification"))

    return {
        "case_id": case.id,
        "title": case.title,
        "matter_id": matter_id,
        "elapsed_ms": elapsed_ms,
        "score": score,
        "verification": md.get("verification") or {},
        # nº de documentos que intake recuperó del expediente del caso (RAG). Con documentos
        # sembrados debe ser > 0: si es 0, el turno corrió a ciegas (regresión de recuperación).
        "documents_retrieved": int(md.get("retrieved", 0) or 0),
        "draft_preview": draft[:_DRAFT_PREVIEW_CHARS],
        "reached_draft": score["reached_draft"],
    }


# ── correr una SUITE + reporte ────────────────────────────────────────────────
async def run_suite(tenant_id: str, cases: Optional[list[GoldenCase]] = None,
                    *, run_id: str) -> dict:
    """Corre una lista de casos (por defecto los canónicos sintéticos) y arma el reporte.
    Resuelve la política de datos reales UNA vez. `run_id` lo fija el llamador (con fecha)."""
    cases = cases if cases is not None else load_golden_cases()
    allow_real = (await read_eval_policy(tenant_id))["allow_real_data"]

    results: list[dict] = []
    for case in cases:
        try:
            results.append(await run_case(tenant_id, case, tenant_allow_real=allow_real))
        except EvalConsentError:
            raise  # el candado de consentimiento NO se traga: sube claro al llamador
        except Exception as exc:  # noqa: BLE001 — un caso que falla no tumba la suite
            logger.exception("run_suite: el caso %s falló", case.id)
            results.append({
                "case_id": case.id, "title": case.title, "error": str(exc),
                "score": score_turn("", "", {}), "reached_draft": False,
            })
    return build_report(run_id, results)


def build_report(run_id: str, case_results: list[dict]) -> dict:
    """Arma el reporte de una corrida a partir de los resultados por caso. Puro."""
    n = len(case_results)
    reached = sum(1 for c in case_results if c.get("reached_draft"))
    clean = sum(1 for c in case_results if (c.get("score") or {}).get("ok"))
    total_unsup = sum(int((c.get("score") or {}).get("citas_sin_respaldo", 0) or 0)
                      for c in case_results)
    errored = sum(1 for c in case_results if c.get("error"))
    return {
        "run_id": run_id,
        "cases": case_results,
        "summary": {
            "n_casos": n,
            "n_llegaron_a_borrador": reached,
            "n_sin_problemas": clean,
            "n_con_error": errored,
            "total_citas_sin_respaldo": total_unsup,
        },
    }


# ── persistencia (JSONL bajo mia-data — corridas SINTÉTICAS, sin RLS necesaria) ─
def _eval_dir(base_dir: Optional[str] = None) -> Path:
    base = Path(base_dir) if base_dir else Path(config.MIA_HOME) / "eval-runs"
    return base


def persist_report(report: dict, *, base_dir: Optional[str] = None) -> Path:
    """Escribe la corrida en `mia-data/eval-runs/{run_id}/` (cases.jsonl + summary.json).
    Datos SINTÉTICOS (no de cliente) → JSONL en disco basta, sin tabla RLS. Devuelve el dir."""
    import json

    run_dir = _eval_dir(base_dir) / report["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "cases.jsonl").open("w", encoding="utf-8") as f:
        for c in report.get("cases", []):
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    (run_dir / "summary.json").write_text(
        json.dumps({"run_id": report["run_id"], "summary": report.get("summary", {})},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return run_dir
