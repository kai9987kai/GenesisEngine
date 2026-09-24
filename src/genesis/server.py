"""Local browser lab. The server owns all simulation state; rendering is read-only."""
from __future__ import annotations

import json
import gzip
import mimetypes
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote

from .experiments import bounded_int, run_experiment
from .simulation import Simulation


class LabServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, seed=42):
        self.simulation = Simulation(seed)
        self.state_lock = threading.Lock()
        self.experiment_lock = threading.Lock()
        source_web = Path(__file__).resolve().parents[2] / "web"
        self.web = source_web if source_web.is_dir() else Path(sys.prefix) / "share" / "genesis" / "web"
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server: LabServer

    def log_message(self, format, *args):
        if args and str(args[1] if len(args) > 1 else "").startswith("5"):
            super().log_message(format, *args)

    def reply(self, status, data, content_type="application/json; charset=utf-8"):
        payload = json.dumps(data, allow_nan=False).encode() if content_type.startswith("application/json") else data
        compressed = len(payload) > 2048 and "gzip" in self.headers.get("Accept-Encoding", "")
        if compressed:
            payload = gzip.compress(payload, compresslevel=1, mtime=0)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        if compressed:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def same_origin(self):
        host = self.headers.get("Host", "")
        port = self.server.server_port
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        if host not in allowed:
            self.reply(403, {"error": "This lab accepts local requests only."})
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{h}" for h in allowed}:
            self.reply(403, {"error": "Cross-origin requests are not accepted."})
            return False
        return True

    def do_GET(self):
        if not self.same_origin():
            return
        path = unquote(urlparse(self.path).path)
        if path in ("/api/state", "/api/snapshot"):
            with self.server.state_lock:
                result = self.server.simulation.view() if path.endswith("state") else self.server.simulation.snapshot()
            self.reply(200, result)
        elif path.startswith("/api/"):
            self.reply(404, {"error": "Unknown API route."})
        else:
            root = self.server.web.resolve()
            file = (root / ("index.html" if path == "/" else path.lstrip("/"))).resolve()
            if not file.is_relative_to(root) or not file.is_file():
                self.reply(404, {"error": "File not found."})
                return
            mime = "text/javascript" if file.suffix == ".js" else mimetypes.guess_type(file)[0] or "application/octet-stream"
            self.reply(200, file.read_bytes(), mime + ("; charset=utf-8" if mime.startswith("text/") else ""))

    def do_POST(self):
        if not self.same_origin():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 32_000_000:
                raise ValueError("Request exceeds the 32 MB import limit.")
            if self.headers.get_content_type() != "application/json":
                raise ValueError("Use application/json.")
            data = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(data, dict):
                raise ValueError("Request body must be an object.")
            json.dumps(data, allow_nan=False)
            path = urlparse(self.path).path
            if path == "/api/experiment":
                if not self.server.experiment_lock.acquire(blocking=False):
                    self.reply(409, {"error": "An experiment is already running."})
                    return
                try:
                    result = run_experiment(data)
                finally:
                    self.server.experiment_lock.release()
            else:
                with self.server.state_lock:
                    sim = self.server.simulation
                    if path == "/api/step":
                        sim.step(bounded_int(data.get("ticks", 1), "ticks", 1, 500))
                    elif path == "/api/reset":
                        self.server.simulation = Simulation(data.get("seed", 42), data.get("config"))
                    elif path == "/api/intervene":
                        sim.intervene(data.get("changes", {}))
                    elif path == "/api/generation":
                        sim.next_generation()
                    elif path == "/api/load":
                        self.server.simulation = Simulation.from_snapshot(data.get("snapshot"))
                    else:
                        self.reply(404, {"error": "Unknown API route."})
                        return
                    result = self.server.simulation.view()
            self.reply(200, result)
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
            self.reply(400, {"error": str(exc) or "Invalid request."})
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self.reply(500, {"error": f"Simulation error: {type(exc).__name__}. See the server log."})


def serve(port=8765, seed=42, open_browser=False):
    with LabServer(("127.0.0.1", port), seed) as server:
        url = f"http://127.0.0.1:{server.server_port}"
        print(f"Genesis Engine is running at {url}", flush=True)
        if open_browser:
            import webbrowser
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nGenesis Engine stopped.")
