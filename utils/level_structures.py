"""Bridges, rails and pipelines of a level seen from above, drawn from the placed objects of utils/level_scene.py.

Each object's footprint is its model's bounding box carried through the object's matrix. Pieces that only exist once a contract is done (they carry the contract's
model tag, e.g. the bridge a "build a bridge" contract adds) are drawn on a separate layer, so the app can show them on request.
"""
import math
import re

import numpy as np
from PIL import Image, ImageDraw

SUPERSAMPLE = 4
RAIL_BED_WIDTH = 5.0 # metres: a track with its ballast
MIN_WIDTH = 2.6 # metres: thinner pipes and rails would vanish at the map's scale
LIGHT_SHIFT = 0.4 # metres of shadow per metre of height, thrown east (the light comes from the west, like the trees')
MAX_SHIFT = 5.0

EXCLUDE = re.compile(r"support|bridge.*_base|beam|pillar|_upper|_middle|rollers|cable_car|culvert|lattice|limiter|holder|valve|plug|wire|distribution|chamfer|corner|smoke|sewer|rail_blocker|"
                     r"carriage|crossing|station|depot|camerabridge|blockpost|^overpass_01_a|^big_pipes|^small_pipes|_set$|^rus_glg|_side$|_nocross|fuel|launchpad|factory|conveyor|logs|ejection|^rus_pipe|^pipe_oil_us_base")
BRIDGE = re.compile(r"bridge|overpass|viaduct", re.I)
RAIL = re.compile(r"^(rail_01|rails_|iron_road|crushing_plant_rails)", re.I)
PIPE = re.compile(r"^(pipe_|water_pipe|ru08_pipegaz|us_lumbermill.*pipes|exploded_water_pipe)", re.I)

# fill, outline (RGB) for each kind of structure
STYLE = {
    "wood": ((150, 112, 72), (70, 50, 32)),
    "concrete": ((158, 155, 148), (52, 50, 48)),
    "metal": ((120, 126, 134), (44, 48, 54)),
    "broken": ((160, 112, 96), (84, 46, 38)),
    "pontoon": ((106, 112, 118), (46, 50, 54)),
    "rail": ((168, 156, 138), (96, 88, 76)), # the ballast bed
    "pipe": ((176, 142, 70), (70, 52, 24)),
    "water pipe": ((118, 150, 178), (40, 60, 82)),
    "rusty pipe": ((156, 98, 68), (72, 40, 28)),
}
BUILT_OUTLINE = (255, 214, 64)
ROAD = {"wood": (112, 80, 52), "concrete": (88, 88, 92), "metal": (84, 88, 94), "broken": (120, 80, 68), "rail": (58, 50, 46)} # the driving surface in the middle of a deck
ROAD_SHARE = {"rail": 0.4} # how much of a deck's (a track's) width the driving surface (the rails) takes: the rest unless given here, 0.68
DEFAULT_ROAD_SHARE = 0.68
PIPE_SUPPORTS = ("pipe_oil_us_base",) # supports every 8 m along a pipeline whose pipes are not placed objects: the pipeline is drawn between them
PIPE_WIDTH = 2.2


def kind_of(name):
    """Which kind of structure the model is (a key of STYLE), or None for everything else."""
    if EXCLUDE.search(name):
        return None

    if RAIL.search(name):
        return "rail"

    if BRIDGE.search(name):
        if re.search(r"broken|break", name):
            return "broken"

        if "pontoon" in name:
            return "pontoon"

        if re.search(r"wood|logs|plank", name):
            return "wood"

        if re.search(r"metal|truss|railroad|railway|rus_|glg", name):
            return "metal"

        return "concrete"

    if PIPE.search(name):
        return "water pipe" if "water" in name else "rusty pipe" if "rusty" in name else "pipe"

    return None


def footprint(obj, bbox):
    """The four corners (world x, z) of the object's bounding box on the ground, and the box's height."""
    (x0, y0, z0, x1, y1, z1) = bbox
    ax, ay, az = obj.axes
    ym = (y0 + y1) / 2
    corners = []

    for lx, lz in ((x0, z0), (x1, z0), (x1, z1), (x0, z1)):
        corners.append((obj.x + lx * ax[0] + ym * ay[0] + lz * az[0], obj.z + lx * ax[2] + ym * ay[2] + lz * az[2]))

    return corners, (y1 - y0) * math.sqrt(sum(c * c for c in ay))


def widen(corners, minimum):
    """Make the box at least `minimum` metres wide across (its shorter side), keeping its centre and direction."""
    c = np.array(corners)
    centre = c.mean(axis=0)
    u, v = c[1] - c[0], c[3] - c[0]
    lu, lv = np.linalg.norm(u), np.linalg.norm(v)

    if lu < 1e-6 or lv < 1e-6:
        return corners

    if lu < minimum:
        u = u / lu * minimum
    if lv < minimum:
        v = v / lv * minimum

    a = centre - u / 2 - v / 2
    return [tuple(a), tuple(a + u), tuple(a + u + v), tuple(a + v)]


def inset(corners, share):
    """The middle `share` of the box across its shorter side (its whole length), as four corners."""
    c = np.array(corners)
    u, v = c[1] - c[0], c[3] - c[0]

    if np.linalg.norm(u) < np.linalg.norm(v):
        return [tuple(p) for p in (c[0] + u * (1 - share) / 2, c[0] + u * (1 + share) / 2, c[3] + u * (1 + share) / 2, c[3] + u * (1 - share) / 2)]

    return [tuple(p) for p in (c[0] + v * (1 - share) / 2, c[1] + v * (1 - share) / 2, c[1] + v * (1 + share) / 2, c[0] + v * (1 + share) / 2)]


def pipelines(scene):
    """Boxes of the pipes between the supports of the pipelines: each support is joined to the next one in the direction its pipe runs."""
    supports = [o for o in scene.objects if o.name in PIPE_SUPPORTS and not o.tag]
    out = []

    if len(supports) < 2:
        return out

    pos = np.array([[o.x, o.z] for o in supports])
    run = np.array([[o.axes[2][0], o.axes[2][2]] for o in supports])
    run /= np.linalg.norm(run, axis=1)[:, None]
    gap = np.linalg.norm(pos[:, None] - pos[None], axis=2)
    np.fill_diagonal(gap, np.inf)

    for i, o in enumerate(supports):
        for j in np.flatnonzero(gap[i] < 12):
            if j > i:
                v = (pos[j] - pos[i]) / gap[i, j]

                if abs(float(v @ run[i])) > 0.9:
                    n = np.array([-v[1], v[0]]) * PIPE_WIDTH / 2
                    a, b = pos[i], pos[j]
                    out.append(("pipe", [tuple(a - n), tuple(b - n), tuple(b + n), tuple(a + n)], 1.8, False, o.y + 8))

    return out


def structures(scene, has_pipeline_spline=False):
    """[(kind, corners, height, tag, top)] of the bridges, rails and pipes of a scene, lowest first (so that higher structures are painted over lower ones)."""
    boxes = {name: bbox for name, _, bbox in scene.library}
    out = []

    for obj in scene.objects:
        kind = kind_of(obj.name)

        if kind is None or (obj.tag and "objective" not in obj.name) or ("objective" in obj.name and not obj.tag):
            continue

        corners, height = footprint(obj, boxes[obj.name])

        if max(math.dist(corners[0], corners[1]), math.dist(corners[0], corners[3])) < 3: # too small to be part of a bridge / pipeline
            continue

        if kind in ("rail", "pipe", "water pipe", "rusty pipe"):
            corners = widen(corners, RAIL_BED_WIDTH if kind == "rail" else MIN_WIDTH)

        out.append((kind, corners, height, obj.tag, obj.y))

    if not has_pipeline_spline:
        out.extend(pipelines(scene))

    out.sort(key=lambda s: (s[4], s[2]))
    return out


# (width in metres, colour) of the layers a spline is drawn with, lowest first; shadow shift in metres
LINE_STYLE = {
    "rail": [(5.0, (168, 156, 138, 255)), (2.0, (58, 50, 46, 255))], # the ballast bed and the rails
    "rail abandoned": [(5.0, (150, 140, 120, 170)), (2.0, (96, 78, 62, 220))],
    "pipe": [(3.6, (70, 52, 24, 255)), (2.4, (190, 154, 76, 255))],
    "water pipe": [(3.0, (40, 60, 82, 255)), (1.8, (118, 150, 178, 255))],
}


def spline_lines(splines):
    """[(style, [(x, z)])] of the rails and pipelines of a level's splines (utils/level_splines.py)"""
    out = []

    for name, found in (splines or {}).items():
        style = "rail abandoned" if "abandoned" in name else "rail" if re.match(r"iron_road|rails_|overlay_rails", name) else "water pipe" if "water" in name else "pipe"
        out.extend((style, pts) for pts, _ in found)

    return out


def draw(items, size, metres_per_pixel, lines=()):
    """RGBA layer (size = (w, h) pixels, the map's picture size) with the structures and their shadows."""
    S = SUPERSAMPLE
    W, H = size[0] * S, size[1] * S
    mpp = metres_per_pixel / S
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d, sd = ImageDraw.Draw(img), ImageDraw.Draw(shadow)

    def pts(corners, dx=0.0):
        return [(W / 2 + (x + dx) / mpp, H / 2 - z / mpp) for x, z in corners]

    for kind, corners, height, built, _ in items:
        sd.polygon(pts(corners, min(MAX_SHIFT, LIGHT_SHIFT * max(height, 1.5))), fill=(0, 0, 0, 90))

    for style, line in lines:
        if style in ("pipe", "water pipe"):
            sd.line(pts(line, 1.5), fill=(0, 0, 0, 80), width=max(1, round(2.4 / mpp)), joint="curve")

    img.alpha_composite(shadow)
    d = ImageDraw.Draw(img)

    for style in LINE_STYLE: # all the rails first, then the pipes: each kind of layer in turn
        for layer, (width, colour) in enumerate(LINE_STYLE[style]):
            for st, line in lines:
                if st == style:
                    d.line(pts(line), fill=colour, width=max(1, round(width / mpp)), joint="curve")

    for kind, corners, height, built, _ in items:
        fill, outline = STYLE[kind]
        p = pts(corners)
        d.polygon(p, fill=fill + (255,))

        if kind in ROAD: # the driving surface between lighter edges
            d.polygon(pts(inset(corners, ROAD_SHARE.get(kind, DEFAULT_ROAD_SHARE))), fill=ROAD[kind] + (255,))

        d.line(p + [p[0]], fill=outline + (255,), width=max(1, S // 3))

    return img.resize(size, Image.LANCZOS)


def built_shapes(items, metres_per_pixel):
    """{contract model tag: [shape]} for the structures that contracts build, as plain data to be drawn as vectors on the 0-1000 map (x to the right, y down):
    shape = {"k": kind (a key of STYLE), "c": the four corners [x0, y0, ..., x3, y3], "r": the driving surface's corners or None, "s": shadow shift to the east}"""
    def flat(corners):
        return [round(v, 1) for x, z in corners for v in (500 + x / metres_per_pixel, 500 - z / metres_per_pixel)]

    out = {}

    for kind, corners, height, tag, _ in items:
        if tag:
            road = flat(inset(corners, ROAD_SHARE.get(kind, DEFAULT_ROAD_SHARE))) if kind in ROAD else None
            out.setdefault(tag, []).append({"k": kind, "c": flat(corners), "r": road, "s": round(min(MAX_SHIFT, LIGHT_SHIFT * max(height, 1.5)) / metres_per_pixel, 2)})

    return dict(sorted(out.items()))


def render_layers(scene, size, metres_per_pixel, splines=None):
    """(RGBA picture of the structures that are always there, {contract model tag: vector shapes of what it builds}); splines: utils.level_splines.load_splines(area id)"""
    lines = spline_lines(splines)
    items = structures(scene, any(s in ("pipe", "water pipe") for s, _ in lines))
    return draw([s for s in items if not s[3]], size, metres_per_pixel, lines), built_shapes(items, metres_per_pixel)
