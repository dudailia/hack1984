"""Text normalisation and number, unit and period matching for the Validator. Pure functions."""
import re
import unicodedata
from decimal import Decimal, InvalidOperation

_NUMBER_RE = re.compile(r"(?<![\w.,])-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
_SCALE_AFTER = re.compile(r"\s?(?:million|mn|m|billion|bn|b|thousand|k)\b", re.IGNORECASE)
_MILLION_AFTER = re.compile(r"\s?(?:million|mn|m)\b", re.IGNORECASE)
_BILLION_AFTER = re.compile(r"\s?(?:billion|bn|b)\b", re.IGNORECASE)
_PERCENT_AFTER = re.compile(r"\s?(?:%|percent\b|per cent\b|pct\b)", re.IGNORECASE)
_TIMES_AFTER = re.compile(r"\s?(?:x|×|times)(?![A-Za-z])", re.IGNORECASE)
_MULTIPLE_BEFORE = re.compile(r"multiple of\s?$", re.IGNORECASE)
_DOLLAR_BEFORE = re.compile(r"(?:\$|US\$|USD\s?)$", re.IGNORECASE)
_TTM_RE = re.compile(r"\b(?:ttm|ltm)\b|trailing twelve months", re.IGNORECASE)


def normalize(text):
    """Unicode NFKC, then every whitespace run collapsed to one space, ends stripped."""
    return " ".join(unicodedata.normalize("NFKC", text).split())


def to_decimal(value):
    """A claim value (int or float) as the Decimal it was written as."""
    try:
        return Decimal(value) if isinstance(value, int) else Decimal(repr(value))
    except (InvalidOperation, ValueError):
        return None


def find_numbers(text):
    """[(Decimal, start, end)] for every number written in text, thousands separators removed."""
    return [(Decimal(m.group().replace(",", "")), m.start(), m.end()) for m in _NUMBER_RE.finditer(text)]


def unit_consistent(text, start, end, unit):
    """Is the number at text[start:end] written with a marker for this unit?"""
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
        return bool(_DOLLAR_BEFORE.search(before)) and not _SCALE_AFTER.match(after)
    if unit in ("count", "year"):
        return not (_PERCENT_AFTER.match(after) or _TIMES_AFTER.match(after) or _SCALE_AFTER.match(after)
                    or _DOLLAR_BEFORE.search(before))
    return False


def _year_in(text, year):
    return re.search(r"(?<!\d)%s(?!\d)" % year, text) is not None


def period_in(text, period):
    if period == "":
        return True
    if period == "ttm":
        return _TTM_RE.search(text) is not None
    return all(_year_in(text, y) for y in period.split("-"))
