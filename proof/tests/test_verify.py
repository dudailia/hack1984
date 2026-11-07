"""
The verifier: VALID on an honest bundle, INVALID with the right reason on each kind of damage, and INVALID on
EVERY single-byte edit (notes/ANANT.md "Done means").
"""

import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest

from proof.tests import helpers  # noqa: F401  (skips the module if cryptography is missing)
from proof.export import canonical_json, row_hash, sign
from proof.tests.helpers import TEST_KEY, sample_bundle
from proof.verify import verify_bytes

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VERIFY = os.path.join(ROOT, "proof", "verify.py")


def resign(obj, key=TEST_KEY):
    """Re-sign a modified bundle, to test that rules other than the signature catch the damage."""
    obj["signature"] = sign(key, obj)
    return canonical_json(obj)


class TestValid(unittest.TestCase):
    def test_honest_bundle_is_valid(self):
        r = verify_bytes(sample_bundle())
        self.assertTrue(r["valid"], r)
        self.assertEqual(r["rows_checked"], 5)
        self.assertIsNone(r["broken_at_seq"])
        self.assertEqual(set(r), {"valid", "rows_checked", "broken_at_seq", "reason", "bundle_head",
                                  "signer_key_sha256"})

    def test_signer_fingerprint_is_sha256_of_raw_public_key(self):
        # PR #4 review #3: the signature only proves "whoever holds this key signed it". The fingerprint lets a judge
        # compare the signer with the key we publish (README, results screen).
        import hashlib
        from cryptography.hazmat.primitives import serialization
        raw = TEST_KEY.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.assertEqual(verify_bytes(sample_bundle())["signer_key_sha256"], hashlib.sha256(raw).hexdigest())

    def test_pinned_signer_accepts_our_key_and_rejects_a_reforged_bundle(self):
        # PR #4 review (Aayush): the verifier trusts the key INSIDE the bundle, so a forger who edits rows, rebuilds
        # the chain and re-signs with their own key gets VALID. Pinning the expected signer closes that: our key
        # (raw public key, full fingerprint, or a >= 16-hex fingerprint prefix) passes, any other key fails.
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        good = sample_bundle()
        fp = verify_bytes(good)["signer_key_sha256"]
        pub = json.loads(good)["public_key"]
        for pin in (pub, fp, fp[:16], fp.upper()):
            with self.subTest(pin=pin[:8]):
                self.assertTrue(verify_bytes(good, expected_signer=pin)["valid"])
        forged = sample_bundle(key=Ed25519PrivateKey.generate())       # fully consistent, signed by someone else
        self.assertTrue(verify_bytes(forged)["valid"])                  # without a pin: VALID (self-attested)
        r = verify_bytes(forged, expected_signer=fp)
        self.assertEqual((r["valid"], r["reason"]), (False, "unexpected_signer"))

    def test_pin_too_short_is_rejected(self):
        with self.assertRaises(ValueError):
            verify_bytes(sample_bundle(), expected_signer="abcd")

    def test_fingerprint_is_null_when_unreadable(self):
        self.assertIsNone(verify_bytes(b"{not json")["signer_key_sha256"])

    def test_no_reveals_is_valid(self):
        self.assertTrue(verify_bytes(sample_bundle(reveal=()))["valid"])


class TestReasons(unittest.TestCase):
    def setUp(self):
        self.obj = json.loads(sample_bundle())

    def reason(self, data):
        r = verify_bytes(data)
        self.assertFalse(r["valid"])
        return r["reason"], r["broken_at_seq"]

    def test_parse_error(self):
        self.assertEqual(self.reason(b"{not json")[0], "parse_error")

    def test_not_canonical(self):
        self.assertEqual(self.reason(json.dumps(self.obj, indent=1).encode())[0], "not_canonical")

    def test_bad_hex(self):
        self.obj["head"] = self.obj["head"].upper()
        self.assertEqual(self.reason(canonical_json(self.obj))[0], "bad_hex")

    def test_hash_mismatch_reports_row(self):
        self.obj["rows"][2]["time"] = "2026-11-07T23:41:26.511Z"
        self.assertEqual(self.reason(resign(self.obj)), ("hash_mismatch", 3))

    def test_prev_mismatch(self):
        row = self.obj["rows"][3]
        row["prev_hash"] = "0" * 64
        row["hash"] = row_hash(row)
        self.assertEqual(self.reason(resign(self.obj)), ("prev_mismatch", 4))

    def test_seq_gap(self):
        del self.obj["rows"][1]
        self.assertEqual(self.reason(resign(self.obj)), ("seq_gap", 2))

    def test_broken_row_is_reported_by_position_not_by_its_own_seq(self):
        # PR #4 review #1: the tampered value may BE the seq. Edit row 3's seq to 7: the UI must flag row 3 (the
        # third row in the file), not "row 7", which does not exist.
        self.obj["rows"][2]["seq"] = 7
        self.assertEqual(self.reason(resign(self.obj)), ("seq_gap", 3))

    def test_bad_hex_in_a_row_reports_its_position(self):
        self.obj["rows"][2]["seq"] = 9                         # a wrong seq AND a bad hash in the same row
        self.obj["rows"][2]["hash"] = "Z" * 64
        self.assertEqual(self.reason(resign(self.obj)), ("bad_hex", 3))

    def test_session_mismatch(self):
        row = self.obj["rows"][0]
        row["session_id"] = "s_other001"
        self.assertEqual(self.reason(resign(self.obj)), ("session_mismatch", 1))

    def test_reveal_mismatch(self):
        self.obj["rows"][0]["reveal"]["payload"] = self.obj["rows"][0]["reveal"]["payload"].replace("2025", "2024")
        self.assertEqual(self.reason(resign(self.obj)), ("reveal_mismatch", 1))

    def test_reveal_on_blocked(self):
        self.obj["rows"][2]["reveal"] = {"payload": "x", "nonce": "33" * 32}
        self.assertEqual(self.reason(resign(self.obj)), ("reveal_on_blocked", 3))

    def test_reveal_on_result(self):
        self.obj["rows"][1]["reveal"] = {"payload": "x", "nonce": "22" * 32}
        self.assertEqual(self.reason(resign(self.obj)), ("reveal_on_result", 2))

    def test_head_mismatch(self):
        self.obj["head"] = self.obj["rows"][0]["hash"]
        self.assertEqual(self.reason(resign(self.obj))[0], "head_mismatch")

    def test_bad_signature_other_key(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        self.obj["signature"] = sign(Ed25519PrivateKey.generate(), self.obj)
        self.assertEqual(self.reason(canonical_json(self.obj))[0], "bad_signature")

    def test_extra_key_rejected(self):
        self.obj["note"] = "hi"
        self.assertEqual(self.reason(resign(self.obj))[0], "bad_bundle")

    def test_duplicate_key_rejected(self):
        data = sample_bundle().replace(b'{"code_hashes"', b'{"v":1,"code_hashes"', 1)
        self.assertEqual(self.reason(data)[0], "parse_error")


class TestEverySingleByteEdit(unittest.TestCase):
    """Replace each byte with 8 different values (every single-bit flip), and delete each byte. All INVALID."""

    def test_every_bit_flip_and_deletion(self):
        data = sample_bundle()
        passed = []
        for i in range(len(data)):
            edits = [data[:i] + bytes([data[i] ^ (1 << b)]) + data[i + 1:] for b in range(8)]
            edits.append(data[:i] + data[i + 1:])
            for e in edits:
                if verify_bytes(e)["valid"]:
                    passed.append((i, e[max(0, i - 20):i + 20]))
        self.assertEqual(passed, [], "single-byte edits that still verify: %r" % passed[:5])

    @unittest.skipUnless(os.environ.get("DT_SLOW"), "set DT_SLOW=1 to try all 255 replacements per byte")
    def test_every_possible_replacement(self):
        data = sample_bundle()
        for i in range(len(data)):
            for v in range(256):
                if v != data[i]:
                    e = data[:i] + bytes([v]) + data[i + 1:]
                    self.assertFalse(verify_bytes(e)["valid"], (i, v))


class TestStandalone(unittest.TestCase):
    def test_imports_only_stdlib_and_cryptography(self):
        with open(VERIFY, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                mods.add((node.module or "").split(".")[0])
        ours = {"checks", "proof", "gate", "planner", "reader", "app", "baseline", "fake_tavily", "ui", "shared"}
        self.assertFalse(mods & ours, mods)
        self.assertTrue(mods <= set(sys.stdlib_module_names) | {"cryptography"}, mods)

    def test_cli_valid_and_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            good = os.path.join(d, "b.json")
            with open(good, "wb") as f:
                f.write(sample_bundle())
            # -I: isolated mode, so the script cannot import anything from the repo even by accident.
            out = subprocess.run([sys.executable, "-I", VERIFY, good], capture_output=True, text=True)
            fp = verify_bytes(sample_bundle())["signer_key_sha256"][:16]
            self.assertEqual((out.returncode, out.stdout.strip()), (0, "VALID (signer key %s)" % fp))
            obj = json.loads(sample_bundle())
            obj["rows"][2]["time"] = "2026-11-07T23:41:26.511Z"
            bad = os.path.join(d, "bad.json")
            with open(bad, "wb") as f:
                f.write(resign(obj))
            out = subprocess.run([sys.executable, "-I", VERIFY, bad, "--json"], capture_output=True, text=True)
            self.assertEqual(out.returncode, 1)
            self.assertEqual(json.loads(out.stdout)["reason"], "hash_mismatch")
            out = subprocess.run([sys.executable, "-I", VERIFY, bad], capture_output=True, text=True)
            self.assertEqual(out.stdout.strip(), "INVALID: row 3 hash_mismatch")
            # --pubkey pins the signer: the right fingerprint passes, a wrong one fails with exit 1.
            out = subprocess.run([sys.executable, "-I", VERIFY, good, "--pubkey", fp], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            out = subprocess.run([sys.executable, "-I", VERIFY, good, "--pubkey", "0" * 16], capture_output=True,
                                 text=True)
            self.assertEqual((out.returncode, out.stdout.strip()), (1, "INVALID: unexpected_signer"))


if __name__ == "__main__":
    unittest.main()
