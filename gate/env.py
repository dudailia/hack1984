"""Parse the repo .env file directly (never os.environ). Values are never printed."""
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(REPO_ROOT, ".env")


class Env:
    def __init__(self, values: dict):
        self._values = dict(values)

    def get(self, key, default=None):
        return self._values.get(key, default)

    def require(self, key) -> str:
        v = self._values.get(key)
        if not v:
            raise KeyError(f".env is missing {key}")
        return v

    def port(self, key) -> int:
        raw = self.require(key)
        try:
            p = int(raw)
        except ValueError:
            raise ValueError(f".env {key} is not a port number") from None
        if not 0 < p < 65536:
            raise ValueError(f".env {key} is out of range")
        return p

    def __repr__(self):
        return f"Env(keys={sorted(self._values)})"

    __str__ = __repr__


def load(path: str = DEFAULT_PATH) -> Env:
    values = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            elif " #" in val:
                val = val.split(" #", 1)[0].strip()
            values[key] = val
    return Env(values)
