"""Local model calls for the single agent, in the Ollama request shape of FORMATS §2.

`think: false` is required (thinking costs about 2 min per call); the system message starts with today's date
(qwen3 otherwise assumes 2024). The model's reply is constrained by a JSON schema and validated again in code.
"""
import datetime
import json

from baseline import config, gate_client, loopback

ACTIONS = ["search", "done"]
ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ACTIONS},
        "need": {"type": "string"},
        "query": {"type": "string", "maxLength": gate_client.MAX_QUERY},
        "preset": {"type": "string", "enum": list(gate_client.PRESETS)},
    },
    "required": ["action"],
}


def build_request(model, today, system, user):
    return {
        "model": model,
        "think": False,
        "stream": False,
        "format": ACTION_SCHEMA,
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": system if system.startswith("Today is ") else
             "Today is %s. %s" % (today.isoformat(), system)},
            {"role": "user", "content": user},
        ],
    }


def validate_action(action, needs):
    """Return a clean action dict, or None if the model's output is unusable."""
    if not isinstance(action, dict) or action.get("action") not in ACTIONS:
        return None
    if action["action"] == "done":
        return {"action": "done"}
    query = action.get("query")
    if not isinstance(query, str) or not query.strip() or len(query.strip()) > gate_client.MAX_QUERY:
        return None
    need = action.get("need") or (needs[0] if needs else None)
    if need not in needs:
        return None
    preset = action.get("preset") or "general"
    if preset not in gate_client.PRESETS:
        return None
    return {"action": "search", "need": need, "query": query.strip(), "preset": preset}


class OllamaClient:
    def __init__(self, port, model, today=None, timeout=300):
        self.port = loopback.check_port(port)
        self.model = config.local_model(model)
        self.today = today
        self.timeout = timeout

    def next_action(self, system, user):
        """The model's reply parsed as JSON (unvalidated), or None if the reply is not usable JSON."""
        today = self.today or datetime.date.today()
        status, body = loopback.post_json(self.port, "/api/chat", build_request(self.model, today, system, user),
                                          timeout=self.timeout)
        if status != 200 or not isinstance(body, dict):
            return None
        content = (body.get("message") or {}).get("content")
        if not isinstance(content, str):
            return None
        try:
            return json.loads(content)
        except ValueError:
            return None
