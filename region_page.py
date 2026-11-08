"""The region page: all areas of a region on one map."""
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
from page_helpers import make_class_toggler, make_visibility_toggler
from obj_tree import *
from cargo_filter import *
from map_header import create_map_header


async def region(region_slug: str):
    region_client_alive_checker = None # element used to check if responder too events is still alive, as described in https://github.com/zauberzeug/nicegui/discussions/5503
    # also need to modify unsubscribe in nicegui event.py as described on ZDec 1 2025
    region_areas = areas_for_region[region_slug]
    region_area_ids = [ai.area_id for ai in region_areas]

    tree_ids = None
    tree_ticked_ids = None

    await ui.context.client.connected()

    ui.page_title(f"{region_areas[0].region}: SnowPlanner")

    highlight_ids = None
    skip_filter_change = False # set when we clear the filter ourselves, so the input's change handler doesn't re-highlight

    def set_highlighted_ids(id):
        nonlocal highlight_ids
        highlight_ids = id

    def clear_filter_if_hiding(node_id):
        nonlocal skip_filter_change

        if hidden_by_filter(obj_tree, node_id):
            skip_filter_change = bool(obj_filter.value)
            obj_filter.value = ""
            obj_tree.filter = ""

    async def build_obj_tree_data():
        return await build_obj_tree_data_base(region_area_ids, all_objs=True, completed_objs=switch_completed_objs.value)

    async def update_obj_tree():
#        tree_and_map.refresh()
#        return
#        print("update_obj_tree", obj_tree)
        ic("update_obj_tree")
        ic(ui.context.client.id)
        nonlocal tree_ids, tree_ticked_ids
        tree_nodes, tree_ticked_ids, tree_ids, expanded = await build_obj_tree_data()
        obj_tree.props['nodes'] = tree_nodes
        obj_tree.untick()
        obj_tree.tick(tree_ticked_ids)
        obj_tree.update()

    async def update_obj_tree_event(area_info):
        if region_client_alive_checker.is_deleted:
            tree_updated.unsubscribe(update_obj_tree_event)
            return

        # we care about all areas in the region
        if area_info.region_slug == region_slug:
            await update_obj_tree()

#    async def update_obj_tree_all():
#        print("update_obj_tree_all")
#        await update_obj_tree() # do our own first for responsiveness
#
#        tree_updated.emit(cur_area_info)

    async def handle_tree_tick(e):
        print("handle_tree_tick:")
        ticked_ids = set(e.value)
        ic(ticked_ids)
        await apply_tree_ticks(ticked_ids, set(tree_ids) - ticked_ids)
        await update_obj_tree()
        await update_svg()
        info = region_areas[0] # lets the other open pages for this region refresh too
        tree_updated.emit(info)
        map_updated.emit(info)

    async def highlight_cargo_highlight_ids(cargo_item_name):
        set_highlighted_ids(await get_cargo_highlight_ids(region_area_ids, cargo_item_name, not switch_completed_objs.value))

    async def obj_tree_selected(e):
        if (tree_id := e.value):
            ic(tree_id)

            if not "_" in tree_id:
                return

            prefix, id = tree_id.split("_", 1)

            if prefix in ("PR", "SPR", "TPR", "TO"):
                id = id.split("|")[1]

                if (pre_req_obj := (await Objective.filter(id=id).first())):
                    select_single_top_tree_node(obj_tree, pre_req_obj.obj_type + "s")

                node_id = "O_" + id
                obj_tree.select(node_id)
                scroll_to_node(node_id)
                obj_tree.expand([node_id])
                set_highlighted_ids(id)
            elif prefix == "L": # an objective's delivery location node: highlight that location on the map
                set_highlighted_ids(await ObjectiveItem.filter(deliver_loc__name=id, deliver_loc__area_id__in=region_area_ids).values_list("deliver_loc_id", flat=True) or id)
            elif prefix == "C":
                if (cargo_item := (await SourceCargoItem.filter(id=id).first())):
                    await highlight_cargo_highlight_ids(cargo_item.name)
            elif prefix == "OI":
                if (obj_item := (await ObjectiveItem.filter(id=id).first())):
                    await highlight_cargo_highlight_ids(obj_item.name)
            else:
                set_highlighted_ids(id)
        else:
            set_highlighted_ids(None)

        await update_svg()

    location_items = None
    areas = [area_info.area for area_info in region_areas]
    best_offsets, x_tiles = await calculate_area_offsets_for_region(region, areas)
    ic(x_tiles)

    # delivery plans
    plan_region = region_areas[0].region
    plan_layout = region_layout(areas, best_offsets)

    async def plan_select_stop(stop_id):
        set_highlighted_ids(f"plan:{stop_id}" if stop_id else None)
        await update_svg()

    async def plan_changed():
        await plan_panel.refresh()
        await update_svg()
        plans_changed.emit(plan_region) # every other open view of this region follows

    plan_panel = PlanPanel(plan_region, region_area_ids, lambda px, py: svg_point_to_db(px, py, *plan_layout), plan_changed, plan_select_stop, None, {a: i.abbrev for a, i in area_infos_by_area_id.items()})

    async def plans_changed_event(region_name):
        if region_client_alive_checker.is_deleted:
            plans_changed.unsubscribe(plans_changed_event)
            return

        if region_name == plan_region and plan_panel is not None:
            await plan_panel.refresh()
            await update_svg()

    # Compute prev/next regions
    other_regions = [r_slug for r_slug, r_name in regions_slugs if r_slug != region_slug]
    prev_region, next_region = None, None
    if other_regions:
        for a, b in pairwise(regions_slugs + regions_slugs[:1]):
            if b[0] == region_slug:
                prev_region = a
            if a[0] == region_slug:
                next_region = b

    async def get_region_svg():
        nonlocal location_items
#        ic("get_svg()", img_type, cur_area_info.area, highlight_ids)
        location_items = dict()
        use_svg_classes = dict(svg_classes.items())
        hide_types = set()

        for title, cb in checkboxes.items():
            if not cb.value:
                hide_types.add(title)

        img_type = "icon"

        img_paths = [get_image_name_ex(area_info, typ="icon") for area_info in region_areas]
        hlinks = [f'/area/{area_info.area_slug}' for area_info in region_areas]
#        highlight_ids = []
        return await generate_region_svg(region_areas[0].region, areas, best_offsets, x_tiles, img_paths, hlinks, location_items=location_items, element_classes = use_svg_classes, hide_types=hide_types, show_all=checkbox_all.value, fix_overlaps=checkbox_overlap.value, selected_ids=highlight_ids, plan=await dp.get_plan_view(plan_region))

    def filter_list_item_clicked(item):
        ic(filter_list_item_clicked, item)
#        ui.notify(f'Selected: {item}')
        obj_filter.value = item
#        obj_tree.filter = item
        obj_tree.expand()

    def get_highlight_ids_from_tree_ids(vis_nodes):
        to_highlight_ids = []

        for tree_id in vis_nodes:
            if not "_" in tree_id:
                continue

            prefix, id = tree_id.split("_", 1)

            if prefix in("C", "O", "IO"):
#                ic(prefix, id)
                to_highlight_ids.append(id)

        return to_highlight_ids

    async def get_vis_nodes_from_tree(obj_tree):
        if obj_tree:
            filter = obj_tree.filter.upper()
            ic("get_vis_nodes_from_tree", filter)
            to_highlight_ids = []

            for tree_node in obj_tree.nodes():
                if not "_" in (tree_id := tree_node["id"]):
                    continue

                if filter in tree_node["label"].upper():
                    to_highlight_ids.append(tree_id)

            return to_highlight_ids + await get_cargo_highlight_ids(region_area_ids, filter, False)

    async def filter_changed(e):
        nonlocal skip_filter_change
        ic("filter_changed", e)

        if skip_filter_change:
            skip_filter_change = False
            return

        obj_tree.filter = e.value
#        await asyncio.sleep(0.1)
#        ui.notify(f'filter_changed: {e.value}')
        to_highlight_ids = await get_vis_nodes_from_tree(obj_tree)
#        to_highlight_ids = list(obj_tree.nodes(visible=True))
#        all_nodes = list(obj_tree.nodes())
        ic(len(to_highlight_ids))
#        ic(len(all_nodes), len(vis_nodes))

#        if len(all_nodes) > len(vis_nodes):
        if to_highlight_ids:
#            to_highlight_ids = get_highlight_ids_from_tree_ids(vis_nodes)
            ic(to_highlight_ids)
            set_highlighted_ids(to_highlight_ids)
        else:
            set_highlighted_ids(None)

        await update_svg()


    async def update_svg():
        ic("update_svg", region_slug)
#        print("update_svg")

        svg_html.set_content(await get_region_svg())
#        initialize_d3()

    async def refresh_from_save():
        await update_obj_tree()
        await fill_cargo_filter_list(filter_cargo_items, region_area_ids, filter_list_item_clicked, checkbox_all.value)
        await plan_panel.refresh()
        await update_svg()

    async def all_changed():
        await update_svg()
        filter_cargo_items is not None and await fill_cargo_filter_list(filter_cargo_items, region_area_ids, filter_list_item_clicked, checkbox_all.value)

    async def update_svg_event(area_info):
        if region_client_alive_checker.is_deleted:
            map_updated.unsubscribe(update_svg_event)
            return

#        if area_info is not cur_area_info:
        await update_svg()

#    async def update_svg_all():
#        print("update_svg_all")
#        await update_svg() # do our own first for responsiveness
#        map_updated.emit(cur_area_info)

    def __REGION_CODE__(): pass
    print("region:", region_slug)


    checkboxes = {}
    checkbox_all = None
    filter_cargo_items = None
    checkbox_overlap = None
    checkbox_detail = None

    with ui.column().classes('w-full h-screen flex flex-col no-wrap overflow-hidden'):
        prev_region_item = (prev_region[0], prev_region[1]) if prev_region else None
        next_region_item = (next_region[0], next_region[1]) if next_region else None
        header = create_map_header(region_areas[0].region, "Region Map", prev_region_item, next_region_item, True, update_svg=lambda: update_svg(), all_changed=lambda: all_changed(), make_visibility_toggler=make_visibility_toggler)
        checkboxes, checkbox_all, checkbox_overlap = header.checkboxes, header.checkbox_all, header.checkbox_overlap

        with ui.row().classes('w-full flex-1 no-wrap gap-2 p-2 flex flex-row overflow-hidden bg-gray-100'):
            # Left Panel: Objective Tree
            with ui.column().classes('w-96 h-full bg-blue-100 p-2 flex flex-col shrink-0 min-h-0 shadow rounded'):
                with ui.row(align_items='center').classes('gap-1 w-full'):
                    ui.icon('refresh', color='primary').on('click', update_obj_tree).classes('text-3xl cursor-pointer')
                    obj_filter = ui.input('Objective filter', on_change=filter_changed).props('clearable').classes('flex-1')

                    with ui.column().classes('gap-0'):
                        switch_completed_objs = ui.switch("Completed", on_change=update_obj_tree).props("dense")

                tree_nodes, tree_ticked_ids, tree_ids, expanded = await build_obj_tree_data()

                with ui.scroll_area().classes('flex-1 w-full border bg-white mt-2'):
                    obj_tree = ui.tree(tree_nodes, tick_strategy='strict', on_tick=handle_tree_tick, on_select=obj_tree_selected).props("dense").classes("w-full")

                setup_obj_tree(obj_tree)
                obj_tree.tick(tree_ticked_ids)
                obj_tree.expand(["contracts", "tasks"] + expanded)
                obj_filter.bind_value_to(obj_tree, 'filter')

            # Middle Panel: Map Area with Header & Home Button
            with ui.column().classes('flex-1 h-full flex flex-col min-h-0 bg-white p-2 shadow rounded'):
                if 1:
                    svg_html = ui.html(await get_region_svg(), sanitize=False).classes('w-full flex-1 overflow-auto border')
                else:
                    with ui.grid(columns=2).classes('gap-4 p-4'):
                        for area_info in areas_for_region[region_slug]:
                            with ui.link(target=f'/area/{area_info.area_slug}').classes('flex flex-col items-center gap-2 no-underline text-black'):
                                ui.label(area_info.area).classes('font-bold text-lg')
                                ui.image(get_image_name_ex(area_info, "icon")).classes('w-100 rounded shadow-md')

            # Right Panel: Cargo Filter List
            filter_cargo_items = await build_cargo_filter_list(region_area_ids, filter_list_item_clicked=filter_list_item_clicked, show_all=checkbox_all.value, plan_panel=plan_panel)

    async def select_clicked_node(node_id, id, objective_id=None):
        clear_filter_if_hiding(node_id)

        if objective_id:
            obj_tree.expand(["O_" + objective_id])

        obj_tree.select(node_id)
        scroll_to_node(node_id)
        set_highlighted_ids(id)
        obj_tree.expand([node_id])
        await update_svg()

    async def handle_js_click_event(e):
        if not (rec := (location_items or {}).get(e.args['id'])) or not rec.id:
            return

        typ = rec.extra or rec.typ
        id = rec.id

        if typ == "plan": # a delivery plan stop: edit it
            await plan_panel.open_editor(int(id.split(":")[1]))
            return

        if plan_panel.pick_mode: # choosing a delivery plan location: use the clicked location's real position
            await plan_panel.handle_location_click(await map_item_for_rec(rec))
            return

        async def select_objective(objective):
            select_single_top_tree_node(obj_tree, objective.obj_type + "s")
            await select_clicked_node("O_" + objective.id, objective.id, objective.id)

        if typ == "gate":
            if (map_item := await MapItem.filter(id=id).prefetch_related("obj_locker").first()):
                if map_item.obj_locker and not map_item.obj_locker.completed:
                    await select_objective(map_item.obj_locker)
                else:
                    select_single_top_tree_node(obj_tree, "gates")
                    await select_clicked_node("G_" + id, id)
        elif typ == "truck":
            select_single_top_tree_node(obj_tree, "trucks")
            await select_clicked_node("T_" + id, id)
        elif typ == "src":
            select_single_top_tree_node(obj_tree, "sources")
            await select_clicked_node("S_" + id, id)
        elif typ == "pickup":
            if (obj_item := await ObjectiveItem.filter(id=id).prefetch_related("objective").first()):
                select_single_top_tree_node(obj_tree, obj_item.objective.obj_type + "s")
                await select_clicked_node("OI_" + obj_item.id, obj_item.id, obj_item.objective_id)
        elif typ == "dst":
            if (obj_item := await ObjectiveItem.filter(deliver_loc_id=id).prefetch_related("objective").first()):
                await select_objective(obj_item.objective)

    ui.on('js_click_event', handle_js_click_event)

    async def handle_plan_drag_event(e):
        if (rec := (location_items or {}).get(e.args['id'])) and rec.typ == "plan":
            await plan_panel.handle_plan_drag(int(rec.id.split(":")[1]), e.args['x'], e.args['y'])

    ui.on('js_map_point_event', lambda e: plan_panel.handle_map_point(e.args['x'], e.args['y']))
    ui.on('js_plan_drag_end', handle_plan_drag_event)
    ui.on('js_plan_reorder', lambda e: plan_panel.handle_reorder(int(e.args['leg']) if e.args['leg'] else None, e.args['ids']))
    ui.on('js_plan_move', lambda e: plan_panel.handle_move(e.args['id'], e.args['leg'], e.args['index']))

    region_client_alive_checker = obj_tree
    tree_updated.subscribe(update_obj_tree_event)
    map_updated.subscribe(update_svg_event)
    save_loaded.subscribe(refresh_from_save)
    plans_changed.subscribe(plans_changed_event)
