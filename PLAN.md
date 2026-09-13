# azimuth — plan

A static page that names the recognisable objects on the horizon from a given position and gives
their exact bearings. PeakFinder for a country with no peaks: in Finland the horizon is broadcast
masts, power station stacks, water towers, observation towers, church spires, wind farms, a few
tall buildings, low named hills, and — from a coastal tower — lighthouses and named islands.
Estonia is included because the Gulf of Finland is where the geometry gets interesting.

Status: plan, nothing built.

Endpoints, counts and byte sizes below were probed live on 2026-09-13 and re-checked independently.
Where the two passes disagreed the corrected figure is used.

[TALL-STRUCTURES-NOTES.md](TALL-STRUCTURES-NOTES.md) is the sibling building-height project's own
write-up of the same MML classes, arrived at separately. Where it knows something this did not
reach — the Rakennukset 3D dead end, the city-model inconsistencies, the Kirkkonummi trap — it is
credited.

## 1. Why not an existing tool

- **PeakFinder** covers Finland and its terrain silhouette is fine — it uses Sonny's LiDAR DTMs,
  derived from MML's own open data. Labels come from OSM `natural=peak`; no man-made structure type
  is in its schema. Within 50 km of Helsinki that is 889 peak nodes with a median elevation of
  52.0 m and ten above 100 m, while the 326 m Kivenlahti mast has no label.
- **PeakVisor** is a 1 arc-second (~30 m) global DEM. Finnish relief is 40–60 m of local variation;
  30 m posting erases it.
- **udeuschle.de** renders Finland correctly, terrain only. Terms: free for private use, commercial
  use needs written consent.
- **HeyWhatsThat** has the right vocabulary (viewshed, path profile, refraction) but its elevation
  data covers 60°N to 54°S. Helsinki is 60.17°N.
- **SPLAT!** and **Radio Mobile** solve the same geometry and emit path loss, not object identities.
  Both GPL.
- Nothing Finnish does this; the closest is a hobby page mapping TV masts with no azimuth
  computation.

The geometry is about 80 lines of code. The work is the object catalogue.

## 2. Object categories

Range limits, standard refraction, `3.86·(√h₁ + √h₂)` km. From 2 m eye height: 29.6 km to a 40 m
water tower, 62.2 km to a 220 m mast, 74.6 km to a 327 m mast. From 30 m: 45.2 / 77.7 / 90.2 km.
Mast top to mast top at 327 m each is 138.4 km. 200 km is not reachable in southern Finland; only
from Lapland fells.

### Tier 1 — hand-curated, always labelled (~150)

Named objects, verified by hand, each pinned to whichever register holds its geometry: the big
broadcast masts (Tiirismaa 327.0 m, Kivenlahti 326.0, Teisko 324.0, Anjalankoski 322.0, Jyväskylä
322.0, Kerimäki 321.2, Lapua 320.3); the named towers (Näsinneula, Puijon torni, Pyynikin
näkötorni, Olympiastadion); the power station stacks (Kymijärvi 155.0 — the tallest chimney,
Vaskiluoto 151.7, Hanasaari 151.0, Tahkoluoto 151.0, Salmisaari 150.0, Suomenoja 149.3, Olkiluoto
2×105.0, Loviisa 105.5); the tallest buildings; the sea lighthouses; the Lapland fells.

This tier cannot be derived. Näsinneula, Puijon torni, Pyynikin näkötorni and the Lahti ski jumps
return nothing within 500–600 m across every MTK tower point class — they are building polygons
carrying no height. So in Tampere, Kuopio and Lahti the most prominent structure in the city is
missing from the registers.

### Tier 2 — registered structures, labelled when in range

| category | MTK | OSM | height sources |
|---|---|---|---|
| Masts | 8,422 | 9,529 (44% h) | MTK 44803 + AIP + OSM |
| Wind turbines | 1,893 | 1,868 (30% h) | AIP tip height + OSM |
| Chimneys | 1,300 | 913 (32% h) | MTK 45303 + AIP + OSM |
| Observation towers | 1,193 | 856 (9% h) | OSM + nDSM |
| Water towers | 360 + strays | 384 (19% h) | OSM + nDSM |
| Bell towers | 378 | — | nDSM |
| Churches | `rakennus` 42170 | — | curated + nDSM |
| Lighthouses, daymarks, edge marks | — | 178 (8% h) | Väylävirasto focal height |
| Buildings ≥ 50 m | — | 5,179 at 8+ storeys | CityGML + curated |

About 15,000 candidate features across the two, merging to ~13,500 distinct structures (§2,
Deduplication).

### Tier 3 — terrain

Named hills (`Kohouma`, MML Nimistö place type **1010210**, 88,233 records, plus `Kohoumaryhmä`
1010205, 4,414), fells, and islands (`Saari tai luoto` **1010110**, 50,299, plus island groups
1010105, 5,443). Both filtered by `scaleRelevance`. §3.5 and §3.9.

### Tier 4 — drawn, not labelled

The terrain silhouette; individual turbines inside a farm; minor skerries; anything below the
labelling threshold that still occludes.

### Excluded

Floodlight masts — 3,303 of Finland's 11,678 OSM mast/tower objects are sports-field and car-park
lighting, and at 58.6% they have the highest height-tag coverage of any category. Transmission
pylons (89,425), transformers (68,553), spar buoys (25,000), monuments under 20 m, approach lights
(1,242).

### The selection rule

A plain angular threshold does not work. "≥ 0.1° tall" at Helsinki centre admits 1,516 objects; the
busiest single degree holds 31; 119 of the 360 degree-bins hold five or more; the worst 60° field of
view contains 671. Raising it does not help cleanly — 0.15° leaves 907, 0.5° leaves 187 — and it
keeps the wrong things: the top of the apparent-size ranking at Helsinki is a 53 m chimney at 300 m
(11.29°) and the railway station clock tower (10.87°). Near foreground beats every horizon landmark
on angular size.

Two limits compete and cross over around 150 m of structure height. Below that angular size binds;
above it, curvature. For a 30 m observer:

| height | geometric range | 0.1° angular range |
|---|---|---|
| 20 m | 37.8 km | 11.5 km |
| 50 m | 47.6 km | 27.1 km |
| 100 m | 58.7 km | 41.0 km |
| 150 m | 67.3 km | 50.6 km |
| 200 m | 74.4 km | 58.4 km |
| 300 m | 86.5 km | 71.1 km |

Observer height moves the far end by nearly 2× (a 300 m mast reaches 58.7 km from 2 m and 91.4 km
from a 150 m deck), so the inclusion radius is computed per observer at runtime, not baked into the
catalogue.

The rule that works is a per-azimuth-window budget:

1. Drop anything closer than 3 km — foreground, not horizon.
2. Require the still-visible part to subtend ≥ 0.15° at the actual observer height.
3. Keep at most 3 labels in any 10° sliding window, ranked by apparent angular height.
4. Collapse wind farms to one centroid label at a 2 km single link — 1,868 mapped turbines become
   238 farms — and draw the individual towers unlabelled.

Output: Helsinki 711 pass → 104 labels; Tampere 297 → 105; Turku 374 → 127; Oulu 225 → 99; Kuopio
106 → 70; Vaasa 109 → 60; Ivalo 10 → 10. About one label per 3.5° almost everywhere, degrading to
nothing in Lapland where there is nothing.

### Deduplication

Nearest-neighbour distances across 15,034 candidate features: 3.6% have a neighbour within 5 m,
12.7% within 30 m, 23.6% within 50 m, 31.2% within 100 m. A 100 m merge collapses a third of the
catalogue.

Merge at 25–60 m, same class group only, with a height-compatibility veto of max(10 m, 15%). At
60 m, 2,646 of 13,166 non-turbine features collapse.

Two cases the threshold has to survive:

- **Old and new mast side by side.** 74 features above 80 m have a neighbour within 100 m; nine
  pairs are both ≥100 m. Jyväskylä has a 322 m broadcast mast with an unnamed 121 m mast 159.4 m
  away. After a 60 m merge, 53 sites still hold a genuinely different second structure.
- **A mast standing on a tower.** Puijo has an 80 m mast at 0.0 m from the 67 m Puijon torni. The
  answer is neither merge nor two objects but one object 147 m tall — a composite rule, not a
  distance rule.

### Names

MTK has no `selite` for `Masto` and none for `Savupiippu`, so it will never say a point is the
Anjalankoski mast. OSM names 83 of 9,529 Finnish masts (0.9%), 14 of 913 chimneys, 26 of 1,868
turbines; lighthouses are the exception at 61%.

Of roughly 10,000 masts, fewer than 100 have a name in any open source. Labelling only named
objects gives ~1,000 labels nationally; labelling everything gives 15,000 objects called "Mast".
Hence tier 1 by hand, and a fallback label of class plus nearest MML place name ("Masto,
Tiirismaa").

### Size

After merging and wind-farm collapse: 10,758 objects — tier 1: 322, tier 2: 1,345, tier 3: 6,118,
tier 4: 2,973. In espoo's columnar encoding, tier 1 alone is ~4 KiB gzipped, tiers 1–2 ~19 KiB,
tiers 1–3 (7,785 objects) ~83 KiB. Everything the page draws is under 100 KB gzipped, so one static
JSON, no tiling and no server.

## 3. Data sources

### 3.1 MML Maastotietokanta

MTK has point classes for these structures nationwide, as 3D points with N2000 ground Z since
spring 2025, available without an API key from the Funet mirror:

```
http://www.nic.funet.fi/index/geodata/mml/maastotietokanta/2025/gpkg/MTK-rakennus_25-04-03.gpkg
```

4,393,316,352 bytes, `Accept-Ranges: bytes`. It does not need downloading: a GeoPackage is SQLite,
so a b-tree page walker over HTTP Range pulls every tower table in 50 requests / 3.2 MB.

Counts from `gpkg_ogr_contents` of the live file:

```
masto              8,422     mastonkorkeus       7,634 rows / 4,282 masts
savupiippu         1,300     savupiipunkorkeus     490 rows /   325 chimneys
tuulivoimala       1,893     nakotorni           1,193
vesitorni            360     kellotapuli           378
muistomerkki       2,882     rakennelma         53,868
rakennus       5,627,446
```

`Lueminut.txt` in the same directory is the data dictionary in 17 KB.
`Maastotietokanta_kohdemalli_2023-01.xlsx` (67,076 B, 10 sheets, 483 numeric `kohdeluokka` codes)
is the machine-readable code list, parseable with `zipfile`. The prose catalogue is
`https://www.maanmittauslaitos.fi/media/31472/download` (1,771,153 B, 118 pages, 27.5.2025).

Heights, and the traps:

- Height is not an attribute. It is a separate text feature class — `Maston korkeus` 44803 and
  `Savupiipun korkeus` 45303 — joined by reference. Reading only `masto` suggests MTK has no
  heights.
- `korkeusarvo` is integer millimetres. 327000 = 327.0 m. `teksti` holds the same value as a metre
  string.
- Join from the height table. `mastonkorkeus.mastoviittaus → masto.mtk_id` resolves 4,282 masts;
  the forward pointer is non-null on 3,957 rows and resolves 3,609, losing ~320 masts.
- `mtk_id` is a signed 32-bit int (530 masto rows negative) while the reference column is an
  unsigned decimal string. Naive integer join matches 4,197/4,282; wrapping values ≥ 2³¹ by −2³²
  recovers 4,278.
- Heights are duplicated per map series, non-uniformly: 3,352 masts have 2 rows, 930 have 1 (ratio
  1.78). Deduplicate on `mtk_id`; do not assume a factor of two.
- The point Z is ground at the base, not the top. The schema has no height column; 8,408 of 8,422
  masts carry `korkeustarkkuus=201`, which the code table decodes as "KM 2 m" (interpolated from the
  bare-earth model); r(ground Z, mast height) = 0.136 over 4,278 pairs; Hanasaari's 151 m stack sits
  at z = 2.7 m. Top AMSL = z + korkeusarvo/1000.
- The height-text features have Z = 0.0 in 8,124 of 8,124 rows.
- The selection criterion is the completeness limit. Masts and chimneys are captured only if
  `>30 m and in the aviation obstacle register, or >60 m unconditionally`; heights are recorded for
  `all significant plus all ≥100 m`. Hence 51% and 25%. Below 100 m, whether an object has a height
  is a coin flip.
- `Tuulivoimala`, `nakotorni`, `vesitorni` and `kellotapuli` have no height in the data model at
  all. 3,824 positioned objects with no vertical extent.
- Names come from a generic `selite` layer (149,565 rows, in `MTK-muut`) with no foreign key — it
  joins by exact coordinate match on `sijainti_piste`; `dx`/`dy` are label draw offsets.
- Geometry columns are `sijainti_piste` / `_viiva` / `_alue`, not `geom`. Code written against a
  pre-2025 GeoPackage breaks.
- Densification vertices are flagged by Z = −999.999 on lines and polygons; on the point classes
  this is a no-op.
- `Kellotapuli` is 44600. 44500 is `Ilmarata`, an aerial cableway line class.

Positional accuracy from `sijaintitarkkuus` over all 8,422 masts: 5 m on 72.8%, 7.5 m on 17.5%,
15 m on 3.5%, with a 40 m tail of 1.0%. 5 m is 1.72′ of azimuth at 10 km and 0.29′ at 60 km —
smaller than the observer's own GPS error and below one screen pixel past 10 km. The 40 m tail is
worth a UI flag.

The shapefile route also works for **positions only, and silently loses the third dimension**: in
the per-sheet SHP mirror the tower layers are shape type `Point`, not `PointZ`, and every
`nakotorni` / `masto` / `savupiippu` / `vesitorni` record has `KORARV=0.0` and `KORKEUS=0.000`.
Positions are fine — observed `TASTAR` is 3,000 mm for towers and 5,000 mm for masts, so 0.017° of
azimuth at 10 km — but ground elevation must come from the GeoPackage, the GML or the OGC API. With
that caveat, the same five classes come out of
the per-sheet tiles (`.../2025/shp/L4/L41/L4131R.shp.zip`, ~12 MB a sheet) in 14 Range requests /
2.66 MB. There the height text has no key and is attached by a distance-capped spatial join on
identical coordinates — 6 of 12 masts matched in a test sheet, nearest unmatched height text 181 m
away, so no near-miss ambiguity. Either route works; the GeoPackage gives an explicit join key, the
shapefiles give smaller units of work.

Coverage in the capital region is better than nationally — 63% of chimneys and 76% of masts against
25% and 51% — so do not generalise from Espoo. Its bbox holds 21 chimneys and 82 masts, 75 with a
height.

Validation set from the sibling project, useful for checking computed azimuths:

| structure | height | ground | top N2000 | lat, lon |
|---|---|---|---|---|
| Kivenlahti radio mast | 326.0 | 43.148 | 369.1 | — |
| Suomenoja stack | 149.3 | 2.334 | 151.6 | 60.14904, 24.71755 |
| Tapiola heating plant | 77.2 | 25.489 | 102.7 | 60.17794, 24.79673 |
| Otaniemi | 75.0 | 3.029 | 78.0 | 60.18836, 24.82745 |

The 2025-04-03 release is the newest on Funet. A newer whole-country GeoPackage is at
`https://kartat.kapsi.fi/files/maastotietokanta/geopackage_maasto/mtkmaasto.zip`, 22,779,746,206
bytes, Last-Modified 2026-09-09.

The OGC API is key-gated: `avoin-paikkatieto.maanmittauslaitos.fi/maastotiedot/features/v1/` returns
401 with `WWW-Authenticate: Basic realm="API-key required to access"` and a zero-byte body. The key
is free and self-service from OmaTili, passed as `?api-key=` or as the Basic username with an empty
password. A bad key returns 403 via `?api-key=` but 401 via Basic, so 401 does not mean "no key
supplied". The mirrors make it unnecessary.

### 3.2 Aviation obstacle register

```
https://www.ais.fi/obstacles-suomi-finland   →  ef_efin_area1_obstdata_<date>.zip
```

91,761 bytes → a 521,206-byte semicolon CSV, 2,676 rows, every man-made obstacle ≥100 m AGL in
Finland. Wind turbine 2,109 · Mast 453 · Chimney 81 · Crane 17 · Building 6 · Tower 4 · Built
structure 3 · Pylon 2 · Pole 1. Heights min 100.3 m AGL, median 220.1, max 327.4.

- Heights are in feet (`HGT AGL (FT)`, `ELEV MSL (FT)`). The `Unit of measurement` column says
  `ft/m` on every row — that describes the schema, not the row. A 327 m mast reads 1073.
- The vertical datum is orthometric, ≈N2000. Differencing `ELEV MSL − HGT AGL` against a
  geoid-referenced DEM over 100 masts gives a median of −1.3 m; ellipsoidal would show +19 m.
  Cross-matched against MTK on 248 masts, `ELEV_MSL − (z_MTK + AGL)` has p50 = +0.3 m (p05 −1.1,
  p95 +1.2).
- Positions are good to ~1.4 m median, from cross-validation against 275 independently mapped OSM
  masts: p90 8.0 m, 91.3% within 10 m. The file's own accuracy metadata is NIL on 2,142 of 2,676
  rows while printing coordinates to 10 decimal places.
- About 20% of rows do carry quality metadata: 535 rows give horizontal accuracy 5 m (138) or 50 m
  (397), with confidence and integrity classes. This is the only per-object accuracy statement in
  the pipeline besides MTK's.
- No names. The only identifier is `EFINOB nnnnn`. Joining to OSM recovers a name for 6.4% of masts
  overall, 45.7% of the ≥200 m tier.
- It fills holes in MTK: 134 of 454 AIP masts ≥100 m (30%) have no MTK `masto` within 300 m,
  nearest neighbours at 628 m to 4.7 km; ~355–360 of 2,109 turbines likewise, depending on match
  tolerance (1,754 matched at 300 m, 1,761 at 400 m — the two halves do not sum cleanly, so state
  the tolerance). Chimneys are fine, 1 of 81 missing. Where MTK has the object the median match
  distance is 1 m; MML documents ANS Finland as its source for mast heights.
- New file every 28-day AIRAC cycle with ADDN/CHG/DEL delta workbooks. The filename embeds the
  effective date, so scrape `aipobst.htm` rather than hard-coding a URL, or it goes stale silently.
- Licence is not CC BY: free for further processing and research, but *"jälleenmyynti sellaisenaan"*
  — reselling the products as such — needs an agreement. Do not republish the CSV.
- The published extract cuts at 100 m AGL while the permit threshold is 60 m nationwide, so a
  60–100 m tier exists in the register and not on the website. See §11.4.

### 3.3 nDSM, for the classes with no registered height

MML/SYKE's normalised surface model (height above ground, decimetres), CC BY 4.0, keyless, via the
CSC GeoCubes WMS. `FORMAT=image/envi` returns raw little-endian uint16, so no GDAL is needed — a
64×64 m window comes back as exactly 8,192 bytes.

```
https://vm0160.kaj.pouta.csc.fi/ogiir?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap
  &LAYERS=ndsm_2025&STYLES=&SRS=EPSG:3067&BBOX=E-32,N-32,E+32,N+32
  &WIDTH=64&HEIGHT=64&FORMAT=image/envi
```

`STYLES=` is mandatory. `GetFeatureInfo` returns empty for this layer, and the OGC-API-Coverages
endpoint answers HTTP 200 with a 94-byte JSON error body rather than a 5xx — so do not branch on
the status code. Only the WMS ENVI route works.

Benchmarked against MTK's own heights, max(nDSM) within 32 m: masts n=70, median error −5.3 m,
within 2 m for 41%, underestimated by >20 m for 43%; chimneys n=60, median −0.6 m, within 2 m for
52%. Adding `ndsm_2024` as a fallback lifts masts to 55%/68%. When the lidar catches the top it is
essentially exact — the 327.0 m Tiirismaa mast reads 327.6 m — and the failure mode is a thin
lattice section lost to 2 m gridding. Solid structures do better than skinny ones, which is
convenient, because the skinny ones are the ones the registers already cover.

For the classes with no other source, sampling max-nDSM within 32 m: `vesitorni` median 31.4 m
(p10 21.9, p90 46.7), `nakotorni` 18.5 m, `kellotapuli` 25.2 m. These move by several metres with
the sampling radius (`vesitorni` reads 25.8 m at r=5 m), so the radius is part of the number and
must be recorded with it.

Guards: ship every nDSM height with a confidence flag; reject the sample if it is below 60% of any
independently known height; never let nDSM lower a height MTK or the AIP already gave. The median
error is near zero, so an unguarded pipeline looks fine in aggregate while being wrong per object.

If that turns out not to be good enough, the 5 pts/m² LAZ point cloud is chargeable at €0.026/km²,
minimum €26.69 — roughly €210–260 + VAT for a one-off national harvest over the ~8–10k 1 km² blocks
containing structures. Raw returns catch the lattice tops the grid drops.

### 3.4 Tall buildings

Ryhti is live and solves discovery, not height:

```
https://paikkatiedot.ymparisto.fi/geoserver/ryhti_building/ogc/features/v1/
```

3,797,652 completed buildings nationwide, no key. The host is `paikkatiedot` (plural);
`paikkatieto.ymparisto.fi` resolves and 404s every OGC path. Server-side CQL2 works, so the national
candidate set is four requests: `number_of_storeys >= 8` → 4,067; `>= 10` → 875; `>= 20` → 233;
`>= 50` → 142. Page with `startIndex`, not `offset` — the server ignores `offset` and re-serves page
one. Bulk `open_building.json.gz` is 331,279,887 bytes, regenerated at least weekly.

The top-end counts are corrupt. 142 buildings claim 50+ storeys in a country whose tallest has 35;
the rows read `number_of_storeys=79` with `gross_floor_area=79` — floor area typed into the storey
field. 382 of 875 above 10 storeys (43.7%) fail that junk test. Do not derive height from
`tilavuus` either: against Tampere's 3D model on four matched buildings it reads +11%, +23%, +36%,
+37% high, because volume is whole-building gross including podium while gfa/storeys assumes a
uniform footprint.

Ryhti geometry is a single centroid, 3.1–15.4 m from the true footprint centroid — 0.086° of azimuth
at 10 km, 0.86° at 1 km. Its licence is not asserted machine-readably on the endpoint (`<Fees>`
Maksuton, `<AccessConstraints>` Lisenssi); publisher Syke is confirmed. Check the avoindata.fi
record before shipping an attribution string.

A curated hand-list is the better answer. Wikipedia's completed list holds 36 buildings at or above
60 m across 34 ranked positions, of which 10 are outside Helsinki/Espoo/Vantaa — so the region the
espoo repo already covers is 72% by count. The tallest entries are the Kirkkonummi cable tower at
185 m and Näsinneula. Two or three hundred hand-verified rows cover every horizon-recognisable
building in the country.

Two more cities are worth integrating because they are cheap:

- **Turku**, a drop-in for espoo's `kind: wfs` CityGML parser.
  `https://turku.asiointi.fi/TeklaOGCWeb/WFS.ashx`, `bldg:Building_LOD2`, 57,158 buildings, ~0.75 GB
  for the city. The obvious host is wrong: `opaskartta.turku.fi` returns HTTP 301 with a 227-byte
  HTML stub, and many WFS clients do not follow redirects. N2000 confirmed — 359 coastal buildings
  floor at exactly 0.00 m. Parser deltas: EPSG:3877 (GK23, not Espoo's 3879/GK25 — both well-formed
  and 100 km apart if confused), repeated `<gml:pos>` rather than one `<gml:posList>`,
  `measuredHeight` uom is the URN `urn:adv:uom:m`, and a bare `resulttype=hits` returns
  `numberOfFeatures="100"` — the default `maxfeatures`, which looks like a real answer.
- **Tampere**, a new kind giving roof and plinth directly.
  `https://geodata.tampere.fi/geoserver/wfs`, layer
  `julkinen:mml_rakennusten_osat_3d_polygon_kaytossa`, 68,984 parts, EPSG:3878 (GK24), with
  `kattokorkeus`, `kivijalkakorkeus` and a per-feature `tarkkuus_z_m` no other Finnish source
  publishes. N2000 confirmed against Näsijärvi at 95.0 m. Group by `vtj_prt` and take max(roof) −
  min(plinth): Hotel Torni is 4 features, one tower is 13. Filter on the difference, never on
  `kattokorkeus` alone — Tampere's terrain is 80–150 m N2000, so `kattokorkeus > 60` matches 67,525
  of 68,984. `kivijalkakorkeus` uses 0 as a missing-value sentinel on 59 features (never NULL), and
  those produce phantom 143–161 m towers at the top of the ranking;
  `(kattokorkeus - kivijalkakorkeus) > 40` returns 104, and adding `AND kivijalkakorkeus > 0`
  returns the real 75.

Stop there. Vantaa has ground Z but no roof surface, and stores `kerrosluku`, `tilavuus` and
`kokonaisala` as `xsd:string`, so `kerrosluku >= 12` returns a 2-storey building lexicographically —
cast all three. `rakval:ValmisRakennus` returns 401 with a byte-identical error body in all six
municipalities tested. Overture's Finnish heights are 100% re-exported OSM.

### 3.5 Islands, coastline, sea marks

MTK has no island feature class. Finnish islands are the interior rings of the `meri` (36211) and
`jarvi` (36200) polygons in `MTK-vakavesi_25-04-03.gpkg`, 2,868,965,376 bytes, Range-readable, plain
SQLite. The shapefile distribution contains no water polygons, only shoreline polylines, so the
GeoPackage route avoids polygonisation.

Names from MML Nimistö: ~56,000 named islands. The place-type code depends on the distribution —
`paikkatyyppiKoodi = 350` in the older vocabulary, `placeType 1010110` ("Saari tai luoto", 50,299)
plus `1010105` (island groups, 5,443) in the current XSD. Same data, two spellings; check which one
the file in hand uses. The noise filter is already in the data as `mittakaavarelevanssiKoodi`, the smallest map
scale at which MML intends the name to be drawn:

```
1:1,000,000 →     55        1:100,000 →  9,932
1:500,000   →    494        1: 50,000 → 14,106
1:250,000   →  2,286        1: 25,000 → 29,280
```

The 2,835 islands at 1:250,000 or coarser are the useful set — Suomenlinna, Isosaari, Örö, Utö,
Kökar. The 29,280 at 1:25,000 are skerry noise. The same field works for hills.

Island names are not unique: Kalliosaari ×359, Isosaari ×320, Selkäsaari ×284. "Bengtskär" returns
two islands 67 km apart; "Söderskär" returns five. Disambiguate by coordinate.

MTK shoreline accuracy on a sampled coastal tile, from `TASTAR`: mostly 4–7 m, but the tail runs to
20, 30, 40 and 100 m classes. The worst class present is 100 m.

Lighthouses are better targets than islands, and Väylävirasto publishes them key-free under
CC BY 4.0 at `https://avoinapi.vaylapilvi.fi/vaylatiedot/ogc/features/v1/` (329 collections, CRS84
bbox queries, GeoJSON). Finland has 43 sea lighthouses (`Merimajakka` — the type string is not
`Majakka`, which returns a healthy-looking zero), 38 daymark towers (`Tunnusmajakka`, where
Söderskär and Porkkala live), and 197 `Reunamerkki`, the concrete offshore caisson beacons standing
alone in open water. About 280 named, surveyed, isolated built landmarks, each with a focal height
parseable from the `loistojen_tiedot` string (Bengtskär: `Korkeus vedestä: 51, Korkeus maasta: 46`).

Those heights are the light's focal plane above mean water and above the rock, not N2000 and not the
tower top. And the GeoJSON returns `MultiPoint`, not `Point`, for every aid.

Åland needs no special handling — MTK tiles reach Signilskär, Nimistö holds 4,961 named Åland
islands, its five lighthouses are in Väylävirasto's own layer — but also query
`turvalaitteet_muut_vaylanpitajat`, where the Åland Government owns 662 aids.

Islands should not be drawn from a DEM. From a 30 m observer at 40 km, 24.7 m of every island is
below the horizon; a 20 m island from 2 m at 20 km shows 5.5 m, subtending 0.94′. An island is a
wide, sub-arcminute-tall smear — a 1 km island spans 2.86° at 20 km. The azimuth extent is the
signal and the height is essentially zero. Draw each island as its plan outline projected to a
start/end azimuth pair, clipped at the horizon line, with the name as the payload. Reserve DEM
silhouettes for observers above ~100 m looking under 40 km, and for lake islands where curvature
vanishes.

### 3.6 Elevation model

GeoCubes, keyless, arbitrary bbox and resolution, resampled server-side:

```
https://vm0160.kaj.pouta.csc.fi/geocubes/clip/{res}/{layer}/bbox:{xmin},{ymin},{xmax},{ymax}/{year}
```

A 10×10 km Helsinki clip of `km2` at 10 m returns 1,598,074 bytes in 1.1 s. Validated by decoding
pixels: a Lapland clip maxes at 719.69 m where Ylläs is 718, and a whole-Finland 50 m clip at
1324.16 m where Halti is 1324 — so N2000, not ellipsoidal. Every MML endpoint for the same data is
401 without a key.

- KM2: 10,408 tiles, 216.3 GB. KM10: 1,523 tiles, 9.58 GB. Accuracy 0.3 m in Class I.
- KM10 is not a downsampled KM2 — it is contour-derived from the Topographic Database. Against KM2
  resampled to the same grid: stdev 1.129 m, p99 +2.97, max 28.36, 23.1% of cells off by >1 m.
  Resampling KM2 is better.
- 10 m is the right resolution. Ray-casting 360 azimuths against a 2 m grid: 10 m costs mean 0.0134°
  / p90 0.0285°; 30 m costs mean 0.0477° / max 0.30°.
- Do not resample by averaging. It is GDAL's default and biases the horizon down by 0.0279° at 10 m
  and 0.0977° at 30 m, because it shaves ridge crests — which makes the page claim visibility
  through hills. Nearest is −0.0126°; max-pooling is +0.0172° and conservative.
- Ship int16 metres + horizontal delta + zlib, not terrain-RGB: 1,230–3,083 B/km² against
  14,170–21,464, because terrarium's low byte is high-entropy fractional noise. All of Finland at
  10 m is ~0.67 GB.
- Open sea is nodata (−9999), not zero — a 10×10 km patch of open Gulf of Finland is 100.00% nodata.
  Substitute 0, or every ray toward Estonia reads a 10 km trench. The Turku archipelago is 0.00%
  nodata, so handling is not uniform; use the GeoCubes `meri` mask to tell sea-nodata from a gap.
- The GeoTIFFs declare no vertical datum. GeoKey 4096 is absent.

Forest is the largest correctness risk. DSM − DTM over a forested interior block: median 4.35 m,
p75 15.27 m, p90 21.37 m, 25.7% of cells above 15 m; Finland is three-quarters forest. In angular
terms a 25 m spruce canopy subtends 2.86° at 500 m, 0.72° at 2 km and 0.29° at 5 km, while a 327 m
mast at 41 km sits at 0.29° and a 150 m mast at 30 km at 0.17°. For any observer inside or behind
forest the treeline at 2–5 km hides everything on the true horizon. Add the GeoCubes `pintamalli` or
`ndsm` layer as an occlusion overlay, or add 20–25 m to forested land cover, which MTK supplies as
`maastokuvio` polygons. This also cuts the other way for the observer: the page has to know whether
the user is above the canopy.

Mapterhorn already publishes Finland as terrarium tiles derived from this same 2 m model (its
catalogue names "National Land Survey of Finland 2025, downloaded via GeoCubes", CC BY 4.0) at
`https://tiles.mapterhorn.com/{z}/{x}/{y}.webp`, Estonia at 1 m. That reuses the PMTiles-over-Range
workflow espoo already has.

Rejected: Copernicus GLO-30 is a DSM and reads 15–25 m high over Finnish forest. EU-DEM v1.1 was
withdrawn in January 2024. FABDEM is CC BY-NC-SA — non-commercial and share-alike.

### 3.7 Estonia

ETAK, key-free WFS at `https://gsavalik.envir.ee/geoserver/etak/wfs`. `etak:e_402_korgrajatis_p` is
a 3,400-record national tall-structure register with `korgus` in metres populated on every record —
Sidemast 1,305, Korsten 843, Torn 834, Valgusmast 418, max 349 m, 188 named, updated daily.
`etak:e_401_hoone_ka` has `korgus_m` on 97.8% of buildings. Estonia has in one WFS what Finland
needs three registers and a lidar surface model to assemble.

Estonia also ships islands as a ready-made layer: `tuletiskihid-saared_gpkg.zip`, 6,745,771 bytes,
opens with stdlib `sqlite3` to a `saared` table of 7,967 island polygons with `nimetus`, `pindala`,
`ymbermoot`.

Estonian AIP Area 1: 417 surveyed obstacles with top elevation AMSL, natively in EH2000 — eAIP
GEN 2.1 states this rather than the EGM96 ICAO usually mandates. Parse the bundled KMZ's `doc.kml`;
the `.xls` is genuine BIFF8 OLE. Where both sources have an object the AIP wins (Teletorn: ETAK 314,
AIP 314.2; Iru: ETAK 200, AIP 202.7).

EH2000 and N2000 are the same datum for this purpose — both EVRS realisations at the Fennoscandian
uplift epoch 2000.0, tied to Amsterdam, differing by millimetres. Concatenate without transformation.

Total Estonian payload ~20 KB gzipped.

#### Tallinn TV Tower

Two corrections to the folk version, both material. Helsinki–Tallinn is 76.31 km from Kaivopuisto to
the Teletorn (Vincenty, forward azimuth 182.813°), not 80. And the top is 338.3 m AMSL, not 314 plus
a guessed 40 m base — the AIP gives 1110 ft elevation over 1031 ft height, so the ground at
Kloostrimetsa is 24.1 m.

With those, at k = 0.13 the minimum observer height to see the tip is 2.39 m. The tower is above the
horizon from ordinary Helsinki high ground under ordinary refraction; no mirage is required. But:

- At 1.7 m on the Helsinki shore the grazing ray reaches 347.2 m, above the tip. Not visible. It
  clears from any rock.
- From Kaivopuisto (20.6 m), 101 m of tower is above the horizon — the steel antenna mast only,
  ~3 m wide, subtending 8 arcseconds. The eye resolves about 60.
- From Harmaja, Vuosaarenhuippu, Malminkartanonhuippu or the Majakka roof, the 30 m observation-deck
  disc clears, subtending 1.2–1.5′ — at the naked-eye limit, easy in binoculars.
- The ray from Kaivopuisto passes 16.6 m above the sea at 7.66 km, between Katajaluoto and Harmaja.
  Curvature is not the occluder for the Helsinki case; Finnish islets, their trees and their beacons
  are. This is why the Finnish side needs a real terrain-and-object sweep, not a curvature test.
- The better vantage point is Porkkala. From Rönnskär (25 m) the Teletorn is 55.82 km at azimuth
  150.518°, tip +0.1032° above horizontal, 246 m of tower visible subtending 15.17′.

The Pakri wind farm is a more legible target than the tower: ~30 AIP obstacles at 149–167 m AMSL
clustered at 59.36–59.38 N, 56–59 km from Jussarö in a 1.5° azimuth fan at 7.6–8.4′ each, visible
from a 10 m observer.

Estonia's 300 m club: Koeru 349 m AGL / 455.4 AMSL, Valgjärve 347 / 537.7 (highest man-made point in
Estonia, never visible from Finland at 210 km), Teletorn 314.2 / 338.3, Kohtla 253.9 / 304.5
(104.6 km from Haapasaari, 4 m of clearance from a 100 m observer — real under ducting, not
otherwise).

Estonian islands are too low to be visible from Finland: Keri is hidden by 47 m at 51.66 km from
Kaivopuisto, and Vaindloo, Naissaar and Aegna likewise. The masts and turbines carry it.

### 3.8 OpenStreetMap

Included in the merged catalogue as of the §8 decision. Counts inside the Finland admin area, with
`height=*` fill:

```
man_made=mast              9,529   44.2%      tower:type=communication  6,144
man_made=tower             2,149   14.2%      tower:type=observation      856    9.5%
man_made=chimney             913   31.9%      man_made=water_tower        384   19.3%
generator:source=wind      1,868   30.1%*     man_made=windmill           285
man_made=lighthouse          178    8.4%      man_made=communications_tower 13
                                              tower:type=lighting       3,304   EXCLUDE
```

\* combining `height` (161) and `height:hub` (455). Total across the app's classes: 15,034 features.
Buildings: 5,179 at 8+ storeys (more than Ryhti's 4,067, and hand-mapped rather than
register-corrupted), plus a `height` tag on 21,742 buildings.

Where OSM and the obstacle register overlap they agree well: on 158 matched pairs OSM `height` minus
AIP `HGT AGL` has median −0.2 m with 76% within 2 m, and positions agree to a median of 1.4 m. So
OSM heights can be trusted at face value where a register value is missing. Only 3 of 4,900 height
strings failed to parse (`75 (estimate)`, `61.0;61`, `10;7.5`).

Where it is weaker: 178 of 453 AIP masts ≥100 m (39%) have no OSM mast or tower within 300 m — but
those have a median height of 140 m and only seven are ≥200 m, so OSM has essentially all the
landmark masts and misses the 100–150 m tier. The register stays the completeness authority.

Class medians, from 4,897 real OSM measurements, usable as the last-resort fallback with an
`estimated` flag: masts 40 m, chimneys 50 m, water towers 34 m (max 67, none above 75), observation
towers ~20 m, lighthouses 17 m. The tail is thin — the whole country has about 40 structures over
150 m.

Traps:

- `tower:height=*` has **zero** uses in Finland. Any guide suggesting it is wasted code.
- `ele=*` is under 2% everywhere, so OSM never supplies ground elevation. Take that from MTK's point
  Z or the DEM.
- `tower:type=lighting` is 3,304 sports-field and car-park floodlights with the *highest* height
  fill of any category (58.6%). An unfiltered "tall OSM structures" query is mostly these.
- Names are sparse — masts 0.9%, chimneys 1.5%, turbines 1.4% — though towers reach 26%, water
  towers 33% and lighthouses 61%.
- Mirrors disagree and fail. Use a mirror list with backoff, cache the response in `raw/`, and query
  the Finland admin area rather than a bbox (§9).

### 3.9 Named hills, fells and lookout towers

MML Nimistö, key-free in bulk as `places_YYYY_MM.zip` from the kapsi mirror — 45.7 MB zipped, 1.16 GB
of XML, 804,912 records, three snapshots a year. The free MML key is only needed for nightly
freshness through the OGC API.

**The classification stops at "Kohouma".** There is no place-type code for tunturi, vaara, mäki,
harju or kukkula; all 88,233 hills are `1010210`, whose own description reads *"tunturi, vaara, mäki,
harju tms."* The sub-kind is recoverable only from the name's suffix: mäki 27,584, vuori 10,198,
vaara 9,884, kallio 9,486, kangas 4,718, harju 2,947, selkä 1,197, várri 385, rova 269, oaivi 197,
kukkula 147, tunturi 140, čohkka 87, kero 82 — and 17,876 (20%) with no recognised suffix.

`placeElevation` is populated on 100% of records and is N2000. Distribution over Kohouma: median
126 m, p90 250, p99 451, max 1,326. Above thresholds: 16,532 ≥200 m, 4,674 ≥300 m, 592 ≥500 m,
26 ≥1,000 m. Every Kohouma at or above 500 m lies north of y = 7,400,000.

**It is the DEM value at the name point, not the summit** — measured against the 10 m N2000 model
over 156 southern hills, median agreement +0.3 m (p10 −1.2, p90 +1.7), and again in the Pallas fells,
median −0.7 m. That settles the datum question too.

**So the name point needs snapping, but only a little.** Over those 156 southern hills, the DEM
maximum within 100 m is a median 2.9 m higher than the name point (p90 10.6 m, 62% exceeding 2 m).
Within 500 m it is 10.0 m higher — but the distance to that maximum has median 357 m and p90 496 m,
pinned to the search radius, which means the search has walked onto a *neighbouring hill*. Snap
within 100–150 m, keep both positions, and flag any snap over ~150 m. Make the radius
relief-dependent: in Lapland the name point is essentially on the summit (median +1.1 m at r=100),
so the flank problem is a southern, low-relief-forest problem, not a national one.

Two failure modes snapping does not fix:

- **Massif names.** `Bállasduottar / Pallastunturi` (783 m) and `Taivaskero` (806 m) are separate
  Kohouma 500 m apart; snapping sends both to the same summit and merges the labels. `Koli` is a
  Kohouma at 169 m with the *highest* notability rank, while the actual summit Ukko-Koli is a
  separate Kohouma at 341 m with the *lowest*.
- **Homonyms.** `Halti` resolves to the 1,326 m fell in Enontekiö and to a 66 m hill in another
  municipality; `Koli` likewise. Scope every name lookup by municipality code or coordinate.

**Use `scaleRelevance` for label filtering before reaching for prominence.** MML's cartographers
already ranked these: 19 nationally at 1:2M, 70 at 1:1M, 876 at 1:500k, 4,073 at 1:250k, 17,961 at
1:100k, and the median elevation rises monotonically with rank (110 m → 538 m), so the field encodes
notability rather than size. The 70 at 1:1M or better are exactly the list a Finn would write: Halti
1326, Saana 1024, Taivaskero 806, Pallastunturi 783, Ylläs 719, Pyhätunturi 538, Levi 525, Ruka 491,
Korvatunturi 457, Iso-Syöte 428, Lauhanvuori 222, Koli 169, Orrdals klint 127 (Åland's highest).
Only four lie south of y = 7,000,000.

Nimistö also carries real Swedish and Sami parallels: over the Kohouma, 6,323 Swedish, 1,672 North
Sami, 754 Inari Sami, 96 Skolt Sami; some fells carry four names at once.

**Prominence as a second axis, computed but not overdone.** The standard descending-flood union-find
runs in pure stdlib: measured at 33.5 s and 719 MB for one 2,400×1,200 tile (~250 bytes/cell). That
does not scale — national coverage at 10 m is 3.4e9 cells, extrapolating to ~11 hours and ~850 GB.
Max-pool to 50 m instead (1.35e8 cells, ~30 min, ~1.5 GB with array-backed storage): max-pooling
preserves summit elevations exactly and only raises cols, so it under-estimates prominence by at most
the intra-cell relief, 1–3 m in Finland. Threshold around 30 m in the south and 100 m in Lapland, and
flag any component still touching a tile edge as unresolved rather than publishing a zero — on the
Pallas tile the algorithm correctly left exactly one component open, Taivaskero, whose real ~509 m
prominence is set by a col hundreds of kilometres away.

Ranking by elevation alone is wrong at the very top: **Halti is Finland's highest point at 1,326 m
and has about 44 m of prominence**, because the true summit is across the Norwegian border. No
openly licensed Finnish prominence list exists — OSM carries `prominence=*` on exactly one Finnish
peak.

OSM is ~12× sparser here and not the base: 6,807 `natural=peak` (41% with `ele`), 282 `natural=hill`.
79% of OSM peaks have a Nimistö Kohouma within 500 m (median offset 49 m) and where both name the
place the spelling is byte-identical 94% of the time. `natural=ridge` is a trap — 408 features, `ele`
on zero of them. Finnish harju ridges come from the 2,947 Kohouma with a `-harju` suffix.

**Lookout towers** are both observation points and targets. MTK class 45000 gives position and ground
Z (from the GeoPackage or OGC API, never the shapefile mirror — §3.1). OSM adds names: 738
`tower:type=observation`, but `ele` on 4 and `height` on ~66, so platform elevation has to be
synthesised from the DEM plus an assumed 15–25 m. About half the OSM entries are *lintutorni* bird
hides, 5–15 m in flat wetland — legitimate observation points, useless as horizon targets, so filter
by name substring or `tower:construction`.

MTK class **52210 `korkeuspiste`** (spot height, 3D point) is the authoritative summit-elevation
source where one exists, and worth preferring over a DEM maximum.

## 4. Geometry

### 4.1 Azimuth

Geodesic forward azimuth in geographic coordinates: ~35 lines of Vincenty inverse on GRS80,
validated to the millimetre against the standard WGS84 check distances. Measured at 0.557 µs per
pair in browser JS, so 200,000 objects cost 111 ms and a realistic 150 km candidate set costs
1–11 ms. Nothing cheaper is worth it.

The alternatives, from Helsinki:

| method | error |
|---|---|
| Vincenty / Karney | reference |
| spherical great circle | systematic 0.048° at 60°N, distance-independent |
| equirectangular | 0.28° to Lahti, 0.48° to Tampere, 1.55° at 198 km |
| TM35FIN grid bearing, no convergence | 1.79° in Helsinki, 6.50° on Åland |

Grid convergence is the main trap. In ETRS-TM35FIN, γ ≈ (λ − 27)·sin φ runs from −6.50° at Eckerö to
+4.07° at Ilomantsi, a 10.6° spread; at 30 km that is 3.4 km of lateral offset. It is invisible in
capital-region testing, because Espoo's WFS is EPSG:3879 (GK25) where convergence at Helsinki centre
is 0.05°, while every national dataset is EPSG:3067.

Reproject to lat/lon at the parser and never touch a projected CRS in the bearing path.

### 4.2 Elevation, curvature, refraction

For a sample or object top at geodesic distance *d* and height *h* (N2000), observer eye height
*h_obs*:

```
α = atan2( h − h_obs − d² / (2·R_eff),  d )        R_eff = R / (1 − k),  R = 6 371 008.8 m
```

Against the exact spherical solution the parabolic approximation differs by 0.03″ at 100 km and
0.75″ at 300 km — far below the refraction uncertainty, so no higher-order term is worth adding.
Keep the `atan`; the small-angle form costs 4.4″ at 1 km.

Refraction dominates the error budget. Swinging k from 0.07 to 0.25 moves the apparent elevation by
58″ at 20 km, 146″ at 50 km, 291″ at 100 km — for a 327 m mast at 100 km, 60% of its own angular
height. Everything else (the approximation at 0.03″, the chord/arc difference, geoid slope at
4–17″) is at least an order of magnitude smaller.

The two conventions differ: k = 0.13 gives R_eff = 7,323 km, while the maritime 7/6·R = 7,433 km
corresponds to k = 0.1429.

So refraction is a control, not a constant. Compute the terrain profile once at k = 0.13 and each
object's elevation three times, at 0.07 / 0.13 / 0.25 — three multiplies — giving four states:

- **Solid** — visible even at k = 0.07.
- **Normal** — visible at 0.13.
- **Marginal** — hidden at 0.13, visible at 0.25. Dashed, with a note that it needs a strong
  temperature inversion over cold water.
- **Mirage only** — behind a toggle.

### 4.3 Datums

Everything N2000, nothing ellipsoidal. The FIN2023N2000 quasigeoid separation, parsed from the grid:
min 14.310 m, max 32.208 m, mean 20.157 — Helsinki 17.611, Kilpisjärvi 30.093. A 19 m mixup is 196″
of elevation error at 20 km, comparable to the whole refraction band.

Do not use the phone's GNSS altitude, and not only for accuracy: iOS and Android disagree about what
it means. The W3C spec says ellipsoidal and Android complies; WebKit assigns `CLLocation.altitude`,
which Apple documents as mean sea level (they added `ellipsoidalAltitude` in iOS 15 for exactly this
reason, and WebKit does not use it). W3C issue #210 is open. Snap the observer to the DEM and add an
explicit eye height.

### 4.4 Error budget

| source | 1 km | 10 km | 50 km | 100 km |
|---|---|---|---|---|
| 10 m position error → azimuth | 0.573° | 0.057° | 0.011° | 0.006° |
| 1 m height error → elevation | 206″ | 20″ | 4.1″ | 2.1″ |
| refraction band → elevation | 2.9″ | 29″ | 146″ | 291″ |

Near objects: coordinate accuracy dominates, refraction is irrelevant. Far objects: the reverse.
Sub-metre coordinates only matter inside ~10 km, and 10 m of GPS error exceeds 0.1° of azimuth only
for targets closer than 5.7 km.

What can be claimed: ~0.014° for targets beyond 30 km with 5 m GNSS, 0.08° at 5 km, and 0.24° at
5 km in an urban canyon with 20 m GNSS. All of it true azimuth, computed geodesically — there is no
magnetic path in this app (§11.1), so declination, crustal anomaly and magnetometer error never
enter the budget.

## 5. Architecture

Same shape as espoo, for the same reasons: `build.py` in pure Python 3 stdlib — no GDAL, no node, no
database, resumable fetch — plus a self-contained `index.html`.

**Bulk data does not live in the repo.** Downloads and generated tiles go to a cache directory named
by `AZIMUTH_CACHE`, defaulting to the platform cache directory. The repo directory holds only text
and the one small generated file the page fetches:

```
<repo>                          $AZIMUTH_CACHE
  PLAN.md                         raw/             download cache, resumable
  build.py                        terrain/         int16 DEM tiles
  index.html                      basemap.pmtiles  ~100 MB per region
  serve.py
  pmtiles.js                      (not version controlled, and safe to delete —
  style.json                       build.py re-fetches all of it)
  landmarks.csv
  objects.json      generated, <100 KB, gitignored
```

Sizes, so the split is justified rather than superstitious: the MTK GeoPackages are read over HTTP
Range and never land whole, but Turku's CityGML is ~0.75 GB, Ryhti's bulk export 331 MB, and the
Overpass and nDSM caches a few hundred MB — call `raw/` 1–2 GB. Finland at 10 m as int16 tiles is
~0.67 GB. A regional z15 basemap is ~106 MB. Two to three gigabytes, all re-downloadable.

The separation matters beyond tidiness: a repo directory can easily sit inside a synced folder, and
a couple of gigabytes of GML appearing there is a slow, annoying mistake to undo.

`objects.json` stays in the repo directory despite being generated: it is what the page fetches, it
is under 100 KB gzipped, and it is harmless to sync.

`serve.py` therefore serves two roots. It is espoo's Range-capable handler with `translate_path`
overridden so `/terrain/…` and `/basemap.pmtiles` resolve into `AZIMUTH_CACHE` and everything else
into the repo directory. A directory symlink or junction would be less code and is the wrong answer:
sync clients follow them and copy the target anyway.

`build.py` prints the resolved cache path on startup, and stops if it is unwritable rather than
falling back to the repo directory.

### 5.1 build.py

A `SOURCES` registry keyed by source, one adapter per `kind`, normalising into one schema — the same
seam espoo already proved.

```
kind: gpkg_range   MTK tower point classes over HTTP Range out of the Funet GeoPackage
kind: aip_csv      Fintraffic Area 1 obstacles (scrape aipobst.htm for the current cycle)
kind: wms_envi     GeoCubes nDSM, one 64x64 window per unresolved object
kind: wfs          Turku CityGML (espoo's parser, EPSG:3877, <gml:pos>)
kind: wfs3d        Tampere kattokorkeus/kivijalkakorkeus, grouped by vtj_prt
kind: ogcapi       Ryhti candidates, Vaylavirasto aids, Estonian ETAK
kind: overpass     OSM masts/chimneys/towers/turbines/islands, mirror list + raw/ cache
kind: curated      landmarks.csv
kind: geocubes     terrain clips
```

Every object normalises to:

```
lat, lon          WGS84, never a projected CRS past the parser
ground_m          N2000 elevation at the base
height_m          structure height above that ground
top_m             ground_m + height_m
width_m           horizontal cross-section, for the silhouette rectangle
cat               mast | chimney | watertower | obstower | belltower | turbine |
                  building | lighthouse | seamark | hill | island
name              may be null
tier              1 | 2 | 3 | 4
src               provenance per attribute -- position and height can differ
conf              height confidence: registered | lidar | estimated
```

`conf` and per-attribute `src` drive the UI (§6.2) and make the licence separation in §8
enforceable.

### 5.2 Objects are not terrain

At 30 km a 3 m guyed mast column subtends 20.6″ and a 0.1° azimuth bin is 360″. Burning a mast into
a raster cell either loses it (averaged) or draws it 17× too wide (cell set to the mast top). At
100 km it is 58×.

So point objects are never ray-cast. Their azimuth and elevation are closed-form geodesy from two
coordinates. Ray-casting is only for terrain, and only to produce the occlusion profile.

Measured in browser JS on this machine, plain `Float32Array`, no WASM:

| workload | desktop | phone (est. 3–5×) | 4 workers |
|---|---|---|---|
| 3600 rays × 3300 samples (11.88 M) | 111–155 ms | 0.4–0.6 s | 0.1–0.2 s |
| 7200 rays | 220–284 ms | 0.8–1.2 s | 0.2–0.3 s |
| canvas 2D repaint, 3600 cols, forced flush | 2.78 ms | ~14 ms | — |
| Vincenty inverse, 200k pairs | 111 ms | ~0.4 s | — |

WebGL and WASM buy nothing here. PeakFinder ships 5,817,521 bytes of WASM plus 262,950 of glue and a
747,530-byte data blob before drawing a pixel, which is a port of their existing C++ engine rather
than a requirement.

Use GRASS r.horizon's inner loop, which compares heights rather than angles — one multiply-add and
one compare per sample instead of a divide, and better behaved numerically:

```
if (h > h_obs + d*d/(2*R_eff) + d*tanmax)  tanmax = (h - h_obs - d*d/(2*R_eff)) / d
```

Plus its `z100` block-max early-out, generalised to a maximum mipmap. Beyond ~60–70 km the horizon
for a low observer is a geometric arc: nothing outside Lapland exceeds ~350 m N2000 and the
refracted drop at 100 km is 683 m. So the terrain sweep can stop at 60–80 km for a low observer, and
the 40–150 km DEM ring can be dropped from the payload below ~50 m eye height.

Sampling: 3600 rays at 0.1° with a fixed-ring radial schedule (10 m step to 5 km, 25 m to 20 km,
50 m to 60 km, 100 m beyond) = 3,300 samples/ray. 7200 rays is not worth it — Finnish terrain has no
0.05°-scale structure at range. Sub-bin precision comes instead from placing objects at their
analytic azimuth and interpolating the profile between adjacent bins: 0.001° object placement at
0.1° terrain cost.

DEM streaming in distance rings, because resolution beyond the ray spacing is wasted (rays are
17.5 m apart at 10 km, 174.5 m at 100 km):

```
0–10 km    z13   9.5 m/px    53 tiles
10–40 km   z11  38.0 m/px    50 tiles
40–150 km  z9  152.1 m/px    43 tiles
                             146 tiles, 13.9 MB on the wire, 19 MB as int16
```

A flat z13 disc of 200 km radius would be 21,222 tiles and 2.02 GB.

Occlusion for a point object is one lookup into the profile, but the profile alone is wrong at short
range: a bin holds the maximum over the whole ray, including terrain beyond the object, so a 60 m
building at 3 km would be hidden by a 120 m hill at 25 km. Store a parallel per-bin
distance-of-maximum array (r.horizon exposes this) and a small monotone staircase of
(distance, tanmax) breakpoints per bin.

The silhouette rectangle, for an object of width *w*:

```
azimuth half-width  dA    = atan( w / (2d) )          -- atan, not w/2d, for close objects
top elevation       α_t   = atan2( top_m   − h_obs − d²/(2·R_eff), d )
base elevation      α_b   = atan2( ground_m − h_obs − d²/(2·R_eff), d )
```

For a building with a real footprint, run the inverse geodesic to every vertex — but unwrap vertex
azimuths relative to the centroid azimuth first, or a building straddling due north yields 0.3° and
359.8° and a 359.5°-wide silhouette.

The horizon profile is small and cacheable: 3600 bins as int16 centidegrees is 7.0 KiB, ~2.5 KiB
gzipped. It is what should cross any client/server boundary, live in IndexedDB, and be reused across
repaints, refraction changes and catalogue updates. Only a change of observer position or eye height
invalidates it.

Nothing exists to reuse: no JS or TS library computes a terrain horizon profile. npm has panorama
image viewers and single-point elevation helpers. Every real implementation is native — GRASS
(GPL-2.0), HORAYZON (MIT, usable server-side for cross-validation), horizonator (LGPL),
`artificial-panos` (no LICENSE file, so all rights reserved; read for ideas, do not fork).

## 6. The page

### 6.1 Shape

On a phone the map fills the screen; the controls sit behind a hamburger and the table behind a
button. On a desktop there is room for the panel, the table and the map at once, so the panel stays
open.

The regions share one piece of state: a centre bearing and a span. Scrolling the panorama moves it,
the map's ray sweeps with it, and the table re-filters to it if it is open. Typing a bearing moves
all of them. Picking an object centres on it.

Desktop — the espoo panel-plus-map split with a strip added:

```
+----------------+------------------------------------------+
|  observer      |  P A N O R A M A   ~120 deg visible      |
|  + filters     |  x = true azimuth, y = elevation angle   |
|----------------+------------------------------------------+
|  azimuth table |                                          |
|  (the window,  |  M A P   observer pin, azimuth wedge,    |
|   sortable)    |          range rings                     |
+----------------+------------------------------------------+
```

Mobile — the map fills the screen, and nothing else is on it by default:

```
+---------------------------+
| [=]                       |  hamburger: observer + filters, as a drawer
|                           |
|   M A P                   |  full viewport
|                           |
|   P A N O R A M A         |  sticky strip, ~35% height
+---------------------------+
| [ 224 objects ]           |  pill: taps open the table as a sheet
+---------------------------+
```

The controls live behind the hamburger. The table is reachable from the pill in the corner, which
doubles as the count so it says something useful while shut, and opens the table as a sheet over the
map. Both are one tap, neither is in the way.

Two layout details that are easy to get wrong and were: a `transform` on the drawer makes it the
containing block for any `position: fixed` descendant, so the sheet has to be a *sibling* of the
drawer rather than a child, or it slides off-screen with it. And the sheet's parts must translate
together — moving a 30 px count bar by `translateY(110%)` moves it 33 px and leaves it sitting on
the map.

Aiming is done by matching the drawn silhouette against the real one: drag the panorama until two
masts and a water tower line up at the right spacing, then read the bearings off. That works without
a compass, and it works inside a steel tower, where a magnetometer does not.

The desktop layout shows the widest azimuth span, and suits planning rather than standing on a
tower.

### 6.2 The table

A desktop panel, and a sheet behind a button on mobile. Sortable, filterable, tabular numerals, one
row per object — espoo's `#list` idiom. Rows computed for an observer on Kaivopuisto hill
(60.15530 N, 24.95350 E, eye at 22.3 m):

```
#   OBJECT                    TYPE      AZ °T      DIST     TOP     H     ALT °
1   Kivenlahden masto         mast    278.275°   17.56 km  369.1  326.0  +1.063
2   Tiirismaan masto          mast     17.979°   99.89 km  544.6  327.0  −0.091
3   Tallinn TV Tower          tower   182.813°   76.30 km  338.3  314.2  −0.061  ⌇
```

The horizon dip from 22.3 m is −0.148°, so rows 2 and 3 are above it — both visible, row 3 only as
an 8-arcsecond thread.

`~` marks a lidar-estimated height, `⌇` a refraction-marginal object. Clicking a row highlights it
in the panorama and the map, as clicking a row flies the espoo map. A copy-as-text action, since the
likely use is writing an azimuth down.

Filters: category toggles, max distance, minimum angular height, labelled-only, the refraction
slider, and a height-confidence toggle (registered / lidar / estimated) exposing §3.3.

### 6.3 Setting position and direction

**Position**, in order of preference:

1. A saved viewpoint. The ~1,200 MTK `nakotorni`, the fells, and whatever the user pins. This is the
   common case: you go back to the same tower.
2. A map pin, dragged. Exact, and the only option on desktop.
3. `navigator.geolocation`, as a starting guess to be nudged. Note `coords.accuracy` is a 95%
   radius, not 1σ — halve it before putting it in an error budget.

**Height** is the most sensitive input — 1 m of error moves every elevation and shifts the grazing
horizon (from 2 m the range to a 40 m tower is 29.6 km; from 3 m, 31.8 km). Snap to the DEM at the
position, then an editable eye height above it: standing (1.7 m), beach, *n*th floor, observation
deck, or a number. Never the GNSS altitude — §4.3.

**Direction** is user input: drag the panorama, type a bearing, or tap a row. No sensors are read.

### 6.4 Wake lock

The one platform API worth using. Someone comparing a panorama against a horizon holds the phone
still for minutes and the screen dims. `navigator.wakeLock` reached iOS Safari in 18.4; older
versions have no usable polyfill, so it degrades to nothing.

### 6.5 Offline

- Precompute a profile per named viewpoint: 1,440 bins × 2 bytes = 2.88 KB, so 500 Finnish
  observation towers and hills is 1.4 MB.
- The Cache API cannot hold PMTiles — the Service Worker spec rejects `Cache.put` and `Cache.addAll`
  for any 206 response. Download the archive whole into OPFS and hand
  `new pmtiles.PMTiles(new pmtiles.FileSource(handle.getFile()))` to MapLibre.
- Install first, then download. A home-screen web app has an isolated storage container from Safari,
  so a region downloaded in a tab vanishes on install. And in a tab, ITP deletes all script-writable
  storage after seven days without interaction, so a tool used three times a summer is always empty.
- Storage is not the constraint: since iOS 17 the origin quota is up to 60% of disk, and
  `navigator.storage.persist()` is granted mainly to installed web apps. The 50 MB figure that
  circulates is stale.
- A region is 5–15 MB without a basemap, 30–40 MB with a z13 regional one.

### 6.6 Hosting

Range support is mandatory and not universal:

| host | 206? | note |
|---|---|---|
| Cloudflare R2 + custom domain | yes | correct `Content-Range`, CORS present, free egress |
| GitHub Pages | yes | 1 GB site, 100 GB/mo soft |
| Netlify | yes | new accounts ~15 GB/mo, not the legacy 100 |
| Cloudflare Pages / Workers | **no** | returns 200 + full body; 25 MiB per-asset cap |

`pmtiles.js` throws rather than degrading when a 200 body exceeds the requested range — the same
trap espoo's README documents for `python -m http.server`.

HTTPS is needed for `navigator.geolocation` and for the page to be installable, so on-device testing
over the plain-HTTP `serve.py` needs a TLS tunnel or a local certificate. Nothing else about the
page requires a secure context.

## 7. Visual design

espoo's language, extended rather than reinvented. Warm paper, hairline rules, one accent, no
shadows, no gradients, no blue.

```
--bg          #f7f6f3    warm paper, never white
--panel       #fffefb
--line        #ddd8cf    1px hairlines, the only separator
--ink         #2b2723
--dim         #6f6759
--accent      #b4531d    burnt sienna
--accent-soft #f3e3d4
```

- espoo's ramp (`#efe4d2 #e7c89a #dda866 #cd7f3c #b4531d #7d2b12`) is already aerial perspective:
  near objects deep rust, far ones fading to pale sand. Colour distance with it in both the panorama
  and the map, and they share one legend.
- Sky is `--bg`, flat, no gradient. Terrain silhouette is a filled warm grey-brown; sea is a
  slightly cooler tint of the same paper.
- Type: the same system stack at 14px/1.45. Micro-labels 11px uppercase, letter-spacing .06em, in
  `--dim`. Every number `font-variant-numeric: tabular-nums`.
- Controls: the `.seg` segmented row, 1px border, 5px radius, pressed = `--accent` text on an
  `--accent-soft` ground at weight 600. Sliders with `accent-color`. Nothing larger than a 5px
  radius.
- Basemap stays the Protomaps grayscale flavour already vendored.
- Panorama chrome: azimuth ruler along the top with degree ticks and cardinal letters; elevation
  scale down the left; a hairline at 0° for the astronomical horizon and a dimmer one at the
  computed sea horizon (they differ by the dip, 9.8′ from 30 m).
- Objects: a 1px `--accent` vertical stroke with a small cap. Refraction-marginal dashed at 50%.
  Labels in `--ink`, deconflicted by pushing up in rows rather than hiding, with a leader line where
  a label sits above its stroke.
- A persistent one-line credit strip with dataset dates, not a credits screen — §8 requires the
  dates anyway.

## 8. Licences

A shipped `objects.json` is a Derivative Database under ODbL §4.4 (share-alike), not a Produced Work
— the rendered panorama is the Produced Work under §4.3 (notice only). And the OSMF Horizontal Map
Layers Guideline closes the obvious loophole: separating data into layers does not avoid share-alike
if the layers interact for the same feature type. Its worked example is a non-OSM layer defined by
reference to what OSM lacks, which is share-alike-infected — exactly what deduplicating MML masts
against OSM masts produces, even though no OSM row survives.

Decision: **take the union and ship `objects.json` under ODbL.** OSM has more masts than MTK
(9,529 vs 8,422), 913 chimneys, 384 water towers and 856 `tower:type=observation`, with a 44% height
fill on masts that is partly disjoint from MTK's — the union is a measurably better catalogue, and
the page, the renderer and the panorama stay Produced Works under whatever licence, so only the data
file inherits share-alike.

That means the layer-separation rule stops mattering: masts, chimneys, towers, turbines and
buildings can be deduplicated across sources freely, because the result is ODbL either way.

| feature type | sources | licence of the merged layer |
|---|---|---|
| masts, chimneys, towers, turbines | MML MTK + Fintraffic AIP + MML/SYKE nDSM + OSM | ODbL |
| buildings | municipal CityGML + Ryhti + OSM + curated | ODbL |
| sea marks | Väylävirasto (+ OSM lighthouses) | ODbL |
| terrain | MML via GeoCubes | CC BY 4.0, kept separate |
| names, hills, islands | MML Nimistö + OSM | ODbL |
| Estonia | ETAK + EANS AIP + OSM | ODbL |
| landmark names, links | Wikidata | CC0 |

Terrain stays out of `objects.json` as its own CC BY 4.0 artefact — the DEM tiles never touch OSM,
and keeping them separate means the terrain data remains reusable on its own terms.

Attribution:

- MML requires a delivery date: *"sisältää Maanmittauslaitoksen Maastotietokannan 04/2025
  aineistoa"*. A bare `© Maanmittauslaitos` is non-compliant, so `build.py` records a fetch timestamp
  per dataset and the page shows it.
- Väylävirasto prescribes a literal string: *"Source: Finnish Transport Infrastructure Agency / Open
  API, license CC 4.0 BY"*, plus a hyperlink and a note of modifications.
- Estonia: *"Map data by Republic of Estonia Land and Spatial Development Board 01.01.2025"* — the
  licence wants the age of the data or date of extraction, a full date not a bare year. The agency
  renamed from Maa-amet to Maa- ja Ruumiamet in 2025. The licence also obliges removal of the source
  reference on request.
- OSM requires attribution visible **without interaction** — it may be dismissed with an `x`,
  collapsed on pan/zoom/click, or auto-collapsed after five seconds, but not hidden behind a menu.
  And because `objects.json` is a published database rather than only a map, the ODbL text or a link
  to it must sit where people would look — the README and the file's own metadata header.
- AIP: free for further processing; do not republish the CSV.
- Wikidata is CC0 and needs nothing — and must not supply coordinates. A direct query returns 118
  Finnish tower-class items with coordinates and 26 with a height, some rounded to two decimal
  places, and Teiskon yleisradiomasto carries two conflicting coordinates 179 m apart (0.34° of
  azimuth at 30 km, wider than the mast). A name source, not a pipeline.

## 9. Rejected sources and dead ends

- `rakval:ValmisRakennus` — 401 with a byte-identical error body in all six municipalities tested.
  Advertised in nearly every Finnish Tekla GetCapabilities, universally credentialed.
- **MML "Rakennukset 3D"** contains no masts and no chimneys — generated from the KMTK *Rakennus*
  class only. Verified empirically next door: on sheet L4133E four MTK masts (37, 59, 31 m) fall
  inside the extent while the tallest solid among 1,353 buildings is 19.54 m, and at the 59 m mast
  the nearest solid is 2.4 m away and 3.98 m tall — the shed at its base. It also needs an API key.
- **City building models do not reliably contain stacks, and each fails differently.** Vantaa models
  chimneys as buildings with a use class (usable). Helsinki models them as anonymous solids with no
  attributes — its two tallest objects, 145.9 m and 144.0 m, carry no address, class or id. Espoo
  does not model them: all 64,479 `measuredHeight` values top out at 88.9 m and the 149.3 m
  Suomenoja stack is absent. The capital-region CityGML pipeline is a building source, not a
  tall-structure source.
- **Kirkkonummi's kantakartta** gives heights that look plausible and are wrong. Its line work is
  digitised at ground level for many structures, so roof-minus-ground returns a small number rather
  than failing: a 9-storey block computes to 0.23 m, and 68% of 4+ storey buildings are physically
  impossible. The tall buildings are compressed into the low-rise bucket, so a sanity check on the
  distribution passes.
- **Traficom's open INSPIRE WFS** — 36 feature types, all marine. No obstacle layer, no mast layer.
- `fintraffic.fi/fi/ans/lentoesteet-paikkatietoaineistona` — 404, and `www.ansfinland.fi` times out.
  The register moved to Traficom in 2023 and the data is at ais.fi (§3.2), free and with no request
  process. `avoindata.suomi.fi` returns zero results for "lentoeste", and the live Fintraffic
  obstacle page carries no email address — a web form and a 204 EUR + VAT per-obstacle fee.
- **Overture** — 6.9 M Finnish buildings, but all 15 tallest have
  `sources[].dataset = OpenStreetMap`. It contributes ML footprint geometry and no heights of its
  own; the height column repackages OSM's 21,742 tags, ODbL-encumbered.
- **Wikidata heights** — `P2048` in Finland is unit-corrupted: the top three height-sorted Finnish
  structures are an 8.5 m sculpture, a monument and another sculpture, all in centimetres,
  outranking every 327 m mast.
- **Digita** publishes no station list. Traficom's OData registers do (1,066 TV + 2,410 radio
  transmitters, 438 sites, CC BY 4.0) — but coordinates are arcsecond-quantised (median 20 m off, 4%
  beyond 50 m) and `AntennaHeight` is the antenna on the structure, a median 5 m and p10 27 m below
  the real structure height. Identity and ownership only, never geometry.
- `mapservice.digita.fi/api/map-data/sites` — an open undocumented endpoint with 198 sites and
  8-decimal coordinates. No licence statement, no height field.
- **PeakFinder's public API** is a URL-embed API (`github.com/Fabiz/PeakFinder-API`), not a bulk data
  interface.
- **Aerodrome Area 2 obstacle sets** — the Helsinki-Vantaa file is 71% approach lights, median height
  7 m; several sets are two years stale.
- **Free global elevation APIs** — three return 21.12, 26.0 and 7.0 m for the same Helsinki point, in
  three different vertical datums.
- **Overpass** is unreliable enough to be a build hazard: on 2026-09-13 `overpass-api.de`,
  `kumi.systems` and `private.coffee` all returned 504 simultaneously, and `overpass.osm.ch` answers
  HTTP 200 with a well-formed 0 for Finnish queries because it is a Switzerland-only extract. Since
  §8 keeps OSM out of the shipped data, this is a development annoyance, not a dependency.
- Never query a raw Finland bounding box: 59.7–70.2 N / 19.0–31.7 E contains St Petersburg, Tallinn,
  eastern Sweden and Kola. The same `building:levels` query returned 11,642 on the bbox and 1,119
  clipped to the admin area.

## 10. Order of work

**v0 — the azimuth table.** `build.py` pulls MTK tower points over Range, fuses AIP heights, samples
nDSM for the rest, emits `objects.json`. `index.html` is the espoo page with a different payload:
map, observer pin, sortable azimuth table. No panorama, no terrain, no sensors. This already answers
the question — pick a point, get every recognisable object with an exact geodesic bearing — for
roughly a fifth of the work.

**v1 — the panorama.** Terrain ring streaming, the profile kernel, the canvas strip, occlusion,
silhouette rectangles, refraction states.

**v2 — mobile.** The sticky-panorama strip, saved viewpoints, wake lock, the install-then-download
offline flow. The hamburger drawer and the table sheet already exist.

**v3 — coast and Estonia.** Islands as azimuth spans, Väylävirasto lighthouses and `Reunamerkki`,
Estonia — leading with Porkkala → Teletorn and Jussarö → Pakri rather than the Helsinki version.

**Deferred.** The 60–100 m obstacle tier. Paid 5 pts/m² lidar for objects nDSM leaves
uncertain. The KMTK migration: MML says production files and API arrive autumn 2026, and it moves
heights onto the objects as `Absoluuttinen korkeus` (N2000) and adds a real `Torni` class. Pin the
2025-04-03 GeoPackage, record every layer and column depended on, re-check.

## 11. Decisions

1. **No compass, no AR, no auto-alignment.** Direction is user input: drag the panorama, type a
   bearing, or tap a row. This removes the largest source of error in the whole system and a lot of
   code with it. Both platforms return *magnetic* heading and neither applies declination (iOS reads
   `CLHeading.magneticHeading`; Android's `deviceorientationabsolute` is `TYPE_ROTATION_VECTOR`,
   magnetic-referenced, and Chromium has no position input so it cannot correct) — so a compass path
   would need the FMI declination grid, which itself disagrees with WMM by up to 1.3° because of the
   Fennoscandian crustal anomaly. On top of that, a phone magnetometer is 5–15° outdoors and worse
   inside a steel observation tower, where the distortion is in the world frame and cannot be
   calibrated out. None of that is worth carrying to reproduce an answer the user already has.
   Camera AR goes with it: iOS 26 rotates the `getUserMedia` frame 90° in home-screen web apps and
   misreports `screen.orientation`, camera permission is not persisted, there is no Fullscreen API
   on iPhone and no web API for camera FOV.

2. **OSM is in, and `objects.json` ships under ODbL.** The union is a better catalogue than any
   single-lineage alternative, and share-alike on one data file is a small price. Terrain stays a
   separate CC BY 4.0 artefact. See §8.

3. **Ranking and labelling by a per-azimuth-window budget**, not a height or angle cutoff. §2.

4. **Point objects are never rasterised into the DEM.** §5.2.

5. **Islands are azimuth spans, not DEM silhouettes**, except above ~100 m observer height under
   40 km, and on lakes. §3.5.

6. **Mobile shows the map full screen**, with the controls behind a hamburger and the table behind
   a button. Desktop keeps the panel open. §6.1.

7. **No bulk data in the repo**, and no machine specifics in it either — the cache location is
   `AZIMUTH_CACHE`, and `build.py` fails loudly rather than falling back to the repo directory. See
   CLAUDE.md; the repo is public. §5.

## 12. Open questions

1. **Massif versus summit.** §3.9 identifies the failure — Pallastunturi/Taivaskero, Koli/Ukko-Koli
   — but not a rule that separates a massif name from a summit name automatically. `scaleRelevance`
   inverts on the Koli pair, so it cannot be the discriminator. Possibly: a Kohouma whose snapped
   maximum belongs to another Kohouma is a massif, and should label a span of azimuth rather than a
   point.
2. **Water towers filed as buildings.** MML's catalogue says a >500 m² water tower may be stored as a
   building polygon. How many actually are, and whether coordinate-matching `Vesitornin selite`
   (45802) against footprints recovers them, is unmeasured.
3. **Forest occlusion in practice.** The p90 DSM−DTM gap is 21.4 m. Whether a canopy term improves
   the felt accuracy or just removes objects that are actually visible — a mast top pokes over the
   trees the whole way — needs a field test.
4. **The 60–100 m tier.** The register holds everything above 60 m nationwide while the published
   extract cuts at 100 m, so a tier of water towers and chimneys exists and is not on the website.
   Requests go through Fintraffic's *selvityspyyntö lentoesteestä* web form at 204 EUR + VAT per
   obstacle — a per-object price, so almost certainly not worth it. The useful part of asking would
   be the register's own statement of its height datum.
