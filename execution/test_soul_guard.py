"""
Mia · test_soul_guard.py — gate de la identidad: ningún agente la escribe solo.

Prueba el freno completo sobre el SOUL.md (capa 1 del prompt, inyectada entera y con
autoridad de sistema en todos los turnos):
  · Dreams NO escribe el SOUL: propone.
  · Al aprobar la propuesta se aplica Y queda versión con autor y motivo.
  · Al rechazarla no cambia nada.
  · El tope RECHAZA (no trunca) y avisa en llano.
  · La instrucción directa del abogado no pasa por el HITL.
  · Aislamiento entre despachos.
  · Idempotencia de la migración 038.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
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

import init_dream_prescriptions  # noqa: E402
import init_dreams  # noqa: E402
import init_feedback  # noqa: E402
import init_playbooks  # noqa: E402
import init_soul_versions  # noqa: E402
import init_turn_usage  # noqa: E402
from mia import config  # noqa: E402
from mia.agent import llm  # noqa: E402
from mia.db import pool  # noqa: E402
from mia.memory import soul_manager as sm  # noqa: E402
from mia.memory.dreams import Dreams  # noqa: E402
from mia.memory.gepa import GEPALoop  # noqa: E402
from mia.memory.trace_capture import TraceCapture  # noqa: E402
from mia.memory.wiki_manager import WikiManager  # noqa: E402

PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"),
    port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"),
    user="postgres",
    password=os.getenv("PG_PASSWORD", ""),
)

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def fake_llm(messages, *, task=None, **kwargs):
    content = messages[-1]["content"]
    if "JSON array" in content:
        out = '["Concepto Soul"]'
    elif "Devuelve JSON" in content:
        out = json.dumps({"title": "P", "applies_when": "Cuando.", "content": "Pasos."})
    else:
        out = ("## Definicion (segun la practica de este despacho)\nT.\n\n"
               "## Patrones identificados\n- P.\n\n"
               "## Casos que lo soportan (referencias anonimas)\n- a.\n\n"
               "## Conexiones con otros conceptos\n- c.\n\n"
               "## Lo que NO funciona (aprendido de rechazos)\n- Pendiente.\n")
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=out))])


def make_tenant(name: str = "Soul Test") -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id", (name,)).fetchone()[0])


def cleanup(tenant_id: str) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id=%s::uuid", (tenant_id,))


def append_trace(tc: TraceCapture, tenant_id: str, **fields) -> None:
    rec = {
        "tenant_id": tenant_id,
        "matter_id": fields.pop("matter_id", "matter-soul"),
        "timestamp": fields.pop("timestamp", datetime.now(timezone.utc).isoformat()),
        "input": fields.pop("input", "consulta recurrente"),
        "output": fields.pop("output", "respuesta"),
        "model": "test", "tokens": 1, "latency_ms": 1,
        **fields,
    }
    path = tc._path_for(tenant_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def proposals(tenant_id: str, ptype: str = "soul_rule", status: str = "pending") -> list[tuple]:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(
            "SELECT id::text, suggested_content, rationale, signal_count FROM feedback_proposals "
            "WHERE tenant_id=%s::uuid AND proposal_type=%s AND status=%s ORDER BY created_at",
            (tenant_id, ptype, status)).fetchall()


def versions(tenant_id: str) -> list[tuple]:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(
            "SELECT content, changed_by, reason FROM soul_versions "
            "WHERE tenant_id=%s::uuid ORDER BY created_at, id", (tenant_id,)).fetchall()


def rls_forced(table: str) -> bool:
    with psycopg.connect(autocommit=True, **PG) as c:
        row = c.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=%s",
            (table,)).fetchone()
    return bool(row and row[0] and row[1])


def seed_soul(tenant_id: str, text: str) -> Path:
    p = sm.soul_path(tenant_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


BASE_SOUL = "# SOUL.md — Soul Test\n## identity\n- name: Soul Test\n"


async def run_checks() -> None:
    original_llm = llm.call_llm
    original_home = config.MIA_HOME
    llm.call_llm = fake_llm
    tenant = make_tenant()
    other = make_tenant("Soul Otro")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            config.MIA_HOME = Path(tmp)
            tc = TraceCapture(Path(tmp) / "traces")

            # ── 1 · Dreams NO escribe el SOUL: propone ────────────────────────
            print("\n== 1 · Dreams propone, no escribe ==")
            src = (ROOT / "backend" / "mia" / "memory" / "dreams.py").read_text(encoding="utf-8")
            # El nombre aparece en el comentario que explica POR QUÉ se quitó; lo que no
            # puede existir es la FUNCIÓN (el escritor automático sin freno).
            check("Dreams ya no define el escritor automático (_append_soul_rule)",
                  "def _append_soul_rule" not in src)
            check("Dreams no conoce la ruta del archivo de identidad (no puede escribirlo)",
                  "soul_path" not in src)

            seed_soul(tenant, BASE_SOUL)
            for i in range(3):
                append_trace(tc, tenant, matter_id=f"edited-{i}", hitl_outcome="edited",
                             input="misma correccion de estilo",
                             draft_original="texto original", draft_final="texto final")
            dreams = Dreams(trace_capture=tc,
                            wiki_manager=WikiManager(home=tmp, trace_capture=tc),
                            gepa=GEPALoop(trace_capture=tc))
            result = await dreams.run(tenant)

            soul_after = sm.read_soul(tenant)
            check("Tras Dreams el SOUL sigue INTACTO (nadie lo escribió)",
                  soul_after == BASE_SOUL)
            pend = proposals(tenant)
            check("Dreams dejó la preferencia como PROPUESTA pendiente", len(pend) == 1)
            check("Dreams reporta la regla como propuesta, no aplicada",
                  len(result["nudges"]) == 1)
            check("La propuesta trae el conteo real de la señal (3 correcciones)",
                  bool(pend) and pend[0][3] == 3)
            reason = pend[0][2] if pend else ""
            check("El porqué está en llano y avisa que solo se guarda si aprueba",
                  "Corregiste 3 borradores" in reason and "si lo apruebas" in reason)
            check("El porqué no tiene jerga técnica",
                  not any(w in reason.lower() for w in
                          ("soul", "hitl", "tenant", "prompt", "token", "trace")))

            # Segunda corrida: no se acosa al abogado con la misma sugerencia.
            await dreams.run(tenant)
            check("Dreams no duplica la propuesta pendiente en la corrida siguiente",
                  len(proposals(tenant)) == 1)

            # ── 2 · Aprobar aplica y versiona ─────────────────────────────────
            print("\n== 2 · Aprobar aplica + versiona ==")
            rule = pend[0][1]
            res = await sm.apply_soul_rule_proposal(tenant, rule)
            check("Aprobada, la regla SÍ se escribe en el SOUL",
                  res["applied"] and rule in sm.read_soul(tenant))
            check("La regla aterriza en su sección propia, sin reescribir la identidad",
                  sm.LEARNED_SECTION in sm.read_soul(tenant)
                  and sm.read_soul(tenant).startswith(BASE_SOUL.rstrip()))
            v = versions(tenant)
            check("Queda UNA versión con el estado ANTERIOR completo",
                  len(v) == 1 and v[0][0] == BASE_SOUL)
            check("La versión registra el autor ('mia': el texto lo originó Mia)",
                  v[0][1] == "mia")
            check("La versión registra el motivo en llano",
                  "aprobó" in v[0][2] and "token" not in v[0][2].lower())
            hist = await sm.soul_versions(tenant)
            check("El historial es consultable bajo RLS", len(hist) == 1
                  and hist[0]["changed_by"] == "mia" and hist[0]["created_at"] is not None)

            # Idempotencia: aplicar la misma regla dos veces no duplica ni versiona de más.
            res2 = await sm.apply_soul_rule_proposal(tenant, rule)
            check("Aplicar la misma regla dos veces no duplica ni versiona de más",
                  not res2["applied"] and len(versions(tenant)) == 1)

            # ── 3 · Rechazar no cambia nada ───────────────────────────────────
            print("\n== 3 · Rechazar no cambia nada ==")
            t3 = make_tenant("Soul Rechazo")
            try:
                seed_soul(t3, BASE_SOUL)
                pid = await sm.propose_soul_rule(t3, "Regla que será rechazada.",
                                                 reason="Motivo en llano.")
                antes = sm.read_soul(t3)
                with psycopg.connect(autocommit=True, **PG) as c:   # lo que hace /ignore
                    c.execute("UPDATE feedback_proposals SET status='rejected', "
                              "reviewed_at=now() WHERE id=%s::uuid", (pid,))
                check("Rechazada: el SOUL no cambió", sm.read_soul(t3) == antes)
                check("Rechazada: no quedó ninguna versión", versions(t3) == [])
                check("Rechazada: no queda pendiente", proposals(t3) == [])
            finally:
                cleanup(t3)

            # ── 4 · Tope: RECHAZA, no trunca ──────────────────────────────────
            print("\n== 4 · El tope rechaza, no trunca ==")
            t4 = make_tenant("Soul Tope")
            try:
                gordo = "# SOUL.md — Tope\n## identity\n" + ("- dato de identidad real\n" * 240)
                seed_soul(t4, gordo)
                antes = sm.read_soul(t4)
                err = None
                try:
                    await sm.apply_soul_rule(t4, "Una regla más que no cabe.",
                                             changed_by="mia", reason="motivo")
                except sm.SoulTooLargeError as e:
                    err = e
                check("El cambio que no cabe se RECHAZA", err is not None)
                check("Rechazado por tope: el SOUL NO se truncó ni cambió",
                      sm.read_soul(t4) == antes)
                check("Rechazado por tope: no queda versión fantasma", versions(t4) == [])
                msg = str(err or "")
                check("El aviso está en llano (palabras, no tokens)",
                      "palabras" in msg and "token" not in msg.lower())
                check("El aviso pide recortar y dice que no se recortó solo",
                      "«Mi despacho»" in msg and "prefiero que decidas tú" in msg)
                check("El aviso no tiene jerga técnica",
                      not any(w in msg.lower() for w in
                              ("soul", "prompt", "hitl", "tenant", "truncar", "presupuesto")))
                # Un SOUL que YA excede el tope se sigue leyendo: el tope frena la
                # ESCRITURA, nunca rompe el turno del abogado ni su identidad actual.
                check("Un SOUL ya excedido se sigue leyendo (el tope no rompe turnos)",
                      sm.read_soul(t4) == gordo)
                # Y el que sí cabe pasa.
                seed_soul(t4, BASE_SOUL)
                ok4 = await sm.apply_soul_rule(t4, "Regla que sí cabe.",
                                               changed_by="mia", reason="cabe")
                check("Lo que sí cabe se aplica normalmente", ok4["applied"])
            finally:
                cleanup(t4)

            # ── 5 · La instrucción directa del abogado NO pasa por HITL ───────
            print("\n== 5 · Lo que el abogado manda es fidedigno ==")
            t5 = make_tenant("Soul Abogado")
            try:
                seed_soul(t5, BASE_SOUL)
                regla = "Nunca cites jurisprudencia sin verificar la fuente."
                r5 = await sm.apply_soul_rule(
                    t5, regla, changed_by="abogado",
                    reason="Lo pediste tú directamente desde «Mi despacho».")
                check("La orden del abogado se aplica de inmediato",
                      r5["applied"] and regla in sm.read_soul(t5))
                check("La orden del abogado NO crea propuesta que aprobar",
                      proposals(t5) == [])
                v5 = versions(t5)
                check("La orden del abogado queda versionada como 'abogado'",
                      len(v5) == 1 and v5[0][1] == "abogado")
                check("El motivo de la orden del abogado queda en llano",
                      "Lo pediste tú" in v5[0][2])
                # El autor es obligatorio y acotado: nadie escribe anónimo.
                bad = None
                try:
                    await sm.apply_soul_rule(t5, "x", changed_by="cron", reason="r")
                except ValueError as e:
                    bad = e
                check("No se puede escribir la identidad sin autor válido", bad is not None)
            finally:
                cleanup(t5)

            # ── 6 · Reglas que Dreams YA escribió antes de este cambio ────────
            print("\n== 6 · Las reglas ya escritas se respetan ==")
            t6 = make_tenant("Soul Fundador")
            try:
                vieja = ("El abogado ha corregido repetidamente respuestas de este contexto; "
                         "prioriza la forma final aprobada en asuntos similares.")
                legado = BASE_SOUL + f"\n{sm.LEARNED_SECTION}\n- {vieja}\n"
                seed_soul(t6, legado)
                check("Una regla ya escrita NO se borra ni se toca",
                      sm.rule_already_present(t6, vieja) and sm.read_soul(t6) == legado)
                check("Una regla ya escrita no se vuelve a proponer",
                      await sm.propose_soul_rule(t6, vieja, reason="r") is None
                      and proposals(t6) == [])
                for i in range(3):
                    append_trace(tc, t6, matter_id=f"e6-{i}", hitl_outcome="edited",
                                 input="misma correccion de estilo",
                                 draft_original="o", draft_final="f")
                r6 = await Dreams(trace_capture=tc,
                                  wiki_manager=WikiManager(home=tmp, trace_capture=tc),
                                  gepa=GEPALoop(trace_capture=tc)).run(t6)
                check("Dreams sobre un SOUL con reglas viejas no propone ni escribe nada",
                      r6["nudges"] == [] and sm.read_soul(t6) == legado
                      and proposals(t6) == [])
            finally:
                cleanup(t6)

            # ── 7 · Degradación limpia ────────────────────────────────────────
            print("\n== 7 · Degrada limpio ==")
            t7 = make_tenant("Soul Degrada")
            try:
                seed_soul(t7, BASE_SOUL)
                for i in range(3):
                    append_trace(tc, t7, matter_id=f"e7-{i}", hitl_outcome="edited",
                                 input="misma correccion de estilo",
                                 draft_original="o", draft_final="f")

                class SoulCaido:
                    """El canal de propuestas caído (DB, migración ausente…)."""
                    async def propose_soul_rule(self, *a, **k):
                        raise RuntimeError("propuestas no disponibles")

                d7 = Dreams(trace_capture=tc,
                            wiki_manager=WikiManager(home=tmp, trace_capture=tc),
                            gepa=GEPALoop(trace_capture=tc), soul=SoulCaido())
                r7 = await d7.run(t7)
                check("Si la propuesta falla, Dreams NO se cae",
                      isinstance(r7.get("report"), str) and r7["nudges"] == [])
                check("Si la propuesta falla, el SOUL sigue intacto",
                      sm.read_soul(t7) == BASE_SOUL)
            finally:
                cleanup(t7)

            # ── 8 · Aislamiento entre despachos ───────────────────────────────
            print("\n== 8 · Aislamiento entre despachos ==")
            seed_soul(other, "# SOUL.md — Otro\n## identity\n- name: Otro\n")
            otro_antes = sm.read_soul(other)
            await sm.apply_soul_rule(tenant, "Regla solo del primer despacho.",
                                     changed_by="abogado", reason="motivo")
            check("Escribir la identidad de un despacho no toca la del otro (fichero)",
                  sm.read_soul(other) == otro_antes
                  and "Regla solo del primer despacho." not in sm.read_soul(other))
            check("Cada despacho tiene su propio archivo de identidad",
                  sm.soul_path(tenant) != sm.soul_path(other))
            check("El historial de un despacho no ve el del otro (RLS)",
                  await sm.soul_versions(other) == [])
            check("soul_versions tiene RLS forzado", rls_forced("soul_versions"))
            # Fail-closed sin el GUC de tenant: una conexión sin contexto no ve historial.
            async with pool.connection() as conn:
                rows = await (await conn.execute(
                    "SELECT count(*) FROM soul_versions")).fetchone()
            check("Sin contexto de despacho, el historial es invisible (fail-closed)",
                  rows[0] == 0)

            # ── 9 · El módulo respeta las reglas del proyecto ─────────────────
            print("\n== 9 · Reglas del proyecto ==")
            src_sm = (ROOT / "backend" / "mia" / "memory"
                      / "soul_manager.py").read_text(encoding="utf-8")
            check("El SOUL no se rediseña: cero LLM en el escritor de identidad",
                  "call_llm" not in src_sm and "from ..agent import llm" not in src_sm)
            check("soul_manager no hardcodea jurisdicciones ni áreas",
                  not any(w in src_sm for w in
                          ("Colombia", "España", "México", "Argentina", "Perú", "Chile")))
    finally:
        llm.call_llm = original_llm
        config.MIA_HOME = original_home
        cleanup(tenant)
        cleanup(other)


def check_migration_idempotent() -> None:
    print("\n== 10 · Migración 038 idempotente y aditiva ==")
    before = None
    with psycopg.connect(autocommit=True, **PG) as c:
        before = c.execute("SELECT count(*) FROM soul_versions").fetchone()[0]
    init_soul_versions.apply()
    init_soul_versions.apply()   # dos veces seguidas: no debe romper ni perder datos
    with psycopg.connect(autocommit=True, **PG) as c:
        after = c.execute("SELECT count(*) FROM soul_versions").fetchone()[0]
        chk = c.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname='feedback_proposals_proposal_type_check'").fetchone()[0]
    check("Aplicar la migración dos veces no falla ni borra datos", after == before)
    check("La migración es aditiva: conserva los tipos previos y suma 'soul_rule'",
          all(t in chk for t in ("improve_playbook", "new_playbook", "flag_gap",
                                 "wiki_correction", "weekly_report", "soul_rule")))
    check("soul_versions tiene el CHECK de autor (abogado|mia)", True if _author_check() else False)


def _author_check() -> bool:
    with psycopg.connect(autocommit=True, **PG) as c:
        rows = c.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid='soul_versions'::regclass AND contype='c'").fetchall()
    return any("abogado" in r[0] and "mia" in r[0] for r in rows)


async def async_main() -> int:
    print("== Guardián de la identidad (SOUL) ==")
    if not os.getenv("PG_PASSWORD"):
        print("  [FAIL] PG_PASSWORD vacío en .env")
        return 1
    init_playbooks.apply()
    init_feedback.apply()
    init_dreams.apply()
    init_turn_usage.apply()
    init_dream_prescriptions.apply()
    init_soul_versions.apply()
    await pool.open_pool()
    try:
        await run_checks()
    finally:
        await pool.close_pool()
    check_migration_idempotent()
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("SOUL OK — la identidad no se escribe sola.")
        return 0
    print("SOUL FAIL — no avanzar con la siguiente tarea.")
    return 1


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
