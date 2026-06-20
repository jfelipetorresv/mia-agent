"""Second brain por tenant: wiki compilado por Mia a partir del uso aprobado."""
from __future__ import annotations

import asyncio
import json
import re
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .. import config
from ..agent import llm
from .trace_capture import TraceCapture

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_name(value: str) -> str:
    name = _SAFE.sub("_", value.strip()).strip("_").lower()
    return name or "concepto"


def _today() -> str:
    return date.today().isoformat()


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    raw = text[4:end].strip()
    body = text[end + 4 :].lstrip()
    meta: dict[str, Any] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if key.strip() in {"confidence"}:
            try:
                meta[key.strip()] = float(value)
            except ValueError:
                meta[key.strip()] = 0.0
        elif key.strip() in {"case_count"}:
            try:
                meta[key.strip()] = int(value)
            except ValueError:
                meta[key.strip()] = 0
        else:
            meta[key.strip()] = value
    return meta, body


def _excerpt(text: str, query: str, limit: int = 240) -> str:
    lower = text.lower()
    pos = lower.find(query.lower())
    if pos < 0:
        pos = 0
    start = max(0, pos - 80)
    return text[start : start + limit].replace("\n", " ").strip()


class WikiManager:
    """Mantiene la capa agente del wiki por tenant.

    No contiene conocimiento juridico especifico: solo estructura y operaciones.
    Los conceptos son strings libres extraidos del trabajo aprobado del despacho.
    """

    def __init__(self, *, home: str | Path | None = None, trace_capture: TraceCapture | None = None) -> None:
        self.home = Path(home) if home else Path(config.MIA_HOME)
        self.trace_capture = trace_capture or TraceCapture()

    def wiki_dir(self, tenant_id: str) -> Path:
        return self.home / "wiki" / str(tenant_id)

    def concepts_dir(self, tenant_id: str) -> Path:
        return self.wiki_dir(tenant_id) / "concepts"

    def concept_path(self, tenant_id: str, concept_name: str) -> Path:
        return self.concepts_dir(tenant_id) / f"{_safe_name(concept_name)}.md"

    async def init_wiki(self, tenant_id: str) -> None:
        root = self.wiki_dir(tenant_id)
        concepts = root / "concepts"
        archived = concepts / "archived"
        archived.mkdir(parents=True, exist_ok=True)
        (root / "sources.md").touch(exist_ok=True)
        (root / "index.md").touch(exist_ok=True)
        schema = root / "schema.md"
        if not schema.exists():
            schema.write_text(
                "# Instrucciones del wiki\n\n"
                "Este wiki recoge patrones aprendidos del trabajo aprobado por el despacho.\n"
                "Cada concepto debe citar evidencia anonima, separar lo confirmado de lo incierto "
                "y registrar rechazos o correcciones cuando existan.\n"
                "No presupongas jurisdiccion, idioma, area, corte, norma ni tipo de proceso: "
                "todo detalle especifico debe venir de fuentes del despacho o de su uso aprobado.\n",
                encoding="utf-8",
            )

    async def _synthesize(self, concept_name: str, evidence: list[str], previous: str | None) -> str:
        prompt = (
            "Compila una nota de wiki para un despacho a partir de evidencia aprobada por humanos. "
            "No asumas jurisdiccion, area, norma, corte ni tipo de proceso. "
            "Usa solo lo que aparezca en la evidencia. Devuelve markdown con estas secciones exactas:\n"
            "## Definicion (segun la practica de este despacho)\n"
            "## Patrones identificados\n"
            "## Casos que lo soportan (referencias anonimas)\n"
            "## Conexiones con otros conceptos\n"
            "## Lo que NO funciona (aprendido de rechazos)\n\n"
            f"Concepto: {concept_name}\n\n"
            f"Version previa:\n{previous or '(sin version previa)'}\n\n"
            f"Evidencia:\n" + "\n\n---\n\n".join(evidence)
        )
        try:
            resp = await asyncio.to_thread(
                llm.call_llm,
                [{"role": "user", "content": prompt}],
                task="curator",
                temperature=0.1,
            )
            content = resp.choices[0].message.content or ""
            if "## Definicion" in content or "## Definición" in content:
                return content.strip()
        except Exception:
            pass
        joined = "\n\n".join(f"- Evidencia anonima: {e[:500]}" for e in evidence)
        return (
            f"# {concept_name}\n"
            "## Definicion (segun la practica de este despacho)\n"
            "Pendiente de consolidar con mas casos aprobados.\n\n"
            "## Patrones identificados\n"
            f"{joined or '- Sin evidencia suficiente.'}\n\n"
            "## Casos que lo soportan (referencias anonimas)\n"
            "- Referencias registradas en sources.md.\n\n"
            "## Conexiones con otros conceptos\n"
            "- Pendiente.\n\n"
            "## Lo que NO funciona (aprendido de rechazos)\n"
            "- Pendiente.\n"
        )

    async def compile_concept(self, tenant_id: str, concept_name: str, evidence: list[str]) -> str:
        await self.init_wiki(tenant_id)
        path = self.concept_path(tenant_id, concept_name)
        old_meta: dict[str, Any] = {}
        old_body: str | None = None
        if path.exists():
            old_meta, old_body = _parse_frontmatter(path.read_text(encoding="utf-8"))

        previous_cases = int(old_meta.get("case_count") or 0)
        case_count = previous_cases + max(1, len(evidence))
        previous_conf = float(old_meta.get("confidence") or 0.0)
        confidence = min(1.0, max(previous_conf, 0.15) + 0.1 * max(1, len(evidence)))
        body = await self._synthesize(concept_name, evidence, old_body)
        if not body.lstrip().startswith(f"# {concept_name}"):
            body = f"# {concept_name}\n{body}"

        content = (
            "---\n"
            f"concept: {concept_name}\n"
            f"confidence: {confidence:.2f}\n"
            f"last_updated: {_today()}\n"
            f"case_count: {case_count}\n"
            "---\n"
            f"{body.strip()}\n"
        )
        path.write_text(content, encoding="utf-8")
        return content

    async def extract_concepts(self, tenant_id: str, matter_text: str) -> list[str]:
        await self.init_wiki(tenant_id)
        prompt = (
            "Identifica conceptos presentes en este asunto aprobado. "
            "No asumas pais, jurisdiccion, area, corte, norma ni tipo de proceso. "
            "Devuelve solo un JSON array de strings libres, maximo 12.\n\n"
            f"Texto:\n{matter_text[:12000]}"
        )
        raw = ""
        try:
            resp = await asyncio.to_thread(
                llm.call_llm,
                [{"role": "user", "content": prompt}],
                task="curator",
                temperature=0,
            )
            raw = resp.choices[0].message.content or ""
        except Exception:
            raw = ""

        concepts: list[str] = []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                concepts = [str(x).strip() for x in parsed]
        except Exception:
            for line in raw.splitlines():
                line = line.strip(" -\t0123456789.")
                if line:
                    concepts.append(line)
        if not concepts:
            words = re.findall(r"\b[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ-]{4,}(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ-]{4,})?\b", matter_text)
            concepts = words[:6] or ["Patron aprobado"]

        seen: set[str] = set()
        out: list[str] = []
        for concept in concepts:
            clean = re.sub(r"\s+", " ", concept).strip()
            key = clean.lower()
            if clean and key not in seen:
                seen.add(key)
                out.append(clean[:120])
            if len(out) >= 12:
                break
        return out

    def _approved_evidence(self, tenant_id: str, matter_id: str) -> list[str]:
        evidence = []
        for rec in self.trace_capture.read(tenant_id):
            if str(rec.get("matter_id")) != str(matter_id):
                continue
            if rec.get("hitl_outcome") != "approved":
                continue
            parts = [str(rec.get("input") or ""), str(rec.get("output") or ""), str(rec.get("draft_final") or "")]
            text = "\n\n".join(p for p in parts if p.strip())
            if text.strip():
                evidence.append(text)
        return evidence

    async def update_from_approved_matter(self, tenant_id: str, matter_id: str) -> list[str]:
        await self.init_wiki(tenant_id)
        evidence = self._approved_evidence(tenant_id, matter_id)
        if not evidence:
            return []
        matter_text = "\n\n".join(evidence)
        concepts = await self.extract_concepts(tenant_id, matter_text)
        for concept in concepts:
            await self.compile_concept(tenant_id, concept, evidence)
        self._update_sources(tenant_id, matter_id, concepts)
        self._update_index(tenant_id, concepts)
        return concepts

    def _update_sources(self, tenant_id: str, matter_id: str, concepts: list[str]) -> None:
        path = self.wiki_dir(tenant_id) / "sources.md"
        line = f"- {datetime.now(timezone.utc).isoformat()} matter:{matter_id} concepts: {', '.join(concepts)}\n"
        with path.open("a", encoding="utf-8") as f:
            f.write(line)

    def _update_index(self, tenant_id: str, concepts: list[str]) -> None:
        path = self.wiki_dir(tenant_id) / "index.md"
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        lines = [existing.rstrip(), "\n## Ultimas conexiones\n"] if existing.strip() else ["# Indice de conceptos\n"]
        for concept in concepts:
            lines.append(f"- [[{concept}]]\n")
        for left, right in zip(concepts, concepts[1:]):
            lines.append(f"- [[{left}]] -- [[{right}]]\n")
        path.write_text("".join(lines), encoding="utf-8")

    async def search_wiki(self, tenant_id: str, query: str) -> list[dict]:
        await self.init_wiki(tenant_id)
        terms = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 2]
        results: list[dict] = []
        for item in await self.list_concepts(tenant_id):
            text = (self.concept_path(tenant_id, item["name"]).read_text(encoding="utf-8"))
            haystack = text.lower()
            score = sum(1 for t in terms if t in haystack)
            if score or query.lower() in haystack:
                results.append({
                    "concept": item["name"],
                    "excerpt": _excerpt(text, query),
                    "confidence": item["confidence"],
                    "case_count": item["case_count"],
                })
        return results

    async def get_concept(self, tenant_id: str, concept_name: str) -> str | None:
        await self.init_wiki(tenant_id)
        path = self.concept_path(tenant_id, concept_name)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    async def list_concepts(self, tenant_id: str) -> list[dict]:
        await self.init_wiki(tenant_id)
        out: list[dict] = []
        for path in sorted(self.concepts_dir(tenant_id).glob("*.md")):
            meta, _ = _parse_frontmatter(path.read_text(encoding="utf-8"))
            out.append({
                "name": str(meta.get("concept") or path.stem),
                "confidence": float(meta.get("confidence") or 0.0),
                "case_count": int(meta.get("case_count") or 0),
                "last_updated": str(meta.get("last_updated") or ""),
            })
        return out

    async def lint_wiki(self, tenant_id: str) -> dict:
        await self.init_wiki(tenant_id)
        cutoff = date.today() - timedelta(days=90)
        index_text = (self.wiki_dir(tenant_id) / "index.md").read_text(encoding="utf-8")
        stale: list[str] = []
        orphan: list[str] = []
        low_confidence: list[str] = []
        for item in await self.list_concepts(tenant_id):
            name = item["name"]
            try:
                updated = date.fromisoformat(item["last_updated"])
                if updated < cutoff:
                    stale.append(name)
            except ValueError:
                stale.append(name)
            if index_text.count(f"[[{name}]]") < 2:
                orphan.append(name)
            if item["confidence"] < 0.3 and item["case_count"] < 2:
                low_confidence.append(name)
        return {"stale": stale, "orphan": orphan, "low_confidence": low_confidence}

    async def archive_concept(self, tenant_id: str, concept_name: str) -> None:
        await self.init_wiki(tenant_id)
        src = self.concept_path(tenant_id, concept_name)
        if not src.exists():
            return
        dst_dir = self.concepts_dir(tenant_id) / "archived"
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst_dir / src.name))
