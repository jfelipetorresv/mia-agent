"""One canonical identity/content fingerprint for captured and live source rows."""
import hashlib
import json

FIELDS = {
    "legal_norm": ("id", "norm_type", "norm_number", "issuing_body", "title", "full_text",
                   "effective_date", "expiry_date", "jurisdiction"),
    "chunk": ("id", "content", "document_id", "ord", "folio_ancla", "filename"),
}


def fingerprint(kind: str, row: dict) -> str:
    fields = FIELDS.get(kind)
    if fields is None:
        raise ValueError("No primary source fingerprint contract for this source kind")
    canonical = {key: str(row.get(key) or "") for key in fields}
    return hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()
