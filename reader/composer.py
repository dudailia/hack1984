"""Composer (FORMATS §10 answer data): template answer from validated claims. Code only, no model.

Every number in the output is either a validated claim value or computed here (invariant 8).
"""
import re
import statistics
from collections import Counter
from decimal import Decimal

from reader.numbers import to_decimal

MULTIPLE_LABELS = {"ev_revenue_multiple": "EV/revenue", "ev_ebitda_multiple": "EV/EBITDA"}
_FORWARD_RE = re.compile(r"\b(?:projected|forecast|forecasts|expected|expects|expect|will|outlook)\b", re.IGNORECASE)
_MONEY = {"usd": ("$", ""), "usd_millions": ("$", " million"), "usd_billions": ("$", " billion")}


def _fmt(value):
    d = value if isinstance(value, Decimal) else to_decimal(value)
    return format(d, "f")


def _label(need):
    return need.get("label") or need["need"].replace("_", " ").capitalize()


def _period_phrase(period, word):
    if period == "":
        return ""
    if period == "ttm":
        return " over the trailing twelve months"
    if "-" in period:
        a, b = period.split("-")
        return " a year from %s to %s" % (a, b) if word == "growth" else " for %s to %s" % (a, b)
    return " %s %s" % ("in" if word == "growth" else "for", period)


def _cite(items):
    return "[%s]" % ", ".join(i["source"]["result_id"] for i in items)


def _item_phrase(item):
    s, v, p, t = item["subject"], _fmt(item["value"]), item["period"], item["claim_type"]
    if t == "revenue_growth":
        if _FORWARD_RE.search(item["quote"]):
            return "the %s is projected to grow %s%%%s" % (s, v, _period_phrase(p, "growth"))
        return "%s grew %s%%%s" % (s, v, _period_phrase(p, "growth"))
    if t in MULTIPLE_LABELS:
        return "%s trades at %sx %s%s" % (s, v, MULTIPLE_LABELS[t], _period_phrase(p, "for"))
    if item["unit"] in _MONEY:
        pre, post = _MONEY[item["unit"]]
        return "%s: %s%s%s%s" % (s, pre, v, post, _period_phrase(p, "for"))
    return "%s: %s%s" % (s, v, _period_phrase(p, "for"))


def _headline(need, items):
    """Median multiple across companies for the most common period; None unless at least two companies."""
    mtype = next((t for t in need.get("claim_types", []) if t in MULTIPLE_LABELS), None)
    pool = [i for i in items if i["claim_type"] == mtype]
    if len(pool) < 2:
        return None, []
    counts = Counter(i["period"] for i in pool)
    period = max(counts, key=lambda p: (counts[p], p))
    used = [i for i in pool if i["period"] == period]
    if len(used) < 2:
        return None, []
    median = statistics.median(to_decimal(i["value"]) for i in used)
    value = float(round(median, 4))
    return {"value": value, "unit": "multiple", "period": period,
            "method": "median of %d companies" % len(used)}, used


def _need_text(need, items, headline, used):
    if not items:
        return "%s: not found." % _label(need)
    parts = []
    if headline:
        label = MULTIPLE_LABELS[used[0]["claim_type"]]
        parts.append("median %s %sx%s across %d companies %s" % (
            label, _fmt(headline["value"]), _period_phrase(headline["period"], "for"), len(used), _cite(used)))
    used_ids = {id(i) for i in used}
    parts += ["%s %s" % (_item_phrase(i), _cite([i])) for i in items if id(i) not in used_ids]
    return "%s: %s." % (_label(need), "; ".join(parts))


def compose(question, needs, kept, sources):
    """needs: [{"need", "claim_types", "label"?}]; kept: validated claims; sources: {result_id: {url, title}}."""
    buckets = {n["need"]: [] for n in needs}
    for claim in sorted(kept, key=lambda c: c["document_id"]):
        src = sources.get(claim["document_id"])
        need = next((n for n in needs if claim["claim_type"] in n.get("claim_types", [])), None)
        if src is None or need is None:
            continue
        bucket = buckets[need["need"]]
        key = (claim["subject"].strip().casefold(), claim["claim_type"], claim["period"])
        if any((i["subject"].strip().casefold(), i["claim_type"], i["period"]) == key for i in bucket):
            continue
        bucket.append({"subject": claim["subject"], "claim_type": claim["claim_type"], "value": claim["value"],
                       "unit": claim["unit"], "period": claim["period"], "quote": claim["quote"],
                       "source": {"result_id": claim["document_id"], "url": src.get("url"),
                                  "title": src.get("title")}})
    out_needs, texts = [], []
    for need in needs:
        items = sorted(buckets[need["need"]], key=lambda i: (to_decimal(i["value"]), i["source"]["result_id"]))
        headline, used = _headline(need, items)
        out_needs.append({"need": need["need"], "status": "found" if items else "not_found",
                          "headline": headline, "items": items})
        texts.append(_need_text(need, items, headline, used))
    return {"question": question, "needs": out_needs, "text": " ".join(texts)}
