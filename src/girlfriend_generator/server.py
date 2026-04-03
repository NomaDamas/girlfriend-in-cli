from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import urlparse

from .api import RomanceService


class RomanceHTTPRequestHandler(BaseHTTPRequestHandler):
    service = RomanceService()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        status, payload = route_request(self.service, "GET", parsed.path, {})
        self._send_json(status, payload)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        payload = self._read_json()
        status, response_payload = route_request(self.service, "POST", parsed.path, payload)
        self._send_json(status, response_payload)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return None

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def route_request(
    service: RomanceService,
    method: str,
    path: str,
    payload: dict,
) -> tuple[HTTPStatus, dict]:
    try:
        if method == "GET":
            if path.startswith("/v1/sessions/") and path.endswith("/state"):
                session_id = path.split("/")[3]
                return HTTPStatus.OK, service.get_state(session_id)
            if path == "/healthz":
                return HTTPStatus.OK, {"status": "ok"}
            return HTTPStatus.NOT_FOUND, {"error": "not_found"}

        if method == "POST":
            if path == "/v1/context/compile":
                return HTTPStatus.CREATED, service.compile_context(payload)
            if path == "/v1/sessions":
                return HTTPStatus.CREATED, service.create_session(payload)
            if path.startswith("/v1/sessions/") and path.endswith("/message"):
                session_id = path.split("/")[3]
                return HTTPStatus.OK, service.post_message(session_id, payload)
            if path.startswith("/v1/sessions/") and path.endswith("/tick"):
                session_id = path.split("/")[3]
                return HTTPStatus.OK, service.tick(session_id, payload)
            return HTTPStatus.NOT_FOUND, {"error": "not_found"}

        return HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"}
    except KeyError as exc:
        return HTTPStatus.NOT_FOUND, {"error": str(exc)}
    except Exception as exc:  # pragma: no cover
        return HTTPStatus.BAD_REQUEST, {"error": str(exc)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Girlfriend Generator JSON API server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    server = ThreadingHTTPServer((args.host, args.port), RomanceHTTPRequestHandler)
    try:
        print(f"girlfriend-generator-api listening on http://{args.host}:{args.port}")
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
