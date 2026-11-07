"""FORMATS §0 and §7 test vectors, reproduced exactly."""
import datetime
import re
import unittest

from gate import canonical as c

N1, N2, N3 = b"\x11" * 32, b"\x22" * 32, b"\x33" * 32
Z = "0" * 64

PAYLOAD = (b'{"include_usage":true,"max_results":10,"query":"payments processing industry revenue growth 2025",'
           b'"search_depth":"basic","topic":"general"}')
ATTEMPT_COMMIT = "4b52c440d83efab1019ba647913621a44d17d704157cd48344a9598461bad87d"
ATTEMPT_HASH = "0e24438ed684680dfd171e311c1aab32bf4cc7179afc7f486593a29c8e100143"
RESP_COMMIT = "2c95e96c303fe880e45217edffd40a56b3ec8cb894b421cdd5224b151b52e3d1"
RESULT_HASH = "ef2bf800d0252fea0ef44d770e80e8d5de3da07c21f55cded504411a18d0346f"
BLOCKED_COMMIT = "2242b109b1e0a5e74dbd8198f5cd4955ba766c2df022bce2c382e2303bc80b7c"
BLOCKED_HASH = "9e049b231e5ab2b8d4ac6c20b871eac774645b7df839b64315b680ca7b19f985"

ATTEMPT_ROW_CANON = (
    '{"bytes":139,"commitment":"4b52c440d83efab1019ba647913621a44d17d704157cd48344a9598461bad87d",'
    '"component":"planner","decision":"allowed","destination":"api.tavily.com","kind":"search",'
    '"prev_hash":"0000000000000000000000000000000000000000000000000000000000000000","row_type":"attempt",'
    '"rule":null,"seq":1,"session_id":"s_dtreal1","time":"2026-11-07T23:41:07.500Z"}').encode()
RESULT_ROW_CANON = (
    '{"attempt_seq":1,"credits_used":1,"http_status":200,'
    '"prev_hash":"0e24438ed684680dfd171e311c1aab32bf4cc7179afc7f486593a29c8e100143",'
    '"response_commitment":"2c95e96c303fe880e45217edffd40a56b3ec8cb894b421cdd5224b151b52e3d1",'
    '"row_type":"result","seq":2,"session_id":"s_dtreal1","status":"sent","time":"2026-11-07T23:41:08.700Z"}'
).encode()


def body(query):
    return {"include_usage": True, "max_results": 10, "query": query, "search_depth": "basic", "topic": "general"}


def attempt_row():
    return {"seq": 1, "time": "2026-11-07T23:41:07.500Z", "session_id": "s_dtreal1", "row_type": "attempt",
            "component": "planner", "kind": "search", "destination": "api.tavily.com",
            "commitment": ATTEMPT_COMMIT, "bytes": 139, "decision": "allowed", "rule": None, "prev_hash": Z}


def result_row():
    return {"seq": 2, "time": "2026-11-07T23:41:08.700Z", "session_id": "s_dtreal1", "row_type": "result",
            "attempt_seq": 1, "status": "sent", "http_status": 200, "credits_used": 1,
            "response_commitment": RESP_COMMIT, "prev_hash": ATTEMPT_HASH}


class TestVectors(unittest.TestCase):
    def test_attempt_payload_bytes(self):
        p = c.canonical_json(body("payments processing industry revenue growth 2025"))
        self.assertEqual(p, PAYLOAD)
        self.assertEqual(len(p), 139)

    def test_attempt_commitment(self):
        self.assertEqual(c.commitment(N1, PAYLOAD), ATTEMPT_COMMIT)

    def test_attempt_row_canonical_and_hash(self):
        row = attempt_row()
        self.assertEqual(c.canonical_json(row), ATTEMPT_ROW_CANON)
        self.assertEqual(c.row_hash(row), ATTEMPT_HASH)

    def test_row_hash_ignores_hash_field(self):
        row = attempt_row()
        row["hash"] = "ff" * 32
        self.assertEqual(c.row_hash(row), ATTEMPT_HASH)

    def test_result_commitment(self):
        self.assertEqual(c.commitment(N2, b'{"example":"response bytes"}'), RESP_COMMIT)

    def test_result_row_canonical_and_hash(self):
        row = result_row()
        self.assertEqual(c.canonical_json(row), RESULT_ROW_CANON)
        self.assertEqual(c.row_hash(row), RESULT_HASH)

    def test_blocked_vector(self):
        p = c.canonical_json(body("Ossory Capital Partners offer for Brackwater Payments"))
        self.assertEqual(len(p), 144)
        cm = c.commitment(N3, p)
        self.assertEqual(cm, BLOCKED_COMMIT)
        row = {"seq": 1, "time": "2026-11-07T23:41:26.510Z", "session_id": "s_careless1", "row_type": "attempt",
               "component": "planner", "kind": "search", "destination": "api.tavily.com", "commitment": cm,
               "bytes": 144, "decision": "blocked", "rule": "secret.buyer", "prev_hash": Z}
        self.assertEqual(c.row_hash(row), BLOCKED_HASH)

    def test_zero_hash(self):
        self.assertEqual(c.ZERO_HASH, Z)


class TestConventions(unittest.TestCase):
    def test_no_whitespace_no_newline(self):
        out = c.canonical_json({"b": [1, 2], "a": {"y": 1, "x": "s"}})
        self.assertEqual(out, b'{"a":{"x":"s","y":1},"b":[1,2]}')

    def test_utf8_not_escaped(self):
        out = c.canonical_json({"q": "café"})
        self.assertEqual(out, '{"q":"café"}'.encode("utf-8"))
        self.assertNotIn(b"\\u", out)

    def test_sha256_hex_lowercase(self):
        h = c.sha256_hex(b"")
        self.assertEqual(h, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")

    def test_commitment_requires_32_byte_nonce(self):
        with self.assertRaises(ValueError):
            c.commitment(b"\x11" * 31, PAYLOAD)

    def test_new_nonce(self):
        a, b = c.new_nonce(), c.new_nonce()
        self.assertEqual(len(a), 32)
        self.assertNotEqual(a, b)

    def test_time_format(self):
        dt = datetime.datetime(2026, 11, 7, 23, 41, 7, 500999, tzinfo=datetime.timezone.utc)
        self.assertEqual(c.format_time(dt), "2026-11-07T23:41:07.500Z")
        self.assertRegex(c.utc_now(), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")

    def test_time_converts_to_utc(self):
        tz = datetime.timezone(datetime.timedelta(hours=-5))
        dt = datetime.datetime(2026, 11, 7, 18, 41, 7, 500000, tzinfo=tz)
        self.assertEqual(c.format_time(dt), "2026-11-07T23:41:07.500Z")

    def test_row_hash_refuses_floats(self):
        row = attempt_row()
        row["bytes"] = 139.0
        with self.assertRaises(ValueError):
            c.row_hash(row)


if __name__ == "__main__":
    unittest.main()
