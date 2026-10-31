"""Process-local network guard for tests/demos; never imported by the app.

Audit hooks cover socket calls even through _socket or pre-existing references.
The one adapter change is narrowing legacy wildcard binds to loopback in CI.
This is a Python socket guard, not an OS firewall for arbitrary native code.
"""
from __future__ import annotations

import ipaddress
import socket
import sys

_installed = False


def _check_host(host):
    if isinstance(host, bytes):
        host = host.decode('ascii')
    if isinstance(host, str) and host.rstrip('.').lower() == 'localhost':
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise PermissionError(f'CI permits loopback addresses only: {host!r}')


def _audit(event, args):
    if event == 'ctypes.dlopen' and args[0] is not None:
        name = str(args[0]).replace('\\', '/').rsplit('/', 1)[-1].lower()
        if name in ('cvirte.dll', 'cvintwrk.dll', 'cviauto.dll', 'cviusi.dll', 'cvirt.dll', 'dataskt.dll', 'mesa.dll'):
            raise PermissionError('CI does not load Native NI runtime DLLs')
    elif event in ('socket.connect', 'socket.sendto', 'socket.sendmsg', 'socket.bind'):
        sock, address = args[:2]
        if sock.family in (socket.AF_INET, socket.AF_INET6) and address is not None:
            _check_host(address[0])
    elif event in ('socket.getaddrinfo', 'socket.gethostbyname', 'socket.gethostbyaddr'):
        _check_host(args[0])


def install():
    """Install once before importing pytest or the application."""
    global _installed
    if _installed:
        return
    original = socket.socket

    class LoopbackSocket(original):
        def _check_address(self, address):
            if self.family in (socket.AF_INET, socket.AF_INET6):
                _check_host(address[0])

        def connect(self, address):
            self._check_address(address)
            return super().connect(address)

        def connect_ex(self, address):
            self._check_address(address)
            return super().connect_ex(address)

        def sendto(self, data, *args):
            # Check before CPython resolves a hostname while parsing the tuple.
            self._check_address(args[-1])
            return super().sendto(data, *args)

        def bind(self, address):
            if self.family in (socket.AF_INET, socket.AF_INET6):
                host, *rest = address
                if host in ('', '0.0.0.0', '::'):
                    host = '::1' if self.family == socket.AF_INET6 else '127.0.0.1'
                address = (host, *rest)
            self._check_address(address)
            return super().bind(address)

    socket.socket = LoopbackSocket
    sys.addaudithook(_audit)
    _installed = True
