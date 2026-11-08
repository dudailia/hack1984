"""Planner profiles (one per demo scenario, app/scenario.py). Halyard is the default and must stay byte-identical:
its system prompt, Ollama grammar and request body are pinned by hashes taken before profiles existed."""
import hashlib
import json
import unittest

from planner import ollama, planner, prompt, schema

HALYARD_PROMPT_SHA = {"2026-11-08": "5fb810ecb33a62368525b84a95fa36b6a724b5f360f5cad9bf6626824c3aef69",
                      "2025-01-31": "833e70c600e8e367e09cb8f4e07fadbc5c81fefe91bb4c9add7f667fb991e660"}
HALYARD_GRAMMAR_SHA = "9c5812d3bbca5cfaf6a76a55928f97a470c5c417ca0c5814c9ed10697b6e717e"
HALYARD_BODY_SHA = "a4a9da8e1bfb94ad4487cc21a1e35e252cb272bd2ea38618e32cc10a068a0d16"
RE_TYPES = ["interest_rate", "cap_rate", "vacancy_rate", "price_per_sqft", "market_size", "revenue_growth"]
MEMO = "PROJECT LARKMOOR. Fund IV is preparing an offer for Larkmoor Wharf.\nRef: kq7m2xw9tpa4hd3n\n"


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def jsha(obj):
    return sha(json.dumps(obj, sort_keys=True))


class TestHalyardUnchanged(unittest.TestCase):
    def test_system_prompt_bytes(self):
        for d, h in HALYARD_PROMPT_SHA.items():
            self.assertEqual(sha(prompt.system_prompt(d)), h)
            self.assertEqual(sha(prompt.system_prompt(d, profile="halyard")), h)
            self.assertEqual(sha(prompt.system_prompt(d, profile=None)), h)

    def test_grammar_and_body(self):
        self.assertEqual(jsha(schema.ACTION_JSON_SCHEMA), HALYARD_GRAMMAR_SHA)
        self.assertEqual(jsha(schema.action_json_schema("halyard")), HALYARD_GRAMMAR_SHA)
        body = ollama.build_body("m", [{"role": "user", "content": "x"}])
        self.assertEqual(jsha(body), HALYARD_BODY_SHA)

    def test_halyard_claim_types_are_the_original_eight(self):
        self.assertEqual(schema.PROFILE_CLAIM_TYPES["halyard"],
                         ("revenue", "revenue_growth", "ev_revenue_multiple", "ev_ebitda_multiple", "ebitda",
                          "market_size", "employees", "founded_year"))

    def test_halyard_rejects_re_types(self):
        for ct in ("cap_rate", "vacancy_rate", "interest_rate", "price_per_sqft"):
            with self.assertRaises(schema.SchemaError):
                schema.validate_action({"action": "search", "need": "x", "claim_types": [ct], "query": "q",
                                        "preset": "general"})


class TestRealEstateProfile(unittest.TestCase):
    def test_profiles(self):
        self.assertEqual(set(schema.PROFILE_CLAIM_TYPES), {"halyard", "real_estate"})
        self.assertEqual(list(schema.PROFILE_CLAIM_TYPES["real_estate"]), RE_TYPES)
        for types in schema.PROFILE_CLAIM_TYPES.values():
            self.assertTrue(set(types) <= set(schema.CLAIM_UNITS))

    def test_prompt(self):
        p = prompt.system_prompt("2026-11-08", profile="real_estate")
        for s in ("property name", "the buyer", "financing amount", "codename", "person's name",
                  "cap rates", "vacancy", "lending rates", "comparable", "re_lending_rates", "re_cap_rates",
                  "re_comps", "Never copy any code", "3 to 8 words", "2026"):
            self.assertIn(s, p)
        for t in RE_TYPES:
            self.assertIn("  - %s: " % t, p)
        for s in ("ev_revenue_multiple", "listed companies", "sector_growth", "payments", "founded_year"):
            self.assertNotIn(s, p)

    def test_prompt_units(self):
        p = prompt.system_prompt("2026-11-08", profile="real_estate")
        self.assertIn("  - cap_rate: percent", p)
        self.assertIn("  - price_per_sqft: usd", p)

    def test_grammar(self):
        g = schema.action_json_schema("real_estate")
        for branch in g["anyOf"][:2]:
            self.assertEqual(branch["properties"]["claim_types"]["items"]["enum"], sorted(RE_TYPES))

    def test_validate(self):
        ok = {"action": "search", "need": "re_cap_rates", "claim_types": ["cap_rate", "vacancy_rate"],
              "query": "office cap rates 2026", "preset": "general"}
        self.assertEqual(schema.validate_action(dict(ok), profile="real_estate")["claim_types"],
                         ["cap_rate", "vacancy_rate"])
        with self.assertRaises(schema.SchemaError):
            schema.validate_action(dict(ok, claim_types=["ev_revenue_multiple"]), profile="real_estate")

    def test_unknown_profile(self):
        for bad in ("mars", "", 3):
            with self.assertRaises(ValueError):
                prompt.system_prompt("2026-11-08", profile=bad)
            with self.assertRaises(ValueError):
                schema.action_json_schema(bad)

    def test_user_prompt_unchanged_by_profile(self):
        a = prompt.build_messages(MEMO, "q?", "2026-11-08", [])
        b = prompt.build_messages(MEMO, "q?", "2026-11-08", [], profile="real_estate")
        self.assertEqual(a[1], b[1])
        self.assertNotEqual(a[0], b[0])


class TestNextActionProfile(unittest.TestCase):
    def test_re_uses_re_prompt_and_grammar(self):
        calls = []

        def chat(messages, schema=None):
            calls.append((messages, schema))
            return json.dumps({"action": "search", "need": "re_cap_rates", "claim_types": ["cap_rate"],
                               "query": "office cap rates 2026", "preset": "general"})
        out = planner.next_action(MEMO, "q?", "2026-11-08", [], chat=chat, profile="real_estate")
        self.assertEqual(out["claim_types"], ["cap_rate"])
        messages, sch = calls[0]
        self.assertEqual(messages[0]["content"], prompt.system_prompt("2026-11-08", profile="real_estate"))
        self.assertEqual(sch, schema.action_json_schema("real_estate"))

    def test_re_rejects_halyard_types(self):
        def chat(messages, schema=None):
            return json.dumps({"action": "search", "need": "x", "claim_types": ["ev_revenue_multiple"],
                               "query": "office cap rates", "preset": "general"})
        self.assertEqual(planner.next_action(MEMO, "q?", "2026-11-08", [], chat=chat, profile="real_estate"),
                         {"action": "done"})

    def test_halyard_calls_chat_with_messages_only(self):
        calls = []

        def chat(*args, **kwargs):
            calls.append((args, kwargs))
            return json.dumps({"action": "done"})
        planner.next_action(MEMO, "q?", "2026-11-08", [], chat=chat)
        planner.next_action(MEMO, "q?", "2026-11-08", [], chat=chat, profile="halyard")
        self.assertEqual([len(a) for a, _ in calls], [1, 1])
        self.assertEqual([k for _, k in calls], [{}, {}])

    def test_re_typed_results_with_new_types_accepted(self):
        typed = [{"need": "re_cap_rates", "found": True,
                  "values": [{"claim_type": "cap_rate", "value": 5.4, "unit": "percent", "period": "2025",
                              "result_id": "r_01"}]}]

        def chat(messages, schema=None):
            return json.dumps({"action": "done"})
        self.assertEqual(planner.next_action(MEMO, "q?", "2026-11-08", typed, chat=chat, profile="real_estate"),
                         {"action": "done"})

    def test_unknown_profile(self):
        with self.assertRaises(ValueError):
            planner.next_action(MEMO, "q?", "2026-11-08", [], chat=lambda m: "{}", profile="mars")

    def test_ollama_chat_sends_the_given_grammar(self):
        sent = []

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps({"message": {"content": "{\"action\":\"done\"}"}}).encode()

        def urlopen(req, timeout=None):
            sent.append(json.loads(req.data))
            return Resp()
        env = {"OLLAMA_MODEL": "qwen3:8b", "OLLAMA_PORT": "11434"}
        ollama.chat([{"role": "user", "content": "x"}], env=env, urlopen=urlopen)
        ollama.chat([{"role": "user", "content": "x"}], env=env, urlopen=urlopen,
                    schema=schema.action_json_schema("real_estate"))
        self.assertEqual(sent[0]["format"], schema.ACTION_JSON_SCHEMA)
        self.assertEqual(sent[1]["format"], schema.action_json_schema("real_estate"))


if __name__ == "__main__":
    unittest.main()
