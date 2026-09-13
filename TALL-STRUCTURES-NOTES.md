# Finnish tall structures: where the data is

Side notes from building <https://github.com/lkangas/buildings-browser> (a capital-region building
height map). Everything below was verified by fetching it, not read off a product page, and the
numbers were reproduced independently. Written for reuse, so it includes the dead ends.

**Short version:** masts and chimneys are *not* in any building dataset. They live in MML's
Maastotietokanta as separate feature classes, which is free and needs no API key. The aviation
obstacle register is a second, independent source and is also free.

## 1. MML Maastotietokanta (MTK) — the main source

Open shapefiles, mirrored on funet, **no API key**:

```
https://www.nic.funet.fi/index/geodata/mml/maastotietokanta/2025/shp/L4/L41/L4131R.shp.zip
```

Sheet naming is the standard MML grid (`L4131R` etc.). One sheet is ~12 MB. MML's own
`avoin-paikkatieto` endpoint returns 401 for the same data — use the mirror.

**CRS: EPSG:3067 (ETRS-TM35FIN), heights N2000 (compound EPSG:3900).** Confirmed in MML's product
description, so Z can be used directly alongside anything else in N2000.

**Licence:** CC BY 4.0.

### Feature classes (national counts, verified)

| class | code | count |
|---|---|---|
| Masto (mast) | 44800 | 8,422 |
| Tuulivoimala (wind turbine) | — | 1,893 |
| Savupiippu (chimney) | 45300 | 1,300 |
| Näkötorni (lookout tower) | 45000 | 1,193 |
| Vesitorni (water tower) | 45800 | 360 |
| | | **13,168** |

### The catch: heights are a separate feature

The structure record itself is a bare POINT. The raw Suomenoja chimney is
`TEKSTI='' KORKEUS=0.0 KORARV=0.0 KUNTA=''` — no height, no name, no id.

The height exists only as a **cartographic text feature** that must be attached by a
distance-capped spatial join:

- chimneys: kohdeluokka **45303**
- masts: kohdeluokka **44803**

**That join is lossy, and worse than a quick sample suggests.** Nationally only
**25.0% of chimneys (325/1300)** and **50.8% of masts (4,278/8,422)** have a height at all. The
capital region is better attributed — 63% of chimneys and 76% of masts — but budget for a fallback
or drop the height-less ones. Espoo specifically is an unusually well-attributed corner; do not
generalise from it.

### Extraction is cheap

Range requests work (`206`, `Accept-Ranges: bytes`), so the five structure classes can be pulled in
**14 requests / 2.66 MB** rather than downloading whole sheets.

## 2. Aviation obstacle register — the cross-check

Free, **no API key**, tiny: **91,761-byte zip → 521,206-byte CSV, 2,676 records**. Every structure
above the registration threshold, with position, height above ground *and* height above sea level.

Independent of MTK, so it is the natural validation set. Agreement is excellent:

| structure | MTK | obstacle register |
|---|---|---|
| Suomenoja chimney | 149.3 m | 149.4 m AGL / 152.1 m MSL |
| Martinlaakso | 86.4 / 85.7 m | 86.6 / 86.0 m (EFHK OLS) |

Positions agree to five decimal places.

## 3. Worked examples (Espoo, verified twice)

| structure | height | ground | top (N2000) | lat, lon |
|---|---|---|---|---|
| Kivenlahti/Latokaski radio mast | 326.0 m | 43.148 | **369.1 m** | — |
| Suomenoja power plant chimney | 149.3 m | 2.334 | 151.6 m | 60.14904, 24.71755 |
| (unnamed) | 100.0 m | — | — | 60.20702, 24.61538 |
| Suomenoja secondary stacks ×2 | 80.5 / 80.3 m | — | 83.2 m | — |
| Tapiola heating plant | 77.2 m | 25.489 | 102.7 m | 60.17794, 24.79673 |
| Otaniemi | 75.0 m | 3.029 | 78.0 m | 60.18836, 24.82745 |

Espoo bounding box totals: **21 chimneys, 82 masts** (75 with a height).

## 4. Dead ends — do not repeat these

**MML "Rakennukset 3D" does not contain masts or chimneys.** It is generated from the KMTK
*Rakennus* (building) feature class only, so non-buildings are excluded by construction. Verified
empirically, not just from the definition: on sheet L4133E, four MTK masts fall inside the sheet's
extent (37.0, 59.0, 31.0 m), while the tallest solid in the entire 1,353-building sheet is 19.54 m.
At the 59 m mast the nearest 3D solid is 2.4 m away and 3.98 m tall — the shed at the mast base.
It also **requires a free API key** from MML OmaTili, which MTK does not.

**City building models are inconsistent and none of them is complete for tall structures:**

- *Vantaa* models chimneys as buildings with a use class — present and usable.
- *Helsinki* models them as anonymous solids with no attributes at all; its two tallest objects
  (145.9 m, 144.0 m) carry no address, class or id.
- *Espoo* does not model them at all. All 64,479 `measuredHeight` values in its CityGML top out at
  88.9 m; nothing above 100 m exists. The Suomenoja chimney is simply absent.

**Kirkkonummi's kantakartta gives heights that look plausible and are wrong.** Its building line
work is digitised at ground level for many structures, so a naive roof-minus-ground returns a small
number rather than failing. Checked against OSM `building:levels`: a 9-storey block computes to
0.23 m, and **68% of 4+ storey buildings are physically impossible**. The trap is that the
resulting height distribution looks like a normal low-rise town — the tall buildings have been
compressed into the low-rise bucket, so a sanity check on the distribution *passes*.

## 5. If you need heights where MTK has none

Ground elevation is easy and free everywhere: MML KM2/KM10 terrain models, or Helsinki's own 1 m
DTM over WCS (no key, EPSG:3879, N2000, verified bare-earth). Structure height is the hard half —
no national source covers it completely. Options, roughly in order of effort: the obstacle register
(only above its threshold), OSM `man_made=mast|chimney|tower` tags, or lidar, which needs a point
cloud pipeline.
