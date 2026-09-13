#!/usr/bin/env python3
"""Static file server with HTTP Range support and a second root for bulk data.

    python serve.py [port]        # default 8000

Two reasons this is not `python -m http.server`.

First, Range. The stdlib server answers every Range request with 200 and the
whole file. Nothing on the page needs that yet, but the terrain tiles and the
PMTiles basemap that arrive with the panorama do -- PMTiles reads a few
kilobytes at a time out of an archive of tens of megabytes, and pmtiles.js
throws rather than degrading when a 200 body is larger than the range it asked
for, so the map fails outright rather than being slow.

Second, two roots. Bulk data lives outside the repo (see build.py), so
/terrain/... and /basemap.pmtiles are served out of AZIMUTH_CACHE while
everything else comes from the repo directory. A directory symlink would be
less code and the wrong answer: sync clients follow them and copy the target
back into the folder this arrangement exists to keep empty.

A plain file:// open will not work either -- the page fetches objects.json,
which browsers block from the filesystem.
"""

import http.server
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, HERE)
from build import CACHE                                   # noqa: E402

# URL prefix -> directory on disk. Everything else resolves under HERE.
MOUNTS = [
    ("/terrain/", os.path.join(CACHE, "terrain")),
    ("/basemap.pmtiles", os.path.join(CACHE, "basemap.pmtiles")),
]


class Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        clean = path.split("?", 1)[0].split("#", 1)[0]
        for prefix, target in MOUNTS:
            if clean == prefix.rstrip("/") or clean.startswith(prefix):
                rest = clean[len(prefix):].lstrip("/")
                if not rest:
                    return target
                # Refuse to climb out of the mount.
                safe = os.path.normpath(rest).replace("\\", "/")
                if safe.startswith("..") or os.path.isabs(safe):
                    return os.path.join(target, "__forbidden__")
                return os.path.join(target, *safe.split("/"))
        return super().translate_path(path)

    def send_head(self):
        rng = self.headers.get("Range")
        if not rng:
            return super().send_head()

        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()
        m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
        if not m:
            return super().send_head()
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        size = os.fstat(f.fileno()).st_size
        first, last = m.group(1), m.group(2)
        if first:
            start = int(first)
            end = int(last) if last else size - 1
        else:
            start = max(0, size - int(last or 0))       # "bytes=-500"
            end = size - 1
        if start >= size:
            f.close()
            self.send_error(416, "Requested Range Not Satisfiable")
            return None
        end = min(end, size - 1)

        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        f.seek(start)
        return _Slice(f, end - start + 1)

    def end_headers(self):
        if "Accept-Ranges" not in self._header_text():
            self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def _header_text(self):
        return b"".join(getattr(self, "_headers_buffer", [])).decode("latin-1")

    def log_message(self, fmt, *args):
        if not self.path.startswith("/favicon"):
            super().log_message(fmt, *args)


class _Slice:
    """A file object that stops after n bytes, for copyfile() to drain."""

    def __init__(self, f, n):
        self.f, self.left = f, n

    def read(self, size=-1):
        if self.left <= 0:
            return b""
        if size is None or size < 0:
            size = self.left
        data = self.f.read(min(size, self.left))
        self.left -= len(data)
        return data

    def close(self):
        self.f.close()


class Server(http.server.ThreadingHTTPServer):
    """Threaded, and not optionally so.

    The single-threaded HTTPServer serialises everything, so one client that
    holds a connection open locks every other client out entirely -- the
    socket stays LISTENING while new connections simply never complete, which
    reads as "the server is down" rather than "the server is busy". A browser
    with a few tabs on the page is enough to do it.
    """
    daemon_threads = True


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    # Loopback by default. Pass a host to expose it -- "0.0.0.0" to reach the
    # page from a phone on the same network.
    host = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
    os.chdir(HERE)
    print("serving %s on http://%s:%d" % (HERE, host, port))
    print("  /terrain/ and /basemap.pmtiles from %s" % CACHE)
    Server((host, port), Handler).serve_forever()
