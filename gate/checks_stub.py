"""STUB until Anant's checks/ lands. It allows EVERYTHING. Owner of the real thing: Anant (checks/).

Needed from checks/ (checks/__init__.py): run_all(payload, session, kind) per FORMATS §6, and
memo_tokens(memo: str, approved_public_terms: list[str]) -> list[str], called once at session creation.
"""
import sys

BANNER = "*** CHECKS STUB: NOTHING IS CHECKED (checks/ not present). Do not demo or measure with this. ***"


def run_all(payload, session, kind):
    print(BANNER, file=sys.stderr, flush=True)
    return {"decision": "allow", "rule": None, "detail": None}


def memo_tokens(memo, approved_public_terms):
    print("*** CHECKS STUB: memo_tokens returns [] ***", file=sys.stderr, flush=True)
    return []
