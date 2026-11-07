"""
checks/decode.py: peel off encodings, so a secret hidden as base64 / hex / %XX / rot13 / reversed text is seen.

THE PROBLEM
-----------
"Ossory" can leave as "T3Nzb3J5" (base64), "4f73736f7279" (hex), "%4F%73%73%6F%72%79" (URL encoding),
"Bffbel" (rot13), "yrossO" (reversed), or layers of these. A check that only looks at the literal text misses all
of them.

THE ANSWER: variants(s)
-----------------------
Return the original string plus every plausible decoding of it, each tagged with how it was produced (the tag goes
into the block `detail`, e.g. "found via base64"). Two stages:

  1. DECODE CLOSURE (up to MAX_DECODE_DEPTH layers): URL-decoding, HTML entities, \\uXXXX escapes, base64 tokens,
     hex tokens. A decoded result is kept only if it is mostly printable text, so random base64-looking English
     words ("revenues" is valid base64 alphabet) decode to junk bytes and are thrown away.
  2. CHEAP TRANSFORMS on every result of stage 1: rot13, reversed, and reversed rot13. These are NOT fed back into
     stage 1, which keeps the number of variants small (big Reader bodies would otherwise explode).

Every rule (canary, secrets, provenance) runs on every variant. Nothing here decides anything.
"""

import base64
import binascii
import codecs
import html
import re
import urllib.parse

from checks import config

# Base64 tokens: 8+ chars from the standard or URL-safe alphabet, optional padding. Also matches ordinary long
# words; that is fine, they fail the printable test below.
_B64_TOKEN = re.compile(r"[A-Za-z0-9+/_-]{8,}={0,2}")
# Hex: 4+ byte pairs, optionally separated by spaces/colons ("4f 73 73" or "4f:73:73").
_HEX_TOKEN = re.compile(r"(?:[0-9a-fA-F]{2}[\s:]?){4,}")


def _printable(raw):
    """bytes -> str if it looks like real text (>= 90% printable, at least 3 chars), else None."""
    try:
        s = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if len(s) < 3:
        return None
    ok = sum(1 for c in s if c.isprintable() or c in "\n\t ")
    return s if ok / len(s) >= 0.9 else None


def _b64(token):
    """Try standard and URL-safe base64 with padding repaired. Returns text or None."""
    t = token.rstrip("=")
    t = t.replace("-", "+").replace("_", "/")       # URL-safe alphabet -> standard
    t += "=" * (-len(t) % 4)                          # restore padding
    try:
        return _printable(base64.b64decode(t, validate=True))
    except (binascii.Error, ValueError):
        return None


def _one_layer(s):
    """Every single-step decoding of s, as (tag, text) pairs. Each decoder only fires if s looks encoded."""
    out = []
    if "%" in s or "+" in s:
        d = urllib.parse.unquote_plus(s)
        if d != s:
            out.append(("url", d))
    if "&" in s:
        d = html.unescape(s)
        if d != s:
            out.append(("html", d))
    if "\\u" in s or "\\x" in s:
        try:
            d = s.encode("latin-1", "backslashreplace").decode("unicode_escape")
            if d != s:
                out.append(("escape", d))
        except (UnicodeDecodeError, ValueError):
            pass
    # base64: every candidate token, plus the whole string with whitespace removed (catches "T3Nz b3J5").
    cands = set(m.group() for m in _B64_TOKEN.finditer(s))
    squashed = re.sub(r"\s+", "", s)
    if len(squashed) >= 8 and squashed != s:
        cands.add(squashed)
    for tok in cands:
        d = _b64(tok)
        if d is not None and d != tok:
            out.append(("base64", d))
    # hex
    for m in _HEX_TOKEN.finditer(s):
        digits = re.sub(r"[\s:]", "", m.group())
        if len(digits) % 2:
            digits = digits[:-1]
        try:
            d = _printable(bytes.fromhex(digits))
        except ValueError:
            d = None
        if d is not None:
            out.append(("hex", d))
    return out


def variants(s):
    """All views of s worth checking, as a list of (how, text). The first item is always ("plain", s)."""
    seen = {s}
    decoded = [("plain", s)]
    frontier = [("plain", s)]
    # Stage 1: decode closure, breadth first, MAX_DECODE_DEPTH layers deep.
    for _ in range(config.MAX_DECODE_DEPTH):
        nxt = []
        for how, text in frontier:
            for tag, d in _one_layer(text):
                if d not in seen:
                    seen.add(d)
                    item = (tag if how == "plain" else how + "+" + tag, d)
                    decoded.append(item)
                    nxt.append(item)
        if not nxt:
            break
        frontier = nxt
    # Stage 2: cheap transforms on every decoded view (not fed back into stage 1).
    out = list(decoded)
    for how, text in decoded:
        r13 = codecs.encode(text, "rot13")
        for tag, t in (("rot13", r13), ("reversed", text[::-1]), ("reversed+rot13", r13[::-1])):
            if t not in seen:
                seen.add(t)
                out.append((tag if how == "plain" else how + "+" + tag, t))
    return out
