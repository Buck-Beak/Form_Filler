"""Serve test_site over HTTP for local bot testing (default port 8000)."""
from __future__ import annotations

import os
import sys
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler


def main() -> None:
    root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

    # Bind to IPv4 so main.py default http://127.0.0.1:8000/ matches
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))

    httpd = HTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Serving {root} at {url}")
    print("Press Ctrl+C to stop.")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
