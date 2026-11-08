"""app/scenario.py: the demo scenario (halyard by default, or real_estate) chosen by DT_SCENARIO."""
import json
import os
import unittest

from app import scenario

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestName(unittest.TestCase):
    def test_default_is_halyard(self):
        self.assertEqual(scenario.DEFAULT, "halyard")
        self.assertEqual(scenario.name({}), "halyard")
        self.assertEqual(scenario.name({"DT_SCENARIO": ""}), "halyard")
        self.assertEqual(scenario.name({"DT_SCENARIO": "  "}), "halyard")

    def test_real_estate(self):
        self.assertEqual(scenario.name({"DT_SCENARIO": "real_estate"}), "real_estate")
        self.assertEqual(scenario.name({"DT_SCENARIO": " real_estate\n"}), "real_estate")

    def test_unknown_is_refused(self):
        for bad in ("re", "Real_Estate", "mars", "halyard;real_estate"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                scenario.name({"DT_SCENARIO": bad})

    def test_reads_process_environment_by_default(self):
        old = os.environ.pop("DT_SCENARIO", None)
        try:
            self.assertEqual(scenario.name(), "halyard")
            os.environ["DT_SCENARIO"] = "real_estate"
            self.assertEqual(scenario.name(), "real_estate")
        finally:
            os.environ.pop("DT_SCENARIO", None)
            if old is not None:
                os.environ["DT_SCENARIO"] = old


class TestScenarios(unittest.TestCase):
    def test_keys(self):
        self.assertEqual(set(scenario.SCENARIOS), {"halyard", "real_estate"})
        for s in scenario.SCENARIOS.values():
            self.assertTrue({"fixture", "careless_query", "need_labels"} <= set(s))

    def test_fixtures_exist_and_name_their_memo(self):
        ids = {}
        for name, s in scenario.SCENARIOS.items():
            with open(s["fixture"], encoding="utf-8") as f:
                fx = json.load(f)
            self.assertTrue(os.path.isfile(os.path.join(REPO, fx["memo_file"])))
            ids[name] = fx["memo_id"]
        self.assertEqual(ids, {"halyard": "halyard", "real_estate": "larkmoor"})

    def test_halyard_unchanged(self):
        h = scenario.SCENARIOS["halyard"]
        self.assertEqual(h["fixture"], os.path.join(REPO, "shared", "fixtures", "halyard_session.json"))
        self.assertEqual(h["careless_query"], "Ossory Capital Partners offer for Brackwater Payments")
        self.assertEqual(h["need_labels"], {"sector_growth": "Sector growth",
                                            "peer_ev_revenue": "Listed payments companies"})

    def test_careless_query_names_each_scenarios_own_secrets(self):
        for name, s in scenario.SCENARIOS.items():
            with open(s["fixture"], encoding="utf-8") as f:
                fx = json.load(f)
            values = {v.lower() for sec in fx["confirmed_secrets"] for v in sec["values"]}
            q = s["careless_query"].lower()
            self.assertTrue(any(v in q for v in values), (name, q))

    def test_real_estate_need_labels(self):
        self.assertEqual(scenario.SCENARIOS["real_estate"]["need_labels"],
                         {"re_lending_rates": "CRE lending rates", "re_cap_rates": "Cap rates and vacancy",
                          "re_comps": "Comparable sales"})


if __name__ == "__main__":
    unittest.main()
