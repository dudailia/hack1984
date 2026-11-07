"""
checks/: the Gate's second layer. Pure Python: no network, no models, no files at call time.

=====================================================================================================================
THE ONE FUNCTION THE GATE CALLS
=====================================================================================================================

    result = checks.run_all(payload, session, kind)

    payload  str   the EXACT outbound body the Gate is about to send (canonical UTF-8 JSON, FORMATS section 0)
    session  dict  the Gate's session (FORMATS section 4): canary, confirmed_secrets, approved_public_terms,
                   memo_tokens, queries_sent, public_text_received, result_ids, urls_returned, call_count,
                   credits_used
    kind     str   "search" | "extract" | "reader"

    returns  {"decision": "allow" | "block", "rule": str | None, "detail": str | None}

    The Gate writes `rule` into the ledger row and shows `detail` in the UI. If this function RAISES, the Gate blocks
    with gate.check_error (fail closed), so a bug here can only cause a false block, never a leak.

And one helper the Gate calls ONCE when it creates a session:

    session["memo_tokens"] = checks.memo_tokens(memo, approved_public_terms)

=====================================================================================================================
WHAT HAPPENS INSIDE run_all, IN ORDER (first rule that fires wins)
=====================================================================================================================

  0. Parse      payload -> JSON object, else "shape.bad_payload". Unknown kind -> "shape.bad_kind".
  1. Collect    every string (and number) inside the JSON, recursively -> `strings`.
  2. Decode     decode.variants() on each string -> `views`: the plain text plus base64 / hex / %XX / HTML-entity /
                \\u-escape decodings (up to 3 layers deep), each also rot13'd and reversed.
  3. History    for search/extract: skeleton(all earlier queries) and skeleton(this query), for split detection.
  4. canary         (canary.py)       the planted random token or any 8-char piece of it, in any view or split.
  5. secret.<label> (secret_terms.py) a confirmed secret in any spelling, encoding, number format, or split.
  6. provenance.*   (provenance.py)   a rare memo word/number the web has not shown us this session.
  7. shape.*        (shape.py)        size, budget, extract URLs, forbidden parameters, reader tools.

Leak rules run before shape so that when a payload is BOTH leaking and over budget, the ledger records the leak.

In doublethink mode a "block" stops the request. In the fake-only modes (single_agent, compromised, two_minds) the
Gate still calls run_all and records the rule on the row but sends anyway: that is how a baseline leak gets counted
(FORMATS section 1). run_all itself does not know or care about the mode.
"""

import json

from checks import canary, provenance, secret_terms, shape
from checks.decode import variants
from checks.provenance import memo_tokens, query_skeletons

__all__ = ["run_all", "memo_tokens", "KINDS"]

KINDS = ("search", "extract", "reader")


def _allow():
    return {"decision": "allow", "rule": None, "detail": None}


def _block(rule, detail):
    return {"decision": "block", "rule": rule, "detail": detail}


def _strings(obj, out):
    """Collect every string value (and every number, as text) inside a JSON value. Keys are skipped: the Gate
    builds every body from a fixed set of keys, and anything an attacker controls ends up in a value."""
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, bool) or obj is None:
        pass
    elif isinstance(obj, (int, float)):
        out.append(str(obj))  # a price smuggled as a JSON number, e.g. "max_results": 412000000
    elif isinstance(obj, list):
        for v in obj:
            _strings(v, out)
    elif isinstance(obj, dict):
        for v in obj.values():
            _strings(v, out)
    return out


def run_all(payload, session, kind):
    # ---- 0. parse ---------------------------------------------------------------------------------------------
    if kind not in KINDS:
        return _block("shape.bad_kind", "unknown request kind")
    try:
        body = json.loads(payload)
    except (TypeError, ValueError):
        return _block("shape.bad_payload", "payload is not JSON")
    if not isinstance(body, dict):
        return _block("shape.bad_payload", "payload is not a JSON object")
    payload_bytes = len(payload.encode("utf-8"))

    # ---- 1-3. collect strings, decode them, build query history ---------------------------------------------
    strings = _strings(body, [])
    views = []
    for s in strings:
        views.extend(variants(s))

    query_history = None
    prov_strings = strings                       # reader: provenance scans everything
    if kind in ("search", "extract"):
        q = body.get("query")
        q = q if isinstance(q, str) else ""
        query_history = query_skeletons(session, q)
        prov_strings = [q] if q else []          # search/extract: provenance scans the query only

    # ---- 4-7. the rules, leak rules first; each returns None or (rule, detail) -----------------------------------
    rules = (
        lambda: canary.check(views, session, query_history),                 # 4. canary
        lambda: secret_terms.check(views, session, query_history),           # 5. secret.<label>
        lambda: provenance.check(prov_strings, session, kind, query_history),  # 6. provenance.*
        lambda: shape.check(body, payload_bytes, session, kind),             # 7. shape.*
    )
    for rule in rules:
        hit = rule()
        if hit:
            return _block(*hit)
    return _allow()
