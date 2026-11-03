"""A real TCP request must update both the reply and the original server UI."""
import socket
import time
from spitfire.__main__ import MemoryView
from spitfire.controller import Controller


def test_status_server_updates_connection_and_receive_controls():
    view = MemoryView()
    app = Controller(view, demo=True, tcp_port=0, tcp_host="127.0.0.1")
    try:
        app.start()
        with socket.create_connection(app.tcp.address, timeout=1) as client:
            client.sendall(b"FAULTS?\n")
            assert client.recv(128) in (b"0\n", b"1\n")
            deadline = time.monotonic() + 1
            while view.read("server", 4) != "FAULTS?\n" and time.monotonic() < deadline:
                app.tick()
                time.sleep(0.001)
            assert view.read("server", 5) == 1
            assert view.read("server", 9) == "127.0.0.1"
            assert view.read("server", 4) == "FAULTS?\n"
        deadline = time.monotonic() + 1
        while view.read("server", 5) and time.monotonic() < deadline:
            app.tick()
            time.sleep(0.001)
        assert view.read("server", 5) == 0
        assert view.read("server", 4) == "-- Client disconnected --\n"
    finally:
        app.stop()
