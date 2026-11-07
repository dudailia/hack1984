"""
checks/text.py: turn any text into a boring, comparable form.

THE PROBLEM
-----------
An attacker (or a careless model) can write "Ossory" a hundred ways: "OSSORY", "O s s o r y", "Ｏｓｓｏｒｙ"
(full-width), "Оssory" (first letter is Cyrillic), "Össory", "0ss0ry", "Os<zero-width-space>sory". A plain
`"ossory" in text` check misses all of them.

THE ANSWER
----------
Every check compares NORMALISED text, never raw text:

  fold(s)       Unicode NFKC (full-width -> normal), drop invisible characters, casefold (lowercase that also
                handles German ß etc.), strip accents (Ö -> o), map common look-alike Cyrillic/Greek letters to
                Latin ones.
  skeleton(s)   fold(s), then keep ONLY a-z and 0-9. Spacing and punctuation disappear, so "O.s.s.o.r.y" and
                "O s s o r y" both become "ossory".
  leet_forms(s) skeleton(s) plus two "leetspeak undone" versions ("0ss0ry" -> "ossory"). There are two because
                "1" can mean "l" or "i".
  tokens(s)     the words and numbers in fold(s), used by the provenance rule.

Nothing here knows about secrets or rules; it is pure text plumbing, shared by every rule.
"""

import re
import unicodedata

# ---- Invisible characters ----------------------------------------------------------------------------------
# Zero-width space/joiners, word joiner, BOM, soft hyphen, Mongolian vowel separator. They render as nothing, so
# "Os​sory" looks like "Ossory" on screen. NFKC does NOT remove them, so we delete them explicitly.
_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿­᠎⁡⁢⁣⁤"), None)

# ---- Look-alike letters (homoglyphs) -----------------------------------------------------------------------
# Lowercase Cyrillic and Greek letters that look like Latin letters. Applied AFTER casefold, so only lowercase
# keys are needed. Not a complete Unicode confusables table, but it covers the letters you can actually type to
# disguise an English word.
_HOMOGLYPHS = str.maketrans({
    # Cyrillic
    "а": "a", "в": "b", "е": "e", "ё": "e", "к": "k", "м": "m", "н": "h", "о": "o", "р": "p", "с": "c",
    "т": "t", "у": "y", "х": "x", "і": "i", "ї": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "ӏ": "l", "ԛ": "q",
    "ԝ": "w", "ь": "b", "г": "r", "п": "n",
    # Greek
    "α": "a", "β": "b", "ε": "e", "η": "n", "ι": "i", "κ": "k", "ν": "v", "ο": "o", "ρ": "p", "τ": "t",
    "υ": "u", "χ": "x", "ζ": "z", "μ": "u", "ω": "w",
    # Latin oddities
    "ı": "i", "ɡ": "g", "ł": "l", "ø": "o", "đ": "d", "ħ": "h",
})

# ---- Leetspeak ---------------------------------------------------------------------------------------------
# Applied to the folded text BEFORE punctuation is stripped (because "@", "$", "!" and "|" are punctuation).
# Two tables because "1" is used for both "l" and "i".
_LEET_L = str.maketrans({"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "9": "g",
                         "@": "a", "$": "s", "!": "i", "|": "l", "+": "t"})
_LEET_I = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "9": "g",
                         "@": "a", "$": "s", "!": "i", "|": "i", "+": "t"})

_NOT_ALNUM = re.compile(r"[^a-z0-9]+")


def fold(s):
    """Normalise text so look-alikes compare equal. Keeps spacing and punctuation (tokens() needs them)."""
    s = unicodedata.normalize("NFKC", s)            # full-width "Ｏ" -> "O", ligatures "ﬁ" -> "fi", etc.
    s = s.translate(_INVISIBLE)                      # delete zero-width characters
    s = s.casefold()                                 # stronger lowercase
    s = unicodedata.normalize("NFKD", s)             # split "ö" into "o" + combining diaeresis ...
    s = "".join(c for c in s if not unicodedata.combining(c))  # ... and drop the diaeresis
    return s.translate(_HOMOGLYPHS)                  # Cyrillic "о" -> Latin "o"


def skeleton(s):
    """fold(s) with only [a-z0-9] kept: "O.s.s.o.r.y Capital" -> "ossorycapital"."""
    return _NOT_ALNUM.sub("", fold(s))


def leet_forms(s):
    """The skeleton plus its two de-leeted versions: {"0ss0ry"} -> {"0ss0ry", "ossory"}.

    Only used to match confirmed secrets that are WORDS. Numbers are compared by value instead (amounts.py),
    because de-leeting turns "412" into "a1l"/"aie" and would destroy them.
    """
    f = fold(s)
    return {_NOT_ALNUM.sub("", f), _NOT_ALNUM.sub("", f.translate(_LEET_L)), _NOT_ALNUM.sub("", f.translate(_LEET_I))}


# ---- Tokens (for the provenance rule) ------------------------------------------------------------------------
# A token is a run of letters/digits, optionally with one decimal part ("4.6"). Thousands commas between digits are
# removed first so "412,000,000" is ONE token "412000000", not three ("412", "000", "000"): otherwise "$1,412,000"
# would contain the token "412" and look like the memo's price.
_THOUSANDS_COMMA = re.compile(r"(?<=\d),(?=\d{3}\b)")
_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
_SPLIT_ALPHA_DIGIT = re.compile(r"[a-z]+|[0-9]+(?:\.[0-9]+)?")


def tokens(s):
    """Ordered list of word/number tokens: "Tobias Renwick-Ash, $412m" -> ["tobias", "renwick", "ash", "412m"]."""
    return _TOKEN.findall(_THOUSANDS_COMMA.sub("", fold(s)))


def sub_tokens(tok):
    """Split a mixed token at letter/digit boundaries: "412m" -> ["412", "m"]. Used on the OUTBOUND side only, so
    "412m" in a query is still recognised as containing the memo number "412"."""
    return _SPLIT_ALPHA_DIGIT.findall(tok)
