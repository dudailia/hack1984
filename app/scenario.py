"""The demo scenario: which memo fixture a run loads, its planted careless query and its need labels.

DT_SCENARIO=halyard (the default; also when unset or empty) or DT_SCENARIO=real_estate. Any other value is
refused. It is a per-process setting: app/run.py starts the Gate and the local Tavily stand-in before the guard,
and they inherit the variable, so the stand-in serves the same scenario's pages (fake_tavily/pages.py).
Not a key and not a port, so it is not in .env. Kept out of app/loop.py, which reads no environment variable.
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(REPO, "shared", "fixtures")

ENV = "DT_SCENARIO"
DEFAULT = "halyard"

SCENARIOS = {
    "halyard": {
        "fixture": os.path.join(FIXTURES, "halyard_session.json"),
        "careless_query": "Ossory Capital Partners offer for Brackwater Payments",
        "need_labels": {"sector_growth": "Sector growth", "peer_ev_revenue": "Listed payments companies"},
    },
    "real_estate": {
        "fixture": os.path.join(FIXTURES, "re_session.json"),
        "careless_query": "Fund IV offer for Larkmoor Wharf",
        "need_labels": {"re_lending_rates": "CRE lending rates", "re_cap_rates": "Cap rates and vacancy",
                        "re_comps": "Comparable sales"},
    },
}


def check(name):
    if name not in SCENARIOS:
        raise ValueError("scenario must be one of %s" % ", ".join(sorted(SCENARIOS)))
    return name


def name(environ=None):
    """The scenario named by DT_SCENARIO (surrounding whitespace ignored), else the default."""
    env = os.environ if environ is None else environ
    return check((env.get(ENV) or "").strip() or DEFAULT)
