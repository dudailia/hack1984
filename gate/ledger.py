"""Append-only, hash-chained SQLite ledger (shared/FORMATS.md §7).

The hashed row is built only from the §7 fields. Nonces and payloads live in private columns that are never
part of row_json, so the chain covers commitments, never payloads. Triggers refuse UPDATE and DELETE.
"""
import json
import os
import sqlite3
import threading

from gate import canonical as c

DEFAULT_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ledger", "doublethink.db")

COMPONENTS = {"planner", "reader", "baseline"}
KINDS = {"search", "extract", "reader"}
DECISIONS = {"allowed", "blocked"}
STATUSES = {"sent", "error"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger (
    session_id   TEXT    NOT NULL,
    seq          INTEGER NOT NULL,
    row_type     TEXT    NOT NULL,
    row_json     BLOB    NOT NULL,
    hash         TEXT    NOT NULL,
    nonce_priv   BLOB    NOT NULL,
    payload_priv BLOB    NOT NULL,
    PRIMARY KEY (session_id, seq)
);
CREATE TRIGGER IF NOT EXISTS ledger_seq_next BEFORE INSERT ON ledger
WHEN NEW.seq != (SELECT COALESCE(MAX(seq), 0) + 1 FROM ledger WHERE session_id = NEW.session_id)
BEGIN SELECT RAISE(ABORT, 'ledger seq must be max+1 (no gaps, no replace)'); END;
CREATE TRIGGER IF NOT EXISTS ledger_no_update BEFORE UPDATE ON ledger
BEGIN SELECT RAISE(ABORT, 'ledger is append only'); END;
CREATE TRIGGER IF NOT EXISTS ledger_no_delete BEFORE DELETE ON ledger
BEGIN SELECT RAISE(ABORT, 'ledger is append only'); END;
"""


class LedgerError(Exception):
    pass


class Ledger:
    def __init__(self, path=DEFAULT_DB, nonce_fn=c.new_nonce, time_fn=c.utc_now):
        if os.path.abspath(path) == DEFAULT_DB:
            os.makedirs(os.path.dirname(DEFAULT_DB), exist_ok=True)
        self._con = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._con.executescript(SCHEMA)
        self._lock = threading.Lock()
        self._nonce_fn = nonce_fn
        self._time_fn = time_fn

    def close(self):
        self._con.close()

    # -- writing ---------------------------------------------------------
    def _append(self, session_id, build, payload: bytes):
        """build(seq, prev_hash, nonce) -> row without hash. Runs inside one write transaction."""
        with self._lock:
            cur = self._con.cursor()
            cur.execute("BEGIN IMMEDIATE")
            try:
                last = cur.execute("SELECT seq, hash FROM ledger WHERE session_id=? ORDER BY seq DESC LIMIT 1",
                                   (session_id,)).fetchone()
                seq, prev = (last[0] + 1, last[1]) if last else (1, c.ZERO_HASH)
                nonce = self._nonce_fn()
                row = build(cur, seq, prev, nonce)
                row["hash"] = c.row_hash(row)
                cur.execute("INSERT INTO ledger VALUES (?,?,?,?,?,?,?)",
                            (session_id, seq, row["row_type"], c.canonical_json(row), row["hash"], nonce, payload))
                cur.execute("COMMIT")
            except BaseException:
                cur.execute("ROLLBACK")
                raise
            return row

    def append_attempt(self, session_id, component, kind, destination, payload, decision, rule):
        if component not in COMPONENTS or kind not in KINDS or decision not in DECISIONS:
            raise LedgerError("bad component, kind or decision")
        if not isinstance(payload, bytes):
            raise LedgerError("payload must be bytes")
        if rule is not None and not isinstance(rule, str):
            raise LedgerError("rule must be a string or None")

        def build(cur, seq, prev, nonce):
            return {"seq": seq, "time": self._time_fn(), "session_id": session_id, "row_type": "attempt",
                    "component": component, "kind": kind, "destination": destination,
                    "commitment": c.commitment(nonce, payload), "bytes": len(payload), "decision": decision,
                    "rule": rule, "prev_hash": prev}

        return self._append(session_id, build, payload)

    def append_result(self, session_id, attempt_seq, status, http_status, credits_used, response_bytes):
        if status not in STATUSES:
            raise LedgerError("bad status")
        if not isinstance(response_bytes, bytes):
            raise LedgerError("response must be bytes")
        for v in (http_status, credits_used):
            if v is not None and (not isinstance(v, int) or isinstance(v, bool)):
                raise LedgerError("http_status and credits_used must be int or None")

        def build(cur, seq, prev, nonce):
            att = cur.execute("SELECT row_type, row_json FROM ledger WHERE session_id=? AND seq=?",
                              (session_id, attempt_seq)).fetchone()
            if att is None or att[0] != "attempt":
                raise LedgerError("attempt_seq is not an attempt in this session")
            if json.loads(att[1])["decision"] != "allowed":
                raise LedgerError("blocked attempts never get a result row")
            for (rj,) in cur.execute("SELECT row_json FROM ledger WHERE session_id=? AND row_type='result'",
                                     (session_id,)):
                if json.loads(rj)["attempt_seq"] == attempt_seq:
                    raise LedgerError("attempt already has a result row")
            return {"seq": seq, "time": self._time_fn(), "session_id": session_id, "row_type": "result",
                    "attempt_seq": attempt_seq, "status": status, "http_status": http_status,
                    "credits_used": credits_used, "response_commitment": c.commitment(nonce, response_bytes),
                    "prev_hash": prev}

        return self._append(session_id, build, response_bytes)

    # -- reading ---------------------------------------------------------
    def rows(self, session_id):
        with self._lock:
            got = self._con.execute("SELECT row_json FROM ledger WHERE session_id=? ORDER BY seq",
                                    (session_id,)).fetchall()
        return [json.loads(r[0]) for r in got]

    def private(self, session_id, seq):
        """(nonce, payload) for one row. For the local bundle exporter only."""
        with self._lock:
            got = self._con.execute("SELECT nonce_priv, payload_priv FROM ledger WHERE session_id=? AND seq=?",
                                    (session_id, seq)).fetchone()
        if got is None:
            raise LedgerError("no such row")
        return bytes(got[0]), bytes(got[1])

    def has_session(self, session_id):
        with self._lock:
            return self._con.execute("SELECT 1 FROM ledger WHERE session_id=? LIMIT 1",
                                     (session_id,)).fetchone() is not None

    def verify_chain(self, session_id):
        prev = c.ZERO_HASH
        for i, row in enumerate(self.rows(session_id), start=1):
            if row.get("seq") != i or row.get("session_id") != session_id or row.get("prev_hash") != prev:
                return False
            if c.row_hash(row) != row.get("hash"):
                return False
            prev = row["hash"]
        return True
