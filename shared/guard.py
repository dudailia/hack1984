"""Loopback guard for every Doublethink process except the Gate (invariant 1).

    from shared.guard import install_loopback_guard
    install_loopback_guard("app")   # or "planner", "baseline", "fake_tavily"; first thing at startup

After install, in this process (Python 3.13 and 3.14):
- connect, bind, sendto and sendmsg to any non-loopback address raise PermissionError;
- on loopback, only the role's ports are allowed (from the *_PORT keys of the repo .env):
      app          connect GATE_PORT, OLLAMA_PORT    bind APP_PORT
      planner      connect OLLAMA_PORT
      baseline     connect GATE_PORT, OLLAMA_PORT
      fake_tavily  no connects                         bind FAKE_TAVILY_PORT
  any other loopback port, port 0 included, raises PermissionError;
- DNS lookups for non-loopback names raise PermissionError ("localhost" and loopback literals are fine);
- Unix sockets are refused: connect, bind and sendto on any path or abstract name raise PermissionError.
  socket.socketpair() still works: an in-process pair reaches nothing, and asyncio's event loop needs it;
- no program can be started, by any role, with no exceptions: subprocess (and everything built on it: os.popen,
  asyncio subprocesses, ...), os.system, os.exec*, os.spawn*, os.posix_spawn[p], os.fork, os.forkpty (pty),
  multiprocessing (fork, spawn and forkserver) all raise PermissionError;
- ctypes is refused: importing ctypes or _ctypes after install raises PermissionError, and every "ctypes.*" audit
  event (dlopen, dlsym, call_function, string_at, cdata, ...) raises PermissionError;
- one role per process: installing the same role again does nothing, a different role raises RuntimeError.
The Gate never calls this: it is the one process allowed on the network.

How program starts are refused, per Python version:
- Both: the audit events subprocess.Popen, os.system, os.exec, os.spawn, os.posix_spawn (also posix_spawnp),
  os.startfile, os.fork and os.forkpty are refused.
- 3.14 also raises _posixsubprocess.fork_exec, which is refused.
- 3.13 raises no event inside _posixsubprocess.fork_exec, and multiprocessing's spawn and forkserver call it
  directly (multiprocessing.util.spawnv_passfds). So at install the guard replaces _posixsubprocess.fork_exec, and
  subprocess's private copy subprocess._fork_exec, with a function that raises PermissionError, and refuses any
  later fresh import of _posixsubprocess (which would bring the original back). importlib.reload keeps the
  replacement. subprocess and _posixsubprocess are imported by install so that later imports of them are cached.
- ctypes on 3.13: ctypes/__init__.py catches OSError around its own dlopen at import, and PermissionError is an
  OSError, so refusing ctypes.dlopen alone does not stop `import ctypes`; the import itself is refused instead.
All policy lives in the hook's closure: changing this module's variables or sys.executable after install changes
nothing.

LIMITS, stated plainly:
- This is a Python audit hook (PEP 578). It stops networking and program starts done through Python's own
  socket, subprocess, os and multiprocessing functions, which is all our code uses, and it refuses ctypes. It
  does NOT stop native code that is already loaded: a C extension (or cffi module) imported before or after
  install can call connect(), fork() or execve() directly without raising any audit event.
- ctypes imported BEFORE install: loading libraries, looking up symbols, reading memory and making new buffers
  are refused on both versions, but on 3.13 calling a C function that was already resolved raises no audit event
  and cannot be refused (3.14 raises ctypes.call_function for it, which is refused).
- On 3.13, a reference to the original _posixsubprocess.fork_exec taken before install (for example
  `from _posixsubprocess import fork_exec` in code that ran earlier) is not covered; on 3.14 the audit event
  covers every call.
- A file descriptor inherited from the parent, or a socket made with socket.socket(fileno=...)/fromfd from one,
  is already connected and needs no connect event.
- A loopback service that fetches for you is outside the guard: Ollama on OLLAMA_PORT can be asked to pull a
  model from a registry.
- An audit hook cannot be removed, but code in the same process can still crash or exit the process.
The macOS/Linux OS sandbox (stretch goal) is what would make this hold against native code.
"""
import ipaddress
import os
import socket
import sys
import threading

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ENV = os.path.join(REPO, ".env")

ROLES = {
    #               connect ports                     bind ports
    "app":         (("GATE_PORT", "OLLAMA_PORT"),     ("APP_PORT",)),
    "planner":     (("OLLAMA_PORT",),                 ()),
    "baseline":    (("GATE_PORT", "OLLAMA_PORT"),     ()),
    "fake_tavily": ((),                               ("FAKE_TAVILY_PORT",)),
}

_CONNECT_EVENTS = ("socket.connect", "socket.sendto", "socket.sendmsg")
_NAME_EVENTS = ("socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyname_ex", "socket.gethostbyaddr")
# Every audit event that starts a program, on 3.13 or 3.14. All refused, for every role.
_PROGRAM_EVENTS = frozenset(("subprocess.Popen", "os.system", "os.exec", "os.spawn", "os.posix_spawn",
                             "os.startfile", "os.fork", "os.forkpty", "_posixsubprocess.fork_exec"))
# Fresh imports refused after install: ctypes (3.13 swallows a refused dlopen at import) and _posixsubprocess
# (a fresh copy would bring back the fork_exec the guard replaced).
_REFUSED_IMPORTS = frozenset(("ctypes", "_ctypes", "_posixsubprocess"))

_lock = threading.Lock()
_installed = {"role": None}  # bookkeeping for idempotence only; the hook never reads module state


# ---------------------------------------------------------------- .env (ports only)

def _read_ports(env_path):
    """Only *_PORT keys are parsed and kept; every other line (API keys included) is skipped unread."""
    ports = {}
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("export "):
                line = line[len("export "):]
            key, sep, val = line.partition("=")
            key = key.strip()
            if not sep or not key.endswith("_PORT") or key.startswith("#"):
                continue
            val = val.split(" #", 1)[0].strip().strip("\"'")
            try:
                p = int(val)
            except ValueError:
                raise ValueError("guard: .env %s is not a port number" % key) from None
            if not 0 < p < 65536:
                raise ValueError("guard: .env %s is out of range" % key)
            ports[key] = p
    return ports


def is_loopback(host):
    if host is None:
        return True  # getaddrinfo(None, port): the local host
    if isinstance(host, (bytes, bytearray)):
        host = bytes(host).decode("ascii", "replace")
    host = str(host).strip("[]")
    if host.lower() == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    return (mapped or ip).is_loopback


# ---------------------------------------------------------------- the hook (all policy frozen in a closure)

def _make_hook(role, connect_ports, bind_ports):
    af_unix = getattr(socket, "AF_UNIX", object())
    ip_address = ipaddress.ip_address  # captured: patching ipaddress or this module later changes nothing
    program_events, refused_imports = _PROGRAM_EVENTS, _REFUSED_IMPORTS

    def is_loopback(host):  # private copy of the module-level is_loopback, bound to the captured functions
        if host is None:
            return True
        if isinstance(host, (bytes, bytearray)):
            host = bytes(host).decode("ascii", "replace")
        host = str(host).strip("[]")
        if host.lower() == "localhost":
            return True
        try:
            ip = ip_address(host.split("%", 1)[0])
        except ValueError:
            return False
        mapped = getattr(ip, "ipv4_mapped", None)
        return (mapped or ip).is_loopback

    def deny(what):
        raise PermissionError("guard(%s): %s is not allowed outside the Gate (invariant 1)" % (role, what))

    def check_address(event, sock, address):
        if address is None:
            return
        if getattr(sock, "family", None) == af_unix or isinstance(address, (str, bytes, bytearray)):
            deny("%s on a Unix socket" % event)  # paths and the abstract namespace; socketpair() needs neither
        if not isinstance(address, tuple) or len(address) < 2:
            deny("%s to %r" % (event, address))
        host, port = address[0], address[1]
        if not is_loopback(host):
            deny("%s to %r" % (event, host))
        if port not in (bind_ports if event == "socket.bind" else connect_ports):
            deny("%s to loopback port %r" % (event, port))

    def hook(event, args):
        if event in program_events:
            deny("starting a program (%s)" % event)
        if event.startswith("ctypes."):
            deny(event)  # dlopen, dlsym, call_function (3.14), string_at, cdata, ...
        if event == "import":
            name = args[0] if args and isinstance(args[0], str) else ""
            if name in refused_imports or name.startswith("ctypes."):
                deny("importing %s" % name)
        elif event == "socket.bind" or event in _CONNECT_EVENTS:
            check_address(event, args[0], args[1] if len(args) > 1 else None)
        elif event in _NAME_EVENTS:
            if not is_loopback(args[0]):
                deny("%s for %r" % (event, args[0]))
        elif event == "socket.getnameinfo":
            sockaddr = args[0]
            if not is_loopback(sockaddr[0] if isinstance(sockaddr, tuple) else sockaddr):
                deny("socket.getnameinfo")

    return hook


def _disable_fork_exec(role):
    """3.13 raises no audit event inside _posixsubprocess.fork_exec, which multiprocessing calls directly. Replace
    it (and subprocess's private copy) with a function that refuses. Harmless on 3.14, which audits it anyway."""
    import _posixsubprocess
    import subprocess

    def fork_exec(*args, **kwargs):
        raise PermissionError("guard(%s): starting a program (_posixsubprocess.fork_exec) is not allowed outside "
                              "the Gate (invariant 1)" % role)

    _posixsubprocess.fork_exec = fork_exec
    if hasattr(subprocess, "_fork_exec"):
        subprocess._fork_exec = fork_exec


def install_loopback_guard(role, env_path=DEFAULT_ENV):
    """Install the guard for `role` once per process. Same role again: no-op. Different role: RuntimeError."""
    if not isinstance(role, str) or role not in ROLES:
        raise ValueError("guard: role must be one of %s (the Gate never installs the guard)" % sorted(ROLES))
    with _lock:
        if _installed["role"] is not None:
            if _installed["role"] != role:
                raise RuntimeError("guard: already installed for role %r" % _installed["role"])
            return
        ports = _read_ports(env_path)
        connect_keys, bind_keys = ROLES[role]
        missing = [k for k in connect_keys + bind_keys if k not in ports]
        if missing:
            raise ValueError("guard: .env is missing %s" % ", ".join(missing))
        _disable_fork_exec(role)  # before the hook, while importing _posixsubprocess is still allowed
        sys.addaudithook(_make_hook(role, frozenset(ports[k] for k in connect_keys),
                                    frozenset(ports[k] for k in bind_keys)))
        _installed["role"] = role


def installed_role():
    return _installed["role"]
