#!/usr/bin/env python3
"""
Bake vysokorozlišeného terénu a hloubkových vrstevnic pro Slapy Navigátor.

Běží v GitHub Actions (sandbox vývojového prostředí nemá přístup k ČÚZK).
Vstupy:  ČÚZK DMR 5G (open data CC BY 4.0) přes ArcGIS ImageServer exportImage,
         osa řeky RIVER_AXIS z js/data/river.js.
Výstupy: terrain/{z}/{x}/{y}.png  — Terrarium DEM dlaždice z10–14
         terrain/meta.json        — metadata (bounds, zoomy, atribuce)
         js/data/isobaths.js      — GeoJSON izobat (ODHAD hloubek) + meta hloubkové mřížky
         data/depth.png           — hloubková mřížka (grayscale, 1 px ≈ 30 m, hodnota = m)

Model hloubek je ORIENTAČNÍ ODHAD (thalweg profil + vzdálenost od břehu);
skutečná batymetrie Povodí Vltavy (sonar 2010) není veřejná.

Závislosti: numpy, scipy, Pillow, requests, tifffile, imagecodecs, scikit-image
"""
import io
import json
import math
import os
import re
import sys
import time

import numpy as np
import requests
import tifffile
from PIL import Image
from skimage import measure

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

IMG_SERVER = "https://ags.cuzk.gov.cz/arcgis2/rest/services/dmr5g/ImageServer/exportImage"
BBOX = (14.17, 49.60, 14.50, 49.86)   # lon_min, lat_min, lon_max, lat_max (Slapy)
# dlaždice: Slapy detailně, koridor po Mělník jen z10–12 (3D pohled po proudu)
TILE_SPECS = [
    (BBOX, range(10, 15)),
    ((14.17, 49.86, 14.60, 50.36), range(10, 13)),
]
META_BOUNDS = (14.17, 49.60, 14.60, 50.36)
WATER_LEVEL = 270.6                    # max. zásobní hladina [m n. m.]
DAM_KM, DAM_DEPTH = 91.61, 58.0        # hloubka u hráze
KAMYK_KM, KAMYK_DEPTH = 134.73, 5.0    # odhad hloubky pod Kamýkem
ISO_LEVELS = [2, 5, 10, 20, 30, 40, 50]
GRID_RES_M = 15.0                      # pracovní mřížka modelu dna

session = requests.Session()
session.headers["User-Agent"] = "slapy-navigator-bake/1.0 (github.com/PetrMB/slapy)"


# ---------- Web Mercator helpers ----------
R = 6378137.0
def lonlat_to_merc(lon, lat):
    return (R * math.radians(lon),
            R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))
def merc_to_lonlat(x, y):
    return (math.degrees(x / R),
            math.degrees(2 * math.atan(math.exp(y / R)) - math.pi / 2))
def tile_bounds_merc(z, x, y):
    n = 2 ** z
    world = 2 * math.pi * R
    xmin = -world / 2 + x * world / n
    xmax = xmin + world / n
    ymax = world / 2 - y * world / n
    ymin = ymax - world / n
    return xmin, ymin, xmax, ymax
def lonlat_to_tile(lon, lat, z):
    n = 2 ** z
    xt = (lon + 180) / 360 * n
    yt = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return int(xt), int(yt)


# ---------- DMR 5G fetch ----------
def fetch_dem(xmin, ymin, xmax, ymax, w, h, retries=4):
    """exportImage → float32 numpy (h, w); NaN = NoData."""
    params = {
        "bbox": f"{xmin},{ymin},{xmax},{ymax}",
        "bboxSR": 3857, "imageSR": 3857,
        "size": f"{w},{h}",
        "format": "tiff", "pixelType": "F32",
        "noData": "", "interpolation": "RSP_BilinearInterpolation",
        "f": "image",
    }
    for a in range(retries):
        try:
            r = session.get(IMG_SERVER, params=params, timeout=90)
            r.raise_for_status()
            arr = tifffile.imread(io.BytesIO(r.content)).astype(np.float32)
            if arr.ndim == 3:
                arr = arr[..., 0]
            arr[arr < -1000] = np.nan
            arr[arr > 9000] = np.nan
            return arr
        except Exception as e:
            if a == retries - 1:
                raise
            time.sleep(2 * (a + 1))


def fill_nodata(arr, fallback=WATER_LEVEL):
    """NoData → průměr sousedů (iterativní dilatace), zbytek hladina."""
    if not np.isnan(arr).any():
        return arr
    out = arr.copy()
    import warnings
    for _ in range(60):
        m = np.isnan(out)
        if not m.any():
            break
        neigh = np.stack([np.roll(out, s, ax) for s, ax in
                          ((1, 0), (-1, 0), (1, 1), (-1, 1))])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fill = np.nanmean(neigh, axis=0)
        out[m] = fill[m]
    out[np.isnan(out)] = fallback
    return out


# ---------- Terrarium tiles ----------
def encode_terrarium(arr):
    v = np.clip(arr + 32768.0, 0, 65535.99)
    r = np.floor(v / 256.0)
    g = np.floor(v - r * 256.0)
    b = np.floor((v - np.floor(v)) * 256.0)
    return np.dstack([r, g, b]).astype(np.uint8)


def bake_tiles():
    total = 0
    all_zooms = set()
    for bbox, zooms in TILE_SPECS:
        all_zooms.update(zooms)
        for z in zooms:
            x0, y1 = lonlat_to_tile(bbox[0], bbox[1], z)
            x1, y0 = lonlat_to_tile(bbox[2], bbox[3], z)
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    path = os.path.join(ROOT, "terrain", str(z), str(x), f"{y}.png")
                    if os.path.exists(path):
                        continue
                    m = tile_bounds_merc(z, x, y)
                    arr = fill_nodata(fetch_dem(*m, 256, 256))
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    Image.fromarray(encode_terrarium(arr)).save(path, optimize=True)
                    total += 1
                    if total % 25 == 0:
                        print(f"  tiles: {total} (z{z})", flush=True)
    meta = {
        "bounds": list(META_BOUNDS),
        "minzoom": min(all_zooms), "maxzoom": max(all_zooms),
        "encoding": "terrarium",
        "attribution": "výškopis © ČÚZK DMR 5G (CC BY 4.0)",
        "baked": time.strftime("%Y-%m-%d"),
    }
    with open(os.path.join(ROOT, "terrain", "meta.json"), "w") as f:
        json.dump(meta, f)
    print(f"terrain tiles done: {total} new")


# ---------- river axis ----------
def load_axis():
    src = open(os.path.join(ROOT, "js", "data", "river.js"), encoding="utf-8").read()
    pts = re.findall(r"\[(49\.\d+),(14\.\d+)\]", src)
    axis = [(float(la), float(lo)) for la, lo in pts]
    cal = [(int(i), float(km)) for i, km in re.findall(r"\{ i: (\d+), km: ([\d.]+) \}", src)]
    # kumulativní vzdálenost
    cum = [0.0]
    for i in range(1, len(axis)):
        a, b = axis[i - 1], axis[i]
        dla = math.radians(b[0] - a[0]); dlo = math.radians(b[1] - a[1])
        x = math.sin(dla / 2) ** 2 + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(dlo / 2) ** 2
        cum.append(cum[-1] + 2 * 6371000 * math.asin(math.sqrt(x)))
    def km_at(i):
        d = cum[i]
        for j in range(1, len(cal)):
            if d <= cum[cal[j][0]] or j == len(cal) - 1:
                (ia, ka), (ib, kb) = cal[j - 1], cal[j]
                da, db = cum[ia], cum[ib]
                return ka + (kb - ka) * (d - da) / (db - da or 1)
    return axis, [km_at(i) for i in range(len(axis))]


# ---------- depth model ----------
def bake_depth():
    lon0, lat0, lon1, lat1 = BBOX
    mx0, my0 = lonlat_to_merc(lon0, lat0)
    mx1, my1 = lonlat_to_merc(lon1, lat1)
    W = int((mx1 - mx0) / GRID_RES_M)
    H = int((my1 - my0) / GRID_RES_M)
    print(f"depth grid {W}x{H} @ {GRID_RES_M} m")

    # DEM mozaika po blocích 1024 px
    dem = np.empty((H, W), np.float32)
    step = 1024
    for iy in range(0, H, step):
        for ix in range(0, W, step):
            w = min(step, W - ix); h = min(step, H - iy)
            bx0 = mx0 + ix * GRID_RES_M
            by1 = my1 - iy * GRID_RES_M
            block = fetch_dem(bx0, by1 - h * GRID_RES_M, bx0 + w * GRID_RES_M, by1, w, h)
            dem[iy:iy + h, ix:ix + w] = block
            print(f"  dem block {ix},{iy}", flush=True)
    dem = fill_nodata(dem)

    # vodní maska: plochá oblast u hladiny, komponenty protnuté osou řeky
    from scipy import ndimage
    near = np.abs(dem - WATER_LEVEL) < 1.5
    axis, axis_km = load_axis()
    def to_px(la, lo):
        x, y = lonlat_to_merc(lo, la)
        return int((my1 - y) / GRID_RES_M), int((x - mx0) / GRID_RES_M)
    labels, _ = ndimage.label(near)
    axis_labels = set()
    for la, lo in axis:
        py, px = to_px(la, lo)
        if 0 <= py < H and 0 <= px < W and labels[py, px]:
            axis_labels.add(labels[py, px])
    water = np.isin(labels, list(axis_labels))
    print(f"  water cells: {water.sum()}")

    # vzdálenost od břehu (EDT) + nejbližší vrchol osy (EDT s indexy)
    dist_m = ndimage.distance_transform_edt(water) * GRID_RES_M
    axis_seed = np.full((H, W), -1, np.int32)
    for i, (la, lo) in enumerate(axis):
        py, px = to_px(la, lo)
        if 0 <= py < H and 0 <= px < W:
            axis_seed[py, px] = i
    ind = ndimage.distance_transform_edt(axis_seed < 0, return_distances=False, return_indices=True)
    axis_id = axis_seed[ind[0], ind[1]]

    # hloubka thalwegu podle km + příčný profil podle relativní vzdálenosti od břehu
    km_grid = np.take(np.array(axis_km, np.float32), np.clip(axis_id, 0, len(axis) - 1))
    t = np.clip((km_grid - DAM_KM) / (KAMYK_KM - DAM_KM), 0, 1)
    thalweg = DAM_DEPTH + (KAMYK_DEPTH - DAM_DEPTH) * t

    # normalizace šířky: 95. percentil vzdálenosti od břehu v 0,5km binech
    depth = np.zeros((H, W), np.float32)
    wy, wx = np.where(water)
    kmw = km_grid[wy, wx]
    dw = dist_m[wy, wx]
    bins = np.floor(kmw * 2).astype(int)
    p95 = {}
    for b in np.unique(bins):
        sel = dw[bins == b]
        p95[b] = max(np.percentile(sel, 95), 20.0)
    dmax = np.array([p95[b] for b in bins], np.float32)
    rel = np.clip(dw / dmax, 0, 1) ** 0.75
    depth[wy, wx] = thalweg[wy, wx] * rel
    depth[depth < 0.3] = 0

    # ---- izobaty (marching squares) ----
    features = []
    for lvl in ISO_LEVELS:
        for contour in measure.find_contours(depth, lvl):
            if len(contour) < 12:
                continue
            coords = []
            for py, px in contour[::3]:          # decimace 1:3
                x = mx0 + px * GRID_RES_M
                y = my1 - py * GRID_RES_M
                lo, la = merc_to_lonlat(x, y)
                coords.append([round(lo, 5), round(la, 5)])
            features.append({
                "type": "Feature",
                "properties": {"depth": lvl},
                "geometry": {"type": "LineString", "coordinates": coords},
            })
    print(f"  isobath features: {len(features)}")

    # ---- hloubková mřížka jako PNG (1 px = 30 m, uint8 m) ----
    small = depth[::2, ::2]
    img = np.clip(np.round(small), 0, 255).astype(np.uint8)
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    Image.fromarray(img, "L").save(os.path.join(ROOT, "data", "depth.png"), optimize=True)

    gj = {"type": "FeatureCollection", "features": features}
    grid_meta = {
        "url": "data/depth.png",
        "bbox": list(BBOX),
        "w": img.shape[1], "h": img.shape[0],
    }
    out = (
        "/* ============ Hloubkove vrstevnice (izobaty) ============\n"
        "   ORIENTACNI MODELOVY ODHAD (thalweg profil + vzdalenost od brehu,\n"
        "   teren CUZK DMR 5G CC BY 4.0). NENAHRAZUJE MERENI - skutecne hloubky\n"
        f"   se mohou vyrazne lisit. Vztazeno k max. hladine {WATER_LEVEL} m n. m.\n"
        f"   Vygenerovano tools/bake_terrain.py {time.strftime('%Y-%m-%d')}. */\n"
        f"const ISOBATHS = {json.dumps(gj, separators=(',', ':'))};\n"
        f"const DEPTH_GRID = {json.dumps(grid_meta)};\n"
    )
    with open(os.path.join(ROOT, "js", "data", "isobaths.js"), "w", encoding="utf-8") as f:
        f.write(out)
    print("isobaths.js + depth.png written")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("all", "tiles"):
        bake_tiles()
    if what in ("all", "depth"):
        bake_depth()
