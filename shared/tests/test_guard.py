"""shared/guard.py tests. Every case runs in a fresh child Python process: an audit hook cannot be removed.

Nothing here reaches the internet: blocked calls raise inside the audit hook, before any packet, and the
addresses used are documentation ranges (192.0.2.1, 2001:db8::1).
"""
import glob
import json
import os
import re
import subprocess
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Python 3.13 raises no audit event when an already-resolved ctypes function is called (3.14 added
# ctypes.call_function to those calls), so that one case is a documented limit there.
CTYPES_CALLS_AUDITED = sys.version_info >= (3, 14)

PRELUDE = r'''
import json, os, socket, subprocess, sys, tempfile, urllib.error, urllib.request
sys.path.insert(0, REPO)
R = {}

def attempt(name, fn):
    try:
        fn()
        R[name] = "ok"
    except PermissionError:
        R[name] = "denied"
    except urllib.error.URLError as e:
        R[name] = "denied" if isinstance(e.reason, PermissionError) else "URLError"
    except Exception as e:
        R[name] = type(e).__name__

def listener(fam=socket.AF_INET, host="127.0.0.1"):
    s = socket.socket(fam)
    s.bind((host, 0))
    s.listen(16)
    return s

def free():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p

L = {k: listener() for k in ("gate", "ollama", "other")}
P = {"GATE_PORT": L["gate"].getsockname()[1], "OLLAMA_PORT": L["ollama"].getsockname()[1],
     "APP_PORT": free(), "FAKE_TAVILY_PORT": free()}
OTHER = L["other"].getsockname()[1]
try:
    L6 = listener(socket.AF_INET6, "::1")
    P6 = L6.getsockname()[1]
except OSError:
    L6, P6 = None, None
TMP = tempfile.mkdtemp()
ENV = os.path.join(TMP, ".env")
with open(ENV, "w") as f:
    f.write("TAVILY_API_KEY=tvly-SHOULD-NOT-LEAK\nANTHROPIC_API_KEY=sk-ant-SHOULD-NOT-LEAK\n")
    f.write("".join("%s=%d\n" % kv for kv in P.items()))

def conn(port, host="127.0.0.1", fam=socket.AF_INET):
    s = socket.socket(fam)
    s.settimeout(2)
    try:
        s.connect((host, port))
    finally:
        s.close()

def bind(port, host="127.0.0.1"):
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((host, port))
    finally:
        s.close()

def udp(host, port, fam=socket.AF_INET):
    s = socket.socket(fam, socket.SOCK_DGRAM)
    try:
        s.sendto(b"x", (host, port))
    finally:
        s.close()

from shared import guard
'''

EPILOGUE = "\nprint('RESULT ' + json.dumps(R))\n"


def run_child(body, env_extra=None, role=None):
    """Run PRELUDE + (install role) + body in a fresh interpreter; return the R dict."""
    code = "REPO = %r\n" % REPO + PRELUDE
    if role:
        code += "guard.install_loopback_guard(%r, env_path=ENV)\n" % role
    code += body + EPILOGUE
    env = dict(os.environ)
    for k in list(env):
        if k.lower().endswith("_proxy"):
            del env[k]
    env.update(env_extra or {})
    p = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60, env=env,
                       cwd=REPO)
    lines = [ln for ln in p.stdout.splitlines() if ln.startswith("RESULT ")]
    if not lines:
        raise AssertionError("child produced no result.\nstdout:\n%s\nstderr:\n%s" % (p.stdout, p.stderr))
    return json.loads(lines[-1][len("RESULT "):])


class TestPorts(unittest.TestCase):
    BODY = '''
attempt("conn_gate", lambda: conn(P["GATE_PORT"]))
attempt("conn_ollama", lambda: conn(P["OLLAMA_PORT"]))
attempt("conn_other", lambda: conn(OTHER))
attempt("conn_localhost_gate", lambda: conn(P["GATE_PORT"], host="localhost"))
attempt("bind_app", lambda: bind(P["APP_PORT"]))
attempt("bind_fake", lambda: bind(P["FAKE_TAVILY_PORT"]))
attempt("bind_zero", lambda: bind(0))
attempt("udp_gate", lambda: udp("127.0.0.1", P["GATE_PORT"]))
attempt("udp_other", lambda: udp("127.0.0.1", OTHER))
'''
    EXPECT = {
        "app": dict(conn_gate="ok", conn_ollama="ok", conn_other="denied", conn_localhost_gate="ok", bind_app="ok",
                    bind_fake="denied", bind_zero="denied", udp_gate="ok", udp_other="denied"),
        "planner": dict(conn_gate="denied", conn_ollama="ok", conn_other="denied", conn_localhost_gate="denied",
                        bind_app="denied", bind_fake="denied", bind_zero="denied", udp_gate="denied",
                        udp_other="denied"),
        "baseline": dict(conn_gate="ok", conn_ollama="ok", conn_other="denied", conn_localhost_gate="ok",
                         bind_app="denied", bind_fake="denied", bind_zero="denied", udp_gate="ok",
                         udp_other="denied"),
        "fake_tavily": dict(conn_gate="denied", conn_ollama="denied", conn_other="denied",
                            conn_localhost_gate="denied", bind_app="denied", bind_fake="ok", bind_zero="denied",
                            udp_gate="denied", udp_other="denied"),
    }

    def test_each_role(self):
        for role, expect in self.EXPECT.items():
            with self.subTest(role=role):
                self.assertEqual(run_child(self.BODY, role=role), expect)

    def test_ipv6_loopback_ports(self):
        r = run_child('''
if P6 is None:
    R["skip"] = "no ipv6"
else:
    # the v6 listener's port is not on any list: the guard checks ports on ::1 exactly like on 127.0.0.1
    attempt("conn_v6_unlisted", lambda: conn(P6, host="::1", fam=socket.AF_INET6))
''', role="app")
        if r.get("skip"):
            self.skipTest("no IPv6 loopback")
        self.assertEqual(r, {"conn_v6_unlisted": "denied"})


class TestNonLoopback(unittest.TestCase):
    BODY = '''
attempt("v4", lambda: conn(80, host="192.0.2.1"))
attempt("v6", lambda: conn(80, host="2001:db8::1", fam=socket.AF_INET6))
attempt("v4_mapped", lambda: conn(80, host="::ffff:192.0.2.1", fam=socket.AF_INET6))
attempt("udp_v4", lambda: udp("192.0.2.1", 53))
attempt("bind_any", lambda: bind(P["APP_PORT"], host="0.0.0.0"))
attempt("dns_getaddrinfo", lambda: socket.getaddrinfo("example.com", 443))
attempt("dns_gethostbyname", lambda: socket.gethostbyname("example.com"))
attempt("dns_localhost", lambda: socket.getaddrinfo("localhost", P["GATE_PORT"]))
attempt("urllib_external", lambda: urllib.request.urlopen("https://example.com/", timeout=2))
'''

    def test_blocked_for_every_role(self):
        for role in ("app", "planner", "baseline", "fake_tavily"):
            with self.subTest(role=role):
                r = run_child(self.BODY, role=role)
                for k in ("v4", "v6", "v4_mapped", "udp_v4", "bind_any", "dns_getaddrinfo", "dns_gethostbyname",
                          "urllib_external"):
                    self.assertEqual(r[k], "denied", k)
                self.assertEqual(r["dns_localhost"], "ok")

    def test_unix_sockets_refused(self):
        body = '''
UPATH = os.path.join(TMP, "listen.sock")
ul = socket.socket(socket.AF_UNIX)            # a Unix listener that existed before the guard
ul.bind(UPATH); ul.listen(4)
ud = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
DPATH = os.path.join(TMP, "dgram.sock"); ud.bind(DPATH)
guard.install_loopback_guard(ROLE, env_path=ENV)
def bind_path():
    s = socket.socket(socket.AF_UNIX)
    try: s.bind(os.path.join(TMP, "new.sock"))
    finally: s.close()
def bind_abstract():
    s = socket.socket(socket.AF_UNIX)
    try: s.bind("\\0doublethink-test-%d" % os.getpid())
    finally: s.close()
def connect_path():
    s = socket.socket(socket.AF_UNIX)
    try: s.connect(UPATH)
    finally: s.close()
def connect_ex_path():
    s = socket.socket(socket.AF_UNIX)
    try:
        if s.connect_ex(UPATH) != 0: raise OSError("not connected")
    finally: s.close()
def sendto_path():
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try: s.sendto(b"x", DPATH)
    finally: s.close()
def socketpair():
    a, b = socket.socketpair()
    a.sendall(b"x"); assert b.recv(1) == b"x"
    a.close(); b.close()
attempt("bind_path", bind_path)
attempt("bind_abstract", bind_abstract)
attempt("connect_path", connect_path)
attempt("connect_ex_path", connect_ex_path)
attempt("sendto_path", sendto_path)
attempt("socketpair", socketpair)
'''
        for role in ("app", "planner", "baseline", "fake_tavily"):
            with self.subTest(role=role):
                r = run_child("ROLE = %r\n" % role + body)
                self.assertEqual(r, {"bind_path": "denied", "bind_abstract": "denied", "connect_path": "denied",
                                     "connect_ex_path": "denied", "sendto_path": "denied", "socketpair": "ok"})

    def test_asyncio_loop_still_works(self):
        """asyncio's self-pipe is a socketpair: refusing Unix sockets must not break an event loop."""
        r = run_child('''
import asyncio
async def main():
    await asyncio.sleep(0)
    return 1
attempt("loop", lambda: asyncio.run(main()))
''', role="app")
        self.assertEqual(r, {"loop": "ok"})


class TestCtypes(unittest.TestCase):
    def test_import_after_install_refused(self):
        body = '''
R["preloaded"] = "ctypes" in sys.modules
guard.install_loopback_guard(ROLE, env_path=ENV)
attempt("import", lambda: __import__("ctypes"))
'''
        for role in ("app", "planner", "baseline", "fake_tavily"):
            with self.subTest(role=role):
                r = run_child("ROLE = %r\n" % role + body)
                self.assertEqual(r, {"preloaded": False, "import": "denied"})

    def test_import_of_ctypes_parts_refused(self):
        # 3.13's ctypes catches OSError (PermissionError included) around its own dlopen at import, so the
        # import itself must be refused, for the package, its submodules and the _ctypes extension
        r = run_child('''
attempt("ctypes_util", lambda: __import__("ctypes.util"))
attempt("_ctypes", lambda: __import__("_ctypes"))
attempt("importlib", lambda: __import__("importlib").import_module("ctypes"))
R["in_modules"] = "ctypes" in sys.modules or "_ctypes" in sys.modules
''', role="planner")
        self.assertEqual(r, {"ctypes_util": "denied", "_ctypes": "denied", "importlib": "denied",
                             "in_modules": False})

    PRE_IMPORTED = '''
import ctypes
libc = ctypes.CDLL(None)
getpid = libc.getpid                          # symbol resolved before the guard
buf = ctypes.create_string_buffer(8)
guard.install_loopback_guard("baseline", env_path=ENV)
'''

    def test_already_imported_ctypes_cannot_load_or_read(self):
        r = run_child(self.PRE_IMPORTED + '''
attempt("dlopen", lambda: ctypes.CDLL(None))
attempt("dlsym", lambda: libc.connect)
attempt("string_at", lambda: ctypes.string_at(ctypes.addressof(buf), 1))
attempt("new_buffer", lambda: ctypes.create_string_buffer(4))
attempt("pythonapi", lambda: ctypes.pythonapi.Py_IsInitialized())
''')
        self.assertEqual(set(r.values()), {"denied"}, r)

    @unittest.skipUnless(CTYPES_CALLS_AUDITED,
                         "documented limit: ctypes imported before install can't be blocked on 3.13")
    def test_already_imported_ctypes_calls_refused(self):
        r = run_child(self.PRE_IMPORTED + '''
attempt("call_resolved", lambda: getpid())
attempt("memmove", lambda: ctypes.memmove(buf, b"ab", 2))
attempt("cast_obj", lambda: ctypes.cast(id(R), ctypes.py_object).value)
''')
        self.assertEqual(set(r.values()), {"denied"}, r)


class TestProxies(unittest.TestCase):
    BODY = '''
attempt("via_proxy", lambda: urllib.request.urlopen("http://127.0.0.1:%d/" % P["GATE_PORT"], timeout=2))
attempt("external_via_proxy", lambda: urllib.request.urlopen("http://example.com/", timeout=2))
'''

    def test_external_proxy_does_not_help(self):
        env = {"HTTP_PROXY": "http://192.0.2.1:3128", "HTTPS_PROXY": "http://192.0.2.1:3128",
               "ALL_PROXY": "http://192.0.2.1:3128", "http_proxy": "http://192.0.2.1:3128"}
        r = run_child(self.BODY, env_extra=env, role="app")
        self.assertEqual(r, {"via_proxy": "denied", "external_via_proxy": "denied"})

    def test_loopback_proxy_on_unlisted_port_does_not_help(self):
        r = run_child('''
os.environ["http_proxy"] = "http://127.0.0.1:%d" % OTHER
os.environ["no_proxy"] = ""
''' + self.BODY, role="app")
        self.assertEqual(r, {"via_proxy": "denied", "external_via_proxy": "denied"})

    def test_no_proxy_does_not_widen(self):
        env = {"NO_PROXY": "*", "no_proxy": "*"}
        r = run_child('attempt("external", lambda: urllib.request.urlopen("http://example.com/", timeout=2))\n',
                      env_extra=env, role="baseline")
        self.assertEqual(r, {"external": "denied"})


class TestPrograms(unittest.TestCase):
    """No role may start any program: no allowlisted argv, no cwd exceptions. Each attempt would create MARK if
    it ran, so a child that slipped through is caught even if no exception says so."""

    BODY = r'''
import multiprocessing, multiprocessing.util, pty, asyncio, time
MARK = os.path.join(TMP, "pwned")
TOUCH = ["touch", MARK]

def fork_child(fork):
    def go():
        pid = fork()
        pid = pid[0] if isinstance(pid, tuple) else pid
        if pid == 0:
            open(MARK, "w").close()
            os._exit(0)
        os.waitpid(pid, 0)
    return go

def mp(method):
    def go():
        p = multiprocessing.get_context(method).Process(target=os.getpid)
        p.start(); p.join(5)
    return go

fake = os.path.join(TMP, "git")
with open(fake, "w") as f:
    f.write("#!/bin/sh\ntouch " + MARK + "\n")
os.chmod(fake, 0o755)

attempt("subprocess_name", lambda: subprocess.run(TOUCH))
attempt("subprocess_abs", lambda: subprocess.run(["/bin/touch", MARK], capture_output=True))
attempt("subprocess_shell", lambda: subprocess.run("touch " + MARK, shell=True))
attempt("subprocess_cwd", lambda: subprocess.run(TOUCH, cwd=REPO))
attempt("python_verify", lambda: subprocess.run([sys.executable, os.path.join(REPO, "proof", "verify.py"), "b",
                                                 "--json"], cwd=REPO, capture_output=True))
attempt("git_rev_parse", lambda: subprocess.run(["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                                                capture_output=True))
attempt("check_output", lambda: subprocess.check_output([sys.executable, "-c", "pass"]))
attempt("os_popen", lambda: os.popen("touch " + MARK).close())
attempt("os_system", lambda: os.system("touch " + MARK))
attempt("posix_spawn", lambda: os.posix_spawn("/bin/touch", TOUCH, dict(os.environ)))
attempt("posix_spawnp", lambda: os.posix_spawnp("touch", TOUCH, dict(os.environ)))
attempt("execv", lambda: os.execv("/bin/touch", TOUCH))
attempt("execvp", lambda: os.execvp("touch", TOUCH))
attempt("spawnv", lambda: os.spawnv(os.P_WAIT, "/bin/touch", TOUCH))
attempt("os_fork", fork_child(os.fork))
attempt("os_forkpty", fork_child(os.forkpty))
attempt("pty_fork", fork_child(pty.fork))
attempt("pty_spawn", lambda: pty.spawn(["/bin/touch", MARK]))
attempt("mp_spawn", mp("spawn"))
attempt("mp_forkserver", mp("forkserver"))
attempt("mp_fork", mp("fork"))
attempt("spawnv_passfds", lambda: multiprocessing.util.spawnv_passfds("/bin/touch", TOUCH, []))
attempt("asyncio_exec", lambda: asyncio.run(asyncio.create_subprocess_exec("/bin/touch", MARK)))
os.environ["PATH"] = TMP + os.pathsep + os.environ.get("PATH", "")
attempt("fake_git_on_path", lambda: subprocess.run(["git", "--version"], capture_output=True))
time.sleep(0.3)
R["pwned"] = os.path.exists(MARK)
'''

    def test_every_program_start_refused_for_every_role(self):
        for role in ("app", "planner", "baseline", "fake_tavily"):
            with self.subTest(role=role):
                r = run_child(self.BODY, role=role)
                pwned = r.pop("pwned")
                self.assertEqual({k: v for k, v in r.items() if v != "denied"}, {}, "not refused")
                self.assertFalse(pwned, "a program ran")

    def test_fork_exec_cannot_be_restored(self):
        """3.13 has no audit event in _posixsubprocess.fork_exec: the guard replaces it at install. A fresh import
        (which would bring the original back) is refused; a reload keeps the replacement."""
        r = run_child(r'''
import importlib, multiprocessing.util, _posixsubprocess
MARK = os.path.join(TMP, "pwned")
attempt("reload", lambda: importlib.reload(_posixsubprocess))
attempt("after_reload", lambda: multiprocessing.util.spawnv_passfds("/bin/touch", ["touch", MARK], []))
def fresh():
    del sys.modules["_posixsubprocess"]
    import _posixsubprocess as again
    again.fork_exec
attempt("fresh_import", fresh)
attempt("after_fresh", lambda: multiprocessing.util.spawnv_passfds("/bin/touch", ["touch", MARK], []))
attempt("subprocess_private", lambda: subprocess._fork_exec())
R["pwned"] = os.path.exists(MARK)
''', role="baseline")
        self.assertEqual(r.pop("pwned"), False)
        self.assertEqual(r.pop("reload"), "ok", "reload is harmless: it keeps the replacement")
        self.assertEqual(set(r.values()), {"denied"}, r)

    def test_stdlib_that_imports_subprocess_still_loads(self):
        r = run_child('''
for name in ("platform", "uuid", "webbrowser", "http.server", "shutil", "multiprocessing.pool"):
    attempt(name, lambda name=name: __import__(name))
attempt("uuid4", lambda: __import__("uuid").uuid4())
''', role="app")
        self.assertEqual(set(r.values()), {"ok"}, r)


class TestBypassRegressions(unittest.TestCase):
    """Auditor findings on earlier versions: changing module state after install must not widen anything."""

    MARKER_HELPERS = '''
MARK = os.path.join(TMP, "pwned")
def pwned():
    return os.path.exists(MARK)
'''

    def test_2_module_tampering_does_not_widen(self):
        r = run_child(self.MARKER_HELPERS + '''
guard._installed["role"] = "app"
guard.ROLES["baseline"] = (("OTHER_PORT",), ())
guard.ROLES["app"] = (("OTHER_PORT",), ())
guard.is_loopback = lambda host: True
sys.executable = "/bin/touch"
attempt("conn_other", lambda: conn(OTHER))
attempt("program", lambda: subprocess.run(["/bin/touch", MARK]))
attempt("still_gate", lambda: conn(P["GATE_PORT"]))
R["pwned"] = pwned()
''', role="baseline")
        self.assertEqual(r, {"conn_other": "denied", "program": "denied", "still_gate": "ok", "pwned": False})

    def test_2c_patching_loopback_helpers_does_not_widen(self):
        # 0.0.0.0 is not loopback to the guard, but Linux delivers it locally: nothing leaves the machine.
        r = run_child('''
import ipaddress
attempt("before", lambda: conn(P["GATE_PORT"], host="0.0.0.0"))
guard.is_loopback = lambda host: True
ipaddress.ip_address = lambda s: ipaddress.IPv4Address("127.0.0.1")
attempt("after_patch", lambda: conn(P["GATE_PORT"], host="0.0.0.0"))
attempt("dns_after_patch", lambda: socket.gethostbyname("example.com"))
''', role="app")
        self.assertEqual(r, {"before": "denied", "after_patch": "denied", "dns_after_patch": "denied"})



class TestInstall(unittest.TestCase):
    def test_idempotent_and_single_role(self):
        r = run_child('''
attempt("again_same", lambda: guard.install_loopback_guard("app", env_path=ENV))
attempt("different", lambda: guard.install_loopback_guard("planner", env_path=ENV))
attempt("still_app", lambda: conn(P["GATE_PORT"]))
''', role="app")
        self.assertEqual(r["again_same"], "ok")
        self.assertEqual(r["different"], "RuntimeError")
        self.assertEqual(r["still_app"], "ok")

    def test_bad_roles(self):
        r = run_child('''
for role in ("gate", "Gate", "reader", "", None, "app "):
    attempt(repr(role), lambda: guard.install_loopback_guard(role, env_path=ENV))
attempt("after", lambda: conn(OTHER))
''')
        for k, v in r.items():
            if k != "after":
                self.assertEqual(v, "ValueError", k)
        # loopback only (no packet leaves the machine): an unguarded process can reach an unlisted port
        self.assertEqual(r["after"], "ok", "a refused install must not have installed anything")

    def test_missing_port_fails_closed(self):
        r = run_child('''
open(ENV, "w").write("OLLAMA_PORT=%d\\nAPP_PORT=%d\\nTAVILY_API_KEY=tvly-SHOULD-NOT-LEAK\\n"
                     % (P["OLLAMA_PORT"], P["APP_PORT"]))
attempt("app_missing_gate", lambda: guard.install_loopback_guard("app", env_path=ENV))
open(ENV, "w").write("OLLAMA_PORT=abc\\n")
attempt("planner_bad_port", lambda: guard.install_loopback_guard("planner", env_path=ENV))
open(ENV, "w").write("OLLAMA_PORT=70000\\n")
attempt("planner_range", lambda: guard.install_loopback_guard("planner", env_path=ENV))
attempt("missing_file", lambda: guard.install_loopback_guard("planner", env_path=os.path.join(TMP, "nope")))
''')
        self.assertEqual(r["app_missing_gate"], "ValueError")
        self.assertEqual(r["planner_bad_port"], "ValueError")
        self.assertEqual(r["planner_range"], "ValueError")
        self.assertEqual(r["missing_file"], "FileNotFoundError")

    def test_keys_never_kept_or_shown(self):
        r = run_child('''
import gc
blob = repr(vars(guard))
for name in dir(guard):
    blob += repr(getattr(guard, name))
for o in gc.get_objects():
    if isinstance(o, dict) and "TAVILY_API_KEY" in o:
        blob += repr(o)
R["leak"] = ("SHOULD-NOT-LEAK" in blob)
try:
    conn(OTHER)
except PermissionError as e:
    R["err"] = str(e)
''', role="app")
        self.assertFalse(r["leak"])
        self.assertNotIn("SHOULD-NOT-LEAK", r["err"])
        self.assertIn("app", r["err"])


class TestGateNeverCallsIt(unittest.TestCase):
    def test_no_gate_source_uses_the_guard(self):
        offenders = []
        for p in glob.glob(os.path.join(REPO, "gate", "**", "*.py"), recursive=True):
            if os.sep + "tests" + os.sep in p:
                continue
            with open(p, encoding="utf-8") as f:
                src = f.read()
            if re.search(r"install_loopback_guard|shared\.guard|from shared import guard", src):
                offenders.append(p)
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
