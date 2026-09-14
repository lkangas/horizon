/* -------------------------------------------------------------------------
 * horizon.js -- the terrain horizon, computed in a Worker.
 *
 * Input:  an observer (lat, lon, eye height) and the AZT1 tiles terrain.py
 *         wrote under /terrain/.
 * Output: 3600 rays at 0.1 degrees, each carrying
 *           prof[i]   the horizon elevation in degrees at azimuth i*0.1
 *           profD[i]  the distance in metres of the terrain that sets it
 *           a staircase of (distance, elevation) breakpoints, so occlusion
 *           can be asked "what is the horizon within r < d", which is a
 *           different question and the only correct one for a near object.
 *
 * Why the staircase. prof[i] is a maximum over the WHOLE ray. Testing an
 * object against it is wrong at short range in exactly the way PLAN.md 5.2
 * describes: a 60 m building at 3 km would be declared hidden by a 120 m hill
 * at 25 km standing behind it. The staircase is monotone by construction --
 * it only ever records a new record high -- so the answer for distance d is
 * the last breakpoint before d, found by binary search.
 *
 * The sweep is r.horizon's inner loop, which compares heights instead of
 * angles and so costs one multiply-add and one compare per sample rather
 * than a divide:
 *
 *     if (h > hobs + d*d/(2*REFF) + d*tanmax)
 *         tanmax = (h - hobs - d*d/(2*REFF)) / d
 *
 * This file is a Worker on purpose. The sweep measures 60-130 ms here (see
 * the numbers the page prints), which is four to eight dropped frames if it
 * runs on the main thread while the map is being dragged.
 *
 * It is also the only place in the page that knows the tile format. Keep it
 * in step with terrain.py's decode_tile, which is the reference decoder.
 * ---------------------------------------------------------------------- */

'use strict';

/* Same constants as the page: k = 0.13 standard refraction, GRS80. If these
   drift apart the profile and the objects stop agreeing about the horizon. */
const K = 0.13, REFF = 6371008.8 / (1 - K);
const D2R = Math.PI / 180, R2D = 180 / Math.PI;
const A_E = 6378137.0, F_E = 1 / 298.257222101, B_E = A_E * (1 - F_E);

const NBINS = 3600, BINW = 360 / NBINS;

/* The radial schedule from PLAN.md 5.2: [outer metres, step metres]. 10 m out
   to 5 km, then coarser as the rays themselves spread -- at 60 km adjacent
   rays are 105 m apart, so a 50 m step along the ray is already finer than
   the sampling across it. 2,200 samples per ray to the 90 km edge of the
   tile set, 7.92 M samples for the sweep. */
const SCHEDULE = [[5000, 10], [20000, 25], [60000, 50], [90000, 100]];

/* GeoCubes' grid anchor, repeated from terrain.py so tile names match. The
   index carries it too and that is what is actually used; this is the
   fallback if an old index has no origin. */
let GRID_E0 = 0, GRID_N0 = 7800000;

/* Staircase economy. Two rules keep it from becoming a per-sample log:
   ANG_FLOOR drops everything below -6 degrees, which is the ground at your
   feet -- at a 20 m eye height -6 degrees is terrain within 190 m, and the
   strip never scales below about -1; EPS_DEG merges steps smaller than
   0.02 degrees, a fifth of a bin and far inside the DEM's own error. Without
   them a ray over flat ground records a new high at nearly every one of its
   first 1,100 samples, because the angle to flat ground climbs all the way
   to the sea horizon. */
const ANG_FLOOR = -6.0, EPS_DEG = 0.02;

/* Skipping a tile on its max_m alone is safe past this distance and not
   before it. Beyond the sea horizon anything below the sea's own angle is
   invisible whatever it is, so the skip changes nothing; nearer than this
   the staircase genuinely uses angles well below the sea horizon -- that is
   how the foot of a near mast gets hidden by the field in front of it -- and
   a skipped tile would be read as 0 m and shift that line. */
const SKIP_MIN_M = 15000;

const NODATA = -32768;

/* ---------------------------------------------------------------- geodesy */

/* EPSG:3067 forward, a port of build.py's wgs84_to_tm35 (Kruger series, GRS80,
   central meridian 27E, k0 0.9996, false easting 500 km). Ported rather than
   approximated because the tiles are indexed in TM35FIN metres and a 1 m slip
   here is a whole 2 m DEM cell. Checked against the Python at six points
   across Finland; see the report. */
const _LON0 = 27 * D2R, _K0 = 0.9996, _FE = 500000.0;
const _n = F_E / (2 - F_E);
const _AA = A_E / (1 + _n) * (1 + _n * _n / 4 + Math.pow(_n, 4) / 64);
const _e = Math.sqrt(F_E * (2 - F_E));
const _a1 = _n / 2 - 2 * _n * _n / 3 + 5 * Math.pow(_n, 3) / 16 + 41 * Math.pow(_n, 4) / 180;
const _a2 = 13 * _n * _n / 48 - 3 * Math.pow(_n, 3) / 5 + 557 * Math.pow(_n, 4) / 1440;
const _a3 = 61 * Math.pow(_n, 3) / 240 - 103 * Math.pow(_n, 4) / 140;
const _a4 = 49561 * Math.pow(_n, 4) / 161280;

function atanh(x) { return 0.5 * Math.log((1 + x) / (1 - x)); }

function tm35(lat, lon) {
  const phi = lat * D2R, dl = lon * D2R - _LON0;
  const s = Math.sin(phi);
  const t = Math.sinh(atanh(s) - _e * atanh(_e * s));
  const xi_ = Math.atan(t / Math.cos(dl));
  const eta_ = atanh(Math.sin(dl) / Math.sqrt(1 + t * t));
  let xi = xi_, eta = eta_;
  const a = [_a1, _a2, _a3, _a4];
  for (let j = 1; j <= 4; j++) {
    xi += a[j - 1] * Math.sin(2 * j * xi_) * Math.cosh(2 * j * eta_);
    eta += a[j - 1] * Math.cos(2 * j * xi_) * Math.sinh(2 * j * eta_);
  }
  return [_FE + _K0 * _AA * eta, _K0 * _AA * xi];
}

/* Vincenty direct on GRS80. One call per ray, not per sample: the ray is then
   a straight line in TM35FIN between the projected observer and the projected
   90 km endpoint, parameterised by GEODESIC distance.

   Stepping in the projection is the part that has to be justified, because
   PLAN.md forbids computing an azimuth there -- grid north is up to 6.5
   degrees off true north in Finland. Anchoring both ends removes the
   convergence and the scale factor exactly; what is left is the arc-to-chord
   effect, the bow of a geodesic against its grid chord. Measured against the
   exact solution (Vincenty direct at each distance, then projected) the
   worst case over a 90 km ray anywhere in Finland is a few tens of metres
   sideways -- see the report -- which is a hundredth of a bin and less than
   one 100 m cell at that range. */
function direct(lat1, lon1, az, s) {
  const a1 = az * D2R;
  const U1 = Math.atan((1 - F_E) * Math.tan(lat1 * D2R));
  const sU1 = Math.sin(U1), cU1 = Math.cos(U1);
  const sa1 = Math.sin(a1), ca1 = Math.cos(a1);
  const sig1 = Math.atan2(Math.tan(U1), ca1);
  const sa = cU1 * sa1;
  const c2a = 1 - sa * sa;
  const u2 = c2a * (A_E * A_E - B_E * B_E) / (B_E * B_E);
  const A = 1 + u2 / 16384 * (4096 + u2 * (-768 + u2 * (320 - 175 * u2)));
  const B = u2 / 1024 * (256 + u2 * (-128 + u2 * (74 - 47 * u2)));
  let sig = s / (B_E * A), prev = 0, c2sm = 0, ss = 0, cs = 0, dsig = 0;
  for (let i = 0; i < 100 && Math.abs(sig - prev) > 1e-12; i++) {
    c2sm = Math.cos(2 * sig1 + sig);
    ss = Math.sin(sig); cs = Math.cos(sig);
    dsig = B * ss * (c2sm + B / 4 * (cs * (-1 + 2 * c2sm * c2sm)
      - B / 6 * c2sm * (-3 + 4 * ss * ss) * (-3 + 4 * c2sm * c2sm)));
    prev = sig;
    sig = s / (B_E * A) + dsig;
  }
  const tmp = sU1 * ss - cU1 * cs * ca1;
  const lat2 = Math.atan2(sU1 * cs + cU1 * ss * ca1,
    (1 - F_E) * Math.sqrt(sa * sa + tmp * tmp));
  const lam = Math.atan2(ss * sa1, cU1 * cs - sU1 * ss * ca1);
  const C = F_E / 16 * c2a * (4 + F_E * (4 - 3 * c2a));
  const L = lam - (1 - C) * F_E * sa
    * (sig + C * ss * (c2sm + C * cs * (-1 + 2 * c2sm * c2sm)));
  return [lat2 * R2D, lon1 + L * R2D];
}

/* ------------------------------------------------------------------ tiles */

/* Relative to the worker script, which sits next to the page, so the page
   works under a subdirectory as well as at a root. A worker created from a
   blob: URL has no hierarchical base to resolve against and throws here --
   that only happens when this file is imported for testing, but a throw at
   load time kills the whole worker, so it falls back to the relative form. */
let BASE = 'terrain/';
try { BASE = new URL('terrain/', self.location.href).href; } catch (e) { /* blob: */ }
let INDEX = null;
const TILES = new Map();          // "cell/tx_ty" -> decoded tile or null

async function loadIndex() {
  if (INDEX) return INDEX;
  /* The tiles are fetched force-cache because a tile name identifies its
     content; index.json is not, because terrain.py rewrites it every time it
     fetches a new region, and a pinned stale index means the new tiles are
     never asked for. */
  const r = await fetch(BASE + 'index.json');
  if (!r.ok) throw new Error('terrain/index.json: HTTP ' + r.status);
  INDEX = await r.json();
  if (INDEX.origin) { GRID_E0 = INDEX.origin[0]; GRID_N0 = INDEX.origin[1]; }
  return INDEX;
}

/* The decoder. This is terrain.py's decode_tile, in the browser: a 36-byte
   header read with DataView, one deflate stream, then TIFF predictor 2 undone
   per row. The `<< 16 >> 16` is not decoration -- the predictor wraps in
   int16, and the nodata sentinel -32768 is exactly the value that overflows
   without it, so a single sea cell would corrupt the rest of its row. */
async function decodeTile(buf) {
  const dv = new DataView(buf);
  if (dv.getUint32(0, false) !== 0x415a5431) throw new Error('not an AZT1 tile');
  const hdr = dv.getUint16(4, true);
  const vtype = dv.getUint8(6), pred = dv.getUint8(7), comp = dv.getUint8(26);
  if (vtype !== 1 || pred !== 2 || comp !== 1) {
    throw new Error('unsupported tile ' + vtype + '/' + pred + '/' + comp);
  }
  const oe = dv.getInt32(8, true), on = dv.getInt32(12, true);
  const cell = dv.getUint16(16, true);
  const w = dv.getUint16(18, true), h = dv.getUint16(20, true);
  const scale = dv.getInt16(22, true);
  const plen = dv.getUint32(28, true);
  const ds = new Response(buf.slice(hdr, hdr + plen)).body
    .pipeThrough(new DecompressionStream('deflate'));
  const v = new Int16Array(await new Response(ds).arrayBuffer());
  if (v.length !== w * h) throw new Error('tile is ' + v.length + ', wanted ' + w * h);
  for (let r = 0; r < h; r++) {
    let p = 0;
    const b = r * w;
    for (let c = 0; c < w; c++) { p = (p + v[b + c]) << 16 >> 16; v[b + c] = p; }
  }
  return { v: v, w: w, h: h, oe: oe, on: on, cell: cell, scale: scale };
}

async function getTile(cell, tx, ty) {
  const key = cell + '/' + tx + '_' + ty;
  if (TILES.has(key)) return TILES.get(key);
  let t = null;
  try {
    const r = await fetch(BASE + cell + '/' + tx + '_' + ty + '.azt',
      { cache: 'force-cache' });
    if (r.ok) t = await decodeTile(await r.arrayBuffer());
  } catch (e) {
    t = null;                       // a missing tile is sea, not a failure
  }
  TILES.set(key, t);
  return t;
}

/* The best elevation tangent a ceiling of `ceil` metres could reach anywhere
   in the distance band [dIn, dOut], which is what both early-outs test.

   f(d) = (ceil - hobs)/d - d/(2R) is only monotone when the ceiling is above
   the eye. Below it the function rises to a maximum at sqrt(2R(hobs-ceil))
   -- that is the sea horizon, the same shape -- so taking f(dIn) as the bound
   would wrongly discard, for example, a 5 m island 20 km out seen from 100 m
   up, whose best angle is at 37 km and does clear the sea horizon. */
function bestTan(ceil, hobs, dIn, dOut) {
  const c = ceil - hobs;
  let d = dIn;
  if (c < 0) {
    const dStar = Math.sqrt(2 * REFF * -c);
    if (dStar > dIn) d = Math.min(dStar, dOut);
  }
  return c / d - d / (2 * REFF);
}

/* Nearest distance from a point to a tile's square, 0 inside it. */
function nearDist(e, n, x0, y0, x1, y1) {
  const dx = e < x0 ? x0 - e : (e > x1 ? e - x1 : 0);
  const dy = n < y0 ? y0 - n : (n > y1 ? n - y1 : 0);
  return Math.hypot(dx, dy);
}

/* ------------------------------------------------------------------ sweep */

async function sweep(msg) {
  const t0 = performance.now();
  const idx = await loadIndex();
  const rings = idx.rings.map(r => [r[0] * 1000, r[1]]);
  const px = idx.tile_px;
  const rMax = Math.min(SCHEDULE[SCHEDULE.length - 1][0], rings[rings.length - 1][0]);

  const [e0, n0] = tm35(msg.lat, msg.lon);

  /* The observer's own ground, from the finest tile that covers the point.
     This is terrain.py's ground_at(source="auto") done client-side: the same
     nearest-cell read of the same tiles. Checked against the Python at the
     page's default pin (8.00 m both ways) and on the Tiirismaa slope
     (154.00 m both ways), against a median-of-nearby-object-bases guess of
     10.5 m at the first of those. */
  let ground = null, groundSrc = null;
  for (const cell of [10, 20, 50, 100]) {
    if (!px[cell]) continue;
    const step = cell * px[cell];
    const tx = Math.floor((e0 - GRID_E0) / step), ty = Math.floor((GRID_N0 - n0) / step);
    if (!(idx.tiles[cell] && idx.tiles[cell][tx + '_' + ty])) continue;
    const t = await getTile(cell, tx, ty);
    if (!t) continue;
    const col = Math.floor((e0 - t.oe) / t.cell), row = Math.floor((t.on - n0) / t.cell);
    if (col < 0 || col >= t.w || row < 0 || row >= t.h) continue;
    const v = t.v[row * t.w + col];
    if (v === NODATA) { ground = 0; groundSrc = cell + ' m tile, no data (sea)'; break; }
    ground = v / (t.scale || 1);
    groundSrc = cell + ' m terrain tile';
    break;
  }
  if (ground == null) throw new Error('no terrain tile covers the observer');

  const hobs = ground + msg.eye;
  const canopy = msg.canopy > 0 ? msg.canopy : 0;

  /* The sea horizon for this eye height, and the reason the far rings can be
     thrown away wholesale: terrain that cannot reach this angle cannot reach
     the horizon either, because every ray already sees sea (0 m N2000) at
     every distance and the sea's own maximum IS this angle. */
  const dipTan = -Math.sqrt(2 * Math.max(0.5, hobs) / REFF);

  /* --- the radial schedule, as flat arrays --- */
  const Dl = [];
  let prev = 0;
  for (const [outer, step] of SCHEDULE) {
    for (let d = prev + step; d <= Math.min(outer, rMax) + 1e-6; d += step) Dl.push(d);
    prev = Math.min(outer, rMax);
    if (prev >= rMax) break;
  }
  const NS = Dl.length;
  const D = new Float64Array(Dl), C = new Float64Array(NS);
  for (let i = 0; i < NS; i++) C[i] = D[i] * D[i] / (2 * REFF);

  /* Which ring each sample belongs to, and where the segments break. */
  const seg = [];
  for (let i = 0; i < NS; i++) {
    let r = 0;
    while (r < rings.length - 1 && D[i] > rings[r][0]) r++;
    if (!seg.length || seg[seg.length - 1].ring !== r) seg.push({ ring: r, i0: i, i1: i + 1 });
    else seg[seg.length - 1].i1 = i + 1;
  }

  /* --- gather the tiles, one rectangular block per ring --- */
  const tFetch0 = performance.now();
  let want = 0, skipped = 0, absent = 0;
  const blocks = [];
  const jobs = [];
  for (let r = 0; r < rings.length; r++) {
    const cell = rings[r][1];
    const outer = Math.min(rings[r][0], rMax);
    const inner = r ? rings[r - 1][0] : 0;
    if (inner >= rMax) break;
    const step = cell * (px[cell] || 512);
    const tx0 = Math.floor((e0 - outer - GRID_E0) / step);
    const tx1 = Math.floor((e0 + outer - GRID_E0) / step);
    const ty0 = Math.floor((GRID_N0 - (n0 + outer)) / step);
    const ty1 = Math.floor((GRID_N0 - (n0 - outer)) / step);
    const nx = tx1 - tx0 + 1, ny = ty1 - ty0 + 1;
    const arr = new Array(nx * ny).fill(null);
    const blk = { cell: cell, step: step, tx0: tx0, ty0: ty0, nx: nx, ny: ny, a: arr, maxm: -1e9 };
    blocks.push(blk);
    const have = idx.tiles[cell] || {};
    for (let ty = ty0; ty <= ty1; ty++) {
      for (let tx = tx0; tx <= tx1; tx++) {
        const meta = have[tx + '_' + ty];
        if (!meta) { absent++; continue; }
        const x0 = GRID_E0 + tx * step, y1 = GRID_N0 - ty * step;
        const dn = nearDist(e0, n0, x0, y1 - step, x0 + step, y1);
        if (dn > outer) continue;                 // corner-only overlap
        const df = Math.hypot(Math.max(Math.abs(e0 - x0), Math.abs(e0 - x0 - step)),
          Math.max(Math.abs(n0 - y1), Math.abs(n0 - y1 + step)));
        if (df < inner) continue;                 // wholly inside the finer ring
        /* max_m is in the index precisely so this decision happens before the
           fetch. At 60 km the refracted drop is 246 m, so a tile topping out
           at 40 m cannot show above a 39 m eye's sea horizon and is 250 kB
           that never needs to cross the wire. */
        if (dn > SKIP_MIN_M && bestTan(meta[2] + canopy, hobs, dn, df) < dipTan) {
          skipped++;
          continue;
        }
        want++;
        if (meta[2] > blk.maxm) blk.maxm = meta[2];
        jobs.push({ cell: cell, tx: tx, ty: ty, blk: blk, at: (ty - ty0) * nx + (tx - tx0) });
      }
    }
  }

  /* Eight at a time. The tiles are 20-60 kB each and the browser's own
     connection limit is six per origin, so more parallelism buys nothing and
     a serial loop costs a round trip per tile. */
  let done = 0;
  const pool = new Array(8).fill(0).map(async () => {
    for (;;) {
      const j = jobs.pop();
      if (!j) return;
      j.blk.a[j.at] = await getTile(j.cell, j.tx, j.ty);
      if ((++done & 15) === 0) self.postMessage({ id: msg.id, stage: 'tiles', done: done, want: want });
    }
  });
  await Promise.all(pool);
  const tFetch = performance.now() - tFetch0;

  /* --- the sweep --- */
  const tSweep0 = performance.now();
  const prof = new Float32Array(NBINS);
  const profD = new Float32Array(NBINS);
  const off = new Int32Array(NBINS + 1);
  let cap = NBINS * 24;
  let sD = new Uint16Array(cap), sA = new Int16Array(cap);
  let np = 0;
  let hits = 0;

  for (let b = 0; b < NBINS; b++) {
    off[b] = np;
    const az = b * BINW;
    const p = direct(msg.lat, msg.lon, az, rMax);
    const [e1, n1] = tm35(p[0], p[1]);
    const ue = (e1 - e0) / rMax, un = (n1 - n0) / rMax;

    let tanmax = -1e9, dmax = 0, lastA = -1e9;

    for (let s = 0; s < seg.length; s++) {
      const blk = blocks[seg[s].ring];
      if (!blk) continue;
      const i0 = seg[s].i0, i1 = seg[s].i1;

      /* Block early-out, r.horizon's z100 trick one level up: over the whole
         segment the best any terrain could do is its own ceiling at the near
         edge. If that is under the running maximum the segment cannot change
         it. On a clear ray this throws away most of the 90 km tail. */
      if (tanmax > -1e8
        && bestTan(Math.max(blk.maxm + canopy, 0), hobs, D[i0], D[i1 - 1]) < tanmax) {
        continue;                     // 0 m sea is still terrain, hence the max
      }

      const invStep = 1 / blk.step, invCell = 1 / blk.cell;
      const tx0 = blk.tx0, ty0 = blk.ty0, nx = blk.nx, ny = blk.ny, arr = blk.a;
      /* Which tile a sample falls in changes once every 512 samples in the
         10 m ring, not every sample -- the tile is 5.12 km across and the
         step is 10 m. So carry the tile and its square, and only redo the
         index arithmetic on the way out of it. Two workers running the same
         sweep alternately in the same tab, so machine noise hits both:
         median 132.5 ms this way against 169.5 ms recomputing the index
         every sample. */
      const step = blk.step;
      let cx0 = 1, cx1 = -1, cy0 = 1, cy1 = -1, cv = null, cw = 0, coe = 0, con = 0;
      for (let i = i0; i < i1; i++) {
        const d = D[i];
        const e = e0 + ue * d, n = n0 + un * d;
        let h = 0;
        if (e < cx0 || e >= cx1 || n <= cy0 || n > cy1) {
          const gx = (e - GRID_E0) * invStep | 0, gy = (GRID_N0 - n) * invStep | 0;
          cx0 = GRID_E0 + gx * step; cx1 = cx0 + step;
          cy1 = GRID_N0 - gy * step; cy0 = cy1 - step;
          const tx = gx - tx0, ty = gy - ty0;
          const t = (tx >= 0 && tx < nx && ty >= 0 && ty < ny) ? arr[ty * nx + tx] : null;
          if (t) { cv = t.v; cw = t.w; coe = t.oe; con = t.on; } else { cv = null; }
        }
        if (cv !== null) {
          const v = cv[((con - n) * invCell | 0) * cw + ((e - coe) * invCell | 0)];
          if (v !== NODATA) {                     // nodata is sea or abroad: 0 m
            h = v;
            if (canopy && h > 0.5) h += canopy;
          }
        }
        if (h > hobs + C[i] + d * tanmax) {
          tanmax = (h - hobs - C[i]) / d;
          dmax = d;
          hits++;
          const a = Math.atan(tanmax) * R2D;
          if (a > ANG_FLOOR && a > lastA + EPS_DEG) {
            if (np === cap) {
              cap *= 2;
              const nD = new Uint16Array(cap); nD.set(sD); sD = nD;
              const nA = new Int16Array(cap); nA.set(sA); sA = nA;
            }
            sD[np] = d / 10 | 0;                  // 10 m units, 655 km of range
            sA[np] = Math.round(a * 100);         // centidegrees, 0.01 deg
            np++;
            lastA = a;
          }
        }
      }
    }
    /* The last breakpoint is always recorded, eps or not, so the staircase
       ends exactly where prof does and an object at the far edge is tested
       against the same number the silhouette is drawn from. */
    const aEnd = Math.atan(tanmax) * R2D;
    if (aEnd > ANG_FLOOR && (np === off[b] || sA[np - 1] !== Math.round(aEnd * 100))) {
      if (np === cap) {
        cap *= 2;
        const nD = new Uint16Array(cap); nD.set(sD); sD = nD;
        const nA = new Int16Array(cap); nA.set(sA); sA = nA;
      }
      sD[np] = dmax / 10 | 0;
      sA[np] = Math.round(aEnd * 100);
      np++;
    }
    prof[b] = aEnd;
    profD[b] = dmax;
  }
  off[NBINS] = np;
  const tSweep = performance.now() - tSweep0;

  const stD = sD.slice(0, np), stA = sA.slice(0, np);
  self.postMessage({
    id: msg.id, ok: true,
    ground: ground, groundSrc: groundSrc, hobs: hobs,
    dip: -Math.atan(dipTan) * R2D,
    prof: prof, profD: profD, off: off, stD: stD, stA: stA,
    stats: {
      rays: NBINS, samples: NS, total: NBINS * NS, hits: hits, steps: np,
      tiles: want, skipped: skipped, absent: absent,
      msTotal: performance.now() - t0, msFetch: tFetch, msSweep: tSweep
    }
  }, [prof.buffer, profD.buffer, off.buffer, stD.buffer, stA.buffer]);
}

self.onmessage = e => {
  const msg = e.data;
  if (msg.base) BASE = msg.base;
  sweep(msg).catch(err => {
    self.postMessage({ id: msg.id, ok: false, error: String(err && err.message || err) });
  });
};
