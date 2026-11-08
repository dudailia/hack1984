"""Stand-in for proof.verify.verify_bytes in app tests: same result shape, checks only the hash chain.

    verifier(signer=True) -> fn(bundle_bytes) -> {"valid", "rows_checked", "broken_at_seq", "reason", "bundle_head",
                                                  "signer_key_sha256"}

Checks only that each row's hash is sha256 of the canonical row without `hash`, and head = last hash. Not a real
verifier; the real one (proof.verify) is used in VerifyRealProofTest.
"""
import hashlib
import json

SIGNER = "ab" * 32


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def check(data):
    try:
        b = json.loads(data)
    except ValueError:
        return {"valid": False, "rows_checked": 0, "broken_at_seq": None, "reason": "parse_error", "bundle_head": None}
    checked = 0
    for row in b["rows"]:
        body = {k: v for k, v in row.items() if k != "hash"}
        checked += 1
        if hashlib.sha256(canonical(body)).hexdigest() != row["hash"]:
            return {"valid": False, "rows_checked": checked, "broken_at_seq": row["seq"], "reason": "hash_mismatch",
                    "bundle_head": b.get("head")}
    if not b["rows"] or b["rows"][-1]["hash"] != b.get("head"):
        return {"valid": False, "rows_checked": checked, "broken_at_seq": None, "reason": "head_mismatch",
                "bundle_head": b.get("head")}
    return {"valid": True, "rows_checked": checked, "broken_at_seq": None, "reason": None, "bundle_head": b["head"]}


def verifier(signer=True):
    def verify_bytes(data):
        r = check(data)
        if signer:
            r["signer_key_sha256"] = SIGNER
        return r
    return verify_bytes
