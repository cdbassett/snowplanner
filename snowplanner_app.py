#!/usr/bin/env python3
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
from region_page import region
from area_page import area


@app.on_startup
async def init_db():
    await db.init_db()

@app.on_startup
async def run_migrations_and_seeding():
    await db.run_migrations_and_seeding()


print("db init finished")

app.add_static_files('/data', snowplanner_data_dir)
app.add_static_files('/js', "js")
app.add_static_files('/map_images', snowplanner_map_image_dir)
app.add_static_files('/assets', snowplanner_base_dir / "assets")


def on_path_changed(path):
    ui.notify(f'Navigated to {path}')


def root():
    ui.query('.nicegui-content').classes('p-0') # remove page padding
#    ui.add_head_html('''
#        <style>
#            body {
#                font-size: 10px !important;
#            }
#        </style>
#    ''')

    ui.add_css((snowplanner_base_dir / 'css' / 'snowplanner.css').read_text())
    ui.add_head_html('<script src="/js/tooltip.js"></script>')
    # delivery plans: map interaction (dragging plan squares, picking a point) and drag-and-drop stop lists
    ui.add_head_html('<script src="/js/Sortable.min.js"></script><script src="/js/plan_map.js"></script>')

    # CSS for objective tree node variations
    ui.add_head_html('''
        <style>
            .red-node .q-tree__node__label { color: red; }
            .blue-node .q-tree__node__label { color: blue; }
            .green-node .q-tree__node__icon { color: green; }
        </style>
    ''')

    if 1:
            # D3 library for dragging, zooming, brushing, and possibly force directed labeling
        ui.add_head_html('<script src="/js/d3.v7.min.js"></script>')


    if 0: # these are top-level only
        with ui.header().classes('items-center'):
            ui.button(on_click=lambda: left_drawer.toggle(), icon='menu').props('flat color=white')
            ui.label('My Application')

        with ui.left_drawer(value=True, fixed=True, bordered=True).classes('bg-gray-100') as left_drawer:
            ui.label('Side Panel Content').classes('text-h6')
            ui.label('You can add menus, sliders, or input fields here.')
            ui.button('Close', on_click=lambda: left_drawer.hide())
            ui.label('inside the expansion')

    ui.sub_pages({'/': main, '/icons': icon_reference, '/region/{region_slug}': region, '/area/{area_slug}': area})
    ui.context.client.sub_pages_router.on_path_changed(on_path_changed)

async def icon_reference():
    cargo_names = set(CARGO_STYLES) | set(GENERIC_STYLES)
    cargo_names |= {normalize_cargo_name(n) for n in await SourceCargoItem.all().values_list("name", flat=True)}
    cargo_names |= {normalize_cargo_name(n) for n in await ObjectiveItem.filter(item_type="cargo").values_list("name", flat=True)}

    vehicles = {"truck": set(), "trailer": set()}
    for name in await MapItem.filter(item_type__in=("truck", "trailer")).values_list("name", flat=True):
        vehicles[vehicle_stack(name).kind].add(name)
    for item_type, name in await ObjectiveItem.filter(item_type__in=("truck", "trailer")).values_list("item_type", "name"):
        vehicles[vehicle_stack(name, kind=item_type).kind].add(name)

    def section(title, stacks):
        ui.label(f"{title} ({len(stacks)})").classes('font-bold text-lg mt-4')
        with ui.row().classes('gap-2 w-full'):
            for stack in stacks:
                color, width = stack.border
                with ui.row().classes('items-center gap-2 no-wrap w-60'):
                    uris = stack.art_uris
                    ui.html(''.join(f'<img src="{u}" style="width:24px;height:24px">' for u in uris) if uris else stack.icon).classes('items-center justify-center flex-none').style(
                        f'display:flex; min-width:34px; height:34px; padding:0 4px; background:{stack.fill}; '
                        f'border:{width}px solid {color}; border-radius:5px; font-size:20px')
                    ui.label(stack.name)

    with ui.column().classes('p-4 gap-0'):
        with ui.row().classes('items-center gap-2'):
            with ui.link(target='/'):
                ui.icon('home', color='primary').classes('text-4xl')
            ui.label('Icon Reference').classes('font-bold text-xl text-blue')
        with ui.row().classes('gap-2 items-center text-xs'):
            for tier, desc in TIER_LEGEND:
                ui.label().style(f'width:14px; height:14px; background:{TIER_FILLS[tier]}; border:1px solid #555; border-radius:3px')
                ui.label(desc)

        section("Cargo", [CargoStack(n.title(), None, n) for n in sorted(cargo_names)])
        for type_key, label in (*TRUCK_TYPE_LABELS.items(), (None, "Other")):
            section(f"Trucks: {label}", [vehicle_stack(n, kind="truck") for n in sorted(vehicles["truck"]) if truck_type(n) == type_key])
        section("Trailers", [vehicle_stack(n, kind="trailer") for n in sorted(vehicles["trailer"])])

def main():
    ui.link('Icon reference', '/icons').classes('m-4')
    if 1:
            # Create a responsive grid
        with ui.grid(columns=4).classes('gap-4 p-4'):
            for (region_slug, region), (_, region_id) in zip(regions_slugs, region_and_ids):
                with ui.link(target=f'/region/{region_slug}').classes('flex flex-col items-center gap-2 no-underline text-black'):
                        # Nest ui.image inside ui.link to make it clickable
                        ui.label(region).classes('font-bold text-lg')
                        ui.image(f"/assets/region_{region_id.lower()}.jpg").classes('w-100 rounded shadow-md')
    else:
        for region_slug, region in regions_slugs:
            ui.link(region, f'/region/{region_slug}')

ui.run(root, port=8081, title='SnowPlanner')

