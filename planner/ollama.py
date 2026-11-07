"""Ollama client for the Planner. Loopback only. Reads OLLAMA_MODEL and OLLAMA_PORT from the .env file
(never from process variables, never any other key)."""
import json
import os
import urllib.error
import urllib.request

from planner.schema import ACTION_JSON_SCHEMA

OLLAMA_HOST = "127.0.0.1"
DEFAULT_PORT = 11434
DEFAULT_TIMEOUT = 120
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
_WANTED = ("OLLAMA_MODEL", "OLLAMA_PORT")


class OllamaError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


# ProxyHandler({}) disables proxies taken from process variables; a proxy would carry the memo off loopback.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def load_env(path=ENV_PATH) -> dict:
    found = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("export "):
                line = line[len("export "):].lstrip()
            key, sep, val = line.partition("=")
            key = key.strip()
            if not sep or key not in _WANTED:
                continue  # every other line, API keys included, is dropped unread
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            elif " #" in val:
                val = val.split(" #", 1)[0].strip()
            found[key] = val
    model = found.get("OLLAMA_MODEL")
    if not model:
        raise ValueError(".env is missing OLLAMA_MODEL")
    if is_cloud_model(model):
        raise ValueError(".env OLLAMA_MODEL is an Ollama cloud model; the memo must stay local")
    raw_port = found.get("OLLAMA_PORT") or str(DEFAULT_PORT)
    try:
        port = int(raw_port)
    except ValueError:
        raise ValueError(".env OLLAMA_PORT is not a number") from None
    if not 0 < port < 65536:
        raise ValueError(".env OLLAMA_PORT is out of range")
    return {"OLLAMA_MODEL": model, "OLLAMA_PORT": port}


def is_cloud_model(name) -> bool:
    """Ollama cloud models (names ending in "cloud", e.g. "-cloud", ":cloud") forward the prompt to ollama.com."""
    return not isinstance(name, str) or name.strip().lower().endswith("cloud")


def build_body(model, messages) -> dict:
    return {"model": model, "think": False, "stream": False, "format": ACTION_JSON_SCHEMA,
            "options": {"temperature": 0}, "messages": messages}


def chat(messages, *, env=None, timeout=DEFAULT_TIMEOUT, urlopen=_OPENER.open) -> str:
    """POST to the local Ollama /api/chat; return the assistant message content."""
    env = env or load_env()
    if is_cloud_model(env["OLLAMA_MODEL"]):
        raise OllamaError("refusing an Ollama cloud model; the memo must stay local")
    port = int(env["OLLAMA_PORT"])
    url = f"http://{OLLAMA_HOST}:{port}/api/chat"
    data = json.dumps(build_body(env["OLLAMA_MODEL"], messages), ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except (OSError, ValueError) as e:  # URLError, HTTPError, timeouts are OSError subclasses
        raise OllamaError(f"ollama request failed: {type(e).__name__}") from None
    try:
        content = json.loads(raw)["message"]["content"]
    except (ValueError, KeyError, TypeError):
        raise OllamaError("ollama response has no message content") from None
    if not isinstance(content, str):
        raise OllamaError("ollama message content is not a string")
    return content
