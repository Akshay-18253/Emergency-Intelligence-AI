"""
Multi-threaded embedded HTTP server for Emergency Intelligence AI web app.
===========================================================================
Wraps Python's standard ThreadingHTTPServer to provide concurrent request processing,
ephemeral port binding for automated test suites, and clean background thread control.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from typing import Optional

from emergency_intelligence.app.handlers import EmergencyRequestHandler
from emergency_intelligence.app.state import AppState


class EmergencyAppServer:
    """Embedded HTTP server hosting REST APIs, SSE telemetry, and tactical UI."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        state: Optional[AppState] = None,
        enable_logging: bool = False,
    ) -> None:
        self.host = host
        self.requested_port = port
        self.state = state if state is not None else AppState()
        self.enable_logging = enable_logging

        # Initialize the underlying multi-threaded HTTP server
        self.httpd = ThreadingHTTPServer((self.host, self.requested_port), EmergencyRequestHandler)
        self.httpd.daemon_threads = True

        # Attach app state and logging preferences to the server instance
        setattr(self.httpd, "state", self.state)
        setattr(self.httpd, "enable_logging", self.enable_logging)

        # Retrieve the actual bound port (useful when requested_port=0 for ephemeral binding)
        self.port = self.httpd.server_port
        self._thread: Optional[threading.Thread] = None
        self._is_running = False

    def get_url(self) -> str:
        """Return the root base URL of the active server."""
        return f"http://{self.host}:{self.port}"

    def start(self, blocking: bool = True) -> None:
        """Start listening for incoming HTTP connections."""
        self._is_running = True
        if blocking:
            try:
                print(f"Emergency Intelligence AI Web App running at: {self.get_url()}")
                self.httpd.serve_forever()
            except KeyboardInterrupt:
                print("\nShutting down server gracefully...")
            finally:
                self.stop()
        else:
            self.start_background()

    def start_background(self) -> threading.Thread:
        """Start the server in a separate background daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return self._thread

        self._is_running = True
        self._thread = threading.Thread(
            target=self.httpd.serve_forever,
            name="EmergencyAppServerThread",
            daemon=True,
        )
        self._thread.start()
        # Brief pause to ensure the server socket is accepting connections
        time.sleep(0.05)
        return self._thread

    def stop(self) -> None:
        """Shut down the server and release all bound socket resources."""
        if self._is_running:
            self._is_running = False
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
            if self._thread and self._thread.is_alive() and self._thread != threading.current_thread():
                self._thread.join(timeout=2.0)


def create_app(
    host: str = "127.0.0.1",
    port: int = 8080,
    state: Optional[AppState] = None,
) -> EmergencyAppServer:
    """Factory function to instantiate an EmergencyAppServer."""
    return EmergencyAppServer(host=host, port=port, state=state)


def main(argv: Optional[list[str]] = None) -> int:
    """Command-line entry point for running the web application."""
    parser = argparse.ArgumentParser(
        description="Emergency Intelligence AI — Tactical Prototype Web Server"
    )
    parser.add_argument("--host", default="127.0.0.1", help="Binding host interface (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Binding TCP port (default: 8080)")
    parser.add_argument("--log", action="store_true", help="Enable verbose HTTP access logging")
    parser.add_argument("--dry-run", action="store_true", help="Validate configuration and bind socket briefly without blocking")

    args = parser.parse_args(argv)

    server = EmergencyAppServer(host=args.host, port=args.port, enable_logging=args.log)
    print("=" * 72)
    print("  Emergency Intelligence AI — Embedded Operations Center Server")
    print("=" * 72)
    print(f"  Target URL: {server.get_url()}")
    print("  Zero Runtime Dependencies: 100% Python Standard Library")

    if args.dry_run:
        print("  Dry-run flag detected: testing server binding...")
        server.start(blocking=False)
        time.sleep(0.05)
        server.stop()
        print("  Server successfully bound and stopped.")
        print("=" * 72 + "\n")
        return 0

    print("  Press Ctrl+C to terminate.")
    print("=" * 72 + "\n")
    try:
        server.start(blocking=True)
    except KeyboardInterrupt:
        print("\nTermination signal received. Shutting down...")
        server.stop()
        print("Server shutdown cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

