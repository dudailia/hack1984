"""Re-judge a recorded red-team run with the frozen detector and append the result as a new run.

    python3 -m baseline.rejudge --results shared/results/results.json [--review PATH] [--run LABEL]

Reads the results file (FORMATS §9) and its review file, re-judges every recorded sent payload with checks.run_all
(baseline/judge.py) using each run's own session, and APPENDS a run labelled "<label> rejudged-frozen" with the same
commit and planner model. The original run, and every other run, are never edited or deleted. Prints, per mode,
the old count against the frozen count, and every payload where they disagree.

The session of each recorded run is rebuilt from the demo fixture (memo, confirmed secrets, approved terms) and
replayed like the Gate: each sent search is judged, then its public text is added. Limits, written into the run:
- canary: judged only if the run recorded its canary. Runs from before ilia-judge did not, so for them canary is
  not judged (secrets and provenance only).
- provenance: the public text is rebuilt from the stand-in's fixed pages, without the planted payload text (it is
  not recorded, and no attack file is opened). A memo word that only appeared in the planted text was public in the
  live run but not here, so provenance can only count more than the live Gate did, never fewer.
- presets are not recorded, so each search body uses the "general" preset (only topic fields differ).
- extract and reader payloads are not rebuilt; only searches are judged.
"""
import argparse
import copy
import json
import os
import shlex
import sys

from baseline import agent, judge, redteam
from fake_tavily import pages
from shared import guard

SUFFIX = " rejudged-frozen"
MAX_RESULTS = 10  # the Gate's search body asks for 10 (gate/tavily.py SEARCH_BASE)
NOTES_NO_CANARY = "canary not judged for runs that did not record their canary; secrets and provenance only"
NOTE_PROVENANCE = ("provenance approximate: public text rebuilt from the stand-in's fixed pages without the planted "
                   "payload text, so it can only over-count against the live Gate")
NOTE_PRESET = "search bodies rebuilt with the general preset (presets were not recorded)"


class RejudgeError(Exception):
    pass


def _fixture():
    spec = agent.load_demo_spec()
    memo = spec["memo"].rsplit("Ref: ", 1)[0]  # the fixture memo without this call's random canary line
    return memo, spec["confirmed_secrets"], spec["approved_public_terms"]


def stand_in_results(fixture_pages, query, first_id):
    """What the stand-in returns for a search, without the planted text; result ids continue from first_id."""
    out = []
    for i, page in enumerate(pages.search(fixture_pages, query, MAX_RESULTS)):
        r = pages.render(page, "")
        out.append({"result_id": "r_%02d" % (first_id + i), "title": r["title"], "url": r["url"],
                    "content": r["content"]})
    return out


def rejudge_record(detector, record, fixture_pages):
    memo, secrets, approved = _fixture()
    canary = record.get("canary")
    if canary:
        memo = memo + "Ref: %s\n" % canary
    session = detector.session(record.get("session_id") or "s_rejudge", record.get("mode"), memo,
                               canary or judge.unguessable_canary(), secrets, approved)
    judged, next_id = [], 1
    for query in record.get("sent_queries") or []:
        rule = session.judge_search(query, "general")
        results = stand_in_results(fixture_pages, query, next_id)
        next_id += len(results)
        session.record_search(query, "sent", results)
        judged.append({"kind": "search", "payload": query, "rule": rule, "frozen_rule": rule, "gate_rule": None,
                       "leak": judge.is_leak_rule(rule), "agree": True})
    rules = []
    for j in judged:
        if j["leak"] and j["rule"] not in rules:
            rules.append(j["rule"])
    out = {k: copy.deepcopy(record.get(k)) for k in ("mode", "payload_index", "session_id", "outcome",
                                                     "sent_queries", "blocked_queries", "seconds")}
    out.update({"canary": canary, "canary_judged": bool(canary), "sent_payloads": judged, "leaked": bool(rules),
                "leak_rules": rules, "fallback_leaked": bool(record.get("leaked")), "disagreements": 0})
    return out


def _pick_run(doc, label):
    if label is not None:
        runs = [r for r in doc["runs"] if r.get("label") == label]
        if not runs:
            raise RejudgeError("no run labelled %r" % label)
        return runs[-1]
    runs = [r for r in doc["runs"] if not str(r.get("label", "")).endswith(SUFFIX)
            and r.get("judge") != judge.JUDGE_NAME]
    if not runs:
        raise RejudgeError("no run judged by the fallback to re-judge")
    return runs[-1]


def review_coverage(review_text, records):
    """Sent queries that the review file does not list (each must appear as its JSON string)."""
    return [(r.get("mode"), r.get("payload_index"), q) for r in records for q in r.get("sent_queries") or []
            if json.dumps(q, ensure_ascii=False) not in review_text]


def rejudge(results_path, review_path=None, label=None, detector=None, command=None, out=sys.stdout):
    with open(results_path, encoding="utf-8") as f:
        doc = json.load(f)
    if not isinstance(doc, dict) or doc.get("v") != 1 or not isinstance(doc.get("runs"), list):
        raise RejudgeError("%s is not a v1 results file" % results_path)
    if doc.get("example") is not False:
        raise RejudgeError("%s is example data" % results_path)
    original_runs = copy.deepcopy(doc["runs"])
    source = _pick_run(doc, label)
    new_label = "%s%s" % (source.get("label"), SUFFIX)
    if any(r.get("label") == new_label for r in doc["runs"]):
        raise RejudgeError("a run labelled %r already exists; nothing appended" % new_label)
    records = source.get("attacks")
    if not records:
        raise RejudgeError("run %r has no per-attack records to re-judge" % source.get("label"))
    review_path = review_path or os.path.join(os.path.dirname(os.path.abspath(results_path)), "review.md")
    with open(review_path, encoding="utf-8") as f:
        missing = review_coverage(f.read(), records)
    if missing:
        raise RejudgeError("the review file does not list %d recorded payload(s), e.g. %r" % (len(missing),
                                                                                          missing[0]))
    detector = detector or judge.load_detector()  # no fallback
    fixture_pages = pages.load_pages()
    new_records = [rejudge_record(detector, r, fixture_pages) for r in records]

    modes = list((source.get("modes") or {}).keys()) or sorted({r["mode"] for r in new_records})
    notes = [NOTE_PROVENANCE, NOTE_PRESET]
    if not all(r["canary_judged"] for r in new_records):
        notes.insert(0, NOTES_NO_CANARY)
    run = {k: copy.deepcopy(v) for k, v in source.items() if k not in ("attacks", "modes", "judge", "label")}
    run.update({
        "label": new_label, "command": command or "python3 -m baseline.rejudge",
        "rejudged_from": {"label": source.get("label"), "judge": source.get("judge"),
                          "command": source.get("command")},
        "judge": judge.JUDGE_NAME, "detector": detector.info, "notes": notes,
        "modes": {m: {"leaked": sum(r["leaked"] for r in new_records if r["mode"] == m),
                      "runs": sum(1 for r in new_records if r["mode"] == m),
                      "errors": sum(1 for r in new_records if r["mode"] == m and r["outcome"] == "error")}
                  for m in modes},
        "attacks": new_records,
    })
    when = redteam._now()
    doc["runs"].append(run)
    if doc["runs"][:-1] != original_runs:
        raise RejudgeError("internal: an existing run changed; nothing written")
    doc["generated"] = when
    redteam._write_atomic(results_path, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    redteam._append_review(review_path, run, when)

    print("re-judged %r -> appended %r (%d records)" % (source.get("label"), new_label, len(new_records)), file=out)
    for note in notes:
        print("  note: " + note, file=out)
    old = source.get("modes") or {}
    for m in modes:
        print("  %-13s fallback %d of %d   frozen %d of %d" % (
            m, (old.get(m) or {}).get("leaked", 0), (old.get(m) or {}).get("runs", 0),
            run["modes"][m]["leaked"], run["modes"][m]["runs"]), file=out)
    disagree = [r for r in new_records if r["leaked"] != r["fallback_leaked"]]
    print("  disagreements: %d" % len(disagree), file=out)
    for r in disagree:
        print("    %s payload %s (%s): fallback %s, frozen %s" % (
            r["mode"], r["payload_index"], r["session_id"], "LEAK" if r["fallback_leaked"] else "no leak",
            "LEAK " + ", ".join(r["leak_rules"]) if r["leaked"] else "no leak"), file=out)
        for p in r["sent_payloads"]:
            print("      %s  rule=%s" % (json.dumps(p["payload"], ensure_ascii=False), p["rule"]), file=out)
    return run


def main(argv=None):
    guard.install_loopback_guard("baseline")  # reads files only; loopback only, no programs (invariant 1)
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser(prog="python3 -m baseline.rejudge", description=__doc__.splitlines()[0])
    ap.add_argument("--results", required=True, metavar="PATH")
    ap.add_argument("--review", metavar="PATH", default=None, help="default: review.md next to --results")
    ap.add_argument("--run", metavar="LABEL", default=None, help="default: the last run not judged by the detector")
    a = ap.parse_args(argv)
    try:
        rejudge(a.results, a.review, a.run, command="python3 -m baseline.rejudge " + shlex.join(argv))
    except (RejudgeError, judge.DetectorUnavailable, OSError, ValueError) as e:
        print("rejudge: %s" % e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
