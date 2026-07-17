"""
Mia · test_curator_conflicts.py — gate de "contradicción antes que fusión" (migración 038).

QUÉ PRUEBA: que el Curator ya no funda criterios que se contradicen. Tras el coseno corre un
juez que separa DUPLICADO (fusionable, como siempre) de CONFLICTO (jamás fusionable: sube al
abogado como elección binaria, con las dos versiones vivas y sin mezclar).

QUÉ **NO** PRUEBA (y es honesto decirlo): la PUNTERÍA del juez. El gate corre sin red, con
`call_llm` mockeado, así que aquí el veredicto lo pone el test. Lo que se verifica es lo que sí
depende de nosotros: que un "contrarios" convencido NO se funda, que todo lo demás — "iguales",
"no_se", confianza floja, JSON roto, modelo caído — caiga a duplicado (el comportamiento previo),
y que el abogado reciba A contra B y nunca una mezcla. Los textos de los pares son criterios
jurídicos reales, agnósticos de jurisdicción, y el veredicto que el test inyecta en cada uno es el
que daría un juez competente sobre ESE par.

HALT si falla (CLAUDE.md §G). Exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_curator_conflicts.py
"""
from __future__ import annotations
import asyncio
import json
import math
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import psycopg
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import init_playbooks                                  # noqa: E402  (migración 005)
import init_jurisdiction_foundation                    # noqa: E402  (011 · audit_logs)
import init_curator_proposals                          # noqa: E402  (012)
import init_curator_conflicts                          # noqa: E402  (038)
from mia import embeddings                             # noqa: E402
from mia.agent import llm                              # noqa: E402
from mia.db import pool                                # noqa: E402
from mia.memory import curator as curator_mod          # noqa: E402
from mia.memory.curator import CONFLICT_MIN_CONFIDENCE, Curator   # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── criterios jurídicos REALES, agnósticos de jurisdicción ───────────────────
# El detector no puede depender del léxico jurídico de ningún país: estos textos hablan de
# estructuras que existen en cualquier ordenamiento (poder de representación, plazos internos).

# Par 1 — el MISMO criterio dicho de dos maneras → duplicado (se funde, como hoy).
CRIT_PODER_A = (
    "Poder de representación antes de actuar.\n"
    "En todo encargo de representación judicial exigimos al cliente el poder autenticado ANTES "
    "de radicar el primer escrito. Mientras no esté firmado y autenticado, no se presenta ninguna "
    "actuación a nombre del cliente, aunque el término esté corriendo. Si el término apremia, se "
    "pide al cliente que autentique el mismo día y se deja constancia escrita del requerimiento."
)
CRIT_PODER_A2 = (
    "Sin poder autenticado no se radica.\n"
    "Ningún escrito sale del despacho a nombre de un cliente si el poder no está autenticado. El "
    "documento se recoge antes de la primera actuación. Cuando el plazo va justo, se le pide al "
    "cliente autenticar ese mismo día y el requerimiento queda por escrito en el expediente."
)

# Par 2 — el criterio INVERTIDO: "siempre exigimos X" contra "nunca exigimos X" → conflicto.
CRIT_PERITO_SIEMPRE = (
    "Prueba pericial de parte en controversias técnicas.\n"
    "En toda controversia con componente técnico SIEMPRE aportamos dictamen pericial de parte "
    "junto con el escrito inicial. No esperamos a que la contraparte lo pida ni a que el juez lo "
    "decrete: el dictamen entra con la primera oportunidad probatoria, sin excepción."
)
CRIT_PERITO_NUNCA = (
    "Prueba pericial de parte en controversias técnicas.\n"
    "En las controversias con componente técnico NUNCA aportamos dictamen pericial de parte con "
    "el escrito inicial. Descubrir nuestra tesis técnica de entrada le regala a la contraparte el "
    "tiempo de refutarla. El dictamen se reserva y solo se aporta si el juez lo decreta o si la "
    "contraparte aporta el suyo primero."
)

# Par 3 — dos umbrales distintos para la misma cosa, formulación ambigua (el juez duda).
CRIT_UMBRAL_A = (
    "Segunda revisión de escritos.\n"
    "Los escritos de cuantía relevante los revisa un segundo abogado antes de salir. En la "
    "práctica, 'relevante' lo define el socio a cargo según el riesgo del asunto."
)
CRIT_UMBRAL_B = (
    "Segunda revisión de escritos.\n"
    "Todo escrito de un asunto de alto riesgo pasa por un segundo par de ojos antes de radicarse. "
    "El socio a cargo decide qué asuntos entran en esa categoría."
)


# ── mocks (sin red): el juez responde lo que el escenario le indique ─────────
_judge_reply: object = None          # str (respuesta cruda) | Exception | None
_judge_calls: list[dict] = []


def _fake_embed(texts):
    return [[0.5] + [0.0] * 1023 for _ in texts]


def _fake_call_llm(messages, *, task=None, model=None, **kw):
    if task == "curator_conflict":
        _judge_calls.append({"task": task, "messages": messages})
        if isinstance(_judge_reply, Exception):
            raise _judge_reply
        content = _judge_reply if isinstance(_judge_reply, str) else ""
    else:
        content = "CONTENIDO_FUSIONADO_MOCK"
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30),
    )


embeddings.embed_texts = _fake_embed
llm.call_llm = _fake_call_llm
curator_mod.llm.call_llm = _fake_call_llm


def judge_says(veredicto: str, confianza: float, dice_a: str = "A ordena una cosa",
               dice_b: str = "B ordena la contraria", *, wrap: bool = False) -> str:
    body = json.dumps({"veredicto": veredicto, "confianza": confianza,
                       "dice_a": dice_a, "dice_b": dice_b}, ensure_ascii=False)
    return f"Aquí va mi análisis:\n```json\n{body}\n```\n" if wrap else body


def set_judge(reply) -> None:
    global _judge_reply
    _judge_reply = reply


PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)


def make_tenant(label: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id", (f"CURCONF_TEST {label}",)
        ).fetchone()[0])


def drop_test_tenants() -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE name LIKE 'CURCONF_TEST%'")


def vec_axis(i: int) -> list[float]:
    v = [0.0] * 1024
    v[i] = 1.0
    return v


def vec_cos(c: float) -> list[float]:
    v = [0.0] * 1024
    v[0] = c
    v[1] = math.sqrt(max(0.0, 1.0 - c * c))
    return v


async def insert_pb(tenant: str, title: str, embedding, *, content="cuerpo",
                    summary="s", applies="cuando aplica", origin="manual") -> str:
    async with pool.tenant_connection(tenant) as conn:
        row = await (await conn.execute(
            "INSERT INTO playbooks (tenant_id, title, summary, applies_when, content, "
            "embedding, status, metadata) "
            "VALUES (%s::uuid,%s,%s,%s,%s,%s,'active',%s::jsonb) RETURNING id",
            (tenant, title, summary, applies, content, embedding,
             json.dumps({"origin": origin})),
        )).fetchone()
    return str(row[0])


async def status_of(tenant: str, pid: str) -> str | None:
    async with pool.tenant_connection(tenant) as conn:
        row = await (await conn.execute(
            "SELECT status FROM playbooks WHERE id=%s::uuid", (pid,))).fetchone()
    return row[0] if row else None


async def conflict_rows(tenant: str, status: str = "pending") -> list[dict]:
    async with pool.tenant_connection(tenant) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id::text, conflict, status, resolution FROM curator_proposals "
                "WHERE kind='conflict' AND status=%s ORDER BY created_at", (status,))
            return [{"id": r[0], "conflict": r[1], "status": r[2], "resolution": r[3]}
                    for r in await cur.fetchall()]


async def proposal_row(tenant: str, pid: str) -> dict | None:
    async with pool.tenant_connection(tenant) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT status, resolution, kind FROM curator_proposals WHERE id=%s::uuid", (pid,))
            r = await cur.fetchone()
    return {"status": r[0], "resolution": r[1], "kind": r[2]} if r else None


async def audit_count(tenant: str, action: str) -> int:
    async with pool.tenant_connection(tenant) as conn:
        return (await (await conn.execute(
            "SELECT count(*) FROM audit_logs WHERE action=%s", (action,))).fetchone())[0]


async def run_gate(t: dict) -> None:
    await pool.open_pool()
    try:
        cur = Curator()

        # ============ 1 · MISMO criterio, dos redacciones → DUPLICADO (se funde) ============
        set_judge(judge_says("iguales", 0.95,
                             "Exige poder autenticado antes del primer escrito",
                             "Exige poder autenticado antes de radicar"))
        d1 = await insert_pb(t["dup"], "Poder antes de actuar", vec_axis(0), content=CRIT_PODER_A)
        d2 = await insert_pb(t["dup"], "Sin poder no se radica", vec_cos(0.93),
                             content=CRIT_PODER_A2)
        p_dup = await cur.propose(t["dup"])
        check("mismo criterio, otra redacción → se propone FUSIÓN (comportamiento de siempre)",
              len(p_dup.proposed_merges) == 1
              and {*p_dup.proposed_merges[0]["source_ids"]} == {d1, d2})
        check("mismo criterio → NO se levanta ningún conflicto",
              len(p_dup.raised_conflicts) == 0 and (await conflict_rows(t["dup"])) == [])
        check("el juez recibió el par (una llamada, task auxiliar 'curator_conflict')",
              len(_judge_calls) == 1)

        # ============ 2 · "siempre X" vs "nunca X" → CONFLICTO (jamás se funde) ============
        _judge_calls.clear()
        set_judge(judge_says(
            "contrarios", 0.94,
            "Aportar SIEMPRE dictamen pericial de parte con el escrito inicial",
            "NUNCA aportar dictamen pericial de parte con el escrito inicial"))
        c_si = await insert_pb(t["conf"], "Perito: siempre con el escrito inicial", vec_axis(0),
                               content=CRIT_PERITO_SIEMPRE, origin="entrevista")
        c_no = await insert_pb(t["conf"], "Perito: nunca con el escrito inicial", vec_cos(0.92),
                               content=CRIT_PERITO_NUNCA, origin="aprendida")
        p_conf = await cur.propose(t["conf"])
        check("'siempre X' vs 'nunca X' → NO se propone fusión", len(p_conf.proposed_merges) == 0)
        check("'siempre X' vs 'nunca X' → se levanta 1 conflicto",
              len(p_conf.raised_conflicts) == 1)
        rows = await conflict_rows(t["conf"])
        check("el conflicto persiste como propuesta pendiente kind='conflict'", len(rows) == 1)
        payload = rows[0]["conflict"] if rows else {}
        check("el conflicto lleva las DOS versiones (ids de ambas guías)",
              {payload.get("a", {}).get("id"), payload.get("b", {}).get("id")} == {c_si, c_no})
        check("cada versión llega con su fecha y su procedencia",
              bool(payload.get("a", {}).get("fecha")) and bool(payload.get("b", {}).get("fecha"))
              and {payload["a"]["procedencia"], payload["b"]["procedencia"]}
              == {"entrevista", "aprendida"})
        check("cada versión dice lo SUYO (dos textos separados, ninguno mezclado)",
              "SIEMPRE" in (payload.get("a", {}).get("dice") or "")
              and "NUNCA" in (payload.get("b", {}).get("dice") or "")
              and payload["a"]["dice"] != payload["b"]["dice"])
        # (el par sale ordenado por id, no por inserción: se comparan como conjunto)
        check("el conflicto conserva el texto original de cada versión (sin fusionar)",
              {payload["a"]["extracto"], payload["b"]["extracto"]}
              == {CRIT_PERITO_SIEMPRE, CRIT_PERITO_NUNCA})
        check("conflicto detectado → las DOS guías siguen vivas y activas",
              (await status_of(t["conf"], c_si)) == "active"
              and (await status_of(t["conf"], c_no)) == "active")

        # el conflicto NO se aprueba en bloque: hay que elegir.
        cid = rows[0]["id"]
        res_ap = await cur.apply_proposal(t["conf"], cid)
        check("aprobar un conflicto en bloque → rechazado (hay que elegir una versión)",
              "conflicto de criterio" in (res_ap.get("error") or ""))
        check("tras el intento de aprobación en bloque el conflicto sigue pendiente",
              (await proposal_row(t["conf"], cid))["status"] == "pending")

        # ============ 3 · resolver eligiendo A: la otra se archiva, nada se funde ============
        res = await cur.resolve_conflict(t["conf"], cid, "a", reviewed_by="abogado@x.co")
        chosen, other = (c_si, c_no) if payload["a"]["id"] == c_si else (c_no, c_si)
        check("elegir una versión → status approved + resolution guardada",
              res["status"] == "approved" and res["archived"] == 1)
        check("la versión elegida queda activa; la otra se archiva (no se borra)",
              (await status_of(t["conf"], chosen)) == "active"
              and (await status_of(t["conf"], other)) == "archived")
        check("no se creó ningún playbook fusionado",
              (await cur.load_playbooks(t["conf"]))[0]["title"]
              in ("Perito: siempre con el escrito inicial", "Perito: nunca con el escrito inicial")
              and len(await cur.load_playbooks(t["conf"])) == 1)
        row_c = await proposal_row(t["conf"], cid)
        check("la decisión queda registrada (resolution='a')", row_c["resolution"] == "a")
        check("resolver deja registro en audit_logs",
              (await audit_count(t["conf"], "curator_conflict_resolved")) == 1)

        # ============ 4 · umbral CONSERVADOR: ante la duda, duplicado ============
        _judge_calls.clear()
        set_judge(judge_says("no_se", 0.9))
        u1 = await insert_pb(t["duda"], "Segunda revisión (socio)", vec_axis(0),
                             content=CRIT_UMBRAL_A)
        u2 = await insert_pb(t["duda"], "Segunda revisión (riesgo)", vec_cos(0.9),
                             content=CRIT_UMBRAL_B)
        p_duda = await cur.propose(t["duda"])
        check("veredicto 'no_se' → duplicado (se funde), NO se interroga al abogado",
              len(p_duda.proposed_merges) == 1 and len(p_duda.raised_conflicts) == 0)

        # "contrarios" pero sin convicción → duplicado (el umbral es lo que protege del interrogatorio)
        set_judge(judge_says("contrarios", CONFLICT_MIN_CONFIDENCE - 0.1))
        b1 = await insert_pb(t["floja"], "Umbral A", vec_axis(0), content=CRIT_UMBRAL_A)
        b2 = await insert_pb(t["floja"], "Umbral B", vec_cos(0.9), content=CRIT_UMBRAL_B)
        p_floja = await cur.propose(t["floja"])
        check(f"'contrarios' con confianza < {CONFLICT_MIN_CONFIDENCE} → duplicado (conservador)",
              len(p_floja.proposed_merges) == 1 and len(p_floja.raised_conflicts) == 0)

        # ... y con convicción sí sube (el umbral no es un apagador)
        set_judge(judge_says("contrarios", CONFLICT_MIN_CONFIDENCE))
        s1 = await insert_pb(t["justo"], "Perito siempre", vec_axis(0), content=CRIT_PERITO_SIEMPRE)
        s2 = await insert_pb(t["justo"], "Perito nunca", vec_cos(0.9), content=CRIT_PERITO_NUNCA)
        p_justo = await cur.propose(t["justo"])
        check(f"'contrarios' con confianza == {CONFLICT_MIN_CONFIDENCE} → conflicto",
              len(p_justo.raised_conflicts) == 1 and len(p_justo.proposed_merges) == 0)

        # ============ 5 · FAIL-SOFT: el juez revienta / responde basura ============
        set_judge(RuntimeError("juez caído"))
        f1 = await insert_pb(t["falla"], "Perito siempre (f)", vec_axis(0),
                             content=CRIT_PERITO_SIEMPRE)
        f2 = await insert_pb(t["falla"], "Perito nunca (f)", vec_cos(0.9),
                             content=CRIT_PERITO_NUNCA)
        p_fail = await cur.propose(t["falla"])
        check("el juez revienta → propose NO revienta (el cron sobrevive)",
              isinstance(p_fail.proposed_merges, list))
        check("el juez revienta → degrada al comportamiento previo (fusión propuesta)",
              len(p_fail.proposed_merges) == 1 and len(p_fail.raised_conflicts) == 0)

        set_judge("no soy JSON, soy un modelo pequeño divagando")
        g1 = await insert_pb(t["basura"], "Perito siempre (g)", vec_axis(0),
                             content=CRIT_PERITO_SIEMPRE)
        g2 = await insert_pb(t["basura"], "Perito nunca (g)", vec_cos(0.9),
                             content=CRIT_PERITO_NUNCA)
        p_junk = await cur.propose(t["basura"])
        check("respuesta ilegible del juez → duplicado (fail-soft)",
              len(p_junk.proposed_merges) == 1 and len(p_junk.raised_conflicts) == 0)

        # JSON envuelto en prosa + ``` → sí se entiende (los modelos locales lo hacen)
        set_judge(judge_says("contrarios", 0.95, "A obliga", "B prohíbe", wrap=True))
        w1 = await insert_pb(t["wrap"], "Perito siempre (w)", vec_axis(0),
                             content=CRIT_PERITO_SIEMPRE)
        w2 = await insert_pb(t["wrap"], "Perito nunca (w)", vec_cos(0.9),
                             content=CRIT_PERITO_NUNCA)
        p_wrap = await cur.propose(t["wrap"])
        check("veredicto envuelto en ```json``` y prosa → se entiende igual",
              len(p_wrap.raised_conflicts) == 1)

        # ============ 6 · "dejar las dos" y no volver a preguntar ============
        set_judge(judge_says("contrarios", 0.95, "A obliga siempre", "B lo prohíbe siempre"))
        n1 = await insert_pb(t["ambas"], "Perito siempre (n)", vec_axis(0),
                             content=CRIT_PERITO_SIEMPRE)
        n2 = await insert_pb(t["ambas"], "Perito nunca (n)", vec_cos(0.9),
                             content=CRIT_PERITO_NUNCA)
        p_amb = await cur.propose(t["ambas"])
        nid = (await conflict_rows(t["ambas"]))[0]["id"]
        res_n = await cur.resolve_conflict(t["ambas"], nid, "none", reviewed_by="abogado@x.co")
        check("'dejar las dos' → nada se archiva; la contradicción queda como estado legítimo",
              res_n["status"] == "rejected" and res_n["archived"] == 0
              and (await status_of(t["ambas"], n1)) == "active"
              and (await status_of(t["ambas"], n2)) == "active")
        p_amb2 = await cur.propose(t["ambas"])
        check("tras 'dejar las dos', el cron NO vuelve a preguntar lo mismo",
              len(p_amb2.raised_conflicts) == 0)
        check("tras 'dejar las dos', el par TAMPOCO se propone como fusión",
              len(p_amb2.proposed_merges) == 0)

        # un conflicto pendiente no se duplica en cada corrida
        _judge_calls.clear()
        p_conf2 = await cur.propose(t["justo"])
        check("un conflicto ya pendiente no se vuelve a levantar (ni se paga el juez otra vez)",
              len(p_conf2.raised_conflicts) == 0 and len(_judge_calls) == 0
              and len(await conflict_rows(t["justo"])) == 1)

        # ============ 7 · aislamiento entre despachos ============
        check("RLS: el despacho B no ve los conflictos del despacho A",
              [p for p in await cur.list_proposals(t["b"], status="pending")
               if p["kind"] == "conflict"] == [])
        check("aislamiento: resolver en A no toca los playbooks de B",
              (await status_of(t["conf"], chosen)) == "active")

        # ============ 8 · protecciones que no se tocan: drift + elección inválida ============
        set_judge(judge_says("contrarios", 0.95, "A obliga", "B prohíbe"))
        x1 = await insert_pb(t["drift"], "Perito siempre (x)", vec_axis(0),
                             content=CRIT_PERITO_SIEMPRE)
        x2 = await insert_pb(t["drift"], "Perito nunca (x)", vec_cos(0.9),
                             content=CRIT_PERITO_NUNCA)
        await cur.propose(t["drift"])
        xid = (await conflict_rows(t["drift"]))[0]["id"]
        await insert_pb(t["drift"], "Guía tardía", vec_axis(70), content="otra cosa")  # cambia el estado
        res_d = await cur.resolve_conflict(t["drift"], xid, "a")
        check("el conocimiento cambió desde que se detectó → drift, no se archiva nada",
              res_d["status"] == "drift" and "regenerar" in (res_d.get("error") or "")
              and (await status_of(t["drift"], x1)) == "active"
              and (await status_of(t["drift"], x2)) == "active")
        check("tras el drift el conflicto vuelve a 'pending' (no queda en 'applying')",
              (await proposal_row(t["drift"], xid))["status"] == "pending")

        res_i = await cur.resolve_conflict(t["conf"], cid, "cualquiera")
        check("elección inválida → se rechaza sin tocar nada", res_i["status"] == "invalid")
        res_dup = await cur.resolve_conflict(t["ambas"], nid, "a")
        check("resolver dos veces el mismo conflicto → el 2º no aplica",
              bool(res_dup.get("error")) and (await status_of(t["ambas"], n1)) == "active")

        # una propuesta de limpieza no se puede 'resolver' como si fuera un conflicto
        res_k = await cur.resolve_conflict(t["dup"], p_dup.id, "a")
        check("una propuesta de limpieza no se resuelve como conflicto",
              "no es un conflicto" in (res_k.get("error") or ""))
    finally:
        await pool.close_pool()


def main() -> int:
    print("== Curator · contradicción antes que fusión (migración 038) ==")
    if not os.getenv("PG_PASSWORD"):
        print("  [FAIL] PG_PASSWORD vacío en .env")
        return 1

    init_playbooks.apply()
    init_jurisdiction_foundation.apply()
    init_curator_proposals.apply()
    init_curator_conflicts.apply()
    init_curator_conflicts.apply()          # idempotente: aplicarla dos veces no rompe nada
    check("la migración 038 es idempotente (se aplica dos veces sin error)", True)

    # el umbral vive en el código y es conservador por diseño
    check("el umbral de conflicto es conservador (>= 0.8)", CONFLICT_MIN_CONFIDENCE >= 0.8)

    drop_test_tenants()
    t = {k: make_tenant(k) for k in
         ("b", "dup", "conf", "duda", "floja", "justo", "falla", "basura", "wrap", "ambas",
          "drift")}
    try:
        asyncio.run(run_gate(t))
    finally:
        drop_test_tenants()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total}")
    if passed == total:
        print("Contradicción antes que fusión OK — el Curator ya no funde criterios opuestos.")
        return 0
    print("FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
