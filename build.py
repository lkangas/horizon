#!/usr/bin/env python3
"""Build objects.json: Finland's horizon-recognisable structures, with N2000 tops.

    python build.py fetch          # populate the cache (resumable)
    python build.py build          # cache -> objects.json
    python build.py stats          # what is in the cache

Everything is Python 3 stdlib. No GDAL, no node, no database.

Positions and ground elevations come from MML Maastotietokanta, read over HTTP
Range out of a 4.4 GB GeoPackage rather than downloading it -- a GeoPackage is
SQLite, so the eight tower tables cost a few megabytes. Structure heights come
from three places, in this order of trust: MTK's own height annotations, the
Fintraffic aviation obstacle register, and OpenStreetMap.

Bulk data never lands in the repo; see cache_dir().
"""

import calendar
import csv
import io
import json
import math
import os
import re
import struct
import sys
import time
import zlib
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "objects.json")

UA = {"User-Agent": "azimuth/0.1 (+https://github.com/lkangas/azimuth)"}


# --------------------------------------------------------------------------
# Cache location.
#
# The repo directory can easily sit inside a synced folder, and this cache runs
# to a couple of gigabytes, so it is deliberately somewhere else. Stop rather
# than fall back to HERE: a silent fallback is how you discover the problem as
# a gigabyte of GML syncing to the cloud.
# --------------------------------------------------------------------------

def cache_dir():
    d = os.environ.get("AZIMUTH_CACHE")
    if not d:
        base = (os.environ.get("LOCALAPPDATA")
                or os.environ.get("XDG_CACHE_HOME")
                or os.path.join(os.path.expanduser("~"), ".cache"))
        d = os.path.join(base, "azimuth")
    try:
        os.makedirs(os.path.join(d, "raw"), exist_ok=True)
        probe = os.path.join(d, ".writable")
        with open(probe, "w") as f:
            f.write("")
        os.remove(probe)
    except OSError as e:
        sys.exit("cache directory %s is not usable (%s).\n"
                 "Set AZIMUTH_CACHE to a writable path on a volume with a few GB free." % (d, e))
    return d


CACHE = cache_dir()
RAW = os.path.join(CACHE, "raw")


def raw(name):
    return os.path.join(RAW, name)


def get(url, timeout=120, headers=None):
    h = dict(UA)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# --------------------------------------------------------------------------
# ETRS-TM35FIN (EPSG:3067) -> WGS84.
#
# Kruger series inverse on GRS80. Accurate to well under a millimetre over
# Finland, which is four orders below the 3-7 m positional accuracy of the data
# going through it.
#
# Note this is the ONLY place projected coordinates exist. Everything
# downstream is lat/lon, because grid bearings in TM35FIN are wrong by -6.5 to
# +4.1 degrees across the country and the error is invisible if you only ever
# test near the central meridian.
# --------------------------------------------------------------------------

_A = 6378137.0
_F = 1 / 298.257222101          # GRS80
_K0 = 0.9996
_FE = 500000.0
_LON0 = math.radians(27.0)


def tm35_to_wgs84(easting, northing):
    n = _F / (2 - _F)
    n2 = n * n
    n3 = n2 * n
    n4 = n3 * n
    A = _A / (1 + n) * (1 + n2 / 4 + n4 / 64)

    xi = northing / (_K0 * A)
    eta = (easting - _FE) / (_K0 * A)

    b1 = n / 2 - 2 * n2 / 3 + 37 * n3 / 96 - n4 / 360
    b2 = n2 / 48 + n3 / 15 - 437 * n4 / 1440
    b3 = 17 * n3 / 480 - 37 * n4 / 840
    b4 = 4397 * n4 / 161280

    xi_ = xi
    eta_ = eta
    for j, b in ((1, b1), (2, b2), (3, b3), (4, b4)):
        xi_ -= b * math.sin(2 * j * xi) * math.cosh(2 * j * eta)
        eta_ -= b * math.cos(2 * j * xi) * math.sinh(2 * j * eta)

    beta = math.asin(max(-1.0, min(1.0, math.sin(xi_) / math.cosh(eta_))))
    lam = _LON0 + math.atan(math.sinh(eta_) / math.cos(xi_))

    d1 = 2 * n - 2 * n2 / 3 - 2 * n3
    d2 = 7 * n2 / 3 - 8 * n3 / 5
    d3 = 56 * n3 / 15
    d4 = 4279 * n4 / 630
    phi = beta
    for j, d in ((1, d1), (2, d2), (3, d3), (4, d4)):
        phi += d * math.sin(2 * j * beta)

    return math.degrees(phi), math.degrees(lam)


# --------------------------------------------------------------------------
# A minimal SQLite reader that pages a remote file over HTTP Range.
#
# MTK-rakennus is 4,393,316,352 bytes and the eight tables we want are a few
# thousand rows. sqlite3 cannot open a URL, so this walks the b-trees directly:
# header -> sqlite_master -> per-table root page -> leaf cells. Pages are
# fetched in runs of 32 because the round-trip dominates, not the bytes.
# --------------------------------------------------------------------------

class Pager:
    RUN = 32

    def __init__(self, url):
        self.url = url
        self.cache = {}
        self.bytes = 0
        self.reqs = 0
        head = self._raw(0, 100)
        if head[:15] != b"SQLite format 3":
            raise SystemExit("%s is not a SQLite/GeoPackage file" % url)
        self.page_size = struct.unpack(">H", head[16:18])[0]
        if self.page_size == 1:
            self.page_size = 65536
        self.npages = struct.unpack(">I", head[28:32])[0]
        self.usable = self.page_size - head[20]

    def _raw(self, off, n):
        last = off + n - 1
        for attempt in range(4):
            try:
                req = urllib.request.Request(
                    self.url, headers=dict(UA, Range="bytes=%d-%d" % (off, last)))
                with urllib.request.urlopen(req, timeout=120) as r:
                    if r.status != 206:
                        raise SystemExit(
                            "%s answered %d, not 206 -- the host is ignoring Range requests "
                            "and this would download 4.4 GB." % (self.url, r.status))
                    d = r.read()
                self.bytes += len(d)
                self.reqs += 1
                return d
            except urllib.error.URLError:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)

    def page(self, pno):
        if pno not in self.cache:
            start = ((pno - 1) // self.RUN) * self.RUN + 1
            n = min(self.RUN, self.npages - start + 1)
            blob = self._raw((start - 1) * self.page_size, n * self.page_size)
            for i in range(n):
                self.cache[start + i] = blob[i * self.page_size:(i + 1) * self.page_size]
        return self.cache[pno]


def _varint(buf, i):
    v = 0
    for k in range(9):
        b = buf[i + k]
        if k == 8:
            return (v << 8) | b, i + 9
        v = (v << 7) | (b & 0x7F)
        if not b & 0x80:
            return v, i + k + 1


_SERLEN = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 6, 6: 8, 7: 8, 8: 0, 9: 0}


def _record(buf):
    hlen, i = _varint(buf, 0)
    types = []
    while i < hlen:
        t, i = _varint(buf, i)
        types.append(t)
    out = []
    for t in types:
        n = (t - 12) // 2 if t >= 12 and t % 2 == 0 else \
            (t - 13) // 2 if t >= 13 else _SERLEN[t]
        chunk = buf[i:i + n]
        i += n
        if t == 0:
            out.append(None)
        elif 1 <= t <= 6:
            out.append(int.from_bytes(chunk, "big", signed=True))
        elif t == 7:
            out.append(struct.unpack(">d", chunk)[0])
        elif t == 8:
            out.append(0)
        elif t == 9:
            out.append(1)
        elif t % 2 == 0:
            out.append(chunk)
        else:
            out.append(chunk.decode("utf-8", "replace"))
    return out


class RemoteDB:
    def __init__(self, url):
        self.p = Pager(url)
        self.tables = {}
        for row in self._rows(1):
            if row[0] == "table":
                self.tables[row[1]] = (row[3], row[4])   # rootpage, ddl

    def _payload(self, page, off, plen):
        u = self.p.usable
        X = u - 35
        if plen <= X:
            return page[off:off + plen]
        M = ((u - 12) * 32 // 255) - 23
        K = M + ((plen - M) % (u - 4))
        local = K if K <= X else M
        data = bytearray(page[off:off + local])
        ovf = struct.unpack(">I", page[off + local:off + local + 4])[0]
        rem = plen - local
        while rem > 0 and ovf:
            op = self.p.page(ovf)
            nxt = struct.unpack(">I", op[0:4])[0]
            take = min(rem, u - 4)
            data += op[4:4 + take]
            rem -= take
            ovf = nxt
        return bytes(data)

    def _rows(self, pno, out=None):
        if out is None:
            out = []
        stack = [pno]
        while stack:
            p = stack.pop()
            page = self.p.page(p)
            base = 100 if p == 1 else 0
            typ = page[base]
            ncell = struct.unpack(">H", page[base + 3:base + 5])[0]
            cstart = base + (12 if typ in (2, 5) else 8)
            cells = [struct.unpack(">H", page[cstart + 2 * i:cstart + 2 * i + 2])[0]
                     for i in range(ncell)]
            if typ == 13:
                for c in cells:
                    plen, i = _varint(page, c)
                    _rid, i = _varint(page, i)
                    out.append(_record(self._payload(page, i, plen)))
            elif typ == 5:
                right = struct.unpack(">I", page[base + 8:base + 12])[0]
                if right:
                    stack.append(right)
                for c in cells:
                    stack.append(struct.unpack(">I", page[c:c + 4])[0])
            else:
                raise SystemExit("unexpected b-tree page type %d at page %d" % (typ, p))
        return out

    def columns(self, table):
        ddl = self.tables[table][1]
        body = ddl[ddl.index("(") + 1:ddl.rindex(")")]
        cols, depth, cur = [], 0, ""
        for ch in body:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch == "," and depth == 0:
                cols.append(cur)
                cur = ""
            else:
                cur += ch
        cols.append(cur)
        return [c.strip().split()[0].strip('"') for c in cols if c.strip()]

    def read(self, table):
        """Every row of `table` as a dict."""
        names = self.columns(table)
        return [dict(zip(names, r)) for r in self._rows(self.tables[table][0])]


def gpkg_point(blob):
    """(x, y, z) out of a GeoPackage point, or None."""
    if not isinstance(blob, (bytes, bytearray)) or blob[:2] != b"GP":
        return None
    flags = blob[3]
    envlen = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[(flags >> 1) & 7]
    off = 8 + envlen
    e = "<" if blob[off] == 1 else ">"
    gtype = struct.unpack(e + "I", blob[off + 1:off + 5])[0]
    if gtype not in (1, 1001, 2001, 3001):
        return None
    x, y = struct.unpack(e + "dd", blob[off + 5:off + 21])
    z = None
    if gtype in (1001, 3001) and len(blob) >= off + 29:
        z = struct.unpack(e + "d", blob[off + 21:off + 29])[0]
        # Cartographic densification vertices. A no-op on the point classes,
        # but the mirror's own readme warns about them and it costs nothing.
        if z == -999.999:
            z = None
    return x, y, z


# --------------------------------------------------------------------------
# Sources.
# --------------------------------------------------------------------------

MTK_GPKG = ("http://www.nic.funet.fi/index/geodata/mml/maastotietokanta/"
            "2025/gpkg/MTK-rakennus_25-04-03.gpkg")

# The point classes worth carrying, and what to call them. Kellotapuli is
# 44600; 44500 is Ilmarata, an aerial cableway line class, and confusing the
# two silently drops every bell tower in the country.
MTK_POINTS = {
    "masto":        ("mast",       44800),
    "savupiippu":   ("chimney",    45300),
    "tuulivoimala": ("turbine",    45500),
    "vesitorni":    ("watertower", 45800),
    "nakotorni":    ("obstower",   45000),
    "kellotapuli":  ("belltower",  44600),
}

# Heights are separate TEXT feature classes, joined by reference. Only masts
# and chimneys have one at all.
MTK_HEIGHTS = {
    "mastonkorkeus":     ("masto",      "mastoviittaus"),
    "savupiipunkorkeus": ("savupiippu", "savupiippuviittaus"),
}

AIP_INDEX = "https://www.ais.fi/obstacles-suomi-finland"

FT = 0.3048


def wrap32(v):
    """mtk_id is a signed 32-bit int; the *viittaus columns are unsigned
    decimal strings. A naive join matches 4,197 of 4,282 masts; wrapping
    recovers 4,278."""
    if v is None:
        return None
    v = int(v)
    return v - (1 << 32) if v >= (1 << 31) else v


def fetch_mtk():
    dest = raw("mtk.json")
    if os.path.exists(dest):
        print("mtk.json present, skipping (delete it to refetch)")
        return
    print("reading %s over HTTP Range" % MTK_GPKG.rsplit("/", 1)[-1])
    db = RemoteDB(MTK_GPKG)

    # Heights first: drive the join FROM the height table. The forward pointer
    # masto.mastonkorkeusviittaus is non-null on 3,957 rows and resolves 3,609,
    # so joining that way silently loses ~320 masts' heights.
    heights = {}
    for htab, (target, ref) in MTK_HEIGHTS.items():
        seen = {}
        for r in db.read(htab):
            key = wrap32(r.get(ref))
            if key is None or r.get("korkeusarvo") is None:
                continue
            seen[key] = r["korkeusarvo"] / 1000.0      # millimetres
        heights[target] = seen
        print("  %-18s %5d rows -> %4d distinct %s" %
              (htab, len(db.read(htab)), len(seen), target))

    out = []
    for table, (cat, code) in MTK_POINTS.items():
        n = 0
        for r in db.read(table):
            pt = gpkg_point(r.get("sijainti_piste"))
            if not pt:
                continue
            x, y, z = pt
            lat, lon = tm35_to_wgs84(x, y)
            mid = wrap32(r.get("mtk_id"))
            rec = {
                "cat": cat,
                "lat": round(lat, 7),
                "lon": round(lon, 7),
                "ground_m": None if z is None else round(z, 2),
                "src_pos": "mtk",
                "mtk_id": mid,
                "acc_m": (r.get("sijaintitarkkuus") or 0) / 1000.0 or None,
            }
            h = heights.get(table, {}).get(mid)
            if h is not None:
                rec["height_m"] = h
                rec["src_h"] = "mtk"
            out.append(rec)
            n += 1
        print("  %-18s %5d points" % (table, n))

    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f)
    print("  %d objects, %d requests, %.1f MB transferred"
          % (len(out), db.p.reqs, db.p.bytes / 1e6))


def fetch_aip():
    dest = raw("aip_area1.csv")
    if os.path.exists(dest):
        print("aip_area1.csv present, skipping")
        return
    # The filename embeds the AIRAC effective date and is republished every 28
    # days at a new path, so scrape the index rather than hard-coding a URL --
    # a stale hard-coded link serves old data forever instead of 404ing.
    page = get(AIP_INDEX).decode("utf-8", "replace")
    links = re.findall(r'href="([^"]*area1_obstdata[^"]*\.zip)"', page, re.I)
    if not links:
        sys.exit("no Area 1 obstacle zip linked from %s" % AIP_INDEX)
    url = urllib.parse.urljoin(AIP_INDEX, sorted(links)[-1])
    print("fetching %s" % url.rsplit("/", 1)[-1])
    blob = get(url)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        data = z.read(name)
    with open(dest, "wb") as f:
        f.write(data)
    print("  %s -> %d bytes" % (name, len(data)))


# --------------------------------------------------------------------------
# OpenStreetMap, via Overpass.
#
# ODbL, so objects.json is ODbL -- see PLAN.md section 8. OSM is here for the
# two things the registers cannot supply: names (MTK has no selite for masts or
# chimneys at all) and heights for the classes MTK never heights.
#
# Overpass is the least reliable dependency in the build, so: a mirror list,
# and the response is cached. Query the Finland admin AREA, never a bbox --
# Finland's bbox contains St Petersburg, Tallinn, eastern Sweden and Kola.
# --------------------------------------------------------------------------

OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# tower:type=lighting is excluded on purpose: 3,304 sports-field and car-park
# floodlights, and they have the HIGHEST height-tag coverage of any category,
# so an unfiltered query is mostly them.
OVERPASS_QL = """
[out:json][timeout:600];
area["ISO3166-1"="FI"][admin_level=2]->.fi;
(
  nwr["man_made"="mast"](area.fi);
  nwr["man_made"="tower"](area.fi);
  nwr["man_made"="communications_tower"](area.fi);
  nwr["man_made"="chimney"](area.fi);
  nwr["man_made"="water_tower"](area.fi);
  nwr["man_made"="lighthouse"](area.fi);
  nwr["generator:source"="wind"](area.fi);
);
out center tags;
"""

OSM_CAT = {
    "mast": "mast",
    "communications_tower": "mast",
    "chimney": "chimney",
    "water_tower": "watertower",
    "lighthouse": "lighthouse",
    "tower": "obstower",          # refined by tower:type below
}


def num(v):
    """OSM height strings. Only 3 of 4,900 Finnish values fail to parse."""
    if v in (None, "", "NIL"):
        return None
    m = re.match(r"\s*(-?\d+(?:[.,]\d+)?)", str(v).replace(",", "."))
    return float(m.group(1)) if m else None


def fetch_osm(max_age_days=45):
    """Fetch from the first mirror that answers with a FRESH Finland.

    Element count alone is not a sufficient check. The fallback mirrors stay up
    while serving a months-old planet: on 2026-09-14 both kumi.systems and
    private.coffee answered happily with a 2026-05-06 snapshot holding 7,764
    masts against the true 9,529 -- an 18% shortfall that looks like a
    perfectly healthy response. So gate on timestamp_osm_base, not on size.
    """
    dest = raw("osm.json")
    if os.path.exists(dest):
        with open(dest, encoding="utf-8") as f:
            age = _osm_age(json.load(f))
        if age is not None and age <= max_age_days:
            print("osm.json present and %.0f days old, skipping" % age)
            return
        print("osm.json is %s days old, refetching" % ("?" if age is None else "%.0f" % age))
    body = OVERPASS_QL.encode()
    stale = []
    for url in OVERPASS_MIRRORS:
        host = urllib.parse.urlsplit(url).netloc
        try:
            print("  %-32s ..." % host, end="", flush=True)
            req = urllib.request.Request(url, data=body, headers=UA)
            with urllib.request.urlopen(req, timeout=900) as r:
                blob = r.read()
            d = json.loads(blob)
            n = len(d.get("elements", []))
            age = _osm_age(d)
            # A small count from an area query is a lie, not a count: a mirror
            # holding a regional extract answers 200 with a well-formed 0.
            if n < 1000:
                print(" %d elements -- wrong extract?" % n)
                continue
            if age is None or age > max_age_days:
                print(" %d elements but %s days stale" % (n, "?" if age is None else "%.0f" % age))
                stale.append((age, blob, n, host))
                continue
            print(" %d elements, %.0f days old" % (n, age))
            with open(dest, "wb") as f:
                f.write(blob)
            return
        except Exception as e:
            print(" %s" % type(e).__name__)
    if stale:
        stale.sort(key=lambda t: t[0] if t[0] is not None else 1e9)
        age, blob, n, host = stale[0]
        sys.exit(
            "every mirror is stale; freshest is %s at %.0f days (%d elements)." % (host, age, n)
            + "\nNames and the OSM-only structures would be that far behind."
            + "\nRetry later, or raise max_age_days deliberately.")
    sys.exit("every Overpass mirror failed; try again later")


def _osm_age(d):
    """Days between the response's planet snapshot and now."""
    ts = (d.get("osm3s") or {}).get("timestamp_osm_base")
    if not ts:
        return None
    try:
        t = time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    return (time.time() - calendar.timegm(t)) / 86400.0


def load_osm():
    path = raw("osm.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    out = []
    for el in d.get("elements", []):
        t = el.get("tags") or {}
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        if t.get("tower:type") == "lighting":
            continue
        if t.get("generator:source") == "wind":
            cat = "turbine"
        else:
            cat = OSM_CAT.get(t.get("man_made"))
            if cat == "obstower":
                cat = {"observation": "obstower", "lookout": "obstower",
                       "communication": "mast", "bell_tower": "belltower"
                       }.get(t.get("tower:type", ""), "obstower")
        if not cat:
            continue
        h = num(t.get("height"))
        if h is None and cat == "turbine":
            # hub height, not tip. Measured over the 53 Finnish turbines
            # tagged with both, height/height:hub has median 1.429.
            hub = num(t.get("height:hub"))
            h = round(hub * 1.43, 1) if hub else None
        out.append({
            "cat": cat, "lat": lat, "lon": lon, "ground_m": None,
            "height_m": h, "src_h": "osm" if h else None,
            "name": t.get("name"), "src_pos": "osm",
        })
    return out


# --------------------------------------------------------------------------
# Aviation obstacle register.
# --------------------------------------------------------------------------

AIP_CAT = {
    "Mast": "mast",
    "Chimney": "chimney",
    "Wind turbine": "turbine",
    "Tower": "obstower",
    "Building": "building",
    # Crane, Pylon, Pole, Built structure: temporary, or not horizon objects.
}


def load_aip():
    path = raw("aip_area1.csv")
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            cat = AIP_CAT.get((r["TYPE"] or "").strip())
            if not cat:
                continue
            try:
                lat = float(r["LAT"])
                lon = float(r["LONG"])
                # FEET. The "Unit of measurement" column reads "ft/m" on every
                # row, which describes the schema, not the row.
                agl = float(r["HGT AGL (FT)"]) * FT
                msl = float(r["ELEV MSL (FT)"]) * FT
            except (TypeError, ValueError):
                continue
            out.append({
                "cat": cat, "lat": lat, "lon": lon,
                "height_m": round(agl, 1), "ground_m": round(msl - agl, 1),
                "src_h": "aip", "src_pos": "aip",
                "acc_m": num(r.get("Horizontal accuracy (m)")),
                "obst_id": (r["OBST ID"] or "").strip(),
            })
    return out


# --------------------------------------------------------------------------
# Merge. Distances are metres in a local flat approximation, exact enough at
# the 25-300 m scale this operates on.
# --------------------------------------------------------------------------

def metres(a, b):
    dlat = (a["lat"] - b["lat"]) * 111320.0
    dlon = (a["lon"] - b["lon"]) * 111320.0 * math.cos(math.radians(a["lat"]))
    return math.hypot(dlat, dlon)


class Grid:
    """Coarse spatial hash; cell is ~1.1 km, so any radius under 1 km needs
    only the 3x3 neighbourhood."""

    def __init__(self, objs, cell=0.01):
        self.cell = cell
        self.b = defaultdict(list)
        for o in objs:
            self.add(o)

    def add(self, o):
        self.b[(int(o["lat"] / self.cell), int(o["lon"] / self.cell))].append(o)

    def near(self, o, radius):
        i, j = int(o["lat"] / self.cell), int(o["lon"] / self.cell)
        hits = []
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for c in self.b.get((i + di, j + dj), ()):
                    d = metres(o, c)
                    if d <= radius:
                        hits.append((d, c))
        hits.sort(key=lambda t: t[0])
        return hits


# Which categories may merge. A mast and a chimney at one site are two
# objects; a mast and a communications tower are one.
COMPATIBLE = {
    "mast": {"mast"},
    "chimney": {"chimney"},
    "turbine": {"turbine"},
    "watertower": {"watertower"},
    "obstower": {"obstower", "building"},
    "belltower": {"belltower"},
    "lighthouse": {"lighthouse"},
    "building": {"building", "obstower"},
}


def height_ok(a, b):
    """Veto a merge when both know a height and they disagree badly. This is
    what keeps the 322 m Jyvaskyla mast separate from the unnamed 121 m one
    159 m away."""
    ha, hb = a.get("height_m"), b.get("height_m")
    if ha is None or hb is None:
        return True
    return abs(ha - hb) <= max(10.0, 0.15 * max(ha, hb))


_RANK = {"mtk": 3, "aip": 3, "osm": 1, None: 0}


def absorb(base, other):
    """Fold `other` into `base`, preferring the more trustworthy attribute."""
    if other.get("height_m") is not None:
        if (base.get("height_m") is None
                or _RANK[other.get("src_h")] > _RANK[base.get("src_h")]):
            base["height_m"] = other["height_m"]
            base["src_h"] = other["src_h"]
    if base.get("ground_m") is None and other.get("ground_m") is not None:
        base["ground_m"] = other["ground_m"]
    if not base.get("name") and other.get("name"):
        base["name"] = other["name"]
    if other.get("obst_id") and not base.get("obst_id"):
        base["obst_id"] = other["obst_id"]
    base["srcs"] |= other["srcs"]


def merge(base, incoming, radius):
    """Fold `incoming` into `base`. Only ACROSS sources, never within one: two
    MTK chimneys 200 m apart are two chimneys (Olkiluoto has a pair of 105 m
    stacks), and self-merging a layer quietly deletes them."""
    out = list(base)
    grid = Grid(out)
    for o in out:
        o["srcs"] = set(o.get("srcs") or ()) | {o.get("src_pos")}
    for o in incoming:
        o["srcs"] = set(o.get("srcs") or ()) | {o.get("src_pos")}
        hit = next((c for _d, c in grid.near(o, radius)
                    if c["cat"] in COMPATIBLE.get(o["cat"], ()) and height_ok(o, c)),
                   None)
        if hit:
            absorb(hit, o)
        else:
            out.append(o)
            grid.add(o)
    return out


# --------------------------------------------------------------------------
# Ground elevation for objects that arrive without one.
#
# MTK points carry a 2 m-derived N2000 Z already. The OSM-only objects carry
# nothing -- OSM's ele=* is under 2% filled in Finland -- so without this they
# have a height and no top elevation, which is the one number the app exists to
# report.
#
# One GeoCubes request pulls the whole country at 100 m, ~115 MB, and it is
# then sampled locally. 100 m posting costs a couple of metres of ground error
# in rolling terrain, which at 20 km is about 30 arcseconds of elevation angle
# -- far better than no answer, and it never overwrites the 2 m-derived value
# an MTK object already has.
# --------------------------------------------------------------------------

DEM_URL = ("https://vm0160.kaj.pouta.csc.fi/geocubes/clip/100/km10/"
           "bbox:50000,6600000,760000,7800000/2018")


def fetch_dem():
    dest = raw("fin100.tif")
    if os.path.exists(dest):
        print("fin100.tif present, skipping")
        return
    print("fetching national DEM at 100 m ...", end="", flush=True)
    blob = get(DEM_URL, timeout=600)
    with open(dest, "wb") as f:
        f.write(blob)
    print(" %.0f MB" % (len(blob) / 1e6))


def _tiff_tags(d, bo, off):
    SZ = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 11: 4, 12: 8, 16: 8}
    n = struct.unpack(bo + "H", d[off:off + 2])[0]
    tags = {}
    for i in range(n):
        e = off + 2 + i * 12
        tag, typ, cnt = struct.unpack(bo + "HHI", d[e:e + 8])
        size = SZ.get(typ, 1) * cnt
        p = struct.unpack(bo + "I", d[e + 8:e + 12])[0] if size > 4 else e + 8
        chunk = d[p:p + size]
        if typ == 2:
            v = chunk.rstrip(b"\x00").decode("latin1")
        elif typ == 3:
            v = list(struct.unpack(bo + "H" * cnt, chunk))
        elif typ == 4:
            v = list(struct.unpack(bo + "I" * cnt, chunk))
        elif typ == 12:
            v = list(struct.unpack(bo + "d" * cnt, chunk))
        else:
            v = chunk
        tags[tag] = v
    return tags


def sample_dem(objs):
    """Fill ground_m from the 100 m model for objects that lack it.

    Decodes one tile at a time and samples the objects inside it, so peak
    memory is one tile rather than the whole 85-megacell mosaic.
    """
    path = raw("fin100.tif")
    need = [o for o in objs if o.get("ground_m") is None]
    if not need or not os.path.exists(path):
        return 0
    with open(path, "rb") as f:
        d = f.read()
    bo = "<" if d[:2] == b"II" else ">"
    t = _tiff_tags(d, bo, struct.unpack(bo + "I", d[4:8])[0])
    W, H = t[256][0], t[257][0]
    comp = t[259][0]
    px, py = t[33550][0], t[33550][1]
    ox, oy = t[33922][3], t[33922][4]
    nodata = float(t[42113].rstrip("\x00")) if 42113 in t else -9999.0
    tw, th = t[322][0], t[323][0]
    offs, cnts = t[324], t[325]
    ntx = (W + tw - 1) // tw

    # Bucket the objects that need a sample by tile, so each tile is
    # decompressed at most once.
    want = defaultdict(list)
    for o in need:
        e, n = wgs84_to_tm35(o["lat"], o["lon"])
        col = int((e - ox) / px)
        row = int((oy - n) / py)
        if 0 <= col < W and 0 <= row < H:
            want[(row // th) * ntx + (col // tw)].append((o, col, row))

    filled = 0
    for ti, items in want.items():
        if ti >= len(offs):
            continue
        blob = d[offs[ti]:offs[ti] + cnts[ti]]
        if comp in (5, 8):
            try:
                blob = zlib.decompress(blob)
            except zlib.error:
                continue
        elif comp != 1:
            continue
        vals = struct.unpack(bo + "f" * (len(blob) // 4), blob)
        tx0, ty0 = (ti % ntx) * tw, (ti // ntx) * th
        for o, col, row in items:
            v = vals[(row - ty0) * tw + (col - tx0)]
            if v == nodata or v < -1000 or v > 1500:
                continue
            # Sea is nodata, not zero, in this model; a coastal lighthouse
            # landing outside the land mask is genuinely at sea level.
            o["ground_m"] = round(v, 1)
            o["src_g"] = "dem100"
            filled += 1
    for o in need:
        if o.get("ground_m") is None and o["cat"] == "lighthouse":
            o["ground_m"] = 0.0            # standing on a skerry, near enough
            o["src_g"] = "sea"
            filled += 1
    return filled


def wgs84_to_tm35(lat, lon):
    """Forward Kruger series, the inverse of tm35_to_wgs84."""
    n = _F / (2 - _F)
    n2, n3, n4 = n * n, n ** 3, n ** 4
    A = _A / (1 + n) * (1 + n2 / 4 + n4 / 64)
    phi = math.radians(lat)
    dl = math.radians(lon) - _LON0
    e2 = _F * (2 - _F)
    e = math.sqrt(e2)
    t = math.sinh(math.atanh(math.sin(phi))
                  - e * math.atanh(e * math.sin(phi)))
    xi_ = math.atan(t / math.cos(dl))
    eta_ = math.atanh(math.sin(dl) / math.sqrt(1 + t * t))
    a1 = n / 2 - 2 * n2 / 3 + 5 * n3 / 16 + 41 * n4 / 180
    a2 = 13 * n2 / 48 - 3 * n3 / 5 + 557 * n4 / 1440
    a3 = 61 * n3 / 240 - 103 * n4 / 140
    a4 = 49561 * n4 / 161280
    xi, eta = xi_, eta_
    for j, a in ((1, a1), (2, a2), (3, a3), (4, a4)):
        xi += a * math.sin(2 * j * xi_) * math.cosh(2 * j * eta_)
        eta += a * math.cos(2 * j * xi_) * math.sinh(2 * j * eta_)
    return _FE + _K0 * A * eta, _K0 * A * xi


def build():
    mtk = []
    if os.path.exists(raw("mtk.json")):
        with open(raw("mtk.json"), encoding="utf-8") as f:
            mtk = json.load(f)
    aip, osm = load_aip(), load_osm()
    print("  mtk %5d   aip %5d   osm %5d" % (len(mtk), len(aip), len(osm)))

    # 150 m for the register: where MTK holds the same object the median
    # offset is 1 m, and the masts MTK genuinely lacks have their nearest MTK
    # neighbour 628 m to 4.7 km away, so the two populations separate cleanly
    # well below 300 m. A wide window would instead start merging the separate
    # stacks and paired old/new masts that share a site.
    objs = merge(mtk, aip, radius=150.0)
    objs = merge(objs, osm, radius=60.0)
    print('  filled ground from the 100 m model: %d' % sample_dem(objs))

    for o in objs:
        if o.get("ground_m") is not None and o.get("height_m") is not None:
            o["top_m"] = round(o["ground_m"] + o["height_m"], 1)
        o["srcs"] = "+".join(sorted(x for x in o["srcs"] if x))
    objs.sort(key=lambda o: -(o.get("top_m") or 0))

    payload = {
        "format": "azimuth-objects/1",
        "generated": time.strftime("%Y-%m-%d"),
        "licence": "ODbL-1.0",
        "attribution": [
            "Contains data from the National Land Survey of Finland "
            "Topographic Database 04/2025, CC BY 4.0",
            "Contains aviation obstacle data from Traficom / Fintraffic AIS Finland",
            "© OpenStreetMap contributors, ODbL",
        ],
        "n": len(objs),
        "objects": objs,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print("  %d objects -> objects.json (%.0f KB)"
          % (len(objs), os.path.getsize(OUT) / 1024))
    report(objs)


def report(objs):
    print()
    print("  %-12s %7s %9s %8s %7s" % ("category", "n", "w/height", "w/top", "named"))
    for cat, n in Counter(o["cat"] for o in objs).most_common():
        sel = [o for o in objs if o["cat"] == cat]
        print("  %-12s %7d %9d %8d %7d" % (
            cat, n,
            sum(1 for o in sel if o.get("height_m") is not None),
            sum(1 for o in sel if o.get("top_m") is not None),
            sum(1 for o in sel if o.get("name"))))
    print("  %-12s %7d %9d %8d %7d" % (
        "TOTAL", len(objs),
        sum(1 for o in objs if o.get("height_m") is not None),
        sum(1 for o in objs if o.get("top_m") is not None),
        sum(1 for o in objs if o.get("name"))))
    print("\n  height source: %s" % dict(Counter(o.get("src_h") for o in objs)))
    print("  provenance:    %s" % dict(Counter(o["srcs"] for o in objs).most_common(8)))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    print("cache: %s" % CACHE)
    if cmd == "fetch":
        which = sys.argv[2:] or ["mtk", "aip", "osm", "dem"]
        if "mtk" in which:
            fetch_mtk()
        if "aip" in which:
            fetch_aip()
        if "osm" in which:
            fetch_osm()
        if "dem" in which:
            fetch_dem()
    elif cmd == "build":
        build()
    elif cmd == "stats":
        if not os.path.exists(OUT):
            sys.exit("no objects.json yet -- run: python build.py build")
        with open(OUT, encoding="utf-8") as f:
            d = json.load(f)
        print("  %s, generated %s, %d objects" % (d["format"], d["generated"], d["n"]))
        report(d["objects"])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
