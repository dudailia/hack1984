"""Claim schema from shared/FORMATS.md §1 and §5."""
import math
import re

CLAIM_UNITS = {
    "revenue": ("usd", "usd_millions", "usd_billions"),
    "revenue_growth": ("percent",),
    "ev_revenue_multiple": ("multiple",),
    "ev_ebitda_multiple": ("multiple",),
    "ebitda": ("usd", "usd_millions", "usd_billions"),
    "market_size": ("usd", "usd_millions", "usd_billions"),
    "employees": ("count",),
    "founded_year": ("year",),
}

CLAIM_KEYS = frozenset(("claim_type", "subject", "value", "unit", "period", "quote", "document_id"))
SUBJECT_MAX = 80
QUOTE_MAX = 400
ID_MAX = 32
PERIOD_RE = re.compile(r"(?:|\d{4}|\d{4}-\d{4}|ttm)")


def _nonempty_str(x, limit):
    return isinstance(x, str) and 0 < len(x) <= limit


def period_ok(period):
    if not isinstance(period, str) or not PERIOD_RE.fullmatch(period):
        return False
    if len(period) == 9:
        start, end = period.split("-")
        return start < end
    return True


def check_claim(claim):
    """Return None if the claim has the §5 shape, else the reason "bad_schema"."""
    if not isinstance(claim, dict) or set(claim) != CLAIM_KEYS:
        return "bad_schema"
    value = claim["value"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "bad_schema"
    if isinstance(value, float) and not math.isfinite(value):
        return "bad_schema"
    if not (_nonempty_str(claim["claim_type"], ID_MAX) and _nonempty_str(claim["unit"], ID_MAX)
            and _nonempty_str(claim["document_id"], ID_MAX) and _nonempty_str(claim["subject"], SUBJECT_MAX)
            and _nonempty_str(claim["quote"], QUOTE_MAX) and period_ok(claim["period"])):
        return "bad_schema"
    return None
