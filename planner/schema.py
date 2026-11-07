"""Planner action (FORMATS §2) and typed input (FORMATS §3 /v1/read "typed"). Strict: unknown keys are rejected."""
import math
import re

CLAIM_UNITS = {
    "revenue": {"usd", "usd_millions", "usd_billions"},
    "revenue_growth": {"percent"},
    "ev_revenue_multiple": {"multiple"},
    "ev_ebitda_multiple": {"multiple"},
    "ebitda": {"usd", "usd_millions", "usd_billions"},
    "market_size": {"usd", "usd_millions", "usd_billions"},
    "employees": {"count"},
    "founded_year": {"year"},
}
UNITS = set().union(*CLAIM_UNITS.values())
SEARCH_PRESETS = {"general", "finance", "news"}
EXTRACT_PRESETS = {"text", "tables"}
MAX_RESULT_IDS = 20
MAX_QUERY_CHARS = 200

NEED_RE = re.compile(r"[a-z0-9_]{1,32}")
RESULT_ID_RE = re.compile(r"r_[0-9]{2}")
PERIOD_RE = re.compile(r"|[0-9]{4}|[0-9]{4}-[0-9]{4}|ttm")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f  ]")

_KEYS = {
    "done": {"action"},
    "search": {"action", "need", "claim_types", "query", "preset"},
    "extract": {"action", "need", "claim_types", "result_ids", "preset"},
}
_TYPED_KEYS = {"need", "found", "values"}
_VALUE_KEYS = {"claim_type", "value", "unit", "period", "result_id"}


class SchemaError(ValueError):
    pass


def _str(v, what):
    if not isinstance(v, str):
        raise SchemaError(f"{what}: not a string")
    return v


def _match(regex, v, what):
    if not regex.fullmatch(_str(v, what)):
        raise SchemaError(f"{what}: bad format")
    return v


def _keys(obj, expected, what):
    if not isinstance(obj, dict):
        raise SchemaError(f"{what}: not an object")
    if set(obj) != expected:
        raise SchemaError(f"{what}: keys must be exactly {sorted(expected)}")


def _list(v, what, lo, hi):
    if not isinstance(v, list) or not lo <= len(v) <= hi:
        raise SchemaError(f"{what}: must be a list of {lo} to {hi} items")
    if len(set(map(repr, v))) != len(v):
        raise SchemaError(f"{what}: duplicates")
    return v


def validate_action(obj, known_ids=None) -> dict:
    """Return a clean copy of a valid action or raise SchemaError.
    known_ids: if given, every extract result_id must be in it."""
    if not isinstance(obj, dict):
        raise SchemaError("action: not an object")
    action = obj.get("action")
    if not isinstance(action, str) or action not in _KEYS:
        raise SchemaError("action: unknown")
    _keys(obj, _KEYS[action], action)
    if action == "done":
        return {"action": "done"}

    need = _match(NEED_RE, obj["need"], "need")
    cts = _list(obj["claim_types"], "claim_types", 1, len(CLAIM_UNITS))
    for ct in cts:
        if not isinstance(ct, str) or ct not in CLAIM_UNITS:
            raise SchemaError("claim_types: unknown type")
    preset = obj["preset"]
    out = {"action": action, "need": need, "claim_types": list(cts)}

    if action == "search":
        q = _str(obj["query"], "query")
        if not q.strip() or len(q) > MAX_QUERY_CHARS or _CONTROL_RE.search(q):
            raise SchemaError("query: empty, too long or has control characters")
        if not isinstance(preset, str) or preset not in SEARCH_PRESETS:
            raise SchemaError("preset: not a search preset")
        out["query"] = q.strip()
    else:
        ids = _list(obj["result_ids"], "result_ids", 1, MAX_RESULT_IDS)
        for rid in ids:
            _match(RESULT_ID_RE, rid, "result_id")
            if known_ids is not None and rid not in known_ids:
                raise SchemaError("result_id: not seen in typed results")
        if not isinstance(preset, str) or preset not in EXTRACT_PRESETS:
            raise SchemaError("preset: not an extract preset")
        out["result_ids"] = list(ids)
    out["preset"] = preset
    return out


def validate_typed(obj) -> dict:
    """Validate one §3 typed object; return a clean copy or raise SchemaError."""
    _keys(obj, _TYPED_KEYS, "typed")
    need = _match(NEED_RE, obj["need"], "typed.need")
    if not isinstance(obj["found"], bool):
        raise SchemaError("typed.found: not a boolean")
    if not isinstance(obj["values"], list):
        raise SchemaError("typed.values: not a list")
    values = []
    for v in obj["values"]:
        _keys(v, _VALUE_KEYS, "typed.values[]")
        ct = _str(v["claim_type"], "claim_type")
        if ct not in CLAIM_UNITS:
            raise SchemaError("claim_type: unknown")
        num = v["value"]
        if isinstance(num, bool) or not isinstance(num, (int, float)) or not math.isfinite(num):
            raise SchemaError("value: not a finite number")
        unit = _str(v["unit"], "unit")
        if unit not in CLAIM_UNITS[ct]:
            raise SchemaError("unit: not allowed for claim_type")
        period = _match(PERIOD_RE, v["period"], "period")
        rid = _match(RESULT_ID_RE, v["result_id"], "result_id")
        values.append({"claim_type": ct, "value": num, "unit": unit, "period": period, "result_id": rid})
    return {"need": need, "found": obj["found"], "values": values}


def validate_typed_list(items) -> list:
    if not isinstance(items, list):
        raise SchemaError("typed_results: not a list")
    return [validate_typed(t) for t in items]


# JSON schema for Ollama's `format`. Flat on purpose (small models follow flat grammars better);
# validate_action enforces the per-action rules.
ACTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["search", "extract", "done"]},
        "need": {"type": "string", "pattern": "^[a-z0-9_]{1,32}$"},
        "claim_types": {"type": "array", "minItems": 1,
                        "items": {"type": "string", "enum": sorted(CLAIM_UNITS)}},
        "query": {"type": "string", "maxLength": MAX_QUERY_CHARS},
        "result_ids": {"type": "array", "minItems": 1, "maxItems": MAX_RESULT_IDS,
                       "items": {"type": "string", "pattern": "^r_[0-9]{2}$"}},
        "preset": {"type": "string", "enum": sorted(SEARCH_PRESETS | EXTRACT_PRESETS)},
    },
    "required": ["action"],
    "additionalProperties": False,
}
