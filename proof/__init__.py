"""
proof/: make the ledger checkable by anyone, offline.

  verify.py   STANDALONE verifier (stdlib + cryptography only). python3 proof/verify.py BUNDLE [--json]
  export.py   ledger (SQLite) -> signed bundle file. python3 -m proof.export SESSION_ID
  tamper.py   demo button: one-byte edit of a COPY, then verify. python3 -m proof.tamper BUNDLE SEQ

This __init__ deliberately imports nothing, so `python3 proof/verify.py` never depends on the package.
"""
