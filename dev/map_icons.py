#!/usr/bin/env python3
"""Which icon the game's map shows where.

objective_rewards_manager.sso (zoneDescs) names the icon of each kind of zone (garage entrance, gateway, trailer store, watch tower, fuel station,
service hub, craft site, resupply, energy, water station, cargo loading). A zone has that kind when its zone description has the matching ZoneProperty*;
zones are in the level scripts, and some are opened by an objective's reward. Positions come from the levels' data_for_ssl.bin (converted to the 0-1000 map
coordinates the app uses).

    python3 dev/map_icons.py OUT_DIR [--gfx-pak PATH]

writes OUT_DIR/map_icons_by_area.tsv, OUT_DIR/map_region_icons.tsv and the PNGs of the icons used in OUT_DIR/icons/.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import extract_gfx_icons
from utils import gamefiles, level_data
from utils.snowrunner_utils import fname_to_area_id, iterate_level_files_basic, iterate_objective_files_basic

# zoneDescs key -> zone property of the zone descriptions
ZONE_PROPERTIES = {
    "CARGO_LOADING": "ZonePropertyCargoLoading",
    "GARAGE_ENTRANCE": "ZonePropertyGarageEntrance",
    "GATEWAY": "ZonePropertyGateway",
    "TRAILER_ATTACH": "ZonePropertyTrailerAttach",
    "WATCHPOINT": "ZonePropertyWatchpoint",
    "FUEL_STATION": "ZonePropertyFuelStation",
    "AUTO_RESTORE": "ZonePropertyAutoRepairAndRestore",
    "STOREHOUSE_CRAFT": "ZonePropertyStorehouseCraft",
    "RESUPPLY_REPAIR": "ZonePropertyResupplyRepairParts",
    "ENERGY": "ZonePropertyEnergy",
    "WATER_STATION": "ZonePropertyWaterStation",
}


def zone_icons():
    """{zone property: (kind, 30px icon, 40px icon)} from objective_rewards_manager.sso"""
    text = gamefiles.read_ps_text("objective_rewards_manager.sso")
    block = text[text.index("zoneDescs"):]
    out = {}

    for m in re.finditer(r"\n\s{3}(\w+)\s+=\s+\{(.*?)\n\s{3}\}", block, re.S):
        key, body = m.groups()

        if key in ZONE_PROPERTIES:
            icons = dict(re.findall(r'(uiIcon\d+x\d+)\s+=\s+"(\w+)"', body))
            out[ZONE_PROPERTIES[key]] = (key, icons.get("uiIcon30x30", ""), icons.get("uiIcon40x40", ""))

    return out


def region_icons():
    """[(region key, map icon, map background)] from zone_desc_storage.sso"""
    text = gamefiles.read_ps_text("zone_desc_storage.sso")
    return re.findall(r'uiName\s+=\s+"(\w+)"\s+uiDesc\s+=\s+"\w+"\s+mapBackground\s+=\s+"(\w+)"\s+mapIcon\s+=\s+"(\w+)"', text)


def walk_dicts(value):
    if isinstance(value, dict):
        yield value

        for v in value.values():
            yield from walk_dicts(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk_dicts(v)


def find_zones(properties):
    """{(area id, zone id): (set of zone properties, opening objective id or '')}"""
    zones = {}

    for fname, data in iterate_level_files_basic():
        try:
            area_id = fname_to_area_id(fname)
        except Exception: # test levels
            continue

        for zone_id, desc in data["zoneDesc"].items():
            props = ((desc or {}).get("props") or {})

            if (found := {p for p in properties if p in props}):
                zones.setdefault((area_id, zone_id), (set(), ""))[0].update(found)

    for _, data in iterate_objective_files_basic():
        for kind in ("tasksSettings", "contractsSettings"):
            for obj_id, objective in data.get(kind, {}).items():
                for d in walk_dicts(objective.get("rewards")):
                    zone_id, props = d.get("zoneId"), d.get("props")

                    if isinstance(zone_id, str) and isinstance(props, dict) and (found := {p for p in properties if p in props}):
                        try:
                            key = (fname_to_area_id(zone_id), zone_id)
                        except Exception:
                            continue

                        zones.setdefault(key, (set(), ""))[0].update(found)
                        zones[key] = (zones[key][0], obj_id)

    return zones


def main(out_dir, gfx_pak=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    icons = zone_icons()
    zones = find_zones(icons)
    strings = gamefiles.english_strings_first()
    levels = {}
    rows = []

    for (area_id, zone_id), (props, opened_by) in sorted(zones.items()):
        if area_id not in levels:
            try:
                data = gamefiles.read_data_for_ssl(area_id)
                parsed = level_data.parse_level_zones(data)
                levels[area_id] = (data, parsed, level_data.area_half_span(data, parsed))
            except Exception:
                levels[area_id] = None

        if not levels[area_id]:
            continue

        data, parsed, half = levels[area_id]
        zone = parsed.get(zone_id)
        placement = level_data.zone_placement(data, zone) if zone else level_data.placement_by_id(data, zone_id)
        x, y = level_data.world_to_db(placement.x, placement.z, half) if placement and abs(placement.x) < 3000 and abs(placement.z) < 3000 else ("", "")
        name = (level_data.zone_display_name(zone, strings) if zone else "") or ""

        for prop in sorted(props):
            kind, icon30, icon40 = icons[prop]
            rows.append((area_id, zone_id, name, prop, kind, icon40, icon30, str(x), str(y), opened_by))

    with open(out_dir / "map_icons_by_area.tsv", "w", encoding="utf-8") as f:
        f.write("area_id\tzone_id\tzone_name\tzone_property\tkind\ticon40\ticon30\tx\ty\topened_by_objective\n")
        f.writelines("\t".join(row) + "\n" for row in rows)

    regions = region_icons()

    with open(out_dir / "map_region_icons.tsv", "w", encoding="utf-8") as f:
        f.write("region_name_key\tmap_background\tmap_icon\n")
        f.writelines("\t".join(r) + "\n" for r in regions)

    used = sorted({r[5] for r in rows} | {r[6] for r in rows} | {r[2] for r in regions} | {"gatewayLockedImg", "gatewayLockedImg30"} - {""})
    extract_gfx_icons.main(out_dir / "icons", ["icons_lib"], gfx_pak, only=used)
    print(f"{len(rows)} map icons in {len({r[0] for r in rows})} areas")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out_dir")
    parser.add_argument("--gfx-pak")
    args = parser.parse_args()
    main(args.out_dir, args.gfx_pak)
