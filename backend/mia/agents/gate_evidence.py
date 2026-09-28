"""Textual evidence for the independent gate; never silently truncate originals."""
from __future__ import annotations

import hashlib
import json
import re

from ..memory.tokens import estimate_tokens

CHECKER_VERSION = "citation-verifier-v3"


def source_locator(source: dict, index: int) -> str:
    return str((f"{source['source_kind']}:{source['source_id']}" if source.get("source_kind") and source.get("source_id") else "") or
               source.get("locator") or source.get("source_path") or source.get("url") or source.get("id") or f"research_sources[{index}]")


def select_used(text: str, sources: list, documents: list, report: dict | None = None) -> tuple[list, list]:
    """Select only unambiguous cited identities; uncertainty retains the full input."""
    from . import verification
    refs = set(verification._sentence_doc_refs(text))
    invalid_refs = refs - set(range(1, len(documents) + 1))
    if invalid_refs:
        documents = [*documents, *[{"content": "", "gate_locator": f"[doc {n}]"}
                                   for n in sorted(invalid_refs)]]
    citations = verification.scan_citations(text)
    if report and isinstance(report.get("detalle"), list):
        details = report["detalle"]
        if len(details) != int(report.get("citas") or 0) or any(not isinstance(d, dict) or not d.get("cita") for d in details):
            return sources, documents
        citations = [{"citation": d["cita"]} for d in details]
    # Unknown-pattern references still present literally must remain in the inventory.
    normalized_text = verification._normalize(text)
    for source in sources:
        if isinstance(source, dict):
            reference = str(source.get("referencia") or "")
            if reference and verification._normalize(reference) in normalized_text:
                citations.append({"citation": reference})
    chosen = []
    for citation in citations:
        detail = next((d for d in (report or {}).get("detalle", [])
                       if isinstance(d, dict) and d.get("cita") == citation["citation"]), {})
        backing = detail.get("fuente") or {}
        if backing.get("tipo") == "expediente":
            if detail.get("estado") == "sellada":
                # A seal's doc number belongs to its earlier turn. Without a
                # source fingerprint in the report, the current position is unknown.
                return sources, documents
            doc_refs = verification._sentence_doc_refs(str(backing.get("referencia") or ""))
            if len(doc_refs) == 1 and 1 <= doc_refs[0] <= len(documents) and not invalid_refs:
                refs.update(doc_refs)
                continue
            return sources, documents
        matches = [s for s in sources if isinstance(s, dict) and
                   verification._backing_source(citation["citation"],
                                                verification.source_index([s])) is not None]
        if len(matches) != 1:
            return sources, documents
        if matches[0] not in chosen:
            chosen.append(matches[0])
    # Facts without explicit document locators cannot safely discard evidence.
    selected_docs = documents
    if refs and all(1 <= n <= len(documents) for n in refs):
        # Preserve locator numbering while excluding unused entries.
        selected_docs = [{**d, "gate_locator": f"[doc {i}]"} if isinstance(d, dict)
                         else {"content": str(d), "gate_locator": f"[doc {i}]"}
                         for i, d in enumerate(documents, 1) if i in refs]
    selected_sources = [s for s in sources if s in chosen or
                        (isinstance(s,dict) and str(s.get("evidence_kind") or "").startswith("derived"))] if citations else sources
    return selected_sources, selected_docs


def explicit_dependencies(text: str, sources: list, documents: list, report: dict | None = None) -> set[str]:
    """Current literal anchors and unambiguous cited source identities are mandatory.

    Inputs retained because of ambiguity remain evidence for the auditor; retention
    itself is not proof of a dependency. Historical sealed doc numbers are excluded.
    """
    from . import verification
    refs = set(verification._sentence_doc_refs(text))
    citations = verification.scan_citations(text)
    details = (report or {}).get("detalle") or []
    citations.extend({"citation":d["cita"]} for d in details if isinstance(d,dict) and d.get("cita"))
    normalized = verification._normalize(text)
    citations.extend({"citation":s["referencia"]} for s in sources if isinstance(s,dict) and s.get("referencia") and
                     verification._normalize(s["referencia"]) in normalized)
    for d in details:
        if isinstance(d,dict) and d.get("estado") != "sellada" and (d.get("fuente") or {}).get("tipo") == "expediente":
            refs.update(verification._sentence_doc_refs(str(d["fuente"].get("referencia") or "")))
    required = set()
    for c in citations:
        matches = [(i,s) for i,s in enumerate(sources,1) if isinstance(s,dict) and
                   verification._backing_source(c["citation"],verification.source_index([s])) is not None]
        if len(matches) == 1:
            required.add(source_locator(matches[0][1],matches[0][0]))
    for i,d in enumerate(documents,1):
        locator = str(d.get("gate_locator") or f"[doc {i}]") if isinstance(d,dict) else f"[doc {i}]"
        if set(verification._sentence_doc_refs(locator)) & refs:
            required.add(locator)
    return required


def provenance(item: dict) -> dict:
    fields = ("source_kind","source_id","id","origin_hash","reviewed_hash","document_id","ord",
              "folio_ancla","filename","url","source_path","jurisdiction","numero","fecha","titulo")
    return {key:item[key] for key in fields if key in item}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build(sources: list, documents: list, *, budget_tokens: int, text: str | None = None, report: dict | None = None) -> dict:
    from . import verification
    entries, missing, excluded_candidates = [], [], []
    for i, source in enumerate(sources or [], 1):
        if not isinstance(source, dict):
            missing.append(f"source {i}")
            continue
        identity = str(source.get("referencia") or source.get("titulo") or "")
        passage = str(source.get("pasaje") or source.get("excerpt") or "")
        original = str(next((source[k] for k in
                            ("content", "contenido", "texto", "texto_completo", "full_text")
                            if source.get(k)), ""))
        locator = source_locator(source,i)
        derived = str(source.get("evidence_kind") or "primary_text").startswith("derived")
        explicit_citations = verification.scan_citations(text or "")
        unresolved_inventory = False
        if report and isinstance(report.get("detalle"), list):
            explicit_citations.extend({"citation":d["cita"]} for d in report["detalle"] if isinstance(d,dict) and d.get("cita"))
            unresolved_inventory = any(isinstance(d,dict) and d.get("cita") and
                (d.get("fuente") or {}).get("tipo") != "expediente" and
                not any(verification._backing_source(d["cita"],verification.source_index([s])) for s in sources if isinstance(s,dict))
                for d in report["detalle"])
        # Only explicit identities/pattern citations prohibit exclusion; semantic
        # dependence is assessed by the same auditor against the global text.
        excludable = derived and text is not None and bool(identity) and not unresolved_inventory and not (
            verification._normalize(identity) in verification._normalize(text) or
            any(verification._backing_source(c["citation"], verification.source_index([source]))
                for c in explicit_citations))
        if excludable:
            excluded_candidates.append({"locator": locator, "identity": identity})
        elif (not identity.strip() or not original.strip() or derived):
            missing.append(identity or locator)
        entries.append({"identity": identity, "locator": locator, "passage": passage,
                        "original": original, "evidence_kind": source.get("evidence_kind") or "provided_text",
                        "hash": digest(original), "available": not derived and bool(original.strip()),
                        "provenance": provenance(source)})
    for i, doc in enumerate(documents or [], 1):
        raw = (str(doc.get("content") or doc.get("text") or "")
               if isinstance(doc, dict) else str(doc or ""))
        identity = str(doc.get("filename") or doc.get("title") or doc.get("id") or f"doc {i}") if isinstance(doc, dict) else f"doc {i}"
        if not raw.strip():
            missing.append(str(doc.get("gate_locator") or f"[doc {i}]") if isinstance(doc, dict) else f"[doc {i}]")
        entries.append({"identity": identity, "locator": str(doc.get("gate_locator") or f"[doc {i}]") if isinstance(doc, dict) else f"[doc {i}]",
                        "original": raw, "evidence_kind": "document_excerpt", "hash": digest(raw), "available": bool(raw.strip()),
                        "provenance": provenance(doc) if isinstance(doc,dict) else {}})
    payload = json.dumps(entries, ensure_ascii=False, sort_keys=True, default=str)
    over_budget = estimate_tokens(payload) > max(0, budget_tokens)
    complete = any(e["available"] for e in entries) and not missing and not over_budget
    return {"payload": payload if not over_budget else "",
            "manifest_hash": digest(payload), "complete": complete,
            "total": len(entries), "missing": missing, "over_budget": over_budget,
            "tokens": estimate_tokens(payload), "scope": "received_material",
            "exclusion_candidates": excluded_candidates}


def reviewed_selection(text: str, md: dict, documents: list) -> tuple[list, list]:
    reviewed = md.get("audited_evidence_selection") or {}
    if (reviewed.get("text_hash") == digest(text) and len(str(reviewed.get("manifest_hash") or "")) == 64 and
            reviewed.get("selection_hash") == selection_hash(reviewed.get("sources") or [],reviewed.get("documents") or [])):
        return reviewed.get("sources") or [], reviewed.get("documents") or []
    return [], []


def selection_hash(sources: list, documents: list) -> str:
    return digest(json.dumps({"sources":sources,"documents":documents},sort_keys=True,ensure_ascii=False,default=str))
