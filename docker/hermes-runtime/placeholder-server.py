#!/usr/bin/env python3
"""Static placeholder server that works behind JupyterHub subpath routing."""

from __future__ import annotations

import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote


APP_DIR = Path(os.environ.get("HERMES_APP_DIR", "/home/hermes/app")).resolve()
BASE_PATH = os.environ.get("PUBLIC_BASE_PATH", "/")
PORT = int(os.environ.get("PORT", "8080"))


def normalized_base_path() -> str:
    base = BASE_PATH or "/"
    if not base.startswith("/"):
        base = "/" + base
    if not base.endswith("/"):
        base += "/"
    return base


class BasePathHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        base = normalized_base_path()
        request_path = unquote(path.split("?", 1)[0].split("#", 1)[0])

        if base != "/" and request_path.startswith(base):
            request_path = "/" + request_path[len(base) :]

        if request_path in ("", "/"):
            request_path = "/index.html"

        target = (APP_DIR / request_path.lstrip("/")).resolve()
        if not str(target).startswith(str(APP_DIR)):
            return str(APP_DIR / "index.html")
        return str(target)


def main() -> None:
    handler = partial(BasePathHandler, directory=str(APP_DIR))
    server = ThreadingHTTPServer(("0.0.0.0", PORT), handler)
    print(f"Serving {APP_DIR} at 0.0.0.0:{PORT} under {normalized_base_path()}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
