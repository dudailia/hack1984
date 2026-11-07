"""Composer (FORMATS §10 answer data): template answer from validated claims. Code only, no model.

Every number in the output is either a validated claim value or computed here (invariant 8).
"""
import datetime
import re
import statistics
from collections import Counter
from decimal import Decimal

from reader.numbers import REPLACEMENT, normalize, to_decimal

MULTIPLE_LABELS = {"ev_revenue_multiple": "EV/revenue", "ev_ebitda_multiple": "EV/EBITDA"}
_FORWARD_RE = re.compile(r"\b(?:projected|projects|projection|projections|forecast|forecasts|forecasted|"
                         r"expected|expects|expect|will|outlook)\b", re.IGNORECASE)
# A multiple whose subject or quote is itself an aggregate is context, never a company in the peer median.
_AGGREGATE_RE = re.compile(r"\b(?:median|medians|average|averages|mean|index|indices|sector|sectors|industry|"
                           r"companies)\b", re.IGNORECASE)
_NAME_WORD = re.compile(r"[a-z0-9&]+")
_POSSESSIVE = re.compile(r"(?:'|\u2019)s?\b")
_SUFFIXES = {"inc", "incorporated", "corp", "corporation", "co", "company", "plc", "ltd", "limited", "llc", "lp",
             "sa", "ag", "nv", "se", "holdings", "holding", "group"}
_SUBJECT_NUMBER = re.compile(r"[0-9]+(?:[.,][0-9]+)*")
WITHHELD_SUBJECT = "[subject withheld]"
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
    """Result ids in first-seen order, each once."""
    ids = []
    for i in items:
        if i["source"]["result_id"] not in ids:
            ids.append(i["source"]["result_id"])
    return "[%s]" % ", ".join(ids)


def _period_end(period):
    """Last year of a "YYYY" or "YYYY-YYYY" period, else None."""
    last = period.split("-")[-1] if period else ""
    return int(last) if len(last) == 4 and last.isdigit() else None


def _is_forecast(item, year):
    """A forecast if the quote says so, or the period ends after the current year."""
    end = _period_end(item["period"])
    return bool(_FORWARD_RE.search(item["quote"])) or (end is not None and end > year)


def _is_aggregate(item):
    """A multiple whose subject or quote is an aggregate (median, average, index, sector, "... companies")."""
    return item["claim_type"] in MULTIPLE_LABELS and bool(
        _AGGREGATE_RE.search(normalize(item["subject"])) or _AGGREGATE_RE.search(normalize(item["quote"])))


def _company_words(subject):
    """Normalised company name as words: case, punctuation, possessive and legal suffixes ignored."""
    words = _NAME_WORD.findall(_POSSESSIVE.sub("", normalize(subject).casefold()))
    while len(words) > 1 and words[-1] in _SUFFIXES:
        words.pop()
    return tuple(words)


def _same_company(a, b):
    """Same company if one normalised name is the other's leading words ("Corvane" and "Corvane Pay")."""
    if not a or not b:
        return False
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return long_[:len(short)] == short


def _item_phrase(item, year):
    s, v, p, t = item["subject"], _fmt(item["value"]), item["period"], item["claim_type"]
    if t == "revenue_growth":
        if _is_forecast(item, year):
            return "the %s is projected to grow %s%%%s" % (s, v, _period_phrase(p, "growth"))
        return "%s grew %s%%%s" % (s, v, _period_phrase(p, "growth"))
    if t in MULTIPLE_LABELS and _is_aggregate(item):
        return "context: %s %sx %s%s" % (s, v, MULTIPLE_LABELS[t], _period_phrase(p, "for"))
    if t in MULTIPLE_LABELS:
        return "%s trades at %sx %s%s" % (s, v, MULTIPLE_LABELS[t], _period_phrase(p, "for"))
    if item["unit"] in _MONEY:
        pre, post = _MONEY[item["unit"]]
        return "%s: %s%s%s%s" % (s, pre, v, post, _period_phrase(p, "for"))
    return "%s: %s%s" % (s, v, _period_phrase(p, "for"))


def _headline(need, items):
    """Median multiple across companies for the most common period; None unless at least two companies.
    Aggregates are not companies; items are already one per company and period (compose)."""
    mtype = next((t for t in need.get("claim_types", []) if t in MULTIPLE_LABELS), None)
    pool = [i for i in items if i["claim_type"] == mtype and not _is_aggregate(i)]
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


def _need_text(need, items, headline, used, year):
    if not items:
        return "%s: not found." % _label(need)
    parts = []
    if headline:
        label = MULTIPLE_LABELS[used[0]["claim_type"]]
        parts.append("median %s %sx%s across %d companies %s" % (
            label, _fmt(headline["value"]), _period_phrase(headline["period"], "for"), len(used), _cite(used)))
    used_ids = {id(i) for i in used}
    parts += ["%s %s" % (_item_phrase(i, year), _cite([i])) for i in items if id(i) not in used_ids]
    return "%s: %s." % (_label(need), "; ".join(parts))


def _subject(claim):
    """The model-written subject, unless it carries a number the quote does not (invariant 8)."""
    subject, quote = normalize(claim["subject"]), normalize(claim["quote"])
    if REPLACEMENT in subject or any(n not in quote for n in _SUBJECT_NUMBER.findall(subject)):
        return WITHHELD_SUBJECT
    return claim["subject"]


def _keys(claim, subject):
    """A claim repeats an earlier one if any key matches: same subject; same number in the same document; or the
    same quoted sentence in another document. Stops one number being counted as several companies."""
    t, p, v = claim["claim_type"], claim["period"], to_decimal(claim["value"])
    keys = {("number", claim["document_id"], t, p, v), ("quote", normalize(claim["quote"]), t, p, v)}
    if subject != WITHHELD_SUBJECT:
        keys.add(("subject", _company_words(subject), t, p))
    return keys


def _repeats_company(claim, subject, companies):
    """One value per company (normalised subject) for each claim type and period; the first one is kept."""
    if subject == WITHHELD_SUBJECT or _is_aggregate(claim):
        return False
    words, tp = _company_words(subject), (claim["claim_type"], claim["period"])
    return any(tp == other_tp and _same_company(words, other) for other, other_tp in companies)


def compose(question, needs, kept, sources, today=None):
    """needs: [{"need", "claim_types", "label"?}]; kept: validated claims; sources: {result_id: {url, title}}.
    today: the date that decides past or forecast tense (default: the system date)."""
    year = (today or datetime.date.today()).year
    buckets = {n["need"]: [] for n in needs}
    seen = {n["need"]: set() for n in needs}
    companies = {n["need"]: [] for n in needs}
    for claim in sorted(kept, key=lambda c: c["document_id"]):
        src = sources.get(claim["document_id"])
        need = next((n for n in needs if claim["claim_type"] in n.get("claim_types", [])), None)
        if src is None or need is None:
            continue
        bucket = buckets[need["need"]]
        subject = _subject(claim)
        keys = _keys(claim, subject)
        if keys & seen[need["need"]] or _repeats_company(claim, subject, companies[need["need"]]):
            continue
        seen[need["need"]] |= keys
        if subject != WITHHELD_SUBJECT and not _is_aggregate(claim):
            companies[need["need"]].append((_company_words(subject), (claim["claim_type"], claim["period"])))
        bucket.append({"subject": subject, "claim_type": claim["claim_type"], "value": claim["value"],
                       "unit": claim["unit"], "period": claim["period"], "quote": claim["quote"],
                       "source": {"result_id": claim["document_id"], "url": src.get("url"),
                                  "title": src.get("title")}})
    out_needs, texts = [], []
    for need in needs:
        items = sorted(buckets[need["need"]], key=lambda i: (to_decimal(i["value"]), i["source"]["result_id"]))
        headline, used = _headline(need, items)
        out_needs.append({"need": need["need"], "status": "found" if items else "not_found",
                          "headline": headline, "items": items})
        texts.append(_need_text(need, items, headline, used, year))
    return {"question": question, "needs": out_needs, "text": " ".join(texts)}
