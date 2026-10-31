"""Exercise actual socket boundaries without sending a packet off loopback."""
import _socket
import ctypes
import socket
from contextlib import closing

import pytest


@pytest.mark.parametrize('host', ['10.19.70.13', '192.168.1.1', '255.255.255.255', '::ffff:10.19.70.13'])
def test_udp_destination_is_rejected_before_io(host):
    # _socket bypasses our Python subclass; the audit hook must still block it.
    family = socket.AF_INET6 if ':' in host else socket.AF_INET
    with closing(_socket.socket(family, socket.SOCK_DGRAM)) as sock:
        with pytest.raises(PermissionError, match='loopback'):
            sock.sendto(b'CI guard probe', (host, 1024))


def test_remote_tcp_and_dns_are_rejected_before_io():
    with socket.socket() as sock:
        with pytest.raises(PermissionError, match='loopback'):
            sock.connect(('10.19.70.13', 1024))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        with pytest.raises(PermissionError, match='loopback'):
            sock.sendto(b'CI guard probe', ('example.com', 1024))
    with pytest.raises(PermissionError, match='loopback'):
        socket.getaddrinfo('example.com', 1024)
    with pytest.raises(PermissionError, match='loopback'):
        socket.gethostbyname('example.com')


def test_wildcard_bind_is_narrowed_and_loopback_udp_works():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        server.bind(('0.0.0.0', 0))
        assert server.getsockname()[0] == '127.0.0.1'
        server.settimeout(1)
        client.sendto(b'localhost', server.getsockname())
        assert server.recv(32) == b'localhost'


def test_direct_wildcard_and_non_loopback_bind_are_rejected():
    with closing(_socket.socket()) as sock:
        for host in ('0.0.0.0', '10.19.70.13'):
            with pytest.raises(PermissionError, match='loopback'):
                sock.bind((host, 0))


def test_ni_dll_load_is_rejected_even_if_bundled_dlls_exist():
    with pytest.raises(PermissionError, match='Native NI runtime'):
        ctypes.CDLL('cvirte.dll')
