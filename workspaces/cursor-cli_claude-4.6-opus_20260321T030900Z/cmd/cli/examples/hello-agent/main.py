"""
Minimal HTTP agent that proxies shell commands through CodeInterpreterClient.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from agentcube import CodeInterpreterClient


class HelloAgentHandler(BaseHTTPRequestHandler):
    """Simple GET health check and POST command runner."""

    server_version = "HelloAgent/1.0"

    def _json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/health"):
            self._send_json(200, {"status": "ok", "agent": "hello-agent"})
            return
        if parsed.path == "/exec":
            qs = parse_qs(parsed.query or "")
            cmd_list = qs.get("cmd") or []
            cmd = cmd_list[0] if cmd_list else "echo hello"
            self._run_and_respond(cmd)
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/exec":
            self._send_json(404, {"error": "not_found"})
            return
        body = self._json_body()
        cmd = str(body.get("command") or body.get("cmd") or "echo hello")
        self._run_and_respond(cmd)

    def _run_and_respond(self, command: str) -> None:
        base = os.environ.get("AGENTCUBE_CONTROL_PLANE_URL", "http://127.0.0.1:8080")
        ns = os.environ.get("AGENTCUBE_NAMESPACE", "default")
        try:
            with CodeInterpreterClient(base, namespace=ns) as ci:
                result = ci.execute_command(command)
                self._send_json(200, {"command": command, "result": result})
        except Exception as exc:  # noqa: BLE001
            self._send_json(500, {"error": str(exc), "command": command})

    def log_message(self, fmt: str, *args: Any) -> None:
        if os.environ.get("HELLO_AGENT_QUIET"):
            return
        super().log_message(fmt, *args)


def main() -> None:
    host = os.environ.get("HELLO_AGENT_HOST", "0.0.0.0")
    port = int(os.environ.get("HELLO_AGENT_PORT", "9000"))
    httpd = HTTPServer((host, port), HelloAgentHandler)
    print(f"hello-agent listening on http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
