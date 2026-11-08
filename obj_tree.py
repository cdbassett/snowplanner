"""Objective tree helpers: building the tree data, selecting / scrolling nodes and applying ticks."""
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

class __TREE_FUNCTIONS__: pass

top_level_nodes = ["contracts", "tasks", "trucks", "sources", "gates"]

def select_single_top_tree_node(obj_tree, id):
    for node in top_level_nodes:
        if id != node:
            obj_tree.collapse([node])

    obj_tree.expand([id])

def hidden_by_filter(obj_tree, node_id):
    """True if the tree's text filter currently hides the node (neither it nor any of its children match)."""
    flt = (obj_tree.filter or "").casefold()

    if not flt:
        return False

    def find(nodes):
        for node in nodes:
            if node["id"] == node_id:
                return node

            if (found := find(node.get("children", []))):
                return found

    def matches(node):
        return flt in node["label"].casefold() or any(matches(child) for child in node.get("children", []))

    node = find(obj_tree.props["nodes"])
    return bool(node) and not matches(node)

def scroll_to_node(node_id):
    # Scroll into view via JavaScript
    # Note: Requires selecting the correct DOM node using the node ID
    # The tree re-lays out after collapse/expand (and the node may not be rendered yet), so retry
    # a few times with instant scrolling; smooth scrolling gets cut short by the shifting layout.
    ui.run_javascript(f'''
        var tries = 0;
        var timer = setInterval(function() {{
            // Quasar's QTree puts no data-id on its nodes, so fall back to the selected node's header.
            var node = document.querySelector('[data-id="{node_id}"]') || document.querySelector('.q-tree__node--selected');
            if (node) {{
                node.scrollIntoView({{behavior: "instant", block: "center"}});
            }}
            if (++tries >= 8) {{
                clearInterval(timer);
            }}
        }}, 100);
    ''')

def setup_obj_tree(obj_tree):
    obj_tree.props("selected-color=purple")
        # styling for blocked objectives
    obj_tree.add_slot('header-blocked', '''
        <span :props="props" style="color:darkred;"><strong>{{ props.node.label }}</strong></span>
    ''')
    obj_tree.add_slot('header-completed', '''
        <span :props="props" style="text-decoration:line-through;">{{ props.node.label }}</span>
    ''')
    obj_tree.add_slot('header-disabled', '''
        <span :props="props" style="color:gray;font-style:italic">{{ props.node.label }}</span>
    ''')
    obj_tree.add_slot('header-location', '''
        <span :props="props" style="color:blue;"><strong>{{ props.node.label }}</strong></span>
    ''')
    obj_tree.add_slot('header-reward', '''
        <span :props="props" style="color:green;"><strong>{{ props.node.label }}</strong></span>
    ''')
    obj_tree.add_slot('header-objective', '''
        <span :props="props" style="color:green;"><strong>{{ props.node.label }}</strong></span>
    ''')
    obj_tree.add_slot('header-prereq', '''
        <span :props="props" style="color:red;"><strong>{{ props.node.label }}</strong></span>
    ''')
#            <div :props="props">{{ props.node.description }}</div>
    obj_tree.add_slot('default-body', '''
        <div :props="props" v-html="props.node.description ? props.node.description.replace(/\\n/g, '<br>') : ''"></div>
    ''')


def nfmt(n):
    return f"{n:,}"

reward_map_items = {
    "truck": "Truck",
    "source": "Location",
    }

async def build_obj_tree_data_base(region_area_ids, all_objs, completed_objs, cur_area_id=None):
    def get_area_desc(desc, area_id):
        return desc if area_id == cur_area_id else f"{desc} ({area_infos_by_area_id[area_id].abbrev})"

    def build_map_item(map_item, prefix, pr_prefix, obj_item = None):
        m_id = prefix + map_item.id
        should_tick = map_item.completed
        prereq_obj = map_item.obj_locker
        map_item_name = get_area_desc(map_item.name + (" Craft" if map_item.item_type=="craft" else ""), map_item.area_id)

        if obj_item:
            map_item_name = map_item_name + "->" + get_area_desc(obj_item.deliver_loc.name, obj_item.deliver_loc.area_id)

        node = {"id": m_id, "label": map_item_name}

        if map_item.item_type in ("source", "craft") and not any(cargo_item.initial_cnt is not None for cargo_item in map_item.cargo_items):
            node["noTick"] = True

        cargo_children = node["children"] = []

#            if objective:
        if obj_item:
            objective = obj_item.objective
            should_tick = should_tick or objective.completed or obj_item.completed

            if not prereq_obj or prereq_obj.id != objective.id:
                truck_objective_id = "TO_" + "|".join((map_item.id, objective.id))
                truck_objective_node = {"id": truck_objective_id, "label": get_area_desc(objective.name, objective.area_id), "header": "objective", "noTick": True}
                cargo_children.append(truck_objective_node)

        if should_tick:
            if not completed_objs:
                return None

            ticked.append(m_id)

        ids.append(m_id)

        if map_item.cargo_items or prereq_obj:
            if prereq_obj and not prereq_obj.completed:
                prereq_id = pr_prefix + "|".join((map_item.id, prereq_obj.id))
                prereq_node = {"id": prereq_id, "label": get_area_desc(prereq_obj.name, prereq_obj.area_id), "header": "prereq", "noTick": True}
                cargo_children.append(prereq_node)

            for cargo_item in map_item.cargo_items:
                c_id = "C_" + str(cargo_item.id)
                ids.append(c_id)
                ccnt = current_cargo_count(cargo_item)

                if cargo_item.initial_cnt and not ccnt:
                    ticked.append(c_id)

                c_node = {"id": c_id, "label": counted_cargo_none(ccnt, cargo_item.name), "noTick": not cargo_item.initial_cnt}

                if cargo_item.craft_desc:
                    c_node["description"] = cargo_item.craft_desc

                cargo_children.append(c_node)

        return node


#        all_objs = False

    tree_nodes = [{ "id": id, "label": id.title(), "children": list(), "noTick": True } for id in top_level_nodes]
    contract_children, task_children,  truck_children, source_children, gate_children = map(itemgetter("children"), tree_nodes)
    ticked, expanded = [], []
    ids = [] # no point in keeping a dict, the list of nodes in actual widget is different (unless we wanted to replace entire content again)
        # we need to also show objectives that start here or are delivering here, so just grag the ids

        # objectives
    if all_objs:
        obj_ids = await Objective.filter(area_id__in=region_area_ids).values_list("id", flat=True)
    else:
        obj_ids = await Objective.all().prefetch_related("obj_items__deliver_loc", "obj_items__map_item", "map_items_locked_by") \
            .filter(Q(area_id=cur_area_id) | Q(obj_items__deliver_loc__area_id=cur_area_id) | Q(obj_items__map_item__area_id=cur_area_id) | Q(map_items_locked_by__area_id=cur_area_id)) \
            .distinct().values_list("id", flat=True)

    for objective in await Objective.filter(id__in=obj_ids).prefetch_related("obj_items__deliver_loc", "obj_items__map_item", "obj_prereqs__prereq_obj", "map_items_locked_by").order_by("name"):
        o_id = "O_" + objective.id

        if objective.completed:
            if completed_objs:
                ticked.append(o_id)
            else:
                continue

        children = task_children if objective.obj_type == "task" else contract_children
        ids.append(o_id)
        obj_node = {"id": o_id, "label": get_area_desc(objective.name, objective.area_id)} # can probably also have: body, icon, classes, iconColor
        children.append(obj_node)
        obj_children = obj_node["children"] = []

        for prereq in objective.obj_prereqs:
            if not (prereq_obj := prereq.prereq_obj).completed:
                prereq_id = "PR_" + "|".join((objective.id, prereq_obj.id))
                prereq_node = {"id": prereq_id, "label": get_area_desc(prereq_obj.name, prereq_obj.area_id), "header": "prereq", "noTick": True}
                obj_children.append(prereq_node)

        for reward in objective.map_items_locked_by:
            reward_id = "R_" + "|".join((objective.id, reward.id))
            reward_node = {"id": reward_id, "label": reward_map_items.get(reward.item_type, reward.item_type.title()) + ": " + get_area_desc(reward.name, reward.area_id), "header": "reward", "noTick": True}
            obj_children.append(reward_node)

        reward_desc = "  ".join(f"{p}{f(s)}" for p, s, f in zip(("$", "XP: ", ""), (objective.reward_money, objective.reward_exp, objective.reward_item), (nfmt, nfmt, str)) if s)

        if reward_desc:
            reward_id = "R_" + objective.id
            reward_node = {"id": reward_id, "label": reward_desc, "header": "reward", "noTick": True}
            obj_children.append(reward_node)

#            descriptions = []
#            if objective.obj_prereqs and not objective.completed:
#                descriptions.extend(get_area_desc(prereq.prereq_obj.name, prereq.prereq_obj.area_id) for prereq in objective.obj_prereqs)
#
#            if objective.map_items_locked_by:
#                descriptions.extend(get_area_desc(map_item_locked_by.name, map_item_locked_by.area_id) for map_item_locked_by in objective.map_items_locked_by)
#
#            if descriptions:
#                obj_node["description"] = "\n".join(descriptions)

            # special formatting to indicate objective is blocked by other incomplete objectives
        if (is_blocked := any(not prereq.prereq_obj.completed for prereq in objective.obj_prereqs)):
            obj_node["header"] = "blocked"
        elif objective.completed:
            obj_node["header"] = "completed"

        if objective.obj_items:
            items_by_location = [(loc_name, list(loc_items)) for loc_name, loc_items in itertools.groupby(sorted(objective.obj_items, key=obj_item_stage_loc_key), obj_item_loc_key)]
            multi_stages, blocked_stages = determine_stage_blocking(objective.obj_items, objective.obj_prereqs)

            for loc_name, loc_items in items_by_location:
                loc_id = "L_" + loc_name
                loc_node = {"id": loc_id, "label": get_area_desc(loc_name, loc_items[0].deliver_loc.area_id), "header": "location", "noTick": True}
                ids.append(loc_id)
                obj_children.append(loc_node)
#                    oi_children = add_obj_items(loc_items)
                oi_children = []
                expanded.append(loc_id)

                for stage, stage_obj_items in itertools.groupby(loc_items, obj_item_stage_key):
                    stage_blocked = stage in blocked_stages

                    if multi_stages:
                        oi_children.append({"id": "OST_" + o_id +"_"+str(stage), "label": f"-  stage {stage+1}  -", "noTick": True})

                    for obj_item in stage_obj_items:
                        oi_id = "OI_" + str(obj_item.id)
                        obj_item_name = obj_item.name
                        if obj_item.map_item: obj_item_name = "*" + get_area_desc(obj_item_name, obj_item.map_item.area_id)
                        oi_node = {"id": oi_id, "label": counted_cargo(obj_item.count, obj_item_name)}
                        ids.append(oi_id)

                        if stage_blocked:
                            oi_node["header"] = "disabled"

                        if obj_item.completed:
                            ticked.append(oi_id)

                        oi_children.append(oi_node)

                if 1:
                    loc_node["children"] = oi_children
                else:
                    obj_children.extend(oi_children)

        if obj_children:
            obj_node["children"] = obj_children

    base_map_filter = Q(area_id__in=region_area_ids) if all_objs else Q(area_id=cur_area_id)

        # trucks
    for map_item in await MapItem.filter(base_map_filter & (Q(item_type="truck") | Q(item_type="trailer"))).prefetch_related("obj_items__objective", "cargo_items", "obj_locker", "obj_items__deliver_loc").order_by("name"):
#            objective = map_item.obj_items[0].objective if map_item.obj_items else None
#            node = build_map_item(map_item, "T_", "TPR_", objective)
        obj_item = map_item.obj_items[0] if map_item.obj_items else None

        if (node := build_map_item(map_item, "T_", "TPR_", obj_item)):
            truck_children.append(node)

        # sources
    for map_item in await MapItem.filter(base_map_filter & (Q(item_type="source") | Q(item_type="craft"))).prefetch_related("cargo_items", "obj_locker").order_by("name"):
        if (node := build_map_item(map_item, "S_", "SPR_")):
            source_children.append(node)

        # gates
    for map_item in await MapItem.filter(base_map_filter & Q(item_type="gate")).prefetch_related("obj_locker").order_by("name"):
        g_id = "G_" + map_item.id
        label = get_area_desc(map_item.name, map_item.area_id)

        if map_item.to_area_id in area_infos_by_area_id:
            label += " -> " + area_infos_by_area_id[map_item.to_area_id].abbrev

        gate_node = {"id": g_id, "label": label, "noTick": True, "children": []}

        if (prereq_obj := map_item.obj_locker) and not prereq_obj.completed:
            gate_node["header"] = "blocked"
            gate_node["children"].append({"id": "GPR_" + "|".join((map_item.id, prereq_obj.id)), "label": get_area_desc(prereq_obj.name, prereq_obj.area_id), "header": "prereq", "noTick": True})

        ids.append(g_id)
        gate_children.append(gate_node)

    return tree_nodes, ticked, ids, expanded

def get_actual_ids(ticked_ids, unticked_ids, prefix):
        filtered_ticked_ids = [id.split("_", 1)[1] for id in ticked_ids if id.startswith(prefix)]
        filtered_unticked_ids = [id.split("_", 1)[1] for id in unticked_ids if id.startswith(prefix)]
        return filtered_ticked_ids, filtered_unticked_ids

async def get_cargo_highlight_ids(area_ids, cargo_item_name, only_incomplete):
    cargo_highlight_ids = []
    completed_filter = (Q(completed=False) | Q(completed=None)) if only_incomplete else Q()
    cargo_highlight_ids.extend(await MapItem.filter(Q(area_id__in=area_ids) & completed_filter).prefetch_related("cargo_items").filter(Q(cargo_items__name__icontains=cargo_item_name) & (Q(cargo_items__current_cnt=None) | Q(cargo_items__current_cnt__gt=0))).values_list("id", flat=True))
    cargo_highlight_ids.extend(await ObjectiveItem.filter(Q(name__icontains=cargo_item_name) & completed_filter).prefetch_related("deliver_loc").filter(deliver_loc__area_id__in=area_ids).values_list("id", flat=True))
    return ic(cargo_highlight_ids)

async def update_completed(ticked_ids, unticked_ids, model):
    ic("update_completed", model, len(ticked_ids), len(unticked_ids))

    if ticked_ids:
        ic(await model.filter(id__in=ticked_ids, completed=False).values_list("id", flat=True))
        await model.filter(id__in=ticked_ids, completed=False).update(completed=True)

    if unticked_ids:
        ic(await model.filter(id__in=unticked_ids, completed=True).values_list("id", flat=True))
        await model.filter(id__in=unticked_ids, completed=True).update(completed=False)


async def apply_tree_ticks(ticked_ids, unticked_ids):
    """Write the completed state of the ticked / unticked objective tree nodes to the DB."""
    ticked_o_ids, unticked_o_ids = get_actual_ids(ticked_ids, unticked_ids, "O_")
    #    ic(ticked_o_ids)
    await update_completed(ticked_o_ids, unticked_o_ids, Objective)

    ticked_oi_ids, unticked_oi_ids = get_actual_ids(ticked_ids, unticked_ids, "OI_")
    await update_completed(ticked_oi_ids, unticked_oi_ids, ObjectiveItem)

    ticked_t_ids, unticked_t_ids = get_actual_ids(ticked_ids, unticked_ids, "T_")
    ticked_s_ids, unticked_s_ids = get_actual_ids(ticked_ids, unticked_ids, "S_")
    await MapItem.filter(completed__isnull=True).update(completed=False) # special handling for null values, otherwise following queries don't work
    await update_completed(ticked_t_ids + ticked_s_ids, unticked_t_ids + unticked_s_ids, MapItem)

    ticked_c_ids, unticked_c_ids = get_actual_ids(ticked_ids, unticked_ids, "C_")

    if ticked_c_ids:
        ic(ticked_c_ids)
        await SourceCargoItem.filter(Q(id__in=ticked_c_ids) & (Q(current_cnt__gt=0) | Q(current_cnt__isnull=True))).update(current_cnt=0)

    if unticked_c_ids:
        await SourceCargoItem.filter(id__in=unticked_c_ids, current_cnt=0).update(current_cnt=None)
