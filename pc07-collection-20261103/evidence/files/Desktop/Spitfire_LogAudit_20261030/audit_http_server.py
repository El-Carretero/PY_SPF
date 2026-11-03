"""Small host-only transfer/control endpoint for the isolated XP audit.

python audit_http_server.py --root C:\\SPF_AUDIT_20261030
Binds only 10.19.70.13:18977. Never executes uploaded files or shell commands.
"""
from __future__ import annotations
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import socket
from urllib.parse import unquote, urlsplit

ALLOWED_CLIENTS = {"10.19.70.2", "10.19.70.13"}
MAX_BYTES = 10 * 1024 * 1024
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}\Z")


def basename(url_path: str, prefix: str) -> str | None:
    if not url_path.startswith(prefix):
        return None
    result = unquote(url_path[len(prefix):])
    return result if NAME.fullmatch(result) else None


def make_handler(root: Path):
    received = root / "received"
    received.mkdir(exist_ok=True)
    if received.is_symlink() or received.resolve().parent != root:
        raise ValueError("received must be a direct, non-symlink child of audit root")

    class Handler(BaseHTTPRequestHandler):
        server_version = "SPFAudit/1.0"

        def allowed(self):
            if self.client_address[0] not in ALLOWED_CLIENTS:
                self.answer(403, b"Forbidden\n")
                return False
            self.connection.settimeout(20)
            return True

        def answer(self, status: int, data: bytes, content_type="text/plain; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
            self.close_connection = True

        def do_GET(self):
            if not self.allowed():
                return
            name = basename(urlsplit(self.path).path, "/")
            if name is None:
                self.answer(400, b"One plain filename is required\n")
                return
            file = root / name
            if file.is_symlink() or file.resolve().parent != root:
                self.answer(403, b"Forbidden path\n")
                return
            if name == "control.txt" and not file.exists():
                self.answer(200, b"0|wait\n")
                return
            if not file.is_file():
                self.answer(404, b"Not found\n")
                return
            if file.stat().st_size > MAX_BYTES:
                self.answer(413, b"File too large\n")
                return
            content_type = "application/octet-stream"
            if file.suffix.lower() == ".hta":
                content_type = "application/hta"
            elif file.suffix.lower() in (".txt", ".jsonl", ".log", ".json"):
                content_type = "text/plain; charset=utf-8"
            self.answer(200, file.read_bytes(), content_type)

        def do_POST(self):
            if not self.allowed():
                return
            name = basename(urlsplit(self.path).path, "/upload/")
            if name is None:
                self.answer(400, b"Use /upload/<plain-basename>\n")
                return
            if self.headers.get("Transfer-Encoding"):
                self.answer(400, b"Content-Length required\n")
                return
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if length < 0:
                self.answer(411, b"Content-Length required\n")
                return
            if length > MAX_BYTES:
                self.answer(413, b"Upload too large\n")
                return
            destination = received / name
            temporary = received / (name + ".uploading")
            if destination.is_symlink() or temporary.is_symlink():
                self.answer(403, b"Forbidden destination\n")
                return
            remaining = length
            try:
                with temporary.open("wb") as stream:
                    while remaining:
                        block = self.rfile.read(min(65536, remaining))
                        if not block:
                            raise ConnectionError("Incomplete request body")
                        stream.write(block)
                        remaining -= len(block)
                temporary.replace(destination)
            except (OSError, ConnectionError, socket.timeout):
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
                self.answer(400, b"Incomplete upload\n")
                return
            self.answer(200, ("Stored " + name + " (" + str(length) + " bytes)\n").encode("ascii"))

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    options = parser.parse_args()
    root = options.root.resolve(strict=True)
    server = ThreadingHTTPServer(("10.19.70.13", 18977), make_handler(root))
    print("Serving isolated SPF audit root " + str(root) + " at http://10.19.70.13:18977/", flush=True)
    print("Allowed clients: " + ", ".join(sorted(ALLOWED_CLIENTS)), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
