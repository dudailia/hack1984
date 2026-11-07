"""
proof/export.py: turn one session's ledger into a signed bundle (shared/FORMATS.md section 8).

    python3 -m proof.export SESSION_ID [--db ledger/doublethink.db] [--out bundles] [--reveal allowed|none]

WHO CALLS THIS (the two entry points)
-------------------------------------
export_bundle(session_id, db_path="ledger/doublethink.db", reveal="allowed",
              key_path="ledger/ed25519_private.pem") -> bytes
    Aayush's Gate, for GET /v1/bundle?session_id=...: returns the bundle bytes, writes no file.
    (The Gate process must have `cryptography` installed for this import.)

export_session(session_id, db_path=..., out_dir="bundles", reveal="allowed", key_path=...) -> path
    The same bytes written to bundles/<session_id>.json. Used by app/run.py for POST /api/verify (then it runs
    `python3 proof/verify.py <path> --json` as a subprocess) and POST /api/tamper (proof.tamper.tamper_and_verify).

THE LEDGER WE READ (Aayush's gate/, as he described it)
-------------------------------------------------------
ledger/doublethink.db, one table keyed by (session_id, seq) with columns:
    row_json      the canonical FORMATS section 7 row, INCLUDING its "hash" (gate/ledger.py sets row["hash"] before
                  inserting canonical_json(row))                          -> parsed and becomes the bundle row
    hash          that row's hash, also as its own column                 -> written over row["hash"]; the two
                  are equal in an honest ledger, and if they ever differ the verifier reports hash_mismatch
    nonce_priv    private, never hashed: the row's nonce (BLOB, or hex TEXT; both accepted)
    payload_priv  private, never hashed: attempt row = exact payload sent; result row = response body
UPDATE and DELETE are refused by triggers. We open the file READ ONLY and never write it.
The table's name is found by its columns (see _find_table), so a rename on the Gate side does not break export.

THE PIECES
----------
commitment(nonce, payload)   SHA-256(nonce || payload) as hex. The ledger stores this instead of the payload, so a
                             shared bundle proves WHAT was sent without having to show it.
attempt_row(...) / result_row(...)
                             build a FORMATS section 7 row and chain it (prev_hash -> hash). The Gate writes rows,
                             not us; these exist so tests (and Aayush, if he wants) produce byte-identical rows.
code_hashes(repo_root)       SHA-256 of every .py under gate/ and checks/ (tests excluded): which code was on disk
                             when the bundle was made.
load_or_create_key(path)     the install's Ed25519 key, ledger/ed25519_private.pem (gitignored), created on first
                             export with file mode 0600. Never printed, never logged.
build_bundle(...)            rows + optional reveals + head + code_hashes + public key + signature -> canonical
                             bytes. Pure: no files, no clock.
rows_from_sqlite(db, sid)    read one session's rows (and, for attempt rows, payload/nonce) from the Gate's ledger.
export_bundle(sid, ...)      rows_from_sqlite + code_hashes + key + build_bundle -> bytes.
export_session(sid, ...)     export_bundle, written to bundles/<session_id>.json; returns the path.

REVEAL POLICY
-------------
"allowed" (default): every CLEAN allowed attempt (decision "allowed" AND rule None) carries reveal {payload, nonce},
so the reader sees each query that actually left. Those payloads passed every check, so they are public by
definition. NEVER revealed:
  - blocked attempts: exactly the payloads that would have leaked the secret;
  - allowed attempts WITH a rule: in the fake-only baseline modes a leak is sent anyway and recorded with its rule,
    so the payload is the leaked secret (PR #4 review, Aayush);
  - result rows: their private columns hold the RESPONSE (web text), not something we sent.
"none": no reveals at all.
"""

import datetime
import hashlib
import json
import os
import pathlib
import sqlite3
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# The verifier's own definitions, so the exporter and verifier can never disagree about canonical form, row hashes
# or the signed message. (The dependency goes this way only: verify.py imports nothing from us.)
from proof.verify import FORMAT, ZERO_HASH, canonical_json, row_hash, signed_message

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(_ROOT, "ledger", "doublethink.db")
DEFAULT_KEY = os.path.join(_ROOT, "ledger", "ed25519_private.pem")
DEFAULT_OUT = os.path.join(_ROOT, "bundles")
HASHED_DIRS = ("gate", "checks")

__all__ = ["commitment", "attempt_row", "result_row", "row_hash", "canonical_json", "code_hashes",
           "load_or_create_key", "sign", "build_bundle", "rows_from_sqlite", "export_bundle", "export_session",
           "LedgerSchemaError"]


# ---------------------------------------------------------------------------------------------------------------
# Rows (FORMATS section 7)
# ---------------------------------------------------------------------------------------------------------------

def commitment(nonce, payload):
    """SHA-256(nonce || payload) hex. nonce: 32 random bytes per row. payload: the exact bytes sent/received."""
    return hashlib.sha256(bytes(nonce) + bytes(payload)).hexdigest()


def attempt_row(seq, time, session_id, component, kind, destination, payload, nonce, decision, rule, prev_hash):
    """An attempt row (written BEFORE sending), with its hash filled in."""
    row = {"seq": seq, "time": time, "session_id": session_id, "row_type": "attempt", "component": component,
           "kind": kind, "destination": destination, "commitment": commitment(nonce, payload),
           "bytes": len(payload), "decision": decision, "rule": rule, "prev_hash": prev_hash}
    row["hash"] = row_hash(row)
    return row


def result_row(seq, time, session_id, attempt_seq, status, http_status, credits_used, response, nonce, prev_hash):
    """A result row (written AFTER the response), with its hash filled in. Blocked attempts never get one."""
    row = {"seq": seq, "time": time, "session_id": session_id, "row_type": "result", "attempt_seq": attempt_seq,
           "status": status, "http_status": http_status, "credits_used": credits_used,
           "response_commitment": commitment(nonce, response), "prev_hash": prev_hash}
    row["hash"] = row_hash(row)
    return row


# ---------------------------------------------------------------------------------------------------------------
# Code hashes and key
# ---------------------------------------------------------------------------------------------------------------

def code_hashes(repo_root=_ROOT):
    """{"checks/__init__.py": sha256hex, "gate/server.py": ...} for every .py under gate/ and checks/, skipping any
    tests/ folder and any test_*.py file. Missing folders (gate/ before Aayush merges) are simply skipped."""
    out = {}
    for top in HASHED_DIRS:
        base = os.path.join(repo_root, top)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in ("tests", "__pycache__"))
            for fn in sorted(filenames):
                if fn.endswith(".py") and not fn.startswith("test_"):
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, repo_root).replace(os.sep, "/")
                    with open(full, "rb") as f:
                        out[rel] = hashlib.sha256(f.read()).hexdigest()
    return out


def load_or_create_key(path=DEFAULT_KEY):
    """Load the install's Ed25519 private key, or create it (mode 0600) on first use."""
    if os.path.exists(path):
        with open(path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)   # never world-readable, never overwritten
    with os.fdopen(fd, "wb") as f:
        f.write(pem)
    return key


def sign(private_key, bundle):
    """Ed25519 signature (hex) over verify.signed_message(bundle)."""
    return private_key.sign(signed_message(bundle)).hex()


# ---------------------------------------------------------------------------------------------------------------
# Bundle
# ---------------------------------------------------------------------------------------------------------------

def _now():
    t = datetime.datetime.now(datetime.timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (t.microsecond // 1000)


def build_bundle(session_id, rows, reveals, private_key, hashes, exported):
    """
    rows:     the session's ledger rows in seq order, each exactly as FORMATS section 7 (with `hash`)
    reveals:  {seq: (payload_bytes, nonce_bytes)} for rows to reveal; ignored for anything but CLEAN allowed
              attempts (decision "allowed" AND rule None)
    Returns the canonical bundle bytes.

    Why "rule is None" too (PR #4 review, Aayush): in the fake-only modes (single_agent, compromised, two_minds) the
    Gate still runs every check but SENDS anyway and records the rule on the row: that is how a baseline leak is
    counted. Such a row is "allowed" with rule "secret.buyer", and its payload IS the leaked secret. Revealing it would
    print the deal in plain text in a shareable bundle. So only rows where no check fired are ever revealed.
    """
    out_rows = []
    for r in rows:
        r = dict(r)
        clean_allowed = r["row_type"] == "attempt" and r["decision"] == "allowed" and r.get("rule") is None
        if r["seq"] in reveals and clean_allowed:
            payload, nonce = reveals[r["seq"]]
            r["reveal"] = {"payload": bytes(payload).decode("utf-8"), "nonce": bytes(nonce).hex()}
        out_rows.append(r)
    pub = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    bundle = {"v": 1, "format": FORMAT, "session_id": session_id, "exported": exported, "rows": out_rows,
              "head": rows[-1]["hash"] if rows else ZERO_HASH, "code_hashes": hashes, "public_key": pub.hex()}
    bundle["signature"] = sign(private_key, bundle)
    return canonical_json(bundle)


# ---------------------------------------------------------------------------------------------------------------
# Reading the Gate's ledger
# ---------------------------------------------------------------------------------------------------------------

_LEDGER_COLUMNS = {"session_id", "seq", "row_json", "hash", "nonce_priv", "payload_priv"}


class LedgerSchemaError(RuntimeError):
    """The DB does not contain exactly one table with the ledger columns Aayush described."""


def _find_table(con):
    """Name of the one table that has every ledger column. Found by columns, not by name, so it survives a rename;
    zero or several candidates is an error (we never guess which table is the ledger)."""
    found = []
    for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'"):
        cols = {r[1] for r in con.execute("PRAGMA table_info(%s)" % _quote_ident(name))}
        if _LEDGER_COLUMNS <= cols:
            found.append(name)
    if len(found) != 1:
        raise LedgerSchemaError("expected one ledger table with columns %s, found %r"
                                % (sorted(_LEDGER_COLUMNS), found))
    return found[0]


def _quote_ident(name):
    """SQLite identifier quoting (table names cannot be passed as ? parameters)."""
    return '"' + name.replace('"', '""') + '"'


def _as_bytes(v):
    """BLOB -> bytes; TEXT payload -> its UTF-8 bytes."""
    if v is None:
        return None
    if isinstance(v, (bytes, bytearray, memoryview)):
        return bytes(v)
    return v.encode("utf-8")


def _nonce_bytes(v):
    """nonce_priv may be a 32-byte BLOB or 64-char hex TEXT. Anything else is unusable for a reveal (None)."""
    if v is None:
        return None
    if isinstance(v, str):
        try:
            v = bytes.fromhex(v)
        except ValueError:
            return None
    v = bytes(v)
    return v if len(v) == 32 else None


def rows_from_sqlite(db_path, session_id):
    """
    Read one session from the Gate's ledger.

    Returns (rows, reveals):
      rows     the FORMATS section 7 rows in seq order: json.loads(row_json) (which already carries "hash"), with
               "hash" set from the hash column. Hashes are NOT recomputed here: the bundle carries exactly what the
               ledger stored, and the verifier re-checks it, so a ledger row whose content and hash disagree shows up
               as INVALID instead of being silently fixed.
      reveals  {seq: (payload_bytes, nonce_bytes)} for ATTEMPT rows whose private columns are filled. Result rows
               are skipped: their private columns hold the response body, which is never revealed.
    """
    # mode=ro: SQLite refuses any write through this connection. timeout: wait if the Gate is mid-write.
    uri = pathlib.Path(os.path.abspath(db_path)).as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=5.0)
    try:
        table = _find_table(con)
        cur = con.execute("SELECT seq, row_json, hash, nonce_priv, payload_priv FROM %s "
                          "WHERE session_id = ? ORDER BY seq" % _quote_ident(table), (session_id,))
        rows, reveals = [], {}
        for seq, row_json, hsh, nonce_priv, payload_priv in cur:
            row = json.loads(row_json)
            row["hash"] = hsh
            rows.append(row)
            nonce = _nonce_bytes(nonce_priv)
            if row.get("row_type") == "attempt" and nonce is not None and payload_priv is not None:
                reveals[seq] = (_as_bytes(payload_priv), nonce)
        return rows, reveals
    finally:
        con.close()


def export_bundle(session_id, db_path=DEFAULT_DB, reveal="allowed", key_path=DEFAULT_KEY, repo_root=_ROOT):
    """THE FUNCTION THE GATE CALLS for GET /v1/bundle. Returns the signed, canonical bundle bytes; writes no file
    (except the signing key, created once on first use).

    Raises LookupError if the ledger has no rows for session_id (typo'd or never-run session): the caller answers
    404. Without this, an empty bundle (head = 64 zeros) would be signed and verify VALID, i.e. a green VALID on
    stage that proves nothing (PR #4 review #2)."""
    if reveal not in ("allowed", "none"):
        raise ValueError("reveal must be 'allowed' or 'none'")
    rows, private = rows_from_sqlite(db_path, session_id)
    if not rows:
        raise LookupError("no ledger rows for session %r" % session_id)
    reveals = private if reveal == "allowed" else {}      # build_bundle also refuses to reveal blocked attempts
    return build_bundle(session_id, rows, reveals, load_or_create_key(key_path), code_hashes(repo_root), _now())


def export_session(session_id, db_path=DEFAULT_DB, out_dir=DEFAULT_OUT, reveal="allowed", key_path=DEFAULT_KEY,
                   repo_root=_ROOT):
    """export_bundle(), written to <out_dir>/<session_id>.json. Returns the path (for verify.py / tamper.py)."""
    data = export_bundle(session_id, db_path, reveal, key_path, repo_root)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, session_id + ".json")
    with open(path, "wb") as f:
        f.write(data)
    return path


def main(argv):
    import argparse
    p = argparse.ArgumentParser(description="Export a session's ledger as a signed bundle.")
    p.add_argument("session_id")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument("--reveal", default="allowed", choices=("allowed", "none"))
    a = p.parse_args(argv)
    print(export_session(a.session_id, a.db, a.out, a.reveal))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
