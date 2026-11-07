"""Loopback-only audit hook for processes that are not the Gate (invariant 1).

Interim: shared/ has no guard module yet. Once one lands (owner: Aayush, gate side), baseline.agent and
fake_tavily.server should call it instead and this module goes.

After install(), in this process: DNS lookups and connect, bind, sendto or sendmsg to anything except a loopback
address raise PermissionError, and starting another program (subprocess, os.system, exec, spawn) raises
PermissionError. Unix sockets are allowed. An audit hook cannot be removed, so install it only at startup.
"""
import ipaddress
import socket
import sys

_installed = False

_SOCKET_ADDRESS_EVENTS = ("socket.connect", "socket.bind", "socket.sendto", "socket.sendmsg")
_NAME_EVENTS = ("socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyname_ex", "socket.gethostbyaddr")
_PROGRAM_EVENTS = ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.startfile")


def is_loopback(host):
    if host is None:
        return True  # getaddrinfo(None, port): the local host
    if isinstance(host, (bytes, bytearray)):
        host = bytes(host).decode("ascii", "replace")
    host = str(host).strip("[]")
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def _deny(what):
    raise PermissionError("netguard: %s is not allowed outside the Gate (invariant 1)" % what)


def _hook(event, args):
    if event in _SOCKET_ADDRESS_EVENTS:
        sock, address = args[0], args[1]
        if address is None or getattr(sock, "family", None) == getattr(socket, "AF_UNIX", object()):
            return
        host = address[0] if isinstance(address, tuple) else address
        if not is_loopback(host):
            _deny("%s to %r" % (event, host))
    elif event in _NAME_EVENTS:
        if not is_loopback(args[0]):
            _deny("%s for %r" % (event, args[0]))
    elif event == "socket.getnameinfo":
        sockaddr = args[0]
        if not is_loopback(sockaddr[0] if isinstance(sockaddr, tuple) else sockaddr):
            _deny("socket.getnameinfo")
    elif event in _PROGRAM_EVENTS:
        _deny(event)


def install():
    """Install the hook once per process."""
    global _installed
    if not _installed:
        sys.addaudithook(_hook)
        _installed = True
