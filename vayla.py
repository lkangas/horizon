#!/usr/bin/env python3
"""Vaylavirasto navigational aids -> isolated sea landmarks.

usage: python vayla.py fetch [dest.json]     download and cache the candidates
       python vayla.py report [dest.json]    counts, heights, spacing

Vaylavirasto publishes the whole Finnish aid-to-navigation register key-free
under CC BY 4.0 as OGC API Features. The interesting part for a horizon page is
not the lights but the STRUCTURES that carry them: 44 sea lighthouses, 38
daymark towers and 197 concrete offshore caisson beacons, every one of them
surveyed, named, and standing alone in open water with nothing else within
kilometres. That is the ideal horizon target, and OpenStreetMap has 163 of them
with no heights at all.

Three things about this API cost an afternoon each if you meet them cold:

  - The type string is `Merimajakka`, not `Majakka`. A CQL2 filter on
    'Majakka' answers 200 with numberMatched="0" and looks perfectly healthy.
  - Paging is GeoServer's `startIndex`, not the OGC-standard `offset`.
    `offset` is accepted and SILENTLY IGNORED, so a naive limit=5000 loop over
    25,508 features returns the same first page six times -- and the histogram
    it builds is a plausible-looking 6x of the truth.
  - Every geometry is a MultiPoint, never a Point, so `coordinates` is a list
    of pairs. 435 of the 8,866 candidates carry the same coordinate two or more
    times over (measured spread between the repeats: 0.0 m on every one), so
    the first coordinate is the position.

Also: CQL2 `a='x' OR a='y'` returns HTTP 500 here, while `a IN ('x','y')`
works, which is why the type filter is built as an IN list.
"""

import collections
import json
import math
import os
import sys
import urllib.parse
import urllib.request

BASE = "https://avoinapi.vaylapilvi.fi/vaylatiedot/ogc/features/v1/"

# Both registers are needed. `turvalaitteet_muut_vaylanpitajat` is not a
# rounding error: the Aland Government alone owns 1,182 aids in it, including
# 10 of the 38 daymark towers and one of the 44 sea lighthouses.
COLLECTIONS = ("turvalaitteet_vaylavirasto", "turvalaitteet_muut_vaylanpitajat")

UA = {"User-Agent": "azimuth/0.1 (+https://github.com/lkangas/azimuth)"}

# Types cached. Viitta (24,998) and Poiju (1,012) are left out of the download
# entirely: they float, they are 1-3 m of plastic, and the spar buoys are
# lifted out of the water for the winter. Everything else is cached even when
# it is not emitted, so the inclusion rule below can be retuned without a
# refetch -- 8,866 features, 12.7 MB.
CANDIDATE_TYPES = (
    "Merimajakka", "Tunnusmajakka", "Reunamerkki", "Sektoriloisto",
    "Tutkamerkki", "Apuloisto", "Suuntaloisto", "Muu merkki",
    "Kummeli", "Linjamerkki",
)

# Included unconditionally: the type itself guarantees a built tower standing
# on its own. 44 + 38 + 197 = 279 objects, of which 230 have nothing at all in
# the current objects.json within 300 m.
#
# Tunnusmajakka is where the decommissioned giants live -- Soderskar and
# Porkkala are both unlit, so neither is typed Merimajakka -- and 30 of the 38
# publish no height at all, which is fine: they are still towers, and the
# surface model can measure them.
TOWER_TYPES = ("Merimajakka", "Tunnusmajakka", "Reunamerkki")

# Included only when the register says the structure is at least TAIL_MIN_M
# tall above its own ground. These types are dominated by a light box or a
# painted board on a short pole -- median structure height 6.7 m for
# Sektoriloisto, 3.0 m for Linjamerkki -- but the tail is real: 181 leading
# marks clear 20 m and the tallest, Klobbudden ylempi, is a 49 m lattice tower
# carrying a 5 m board.
TAIL_TYPES = ("Linjamerkki", "Sektoriloisto", "Tutkamerkki",
              "Apuloisto", "Suuntaloisto")
TAIL_MIN_M = 20.0

# Never emitted:
#   Kummeli (2,491) -- stone cairns, median 2.4 m, exactly one clears 20 m.
#   Muu merkki (48) -- the only tall ones are radio masts the catalogue
#     already holds from MTK/AIP as cat=mast: Kuusisto 360 m, Ahvenanmaan
#     yleisradioasema 246 m, Jarso radiomasto 170 m. Admitting them as
#     cat=lighthouse would create three duplicates that COMPATIBLE can never
#     merge away, because mast and lighthouse do not merge.

CAT = "lighthouse"
CACHE_NAME = "vayla.json"

# For build.py's payload["attribution"]. The licence page for the
# vaylatiedot open API names Vaylavirasto and CC BY 4.0.
ATTRIBUTION = ("Contains navigational aid data from the Finnish Transport "
               "Infrastructure Agency (Vaylavirasto), CC BY 4.0")


def _metres(a, b):
    """Metres between two (lat, lon) pairs, flat approximation."""
    return math.hypot((a[0] - b[0]) * 111320.0,
                      (a[1] - b[1]) * 111320.0 * math.cos(math.radians(a[0])))


# --------------------------------------------------------------------------
# Fetch.
# --------------------------------------------------------------------------

def _default_path():
    """Same cache rules as build.py, so the module also runs standalone.

    Deliberately does NOT import build.py: build.py will import this module,
    and the cycle is avoidable by just passing the path in.
    """
    d = os.environ.get("AZIMUTH_CACHE")
    if not d:
        base = (os.environ.get("LOCALAPPDATA")
                or os.environ.get("XDG_CACHE_HOME")
                or os.path.join(os.path.expanduser("~"), ".cache"))
        d = os.path.join(base, "azimuth")
    return os.path.join(d, "raw", CACHE_NAME)


def _get(url, timeout=180):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _items(collection, cql, page=2000):
    """Page one collection with startIndex; see the module docstring on offset."""
    out = []
    start = 0
    while True:
        url = (BASE + "collections/%s/items?f=json&limit=%d&startIndex=%d"
               "&filter-lang=cql2-text&filter=%s"
               % (collection, page, start, urllib.parse.quote(cql)))
        d = _get(url)
        feats = d.get("features") or []
        if not feats:
            break
        out.extend(feats)
        start += len(feats)
        matched = d.get("numberMatched")
        if matched is None or start >= matched:
            break
    return out


def fetch_vayla(dest=None, force=False):
    """Download the candidate aids into one JSON cache file. Returns its path.

    The whole thing is 8,866 features and about 13 MB over ~6 requests, so
    there is no incremental logic: delete the file to refetch.
    """
    dest = dest or _default_path()
    if os.path.exists(dest) and not force:
        print("%s present, skipping (delete it to refetch)"
              % os.path.basename(dest))
        return dest
    cql = "turvalaitetyyppifi IN (%s)" % ",".join(
        "'%s'" % t for t in CANDIDATE_TYPES)
    feats = []
    for col in COLLECTIONS:
        got = _items(col, cql)
        print("  %-34s %5d features" % (col, len(got)))
        for f in got:
            p = f.get("properties") or {}
            p["_collection"] = col
            g = f.get("geometry") or {}
            # MultiPoint on every record; see the module docstring.
            cs = g.get("coordinates") or []
            if g.get("type") == "Point":
                p["_lonlat"] = cs
            elif cs:
                p["_lonlat"] = cs[0]
            else:
                continue
            feats.append(p)
    feats.sort(key=lambda p: (p["_collection"], p.get("id") or 0))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(feats, f, ensure_ascii=False)
    print("  %d features -> %s (%.1f MB)"
          % (len(feats), os.path.basename(dest), os.path.getsize(dest) / 1e6))
    return dest


# --------------------------------------------------------------------------
# Heights.
#
# Both height-bearing columns are free text holding a flat key: value list:
#
#   loistojen_tiedot:      "Loiston laji: Yovalo, Korkeus vedesta: 51,
#                           Korkeus maasta: 46, Tehollinen valovoima: 1236, ..."
#   paivatunnusten_tiedot: "Vari: Harmaa, ..., Korkeus (m): , Leveys (m): ,
#                           Korkeus maasta (m): 46, Korkeus vedesta: 51"
#
# A structure with two lights carries both records in one string, separated by
# a LITERAL backslash-n -- two characters, not a newline. Uto alempi is one:
# splitting only on "," turns the join into the key "Tahdistus: K\nLoiston
# laji". 46 of the 2,995 light records are second records like that.
#
# NONE of these numbers is a top elevation, and none is N2000:
#
#   Korkeus vedesta       focal plane of the LIGHT above mean water
#   Korkeus maasta        focal plane of the LIGHT above its own rock/deck
#   Korkeus maasta (m)    top of the DAYMARK above its own rock/deck
#
# and the focal plane is below the top of the tower by the lantern and roof:
# Bengtskar reads 46 m above the rock against a 52 m tower.
#
# `Korkeus (m)` in paivatunnusten_tiedot is deliberately not read. On a tower
# it is the tower (Market: 14, and Korkeus maasta (m) is also 14), but on a
# leading mark it is the painted board, not the structure: Uto ylempi reads
# Korkeus (m) 7.5, Leveys (m) 5.5, Korkeus maasta (m) 24.5. Using it as a
# structure height turns a 24 m tower into a 7 m one.
# --------------------------------------------------------------------------

# Spelled out as an escape so this file stays ASCII like build.py: the key in
# the data is "Korkeus vedesta" with an a-umlaut on the last a.
KEY_WATER = "Korkeus vedestä"


def _kv(text):
    d = {}
    if not text:
        return d
    for record in str(text).split("\\n"):
        for part in record.split(","):
            if ":" in part:
                k, v = part.split(":", 1)
                d.setdefault(k.strip(), v.strip())
    return d


def _num(v):
    if v in (None, "", "-"):
        return None
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


def heights(props):
    """(focal_m, focal_agl_m, daymark_agl_m) for one aid; any may be None."""
    light = _kv(props.get("loistojen_tiedot"))
    day = _kv(props.get("paivatunnusten_tiedot"))
    focal = _num(light.get(KEY_WATER))
    if focal is None:
        focal = _num(day.get(KEY_WATER))
    return (focal,
            _num(light.get("Korkeus maasta")),
            _num(day.get("Korkeus maasta (m)")))


def structure_m(props):
    """Best published height of the structure above its OWN ground, or None.

    Only the two above-ground numbers count here. This is the number the
    inclusion gate for TAIL_TYPES uses, and it has to be above-ground: on a
    shore leading mark `Korkeus vedesta` is the light above the SEA, so it
    silently includes the hill the mark stands on. Across the 1,846 leading
    marks publishing both, above-water exceeds above-ground by a median 2.2 m
    and by as much as 37.5 m.
    """
    _f, agl, day = heights(props)
    vals = [v for v in (agl, day) if v is not None]
    return max(vals) if vals else None


# --------------------------------------------------------------------------
# Load.
# --------------------------------------------------------------------------

# One physical tower can be registered several times over, because the
# register is a register of AIDS, not of structures: Tankar lighthouse is also
# "Tankar 2 ylempi", a leading mark, at the same coordinate to seven decimals.
# Eight such pairs exist in the emitted set, all within 4.7 m, and the next
# closest pair in the whole layer is the 60.3 m between Ruotsinsalmi diktaali 2
# and 4 -- two genuinely separate caissons. So collapsing under 10 m is
# unambiguous, and doing it here rather than leaving it to build.py's merge()
# matters: merge() keeps whichever record it saw FIRST, which would have left
# Tankar lighthouse recorded as a leading mark.
COLLAPSE_M = 10.0

# Preference when collapsing: the record whose type says "tower" wins, so the
# surviving object keeps the lighthouse's name and its focal plane.
_TYPE_RANK = {"Merimajakka": 6, "Tunnusmajakka": 5, "Reunamerkki": 4,
              "Sektoriloisto": 3, "Tutkamerkki": 2, "Apuloisto": 2,
              "Suuntaloisto": 2, "Linjamerkki": 1}

_FOLD = ("focal_m", "focal_agl_m", "daymark_agl_m", "name", "vayla_id")


def _collapse(objs, radius=COLLAPSE_M):
    cell = 0.01                              # ~1.1 km, so 3x3 covers any radius
    grid = collections.defaultdict(list)
    kept = []
    for o in sorted(objs, key=lambda o: (-_TYPE_RANK.get(o["vayla_type"], 0),
                                         -(structure_hint(o) or 0.0))):
        i, j = int(o["lat"] / cell), int(o["lon"] / cell)
        hit = None
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for c in grid.get((i + di, j + dj), ()):
                    if _metres((o["lat"], o["lon"]), (c["lat"], c["lon"])) <= radius:
                        hit = c
                        break
                if hit:
                    break
            if hit:
                break
        if hit:
            for k in _FOLD:
                if hit.get(k) is None and o.get(k) is not None:
                    hit[k] = o[k]
            continue
        kept.append(o)
        grid[(i, j)].append(o)
    return kept


def structure_hint(o):
    """Tallest published number on a loaded object; ordering only."""
    vals = [v for v in (o.get("focal_agl_m"), o.get("daymark_agl_m"),
                        o.get("focal_m")) if v is not None]
    return max(vals) if vals else None


def load_vayla(path=None, tail_min_m=TAIL_MIN_M):
    """Objects in the build.py schema. Returns [] when the cache is absent.

    height_m is left None on every object on purpose. The register publishes
    focal planes and daymark tops, not tower tops, and none of it is N2000, so
    it must not flow into top_m unannounced. The three published numbers ride
    along in their own fields; apply_focal_heights() below turns them into a
    height explicitly, if the build wants that.
    """
    path = path or _default_path()
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        feats = json.load(f)
    out = []
    for p in feats:
        t = p.get("turvalaitetyyppifi")
        if t in TOWER_TYPES:
            pass
        elif t in TAIL_TYPES and (structure_m(p) or 0.0) >= tail_min_m:
            pass
        else:
            continue
        lon, lat = p["_lonlat"][0], p["_lonlat"][1]
        focal, agl, day = heights(p)
        name = (p.get("nimifi") or p.get("nimisv") or "").strip()
        out.append({
            "cat": CAT,
            "lat": round(lat, 7),
            "lon": round(lon, 7),
            "ground_m": None,       # sea level; build.py's sample_dem fills it
            "height_m": None,       # see the docstring
            "src_h": None,
            "name": name or None,
            "src_pos": "vayla",
            "vayla_type": t,
            "vayla_id": p.get("turvalaitenumero"),
            "focal_m": focal,       # light focal plane above MEAN WATER
            "focal_agl_m": agl,     # light focal plane above its own base
            "daymark_agl_m": day,   # top of the daymark above its own base
            # toimintatilakoodi 1 = in service. Only one tower is not:
            # Ulkokalla, code 0, whose 1834 stone tower is still standing and
            # is still the only thing on the horizon out there.
            "in_service": p.get("toimintatilakoodi") == 1,
            "owner": p.get("omistajafi"),
        })
    return _collapse(out)


def apply_focal_heights(objs):
    """Fill height_m from the published focal plane, explicitly. Returns count.

    Optional, and the build has to ask for it. The reason it is worth asking
    for: the nDSM has no coverage over open water. Sampling 19 towers through
    build.py's own ndsm_window returned a usable height on 11 and 0.0 on 8 --
    Langden, Raahe, Soderbadan, Tommoskars haruni among them, all sitting on
    bare rock outside the lidar blocks. The register covers 458 of 470.

    What is filled is an UNDERSTATEMENT of the top by the lantern and roof --
    Bengtskar 46 against 52 -- so it never overwrites a measured height, and
    it is tagged src_h="vayla" / conf="focal" so the page can say so.
    """
    n = 0
    for o in objs:
        # vayla_id, not src_pos: a sea mark that merged into an OSM lighthouse
        # keeps the register's fields but the merged object's src_pos is the
        # base's. build.py's CARRY is what brings them across.
        if o.get("vayla_id") is None or o.get("height_m") is not None:
            continue
        h = o.get("focal_agl_m") or o.get("daymark_agl_m")
        basis = "agl"
        if h is None:
            # Last resort, and only where the object is at the waterline, so
            # that above-water and above-ground are the same number. It is the
            # only number 196 of the 197 caisson beacons publish. On the four
            # Reunamerkki that publish both, above-water exceeds above-ground
            # by a median 0.7 m.
            g = o.get("ground_m")
            if o.get("focal_m") is not None and g is not None and g <= 2.0:
                h = o["focal_m"]
                basis = "water"
        if h is None:
            continue
        o["height_m"] = round(h, 1)
        o["src_h"] = "vayla"
        o["conf"] = "focal"
        o["h_basis"] = basis
        n += 1
    return n


# --------------------------------------------------------------------------
# Standalone report.
# --------------------------------------------------------------------------

def report(path=None):
    objs = load_vayla(path)
    if not objs:
        sys.exit("no cache yet -- run: python vayla.py fetch")
    print("  %-16s %6s %8s %10s %11s %7s" % (
        "type", "n", "focal_m", "focal_agl", "daymark_agl", "named"))
    for t, n in collections.Counter(o["vayla_type"] for o in objs).most_common():
        s = [o for o in objs if o["vayla_type"] == t]
        print("  %-16s %6d %8d %10d %11d %7d" % (
            t, n,
            sum(1 for o in s if o["focal_m"] is not None),
            sum(1 for o in s if o["focal_agl_m"] is not None),
            sum(1 for o in s if o["daymark_agl_m"] is not None),
            sum(1 for o in s if o["name"])))
    print("  %-16s %6d %8d %10d %11d %7d" % (
        "TOTAL", len(objs),
        sum(1 for o in objs if o["focal_m"] is not None),
        sum(1 for o in objs if o["focal_agl_m"] is not None),
        sum(1 for o in objs if o["daymark_agl_m"] is not None),
        sum(1 for o in objs if o["name"])))
    print("  out of service: %d" % sum(1 for o in objs if not o["in_service"]))
    owners = collections.Counter(o["owner"] for o in objs)
    print("  owners: %s" % dict(owners.most_common(4)))

    # Nearest neighbour WITHIN this layer. build.py's merge() adds each
    # appended object to its grid, so a layer does self-merge as it is folded
    # in, and this distance is what caps the merge radius.
    cell = 0.01
    grid = collections.defaultdict(list)
    for o in objs:
        grid[(int(o["lat"] / cell), int(o["lon"] / cell))].append(o)
    nn = []
    for o in objs:
        i, j = int(o["lat"] / cell), int(o["lon"] / cell)
        best, who = 1e9, None
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for c in grid.get((i + di, j + dj), ()):
                    if c is o:
                        continue
                    d = _metres((o["lat"], o["lon"]), (c["lat"], c["lon"]))
                    if d < best:
                        best, who = d, c
        if who is not None:
            nn.append((best, o, who))
    nn.sort(key=lambda t: t[0])
    print("\n  closest pairs inside the layer:")
    for d, a, b in nn[:6]:
        print("    %6.1f m  %-26s <-> %s" % (d, (a["name"] or "?")[:26],
                                             b["name"] or "?"))
    for r in (30, 50, 60, 100, 150):
        print("    pairs closer than %3d m: %d"
              % (r, sum(1 for d, _a, _b in nn if d < r)))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    path = sys.argv[2] if len(sys.argv) > 2 else None
    if cmd == "fetch":
        fetch_vayla(path)
    elif cmd == "report":
        report(path)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
