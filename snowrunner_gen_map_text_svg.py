#!/usr/bin/env python3
import itertools
from collections import defaultdict, namedtuple
from operator import itemgetter
from collections.abc import Iterable
import math
import textwrap

from icecream import ic
import drawsvg as draw
from tortoise.expressions import Q
from tortoise import Tortoise, run_async

from snowplanner_utils import *
from utils.iter_utils import arithtuple, first_true, flatten
from utils.correct_overlaps import Rectangle, correct_rect_overlaps, correct_rect_overlaps_cached
from database.models import *
from cargo_icons import CargoStack, Recipe, parse_recipe, vehicle_stack
from utils.timer_utils import Timer
from database.config import snowplanner_db_url


main_scale = 925

# Subclass DrawingBasicElement if it cannot have child nodes
# Subclass DrawingParentElement otherwise
# Subclass DrawingDef if it must go between <def></def> tags in an SVG
class Hyperlink(draw.DrawingParentElement):
    TAG_NAME = 'a'
    def __init__(self, href, target=None, **kwargs):
        # Other init logic...
        # Keyword arguments to super().__init__() correspond to SVG node
        # arguments: stroke_width=5 -> <a stroke-width="5" ...>...</a>
        super().__init__(href=href, target=target, **kwargs)

area_ids_by_area = get_area_ids_by_area()
areas_by_area_id = get_areas_by_area_id()
abbreviations_by_area_id = get_abbreviations_by_area_id()

DrawItem = namedtuple("DrawItem", "flt,map_item_id,id,typ,disp_name,cargo_items,selected,blocked,back,fore,width,loc_name,extra,classes,arrow,tip")
DrawRec = namedtuple("DrawRec", "flt,map_item_id,id,typ,disp_name,cargo_items,selected,blocked,back,fore,width,loc_name,extra,classes,arrow,tip,html_id,cur_pos,adjusted_pos")

precedence = [
    "loc",
    "location",
    "src",
    "pickup",
    "dst",
    ]
precedence = dict((s, n) for n, s in enumerate(precedence))

ICON_MAX_COLS = 3
ENTRY_CORNER_RADIUS = 3
LINK_CASING_LAYERS = [(7, "black", 0.4), (5, "white", 1)] # (width, color, opacity) under the pickup -> delivery lines, widest first
LINK_ARROW_SPACING = 80
LINK_ARROW_LENGTH = 15
LINK_ARROW_WIDTH = 16
LINK_ARROW_NOTCH = 6 # how far the chevron's inner notch sits in from its wing tips
LINK_COLOR = "RebeccaPurple"
LINK_SELECTED_COLOR = "hotpink" # center color while the link's pickup is highlighted
LINK_CHEVRON_COLOR = "DeepSkyBlue"
# LINK_CHEVRON_STROKE = "white"
LINK_CHEVRON_STROKE = "black"
TITLE_MAX_CHARS = 12


def wrap_title(title):
    """Break a location/objective name into lines of about TITLE_MAX_CHARS, only between words."""
    return textwrap.wrap(title, TITLE_MAX_CHARS, break_long_words=False, break_on_hyphens=False)


def entry_title_lines(entry):
    """Entries with a hover tip (deliveries and pickups) don't show their objective name; it's only in the tip."""
    return [] if entry.tip else wrap_title(entry.disp_name)


def cargo_icon_size(text_height):
    return text_height * 2.2


def layout_cargo(cargo_items, text_height):
    """Place cargo lines under an entry's title: text lines as rows, consecutive CargoStacks as wrapped rows of icon squares.

    Recipes are laid out as equation rows. Returns (placements, width, height); placements are ("text", str, y), ("icon", CargoStack, x, y) or ("arrow", x, y, w), relative to the top-left of the area under the title.
    """
    sq = cargo_icon_size(text_height)
    gap = text_height / 4
    char_w = text_height / 2
    placements = []
    width = 0
    y = 0

    def kind(c):
        return "recipe" if isinstance(c, Recipe) else "icon" if isinstance(c, CargoStack) else "text"

    for item_kind, group in itertools.groupby(cargo_items, kind):
        group = list(group)

        if item_kind == "recipe": # one equation per row: product <- ingredients
            arrow_w = sq * 0.7

            for recipe in group:
                placements.append(("icon", recipe.product, 0, y))
                placements.append(("arrow", sq + gap, y, arrow_w))
                x = sq + gap + arrow_w + gap

                for ingredient in recipe.ingredients:
                    placements.append(("icon", ingredient, x, y))
                    x += sq + gap

                width = max(width, x - gap)
                y += sq + gap
        elif item_kind == "icon":
            cols = 2 if len(group) == 4 else ICON_MAX_COLS # exactly 4 icons: one square of 4 rather than 3 + 1
            max_w = cols * sq + (cols - 1) * gap
            row = x = used = 0
            on_vehicle_row = False # cargo loaded on a truck or trailer stays on the vehicle's line

            for stack in group: # trailer squares are wider; trucks and trailers otherwise get a line of their own
                w = stack.width_factor * sq
                new_row = stack.is_vehicle or (on_vehicle_row and not stack.loaded)

                if x and (new_row or x + w > max_w + 0.01):
                    row += 1
                    x = 0

                placements.append(("icon", stack, x, y + row * (sq + gap)))
                x += w + gap
                used = max(used, x - gap)
                on_vehicle_row = stack.is_vehicle or (on_vehicle_row and stack.loaded)

            width = max(width, used)
            y += (row + (1 if x else 0)) * (sq + gap)
        else:
            for line in group:
                placements.append(("text", line, y))
                width = max(width, len(line) * char_w)
                y += text_height

    return placements, width, y


def is_iterable_not_string(obj):
    return isinstance(obj, Iterable) and not isinstance(obj, (str, bytes))

def as_set(items):
    if is_iterable_not_string(items):
        return set(items)

    return set([items])


def create_drawing(width=main_scale, height=main_scale, text_height = 8, loc_mode = False):
#    W, H = size, size
    draw_width = width

    if loc_mode:
        draw_width += width // 10

#    d = draw.Drawing(draw_width, height, origin=(0,0), id="map_svg")
    d = draw.Drawing(draw_width, height, origin=(0,0), id="map_svg",
        animation_config=draw.types.SyncedAnimationConfig(
            # Animation configuration
            duration=4,  # Seconds
            ))
#        d.append_css()
#        d.append(draw.Raw(r'<style>text { font-family: "Arial"; font-size: "30";}</style>'))
    d.append(draw.Raw(r'<style>text { font-family: "Arial";}</style>'))
    d.append(draw.Raw(r'<style>.hide-me { visibility: hidden; }</style>'))

    if loc_mode:
        drag_mask = draw.Mask(id='drag_mask', maskContentUnits='userSpaceOnUse')
        drag_mask.append(draw.Rectangle(-200, -200, 400, 400, fill='white')) # Opaque area
        drag_mask.append(draw.Circle(0, 0, 10, fill='black'))
        drag_mask.append(draw.Line(-10, 0, 10, 0, stroke='white'))
        drag_mask.append(draw.Line(0, -10, 0, 10, stroke='white'))
        d.append(drag_mask)

    id_gen = itertools.count(1)
    return d, id_gen




async def generate_area_svg_objects(region, area, text_height = 8, loc_mode = False,
        element_classes = {}, hide_types = set(), show_all=False, selected_ids=None, detail_in_loc_mode=False,
        override_positions=None, overall_group=None, offset_lookup={}):
    selected_ids = as_set(selected_ids)
    override_positions = override_positions or dict()
    multi_area = overall_group is not None

    text_width_mult = text_height / 2
    text_h_margin = text_height / 2
#    text_h_margin = text_height

    def calc_text_width(title, lst):
        return max(max(map(len, wrap_title(title)), default=0) * text_width_mult, layout_cargo(lst, text_height)[1]) + text_h_margin * 3

    def make_draw_item(flt, map_item_id, id, typ, disp_name, cargos, selected, blocked, back, fore="black", loc_name=None, extra=None, classes=None, arrow=None, tip=None):
        if loc_mode: # icons aren't drawn when editing locations
            cargos = [str(c) for c in cargos]

        sl = abbreviate_line(disp_name)
        return DrawItem(flt, map_item_id, id, typ, disp_name, cargos, selected, blocked, back, fore, calc_text_width('' if tip else sl, cargos), loc_name, extra, classes, arrow, tip)

    def make_location_item(flt, map_item_id, id, disp_name, selected, blocked, back="lightblue", fore="black", loc_name=None, extra=None, lst=[], classes=None, arrow=None):
        lst = [str(c) for c in lst]
        sl = abbreviate_line(disp_name.split("|")[0])
#        return (id, "loc" if loc_mode else "location", sl, lst, back, fore, calc_text_width(sl, lst), loc_name, extra)
        return DrawItem(flt, map_item_id, id, "loc" if loc_mode else "location", sl, lst, selected, blocked, back, fore, calc_text_width(sl, lst), loc_name, extra, classes, arrow, None)

    def make_source_cargo(cargo_item, ccnt):
        if (recipe := parse_recipe(cargo_item.craft_desc)):
            return recipe

        return CargoStack(cargo_item.name, ccnt, counted_cargo_none(ccnt, abbreviate_line(cargo_item.name)))

    def normalized(val):
#        return max(min(val, 950), 50)
        return max(min(val, 1000), 0)

    def db_pos(rec):
        if (pos_rec := override_positions.get(rec.id)):
            pos = pos_rec[1]
            x, y = normalized(pos[0]), normalized(pos[1])
        elif rec.x is not None and rec.y is not None:
#            assert 1000 >= rec.x >= 0 and 1000 >= rec.y >= 0, f"({rec.x}, {rec.y}) is out of bounds"
            x, y = normalized(rec.x), normalized(rec.y)
        else:

            return None, None
        if 0:
            ofs_x, ofs_y = None, None

            if offset_lookup:
                ofs_x, ofs_y = offset_lookup[rec.area_id]
#            ic(x, ofs_x, y, ofs_y)
                x += ofs_x
                y += ofs_y

#        ic(rec.name, rec.area_id, x, y, ofs_x, ofs_y, len(offset_lookup))
            ic(rec.name, rec.area_id, x, y, ofs_x, ofs_y)

        ofs_x, ofs_y = 0, 0

        if offset_lookup:
            ofs_x, ofs_y = offset_lookup[rec.area_id]
#            ic(x, ofs_x, y, ofs_y)

        return (x, y), (ofs_x, ofs_y)

    def pickup_tip_sub(map_item, obj_item):
        """Hover subtitle for a pickup; says where it goes when that is in another area."""
        sub = "Pickup"

        if obj_item.deliver_loc.area_id != map_item.area_id:
            sub += f" → {areas_by_area_id[obj_item.deliver_loc.area_id]}: {obj_item.deliver_loc.name}"

        return sub

    def can_link(deliver_loc, map_item):
        """A pickup can be linked to its delivery location in the same area, or in any area shown in the region view."""
        return deliver_loc.area_id == map_item.area_id or (multi_area and deliver_loc.area_id in offset_lookup)

    def have_db_pos(rec):
        if (pos_rec := override_positions.get(rec.id)):
            return pos_rec[1][0] is not None

        return rec.x is not None


    def get_selected_color(cur_color, id, blocked=False, blocked_color=None):
        color = blocked_color if blocked else cur_color

        if id or selected_ids:
            if not isinstance(id, tuple):
                id = (id,)

#        if (id == selected_ids or (selected_ids in id)):
            if selected_ids.intersection(id):
#            ic("get_selected_color", cur_color, id, selected_ids, blocked)
#                return "mediumorchid" if blocked else "violet"
                return True, color

        return False, color

    cargo_by_pos = defaultdict(list)
    area_id = area_ids_by_area[area]
    ic("gas", area_id, region, area, selected_ids)
    hide_class = element_classes.get("Hide")
    hide_class = (" " + hide_class) if hide_class else ""
    hide_tasks = "Tasks" in hide_types
    hide_contracts = "Contracts" in hide_types
    hide_sources = "Sources" in hide_types
    hide_framing = "Framing" in hide_types
    hide_spawns = "Spawns" in hide_types
    hide_trucks = "Trucks" in hide_types

        # cargo sources
    if not hide_sources or not hide_framing:
        klass = element_classes.get("Sources", "location-source")
        for map_item in await MapItem.filter(Q(area_id=area_id) & (Q(item_type="source") | Q(item_type="craft"))).prefetch_related("cargo_items", "obj_locker"):
#            if 1 or have_db_pos(map_item):
            check_hide = hide_framing if "framing" in map_item.name else hide_sources

            if not check_hide and (show_all or not map_item.completed):
                flt = MapItem.filter(id=map_item.id)
                cargo_items = sorted((make_source_cargo(cargo_item, ccnt) for cargo_item in map_item.cargo_items if (ccnt := current_cargo_count(cargo_item)) != 0), key=lambda c: (c.product if isinstance(c, Recipe) else c).name)
                blocked = (obj_locker := map_item.obj_locker) and not obj_locker.completed
                selected, source_color = get_selected_color("yellow", map_item.id, blocked, "gold")
                desc = abbreviate_line(map_item.name) + (" Craft" if map_item.item_type=="craft" else "")

                if loc_mode:
                    cargo_by_pos[db_pos(map_item)].append(make_location_item(flt, map_item.id, map_item.id, desc, selected, blocked, back=source_color, extra="cargo", classes=klass, lst=cargo_items if detail_in_loc_mode else []))
                else:
                    cargo_by_pos[db_pos(map_item)].append(make_draw_item(flt, map_item.id, map_item.id, "src", desc, cargo_items, selected, blocked, source_color, "blue", map_item.name, classes=klass, tip=("📍", map_item.name, "Crafting site" if map_item.item_type == "craft" else "Source") if cargo_items else None))


        # trucks/trailers on map
    if not hide_trucks or not hide_spawns and loc_mode:
        truck_klass = element_classes.get("Trucks", "location-truck")

        for map_item in await MapItem.filter(Q(area_id=area_id) & (Q(item_type="truck") | Q(item_type="trailer") | Q(item_type="spawn"))) \
                .prefetch_related("obj_items__objective__obj_prereqs__prereq_obj", "obj_items__deliver_loc", "obj_locker", "cargo_items"):
            is_spawn = map_item.item_type == "spawn"

            if ((hide_spawns or not loc_mode) if is_spawn else hide_trucks):
                continue

            rec = None
            flt = MapItem.filter(id=map_item.id)
                # is part of an objective
            if show_all or not map_item.completed:
                desc = abbreviate_line(map_item.name)
                cargo_items = sorted((CargoStack(cargo_item.name, ccnt, ">" + counted_cargo_none(ccnt, abbreviate_line(cargo_item.name) + "<"), loaded=True) for cargo_item in map_item.cargo_items if (ccnt := current_cargo_count(cargo_item)) != 0), key=lambda c: c.name)

                if map_item.obj_items and (obj_item := map_item.obj_items[0]):
                    if not show_all and (obj_item.completed or obj_item.objective.completed):
                        continue

                    cur_task = abbreviate_line(obj_item.objective.name)
                    is_task = obj_item.objective.obj_type == "task"
                    klass = truck_klass
                    blocked = any(not prereq.prereq_obj.completed for prereq in obj_item.objective.obj_prereqs)
#                ic(map_item.name, obj_item.objective_id, obj_item.id)
                    selected, back_color = get_selected_color("greenyellow", (obj_item.objective_id, obj_item.id), blocked, "limegreen")

                    if loc_mode:
                        rec = make_location_item(flt, map_item.id, obj_item.id, desc, selected, blocked, back=back_color, fore="blue", extra="pickup", lst=[cur_task] + (cargo_items  if detail_in_loc_mode else []), classes=klass)
                    else:
                        arrow = None

                        if can_link(obj_item.deliver_loc, map_item):
                            if not (hide_tasks if is_task else hide_contracts):
                                arrow = db_pos(obj_item.deliver_loc)

                            cargo_list = [vehicle_stack(map_item.name, desc)] + cargo_items
                        else:
                            cargo_list = [vehicle_stack(map_item.name, desc)] + cargo_items

                        rec = make_draw_item(flt, map_item.id, obj_item.id, "pickup", cur_task, cargo_list, selected, blocked, back_color, "blue", None, classes=klass, arrow=arrow, tip=("🚚", obj_item.objective.name, pickup_tip_sub(map_item, obj_item)))
                elif not is_spawn:
                    blocked = (obj_locker := map_item.obj_locker) and not obj_locker.completed
                    selected, back_color = get_selected_color("mediumpurple", map_item.id, blocked, "darkslateblue")
                    if loc_mode:
                        tip = None
                    else:
                        vehicle = vehicle_stack(map_item.name, desc)
                        cargo_items = [vehicle] + cargo_items
                        tip = (vehicle.icon, map_item.name, vehicle.tip_sub)

                    rec = make_draw_item(flt, map_item.id, map_item.id, "loc" if loc_mode else "truck", desc, cargo_items, selected, blocked, back=back_color, extra="truck", classes=truck_klass, tip=tip)
#                    if map_item.id == "US_09_01|scout_trailer_oiltank|6":
#                        ic(rec)

            if rec:
                cargo_by_pos[db_pos(map_item)].append(rec)

            # handle spawns separately than trucks as there can be multiple at same position in which case we want to combine them, but only when not in loc_mode
        if not loc_mode and not hide_spawns:
            for (x, y, name, o_id), map_items in itertools.groupby(await MapItem.filter(Q(area_id=area_id) & Q(item_type="spawn")) \
                    .prefetch_related("obj_items__objective__obj_prereqs__prereq_obj", "obj_items__deliver_loc")
                    .order_by("x", "y", "name"), lambda mi: (mi.x, mi.y, mi.name, (mi_oi := mi.obj_items) and mi_oi[0].objective_id)):
                map_items = list(map_item for map_item in map_items if show_all or not map_item.completed)
                flt = MapItem.filter(id__in=[map_item.id for map_item in map_items])
                    # is part of an objective

                if map_items:
                    map_item = map_items[0]
                    desc = abbreviate_line(map_item.name)

                    if map_item.obj_items and (obj_item := map_item.obj_items[0]):
                        if not show_all and (obj_item.completed or obj_item.objective.completed):
                            continue

                        cur_task = abbreviate_line(obj_item.objective.name)
                        is_task = obj_item.objective.obj_type == "task"
                        klass = truck_klass
                        blocked = any(not prereq.prereq_obj.completed for prereq in obj_item.objective.obj_prereqs)
    #                ic(map_item.name, obj_item.objective_id, obj_item.id)
                        selected, back_color = get_selected_color("greenyellow", (obj_item.objective_id, obj_item.id), blocked, "limegreen")

                        if loc_mode:
                            rec = make_location_item(flt, map_item.id, obj_item.id, desc, selected, blocked, back=back_color, fore="blue", extra="pickup", lst=[cur_task], classes=klass)
                        else:
                            arrow = None

                            if can_link(obj_item.deliver_loc, map_item):
                                if not (hide_tasks if is_task else hide_contracts):
                                    arrow = db_pos(obj_item.deliver_loc)

                                spawn_stack = CargoStack(map_item.name, len(map_items), counted_cargo(len(map_items), desc)) # a spawn is the cargo itself
                                cargo_list = [spawn_stack]
                            else:
                                cargo_list = [CargoStack(map_item.name, len(map_items), desc)]

                            rec = make_draw_item(flt, map_item.id, obj_item.id, "pickup", cur_task, cargo_list, selected, blocked, back_color, "blue", None, classes=klass, arrow=arrow, tip=("🚚", obj_item.objective.name, pickup_tip_sub(map_item, obj_item)))
                            cargo_by_pos[db_pos(map_item)].append(rec)

        # read deliveries for region and add to list
        # deliveries are ObjectiveItem records with optional MapItem "truck/trailer" records
#    filtered_obj_items = ObjectiveItem.filter(area_id=area_id).prefetch_related("map_item", "deliver_loc")

    task_klass = element_classes.get("Tasks", "location-task")
    contract_klass = element_classes.get("Contracts", "location-contract")

    for objective in await Objective.filter(obj_items__deliver_loc__area_id=area_id) \
            .prefetch_related("obj_items__deliver_loc", "obj_items__map_item", "obj_prereqs__prereq_obj") \
            .order_by("obj_items__stage", "obj_items__name").distinct():
        abbr_task = abbreviate_line(objective.name)
        is_task = objective.obj_type == "task"

        if hide_tasks if is_task else hide_contracts:
            continue

        klass = task_klass if is_task else contract_klass

        if not show_all and objective.completed:
            continue

        filtered_obj_items = [oj for oj in objective.obj_items if oj.deliver_loc.area_id == area_id] # this extra trickiness is needed because first filter just gets the objective, which could have items in other areas too
        next_stage_blocked = False

            # if more than one cargo from task is in same location, join them together instead of separate boxes (unless in different stages)
        for stage, stage_obj_items in itertools.groupby(filtered_obj_items, lambda r: r.stage):
            stage_blocked = next_stage_blocked

            for _, obj_items in itertools.groupby(stage_obj_items, lambda oi: oi.deliver_loc_id if loc_mode else (oi.deliver_loc.x, oi.deliver_loc.y)):
                cargo_list = []
                from_notes = [] # where cargo is coming from when that is another area, shown on hover
                obj_items = list(obj_items)
                blocked = stage_blocked or any(not prereq.prereq_obj.completed for prereq in objective.obj_prereqs)

                if loc_mode and not detail_in_loc_mode:
                    obj_item = obj_items[0]
                else:
                    for obj_item in obj_items:
                        if not blocked and not obj_item.completed:
                            next_stage_blocked = True

                        if (not obj_item.map_item or obj_item.map_item.item_type != "spawn") and (show_all or not obj_item.completed):
                            cargo_text = counted_cargo(obj_item.count, abbreviate_line(obj_item.name))
                            is_vehicle = obj_item.item_type in ("truck", "trailer")
                            cargo_label = vehicle_stack(obj_item.name, cargo_text, kind=obj_item.item_type) if is_vehicle else CargoStack(obj_item.name, obj_item.count, cargo_text)
                            cargo_labels = [cargo_label]

                                # extra info if between 2 areas
                            if obj_item.map_item and obj_item.map_item.area_id != obj_item.deliver_loc.area_id:
                                from_notes.append(f"{obj_item.name} from {get_compass_repr_of_pos_int((obj_item.map_item.x, obj_item.map_item.y))} {areas_by_area_id[obj_item.map_item.area_id]}")

                            cargo_list.append((obj_item.stage or -1, abbreviate_line(obj_item.name), cargo_labels))

                    # this is the deliveries
                if cargo_list or loc_mode and obj_item:
                    selected, back_color = get_selected_color("white", tuple(obj_item.id for obj_item in obj_items) + (objective.id,), blocked, "lightgrey")
#                ic(cargo_list)
#                ic(sorted(cargo_list, key=itemgetter(0)))
                    cargo_list = sorted(cargo_list, key=itemgetter(0, 1))
                    cargo_list = list(flatten(map(itemgetter(2), cargo_list))) # pull out actual values after sorting
                    deliver_loc_id = obj_item.deliver_loc_id
                    dst_list = cargo_by_pos[db_pos(obj_item.deliver_loc)]
                    ids = await MapItem.filter(obj_item_deliveries__deliver_loc_id=deliver_loc_id).distinct().values_list("id", flat=True)
                    flt = MapItem.filter(id__in=ids)

                    if loc_mode:
                        # when editing we show position then task, if more than one task in same position then join them instead of creating a new entry
                        dst_list.append(make_location_item(flt, deliver_loc_id, deliver_loc_id, obj_item.deliver_loc.name, selected, blocked, back=back_color, fore="green", extra="dst", lst = [abbr_task] + cargo_list if detail_in_loc_mode else [abbr_task], classes=klass))
                    else:
                        dst_list.append(make_draw_item(flt, deliver_loc_id, deliver_loc_id, "dst", abbr_task, cargo_list, selected, blocked, back_color, "green", obj_item.deliver_loc.name, classes=klass, tip=("📍", obj_item.deliver_loc.name, "; ".join(["Objective: " + objective.name] + from_notes))))


    gate_lines = []

        # gates
    if "Gates" not in hide_types:
        klass = element_classes.get("Gates", "location-gate")

        for map_item in await MapItem.filter(area_id=area_id, item_type="gate").prefetch_related("obj_locker"):
            if have_db_pos(map_item):
                gate_color = "teal" if (obj_locker := map_item.obj_locker) and not obj_locker.completed else "mediumturquoise"
                map_item_dest = await MapItem.filter(id=map_item.to_map_item_id).first()
                gate_dest = ((get_compass_repr_of_pos_int((map_item_dest.x, map_item_dest.y)) + " ") if map_item_dest else "") + abbreviations_by_area_id[map_item.to_area_id]
                cargo_by_pos[db_pos(map_item)].append(make_draw_item(MapItem.filter(id=map_item.id), map_item.id, map_item.id, "loc" if loc_mode else "gate", "Gate", [gate_dest], False, False, back=gate_color, extra="gate", classes=klass))

                if map_item_dest and (multi_area or map_item_dest.area_id == map_item.area_id):
                    gate_lines.append(tuple(sorted((db_pos(map_item), db_pos(map_item_dest)))))



    return cargo_by_pos, gate_lines

def add_svg_image(parent, img_path=None, map_id = "map_svg_image", size=main_scale, x_ofs=0, y_ofs=0, link=False):
    ig = draw.Group(id=map_id + "_group")

    if img_path:
        if link:
            ig.append(draw.Image(0, 0, size, size, img_path, embed=False, id=map_id))
#            ig.append(draw.Image(0, 0, size, size, img_path, embed=False, pointer_events="none", id=map_id))
        else:
#            ig.append(draw.Image(0, 0, size, size, img_path, embed=False, id=map_id))
            ig.append(draw.Image(0, 0, size, size, img_path, embed=False, pointer_events="none", id=map_id))

    parent.append(draw.Use(ig, x_ofs, y_ofs))


async def render_area_svg_objects(d, objects, id_gen, guides=False, fix_overlaps=False, size=main_scale, text_height = 8, loc_mode = False,
        location_items=None, group_rectangles=True,
        map_id = "map_svg_image", x_ofs=0, y_ofs=0, overall_group=None, desc=None, bounds=None):
    multi_area = overall_group is not None
    cargo_by_pos, gate_lines = objects

    text_v_margin = text_height / 4
    text_h_margin = text_height / 2
    quarter_height = text_height / 4
    half_height = text_height / 2
    eight_height = text_height / 8
#    text_h_margin = text_height
    W, H = size, size
    half = size / 2
    scale = size
    scale_tuple = (scale, scale)

    def scaled_pos(pos, ofs):
        if ofs is None:
#            ic(pos, "ofs is None!")
            ofs = 0, 0

        if pos is None or pos[0] is None:
            if loc_mode:
                pos = (W + W // 20, H//2)
            else:
                pos = (W // 2, H // 2)

        if size == 1000:
            return pos

        scale_pos = (arithtuple(pos) * scale_tuple) // 1000 + ofs
#        scale_pos = add_tuple(true_divide_scalar_tuple(multiply_scalar_tuple(pos, scale), 1000), ofs)
#        ic(pos, ofs, scale_tuple, scale_pos)
#        ic(size, pos, scale_pos)
        return scale_pos


    ##########
    # Drawing
    ##########

    eg = draw.Group(id="everything")
#    eg = draw.Group(id=map_id + "everything")
    overall_group = overall_group or eg

    d.append(draw.Use(eg, x_ofs, y_ofs))

        # cargo icons need their own hover, which elements inside a <use> can't get, so they live in plain inline groups
    if multi_area:
        overlay_parent = overall_group
    else:
        overlay_parent = draw.Group(transform=f"translate({x_ofs} {y_ofs})") if x_ofs or y_ofs else draw.Group()
        d.append(overlay_parent)
#
#    if x_ofs or y_ofs:
#        d.append(draw.Use(ig, x_ofs, y_ofs))
#        d.append(draw.Use(eg, x_ofs, y_ofs))
#    else:
#        d.append(ig)
#        d.append(eg)

    if guides:
        tenth = size / 10

        for n in range(1, 10):
            pos = tenth * n
            color = "orange" if n == 5 else "red"
            d.append(draw.Line(0, pos, W, pos, stroke=color))
            d.append(draw.Line(pos, 0, pos, H, stroke=color))

    rectangles = []
    grouped_rectangles = []
    rects_and_objects = []
    dots = []
    inset= 15
    diag_overlap = 0


    def entry_height(entry):
        no_cargo = int(not entry.cargo_items)
        return text_height * len(entry_title_lines(entry)) + layout_cargo(entry.cargo_items, text_height)[2] + text_v_margin + no_cargo * quarter_height

    overlay_groups = [] # drawn after everything else so they stay on top
    overlays = {} # group id -> (css class, elements) drawn above all entries, in the group's coordinates, so they can have their own hover


    for src, dst in gate_lines:
        xf, yf = scaled_pos(*src)
        xt, yt = scaled_pos(*dst)
        overall_group.append(draw.Line(xf, yf, xt, yt, stroke="mediumturquoise", stroke_width=3))

        # plot cargo and deliveries
    for (pos, ofs), lst in cargo_by_pos.items():
        grouped_rect = None

        if ofs is None:
            print("ofs is None!")
            ic(pos, lst)

        scale_pos = scaled_pos(pos, ofs)
            # position all items at same location one above one another, vertically centered
        th = sum(map(entry_height, lst))
        y_map = first_y = -th // 2

#        if th < H:
#            y_map = min(H-th-scale_pos[1]-inset, max(-scale_pos[1]+inset, first_y))

        for entry in sorted(lst, key=lambda e: (precedence.get(e.typ, 100), e.disp_name)):
            id = "id" + str(next(id_gen))
            c = entry.typ
            no_cargo = int(not entry.cargo_items)

            if entry.classes:
                c += " " + entry.classes

#            g = draw.Group(id=id, class_=c, mask=drag_mask)
#            g = draw.Group(id=id, class_=c, mask=drag_mask if loc_mode else None)
            g = draw.Group(id=id, class_=c)
            h = entry_height(entry)
            pre_x = x = -entry.width // 2
            y = -h // 2
            rec = None

            if 0:
                hlink = Hyperlink('https://www.python.org', target='_blank')
                hlink.append(g)
                g = hlink

#            if pos[0] is not None: # don't fix x out of bounds if we haven't assigned locations, this makes it currently on right side outside visible map
#                x = min(W - entry.width - scale_pos[0] - inset, max(-scale_pos[0] + inset, x))

            map_pos_x, map_pos_y = scale_pos[0] + x, scale_pos[1] + y_map

            if location_items is not None:
#                rec = location_items[id] = DrawRec(*(entry + (id, [map_pos_x, map_pos_y])))
                rec = location_items[id] = DrawRec(*(entry + (id, list(scale_pos), [scale_pos[0] + x - pre_x, scale_pos[1] + y_map - y])))

            if entry.selected:
                g.append(draw.Rectangle(x, y, entry.width, h, rx=ENTRY_CORNER_RADIUS, fill=entry.back, stroke='hotpink', stroke_width=4))
            else:
                g.append(draw.Rectangle(x, y, entry.width, h, rx=ENTRY_CORNER_RADIUS, fill=entry.back, stroke='black',))

            tx, ty = x + text_h_margin, y + text_v_margin
            title_lines = entry_title_lines(entry)

            for n, title_line in enumerate(title_lines):
                g.append(draw.Text(title_line, text_height, tx, ty + no_cargo * eight_height + text_height * n, fill='black', font_weight='bold', dominant_baseline="hanging"))

            placements = layout_cargo(entry.cargo_items, text_height)[0]
            cargo_y = ty + text_height * len(title_lines)
            sq = cargo_icon_size(text_height)
            overlay_elements = []

            if entry.tip and not loc_mode: # full objective / delivery location names are only shown on hover; transparent rect catches the mouse
                tip_icon, tip_title, tip_sub = entry.tip
                overlay_elements.append(draw.Rectangle(x, y, entry.width, h, rx=ENTRY_CORNER_RADIUS, fill="black", fill_opacity=0, pointer_events="all", data_tip_icon=tip_icon, data_tip_title=tip_title, data_tip_sub=tip_sub))

            for placement in placements:
                if placement[0] == "text":
                    _, t, py = placement
                    g.append(draw.Text(t, text_height, tx, cargo_y + py, fill=entry.fore, dominant_baseline="hanging"))
                elif placement[0] == "arrow":
                    _, px, py, aw = placement
                    g.append(draw.Text("←", sq * 0.7, tx + px + aw / 2, cargo_y + py + sq / 2, text_anchor="middle", dominant_baseline="central", font_weight="bold", fill="black"))
                else:
                    _, stack, px, py = placement
                    sx, sy = tx + px, cargo_y + py
                    sg = draw.Group(data_tip_icon=stack.icon, data_tip_title=stack.name, data_tip_sub=stack.tip_sub)
                    sw = stack.width_factor * sq
                    sg.append(draw.Rectangle(sx, sy, sw, sq, rx=3, fill=stack.fill, fill_opacity=0.9, stroke=stack.border[0], stroke_width=stack.border[1]))

                    sg.append(draw.Text(stack.icon, sq * 0.6, sx + sw / 2, sy + sq * 0.42, text_anchor="middle", dominant_baseline="central")) # one text so a trailer's two emoji touch

                    stack.count_text and sg.append(draw.Text(stack.count_text, text_height * 0.9, sx + sw - 1, sy + sq - 1, text_anchor="end", font_weight="bold", fill="black", stroke="white", stroke_width=2, paint_order="stroke"))
                    overlay_elements.append(sg)

            if overlay_elements:
                overlays[id] = (c, overlay_elements)

            rect = Rectangle(map_pos_x, map_pos_y, entry.width, h - 1) # slightly decrease the height because overlapping one pixel on borders is A-OK
            rect.fixed = entry.typ == "gate" # gates must stay at their real location
            rectangles.append(rect)

            if grouped_rect:
                grouped_rect.combine(rect)
            else:
                grouped_rect = Rectangle(rect.left, rect.top, rect.width, rect.height)
                grouped_rect.fixed = rect.fixed
                grouped_rectangles.append(grouped_rect)

            rects_and_objects.append((entry, rect, grouped_rect, g, scale_pos, (x, y), rec))

            if loc_mode:
                g.append(draw.Circle(0, 0, quarter_height, fill='purple', stroke_width=1, stroke='black'))

            if (not loc_mode or len(lst) > 1) and entry.typ != "gate":
                dots.append(draw.Circle(scale_pos[0], scale_pos[1], half_height, fill='purple', stroke_width=1, stroke='black', class_="location-dot"))

            y_map += h

#    ic(area_id)
    if fix_overlaps:
#        ic("correcting", area_id)
        with Timer("correcting " + desc):
            hit = correct_rect_overlaps_cached(grouped_rectangles if group_rectangles else rectangles, *(bounds or (W, H)), group_key=group_rectangles)
            ic(hit)
#        ic("done correcting", area_id)

        # separate loop to draw underneath rectangles
    links = [] # (delivery x, delivery y, pickup x, pickup y)

    for entry, rect, grouped_rect, g, scale_pos, (x, y), rec in rects_and_objects:
        if entry.arrow: # connect vehicles with their destinations
            moved_rect = grouped_rect if group_rectangles else rect
            xf, yf = scaled_pos(*entry.arrow)
            xt, yt = rect.original_midx - moved_rect.deltax, rect.original_midy - moved_rect.deltay
            links.append((xf, yf, xt, yt, entry.selected))

        # each layer is drawn for every link before the next, so a link's casing never covers another link's line
    for width, color, opacity in LINK_CASING_LAYERS:
        for xf, yf, xt, yt, selected in links:
            overall_group.append(draw.Line(xf, yf, xt, yt, stroke=color, stroke_width=width, stroke_opacity=opacity))

    for xf, yf, xt, yt, selected in links:
        overall_group.append(draw.Line(xf, yf, xt, yt, stroke=LINK_SELECTED_COLOR if selected else LINK_COLOR, stroke_width=3))

        # chevrons along the line point from the pickup to the delivery; the ends are covered by the boxes
    for xf, yf, xt, yt, selected in links:
        length = math.hypot(xf - xt, yf - yt)

        if length < 1:
            continue

        ux, uy = (xf - xt) / length, (yf - yt) / length # unit vector pickup -> delivery
        count = max(1, int(length // LINK_ARROW_SPACING))

        for n in range(count):
            d_along = length * (n + 0.5) / count # centered, so a short line gets one arrow in the middle
            cx, cy = xt + ux * d_along, yt + uy * d_along
            half_len, half_wid = LINK_ARROW_LENGTH / 2, LINK_ARROW_WIDTH / 2

            def point(along, across): # position relative to the chevron center; along points toward the delivery
                return cx + ux * along - uy * across, cy + uy * along + ux * across

            points = [point(half_len, 0), point(-half_len, half_wid), point(-half_len + LINK_ARROW_NOTCH, 0), point(-half_len, -half_wid)]
            overall_group.append(draw.Lines(*itertools.chain.from_iterable(points), close=True, fill=LINK_CHEVRON_COLOR, stroke=LINK_CHEVRON_STROKE, stroke_width=1, stroke_linejoin="round"))

    for (grouped_rect, scale_pos), rects_and_objects_bygroup in itertools.groupby(rects_and_objects, itemgetter(2, 4)):
        if group_rectangles:
#                ic(grouped_rect.left, grouped_rect.top, grouped_rect.width, grouped_rect.height, grouped_rect.original_left, grouped_rect.original_top)
#                assert grouped_rect.original_left == grouped_rect.left and grouped_rect.original_top == grouped_rect.top
            if diag_overlap:
                if fix_overlaps:
                    overall_group.append(draw.Rectangle(grouped_rect.original_left, grouped_rect.original_top, grouped_rect.width, grouped_rect.height, fill=None, stroke='red'))

                overall_group.append(draw.Rectangle(grouped_rect.left, grouped_rect.top, grouped_rect.width, grouped_rect.height, fill=None, stroke='yellow'))

        for entry, rect, grouped_rect, g, scale_pos, (x, y), rec in rects_and_objects_bygroup:
            if diag_overlap:
                overall_group.append(draw.Rectangle(rect.left, rect.top, rect.width, rect.height, fill=None, stroke='green'))

            moved_rect = grouped_rect if group_rectangles else rect
            use_left = rect.original_left - moved_rect.deltax
            use_top = rect.original_top - moved_rect.deltay

            if not fix_overlaps:
                assert moved_rect.deltay == moved_rect.deltax == 0

#            ic(entry.disp_name, moved_rect.deltax, moved_rect.deltay)
            id = "id" + str(next(id_gen)) # selection dragging grabs these ids, gsap drag and drop grabs the ids of the groups
                # we want to use from center of group, but can't uise scale_pos directly bc it may be different than what db holds (vertical grouping. moving away from edges)
#            overall_group.append(draw.Use(g, scale_pos[0] - moved_rect.deltax, scale_pos[1] - moved_rect.deltay, id=id, class_="loc2"))
            overall_group.append(draw.Use(g, use_left - x, use_top - y, id=id, class_="loc2"))

            if (overlay := overlays.get(g.args["id"])):
                og = draw.Group(class_=overlay[0], transform=f"translate({use_left - x} {use_top - y})", data_click_id=id) # clicks are forwarded to the entry underneath
                og.extend(overlay[1])
                overlay_groups.append(og)

            if location_items is not None:
                location_items[id] = rec

        # lines to show where an item was before it got moved - draw these last to be on top
    for (grouped_rect, scale_pos), rects_and_objects_bygroup in itertools.groupby(rects_and_objects, itemgetter(2, 4)):
        if group_rectangles and (grouped_rect.deltax or grouped_rect.deltay):
            overall_group.append(draw.Line(scale_pos[0], scale_pos[1], scale_pos[0] - grouped_rect.deltax, scale_pos[1] - grouped_rect.deltay, stroke="purple", stroke_width=2))

    for dot in dots:
        overall_group.append(dot)

    overlay_parent.extend(overlay_groups)

#    if loc_mode:    # selection rectangle
#        eg.append(draw.Rectangle(0, 0, 10, 10, fill="rgba(0,0,255,0.3)", stroke='blue', stroke_width=2, id="selection_rect"))
##            rect = ui.element('rect').props('fill="rgba(0,0,255,0.3)" stroke="blue" stroke-width="2"')

    return d

async def generate_area_svg(region, area, img_path=None, size=main_scale, text_height=11, loc_mode=False, location_items=None, element_classes = {}, hide_types = set(), fix_overlaps=False, show_all=False, selected_ids=None, detail_in_loc_mode=False, override_positions=None):
    d, id_gen = create_drawing(width=size, height=size, text_height=text_height, loc_mode = loc_mode)
    objects = await generate_area_svg_objects(region, area, text_height=text_height, loc_mode = loc_mode, element_classes = element_classes, hide_types = hide_types, show_all=show_all, selected_ids=selected_ids, detail_in_loc_mode=detail_in_loc_mode, override_positions=override_positions)
    add_svg_image(d, img_path, size=size)
    await render_area_svg_objects(d, objects, id_gen, size=size, text_height=text_height, loc_mode = loc_mode, location_items = location_items, fix_overlaps=fix_overlaps, desc=area)
    s = d.as_svg(header="")
#    s = d.as_svg()
    return s

async def calculate_area_offsets_for_region(region, areas, size=main_scale):
    def have_db_pos(rec):
        return rec.x is not None

    def scaled(x):
        return x * half_size // 1000

    async def calc_best_offsets():
        gates = defaultdict(list)

        for map_item in await MapItem.filter(area_id__in=area_ids, item_type="gate").prefetch_related("obj_locker"):
            if have_db_pos(map_item):
                map_item_dest = await MapItem.filter(id=map_item.to_map_item_id).first()

                if map_item_dest:
                    gates[map_item.area_id].append((scaled(map_item.x), scaled(map_item.y), map_item.to_area_id, scaled(map_item_dest.x), scaled(map_item_dest.y)))

        calculated_offsets = set()

        for possible_offsets in itertools.permutations(offsets):
            possible_offsets = possible_offsets[:area_count]

            if 0:
                    # ignore anything that doesn't use either top left or bottom left
                if not any(ofs[0] == 0 for ofs in possible_offsets):
                    continue

                    # also anything that results in an empty column in the middle
                if any(ofs[0] == size for ofs in possible_offsets) and not any(ofs[0] == half_size for ofs in possible_offsets):
                    continue

            cost = 0
            cost_det = []
            gate_positions = []
            offset_lookup = dict(zip(area_ids, possible_offsets))

            for area_id, (possible_offset_x, possible_offset_y) in zip(area_ids, possible_offsets):
                    # distance from each gate to its dest
                for x, y, to_area_id, dest_x, dest_y in gates[area_id]:
                    dest_ofs_x, dest_ofs_y = offset_lookup[to_area_id]
                    cost += (one_cost := int(math.dist(((possible_offset_x + x), (possible_offset_y + y)), ((dest_ofs_x + dest_x), (dest_ofs_y + dest_y)))))
                    cost_det.append(one_cost)
                    gate_positions.append((area_id, possible_offset_x, possible_offset_y, x, y, to_area_id, dest_ofs_x, dest_ofs_y, dest_x, dest_y))

            calculated_offsets.add((cost, possible_offsets, tuple(cost_det), tuple(gate_positions)))

        calculated_offsets = sorted(calculated_offsets)
#        ic(calculated_offsets[:10])
        ic(len(calculated_offsets))
        best_offsets = calculated_offsets[0][1]
        ic(best_offsets)
        return best_offsets[:area_count]

    area_count = len(areas)
    half_size = size//2
    margin = half_size // 10
    half_margin = margin // 2
    sub_size = half_size - margin
#    offsets = list(itertools.product((0, half_size), repeat=2))
    offsets = list(itertools.product((0, half_size, size) if len(areas) > 2 else (0, half_size), (0, half_size)))
#    offsets = list(itertools.product((0, half_size), (0, half_size)))
    ic(len(offsets))
    offsets = sorted(offsets, key=itemgetter(1, 0))
    ic(offsets)
    area_ids = [area_ids_by_area[area] for area in areas]

    # find best offsets (based on how close gates in different areas are)
    best_offsets = await calc_best_offsets()
    return best_offsets, max(best_offsets, key=itemgetter(0))[0] // half_size + 1


#def offsets_ok(ofs):
#    return ofs[0][0] == ofs[0][1] == 0

async def generate_region_svg(region, areas, best_offsets, x_tiles, img_paths, hlinks, size=main_scale, text_height=8, loc_mode=False, location_items=None, element_classes = {}, hide_types = set(), fix_overlaps=False, show_all=False, selected_ids=None, detail_in_loc_mode=False, override_positions={}):
    d, id_gen = create_drawing(width=size // 2 * x_tiles, height=size, text_height=text_height, loc_mode = loc_mode)
    overall_group = draw.Group(id="region_group")
    half_size = size//2
    margin = half_size // 10
    half_margin = margin // 2
    sub_size = half_size - margin
#    offsets = list(itertools.product((0, half_size), repeat=2))
#    x_tuple = tuple(range(3 if len(areas) > 2 else 2))
#    y_tuple = tuple(range(2))
#    offsets = list(itertools.product((0, half_size, size) if len(areas) > 2 else (0, half_size), (0, half_size)))
#    ic(len(offsets))
##    offsets = [(x, y) ]
#    offsets = sorted(offsets, key=itemgetter(1, 0))
#    ic(offsets)
    area_ids = [area_ids_by_area[area] for area in areas]

#    best_offsets = await calculate_area_offsets_for_region(region, areas, size)
    offset_lookup = dict((area_id, (ofs_x+half_margin, ofs_y+margin)) for area_id, (ofs_x, ofs_y) in zip(area_ids, best_offsets))
    ic(offset_lookup)
    svg_vis_togglers = [
        "Contracts",
        "Tasks",
        "Sources",
        "Trucks",
        "Framing",
        "Spawns",
        ]

#    hide_types = set(svg_vis_togglers)
    all_objects, all_gate_lines = dict(), set()
    hlink_groups = []

    for area, img_path, offset, hlink in zip(areas, img_paths, best_offsets, hlinks):
        ic(area, img_path, offset)
        area_id = area_ids_by_area[area]
        hlink_group = Hyperlink(hlink)
        x_ofs, y_ofs = offset_lookup[area_id]
        objects = await generate_area_svg_objects(region, area, text_height=text_height, loc_mode = loc_mode, element_classes = element_classes, hide_types = hide_types, show_all=show_all, selected_ids=selected_ids, detail_in_loc_mode=detail_in_loc_mode, override_positions=override_positions, overall_group=overall_group, offset_lookup=offset_lookup)
        all_objects.update(objects[0])
        all_gate_lines.update(objects[1])
        d.append(hlink_group)
        hlink_groups.append(hlink_group)
        add_svg_image(hlink_group, img_path, map_id = "map_svg_image_"+area_id, size=sub_size, x_ofs=x_ofs, y_ofs=y_ofs, link=True)

#    await render_area_svg_objects(d, (all_objects, all_gate_lines), id_gen, size=sub_size, text_height=text_height, loc_mode = loc_mode, location_items = location_items, fix_overlaps=fix_overlaps, map_id = "map_svg_image_"+area_id, x_ofs=x_ofs, y_ofs=y_ofs,overall_group=overall_group, desc=region)
    await render_area_svg_objects(d, (all_objects, all_gate_lines), id_gen, size=sub_size, text_height=text_height, loc_mode = loc_mode, location_items = location_items, fix_overlaps=fix_overlaps, x_ofs=x_ofs, y_ofs=y_ofs,overall_group=overall_group, desc=region, bounds=(size // 2 * x_tiles, size))
    d.append(overall_group)

        # draw hlink text on top of everything (inter-area lines)
    for area, img_path, offset, hlink, hlink_group in zip(areas, img_paths, best_offsets, hlinks, hlink_groups):
        hlink_group = Hyperlink(hlink)
        hlink_group.append(draw.Text(area, 33, offset[0]+half_margin, offset[1] + text_height, dominant_baseline="hanging"))
        d.append(hlink_group)

    s = d.as_svg(header="")
    return s

async def main(region_filter, area_filter=None, guides=False):
    await Tortoise.init(db_url=snowplanner_db_url, modules={"models": ["database.models"]})
    await Tortoise.generate_schemas()

    ic(region_filter, area_filter)

    for region, recs in itertools.groupby(iterate_region_area(), lambda x: x.region):
        if region_filter and region_filter != region:
            continue

        print(f"Processing region {region}")

        for region_area in recs:
            if area_filter and area_filter != region_area.area:
                continue

            print(f"    Processing area {region_area.area}")
#            img_path=f"{region}_{region_area.area}.png".replace(" ", "%20")
            img_path=f"{slugify_region_area(region_area.region, region_area.abbrev)}_icon.png"
            d, id_gen = create_drawing()
            objects = await generate_area_svg_objects(region, region_area.area)
            add_svg_image(d, img_path, size=size)
            await render_area_svg_objects(d, objects, id_gen, guides=guides, fix_overlaps=False,desc=region_area.area)
            d.save_svg(make_snowrunner_doc_path(f"{region}_{region_area.area}.svg"))
#                d.save_png(os.path.join(snowrunner_doc_dir, f"{region}_{area}.png"))


if __name__ == "__main__":
    "Cargo list taken from www.maprunner.info"
    parser = argparse.ArgumentParser(description="Parse available cargo and deliveries, and generate an svg that shows both as a map")
    add_region_area_args(parser)
    parser.add_argument('-g', '--guides', action='store_true', help='show grid and center points')
    args = parser.parse_args()

    run_async(main(args.region, args.area, args.guides))


