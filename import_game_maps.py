#!/usr/bin/env python3
"""Use the game's own area maps and map icons.

* Every area's map (level_xx_nn_map, shared_textures.pak) is resized to 1000 px on its longest side, given hillshading from the level's height map and saved as
  map_images/<region>_<area>_normal.png; the water depth (water surface - ground) is saved next to it as a transparent <region>_<area>_water.png overlay (see utils/terrain_maps.py).
  data/map_height_scales.tsv records the height range found per level.
  The pictures it replaces are moved to potential_map_images/previous_area_maps/ (the old "_icon" pictures, which had the icons painted in, are no longer used).
* Every zone the game draws an icon for (its "model kind": task, delivery, garage, gateway, watch tower, ...) is written to data/map_zone_icons.tsv with its
  position on the 0-1000 map, and the icons used are extracted from gfx.pak to assets/map_icons/<name>.png. The app paints these on the map when "Icons" is checked.

Positions of the map items are not touched here: run `python3 import_new_regions.py --reset-positions` to take them from the game files too.

    python3 import_game_maps.py [--area AREA_ID ...] [--no-maps] [--no-icons]
"""
import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev"))

import extract_gfx_icons
import extract_map_textures
from database.config import snowplanner_db_filename
from utils import gamefiles, level_data, terrain_maps
from utils.snowrunner_utils import slugify_region_area

MAP_SIZE = 1000
ICON_SIZE = 64
MAP_IMAGE_DIR = ROOT / "map_images"
TEXTURE_DIR = ROOT / "extracted_map_textures"
PREVIOUS_DIR = ROOT / "potential_map_images" / "previous_area_maps"
ICON_DIR = ROOT / "assets" / "map_icons"
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


def import_maps(slugs):
    """slugs: {area id: file name stem}"""
    levels = {a: gamefiles.list_level_paks()[a].stem for a in slugs} # the level's file name: usually level_us_12_04, sometimes with a suffix (_new, _crop)
    missing = [lvl for lvl in levels.values() if not (TEXTURE_DIR / f"{lvl}_map.png").exists()]

    if missing:
        extract_map_textures.main(TEXTURE_DIR, missing)

    PREVIOUS_DIR.mkdir(parents=True, exist_ok=True)
    scales = {}

    for area_id, slug in slugs.items():
        for typ in ("normal", "icon"):
            old = MAP_IMAGE_DIR / f"{slug}_{typ}.png"

            if old.exists():
                shutil.move(old, PREVIOUS_DIR / old.name) if not (PREVIOUS_DIR / old.name).exists() else old.unlink()

        image = Image.open(TEXTURE_DIR / f"{levels[area_id]}_map.png")
        half = level_data.area_half_span(gamefiles.read_data_for_ssl(area_id)) # the app's 0-1000 map spans 2 * half metres
        metres_per_pixel = 2 * half / MAP_SIZE
        size = (round(image.width / terrain_maps.PIXELS_PER_METRE / metres_per_pixel), round(image.height / terrain_maps.PIXELS_PER_METRE / metres_per_pixel)) # 1000 px on the longest side, unless the level is smaller than its map span
        water_path = MAP_IMAGE_DIR / f"{slug}_water.png"
        water_path.unlink(missing_ok=True)

        try:
            terrain = terrain_maps.load_terrain(area_id)
        except Exception as e: # no usable height map: the plain map
            terrain, note = None, f"no relief ({e})"

        if terrain:
            shaded, water, vmax = terrain_maps.render(image, terrain, size, metres_per_pixel)
            padded(shaded).save(MAP_IMAGE_DIR / f"{slug}_normal.png", optimize=True)
            note = f"top height {terrain.top_height:.0f} m ({terrain.fit_note})"

            if water:
                padded(water).save(water_path, optimize=True)
                note += f", water depth to {vmax:.1f} m"

            scales[area_id] = (terrain.top_height, terrain.fit_note, f"{vmax:.1f}")
        else:
            padded(image.convert("RGB").resize(size, Image.LANCZOS)).save(MAP_IMAGE_DIR / f"{slug}_normal.png", optimize=True)

        print(f"{area_id}: {image.size[0]}x{image.size[1]} -> {slug}_normal.png; {note}", flush=True)

    with open(SCALE_TABLE, "w", encoding="utf-8") as f:
        f.write("area_id\ttop_height_m\tfit\twater_colour_range_m\n")
        f.writelines("\t".join([a, f"{t:.0f}", n, v]) + "\n" for a, (t, n, v) in sorted(scales.items()))


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

    names = sorted({r[2] for r in rows} | {r[2][:-2] for r in rows if r[2].endswith("40")}) # some zones name a 40 px icon that only exists without the size
    ICON_WORK_DIR.mkdir(parents=True, exist_ok=True)
    extract_gfx_icons.main(ICON_WORK_DIR, ["icons_lib"], only=names)
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    found = {p.stem for p in (ICON_WORK_DIR / "icons_lib").glob("*.png")}

    for name in sorted(found & set(names)):
        icon = Image.open(ICON_WORK_DIR / "icons_lib" / f"{name}.png")
        icon.thumbnail((ICON_SIZE, ICON_SIZE), Image.LANCZOS) # extracted at 4x
        icon.save(ICON_DIR / f"{name}.png", optimize=True)

    rows = [(a, z, i[:-2] if i not in found and i.endswith("40") else i, x, y) for a, z, i, x, y in rows]
    unknown = sorted({r[2] for r in rows if r[2] not in found})
    rows = [r for r in rows if r[2] in found]

    if ICON_TABLE.exists(): # keep the other areas' rows when only some areas were imported
        rows = [tuple(line.rstrip("\n").split("\t")) for line in ICON_TABLE.read_text(encoding="utf-8").splitlines()[1:] if line.split("\t")[0] not in area_ids] + rows

    with open(ICON_TABLE, "w", encoding="utf-8") as f:
        f.write("area_id\tzone_id\ticon\tx\ty\n")
        f.writelines("\t".join(map(str, r)) + "\n" for r in rows)

    print(f"{len(rows)} zone icons in {len({r[0] for r in rows})} areas, {len(found & set(names))} icon pictures in {ICON_DIR.relative_to(ROOT)}; zone kinds without an icon in the game's icon library (skipped): {unknown}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--area", action="append", metavar="AREA_ID")
    parser.add_argument("--no-maps", action="store_true")
    parser.add_argument("--no-icons", action="store_true")
    args = parser.parse_args()
    slugs = {a: s for a, s in region_areas().items() if not args.area or a in args.area}

    if not args.no_maps:
        import_maps(slugs)

    if not args.no_icons:
        import_icons(list(slugs))
