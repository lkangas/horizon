#!/usr/bin/env python3
"""Terrain tiles for the client ray-caster, plus the observer's own ground.

    python terrain.py                       # default region (Kaivopuisto), all rings
    python terrain.py --lat 61.0 --lon 25.5 # somewhere else
    python terrain.py --rings 2             # only the two inner rings
    python terrain.py --ground 60.1567 24.9560

Pure stdlib. Tiles land in $AZIMUTH_CACHE/terrain/, which serve.py already
serves at /terrain/.


THE TILE FORMAT -- "AZT1"
=========================

One tile is one file, `terrain/<cell_m>/<x>_<y>.azt`. Fixed 36-byte header in
plain bytes, then one deflate stream. A browser needs DataView plus
DecompressionStream('deflate') and nothing else.

    off  size  type     field
      0     4  char[4]  magic, ASCII "AZT1"
      4     2  uint16   header_bytes -- 36 here; skip this many to reach the
                        payload, so a later version can add fields without
                        breaking a reader that ignores them
      6     1  uint8    value_type   -- 1 = int16
      7     1  uint8    predictor    -- 2 = horizontal delta (see below)
      8     4  int32    origin_e     -- TM35FIN easting, WEST edge of column 0
     12     4  int32    origin_n     -- TM35FIN northing, NORTH edge of row 0
     16     2  uint16   cell_m       -- cell size in metres, square
     18     2  uint16   width        -- columns
     20     2  uint16   height       -- rows
     22     2  int16    scale        -- metres = stored / scale; 1 here
     24     2  int16    nodata       -- -32768
     26     1  uint8    compression  -- 1 = deflate, RFC 1950 (zlib wrapper)
     27     1  uint8    flags        -- bit0: values are a max over a finer
                                        grid; bit1: the tile contains nodata
     28     4  uint32   payload_bytes -- compressed length that follows
     32     2  int16    min_m        -- lowest real value in the tile
     34     2  int16    max_m        -- highest real value in the tile
     36   ...           the deflate stream

min_m/max_m are there for r.horizon's block-max early-out (PLAN.md 5.2): a
ray that already has tan(alpha) above what max_m can reach at that distance
can skip the whole tile without decoding it, and index.json repeats both so
the skip can happen before the fetch.

Every multi-byte header field is LITTLE-ENDIAN, and so are the int16 samples.
That is the byte order of every platform the page runs on; a reader that wants
to be strict should use DataView.getInt16(i, true) rather than Int16Array.

The stream inflates to width*height int16 values, row-major, rows running
NORTH to SOUTH and columns WEST to EAST -- raster order, the same order GDAL
and every GeoTIFF use, so a tile can be eyeballed as an image without
flipping.

CRS is EPSG:3067 (ETRS-TM35FIN) and heights are metres in N2000, both
inherited from the source and neither of them negotiable per tile. The centre
of cell (col, row) is

    E = origin_e + (col + 0.5) * cell_m
    N = origin_n - (row + 0.5) * cell_m

The grid is anchored at GeoCubes' own origin (0, 7800000) and steps by
cell_m * width, so origin_e = tx * step and origin_n = 7800000 - ty * step for
integer tx, ty -- which is the whole point: two observers in the same town ask
for the same tile names and the cache is shared.

PREDICTOR 2 is a per-row horizontal delta, exactly TIFF's predictor 2: the
stored value is the difference from the previous sample in the same row, the
first sample in a row differencing against 0, arithmetic wrapping in int16.
Reconstruct with wraparound or the nodata sentinel will corrupt its neighbour:

    let p = 0;
    for (let c = 0; c < w; c++) { p = (p + v[b + c]) << 16 >> 16; v[b + c] = p; }

NODATA is -32768 and means the national laser model does not cover the cell.
It is NOT sea. Finnish coastal water is surveyed and reads a real 0.0-0.1 m
(a 10x10 km Turku archipelago block is 0.0% nodata), so nodata is only two
things: open sea past the survey edge, and foreign soil. A ray-caster should
treat it as 0 m N2000 -- right for the sea, and over Sweden or Norway it draws
no terrain instead of the 10 km trench that -9999 would carve. Never
interpolate across it.

A TILE THAT IS ENTIRELY NODATA IS NOT WRITTEN. Over the open Gulf of Finland
that is most of the southern rings. The index lists what exists; a tile absent
from the index is all nodata, and the client should not request it.

terrain/index.json is the client's entry point:

    {"format": "AZT1", "crs": "EPSG:3067", "vdatum": "N2000",
     "origin": [0, 7800000], "rings": [[12, 10], [35, 20], [60, 50], [90, 100]],
     "tile_px": {"10": 512, ...},
     "tiles": {"10": {"75_220": [41594, -8, 32], ...}, "20": {...}, ...}}

`rings` is [outer_radius_km, cell_m] in increasing radius; a sample at
distance d belongs to the first ring whose outer radius exceeds d. `tiles`
maps cell size -> "x_y" -> [bytes on disk, min_m, max_m].


WHY THESE RINGS
===============

Resolution finer than the ray spacing is wasted. At 0.1 deg the rays are
d * 1.745e-3 metres apart -- 17 m at 10 km, 61 m at 35 km, 157 m at 90 km --
so the ring boundaries are placed where the cell size stops being the finer of
the two:

    ring     cells    ray spacing at the outer edge    cells per sample
    0-12 km   10 m    20.9 m                           2.1
    12-35     20 m    61.1 m                           3.1
    35-60     50 m    104.7 m                          2.1
    60-90    100 m    157.1 m                          1.6

Ninety kilometres is the outer edge because that is where the geometry runs
out, not the data: with k = 0.13 refraction the drop at 90 km is 553 m, and
outside Lapland nothing in Finland reaches 350 m N2000. It also matches the
object-visibility ceiling in PLAN.md 2 -- 90.2 km to the tallest mast from a
30 m eye height. A Lapland observer is the exception -- Halti at 1,324 m
clears the drop out to 139 km -- so pass rings=RINGS + ((140, 100),) up there;
everything below is parameterised, nothing is baked in.

Measured, both runs on a cold cache:

    Kaivopuisto (coastal)              Tiirismaa (inland, hilly)
    ring   tiles  MB ship  MB fetch    tiles  MB ship  MB fetch
    10 m      25     0.92      43.2       29     1.85      85.3
    20 m      51     2.57      24.3       52     4.54      41.4
    50 m      73     1.39       9.1       75     2.31      12.2
    100 m     39     0.92       5.4       44     1.61       6.6
    total    188     5.79      82.0      200    10.32     145.5
    wall                      16.8 s                     19.3 s

SO AN OBSERVER DOWNLOADS 5.8 MB on the coast and 10.3 MB inland -- 4.9 and
8.7 MB with the 100 m ring dropped, which PLAN.md 5.2 says it can be below a
50 m eye height. The GeoCubes fetch is the build machine's problem, not the
phone's, and it happens once: a second run over the same cache fetches 0 MB
and finishes in 1.8 s.

Helsinki ships less than Lahti because 41 of its 188 tiles are open Gulf of
Finland and are never written at all (spot-checked: every one of them decodes
to 0 live cells out of 65,536).

RESAMPLING. GeoCubes' stored resolution levels are AVERAGE-resampled. Checked
against the 2 m source over 8x8 km at Nuuksio, its 10 m level differs from the
block average by a mean of +0.0001 m -- it is the average. Averaging shaves
ridge crests, and PLAN.md 3.6 is blunt about what that costs: the horizon
comes out low, so the page claims visibility through hills. Ray-casting 360
azimuths from a 93 m hilltop out to 3.8 km, against the 2 m model as truth:

    10 m grid built by          mean error   p50 |err|   p90 |err|
    GeoCubes average            -0.1768 deg     0.0840      0.6878
    max-pool 2 m -> 10 m        +0.2109         0.0919      0.6701
    max-pool 5 m -> 10 m        +0.0593         0.0585      0.4252

So ring 0 fetches the 5 m level and max-pools 2x2. It beats both the server's
average and a true 2 m max-pool on absolute error, and its residual bias is
upward, which hides things rather than inventing them.

The outer rings take the server's level as it comes, because there the same
shave is already below the noise. Max-pool minus server average, and what the
mean of that is worth in angle at the ring's INNER edge, where it matters most:

    ring        mean shave   at inner edge
    20 m  @12 km   0.728 m      0.0035 deg
    50 m  @35 km   1.976 m      0.0032 deg
    100 m @60 km   2.687 m      0.0026 deg

All well under the 0.0134 deg that choosing 10 m over 2 m costs in the first
place. Refining ring 1 the way ring 0 is refined would roughly quadruple its
fetch -- another 120 MB at the inland test point -- to buy 0.008 deg at p90.
It is not worth it, but REFINE below is the one line to change if you
disagree.
"""

import argparse
import concurrent.futures as futures
import json
import math
import os
import struct
import sys
import threading
import time
import zlib
from array import array

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build import CACHE, RAW, UA, _tiff_tags, get, wgs84_to_tm35   # noqa: E402

TERRAIN = os.path.join(CACHE, "terrain")
INDEX = os.path.join(TERRAIN, "index.json")

MAGIC = b"AZT1"
HDR = 36
HFMT = "<4sHBBiiHHHhhBBIhh"
NODATA = -32768
SCALE = 1                      # stored int16 is metres; see the docstring

# GeoCubes' own grid anchor, so tiles are shared between observers.
GRID_E0 = 0
GRID_N0 = 7800000

# The cube's national extent. build.py's whole-Finland clip uses
# 50000,6600000 - 760000,7800000; this is that, rounded outward to the nearest
# 100 km block boundary, which is how GeoCubes stores it.
CUBE = (0, 6600000, 800000, 7800000)

CLIP = ("https://vm0160.kaj.pouta.csc.fi/geocubes/clip/%d/%s/"
        "bbox:%d,%d,%d,%d/%d")
LAYER = "km2"
YEAR = 2022

# (outer radius km, cell size m). See WHY THESE RINGS.
RINGS = ((12, 10), (35, 20), (60, 50), (90, 100))

# Tile edge in cells, per cell size. Bigger tiles mean fewer requests and more
# waste at the rim: a 90 km disc tiled at 51.2 km fetches 2.2x its own area,
# at 25.6 km only 1.35x. These are the sizes where the two stop trading well.
TILE_PX = {10: 512, 20: 512, 50: 256, 100: 256}

# cell size -> the finer GeoCubes level to fetch and max-pool from.
REFINE = {10: 5}

# GeoCubes resolution levels. Asking for anything else silently gives you one
# of these, so an unlisted value is a bug, not a fallback.
LEVELS = (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000)


# --------------------------------------------------------------------------
# The tile grid.
# --------------------------------------------------------------------------

def tile_step(cell_m):
    return cell_m * TILE_PX[cell_m]


def tile_bbox(cell_m, tx, ty):
    """(xmin, ymin, xmax, ymax) in TM35FIN for tile (tx, ty)."""
    s = tile_step(cell_m)
    x0 = GRID_E0 + tx * s
    y1 = GRID_N0 - ty * s
    return x0, y1 - s, x0 + s, y1


def tiles_for(cell_m, e, n, r_outer_m, r_inner_m=0.0):
    """Tiles whose square meets the disc of r_outer and is not swallowed by r_inner.

    The inner test is against the tile's farthest corner: a tile entirely
    inside the previous ring is already covered at a finer cell size, and
    shipping it twice is pure waste.
    """
    s = float(tile_step(cell_m))
    tx0 = int(math.floor((e - r_outer_m - GRID_E0) / s))
    tx1 = int(math.floor((e + r_outer_m - GRID_E0) / s))
    ty0 = int(math.floor((GRID_N0 - (n + r_outer_m)) / s))
    ty1 = int(math.floor((GRID_N0 - (n - r_outer_m)) / s))
    out = []
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            x0, y0, x1, y1 = tile_bbox(cell_m, tx, ty)
            if x1 <= CUBE[0] or x0 >= CUBE[2] or y1 <= CUBE[1] or y0 >= CUBE[3]:
                continue
            # nearest point of the square to the observer
            dx = max(x0 - e, 0.0, e - x1)
            dy = max(y0 - n, 0.0, n - y1)
            if dx * dx + dy * dy > r_outer_m * r_outer_m:
                continue
            if r_inner_m > 0:
                fx = max(abs(e - x0), abs(e - x1))
                fy = max(abs(n - y0), abs(n - y1))
                if fx * fx + fy * fy <= r_inner_m * r_inner_m:
                    continue
            out.append((tx, ty))
    return out


def tile_path(cell_m, tx, ty):
    return os.path.join(TERRAIN, str(cell_m), "%d_%d.azt" % (tx, ty))


# --------------------------------------------------------------------------
# GeoTIFF in, int16 out.
#
# The reader is build.py's sample_dem loop with the object bucketing taken out
# and array('f') in place of a list: a 1024x1024 Float32 clip is 1 M cells, and
# a Python list of floats for that is 40 MB of boxed objects against 4 MB here.
# --------------------------------------------------------------------------

def read_float_tiff(d):
    """Decode a tiled or stripped deflate Float32 GeoTIFF into one flat array."""
    bo = "<" if d[:2] == b"II" else ">"
    t = _tiff_tags(d, bo, struct.unpack(bo + "I", d[4:8])[0])
    W, H = t[256][0], t[257][0]
    if t.get(258, [32])[0] != 32 or t.get(339, [3])[0] != 3:
        raise ValueError("expected Float32, got bits=%s fmt=%s"
                         % (t.get(258), t.get(339)))
    comp = t[259][0]
    px, py = t[33550][0], t[33550][1]
    if px != py:
        raise ValueError("non-square cells %g x %g" % (px, py))
    ox, oy = t[33922][3], t[33922][4]
    nd = float(t[42113].rstrip("\x00")) if 42113 in t else -9999.0
    g = array("f", [nd]) * (W * H)

    if 322 in t:
        tw, th = t[322][0], t[323][0]
        offs, cnts = t[324], t[325]
        ntx = (W + tw - 1) // tw
        for i in range(len(offs)):
            blob = d[offs[i]:offs[i] + cnts[i]]
            if comp in (5, 8):
                blob = zlib.decompress(blob)
            elif comp != 1:
                raise ValueError("compression %d" % comp)
            v = array("f")
            v.frombytes(blob)
            if bo == ">":
                v.byteswap()
            x0, y0 = (i % ntx) * tw, (i // ntx) * th
            w = min(tw, W - x0)
            for r in range(min(th, H - y0)):
                p = (y0 + r) * W + x0
                g[p:p + w] = v[r * tw:r * tw + w]
    else:
        offs, cnts = t[273], t[279]
        row = 0
        for i in range(len(offs)):
            blob = d[offs[i]:offs[i] + cnts[i]]
            if comp in (5, 8):
                blob = zlib.decompress(blob)
            elif comp != 1:
                raise ValueError("compression %d" % comp)
            v = array("f")
            v.frombytes(blob)
            if bo == ">":
                v.byteswap()
            n = len(v) // W
            g[row * W:(row + n) * W] = v[:n * W]
            row += n
    return g, W, H, px, ox, oy, nd


def maxpool(g, W, H, f):
    """Max-pool by an integer factor, ignoring the -9999 that means nodata.

    map(max, ...) rather than nested indexing because this runs on a million
    cells per tile: rows first, then columns, is two C-level passes instead of
    f*f Python ones.
    """
    if f == 1:
        return g, W, H
    w, h = W // f, H // f
    out = array("f", [0.0]) * (w * h)
    for r in range(h):
        b = r * f
        row = g[b * W:(b + 1) * W]
        for i in range(1, f):
            row = array("f", map(max, row, g[(b + i) * W:(b + i + 1) * W]))
        m = row[0::f]
        for j in range(1, f):
            m = array("f", map(max, m, row[j::f]))
        out[r * w:(r + 1) * w] = m[:w]
    return out, w, h


def encode_tile(g, W, H, origin_e, origin_n, cell_m, pooled, src_nodata=-9999.0):
    """Float array -> one AZT1 file. Returns (bytes, all_nodata)."""
    a = array("h", bytes(2 * W * H))
    live = 0
    lo, hi = 32767, -32767
    for i in range(W * H):
        v = g[i]
        if v <= src_nodata + 1.0:
            a[i] = NODATA
        else:
            live += 1
            x = int(round(v * SCALE))
            x = 32767 if x > 32767 else (-32767 if x < -32767 else x)
            a[i] = x
            if x < lo:
                lo = x
            if x > hi:
                hi = x
    if not live:
        return b"", True

    d = array("h", bytes(2 * W * H))
    for r in range(H):
        b = r * W
        prev = 0
        for c in range(b, b + W):
            v = a[c]
            x = (v - prev) & 0xFFFF
            d[c] = x - 65536 if x > 32767 else x
            prev = v
    if sys.byteorder == "big":
        d.byteswap()
    body = zlib.compress(d.tobytes(), 9)

    flags = (1 if pooled else 0) | (2 if live < W * H else 0)
    hdr = struct.pack(HFMT, MAGIC, HDR, 1, 2,
                      int(origin_e), int(origin_n), cell_m, W, H,
                      SCALE, NODATA, 1, flags, len(body), lo, hi)
    assert len(hdr) == HDR, len(hdr)
    return hdr + body, False


def tile_meta(blob):
    """Header only. write_index reads 36 bytes per file instead of decoding."""
    (magic, hdr, vtype, pred, oe, on, cell, W, H,
     scale, nd, comp, flags, plen, lo, hi) = struct.unpack(HFMT, blob[:HDR])
    if magic != MAGIC:
        raise ValueError("not an AZT1 tile")
    return dict(hdr=hdr, vtype=vtype, pred=pred, origin_e=oe, origin_n=on,
                cell_m=cell, W=W, H=H, scale=scale, nodata=nd, comp=comp,
                flags=flags, plen=plen, min_m=lo, max_m=hi,
                pooled=bool(flags & 1), has_nodata=bool(flags & 2))


def decode_tile(blob):
    """The reference decoder. The browser does exactly this; keep them in step."""
    m = tile_meta(blob)
    hdr, W, H = m["hdr"], m["W"], m["H"]
    if (m["vtype"], m["pred"], m["comp"]) != (1, 2, 1):
        raise ValueError("unsupported vtype/pred/comp %d/%d/%d"
                         % (m["vtype"], m["pred"], m["comp"]))
    plen = m["plen"]
    v = array("h")
    v.frombytes(zlib.decompress(blob[hdr:hdr + plen]))
    if sys.byteorder == "big":
        v.byteswap()
    for r in range(H):
        b = r * W
        prev = 0
        for c in range(b, b + W):
            x = (prev + v[c]) & 0xFFFF
            prev = x - 65536 if x > 32767 else x
            v[c] = prev
    m["v"] = v
    return m


# --------------------------------------------------------------------------
# Fetching.
# --------------------------------------------------------------------------

def _build_tile(cell_m, tx, ty):
    """Fetch, resample and write one tile. Returns (bytes_on_disk, bytes_fetched)."""
    path = tile_path(cell_m, tx, ty)
    if os.path.exists(path):
        return os.path.getsize(path), 0

    src = REFINE.get(cell_m, cell_m)
    if src not in LEVELS:
        raise ValueError("%d m is not a GeoCubes level" % src)
    f = cell_m // src
    if f * src != cell_m:
        raise ValueError("%d m does not divide %d m" % (src, cell_m))

    x0, y0, x1, y1 = tile_bbox(cell_m, tx, ty)
    blob = get(CLIP % (src, LAYER, x0, y0, x1, y1, YEAR), timeout=600)
    g, W, H, px, ox, oy, nd = read_float_tiff(blob)
    if px != src:
        raise ValueError("asked for %d m, got %g m" % (src, px))
    g, W, H = maxpool(g, W, H, f)
    out, empty = encode_tile(g, W, H, ox, oy, cell_m, f > 1, nd)
    if empty:
        return 0, len(blob)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "wb") as fh:
        fh.write(out)
    os.replace(tmp, path)
    return len(out), len(blob)


def fetch_terrain(lat, lon, rings=RINGS, workers=6, verbose=True):
    """Pull everything an observer at (lat, lon) needs, ring by ring.

    Resumable: a tile already on disk is never refetched, and tiles sit on a
    global grid, so a second observer down the road pays only for the rim.
    Returns the manifest that fetch_terrain wrote to terrain/index.json.
    """
    e, n = wgs84_to_tm35(lat, lon)
    os.makedirs(TERRAIN, exist_ok=True)
    report = []
    inner = 0.0
    for outer_km, cell_m in rings:
        outer = outer_km * 1000.0
        want = tiles_for(cell_m, e, n, outer, inner)
        inner = outer
        t0 = time.time()
        ship = fetched = 0
        with futures.ThreadPoolExecutor(max_workers=workers) as ex:
            for s, f in ex.map(lambda t: _build_tile(cell_m, t[0], t[1]), want):
                ship += s
                fetched += f
        report.append(dict(cell_m=cell_m, outer_km=outer_km, tiles=len(want),
                           shipped=ship, fetched=fetched, secs=time.time() - t0))
        if verbose:
            print("  %4d m  %3d tiles  %7.2f MB shipped  %7.1f MB fetched  %5.1f s"
                  % (cell_m, len(want), ship / 1e6, fetched / 1e6,
                     report[-1]["secs"]))
    return write_index(rings, report)


def tiles_over(cell_m, bbox=CUBE):
    """Every tile of this cell size whose square meets `bbox`.

    The national counterpart of tiles_for. There is no observer to measure
    from, so there is no disc test and no inner ring: at this size the grid
    IS the selection.
    """
    s = float(tile_step(cell_m))
    tx0 = int(math.floor((bbox[0] - GRID_E0) / s))
    tx1 = int(math.floor((bbox[2] - GRID_E0 - 1) / s))
    ty0 = int(math.floor((GRID_N0 - bbox[3]) / s))
    ty1 = int(math.floor((GRID_N0 - bbox[1] - 1) / s))
    return [(tx, ty) for ty in range(ty0, ty1 + 1)
            for tx in range(tx0, tx1 + 1)]


def fetch_nationwide(bbox=CUBE, cells=None, workers=8, verbose=True):
    """Every tile in the country, at every cell size the rings use.

    fetch_terrain covers a disc around one observer, which is the wrong shape
    for a hosted deployment: the observer can be anywhere, so the tiles cannot
    be generated around places chosen in advance.

    Two properties of _build_tile make this affordable. It writes nothing for
    an all-nodata square, so open sea and the far side of the border cost a
    request and no disk; and it never refetches a tile that exists, so the run
    is resumable and a second pass over a warm cache is free.

    The whole GeoCubes window is 47,505 tiles across the four sizes and about
    2.3 GB if every one of them held land. Finland is roughly 40% of that
    window, so the real figure is nearer 19,000 tiles and 0.9 GB -- but every
    one of the 47,505 has to be ASKED for, because nodata is only discoverable
    by fetching. That, not the writing, is what sets the runtime.
    """
    os.makedirs(TERRAIN, exist_ok=True)
    cells = cells or sorted(TILE_PX)
    report = []
    for cell_m in cells:
        want = tiles_over(cell_m, bbox)
        t0 = time.time()
        ship = fetched = 0
        wrote = 0
        done = [0]
        lock = threading.Lock()

        def one(t):
            s_, f_ = _build_tile(cell_m, t[0], t[1])
            with lock:
                done[0] += 1
                if verbose and done[0] % 500 == 0:
                    print("    %d m  %d / %d  %.2f GB"
                          % (cell_m, done[0], len(want), ship / 1e9), flush=True)
            return s_, f_

        with futures.ThreadPoolExecutor(max_workers=workers) as ex:
            for s_, f_ in ex.map(one, want):
                ship += s_
                fetched += f_
                if s_:
                    wrote += 1
        report.append(dict(cell_m=cell_m, outer_km=None, tiles=len(want),
                           written=wrote, shipped=ship, fetched=fetched,
                           secs=time.time() - t0))
        if verbose:
            print("  %4d m  %6d asked  %6d written  %8.2f GB shipped  %6.0f s"
                  % (cell_m, len(want), wrote, ship / 1e9,
                     report[-1]["secs"]), flush=True)
    return write_index(RINGS, report)


def write_index(rings=RINGS, report=None):
    """Rebuild terrain/index.json from what is actually on disk."""
    tiles = {}
    for cell_m in sorted(TILE_PX):
        d = os.path.join(TERRAIN, str(cell_m))
        if not os.path.isdir(d):
            continue
        here = {}
        for fn in os.listdir(d):
            if not fn.endswith(".azt"):
                continue
            p = os.path.join(d, fn)
            with open(p, "rb") as f:
                m = tile_meta(f.read(HDR))
            here[fn[:-4]] = [os.path.getsize(p), m["min_m"], m["max_m"]]
        if here:
            tiles[str(cell_m)] = here
    idx = dict(format="AZT1", crs="EPSG:3067", vdatum="N2000",
               origin=[GRID_E0, GRID_N0],
               rings=[list(r) for r in rings],
               tile_px={str(k): v for k, v in sorted(TILE_PX.items())},
               source="MML Korkeusmalli 2 m via CSC GeoCubes, %d" % YEAR,
               licence="CC BY 4.0",
               tiles=tiles)
    if report:
        idx["last_fetch"] = report
    os.makedirs(TERRAIN, exist_ok=True)
    with open(INDEX, "w") as f:
        json.dump(idx, f, separators=(",", ":"))
    return idx


# --------------------------------------------------------------------------
# The observer's own ground.
#
# The page currently guesses this from the median base elevation of nearby
# objects, which reads 10.5 m at Kaivopuisto against a true 18-19 m -- an 8 m
# error is 0.05 deg at 10 km, more than the whole DEM error budget, and it
# shifts every elevation angle on the page at once.
#
# fin100.tif is read by seeking, not by slurping: it is 115 MB and one point
# needs one 256x256 tile out of 1,326 of them.
# --------------------------------------------------------------------------

_DEM = None
_DEM_TILES = {}


def _dem_header():
    global _DEM
    if _DEM is not None:
        return _DEM
    path = os.path.join(RAW, "fin100.tif")
    if not os.path.exists(path):
        return None
    # _tiff_tags indexes absolutely into the buffer it is given, so it needs a
    # prefix that reaches the last out-of-line tag value. Walk the directory
    # entries to find where that is rather than guessing: for fin100.tif the
    # two tile-offset arrays are 1,316 uint32 each, but nothing in the format
    # says where they sit, and slurping 115 MB to read one point is the thing
    # this function exists to avoid.
    SZ = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 11: 4, 12: 8, 16: 8}
    with open(path, "rb") as f:
        head = f.read(8)
        bo = "<" if head[:2] == b"II" else ">"
        off = struct.unpack(bo + "I", head[4:8])[0]
        f.seek(off)
        cnt = struct.unpack(bo + "H", f.read(2))[0]
        ents = f.read(cnt * 12)
        end = off + 2 + cnt * 12
        for i in range(cnt):
            _, typ, n = struct.unpack(bo + "HHI", ents[i * 12:i * 12 + 8])
            size = SZ.get(typ, 1) * n
            if size > 4:
                p = struct.unpack(bo + "I", ents[i * 12 + 8:i * 12 + 12])[0]
                end = max(end, p + size)
        f.seek(0)
        d = f.read(end)
    t = _tiff_tags(d, bo, off)
    _DEM = dict(path=path, bo=bo, W=t[256][0], H=t[257][0],
                px=t[33550][0], py=t[33550][1],
                ox=t[33922][3], oy=t[33922][4],
                nodata=float(t[42113].rstrip("\x00")) if 42113 in t else -9999.0,
                comp=t[259][0], tw=t[322][0], th=t[323][0],
                offs=t[324], cnts=t[325])
    _DEM["ntx"] = (_DEM["W"] + _DEM["tw"] - 1) // _DEM["tw"]
    return _DEM


def _dem_cell(col, row):
    m = _dem_header()
    if m is None or not (0 <= col < m["W"] and 0 <= row < m["H"]):
        return None
    ti = (row // m["th"]) * m["ntx"] + (col // m["tw"])
    if ti >= len(m["offs"]):
        return None
    v = _DEM_TILES.get(ti)
    if v is None:
        with open(m["path"], "rb") as f:
            f.seek(m["offs"][ti])
            blob = f.read(m["cnts"][ti])
        if m["comp"] in (5, 8):
            blob = zlib.decompress(blob)
        v = array("f")
        v.frombytes(blob)
        if m["bo"] == ">":
            v.byteswap()
        if len(_DEM_TILES) > 12:
            _DEM_TILES.clear()
        _DEM_TILES[ti] = v
    x = v[(row % m["th"]) * m["tw"] + (col % m["tw"])]
    if x <= m["nodata"] + 1.0 or x < -1000 or x > 1500:
        return None
    return x


def _dem100(lat, lon):
    """Bilinear over the 100 m model. Contour-derived, so it is smooth anyway."""
    m = _dem_header()
    if m is None:
        return None
    e, n = wgs84_to_tm35(lat, lon)
    fc = (e - m["ox"]) / m["px"] - 0.5
    fr = (m["oy"] - n) / m["py"] - 0.5
    c0, r0 = int(math.floor(fc)), int(math.floor(fr))
    u, v = fc - c0, fr - r0
    s = w = 0.0
    for dr, dc, wt in ((0, 0, (1 - u) * (1 - v)), (0, 1, u * (1 - v)),
                       (1, 0, (1 - u) * v), (1, 1, u * v)):
        if wt <= 0:
            continue
        x = _dem_cell(c0 + dc, r0 + dr)
        if x is not None:
            s += x * wt
            w += wt
    return s / w if w > 0 else None


# Beyond this, a tile is worse than the 100 m model for a single point: the
# tiles store a MAX over the cell, so a 50 m cell hands back the top of a
# 50 m square, while dem100 at least interpolates. 20 m is where the max
# stops costing more than the coarser grid saves.
GROUND_TILE_MAX_M = 20


def _from_tiles(lat, lon):
    """Nearest cell of the finest cached tile covering the point."""
    e, n = wgs84_to_tm35(lat, lon)
    for cell_m in sorted(c for c in TILE_PX if c <= GROUND_TILE_MAX_M):
        s = tile_step(cell_m)
        tx = int(math.floor((e - GRID_E0) / s))
        ty = int(math.floor((GRID_N0 - n) / s))
        p = tile_path(cell_m, tx, ty)
        if not os.path.exists(p):
            continue
        with open(p, "rb") as f:
            t = decode_tile(f.read())
        col = int((e - t["origin_e"]) / t["cell_m"])
        row = int((t["origin_n"] - n) / t["cell_m"])
        if not (0 <= col < t["W"] and 0 <= row < t["H"]):
            continue
        x = t["v"][row * t["W"] + col]
        if x != t["nodata"]:
            return x / float(t["scale"])
    return None


def ground_at(lat, lon, source="auto"):
    """Ground elevation in metres N2000, or None off the model.

    source="auto"   cached 10 m tile if there is one, else the 100 m model
           "dem100" the 100 m model only -- offline, no network, +-2 m
           "live"   one 20x20 m GeoCubes clip at 2 m. Costs an HTTP round trip
                    (~0.3 s, ~1 kB) and is the only one that resolves a hill
                    the size of Kaivopuisto, which a 100 m cell averages away.

    Against MTK's own lidar-derived base elevations, which is the best
    independent truth available:

        point               truth   dem100         auto      live
        Kivenlahti mast     43.15    41.98    44.0 (20m)    43.44
        Tiirismaa mast     217.58   217.75   218.0 (10m)   217.86
        Suomenoja stack      2.33     2.34     2.0 (20m)     2.58
        Kaivopuisto NE          -    12.97    19.0 (10m)    18.93

    The last row is why "auto" prefers a tile: the 100 m model averages a 19 m
    ridge down to 13 m, and 6 m of observer error is 0.034 deg at 10 km, on
    every object at once. What the tile costs in exchange is its max-pooling,
    +0.4 m at Tiirismaa and +0.85 m at Kivenlahti, which biases the observer
    UP and so makes things slightly MORE visible. Use "live" when the answer
    has to be right rather than close.
    """
    if source == "live":
        e, n = wgs84_to_tm35(lat, lon)
        x0 = int(e // 2) * 2 - 10
        y0 = int(n // 2) * 2 - 10
        blob = get(CLIP % (2, LAYER, x0, y0, x0 + 20, y0 + 20, YEAR), timeout=60)
        g, W, H, px, ox, oy, nd = read_float_tiff(blob)
        vals = [v for v in g if v > nd + 1.0]
        if not vals:
            return None
        col = int((e - ox) / px)
        row = int((oy - n) / px)
        if 0 <= col < W and 0 <= row < H:
            v = g[row * W + col]
            if v > nd + 1.0:
                return round(v, 2)
        return round(sum(vals) / len(vals), 2)
    if source == "dem100":
        v = _dem100(lat, lon)
        return None if v is None else round(v, 2)
    v = _from_tiles(lat, lon)
    if v is None:
        v = _dem100(lat, lon)
    return None if v is None else round(v, 2)


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lat", type=float, default=60.15672)
    ap.add_argument("--lon", type=float, default=24.95604)
    ap.add_argument("--rings", type=int, default=len(RINGS),
                    help="how many rings, innermost first")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--nationwide", action="store_true",
                    help="every tile in the country, not a disc around --lat/--lon")
    ap.add_argument("--cells", type=int, nargs="+",
                    help="restrict --nationwide to these cell sizes, metres")
    ap.add_argument("--ground", nargs=2, type=float, metavar=("LAT", "LON"),
                    help="just print ground_at() three ways and stop")
    a = ap.parse_args()

    if a.ground:
        lat, lon = a.ground
        for s in ("dem100", "auto", "live"):
            t0 = time.time()
            try:
                v = ground_at(lat, lon, s)
            except Exception as exc:                        # noqa: BLE001
                print("  %-7s failed: %s" % (s, exc))
                continue
            print("  %-7s %8s m  %.3f s" % (s, v, time.time() - t0))
        return

    if a.nationwide:
        cells = a.cells or sorted(TILE_PX)
        want = sum(len(tiles_over(c)) for c in cells)
        print("nationwide terrain -> %s" % TERRAIN)
        print("cell sizes: %s" % ", ".join("%d m" % c for c in cells))
        print("%d tiles to ask for; the ones that are all nodata are not written"
              % want)
        t0 = time.time()
        idx = fetch_nationwide(cells=cells, workers=a.workers)
        r = idx["last_fetch"]
        print("  %-6s %6d asked  %6d written  %8.2f GB shipped  %6.0f s"
              % ("total", sum(x["tiles"] for x in r),
                 sum(x["written"] for x in r),
                 sum(x["shipped"] for x in r) / 1e9, time.time() - t0))
        print("index: %s (%d bytes, %d tiles cached)"
              % (INDEX, os.path.getsize(INDEX),
                 sum(len(v) for v in idx["tiles"].values())))
        return

    rings = RINGS[:a.rings]
    print("terrain for %.5f, %.5f -> %s" % (a.lat, a.lon, TERRAIN))
    print("rings: %s" % ", ".join("%d km @ %d m" % (o, c) for o, c in rings))
    t0 = time.time()
    idx = fetch_terrain(a.lat, a.lon, rings, workers=a.workers)
    r = idx["last_fetch"]
    print("  %-6s %3d tiles  %7.2f MB shipped  %7.1f MB fetched  %5.1f s"
          % ("total", sum(x["tiles"] for x in r),
             sum(x["shipped"] for x in r) / 1e6,
             sum(x["fetched"] for x in r) / 1e6, time.time() - t0))
    print("index: %s (%d bytes, %d tiles cached)"
          % (INDEX, os.path.getsize(INDEX),
             sum(len(v) for v in idx["tiles"].values())))
    print("observer ground: %s m N2000 (auto), %s m (dem100)"
          % (ground_at(a.lat, a.lon), ground_at(a.lat, a.lon, "dem100")))


if __name__ == "__main__":
    main()
