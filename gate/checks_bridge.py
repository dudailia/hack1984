"""Choose Anant's checks/ if it exists, otherwise the loud stub.

If checks/ exists but fails to import, the error propagates: a broken checks module must stop the Gate,
never fall back silently to the allow-everything stub.
"""
import importlib
import importlib.util
import os
import sys

from gate import checks_stub

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load():
    """Return (run_all, memo_tokens, name) where name is "checks" or "stub"."""
    spec = importlib.util.find_spec("checks")
    if spec is None:
        print("*** CHECKS STUB: checks/ not found, using gate/checks_stub.py (ALLOWS EVERYTHING) ***", file=sys.stderr, flush=True)
        return checks_stub.run_all, checks_stub.memo_tokens, "stub"
    origin = getattr(spec, "origin", None)
    if isinstance(origin, str) and not os.path.abspath(origin).startswith(REPO_ROOT + os.sep):
        raise RuntimeError("a 'checks' module outside this repo was found; refusing to use it")
    mod = sys.modules.get("checks") or importlib.import_module("checks")
    run_all = getattr(mod, "run_all", None)
    if not callable(run_all):
        raise RuntimeError("checks module has no run_all")
    memo_tokens = getattr(mod, "memo_tokens", None)
    if not callable(memo_tokens):
        print("*** checks.memo_tokens not found: memo_tokens will be [] ***", file=sys.stderr, flush=True)
        memo_tokens = checks_stub.memo_tokens
    return run_all, memo_tokens, "checks"
