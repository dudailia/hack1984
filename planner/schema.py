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
    # real estate scenario (FORMATS §1): existing units only
    "cap_rate": {"percent"},
    "vacancy_rate": {"percent"},
    "interest_rate": {"percent"},
    "price_per_sqft": {"usd"},
}
UNITS = set().union(*CLAIM_UNITS.values())

# The claim types each Planner profile (one per demo scenario, app/scenario.py) may name. Halyard is the default
# and keeps exactly the original eight, so its prompt and grammar are unchanged byte for byte.
DEFAULT_PROFILE = "halyard"
PROFILE_CLAIM_TYPES = {
    "halyard": ("revenue", "revenue_growth", "ev_revenue_multiple", "ev_ebitda_multiple", "ebitda", "market_size",
                "employees", "founded_year"),
    "real_estate": ("interest_rate", "cap_rate", "vacancy_rate", "price_per_sqft", "market_size", "revenue_growth"),
}


def profile_claim_types(profile=None):
    """The claim types of a profile (None = the default). Raises ValueError for an unknown profile."""
    p = DEFAULT_PROFILE if profile is None else profile
    if not isinstance(p, str) or p not in PROFILE_CLAIM_TYPES:
        raise ValueError("unknown planner profile")
    return PROFILE_CLAIM_TYPES[p]
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


def validate_action(obj, known_ids=None, profile=None) -> dict:
    """Return a clean copy of a valid action or raise SchemaError.
    known_ids: if given, every extract result_id must be in it.
    profile: claim_types must be the profile's (None = the default, Halyard)."""
    allowed = profile_claim_types(profile)
    if not isinstance(obj, dict):
        raise SchemaError("action: not an object")
    action = obj.get("action")
    if not isinstance(action, str) or action not in _KEYS:
        raise SchemaError("action: unknown")
    _keys(obj, _KEYS[action], action)
    if action == "done":
        return {"action": "done"}

    need = _match(NEED_RE, obj["need"], "need")
    cts = _list(obj["claim_types"], "claim_types", 1, len(allowed))
    for ct in cts:
        if not isinstance(ct, str) or ct not in allowed:
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


# Preset safety net (qwen3:8b often answered extract + "general"). Only the preset is ever corrected, and only to a
# value from the fixed lists above, so this can never let model or web text through.
PRESETS = {"search": SEARCH_PRESETS, "extract": EXTRACT_PRESETS}
DEFAULT_PRESET = {"search": "general", "extract": "text"}


def normalize_preset(obj):
    """Return (copy, corrected). For a search or extract whose `preset` key holds anything outside that action's
    list, the copy gets the action's default preset. Nothing else changes: a missing preset is not added, an unknown
    action or extra key is left for validate_action to reject, and the input is never mutated."""
    if not isinstance(obj, dict):
        return obj, False
    action = obj.get("action")
    # str check first: `[] in PRESETS` raises TypeError (unhashable), which next_action does not catch
    if not isinstance(action, str) or action not in PRESETS or "preset" not in obj:
        return dict(obj), False
    preset = obj["preset"]
    if isinstance(preset, str) and preset in PRESETS[action]:
        return dict(obj), False
    fixed = dict(obj)
    fixed["preset"] = DEFAULT_PRESET[action]
    return fixed, True


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


# JSON schema for Ollama's `format`: one anyOf branch per action, each with its own preset list and exactly its own
# keys, so the grammar cannot produce an extract with a search preset (the flat schema allowed any preset with any
# action, and qwen3:8b chose extract + "general" every time when nudged). Checked on Ollama 0.40.15 with qwen3:8b:
# the same nudge gives extract + "text" 5/5 with this schema, extract + "general" 5/5 with the old flat one.
# validate_action still enforces every rule; normalize_preset stays as the safety net.
_NEED = {"type": "string", "pattern": "^[a-z0-9_]{1,32}$"}


def _branch(action, extra):
    props = {"action": {"type": "string", "enum": [action]}, **extra}
    return {"type": "object", "properties": props, "required": sorted(props), "additionalProperties": False}


def action_json_schema(profile=None):
    """The Ollama grammar for a profile: claim_types enum = that profile's types (None = the default, Halyard)."""
    cts = {"type": "array", "minItems": 1, "items": {"type": "string", "enum": sorted(profile_claim_types(profile))}}
    return {
        "anyOf": [
            _branch("search", {"need": _NEED, "claim_types": cts,
                               "query": {"type": "string", "maxLength": MAX_QUERY_CHARS},
                               "preset": {"type": "string", "enum": sorted(SEARCH_PRESETS)}}),
            _branch("extract", {"need": _NEED, "claim_types": cts,
                                "result_ids": {"type": "array", "minItems": 1, "maxItems": MAX_RESULT_IDS,
                                               "items": {"type": "string", "pattern": "^r_[0-9]{2}$"}},
                                "preset": {"type": "string", "enum": sorted(EXTRACT_PRESETS)}}),
            _branch("done", {}),
        ]
    }


ACTION_JSON_SCHEMA = action_json_schema()  # Halyard, the default
