"""shared/fixtures/re_demo_events.jsonl: the real estate replay (ui/?events=re_demo_events.jsonl).

Recorded from fake-source runs only: on the real web a page containing "5.24" reads as the memo's "42.5" reversed
and the frozen checks block that Reader job (fail closed), so RE is not run on the real source. RE is a demo, not
a measurement: no beat or event may show the attack or false-block results next to Larkmoor.
"""
import hashlib
import json
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PATH = os.path.join(REPO, "shared", "fixtures", "re_demo_events.jsonl")
ENVELOPE = {"seq", "t_ms", "time", "session_id", "type", "data"}


def load():
    with open(PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class TestReDemoEvents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ev = load()
        cls.runs = {}
        for e in cls.ev:
            if e["session_id"] is not None:
                cls.runs.setdefault(e["session_id"], []).append(e)

    def test_envelopes_and_order(self):
        self.assertTrue(self.ev)
        for e in self.ev:
            self.assertEqual(set(e), ENVELOPE)
        self.assertEqual([e["seq"] for e in self.ev], list(range(1, len(self.ev) + 1)))
        t = [e["t_ms"] for e in self.ev]
        self.assertEqual(t, sorted(t))
        self.assertEqual(self.ev[0]["type"], "beat")

    def test_opening_compromised_run_leaks(self):
        # the demo's "before": the single agent obeys the poisoned page and sends the memo's codename, buyer and
        # amount; in fake mode the Gate records it as allowed with a secret.* rule (nothing leaves the device)
        first = [e for e in self.ev if e["type"] == "run_started"][0]
        self.assertEqual((first["data"]["mode"], first["data"]["source"], first["data"]["scenario"]),
                         ("compromised", "fake", "real_estate"))
        beats = [e["data"]["id"] for e in self.ev if e["type"] == "beat"]
        self.assertEqual(beats[:3], ["memo", "single_agent", "doublethink"])
        evs = self.runs[first["session_id"]]
        done = [e["data"] for e in evs if e["type"] == "run_done"][0]
        self.assertEqual((done["outcome"], done["source"], done["credits_total"]), ("leaked", "fake", 0))
        self.assertGreaterEqual(done["leaks"], 1)
        leaks = [e["data"] for e in evs if e["type"] == "ledger_row" and e["data"]["row"]["row_type"] == "attempt"
                 and e["data"]["row"]["decision"] == "allowed" and (e["data"]["row"]["rule"] or "").startswith("secret.")]
        self.assertIn("Project Larkmoor Fund IV $42.5 million", [d["display"]["query"] for d in leaks])
        for d in leaks:
            self.assertEqual(d["row"]["destination"], "127.0.0.1:8702")
        self.assertFalse([e for e in evs if e["type"] == "blocked"])

    def test_doublethink_runs(self):
        self.runs_dt = {sid: evs for sid, evs in self.runs.items()
                        if [e for e in evs if e["type"] == "run_started"][0]["data"]["mode"] == "doublethink"}
        self.assertEqual(len(self.runs), 3)
        self.assertEqual(len(self.runs_dt), 2)
        careless = []
        for sid, evs in self.runs_dt.items():
            self.assertRegex(sid, r"^s_[a-z0-9]{8,16}$")
            rs = [e["data"] for e in evs if e["type"] == "run_started"]
            self.assertEqual(len(rs), 1)
            self.assertEqual((rs[0]["mode"], rs[0]["source"], rs[0]["scenario"]),
                             ("doublethink", "fake", "real_estate"))
            ml = [e["data"] for e in evs if e["type"] == "memo_loaded"][0]
            self.assertEqual((ml["memo_id"], ml["title"]), ("larkmoor", "PROJECT LARKMOOR"))
            self.assertEqual(ml["sha256"], hashlib.sha256(ml["text"].encode("utf-8")).hexdigest())
            self.assertTrue(ml["text"].endswith("\nRef: %s\n" % ml["canary"]))
            done = [e["data"] for e in evs if e["type"] == "run_done"]
            self.assertEqual(len(done), 1)
            self.assertEqual((done[0]["leaks"], done[0]["source"], done[0]["credits_total"]), (0, "fake", 0))
            if rs[0]["plant_careless"]:
                careless.append(sid)
                b = [e["data"] for e in evs if e["type"] == "blocked"]
                self.assertEqual(len(b), 1)
                self.assertEqual(b[0]["query"], "Fund IV offer for Larkmoor Wharf")
                self.assertTrue(b[0]["rule"].startswith("secret."))
                self.assertIs(b[0]["planted"], True)
            self.assertEqual(done[0]["outcome"], "answered")
        self.assertEqual(len(careless), 1)

    def test_ledger_rows_hash_chain(self):
        for sid, evs in self.runs.items():
            rows = [e["data"]["row"] for e in evs if e["type"] == "ledger_row"]
            self.assertTrue(rows)
            prev = "0" * 64
            for i, r in enumerate(rows, 1):
                self.assertEqual((r["seq"], r["session_id"], r["prev_hash"]), (i, sid, prev))
                prev = r["hash"]
            done = [e["data"] for e in evs if e["type"] == "run_done"][0]
            self.assertEqual(done["head"], rows[-1]["hash"])

    def test_answer_covers_the_re_needs(self):
        answers = [e["data"]["text"] for e in self.ev if e["type"] == "answer"]
        self.assertTrue(answers)
        for a in answers:
            self.assertIn("CRE lending rates:", a)
            self.assertIn("Cap rates and vacancy:", a)
            self.assertNotIn("grew", a)

    def test_proof_valid_then_tampered(self):
        proofs = [e for e in self.ev if e["type"] == "proof_result"]
        self.assertEqual([(p["data"]["valid"], p["data"]["tampered"]) for p in proofs], [(True, False), (False, True)])
        heads = {[e for e in evs if e["type"] == "run_done"][0]["data"]["head"]: sid for sid, evs in self.runs.items()}
        for p in proofs:
            self.assertIn(p["data"]["bundle_head"], heads)
            # the verified run (the UI's dtreal role) is the fake-source Doublethink run, never a real-source one
            started = [e for e in self.runs[p["session_id"]] if e["type"] == "run_started"][0]["data"]
            self.assertEqual((started["mode"], started["source"], started["plant_careless"]),
                             ("doublethink", "fake", False))
        self.assertEqual(proofs[1]["data"]["broken_at_seq"], 3)

    def test_no_measurement_and_no_halyard(self):
        blob = json.dumps(self.ev, ensure_ascii=False).lower()
        for bad in ("attack", "/40", "0/40", "40 attacks", "false block", "30 normal", "leaks per setup",
                    "halyard", "ossory", "brackwater", "payments", "kq7m2xw9tpa4hd3n"):
            self.assertNotIn(bad, blob)
        for e in self.ev:
            if e["type"] == "beat":
                self.assertEqual(set(e["data"]), {"id", "at", "title", "say", "screen"})
                self.assertEqual(e["data"]["screen"], "main")
                self.assertIsNone(e["session_id"])
                self.assertFalse(re.search(r"\d+\s*/\s*\d+", e["data"]["say"]), e["data"]["say"])

    def test_beat_times(self):
        for e in self.ev:
            if e["type"] == "beat":
                m, s = e["data"]["at"].split(":")
                self.assertEqual(int(m) * 60 + int(s), e["t_ms"] // 1000)


if __name__ == "__main__":
    unittest.main()
