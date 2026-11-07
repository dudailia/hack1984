#!/usr/bin/env python3
"""
proof/verify.py: the STANDALONE bundle verifier.

    python3 proof/verify.py BUNDLE.json            ->  VALID (signer key 3f9a1c0b7d2e4a51)
                                                       or  INVALID: row 3 hash_mismatch
    python3 proof/verify.py BUNDLE.json --json     ->  {"valid":false,"rows_checked":3,"broken_at_seq":3,
                                                        "reason":"hash_mismatch","bundle_head":"...",
                                                        "signer_key_sha256":"<64 hex>"}
    exit code 0 if valid, 1 if not.

WHY "STANDALONE"
----------------
This is the script a judge, auditor or compliance officer runs on their own machine to check our record. If it
imported our code, they would have to trust our code to check our code. So it imports ONLY the Python standard
library and `cryptography` (for Ed25519), and it is one file you can read top to bottom. A test enforces this.

WHAT A BUNDLE IS (shared/FORMATS.md section 8)
----------------------------------------------
The whole ledger of one session, exported as canonical JSON:
    v, format, session_id, exported       header
    rows                                  every ledger row, in order, each hash-chained to the one before
    head                                  the last row's hash: one value that fixes the whole chain
    code_hashes                           SHA-256 of every gate/ and checks/ source file at export time
    public_key, signature                 Ed25519 signature over {code_hashes, exported, head, session_id, v}

Rows never contain the payload itself, only commitment = SHA-256(nonce || payload). A row MAY carry
reveal = {payload, nonce} for an ALLOWED attempt, so a reader can see exactly what left; blocked attempts are never
revealed (they are the ones that would have leaked).

WHAT IS CHECKED, IN ORDER (the first failure is reported)
---------------------------------------------------------
  1. parse_error / not_canonical   the file is valid UTF-8 JSON with no duplicate keys, and its bytes are EXACTLY
                                   the canonical re-serialisation. So whitespace, key order, escapes: nothing can
                                   change without being noticed.
  -  bad_bundle / bad_row          exact key sets and value types (a renamed or extra key is not ignored).
  2. bad_hex                       every hash/key/signature/nonce is lowercase hex of the right length.
  3. per row, in order:
       seq_gap                     seq is 1, 2, 3, ... with no gap
       session_mismatch            row session_id = bundle session_id
       prev_mismatch               prev_hash = previous row's hash (64 zeros for row 1)
       hash_mismatch               hash = SHA-256(canonical row without `hash` and `reveal`)
  4. per reveal:
       reveal_on_result / reveal_on_blocked   reveals only on allowed attempts
       reveal_mismatch             SHA-256(nonce || payload) = commitment, and len(payload) = bytes
  5. head_mismatch                 head = last row's hash
  6. bad_signature                 the Ed25519 signature verifies under public_key

Because every byte is covered by (1) canonical form, (3) row hashes, (4) commitments, or (6) the signature, ANY
single-byte edit gives INVALID. The test suite edits every byte of a sample bundle to prove it.

The signed message matches FORMATS section 8: {code_hashes, exported, head, session_id, v}. (`exported` is signed
so that even the export time cannot change without breaking the signature.)

WHICH ROW IS "BROKEN"
---------------------
broken_at_seq is the row's POSITION in the file (1 = first row), not the row's own `seq` field: the seq may be the
very value that was tampered with ("seq":3 edited to "seq":7 must flag the third row, not a row 7 that does not
exist). For an honest chain the two are equal. The UI marks every row from broken_at_seq down (FORMATS section 10).

WHO SIGNED: THE KEY FINGERPRINT
-------------------------------
The signature is checked against the public_key INSIDE the bundle. So VALID means "consistent, and signed by the
holder of this key", not "signed by us": anyone can rebuild an edited chain and sign it with their own key. To tell
the two apart, the verifier reports signer_key_sha256 = SHA-256 of the raw 32-byte public key (text output shows the
first 16 hex characters). We publish our fingerprint (README, results screen); a judge compares the two.
"""

import hashlib
import json
import re
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ZERO_HASH = "0" * 64
FORMAT = "doublethink-bundle"

# Exact key sets. `reveal` is optional on any row (rule 4 then decides if it is allowed there).
TOP_KEYS = {"v", "format", "session_id", "exported", "rows", "head", "code_hashes", "public_key", "signature"}
ATTEMPT_KEYS = {"seq", "time", "session_id", "row_type", "component", "kind", "destination", "commitment", "bytes",
                "decision", "rule", "prev_hash", "hash"}
RESULT_KEYS = {"seq", "time", "session_id", "row_type", "attempt_seq", "status", "http_status", "credits_used",
               "response_commitment", "prev_hash", "hash"}
REVEAL_KEYS = {"payload", "nonce"}

_HEX = {64: re.compile(r"^[0-9a-f]{64}$"), 128: re.compile(r"^[0-9a-f]{128}$")}


# ---------------------------------------------------------------------------------------------------------------
# Small building blocks
# ---------------------------------------------------------------------------------------------------------------

def canonical_json(obj):
    """FORMATS section 0: sorted keys, no whitespace, UTF-8, non-ASCII kept as-is."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def row_hash(row):
    """SHA-256 of the canonical row WITHOUT its own `hash` and without `reveal` (the reveal is extra evidence about
    the commitment, not part of the chained record)."""
    body = {k: v for k, v in row.items() if k not in ("hash", "reveal")}
    return hashlib.sha256(canonical_json(body)).hexdigest()


def signed_message(bundle):
    """The exact bytes the Ed25519 signature covers."""
    return canonical_json({"code_hashes": bundle["code_hashes"], "exported": bundle["exported"],
                           "head": bundle["head"], "session_id": bundle["session_id"], "v": bundle["v"]})


class _Invalid(Exception):
    """Raised at the first failure; carries what the --json output reports."""

    def __init__(self, reason, seq=None, rows_checked=0):
        super().__init__(reason)
        self.reason, self.seq, self.rows_checked = reason, seq, rows_checked


def _no_duplicates(pairs):
    """json.loads hook: a duplicate key would otherwise silently keep the last value."""
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise ValueError("duplicate key %r" % k)
        obj[k] = v
    return obj


def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _is_hex(x, n):
    return isinstance(x, str) and bool(_HEX[n].match(x))


# ---------------------------------------------------------------------------------------------------------------
# The checks, one function per step
# ---------------------------------------------------------------------------------------------------------------

def _step1_parse(data):
    try:
        obj = json.loads(data.decode("utf-8"), object_pairs_hook=_no_duplicates,
                         parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))  # reject NaN/Infinity
    except (UnicodeDecodeError, ValueError):
        raise _Invalid("parse_error")
    if not isinstance(obj, dict):
        raise _Invalid("parse_error")
    if canonical_json(obj) != data:
        raise _Invalid("not_canonical")
    return obj


def _structure(b):
    """Exact keys and value types. Rows are reported by position (1-based) since their seq may be the damage."""
    if set(b) != TOP_KEYS or b["v"] != 1 or not _is_int(b["v"]) or b["format"] != FORMAT:
        raise _Invalid("bad_bundle")
    if not isinstance(b["session_id"], str) or not isinstance(b["exported"], str):
        raise _Invalid("bad_bundle")
    if not isinstance(b["rows"], list) or not isinstance(b["code_hashes"], dict):
        raise _Invalid("bad_bundle")
    for i, r in enumerate(b["rows"], 1):
        if not isinstance(r, dict):
            raise _Invalid("bad_row", i, i - 1)
        keys = set(r) - {"reveal"}
        rt = r.get("row_type")
        ok = (rt == "attempt" and keys == ATTEMPT_KEYS) or (rt == "result" and keys == RESULT_KEYS)
        if ok and rt == "attempt":
            ok = (_is_int(r["seq"]) and _is_int(r["bytes"]) and r["decision"] in ("allowed", "blocked")
                  and (r["rule"] is None or isinstance(r["rule"], str))
                  and all(isinstance(r[k], str) for k in ("time", "session_id", "component", "kind", "destination")))
        elif ok:
            ok = (_is_int(r["seq"]) and _is_int(r["attempt_seq"]) and r["status"] in ("sent", "error")
                  and (r["http_status"] is None or _is_int(r["http_status"]))
                  and (r["credits_used"] is None or _is_int(r["credits_used"]))
                  and all(isinstance(r[k], str) for k in ("time", "session_id")))
        if ok and "reveal" in r:
            rv = r["reveal"]
            ok = isinstance(rv, dict) and set(rv) == REVEAL_KEYS and isinstance(rv["payload"], str)
        if not ok:
            raise _Invalid("bad_row", i, i - 1)


def _step2_hex(b):
    if not (_is_hex(b["head"], 64) and _is_hex(b["public_key"], 64) and _is_hex(b["signature"], 128)):
        raise _Invalid("bad_hex")
    if not all(isinstance(k, str) and _is_hex(v, 64) for k, v in b["code_hashes"].items()):
        raise _Invalid("bad_hex")
    # Rows are reported by POSITION i (see "WHICH ROW IS BROKEN" above), never by r["seq"], which may be tampered.
    for i, r in enumerate(b["rows"], 1):
        fields = ["prev_hash", "hash", "commitment" if r["row_type"] == "attempt" else "response_commitment"]
        if not all(_is_hex(r[f], 64) for f in fields):
            raise _Invalid("bad_hex", i, i - 1)
        if "reveal" in r and not _is_hex(r["reveal"]["nonce"], 64):
            raise _Invalid("bad_hex", i, i - 1)


def _step3_chain(b):
    prev = ZERO_HASH
    for i, r in enumerate(b["rows"], 1):
        if r["seq"] != i:
            raise _Invalid("seq_gap", i, i)
        if r["session_id"] != b["session_id"]:
            raise _Invalid("session_mismatch", i, i)
        if r["prev_hash"] != prev:
            raise _Invalid("prev_mismatch", i, i)
        if row_hash(r) != r["hash"]:
            raise _Invalid("hash_mismatch", i, i)
        prev = r["hash"]


def _step4_reveals(b):
    n = len(b["rows"])
    for i, r in enumerate(b["rows"], 1):
        if "reveal" not in r:
            continue
        if r["row_type"] != "attempt":
            raise _Invalid("reveal_on_result", i, n)
        if r["decision"] != "allowed":
            raise _Invalid("reveal_on_blocked", i, n)
        payload = r["reveal"]["payload"].encode("utf-8")
        digest = hashlib.sha256(bytes.fromhex(r["reveal"]["nonce"]) + payload).hexdigest()
        if digest != r["commitment"] or len(payload) != r["bytes"]:
            raise _Invalid("reveal_mismatch", i, n)


def _step5_head(b):
    expected = b["rows"][-1]["hash"] if b["rows"] else ZERO_HASH
    if b["head"] != expected:
        raise _Invalid("head_mismatch", None, len(b["rows"]))


def _step6_signature(b):
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(b["public_key"]))
        key.verify(bytes.fromhex(b["signature"]), signed_message(b))
    except (InvalidSignature, ValueError):
        raise _Invalid("bad_signature", None, len(b["rows"]))


# ---------------------------------------------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------------------------------------------

def key_fingerprint(public_key_hex):
    """SHA-256 (hex) of the raw 32-byte Ed25519 public key, or None if the field is not a valid key encoding.
    Compare it with the fingerprint we publish to know WHO signed (see the module docstring)."""
    if not _is_hex(public_key_hex, 64):
        return None
    return hashlib.sha256(bytes.fromhex(public_key_hex)).hexdigest()


def verify_bytes(data):
    """Verify bundle bytes. Returns
    {"valid", "rows_checked", "broken_at_seq", "reason", "bundle_head", "signer_key_sha256"}.
    signer_key_sha256 is reported whenever the bundle's public_key is readable, even if the bundle is INVALID."""
    head = signer = None
    try:
        b = _step1_parse(data)
        head = b.get("head") if isinstance(b.get("head"), str) else None
        signer = key_fingerprint(b.get("public_key"))
        _structure(b)
        _step2_hex(b)
        _step3_chain(b)
        _step4_reveals(b)
        _step5_head(b)
        _step6_signature(b)
    except _Invalid as e:
        return {"valid": False, "rows_checked": e.rows_checked, "broken_at_seq": e.seq, "reason": e.reason,
                "bundle_head": head, "signer_key_sha256": signer}
    return {"valid": True, "rows_checked": len(b["rows"]), "broken_at_seq": None, "reason": None,
            "bundle_head": head, "signer_key_sha256": signer}


def verify_file(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return {"valid": False, "rows_checked": 0, "broken_at_seq": None, "reason": "parse_error",
                "bundle_head": None, "signer_key_sha256": None}
    return verify_bytes(data)


def main(argv):
    args = [a for a in argv if a != "--json"]
    if len(args) != 1:
        print("usage: python3 proof/verify.py BUNDLE.json [--json]", file=sys.stderr)
        return 2
    r = verify_file(args[0])
    if "--json" in argv:
        print(json.dumps(r, sort_keys=True))
    elif r["valid"]:
        print("VALID (signer key %s)" % r["signer_key_sha256"][:16])
    elif r["broken_at_seq"] is not None:
        print("INVALID: row %d %s" % (r["broken_at_seq"], r["reason"]))
    else:
        print("INVALID: %s" % r["reason"])
    return 0 if r["valid"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
