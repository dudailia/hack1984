"""
Shared helpers for proof/ tests: a deterministic sample session and its bundle.

The sample session reuses the EXACT test vectors from shared/FORMATS.md section 7 (rows 1 and 2), then adds a
blocked attempt (the demo's careless query) and a reader attempt + result, so every row type and both decisions
are covered. Nonces and the signing key are fixed bytes so every run produces the same bundle.
"""

import unittest

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
except ImportError:  # pragma: no cover
    raise unittest.SkipTest("cryptography is not installed: run `.venv/bin/python -m unittest discover` "
                            "(setup: python3 -m venv .venv && .venv/bin/pip install cryptography)")

from proof.export import attempt_row, build_bundle, result_row

SESSION = "s_dtreal1"
TEST_KEY = Ed25519PrivateKey.from_private_bytes(bytes([7]) * 32)   # test only, never a real key
CODE_HASHES = {"checks/__init__.py": "ab" * 32, "gate/pipeline.py": "cd" * 32}
EXPORTED = "2026-11-07T23:41:44.000Z"

# FORMATS section 7 test vector payloads.
P1 = (b'{"include_usage":true,"max_results":10,"query":"payments processing industry revenue growth 2025",'
      b'"search_depth":"basic","topic":"general"}')
P_CARELESS = P1.replace(b"payments processing industry revenue growth 2025",
                        b"Ossory Capital Partners offer for Brackwater Payments")
P_READER = b'{"max_tokens":2048,"messages":[],"model":"claude-haiku-5-5","system":"x","temperature":0}'

# Response bodies and nonces of the two result rows. In Aayush's ledger these sit in the private columns
# (payload_priv, nonce_priv) of the RESULT rows; the exporter must never reveal them.
RESPONSES = {2: (b'{"example":"response bytes"}', b"\x22" * 32), 5: (b'{"claims":[]}', b"\x55" * 32)}


def sample_rows():
    """[rows], {seq: (payload_bytes, nonce_bytes)} for a 5-row session (attempt payloads only)."""
    secrets = {}
    rows = []
    r1 = attempt_row(1, "2026-11-07T23:41:07.500Z", SESSION, "planner", "search", "api.tavily.com",
                     P1, b"\x11" * 32, "allowed", None, "0" * 64)
    rows.append(r1); secrets[1] = (P1, b"\x11" * 32)
    r2 = result_row(2, "2026-11-07T23:41:08.700Z", SESSION, 1, "sent", 200, 1,
                    RESPONSES[2][0], RESPONSES[2][1], r1["hash"])
    rows.append(r2)
    r3 = attempt_row(3, "2026-11-07T23:41:26.510Z", SESSION, "planner", "search", "api.tavily.com",
                     P_CARELESS, b"\x33" * 32, "blocked", "secret.buyer", r2["hash"])
    rows.append(r3); secrets[3] = (P_CARELESS, b"\x33" * 32)
    r4 = attempt_row(4, "2026-11-07T23:41:27.000Z", SESSION, "reader", "reader", "api.anthropic.com",
                     P_READER, b"\x44" * 32, "allowed", None, r3["hash"])
    rows.append(r4); secrets[4] = (P_READER, b"\x44" * 32)
    r5 = result_row(5, "2026-11-07T23:41:29.000Z", SESSION, 4, "sent", 200, None,
                    RESPONSES[5][0], RESPONSES[5][1], r4["hash"])
    rows.append(r5)
    return rows, secrets


def sample_bundle(reveal=(1, 4), key=TEST_KEY):
    """Canonical bundle bytes. By default reveals the two allowed attempts (never the blocked one)."""
    rows, secrets = sample_rows()
    reveals = {seq: secrets[seq] for seq in reveal}
    return build_bundle(SESSION, rows, reveals, key, CODE_HASHES, EXPORTED)
