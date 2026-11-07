"""
checks/secret_terms.py: RULE 2, "secret.<label>" (secret.codename, secret.buyer, secret.price, secret.person ...).

WHAT IT PROTECTS
----------------
session["confirmed_secrets"] is what the user confirmed on screen, e.g.
    [{"label": "buyer", "values": ["Ossory Capital Partners", "Ossory"]},
     {"label": "price", "values": ["$412 million"]}, ...]
None of these may leave, in ANY form. The rule id is "secret." + label, so the UI can say WHICH secret was
stopped (the demo's careless query is blocked as "secret.buyer").

HOW EACH SECRET VALUE IS MATCHED
--------------------------------
Word secrets ("Ossory", "Dana Whitcombe"):
    key = skeleton(value)  ->  "ossory", "danawhitcombe"
    For every decoded view of the payload, compute leet_forms(view) (skeleton + two de-leeted skeletons) and look
    for the key as a substring. That one test covers case, accents, look-alike letters, full-width letters,
    zero-width characters, spacing ("O s s o r y"), punctuation ("O.s.s.o.r.y"), leetspeak ("0ss0ry"); and
    because the views include decodings, also base64, hex, %XX, rot13 and reversed text.

Number secrets ("$412 million"):
    amounts = parse_amounts(value) -> {412000000}
    For every decoded view, parse_amounts(view); block if any value is EXACTLY equal (all formats, number words,
    "4 1 2 million"). No skeleton string match for numbers: "$41.2 million" would collide with "$412 million".

    Split numbers ("412" in one query, "million" in the next) are caught by provenance instead: "412" is a rare
    memo number, so it cannot leave on its own unless the web already showed it.

Split across queries (search/extract only):
    skeleton(all earlier queries) + skeleton(this query): block if a key occurrence STARTS in the earlier part and
    ENDS in this query, i.e. this query completes the secret. Occurrences entirely in old queries are ignored:
    those queries were already judged, and re-blocking every later query would inflate leak counts in the
    fake-only baseline modes.
"""

from checks import config
from checks.amounts import parse_amounts
from checks.text import leet_forms, skeleton, tokens


def _compile(session):
    """Turn confirmed_secrets into matchers: list of (label, word_keys, number_values, short_tokens)."""
    out = []
    for group in session.get("confirmed_secrets") or []:
        label = group["label"]
        keys, nums, short = set(), set(), set()
        for value in group.get("values") or []:
            amounts = parse_amounts(value)
            sk = skeleton(value)
            if amounts:
                # Number secret: compare by VALUE only. A skeleton match would be wrong here: "$41.2 million" and
                # "$412 million" have the same skeleton ("412million") once the decimal point is stripped.
                nums.update(amounts)
                continue
            if len(sk) >= config.MIN_SECRET_SKELETON:
                keys.add(sk)                    # substring match in skeletons
            elif sk:
                short.add(sk)                   # very short secret: whole-token match only (avoids false blocks)
        out.append((label, keys, nums, short))
    return out


def check(views, session, query_history):
    """
    views:          list of (how, text) from decode.variants over every string in the payload
    query_history:  (prefix_skeleton, current_skeleton) for search/extract, or None for reader jobs
    Returns None or (rule, detail). Detail names the label and the encoding, never the secret itself.
    """
    matchers = _compile(session)
    if not matchers:
        return None

    # Pre-compute what we need from each view once (not once per secret).
    prepared = []
    for how, text in views:
        prepared.append((how, leet_forms(text), None, text))  # amounts parsed lazily below

    amount_cache = {}

    def amounts_of(i):
        if i not in amount_cache:
            amount_cache[i] = set(parse_amounts(prepared[i][3]))
        return amount_cache[i]

    for label, keys, nums, short in matchers:
        rule = "secret." + label
        for i, (how, forms, _, text) in enumerate(prepared):
            # Word / string match inside skeletons (with leetspeak undone).
            for key in keys:
                if any(key in f for f in forms):
                    return rule, "matches a confirmed secret (%s) via %s" % (label, how)
            # Very short secrets: whole tokens only.
            if short and short & set(tokens(text)):
                return rule, "matches a confirmed secret (%s) via %s" % (label, how)
            # Numbers by exact value.
            if nums and nums & amounts_of(i):
                return rule, "matches a confirmed secret amount (%s) via %s" % (label, how)

        # Split across this session's queries.
        if query_history:
            prefix, current = query_history
            joined = prefix + current
            for key in keys:
                start = joined.find(key, max(0, len(prefix) - len(key) + 1))
                while start != -1 and start < len(prefix):
                    if start + len(key) > len(prefix):
                        return rule, "confirmed secret (%s) split across this session's queries" % label
                    start = joined.find(key, start + 1)
    return None
