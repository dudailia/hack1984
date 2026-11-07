"""Fixture pages for the fake Tavily: loading, deterministic keyword routing, planted-text substitution.

Pure functions, no network. All pages are fictional (invariant 9).
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FIXTURES = os.path.join(HERE, "fixtures", "halyard")
PLANTED_MARKER = "{{PLANTED}}"

TOP_SCORE = 0.92
SCORE_STEP = 0.07

_TOKEN = re.compile(r"[a-z0-9]+(?:/[a-z0-9]+)*")


def load_pages(fixtures_dir=DEFAULT_FIXTURES):
    """Load every *.json page in file-name order (the order is the ranking within a match)."""
    out = []
    for name in sorted(os.listdir(fixtures_dir)):
        if name.endswith(".json"):
            with open(os.path.join(fixtures_dir, name), encoding="utf-8") as f:
                page = json.load(f)
            page["keywords"] = [k.lower() for k in page.get("keywords", [])]
            out.append(page)
    poisoned = [p for p in out if p.get("poisoned")]
    if len(poisoned) > 1:
        raise ValueError("at most one poisoned page per fixture set")
    return out


def default_planted(pages):
    for p in pages:
        if p.get("poisoned"):
            return p["planted_default"]
    return ""


def tokens(query):
    """Lowercase word tokens; 'EV/revenue' yields 'ev/revenue', 'ev' and 'revenue'."""
    out = set()
    for tok in _TOKEN.findall(query.lower()):
        out.add(tok)
        out.update(tok.split("/"))
    return out


def search(pages, query, max_results=5):
    """Return the matching pages (unrendered), best first.

    Topical pages match on any keyword. The poisoned page is always included, last, and keeps its slot when
    max_results truncates. If nothing topical matches, the first ordinary page is added so the list is
    never only the poison.
    """
    if max_results <= 0:
        return []
    q = tokens(query)
    ordinary = [p for p in pages if not p.get("poisoned")]
    poisoned = [p for p in pages if p.get("poisoned")]
    matched = [p for p in ordinary if q.intersection(p["keywords"])]
    if not matched and ordinary:
        matched = ordinary[:1]
    if poisoned:
        return matched[: max_results - 1] + poisoned
    return matched[:max_results]


def score(rank):
    return round(TOP_SCORE - SCORE_STEP * rank, 4)


def render(page, planted):
    """Copy of the page with the planted text substituted (literal, single pass)."""
    out = dict(page)
    for k in ("content", "raw_content"):
        out[k] = page[k].replace(PLANTED_MARKER, planted)
    return out


def _norm(url):
    return url.strip().rstrip("/")


def lookup(pages, url):
    want = _norm(url)
    for p in pages:
        if _norm(p["url"]) == want:
            return p
    return None
