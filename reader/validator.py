"""Validator (FORMATS §5): keep a claim only if every rule holds. Code only, no model.

Numbers are read from the document, not from the quote alone: a number counts only if the whole number (sign
included) lies inside the quoted span, so a quote cut inside "14.2%" or "$412,000,000" cannot yield 4.2 or 412.
The unit marker must be inside the quote, and the document around it must not add a scale the quote cut off.
"""
from reader.numbers import normalize, period_in, scan, to_decimal, unit_consistent
from reader.request import check_job
from reader.schema import CLAIM_UNITS, check_claim


def _short_str(x):
    return x if isinstance(x, str) and len(x) <= 64 else None


def _occurrences(doc, quote):
    i = doc.find(quote)
    while i != -1:
        yield i
        i = doc.find(quote, i + 1)


def _reason(claim, job_types, docs, tokens):
    if check_claim(claim):
        return "bad_schema"
    ctype, unit = claim["claim_type"], claim["unit"]
    if ctype not in CLAIM_UNITS or ctype not in job_types:
        return "wrong_type"
    if unit not in CLAIM_UNITS[ctype]:
        return "unit_mismatch"
    did = claim["document_id"]
    doc = docs.get(did)
    if doc is None:
        return "unknown_document"
    quote = normalize(claim["quote"])
    starts = list(_occurrences(doc, quote)) if quote else []
    if not starts:
        return "quote_not_verbatim"
    target = to_decimal(claim["value"])
    reason = "value_not_in_quote"
    for o in starts:
        hi = o + len(quote)
        window = doc[o:hi]
        for t in tokens[did]:
            if t.start < o or t.end > hi or t.range or t.value is None or t.value != target:
                continue
            if not (unit_consistent(window, t.num_start - o, t.end - o, unit)
                    and unit_consistent(doc, t.num_start, t.end, unit)):
                reason = "unit_mismatch" if reason == "value_not_in_quote" else reason
                continue
            if not period_in(doc, claim["period"], o, hi):
                reason = "period_mismatch"
                continue
            return None
    return reason


def validate(job, claims):
    """Return (kept, dropped). dropped entries are {claim_type, document_id, reason}."""
    check_job(job)
    job_types = set(job["claim_types"])
    docs = {d["id"]: normalize(d["text"]) for d in job["documents"]}
    tokens = {i: scan(text) for i, text in docs.items()}
    kept, dropped = [], []
    for claim in claims:
        reason = _reason(claim, job_types, docs, tokens)
        if reason is None:
            kept.append(claim)
        else:
            c = claim if isinstance(claim, dict) else {}
            dropped.append({"claim_type": _short_str(c.get("claim_type")),
                            "document_id": _short_str(c.get("document_id")), "reason": reason})
    return kept, dropped
