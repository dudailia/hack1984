"""Build the Anthropic Messages body for a reading job (FORMATS §5). The Gate adds headers and sends it."""
import re

from reader.prompt import SYSTEM_PROMPT
from reader.schema import CLAIM_UNITS

MODEL = "claude-haiku-5-5"
MAX_TOKENS = 2048

JOB_KEYS = frozenset(("job", "public_query", "claim_types", "documents"))
DOC_KEYS = frozenset(("id", "url", "title", "text"))

# Web text must not be able to open or close our tags. The fullwidth "＜" maps back to "<" under NFKC, so the
# Validator's verbatim check still matches a quote the model copied from the escaped text.
_RESULT_ID = re.compile(r"r_[0-9]{2}")
_JOB_ID = re.compile(r"j_[0-9]{2}")
_TAG_RE = re.compile(r"<(\s*/?\s*(?:documents?|title|text|public_query|allowed_claim_types)\b)", re.IGNORECASE)


def _escape(text):
    return _TAG_RE.sub("\uff1c\\1", text)


def check_job(job):
    """Raise ValueError unless the job has exactly the §5 shape. Ids must look like ids (r_01, j_01), so nothing
    else (a session id, a need id) can ride into the body in their place."""
    if not isinstance(job, dict):
        raise ValueError("job must be a dict")
    extra = set(job) - JOB_KEYS
    if extra:
        raise ValueError("unexpected job keys: %s" % sorted(extra))
    if "job" in job and not (isinstance(job["job"], str) and _JOB_ID.fullmatch(job["job"])):
        raise ValueError("job id must look like j_01")
    query, types, docs = job.get("public_query"), job.get("claim_types"), job.get("documents")
    if not isinstance(query, str):
        raise ValueError("public_query must be a string")
    if not isinstance(types, list) or not types or any(t not in CLAIM_UNITS for t in types):
        raise ValueError("claim_types must be a non-empty list of known claim types")
    if not isinstance(docs, list):
        raise ValueError("documents must be a list")
    for doc in docs:
        if not isinstance(doc, dict):
            raise ValueError("each document must be a dict")
        extra = set(doc) - DOC_KEYS
        if extra:
            raise ValueError("unexpected document keys: %s" % sorted(extra))
        if not isinstance(doc.get("id"), str) or not isinstance(doc.get("text"), str):
            raise ValueError("each document needs string id and text")
        if not _RESULT_ID.fullmatch(doc["id"]):
            raise ValueError("document id must look like r_01")
        if not isinstance(doc.get("title", ""), str) or not isinstance(doc.get("url", ""), str):
            raise ValueError("document title and url must be strings")


def _user_content(job):
    lines = ["<public_query>%s</public_query>" % _escape(job["public_query"]), "<allowed_claim_types>"]
    # Fixed order, each type once: the Planner's ordering or repetition of claim_types never reaches the body.
    wanted = set(job["claim_types"])
    for t in (t for t in CLAIM_UNITS if t in wanted):
        lines.append("%s: %s" % (t, ", ".join(CLAIM_UNITS[t])))
    lines += ["</allowed_claim_types>", "<documents>"]
    for doc in job["documents"]:
        lines += ['<document id="%s">' % doc["id"],
                  "<title>%s</title>" % _escape(doc.get("title", "")),
                  "<text>%s</text>" % _escape(doc["text"]),
                  "</document>"]
    lines += ["</documents>", "Return the claims JSON object now."]
    return "\n".join(lines)


def build_request(job):
    """Return the Messages API body. No tools, no temperature, no prefill (tested)."""
    check_job(job)
    return {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "thinking": {"type": "disabled"},
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": _user_content(job)}],
    }
