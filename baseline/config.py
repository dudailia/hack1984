"""Settings for the baseline: loopback ports and the Ollama model name. Never API keys.

A value comes from the environment, else from the one matching line of the repo's .env, else the default.
Every other .env line (API keys included) is skipped unparsed and not kept.
"""
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED_KEYS = {"APP_PORT", "GATE_PORT", "FAKE_TAVILY_PORT", "OLLAMA_PORT", "OLLAMA_MODEL"}
DEFAULT_MODEL = "qwen3:4b"  # FORMATS §0: qwen3:4b for development, qwen3:8b on the demo laptop
# A local library model: name[:tag], no registry or namespace path. Ollama "cloud" models (tag ending in
# "cloud") run on ollama.com, so the memo would leave the machine outside the Gate (invariants 1 and 5).
_LOCAL_MODEL = re.compile(r"[a-z0-9][a-z0-9._-]*(?::[a-z0-9][a-z0-9._-]*)?", re.IGNORECASE)


def env_value(key, default, env=None, env_file=None):
    if key not in ALLOWED_KEYS:
        raise ValueError("baseline may not read %s" % key)
    env = os.environ if env is None else env
    raw = env.get(key)
    if raw is None:
        raw = _from_env_file(key, env_file or os.path.join(REPO, ".env"))
    return default if raw is None else raw


def _from_env_file(key, path):
    try:
        f = open(path, encoding="utf-8")
    except FileNotFoundError:
        return None
    with f:
        for line in f:
            s = line.strip()
            if s.startswith("export "):
                s = s[len("export "):].lstrip()
            if s.startswith(key + "="):
                return s.split("=", 1)[1].split("#", 1)[0].strip().strip("'\"")
    return None


def _port(key, default, env, env_file):
    raw = str(env_value(key, str(default), env, env_file)).strip()
    if not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise ValueError("%s must be a port number 1-65535" % key)
    return int(raw)


def gate_port(env=None, env_file=None):
    return _port("GATE_PORT", 8701, env, env_file)


def ollama_port(env=None, env_file=None):
    return _port("OLLAMA_PORT", 11434, env, env_file)


def local_model(name):
    """Return the model name stripped, or raise ValueError unless it names a local (non-cloud) model."""
    name = name.strip() if isinstance(name, str) else name
    if not isinstance(name, str) or not _LOCAL_MODEL.fullmatch(name) or name.lower().endswith("cloud"):
        raise ValueError("OLLAMA_MODEL must name a local model (no cloud tag, no registry path), got %r" % (name,))
    return name


def ollama_model(env=None, env_file=None):
    return local_model(env_value("OLLAMA_MODEL", DEFAULT_MODEL, env, env_file).strip() or DEFAULT_MODEL)
