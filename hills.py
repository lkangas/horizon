#!/usr/bin/env python3
"""Named terrain features from MML Nimistö, for labelling the terrain silhouette.

    python hills.py fetch      # Nimistö bulk -> raw/nimisto_kohouma.json  (~2 s)
    python hills.py summits    # 10 m DEM windows -> raw/hill_summits.json (~9 min)
    python hills.py build      # -> hills.json, and a size report
    python hills.py stats      # what the filters do, step by step

A hill is NOT a point object. It does not go into objects.json and it is not
drawn as a vertical stroke: the terrain ray-caster draws the silhouette, and
what this module supplies is the name, the anchor the label hangs from, and the
elevation of that anchor. Koli is a shape, not a stick.

Everything here is Python 3 stdlib. Geometry helpers are imported from build.py
rather than copied -- `tm35_to_wgs84` in particular, because grid bearings in
TM35FIN are wrong by -6.5 to +4.1 degrees across Finland and the only safe rule
is that projected coordinates stop at the parser.

Not done here, deliberately:

  * Prominence. scaleRelevance already encodes notability -- MML's own
    cartographers ranked these, and the median elevation rises monotonically
    with the rank, 110 m at 1:25k to 538 m at 1:2M -- so the filtering this
    module needs does not require it. A national union-find flood at 10 m is
    ~11 hours and ~850 GB (PLAN.md section 3.9); at 50 m it is affordable, but
    nothing downstream is waiting on it. No record carries prom_m.

  * Massif versus summit, in general. The `open` and `claimed_by` flags DETECT
    the case and refuse to guess; they do not turn a massif name into the
    azimuth span it should be. PLAN.md section 12 item 1 stays open.

  * Homonym resolution. Nothing here looks a hill up by name, so nothing here
    can pick the wrong Halti. Every record carries `muni` and its own
    coordinates; a consumer that does look up by name must scope by one of
    them.
"""

import concurrent.futures as futures
import json
import math
import os
import re
import struct
import sys
import threading
import time
import urllib.parse
import urllib.request
import zipfile
import zlib
from collections import Counter

import build
from build import UA, get, raw, tm35_to_wgs84

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "hills.json")


# --------------------------------------------------------------------------
# Sources.
# --------------------------------------------------------------------------

# Nimistö in bulk, key-free. Three snapshots a year, each a 45.7 MB zip around
# a 1.16 GB single-line XML with 804,912 records. The free MML key is only
# needed for nightly freshness through the OGC API, which this does not need:
# a place name changes on a timescale of decades.
#
# Scrape the index rather than hard-coding places_2026_05.zip -- a hard-coded
# snapshot keeps working forever while quietly serving stale data, the same
# failure the AIP index scrape in build.py avoids.
NIMISTO_INDEX = "https://kartat.kapsi.fi/files/nimisto_oapif/places/etrs89/gml/"

# 1010210 "Kohouma" is where the classification stops. Its own description
# reads "tunturi, vaara, mäki, harju tms." -- there is no code for the
# sub-kinds, so KIND below has to read them off the name. 1010205 is
# "Kohoumaryhmä", a named group of hills (Pallastunturit, Salpausselkä).
PLACE_HILL = "1010210"
PLACE_HILL_GROUP = "1010205"

# GeoCubes km10: the MML 10 m elevation model, N2000, keyless, same host
# build.py already uses for the 100 m national DEM and the nDSM. A 330 m
# window comes back as a 33x33 float32 GeoTIFF in ~5 KB.
KM10_CLIP = ("https://vm0160.kaj.pouta.csc.fi/geocubes/clip/10/km10/"
             "bbox:%d,%d,%d,%d/2018")
KM10_CELL = 10.0

# Search radius for the summit snap. Measured over 120 sampled southern hills
# at r=160 m: the DEM maximum is a median 1.9 m above the name point, p90
# +14.0 m. Widening to 500 m raises the median gain to 10 m but the distance to
# that maximum pins itself to the search radius, which means the search has
# walked onto a neighbouring hill -- see SNAP_OPEN_RING below.
SNAP_R = 150.0

# If the argmax lands in the outermost ring of the window, the ground was still
# rising when the window ran out, so the summit is outside it and moving the
# label there would put it on a flank. Koli is the clean example: name point
# 170.5 m, max within 150 m is 234.5 m at d=149 (the boundary), max within
# 500 m is 345.3 m -- which is Ukko-Koli's summit, a different Kohouma.
SNAP_OPEN_RING = 1.5 * KM10_CELL


# --------------------------------------------------------------------------
# Sub-kind from the name suffix.
#
# There is no place-type code for it, and 88,233 Kohouma share one code. These
# 39 suffixes cover 79.5% of them; the rest get kind=None rather than a guess.
#
# saari / niemi / kari are deliberately absent even though 2,022 Kohouma end in
# -saari and 553 in -niemi: those are hills named after an island or a headland
# (a dry knoll in a bog keeps the bog's island name), and filing them as
# "island" would be a worse answer than filing them as unknown.
# --------------------------------------------------------------------------

KIND = (
    # Finnish. Counts over the 88,233 Kohouma: mäki 27,584, vuori 10,198,
    # vaara 9,884, kallio 9,486, kangas 4,718, harju 2,947, kumpu 1,453,
    # selkä 1,197, laki 683, kukkula 147, nyppylä 5, huippu 2.
    "mäki", "vuori", "vaara", "kallio", "kangas", "harju", "kumpu",
    "selkä", "laki", "kukkula", "nyppylä", "huippu",
    # Plurals, which a Kohoumaryhmä name usually takes: Kahperusvaarat,
    # Muotkatunturit, Juppurat.
    "mäet", "vuoret", "kalliot", "harjut", "vaarat", "kankaat", "tunturit",
    # Swedish: berg 249, klint 47, holm 34, backe 1.
    "berg", "backe", "klint", "ås", "holm",
    # North Sami, Inari Sami, Skolt Sami: várri 385, rova 269, oaivi 197,
    # tunturi 140, čohkka 87, kero 82, čielgi 57, duottar 9.
    "tunturi", "duottar", "várri", "váárr", "vaarâ", "oaivi", "čohkka",
    "kero", "rova", "čielgi", "gaisi", "gáisá",
)
_KINDS = sorted(KIND, key=len, reverse=True)


def kind_of(name):
    """Longest matching suffix, or None.

    Matching on the tail only, so 'Kalliomäki' resolves to mäki and never to
    kallio. 18,087 of 88,233 Kohouma (20.5%) match nothing -- 'Pukinparta',
    'Ristenummi', 'Kivilevo' -- and those keep kind=None.
    """
    n = name.lower().rstrip(".")
    for s in _KINDS:
        if n.endswith(s):
            return s
    return None


# --------------------------------------------------------------------------
# Nimistö: stream the bulk XML, keep two place types.
# --------------------------------------------------------------------------

_SEP = b"</gml:featureMember>"
_WANT = (b"<placeType>" + PLACE_HILL.encode() + b"<",
         b"<placeType>" + PLACE_HILL_GROUP.encode() + b"<")


def _tag(name, s):
    m = re.search("<%s>([^<]*)</%s>" % (name, name), s)
    return m.group(1) if m else None


def _parse_place(s):
    """One <Place> element -> a compact dict, or None if it is unusable."""
    pos = re.search(r"<gml:pos>([\d.\-]+) ([\d.\-]+)</gml:pos>", s)
    if not pos:
        return None
    names = []
    for n in re.findall(r"<Name [^>]*>(.*?)</Name>", s, re.S):
        sp = _tag("spelling", n)
        if not sp:
            continue
        names.append({
            "n": sp,
            "lang": _tag("language", n),                 # fin swe sme smn sms
            "off": _tag("languageOfficiality", n),       # 1 = official
            "dom": _tag("languageDominance", n),         # 1 = dominant locally
        })
    if not names:
        return None
    ele = _tag("placeElevation", s)
    return {
        "id": int(_tag("placeId", s)),
        "typ": _tag("placeType", s),
        "x": float(pos.group(1)),
        "y": float(pos.group(2)),
        "ele": None if ele is None else float(ele),
        "muni": _tag("municipality", s),
        "region": _tag("region", s),
        "sr": int(_tag("scaleRelevance", s) or 0),
        "names": names,
    }


def _newest_snapshot():
    page = get(NIMISTO_INDEX).decode("utf-8", "replace")
    links = re.findall(r'href="(places_\d{4}_\d{2}\.zip)"', page)
    if not links:
        sys.exit("no places_YYYY_MM.zip linked from %s" % NIMISTO_INDEX)
    name = sorted(links)[-1]
    return urllib.parse.urljoin(NIMISTO_INDEX, name), name


def fetch_nimisto(force=False):
    """Download the newest Nimistö snapshot and extract the hill place types.

    The zip is never unpacked to disk: places.xml is 1.16 GB and the 92,647
    records wanted are 11% of it by count and far less by volume, so it is read
    as a stream, split on the record separator, and pre-filtered with a
    substring test before anything is parsed. Measured: 2.2 s for the whole
    804,912-record pass, against minutes for an ElementTree walk.
    """
    dest = raw("nimisto_kohouma.json")
    if os.path.exists(dest) and not force:
        print("nimisto_kohouma.json present, skipping (delete it to refetch)")
        return

    url, name = _newest_snapshot()
    zpath = raw(name)
    if not os.path.exists(zpath):
        print("fetching %s" % name)
        t0 = time.time()
        req = urllib.request.Request(url, headers=dict(UA))
        with urllib.request.urlopen(req, timeout=900) as r, open(zpath, "wb") as f:
            n = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                n += len(chunk)
        print("  %.1f MB in %.1f s" % (n / 1e6, time.time() - t0))

    t0 = time.time()
    out, total, types = [], 0, Counter()
    with zipfile.ZipFile(zpath) as z, z.open("places.xml") as f:
        carry = b""
        while True:
            chunk = f.read(1 << 23)
            if not chunk:
                break
            parts = (carry + chunk).split(_SEP)
            carry = parts.pop()
            for p in parts:
                total += 1
                i = p.find(b"<placeType>")
                if i < 0:
                    continue
                if p[i:i + 11 + len(PLACE_HILL) + 1] not in _WANT:
                    continue
                rec = _parse_place(p.decode("utf-8"))
                if rec:
                    out.append(rec)
                    types[rec["typ"]] += 1
    print("  %d featureMembers scanned in %.1f s" % (total, time.time() - t0))
    print("  %-8s Kohouma       %6d" % (PLACE_HILL, types[PLACE_HILL]))
    print("  %-8s Kohoumaryhmä  %6d" % (PLACE_HILL_GROUP, types[PLACE_HILL_GROUP]))
    with open(dest, "w", encoding="utf-8") as f:
        json.dump({"source": name, "places": out}, f, ensure_ascii=False)
    print("  -> %s, %.1f MB" % (os.path.basename(dest),
                                os.path.getsize(dest) / 1e6))


def _places():
    path = raw("nimisto_kohouma.json")
    if not os.path.exists(path):
        sys.exit("no nimisto_kohouma.json -- run: python hills.py fetch")
    with open(path, encoding="utf-8") as f:
        return json.load(f)["places"]


# --------------------------------------------------------------------------
# Summit snap against the 10 m model.
#
# placeElevation is populated on 100% of records and is N2000 -- measured
# against km10 at the name point over 240 sampled hills, median agreement
# +0.3 m (p10 -0.5, p90 +0.9), which settles the datum question.
#
# But it is the DEM value AT THE NAME POINT, and a Finnish name point sits
# wherever the surveyor could see the hill from, which in southern forest is
# often on a flank. Hence a short snap, and a hard refusal to snap far.
# --------------------------------------------------------------------------

def _clip(x0, y0, x1, y1, timeout=120):
    """One km10 window as (values, ox, oy, W, H). Values are None at nodata.

    GeoCubes answers a 330 m clip with a tiled deflate float32 GeoTIFF, one
    256x256 tile, ~5 KB. Anything else -- an error page, a striped layout --
    raises or returns None, the caller retries, and a window that never parses
    leaves the hill on its Nimistö elevation rather than failing the build.
    """
    url = KM10_CLIP % (x0, y0, x1, y1)
    d = get(url, timeout=timeout)
    if d[:2] not in (b"II", b"MM"):
        return None
    bo = "<" if d[:2] == b"II" else ">"
    t = build._tiff_tags(d, bo, struct.unpack(bo + "I", d[4:8])[0])
    W, H = t[256][0], t[257][0]
    ox, oy = t[33922][3], t[33922][4]
    tw, th = t[322][0], t[323][0]
    nd = float(t[42113].rstrip("\x00")) if 42113 in t else -9999.0
    ntx = (W + tw - 1) // tw
    vals = [None] * (W * H)
    for ti, (off, cnt) in enumerate(zip(t[324], t[325])):
        blob = d[off:off + cnt]
        if t[259][0] in (5, 8):
            blob = zlib.decompress(blob)
        elif t[259][0] != 1:
            return None
        f = struct.unpack(bo + "f" * (len(blob) // 4), blob)
        tx0, ty0 = (ti % ntx) * tw, (ti // ntx) * th
        for r in range(th):
            yy = ty0 + r
            if yy >= H:
                break
            for c in range(tw):
                xx = tx0 + c
                if xx >= W:
                    break
                v = f[r * tw + c]
                if v != nd and -500.0 < v < 2000.0:
                    vals[yy * W + xx] = v
    return vals, ox, oy, W, H


def _summit(x, y, r=SNAP_R):
    """Highest km10 cell within r of (x, y) in TM35FIN, plus the name-point cell.

    Returns a dict, or None if the request failed. `open` is set when the
    maximum sits in the outermost ring: the ground had not stopped rising, so
    the real summit is outside the window and this point is on a flank.
    """
    pad = r + KM10_CELL
    g = _clip(int(x - pad), int(y - pad), int(x + pad), int(y + pad))
    if g is None:
        return None
    vals, ox, oy, W, H = g
    best = None
    for row in range(H):
        cy = oy - (row + 0.5) * KM10_CELL
        dy = cy - y
        if abs(dy) > r:
            continue
        base = row * W
        for col in range(W):
            v = vals[base + col]
            if v is None:
                continue
            cx = ox + (col + 0.5) * KM10_CELL
            d = math.hypot(cx - x, dy)
            if d > r:
                continue
            if best is None or v > best[0]:
                best = (v, cx, cy, d)
    col = int((x - ox) / KM10_CELL)
    row = int((oy - y) / KM10_CELL)
    v0 = vals[row * W + col] if 0 <= row < H and 0 <= col < W else None
    if best is None:
        # Every cell in the window is nodata: outside the km10 land mask, which
        # happens along the Norwegian border. Halti's own name point reads
        # nodata and is rescued by the 25 m-away maximum; a window with nothing
        # in it at all falls back to placeElevation in load_hills().
        return {"pt": None if v0 is None else round(v0, 1), "top": None}
    return {
        "pt": None if v0 is None else round(v0, 1),
        "top": round(best[0], 1),
        "x": round(best[1], 1),
        "y": round(best[2], 1),
        "d": round(best[3], 1),
        "open": best[3] > r - SNAP_OPEN_RING,
    }


def fetch_summits(min_scale=100000, ids=None, workers=16, force=False):
    """Sample km10 around every hill at or above `min_scale`, plus `ids`.

    Cached by placeId, so an interrupted run resumes and a re-run at a lower
    min_scale only fetches what is new. One window is ~5 KB on the wire and the
    host answered 60 a second at 16 workers, so the default tier
    (scaleRelevance >= 100,000: 18,820 places) cost 95 MB and 5.1 minutes.
    """
    ids = set(ids or ())
    places = _places()
    todo_all = [p for p in places if p["sr"] >= min_scale or p["id"] in ids]
    dest = raw("hill_summits.json")
    done = {}
    if os.path.exists(dest) and not force:
        with open(dest, encoding="utf-8") as f:
            done = json.load(f)
    todo = [p for p in todo_all if str(p["id"]) not in done]
    print("  %d places at scaleRelevance >= %d%s, %d cached, %d to sample"
          % (len(todo_all), min_scale,
             " plus %d named claimants" % len(ids) if ids else "",
             len(done), len(todo)))
    if not todo:
        return

    lock = threading.Lock()
    n = [0]
    t0 = time.time()

    def work(p):
        s = None
        for attempt in range(3):
            try:
                s = _summit(p["x"], p["y"])
                break
            except Exception:
                time.sleep(1.5 * (attempt + 1))
        with lock:
            if s is not None:
                done[str(p["id"])] = s
            n[0] += 1
            if n[0] % 1000 == 0:
                print("    %d / %d  (%.0f/s)"
                      % (n[0], len(todo), n[0] / (time.time() - t0)), flush=True)
                with open(dest, "w", encoding="utf-8") as f:
                    json.dump(done, f)

    with futures.ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, todo))
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(done, f)
    print("  %d sampled in %.0f s, %.1f MB cached"
          % (len(done), time.time() - t0, os.path.getsize(dest) / 1e6))


# --------------------------------------------------------------------------
# Second pass: the hills the first pass refused.
#
# 22% of southern hills and 12% of northern ones come back `open` -- the ground
# was still rising at 150 m. Some of those are massif names whose summit
# belongs to a neighbour and must stay where they are; the rest are ordinary
# hills whose name point simply sits further down the flank than 150 m.
#
# PLAN.md section 12 proposes the discriminator and it holds up: a Kohouma
# whose maximum is closer to ANOTHER Kohouma's name point than to its own is
# naming the massif, not the summit. Measured over the 202 open records at
# scaleRelevance >= 500,000, a 500 m re-search rescues 123 and the claim rule
# refuses 19, among them exactly the two cases PLAN.md names:
#
#   Koli          -> maximum 345 m, 384 m away, but 26 m from Ukko-Koli
#   Pallastunturi -> maximum 809 m, 187 m away, but 62 m from Taivaskero
#
# The remaining 60 are still rising at 500 m and are left alone.
# --------------------------------------------------------------------------

WIDE_R = 500.0


class _Index:
    """1 km spatial hash over every Nimistö name point, for the claim test."""

    def __init__(self, places):
        self.g = {}
        for p in places:
            self.g.setdefault((int(p["x"] // 1000), int(p["y"] // 1000)), []).append(p)

    def near(self, x, y, r):
        out = []
        for cx in range(int((x - r) // 1000), int((x + r) // 1000) + 1):
            for cy in range(int((y - r) // 1000), int((y + r) // 1000) + 1):
                out += self.g.get((cx, cy), [])
        return out

    def claimant(self, x, y, own_d, own_id):
        """The nearest other name point to (x, y), if it is nearer than own_d."""
        best = None
        for q in self.near(x, y, own_d):
            if q["id"] == own_id:
                continue
            d = math.hypot(x - q["x"], y - q["y"])
            if d < own_d and (best is None or d < best[1]):
                best = (q, d)
        return best


def fetch_summits_wide(min_scale=100000, workers=16):
    """Re-search the `open` hills at 500 m and keep the ones nothing else claims.

    Writes back into hill_summits.json under the same placeId key, with
    `wide` set, so load_hills() needs no extra file. A 1,020 m window is
    ~35 KB on the wire against ~5 KB for the 330 m one, but it only runs on the
    ~20% the first pass refused.
    """
    places = _places()
    dest = raw("hill_summits.json")
    if not os.path.exists(dest):
        sys.exit("no hill_summits.json -- run: python hills.py summits")
    with open(dest, encoding="utf-8") as f:
        done = json.load(f)
    idx = _Index(places)
    todo = [p for p in places
            if p["sr"] >= min_scale
            and (done.get(str(p["id"])) or {}).get("open")
            and "wide" not in (done.get(str(p["id"])) or {})]
    print("  %d open records to re-search at %d m" % (len(todo), WIDE_R))
    if not todo:
        return

    lock = threading.Lock()
    n = [0]
    stat = Counter()
    t0 = time.time()

    def work(p):
        s = None
        for attempt in range(3):
            try:
                s = _summit(p["x"], p["y"], WIDE_R)
                break
            except Exception:
                time.sleep(1.5 * (attempt + 1))
        key = str(p["id"])
        with lock:
            n[0] += 1
            rec = done[key]
            rec["wide"] = True
            if s is None or s.get("top") is None:
                stat["failed"] += 1
            elif s["open"]:
                stat["still open at %d m" % WIDE_R] += 1
            else:
                rival = idx.claimant(s["x"], s["y"],
                                     math.hypot(s["x"] - p["x"], s["y"] - p["y"]),
                                     p["id"])
                if rival:
                    stat["claimed by a neighbouring name"] += 1
                    rec["claimed"] = rival[0]["id"]
                else:
                    stat["rescued"] += 1
                    rec.update(top=s["top"], x=s["x"], y=s["y"], d=s["d"],
                               open=False)
            if n[0] % 500 == 0:
                print("    %d / %d" % (n[0], len(todo)), flush=True)
                with open(dest, "w", encoding="utf-8") as f:
                    json.dump(done, f)

    with futures.ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, todo))
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(done, f)
    print("  %.0f s" % (time.time() - t0))
    for k, v in stat.most_common():
        print("    %-32s %6d" % (k, v))


def claimants():
    """placeIds that some hill's maximum belongs to, from hill_summits.json.

    Ukko-Koli, which owns Koli's summit, has scaleRelevance 25,000 -- the
    LOWEST rank there is -- while Koli itself has the highest. So the claimant
    is routinely outside the published tier, and load_hills() pulls it back in
    rather than emitting a dangling claimed_by.
    """
    path = raw("hill_summits.json")
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {s["claimed"] for s in json.load(f).values() if s.get("claimed")}


def fetch_hills(min_scale=100000, snap=True, workers=16, force=False):
    """Everything the build needs: the Nimistö extract, then the snap passes.

    Three passes, because the third depends on the second: sample at 150 m,
    re-search what came back open at 500 m, then sample the neighbours that
    turned out to own those summits.
    """
    fetch_nimisto(force=force)
    if snap:
        fetch_summits(min_scale=min_scale, workers=workers, force=force)
        fetch_summits_wide(min_scale=min_scale, workers=workers)
        fetch_summits(min_scale=min_scale, ids=claimants(), workers=workers)


# --------------------------------------------------------------------------
# Assemble.
# --------------------------------------------------------------------------

def _name_fields(names):
    """Primary spelling plus every parallel, Swedish and Sami kept.

    Nimistö carries 7,342 Swedish, 1,826 North Sami, 800 Inari Sami and 99
    Skolt Sami spellings over these place types, and some fells carry four at
    once (Bállasduottar / Pallastunturi). The primary is the locally dominant
    official one, which in Enontekiö and Utsjoki is often the Sami spelling and
    should be; ties go to Finnish, because that is what the rest of the
    catalogue is in.

    Returns (primary, [every spelling in rank order]).
    """
    def rank(nm):
        return (nm["dom"] != "1", nm["off"] != "1", nm["lang"] != "fin")
    ordered = sorted(names, key=rank)
    return ordered[0]["n"], [{"n": m["n"], "lang": m["lang"]} for m in ordered]


def load_hills(min_scale=100000, min_top_m=None, groups=True, verbose=False):
    """Named terrain features, ready to attach to the terrain silhouette.

    Each record. Fields marked (opt) are omitted when they would be null or
    false, which is most of them on most records and is worth about 25% of the
    payload:

        id          Nimistö placeId. Stable across snapshots; the join key.
        cat         "hill" (Kohouma) or "hillgroup" (Kohoumaryhmä).
        lat, lon    THE LABEL ANCHOR. The snapped summit where the snap was
                    accepted, the Nimistö name point everywhere else.
        top_m       N2000 elevation of that anchor.
        name        primary spelling: the locally dominant official one.
        muni        municipality code -- the scope that disambiguates homonyms.
                    `Halti` is both a 1,326 m fell in 047 Enontekiö and a 66 m
                    hill in 755; `Koli` occurs six times.
        rank        scaleRelevance, MML's own notability ranking.
        src_top     "dem10" (a km10 cell) or "nimisto" (placeElevation).
        kind  (opt) mäki / vaara / tunturi / ... read off the name suffix.
        names (opt) the OTHER spellings, [{n, lang}], Swedish and Sami kept.
        name_lat, name_lon (opt)
                    the Nimistö name point, present only when the anchor moved
                    away from it, so a consumer that distrusts the snap can go
                    back.
        snap_m (opt) metres the anchor moved.
        gain_m (opt) top_m minus km10 at the name point (placeElevation where
                    km10 is nodata there, as at Halti).
        wide  (opt) the anchor came from the 500 m second pass, not the 150 m
                    first pass. A weaker result: trust it less.
        open  (opt) no summit was accepted. The ground was still rising at the
                    search boundary, so the name point is on a flank or the
                    name is a massif name. The anchor is the name point and
                    nothing was moved.
        claimed_by (opt)
                    on an `open` record, the placeId of the Kohouma whose name
                    point is nearer the maximum than this one's. That is the
                    massif signature: Koli carries claimed_by Ukko-Koli.

    There is deliberately no height_m and no top-of-structure: a hill's
    silhouette comes from the ray-caster, and this is the label that goes on it.
    There is no prom_m either -- see the module notes on prominence.
    """
    places = _places()
    snaps = {}
    path = raw("hill_summits.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            snaps = json.load(f)

    steps = []
    sel = places
    steps.append(("all Kohouma + Kohoumaryhmä", len(sel)))
    if not groups:
        sel = [p for p in sel if p["typ"] == PLACE_HILL]
        steps.append(("Kohouma only", len(sel)))
    sel = [p for p in sel if p["sr"] >= min_scale]
    steps.append(("scaleRelevance >= %d" % min_scale, len(sel)))
    # Pull in the hills that own a selected hill's summit even when their own
    # rank is below the tier: Ukko-Koli, which owns Koli's, ranks 25,000 while
    # Koli ranks 2,000,000. Without this, claimed_by dangles and the 345 m
    # summit a visitor actually sees is missing while the 169 m name is there.
    keep = {snaps[str(p["id"])]["claimed"]
            for p in sel
            if (snaps.get(str(p["id"])) or {}).get("claimed")}
    have = {p["id"] for p in sel}
    extra = [p for p in places if p["id"] in keep and p["id"] not in have]
    sel = sel + extra
    steps.append(("  plus claimants below the tier", len(sel)))

    out, snapped, opened, nosnap, claimed, wide = [], 0, 0, 0, 0, 0
    for p in sel:
        lat, lon = tm35_to_wgs84(p["x"], p["y"])
        s = snaps.get(str(p["id"])) or {}
        top = s.get("top")
        pt = s.get("pt")
        if pt is None:
            pt = p["ele"]                      # km10 nodata at the name point
        rec = {
            "id": p["id"],
            "cat": "hill" if p["typ"] == PLACE_HILL else "hillgroup",
            "kind": None,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "name_lat": round(lat, 6),
            "name_lon": round(lon, 6),
            "top_m": p["ele"],
            "muni": p["muni"],
            "rank": p["sr"],
            "snap_m": None,
            "gain_m": None,
            "open": False,
            "src_top": "nimisto",
        }
        if top is None:
            nosnap += 1
        elif s.get("open"):
            # Refused. Keep the name point and the name point's own elevation:
            # the maximum found belongs to ground the window did not contain,
            # and at Koli that ground is Ukko-Koli.
            opened += 1
            rec["open"] = True
            rec["top_m"] = pt
            rec["src_top"] = "dem10"
            if s.get("claimed"):
                rec["claimed_by"] = s["claimed"]
                claimed += 1
        else:
            slat, slon = tm35_to_wgs84(s["x"], s["y"])
            rec["lat"] = round(slat, 6)
            rec["lon"] = round(slon, 6)
            rec["top_m"] = top
            rec["snap_m"] = s["d"]
            rec["gain_m"] = None if pt is None else round(top - pt, 1)
            rec["src_top"] = "dem10"
            snapped += 1
            if s.get("wide"):
                # Rescued by the 500 m second pass, a weaker rule than the
                # 150 m one: the maximum is real but further from the name.
                rec["wide"] = True
                wide += 1
        rec["name"], names = _name_fields(p["names"])
        rec["kind"] = kind_of(rec["name"])
        # Only the parallels. 7,342 Swedish and 2,725 Sami spellings are worth
        # carrying; 84,469 copies of the Finnish name already in `name` are not.
        if len(names) > 1:
            rec["names"] = names[1:]
        if rec["snap_m"] is None:
            # The anchor IS the name point; two more coordinate pairs per
            # record would be 40 bytes of nothing.
            del rec["name_lat"], rec["name_lon"]
        for k in ("kind", "snap_m", "gain_m"):
            if rec[k] is None:
                del rec[k]
        if not rec["open"]:
            del rec["open"]
        out.append(rec)

    if min_top_m is not None:
        out = [r for r in out if r["top_m"] is not None and r["top_m"] >= min_top_m]
        steps.append(("top_m >= %g m" % min_top_m, len(out)))
    # placeId order, so the promoted claimants do not land in a clump at the
    # end and two runs of the same tier produce byte-identical output.
    out.sort(key=lambda r: r["id"])

    if verbose:
        for label, n in steps:
            print("  %-32s %6d" % (label, n))
        print("  %-32s %6d  (median move %.0f m)"
              % ("snapped to a km10 maximum", snapped,
                 _median([r.get("snap_m") for r in out]) or 0.0))
        print("  %-32s %6d  (the rest came from the 150 m pass)"
              % ("  of those, by the 500 m pass", wide))
        print("  %-32s %6d  (%.0f%%)  anchor left at the name point"
              % ("open: no summit accepted", opened,
                 100.0 * opened / max(1, len(sel))))
        print("  %-32s %6d  massif names: the maximum is nearer another"
              % ("  of those, claimed", claimed))
        if nosnap:
            print("  %-32s %6d  (elevation from Nimistö)"
                  % ("not sampled / no DEM cover", nosnap))
        _collisions(out)
    return out


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    return xs[len(xs) // 2] if xs else None


def _collisions(recs):
    """Count anchors that landed on the same km10 cell as another hill's.

    This is the massif failure showing itself: two Kohouma whose snaps converge
    are one summit with two names. They are reported, not merged -- merging
    would delete the distinction between Bállasduottar (783 m) and Taivaskero
    (806 m), which are 183 m apart and genuinely two names for two summits of
    one fell.
    """
    cells = {}
    for r in recs:
        k = (round(r["lat"], 4), round(r["lon"], 4))
        cells.setdefault(k, []).append(r)
    dup = [v for v in cells.values() if len(v) > 1]
    if dup:
        print("  %-32s %6d  (%d anchors)"
              % ("anchors sharing a cell", len(dup), sum(len(v) for v in dup)))
    return dup


# --------------------------------------------------------------------------
# CLI.
# --------------------------------------------------------------------------

def _size(recs):
    blob = json.dumps(recs, ensure_ascii=False, separators=(",", ":")).encode()
    return len(blob), len(zlib.compress(blob, 9))


def stats():
    places = _places()
    koh = [p for p in places if p["typ"] == PLACE_HILL]
    grp = [p for p in places if p["typ"] == PLACE_HILL_GROUP]
    print("Kohouma %d, Kohoumaryhmä %d" % (len(koh), len(grp)))

    print("\nscaleRelevance, cumulative over Kohouma:")
    c = Counter(p["sr"] for p in koh)
    cum = 0
    for k in sorted(c, reverse=True):
        cum += c[k]
        sub = [p["ele"] for p in koh if p["sr"] >= k]
        print("  >= 1:%-9d %6d   median elevation %4.0f m" % (k, cum, _median(sub)))

    print("\nsub-kind from the name suffix (Kohouma):")
    k = Counter(kind_of(_name_fields(p["names"])[0]) for p in koh)
    for name, n in k.most_common(16):
        print("  %-10s %6d" % (name or "(none)", n))

    print("\nname languages, all records:")
    for lang, n in Counter(nm["lang"] for p in places for nm in p["names"]).most_common():
        print("  %-5s %6d" % (lang, n))

    print("\npayload by tier (raw / deflate):")
    for tier in (2000000, 1000000, 500000, 250000, 100000, 50000):
        recs = load_hills(min_scale=tier)
        a, b = _size(recs)
        print("  >= 1:%-9d %6d records  %8.0f KB  %8.0f KB gz"
              % (tier, len(recs), a / 1024.0, b / 1024.0))


def build_json(min_scale=100000):
    recs = load_hills(min_scale=min_scale, verbose=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"source": "MML Nimistö + MML km10 (CC BY 4.0)",
                   "min_scale": min_scale,
                   "hills": recs}, f, ensure_ascii=False, separators=(",", ":"))
    a, b = _size(recs)
    print("  -> %s  %d records, %.0f KB raw, %.0f KB deflate"
          % (os.path.basename(OUT), len(recs), a / 1024.0, b / 1024.0))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "fetch":
        fetch_nimisto()
    elif cmd == "summits":
        fetch_summits()
    elif cmd == "all":
        fetch_hills()
        build_json()
    elif cmd == "build":
        build_json()
    elif cmd == "stats":
        stats()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
