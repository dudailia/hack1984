"""STUB until Anant's checks/ lands. It allows EVERYTHING. Owner of the real thing: Anant (checks/).

Needed from checks/: run_all(payload, session, kind) per FORMATS §6, and a memo_tokens(memo) -> [str] function
(name is Anant's choice; gate/checks_bridge.py looks for `memo_tokens`).
"""
import sys

BANNER = "*** CHECKS STUB: NOTHING IS CHECKED (checks/ not present). Do not demo or measure with this. ***"


def run_all(payload, session, kind):
    print(BANNER, file=sys.stderr, flush=True)
    return {"decision": "allow", "rule": None, "detail": None}


def memo_tokens(memo):
    print("*** CHECKS STUB: memo_tokens returns [] ***", file=sys.stderr, flush=True)
    return []
