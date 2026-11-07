"""Canonical JSON, hashes, commitments and time (shared/FORMATS.md §0 and §7)."""
import datetime
import hashlib
import json
import os

ZERO_HASH = "0" * 64
NONCE_BYTES = 32


def canonical_json(obj) -> bytes:
    """Sorted keys, UTF-8, no whitespace, no trailing newline (FORMATS §0)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def new_nonce() -> bytes:
    return os.urandom(NONCE_BYTES)


def commitment(nonce: bytes, payload: bytes) -> str:
    """SHA-256(nonce || payload), lowercase hex."""
    if not isinstance(nonce, (bytes, bytearray)) or len(nonce) != NONCE_BYTES:
        raise ValueError("nonce must be exactly 32 bytes")
    if not isinstance(payload, (bytes, bytearray)):
        raise ValueError("payload must be bytes")
    return sha256_hex(bytes(nonce) + bytes(payload))


def _refuse_floats(value):
    if isinstance(value, float):
        raise ValueError("floats are not allowed in ledger rows")
    if isinstance(value, dict):
        for v in value.values():
            _refuse_floats(v)
    elif isinstance(value, list):
        for v in value:
            _refuse_floats(v)


def row_hash(row: dict) -> str:
    """SHA-256 of the canonical row without its `hash` field."""
    body = {k: v for k, v in row.items() if k != "hash"}
    _refuse_floats(body)
    return sha256_hex(canonical_json(body))


def format_time(dt: datetime.datetime) -> str:
    """UTC ISO 8601 with milliseconds (truncated) and Z."""
    if dt.tzinfo is None:
        raise ValueError("naive datetime")
    u = dt.astimezone(datetime.timezone.utc)
    return u.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (u.microsecond // 1000)


def utc_now() -> str:
    return format_time(datetime.datetime.now(datetime.timezone.utc))
