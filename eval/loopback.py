"""Loopback-only guard and settings for eval/ (invariant 1). Never reads API keys.

eval/ talks to app/run.py on 127.0.0.1 only. install_audit_hook() makes any non-loopback socket connect raise,
so even a bug cannot reach the network from this process.
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED_KEYS = {"APP_PORT", "OLLAMA_MODEL"}
LOOPBACK_HOSTS = {"127.0.0.1", "::1"}
_installed = False


class NetworkRefused(RuntimeError):
    pass


def _audit(event, args):
    if event == "socket.connect":
        addr = args[1] if len(args) > 1 else None
        if isinstance(addr, tuple) and addr and addr[0] not in LOOPBACK_HOSTS:
            raise NetworkRefused("eval may connect to loopback only, not %r" % (addr[0],))
    elif event == "socket.getaddrinfo":
        host = args[0] if args else None
        if isinstance(host, bytes):
            host = host.decode("ascii", "replace")
        if host not in LOOPBACK_HOSTS and host not in (None, "localhost"):
            raise NetworkRefused("eval may resolve loopback only, not %r" % (host,))


def install_audit_hook():
    """Idempotent: sys.addaudithook cannot be removed, so install once per process."""
    global _installed
    if not _installed:
        sys.addaudithook(_audit)
        _installed = True


def env_value(key, default, env=None, env_file=None):
    """From the environment, else the one matching .env line, else default. Every other line is skipped unparsed."""
    if key not in ALLOWED_KEYS:
        raise ValueError("eval may not read %s" % key)
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


def app_port(env=None, env_file=None):
    raw = str(env_value("APP_PORT", "8700", env, env_file)).strip()
    if not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise ValueError("APP_PORT must be a port number 1-65535")
    return int(raw)


def planner_model(env=None, env_file=None):
    return env_value("OLLAMA_MODEL", "", env, env_file).strip() or None
