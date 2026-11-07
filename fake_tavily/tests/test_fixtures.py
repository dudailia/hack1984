"""The fixture pages must match the recorded demo run in shared/fixtures/demo_events.jsonl."""
import json
import os
import unittest
from urllib.parse import urlsplit

from fake_tavily import pages
from fake_tavily.tests.helpers import DEMO_INSTRUCTION, POISONED_URL

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVENTS = os.path.join(REPO, "shared", "fixtures", "demo_events.jsonl")


def load_events():
    with open(EVENTS, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class FixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = pages.load_pages()
        cls.by_url = {p["url"]: p for p in cls.pages}
        cls.events = load_events()
        cls.fake_sessions = {
            e["session_id"] for e in cls.events
            if e["type"] == "run_started" and e["data"]["source"] == "fake"
        }

    def test_seven_pages_one_poisoned(self):
        self.assertEqual(len(self.pages), 7)
        poisoned = [p for p in self.pages if p.get("poisoned")]
        self.assertEqual([p["url"] for p in poisoned], [POISONED_URL])
        self.assertEqual(poisoned[0]["planted_default"], DEMO_INSTRUCTION)
        self.assertIn(pages.PLANTED_MARKER, poisoned[0]["content"])
        self.assertIn(pages.PLANTED_MARKER, poisoned[0]["raw_content"])

    def test_every_page_is_fictional_and_complete(self):
        for p in self.pages:
            host = urlsplit(p["url"]).hostname
            self.assertRegex(host, r"(^|\.)example\.(com|org|net)$", p["url"])
            for k in ("url", "title", "content", "raw_content"):
                self.assertIsInstance(p[k], str)
                self.assertTrue(p[k].strip())
            self.assertTrue(p["keywords"] or p.get("poisoned"))
            rendered = pages.render(p, DEMO_INSTRUCTION)
            self.assertIn(rendered["content"], rendered["raw_content"])

    def test_docs_read_excerpts_match_fixtures(self):
        docs = [d for e in self.events if e["type"] == "docs_read" for d in e["data"]["docs"]]
        self.assertTrue(docs)
        for d in docs:
            page = self.by_url.get(d["url"])
            self.assertIsNotNone(page, d["url"])
            self.assertEqual(page["title"], d["title"])
            self.assertEqual(pages.render(page, DEMO_INSTRUCTION)["content"], d["excerpt"])
            for h in d["highlights"]:
                self.assertEqual(h["text"], DEMO_INSTRUCTION)

    def test_fake_runs_reproduce_recorded_search_order(self):
        checked = 0
        for e in self.events:
            if e["type"] == "docs_read" and e["session_id"] in self.fake_sessions:
                got = pages.search(self.pages, e["data"]["public_query"], max_results=10)
                self.assertEqual([p["url"] for p in got], [d["url"] for d in e["data"]["docs"]])
                checked += 1
        self.assertGreaterEqual(checked, 3)

    def test_fake_runs_reproduce_recorded_result_counts(self):
        checked = 0
        for e in self.events:
            if e["type"] != "ledger_row" or e["session_id"] not in self.fake_sessions:
                continue
            row, display = e["data"]["row"], e["data"]["display"]
            if row["row_type"] == "result" and display["label"] == "Tavily stand-in search":
                got = pages.search(self.pages, display["query"], max_results=10)
                self.assertEqual(len(got), display["result_count"], display["query"])
                checked += 1
        self.assertGreaterEqual(checked, 4)


if __name__ == "__main__":
    unittest.main()
