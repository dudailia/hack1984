import json
import unittest

import reader
from reader.tests import fixtures as fx

GOOD = {"claim_type": "revenue_growth", "subject": "global payments processing market", "value": 9.8,
        "unit": "percent", "period": "2025-2030",
        "quote": "The global payments processing market is projected to grow at a compound annual rate of 9.8% from 2025 to 2030.",
        "document_id": "r_01"}


def response(text):
    return {"id": "msg_x", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
            "content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}


class ParseResponse(unittest.TestCase):
    def setUp(self):
        self.job = fx.page("j01_sector_growth.json")

    def test_plain_json(self):
        self.assertEqual(reader.parse_response(self.job, response(json.dumps({"claims": [GOOD]}))), [GOOD])

    def test_fenced_json(self):
        text = "```json\n" + json.dumps({"claims": [GOOD]}) + "\n```"
        self.assertEqual(reader.parse_response(self.job, response(text)), [GOOD])

    def test_prose_around_json(self):
        text = "Here are the claims:\n" + json.dumps({"claims": [GOOD]}) + "\nDone."
        self.assertEqual(reader.parse_response(self.job, response(text)), [GOOD])

    def test_text_split_over_blocks_and_thinking_ignored(self):
        raw = json.dumps({"claims": [GOOD]})
        resp = {"content": [{"type": "thinking", "thinking": "{\"claims\":[]}"},
                            {"type": "text", "text": raw[:20]}, {"type": "text", "text": raw[20:]}]}
        self.assertEqual(reader.parse_response(self.job, resp), [GOOD])

    def test_raw_string_response_accepted(self):
        self.assertEqual(reader.parse_response(self.job, json.dumps(response(json.dumps({"claims": [GOOD]})))), [GOOD])

    def test_empty_claims(self):
        self.assertEqual(reader.parse_response(self.job, response('{"claims": []}')), [])

    def test_off_schema_claims_dropped(self):
        bad = [
            {k: v for k, v in GOOD.items() if k != "quote"},          # missing field
            dict(GOOD, confidence=0.9),                                # extra field
            dict(GOOD, value="9.8"),                                   # string value
            dict(GOOD, value=True),                                    # bool value
            dict(GOOD, period="FY2025"),                               # bad period format
            dict(GOOD, subject="x" * 81),                              # subject too long
            dict(GOOD, quote="q" * 401),                               # quote too long
            "not a claim",
        ]
        out = reader.parse_response(self.job, response(json.dumps({"claims": bad + [GOOD]})))
        self.assertEqual(out, [GOOD])

    def test_garbage_gives_empty_list(self):
        for resp in (response("no json here"), response('{"claims": "nope"}'), response("[1,2]"),
                     response('{"claims": [ {"claim_type": '), {"content": []}, {}, None, 42, "not json",
                     {"type": "error", "error": {"type": "overloaded_error"}}):
            self.assertEqual(reader.parse_response(self.job, resp), [], repr(resp))

    def test_nan_rejected(self):
        text = '{"claims":[' + json.dumps(GOOD).replace("9.8,", "NaN,", 1) + "]}"
        self.assertEqual(reader.parse_response(self.job, response(text)), [])


if __name__ == "__main__":
    unittest.main()
