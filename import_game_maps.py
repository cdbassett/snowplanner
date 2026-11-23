#!/usr/bin/env python3
"""Use the game's own area maps and map icons.

* Every area's map (level_xx_nn_map, shared_textures.pak) is resized to 1000 px on its longest side, given hillshading from the level's height map and saved as
  map_images/<region>_<area>_normal.png; the water depth (water surface - ground) is saved next to it as a transparent <region>_<area>_water.png overlay (see utils/terrain_maps.py).
  Trees and bushes (placed objects of the level's data.stg, see utils/level_objects.py) are drawn on the map from above; data/map_height_scales.tsv records the height range found per level.
  The pictures it replaces are moved to potential_map_images/previous_area_maps/ (the old "_icon" pictures, which had the icons painted in, are no longer used).
* Every zone the game draws an icon for (its "model kind": task, delivery, garage, gateway, watch tower, ...) is written to data/map_zone_icons.tsv with its
  position on the 0-1000 map, and the icons used are extracted from gfx.pak to assets/map_icons/<name>.png. The app paints these on the map when "Icons" is checked.

Positions of the map items are not touched here: run `python3 import_new_regions.py --reset-positions` to take them from the game files too.

* The main page's region pictures (assets/region_<region id>.jpg, 500 px wide) are the game's area background pictures (gfx.pak, levelus_0201_i1 ...) of each
  region's first area (the lowest area number). The pictures they replace are moved to potential_map_images/previous_region_images/.

    python3 import_game_maps.py [--area AREA_ID ...] [--no-maps] [--no-icons] [--no-regions] [--no-trees]
"""
import argparse
import concurrent.futures
import functools
import json
import re
import shutil
import sqlite3
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev"))

import extract_gfx_icons
import extract_gfx_textures
import extract_map_textures
from database.config import snowplanner_db_filename
from utils import gamefiles, level_data, level_objects, level_scene, level_splines, level_structures, objective_models, terrain_maps
from utils.snowrunner_utils import slugify_region_area

MAP_SIZE = 1000
ICON_SIZE = 64
ICON_SUBSTITUTES = {"trailerShopImg40": "trailerStoreImg40"} # the game's trailer shop symbol draws nothing here: its trailer store symbol is the same picture (without an outline, which is added)
ICON_TINTS = {"garageImg": (165, 212, 245), "trailerShopImg40": (165, 212, 245), "fuelStationImg": (255, 205, 145)} # the white of these icons: garages and trailer stores light blue, fuel stations light orange
COURSE_POINT = re.compile(r"(RACE|RING|DOWNHILL|CONTEST)\w*_(\d+|FINISH)$|_FINISH$|SCOUT_(\d+|END)$") # zone names of race / contest checkpoints
PERMANENT_ICONS = {"garageImg", "watchTowerImg", "gatewayImg", "serviceHubImg", "townStorage", "fuelStationImg", "trailerShopImg40", "trailerShopImg", "factoryImg", "sawmillImg", "lumberjackImg"} # places that stay, whatever objectives use them
MAP_IMAGE_DIR = ROOT / "map_images"
TEXTURE_DIR = ROOT / "extracted_map_textures"
PREVIOUS_DIR = ROOT / "potential_map_images" / "previous_area_maps"
ICON_DIR = ROOT / "assets" / "map_icons"
ASSET_DIR = ROOT / "assets"
PREVIOUS_REGION_DIR = ROOT / "potential_map_images" / "previous_region_images"
REGION_IMAGE_WIDTH = 500
ICON_TABLE = ROOT / "data" / "map_zone_icons.tsv"
SCALE_TABLE = ROOT / "data" / "map_height_scales.tsv"
ICON_WORK_DIR = ROOT / "extracted_gfx" / "map_zone_icons"
Image.MAX_IMAGE_PIXELS = None


def region_areas():
    con = sqlite3.connect(f"file:{snowplanner_db_filename}?mode=ro", uri=True)
    return {area_id: slugify_region_area(region, abbrev) for area_id, region, abbrev in con.execute("select area_id, region, abbrev from region_area order by seq")}


def padded(image):
    """A picture smaller than the 1000 x 1000 map (a level that covers less ground) is centred on a transparent canvas, so the positions on the map stay right."""
    if max(image.size) >= MAP_SIZE - 1:
        return image

    square = Image.new("RGBA", (MAP_SIZE, MAP_SIZE), (0, 0, 0, 0))
    square.paste(image.convert("RGBA"), ((MAP_SIZE - image.width) // 2, (MAP_SIZE - image.height) // 2))
    return square


BUILT_DIR = ROOT / "data" / "built_structures"
PLAIN_DIR = TEXTURE_DIR / "plain" # the map and water pictures before the structures are drawn in, so that the structures can be redone without rebuilding the trees


@functools.cache
def objective_ids():
    con = sqlite3.connect(f"file:{snowplanner_db_filename}?mode=ro", uri=True)
    return {r[0] for r in con.execute("select id from objective")}


def import_structures(area_id, slug, size, metres_per_pixel):
    """Draw the bridges, rails and pipelines that are always there into the area's map picture (from the plain picture in PLAIN_DIR; the water overlay is made transparent under them, so
    that they are not tinted), and write data/built_structures/<area id>.json with the vector shapes of what each contract model builds and the objectives that build it. Returns a note for the log."""
    BUILT_DIR.mkdir(parents=True, exist_ok=True)
    (BUILT_DIR / f"{area_id}.json").unlink(missing_ok=True)

    try:
        scene = level_scene.load_scene(area_id)
        always, built = level_structures.render_layers(scene, size, metres_per_pixel, level_splines.load_splines(area_id))
        always = padded(always)
        plain = Image.open(PLAIN_DIR / f"{slug}_normal.png").convert("RGBA")
        plain.alpha_composite(always)
        plain.convert("RGB").save(MAP_IMAGE_DIR / f"{slug}_normal.png", optimize=True)

        if (PLAIN_DIR / f"{slug}_water.png").exists():
            water = np.array(Image.open(PLAIN_DIR / f"{slug}_water.png").convert("RGBA"))
            water[..., 3] = (water[..., 3] * (1 - np.array(always)[..., 3] / 255.0)).astype(np.uint8)
            Image.fromarray(water, "RGBA").save(MAP_IMAGE_DIR / f"{slug}_water.png", optimize=True)

        owners = objective_models.objective_models(objective_ids())
        layers = {tag: {"objectives": list(owners.get((area_id, tag), ())), "shapes": shapes} for tag, shapes in built.items()}

        if layers:
            (BUILT_DIR / f"{area_id}.json").write_text(json.dumps(layers, separators=(",", ":")), encoding="utf-8")

        return ", bridges / rails / pipes" + (f" + {len(layers)} built ({sum(1 for v in layers.values() if not v['objectives'])} without objective)" if layers else "")
    except Exception as e:
        print(f"{area_id}: no bridges / pipes ({e})", flush=True)
        return ""


def map_size(area_id, level):
    """(picture size in pixels, metres per pixel) of an area's map picture: 1000 px on the longest side, unless the level is smaller than its map span."""
    image = Image.open(TEXTURE_DIR / f"{level}_map.png")
    half = level_data.area_half_span(gamefiles.read_data_for_ssl(area_id)) # the app's 0-1000 map spans 2 * half metres
    metres_per_pixel = 2 * half / MAP_SIZE
    return (round(image.width / terrain_maps.PIXELS_PER_METRE / metres_per_pixel), round(image.height / terrain_maps.PIXELS_PER_METRE / metres_per_pixel)), metres_per_pixel


def import_one_map(area_id, slug, level, trees, structures=True):
    """Build one area's map picture(s); returns (area id, (top height, fit note, water colour range) or None, log line)"""
    for typ in ("normal", "icon"):
        old = MAP_IMAGE_DIR / f"{slug}_{typ}.png"

        if old.exists():
            shutil.move(old, PREVIOUS_DIR / old.name) if not (PREVIOUS_DIR / old.name).exists() else old.unlink()

    image = Image.open(TEXTURE_DIR / f"{level}_map.png")
    size, metres_per_pixel = map_size(area_id, level)
    water_path = MAP_IMAGE_DIR / f"{slug}_water.png"
    water_path.unlink(missing_ok=True)
    scale = None

    try:
        terrain = terrain_maps.load_terrain(area_id)
    except Exception as e: # no usable height map: the plain map
        terrain, note = None, f"no relief ({e})"

    if terrain:
        objects = None

        if trees:
            try:
                objects = level_objects.load_objects(area_id, terrain.ground)
            except Exception as e: # unreadable scene data: no trees on this map
                print(f"{area_id}: no trees ({e})", flush=True)

        shaded, water, vmax = terrain_maps.render(image, terrain, size, metres_per_pixel, objects)
        padded(shaded).save(MAP_IMAGE_DIR / f"{slug}_normal.png", optimize=True)
        note = f"top height {terrain.top_height:.0f} m ({terrain.fit_note})" + (f", {len(objects.x)} objects" if objects is not None else "")

        if water:
            padded(water).save(water_path, optimize=True)
            note += f", water depth to {vmax:.1f} m"

        scale = (terrain.top_height, terrain.fit_note, f"{vmax:.1f}")
    else:
        padded(image.convert("RGB").resize(size, Image.LANCZOS)).save(MAP_IMAGE_DIR / f"{slug}_normal.png", optimize=True)

    if structures:
        PLAIN_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy(MAP_IMAGE_DIR / f"{slug}_normal.png", PLAIN_DIR / f"{slug}_normal.png")
        (PLAIN_DIR / f"{slug}_water.png").unlink(missing_ok=True)

        if water_path.exists():
            shutil.copy(water_path, PLAIN_DIR / f"{slug}_water.png")

        note += import_structures(area_id, slug, size, metres_per_pixel)

    return area_id, scale, f"{area_id}: {image.size[0]}x{image.size[1]} -> {slug}_normal.png; {note}"


def import_maps(slugs, trees=True, jobs=3, structures=True):
    """slugs: {area id: file name stem}"""
    levels = {a: gamefiles.list_level_paks()[a].stem for a in slugs} # the level's file name: usually level_us_12_04, sometimes with a suffix (_new, _crop)
    missing = [lvl for lvl in levels.values() if not (TEXTURE_DIR / f"{lvl}_map.png").exists()]

    if missing:
        extract_map_textures.main(TEXTURE_DIR, missing)

    PREVIOUS_DIR.mkdir(parents=True, exist_ok=True)
    scales = {}

    with concurrent.futures.ProcessPoolExecutor(max_workers=max(1, jobs)) as pool:
        for area_id, scale, line in pool.map(import_one_map, list(slugs), list(slugs.values()), [levels[a] for a in slugs], [trees] * len(slugs), [structures] * len(slugs)):
            print(line, flush=True)

            if scale:
                scales[area_id] = scale

    rows = {}

    if SCALE_TABLE.exists(): # keep the rows of areas that were not imported this time
        rows = {line.split("\t")[0]: line.rstrip("\n") for line in SCALE_TABLE.read_text(encoding="utf-8").splitlines()[1:]}

    rows.update({a: "\t".join([a, f"{t:.0f}", n, v]) for a, (t, n, v) in scales.items()})

    with open(SCALE_TABLE, "w", encoding="utf-8") as f:
        f.write("area_id\ttop_height_m\tfit\twater_colour_range_m\n")
        f.writelines(rows[a] + "\n" for a in sorted(rows))


def import_region_images():
    con = sqlite3.connect(f"file:{snowplanner_db_filename}?mode=ro", uri=True)
    first = {}

    for region_id, area_id in con.execute("select region_id, area_id from region_area order by area_id"):
        first.setdefault(region_id, area_id)

    PREVIOUS_REGION_DIR.mkdir(parents=True, exist_ok=True)
    work = ROOT / "extracted_gfx" / "areas"

    for region_id, area_id in sorted(first.items()):
        prefix, region_no, area_no = area_id.lower().split("_") # US_02_01 -> levelus_0201_i1
        name = f"level{prefix}_{region_no}{area_no}_i1"

        try:
            extract_gfx_textures.main(work, [name])
        except KeyError:
            print(f"{region_id}: no background picture {name} in gfx.pak, kept the existing one")
            continue

        image = Image.open(work / f"{name}.png").convert("RGB")
        target = ASSET_DIR / f"region_{region_id.lower()}.jpg"

        if target.exists() and not (PREVIOUS_REGION_DIR / target.name).exists():
            shutil.move(target, PREVIOUS_REGION_DIR / target.name)

        image.resize((REGION_IMAGE_WIDTH, round(image.height * REGION_IMAGE_WIDTH / image.width)), Image.LANCZOS).save(target, quality=88, optimize=True)
        print(f"{region_id}: {name} -> {target.relative_to(ROOT)}")


def outlined(icon, width=2):
    """The icon with a black outline around its shape"""
    big = Image.new("RGBA", (icon.width + 2 * width, icon.height + 2 * width), (0, 0, 0, 0))
    big.paste(icon, (width, width))
    out = Image.new("RGBA", big.size, (0, 0, 0, 0))
    out.paste(Image.new("RGBA", big.size, (0, 0, 0, 255)), (0, 0), big.getchannel("A").filter(ImageFilter.MaxFilter(2 * width + 1)))
    out.alpha_composite(big)
    return out


def import_icons(area_ids):
    rows = []

    for area_id in area_ids:
        data = gamefiles.read_data_for_ssl(area_id)
        zones = level_data.parse_level_zones(data)
        half = level_data.area_half_span(data, zones)

        for zone_id, zone in zones.items():
            p = level_data.zone_placement(data, zone)

            if abs(p.x) < 3000 and abs(p.z) < 3000 and zone.model_kind:
                rows.append((area_id, zone_id, zone.model_kind, *level_data.world_to_db(p.x, p.z, half)))

    names = sorted({r[2] for r in rows} | {r[2][:-2] for r in rows if r[2].endswith("40")} | set(ICON_SUBSTITUTES.values())) # some zones name a 40 px icon that only exists without the size
    ICON_WORK_DIR.mkdir(parents=True, exist_ok=True)
    extract_gfx_icons.main(ICON_WORK_DIR, ["icons_lib"], only=names)
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    found = {p.stem for p in (ICON_WORK_DIR / "icons_lib").glob("*.png")}

    for name in sorted(found & set(names)):
        icon = Image.open(ICON_WORK_DIR / "icons_lib" / f"{ICON_SUBSTITUTES.get(name, name)}.png").convert("RGBA")
        icon.thumbnail((ICON_SIZE, ICON_SIZE), Image.LANCZOS) # extracted at 4x

        if name in ICON_SUBSTITUTES:
            icon = outlined(icon)

        if name in ICON_TINTS: # white -> the colour, black stays black
            r, g, b, a = icon.split()
            tint = ICON_TINTS[name]
            icon = Image.merge("RGBA", (r.point(lambda v: v * tint[0] // 255), g.point(lambda v: v * tint[1] // 255), b.point(lambda v: v * tint[2] // 255), a))

        icon.save(ICON_DIR / f"{name}.png", optimize=True)

    rows = [(a, z, i[:-2] if i not in found and i.endswith("40") else i, x, y) for a, z, i, x, y in rows]
    unknown = sorted({r[2] for r in rows if r[2] not in found})
    rows = [r for r in rows if r[2] in found]
    used, rewarded, opens = objective_models.zone_objectives(objective_ids(), {r[1] for r in rows})
    ids = objective_ids()
    # objectives that use the zone (its icon is hidden once all are completed), and 1 when the icon stays regardless: a place that stays (garage, watch tower ...) or one that a reward opens
    def uses(a, z, i):
        """the objectives that use a zone; a task's other start spots and sub markers that only the level script defines are the zones whose name begins with the task's id"""
        found = used.get(z)

        if not found and i in ("taskImg40", "taskSubImg40"):
            found = [max((o for o in ids if o.startswith(a) and z.startswith(o) and len(o) > len(a) + 4), key=len, default=None)]

            if not found[0]: # not named after the task's id: strip the spot suffix (_a, _02, _GIVER_01 ...) and take the tasks whose ids begin with what is left
                stem = z

                while not found[0]:
                    shorter = re.sub(r"(_GIVER(_\d+)?|_TSK|_TASK|_DELIVERY|_\d+|\d*[a-z]|_[A-Z])$", "", stem)

                    if shorter == stem or len(shorter) <= len(a) + 4:
                        break

                    stem = shorter
                    found = sorted(o for o in ids if o.startswith(stem))[:3] or [None]

        return [o for o in found or () if o]

    rows = [(a, z, i, x, y, ",".join(uses(a, z, i)), int(z in rewarded or i in PERMANENT_ICONS), ",".join(opens.get(z, ()))) for a, z, i, x, y in rows]
    before = len(rows)
    rows = [r for r in rows if not (r[2] in ("taskImg40", "taskSubImg40") and not r[5] and COURSE_POINT.search(r[1]))] # the points of a race / contest course are not task starts: the contest's own start icon stays
    print(f"{before - len(rows)} race / contest course points left out")

    # a garage or trailer store whose zone the game gives no icon kind (it still has a spot in the database): its icon from the map items
    known = {r[1] for r in rows}
    con = sqlite3.connect(f"file:{snowplanner_db_filename}?mode=ro", uri=True)

    for zone, area, kind, x, y in con.execute("select id, area_id, item_type, x, y from map_item where item_type in ('garage', 'trlstore') and x is not null"):
        if zone not in known and area in area_ids:
            rows.append((area, zone, "garageImg" if kind == "garage" else "trailerShopImg40", x, y, "", 1, ""))

    if ICON_TABLE.exists(): # keep the other areas' rows when only some areas were imported
        rows = [tuple(line.rstrip("\n").split("\t")) for line in ICON_TABLE.read_text(encoding="utf-8").splitlines()[1:] if line.split("\t")[0] not in area_ids and line.count("\t") == 7] + rows

    with open(ICON_TABLE, "w", encoding="utf-8") as f:
        f.write("area_id\tzone_id\ticon\tx\ty\tobjectives\tkeep\topens_with\n")
        f.writelines("\t".join(map(str, r)) + "\n" for r in rows)

    print(f"{len(rows)} zone icons in {len({r[0] for r in rows})} areas, {len(found & set(names))} icon pictures in {ICON_DIR.relative_to(ROOT)}; zone kinds without an icon in the game's icon library (skipped): {unknown}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--area", action="append", metavar="AREA_ID")
    parser.add_argument("--no-maps", action="store_true")
    parser.add_argument("--no-icons", action="store_true")
    parser.add_argument("--no-regions", action="store_true")
    parser.add_argument("--no-trees", action="store_true", help="leave the trees and bushes out of the map pictures")
    parser.add_argument("--no-structures", action="store_true", help="leave out the bridge / rail / pipeline layers")
    parser.add_argument("--structures-only", action="store_true", help="only (re)build the bridge / rail / pipeline layers")
    parser.add_argument("--jobs", type=int, default=3, help="areas built at the same time (each needs about 1 GB)")
    parser.add_argument("--regions-only", action="store_true")
    args = parser.parse_args()
    slugs = {a: s for a, s in region_areas().items() if not args.area or a in args.area}

    if args.structures_only:
        levels = {a: gamefiles.list_level_paks()[a].stem for a in slugs}

        for a, slug in slugs.items():
            size, mpp = map_size(a, levels[a])
            print(a + import_structures(a, slug, size, mpp), flush=True)

        sys.exit()

    if args.regions_only:
        import_region_images()
        sys.exit()

    if not args.no_maps:
        import_maps(slugs, trees=not args.no_trees, jobs=args.jobs, structures=not args.no_structures)

    if not args.no_icons:
        import_icons(list(slugs))

    if not args.no_regions and not args.area:
        import_region_images()
