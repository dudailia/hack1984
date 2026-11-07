"""Loopback guard for every Doublethink process except the Gate (invariant 1).

    from shared.guard import install_loopback_guard
    install_loopback_guard("app")   # or "planner", "baseline", "fake_tavily"; first thing at startup

After install, in this process (behaviour of baseline/netguard.py, plus per-role port and program allowlists):
- connect, bind, sendto and sendmsg to any non-loopback address raise PermissionError;
- on loopback, only the role's ports are allowed (from the *_PORT keys of the repo .env):
      app          connect GATE_PORT, OLLAMA_PORT    bind APP_PORT
      planner      connect OLLAMA_PORT
      baseline     connect GATE_PORT, OLLAMA_PORT
      fake_tavily  no connects                         bind FAKE_TAVILY_PORT
  any other loopback port, port 0 included, raises PermissionError;
- DNS lookups for non-loopback names raise PermissionError ("localhost" and loopback literals are fine);
- Unix sockets are allowed;
- starting a program raises PermissionError, except these exact argv lists, started through subprocess with
  no shell, no cwd and no env, and only when the program actually run is the one fixed at install time:
      app       [sys.executable, ("-I"), <repo>/proof/verify.py, BUNDLE, ("--json")]   (POST /api/verify)
      baseline  ["git", "-C", <repo>, "rev-parse", "-q", "--verify", "refs/tags/checks-frozen"]
                ["git", "-C", <repo>, "rev-parse", "--short", "HEAD"]                (baseline/redteam.py)
  os.exec*, os.system, os.spawn* and os.startfile are always refused (subprocess never needs them), so a
  preexec_fn, pty.spawn or multiprocessing child cannot start another program either;
- one role per process: installing the same role again does nothing, a different role raises RuntimeError.
The Gate never calls this: it is the one process allowed on the network.

How the program check works: subprocess raises "subprocess.Popen" and then either "os.posix_spawn" (absolute
executable) or "_posixsubprocess.fork_exec" (name looked up in PATH). Every one of these events is checked on
its own against the fixed list: exact argv, env None, and the real path of the program that will run (the first
existing PATH candidate for fork_exec) must equal the one resolved at install (git) or sys.executable as it
was at install (verify). Nothing is remembered between events. All allowlists live in the hook's closure, so
changing this module's variables, sys.executable or PATH after install changes nothing.

LIMITS, stated plainly:
- This is a Python audit hook (PEP 578). It stops networking and program starts done through Python's own
  socket, subprocess and os functions, which is all our code uses. It does NOT stop native code: ctypes,
  cffi or a C extension can call connect() or execve() directly without raising any audit event.
- The allowed child programs are not guarded themselves: proof/verify.py runs as a separate, unguarded
  Python process (it uses only the standard library and cryptography); git runs as itself.
- A loopback service that fetches for you is outside the guard: Ollama on OLLAMA_PORT can be asked to pull a
  model from a registry, and any Unix socket (for example a local proxy) is allowed.
- An audit hook cannot be removed, but code in the same process can still crash or exit the process.
The macOS/Linux OS sandbox (stretch goal) is what would make this hold against native code.
"""
import ipaddress
import os
import shutil
import socket
import sys
import threading

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ENV = os.path.join(REPO, ".env")
VERIFY = os.path.join(REPO, "proof", "verify.py")

ROLES = {
    #               connect ports                     bind ports
    "app":         (("GATE_PORT", "OLLAMA_PORT"),     ("APP_PORT",)),
    "planner":     (("OLLAMA_PORT",),                 ()),
    "baseline":    (("GATE_PORT", "OLLAMA_PORT"),     ()),
    "fake_tavily": ((),                               ("FAKE_TAVILY_PORT",)),
}
GIT_ARGVS = (
    ("git", "-C", REPO, "rev-parse", "-q", "--verify", "refs/tags/checks-frozen"),
    ("git", "-C", REPO, "rev-parse", "--short", "HEAD"),
)

_CONNECT_EVENTS = ("socket.connect", "socket.sendto", "socket.sendmsg")
_NAME_EVENTS = ("socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyname_ex", "socket.gethostbyaddr")
_ALWAYS_DENIED = ("os.exec", "os.system", "os.spawn", "os.startfile")

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
    realpath, isabs, isfile, access, X_OK = os.path.realpath, os.path.isabs, os.path.isfile, os.access, os.X_OK
    fsdecode = os.fsdecode
    ip_address = ipaddress.ip_address  # captured: patching ipaddress or this module later changes nothing

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

    # programs: argv -> real path of the program that must run for it
    allowed = {}
    if role == "baseline":
        git = shutil.which("git")
        if git:
            for argv in GIT_ARGVS:
                allowed[tuple(argv)] = realpath(git)
    exe = sys.executable
    exe_real = realpath(exe) if exe else None
    verify = VERIFY

    def deny(what):
        raise PermissionError("guard(%s): %s is not allowed outside the Gate (invariant 1)" % (role, what))

    def program_for(argv):
        """Real path the argv must run, or None if the argv is not allowed for this role."""
        if not isinstance(argv, (list, tuple)) or not argv or not all(isinstance(a, str) for a in argv):
            return None
        argv = tuple(argv)
        if argv in allowed:
            return allowed[argv]
        if role == "app" and exe and argv[0] == exe:
            rest = argv[1:]
            if rest[:1] == ("-I",):
                rest = rest[1:]
            if rest[:1] == (verify,):
                args = rest[1:]
                if (len(args) in (1, 2) and args[0] and not args[0].startswith("-")
                        and (len(args) == 1 or args[1] == "--json")):
                    return exe_real
        return None

    def check_address(event, sock, address):
        if address is None or getattr(sock, "family", None) == af_unix:
            return
        if not isinstance(address, tuple) or len(address) < 2:
            if isinstance(address, (str, bytes)):
                return  # AF_UNIX path
            deny("%s to %r" % (event, address))
        host, port = address[0], address[1]
        if not is_loopback(host):
            deny("%s to %r" % (event, host))
        if port not in (bind_ports if event == "socket.bind" else connect_ports):
            deny("%s to loopback port %r" % (event, port))

    def check_popen(executable, args, cwd, env):
        want = program_for(args)
        if want is None or cwd is not None or env is not None or executable != args[0]:
            deny("starting %r" % (args[0] if isinstance(args, (list, tuple)) and args else args))

    def check_posix_spawn(path, argv, env):
        want = program_for(argv)
        path = fsdecode(path) if isinstance(path, (str, bytes)) else None
        if want is None or env is not None or not path or not isabs(path) or realpath(path) != want:
            deny("os.posix_spawn")

    def check_fork_exec(executables, argv, env):
        want = program_for(argv)
        if want is None or env is not None or not isinstance(executables, (list, tuple)):
            deny("starting a program")
        for cand in executables:  # exec tries these in order: the first that can run is what runs
            c = fsdecode(cand)
            if isfile(c) and access(c, X_OK):
                if realpath(c) != want:
                    deny("starting %r" % c)
                return
        deny("starting a program")

    def hook(event, args):
        if event == "socket.bind" or event in _CONNECT_EVENTS:
            check_address(event, args[0], args[1] if len(args) > 1 else None)
        elif event in _NAME_EVENTS:
            if not is_loopback(args[0]):
                deny("%s for %r" % (event, args[0]))
        elif event == "socket.getnameinfo":
            sockaddr = args[0]
            if not is_loopback(sockaddr[0] if isinstance(sockaddr, tuple) else sockaddr):
                deny("socket.getnameinfo")
        elif event == "subprocess.Popen":
            check_popen(*args[:4])
        elif event == "os.posix_spawn":
            check_posix_spawn(*args[:3])
        elif event == "_posixsubprocess.fork_exec":
            check_fork_exec(*args[:3])
        elif event in _ALWAYS_DENIED:
            deny(event)

    return hook


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
        sys.addaudithook(_make_hook(role, frozenset(ports[k] for k in connect_keys),
                                    frozenset(ports[k] for k in bind_keys)))
        _installed["role"] = role


def installed_role():
    return _installed["role"]
