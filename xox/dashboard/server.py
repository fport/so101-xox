"""HTTP server for the dashboard, standard library only.

Routes
    GET  /                    the page (index.html next to this file)
    GET  /state               JSON snapshot of the GameState
    GET  /frame/<name>.jpg    latest JPEG of a camera, never cached
    GET  /stream/<name>       MJPEG (multipart/x-mixed-replace) stream
    POST /stop                asks the game to stop, answers 204
"""

from __future__ import annotations

import json
import re
import select
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from ..state import GameState

INDEX_HTML = Path(__file__).with_name("index.html")
BOUNDARY = "frame"

_FRAME_ROUTE = re.compile(r"^/frame/([a-z0-9_]{1,32})\.jpg$")
_STREAM_ROUTE = re.compile(r"^/stream/([a-z0-9_]{1,32})$")
_CLIENT_GONE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError)


class DashboardServer(ThreadingHTTPServer):
    """A ThreadingHTTPServer bound to one GameState, with a clean ``stop``."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], state: GameState, stream_fps: float = 10.0):
        super().__init__(address, _Handler)
        self.state = state
        self.stream_interval = 1.0 / max(1.0, float(stream_fps))
        self.stopping = threading.Event()
        self.thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}/"

    def start(self) -> "DashboardServer":
        if self.thread is None:
            self.thread = threading.Thread(
                target=self.serve_forever, kwargs={"poll_interval": 0.2},
                name="xox-dashboard", daemon=True,
            )
            self.thread.start()
        return self

    def stop(self, timeout: float = 5.0) -> None:
        """Stop serving, end open streams and release the port."""
        self.stopping.set()
        if self.thread is not None:
            self.shutdown()
            self.thread.join(timeout)
            self.thread = None
        self.server_close()

    def handle_error(self, request, client_address) -> None:
        # A browser tab closing mid-response is not worth a traceback.
        return


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "xox-dashboard"
    timeout = 30  # idle keep-alive connections are dropped after this

    server: DashboardServer

    def log_message(self, format: str, *args) -> None:  # quiet by design
        return

    # ---------------------------------------------------------------- routing

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            self._send_page()
        elif path == "/state":
            body = json.dumps(self.server.state.snapshot(), ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
        elif match := _FRAME_ROUTE.match(path):
            jpeg = self.server.state.frame(match.group(1))
            if jpeg is None:
                self._send(404, "text/plain; charset=utf-8", b"no frame yet\n")
            else:
                self._send(200, "image/jpeg", jpeg)
        elif match := _STREAM_ROUTE.match(path):
            self._stream(match.group(1))
        elif path == "/favicon.ico":
            self._send(204, None, b"")
        else:
            self._send(404, "text/plain; charset=utf-8", b"not found\n")

    def do_HEAD(self) -> None:
        self._send(405, "text/plain; charset=utf-8", b"")

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(min(length, 65536))
        if urlsplit(self.path).path != "/stop":
            self._send(404, "text/plain; charset=utf-8", b"not found\n")
            return
        # Only the dashboard page itself may press Stop, not another website.
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).netloc != self.headers.get("Host"):
            self._send(403, "text/plain; charset=utf-8", b"cross-origin stop refused\n")
            return
        self.server.state.request_stop()
        self._send(204, None, b"")

    # -------------------------------------------------------------- responses

    def _send(self, status: int, content_type: Optional[str], body: bytes) -> None:
        try:
            self.send_response(status)
            if content_type:
                self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.end_headers()
            if body and self.command != "HEAD":
                self.wfile.write(body)
        except _CLIENT_GONE:
            self.close_connection = True

    def _send_page(self) -> None:
        try:
            body = INDEX_HTML.read_bytes()  # read each time: edits show on reload
        except OSError:
            self._send(500, "text/plain; charset=utf-8", b"index.html is missing\n")
            return
        self._send(200, "text/html; charset=utf-8", body)

    def _stream(self, name: str) -> None:
        """Send new frames as they arrive, at most ``stream_fps`` per second."""
        state = self.server.state
        stopping = self.server.stopping
        self.close_connection = True
        try:
            self.send_response(200)
            self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}")
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(f"--{BOUNDARY}\r\n".encode())
            seq = 0
            while not stopping.is_set():
                new_seq, jpeg = state.wait_frame(name, seq, timeout=0.5)
                if jpeg is None or new_seq == seq:
                    if self._client_gone():
                        break
                    continue
                seq = new_seq
                sent_at = time.monotonic()
                # The boundary after the image lets browsers paint it at once.
                self.wfile.write(
                    b"Content-Type: image/jpeg\r\nContent-Length: "
                    + str(len(jpeg)).encode()
                    + b"\r\n\r\n"
                    + jpeg
                    + f"\r\n--{BOUNDARY}\r\n".encode()
                )
                self.wfile.flush()
                stopping.wait(max(0.0, self.server.stream_interval - (time.monotonic() - sent_at)))
        except _CLIENT_GONE:
            pass
        except OSError:
            pass

    def _client_gone(self) -> bool:
        """True when the peer closed a connection we are not writing to."""
        try:
            readable, _, _ = select.select([self.connection], [], [], 0)
            if not readable:
                return False
            return self.connection.recv(1, socket.MSG_PEEK) == b""
        except (OSError, ValueError):
            return True


def start_dashboard(
    state: GameState,
    host: str = "127.0.0.1",
    port: int = 8765,
    stream_fps: float = 10.0,
) -> DashboardServer:
    """Serve the dashboard for ``state`` from a daemon thread and return the server.

    ``port=0`` picks a free port; read it back from ``server.url``. Call
    ``server.stop()`` to shut down. Raises OSError if the port is taken.
    """
    return DashboardServer((host, port), state, stream_fps=stream_fps).start()
