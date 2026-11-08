"""Stand-in for proof/verify.py in app tests (proof/ is Anant's and not merged): same CLI and --json shape.

    python3 fake_verify.py [--no-signer] BUNDLE.json --json

Checks only that each row's hash is sha256 of the canonical row without `hash`, and head = last hash.
Exit 0 if valid, 1 if not. Not a real verifier.
"""
import hashlib
import json
import sys

SIGNER = "ab" * 32


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def check(path):
    with open(path, "rb") as f:
        data = f.read()
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


def main(argv):
    signer = "--no-signer" not in argv
    path = [a for a in argv if not a.startswith("--")][0]
    r = check(path)
    if signer:
        r["signer_key_sha256"] = SIGNER
    if "--json" in argv:
        print(json.dumps(r, sort_keys=True))
    return 0 if r["valid"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
