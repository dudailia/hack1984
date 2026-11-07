"""STUB run loop (Ilia). Aayush replaces it with app/loop.py; app/run.py uses this only while app.loop is missing.

Same contract as the real loop (Aayush, 15:37):
    start_run(mode, source, plant_careless, question, emit) -> session_id
- returns the session id immediately and runs in its own background thread;
- emit(type, session_id, data), positional, session_id always passed;
- raises ValueError for bad input, and ValueError("... already active") while a run is active.

It replays one recorded run from shared/fixtures/demo_events.jsonl through emit, with the fixture's session id
replaced by a fresh one and run_started set to the requested mode, source, plant_careless and question. Nothing
is sent anywhere and no Gate session exists, so /api/verify on a stub run gets no bundle (502), never VALID.
"""
import json
import os
import secrets
import string
import threading

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS_FILE = os.path.join(REPO, "shared", "fixtures", "demo_events.jsonl")
MODES = ("single_agent", "compromised", "two_minds", "doublethink")
FAKE_ONLY = ("single_agent", "compromised", "two_minds")
TIME_SCALE = 1.0  # 1.0 = the recorded timing, 0 = as fast as possible (tests)
SKIP_TYPES = ("beat", "proof_result")

_lock = threading.Lock()
_thread = None
_cancel = threading.Event()


def _fixture_session(mode, source, plant_careless):
    if plant_careless:
        return "s_careless1"
    if mode in ("single_agent", "compromised"):
        return "s_compromised1"
    return "s_dtreal1" if source == "real" else "s_dtfake1"


def _load(fixture_sid):
    with open(EVENTS_FILE, encoding="utf-8") as f:
        envs = [json.loads(line) for line in f if line.strip()]
    return [e for e in envs if e["session_id"] == fixture_sid and e["type"] not in SKIP_TYPES]


def _new_sid():
    alnum = string.ascii_lowercase + string.digits
    return "s_stub" + "".join(secrets.choice(alnum) for _ in range(8))


def _replay(envs, fixture_sid, sid, overrides, emit):
    global _thread
    try:
        prev_t = envs[0]["t_ms"] if envs else 0
        for env in envs:
            delay = max(0, env["t_ms"] - prev_t) / 1000.0 * TIME_SCALE
            prev_t = env["t_ms"]
            if delay and _cancel.wait(delay):
                return
            if _cancel.is_set():
                return
            data = json.loads(json.dumps(env["data"]).replace(fixture_sid, sid))
            if env["type"] == "run_started":
                data.update(overrides)
            elif "source" in data and env["type"] in ("memo_loaded", "run_done"):
                data["source"] = overrides["source"]
            emit(env["type"], sid, data)
    finally:
        with _lock:
            _thread = None


def start_run(mode, source, plant_careless, question, emit):
    global _thread
    if mode not in MODES:
        raise ValueError("unknown mode %r" % (mode,))
    if source not in ("real", "fake"):
        raise ValueError("unknown source %r" % (source,))
    if mode in FAKE_ONLY and source != "fake":
        raise ValueError("mode %s requires source fake" % mode)
    if not isinstance(plant_careless, bool) or not isinstance(question, str) or not question:
        raise ValueError("plant_careless must be a bool and question a non-empty string")
    fixture_sid = _fixture_session(mode, source, plant_careless)
    envs = _load(fixture_sid)
    sid = _new_sid()
    overrides = {"mode": mode, "source": source, "plant_careless": plant_careless, "question": question}
    with _lock:
        if _thread is not None:
            raise ValueError("a run is already active")
        _cancel.clear()
        _thread = threading.Thread(target=_replay, args=(envs, fixture_sid, sid, overrides, emit), daemon=True,
                                   name="loop-stub-" + sid)
        _thread.start()
    return sid


def cancel():
    """Stop the active replay (tests)."""
    _cancel.set()
    wait_idle(5)


def wait_idle(timeout=None):
    """Wait until no replay is running; True if idle."""
    with _lock:
        t = _thread
    if t is not None:
        t.join(timeout)
    with _lock:
        return _thread is None
