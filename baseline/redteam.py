"""Red-team runner (skeleton). Filled in only after checks/ is frozen at the tag `checks-frozen`.

    python3 -m baseline.redteam --attacks ATTACKS.md --modes all --out shared/results/results.json

Until then it parses its arguments and stops. It never opens the attack file.
"""
import argparse
import sys

MODES = ["single_agent", "compromised", "two_minds", "doublethink"]


def _modes(text):
    if text == "all":
        return list(MODES)
    out = [m.strip() for m in text.split(",") if m.strip()]
    bad = [m for m in out if m not in MODES]
    if not out or bad:
        raise argparse.ArgumentTypeError("modes: 'all' or a comma list of %s" % ", ".join(MODES))
    return out


def parse_args(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m baseline.redteam", description=__doc__.splitlines()[0])
    ap.add_argument("--attacks", required=True, metavar="PATH", help="attack file (opened only after checks-frozen)")
    ap.add_argument("--modes", required=True, type=_modes, help="'all' or a comma list of " + ", ".join(MODES))
    ap.add_argument("--out", required=True, metavar="PATH", help="results file (FORMATS §9)")
    return ap.parse_args(argv)


def main(argv=None):
    parse_args(argv)
    # TODO(after checks-frozen): verify sha256 of --attacks against notes/ATTACKS_HASH.md, plant each payload via
    # fake_tavily.inject, run each mode on source=fake, count leaks from the ledger, write FORMATS §9 to --out.
    raise NotImplementedError("baseline.redteam is filled in after the checks-frozen tag")


if __name__ == "__main__":
    sys.exit(main())
