#!/usr/bin/env python3
"""Cross-platform production runner for Sagar System Health Monitor."""
from __future__ import annotations

import argparse
import json
import os
import platform
import signal
import socket
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import server as app

VERSION = "8.5.0"
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class UniversalServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 128


class UniversalHandler(app.Handler):
    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] == "/api/health":
            return self.send_json(
                {
                    "ok": True,
                    "version": VERSION,
                    "runtime": "universal-supervisor",
                    "platform": platform.system(),
                    "python": platform.python_version(),
                    "pid": os.getpid(),
                    "db": str(app.DB_PATH),
                    "app_name": app.APP_NAME,
                    "time": app.now_iso(),
                }
            )
        return super().do_GET()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("CMP_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("CMP_PORT", "2278")))
    args = parser.parse_args()

    app.init_db()
    try:
        httpd = UniversalServer((args.host, args.port), UniversalHandler)
    except OSError as exc:
        app.log(f"UNIVERSAL STARTUP ERROR host={args.host} port={args.port}: {exc}")
        print(f"STARTUP ERROR: cannot bind {args.host}:{args.port}: {exc}", flush=True)
        print("Check for another server or watchdog already using the port.", flush=True)
        raise

    runtime = {
        "version": VERSION,
        "runtime": "universal-supervisor",
        "platform": platform.system(),
        "platform_release": platform.release(),
        "python": platform.python_version(),
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "host": args.host,
        "port": args.port,
    }
    (DATA_DIR / "server_runtime.json").write_text(json.dumps(runtime, indent=2), encoding="utf-8")
    app.log("UNIVERSAL SERVER START " + json.dumps(runtime))

    stopping = threading.Event()

    def stop_server(signum=None, frame=None):
        if stopping.is_set():
            return
        stopping.set()
        app.log(f"UNIVERSAL SERVER STOP requested signal={signum}")
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    for name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                signal.signal(sig, stop_server)
            except Exception:
                pass

    print(f"{app.APP_NAME} V{VERSION} running on http://{args.host}:{args.port}", flush=True)
    try:
        httpd.serve_forever(poll_interval=0.5)
    finally:
        httpd.server_close()
        app.log("UNIVERSAL SERVER STOPPED")


if __name__ == "__main__":
    main()
