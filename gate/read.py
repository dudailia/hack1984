"""POST /v1/read (shared/FORMATS.md §3, §5): build a reading job, send reader.build_request(job) to Anthropic
through the pipeline, then parse and validate.

Invariant 3: the job holds only the public query that was already sent, the claim-type enums, and web data the
Gate received. Never the memo, the question, the need id, the session id or any secret.
Invariant 2: `typed` (numbers, enums, ids) is the only thing meant for the Planner; it is rebuilt here from
validated claims with a fixed key set. If the reader code fails in any way, nothing typed comes back
(status blocked, rule gate.reader_error).
"""
import math
import re

import reader
from reader.schema import CLAIM_UNITS

from gate.errors import ApiError
from gate.pipeline import ANTHROPIC, GateConfigError
from gate.tavily import check_ids, split_ids

R_READER_ERROR = "gate.reader_error"
NEED_RE = re.compile(r"[a-z0-9_]{1,32}")
PERIOD_RE = re.compile(r"|[0-9]{4}|[0-9]{4}-[0-9]{4}|ttm")  # FORMATS §1, re-checked here independently of reader/
READER_MODES = {"two_minds", "doublethink"}
MAX_JOB = 99
MAX_EXCERPT = 2000  # docs[].excerpt for the UI's docs_read event; never part of typed


def build_job(session, state, job_id, known_ids, claim_types, public_query):
    docs = []
    for rid in known_ids:
        d = state.docs[rid]
        text = state.extracted.get(rid)
        docs.append({"id": rid, "url": d["url"], "title": d["title"],
                     "text": text if text is not None else d["content"]})
    return {"job": job_id, "public_query": public_query, "claim_types": list(claim_types), "documents": docs}


def _empty(need):
    return {"need": need, "found": False, "values": []}


def failure_reason(http_status, transport_error):
    """(error code, human detail) for a reader request that was sent but did not succeed. Built only from fixed
    text, the HTTP status and the exception type name: never keys, headers, payloads or response bodies."""
    if http_status in (401, 403):
        return "reader_auth_failed", "Reader auth failed: %d" % http_status
    if http_status is None:
        return "reader_unreachable", "Reader unreachable: %s" % (transport_error or "no response")
    return "reader_http_error", "Reader answered HTTP %d" % http_status


def _typed(need, kept, job):
    """Fixed-shape typed fields from validated claims. Raises on anything unexpected (-> gate.reader_error)."""
    doc_ids = {d["id"] for d in job["documents"]}
    values = []
    for c in kept:
        v = c["value"]
        if (c["claim_type"] not in job["claim_types"] or isinstance(v, bool) or not isinstance(v, (int, float))
                or not math.isfinite(v) or c["unit"] not in CLAIM_UNITS[c["claim_type"]]
                or not isinstance(c["period"], str) or not PERIOD_RE.fullmatch(c["period"])
                or c["document_id"] not in doc_ids):
            raise ValueError("validated claim has an unexpected shape")
        values.append({"claim_type": c["claim_type"], "value": v, "unit": c["unit"], "period": c["period"],
                       "result_id": c["document_id"]})
    return {"need": need, "found": bool(values), "values": values}


def read(pipeline, session_id, need, result_ids, claim_types):
    sessions = pipeline.sessions
    session = sessions.get(session_id)
    state = sessions.state(session_id)
    if session["mode"] not in READER_MODES:
        raise ApiError(400, "component_mode_mismatch", "no Reader in this mode")
    if not isinstance(need, str) or not NEED_RE.fullmatch(need):
        raise ApiError(400, "bad_need", "need must match [a-z0-9_]{1,32}")
    if (not isinstance(claim_types, list) or not claim_types or len(set(map(str, claim_types))) != len(claim_types)
            or not all(isinstance(t, str) and t in CLAIM_UNITS for t in claim_types)):
        raise ApiError(400, "bad_claim_types", "claim_types must be unique known claim types")
    check_ids(result_ids)

    with state.lock:
        known, pre_rule, public_query = split_ids(session, state, result_ids)
        if state.next_job_n > MAX_JOB:
            raise ApiError(400, "too_many_jobs", "job id limit reached for this session")
        job_id = "j_%02d" % state.next_job_n  # spent only once an attempt row exists
        job = build_job(session, state, job_id, known, claim_types, public_query)

        resp = {"status": "blocked", "rule": R_READER_ERROR, "ledger_seq": None, "job": None,
                "typed": _empty(need), "claims": [], "dropped": [], "sources": {}, "docs": [], "ledger": [],
                "detail": "the reader failed; nothing typed returned (fail closed)"}
        try:
            body = reader.build_request(job)
        except BaseException:  # incl. SystemExit: fail closed
            return resp  # nothing attempted, nothing sent, no job id spent

        # sent exactly as returned: the pipeline serializes it canonically once and adds nothing.
        # A missing key is found before any row, so nothing is ledgered and no job id is spent.
        try:
            out = pipeline.send(session_id, "reader", "reader", ANTHROPIC, "/v1/messages", body, pre_rule=pre_rule)
        except GateConfigError:
            raise ApiError(503, "reader_key_missing", "ANTHROPIC_API_KEY not set") from None
        state.next_job_n += 1
        resp.update(status=out["status"], rule=out["rule"], ledger_seq=out["ledger_seq"], ledger=out["rows"],
                    job=job_id)
        resp.pop("detail")
        if out["status"] == "blocked":
            resp["detail"] = out["detail"]
            return resp
        if out["status"] != "sent":
            # sent but failed: say why (the ledger rows stay exactly as §7 has them; the reason is only here)
            resp["error"], resp["detail"] = failure_reason(out["http_status"], out.get("transport_error"))
            return resp

        try:
            claims = reader.parse_response(job, out["response"])
            kept, dropped = reader.validate(job, claims)
            typed = _typed(need, kept, job)
            if not isinstance(dropped, list):
                raise ValueError("dropped must be a list")
        except BaseException:  # incl. SystemExit: fail closed, nothing typed
            resp.update(status="blocked", rule=R_READER_ERROR,
                        detail="the reader failed; nothing typed returned (fail closed)")
            return resp

        # docs: UI only (docs_read event); one per job document, excerpt = the text the Reader got, cut to 2,000
        resp.update(typed=typed, claims=kept, dropped=dropped,
                    sources={d["id"]: {"url": d["url"], "title": d["title"]} for d in job["documents"]},
                    docs=[{"result_id": d["id"], "title": d["title"], "url": d["url"],
                           "excerpt": d["text"][:MAX_EXCERPT]} for d in job["documents"]])
        return resp
