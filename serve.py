"""Static server for local preview, with live reload.

Two things a plain `python -m http.server` will not do:

1. It lets the browser cache index.html, so edits do not show up on reload.
2. It has no way to tell the page that the file changed.

This handler sends no-store on everything, exposes the page's modification time
at /__mtime, and injects a small poller into the HTML on the way out. The
injection happens in memory only - index.html on disk stays clean, so nothing
here ends up in a commit.
"""
import http.server
import os
import sys

ROOT = r"C:\Users\kenor\humane-performance"
PAGE = os.path.join(ROOT, "index.html")

# location.reload() preserves the hash, so a live edit keeps you on whichever
# section you were looking at.
RELOAD_SNIPPET = b"""
<script>
(function () {
  var last = null;
  setInterval(function () {
    fetch('/__mtime', { cache: 'no-store' })
      .then(function (r) { return r.text(); })
      .then(function (t) {
        if (last === null) { last = t; return; }
        if (t !== last) { location.reload(); }
      })
      .catch(function () { /* server restarting; try again next tick */ });
  }, 700);
})();
</script>
</body>"""


class PreviewHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        # log_error passes an HTTPStatus here, not a string, so coerce before
        # testing - otherwise every error response raises inside the logger.
        first = str(args[0]) if args else ""
        if "__mtime" not in first:
            super().log_message(fmt, *args)

    def _no_cache(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path == "/__mtime":
            body = str(os.path.getmtime(PAGE)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/favicon.ico":
            # The site has no favicon; answer cleanly instead of 404-ing on
            # every page load.
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if path in ("/", "/index.html"):
            with open(PAGE, "rb") as fh:
                body = fh.read()
            if b"</body>" in body:
                body = body.replace(b"</body>", RELOAD_SNIPPET, 1)
            else:
                body += RELOAD_SNIPPET
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        super().do_GET()

    def end_headers(self):
        # Single place that stamps no-cache, so every response gets it exactly
        # once - the injected page, /__mtime, and anything the parent serves.
        self._no_cache()
        super().end_headers()

    def send_header(self, keyword, value):
        # Drop validators that would let the browser answer from cache.
        if keyword in ("Last-Modified", "ETag"):
            return
        super().send_header(keyword, value)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), PreviewHandler) as httpd:
        print(f"serving {ROOT} on http://localhost:{port} (no-cache, live reload)", flush=True)
        httpd.serve_forever()
