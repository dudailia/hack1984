"""Red-team hook: swap the planted instruction on the poisoned page for any payload text.

The payload is given as an argument. This module never opens an attack file. A running server re-reads the
state file on every request, so no restart is needed.

    python3 -m fake_tavily.inject "payload text"
    python3 -m fake_tavily.inject --reset
"""
import argparse
import os
import sys
import tempfile

from fake_tavily import pages

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_ENV = "FAKE_TAVILY_STATE"


def default_state_path():
    return os.environ.get(STATE_ENV) or os.path.join(HERE, "state", "planted.txt")


def set_planted(text, state_path=None):
    if not isinstance(text, str):
        raise TypeError("planted text must be str")
    path = state_path or default_state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".planted-")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)  # atomic: a request never sees a half-written payload


def reset(state_path=None):
    try:
        os.remove(state_path or default_state_path())
    except FileNotFoundError:
        pass


def current_planted(state_path=None, fixture_pages=None):
    """The text the poisoned page currently carries (the injected payload, else the DEMO.md default)."""
    try:
        with open(state_path or default_state_path(), encoding="utf-8", newline="") as f:
            return f.read()
    except FileNotFoundError:
        return pages.default_planted(fixture_pages if fixture_pages is not None else pages.load_pages())


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m fake_tavily.inject", description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("text", nargs="?", help="payload text to plant on the poisoned page")
    g.add_argument("--reset", action="store_true", help="restore the default instruction from notes/DEMO.md")
    args = ap.parse_args(argv)
    if args.reset:
        reset()
        print("planted text reset to default")
    else:
        set_planted(args.text)
        print("planted text set (%d chars)" % len(args.text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
