import os
import runpy
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class RenderHealthHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Sayafaqbot is starting.\n")

    def log_message(self, format, *args):
        return


def start_render_port_server():
    host = os.getenv("WEB_SERVER_BIND_ADDRESS", "0.0.0.0")
    port = int(os.getenv("PORT", "10000"))
    server = ThreadingHTTPServer((host, port), RenderHealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"Render health port listening on {host}:{port}", flush=True)
    return server


if __name__ == "__main__":
    start_render_port_server()

    # The wrapper owns Render's web port. Disable the bot's aiohttp server so
    # startup cannot fail by trying to bind the same port twice.
    os.environ["IS_WEB_SUP"] = "False"

    runpy.run_module("AloneX.__main__", run_name="__main__")
