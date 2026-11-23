"""Placed vegetation and props of a level, from the level pak's data.stg (reverse engineered, see dev/readme.md).

The start of data.stg has a table of object type names (trees, bushes, rocks, twigs, signs, fences, barrels, vehicles ...): a u32 count, then per name a u16 length,
the ASCII name with its NUL and one more byte. The instances are stored as 32 byte records anywhere in the file:
    float32 x, height, z (world metres, centred on the level)  |  u32 0x40000000 (marker)  |  4 orientation bytes + 0xff  |  4 bytes (the last is a scale?)  |  3 tint bytes + a flag
    |  u32 whose third byte is the index in the name table.
Records are found by their marker, and kept when their position is on the level's ground (the height matches the height map within 2 m)."""
import re
import struct
import zipfile
from collections import namedtuple
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from utils import gamefiles, terrain_maps

MARKER = 0x40000000
Objects = namedtuple("Objects", "names,x,y,z,type,scale,tint") # arrays, one entry per placed object


def read_name_table(data, search=4 << 20):
    """The list of object type names: the longest run of 'u32 count, count x (u16 length, name, NUL, byte)' within the first `search` bytes."""
    head = data[:search]
    a = np.frombuffer(head, dtype=np.uint8)
    name_re = re.compile(rb"[A-Za-z0-9_ .\-]+\Z")
    n = len(a) - 8
    # cheap prefilter: a count of 20..600, then a name length of 2..80 and a letter
    cand = np.flatnonzero((a[2:n + 2] == 0) & (a[3:n + 3] == 0) & (a[5:n + 5] == 0) & (a[4:n + 4] >= 2) & (a[4:n + 4] <= 80) & (a[6:n + 6] >= 0x41) & (a[6:n + 6] <= 0x7a))
    best = []

    for p in cand:
        p = int(p)
        count = struct.unpack_from("<H", head, p)[0]

        if not 20 <= count <= 600 or count <= len(best):
            continue

        q, names = p + 4, []

        for _ in range(count):
            if q + 2 > len(head):
                break

            (ln,) = struct.unpack_from("<H", head, q)
            raw = head[q + 2:q + 2 + ln]

            if not 2 <= ln <= 80 or not raw.endswith(b"\0") or not name_re.match(raw[:-1]):
                break

            names.append(raw[:-1].decode("ascii"))
            q += 2 + ln + 1

        if len(names) == count:
            best = names

    return best


def load_objects(area_id, ground=None, half=None):
    """Objects(...) of an area, or None when there is no scene data"""
    pak = zipfile.ZipFile(gamefiles.list_level_paks()[area_id])
    entry = next((i for i in pak.infolist() if i.filename.replace("\\", "/").endswith("data.stg")), None)

    if entry is None:
        return None

    data = pak.read(entry)
    names = read_name_table(data)

    if ground is None:
        ground = terrain_maps.load_terrain(area_id).ground

    h, w = ground.shape
    arr = np.frombuffer(data, dtype=np.uint8)
    starts = []

    for al in range(4):
        u = np.frombuffer(data[al:al + (len(data) - al) // 4 * 4], dtype="<u4")
        idx = np.flatnonzero(u == MARKER)
        starts.append((idx[idx >= 3] - 3) * 4 + al)

    starts = np.concatenate(starts)
    starts = starts[starts + 32 <= len(data)]
    rec = np.stack([arr[starts + k] for k in range(32)], axis=1)
    pos = np.ascontiguousarray(rec[:, 0:12]).view("<f4").reshape(-1, 3)
    ok = np.isfinite(pos).all(1) & (np.abs(pos[:, 0]) < 1000) & (np.abs(pos[:, 2]) < 1000)
    col = np.where(ok, (w - 1) / 2 + pos[:, 0] * terrain_maps.PIXELS_PER_METRE, 0).astype(int)
    row = np.where(ok, (h - 1) / 2 - pos[:, 2] * terrain_maps.PIXELS_PER_METRE, 0).astype(int)
    ins = ok & (col >= 0) & (col < w) & (row >= 0) & (row < h)
    on_ground = np.zeros(len(pos), bool)
    on_ground[ins] = np.abs(pos[ins, 1] - ground[row[ins], col[ins]]) < 2.0
    on_ground &= rec[:, 12 + 18] < len(names)
    rec, pos = rec[on_ground], pos[on_ground]
    objects = Objects(names, pos[:, 0], pos[:, 1], pos[:, 2], rec[:, 12 + 18].astype(int), rec[:, 12 + 11].astype(np.float32) / 255, rec[:, 12 + 12:12 + 15])
    return without_vegetation_in(objects, area_id, tree_free_areas().get(area_id, ()))


TREE_FREE_TABLE = Path(__file__).resolve().parent.parent / "data" / "tree_free_areas.tsv"


def tree_free_areas():
    """{area id: [(centre x, centre z, radius x, radius z) in metres, ...]} from data/tree_free_areas.tsv: places where the game shows no trees although the level data has some (quarries ...)"""
    out = {}

    if TREE_FREE_TABLE.exists():
        for line in TREE_FREE_TABLE.read_text(encoding="utf-8").splitlines()[1:]:
            parts = line.split("\t")

            if len(parts) >= 5:
                out.setdefault(parts[0], []).append(tuple(float(v) for v in parts[1:5]))

    return out


def without_vegetation_in(objects, area_id, ellipses):
    """The objects without the trees / bushes inside the given ellipses"""
    if not ellipses:
        return objects

    veg = np.isin(objects.type, list(tree_types(objects.names)))
    inside = np.zeros(len(objects.x), bool)

    for cx, cz, rx, rz in ellipses:
        inside |= ((objects.x - cx) / rx) ** 2 + ((objects.z - cz) / rz) ** 2 <= 1

    return subset(objects, ~(veg & inside))


# Tree families: (name regex, crown radius in metres, colour, shape). Anything matching SKIP (fallen trees, stumps, twigs, signs ...) is not drawn as a tree.
SKIP = re.compile(r"lying|stump|chunk|root|twig|stub|sign|banner|fence|cane|fern|flower|ivy|mushroom|broken|log_")
CONE, DOME = "cone", "dome"
TREE_FAMILIES = [
    (re.compile(r"^burnt_(pine|spruce|us_tsuga)"), 1.5, (34, 30, 28), CONE), # charred trees of a burned forest
    (re.compile(r"^burnt_"), 1.2, (52, 44, 38), DOME),
    (re.compile(r"(tsuga|pine|spruce|larch).*dry|dry.*(tsuga|pine)"), 2.0, (66, 56, 48), CONE), # dead conifers
    (re.compile(r"(birch|aspen|poplar|oak|maple|ash_tree|chestnut).*(dry|driedup)"), 2.0, (98, 92, 58), DOME), # leafless broadleaf trees
    (re.compile(r"^dry_bush"), 0.9, (108, 94, 60), DOME),
    (re.compile(r"spruce|tsuga|pine|fir_|larch|cypress|cedar"), 2.4, (24, 56, 36), CONE),
    (re.compile(r"palm|banana|cocos|sabal"), 2.6, (40, 92, 50), DOME),
    (re.compile(r"saman|willow|mangrove|eucalypt|acacia|baobab|big_0"), 3.4, (48, 86, 42), DOME),
    (re.compile(r"cactus|agave|saguaro"), 0.9, (92, 118, 78), DOME),
    (re.compile(r"birch|aspen"), 2.2, (88, 116, 56), DOME),
    (re.compile(r"ash_tree|chestnut|oak|maple"), 3.2, (52, 88, 40), DOME),
    (re.compile(r"small_tree"), 1.5, (66, 96, 48), DOME),
    (re.compile(r"^(bush|birch_bush|dry_bush)"), 0.9, (64, 86, 42), DOME),
]
SNOW_COLOR = np.array([232, 238, 244], np.float32)
LIGHT = np.array([-1.0, -0.12, 0.75]) / np.linalg.norm([-1.0, -0.12, 0.75]) # towards the light: from the west (left on the map), a little north, well above
OPACITY, EDGE_START = 0.9, 0.62 # the crowns are a little see-through, more so near the rim
AMBIENT, CONE_TILT = 0.42, np.deg2rad(58) # the sides of a cone lean this far from vertical
CROWN_SCALE = 1.15 # crowns are drawn a bit larger than their real size so they read at map scale


def tree_types(names):
    """{type index: (crown radius m, colour, shape)} for the names that are trees or bushes"""
    out = {}

    for i, name in enumerate(names):
        if SKIP.search(name):
            continue

        for rx, radius, colour, shape in TREE_FAMILIES:
            if rx.search(name):
                out[i] = (radius, colour, shape)
                break

    return out


# Autumn colours by species, used where the game's map picture shows the ground in warm colours (so the level is in autumn): (name regex, [(weight, colour), ...]).
# Evergreens (spruce, pine ...) are not listed and stay green; dried-up trees are brown.
AUTUMN = [
    (re.compile(r"dry|driedup"), [(0.6, (146, 104, 56)), (0.4, (120, 86, 50))]),
    (re.compile(r"maple"), [(0.5, (196, 62, 34)), (0.35, (214, 104, 36)), (0.15, (204, 150, 44))]),
    (re.compile(r"oak"), [(0.5, (176, 122, 42)), (0.3, (150, 100, 40)), (0.2, (196, 96, 34))]),
    (re.compile(r"birch|aspen|poplar|ash_tree|chestnut|larch|willow|saman|mangrove"), [(0.78, (208, 150, 44)), (0.14, (196, 128, 40)), (0.08, (216, 104, 34))]),
    (re.compile(r"^(small_tree|bush|birch_bush)"), [(0.6, (168, 136, 48)), (0.4, (150, 124, 46))]),
]
ALWAYS_COLOURFUL = re.compile(r"maple") # maples show their red / orange leaves on every level
EVERGREEN = re.compile(r"spruce|tsuga|pine|fir_|cypress|cedar|palm|cactus")


def autumn_group(name):
    """Index into AUTUMN for a type name, or -1 when it keeps its own colour (evergreens, burnt and dead trees)"""
    if EVERGREEN.search(name) or name.startswith("burnt"):
        return -1

    return next((i for i, (rx, _) in enumerate(AUTUMN) if rx.search(name)), -1)


def subset(objects, keep):
    """The objects selected by the boolean mask `keep`"""
    return Objects(objects.names, objects.x[keep], objects.y[keep], objects.z[keep], objects.type[keep], objects.scale[keep], objects.tint[keep])


_sprites = {}


def crown_sprite(shape, radius_px):
    """(shade, alpha) arrays of one crown seen from above and lit from the west: a cone or the top half of a sphere. radius_px is rounded to a quarter pixel."""
    r = max(0.5, round(radius_px * 4) / 4)
    key = (shape, r)

    if key not in _sprites:
        n = int(np.ceil(r * 2)) + 2
        c = (n - 1) / 2
        yy, xx = np.mgrid[0:n, 0:n]
        dx, dy = (xx - c) / r, (yy - c) / r
        d = np.hypot(dx, dy)

        if shape == CONE:
            phi = np.arctan2(dy, dx)
            normal = np.stack([np.cos(phi) * np.sin(CONE_TILT), np.sin(phi) * np.sin(CONE_TILT), np.full_like(d, np.cos(CONE_TILT))], axis=-1)
        else:
            nz = np.sqrt(np.clip(1 - d * d, 0, 1))
            normal = np.stack([dx, dy, nz], axis=-1)

        diffuse = np.clip(normal @ LIGHT, 0, 1)
        shade = AMBIENT + (1 - AMBIENT) * diffuse * 1.15 - 0.12 * d # a little darker towards the rim
        edge = 1 - np.clip((d - EDGE_START) / (1 - EDGE_START), 0, 1) * 0.55 # see-through leaves near the rim
        cover = np.clip((1 - d) * r + 0.5, 0, 1) # anti-aliased outline
        _sprites[key] = (shade.astype(np.float32), (OPACITY * edge * cover).astype(np.float32))

    return _sprites[key]


def rgb_to_hue_sat(rgb):
    """hue (degrees, reds around 0 so reds above 300 count as negative) and saturation of float RGB 0..255 arrays (..., 3)"""
    mx, mn = rgb.max(-1), rgb.min(-1)
    delta = np.where(mx - mn == 0, 1, mx - mn)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    hue = np.where(mx == r, ((g - b) / delta) % 6, np.where(mx == g, (b - r) / delta + 2, (r - g) / delta + 4)) * 60
    hue = np.where(hue > 300, hue - 360, hue)
    return hue, (mx - mn) / np.maximum(mx, 1)


def is_autumn_level(objects, types, ground_rgb, metres_per_pixel):
    """True when the game's map picture is strongly gold / orange under the level's broadleaf trees (Don, Michigan: saturation 0.69 - 0.76, hue about 40 degrees; every other level is
    at most 0.51), i.e. the level is in autumn colours"""
    broad = [i for i, (r, c, shape) in types.items() if shape == DOME and not re.search(r"bush|small_tree|dry|burnt", objects.names[i])]
    chosen = np.flatnonzero(np.isin(objects.type, broad))

    if len(chosen) < 200:
        return False

    h, w, _ = ground_rgb.shape
    col = np.clip((w / 2 + objects.x[chosen] / metres_per_pixel).astype(int), 0, w - 1)
    row = np.clip((h / 2 - objects.z[chosen] / metres_per_pixel).astype(int), 0, h - 1)
    hue, sat = rgb_to_hue_sat(ground_rgb[row, col])
    return bool(np.median(sat) > 0.6 and np.median(hue) < 50)


def crown_colors(objects, chosen, types, ground_rgb, metres_per_pixel):
    """RGB (n, 3) of the chosen trees: the species colour; on an autumn level the broadleaf species take autumn colours picked per tree (maples red / orange, birches yellow ...),
    maples do so on every level; burnt and dead trees keep their dark colours. Snowy ground (white in the picture) dusts the crowns with snow."""
    h, w, _ = ground_rgb.shape
    col = np.clip((w / 2 + objects.x[chosen] / metres_per_pixel).astype(int), 0, w - 1)
    row = np.clip((h / 2 - objects.z[chosen] / metres_per_pixel).astype(int), 0, h - 1)
    tex = ground_rgb[row, col]
    tchosen = objects.type[chosen]
    species = np.array([types[int(t)][1] for t in tchosen], np.float32)
    bright = (0.85 + 0.2 * objects.tint[chosen].mean(axis=1) / 128.0)[:, None]
    autumn_level = is_autumn_level(objects, types, ground_rgb, metres_per_pixel)
    group = np.array([autumn_group(n) for n in objects.names])[tchosen]
    always = np.array([bool(ALWAYS_COLOURFUL.search(n)) for n in objects.names])[tchosen]
    use = (group >= 0) & (always | autumn_level)
    pick = (np.sin(objects.x[chosen] * 12.9898 + objects.z[chosen] * 78.233) * 43758.5453) % 1 # a stable pseudo random number per tree
    autumn = species.copy()

    for gi, (_, palette) in enumerate(AUTUMN):
        m = use & (group == gi)

        if m.any():
            colours = np.array([c for _, c in palette], np.float32)
            idx = np.minimum(np.searchsorted(np.cumsum([wt for wt, _ in palette]), pick[m]), len(palette) - 1)
            autumn[m] = colours[idx]

    colour = np.where(use[:, None], autumn * (0.9 + 0.2 * pick[:, None]), species * bright)
    white = np.clip((tex.min(axis=1) - 110) / 100, 0, 1)
    k = (0.6 * white)[:, None]
    return np.clip(colour * (1 - k) + SNOW_COLOR * k, 0, 255).astype(np.float32)


def paint_trees(canvas, objects, metres_per_pixel, ground_rgb, ground_mpp, supersample):
    """Paint the trees and bushes onto canvas (float32 RGB, h x w x 3, scale metres_per_pixel / supersample per pixel) in place, far (north) to near so nearer crowns cover farther ones.
    ground_rgb (h2 x w2 x 3 floats, ground_mpp metres per pixel) is the map picture the colours are judged from."""
    H, W, _ = canvas.shape
    mpp = metres_per_pixel / supersample
    types = tree_types(objects.names)
    chosen = np.flatnonzero(np.isin(objects.type, list(types)))
    chosen = chosen[np.argsort(-objects.z[chosen], kind="stable")]
    colours = crown_colors(objects, chosen, types, ground_rgb, ground_mpp)
    cx = W / 2 + objects.x[chosen] / mpp
    cy = H / 2 - objects.z[chosen] / mpp

    for n, i in enumerate(chosen):
        radius, _, shape = types[int(objects.type[i])]
        shade, alpha = crown_sprite(shape, CROWN_SCALE * radius * (0.75 + 0.5 * objects.scale[i]) / mpp)
        sh = shade.shape[0]
        x0, y0 = int(round(cx[n] - (sh - 1) / 2)), int(round(cy[n] - (sh - 1) / 2))
        xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + sh, W), min(y0 + sh, H)

        if xa >= xb or ya >= yb:
            continue

        sl = (slice(ya - y0, yb - y0), slice(xa - x0, xb - x0))
        a = alpha[sl][..., None]
        region = canvas[ya:yb, xa:xb]
        region *= 1 - a
        region += colours[n] * shade[sl][..., None] * a


def shadows(objects, size, metres_per_pixel, supersample):
    """RGBA layer with the soft shadows of the crowns, thrown east (the light comes from the west)"""
    S = supersample
    layer = Image.new("RGBA", (size[0] * S, size[1] * S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    mpp = metres_per_pixel / S
    types = tree_types(objects.names)

    for i in np.flatnonzero(np.isin(objects.type, list(types))):
        radius, _, shape = types[int(objects.type[i])]
        r = CROWN_SCALE * radius * (0.75 + 0.5 * objects.scale[i]) / mpp
        cx, cy = layer.width / 2 + objects.x[i] / mpp + 0.9 * r, layer.height / 2 - objects.z[i] / mpp + 0.2 * r
        draw.ellipse((cx - r, cy - r * 0.9, cx + r, cy + r * 0.9), fill=(0, 0, 0, 90))

    return layer.filter(ImageFilter.GaussianBlur(0.5 * S))
