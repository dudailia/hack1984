import os
import tempfile
import unittest
from unittest import mock

from gate import bundle
from gate.ledger import Ledger


class TestBundle(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.dir.name, "sub", "..", "t.db")  # non-normalized on purpose
        self.led = Ledger(self.db)

    def tearDown(self):
        self.led.close()
        self.dir.cleanup()

    def test_ledger_path_absolute(self):
        self.assertTrue(os.path.isabs(self.led.path))
        self.assertEqual(self.led.path, os.path.abspath(self.db))

    def test_not_available_without_proof(self):
        with mock.patch("importlib.util.find_spec", return_value=None):
            with self.assertRaises(bundle.NotAvailable):
                bundle.export("s_bund00001", self.led.path)

    def test_calls_export_with_absolute_paths(self):
        calls = []

        def export_bundle(session_id, db_path="ledger/doublethink.db", reveal="allowed",
                          key_path="ledger/ed25519_private.pem"):
            calls.append((session_id, db_path, reveal, key_path))
            return b'{"v":1}'

        with mock.patch.object(bundle, "_load", return_value=export_bundle):
            with mock.patch("os.getcwd", return_value="/somewhere/else"):
                out = bundle.export("s_bund00001", self.led.path)
        self.assertEqual(out, b'{"v":1}')
        sid, db, reveal, key = calls[0]
        self.assertEqual((sid, reveal), ("s_bund00001", "allowed"))
        self.assertEqual(db, os.path.abspath(self.db))
        self.assertEqual(key, os.path.join(os.path.dirname(os.path.abspath(self.db)), "ed25519_private.pem"))
        self.assertTrue(os.path.isabs(db) and os.path.isabs(key))

    def test_non_bytes_refused(self):
        with mock.patch.object(bundle, "_load", return_value=lambda *a, **k: "not bytes"):
            with self.assertRaises(TypeError):
                bundle.export("s_bund00001", self.led.path)

    def test_proof_outside_repo_refused(self):
        spec = mock.Mock(origin="/usr/lib/python3/site-packages/proof/__init__.py")
        with mock.patch("importlib.util.find_spec", return_value=spec):
            with self.assertRaises(bundle.NotAvailable):
                bundle.export("s_bund00001", self.led.path)


if __name__ == "__main__":
    unittest.main()
