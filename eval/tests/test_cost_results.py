import json
import os
import tempfile
import unittest

from eval import cost, results


def rec(n, credits, seconds, done=True):
    return {"n": n, "question": "q%d" % n, "credits": credits, "seconds": seconds, "blocked": 0,
            "outcome": "answered" if done else None, "run_done": done, "error": None if done else "timeout"}


class Cost(unittest.TestCase):
    def test_summary_over_completed_runs_only(self):
        s = cost.summarise([rec(1, 2, 10.0), rec(2, 4, 20.0), rec(3, None, 300.0, done=False)])
        self.assertEqual(cost.cost_fields(s), {"tavily_credits_per_question": 3.0, "seconds_per_question": 15.0})
        self.assertEqual(s["completed"], 2)
        self.assertEqual(s["questions"], 3)
        self.assertEqual(s["credits"]["total"], 6)
        self.assertEqual(s["seconds"]["max"], 20.0)

    def test_no_completed_runs_gives_null_not_zero(self):
        s = cost.summarise([rec(1, None, 5.0, done=False)])
        self.assertEqual(cost.cost_fields(s), {"tavily_credits_per_question": None, "seconds_per_question": None})

    def test_cli_reads_details_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "20261107T230000Z.json")
            with open(p, "w") as f:
                json.dump({"records": [rec(1, 2, 10.0), rec(2, 1, 4.0)]}, f)
            self.assertEqual(cost.latest_details(d), p)
            self.assertEqual(cost.summarise(cost.load_records(p))["tavily_credits_per_question"], 1.5)

    def test_table_mentions_every_question(self):
        recs = [rec(1, 2, 10.0), rec(2, None, 3.0, done=False)]
        t = cost.format_table(recs, cost.summarise(recs))
        self.assertIn("q1", t)
        self.assertIn("q2", t)
        self.assertIn("completed runs: 1 of 2", t)


class Results(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "results.json")
        self.run = results.make_run("usefulness", "abc1234", "qwen3:8b", "real", "cmd",
                                    {"answered_with_cited_number": 1, "total": 30},
                                    {"tavily_credits_per_question": 2.0, "seconds_per_question": 9.5})

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_file_header_uses_registered_hash(self):
        doc = results.append_run(self.path, self.run, "2026-11-07T23:00:00.000Z")
        self.assertEqual(doc["attack_file_sha256"],
                         "961d23204616ac8cd91b303bd847029e9db84ca3a5f73c379fea20333c41d1be")
        self.assertEqual(doc["attacks_total"], 40)
        self.assertIs(doc["example"], False)
        self.assertEqual(doc["runs"], [self.run])
        with open(self.path) as f:
            self.assertEqual(json.load(f), doc)

    def test_refuses_example_file(self):
        with open(os.path.join(results.REPO, "shared", "fixtures", "results_example.json")) as f:
            example = f.read()
        with open(self.path, "w") as f:
            f.write(example)
        with self.assertRaises(results.RefusedError):
            results.append_run(self.path, self.run)
        with open(self.path) as f:
            self.assertEqual(f.read(), example)

    def test_refuses_non_json_and_non_v1(self):
        for content in ("not json", json.dumps({"v": 2, "example": False, "runs": []})):
            with open(self.path, "w") as f:
                f.write(content)
            with self.assertRaises(results.RefusedError):
                results.append_run(self.path, self.run)

    def test_never_writes_modes_or_false_blocks(self):
        bad = dict(self.run, false_blocks={"blocked": 0, "total": 30})
        with self.assertRaises(results.RefusedError):
            results.append_run(self.path, bad)
        bad = dict(self.run, modes={})
        with self.assertRaises(results.RefusedError):
            results.append_run(self.path, bad)
        self.assertFalse(os.path.exists(self.path))

    def test_make_run_rejects_extra_fields(self):
        with self.assertRaises(ValueError):
            results.make_run("l", "c", "m", "real", "cmd", {"answered_with_cited_number": 1, "total": 1, "x": 1},
                             {"tavily_credits_per_question": 1, "seconds_per_question": 1})


if __name__ == "__main__":
    unittest.main()
