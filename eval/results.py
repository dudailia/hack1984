"""Append a usefulness-and-cost run to shared/results/results.json (FORMATS §9).

This module writes only its own run object: label, commit, planner_model, source, command, usefulness, cost
(plus a pointer to the per-question details). It never writes `modes` or `false_blocks`, which belong to the
red team and to Anant, and never edits or removes an existing run.
"""
import json
import os
import re
import tempfile
from datetime import datetime, timezone

from eval.loopback import REPO

RESULTS_PATH = os.path.join("shared", "results", "results.json")
BENIGN_TOTAL = 30
OWNED_RUN_KEYS = ("label", "commit", "planner_model", "source", "command", "usefulness", "cost", "details")


class RefusedError(RuntimeError):
    pass


def now_iso():
    t = datetime.now(timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (t.microsecond // 1000)


def registered_attack_hash(path=None):
    """The pre-registered SHA-256 from notes/ATTACKS_HASH.md, so a header created here matches the one the red-team
    runner expects. Only the hash line is read; the attack file itself is never touched."""
    path = path or os.path.join(REPO, "notes", "ATTACKS_HASH.md")
    try:
        with open(path, encoding="utf-8") as f:
            m = re.search(r"SHA-256:\s*([0-9a-f]{64})", f.read())
    except FileNotFoundError:
        return None
    return m.group(1) if m else None


def new_header(attack_hash):
    return {"v": 1, "example": False, "generated": None, "attack_file_sha256": attack_hash,
            "attacks_total": 40 if attack_hash else None, "benign_total": BENIGN_TOTAL, "leak_judge": None,
            "runs": []}


def load_or_create(path, attack_hash=None):
    if not os.path.exists(path):
        return new_header(attack_hash if attack_hash is not None else registered_attack_hash())
    with open(path, encoding="utf-8") as f:
        try:
            doc = json.load(f)
        except ValueError:
            raise RefusedError("%s is not JSON; not appending" % path)
    if not isinstance(doc, dict) or doc.get("v") != 1 or not isinstance(doc.get("runs"), list):
        raise RefusedError("%s is not a v1 results file; not appending" % path)
    if doc.get("example") is not False:
        raise RefusedError("%s is example data; not appending a measurement to it" % path)
    return doc


def make_run(label, commit, planner_model, source, command, usefulness, cost, details=None):
    if set(usefulness) != {"answered_with_cited_number", "total"}:
        raise ValueError("usefulness must have exactly answered_with_cited_number and total")
    if set(cost) != {"tavily_credits_per_question", "seconds_per_question"}:
        raise ValueError("cost must have exactly tavily_credits_per_question and seconds_per_question")
    run = {"label": label, "commit": commit, "planner_model": planner_model, "source": source,
           "command": command, "usefulness": dict(usefulness), "cost": dict(cost)}
    if details:
        run["details"] = details
    return run


def append_run(path, run, generated=None, attack_hash=None):
    """Append run to the results file atomically. Returns the written document."""
    extra = set(run) - set(OWNED_RUN_KEYS)
    if extra:
        raise RefusedError("eval does not write %s" % ", ".join(sorted(extra)))
    doc = load_or_create(path, attack_hash)
    if doc.get("benign_total") is None:
        doc["benign_total"] = BENIGN_TOTAL
    doc["generated"] = generated or now_iso()
    doc["runs"].append(run)
    write_atomic(path, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    return doc


def write_atomic(path, text):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".results-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
