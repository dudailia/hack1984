"""EventHub: §10 envelope, global seq, replay of the current run, Last-Event-ID, thread safety, frames."""
import json
import re
import threading
import unittest

from app import events

TIME_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")


def start(hub, sid):
    return hub.emit("run_started", sid, {"mode": "doublethink", "source": "fake", "plant_careless": False,
                                         "question": "q"})


class EnvelopeTest(unittest.TestCase):
    def test_envelope_exact(self):
        hub = events.EventHub()
        env = start(hub, "s_aaaaaaaa")
        self.assertEqual(list(env), ["seq", "t_ms", "time", "session_id", "type", "data"])
        self.assertEqual(env["seq"], 1)
        self.assertIsInstance(env["t_ms"], int)
        self.assertGreaterEqual(env["t_ms"], 0)
        self.assertRegex(env["time"], TIME_RE)
        self.assertEqual((env["session_id"], env["type"]), ("s_aaaaaaaa", "run_started"))
        env2 = hub.emit("memo_loaded", "s_aaaaaaaa", {"memo_id": "halyard"})
        self.assertEqual(env2["seq"], 2)
        self.assertGreaterEqual(env2["t_ms"], env["t_ms"])

    def test_seq_is_global_across_sessions(self):
        hub = events.EventHub()
        start(hub, "s_aaaaaaaa")
        self.assertEqual(hub.emit("run_done", "s_aaaaaaaa", {})["seq"], 2)
        self.assertEqual(start(hub, "s_bbbbbbbb")["seq"], 3)

    def test_bad_input(self):
        hub = events.EventHub()
        for t, sid, data in (("", "s_a", {}), (5, "s_a", {}), ("ledger_row", "s_a", "not a dict"),
                             ("ledger_row", 7, {})):
            with self.subTest(t=t, sid=sid), self.assertRaises(ValueError):
                hub.emit(t, sid, data)

    def test_data_is_copied(self):
        hub = events.EventHub()
        data = {"x": [1]}
        start(hub, "s_aaaaaaaa")
        hub.emit("ledger_row", "s_aaaaaaaa", data)
        data["x"].append(2)
        self.assertEqual(hub.events("s_aaaaaaaa")[-1]["data"], {"x": [1]})


class FrameTest(unittest.TestCase):
    def test_frame_format(self):
        hub = events.EventHub()
        env = hub.emit("run_started", "s_aaaaaaaa", {"question": "line one\nline two \u00e9"})
        raw = events.frame(env).decode("utf-8")
        self.assertTrue(raw.startswith("id: 1\ndata: "))
        self.assertTrue(raw.endswith("\n\n"))
        self.assertNotIn("event:", raw)
        self.assertEqual(raw.count("\n"), 3, "data must be one line")
        self.assertEqual(json.loads(raw.split("data: ", 1)[1]), env)
        self.assertEqual(events.PING, b": ping\n\n")


class ReplayTest(unittest.TestCase):
    def setUp(self):
        self.hub = events.EventHub()
        start(self.hub, "s_old00000")
        self.hub.emit("run_done", "s_old00000", {})
        start(self.hub, "s_new00000")                      # seq 3
        self.hub.emit("memo_loaded", "s_new00000", {})       # seq 4
        self.hub.emit("parties_confirmed", "s_new00000", {})  # seq 5

    def test_replays_current_run_only(self):
        sub = self.hub.subscribe()
        self.assertEqual([e["seq"] for e in sub.backlog], [3, 4, 5])
        self.assertEqual({e["session_id"] for e in sub.backlog}, {"s_new00000"})

    def test_last_event_id_resume(self):
        sub = self.hub.subscribe(last_event_id=4)
        self.assertEqual([e["seq"] for e in sub.backlog], [5])
        sub = self.hub.subscribe(last_event_id=5)
        self.assertEqual(sub.backlog, [])
        sub = self.hub.subscribe(last_event_id=1)  # an id from an older run: the whole current run
        self.assertEqual([e["seq"] for e in sub.backlog], [3, 4, 5])

    def test_live_after_backlog_no_gap_no_duplicate(self):
        sub = self.hub.subscribe(last_event_id=4)
        self.hub.emit("ledger_row", "s_new00000", {})
        self.hub.emit("proof_result", "s_old00000", {})  # a late event of an older session still goes live
        live = [sub.queue.get(timeout=1)["seq"] for _ in range(2)]
        self.assertEqual([e["seq"] for e in sub.backlog] + live, [5, 6, 7])
        self.hub.unsubscribe(sub)
        self.hub.emit("ledger_row", "s_new00000", {})
        self.assertTrue(sub.queue.empty())

    def test_known_and_finished(self):
        self.assertTrue(self.hub.known("s_old00000"))
        self.assertTrue(self.hub.finished("s_old00000"))
        self.assertTrue(self.hub.known("s_new00000"))
        self.assertFalse(self.hub.finished("s_new00000"))
        self.assertFalse(self.hub.known("s_nope0000"))
        self.assertFalse(self.hub.finished("s_nope0000"))

    def test_no_run_yet(self):
        self.assertEqual(events.EventHub().subscribe().backlog, [])

    def test_close_wakes_subscribers(self):
        sub = self.hub.subscribe()
        self.hub.close()
        self.assertIsNone(sub.queue.get(timeout=1))


class ThreadSafetyTest(unittest.TestCase):
    def test_concurrent_emit(self):
        hub = events.EventHub()
        start(hub, "s_aaaaaaaa")
        sub = hub.subscribe()

        def worker():
            for _ in range(200):
                hub.emit("ledger_row", "s_aaaaaaaa", {})

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        seqs = [e["seq"] for e in hub.events("s_aaaaaaaa")]
        self.assertEqual(seqs, list(range(1, 1602)))
        live = [sub.queue.get(timeout=1)["seq"] for _ in range(1600)]
        self.assertEqual(live, list(range(2, 1602)), "subscribers see events in seq order")


if __name__ == "__main__":
    unittest.main()
