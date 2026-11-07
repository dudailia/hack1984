"""
Tests for the public interface: checks.run_all(payload, session, kind) -> {"decision", "rule", "detail"}.

These pin down the CONTRACT with the Gate (shared/FORMATS.md section 6), not how any rule works inside:
  - the result always has exactly those three keys;
  - an ordinary query is allowed with rule None;
  - garbage in is blocked (never "allowed by accident");
  - a broken session makes run_all RAISE, so the Gate fails closed with gate.check_error.
"""

import unittest

from checks import run_all
from checks.tests.helpers import halyard_session, search_body, reader_body


class TestContract(unittest.TestCase):
    def test_result_shape_on_allow(self):
        r = run_all(search_body("payments processing industry revenue growth 2025"), halyard_session(), "search")
        self.assertEqual(set(r), {"decision", "rule", "detail"})
        self.assertEqual(r["decision"], "allow")
        self.assertIsNone(r["rule"])

    def test_result_shape_on_block(self):
        r = run_all(search_body("Ossory Capital Partners offer for Brackwater Payments"), halyard_session(), "search")
        self.assertEqual(set(r), {"decision", "rule", "detail"})
        self.assertEqual(r["decision"], "block")
        # The exact rule id from FORMATS section 3's blocked example: the demo's "careless planner" beat.
        self.assertEqual(r["rule"], "secret.buyer")
        self.assertIsInstance(r["detail"], str)

    def test_detail_never_echoes_the_secret(self):
        # `detail` is shown in the UI and may end up in screenshots: it names the label, not the value.
        r = run_all(search_body("Ossory deal"), halyard_session(), "search")
        self.assertNotIn("ossory", r["detail"].lower())

    def test_not_json_is_blocked(self):
        r = run_all("this is not json", halyard_session(), "search")
        self.assertEqual((r["decision"], r["rule"]), ("block", "shape.bad_payload"))

    def test_json_but_not_an_object_is_blocked(self):
        r = run_all('["payments"]', halyard_session(), "search")
        self.assertEqual((r["decision"], r["rule"]), ("block", "shape.bad_payload"))

    def test_unknown_kind_is_blocked(self):
        r = run_all(search_body("payments growth"), halyard_session(), "telnet")
        self.assertEqual((r["decision"], r["rule"]), ("block", "shape.bad_kind"))

    def test_broken_session_raises_so_gate_fails_closed(self):
        s = halyard_session()
        del s["memo_tokens"]
        with self.assertRaises(Exception):
            run_all(search_body("payments growth"), s, "search")

    def test_leak_rule_wins_over_shape_rule(self):
        # Over budget AND leaking: the ledger should record the leak (more informative), not the budget.
        r = run_all(search_body("Ossory payments"), halyard_session(call_count=10_000), "search")
        self.assertEqual(r["rule"], "secret.buyer")

    def test_clean_reader_job_is_allowed(self):
        docs = [("r_01", "Merchant acquiring revenue grew 7.4% in 2025, according to the survey.")]
        s = halyard_session(public_text_received=[docs[0][1]], queries_sent=["payments growth 2025"])
        r = run_all(reader_body("payments growth 2025", docs), s, "reader")
        self.assertEqual(r["decision"], "allow", r)

    def test_import_needs_only_the_standard_library(self):
        # Aayush's Gate imports `checks` at start-up and REFUSES TO START if that import fails (no silent fallback
        # to the allow-all stub). So `import checks` must work in a bare Python: no cryptography, nothing from pip.
        import subprocess
        import sys
        from checks.tests.helpers import ROOT
        # Count only modules that `import checks` itself ADDS (some Pythons preload site hooks before any code runs).
        code = ("import sys; before = set(sys.modules); import checks; "
                "bad = {m.split('.')[0] for m in set(sys.modules) - before} - set(sys.stdlib_module_names) "
                "- {'checks'}; print(','.join(sorted(bad)))")
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), "")
        self.assertTrue(callable(__import__("checks").run_all))
        self.assertTrue(callable(__import__("checks").memo_tokens))

    def test_reader_job_carrying_a_secret_is_blocked(self):
        # Invariant 3: the Reader never receives the secrets. If one ever got into a reader body, block it.
        docs = [("r_01", "Merchant acquiring revenue grew 7.4% in 2025.")]
        s = halyard_session(public_text_received=[docs[0][1]])
        r = run_all(reader_body("Project Halyard payments", docs), s, "reader")
        self.assertEqual((r["decision"], r["rule"]), ("block", "secret.codename"))


if __name__ == "__main__":
    unittest.main()
