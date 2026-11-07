"""Text normalisation and number, unit and period matching for the Validator. Pure functions.

A number is a maximal run of ASCII digits joined by separators: any single character between two digits that is
not a space, a letter, a dash or a marker such as % $ ( ), or a space before a group of three. The run counts only
if it parses strictly as 123, 1,234 or either with ".5"; anything else ("4 200", "1'234", "1,2345", "4,2", "1/2")
is ambiguous and yields no number. Before NFKC, characters that NFKC would turn into digits without being digits
(superscripts, fractions, circled numbers, non-Latin digits) and bidi controls become U+FFFD, and other invisible
format characters are removed, so normalisation never manufactures, splits or reorders a number. Each number
records its sign (ASCII hyphen, Unicode minus or dashes, also before the currency sign) and whether it is one end
of a range.
"""
import re
import unicodedata
from collections import namedtuple
from decimal import Decimal, InvalidOperation

MAX_DIGITS = 15
REPLACEMENT = "\ufffd"
DASHES = "-\u2212\u2010\u2011\u2012\u2013\u2014\u2015"
BIDI_CONTROLS = frozenset("\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")
_D = re.escape(DASHES)
# One character that joins two digit runs into one number-like cluster.
_GLUE = "[^\\sA-Za-z" + _D + "%$\u20ac\u00a3\u00a5()\\[\\]{}:;!?\"\u201c\u201d<>=+~\u2248&*|#@]"

_CLUSTER_RE = re.compile(
    r"(?<![\w.,])(?<![0-9\ufffd]" + _GLUE + r")"
    r"[0-9]+(?:(?:" + _GLUE + r"| (?=[0-9]{3}(?![0-9])))[0-9]+)*"
    r"(?![\d\ufffd])(?!" + _GLUE + r"[\d\ufffd])")
_STRICT_RE = re.compile(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?")
_CUR = r"(?:US\$|\$|USD ?|\u20ac|EUR ?|\u00a3|GBP ?)"
_CUR_BEFORE = re.compile(_CUR + r"$")
_NUM_BEFORE_DASH = re.compile(r"[0-9] ?(?:%|x|\u00d7)?$", re.IGNORECASE)
_OPENERS = "([{:;=~\u2248"
_PAREN_BEFORE = re.compile(r"\(%s?$" % _CUR)
_PAREN_AFTER = re.compile(r"(?: ?(?:%|x|\u00d7))?\)", re.IGNORECASE)
_MARK = r"(%|x|\u00d7|percent|per cent)"
_GAP_DASH = re.compile(r" ?(?:%%|x|\u00d7)? ?[%s] ?%s?" % (_D, _CUR), re.IGNORECASE)
_GAP_TO = re.compile(r" ?%s? (to|and) %s?" % (_MARK, _CUR), re.IGNORECASE)
_MARK_AFTER = re.compile(r" ?%s(?![A-Za-z])" % _MARK, re.IGNORECASE)
_FROM_BEFORE = re.compile(r"\bfrom %s?$" % _CUR, re.IGNORECASE)
_BETWEEN_BEFORE = re.compile(r"\bbetween %s?$" % _CUR, re.IGNORECASE)

_SCALE_WORDS = ("million|millions|mn|mm|mil|mln|m|billion|billions|bn|bln|b|thousand|thousands|k|trillion|"
                "trillions|tn|trn|t|crore|crores|cr|lakh|lakhs|lac|hundred")
_ANY_SCALE_AFTER = re.compile(r"(?:[A-Za-z]| (?:%s)\b)" % _SCALE_WORDS, re.IGNORECASE)
_MILLION_AFTER = re.compile(r" ?(?:million|mn|m)\b", re.IGNORECASE)
_BILLION_AFTER = re.compile(r" ?(?:billion|bn|b)\b", re.IGNORECASE)
_PERCENT_AFTER = re.compile(r" ?(?:%|percent\b|per cent\b|pct\b)", re.IGNORECASE)
_TIMES_AFTER = re.compile(r" ?(?:x|\u00d7|times)(?![A-Za-z])", re.IGNORECASE)
_MULTIPLE_BEFORE = re.compile(r"multiple of ?$", re.IGNORECASE)
_DOLLAR_BEFORE = re.compile(r"(?:\$|US\$|USD ?)[%s]?$" % _D, re.IGNORECASE)
_TTM_RE = re.compile(r"\b(?:ttm|ltm)\b|trailing twelve months", re.IGNORECASE)

# value: Decimal, or None if ambiguous. start: first character, sign included. num_start: first digit.
# range: one end of a range such as 5-7%, 3.5x to 6.0x or between 5% and 7%.
Token = namedtuple("Token", "value start num_start end range")


def _clean_char(ch):
    if ch < "\x80":
        return ch
    if ch in BIDI_CONTROLS:
        return REPLACEMENT
    cat = unicodedata.category(ch)
    if cat == "Cf":
        return ""  # zero-width space, joiners, soft hyphen, BOM: invisible, so not part of what is read
    folded = unicodedata.normalize("NFKC", ch)
    digitish = cat in ("Nd", "No", "Nl") or any("0" <= c <= "9" for c in folded)
    if digitish and not (cat == "Nd" and len(folded) == 1 and "0" <= folded <= "9"):
        return REPLACEMENT
    if not ch.isspace() and any(c.isspace() for c in folded):
        return REPLACEMENT  # spacing accents such as U+02D9: NFKC would put a space inside "4˙2"
    return ch


def normalize(text):
    """Digit look-alikes and bidi controls to U+FFFD, other invisible characters removed, then Unicode NFKC,
    then every whitespace run collapsed to one space."""
    cleaned = "".join(_clean_char(ch) for ch in text)
    return " ".join(unicodedata.normalize("NFKC", cleaned).split())


def to_decimal(value):
    """A claim value (int or float) as the Decimal it was written as."""
    try:
        return Decimal(value) if isinstance(value, int) else Decimal(repr(value))
    except (InvalidOperation, ValueError):
        return None


def _sign(text, s):
    """("neg" | "range" | "plain", start of the token) for the digits starting at s."""
    i = s
    m = _CUR_BEFORE.search(text, 0, i)
    if m:
        i = m.start()
    if i == 0 or text[i - 1] not in DASHES:
        return "plain", s
    d = i - 1
    j = d
    m = _CUR_BEFORE.search(text, 0, d)
    if m:
        j = m.start()
    if _NUM_BEFORE_DASH.search(text, 0, j):
        return "range", s
    if j == 0 or text[j - 1].isspace() or text[j - 1] in _OPENERS:
        return "neg", min(d, j)
    return "plain", s


def _mark(m):
    if m is None or m.group(1) is None:
        return None
    t = m.group(1).lower()
    return {"\u00d7": "x", "percent": "%", "per cent": "%"}.get(t, t)


def scan(text):
    """Every number written in text, as Tokens, in order."""
    toks = []
    for m in _CLUSTER_RE.finditer(text):
        s, e, raw = m.start(), m.end(), m.group()
        value = None
        digits = sum(c.isdigit() for c in raw)
        if _STRICT_RE.fullmatch(raw) and digits <= MAX_DIGITS:
            value = Decimal(raw.replace(",", ""))
        kind, start = _sign(text, s)
        if value is not None and kind == "neg":
            value = -value
        before = text[:start]
        if value is not None and _PAREN_BEFORE.search(before) and _PAREN_AFTER.match(text, e):
            value = None  # accounting negative or aside: ambiguous
        toks.append(Token(value, start, s, e, kind == "range"))
    out = list(toks)
    for k in range(len(toks) - 1):
        a, b = toks[k], toks[k + 1]
        is_range = bool(_GAP_DASH.fullmatch(text, a.end, b.start))
        g = _GAP_TO.fullmatch(text, a.end, b.start)
        if g and not is_range:
            ma, mb = _mark(g), _mark(_MARK_AFTER.match(text, b.end))
            if g.group(2).lower() == "to":
                is_range = not _FROM_BEFORE.search(text, 0, a.start) and mb is not None and ma in (None, mb)
            else:
                is_range = bool(_BETWEEN_BEFORE.search(text, 0, a.start))
        if is_range:
            out[k] = out[k]._replace(range=True)
            out[k + 1] = out[k + 1]._replace(range=True)
    return out


def find_numbers(text):
    """[(Decimal, start, end)] for every unambiguous number in text; start is the first digit."""
    return [(t.value, t.num_start, t.end) for t in scan(text) if t.value is not None]


def unit_consistent(text, start, end, unit):
    """Is the number at text[start:end] (digits only) written with a marker for this unit, and no other scale?"""
    after, before = text[end:], text[:start]
    if unit == "percent":
        return bool(_PERCENT_AFTER.match(after))
    if unit == "multiple":
        return bool(_TIMES_AFTER.match(after) or _MULTIPLE_BEFORE.search(before))
    if unit == "usd_millions":
        return bool(_MILLION_AFTER.match(after))
    if unit == "usd_billions":
        return bool(_BILLION_AFTER.match(after))
    if unit == "usd":
        return bool(_DOLLAR_BEFORE.search(before)) and not _ANY_SCALE_AFTER.match(after)
    if unit in ("count", "year"):
        raw = text[start:end]
        if "." in raw or (unit == "year" and not re.fullmatch(r"[0-9]{4}", raw)):
            return False
        return not (_PERCENT_AFTER.match(after) or _TIMES_AFTER.match(after) or _ANY_SCALE_AFTER.match(after)
                    or _DOLLAR_BEFORE.search(before))
    return False


def _inside(pattern, text, lo, hi):
    return any(lo <= m.start() and m.end() <= hi for m in pattern.finditer(text))


def period_in(text, period, lo=0, hi=None):
    """Is the period written in text[lo:hi]? Matches are found in the whole text, so a year cut out of a longer
    number does not count."""
    hi = len(text) if hi is None else hi
    if period == "":
        return True
    if period == "ttm":
        return _inside(_TTM_RE, text, lo, hi)
    return all(_inside(re.compile(r"(?<![0-9])%s(?![0-9])" % y), text, lo, hi) for y in period.split("-"))
