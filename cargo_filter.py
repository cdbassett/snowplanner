"""The cargo filter list (right panel tab) and helpers that map clicked entries to map items."""
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
from app_state import *
from obj_tree import nfmt

async def fill_cargo_filter_list(list_el, region_area_ids, filter_list_item_clicked, show_all=False):
    filter_cargo_items = set()

        # plain sources only list cargo that an incomplete objective still needs, same as the map
    needed_cargo = None if show_all else set(await ObjectiveItem.filter(item_type="cargo", completed=False, objective__completed=False, deliver_loc__area_id__in=region_area_ids).values_list("name", flat=True))

    for map_item in await MapItem.filter(Q(area_id__in=region_area_ids)).prefetch_related("cargo_items"):
        if show_all or not map_item.completed:
            for cargo_item in map_item.cargo_items:
                if (ccnt := current_cargo_count(cargo_item)) != 0 and (needed_cargo is None or map_item.item_type != "source" or cargo_item.name in needed_cargo):
                    filter_cargo_items.add(cargo_item.name)

    for objective in await Objective.filter(obj_items__deliver_loc__area_id__in=region_area_ids).prefetch_related("obj_items__map_item"):
        for obj_item in objective.obj_items:
            if (not obj_item.map_item or obj_item.map_item.item_type not in ("spawn", "truck")) and (show_all or not (obj_item.completed or objective.completed)):
                filter_cargo_items.add(obj_item.name)

    found_items = list(sorted(filter_cargo_items))
    srch_items = list(map(str.casefold, found_items))
    generic_items = [s for s in ["logs", "pipes", "planks", "concrete", "metal"] if sum(int(s.casefold() in srch) for srch in srch_items)>1]
    ic(generic_items)
    items = generic_items + found_items
    ic(items)

    list_el.clear()

    with list_el:
        for item in items:
            with ui.item(on_click=lambda list_item=item: filter_list_item_clicked(list_item)):
                if has_cargo_style(item):
                    emoji = cargo_style(item)[0]
                    fill = CargoStack(item, None, item).fill # same background as on the map
                    with ui.item_section().props('side'):
                        uris = cargo_art_uris(item)
                        ui.html(''.join(f'<img src="{u}" style="width:20px;height:20px">' for u in uris) if uris else emoji).classes('items-center justify-center').style(f'display:flex; width:26px; height:26px; background:{fill}; border:1px solid #555; border-radius:4px; font-size:16px')

                ui.label(item)


async def build_cargo_filter_list(region_area_ids, filter_list_item_clicked, show_all=False, plan_panel=None):
    """The right-hand panel: tabs for the cargo filter and the delivery plans. Returns the cargo filter's list element."""
    with ui.column().classes('w-96 h-full bg-gray-50 p-2 flex flex-col shrink-0 min-h-0'):
        with ui.tabs().props('dense').classes('w-full') as tabs:
            filter_tab = ui.tab('Cargo Filter')
            plans_tab = ui.tab('Delivery Plans')

        with ui.tab_panels(tabs, value=filter_tab, animated=False).classes('w-full flex-1 min-h-0 bg-gray-50').props('keep-alive'):
            with ui.tab_panel(filter_tab).classes('p-0 h-full flex flex-col'):
                with ui.row().classes('gap-2 items-center text-xs mb-1'):
                    for tier, desc in TIER_LEGEND:
                        ui.label().style(f'width:14px; height:14px; background:{TIER_FILLS[tier]}; border:1px solid #555; border-radius:3px')
                        ui.label(desc)

                with ui.scroll_area().classes('flex-1 w-full border bg-white'):
                    filter_cargo_items = ui.list().props('dense separator')

            with ui.tab_panel(plans_tab).classes('p-0 h-full'):
                if plan_panel:
                    await plan_panel.build()

    await fill_cargo_filter_list(filter_cargo_items, region_area_ids, filter_list_item_clicked, show_all)
    return filter_cargo_items


async def map_item_for_rec(rec):
    """The MapItem behind a clicked map entry (for choosing a delivery plan location), or None."""
    typ = rec.extra or rec.typ

    if typ == "pickup":
        obj_item = await ObjectiveItem.filter(id=rec.id).first()
        return obj_item and obj_item.map_item_id and await MapItem.filter(id=obj_item.map_item_id).first()

    return await MapItem.filter(id=rec.id).first()
