"""Tavily search through the pipeline (shared/FORMATS.md §1 presets, §3 response).

The Gate issues its own r_01, r_02 … ids per session and never passes Tavily's ids on. The Planner gets ids only;
titles, URLs and content stay in the Gate (GateState.docs) and go to the baseline only when component = baseline.
"""
import copy
import json

from gate.pipeline import TAVILY

SEARCH_BASE = {"search_depth": "basic", "max_results": 10, "include_usage": True}
FINANCE_DOMAINS = ["sec.gov", "investor.gov", "nasdaq.com", "nyse.com"]
SEARCH_PRESETS = {
    "general": {"topic": "general"},
    "finance": {"topic": "finance", "include_domains": FINANCE_DOMAINS, "include_domains_mode": "prefer"},
    "news": {"topic": "news"},
}
MAX_RESULT_ID = 99


class TavilyError(Exception):
    pass


def search_body(query, preset):
    if preset not in SEARCH_PRESETS:
        raise ValueError("unknown search preset")
    body = dict(SEARCH_BASE)
    body.update(copy.deepcopy(SEARCH_PRESETS[preset]))
    body["query"] = query
    return body


def _credits(usage):
    v = usage.get("credits") if isinstance(usage, dict) else None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return None


def parse_search(response_bytes):
    """-> ([{url, title, content}], credits or None). Every other Tavily field is dropped."""
    data = json.loads(response_bytes)
    results = []
    for r in data.get("results") or []:
        if not isinstance(r, dict) or not isinstance(r.get("url"), str) or not r["url"]:
            continue
        title = r.get("title") if isinstance(r.get("title"), str) else ""
        content = r.get("content") if isinstance(r.get("content"), str) else ""
        results.append({"url": r["url"], "title": title, "content": content})
    return results, _credits(data.get("usage"))


def _credits_fn(status, response):
    return parse_search(response)[1]


def search(pipeline, session_id, component, need, query, preset, api_key):
    sessions = pipeline.sessions
    session = sessions.get(session_id)
    state = sessions.state(session_id)
    body = search_body(query, preset)
    real = session["source"] == "real"
    if real:
        if not api_key:
            raise TavilyError("TAVILY_API_KEY is not set")
        destination, headers = TAVILY, {"Authorization": f"Bearer {api_key}"}
    else:
        destination, headers = pipeline.fake, {}

    with state.lock:
        out = pipeline.send(session_id, component, "search", destination, "/search", body, headers=headers,
                            credits_fn=_credits_fn if real else None)
        resp = {"status": out["status"], "rule": out["rule"], "ledger_seq": out["ledger_seq"], "result_ids": [],
                "credits_used": 0, "ledger": out["rows"]}
        if out["status"] == "blocked":
            resp["detail"] = out["detail"]
            return resp

        session["call_count"] += 1
        session["queries_sent"].append(query)
        # ledger row: credits from Tavily, null for the fake; response: always an int (0 when unknown)
        credits = out["rows"][-1].get("credits_used") if real else None
        resp["credits_used"] = credits or 0
        if credits:
            session["credits_used"] += credits
        if out["status"] != "sent":
            return resp

        try:
            results, _ = parse_search(out["response"])
        except (ValueError, AttributeError):
            results = []
        issued = []
        for r in results:
            if state.next_result_n > MAX_RESULT_ID:
                break
            rid = "r_%02d" % state.next_result_n
            state.next_result_n += 1
            state.docs[rid] = r
            session["result_ids"][rid] = r["url"]
            session["urls_returned"].append(r["url"])
            for text in (r["title"], r["content"]):
                if text:
                    session["public_text_received"].append(text)
            issued.append(rid)
        resp["result_ids"] = issued
        if component == "baseline":
            resp["results"] = [{"result_id": rid, "title": state.docs[rid]["title"], "url": state.docs[rid]["url"],
                                "content": state.docs[rid]["content"]} for rid in issued]
        return resp
