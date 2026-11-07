"""Usefulness on the 30 benign questions (SPEC "Measurements" 3), with cost and time per question (4).

    python3 -m eval.usefulness --app-url 'http://127.0.0.1:8700/ui/index.html?token=…' --limit 3   # smoke
    python3 -m eval.usefulness --app-url 'http://127.0.0.1:8700/ui/index.html?token=…'             # full run
    python3 -m eval.usefulness --dry-run                                                          # sends nothing

Each question in notes/BENIGN.md goes to POST /api/run on app/run.py (mode doublethink, source real), one at a
time. The run's events are read from /events until run_done. Per question it records: answered with at least one
validated cited number (yes/no), Tavily credits, seconds, and blocked count.

"Validated cited number" means an `answer` item whose value is a number, whose quote is non-empty, whose source
has a result_id and URL, and which matches a claim the Validator kept in this run's `reader_claims` (same value,
quote and document). An answer whose run_started echoes a different question than the one sent does not count.

Writes the per-question records to shared/results/usefulness/<time>.json and appends one run with the
`usefulness` and `cost` fields to shared/results/results.json (FORMATS §9). A --limit run is a smoke run: it writes
the details file but appends to results.json only with --record-partial.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

from eval import cost as cost_mod
from eval import results as results_mod
from eval.app_client import AppClient, AppError, parse_app_url
from eval.loopback import REPO, app_port, install_audit_hook, planner_model

BENIGN_PATH = os.path.join("notes", "BENIGN.md")
MODE = "doublethink"


# ---------------------------------------------------------------- questions

def parse_benign(text):
    """Numbered list items, continuation lines joined. A trailing parenthetical note after the '?' (question 30's
    instruction to testers) is not part of the question."""
    items, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^(\d+)\.\s+(.*)$", line)
        if m:
            cur = [int(m.group(1)), m.group(2).strip()]
            items.append(cur)
        elif cur is not None and line.startswith((" ", "\t")) and line.strip():
            cur[1] += " " + line.strip()
        else:
            cur = None
    out = []
    for n, q in items:
        q = re.sub(r"(\?)\s*\(.*\)\s*$", r"\1", q)
        out.append((n, q))
    return out


def load_questions(path=None):
    path = path or os.path.join(REPO, BENIGN_PATH)
    with open(path, encoding="utf-8") as f:
        qs = parse_benign(f.read())
    if [n for n, _ in qs] != list(range(1, len(qs) + 1)):
        raise ValueError("%s: questions are not numbered 1..N" % path)
    return qs


# ---------------------------------------------------------------- scoring

def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def cited_numbers(events):
    """Count answer items that are validated, cited numbers (see module doc)."""
    kept = set()
    answer = None
    for e in events:
        d = e.get("data") or {}
        if e.get("type") == "reader_claims":
            for c in d.get("kept") or []:
                if isinstance(c, dict) and _num(c.get("value")):
                    kept.add((float(c["value"]), c.get("quote"), c.get("document_id")))
        elif e.get("type") == "answer":
            answer = d
    if not answer:
        return 0
    n = 0
    for need in answer.get("needs") or []:
        for it in (need or {}).get("items") or []:
            if not isinstance(it, dict) or not _num(it.get("value")):
                continue
            quote, src = it.get("quote"), it.get("source") or {}
            if not (isinstance(quote, str) and quote.strip()):
                continue
            if not (isinstance(src, dict) and src.get("result_id") and src.get("url")):
                continue
            if (float(it["value"]), quote, src["result_id"]) in kept:
                n += 1
    return n


def score(n, question, session_id, events, wall_seconds, source, error=None):
    """One per-question record."""
    started = next((e["data"] for e in events if e.get("type") == "run_started"), None) or {}
    done = next((e["data"] for e in events if e.get("type") == "run_done"), None)
    blocked_events = sum(1 for e in events if e.get("type") == "blocked")
    if error is None and started:
        if started.get("question") != question:
            error = "app_ignored_question"
        elif started.get("mode") != MODE or started.get("source") != source:
            error = "wrong_mode_or_source"
    cited = cited_numbers(events) if error is None else 0
    done = done or {}
    return {
        "n": n,
        "question": question,
        "session_id": session_id,
        "outcome": done.get("outcome"),
        "answered_with_cited_number": cited >= 1,
        "cited_numbers": cited,
        "credits": done.get("credits_total") if _num(done.get("credits_total")) else None,
        "seconds": done.get("seconds") if _num(done.get("seconds")) else round(wall_seconds, 1),
        "wall_seconds": round(wall_seconds, 1),
        "blocked": done.get("blocked") if isinstance(done.get("blocked"), int) else blocked_events,
        "run_done": bool(done),
        "error": error,
    }


# ---------------------------------------------------------------- running

def run_body(question, source):
    # FORMATS §11 defines mode, source, plant_careless. `question` is the one addition eval needs:
    # app/run.py must accept it (Aayush). score() refuses a run whose run_started shows another question.
    return {"mode": MODE, "source": source, "plant_careless": False, "question": question}


def run_questions(client, questions, source, timeout, log=print, clock=time.monotonic):
    records = []
    for n, q in questions:
        t0 = clock()
        sid, events, err = None, [], None
        try:
            sid = client.start_run(run_body(q, source))
            events = client.collect_run(sid, timeout)
        except AppError as exc:
            err = str(exc)
        rec = score(n, q, sid, events, clock() - t0, source, error=err)
        records.append(rec)
        log("%2d/%d  %-3s  credits=%s  seconds=%s  blocked=%s  %s%s" % (
            n, len(questions), "yes" if rec["answered_with_cited_number"] else "no", rec["credits"],
            rec["seconds"], rec["blocked"], rec["outcome"] or "-", ("  ERROR " + rec["error"]) if rec["error"] else ""))
    return records


def usefulness_fields(records):
    return {"answered_with_cited_number": sum(1 for r in records if r["answered_with_cited_number"]),
            "total": len(records)}


def git_commit():
    try:
        out = subprocess.run(["git", "describe", "--always", "--dirty", "--abbrev=7"], cwd=REPO,
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def redacted_command(argv):
    """The command as run, with the token and app URL replaced, for the results file."""
    out, skip = [], False
    for a in argv:
        if skip:
            out.append("<redacted>")
            skip = False
        elif a in ("--token", "--app-url"):
            out.append(a)
            skip = True
        elif a.startswith(("--token=", "--app-url=")):
            out.append(a.split("=", 1)[0] + "=<redacted>")
        else:
            out.append(a)
    return " ".join(["python3", "-m", "eval.usefulness"] + out)


def parse_args(argv):
    ap = argparse.ArgumentParser(prog="python3 -m eval.usefulness", description=__doc__.split("\n")[0])
    ap.add_argument("--app-url", help="the UI URL app/run.py prints at startup (carries port and token)")
    ap.add_argument("--port", type=int, help="app port (default: APP_PORT from env or .env, else 8700)")
    ap.add_argument("--token", help="app token (default: from --app-url)")
    ap.add_argument("--source", choices=("real", "fake"), default="real", help="default real")
    ap.add_argument("--benign", default=None, help="questions file (default notes/BENIGN.md)")
    ap.add_argument("--limit", type=int, default=None, metavar="N", help="only the first N questions (smoke run)")
    ap.add_argument("--timeout", type=float, default=300.0, help="seconds per question before giving up")
    ap.add_argument("--dry-run", action="store_true", help="print what would be sent; send and write nothing")
    ap.add_argument("--label", default=None, help="run label in results.json (default usefulness or smoke)")
    ap.add_argument("--out", default=None, help="results file (default shared/results/results.json)")
    ap.add_argument("--details-dir", default=None, help="per-question details (default shared/results/usefulness)")
    ap.add_argument("--record-partial", action="store_true",
                    help="append a --limit run to results.json too (runs are never deleted)")
    args = ap.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        ap.error("--limit must be at least 1")
    return args


def main(argv=None, client=None, log=print):
    argv = sys.argv[1:] if argv is None else list(argv)
    args = parse_args(argv)
    questions = load_questions(args.benign)
    partial = args.limit is not None and args.limit < len(questions)
    if args.limit is not None:
        questions = questions[:args.limit]

    port, token = args.port, args.token
    if args.app_url:
        url_port, url_token = parse_app_url(args.app_url)
        port, token = port or url_port, token or url_token
    port = port or app_port()

    if args.dry_run:
        log("dry run: %d question(s), nothing sent, nothing written" % len(questions))
        log("target: POST http://127.0.0.1:%d/api/run (X-DT-Token: %s), then GET /events until run_done"
            % (port, "<set>" if token else "<MISSING: pass --app-url or --token>"))
        for n, q in questions:
            log("%2d  %s" % (n, json.dumps(run_body(q, args.source), sort_keys=True, ensure_ascii=False)))
        return 0

    install_audit_hook()
    if client is None:
        if not token:
            log("error: no token; pass --app-url (as printed by app/run.py) or --token")
            return 2
        client = AppClient(port, token)

    records = run_questions(client, questions, args.source, args.timeout, log=log)
    useful = usefulness_fields(records)
    summary = cost_mod.summarise(records)
    generated = results_mod.now_iso()
    label = args.label or ("smoke" if partial else "usefulness")
    commit = git_commit()
    command = redacted_command(argv)

    details_dir = args.details_dir or os.path.join(REPO, cost_mod.DETAILS_DIR)
    os.makedirs(details_dir, exist_ok=True)
    details_path = os.path.join(details_dir, generated.replace("-", "").replace(":", "").split(".")[0] + "Z.json")
    details = {"generated": generated, "label": label, "commit": commit, "command": command, "mode": MODE,
               "source": args.source, "usefulness": useful, "cost": summary, "records": records}
    results_mod.write_atomic(details_path, json.dumps(details, indent=2, ensure_ascii=False) + "\n")

    log("")
    log(cost_mod.format_table(records, summary))
    log("answered with a validated cited number: %d of %d" % (useful["answered_with_cited_number"], useful["total"]))
    log("details: %s" % details_path)

    if partial and not args.record_partial:
        log("smoke run (--limit): results.json not touched; pass --record-partial to append it")
        return 0
    out = args.out or os.path.join(REPO, results_mod.RESULTS_PATH)
    rel_details = os.path.relpath(details_path, REPO)
    run = results_mod.make_run(label, commit, planner_model(), args.source, command, useful,
                               cost_mod.cost_fields(summary), details=rel_details)
    try:
        results_mod.append_run(out, run, generated)
    except results_mod.RefusedError as exc:
        log("error: %s" % exc)
        return 1
    log("appended run %r to %s" % (label, out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
