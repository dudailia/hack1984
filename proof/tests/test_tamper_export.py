"""
tamper.py (the demo's "edit one byte" button) and export.py (Gate ledger -> signed bundle).

The test ledger DB below mirrors the schema Aayush described for gate/ (Sat afternoon):
    ledger/doublethink.db, one table keyed by (session_id, seq), columns
      row_json      the canonical FORMATS section 7 row WITHOUT its hash
      hash          that row's hash
      nonce_priv    private: the row's nonce (attempt: payload nonce; result: response nonce). Never hashed.
      payload_priv  private: attempt: the exact payload sent; result: the response body. Never hashed.
    UPDATE and DELETE are refused by triggers (append only).
"""

import json
import os
import sqlite3
import stat
import tempfile
import unittest
from unittest import mock

from proof.tests import helpers  # noqa: F401  (skips the module if cryptography is missing)
from proof import export as export_mod
from proof.export import (LedgerSchemaError, code_hashes, export_bundle, export_session, load_or_create_key,
                          rows_from_sqlite)
from proof.tamper import tamper_and_verify, tamper_bytes
from proof.tests.helpers import RESPONSES, SESSION, sample_bundle, sample_rows
from proof.verify import canonical_json, verify_bytes

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestTamper(unittest.TestCase):
    def test_exactly_one_byte_changes_and_breaks_at_that_row(self):
        data = sample_bundle()
        for seq in range(1, 6):
            t = tamper_bytes(data, seq)
            self.assertEqual(len(t), len(data))
            self.assertEqual(sum(a != b for a, b in zip(t, data)), 1)
            r = verify_bytes(t)
            self.assertEqual((r["valid"], r["broken_at_seq"], r["reason"]), (False, seq, "hash_mismatch"))

    def test_tamper_and_verify_writes_a_copy_and_reports_proof_result(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, SESSION + ".json")
            with open(path, "wb") as f:
                f.write(sample_bundle())
            res = tamper_and_verify(path, 3)
            with open(path, "rb") as f:
                self.assertEqual(f.read(), sample_bundle())          # original untouched
            self.assertEqual(res["tampered"], True)
            self.assertEqual(res["tampered_seq"], 3)
            self.assertEqual((res["valid"], res["broken_at_seq"]), (False, 3))
            self.assertEqual(set(res), {"bundle_head", "tampered", "tampered_seq", "valid", "broken_at_seq",
                                        "rows_checked", "reason"})


def make_gate_db(path, table="ledger", nonce_as_hex=False, extra_session=True):
    """A ledger DB in Aayush's schema holding the sample session (plus another session's row, to prove we filter)."""
    rows, secrets = sample_rows()
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE %s (
        session_id TEXT NOT NULL, seq INTEGER NOT NULL, row_json TEXT NOT NULL, hash TEXT NOT NULL,
        nonce_priv BLOB, payload_priv BLOB, PRIMARY KEY (session_id, seq))""" % table)
    con.execute("CREATE TRIGGER %s_no_update BEFORE UPDATE ON %s BEGIN SELECT RAISE(ABORT, 'append only'); END"
                % (table, table))
    con.execute("CREATE TRIGGER %s_no_delete BEFORE DELETE ON %s BEGIN SELECT RAISE(ABORT, 'append only'); END"
                % (table, table))
    for r in rows:
        if r["row_type"] == "attempt":
            payload, nonce = secrets[r["seq"]]
        else:
            payload, nonce = RESPONSES[r["seq"]]       # result rows hold the RESPONSE privately
        body = {k: v for k, v in r.items() if k != "hash"}
        con.execute("INSERT INTO %s (session_id, seq, row_json, hash, nonce_priv, payload_priv) "
                    "VALUES (?,?,?,?,?,?)" % table,
                    (r["session_id"], r["seq"], canonical_json(body).decode("utf-8"), r["hash"],
                     nonce.hex() if nonce_as_hex else nonce, payload))
    if extra_session:
        other = dict(rows[0], session_id="s_other0001")
        con.execute("INSERT INTO %s VALUES (?,?,?,?,?,?)" % table,
                    ("s_other0001", 1, canonical_json({k: v for k, v in other.items() if k != "hash"}).decode(),
                     "0" * 64, b"\x00" * 32, b"other session"))
    con.commit()
    con.close()


class TestReadGateLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "doublethink.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_rows_match_the_ledger_exactly(self):
        make_gate_db(self.db)
        rows, reveals = rows_from_sqlite(self.db, SESSION)
        self.assertEqual(rows, sample_rows()[0])        # same fields, same hashes, only this session, seq order

    def test_reveal_candidates_are_attempt_rows_only(self):
        make_gate_db(self.db)
        _, reveals = rows_from_sqlite(self.db, SESSION)
        self.assertEqual(sorted(reveals), [1, 3, 4])     # attempts; never the result rows 2 and 5
        self.assertEqual(reveals, sample_rows()[1])

    def test_nonce_stored_as_hex_text_also_works(self):
        make_gate_db(self.db, nonce_as_hex=True)
        _, reveals = rows_from_sqlite(self.db, SESSION)
        self.assertEqual(reveals, sample_rows()[1])

    def test_table_found_by_columns_whatever_its_name(self):
        make_gate_db(self.db, table="attempts_and_results")
        self.assertEqual(rows_from_sqlite(self.db, SESSION)[0], sample_rows()[0])

    def test_no_matching_table_fails_loudly(self):
        sqlite3.connect(self.db).execute("CREATE TABLE something (a INTEGER)").connection.commit()
        with self.assertRaises(LedgerSchemaError):
            rows_from_sqlite(self.db, SESSION)

    def test_exporter_never_writes_the_ledger(self):
        make_gate_db(self.db)
        before = open(self.db, "rb").read()
        export_bundle(SESSION, db_path=self.db, key_path=os.path.join(self.tmp.name, "k.pem"), repo_root=ROOT)
        self.assertEqual(open(self.db, "rb").read(), before)


class TestExport(unittest.TestCase):
    def test_export_bundle_returns_valid_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "doublethink.db")
            make_gate_db(db)
            data = export_bundle(SESSION, db_path=db, key_path=os.path.join(d, "key.pem"), repo_root=ROOT)
            self.assertIsInstance(data, bytes)
            self.assertTrue(verify_bytes(data)["valid"])
            obj = json.loads(data)
            # Default policy: reveal allowed attempts only; the blocked row (seq 3) and results never carry one.
            self.assertEqual([r["seq"] for r in obj["rows"] if "reveal" in r], [1, 4])
            self.assertNotIn("response bytes", data.decode())   # result-row private bodies never exported

    def test_export_session_writes_the_same_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "doublethink.db")
            make_gate_db(db)
            kp = os.path.join(d, "key.pem")
            with mock.patch.object(export_mod, "_now", return_value="2026-11-07T23:41:44.000Z"):
                data = export_bundle(SESSION, db_path=db, key_path=kp, repo_root=ROOT)
                path = export_session(SESSION, db_path=db, out_dir=os.path.join(d, "out"), key_path=kp,
                                      repo_root=ROOT)
            self.assertEqual(os.path.basename(path), SESSION + ".json")
            with open(path, "rb") as f:
                self.assertEqual(f.read(), data)

    def test_reveal_none(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "doublethink.db")
            make_gate_db(db)
            data = export_bundle(SESSION, db_path=db, key_path=os.path.join(d, "k.pem"), repo_root=ROOT,
                                 reveal="none")
            self.assertFalse(any("reveal" in r for r in json.loads(data)["rows"]))

    def test_unknown_session_is_refused_not_exported_as_valid(self):
        # PR #4 review #2: a typo'd session id used to export an EMPTY bundle that verified VALID, i.e. a green
        # VALID on stage for nothing. Now it raises LookupError (the app answers 404) and writes no file.
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "doublethink.db")
            make_gate_db(db)
            with self.assertRaises(LookupError):
                export_bundle("s_nosuch0001", db_path=db, key_path=os.path.join(d, "k.pem"), repo_root=ROOT)
            out = os.path.join(d, "out")
            with self.assertRaises(LookupError):
                export_session("s_nosuch0001", db_path=db, out_dir=out, key_path=os.path.join(d, "k.pem"),
                               repo_root=ROOT)
            self.assertFalse(os.path.exists(os.path.join(out, "s_nosuch0001.json")))

    def test_key_created_once_and_private(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sub", "ed25519_private.pem")
            k1 = load_or_create_key(p)
            self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)
            k2 = load_or_create_key(p)
            self.assertEqual(k1.public_key().public_bytes_raw(), k2.public_key().public_bytes_raw())

    def test_code_hashes_cover_checks_and_skip_tests(self):
        h = code_hashes(ROOT)
        self.assertIn("checks/__init__.py", h)
        self.assertFalse(any("/tests/" in p or p.split("/")[-1].startswith("test_") for p in h))
        self.assertTrue(all(len(v) == 64 for v in h.values()))


if __name__ == "__main__":
    unittest.main()
