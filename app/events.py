"""Event hub for the UI stream (shared/FORMATS.md §10). Standard library only, thread-safe.

The run loop calls `hub.emit(type, session_id, data)`. Each event gets the §10 envelope (seq +1 across the whole
stream, t_ms since the hub started, UTC time, session_id, type, data), is kept in its session's list, and is
pushed to every subscriber. A new subscriber first gets the current run (the session of the latest run_started)
after its Last-Event-ID, then everything live, with no gap and no duplicate.
"""
import copy
import datetime
import json
import queue
import threading
import time

PING = b": ping\n\n"


def iso_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def frame(env):
    """One SSE frame: `id: <seq>`, then the envelope as one line of JSON. No `event:` line (§10)."""
    data = json.dumps(env, ensure_ascii=False, separators=(",", ":"))
    return ("id: %d\ndata: %s\n\n" % (env["seq"], data)).encode("utf-8")


class Subscription:
    def __init__(self, backlog):
        self.backlog = backlog
        self.queue = queue.Queue()


class EventHub:
    def __init__(self, clock=time.monotonic, now=iso_now):
        self._lock = threading.Lock()
        self._clock, self._now = clock, now
        self._t0 = clock()
        self._seq = 0
        self._sessions = {}       # session_id -> [envelope]
        self._finished = set()
        self._current = None      # session of the latest run_started
        self._subs = []
        self._closed = False

    def emit(self, type, session_id, data):
        """Record and broadcast one event; returns its envelope. session_id may be None (beat only)."""
        if not isinstance(type, str) or not type:
            raise ValueError("event type must be a non-empty string")
        if session_id is not None and not isinstance(session_id, str):
            raise ValueError("session_id must be a string or None")
        if not isinstance(data, dict):
            raise ValueError("event data must be a dict")
        data = copy.deepcopy(data)
        with self._lock:
            self._seq += 1
            env = {"seq": self._seq, "t_ms": int((self._clock() - self._t0) * 1000), "time": self._now(),
                   "session_id": session_id, "type": type, "data": data}
            if session_id is not None:
                self._sessions.setdefault(session_id, []).append(env)
                if type == "run_started":
                    self._current = session_id
                elif type == "run_done":
                    self._finished.add(session_id)
            for sub in self._subs:
                sub.queue.put(env)  # under the lock, so every subscriber sees seq order
        return env

    def subscribe(self, last_event_id=None):
        with self._lock:
            run = self._sessions.get(self._current, []) if self._current else []
            after = last_event_id if isinstance(last_event_id, int) else 0
            sub = Subscription([e for e in run if e["seq"] > after])
            if self._closed:
                sub.queue.put(None)
            else:
                self._subs.append(sub)
        return sub

    def unsubscribe(self, sub):
        with self._lock:
            if sub in self._subs:
                self._subs.remove(sub)

    def known(self, session_id):
        with self._lock:
            return session_id in self._sessions

    def finished(self, session_id):
        with self._lock:
            return session_id in self._finished

    def running(self):
        """The session of the latest run_started if it has no run_done yet, else None."""
        with self._lock:
            if self._current is not None and self._current not in self._finished:
                return self._current
            return None

    def events(self, session_id):
        with self._lock:
            return list(self._sessions.get(session_id, []))

    def close(self):
        """Wake every subscriber with None so streaming handlers end (shutdown)."""
        with self._lock:
            self._closed = True
            for sub in self._subs:
                sub.queue.put(None)
            self._subs = []
