import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from truth_guardian.web.engine import ROOT

SCRIPT = ROOT / "scripts" / "docker_healthcheck.py"


def check_against(state: str | None) -> subprocess.CompletedProcess:
    """Run the health check against a stand-in /api/health that reports `state` (None: nothing listens)."""

    class Health(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"state": state}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Health)
    port = server.server_address[1]
    if state is None:
        server.server_close()
    else:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        env = {**os.environ, "TG_CONTAINER_PORT": str(port), "NO_PROXY": "127.0.0.1"}
        return subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30)
    finally:
        if state is not None:
            server.shutdown()
            server.server_close()


def test_healthy_only_once_the_models_are_ready():
    assert check_against("ready").returncode == 0
    for state in ("loading", "warming", "failed"):
        result = check_against(state)
        assert result.returncode == 1 and state in result.stdout


def test_unhealthy_when_nothing_answers():
    result = check_against(None)
    assert result.returncode == 1 and "no answer" in result.stdout
