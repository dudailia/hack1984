"""Parse the Anthropic response into claims. Anything off-schema is dropped; never raises."""
import json

from reader.schema import check_claim

_MAX_CANDIDATES = 50


def _text_of(response):
    if isinstance(response, (str, bytes)):
        try:
            response = json.loads(response)
        except ValueError:
            return ""
    if not isinstance(response, dict) or not isinstance(response.get("content"), list):
        return ""
    return "".join(b["text"] for b in response["content"]
                   if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str))


def _claims_object(text):
    decoder = json.JSONDecoder()
    start = text.find("{")
    tries = 0
    while start != -1 and tries < _MAX_CANDIDATES:
        tries += 1
        try:
            obj, _ = decoder.raw_decode(text, start)
        except ValueError:
            obj = None
        if isinstance(obj, dict) and isinstance(obj.get("claims"), list):
            return obj
        start = text.find("{", start + 1)
    return None


def parse_response(job, response_json):
    obj = _claims_object(_text_of(response_json))
    if obj is None:
        return []
    return [c for c in obj["claims"] if check_claim(c) is None]
