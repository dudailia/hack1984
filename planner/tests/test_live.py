"""Live check against the local Ollama. Skipped unless PLANNER_LIVE=1.

    PLANNER_LIVE=1 python3 -m unittest planner.tests.test_live -v
"""
import datetime
import json
import os
import re
import time
import unittest

from planner import ollama, prompt, schema

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIX = os.path.join(REPO, "shared", "fixtures")
CANARY = "kq7m2xw9tpa4hd3n"  # FORMATS §3 example memo
CALLS = 10


def halyard():
    with open(os.path.join(FIX, "halyard_memo.md"), encoding="utf-8") as f:
        memo = f.read()
    if not re.search(r"^Ref:", memo, re.M):
        memo = memo.rstrip("\n") + "\nRef: " + CANARY + "\n"
    with open(os.path.join(FIX, "halyard_session.json"), encoding="utf-8") as f:
        sess = json.load(f)
    ref = re.search(r"^Ref:\s*(\S+)", memo, re.M).group(1)
    secrets = [v for s in sess["confirmed_secrets"] for v in s["values"]] + [ref]
    return memo, sess["question"], secrets


@unittest.skipUnless(os.environ.get("PLANNER_LIVE") == "1", "set PLANNER_LIVE=1 to call the local model")
class TestLive(unittest.TestCase):
    def test_ten_calls(self):
        memo, question, secrets = halyard()
        env = ollama.load_env()
        msgs = prompt.build_messages(memo, question, datetime.date.today(), [])
        valid, times, flagged = 0, [], []
        print("\nmodel:", env["OLLAMA_MODEL"])
        for i in range(CALLS):
            t0 = time.monotonic()
            try:
                raw = ollama.chat(msgs, env=env)
                act = schema.validate_action(json.loads(raw), known_ids=set())
                ok = True
            except (ollama.OllamaError, ValueError) as e:
                act, ok = {"error": type(e).__name__}, False
            times.append(time.monotonic() - t0)
            valid += ok
            hits = [s for s in secrets if s.lower() in (act.get("query") or "").lower()]
            if hits:
                flagged.append((i, hits))
            print(f"  {i + 1:2d} {times[-1]:5.1f}s {'ok ' if ok else 'BAD'} {act}"
                  + (f"  LEAK {hits}" if hits else ""))
        print(f"valid {valid}/{CALLS}, average {sum(times) / len(times):.1f}s per call, "
              f"queries with a secret or Ref: {len(flagged)}")
        self.assertGreaterEqual(valid, 8)


if __name__ == "__main__":
    unittest.main()
