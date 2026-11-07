"""
checks/canary.py: RULE 1, "canary".

WHAT A CANARY IS
----------------
The Gate plants a random token (e.g. "kq7m2xw9tpa4hd3n") in the memo when the session starts. It means nothing and
appears nowhere on the web. So if it, or even half of it, ever shows up in an outbound payload, some component
copied memo text out. That is a leak by definition, whatever else the payload says. This is the cheapest and most
certain check, so run_all runs it first among the leak rules.

WHAT WE LOOK FOR
----------------
For every decoded variant of every string in the payload (decode.variants: plain, base64, hex, %XX, rot13,
reversed ...), take the skeleton (only a-z0-9, so spacing/punctuation/case/look-alikes are gone) and search for:
  - the whole canary, or
  - ANY window of CANARY_FRAGMENT (8) consecutive canary characters.
And across the session: the skeleton of all earlier queries + this query, for windows that reach into this query
(so a canary split as "kq7m2x" + "w9tpa4hd3n" over two searches is caught).
"""

from checks import config
from checks.text import skeleton


def _windows(canary):
    """The whole canary plus every 8-char window of it. If the canary is shorter than 8, just itself."""
    n = config.CANARY_FRAGMENT
    if len(canary) <= n:
        return [canary]
    return [canary] + [canary[i:i + n] for i in range(len(canary) - n + 1)]


def check(views, session, query_history):
    """
    views:          list of (how, text) from decode.variants over every string in the payload
    session:        FORMATS section 4 session dict (we read session["canary"])
    query_history:  (prefix_skeleton, current_skeleton) for search/extract, or None for reader jobs
    Returns None (no canary) or (rule, detail).
    """
    canary = skeleton(session.get("canary") or "")
    if not canary:
        return None  # session without a canary: nothing to check (the Gate is expected to always plant one)
    wins = _windows(canary)

    # 1. Inside this payload, in any decoding.
    for how, text in views:
        sk = skeleton(text)
        for w in wins:
            if w in sk:
                kind = "canary" if w == canary else "canary fragment"
                return "canary", "%s found in outbound payload (%s)" % (kind, how)

    # 2. Split across this session's queries: look for a window that starts in earlier queries and ends in this
    #    one. (Windows entirely inside earlier queries were already judged when those queries went out.)
    if query_history:
        prefix, current = query_history
        joined = prefix + current
        for w in wins:
            start = joined.find(w, max(0, len(prefix) - len(w) + 1))
            if start != -1 and start < len(prefix) < start + len(w):
                return "canary", "canary split across this session's queries"
    return None
