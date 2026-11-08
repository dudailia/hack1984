"""Planner prompts. The user prompt carries only the memo, the question and validated typed results."""
import datetime
import json

from planner.schema import CLAIM_UNITS, profile_claim_types

# The lines that differ per profile (one per demo scenario). Halyard's are the original text, byte for byte.
_PROFILE_LINES = {
    "halyard": {
        "secrets": "- Never put the buyer, the price, the codename or any person's name in a query, in any form or "
                   "spelling.",
        "scope": "- Ask only about the target's sector and public peers (listed companies in the same sector), in "
                 "general terms.",
        "needs": "need is a short id in lowercase letters, digits and underscores, for example sector_growth or "
                 "peer_ev_revenue.",
        "presets": "Preset finance suits company figures and valuations; news suits recent events; general otherwise.",
    },
    "real_estate": {
        "secrets": "- Never put the property name, the buyer, the financing amount, the price, the codename or any "
                   "person's name in a query, in any form or spelling.",
        "scope": "- Ask only about the market, in general terms: cap rates, vacancy, commercial real estate lending "
                 "rates and comparable sales for the property type.",
        "needs": "need is a short id in lowercase letters, digits and underscores, for example re_lending_rates, "
                 "re_cap_rates or re_comps.",
        "presets": "Preset general suits market rates and comparable sales; news suits recent deals and rate moves.\n"
                   "Use interest_rate for loan rates, cap_rate for cap rates, vacancy_rate for vacancy and "
                   "price_per_sqft for sale prices per square foot.",
    },
}


def _date_str(today) -> str:
    if isinstance(today, datetime.datetime) or not isinstance(today, (datetime.date, str)):
        raise ValueError("today must be a date or YYYY-MM-DD")
    if isinstance(today, str):
        try:
            today = datetime.date.fromisoformat(today)
        except ValueError:
            raise ValueError("today must be YYYY-MM-DD") from None
    return today.isoformat()


def system_prompt(today, profile=None) -> str:
    """profile: None or "halyard" (the default) or "real_estate"; ValueError for anything else."""
    types = profile_claim_types(profile)
    lines = _PROFILE_LINES[profile or "halyard"]
    d = _date_str(today)
    year = d[:4]
    claim_lines = "\n".join(f"  - {ct}: {', '.join(sorted(CLAIM_UNITS[ct]))}" for ct in types)
    return f"""Today is {d}. The current year is {year}.

You plan web research for a confidential memo. You research public facts that the memo needs. You never read
web pages yourself: after each step you receive only typed results (numbers, units, periods, found or not
found, and result ids).

Rules for every query:
{lines["secrets"]}
- Never copy any code, reference number, ID or "Ref:" value from the memo into a query.
{lines["scope"]}
- Queries are short: 3 to 8 words.
- Prefer the most recent data: name the latest year ({year} or {int(year) - 1}) when a year helps.

Reply with exactly one JSON action:
- {{"action":"search","need":"<need id>","claim_types":[...],"query":"<3 to 8 words>","preset":"general|finance|news"}}
- {{"action":"extract","need":"<need id>","claim_types":[...],"result_ids":["r_01"],"preset":"text|tables"}}
  Use extract only on result ids that appear in the typed results, to read those pages in more detail.
- {{"action":"done"}} when every need has found values, or when more research will not help.

{lines["needs"]}
{lines["presets"]}
Allowed claim_types and their units:
{claim_lines}
"""


def user_prompt(memo, question, typed_results) -> str:
    typed = (json.dumps(typed_results, sort_keys=True, separators=(",", ":"))
             if typed_results else "none yet")
    return (f"MEMO:\n{memo}\n\nQUESTION:\n{question}\n\n"
            f"TYPED RESULTS SO FAR:\n{typed}\n\nReply with the next action as JSON.")


def build_messages(memo, question, today, typed_results, profile=None) -> list:
    return [{"role": "system", "content": system_prompt(today, profile)},
            {"role": "user", "content": user_prompt(memo, question, typed_results)}]
