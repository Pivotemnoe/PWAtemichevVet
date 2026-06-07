#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


UPSTREAM_CHAT_COMPLETIONS = "https://api.openai.com/v1/chat/completions"


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


class OpenAIGatewayHandler(BaseHTTPRequestHandler):
    server_version = "TemichevVetOpenAIGateway/1.0"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"ok": True})
            return
        self._send_json(404, {"error": {"message": "not_found"}})

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self._send_json(404, {"error": {"message": "not_found"}})
            return
        if not self._authorized():
            self._send_json(401, {"error": {"message": "unauthorized"}})
            return

        try:
            length = int(self.headers.get("content-length", "0"))
        except ValueError:
            length = 0
        body = self.rfile.read(length)
        if not body:
            self._send_json(400, {"error": {"message": "empty_body"}})
            return

        upstream_key = _env("OPENAI_API_KEY")
        if not upstream_key:
            self._send_json(500, {"error": {"message": "openai_key_not_configured"}})
            return

        request = Request(
            UPSTREAM_CHAT_COMPLETIONS,
            data=body,
            headers={
                "Authorization": f"Bearer {upstream_key}",
                "Content-Type": self.headers.get("content-type", "application/json"),
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=float(_env("OPENAI_GATEWAY_TIMEOUT", "65"))) as response:
                payload = response.read()
                self._send_bytes(response.status, payload, response.headers.get("content-type", "application/json"))
        except HTTPError as exc:
            payload = exc.read()
            self._send_bytes(exc.code, payload, exc.headers.get("content-type", "application/json"))
        except URLError as exc:
            self._send_json(502, {"error": {"message": f"upstream_unavailable: {exc.reason}"}})
        except Exception as exc:
            self._send_json(502, {"error": {"message": f"gateway_error: {exc}"}})

    def _authorized(self) -> bool:
        token = _env("OPENAI_GATEWAY_TOKEN")
        if not token:
            return False
        auth = self.headers.get("authorization", "")
        if auth == f"Bearer {token}":
            return True
        return self.headers.get("x-gateway-token", "") == token

    def _send_json(self, status: int, payload: dict) -> None:
        self._send_bytes(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json")

    def _send_bytes(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))


def main() -> None:
    host = _env("OPENAI_GATEWAY_HOST", "127.0.0.1")
    port = int(_env("OPENAI_GATEWAY_PORT", "8091"))
    server = ThreadingHTTPServer((host, port), OpenAIGatewayHandler)
    print(f"OpenAI gateway listening on {host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
