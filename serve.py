#!/usr/bin/env python3
"""Static file server with HTTP Range support and a second root for bulk data.

    python serve.py [port] [host]      # default 8000 127.0.0.1
    python serve.py 8011 0.0.0.0 --tls # HTTPS, for testing on a phone

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

--tls exists for one reason: navigator.geolocation requires a secure context,
so over plain http://192.168.x.x the phone refuses to give a position at all.
localhost is exempt, which is why the desktop works without this. The cert is
self-signed, so the phone will warn once and needs "visit anyway"; it is
written into AZIMUTH_CACHE, never into the repo, because it is a private key.
"""

import http.server
import os
import re
import socket
import subprocess
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


def lan_ip():
    """The address a phone on the same network can reach. Connecting a UDP
    socket assigns a local address without sending anything."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def ensure_cert(ip):
    """Self-signed cert covering this machine's LAN IP, cached alongside the
    data. Regenerated if the address changed -- a cert for the wrong IP fails
    in a way that looks like a server fault."""
    cert = os.path.join(CACHE, "devcert.pem")
    key = os.path.join(CACHE, "devkey.pem")
    stamp = os.path.join(CACHE, "devcert.ip")
    have = os.path.exists(cert) and os.path.exists(key)
    same = have and os.path.exists(stamp) and open(stamp).read().strip() == ip
    if not same:
        print("generating a self-signed certificate for %s ..." % ip)
        try:
            subprocess.run([
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", key, "-out", cert, "-days", "825", "-nodes",
                "-subj", "/CN=azimuth-dev",
                "-addext", "subjectAltName=IP:%s,IP:127.0.0.1,DNS:localhost" % ip,
            ], check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError) as e:
            detail = getattr(e, "stderr", b"") or b""
            sys.exit("could not generate a certificate with openssl (%s).\n%s"
                     % (e, detail.decode("utf-8", "replace")[:400]))
        with open(stamp, "w") as fh:
            fh.write(ip)
    return cert, key


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tls = "--tls" in sys.argv
    port = int(args[0]) if args else 8000
    # Loopback by default. Pass a host to expose it -- "0.0.0.0" to reach the
    # page from a phone on the same network.
    host = args[1] if len(args) > 1 else ("0.0.0.0" if tls else "127.0.0.1")
    os.chdir(HERE)

    srv = Server((host, port), Handler)
    scheme = "http"
    if tls:
        import ssl
        ip = lan_ip()
        cert, key = ensure_cert(ip)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        scheme = "https"
        print("on the phone, open:  https://%s:%d" % (ip, port))
        print("  the certificate is self-signed, so accept the warning once")
        print("  (geolocation needs a secure context; plain http will refuse)")
    print("serving %s on %s://%s:%d" % (HERE, scheme, host, port))
    print("  /terrain/ and /basemap.pmtiles from %s" % CACHE)
    srv.serve_forever()
