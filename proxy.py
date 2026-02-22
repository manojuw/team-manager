import http.server
import urllib.request
import urllib.error
import socket
import sys
import os
import signal
import time
import threading

LISTEN_PORT = 5000
NEXT_PORT = 5001
MGMT_PORT = 3001
AI_PORT = 8001

class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self._proxy()

    def do_POST(self):
        self._proxy()

    def do_PUT(self):
        self._proxy()

    def do_DELETE(self):
        self._proxy()

    def do_PATCH(self):
        self._proxy()

    def do_OPTIONS(self):
        self._proxy()

    def do_HEAD(self):
        self._proxy()

    def _proxy(self):
        target = self._get_target()
        try:
            body = None
            content_length = self.headers.get("Content-Length")
            if content_length:
                body = self.rfile.read(int(content_length))

            headers = {}
            for key, val in self.headers.items():
                if key.lower() not in ("host", "transfer-encoding"):
                    headers[key] = val

            req = urllib.request.Request(
                f"http://127.0.0.1:{target}{self.path}",
                data=body,
                headers=headers,
                method=self.command,
            )

            with urllib.request.urlopen(req, timeout=120) as resp:
                self.send_response(resp.status)
                for key, val in resp.getheaders():
                    if key.lower() not in ("transfer-encoding",):
                        self.send_header(key, val)
                self.end_headers()

                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            for key, val in e.headers.items():
                if key.lower() not in ("transfer-encoding",):
                    self.send_header(key, val)
            self.end_headers()
            body_data = e.read()
            if body_data:
                self.wfile.write(body_data)
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"Proxy error: {e}".encode())

    def _get_target(self):
        path = self.path
        if path.startswith("/api/management/"):
            self.path = "/api/" + path[len("/api/management/"):]
            return MGMT_PORT
        if path.startswith("/api/ai/"):
            self.path = "/api/" + path[len("/api/ai/"):]
            return AI_PORT
        return NEXT_PORT

    def log_message(self, format, *args):
        pass


class ThreadedHTTPServer(http.server.HTTPServer):
    allow_reuse_address = True
    request_queue_size = 128

    def process_request(self, request, client_address):
        t = threading.Thread(target=self.process_request_thread, args=(request, client_address))
        t.daemon = True
        t.start()

    def process_request_thread(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)


if __name__ == "__main__":
    server = ThreadedHTTPServer(("0.0.0.0", LISTEN_PORT), ProxyHandler)
    print(f"[PROXY] Reverse proxy listening on port {LISTEN_PORT}", flush=True)
    print(f"[PROXY] Routing: / -> Next.js:{NEXT_PORT}, /api/management/* -> :{MGMT_PORT}, /api/ai/* -> :{AI_PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
