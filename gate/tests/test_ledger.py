import json
import os
import shutil
import sqlite3
import tempfile
import threading
import unittest

from gate import canonical as c
from gate.ledger import Ledger, LedgerError
from gate.tests.test_canonical import ATTEMPT_HASH, RESULT_HASH, PAYLOAD, ATTEMPT_COMMIT, RESP_COMMIT

ATTEMPT_KEYS = {"seq", "time", "session_id", "row_type", "component", "kind", "destination", "commitment",
                "bytes", "decision", "rule", "prev_hash", "hash"}
RESULT_KEYS = {"seq", "time", "session_id", "row_type", "attempt_seq", "status", "http_status", "credits_used",
               "response_commitment", "prev_hash", "hash"}


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "t.db")
        self.led = Ledger(self.path)

    def tearDown(self):
        self.led.close()
        self.dir.cleanup()

    def attempt(self, sid="s_test0001", decision="allowed", rule=None, payload=b"{}"):
        return self.led.append_attempt(sid, "planner", "search", "api.tavily.com", payload, decision, rule)


class TestVectorsThroughLedger(Base):
    def test_reproduces_section7_hashes(self):
        nonces = iter([b"\x11" * 32, b"\x22" * 32])
        times = iter(["2026-11-07T23:41:07.500Z", "2026-11-07T23:41:08.700Z"])
        led = Ledger(os.path.join(self.dir.name, "v.db"), nonce_fn=lambda: next(nonces), time_fn=lambda: next(times))
        a = led.append_attempt("s_dtreal1", "planner", "search", "api.tavily.com", PAYLOAD, "allowed", None)
        r = led.append_result("s_dtreal1", 1, "sent", 200, 1, b'{"example":"response bytes"}')
        self.assertEqual(a["commitment"], ATTEMPT_COMMIT)
        self.assertEqual(a["hash"], ATTEMPT_HASH)
        self.assertEqual(r["response_commitment"], RESP_COMMIT)
        self.assertEqual(r["hash"], RESULT_HASH)
        led.close()


class TestRowShape(Base):
    def test_attempt_keys_exact_with_nulls(self):
        a = self.attempt()
        self.assertEqual(set(a), ATTEMPT_KEYS)
        self.assertIsNone(a["rule"])
        self.assertEqual(a["prev_hash"], c.ZERO_HASH)
        self.assertEqual(a["bytes"], 2)

    def test_result_keys_exact_with_nulls(self):
        self.attempt()
        r = self.led.append_result("s_test0001", 1, "error", None, None, b"")
        self.assertEqual(set(r), RESULT_KEYS)
        self.assertIsNone(r["http_status"])
        self.assertIsNone(r["credits_used"])

    def test_stored_rows_match_returned(self):
        a = self.attempt()
        r = self.led.append_result("s_test0001", 1, "sent", 200, 1, b"x")
        self.assertEqual(self.led.rows("s_test0001"), [a, r])

    def test_bad_enums_refused(self):
        with self.assertRaises(LedgerError):
            self.attempt(decision="maybe")
        with self.assertRaises(LedgerError):
            self.led.append_attempt("s_test0001", "planner", "telnet", "api.tavily.com", b"", "allowed", None)
        with self.assertRaises(LedgerError):
            self.led.append_attempt("s_test0001", "planner", "search", "api.tavily.com", "str", "allowed", None)


class TestChain(Base):
    def test_seq_no_gaps_per_session(self):
        self.attempt()
        self.led.append_result("s_test0001", 1, "sent", 200, 1, b"")
        self.attempt(decision="blocked", rule="secret.buyer")
        self.attempt(sid="s_other0001")
        self.attempt()
        self.assertEqual([r["seq"] for r in self.led.rows("s_test0001")], [1, 2, 3, 4])
        self.assertEqual([r["seq"] for r in self.led.rows("s_other0001")], [1])

    def test_prev_hash_links_and_verifies(self):
        self.attempt()
        self.led.append_result("s_test0001", 1, "sent", 200, 1, b"")
        self.attempt(decision="blocked", rule="canary")
        rows = self.led.rows("s_test0001")
        self.assertEqual(rows[1]["prev_hash"], rows[0]["hash"])
        self.assertEqual(rows[2]["prev_hash"], rows[1]["hash"])
        self.assertTrue(self.led.verify_chain("s_test0001"))

    def test_tamper_detected(self):
        self.attempt()
        self.attempt()
        self.led.close()
        copy = os.path.join(self.dir.name, "copy.db")
        shutil.copy(self.path, copy)
        con = sqlite3.connect(copy)
        con.execute("DROP TRIGGER ledger_no_update")
        row = json.loads(con.execute("SELECT row_json FROM ledger WHERE seq=1").fetchone()[0])
        row["bytes"] = 3
        con.execute("UPDATE ledger SET row_json=? WHERE seq=1", (c.canonical_json(row),))
        con.commit()
        con.close()
        tampered = Ledger(copy)
        self.assertFalse(tampered.verify_chain("s_test0001"))
        tampered.close()
        self.led = Ledger(self.path)

    def test_concurrent_appends(self):
        errors = []

        def work():
            try:
                self.attempt()
            except Exception as e:  # pragma: no cover
                errors.append(e)

        ts = [threading.Thread(target=work) for _ in range(20)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual([r["seq"] for r in self.led.rows("s_test0001")], list(range(1, 21)))
        self.assertTrue(self.led.verify_chain("s_test0001"))


class TestAppendOnly(Base):
    def test_update_refused(self):
        self.attempt()
        con = sqlite3.connect(self.path)
        with self.assertRaises(sqlite3.DatabaseError):
            con.execute("UPDATE ledger SET hash='x'")
        con.close()

    def test_delete_refused(self):
        self.attempt()
        con = sqlite3.connect(self.path)
        with self.assertRaises(sqlite3.DatabaseError):
            con.execute("DELETE FROM ledger")
        con.close()
        self.assertEqual(len(self.led.rows("s_test0001")), 1)


class TestPrivateColumns(Base):
    def test_nonce_and_payload_private(self):
        a = self.attempt(payload=b'{"query":"hello world"}')
        con = sqlite3.connect(self.path)
        row_json, nonce, payload = con.execute(
            "SELECT row_json, nonce_priv, payload_priv FROM ledger WHERE seq=1").fetchone()
        con.close()
        self.assertEqual(bytes(payload), b'{"query":"hello world"}')
        self.assertEqual(len(nonce), 32)
        self.assertNotIn(b"hello world", bytes(row_json))
        self.assertNotIn(bytes(nonce).hex().encode(), bytes(row_json))
        self.assertEqual(c.commitment(bytes(nonce), bytes(payload)), a["commitment"])

    def test_fresh_nonce_per_row(self):
        a1 = self.attempt()
        a2 = self.attempt()
        self.assertNotEqual(a1["commitment"], a2["commitment"])

    def test_private_reveal_accessor(self):
        a = self.attempt(payload=b"abc")
        nonce, payload = self.led.private("s_test0001", a["seq"])
        self.assertEqual(c.commitment(nonce, payload), a["commitment"])


class TestResultRules(Base):
    def test_result_on_blocked_refused(self):
        self.attempt(decision="blocked", rule="canary")
        with self.assertRaises(LedgerError):
            self.led.append_result("s_test0001", 1, "sent", 200, 1, b"")

    def test_second_result_refused(self):
        self.attempt()
        self.led.append_result("s_test0001", 1, "sent", 200, 1, b"")
        with self.assertRaises(LedgerError):
            self.led.append_result("s_test0001", 1, "sent", 200, 1, b"")

    def test_result_on_missing_or_result_row_refused(self):
        with self.assertRaises(LedgerError):
            self.led.append_result("s_test0001", 1, "sent", 200, 1, b"")
        self.attempt()
        self.led.append_result("s_test0001", 1, "sent", 200, 1, b"")
        with self.assertRaises(LedgerError):
            self.led.append_result("s_test0001", 2, "sent", 200, 1, b"")

    def test_has_session(self):
        self.assertFalse(self.led.has_session("s_test0001"))
        self.attempt()
        self.assertTrue(self.led.has_session("s_test0001"))


if __name__ == "__main__":
    unittest.main()
