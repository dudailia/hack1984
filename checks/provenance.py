"""
checks/provenance.py: RULE 3, "provenance.rare_term" and "provenance.split". Also memo_tokens(), which the Gate
calls once per session.

WHY THIS RULE EXISTS
--------------------
Rule 2 only protects what the user CONFIRMED. People forget things: a second contact's surname, an internal deal
number, the meeting date. Provenance is the safety net for everything else that is unusual in the memo.

THE IDEA IN ONE LINE
--------------------
A rare word or number from the memo may only leave if the web already showed it to us this session.
  "rare"           = not a stopword, not in wordlists.COMMON, not part of an approved public term ("Brackwater
                     Payments"), and for numbers: >= 100 and not a year. Plus canonical amounts ("412000000").
  "web showed it"  = it appears in session["public_text_received"] (search results the Gate already got back).
If the web already printed "Renwick", repeating "Renwick" reveals nothing about the memo. If it did not, the only
place the query could have got it from is the memo, so block.

TWO PARTS
---------
memo_tokens(memo, approved_public_terms)  -> sorted list of rare tokens. The Gate calls this ONCE at session
    creation and stores it in session["memo_tokens"]. (FORMATS section 4 says the checks name this function.)
    The memo itself is not in the session; only these tokens are.

check(...) at every outbound attempt:
  a. TOKEN MATCH: tokens (and amounts) of every decoded view of the scanned text  ∩  rare memo tokens not yet
     seen in public text  ->  provenance.rare_term.
  b. SKELETON MATCH (search/extract only): rare tokens of >= 5 chars searched in the skeleton of this query
     ("R e n w i c k" -> "renwick")  ->  provenance.rare_term; and in skeleton(earlier queries + this query) for an
     occurrence that this query completes ("payments renw" then "ick growth")  ->  provenance.split.
     Skeleton matching is NOT done on reader bodies: they hold whole web pages, and gluing all words together
     there would create accidental matches ("to bias" -> "tobias").

WHAT IS SCANNED
---------------
search / extract: the `query` string only (domains and URLs are checked by shape.py; extract URLs must be ones the
                  Gate itself returned).
reader:           every string in the Anthropic body (system prompt, public query, documents). For this to work the
                  Gate must append each result's title + content to public_text_received BEFORE it builds the
                  reader request, so the documents count as "seen".
"""

from decimal import Decimal, InvalidOperation

from checks import config
from checks.amounts import canon, parse_amounts
from checks.decode import variants
from checks.text import skeleton, sub_tokens, tokens
from checks.wordlists import COMMON, STOPWORDS


def _is_number(tok):
    try:
        Decimal(tok)
        return True
    except InvalidOperation:
        return False


def _rare_number(tok):
    """412 is rare; 16 (a day), 2025 (a year) and 4.6 are not. Rule: at least 3 significant digits, not a year."""
    digits = tok.replace(".", "").lstrip("0")
    if len(digits) < 3:
        return False
    v = Decimal(tok)
    if v == v.to_integral_value() and 1900 <= v <= 2100:
        return False
    return True


def memo_tokens(memo, approved_public_terms):
    """Rare tokens of the memo, sorted (so the result is deterministic and the session JSON is stable)."""
    approved = set()
    for term in approved_public_terms or []:
        approved.update(tokens(term))
    rare = set()
    for t in tokens(memo):
        if t in approved or t in STOPWORDS or t in COMMON:
            continue
        if _is_number(t):
            if _rare_number(t):
                rare.add(t)
        elif t.isalpha():
            if len(t) >= 3:
                rare.add(t)              # names, codenames: "halyard", "ossory", "whitcombe"
        elif len(t) >= 4:
            rare.add(t)                  # mixed letters+digits: reference codes, the canary
    # Amounts in canonical form, so "$412 million" in the memo also protects "412,000,000" and "0.412bn".
    for a in parse_amounts(memo):
        if a >= 1000:
            rare.add(canon(a))
    return sorted(rare)


def terms_of(text):
    """Everything in `text` that could equal a memo token: tokens, their letter/digit pieces, canonical amounts."""
    out = set()
    for t in tokens(text):
        out.add(t)
        out.update(sub_tokens(t))
    out.update(canon(a) for a in parse_amounts(text))
    return out


def _seen(session):
    """Tokens of all public text the Gate has received this session."""
    seen = set()
    for txt in session.get("public_text_received") or []:
        seen |= terms_of(txt)
    return seen


def check(strings, session, kind, query_history):
    """
    strings:        the payload strings to scan (the query for search/extract; all strings for reader)
    query_history:  (prefix_skeleton, current_skeleton) for search/extract, or None for reader jobs
    Returns None or (rule, detail).
    """
    rare = set(session["memo_tokens"])        # KeyError if the Gate forgot it -> run_all raises -> fail closed
    if not rare:
        return None
    unseen = rare - _seen(session)
    if not unseen:
        return None

    # a. token match on every decoded view
    for s in strings:
        for how, text in variants(s):
            hit = terms_of(text) & unseen
            if hit:
                return ("provenance.rare_term",
                        "%d rare memo term(s) not seen in public text (%s)" % (len(hit), how))

    # b. skeleton match: spaced-out words inside this query, and words split across queries
    if query_history:
        prefix, current = query_history
        long_unseen = [t for t in unseen if len(t) >= config.MIN_SPLIT_TOKEN]
        for t in long_unseen:
            if t in current:
                return "provenance.rare_term", "rare memo term written with spacing or punctuation"
        joined = prefix + current
        for t in long_unseen:
            start = joined.find(t, max(0, len(prefix) - len(t) + 1))
            if start != -1 and start < len(prefix) < start + len(t):
                return "provenance.split", "rare memo term split across this session's queries"
    return None


def query_skeletons(session, query):
    """(skeleton of every earlier query joined, skeleton of this query): the input to every split check."""
    prefix = "".join(skeleton(q) for q in session.get("queries_sent") or [])
    return prefix, skeleton(query)
