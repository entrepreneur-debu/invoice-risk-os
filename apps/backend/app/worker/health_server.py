"""Optional liveness endpoint for platforms that require an HTTP port (Cloud Run services).

Enabled only when WORKER_HEALTH_PORT is set. Runs in a daemon thread of the Celery main
process and answers 200 on any GET; it exposes no data.
"""

import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger(__name__)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b'{"status":"ok"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:  # keep logs structured and quiet
        return


def start_if_configured() -> ThreadingHTTPServer | None:
    port = os.environ.get("WORKER_HEALTH_PORT")
    if not port:
        return None
    server = ThreadingHTTPServer(("0.0.0.0", int(port)), _Handler)  # noqa: S104 - container port
    threading.Thread(target=server.serve_forever, name="worker-health", daemon=True).start()
    logger.info("worker health endpoint listening", extra={"port": int(port)})
    return server
