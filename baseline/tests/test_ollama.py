"""Ollama request matches FORMATS §2; actions are validated in code."""
import datetime
import unittest

from baseline import ollama
from baseline.tests.stubs import StubOllama

NEEDS = ["sector_growth", "peer_ev_revenue"]


class BuildRequestTest(unittest.TestCase):
    def test_shape(self):
        req = ollama.build_request("qwen3:8b", datetime.date(2026, 11, 7), "SYS", "USER")
        self.assertEqual(set(req), {"model", "think", "stream", "format", "options", "messages"})
        self.assertEqual(req["model"], "qwen3:8b")
        self.assertIs(req["think"], False)
        self.assertIs(req["stream"], False)
        self.assertEqual(req["format"], ollama.ACTION_SCHEMA)
        self.assertEqual(req["options"], {"temperature": 0})
        self.assertEqual([m["role"] for m in req["messages"]], ["system", "user"])
        self.assertTrue(req["messages"][0]["content"].startswith("Today is 2026-11-07. "))
        self.assertTrue(req["messages"][0]["content"].endswith("SYS"))
        self.assertEqual(req["messages"][1]["content"], "USER")

    def test_date_not_repeated_when_prompt_already_states_it(self):
        sys_text = "Today is 2026-11-07. The current year is 2026. SYS"
        req = ollama.build_request("qwen3:8b", datetime.date(2026, 11, 7), sys_text, "USER")
        self.assertEqual(req["messages"][0]["content"], sys_text)

    def test_schema_is_json_schema_for_search_or_done(self):
        s = ollama.ACTION_SCHEMA
        self.assertEqual(s["type"], "object")
        self.assertEqual(s["properties"]["action"]["enum"], ["search", "done"])
        self.assertEqual(s["properties"]["preset"]["enum"], ["general", "finance", "news"])
        self.assertEqual(s["required"], ["action"])


class ValidateTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(ollama.validate_action({"action": "done"}, NEEDS), {"action": "done"})
        a = {"action": "search", "need": "sector_growth", "query": " payments growth ", "preset": "finance"}
        self.assertEqual(ollama.validate_action(a, NEEDS),
                         {"action": "search", "need": "sector_growth", "query": "payments growth",
                          "preset": "finance"})

    def test_defaults(self):
        a = ollama.validate_action({"action": "search", "query": "payments growth"}, NEEDS)
        self.assertEqual(a["need"], "sector_growth")
        self.assertEqual(a["preset"], "general")

    def test_invalid(self):
        for a in (None, "done", {}, {"action": "extract"}, {"action": "search"},
                  {"action": "search", "query": ""}, {"action": "search", "query": 5},
                  {"action": "search", "query": "x" * 401},
                  {"action": "search", "query": "q", "need": "other_need"},
                  {"action": "search", "query": "q", "preset": "advanced"}):
            with self.subTest(a=a):
                self.assertIsNone(ollama.validate_action(a, NEEDS))


class ClientTest(unittest.TestCase):
    def test_round_trip_against_stub(self):
        stub = StubOllama([{"action": "search", "need": "sector_growth", "query": "q1", "preset": "general"},
                           "not json"]).start()
        self.addCleanup(stub.stop)
        client = ollama.OllamaClient(stub.port, "qwen3:4b", today=datetime.date(2026, 11, 7))
        self.assertEqual(client.next_action("SYS", "USER")["query"], "q1")
        self.assertIsNone(client.next_action("SYS", "USER"))
        [r1, _] = stub.requests
        self.assertEqual(r1["path"], "/api/chat")
        self.assertEqual(r1["body"], ollama.build_request("qwen3:4b", datetime.date(2026, 11, 7), "SYS", "USER"))


if __name__ == "__main__":
    unittest.main()
