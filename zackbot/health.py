"""Tiny HTTP health endpoint.

Socket Mode doesn't need inbound HTTP, but Cloud Run services must listen on
$PORT or they fail their startup check. If PORT is set, answer 200 on any GET.
"""

import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server naming
        body = b"ZackBot is up. Allegedly.\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep logs quiet
        pass


def start_health_server(port: int | None = None) -> ThreadingHTTPServer | None:
    """Start the health server in a background thread if a port is configured."""
    if port is None:
        if not os.getenv("PORT"):
            return None
        port = int(os.environ["PORT"])
    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
