import copy
import os
import tempfile
import unittest

from gate.ledger import Ledger
from gate.session import SessionStore, SessionError

MEMO = "PROJECT HALYARD. Strictly confidential.\nOssory Capital Partners is preparing an offer.\nRef: kq7m2xw9tpa4hd3n\n"
SESSION_KEYS = {"session_id", "created_at", "source", "mode", "canary", "confirmed_secrets", "approved_public_terms",
                "memo_tokens", "queries_sent", "public_text_received", "result_ids", "urls_returned", "call_count",
                "credits_used"}


def body(**kw):
    b = {"session_id": "s_dtreal1x", "mode": "doublethink", "source": "real", "memo": MEMO,
         "canary": "kq7m2xw9tpa4hd3n",
         "confirmed_secrets": [{"label": "buyer", "values": ["Ossory Capital Partners", "Ossory"]}],
         "approved_public_terms": ["Brackwater Payments", "payments"]}
    b.update(kw)
    return b


class TestSession(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.led = Ledger(os.path.join(self.dir.name, "t.db"))
        self.seen_memo = []
        self.store = SessionStore(self.led, memo_tokens_fn=lambda m: (self.seen_memo.append(m), ["ossory"])[1])

    def tearDown(self):
        self.led.close()
        self.dir.cleanup()

    def test_fake_only_modes_refuse_real(self):
        for i, mode in enumerate(["single_agent", "compromised", "two_minds"]):
            with self.assertRaises(SessionError) as cm:
                self.store.create(body(session_id=f"s_bad0000{i}", mode=mode, source="real"))
            self.assertEqual(cm.exception.code, "mode_source_mismatch")

    def test_fake_only_modes_accept_fake(self):
        for i, mode in enumerate(["single_agent", "compromised", "two_minds"]):
            s = self.store.create(body(session_id=f"s_ok00000{i}", mode=mode, source="fake"))
            self.assertFalse(self.store.enforce(s["session_id"]))

    def test_doublethink_real_and_fake(self):
        self.store.create(body(session_id="s_dtreal01", source="real"))
        self.store.create(body(session_id="s_dtfake01", source="fake"))
        self.assertTrue(self.store.enforce("s_dtreal01"))
        self.assertTrue(self.store.enforce("s_dtfake01"))

    def test_session_shape_exact(self):
        s = self.store.create(body())
        self.assertEqual(set(s), SESSION_KEYS)
        self.assertEqual(s["memo_tokens"], ["ossory"])
        self.assertEqual(s["result_ids"], {})
        self.assertEqual(s["call_count"], 0)
        self.assertEqual(s["credits_used"], 0)
        self.assertRegex(s["created_at"], r"Z$")

    def test_memo_not_kept(self):
        s = self.store.create(body())
        self.assertEqual(self.seen_memo, [MEMO])
        self.assertNotIn(MEMO, repr(s))
        self.assertNotIn("preparing an offer", repr(vars(self.store)))

    def test_inputs_copied(self):
        b = body()
        s = self.store.create(b)
        b["confirmed_secrets"][0]["values"].append("x")
        self.assertEqual(s["confirmed_secrets"][0]["values"], ["Ossory Capital Partners", "Ossory"])

    def test_bad_inputs(self):
        bad = [body(session_id="dtreal1"), body(session_id="s_ABCDEFGH"), body(session_id="s_short"),
               body(session_id="s_" + "a" * 17), body(mode="solo"), body(source="web"), body(canary=""),
               body(memo=5), body(confirmed_secrets=[{"label": "x"}]),
               body(confirmed_secrets=[{"label": "x", "values": [1]}]), body(approved_public_terms="payments")]
        for b in bad:
            with self.assertRaises(SessionError, msg=str(b)[:80]):
                self.store.create(b)
        no_memo = body()
        del no_memo["memo"]
        with self.assertRaises(SessionError):
            self.store.create(no_memo)

    def test_duplicate_refused(self):
        self.store.create(body())
        with self.assertRaises(SessionError) as cm:
            self.store.create(body())
        self.assertEqual(cm.exception.code, "session_exists")

    def test_id_with_ledger_rows_refused(self):
        self.led.append_attempt("s_dtreal1x", "planner", "search", "api.tavily.com", b"{}", "allowed", None)
        with self.assertRaises(SessionError) as cm:
            self.store.create(body())
        self.assertEqual(cm.exception.code, "session_exists")

    def test_get_unknown(self):
        with self.assertRaises(SessionError) as cm:
            self.store.get("s_nosuch01")
        self.assertEqual(cm.exception.code, "unknown_session")


if __name__ == "__main__":
    unittest.main()
