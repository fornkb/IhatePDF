"""Serve IhatePDF on loopback and open the user's browser."""

from pathlib import Path
import os
import socket
import sys
import tempfile
import threading
import webbrowser

from werkzeug.serving import BaseWSGIServer

from .web import create_app


class LocalServer(BaseWSGIServer):
    # Windows SO_REUSEADDR permits two servers to bind the same port. An old
    # preview could then serve stale HTML together with the new static files.
    allow_reuse_address = False

    def server_bind(self):
        if sys.platform == "win32":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main() -> int:
    project = Path(__file__).resolve().parents[2]
    temporary_root = project / "tmp"
    temporary_root.mkdir(parents=True, exist_ok=True)
    try:
        port = int(os.environ.get("IHATEPDF_PORT", "8765"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        print("IHATEPDF_PORT must be a number between 1 and 65535.")
        return 1
    with tempfile.TemporaryDirectory(prefix="ihatepdf-web-", dir=temporary_root) as work:
        app = create_app(Path(work))
        try:
            # PyMuPDF operations run sequentially; the engine is not thread-safe.
            server = LocalServer("127.0.0.1", port, app)
        except (OSError, SystemExit):
            print(f"Port {port} is in use. Close the other app or set IHATEPDF_PORT to another port.")
            return 1
        url = f"http://127.0.0.1:{port}"
        print(f"\nIhatePDF\nOpen {url}\nPress Ctrl+C to stop.\n", flush=True)
        if os.environ.get("IHATEPDF_NO_BROWSER") != "1":
            timer = threading.Timer(0.5, lambda: webbrowser.open(url))
            timer.daemon = True
            timer.start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nIhatePDF stopped.")
        finally:
            server.server_close()
    return 0

