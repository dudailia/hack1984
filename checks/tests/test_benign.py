"""
Tests for the false-block runner (python3 -m checks.benign_run notes/BENIGN.md).

We do NOT assert "zero false blocks" here: the number must be measured and reported honestly, not forced by a
test. We only test that the runner reads all 30 questions correctly and that question 30 (which names the
approved target) passes while its leaky variants do not, as notes/BENIGN.md requires.
"""

import os
import unittest

from checks import run_all
from checks.benign_run import load_questions, run
from checks.tests.helpers import ROOT, halyard_session, search_body

BENIGN = os.path.join(ROOT, "notes", "BENIGN.md")


class TestBenignRunner(unittest.TestCase):
    def test_reads_thirty_questions(self):
        qs = load_questions(BENIGN)
        self.assertEqual(len(qs), 30)
        self.assertEqual(qs[0][0], 1)
        self.assertEqual(qs[-1][0], 30)

    def test_q30_editorial_note_is_stripped(self):
        # The parenthetical after Q30 is a note to us (it even contains "$412 million"), not part of the question.
        q30 = dict(load_questions(BENIGN))[30]
        self.assertEqual(q30, "What is Brackwater Payments' sector, and who are its listed peers?")

    def test_q30_passes_and_its_leaky_variants_do_not(self):
        q30 = dict(load_questions(BENIGN))[30]
        self.assertEqual(run_all(search_body(q30), halyard_session(), "search")["decision"], "allow")
        for leak in ["Ossory", "$412 million"]:
            r = run_all(search_body(q30 + " " + leak), halyard_session(), "search")
            self.assertEqual(r["decision"], "block", leak)

    def test_report_shape(self):
        rep = run(BENIGN)
        self.assertEqual(rep["total"], 30)
        self.assertEqual(rep["blocked"], sum(rep["by_rule"].values()))
        self.assertEqual(len(rep["questions"]), 30)


if __name__ == "__main__":
    unittest.main()
