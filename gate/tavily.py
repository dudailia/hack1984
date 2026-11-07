"""Tavily search through the pipeline (shared/FORMATS.md §1 presets, §3 response).

The Gate issues its own r_01, r_02 … ids per session and never passes Tavily's ids on. The Planner gets ids only;
titles, URLs and content stay in the Gate (GateState.docs) and go to the baseline only when component = baseline.
"""
import copy
import json
import re

from gate.errors import ApiError
from gate.pipeline import R_UNKNOWN_ID, TAVILY

SEARCH_BASE = {"search_depth": "basic", "max_results": 10, "include_usage": True}
FINANCE_DOMAINS = ["sec.gov", "investor.gov", "nasdaq.com", "nyse.com"]
SEARCH_PRESETS = {
    "general": {"topic": "general"},
    "finance": {"topic": "finance", "include_domains": FINANCE_DOMAINS, "include_domains_mode": "prefer"},
    "news": {"topic": "news"},
}
MAX_RESULT_ID = 99
EXTRACT_BASE = {"format": "text", "chunks_per_source": 3, "include_usage": True}
EXTRACT_PRESETS = {"text": {"extract_depth": "basic"}, "tables": {"extract_depth": "advanced"}}
MAX_IDS = 20
MAX_DOC_CHARS = 30000
RESULT_ID_RE = re.compile(r"r_[0-9]{2}")


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
        if not isinstance(r, dict):
            continue
        url = _utf8(r.get("url"))
        if not url:
            continue  # no usable url (missing, or not encodable): skip the whole result
        results.append({"url": url, "title": _text(r.get("title")), "content": _text(r.get("content"))})
    return results, _credits(data.get("usage"))


# JSON can carry lone surrogates (\ud800) that make canonical_json raise later, which would break every read of
# that search. They are handled on arrival: urls that carry one are dropped (an altered url is another url);
# in titles and text only the surrogate characters are removed.
_SURROGATES = re.compile("[\ud800-\udfff]")


def _utf8(value):
    """The string if it encodes as UTF-8, else None."""
    if not isinstance(value, str):
        return None
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return None
    return value


def _text(value):
    return _SURROGATES.sub("", value) if isinstance(value, str) else ""


def _credits_fn(status, response):
    return parse_search(response)[1]


def destination_for(pipeline, session):
    return TAVILY if session["source"] == "real" else pipeline.fake


def search(pipeline, session_id, component, need, query, preset):
    sessions = pipeline.sessions
    session = sessions.get(session_id)
    state = sessions.state(session_id)
    body = search_body(query, preset)
    real = session["source"] == "real"
    destination = destination_for(pipeline, session)

    with state.lock:
        out = pipeline.send(session_id, component, "search", destination, "/search", body,
                            credits_fn=_credits_fn if real else None)
        resp = {"status": out["status"], "rule": out["rule"], "ledger_seq": out["ledger_seq"], "result_ids": [],
                "credits_used": 0, "ledger": out["rows"]}
        if out["status"] == "blocked":
            resp["detail"] = out["detail"]
            return resp

        # Counters are updated only here, after the send, so at run_all time they mean "used before this call".
        # call_count counts every attempt that reached the network (sent or error); blocked attempts never do.
        session["call_count"] += 1
        # ledger row: credits from Tavily, null for the fake; response: always an int (0 when unknown)
        credits = out["rows"][-1].get("credits_used") if real else None
        resp["credits_used"] = credits or 0
        if credits:
            session["credits_used"] += credits
        if out["status"] != "sent":
            return resp
        session["queries_sent"].append(query)  # only queries actually sent (2xx)

        try:
            results, _ = parse_search(out["response"])
        except (ValueError, AttributeError):
            results = []
        # Public text is recorded as soon as the response arrives, before any Reader request is built,
        # for every parsed result (including any past the r_99 id cap).
        for r in results:
            for text in (r["title"], r["content"]):
                if text:
                    session["public_text_received"].append(text)
        issued = []
        for r in results:
            if state.next_result_n > MAX_RESULT_ID:
                break
            rid = "r_%02d" % state.next_result_n
            state.next_result_n += 1
            state.docs[rid] = r
            state.query_of[rid] = query
            session["result_ids"][rid] = r["url"]
            session["urls_returned"].append(r["url"])
            issued.append(rid)
        resp["result_ids"] = issued
        if component == "baseline":
            resp["results"] = [{"result_id": rid, "title": state.docs[rid]["title"], "url": state.docs[rid]["url"],
                                "content": state.docs[rid]["content"]} for rid in issued]
        return resp


# -- shared by extract and read ----------------------------------------------------------------------------------
def check_ids(result_ids):
    """Shape check before any ledger row: 1..20 unique ids shaped r_NN. Raises ApiError (400)."""
    if (not isinstance(result_ids, list) or not 1 <= len(result_ids) <= MAX_IDS
            or not all(isinstance(r, str) and RESULT_ID_RE.fullmatch(r) for r in result_ids)
            or len(set(result_ids)) != len(result_ids)):
        raise ApiError(400, "bad_result_ids", f"result_ids must be 1 to {MAX_IDS} unique ids like r_01")


def split_ids(session, state, result_ids):
    """-> (known ids, pre_rule, public_query). Ids from different searches: ApiError 400 mixed_searches."""
    known = [r for r in result_ids if r in session["result_ids"]]
    pre_rule = R_UNKNOWN_ID if len(known) != len(result_ids) else None
    queries = {state.query_of[r] for r in known}
    if len(queries) > 1:
        raise ApiError(400, "mixed_searches", "result ids must all come from the same search")
    return known, pre_rule, (queries.pop() if queries else "")


# -- extract -----------------------------------------------------------------------------------------------------
def extract_body(urls, query, preset):
    if preset not in EXTRACT_PRESETS:
        raise ValueError("unknown extract preset")
    body = dict(EXTRACT_BASE)
    body.update(EXTRACT_PRESETS[preset])
    body["urls"] = list(urls)
    body["query"] = query
    return body


def parse_extract(response_bytes):
    """-> ({url: text}, [failed urls], credits or None). Reads both results and failed_results."""
    data = json.loads(response_bytes)
    texts, failed = {}, []
    results = data.get("results") if isinstance(data.get("results"), list) else []
    for r in results:
        if isinstance(r, dict) and _utf8(r.get("url")) and isinstance(r.get("raw_content"), str):
            texts[r["url"]] = _text(r["raw_content"])
    fr = data.get("failed_results") if isinstance(data.get("failed_results"), list) else []
    for r in fr:
        if isinstance(r, dict) and _utf8(r.get("url")):
            failed.append(r["url"])
    return texts, failed, _credits(data.get("usage"))


def extract(pipeline, session_id, component, need, result_ids, preset):
    if preset not in EXTRACT_PRESETS:
        raise ApiError(400, "bad_options", "options must be {preset: text|tables}")
    check_ids(result_ids)
    sessions = pipeline.sessions
    session = sessions.get(session_id)
    state = sessions.state(session_id)
    real = session["source"] == "real"
    destination = destination_for(pipeline, session)

    with state.lock:
        known, pre_rule, query = split_ids(session, state, result_ids)
        # unknown ids are carried as-is (shape-checked r_NN) so the blocked attempt commits what was asked
        urls = [session["result_ids"].get(r, r) for r in result_ids]
        body = extract_body(urls, query, preset)
        out = pipeline.send(session_id, component, "extract", destination, "/extract", body, pre_rule=pre_rule,
                            credits_fn=(lambda s, resp: parse_extract(resp)[2]) if real else None)
        resp = {"status": out["status"], "rule": out["rule"], "ledger_seq": out["ledger_seq"], "result_ids": [],
                "credits_used": 0, "ledger": out["rows"]}
        if out["status"] == "blocked":
            resp["detail"] = out["detail"]
            return resp

        session["call_count"] += 1
        credits = out["rows"][-1].get("credits_used") if real else None
        resp["credits_used"] = credits or 0
        if credits:
            session["credits_used"] += credits
        if out["status"] != "sent":
            return resp

        try:
            texts, _failed, _ = parse_extract(out["response"])
        except (ValueError, AttributeError):
            texts = {}
        extracted = []
        for rid in known:
            u = session["result_ids"][rid]
            if u not in texts:
                continue  # failed or missing: a later read falls back to the search content
            text = texts[u][:MAX_DOC_CHARS]
            state.extracted[rid] = text
            if text:
                session["public_text_received"].append(text)  # on arrival, before any Reader request
            if u not in session["urls_returned"]:
                session["urls_returned"].append(u)
            extracted.append(rid)
        resp["result_ids"] = extracted
        if component == "baseline":
            resp["results"] = [{"result_id": rid, "title": state.docs[rid]["title"], "url": state.docs[rid]["url"],
                                "content": state.extracted[rid]} for rid in extracted]
        return resp
