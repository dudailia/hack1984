"""
checks/amounts.py: read every number in a text and turn it into one exact canonical value.

THE PROBLEM
-----------
The memo's price is "$412 million". It can leave as "412m", "$412M", "412 mln", "412mm", "412,000,000",
"412 000 000", "412.000.000", "0.412bn", "4.12e8", "412,000 thousand", "four hundred and twelve million",
"4 1 2 0 0 0 0 0 0"... String matching cannot catch all of these; comparing VALUES can.

THE ANSWER
----------
parse_amounts(text) -> list of decimal.Decimal values found in the text. Each digit number is multiplied by the
scale word that follows it (k, m, mn, mln, million, bn, billion, ...). Number words are parsed too. Decimal (not
float) is used so 0.412 * 1e9 is exactly 412000000, never 412000000.00000006.

canon(value) -> a stable string form ("412000000", "4.6"), used as a token by the provenance rule.

Tolerance: EXACT match (notes/ANANT.md: "exact match is the safe default for the demo"). So $412 million and
$412.5 million are different amounts.
"""

import re
from decimal import Decimal, InvalidOperation

from checks.text import fold

# ---- Scale words ----------------------------------------------------------------------------------------------
_SCALES = {
    "k": 10**3, "thousand": 10**3, "thousands": 10**3,
    "m": 10**6, "mm": 10**6, "mn": 10**6, "mln": 10**6, "mil": 10**6, "mio": 10**6, "million": 10**6,
    "millions": 10**6,
    "b": 10**9, "bn": 10**9, "bln": 10**9, "billion": 10**9, "billions": 10**9,
    "t": 10**12, "tn": 10**12, "trillion": 10**12, "trillions": 10**12,
}
# Longest words first so "million" wins over "m". The trailing \b means the scale must end a word, so
# "10 merchants" is 10, not 10 million.
_SCALE_ALT = "|".join(sorted(map(re.escape, _SCALES), key=len, reverse=True))

# ---- Digit numbers ----------------------------------------------------------------------------------------------
# Alternatives, tried in order:
#   412.000.000      dots as thousands separators (2+ groups, European style)
#   412,000,000      commas / underscores / spaces as thousands separators
#   412000000        plain digits
# then an optional decimal part, an optional exponent (4.12e8), an optional scale word.
#
# SAFETY (PR #4 review, Aayush): the gap before the scale word is BOUNDED: at most 3 spaces/dashes. The old
# "\s*-?\s*" let the regex engine try every way of splitting a long whitespace run between the two \s*, i.e.
# quadratic time: "412" + 100k spaces in an attacker's web page would stall the Gate for minutes. Longer gaps
# ("$412    million", "412\n\n\n\nmillion") are first shrunk by _collapse_gaps() in parse_amounts, so they still match.
_NUMBER = re.compile(
    r"(?<![\w.])"
    r"(?P<int>\d{1,3}(?:\.\d{3}){2,}|\d{1,3}(?:[,_ ]\d{3})+|\d+)"
    r"(?P<frac>\.\d+)?"
    r"(?:e(?P<exp>[+-]?\d{1,2}))?"
    r"(?:[\s-]{0,3}(?P<scale>" + _SCALE_ALT + r")\b)?"
)

# "4 1 2 0 0 0 0 0 0": three or more single digits separated by one space/dot/dash/underscore are glued back
# together before parsing. ("3.5" has only two digits, so decimals are untouched.)
_SPACED_DIGITS = re.compile(r"(?<![\d.])\d(?:[ .\-_]\d(?![\d]))+")


def _glue_spaced_digits(text):
    def glue(m):
        g = m.group()
        return re.sub(r"\D", "", g) if len(re.sub(r"\D", "", g)) >= 3 else g
    return _SPACED_DIGITS.sub(glue, text)


# ---- Number words -------------------------------------------------------------------------------------------
_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen".split())}
_TENS = {w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())}
_WORD_SCALES = {"thousand": 10**3, "million": 10**6, "billion": 10**9, "trillion": 10**12}


def _word_numbers(text):
    """Parse runs like "four hundred and twelve million" -> 412000000. Standard algorithm: `current` builds the
    part below the next scale word, `total` accumulates finished scale groups."""
    words = re.findall(r"[a-z]+", text.replace("-", " "))
    found = []
    total = current = 0
    in_number = False
    for w in words + ["<end>"]:
        if w in _UNITS:
            current += _UNITS[w]
            in_number = True
        elif w in _TENS:
            current += _TENS[w]
            in_number = True
        elif w == "hundred" and in_number:
            current = (current or 1) * 100
        elif w.rstrip("s") in _WORD_SCALES and in_number:
            total += (current or 1) * _WORD_SCALES[w.rstrip("s")]
            current = 0
        elif w == "and" and in_number:
            continue  # "four hundred AND twelve" keeps the run going
        else:
            if in_number:
                found.append(Decimal(total + current))
            total = current = 0
            in_number = False
    return found


_WHITESPACE_RUN = re.compile(r"\s+")
_SPACE_DASH_RUN = re.compile(r"[ -]{4,}")


def _collapse_gaps(t):
    """Shrink every gap so the BOUNDED scale separator in _NUMBER ([\\s-]{0,3}) can still reach the scale word.

    1. any run of whitespace (spaces, tabs, newlines) -> one space:   "412\\n\\n\\n\\nmillion" -> "412 million"
    2. any remaining run of 4+ spaces/dashes          -> " - ":       "412 -- -- million"  -> "412 - million"
    Both are single-pass, character-class regexes (no nesting, no alternation): linear time, so hostile input
    cannot make them slow. Step 2 only fires on 4+ characters, so ordinary "5 - 100" and "2025-2030" are unchanged.

    Why this exists (PR #4 re-review, Aayush): bounding the separator fixed the quadratic backtracking, but on its
    own it made "$412    million" parse as plain 412, so secret.price did not fire. Collapsing first restores the
    old "any gap" behaviour while keeping the regex linear.
    """
    return _SPACE_DASH_RUN.sub(" - ", _WHITESPACE_RUN.sub(" ", t))


def parse_amounts(text):
    """Every numeric value in text, as Decimal. Duplicates are fine; callers use set membership."""
    t = _glue_spaced_digits(_collapse_gaps(fold(text)))
    out = []
    for m in _NUMBER.finditer(t):
        digits = re.sub(r"[,_ .]", "", m.group("int"))
        try:
            v = Decimal(digits + (m.group("frac") or ""))
        except InvalidOperation:
            continue
        if m.group("exp"):
            v = v.scaleb(int(m.group("exp")))
        if m.group("scale"):
            v = v * _SCALES[m.group("scale")]
        out.append(v)
    out.extend(_word_numbers(t))
    return out


def canon(v):
    """Stable text for a Decimal: no exponent, no trailing zeros. canon(Decimal("412000000.000")) == "412000000"."""
    v = v.normalize()
    s = format(v, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s
