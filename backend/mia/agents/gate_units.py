"""Conservative reuse of independently audited paragraph units with explicit dependencies."""
from __future__ import annotations

import json
import re

from .gate_evidence import CHECKER_VERSION, digest


def plan(text: str, evidence: dict, jurisdictions: list, previous: dict | None, *, tenant_id: str, matter_id: str) -> dict:
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    units = [{"id": f"p{i}", "text": p, "hash": digest(p)} for i, p in enumerate(paragraphs, 1)]
    context = digest(json.dumps({"evidence": evidence["manifest_hash"],
                                 "jurisdictions": sorted(jurisdictions),
                                 "checker": CHECKER_VERSION, "tenant_id": tenant_id, "matter_id": matter_id}, sort_keys=True))
    full_hash = digest(text)
    old = previous if isinstance(previous, dict) else {}
    receipts = old.get("units") or []
    old_by_id = {r.get("id"): r for r in receipts if isinstance(r, dict)}
    pending = {u["id"] for u in units if old_by_id.get(u["id"], {}).get("hash") != u["hash"]}
    # Missing coverage, changed evidence/context, deletions, reorderings and headings
    # cannot establish unchanged semantics. Duplicate paragraphs are ambiguous too.
    full = (not tenant_id or not matter_id or old.get("context") != context or not old.get("complete") or
            len(receipts) != len(units) or len({u["hash"] for u in units}) != len(units))
    if old.get("text_hash") != full_hash:
        old_hashes = {r.get("hash") for r in receipts}
        if any(u["id"] in pending and (u["text"].lstrip().startswith("#") or
                u["hash"] in old_hashes or len(u["text"].strip()) < 60) for u in units):
            full = True
        if any(r.get("scope") != "local" for r in receipts):
            full = True
    if full:
        pending = {u["id"] for u in units}
    else:
        while True:
            affected = {r["id"] for r in receipts
                        if set(r.get("unit_dependencies") or []) & pending}
            if affected <= pending:
                break
            pending |= affected
    return {"units": units, "pending": sorted(pending), "context": context,
            "text_hash": full_hash, "full": full,
            "inherited": [r for r in receipts if r.get("id") not in pending]}


def decode(raw):
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    if raw.startswith("```json\n") and raw.endswith("\n```"):
        raw = raw[8:-4].strip()
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def accept(raw: str, current: dict, source_ids: set[str]) -> tuple[bool, dict | None]:
    """Only explicit, exact structured coverage may create local receipts."""
    parsed = decode(raw)
    if parsed is None:
        return False, None
    if not isinstance(parsed, dict) or parsed.get("veredicto") != "APTO":
        return False, None
    if not isinstance(parsed.get("impacto_global"), bool) or (parsed["impacto_global"] and not current["full"]):
        return False, None
    rows = parsed.get("unidades")
    if not isinstance(rows, list) or len(rows) != len(current["pending"]):
        return False, None
    ids = {u["id"] for u in current["units"]}
    by_id = {u["id"]: u for u in current["units"]}
    seen, receipts = set(), list(current["inherited"])
    for row in rows:
        if not isinstance(row, dict):
            return False, None
        uid = row.get("id")
        unit_deps, source_deps = row.get("dependencias_unidades"), row.get("dependencias_fuentes")
        if (uid not in current["pending"] or uid in seen or row.get("apto") is not True or
                row.get("alcance") not in ("local", "global") or
                not isinstance(unit_deps, list) or not isinstance(source_deps, list) or
                any(not isinstance(v, str) for v in unit_deps + source_deps) or
                not set(unit_deps) <= ids or not set(source_deps) <= source_ids):
            return False, None
        if not current["full"] and row["alcance"] == "global":
            return False, None
        seen.add(uid)
        receipts.append({"id": uid, "hash": by_id[uid]["hash"],
                         "scope": "global" if parsed["impacto_global"] else row["alcance"], "unit_dependencies": unit_deps,
                         "source_dependencies": source_deps})
    return True, {"complete": True, "context": current["context"],
                  "text_hash": current["text_hash"], "units": receipts}
