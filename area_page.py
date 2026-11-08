"""The area page: one area map with location editing."""
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


#@ui.page('/area')
async def area(area_slug: str):
    area_client_alive_checker = None # element used to check if responder too events is still alive, as described in https://github.com/zauberzeug/nicegui/discussions/5503
    # also need to modify unsubscribe in nicegui event.py as described on ZDec 1 2025

    # this ic await caused drag and drop to not work
#    ic(await MapItem.filter(id='US_09_01_WH_02').values("id", "name", "x", "y"))
    cur_area_info = copy.copy(areas_by_slug[area_slug]) # use copy so each client has is own uniquer ptr for copmarison
    region_areas = areas_for_region[cur_area_info.region_slug]
    region_area_ids = [ai.area_id for ai in region_areas]
    other_areas = [ai for ai in region_areas if ai.area_slug != area_slug]
    prev_area, next_area = None, None

    if other_areas:
        if len(other_areas) > 1:
            for a, b in pairwise(region_areas + region_areas[:1]):
                if b.area_slug == area_slug:
                    prev_area = a
                if a.area_slug == area_slug:
                    next_area = b
        else:
            prev_area = other_areas[0]

    await ui.context.client.connected()

    ui.page_title(f"{cur_area_info.partial_abbrev}: SnowPlanner")
    area_id = area_ids_by_area[cur_area_info.area]
    img_type = "icon"
    location_items = None
    selected_ids = []
    highlight_ids = None
    svg_html = None
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


    async def set_warning(warn=True):
        warn = False
        ic("set_warning", warn)

        if warn:
            js = '''
                window.onbeforeunload = function() {{
                    // This return value triggers the browser's confirmation dialog
                    return 'Are you sure you want to cancel changes?';
                    }}
                console.log("now warning")
            '''
        else:
            js = 'window.onbeforeunload = null;console.log("now not warning")'
        await ui.run_javascript(js)


    if 0:
        ui.add_css("""
            .my-blue-label {
                color: blue !important;
                font-size: 20px;
            }
        """)


    #######################
    # edit mode           #
    #######################

    loc_mode = False
    temp_positions = dict()

    class __EDIT_MODE__: pass

    async def set_loc_mode(value=True):
        nonlocal loc_mode
        loc_mode = value
        await set_warning(loc_mode)

    async def exit_loc_mode():
        await set_loc_mode(False)
        temp_positions.clear()
        save_button.set_text("Edit")
        cancel_button.set_visibility(False)
        group_button.set_visibility(False)

    async def cancel_save_locations():
        await exit_loc_mode()
        await update_svg()

    async def edit_save_locations():
        ic(loc_mode, cur_area_info.area)

        if loc_mode:
            for id, (flt, pos) in temp_positions.items():
                await flt.update(x=pos[0], y=pos[1])

            await exit_loc_mode()
        else:
            temp_positions.clear()
            save_button.set_text("Save")
            cancel_button.set_visibility(True)
            await set_loc_mode()

        await update_svg()

    async def update_location_dict_for_rec(id, new_pos):
        rec = location_items[id]
        map_item_id = rec.map_item_id
        flt = rec.flt
        assert new_pos[0] > 0 and new_pos[1] > 0

        if flt:
            ic("pre", map_item_id, rec.cur_pos)
            ic(await flt.values("id", "x", "y"))
#            await flt.update(x=new_pos[0], y=new_pos[1])
            temp_positions[map_item_id] = (flt, new_pos)
#            ic(await flt.values("map_item_id", "x", "y"))
            rec.cur_pos[:] = rec.adjusted_pos[:] = new_pos
            ic("post", map_item_id, rec.cur_pos)
        else:
            ic("no flt", rec)

    async def get_db_position(map_item_id, flt):
        if (res := temp_positions.get(map_item_id)):
            return res[1]

        map_item = await flt.first()
        ic(map_item, map_item.x, map_item.y, map_item.id)
        return map_item.x, map_item.y

    async def group_locations():
        ic("group", selected_ids, temp_positions)
        recs = [location_items[id] for id in selected_ids]
        xys = [await get_db_position(rec.map_item_id, rec.flt) for rec in recs]
        cnt = len(selected_ids)
        avg_x = sum(map(itemgetter(0), xys))/cnt
        avg_y = sum(map(itemgetter(1), xys))/cnt
#        ic(xys, avg_x, avg_y)
        new_pos = (avg_x, avg_y)

        for id in selected_ids:
            await update_location_dict_for_rec(id, new_pos)

        await update_svg()

    def update_group_locations_ui():
        cnt = len(selected_ids)
        group_button.set_visibility(cnt > 1)

        if cnt > 1:
            group_button.set_text(f"Group {cnt}")


    #######################
    # rectangle selection #
    #######################
    class __RECTANGLE_SELECTION__: pass

    async def get_id_by_x_y(x, y):
        js = """
          // 1. Get the element under the cursor coordinates
          const element = document.elementFromPoint(%d, %d);
          console.log(element);

          // 2. Check if the element or any parent has the class '.active-parent'
          // .closest() returns the element itself if it matches, otherwise the nearest matching ancestor
          const hasTargetClass = element ? element.closest('.loc2') : null;

          if (hasTargetClass) {
            console.log("Match found:", hasTargetClass);
          } else {
            console.log("No match found under cursor.");
          }
            return hasTargetClass ? hasTargetClass.id : null;
        """ % (x, y)
        return await ui.run_javascript(js)

    async def check_brush_selection(x0, y0, x1, y1):
        js_content, cached = d3_brush_selection_js_cache.get_content(True)
        if not cached: print("d3_brush_selection refresh")
        selected_ids_list = await ui.run_javascript(js_content % (x0, y0, x1, y1))
        return selected_ids_list

    async def handle_js_brush_end_event(e):
        print("handle_js_brush_end_event")
        x0, y0, x1, y1 = [e.args[k] for k in "x0,y0,x1,y1".split(",")]
#        ic(x0, y0, x1, y1)

        if not (x1 == y1 == 0):
            result = await check_brush_selection(x0, y0, x1, y1)
            ic(result)
            selected_ids[:] = result

            if result:
                update_group_locations_ui()


    #######################
    # dragging of locations
    #######################
    class __DRAGGING__(): pass

    def get_new_pos(rec, dx, dy):
        # have to deal with desired position (cur_pos) and where it was actaully placed (adjusted_pos)
        old_pos = rec.cur_pos
        act_pos = rec.adjusted_pos
        new_pos = dx + act_pos[0], dy + act_pos[1]
        ic(old_pos, new_pos)
        return new_pos

    def handle_js_drag_start_event(e):
        pass

    async def handle_js_drag_end_event(e):
#        ui.notify(f"Python received drag id from JS: {e.args['id']}")
        id = e.args['id']
        rec = location_items[id]
        dx, dy = e.args['dx'], e.args['dy']
        old_pos = rec.cur_pos
        new_pos = get_new_pos(rec, dx, dy)
        ic("drag", old_pos, new_pos)
        await update_location_dict_for_rec(id, new_pos)


    async def handle_js_click_event(e):
        target_id = e.args['id']
#        ui.notify(f"{id} clicked")
#        target_id = await get_id_by_x_y(e.args['clientX'], e.args['clientY'])

        if target_id:
            ic(target_id)
            await handle_clicked_id(target_id)

    async def handle_js_dblclick_event(e):
        target_id = e.args['id']

        if target_id:
            ic(target_id)

            if not (rec := location_items.get(target_id)):
                return

    #        rec2, id, typ, disp_name, cargos, back, fore, tw, loc_name, extra, classes, arrow, x, y = rec
            id = rec.id
            typ = rec.typ
            extra = rec.extra

            ic("handle_js_dblclick_event", target_id, id)

            if id:
                typ = extra or typ

                if typ == "gate":
                    if (map_item := (await MapItem.filter(id=id).first())):
                        new_area_id = map_item.to_area_id
                        area_slug = slugify(areas_by_area_id[new_area_id])
                        ic(new_area_id, area_slug)
                        ui.navigate.to(f"/area/{area_slug}")


    # 3. Register the Python handlers for the custom events
    ui.on('js_drag_start_event', handle_js_drag_start_event)
    ui.on('js_drag_end_event', handle_js_drag_end_event)
    ui.on('js_click_event', handle_js_click_event)
    ui.on('js_dblclick_event', handle_js_dblclick_event)
    ui.on('js_brush_end_event', handle_js_brush_end_event)

    #######################
    # Tree Functions
    #######################

    class __TREE_FUNCTIONS__: pass

    tree_ids = None
    tree_ticked_ids = None

    async def build_obj_tree_data():
        return await build_obj_tree_data_base(region_area_ids, all_objs=switch_all_objs.value, completed_objs=switch_completed_objs.value, cur_area_id=cur_area_info.area_id)

    async def update_obj_tree():
#        tree_and_map.refresh()
#        return
#        print("update_obj_tree", obj_tree)
        ic("update_obj_tree", area_id)
        ic(ui.context.client.id)
        nonlocal tree_ids, tree_ticked_ids
        tree_nodes, tree_ticked_ids, tree_ids, expanded = await build_obj_tree_data()
        obj_tree.props['nodes'] = tree_nodes
        obj_tree.untick()
        obj_tree.tick(tree_ticked_ids)
        obj_tree.update()

    async def update_obj_tree_event(area_info):
        if area_client_alive_checker.is_deleted:
            tree_updated.unsubscribe(update_obj_tree_event)
            return

#        ic(region)
        if area_info is not cur_area_info:
            await update_obj_tree()

    async def update_obj_tree_all():
        print("update_obj_tree_all")
        await update_obj_tree() # do our own first for responsiveness

        tree_updated.emit(cur_area_info)


#    QTree Tick strategy
#    There are three ticking strategy: ‘leaf’, ‘leaf-filtered’, ‘strict’ with an additional (and default) ‘none’ which disables ticking.
#    leaf    Ticked nodes are only the leaves. Ticking a node influences the parent’s ticked state too (parent becomes partially ticked or ticked), as well as its children (all tickable children become ticked).
#    leaf-filtered   Same concept as leaf, only that this strategy applies only to filtered nodes (the nodes that remain visible after filtering).
#    strict  Ticked nodes are independent of parent or children tick state.


    async def handle_tree_tick(e):
        print("handle_tree_tick:")
        ticked_ids = set(e.value)
        ic(ticked_ids)
        unticked_ids = set(tree_ids) - ticked_ids
#        ic(len(tree_ids), len(ticked_ids), len(unticked_ids), len(tree_ticked_ids))
        old_ticked_ids = set(tree_ticked_ids)
#        ic(old_ticked_ids - ticked_ids, ticked_ids - old_ticked_ids)

            # update in DB
#        await Objective.filter(id__in=tree_ids).update(
#            completed = Case(When(id__in  = hide_ids, then = True), default=False))

        await apply_tree_ticks(ticked_ids, unticked_ids)

            # update to show any objectives that have become unblocked
#        await update_obj_tree()
        await update_obj_tree_all()

            # need full update bc of how itmes are group and can have alocation name added
        await update_svg_all()

    async def highlight_cargo_highlight_ids(cargo_item_name):
        ic(cargo_item_name)
        to_highlight_ids = await get_cargo_highlight_ids([area_id], cargo_item_name, not switch_completed_objs.value)
        ic(to_highlight_ids)
        set_highlighted_ids(to_highlight_ids)

    async def obj_tree_selected(e):
        if (tree_id := e.value):
            ic(tree_id)

            if not "_" in tree_id:
                return

            prefix, id = tree_id.split("_", 1)
            ic("selected", prefix, id)

            if prefix in("PR", "SPR", "TPR", "TO"):
                id = id.split("|")[1]

                if (pre_req_obj := (await Objective.filter(id=id).first())):
                    select_single_top_tree_node(obj_tree, pre_req_obj.obj_type + "s")

                node_id = "O_" + id
#                set_highlighted_ids(id)
#                obj_tree.select(node_id)
#                scroll_to_node(node_id)

                await select_tree_node(node_id, id, objective_id=None)
                return
            elif prefix == "L": # an objective's delivery location node: highlight that location on the map
                set_highlighted_ids(await ObjectiveItem.filter(deliver_loc__name=id, deliver_loc__area_id__in=region_area_ids).values_list("deliver_loc_id", flat=True) or id)
            elif prefix == "C":
                ic(id)

                if (cargo_item := (await SourceCargoItem.filter(id=id).first())):
                    await highlight_cargo_highlight_ids(cargo_item.name)
            elif prefix == "OI":
                if (obj_item := (await ObjectiveItem.filter(id=id).prefetch_related("objective").first())):
                    await highlight_cargo_highlight_ids(obj_item.name)
            else:
                set_highlighted_ids(id)
#                obj_tree.expand([tree_id])
        else:
            set_highlighted_ids(None)

        ic("obj_tree_selected", highlight_ids)
        await update_svg()

    async def select_tree_node(node_id, id, objective_id=None):
        clear_filter_if_hiding(node_id)

        if objective_id:
            obj_tree.expand(["O_" + objective_id])

        obj_tree.select(node_id)
        scroll_to_node(node_id)
        set_highlighted_ids(id)
        obj_tree.expand([node_id])
        show_panel()
        await update_svg_all()

    async def filter_changed(e):
        nonlocal skip_filter_change

        if skip_filter_change:
            skip_filter_change = False
            return

#        obj_tree.filter = e.value
        to_highlight_ids = await get_cargo_highlight_ids(region_area_ids, e.value, not switch_completed_objs.value)
        set_highlighted_ids(to_highlight_ids)
        await update_svg()

    #######################
    # SVG Map Functions
    #######################

    class __SVG_MAP_FUNCTIONS__: pass


    async def handle_clicked_id(target_id):
#                ui.notify(f"clicked {target_id}")
#                ic("clicked", target_id)
        if not (rec := location_items.get(target_id)):
            return

#        flt, id, typ, disp_name, cargos, back, fore, tw, loc_name, extra, classes, arrow, x, y = rec
        id = rec.id
        typ = rec.typ
        extra = rec.extra

        if (extra or typ) == "plan": # a delivery plan stop: edit it
            await plan_panel.open_editor(int(id.split(":")[1]))
            return

        if plan_panel.pick_mode: # choosing a delivery plan location: use the clicked location's real position
            await plan_panel.handle_location_click(await map_item_for_rec(rec))
            return

        async def select_objective(objective):
            objective_id = objective.id
            select_single_top_tree_node(obj_tree, objective.obj_type + "s")
            await select_tree_node("O_" + (objective_id), (objective_id), (objective_id))

        if id:
            typ = extra or typ
            ic("clicked", typ, id, rec.disp_name, extra)

            if typ == "gate":
                if (map_item := await MapItem.filter(id=id).prefetch_related("obj_locker").first()):
                    if map_item.obj_locker and not map_item.obj_locker.completed:
                        await select_objective(map_item.obj_locker)
                    else:
                        select_single_top_tree_node(obj_tree, "gates")
                        await select_tree_node("G_" + id, id)
            elif typ == "truck":
                node_id = "T_" + id
                ic(node_id)
                select_single_top_tree_node(obj_tree, "trucks")
                await select_tree_node(node_id, id)
            elif typ == "src":
                node_id = "S_" + id
                ic(node_id)
                select_single_top_tree_node(obj_tree, "sources")
                await select_tree_node(node_id, id)
            elif typ == "pickup":
                if (obj_item := (await ObjectiveItem.filter(id=id).prefetch_related("objective").first())):
                    ic("found objective", obj_item.objective_id)
                    id = obj_item.objective_id
                    select_single_top_tree_node(obj_tree, obj_item.objective.obj_type + "s")
                    await select_tree_node("OI_" + obj_item.id, obj_item.id, id)
            elif typ == "dst":
                if (obj_item := (await ObjectiveItem.filter(deliver_loc_id=id).prefetch_related("objective").first())):
                    ic("found objective", obj_item.objective_id)
                    await select_objective(obj_item.objective)

    async def svg_double_clicked(e):
        target_id = await get_id_by_x_y(e.args['clientX'], e.args['clientY'])

        if not (rec := location_items.get(target_id)):
            return

        id, typ, extra = rec.id, rec.typ, rec.extra
#        ic("svg_double_clicked", target_id, id, e.args['clientX'], e.args['clientY'])

        if id:
            typ = extra or typ

            if typ == "gate":
                if (map_item := (await MapItem.filter(id=id).first())):
                    new_area_id = map_item.to_area_id
                    area_slug = slugify(areas_by_area_id[new_area_id])
                    ic(new_area_id, area_slug)
                    ui.navigate.to(f"/area/{area_slug}")

    async def get_area_svg():
        nonlocal location_items
#        ic("get_area_svg()", img_type, cur_area_info.area, highlight_ids)
        img_src = get_image_name(img_type)
        location_items = dict()

        use_svg_classes = dict(svg_classes.items())
        hide_types = set()

        for title, cb in checkboxes.items():
            if not cb.value:
#                    ic("hide", title)
                hide_types.add(title)

        return await generate_area_svg(cur_area_info.region, cur_area_info.area, img_src, loc_mode=loc_mode, location_items=location_items, element_classes = use_svg_classes, hide_types=hide_types, show_all=checkbox_all.value, fix_overlaps=not loc_mode and checkbox_overlap.value, selected_ids=highlight_ids, detail_in_loc_mode=checkbox_detail.value, override_positions=temp_positions, plan=None if loc_mode else await dp.get_plan_view(cur_area_info.region))

    def initialize_d3():
        print(f"initialize_d3 {cur_area_info.area_id}")
        js_content, cached = d3_init_js_cache.get_content(True)
        if not cached: print("initialize_d3 refresh")
        ui.run_javascript(js_content % (("true", "#map_svg", "#map_svg_image_group") if loc_mode else ("false", "#map_svg", "#map_svg_image_group")))
        print("done initialize_d3")


    async def update_svg():
        ic("update_svg", area_id)
#        print("update_svg")

        if svg_html:
            svg_html.set_content(await get_area_svg())
            initialize_d3()

    async def refresh_from_save():
        await update_obj_tree()
        await fill_cargo_filter_list(filter_cargo_items, [cur_area_info.area_id], filter_list_item_clicked, checkbox_all.value)
        await plan_panel.refresh()
        await update_svg()

    async def all_changed():
        await update_svg()
        filter_cargo_items is not None and await fill_cargo_filter_list(filter_cargo_items, [cur_area_info.area_id], filter_list_item_clicked, checkbox_all.value)

    async def update_svg_event(area_info):
        ic("update_svg_event", area_id)

        if area_client_alive_checker.is_deleted:
            map_updated.unsubscribe(update_svg_event)
            return

        if area_info is not cur_area_info:
            await update_svg()

    async def update_svg_all():
        print("update_svg_all")
        await update_svg() # do our own first for responsiveness
        map_updated.emit(cur_area_info)

    # delivery plans
    async def plan_select_stop(stop_id):
        set_highlighted_ids(f"plan:{stop_id}" if stop_id else None)
        await update_svg()

    async def plan_changed():
        await plan_panel.refresh()
        await update_svg()
        plans_changed.emit(cur_area_info.region) # every other open view of this region follows

    def plan_point_to_location(px, py):
        if (hit := svg_point_to_db(px, py)):
            return cur_area_info.area_id, hit[1], hit[2]

    plan_panel = PlanPanel(cur_area_info.region, region_area_ids, plan_point_to_location, plan_changed, plan_select_stop, cur_area_info.area_id, {a: i.abbrev for a, i in area_infos_by_area_id.items()})

    async def plans_changed_event(region_name):
        if area_client_alive_checker.is_deleted:
            plans_changed.unsubscribe(plans_changed_event)
            return

        if region_name == cur_area_info.region:
            await plan_panel.refresh()
            await update_svg()

    async def handle_plan_drag_event(e):
        if (rec := location_items.get(e.args['id'])) and rec.typ == "plan":
            await plan_panel.handle_plan_drag(int(rec.id.split(":")[1]), e.args['x'], e.args['y'])

    ui.on('js_map_point_event', lambda e: plan_panel.handle_map_point(e.args['x'], e.args['y']))
    ui.on('js_plan_drag_end', handle_plan_drag_event)
    ui.on('js_plan_reorder', lambda e: plan_panel.handle_reorder(int(e.args['leg']) if e.args['leg'] else None, e.args['ids']))
    ui.on('js_plan_move', lambda e: plan_panel.handle_move(e.args['id'], e.args['leg'], e.args['index']))


    #######################
    # Main Functions
    #######################

    def __MAIN_FUNCTIONS__(): pass

    if 0:
        def add_class_via_js(search_class, add_class):
            # JavaScript selects elements by class and adds a new one
            ui.run_javascript('''
                document.querySelectorAll(".%s").forEach(el => {
                    el.classList.add("%s");
                });
            ''' % (search_class, add_class))

        def remove_class_via_js(search_class, remove_class):
            # JavaScript selects elements by class and adds a new one
            ui.run_javascript('''
                document.querySelectorAll(".%s").forEach(el => {
                    el.classList.remove("%s");
                });
            ''' % (search_class, remove_class))




    checkboxes = {}
    checkbox_all = None
    filter_cargo_items = None
    checkbox_overlap = None
    checkbox_detail = None

    def get_image_name(typ, actual=False):
        return get_image_name_ex(cur_area_info, typ, actual=actual)

    async def switch_map(icons):
        nonlocal img_type
        img_type = "icon" if icons else "normal"
        ic("switch_map()", img_type, cur_area_info.area)

        if 0:
            await update_svg()
        else:
            # change background dynamically
            ui.query('#map_svg_image').props(f'href="{get_image_name(img_type)}"')

        # Function to toggle the panel
    def show_panel():
        side_panel.classes(remove='w-0 overflow-hidden', add='w-100') # Expand

    def hide_panel():
        side_panel.classes(remove='w-100', add='w-0 overflow-hidden') # Collapse

    def toggle_panel():
        if 'w-0' in side_panel.classes:
            show_panel()
        else:
            hide_panel()

    def filter_list_item_clicked(item):
        obj_filter.value = item
        obj_tree.expand()

    #######################
    # Main Code
    #######################

    def __AREA_CODE__(): pass

    await ui.context.client.connected()

#    with ui.column().classes('gap-0 w-full h-full'):
#    with ui.column().classes('gap-0 w-screen h-screen'):
#    with ui.column().classes('gap-0 w-screen h-dvh flex flex-col'):
    with ui.column().classes('gap-0 w-dvw h-dvh flex flex-col no-wrap'):
            # Header row
        prev_area_item = (prev_area.area_slug, prev_area.partial_abbrev) if prev_area else None
        next_area_item = (next_area.area_slug, next_area.partial_abbrev) if next_area else None
        header = create_map_header(cur_area_info.region, cur_area_info.partial_abbrev, prev_area_item, next_area_item, False, update_svg=lambda: update_svg(), all_changed=lambda: all_changed(), make_visibility_toggler=make_visibility_toggler, toggle_panel=lambda: toggle_panel(), switch_map=lambda icons: switch_map(icons), edit_save_locations=lambda: edit_save_locations(), group_locations=lambda: group_locations(), cancel_save_locations=lambda: cancel_save_locations())
        checkboxes, checkbox_all, checkbox_overlap, checkbox_detail = header.checkboxes, header.checkbox_all, header.checkbox_overlap, header.checkbox_detail
        save_button, group_button, cancel_button = header.save_button, header.group_button, header.cancel_button

            # Container holding both the side panel and content
#        with ui.row().classes('w-full h-full no-wrap gap-0 overflow-hidden gap-1'):
#        with ui.row().classes('w-full h-full no-wrap gap-1 grow overflow-y-auto'):
#        with ui.row().classes('w-full h-full no-wrap gap-1 flex-1'):
        with ui.row().classes('w-full no-wrap gap-1 flex-1 flex flex-row min-h-0 overflow-hidden'):
            # The Sliding Panel, Use transition to animate the width change
#            with ui.column().classes('h-full bg-blue-100 transition-all duration-300 ease-in-out w-0 overflow-hidden') as side_panel:
            with ui.column().classes('h-full bg-blue-100 transition-all duration-300 ease-in-out w-100 flex flex-col shrink-0 min-h-0') as side_panel:
#            side_panel.bind_visibility_from(menu, 'value')
                with ui.row(align_items='center').classes('gap-1'):
    #                    ui.button(icon='cached', on_click=update_obj_tree).classes('m-0')
                    ui.icon('refresh', color='primary').on('click', update_obj_tree).classes('text-3xl')
                    obj_filter = ui.input('Objective filter', on_change=filter_changed).props('clearable')
#                    ui.icon('clear all', color='primary').on('click', update_obj_tree).classes('text-4xl')
#                    ui.icon('done all', color='primary', on_click=update_obj_tree) # .classes('text-4xl')
                    with ui.column().classes('gap-0'):
                        switch_all_objs = ui.switch("Region", on_change=update_obj_tree).props("dense")
                        switch_completed_objs = ui.switch("Completed", on_change=update_obj_tree).props("dense")

                tree_nodes, tree_ticked_ids, tree_ids, expanded = await build_obj_tree_data()

#                with ui.scroll_area().classes('h-205 border'):
                with ui.scroll_area().classes('flex-1 w-full border bg-white min-h-0'):
                    obj_tree = ui.tree(tree_nodes, tick_strategy='strict', on_tick=handle_tree_tick, on_select=obj_tree_selected).props("dense").classes("w-full")

                setup_obj_tree(obj_tree)
                obj_tree.tick(tree_ticked_ids)
                obj_tree.expand(["contracts", "tasks"] + expanded)
                obj_filter.bind_value_to(obj_tree, 'filter')

                # Main Content Area
#            with ui.column().classes('h-full w-full bg-gray-100'):
#            with ui.column().classes('h-full bg-gray-100'):
            if 1:
                svg_html = ui.html(await get_area_svg(), sanitize=False).classes('h-fullflex-1')
                initialize_d3()
                svg_html.on('dblclick', svg_double_clicked)

            filter_cargo_items = await build_cargo_filter_list([cur_area_info.area_id], filter_list_item_clicked=filter_list_item_clicked, show_all=checkbox_all.value, plan_panel=plan_panel)

        area_client_alive_checker = obj_tree
        tree_updated.subscribe(update_obj_tree_event)
        map_updated.subscribe(update_svg_event)
        save_loaded.subscribe(refresh_from_save)
        plans_changed.subscribe(plans_changed_event)
