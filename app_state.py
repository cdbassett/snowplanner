"""Shared registries (regions, areas), cross-page events and small constants used by the pages."""
from collections import defaultdict, namedtuple
from types import SimpleNamespace
import itertools
from itertools import pairwise
import copy

from nicegui import app, ui, Event
from icecream import ic
from tortoise.expressions import Q

from snowplanner_utils import *
from snowrunner_gen_map_text_svg import generate_area_svg, generate_region_svg, calculate_area_offsets_for_region, region_layout, svg_point_to_db
import delivery_plans as dp
from plan_panel import PlanPanel
from database import db
from database.models import *
from cargo_icons import TRUCK_TYPE_LABELS, truck_type, cargo_art_uris, normalize_cargo_name, cargo_style, has_cargo_style, TIER_FILLS, TIER_LEGEND, CARGO_STYLES, GENERIC_STYLES, CargoStack, vehicle_stack, vehicle_kind
from snowrunner_read_game_save import find_newest_game_save, apply_game_save, apply_game_save_summary

AreaInfo = namedtuple("AreaInfo", "region,area,region_slug,area_slug,abbrev,area_id,partial_abbrev")

regions = list(iterate_region())
regions_areas = list(iterate_region_area())
regions_slugs = list((slugify(region), region) for region in regions)
region_and_ids = list(iterate_region_and_ids())
areas_for_region = defaultdict(list) # area_slug, area_info
area_ids_by_area = get_area_ids_by_area()
areas_by_area_id = get_areas_by_area_id()
regions_by_slug = dict(regions_slugs)
area_infos = [AreaInfo(region_area.region, region_area.area, slugify(region_area.region), slugify(region_area.area), region_area.abbrev, region_area.area_id, region_area.partial_abbrev) for region_area in regions_areas]
areas_by_slug = dict((area_info.area_slug, area_info) for area_info in area_infos)
area_infos_by_area_id = dict((area_info.area_id, area_info) for area_info in area_infos)

for area_info in area_infos:
    areas_for_region[area_info.region_slug].append(area_info)


tree_updated = Event[AreaInfo]()
map_updated = Event[AreaInfo]()
save_loaded = Event() # fired after the DB was updated from a game save; every open view refreshes
plans_changed = Event[str]() # a delivery plan of this region (name) changed; every open view of that region refreshes

async def load_game_save():
    try:
        save_file = find_newest_game_save()
        result = await apply_game_save(save_file)
    except Exception as e:
        ui.notify(f"Failed to load game save: {e}", type="negative")
        return

    ui.notify(f"Loaded {save_file.name}: {apply_game_save_summary(result)}")
    save_loaded.emit()

d3_init_js_cache = FileCache("d3_init.js", ReadFile)
d3_brush_selection_js_cache = FileCache("d3_brush_selection.js", ReadFile)
diagnosing_console_errors = False


class_togglers = dict([
    ("Dots", "location-dot"),
    ("Contracts", "location-contract"),
    ("Tasks", "location-task"),
    ("Trucks", "location-truck"),
    ("Sources", "location-source"),
    ])

svg_vis_togglers = [
    "Contracts",
    "Tasks",
    "Sources",
    "Trucks",
    "Framing",
    "Spawns",
    ]

svg_classes = dict(class_togglers.items())
svg_classes["Hide"] = "hide-me"


def get_image_name_ex(area_info, typ="normal", actual=False):
    base = snowplanner_map_image_dir + "\\" if actual else "/map_images/"
    return f"{base}{slugify_region_area(area_info.region, area_info.abbrev)}_{typ}.png"
