#!/usr/bin/env python3
"""Report which map items (locations) are not among the zones of the game files, and which are found but placed significantly differently.

Uses data/zone_coordinates_from_game.tsv (dev/export_zone_coordinates.py). "Not found" only covers the place types (source, craft, gate, garage, trlstore):
deliveries, cargo spawns and vehicles take their ids from objectives, not zones. "Different" covers every map item whose id is a zone, when the position
differs by more than THRESHOLD (0-1000 map units).

    python3 dev/report_map_items_vs_game.py [OUT_FILE]      # default data/map_items_vs_game_files.txt
"""
import csv
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from database.config import snowplanner_db_filename
from utils import gamefiles, level_data

DATA = Path(__file__).resolve().parent.parent / "data"
PLACE_TYPES = ("source", "craft", "gate", "garage", "trlstore")
THRESHOLD = 40


def game_position(area_id, id_, name, x, y, zones):
    """Where the game files put an item that isn't a regular zone (e.g. a location a reward switches on): the placement stored under its id when it is a real one,
    otherwise the zones of the area with the same name or within 40 map units (candidates, not certain). Returns a text."""
    data = gamefiles.read_data_for_ssl(area_id)
    found = level_data.placement_by_id(data, id_)

    if found and found.width > 0 and all(abs(c) < 3000 for c in found[:2]):
        gx, gy = level_data.world_to_db(found.x, found.z, level_data.area_half_span(data))
        return f"game has it at ({gx}, {gy}), {math.hypot(gx - x, gy - y):.0f} from the db"

    near = [(math.hypot(float(z["db_x"]) - x, float(z["db_y"]) - y), zid, z) for zid, z in zones.items() if z["area_id"] == area_id]
    near = [n for n in sorted(near, key=lambda n: n[0]) if n[0] <= 40 and n[2]["name"]]
    return "no placement under this id; nearest zones: " + ("; ".join(f"{zid} '{z['name']}' ({z['db_x']}, {z['db_y']}) {d:.0f} away" for d, zid, z in near[:3]) or "none")


def main(out):
    con = sqlite3.connect(f"file:{snowplanner_db_filename}?mode=ro", uri=True)
    areas = {r[0]: r[1:] for r in con.execute("select area_id, seq, region, area from region_area")}
    zones = {r["zone_id"]: r for r in csv.DictReader(open(DATA / "zone_coordinates_from_game.tsv", encoding="utf-8"), delimiter="\t")}
    missing, different = defaultdict(list), defaultdict(list)

    for id_, area_id, type_, name, x, y in con.execute("select id, area_id, item_type, name, x, y from map_item order by name, id"):
        seq, region, area = areas.get(area_id, (999, area_id, area_id))
        z = zones.get(id_)

        if z is None:
            if type_ in PLACE_TYPES:
                missing[(seq, region, area)].append((name, id_, type_, x, y, game_position(area_id, id_, name, x, y, zones)))
        elif x is not None and y is not None:
            d = math.hypot(float(z["db_x"]) - x, float(z["db_y"]) - y)

            if d > THRESHOLD:
                different[(seq, region, area)].append((name, id_, type_, x, y, float(z["db_x"]), float(z["db_y"]), d))

    def section(title, groups, fmt):
        lines = [title, "=" * len(title), ""]
        total = sum(map(len, groups.values()))
        by_region = defaultdict(list)

        for key in sorted(groups):
            by_region[key[1]].append(key)

        for region, keys in by_region.items(): # sorted by seq, so regions come in display order
            lines.append(f"{region}  ({sum(len(groups[k]) for k in keys)})")

            for key in keys:
                lines.append(f"  {key[2]}  ({len(groups[key])})")
                lines.extend("    " + fmt(r) for r in sorted(groups[key], key=lambda r: (r[0].lower(), r[1])))

            lines.append("")

        return lines + [f"Total: {total}", ""]

    lines = section(f"Map items ({'/'.join(PLACE_TYPES)}) with no zone of that id in the game files", missing,
                    lambda r: f"{r[0]} [{r[2]}] {r[1]}  db ({r[3]}, {r[4]}); {r[5]}")
    lines += section(f"Map items found in the game files but more than {THRESHOLD} map units (of 1000) from the game's position", different,
                     lambda r: f"{r[0]} [{r[2]}] {r[1]}  db ({r[3]}, {r[4]}) vs game ({r[5]:.0f}, {r[6]:.0f})  off by {r[7]:.0f}")
    Path(out).write_text("\n".join(lines), encoding="utf-8")
    print(f"{sum(map(len, missing.values()))} not found, {sum(map(len, different.values()))} different -> {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DATA / "map_items_vs_game_files.txt")
