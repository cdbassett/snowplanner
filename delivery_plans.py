"""Delivery plans: user-owned, ordered routes of pickup / drop-off stops within one region.

Plans live in their own tables (DeliveryPlan, PlanStop, PlanCargo) which are deliberately not part of the fixtures.
Everything here is plain async DB logic so the UI and the map generator don't need to know how plans are stored.
"""
import math
from collections import Counter, defaultdict, namedtuple
from dataclasses import dataclass

from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from database.models import DeliveryPlan, PlanStop, PlanCargo, PlanLeg, PlanLegCargo, MapItem, Objective, ObjectiveItem, SourceCargoItem, current_cargo_count
from cargo_icons import CargoStack, PlanRow

PLAN_LEG_COLOR_COUNT = 6 # size of PLAN_LEG_COLORS in the map generator: the main route plus five leg colours
SNAP_TOLERANCE = 12 # map units (of 1000); a click / drop this close to a location snaps to it, and plan items this close are "at" a location
GENERIC_CARGO = ("logs", "pipes", "planks", "concrete", "metal")
SNAPPABLE_TYPES = ("source", "craft", "delivery", "truck", "trailer", "spawn", "gate")

# what the map generator needs to draw one stop; rows are (action, [CargoStack]) with pickups first
# number is text ("3", or "3a.1" on a leg); prev_id is the remaining stop its line comes from (None for the first); color indexes the leg palette (0 = main route); legs lists the names of a split's legs
StopView = namedtuple("StopView", "id,number,area_id,x,y,map_item_id,label,completed,rows,prev_id,color,legs", defaults=(None, 0, ()))


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


async def get_tree(plan_id):
    """The plan's stops and legs organised as a tree (see PlanTree)."""
    legs = await PlanLeg.filter(split_stop__plan_id=plan_id).prefetch_related("cargo")
    return PlanTree(await get_stops(plan_id), legs)


def _sequence(plan_id, leg_id):
    """The stops of the main route (leg_id None) or of one leg."""
    return PlanStop.filter(plan_id=plan_id, leg_id=leg_id) if leg_id is not None else PlanStop.filter(plan_id=plan_id, leg_id__isnull=True)


async def add_stop(plan_id, area_id, x, y, map_item_id=None, label="", leg_id=None):
    if leg_id is not None and not await PlanLeg.filter(id=leg_id).exists():
        leg_id = None # the leg went away while the location was being picked

    position = await _sequence(plan_id, leg_id).count()

    if not label and map_item_id and (map_item := await MapItem.filter(id=map_item_id).first()):
        label = map_item.name

    return await PlanStop.create(plan_id=plan_id, position=position, area_id=area_id, x=int(x), y=int(y), map_item_id=map_item_id, label=label or f"Point ({int(x)}, {int(y)})", leg_id=leg_id)


async def _delete_stop_tree(stop_id):
    """Delete a stop together with every leg it splits into and everything on those legs."""
    for leg in await PlanLeg.filter(split_stop_id=stop_id):
        for child in await PlanStop.filter(leg_id=leg.id):
            await _delete_stop_tree(child.id)

        await PlanLegCargo.filter(leg_id=leg.id).delete()
        await leg.delete()

    await PlanCargo.filter(stop_id=stop_id).delete()
    await PlanStop.filter(id=stop_id).delete()


async def delete_stop(stop_id):
    if (stop := await PlanStop.filter(id=stop_id).first()):
        async with in_transaction():
            await _delete_stop_tree(stop_id)
            await renumber(stop.plan_id, stop.leg_id)


async def renumber(plan_id, leg_id=None):
    for position, stop in enumerate(await _sequence(plan_id, leg_id).order_by("position", "id")):
        if stop.position != position:
            await PlanStop.filter(id=stop.id).update(position=position)


async def reorder_stops(plan_id, ordered_ids, leg_id=None):
    """ordered_ids is the new order of (some or all of) one sequence's stop ids; any not mentioned keep their relative order at the end."""
    stops = await _sequence(plan_id, leg_id).order_by("position", "id")
    by_id = {s.id: s for s in stops}
    new_order = [by_id[i] for i in dict.fromkeys(int(i) for i in ordered_ids) if i in by_id]
    new_order += [s for s in stops if s not in new_order]

    for position, stop in enumerate(new_order):
        if stop.position != position:
            await PlanStop.filter(id=stop.id).update(position=position)


async def _leg_is_inside(leg_id, stop_id):
    """True when the leg hangs (at any depth) below the stop."""
    while leg_id is not None:
        leg = await PlanLeg.filter(id=leg_id).prefetch_related("split_stop").first()

        if leg is None:
            return False

        if leg.split_stop_id == stop_id:
            return True

        leg_id = leg.split_stop.leg_id

    return False


async def move_stop_to_leg(stop_id, leg_id, index):
    """Move a stop to position `index` of another sequence (leg_id None = main route). A split can't be moved into its own legs."""
    stop = await PlanStop.filter(id=stop_id).first()

    if not stop or (leg_id is not None and await _leg_is_inside(leg_id, stop_id)):
        return False

    async with in_transaction():
        old_leg = stop.leg_id
        target = [s for s in await _sequence(stop.plan_id, leg_id).order_by("position", "id") if s.id != stop_id]
        index = max(0, min(int(index), len(target)))
        await PlanStop.filter(id=stop_id).update(leg_id=leg_id)
        ids = [s.id for s in target]
        ids.insert(index, stop_id)

        for position, sid in enumerate(ids):
            await PlanStop.filter(id=sid).update(position=position)

        if old_leg != leg_id:
            await renumber(stop.plan_id, old_leg)

    return True


# ---------------------------------------------------------------------------------------------------------------------
# splits: a stop whose cargo / trucks go different ways, one leg each
# ---------------------------------------------------------------------------------------------------------------------

async def add_leg(stop_id):
    number = await PlanLeg.filter(split_stop_id=stop_id).count() + 1
    return await PlanLeg.create(split_stop_id=stop_id, number=number)


async def split_stop(stop_id, leg_count=2):
    """Turn a stop into a split with (at least) leg_count legs."""
    while await PlanLeg.filter(split_stop_id=stop_id).count() < max(2, leg_count):
        await add_leg(stop_id)


async def rename_leg(leg_id, name):
    await PlanLeg.filter(id=leg_id).update(name=name)


async def remove_leg(leg_id):
    """Delete a leg and its stops; the remaining legs are renumbered. Removing the last leg makes the stop a plain stop again."""
    if not (leg := await PlanLeg.filter(id=leg_id).first()):
        return

    async with in_transaction():
        for child in await PlanStop.filter(leg_id=leg_id):
            await _delete_stop_tree(child.id)

        await PlanLegCargo.filter(leg_id=leg_id).delete()
        await leg.delete()

        for number, other in enumerate(await PlanLeg.filter(split_stop_id=leg.split_stop_id).order_by("number", "id"), 1):
            if other.number != number:
                await PlanLeg.filter(id=other.id).update(number=number)


async def unsplit(stop_id):
    """Remove a split. Only possible when at most one leg has stops: those stops continue the route after the split stop. Returns whether it happened."""
    stop = await PlanStop.filter(id=stop_id).first()
    legs = await PlanLeg.filter(split_stop_id=stop_id)
    used = [leg for leg in legs if await PlanStop.filter(leg_id=leg.id).exists()]

    if not stop or len(used) > 1:
        return False

    async with in_transaction():
        moved = list(await PlanStop.filter(leg_id=used[0].id).order_by("position", "id")) if used else []
        seq = [s for s in await _sequence(stop.plan_id, stop.leg_id).order_by("position", "id")]
        at = [s.id for s in seq].index(stop_id) + 1
        ids = [s.id for s in seq[:at]] + [s.id for s in moved] + [s.id for s in seq[at:]]

        if moved:
            await PlanStop.filter(id__in=[s.id for s in moved]).update(leg_id=stop.leg_id)

        for position, sid in enumerate(ids):
            await PlanStop.filter(id=sid).update(position=position)

        for leg in legs:
            await PlanLegCargo.filter(leg_id=leg.id).delete()
            await leg.delete()

    return True


async def set_leg_cargo(leg_id, rows):
    """Replace what the split hands to this leg. rows: iterable of (kind, name, count, ref_id)."""
    async with in_transaction():
        await PlanLegCargo.filter(leg_id=leg_id).delete()

        for kind, name, count, ref_id in rows:
            if count and count > 0:
                await PlanLegCargo.create(leg_id=leg_id, kind=kind, name=name, count=count, ref_id=ref_id)


def _apply(held, cargo_rows):
    for c in cargo_rows:
        held[(c.kind, c.name)] += c.count if getattr(c, "action", "pickup") == "pickup" else -c.count


def leg_letter(number):
    return chr(ord("a") + (number - 1) % 26)


class PlanTree:
    """A plan's stops and legs. The main route is a sequence; a split stop's legs are further sequences, which can contain splits of their own."""

    def __init__(self, stops, legs):
        self.stops = {s.id: s for s in stops}
        self.legs = {l.id: l for l in legs}
        self.seq = defaultdict(list) # leg id (None = main route) -> its stops in order
        self.legs_of = defaultdict(list) # split stop id -> its legs in order

        for stop in sorted(stops, key=lambda s: (s.position, s.id)):
            self.seq[stop.leg_id].append(stop)

        for leg in sorted(legs, key=lambda l: (l.number, l.id)):
            self.legs_of[leg.split_stop_id].append(leg)

        self._numbers = {}

    def is_split(self, stop):
        return bool(self.legs_of.get(stop.id))

    def number(self, stop):
        """'3' on the main route, '3a.1' for the first stop of the first leg of stop 3."""
        if stop.id not in self._numbers:
            index = self.seq[stop.leg_id].index(stop) + 1

            if stop.leg_id is None:
                self._numbers[stop.id] = str(index)
            else:
                leg = self.legs[stop.leg_id]
                self._numbers[stop.id] = f"{self.number(self.stops[leg.split_stop_id])}{leg_letter(leg.number)}.{index}"

        return self._numbers[stop.id]

    def leg_title(self, leg):
        return f"{leg_letter(leg.number)}" + (f": {leg.name}" if leg.name else "")

    def split_totals(self, split):
        """Counter of everything the split's legs are handed in total."""
        total = Counter()

        for leg in self.legs_of.get(split.id, []):
            _apply(total, leg.cargo)

        return total

    def held_before(self, stop):
        """What is being carried on arrival at this stop. A leg starts with what the split handed to it; completed stops count (the cargo really moved)."""
        held = Counter()

        if stop.leg_id is not None:
            _apply(held, self.legs[stop.leg_id].cargo)

        for other in self.seq[stop.leg_id]:
            if other.id == stop.id:
                break

            _apply(held, other.cargo)

            if self.is_split(other): # whatever the legs were handed has left; the rest travels on
                held.subtract(self.split_totals(other))

        return +held

    def leftover(self, leg_id):
        """What is still being carried at the end of a sequence (the main route or a leg), i.e. never marked for drop-off anywhere. A sequence ending in a split hands its load to the legs instead."""
        seq = self.seq.get(leg_id, [])

        if not seq:
            held = Counter()

            if leg_id is not None:
                _apply(held, self.legs[leg_id].cargo)

            return +held

        last = seq[-1]

        if self.is_split(last):
            return Counter()

        held = Counter(self.held_before(last))
        _apply(held, last.cargo)
        return +held

    def balance(self, split):
        """(unassigned, over_assigned) Counters for a split: carried after its own stop but not handed to any leg, and handed out more than carried."""
        after = Counter(self.held_before(split))
        _apply(after, split.cargo)
        diff = Counter(after)
        diff.subtract(self.split_totals(split))
        return +diff, Counter({k: -v for k, v in diff.items() if v < 0})

    def prev_of(self, stop, remaining_ids):
        """The remaining stop whose line leads to this one: the one before it, or for a leg's first stop the split stop (or whatever precedes that when it is done)."""
        seq = self.seq[stop.leg_id]

        for other in reversed(seq[:seq.index(stop)]):
            if other.id in remaining_ids:
                return other

        if stop.leg_id is None:
            return None

        split = self.stops[self.legs[stop.leg_id].split_stop_id]
        return split if split.id in remaining_ids else self.prev_of(split, remaining_ids)

    def leg_color(self, leg):
        """Palette index of a leg. Every leg in the plan gets its own (cycling through the palette), so a leg keeps one colour all the way along and a later split's legs look different from it."""
        if not hasattr(self, "_leg_colors"):
            self._leg_colors = {}

            def walk(leg_id):
                for stop in self.seq.get(leg_id, []):
                    for leg in self.legs_of.get(stop.id, []):
                        self._leg_colors[leg.id] = 1 + len(self._leg_colors) % (PLAN_LEG_COLOR_COUNT - 1)
                        walk(leg.id)

            walk(None)

        return self._leg_colors.get(leg.id, 1)

    def color(self, stop):
        return 0 if stop.leg_id is None else self.leg_color(self.legs[stop.leg_id])


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
    held = (await get_tree(plan.id)).held_before(stop)
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
    """StopViews of the region's visible plan. Stops keep their number even when completed ones are dropped from the map."""
    if not (plan := await get_visible_plan(region)):
        return None

    tree = await get_tree(plan.id)
    remaining = {s.id for s in tree.stops.values() if not s.completed}
    stops = sorted(tree.stops.values(), key=lambda s: s.id)
    views = []

    for s in stops:
        prev = tree.prev_of(s, remaining)
        legs = tuple(tree.leg_title(l) for l in tree.legs_of.get(s.id, []))
        views.append(StopView(s.id, tree.number(s), s.area_id, s.x, s.y, s.map_item_id, s.label, s.completed, stop_rows(s), prev.id if prev else None, tree.color(s), legs))

    return views
