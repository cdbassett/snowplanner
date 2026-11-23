"""The header row shared by the region and area pages."""
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


def create_map_header(region_name, partial_title, prev_item, next_item, is_region, update_svg, all_changed, make_visibility_toggler, toggle_panel=None, switch_map=None, switch_water=None, has_water=False, switch_built=None, has_built=False, all_areas=None, edit_save_locations=None, group_locations=None, cancel_save_locations=None, ids_changed=None):
    """The header row shared by the region and area pages: buttons, title with prev / next links and the view checkboxes.

    The callbacks come from the page (they are only called when the user acts, so late-bound lambdas are fine). Returns a namespace with the widgets the page needs afterwards.
    """
    def checkbox(text, **kw):
        return ui.checkbox(text, **kw).props("dense")

    async def update_ids(): # map ids instead of names: redraw the map and relabel the objective tree
        await update_svg()

        if ids_changed:
            await ids_changed()

    w = SimpleNamespace(checkbox_water=None, checkbox_built=None, checkboxes=None, checkbox_all=None, checkbox_overlap=None, checkbox_ids=None, save_button=None, group_button=None, cancel_button=None)

    with ui.row(align_items='center').classes('gap-1 no-wrap flex-none'):
        if not is_region:
            ui.button(icon='menu', on_click=toggle_panel)

        ui.button(icon='refresh', on_click=update_svg).classes('m-0')
        with ui.button_group().classes('m-0'):
            save_button = ui.button(icon='save', on_click=load_game_save).props('color=secondary').classes('m-0')

            with save_button:
                save_tip = ui.tooltip('')

            with ui.button(icon='arrow_drop_down').props('color=secondary dense').classes('m-0'):
                save_menu = ui.menu()

        def fill_save_menu():
            """List the save slots (newest first); the chosen one is kept for every later refresh until another is chosen."""
            import time
            current = selected_game_save()
            save_menu.clear()

            async def choose(path):
                select_game_save(path)
                await load_game_save()

            with save_menu:
                ui.menu_item(('✔ ' if current is None else '') + 'Newest save (automatic)', on_click=lambda: choose(None))

                try:
                    saves = list_game_saves()
                except Exception as e:
                    saves = []
                    ui.label(f'Cannot list saves: {e}').classes('text-xs px-2')

                for path in saves:
                    when = time.strftime('%Y-%m-%d %H:%M', time.localtime(path.stat().st_mtime))
                    ui.menu_item(('✔ ' if current == path else '') + f'{path.name}  ({when})', on_click=lambda p=path: choose(p))

            save_tip.set_text(f'Refresh from {current.name}' if current else 'Refresh from newest game save')

        save_menu.on('before-show', fill_save_menu)
        fill_save_menu()

        with ui.link(target='/'):
            ui.icon('home', color='primary').classes('text-4xl')

        if all_areas: # (previous, next) area slugs in the game's order across all regions, to step through every map
            go_prev, go_next = f'/area/{all_areas[0]}', f'/area/{all_areas[1]}'
            ui.keyboard(on_key=lambda e: ui.navigate.to(go_prev if e.key.name == "PageUp" else go_next) if e.action.keydown and e.key.name in ("PageUp", "PageDown") else None, ignore=['input', 'select', 'button', 'textarea'])

        with ui.column().classes('gap-0'):
            ui.label(f'{region_name}: {partial_title}').classes(f'font-bold text-xl text-blue').classes('m-0').props("dense")

            if prev_item:
                prev_slug, prev_name = prev_item
                with ui.row().classes('gap-2'):
                    target_url = f'/region/{prev_slug}' if is_region else f'/area/{prev_slug}'
                    ui.link(("<<" if next_item else "") + prev_name, target_url).classes('m-0')

                    if next_item:
                        next_slug, next_name = next_item
                        next_target_url = f'/region/{next_slug}' if is_region else f'/area/{next_slug}'
                        ui.link(next_name + ">>", next_target_url).classes('m-0')

        if not is_region:
            checkbox("Icons", value=True, on_change=lambda e: switch_map(e.value)).bind_value(app.storage.tab, 'Icons')

            if has_water: # the level has a water depth overlay
                w.checkbox_water = checkbox("Water", value=False, on_change=lambda e: switch_water(e.value)).bind_value(app.storage.tab, 'Water')

            if has_built: # the level has bridges / pipes that contracts build
                w.checkbox_built = checkbox("Built", value=False, on_change=lambda e: switch_built(e.value)).bind_value(app.storage.tab, 'Built')

            with ui.column().classes('gap-0'):
                w.checkbox_overlap = checkbox("Ovl", value=True, on_change=update_svg).bind_value(app.storage.tab, 'Overlap')
                w.checkbox_ids = checkbox("Ids", value=False, on_change=update_ids).bind_value(app.storage.tab, 'MapIds') # show map ids instead of location names

            with ui.column().classes('gap-0'):
                checkbox("Dots", value=True, on_change=make_visibility_toggler("location-dot"))
                w.checkbox_all = checkbox("All", value=False, on_change=lambda: all_changed()).bind_value(app.storage.tab, 'Completed')
        else:
            with ui.column().classes('gap-0'):
                w.checkbox_overlap = checkbox("Ovl", value=False, on_change=update_svg).bind_value(app.storage.tab, 'RegionOverlap')
                checkbox("Dots", value=True, on_change=make_visibility_toggler("location-dot"))

            with ui.column().classes('gap-0'):
                w.checkbox_all = checkbox("All", value=False, on_change=lambda: all_changed()).bind_value(app.storage.tab, 'Completed')
                w.checkbox_ids = checkbox("Ids", value=False, on_change=update_ids).bind_value(app.storage.tab, 'MapIds')

        with ui.grid(columns=3).classes('gap-y-0 gap-x-2'):
            w.checkboxes = dict((title, checkbox(title, value=title not in svg_vis_default_off, on_change=update_svg).bind_value(app.storage.tab, title)) for title in svg_vis_togglers)

        if not is_region: # editing the positions of locations is only available per area
            w.save_button = ui.button('Edit', on_click=lambda: edit_save_locations())
            w.group_button = ui.button('Group', on_click=lambda: group_locations())
            w.group_button.set_visibility(False)
            w.cancel_button = ui.button('Cancel', on_click=lambda: cancel_save_locations())
            w.cancel_button.set_visibility(False)

    return w
