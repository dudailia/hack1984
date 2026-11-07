"""
checks/benign_run.py: measure FALSE BLOCKS on the 30 ordinary questions in notes/BENIGN.md.

    python3 -m checks.benign_run notes/BENIGN.md            # human-readable table
    python3 -m checks.benign_run notes/BENIGN.md --json     # the false_blocks object for shared/results/results.json

WHAT IT DOES
------------
For each question:
  1. build a fresh Project Halyard session (same fixtures as the demo: shared/fixtures/halyard_session.json, the memo
     with its canary planted, memo_tokens computed exactly as the Gate will),
  2. put the question VERBATIM in a Tavily search body (the `general` preset), as if the Planner had sent the user's
     question unchanged. This is the strict case: real Planner queries are shorter and contain fewer words.
  3. call run_all(payload, session, "search") and record allow / block + rule.

Every question in BENIGN.md is something an analyst would really ask, so EVERY block is a false block. Report the
true number (notes/ANANT.md): if it is bad, fix, re-run, and report both runs. Never edit the questions.

Note: question 30 is followed by an editorial note in parentheses ("... while "Ossory" or "$412 million" must not")
that is for us, not part of the question; a trailing parenthetical is stripped before the question is sent.
"""

import json
import os
import re
import sys

from checks import memo_tokens, run_all

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CANARY = "kq7m2xw9tpa4hd3n"   # same demo canary as FORMATS.md; a random one would give the same result
_QUESTION = re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*$")
_TRAILING_NOTE = re.compile(r"\s*\([^()]*\)\s*$")


def load_questions(path):
    """[(number, question)] from a markdown numbered list. Indented lines continue the previous item."""
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = _QUESTION.match(line)
            if m:
                items.append([int(m.group(1)), m.group(2)])
            elif items and line.startswith((" ", "\t")) and line.strip():
                items[-1][1] += " " + line.strip()       # wrapped continuation line
            elif not line.strip() and items:
                pass
    return [(n, _TRAILING_NOTE.sub("", q)) for n, q in items]


def halyard_session():
    """The demo session, built the way the Gate builds it."""
    with open(os.path.join(_ROOT, "shared", "fixtures", "halyard_session.json"), encoding="utf-8") as f:
        fx = json.load(f)
    with open(os.path.join(_ROOT, fx["memo_file"]), encoding="utf-8") as f:
        memo = f.read()
    if _CANARY not in memo:
        memo = memo.rstrip("\n") + "\nRef: " + _CANARY + "\n"
    return {
        "session_id": "s_benign01", "created_at": "2026-11-07T00:00:00.000Z", "source": "fake",
        "mode": "doublethink", "canary": _CANARY, "confirmed_secrets": fx["confirmed_secrets"],
        "approved_public_terms": fx["approved_public_terms"],
        "memo_tokens": memo_tokens(memo, fx["approved_public_terms"]),
        "queries_sent": [], "public_text_received": [], "result_ids": {}, "urls_returned": [],
        "call_count": 0, "credits_used": 0,
    }


def search_payload(query):
    body = {"include_usage": True, "max_results": 10, "query": query, "search_depth": "basic", "topic": "general"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def run(path):
    """Run every question; return the report dict."""
    rows, by_rule = [], {}
    for n, q in load_questions(path):
        r = run_all(search_payload(q), halyard_session(), "search")
        rows.append({"n": n, "question": q, "decision": r["decision"], "rule": r["rule"], "detail": r["detail"]})
        if r["decision"] == "block":
            by_rule[r["rule"]] = by_rule.get(r["rule"], 0) + 1
    return {"blocked": sum(by_rule.values()), "total": len(rows), "by_rule": by_rule,
            "command": "python3 -m checks.benign_run notes/BENIGN.md", "questions": rows}


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    path = args[0] if args else os.path.join(_ROOT, "notes", "BENIGN.md")
    rep = run(path)
    if "--json" in argv:
        # Exactly the `false_blocks` object of FORMATS section 9 (without the per-question list).
        print(json.dumps({k: rep[k] for k in ("blocked", "total", "by_rule", "command")}, indent=2))
        return 0
    for row in rep["questions"]:
        mark = "BLOCK " + row["rule"] if row["decision"] == "block" else "ok"
        print("%2d  %-28s %s" % (row["n"], mark, row["question"]))
    print("\nFalse blocks: %d of %d  %s" % (rep["blocked"], rep["total"], rep["by_rule"] or ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
