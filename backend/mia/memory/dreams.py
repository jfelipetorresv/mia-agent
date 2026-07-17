"""Dreams: consolidación semanal profunda del second brain por tenant."""
from __future__ import annotations

import asyncio
import logging
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg.types.json import Json

from .. import config
from ..agent import llm
from ..db import pool
from . import soul_manager
from .gepa import GEPALoop
from .prescriptions import PrescriptionEngine
from .trace_capture import TraceCapture
from .wiki_manager import WIKI_SCHEMA_VERSION, WikiManager, confidence_score

logger = logging.getLogger("mia.memory.dreams")


def _parse_ts(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def _outcome(trace: dict) -> str:
    return str(trace.get("hitl_outcome") or trace.get("outcome") or "")


def _playbook_ids(trace: dict) -> list[str]:
    ids: list[str] = []
    for key in ("playbook_id", "skill_id"):
        if trace.get(key):
            ids.append(str(trace[key]))
    for key in ("playbook_ids", "skill_ids", "activated_playbooks"):
        value = trace.get(key)
        if isinstance(value, list):
            ids.extend(str(v) for v in value)
    return list(dict.fromkeys(ids))


class Dreams:
    """Une replay, wiki, GEPA, lint, nudges y reporte semanal."""

    def __init__(
        self,
        *,
        trace_capture: TraceCapture | None = None,
        wiki_manager: WikiManager | None = None,
        gepa: GEPALoop | None = None,
        prescriptions: PrescriptionEngine | None = None,
        soul: object | None = None,
    ) -> None:
        self.trace_capture = trace_capture or TraceCapture()
        self.wiki_manager = wiki_manager or WikiManager(trace_capture=self.trace_capture)
        self.gepa = gepa or GEPALoop(trace_capture=self.trace_capture)
        self.prescriptions = prescriptions or PrescriptionEngine(trace_capture=self.trace_capture)
        # Dreams NO escribe el SOUL: solo puede PROPONER a través de este módulo (el único
        # escritor de la identidad). Inyectable para los gates.
        self.soul = soul or soul_manager

    def _week_traces(self, tenant_id: str) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        return [t for t in self.trace_capture.read(tenant_id) if _parse_ts(t.get("timestamp")) >= cutoff]

    async def _firm_name(self, tenant_id: str) -> str:
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute("SELECT name FROM tenants WHERE id=%s::uuid", (tenant_id,))).fetchone()
        return row[0] if row else "El despacho"

    async def _save_metrics(self, tenant_id: str, metrics: dict) -> None:
        async with pool.tenant_connection(tenant_id) as conn:
            await conn.execute(
                "INSERT INTO tenant_settings (tenant_id, config) VALUES (%s::uuid, %s) "
                "ON CONFLICT (tenant_id) DO UPDATE SET "
                "config = jsonb_set(tenant_settings.config, '{dreams,last_metrics}', %s::jsonb, true), "
                "updated_at = now()",
                (tenant_id, Json({"dreams": {"last_metrics": metrics}}), Json(metrics)),
            )

    async def _replay(self, tenant_id: str, traces: list[dict]) -> dict:
        total = len(traces)
        outcomes = Counter(_outcome(t) for t in traces)
        skills = Counter(pid for t in traces for pid in _playbook_ids(t))
        gaps = [t.get("matter_id") for t in traces if t.get("retrieved_doc_ids") == []]
        hours = Counter(_parse_ts(t.get("timestamp")).hour for t in traces if t.get("timestamp"))
        metrics = {
            "matters_worked": len({str(t.get("matter_id")) for t in traces if t.get("matter_id")}),
            "approval_rate": outcomes.get("approved", 0) / total if total else 0.0,
            "edit_rate": outcomes.get("edited", 0) / total if total else 0.0,
            "rejection_rate": outcomes.get("rejected", 0) / total if total else 0.0,
            "skills": dict(skills),
            "gaps": [str(g) for g in gaps if g],
            "work_hours": dict(hours),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._save_metrics(tenant_id, metrics)
        return metrics

    async def _wiki_update(self, tenant_id: str, traces: list[dict]) -> dict:
        approved_matters = sorted({str(t.get("matter_id")) for t in traces if _outcome(t) == "approved" and t.get("matter_id")})
        rejected = [t for t in traces if _outcome(t) == "rejected"]
        updated: set[str] = set()
        for matter_id in approved_matters:
            updated.update(await self.wiki_manager.update_from_approved_matter(tenant_id, matter_id))
        for trace in rejected:
            await self._record_rejection(tenant_id, trace)
        return {"approved_matters": len(approved_matters), "concepts_updated": sorted(updated), "rejections": len(rejected)}

    # Presupuesto de la sección "Lo que NO funciona" (la única que el LECTOR del
    # wiki extrae de este archivo). El _card acota el TOTAL a WIKI_NOTE_MAX_CHARS
    # (1400) y rechaza —no trunca— si no cabe; mantenemos esta sección holgada bajo
    # ese tope para que el concepto siempre entre al turno.
    _REJECTION_ENTRY_MAX_CHARS = 200
    _REJECTION_SECTION_MAX_CHARS = 650

    @staticmethod
    def _entries_under(body: str, header: str) -> list[str]:
        """Líneas de viñeta (`- …`) bajo un encabezado `## …`, en orden."""
        lines = body.splitlines()
        out: list[str] = []
        capturing = False
        for line in lines:
            if line.startswith("## "):
                capturing = line[3:].strip().startswith(header)
                continue
            if capturing and line.strip().startswith("- "):
                out.append(line.strip()[2:].strip())
        return out

    async def _record_rejection(self, tenant_id: str, trace: dict) -> None:
        await self.wiki_manager.init_wiki(tenant_id)
        path = self.wiki_manager.concept_path(tenant_id, "Patrones rechazados")
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        count = existing.count("- matter:")
        total = count + 1

        # "Patrones rechazados" es evidencia negativa DURA: cada rechazo es un acto
        # deliberado del abogado que CONFIRMA el patrón (rechazar cuesta, aprobar es
        # el default del HITL). Por eso los rechazos son el `support` del concepto y
        # no hay evidencia en contra: la confianza sube con el volumen, sin hardcodear.
        # Con la fórmula del wiki, 3+ rechazos superan WIKI_MIN_CONFIDENCE (0.60) y el
        # concepto entra al prompt — cerrando el lazo que el 0.10 fijo dejaba abierto.
        confidence = confidence_score(total, 0.0)

        # Acumular los rechazos (no solo el último) para que el modelo vea el conjunto
        # de patrones a evitar, acotado al presupuesto de la ficha que lee el turno.
        prev_no_funciona = self._entries_under(existing, "Lo que NO funciona")
        nuevo = str(trace.get("draft_final") or trace.get("output") or "").strip()
        nuevo = " ".join(nuevo.split())[: self._REJECTION_ENTRY_MAX_CHARS]
        if nuevo:
            prev_no_funciona.append(nuevo)
        # Conservar los más recientes que quepan en el presupuesto de la sección.
        seleccion: list[str] = []
        usado = 0
        for entry in reversed(prev_no_funciona):
            costo = len(entry) + 3  # "- " + salto de línea
            if usado + costo > self._REJECTION_SECTION_MAX_CHARS and seleccion:
                break
            seleccion.insert(0, entry)
            usado += costo
        no_funciona_block = "\n".join(f"- {e}" for e in seleccion) or "- (pendiente)"

        prev_patrones = self._entries_under(existing, "Patrones identificados")
        prev_patrones.append(
            f"matter:{trace.get('matter_id')} motivo:{str(trace.get('output', ''))[:240]}"
        )
        patrones_block = "\n".join(f"- {p}" for p in prev_patrones[-20:])

        content = (
            "---\n"
            "concept: Patrones rechazados\n"
            f"wiki_schema: {WIKI_SCHEMA_VERSION}\n"
            f"confidence: {confidence}\n"
            f"support_count: {total}\n"
            "contra_count: 0\n"
            f"last_updated: {datetime.now(timezone.utc).date().isoformat()}\n"
            f"case_count: {total}\n"
            "---\n"
            "# Patrones rechazados\n"
            "## Definicion (segun la practica de este despacho)\n"
            "Registro de salidas que no funcionaron para este despacho.\n\n"
            "## Patrones identificados\n"
            f"{patrones_block}\n\n"
            "## Casos que lo soportan (referencias anonimas)\n"
            "- Ver sources.md.\n\n"
            "## Conexiones con otros conceptos\n"
            "- Pendiente.\n\n"
            "## Lo que NO funciona (aprendido de rechazos)\n"
            f"{no_funciona_block}\n"
        )
        path.write_text(content, encoding="utf-8")
        index = self.wiki_manager.wiki_dir(tenant_id) / "index.md"
        current = index.read_text(encoding="utf-8") if index.exists() else "# Indice de conceptos\n"
        if "[[Patrones rechazados]] -- [[Patrones rechazados]]" not in current:
            index.write_text(current.rstrip() + "\n- [[Patrones rechazados]] -- [[Patrones rechazados]]\n", encoding="utf-8")

    async def _lint_and_archive(self, tenant_id: str) -> dict:
        lint = await self.wiki_manager.lint_wiki(tenant_id)
        archived_concepts: list[str] = []
        for name in sorted(set(lint["stale"]) | set(lint["orphan"])):
            await self.wiki_manager.archive_concept(tenant_id, name)
            archived_concepts.append(name)
        pruned_skills = await self.gepa.prune_unused_skills(tenant_id)
        return {"lint": lint, "archived_concepts": archived_concepts, "pruned_skills": pruned_skills}

    async def _nudges(self, tenant_id: str, traces: list[dict]) -> list[str]:
        """Detecta preferencias repetidas y las PROPONE. Ya NO escribe el SOUL.

        Antes, `_append_soul_rule` añadía la regla directo al SOUL.md: sin aprobación del
        abogado, sin tope de tamaño y sin historial — el único escritor automático sin
        freno sobre la capa 1 del prompt (la que se inyecta entera, con autoridad de
        sistema, en todos los turnos). Hoy Dreams PROPONE y el abogado decide
        (`memory/soul_manager.py`): la capa de máxima autoridad es la de menor autonomía.

        Degrada limpio: si la propuesta no se puede crear (DB caída, tipo no migrado…),
        se registra y Dreams sigue. Un nudge no puede tumbar el cron ni el turno del
        abogado. Devuelve las reglas PROPUESTAS (no aplicadas)."""
        edited = [t for t in traces if _outcome(t) == "edited" and (t.get("draft_original") or t.get("draft_final"))]
        if len(edited) < 3:
            return []
        contexts = defaultdict(list)
        for trace in edited:
            key = str(trace.get("input") or "")[:80].lower()
            contexts[key].append(trace)
        rules: list[str] = []
        for key, items in contexts.items():
            if len(items) < 3:
                continue
            rule = (
                "El abogado ha corregido repetidamente respuestas de este contexto; "
                "prioriza la forma final aprobada en asuntos similares."
            )
            # El porqué que leerá el abogado, en llano (§G): qué vio Mia y qué propone.
            reason = (
                f"Corregiste {len(items)} borradores parecidos esta semana. Mia propone "
                "recordar tu forma final para no repetirte la corrección. Es un cambio a "
                "la descripción de tu despacho: solo se guarda si lo apruebas."
            )
            try:
                created = await self.soul.propose_soul_rule(
                    tenant_id, rule, reason=reason, signal_count=len(items),
                    trace_ids=[f"{tenant_id}:{t.get('matter_id')}:{t.get('timestamp')}"
                               for t in items],
                )
            except Exception:  # noqa: BLE001 — un nudge nunca tumba la consolidación
                logger.warning(
                    "no se pudo dejar la preferencia aprendida como propuesta; "
                    "Dreams continúa (el SOUL no se toca sin aprobación).",
                    exc_info=True)
                continue
            if created:
                rules.append(rule)
        return rules

    async def _weekly_report(self, tenant_id: str, firm_name: str, metrics: dict, wiki: dict,
                             gepa: dict, diagnostics: dict | None = None) -> str:
        concepts = len(wiki.get("concepts_updated") or [])
        report = (
            f"Esta semana {firm_name} trabajó {metrics['matters_worked']} asuntos.\n"
            f"Tasa de aprobación: {metrics['approval_rate']:.0%}.\n"
            f"Mia aprendió sobre {concepts} conceptos nuevos o actualizados.\n"
            f"{gepa.get('skills_evolved', 0)} procedimientos quedaron con mejoras listas para revisión.\n"
            f"{gepa.get('new_skills_proposed', 0)} procedimientos nuevos quedaron sugeridos en el panel de conocimiento."
        )
        # CP-V2: el diagnóstico prescriptivo entra al reporte solo si encontró algo
        # (con pocos datos los buckets se saltan y no se inventa nada).
        top = (diagnostics or {}).get("prescriptions") or []
        if top:
            report += (
                f"\nMia dejó {len(top)} recomendaciones de mejora en el panel. "
                f"La principal: {top[0]['headline']}."
            )
        async with pool.tenant_connection(tenant_id) as conn:
            await conn.execute(
                "INSERT INTO feedback_proposals "
                "  (tenant_id, proposal_type, suggested_content, rationale, signal_count) "
                "VALUES (%s::uuid, 'weekly_report', %s, %s, %s)",
                (tenant_id, report, "Resumen semanal generado por Dreams.", max(1, metrics["matters_worked"])),
            )
        # CP-C2 (decisión #32): espejo del reporte en el vault de Obsidian del despacho.
        await self._mirror_report_to_vault(tenant_id, report)
        return report

    async def _mirror_report_to_vault(self, tenant_id: str, report: str) -> None:
        """Copia el reporte semanal al vault de Obsidian del despacho (Mia/reportes/,
        CP-C2 · decisión #32). El reporte interno ya quedó guardado: si el vault falla,
        solo se registra en el log y el flujo continúa."""
        try:
            from ..connectors import vault_writer as vw

            writer = await vw.tenant_vault_writer(tenant_id)
            if writer is None:
                return
            # Revisión CP-C2: la escritura al vault es E/S síncrona de disco (y puede
            # ser LENTA con vaults en OneDrive) → a un hilo, sin congelar el event loop.
            await asyncio.to_thread(
                writer.export_report, tenant_id, "Resumen semanal de Mia", report)
        except Exception:  # noqa: BLE001 — el espejo nunca tumba el reporte interno
            logger.warning(
                "No se pudo copiar el reporte semanal al vault de Obsidian; "
                "el reporte interno sí quedó guardado.",
                exc_info=True,
            )

    async def run(self, tenant_id: str) -> dict:
        traces = self._week_traces(tenant_id)
        firm_name = await self._firm_name(tenant_id)
        metrics = await self._replay(tenant_id, traces)
        wiki = await self._wiki_update(tenant_id, traces)
        gepa_result = await self.gepa.run_evolution_cycle(tenant_id)
        cleanup = await self._lint_and_archive(tenant_id)
        nudges = await self._nudges(tenant_id, traces)
        # CP-V2: auto-diagnóstico prescriptivo. Si falla, Dreams sigue — el
        # diagnóstico es una mejora del reporte, no un requisito de la consolidación.
        try:
            diagnostics = await self.prescriptions.run(tenant_id)
        except Exception:  # noqa: BLE001
            logger.warning("el diagnóstico prescriptivo falló; Dreams continúa sin él",
                           exc_info=True)
            diagnostics = {"prescriptions": [], "candidates_total": 0, "suppressed": []}
        report = await self._weekly_report(tenant_id, firm_name, metrics, wiki, gepa_result,
                                           diagnostics)
        return {
            "metrics": metrics,
            "wiki": wiki,
            "gepa": gepa_result,
            "cleanup": cleanup,
            "nudges": nudges,
            "diagnostics": diagnostics,
            "report": report,
        }

    async def run_all_tenants(self) -> dict:
        out: dict[str, Any] = {}
        for tenant_id in self._list_tenant_ids():
            try:
                async with llm.tenant_model_policy(tenant_id):  # CP2: política por tenant
                    out[tenant_id] = await self.run(tenant_id)
            except Exception as e:
                out[tenant_id] = {"error": str(e)}
        return out

    def _list_tenant_ids(self) -> list[str]:
        import psycopg

        pw = os.getenv("PG_PASSWORD", "")
        if not pw:
            return []
        kw = dict(
            host=os.getenv("PG_HOST", "127.0.0.1"),
            port=os.getenv("PG_PORT", "5432"),
            dbname=os.getenv("PG_DB", "mia"),
            user="postgres",
            password=pw,
        )
        with psycopg.connect(autocommit=True, **kw) as c:
            rows = c.execute("SELECT id FROM tenants").fetchall()
        return [str(r[0]) for r in rows]
