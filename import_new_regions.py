#!/usr/bin/env python3
"""One-step import of new seasons / regions (and whatever else is missing from the database) straight from the game files.

Reads client_dir (config.yaml): initial.pak (strings, scripts, truck definitions) and the level_*.pak files (placed trucks
and the names of the zones), and then
  * adds missing areas to the region_area table (names, abbreviations),
  * adds missing trucks / trailers to the truck_info table,
  * adds the cargo sources, crafting sites, gates, placed trucks and objectives of every area that is not completely in the
    database yet (nothing existing is renamed or overwritten, so it can be run again at any time),
  * creates placeholder map images for new areas and a placeholder home page image for new regions.

    python3 import_new_regions.py --dry-run        # only say what would be imported
    python3 import_new_regions.py                  # import
    python3 import_new_regions.py --area US_19_01  # only this area
"""
import argparse
import functools
import asyncio
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="only report what would be imported; nothing is written")
    parser.add_argument("--area", action="append", metavar="AREA_ID", help="import only this area (e.g. US_19_01), even if it looks complete; may be repeated")
    parser.add_argument("--region", action="append", metavar="REGION_ID", help="import only this region's areas (e.g. US_19); may be repeated")
    parser.add_argument("--db", metavar="FILE", help="use this SQLite file instead of database/snowplanner.sqlite (for trying it out on a copy)")
    parser.add_argument("--positions", action="store_true", help="also fill in missing map positions (x, y) of every area, not just the areas imported in this run; positions that are already set are never changed")
    parser.add_argument("--reset-positions", action="store_true", help="replace the position of every map item the game files know with the game's (the maps are the game's own maps)")
    parser.add_argument("--no-images", action="store_true", help="do not create placeholder images")
    return parser.parse_args(argv)


args = parse_args() if __name__ == "__main__" else parse_args([])

if args.db:
    os.environ["SNOWPLANNER_DB_FILE"] = str(Path(args.db).resolve())

from icecream import ic
from tortoise import Tortoise

ic.disable() # the game script readers are chatty

from database.config import TORTOISE_CONFIG, snowplanner_db_filename
from database.models import *
from utils import gamefiles, level_data
from utils.truck_stats import truck_stats
from utils.snowrunner_utils import (area_acronym, area_string, cargo_names_dict, counted_cargo, encapsulate, parse_xml, slugify_region_area,
                                    fname_to_area_id, iterate_level_files_basic, iterate_objective_files_basic)
import populate_game_data as pgd

ROOT = Path(__file__).resolve().parent
MAP_IMAGE_DIR = ROOT / "map_images"
ASSET_DIR = ROOT / "assets"
TRUCK_XML_RE = re.compile(r"\[media\]/(?:_dlc/.+?/)?classes/trucks/(trailers/)?[^/]+\.xml$")


# ---------------------------------------------------------------- regions / areas

def area_names_from_game(ed):
    """{area id: (region id, region, area)} for every level pak."""
    found = {}

    for area_id in gamefiles.list_level_paks():
        region_id = area_id[:5]

        try:
            region = ed[region_id].split(",")[0].strip()
            area = area_string(ed, area_id).replace('"', "").replace("\\", "").strip()
        except KeyError:
            print(f"WARNING: no region / area name in the game strings for {area_id}; skipped")
            continue

        found[area_id] = (region_id, region, area)

    return found


def new_abbreviation(area, taken):
    """Initials of the area's words; the first letters of its name when those are already used in the region."""
    abbrev = area_acronym(area)
    n = 2

    while abbrev in taken and n <= len(area):
        abbrev = area[:n]
        n += 1

    return abbrev


def plan_region_areas(game_areas, existing):
    """Rows to add: [(area id, region id, region, area, abbrev)]; existing is {area id: RegionArea}."""
    taken = defaultdict(set)

    for ra in existing.values():
        taken[ra.region].add(ra.abbrev)

    names = {ra.area for ra in existing.values()}
    new_rows = []

    for area_id, (region_id, region, area) in sorted(game_areas.items(), key=lambda kv: (kv[1][1], kv[1][2], kv[0])):
        if area_id in existing:
            continue

        if area in names:
            print(f"WARNING: area name '{area}' ({area_id}) is not unique across regions; the app looks areas up by name")

        abbrev = new_abbreviation(area, taken[region])
        taken[region].add(abbrev)
        names.add(area)
        new_rows.append((area_id, region_id, region, area, abbrev))

    return new_rows


async def store_region_areas(new_rows, existing):
    for area_id, region_id, region, area, abbrev in new_rows:
        await RegionArea.create(area_id=area_id, seq=0, region_id=region_id, region=region, area=area, abbrev=abbrev)

    rows = await RegionArea.all()
    rows.sort(key=lambda r: (r.region, r.area))

    for seq, row in enumerate(rows):
        row.seq = seq

    await RegionArea.bulk_update(rows, fields=["seq"])
    return rows


# ---------------------------------------------------------------- trucks and trailers

def parse_truck_xml(path, text):
    """(kind, file id, UI name key, truck type) of a truck / trailer definition, or None."""
    root = parse_xml(encapsulate(text.replace("region:default", "region_default")))
    ui_desc = root.find(".//GameData//UiDesc")

    if ui_desc is None:
        return None

    if not (name := ui_desc.attrib.get("UiName")):
        default = root.find(".//GameData//UiDesc/region_default")
        name = default.attrib.get("UiName") if default is not None else None

    truck_type = (ui_truck := root.find(".//TruckData")) is not None and ui_truck.attrib.get("TruckType") or ""

    if not name:
        print(f"WARNING: couldn't find UiName for {path}")
        return None

    return ("trailer" if "/trailers/" in path else "truck", Path(path).stem, name, truck_type)


def trucks_from_game(ed):
    pak = gamefiles.initial_pak()
    out = {}

    for name in sorted(pak.all_names()):
        if TRUCK_XML_RE.match(name) and (rec := parse_truck_xml(name, pak.read(name).decode("utf-8", errors="replace"))):
            kind, file_id, ui_key, truck_type = rec
            out[file_id] = dict(id=file_id, kind=kind, ui_key=ui_key, name=ed.get(ui_key.upper()), truck_type=truck_type)

    return out


async def store_trucks(game_trucks):
    existing = {t.id for t in await TruckInfo.all()}
    new = [TruckInfo(**rec) for file_id, rec in game_trucks.items() if file_id not in existing]

    if new:
        await TruckInfo.bulk_create(new)

    return new


# ---------------------------------------------------------------- cargo types

CARGO_TYPE_XML_RE = re.compile(r"\[media\]/(?:_dlc/.+?/)?classes/cargo_types/([^/]+)\.xml$")


def add_missing_cargo_names(ed):
    """cargo_names_dict is the app's table of cargo type -> display name (with the size in brackets, e.g. 'Bricks [1]').
    Types it doesn't have yet (new seasons) get their plain in-game name so the import can go on; the size, if wanted, has to be added to the dict by hand."""
    pak = gamefiles.initial_pak()
    added = {}

    for name in sorted(pak.all_names()):
        if (m := CARGO_TYPE_XML_RE.match(name)) and m.group(1) not in cargo_names_dict:
            ui_name = re.search(r'UiName="([^"]+)"', pak.read(name).decode("utf-8", errors="replace"))

            if ui_name and (text := ed.get(ui_name.group(1).upper())):
                added[m.group(1)] = cargo_names_dict[m.group(1)] = text

    if added:
        print("Cargo types not in cargo_names_dict (utils/snowrunner_utils.py), using the game's names (no [size]):")

        for cargo_type, text in sorted(added.items()):
            print(f"    \"{cargo_type}\": \"{text}\",")

    return added


# ---------------------------------------------------------------- level data

def to_camel_case(snake_str):
    components = snake_str.split("_")

    if components[-1].isnumeric():
        components = components[:-1]

    return "".join(x.title() for x in components)


def cargo_string_of(cargo_strings):
    """'2 Bricks [1]|1 Planks' text of the cargo a placed truck carries."""
    cargos = [to_camel_case(c) for c in cargo_strings if c.startswith("cargo")]
    cargos = [cname for cargo in cargos if (cname := cargo_names_dict.get(cargo, cargo))]
    return "|".join(counted_cargo(cnt, cname) for cname, cnt in Counter(cargos).items())


def level_item_rows(area_id, truck_id_lookup, ed):
    """Rows (area id, task id, truck file id, UI key, display name, index, cargo) of the trucks / trailers placed in an area; only ones the game has a definition for."""
    rows = []

    for item in level_data.parse_level_items(gamefiles.read_data_for_ssl(area_id)):
        if (ui_key := truck_id_lookup.get(item.item_id)):
            rows.append([area_id, item.task_id, item.item_id, ui_key.upper(), ed[ui_key.upper()], str(item.index), cargo_string_of(item.cargo_strings) if item.cargo_strings else ""])

    return rows


def storage_zone_ids(level_scripts):
    """{area id: {zone id}} of the cargo loading / crafting zones (with cargo) the level scripts define."""
    out = defaultdict(set)

    for fname, python_data in level_scripts:
        area_id = fname_to_area_id(fname)

        for loc_id, dct in python_data["zoneDesc"].items():
            props = dct.get("props") or {}

            if (sub := props.get("ZonePropertyCargoLoading")) and sub.get("cargosSettings"):
                out[area_id].add(loc_id)
            elif (sub := props.get("ZonePropertyStorehouseCraft")) and sub.get("craftSettings"):
                out[area_id].add(loc_id)

    return out


def source_names_for_area(area_id, source_zone_ids):
    """{zone id: display name} from the area's data_for_ssl.bin. Sources that share a name in the area get the letters A, B, C... in zone id order."""
    zones = level_data.parse_level_zones(gamefiles.read_data_for_ssl(area_id))
    names = {}

    for zone_id, zone in zones.items():
        names[zone_id] = level_data.zone_display_name(zone)

    counts = Counter(names[z] for z in source_zone_ids if names.get(z))
    used = Counter()

    for zone_id in sorted(source_zone_ids):
        if (name := names.get(zone_id)) and counts[name] > 1:
            names[zone_id] = f"{name} {chr(ord('A') + used[name])}"
            used[name] += 1

    return {z: n for z, n in names.items() if n}


def objective_ids_by_area():
    out = defaultdict(set)

    for fname, python_data in iterate_objective_files_basic():
        area_id = fname_to_area_id(fname)

        for typ in ("tasksSettings", "contractsSettings"):
            out[area_id].update(python_data[typ])

    return out


# ---------------------------------------------------------------- map positions

@functools.cache
def delivery_zone_refs():
    return level_data.delivery_zones()


POSITION_ALIASES = {"US_12_03_TRAILER_SHOP": "US_12_03_TRAILER_GARAGE"} # map items the game has no zone of that id for (a trailer store a contract switches on): the zone it uses


async def fill_positions(area_ids, overwrite=False):
    """Give the map items of these areas that have no position yet the one the game files hold for them (zones from data_for_ssl.bin, placed trucks from the item list),
    converted to the app's 0-1000 coordinates. Positions that are already set (e.g. by hand in edit mode) are never touched, unless overwrite is set: then every
    item the game files know gets the game's position (items they don't know keep theirs, and are counted as unmatched)."""
    total = Counter()
    unmatched = Counter()

    for area_id in sorted(area_ids):
        data = gamefiles.read_data_for_ssl(area_id)
        zones = level_data.parse_level_zones(data)
        half = level_data.area_half_span(data, zones)
        coords = {zone_id: level_data.zone_placement(data, zone)[:2] for zone_id, zone in zones.items()}

        for item in level_data.parse_level_items(data):
            coords[item.task_id or f"{area_id}|{item.item_id}|{item.index}"] = (item.x, item.z)

        changed = []

        for map_item in await (MapItem.filter(area_id=area_id) if overwrite else MapItem.filter(area_id=area_id, x=None, y=None)):
            pos = coords.get(map_item.id) or coords.get(POSITION_ALIASES.get(map_item.id))

            if not pos and map_item.item_type == "delivery": # the id is the objective's uiDesc, not a zone: follow it to the zone it is delivered in
                zone_refs = [z for a, z in delivery_zone_refs().get(map_item.id, ()) if a == area_id and z in coords]
                pos = coords[zone_refs[0]] if zone_refs else None

            if not pos and map_item.item_type not in ("truck", "trailer") and (found := level_data.placement_by_id(data, map_item.id)) and found.width > 0: # e.g. spawns, locations a reward switches on
                pos = (found.x, found.z)

            if pos and all(abs(c) < 3000 for c in pos):
                map_item.x, map_item.y = level_data.world_to_db(*pos, half)
                changed.append(map_item)
                total[area_id] += 1
            else:
                unmatched[map_item.item_type] += 1

        if changed:
            await MapItem.bulk_update(changed, fields=["x", "y"])

    return total, unmatched


def _zone_ref(value):
    """'level_x || ZONE' from the plain string or the {globalZoneId: ...} wrapper(s) a script may use."""
    while isinstance(value, dict):
        value = value.get("globalZoneId")

    return value


@functools.cache
def task_giver_refs():
    """{task id: [(area id, zone id), ...]}: where each task is activated, main spot first (taskGiverZone, then additionalTaskGivers, which are zones of the same level)."""
    refs = {}

    for _, data in iterate_objective_files_basic():
        for task_id, task in data.get("tasksSettings", {}).items():
            main = _zone_ref(task.get("taskGiverZone"))

            if main and " || " in main:
                level, zone_id = (x.strip() for x in main.split("||"))
                area_id = fname_to_area_id(level)
                refs[task_id] = [(area_id, zone_id)] + [(area_id, z) for z in task.get("additionalTaskGivers") or ()]

    return refs


async def fill_task_givers(area_ids):
    """Record where the tasks of these areas are activated (task_giver table), with positions from the level files. Tasks that already have their spots are left alone."""
    objectives = {o.id: o for o in await Objective.filter(area_id__in=list(area_ids), obj_type="task")}
    done = set(await TaskGiver.filter(objective_id__in=list(objectives)).values_list("objective_id", flat=True))
    levels = {}
    added = Counter()
    missing = []

    for task_id, refs in task_giver_refs().items():
        if task_id not in objectives or task_id in done:
            continue

        for n, (area_id, zone_id) in enumerate(refs):
            if area_id not in levels:
                data = gamefiles.read_data_for_ssl(area_id)
                zones = level_data.parse_level_zones(data)
                levels[area_id] = (data, zones, level_data.area_half_span(data, zones))

            data, zones, half = levels[area_id]
            placement = level_data.zone_placement(data, zones[zone_id]) if zone_id in zones else level_data.placement_by_id(data, zone_id)

            if placement and abs(placement.x) < 3000 and abs(placement.z) < 3000:
                x, y = level_data.world_to_db(placement.x, placement.z, half)
                await TaskGiver.create(objective_id=task_id, area_id=objectives[task_id].area_id, zone_id=zone_id, x=x, y=y, primary=n == 0)
                added[objectives[task_id].area_id] += 1
            else:
                missing.append(f"{task_id}: {zone_id}")

    return added, missing


@functools.cache
def repair_steps():
    """[(objective id, stage, index, vehicle id, phase, damage %, fuel %, what happens to it after the stage)] of every repairTruck entry of the tasks and contracts. The phase says where it is shown:
    before = the vehicle is delivered later (repaired first, or while being delivered), after = it was delivered in an earlier stage, alone = it isn't delivered."""
    steps = []

    for _, data in iterate_objective_files_basic():
        for typ in ("tasksSettings", "contractsSettings"):
            for obj_id, objective in data.get(typ, {}).items():
                stages = objective.get("stages") or []
                delivered = defaultdict(list) # vehicle id -> stages it is delivered in

                for n, stage in enumerate(stages):
                    for delivery in (stage or {}).get("truckDelivery") or ():
                        delivered[delivery["truckId"]].append(n)

                for n, stage in enumerate(stages):
                    for idx, repair in enumerate((stage or {}).get("repairTruck") or ()):
                        truck_id = repair["truckId"]
                        stages_delivered = delivered.get(truck_id)
                        phase = "alone" if not stages_delivered else "before" if n <= min(stages_delivered) else "after"
                        steps.append((obj_id, n, idx, truck_id, phase, repair.get("truckDamageState"), repair.get("truckFuelState"), repair.get("afterStageFinished") or ""))

    return steps


def repair_needs(level_item, damage, fuel):
    """(damage %, fuel %, repair points, liters of fuel) a vehicle needs, from its condition in the level file (the objective's own states when the vehicle isn't in the level) and the capacities of its parts. Points are
    rounded to tens, as the game shows them (Kenworth 963 at 33 % damage: 237.6 -> 240); the fuel is what is missing from the tank (ZiKZ 5368 at 28 %: 137 l)."""
    if level_item:
        damage, fuel = round(level_item.damage), round(level_item.fuel)

    stats = truck_stats(level_item.item_id) if level_item else None
    points = round(damage / 100 * stats[0], -1) if stats and damage else None
    liters = round((100 - fuel) / 100 * stats[1]) if stats and fuel is not None and fuel < 100 else None
    return damage, fuel, points, liters


async def fill_repairs():
    """Add the repair steps of the objectives that are in the database, and what each vehicle needs (existing steps keep their done state)."""
    objective_ids = set(await Objective.all().values_list("id", flat=True))
    vehicles = {m.id: m for m in await MapItem.filter(item_type__in=["truck", "trailer"])}
    existing = {r.id: r for r in await ObjectiveRepair.all()}
    level_items = {}
    added, missing = 0, []

    for obj_id, stage, idx, truck_id, phase, objective_damage, objective_fuel, after_stage in repair_steps():
        step_id = f"{obj_id}|{stage}|{idx}"

        if obj_id not in objective_ids:
            continue

        if truck_id not in vehicles:
            missing.append(f"{obj_id}: {truck_id}")
            continue

        area_id = vehicles[truck_id].area_id

        if area_id not in level_items:
            level_items[area_id] = {item.task_id or f"{area_id}|{item.item_id}|{item.index}": item for item in level_data.parse_level_items(gamefiles.read_data_for_ssl(area_id))}

        damage, fuel, points, liters = repair_needs(level_items[area_id].get(truck_id), objective_damage, objective_fuel)
        values = dict(damage_state=damage, fuel_state=fuel, repair_points=points, fuel_liters=liters, after_stage=after_stage)

        if (row := existing.get(step_id)):
            if any(getattr(row, k) != v for k, v in values.items()):
                for k, v in values.items():
                    setattr(row, k, v)

                await row.save(update_fields=list(values))
        else:
            await ObjectiveRepair.create(id=step_id, objective_id=obj_id, map_item_id=truck_id, stage=stage, phase=phase, **values)
            added += 1

    return added, missing


PLACE_PROPS = {"ZonePropertyGarageEntrance": ("garage", "Garage"), "ZonePropertyTrailerAttach": ("trlstore", "Trailer Store")} # zone property -> (map item type, name when the game gives the zone none)


def _walk_dicts(value):
    if isinstance(value, dict):
        yield value

        for v in value.values():
            yield from _walk_dicts(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_dicts(v)


@functools.cache
def garage_zones():
    """{zone id: (map item type, area id, id of the objective whose reward opens it or None)} of the garages and trailer stores: zones of the level scripts, and zones an objective's reward opens."""
    zones = {}

    for fname, data in iterate_level_files_basic():
        try:
            area_id = fname_to_area_id(fname)
        except Exception: # test levels
            continue

        for zone_id, dct in data["zoneDesc"].items():
            props = (dct or {}).get("props") or {}

            for prop, (typ, _) in PLACE_PROPS.items():
                if prop in props:
                    zones[zone_id] = (typ, area_id, None)

    for _, data in iterate_objective_files_basic():
        for kind in ("tasksSettings", "contractsSettings"):
            for obj_id, objective in data.get(kind, {}).items():
                for d in _walk_dicts(objective.get("rewards")):
                    zone_id, props = d.get("zoneId"), d.get("props")

                    if isinstance(zone_id, str) and isinstance(props, dict):
                        for prop, (typ, _) in PLACE_PROPS.items():
                            if prop in props:
                                try:
                                    zones[zone_id] = (typ, fname_to_area_id(zone_id), obj_id)
                                except Exception:
                                    pass

    return zones


async def fill_places(area_ids=None):
    """Add the garages and trailer stores (map items of type garage / trlstore) with their positions; those a task's reward opens are locked by that objective. Existing rows keep their names and positions."""
    objective_ids = set(await Objective.all().values_list("id", flat=True))
    existing = {m.id: m for m in await MapItem.filter(item_type__in=[t for t, _ in PLACE_PROPS.values()])}
    known_areas = set(await RegionArea.all().values_list("area_id", flat=True))
    levels = {}
    added = 0

    for zone_id, (typ, area_id, locker) in sorted(garage_zones().items()):
        if (area_ids is not None and area_id not in area_ids) or area_id not in known_areas:
            continue

        if area_id not in levels:
            data = gamefiles.read_data_for_ssl(area_id)
            zones = level_data.parse_level_zones(data)
            levels[area_id] = (data, zones, level_data.area_half_span(data, zones))

        data, zones, half = levels[area_id]
        zone = zones.get(zone_id)
        placement = level_data.zone_placement(data, zone) if zone else level_data.placement_by_id(data, zone_id)
        pos = level_data.world_to_db(placement.x, placement.z, half) if placement and abs(placement.x) < 3000 and abs(placement.z) < 3000 else (None, None)
        name = (zone and level_data.zone_display_name(zone)) or next(n for t, n in PLACE_PROPS.values() if t == typ)
        locker = locker if locker in objective_ids else None

        if (item := existing.get(zone_id)):
            changed = False

            if item.x is None and pos[0] is not None:
                item.x, item.y, changed = pos[0], pos[1], True

            if locker and item.obj_locker_id != locker:
                item.obj_locker_id, changed = locker, True

            if changed:
                await item.save()
        else:
            await MapItem.create(id=zone_id, area_id=area_id, name=name, item_type=typ, x=pos[0], y=pos[1], obj_locker_id=locker, completed=False)
            added += 1

    return added


# ---------------------------------------------------------------- placeholder images

def make_placeholder(path, size, lines, color, fmt):
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(img)
    w, h = size

    for i in range(0, w + h, 64): # light diagonal hatching so it is obviously a placeholder
        draw.line([(i, 0), (0, i)], fill=tuple(min(255, c + 14) for c in color), width=2)

    try:
        font = ImageFont.load_default(size=max(24, h // 14))
    except TypeError:
        font = ImageFont.load_default()

    y = h // 2 - len(lines) * h // 28

    for line in lines:
        box = draw.textbbox((0, 0), line, font=font)
        draw.text(((w - (box[2] - box[0])) // 2, y), line, fill=(235, 235, 235), font=font)
        y += (box[3] - box[1]) * 3 // 2 + 8

    img.save(path, fmt)


def create_placeholder_images(new_rows, all_rows):
    made = []

    for area_id, region_id, region, area, abbrev in new_rows:
        for typ, color in (("normal", (74, 92, 84)),):
            path = MAP_IMAGE_DIR / f"{slugify_region_area(region, abbrev)}_{typ}.png"

            if not path.exists():
                make_placeholder(path, (1029, 1024), [region, area, "(placeholder map image)"], color, "PNG")
                made.append(path)

    for region_id, region in sorted({(r.region_id, r.region) for r in all_rows}):
        path = ASSET_DIR / f"region_{region_id.lower()}.jpg"

        if not path.exists():
            make_placeholder(path, (1280, 720), [region, "(placeholder region image)"], (64, 78, 96), "JPEG")
            made.append(path)

    return made


# ---------------------------------------------------------------- main

async def main():
    ed = gamefiles.english_strings()
    print(f"Game files: {gamefiles.client_dir()}")

    if args.dry_run:
        await Tortoise.init(config=TORTOISE_CONFIG)
    else:
        from database.db import run_migrations_and_seeding # makes sure the tables exist and the reference data is seeded
        await run_migrations_and_seeding()

    try:
        existing_ra = {ra.area_id: ra for ra in await RegionArea.all()}
        existing_trucks = {t.id for t in await TruckInfo.all()}
    except Exception as e:
        sys.exit(f"The database has no region_area / truck_info tables yet ({e}). Run the app once (or this script without --dry-run) to migrate it.")

    add_missing_cargo_names(ed)
    game_areas = area_names_from_game(ed)
    game_trucks = trucks_from_game(ed)

    new_areas = plan_region_areas(game_areas, existing_ra)
    new_trucks = sorted(set(game_trucks) - existing_trucks)
    print(f"Areas in the game: {len(game_areas)}, new to the region_area table: {[r[0] for r in new_areas]}")
    print(f"Trucks / trailers in the game: {len(game_trucks)}, new: {len(new_trucks)}")

    # what each area still lacks in the database
    truck_id_lookup = {tid: rec["ui_key"] for tid, rec in game_trucks.items()}
    level_scripts = list(iterate_level_files_basic())
    storage_ids = storage_zone_ids(level_scripts)
    objective_ids = objective_ids_by_area()
    db_map_ids = set(await MapItem.all().values_list("id", flat=True))
    db_objective_ids = set(await Objective.all().values_list("id", flat=True))

    wanted_areas = sorted(a for a in game_areas if (not args.area or a in args.area) and (not args.region or a[:5] in args.region))
    rows_by_area = {}
    source_names_by_area = {}
    todo = {}

    for area_id in wanted_areas:
        rows_by_area[area_id] = level_item_rows(area_id, truck_id_lookup, ed)
        source_names = source_names_by_area[area_id] = source_names_for_area(area_id, storage_ids[area_id])
        placed = {task_id or f"{area_id}|{truck_id}|{idx}" for _, task_id, truck_id, _, _, idx, _ in rows_by_area[area_id]}
        named_sources = {z for z in storage_ids[area_id] if source_names.get(z)} # a zone the game gives no name is skipped
        missing = {"sources": named_sources - db_map_ids, "trucks": placed - db_map_ids, "objectives": objective_ids[area_id] - db_objective_ids}

        if args.area or any(missing.values()) or area_id in {r[0] for r in new_areas}:
            todo[area_id] = missing

    for area_id, missing in todo.items():
        print(f"  {area_id}: missing " + ", ".join(f"{len(v)} {k}" for k, v in missing.items()))

    givers_needed = bool((set(task_giver_refs()) & set(await Objective.filter(obj_type="task").values_list("id", flat=True))) - set(await TaskGiver.all().values_list("objective_id", flat=True)))

    db_repairs = {r.id: (r.damage_state, r.after_stage) for r in await ObjectiveRepair.all()}
    repairs_needed = any(None in db_repairs.get(f"{o}|{n}|{i}", (None,)) for o, n, i, *_ in repair_steps() if o in db_objective_ids)

    places_needed = bool(set(garage_zones()) - db_map_ids)

    if not todo and not new_areas and not new_trucks and not args.positions and not args.reset_positions and not givers_needed and not repairs_needed and not places_needed:
        print("Nothing to import.")
        return

    if args.dry_run:
        print("Dry run: nothing written.")
        return

    all_rows = await store_region_areas(new_areas, existing_ra)
    added_trucks = await store_trucks(game_trucks)
    print(f"Added {len(new_areas)} areas and {len(added_trucks)} trucks / trailers.")

    ctx = pgd.ctx
    ctx.areas_by_area_id = {r.area_id: r.area for r in all_rows}
    ctx.truck_id_lookup = truck_id_lookup
    ctx.level_items = [row for area_id in todo for row in rows_by_area[area_id]]
    ctx.truck_lookup = {row[1]: row[2] for rows in rows_by_area.values() for row in rows}
    ctx.level_item_seasons = {row[0][:5] for row in ctx.level_items}
    ctx.source_names = {}

    for area_id in todo:
        ctx.source_names.update(source_names_by_area[area_id])

    if todo:
        await pgd.populate(todo)

    filled, unmatched = await fill_positions(set(todo) | (set(game_areas) if args.positions or args.reset_positions else set()), overwrite=args.reset_positions)
    print(f"Positions filled for {sum(filled.values())} map items " + ", ".join(f"{a}: {n}" for a, n in sorted(filled.items())))

    if unmatched:
        print("Map items without a position in the game files (place them in edit mode): " + ", ".join(f"{n} {t}" for t, n in sorted(unmatched.items())))

    givers, no_giver_pos = await fill_task_givers(set(game_areas) if (args.positions or givers_needed) else set(todo))
    print(f"Task activation spots added for {sum(givers.values())} places " + ", ".join(f"{a}: {n}" for a, n in sorted(givers.items())))

    if no_giver_pos:
        print("Task activation zones not found in the level files: " + ", ".join(no_giver_pos))

    added_places = await fill_places()
    print(f"Garages / trailer stores added: {added_places}")

    added_repairs, missing_repairs = await fill_repairs()
    print(f"Repair steps added: {added_repairs}")

    if missing_repairs:
        print("Repair steps whose vehicle isn't in the database: " + ", ".join(missing_repairs))

    if not args.no_images:
        for path in create_placeholder_images(new_areas, all_rows):
            print(f"Created placeholder image {path.relative_to(ROOT)}")

    print("Done. Restart the app to pick up new regions; run `python3 -m database.dump_data` to refresh the fixture.")


if __name__ == "__main__":
    print(f"Database: {snowplanner_db_filename}")

    async def run_and_close():
        try:
            await main()
        finally:
            await Tortoise.close_connections() # in the same event loop that opened them, or the process never exits

    asyncio.run(run_and_close())
