"""Cost and time per question (SPEC "Measurements" 4): Tavily credits and seconds.

    python3 -m eval.cost                                  # latest file in shared/results/usefulness/
    python3 -m eval.cost shared/results/usefulness/20261107T230000Z.json

Reads the per-question details file that eval.usefulness writes. Only questions whose run reached run_done
count toward the averages (credits are unknown otherwise); the number of such questions is reported.
"""
import argparse
import glob
import json
import os
import statistics
import sys

from eval.loopback import REPO

DETAILS_DIR = os.path.join("shared", "results", "usefulness")


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def summarise(records):
    """Return the §9 cost fields plus the spread behind them."""
    done = [r for r in records if r.get("run_done")]
    credits = [r["credits"] for r in done if _num(r.get("credits"))]
    seconds = [r["seconds"] for r in done if _num(r.get("seconds"))]

    def spread(xs, nd):
        if not xs:
            return {"mean": None, "median": None, "max": None, "total": None, "n": 0}
        return {"mean": round(statistics.fmean(xs), nd), "median": round(statistics.median(xs), nd),
                "max": round(max(xs), nd), "total": round(sum(xs), nd), "n": len(xs)}

    c, s = spread(credits, 2), spread(seconds, 1)
    return {"tavily_credits_per_question": c["mean"], "seconds_per_question": s["mean"],
            "credits": c, "seconds": s, "questions": len(records), "completed": len(done)}


def cost_fields(summary):
    """Only the two keys FORMATS §9 defines."""
    return {"tavily_credits_per_question": summary["tavily_credits_per_question"],
            "seconds_per_question": summary["seconds_per_question"]}


def format_table(records, summary):
    def cell(x):
        return "-" if x is None else str(x)
    lines = ["%3s  %7s  %7s  %7s  %-9s  %s" % ("#", "credits", "seconds", "blocked", "outcome", "question")]
    for r in records:
        lines.append("%3s  %7s  %7s  %7s  %-9s  %s" % (
            r.get("n"), cell(r.get("credits")), cell(r.get("seconds")), cell(r.get("blocked")),
            (r.get("outcome") or r.get("error") or "-")[:9], (r.get("question") or "")[:70]))
    c, s = summary["credits"], summary["seconds"]
    lines.append("")
    lines.append("completed runs: %d of %d" % (summary["completed"], summary["questions"]))
    lines.append("credits per question: mean %s, median %s, max %s, total %s" % (
        cell(c["mean"]), cell(c["median"]), cell(c["max"]), cell(c["total"])))
    lines.append("seconds per question: mean %s, median %s, max %s, total %s" % (
        cell(s["mean"]), cell(s["median"]), cell(s["max"]), cell(s["total"])))
    return "\n".join(lines)


def latest_details(directory=None):
    directory = directory or os.path.join(REPO, DETAILS_DIR)
    files = sorted(glob.glob(os.path.join(directory, "*.json")))
    if not files:
        raise FileNotFoundError("no details file in %s; run python3 -m eval.usefulness first" % directory)
    return files[-1]


def load_records(path):
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    if not isinstance(doc, dict) or not isinstance(doc.get("records"), list):
        raise ValueError("%s is not an eval.usefulness details file" % path)
    return doc["records"]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m eval.cost", description=__doc__.split("\n")[0])
    ap.add_argument("details", nargs="?", help="details file (default: latest in %s)" % DETAILS_DIR)
    ap.add_argument("--json", action="store_true", help="print the summary as JSON only")
    args = ap.parse_args(argv)
    path = args.details or latest_details()
    records = load_records(path)
    summary = summarise(records)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(path)
        print(format_table(records, summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
