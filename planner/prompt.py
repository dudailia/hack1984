"""Planner prompts. The user prompt carries only the memo, the question and validated typed results."""
import datetime
import json

from planner.schema import CLAIM_UNITS


def _date_str(today) -> str:
    if isinstance(today, datetime.datetime) or not isinstance(today, (datetime.date, str)):
        raise ValueError("today must be a date or YYYY-MM-DD")
    if isinstance(today, str):
        try:
            today = datetime.date.fromisoformat(today)
        except ValueError:
            raise ValueError("today must be YYYY-MM-DD") from None
    return today.isoformat()


def system_prompt(today) -> str:
    d = _date_str(today)
    year = d[:4]
    claim_lines = "\n".join(f"  - {ct}: {', '.join(sorted(u))}" for ct, u in CLAIM_UNITS.items())
    return f"""Today is {d}. The current year is {year}.

You plan web research for a confidential memo. You research public facts that the memo needs. You never read
web pages yourself: after each step you receive only typed results (numbers, units, periods, found or not
found, and result ids).

Rules for every query:
- Never put the buyer, the price, the codename or any person's name in a query, in any form or spelling.
- Never copy any code, reference number, ID or "Ref:" value from the memo into a query.
- Ask only about the target's sector and public peers (listed companies in the same sector), in general terms.
- Queries are short: 3 to 8 words.
- Prefer the most recent data: name the latest year ({year} or {int(year) - 1}) when a year helps.

Reply with exactly one JSON action:
- {{"action":"search","need":"<need id>","claim_types":[...],"query":"<3 to 8 words>","preset":"general|finance|news"}}
- {{"action":"extract","need":"<need id>","claim_types":[...],"result_ids":["r_01"],"preset":"text|tables"}}
  Use extract only on result ids that appear in the typed results, to read those pages in more detail.
- {{"action":"done"}} when every need has found values, or when more research will not help.

need is a short id in lowercase letters, digits and underscores, for example sector_growth or peer_ev_revenue.
Preset finance suits company figures and valuations; news suits recent events; general otherwise.
Allowed claim_types and their units:
{claim_lines}
"""


def user_prompt(memo, question, typed_results) -> str:
    typed = (json.dumps(typed_results, sort_keys=True, separators=(",", ":"))
             if typed_results else "none yet")
    return (f"MEMO:\n{memo}\n\nQUESTION:\n{question}\n\n"
            f"TYPED RESULTS SO FAR:\n{typed}\n\nReply with the next action as JSON.")


def build_messages(memo, question, today, typed_results) -> list:
    return [{"role": "system", "content": system_prompt(today)},
            {"role": "user", "content": user_prompt(memo, question, typed_results)}]
