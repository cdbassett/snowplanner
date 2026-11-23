"""Terrain relief and water depth of a level, from the level pak's height_map and water_height_map textures.

* height_map: 16 bit ground height, 0..65535 spreads over the level's top height (a round number of metres: 60, 100, 120, 150, 180, 200, 220, 250 ...). The game files
  don't state it where we could find it, so it is fitted from the heights of the trucks / trailers placed in the level (their origins stand a little above the ground)
  and rounded to 5 m.
* water_height_map: float32 water surface height in metres (a huge negative number where there is no water), at a coarser resolution.
  Depth = water height - ground height. Depths of 0.5 m or less are ice / puddles and fade out.
"""
import struct
import zipfile
from collections import namedtuple

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from utils import gamefiles, level_data

TRAILER = 6 # bytes after the image data of a .pct
NO_WATER = -1e30
DEPTH_MIN, DEPTH_FULL = 0.5, 0.9 # metres: no water drawn at / below the first, fully drawn from the second
PIXELS_PER_METRE = 4033 / 2000 # every level's height map (and map texture) has this resolution; smaller levels just cover less ground
LIGHT_AZIMUTH, LIGHT_ALTITUDE = np.deg2rad(315), np.deg2rad(40)
SHADE_STRENGTH = 0.30 # standard deviation of the brightness change the relief gives (every level gets the same, whatever its heights)
SHADE_LIMIT = 0.6
TREE_SUPERSAMPLE = 3 # trees are painted at this many times the map's resolution, then reduced
WATER_REACH = 1.5 # water cells' reach in cells past their edge: the waterline follows the ground height

Terrain = namedtuple("Terrain", "ground,water,top_height,fit_note,half")


def read_pct(pak, name, bytes_per_pixel, dtype):
    data = pak.read(name)
    width, height = struct.unpack_from("<II", data, 16)
    end = len(data) - TRAILER
    start = end - width * height * bytes_per_pixel

    if not 0 <= start <= 200: # not the plain single level layout
        raise ValueError(f"{name}: unexpected size")

    return np.frombuffer(data[start:end], dtype=dtype).reshape(height, width)[::-1] # stored bottom to top


def fit_top_height(ground, positions, half):
    """(metres, note): the top of the 16 bit height range, from the placed items' heights (trimmed fit through the origin, rounded to 5 m)."""
    h, w = ground.shape # the picture is centred on the level's origin
    xs, ys = [], []

    for x, height, z in positions:
        col, row = (w - 1) / 2 + x * PIXELS_PER_METRE, (h - 1) / 2 - z * PIXELS_PER_METRE

        if 0 <= col <= w - 1 and 0 <= row <= h - 1:
            xs.append(float(ground[int(round(row)), int(round(col))]))
            ys.append(height)

    xs, ys = np.array(xs), np.array(ys)
    keep = xs > 1000 # items on the lowest ground say little about the scale

    if keep.sum() < 4:
        return None, f"only {len(xs)} usable items"

    xs, ys = xs[keep], ys[keep]
    ok = np.ones(len(xs), bool)

    for _ in range(4): # drop items that sit far from the fit (on bridges, in the air ...) and refit
        scale = (xs[ok] @ ys[ok]) / (xs[ok] @ xs[ok])
        res = ys - scale * xs
        ok = np.abs(res) < max(1.0, 2.5 * np.std(res[ok]))

    scale = (xs[ok] @ ys[ok]) / (xs[ok] @ xs[ok])
    resid = float(np.std((ys - scale * xs)[ok]))
    top = round(scale * 65535 / 5) * 5
    return float(top), f"{int(ok.sum())}/{len(xs)} items, fitted {scale * 65535:.1f} m, residual {resid:.2f} m"


def load_terrain(area_id):
    """Terrain(ground metres array (north at the top), water surface array or None, top height, note, half span) or None when the level has no height map"""
    pak = zipfile.ZipFile(gamefiles.list_level_paks()[area_id])
    names = {i.filename.replace("\\", "/").rsplit("/", 1)[-1]: i.filename for i in pak.infolist()}
    height = [n for n in names if n.endswith("_height_map.pct") and not n.endswith("_water_height_map.pct")]

    if not height:
        return None

    ground = read_pct(pak, names[height[0]], 2, "<u2")
    water = [n for n in names if n.endswith("_water_height_map.pct")]
    water = read_pct(pak, names[water[0]], 4, "<f4") if water else None
    data = gamefiles.read_data_for_ssl(area_id)
    half = level_data.area_half_span(data)
    top, note = fit_top_height(ground, level_data.parse_level_item_positions(data), half)

    if top is None:
        top = 100.0
        note += " - assumed 100 m"

    return Terrain(ground.astype(np.float32) * (top / 65535), water, top, note, half)


def shade(ground, out_size, metres_per_pixel, strength=SHADE_STRENGTH):
    """Brightness change (about -limit..limit, 0 on flat ground) of the relief lit from the north west, at out_size (w, h)"""
    g = np.asarray(Image.fromarray(ground).resize(out_size, Image.LANCZOS))
    dy, dx = np.gradient(ndi.gaussian_filter(g, 1.0), metres_per_pixel)
    toward_light = np.arctan(dx * np.cos(LIGHT_AZIMUTH) + dy * np.sin(LIGHT_AZIMUTH))
    toward_light = toward_light / (np.std(toward_light) + 1e-6) * strength
    return np.clip(toward_light, -SHADE_LIMIT, SHADE_LIMIT), g


def depth_map(g, water, out_size):
    """Water depth in metres at out_size, from the coarse water surface and the ground (resampled to out_size)"""
    has = water > NO_WATER
    wh, ww = water.shape
    nearest = ndi.distance_transform_edt(~has, return_distances=False, return_indices=True)
    level = np.asarray(Image.fromarray(water[tuple(nearest)].astype(np.float32)).resize(out_size, Image.BILINEAR)) # no-water cells take the level of the nearest water, so there is nothing to smear
    cells = ndi.zoom(has.astype(np.float32), (out_size[1] / wh, out_size[0] / ww), order=0)
    reach = ndi.distance_transform_edt(cells < 0.5) <= WATER_REACH * max(out_size[0] / ww, out_size[1] / wh)
    return np.where(reach, np.clip(level - g, 0, None), 0)


# Water colour by depth, the same on every level so a colour always means the same depth: bright cyan where a vehicle can still cross, through blues to navy where it is submerged.
WATER_RAMP = [(0.5, (150, 240, 255)), (1.0, (70, 200, 255)), (1.5, (20, 150, 245)), (2.0, (10, 100, 215)), (3.0, (0, 50, 165)), (5.0, (0, 15, 95))]


def water_color(depth):
    metres, colors = zip(*WATER_RAMP)
    return np.dstack([np.interp(depth, metres, [c[i] for c in colors]) for i in range(3)]).astype(np.float32)


def render(texture, terrain, out_size, metres_per_pixel, objects=None):
    """out_size (w, h) is the map picture at the app's scale (metres_per_pixel on it); returns (shaded map image RGB, water depth overlay RGBA or None, deepest colour depth in metres)"""
    base = np.asarray(texture.convert("RGB").resize(out_size, Image.LANCZOS), dtype=np.float32)
    s, g = shade(terrain.ground, out_size, metres_per_pixel)
    shaded = Image.fromarray(np.clip(base * (1 + s[..., None]), 0, 255).astype(np.uint8))

    depth = depth_map(g, terrain.water, out_size) if terrain.water is not None else None

    if objects is not None: # trees and bushes seen from above
        from utils import level_objects

        col = np.clip((out_size[0] / 2 + objects.x / metres_per_pixel).astype(int), 0, out_size[0] - 1)
        row = np.clip((out_size[1] / 2 - objects.z / metres_per_pixel).astype(int), 0, out_size[1] - 1)
        keep = np.ones(len(objects.x), bool)

        if depth is not None: # no trees standing in the water
            keep &= depth[row, col] <= DEPTH_MIN

        objects = level_objects.subset(objects, keep)

        S = TREE_SUPERSAMPLE
        big = shaded.convert("RGBA").resize((out_size[0] * S, out_size[1] * S), Image.LANCZOS)
        big.alpha_composite(level_objects.shadows(objects, out_size, metres_per_pixel, S))
        canvas = np.asarray(big.convert("RGB"), dtype=np.float32).copy()
        level_objects.paint_trees(canvas, objects, metres_per_pixel, ndi.gaussian_filter(base, (1.5, 1.5, 0)), metres_per_pixel, S)
        shaded = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8)).resize(out_size, Image.LANCZOS)

    if terrain.water is None:
        return shaded, None, 0.0

    wet = depth > DEPTH_MIN

    if not wet.any():
        return shaded, None, 0.0

    vmax = float(np.percentile(depth[wet], 98)) # for the notes only: the colours don't depend on it
    color = water_color(depth) * (1 + 0.5 * s[..., None]) # a little relief shows through
    alpha = np.clip((depth - DEPTH_MIN) / (DEPTH_FULL - DEPTH_MIN), 0, 1)
    overlay = np.dstack([np.clip(color, 0, 255), alpha * 255]).astype(np.uint8)
    return shaded, Image.fromarray(overlay, "RGBA"), vmax
