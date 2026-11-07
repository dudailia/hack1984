"""Test helpers: load saved pages and the shared demo fixtures (tests may read files; reader/ may not)."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PAGES = HERE / "pages"
EVENTS = ROOT / "shared" / "fixtures" / "demo_events.jsonl"
SESSION = ROOT / "shared" / "fixtures" / "halyard_session.json"

LABELS = {"sector_growth": "Sector growth", "peer_ev_revenue": "Listed payments companies"}


def page(name):
    return json.loads((PAGES / name).read_text(encoding="utf-8"))


def events():
    with open(EVENTS, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def session():
    return json.loads(SESSION.read_text(encoding="utf-8"))


def memo():
    return (ROOT / session()["memo_file"]).read_text(encoding="utf-8")


def needs_with_labels():
    return [dict(n, label=LABELS[n["need"]]) for n in session()["needs"]]
