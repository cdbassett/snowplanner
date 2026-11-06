"""Delivery plans: user-owned, ordered routes of pickup / drop-off stops within one region.

Plans live in their own tables (DeliveryPlan, PlanStop, PlanCargo) which are deliberately not part of the fixtures.
Everything here is plain async DB logic so the UI and the map generator don't need to know how plans are stored.
"""
import math
from collections import Counter, namedtuple
from dataclasses import dataclass

from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from database.models import DeliveryPlan, PlanStop, PlanCargo, MapItem, Objective, ObjectiveItem, SourceCargoItem, current_cargo_count
from cargo_icons import CargoStack, PlanRow

SNAP_TOLERANCE = 12 # map units (of 1000); a click / drop this close to a location snaps to it, and plan items this close are "at" a location
GENERIC_CARGO = ("logs", "pipes", "planks", "concrete", "metal")
SNAPPABLE_TYPES = ("source", "craft", "delivery", "truck", "trailer", "spawn", "gate")

# what the map generator needs to draw one stop; rows are (action, [CargoStack]) with pickups first
StopView = namedtuple("StopView", "id,number,area_id,x,y,map_item_id,label,completed,rows")


@dataclass
class Choice:
    kind: str # cargo, truck or trailer
    name: str
    max_count: int | None = None # None = unlimited / unknown
    ref_id: str | None = None
    note: str = ""
    suggested: int = 0 # default count to prefill in the editor


# ---------------------------------------------------------------------------------------------------------------------
# plans
# ---------------------------------------------------------------------------------------------------------------------

async def list_plans(region, include_completed=False):
    flt = DeliveryPlan.filter(region=region)

    if not include_completed:
        flt = flt.filter(completed=False)

    return await flt.order_by("id")


async def create_plan(region, name):
    plan = await DeliveryPlan.create(region=region, name=name or "New plan")

    if not await DeliveryPlan.filter(region=region, visible=True).exists():
        await set_visible(plan)
        await plan.refresh_from_db()

    return plan


async def rename_plan(plan_id, name):
    await DeliveryPlan.filter(id=plan_id).update(name=name)


async def delete_plan(plan_id):
    if (plan := await DeliveryPlan.filter(id=plan_id).first()):
        was_visible = plan.visible
        await plan.delete()

        if was_visible:
            await show_first_plan(plan.region)


async def show_first_plan(region):
    """After the visible plan went away, show the first remaining incomplete one (if any)."""
    if (plan := await DeliveryPlan.filter(region=region, completed=False).order_by("id").first()):
        await set_visible(plan)


async def get_visible_plan(region):
    return await DeliveryPlan.filter(region=region, visible=True).first()


async def set_visible(plan):
    """Make this the plan drawn on the map for its region; every other plan in the region is hidden."""
    async with in_transaction():
        await DeliveryPlan.filter(region=plan.region).exclude(id=plan.id).update(visible=False)
        await DeliveryPlan.filter(id=plan.id).update(visible=True)


async def set_plan_completed(plan_id, completed=True):
    if (plan := await DeliveryPlan.filter(id=plan_id).first()):
        await DeliveryPlan.filter(id=plan_id).update(completed=completed, visible=False if completed else plan.visible)

        if completed and plan.visible:
            await show_first_plan(plan.region)


# ---------------------------------------------------------------------------------------------------------------------
# stops
# ---------------------------------------------------------------------------------------------------------------------

async def get_stops(plan_id):
    return await PlanStop.filter(plan_id=plan_id).order_by("position", "id").prefetch_related("cargo")


async def add_stop(plan_id, area_id, x, y, map_item_id=None, label=""):
    position = await PlanStop.filter(plan_id=plan_id).count()

    if not label and map_item_id and (map_item := await MapItem.filter(id=map_item_id).first()):
        label = map_item.name

    return await PlanStop.create(plan_id=plan_id, position=position, area_id=area_id, x=int(x), y=int(y), map_item_id=map_item_id, label=label or f"Point ({int(x)}, {int(y)})")


async def delete_stop(stop_id):
    if (stop := await PlanStop.filter(id=stop_id).first()):
        plan_id = stop.plan_id
        await stop.delete()
        await renumber(plan_id)


async def renumber(plan_id):
    for position, stop in enumerate(await PlanStop.filter(plan_id=plan_id).order_by("position", "id")):
        if stop.position != position:
            await PlanStop.filter(id=stop.id).update(position=position)


async def reorder_stops(plan_id, ordered_ids):
    """ordered_ids is the new order of (some or all of) the plan's stop ids; any not mentioned keep their relative order at the end."""
    stops = await PlanStop.filter(plan_id=plan_id).order_by("position", "id")
    by_id = {s.id: s for s in stops}
    new_order = [by_id[i] for i in dict.fromkeys(int(i) for i in ordered_ids) if i in by_id]
    new_order += [s for s in stops if s not in new_order]

    for position, stop in enumerate(new_order):
        if stop.position != position:
            await PlanStop.filter(id=stop.id).update(position=position)


async def move_stop_location(stop_id, area_id, x, y, map_item_id=None):
    stop = await PlanStop.filter(id=stop_id).first()

    if not stop:
        return

    label = stop.label

    if map_item_id and (map_item := await MapItem.filter(id=map_item_id).first()):
        label = map_item.name
    elif stop.map_item_id or label.startswith("Point ("): # no longer at a named location, or a free point whose automatic name shows its coordinates
        label = f"Point ({int(x)}, {int(y)})"

    await PlanStop.filter(id=stop_id).update(area_id=area_id, x=int(x), y=int(y), map_item_id=map_item_id, label=label)


async def set_stop_completed(stop_id, completed):
    await PlanStop.filter(id=stop_id).update(completed=completed)


async def set_stop_cargo(stop_id, rows):
    """Replace a stop's pickup / drop-off rows. rows: iterable of (action, kind, name, count, ref_id)."""
    async with in_transaction():
        await PlanCargo.filter(stop_id=stop_id).delete()

        for action, kind, name, count, ref_id in rows:
            if count is None or count > 0:
                await PlanCargo.create(stop_id=stop_id, action=action, kind=kind, name=name, count=count or 1, ref_id=ref_id)


async def default_plan_name(region):
    """'Plan N' with the lowest N not already used in this region."""
    used = {plan.name for plan in await DeliveryPlan.filter(region=region)}
    n = 1

    while f"Plan {n}" in used:
        n += 1

    return f"Plan {n}"


async def snap_location(area_id, x, y, tolerance=SNAP_TOLERANCE):
    """The nearest real location (source, craft, delivery location, loose vehicle) within tolerance of a map point, or None."""
    best, best_dist = None, tolerance

    for map_item in await MapItem.filter(area_id=area_id, item_type__in=SNAPPABLE_TYPES, x__not_isnull=True, y__not_isnull=True):
        if (dist := math.hypot(map_item.x - x, map_item.y - y)) <= best_dist:
            best, best_dist = map_item, dist

    return best


# ---------------------------------------------------------------------------------------------------------------------
# what is held / available
# ---------------------------------------------------------------------------------------------------------------------

def held_after(stops, up_to_position):
    """Counter of (kind, name) carried after finishing every stop whose position < up_to_position. Completed stops count: the cargo really moved."""
    held = Counter()

    for stop in sorted(stops, key=lambda s: s.position):
        if stop.position >= up_to_position:
            break

        for c in stop.cargo:
            held[(c.kind, c.name)] += c.count if c.action == "pickup" else -c.count

    return +held # drop zero / negative entries


def _same_place(stop, other):
    if stop.map_item_id or other.map_item_id:
        return stop.map_item_id == other.map_item_id and stop.area_id == other.area_id

    return stop.area_id == other.area_id and math.hypot(stop.x - other.x, stop.y - other.y) <= SNAP_TOLERANCE


async def dropped_by_other_plans(plan, stop):
    """Counter of (kind, name) that other incomplete plans in this region leave at this stop's place (drops minus pickups) at non-objective locations."""
    avail = Counter()

    for other_plan in await DeliveryPlan.filter(region=plan.region, completed=False).exclude(id=plan.id):
        for other_stop in await get_stops(other_plan.id):
            if _same_place(stop, other_stop):
                for c in other_stop.cargo:
                    avail[(c.kind, c.name)] += c.count if c.action == "dropoff" else -c.count

    if stop.map_item_id and await MapItem.filter(id=stop.map_item_id, item_type="delivery").exists():
        return Counter() # drop-offs at objective locations are consumed by the objective, not left for pickup

    return +avail


async def available_cargo_names(region_area_ids, show_all=False):
    """Names of the cargo currently available in these areas (the cargo filter's list, before generic groups are added)."""
    names = set()

        # plain sources only list cargo that an incomplete objective still needs, same as the map
    needed_cargo = None if show_all else set(await ObjectiveItem.filter(item_type="cargo", completed=False, objective__completed=False, deliver_loc__area_id__in=region_area_ids).values_list("name", flat=True))

    for map_item in await MapItem.filter(Q(area_id__in=region_area_ids)).prefetch_related("cargo_items"):
        if show_all or not map_item.completed:
            for cargo_item in map_item.cargo_items:
                if current_cargo_count(cargo_item) != 0 and (needed_cargo is None or map_item.item_type != "source" or cargo_item.name in needed_cargo):
                    names.add(cargo_item.name)

    for objective in await Objective.filter(obj_items__deliver_loc__area_id__in=region_area_ids).prefetch_related("obj_items__map_item"):
        for obj_item in objective.obj_items:
            if (not obj_item.map_item or obj_item.map_item.item_type not in ("spawn", "truck")) and (show_all or not (obj_item.completed or objective.completed)):
                names.add(obj_item.name)

    return names


async def pickup_choices(plan, stop, region_area_ids):
    """(at_location, others): what can be picked up at this stop. at_location first (including items other plans drop here), then other cargo available in the region."""
    at_location = []
    seen = set()

    def add(choice):
        if (choice.kind, choice.name) not in seen:
            seen.add((choice.kind, choice.name))
            at_location.append(choice)

    if stop.map_item_id:
        for cargo_item in await SourceCargoItem.filter(map_item_id=stop.map_item_id):
            if (cnt := current_cargo_count(cargo_item)) != 0:
                add(Choice("cargo", cargo_item.name, cnt))

        for obj_item in await ObjectiveItem.filter(map_item_id=stop.map_item_id, item_type="cargo", completed=False, objective__completed=False):
            add(Choice("cargo", obj_item.name, obj_item.count, obj_item.id, "from objective"))

    # loose trucks / trailers at this place
    for vehicle in await MapItem.filter(area_id=stop.area_id, item_type__in=("truck", "trailer"), completed=False):
        if vehicle.id == stop.map_item_id or (vehicle.x is not None and math.hypot(vehicle.x - stop.x, vehicle.y - stop.y) <= SNAP_TOLERANCE):
            add(Choice(vehicle.item_type, vehicle.name, 1, vehicle.id))

    for (kind, name), cnt in (await dropped_by_other_plans(plan, stop)).items():
        add(Choice(kind, name, cnt, None, "dropped by another plan"))

    others = []

    for name in sorted(await available_cargo_names(region_area_ids)):
        if ("cargo", name) not in seen and not any(name.casefold() == g for g in GENERIC_CARGO):
            others.append(Choice("cargo", name))

    return at_location, others


async def dropoff_choices(plan, stop):
    """Items this plan is carrying when it reaches the stop; those an incomplete objective still needs at this location come first."""
    held = held_after(await get_stops(plan.id), stop.position)
    needed = Counter()

    if stop.map_item_id:
        for obj_item in await ObjectiveItem.filter(deliver_loc_id=stop.map_item_id, completed=False, objective__completed=False):
            needed[obj_item.name] += obj_item.count or 1

    choices = []

    for (kind, name), cnt in held.items():
        need = needed.get(name, 0)
        choices.append(Choice(kind, name, cnt, None, f"objective needs {need}" if need else "", min(cnt, need) if kind == "cargo" else 0))

    choices.sort(key=lambda c: (not c.note, c.name))
    return choices


# ---------------------------------------------------------------------------------------------------------------------
# map view
# ---------------------------------------------------------------------------------------------------------------------

def stop_rows(stop):
    """[(action, [CargoStack])] for a stop, pickups first; an action with nothing is omitted."""
    rows = []

    for action in ("pickup", "dropoff"):
        stacks = [CargoStack(c.name, c.count, c.name, False, None, c.kind) for c in stop.cargo if c.action == action]

        if stacks:
            rows.append(PlanRow(action, stacks))

    return rows


async def get_plan_view(region):
    """StopViews of the region's visible plan, in order. Stops keep their number (position + 1) even when completed ones are dropped."""
    if not (plan := await get_visible_plan(region)):
        return None

    return [StopView(s.id, s.position + 1, s.area_id, s.x, s.y, s.map_item_id, s.label, s.completed, stop_rows(s)) for s in await get_stops(plan.id)]
