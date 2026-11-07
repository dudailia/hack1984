"""
proof/tamper.py: the demo's "Tamper one byte" button.

    python3 -m proof.tamper bundles/s_dtreal1.json 3        # prints the proof_result JSON for the tampered copy

WHAT IT DOES
------------
Takes a COPY of a bundle, changes exactly ONE byte inside row <seq>, writes the copy next to the original
(<name>.tampered-<seq>.json), and verifies the copy. The original bundle and the ledger are never touched
(FORMATS section 11, POST /api/tamper).

WHICH BYTE
----------
The first hex character of that row's commitment (attempt) or response_commitment (result), changed to a different
hex digit. That keeps the file valid canonical JSON with valid lowercase hex, so the verifier gets past parsing
and format checks and fails exactly where the audience should see it: "hash_mismatch" at that row. The UI then
marks that row and every row after it as broken (each later row's prev_hash depends on it).
"""

import json
import os
import sys

from proof.verify import canonical_json, verify_bytes


def tamper_bytes(data, seq):
    """Return a copy of bundle bytes with ONE byte changed inside row `seq`."""
    obj = json.loads(data)
    rows = [r for r in obj["rows"] if r.get("seq") == seq]
    if not rows:
        raise ValueError("no row with seq %d" % seq)
    row = rows[0]
    field = "commitment" if row["row_type"] == "attempt" else "response_commitment"
    old = row[field]
    row[field] = ("1" if old[0] == "0" else "0") + old[1:]
    out = canonical_json(obj)
    # Guarantee the promise on the button: same length, exactly one byte different.
    if len(out) != len(data) or sum(a != b for a, b in zip(out, data)) != 1:
        raise RuntimeError("tamper did not produce a single-byte edit")
    return out


def tamper_and_verify(bundle_path, seq):
    """Write the tampered copy and return the `proof_result` event data (FORMATS section 10)."""
    with open(bundle_path, "rb") as f:
        data = f.read()
    bad = tamper_bytes(data, seq)
    root, ext = os.path.splitext(bundle_path)
    with open("%s.tampered-%d%s" % (root, seq, ext or ".json"), "wb") as f:
        f.write(bad)
    r = verify_bytes(bad)
    return {"bundle_head": json.loads(data)["head"], "tampered": True, "tampered_seq": seq, "valid": r["valid"],
            "broken_at_seq": r["broken_at_seq"], "rows_checked": r["rows_checked"], "reason": r["reason"]}


def main(argv):
    if len(argv) != 2:
        print("usage: python3 -m proof.tamper BUNDLE.json SEQ", file=sys.stderr)
        return 2
    print(json.dumps(tamper_and_verify(argv[0], int(argv[1])), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
