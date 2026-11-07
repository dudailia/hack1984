"""Validator (FORMATS §5): keep a claim only if every rule holds. Code only, no model."""
from reader.numbers import find_numbers, normalize, period_in, to_decimal, unit_consistent
from reader.schema import CLAIM_UNITS, check_claim


def _short_str(x):
    return x if isinstance(x, str) and len(x) <= 64 else None


def _reason(claim, job_types, docs):
    if check_claim(claim):
        return "bad_schema"
    ctype, unit = claim["claim_type"], claim["unit"]
    if ctype not in CLAIM_UNITS or ctype not in job_types:
        return "wrong_type"
    if unit not in CLAIM_UNITS[ctype]:
        return "unit_mismatch"
    doc = docs.get(claim["document_id"])
    if doc is None:
        return "unknown_document"
    quote = normalize(claim["quote"])
    if not quote or quote not in doc:
        return "quote_not_verbatim"
    target = to_decimal(claim["value"])
    spans = [(s, e) for v, s, e in find_numbers(quote) if v == target]
    if not spans:
        return "value_not_in_quote"
    if not any(unit_consistent(quote, s, e, unit) for s, e in spans):
        return "unit_mismatch"
    if not period_in(quote, claim["period"]):
        return "period_mismatch"
    return None


def validate(job, claims):
    """Return (kept, dropped). dropped entries are {claim_type, document_id, reason}."""
    job_types = set(job["claim_types"])
    docs = {d["id"]: normalize(d["text"]) for d in job["documents"]}
    kept, dropped = [], []
    for claim in claims:
        reason = _reason(claim, job_types, docs)
        if reason is None:
            kept.append(claim)
        else:
            c = claim if isinstance(claim, dict) else {}
            dropped.append({"claim_type": _short_str(c.get("claim_type")),
                            "document_id": _short_str(c.get("document_id")), "reason": reason})
    return kept, dropped
