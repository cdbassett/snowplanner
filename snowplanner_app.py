#!/usr/bin/env python3
from collections import defaultdict, namedtuple
import itertools
from itertools import pairwise
import copy

from nicegui import app, ui, Event
from icecream import ic
from tortoise.expressions import Q

from snowplanner_utils import *
from snowrunner_gen_map_text_svg import generate_area_svg, generate_region_svg, calculate_area_offsets_for_region
from database import db
from database.models import *
from cargo_icons import normalize_cargo_name, cargo_style, has_cargo_style, TIER_FILLS, TIER_LEGEND, CARGO_STYLES, GENERIC_STYLES, CargoStack, vehicle_stack, vehicle_kind
from snowrunner_read_game_save import find_newest_game_save, apply_game_save


@app.on_startup
async def init_db():
    await db.init_db()

@app.on_startup
async def run_migrations_and_seeding():
    await db.run_migrations_and_seeding()


print("db init finished")

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

app.add_static_files('/data', snowplanner_data_dir)
app.add_static_files('/js', "js")
app.add_static_files('/map_images', snowplanner_map_image_dir)
app.add_static_files('/assets', snowplanner_base_dir / "assets")

tree_updated = Event[AreaInfo]()
map_updated = Event[AreaInfo]()
save_loaded = Event() # fired after the DB was updated from a game save; every open view refreshes

async def load_game_save():
    try:
        save_file = find_newest_game_save()
        cnt = await apply_game_save(save_file)
    except Exception as e:
        ui.notify(f"Failed to load game save: {e}", type="negative")
        return

    ui.notify(f"Loaded {save_file.name} ({cnt} finished objectives)")
    save_loaded.emit()

d3_init_js_cache = FileCache("d3_init.js", ReadFile)
d3_brush_selection_js_cache = FileCache("d3_brush_selection.js", ReadFile)
diagnosing_console_errors = False


def on_path_changed(path):
    ui.notify(f'Navigated to {path}')

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

def root():
    ui.query('.nicegui-content').classes('p-0') # remove page padding
#    ui.add_head_html('''
#        <style>
#            body {
#                font-size: 10px !important;
#            }
#        </style>
#    ''')
    ui.add_css('''
        .unselectable {
          -webkit-user-select: none; /* Safari, Chrome, Opera, iOS, Android */
          -moz-user-select: none;    /* Firefox */
          -ms-user-select: none;     /* Internet Explorer/Edge */
          user-select: none;         /* Standard syntax (Modern browsers) */
        }
    ''')
    ui.add_css('''
        body {
            font-size: 15px !important;
            }
        @layer components {
           background-color: red !important;
           }
    ''')
    ui.add_css('''
        .q-tree__node--selected {
            background-color: LightGreen !important;  /* Change to your desired color */
            border-radius: 4px;
        }
    ''')

    # hover tooltip for cargo icons drawn in the map svg (elements carry data-tip-* attributes)
    ui.add_css('''
        .cargo-tip {
            position: fixed; z-index: 10000; pointer-events: none; display: none;
            align-items: center; gap: 10px; padding: 6px 12px;
            background: white; color: black; border: 1px solid #444; border-radius: 6px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.35); font-family: Arial;
        }
        .cargo-tip .cargo-tip-icon { font-size: 34px; line-height: 1; }
        .cargo-tip .cargo-tip-name { font-weight: bold; font-size: 15px; }
        .cargo-tip .cargo-tip-count { font-size: 14px; }
    ''')
    ui.add_head_html('''
        <script>
        (() => {
            let tip = null;
            const make = (cls, parent) => { const el = document.createElement('div'); el.className = cls; parent.appendChild(el); return el; };
            const ensureTip = () => {
                if (!tip) {
                    tip = make('cargo-tip', document.body);
                    tip.icon = make('cargo-tip-icon', tip);
                    const text = make('', tip);
                    tip.name = make('cargo-tip-name', text);
                    tip.count = make('cargo-tip-count', text);
                }
                return tip;
            };
            const place = (e) => {
                const t = ensureTip();
                t.style.left = Math.min(e.clientX + 14, window.innerWidth - t.offsetWidth - 4) + 'px';
                t.style.top = Math.min(e.clientY + 14, window.innerHeight - t.offsetHeight - 4) + 'px';
            };
            document.addEventListener('mouseover', (e) => {
                const el = e.target.closest ? e.target.closest('[data-tip-title]') : null;
                if (!el) { if (tip) tip.style.display = 'none'; return; }
                const t = ensureTip();
                t.icon.textContent = el.dataset.tipIcon;
                t.name.textContent = el.dataset.tipTitle;
                t.count.textContent = el.dataset.tipSub || '';
                t.count.style.display = t.count.textContent ? 'block' : 'none';
                t.style.display = 'flex';
                place(e);
            });
            // icons and hover areas sit above the map entries, so pass clicks through to the entry underneath
            document.addEventListener('click', (e) => {
                const el = e.target.closest ? e.target.closest('[data-click-id]') : null;
                if (el && typeof emitEvent === 'function') emitEvent('js_click_event', { id: el.dataset.clickId });
            });
            document.addEventListener('mousemove', (e) => { if (tip && tip.style.display !== 'none') place(e); });
        })();
        </script>
    ''')

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
                    ui.label(stack.icon).classes('items-center justify-center flex-none').style(
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
        section("Trucks", [vehicle_stack(n, kind="truck") for n in sorted(vehicles["truck"])])
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

def get_image_name_ex(area_info, typ="normal", actual=False):
    base = snowplanner_map_image_dir + "\\" if actual else "/map_images/"
    return f"{base}{slugify_region_area(area_info.region, area_info.abbrev)}_{typ}.png"

class __TREE_FUNCTIONS__: pass

top_level_nodes = ["contracts", "tasks", "trucks", "sources", "gates"]

def select_single_top_tree_node(obj_tree, id):
    for node in top_level_nodes:
        if id != node:
            obj_tree.collapse([node])

    obj_tree.expand([id])

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

async def fill_cargo_filter_list(list_el, region_area_ids, filter_list_item_clicked):
    filter_cargo_items = set()

    # if cargo is only present in a source, we DO want to show it to allow filtering by all available cargo.
    for map_item in await MapItem.filter(Q(area_id__in=region_area_ids)).prefetch_related("cargo_items"):
        if not map_item.completed:
            for cargo_item in map_item.cargo_items:
                if (ccnt := current_cargo_count(cargo_item)) != 0:
                    filter_cargo_items.add(cargo_item.name)

    for objective in await Objective.filter(obj_items__deliver_loc__area_id__in=region_area_ids).prefetch_related("obj_items__map_item"):
        for obj_item in objective.obj_items:
            if (not obj_item.map_item or obj_item.map_item.item_type not in ("spawn", "truck")) and not obj_item.completed:
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
                    emoji, fill = cargo_style(item)
                    with ui.item_section().props('side'):
                        ui.label(emoji).classes('items-center justify-center').style(f'display:flex; width:26px; height:26px; background:{fill}; border:1px solid #555; border-radius:4px; font-size:16px')

                ui.label(item)


async def build_cargo_filter_list(region_area_ids, filter_list_item_clicked):
    with ui.column().classes('w-72 h-full bg-gray-50 p-2 flex flex-col shrink-0 min-h-0'):
        ui.label('Cargo Filter').classes('font-bold text-sm mb-1')

        with ui.row().classes('gap-2 items-center text-xs mb-1'):
            for tier, desc in TIER_LEGEND:
                ui.label().style(f'width:14px; height:14px; background:{TIER_FILLS[tier]}; border:1px solid #555; border-radius:3px')
                ui.label(desc)

        with ui.scroll_area().classes('flex-1 w-full border bg-white'):
            filter_cargo_items = ui.list().props('dense separator')

    await fill_cargo_filter_list(filter_cargo_items, region_area_ids, filter_list_item_clicked)
    return filter_cargo_items

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
            items_by_location = [(loc_name, list(loc_items)) for loc_name, loc_items in itertools.groupby(objective.obj_items, lambda r: r.deliver_loc.name)]

            for loc_name, loc_items in items_by_location:
                loc_id = "L_" + loc_name
                loc_node = {"id": loc_id, "label": get_area_desc(loc_name, loc_items[0].deliver_loc.area_id), "header": "location", "noTick": True}
                ids.append(loc_id)
                obj_children.append(loc_node)
#                    oi_children = add_obj_items(loc_items)
                oi_children = []
                expanded.append(loc_id)
                next_stage_blocked = False

                for stage, stage_obj_items in itertools.groupby(loc_items, lambda r: r.stage):
                    stage_blocked = next_stage_blocked
                    stage = stage or 0

                    if stage > 0:
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

                        if not is_blocked and not obj_item.completed:
                            next_stage_blocked = True

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


class __REGION__: pass

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

    def set_highlighted_ids(id):
        nonlocal highlight_ids
        highlight_ids = id

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
        ui.notify("does nothing yet")

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
        return await generate_region_svg(region_areas[0].region, areas, best_offsets, x_tiles, img_paths, hlinks, location_items=location_items, element_classes = use_svg_classes, hide_types=hide_types, show_all=checkbox_all.value, fix_overlaps=checkbox_overlap.value, selected_ids=highlight_ids)

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
        ic("filter_changed", e)
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
        await fill_cargo_filter_list(filter_cargo_items, region_area_ids, filter_list_item_clicked)
        await update_svg()

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

    def make_class_toggler(search_class, add_class):
        search_class = "." + search_class
        def toggler(e):
            ic("toggle", e.value, search_class, add_class)
            if e.value: # e.value is True if checked, False if unchecked
                ui.query(search_class).classes(remove=add_class)
            else:
                ui.query(search_class).classes(add=add_class)

        return toggler


    def make_visibility_toggler(search_class):
        return make_class_toggler(search_class, "hide-me")

    checkboxes = {}
    checkbox_all = None
    checkbox_overlap = None
    checkbox_detail = None

    def checkbox(text, **kw):
        return ui.checkbox(text, **kw).props("dense")

    def create_map_header(region_name, partial_title, prev_item, next_item, is_region=False):
        nonlocal checkboxes, checkbox_all, checkbox_overlap, checkbox_detail
        with ui.row(align_items='center').classes('gap-1 no-wrap flex-none'):
            if is_region:
                ui.button(icon='refresh', on_click=update_svg).classes('m-0')
            else:
                ui.button(icon='menu', on_click=toggle_panel)
                ui.button(icon='refresh', on_click=update_svg).classes('m-0')

            ui.button(icon='save', on_click=load_game_save).props('color=secondary').classes('m-0').tooltip('Refresh from newest game save')

            with ui.link(target='/'):
                ui.icon('home', color='primary').classes('text-4xl')

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
                checkbox_map_type = checkbox("Icons", value=True, on_change=lambda e: switch_map(e.value)).props("dense").bind_value(app.storage.tab, 'Icons')

                with ui.column().classes('gap-0'):
                    checkbox_overlap = checkbox("Ovl", value=True, on_change=update_svg).props("dense").bind_value(app.storage.tab, 'Overlap')
                    checkbox_detail = checkbox("Det", value=False, on_change=update_svg).props("dense").bind_value(app.storage.tab, 'Detail')

                with ui.column().classes('gap-0'):
                    checkbox("Dots", value=True, on_change=make_visibility_toggler("location-dot")).props("dense")
                    checkbox_all = checkbox("All", value=False, on_change=update_svg).props("dense").bind_value(app.storage.tab, 'Completed')

                with ui.grid(columns=3).classes('gap-y-0 gap-x-2'):
                    checkboxes = dict((title, checkbox(title, value=True, on_change=update_svg).props("dense").bind_value(app.storage.tab, title)) for title in svg_vis_togglers)

                save_button = ui.button('Edit', on_click=lambda: edit_save_locations())
                (group_button := ui.button('Group', on_click=lambda: group_locations())).set_visibility(False)
                (cancel_button := ui.button('Cancel', on_click=lambda: cancel_save_locations())).set_visibility(False)
            else:
                with ui.column().classes('gap-0'):
                    checkbox_overlap = checkbox("Ovl", value=False, on_change=update_svg).props("dense").bind_value(app.storage.tab, 'RegionOverlap')
                    checkbox("Dots", value=True, on_change=make_visibility_toggler("location-dot")).props("dense")
                    checkbox_all = checkbox("All", value=False, on_change=update_svg).props("dense").bind_value(app.storage.tab, 'Completed')

                with ui.grid(columns=3).classes('gap-y-0 gap-x-2'):
                    checkboxes = dict((title, checkbox(title, value=True, on_change=update_svg).props("dense").bind_value(app.storage.tab, title)) for title in svg_vis_togglers)

    with ui.column().classes('w-full h-screen flex flex-col no-wrap overflow-hidden'):
        prev_region_item = (prev_region[0], prev_region[1]) if prev_region else None
        next_region_item = (next_region[0], next_region[1]) if next_region else None
        create_map_header(region_areas[0].region, "Region Map", prev_region_item, next_region_item, is_region=True)

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
            filter_cargo_items = await build_cargo_filter_list(region_area_ids, filter_list_item_clicked=filter_list_item_clicked)

    region_client_alive_checker = obj_tree
    tree_updated.subscribe(update_obj_tree_event)
    map_updated.subscribe(update_svg_event)
    save_loaded.subscribe(refresh_from_save)


class __AREA__: pass

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

    def set_highlighted_ids(id):
        nonlocal highlight_ids
        highlight_ids = id


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

        ticked_o_ids, unticked_o_ids = get_actual_ids(ticked_ids, unticked_ids, "O_")
#        ic(ticked_o_ids)
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
        if objective_id:
            obj_tree.expand(["O_" + objective_id])

        obj_tree.select(node_id)
        scroll_to_node(node_id)
        set_highlighted_ids(id)
        obj_tree.expand([node_id])
        show_panel()
        await update_svg_all()

    async def filter_changed(e):
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

        return await generate_area_svg(cur_area_info.region, cur_area_info.area, img_src, loc_mode=loc_mode, location_items=location_items, element_classes = use_svg_classes, hide_types=hide_types, show_all=checkbox_all.value, fix_overlaps=not loc_mode and checkbox_overlap.value, selected_ids=highlight_ids, detail_in_loc_mode=checkbox_detail.value, override_positions=temp_positions)

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
        await fill_cargo_filter_list(filter_cargo_items, [cur_area_info.area_id], filter_list_item_clicked)
        await update_svg()

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



    def make_class_toggler(search_class, add_class):
        search_class = "." + search_class
        def toggler(e):
            ic("toggle", e.value, search_class, add_class)
            if e.value: # e.value is True if checked, False if unchecked
                ui.query(search_class).classes(remove=add_class)
            else:
                ui.query(search_class).classes(add=add_class)

        return toggler


    def make_visibility_toggler(search_class):
        return make_class_toggler(search_class, "hide-me")

    checkboxes = {}
    checkbox_all = None
    checkbox_overlap = None
    checkbox_detail = None

    def checkbox(text, **kw):
        return ui.checkbox(text, **kw).props("dense")

    def create_map_header(region_name, partial_title, prev_item, next_item, is_region=False):
        nonlocal checkboxes, checkbox_all, checkbox_overlap, checkbox_detail
        with ui.row(align_items='center').classes('gap-1 no-wrap flex-none'):
            if is_region:
                ui.button(icon='refresh', on_click=update_svg).classes('m-0')
            else:
                ui.button(icon='menu', on_click=toggle_panel)
                ui.button(icon='refresh', on_click=update_svg).classes('m-0')

            ui.button(icon='save', on_click=load_game_save).props('color=secondary').classes('m-0').tooltip('Refresh from newest game save')

            with ui.link(target='/'):
                ui.icon('home', color='primary').classes('text-4xl')

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
                checkbox_map_type = checkbox("Icons", value=True, on_change=lambda e: switch_map(e.value)).props("dense").bind_value(app.storage.tab, 'Icons')

                with ui.column().classes('gap-0'):
                    checkbox_overlap = checkbox("Ovl", value=True, on_change=update_svg).props("dense").bind_value(app.storage.tab, 'Overlap')
                    checkbox_detail = checkbox("Det", value=False, on_change=update_svg).props("dense").bind_value(app.storage.tab, 'Detail')

                with ui.column().classes('gap-0'):
                    checkbox("Dots", value=True, on_change=make_visibility_toggler("location-dot")).props("dense")
                    checkbox_all = checkbox("All", value=False, on_change=update_svg).props("dense").bind_value(app.storage.tab, 'Completed')

                with ui.grid(columns=3).classes('gap-y-0 gap-x-2'):
                    checkboxes = dict((title, checkbox(title, value=True, on_change=update_svg).props("dense").bind_value(app.storage.tab, title)) for title in svg_vis_togglers)

                save_button = ui.button('Edit', on_click=lambda: edit_save_locations())
                (group_button := ui.button('Group', on_click=lambda: group_locations())).set_visibility(False)
                (cancel_button := ui.button('Cancel', on_click=lambda: cancel_save_locations())).set_visibility(False)
            else:
                with ui.column().classes('gap-0'):
                    checkbox("Dots", value=True, on_change=make_visibility_toggler("location-dot")).props("dense")
                    checkbox_all = checkbox("All", value=False, on_change=update_svg).props("dense").bind_value(app.storage.tab, 'Completed')

                with ui.grid(columns=3).classes('gap-y-0 gap-x-2'):
                    checkboxes = dict((title, checkbox(title, value=True, on_change=update_svg).props("dense").bind_value(app.storage.tab, title)) for title in svg_vis_togglers)


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

    def checkbox(text, **kw):
        return ui.checkbox(text, **kw).props("dense")

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
        create_map_header(cur_area_info.region, cur_area_info.partial_abbrev, prev_area_item, next_area_item, is_region=False)

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

            filter_cargo_items = await build_cargo_filter_list([cur_area_info.area_id], filter_list_item_clicked=filter_list_item_clicked)

        area_client_alive_checker = obj_tree
        tree_updated.subscribe(update_obj_tree_event)
        map_updated.subscribe(update_svg_event)
        save_loaded.subscribe(refresh_from_save)

ui.run(root, port=8081, title='SnowPlanner')

