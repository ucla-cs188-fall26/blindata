#!/usr/bin/env python3
"""Zero-dependency local web UI for interactive_agent.py and the original checker.py.

Run from the blindata repository: python3 agent_web.py
Then open http://127.0.0.1:8765 in a browser.
"""
from __future__ import annotations

from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import secrets
import tempfile

from interactive_agent import EvidenceAgent

UI = Path(__file__).with_name("agent_ui.html")
SESSIONS: dict[str, EvidenceAgent] = {}
MAX_BODY = 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path not in ("/", "/static/agent_ui.js"):
            self.send_error(404)
            return
        try:
            body = (UI if self.path == "/" else UI.parent / "static" / "agent_ui.js").read_bytes()
        except OSError:
            self.send_error(500, "Missing agent_ui.html")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8" if self.path == "/" else "application/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path not in ("/api/start", "/api/ask"):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                self._json(413, {"error": "Request must be under 1 MB."})
                return
            params = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(params, dict):
                raise ValueError("Expected a JSON object.")
            if self.path == "/api/start":
                fmt = params.get("format", "csv")
                if fmt not in ("csv", "json", "tsv", "txt"):
                    raise ValueError("Unsupported format.")
                data, desc = params.get("data"), params.get("description")
                if not isinstance(data, str) or not isinstance(desc, str) or not data.strip() or not desc.strip():
                    raise ValueError("Data and description are required.")
                with tempfile.TemporaryDirectory(prefix="blindata_agent_") as folder:
                    dpath = Path(folder) / ("data." + fmt)
                    tpath = Path(folder) / "description.txt"
                    dpath.write_text(data, encoding="utf-8")
                    tpath.write_text(desc, encoding="utf-8")
                    agent = EvidenceAgent.from_files(dpath, tpath)
                session_id = secrets.token_urlsafe(18)
                # Keeps only a small set of local sessions, all in process memory.
                if len(SESSIONS) >= 16:
                    SESSIONS.pop(next(iter(SESSIONS)))
                SESSIONS[session_id] = agent
                self._json(200, {"session_id": session_id,
                                 "result": agent.summary(),
                                 "findings": [asdict(f) for f in agent.findings],
                                 "agent_mode": ("llm" if os.environ.get("BLINDATA_AGENT_MODE", "auto") != "rules"
                                                and bool(os.environ.get("OPENAI_API_KEY")) else "rules")})
                return
            session_id = params.get("session_id")
            question = params.get("question")
            if not isinstance(question, str) or len(question) > 4000:
                raise ValueError("Question must be text under 4000 characters.")
            agent = SESSIONS.get(session_id)
            if agent is None:
                self._json(404, {"error": "Session expired. Run verification again."})
                return
            self._json(200, {"result": agent.ask(question)})
        except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            self._json(400, {"error": f"Invalid input: {error}"})
        except Exception:
            # Don't leak local paths or tracebacks through the web UI.
            self._json(500, {"error": "Unable to process this input. Please review the data format."})


def main() -> None:
    address = ("127.0.0.1", 8765)
    print(f"Open http://{address[0]}:{address[1]} in your browser. Press Ctrl+C to quit.")
    with ThreadingHTTPServer(address, Handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
