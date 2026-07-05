"""Tiny static file server for a generated app's frontend.

Launched as a subprocess by ``forge.app_runner``. Serves the generated
``frontend/`` directory and injects ``window.FORGE_API_BASE`` into index.html
so the frontend talks to whichever port the backend actually bound to
(the generated app.js falls back to http://localhost:8000 otherwise).

Usage:
    python _static_server.py <directory> <port> <api_base>
"""
from __future__ import annotations

import http.server
import os
import socketserver
import sys


def main() -> None:
    directory = sys.argv[1]
    port = int(sys.argv[2])
    api_base = sys.argv[3]
    inject = f"<script>window.FORGE_API_BASE={api_base!r};</script>"

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

        def log_message(self, *args):  # keep the console quiet
            pass

        def _send_index(self) -> None:
            index_path = os.path.join(directory, "index.html")
            with open(index_path, "r", encoding="utf-8") as f:
                html = f.read()
            if "</head>" in html:
                html = html.replace("</head>", inject + "</head>", 1)
            else:
                html = inject + html
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send_index()
                return
            super().do_GET()

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), Handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
