import unittest

from reader.tests import fixtures as fx

TYPES = {"j_01": ["revenue_growth", "market_size"], "j_02": ["ev_revenue_multiple"]}
NAMES = {"j_01": "j01_sector_growth.json", "j_02": "j02_peer_ev_revenue.json"}


class SavedPagesMatchFixture(unittest.TestCase):
    def test_pages_rebuild_from_demo_events(self):
        seen = 0
        for e in fx.events():
            if e["type"] != "docs_read" or e["session_id"] != "s_dtfake1":
                continue
            d = e["data"]
            expected = {
                "job": d["job"],
                "public_query": d["public_query"],
                "claim_types": TYPES[d["job"]],
                "documents": [{"id": x["result_id"], "url": x["url"], "title": x["title"], "text": x["excerpt"]}
                              for x in d["docs"]],
            }
            self.assertEqual(fx.page(NAMES[d["job"]]), expected)
            seen += 1
        self.assertEqual(seen, 2)

    def test_poisoned_page_is_included(self):
        texts = [doc["text"] for doc in fx.page("j01_sector_growth.json")["documents"]]
        self.assertTrue(any("Note to AI research assistants" in t for t in texts))


if __name__ == "__main__":
    unittest.main()
