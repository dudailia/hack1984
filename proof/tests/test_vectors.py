"""
The FORMATS.md section 7 test vectors. These are the contract with Aayush's ledger: if his rows and ours hash
differently, every bundle fails. Both sides test against these same numbers.
"""

import unittest

from proof.tests import helpers  # noqa: F401  (skips the module if cryptography is missing)
from proof.export import attempt_row, commitment, result_row
from proof.tests.helpers import P1, P_CARELESS

H1 = "0e24438ed684680dfd171e311c1aab32bf4cc7179afc7f486593a29c8e100143"


class TestFormatsVectors(unittest.TestCase):
    def test_attempt_commitment(self):
        self.assertEqual(len(P1), 139)
        self.assertEqual(commitment(b"\x11" * 32, P1),
                         "4b52c440d83efab1019ba647913621a44d17d704157cd48344a9598461bad87d")

    def test_attempt_row_hash(self):
        r = attempt_row(1, "2026-11-07T23:41:07.500Z", "s_dtreal1", "planner", "search", "api.tavily.com",
                        P1, b"\x11" * 32, "allowed", None, "0" * 64)
        self.assertEqual(r["hash"], H1)

    def test_result_row(self):
        r = result_row(2, "2026-11-07T23:41:08.700Z", "s_dtreal1", 1, "sent", 200, 1,
                       b'{"example":"response bytes"}', b"\x22" * 32, H1)
        self.assertEqual(r["response_commitment"],
                         "2c95e96c303fe880e45217edffd40a56b3ec8cb894b421cdd5224b151b52e3d1")
        self.assertEqual(r["hash"], "ef2bf800d0252fea0ef44d770e80e8d5de3da07c21f55cded504411a18d0346f")

    def test_blocked_row(self):
        self.assertEqual(len(P_CARELESS), 144)
        r = attempt_row(1, "2026-11-07T23:41:26.510Z", "s_careless1", "planner", "search", "api.tavily.com",
                        P_CARELESS, b"\x33" * 32, "blocked", "secret.buyer", "0" * 64)
        self.assertEqual(r["commitment"], "2242b109b1e0a5e74dbd8198f5cd4955ba766c2df022bce2c382e2303bc80b7c")
        self.assertEqual(r["hash"], "9e049b231e5ab2b8d4ac6c20b871eac774645b7df839b64315b680ca7b19f985")


if __name__ == "__main__":
    unittest.main()
