"""GET /v1/bundle: hand off to Anant's proof.export.export_bundle if proof/ exists. gate/ never edits proof/.

Interface (Anant): export_bundle(session_id, db_path, reveal="allowed", key_path) -> bytes; it opens the DB
read-only itself. Paths are always absolute, derived from the Gate's own ledger location, never the cwd.
"""
import importlib
import importlib.util
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY_FILE = "ed25519_private.pem"


class NotAvailable(Exception):
    pass


def _load():
    spec = importlib.util.find_spec("proof")
    if spec is None:
        raise NotAvailable("proof/ is not present")
    origin = getattr(spec, "origin", None)
    if isinstance(origin, str) and not os.path.abspath(origin).startswith(REPO_ROOT + os.sep):
        raise NotAvailable("a 'proof' module outside this repo was found; refusing to use it")
    if importlib.util.find_spec("proof.export") is None:
        raise NotAvailable("proof.export is not present")
    fn = getattr(importlib.import_module("proof.export"), "export_bundle", None)
    if not callable(fn):
        raise NotAvailable("proof.export has no export_bundle")
    return fn


def export(session_id, ledger_path):
    db = os.path.abspath(ledger_path)
    key = os.path.join(os.path.dirname(db), KEY_FILE)
    out = _load()(session_id, db_path=db, reveal="allowed", key_path=key)
    if not isinstance(out, bytes):
        raise TypeError("export_bundle must return bytes")
    return out
