"""The "Delivery Plans" tab: choose / create plans, edit their ordered stops, and pick stop locations on the map.

One PlanPanel lives in each open region or area page. All edits go through delivery_plans (the DB) and then call on_changed, which the page uses to refresh itself and tell every other open view.
"""
from collections import Counter

from nicegui import ui

import delivery_plans as dp
from cargo_icons import CargoStack
from snowrunner_gen_map_text_svg import PLAN_LEG_COLORS

ACTION_TEXT = {"pickup": "▲", "dropoff": "▼"}
ACTION_COLOR = {"pickup": "#2e7d32", "dropoff": "#b23a48"}


def icon_html(kind, name, size=22):
    stack = CargoStack(name, None, name, False, None, kind)
    uris = stack.art_uris
    return "".join(f'<img src="{u}" style="width:{size}px;height:{size}px">' for u in uris) if uris else f'<span style="font-size:{size - 4}px">{stack.icon}</span>'


def rows_summary(stop):
    parts = []

    for action in ("pickup", "dropoff"):
        items = [f"{c.count}× {c.name.split(' [')[0]}" for c in stop.cargo if c.action == action]

        if items:
            parts.append(f"{ACTION_TEXT[action]} " + ", ".join(items))

    return "   ".join(parts)


class PlanPanel:
    def __init__(self, region, region_area_ids, point_to_location, on_changed, on_select_stop, cur_area_id=None, abbrevs=None):
        """point_to_location(svg_x, svg_y) -> (area_id, x, y) in map units, or None when the point isn't on a map (the page knows its own layout).

        on_changed: async callable run after any plan change. on_select_stop(stop_id or None): highlights a stop's square on the map.
        """
        self.region = region
        self.cur_area_id = cur_area_id # None in the region view
        self.abbrevs = abbrevs or {}
        self.region_area_ids = region_area_ids
        self.point_to_location = point_to_location
        self.on_changed = on_changed
        self.on_select_stop = on_select_stop
        self.pick_mode = False
        self.show_completed = False
        self.header = None
        self.stops_box = None
        self.pick_button = None
        self.pick_leg_id = None # where the stop being picked on the map will go: None = main route, else a leg id
        self.plan_completed = False
        self.dialog_host = None

    # ---------------------------------------------------------------------------------------------------------------
    # building
    # ---------------------------------------------------------------------------------------------------------------

    async def build(self):
        with ui.column().classes("w-full h-full gap-1 min-h-0") as self.root:
            self.dialog_host = ui.element("div") # dialogs are created in here so refreshing the lists below never deletes an open dialog
            self.header = ui.column().classes("w-full gap-1")
            self.stops_box = ui.column().classes("w-full gap-1 flex-1 overflow-auto min-h-0")

        await self.refresh()

    async def refresh(self):
        plans = await dp.list_plans(self.region, self.show_completed)
        visible = await dp.get_visible_plan(self.region)
        self.header.clear()

        with self.header:
            with ui.row().classes("w-full items-center gap-1 no-wrap"):
                options = {p.id: p.name + (" ✔" if p.completed else "") for p in plans}

                if visible and visible.id not in options: # a completed plan that's visible while the completed toggle is off
                    options[visible.id] = visible.name + " ✔"

                ui.select(options, value=visible.id if visible else None, label="Plan", on_change=lambda e: self.choose_plan(e.value)).props("dense outlined options-dense").classes("flex-1 min-w-0")
                ui.button(icon="add", on_click=self.new_plan_dialog).props("flat dense round").tooltip("New plan")

            with ui.row().classes("w-full items-center gap-1 no-wrap"):
                if visible:
                    ui.button(icon="edit", on_click=lambda: self.rename_dialog(visible)).props("flat dense round").tooltip("Rename plan")
                    ui.button(icon="undo" if visible.completed else "task_alt", on_click=lambda: self.toggle_plan_completed(visible)).props("flat dense round").tooltip("Mark plan not complete" if visible.completed else "Mark plan complete")
                    ui.button(icon="delete", on_click=lambda: self.delete_dialog(visible)).props("flat dense round color=negative").tooltip("Delete plan")

                ui.space()
                ui.checkbox("completed", value=self.show_completed, on_change=self.toggle_show_completed).props("dense").classes("text-xs")

        self.stops_box.clear()

        if not visible:
            with self.stops_box:
                ui.label("No delivery plan in this region yet. Use + to create one.").classes("text-xs text-gray-600")

            self.pick_button = None
            return

        tree = await dp.get_tree(visible.id)
        self.plan_completed = visible.completed

        with self.stops_box:
            self.sequence(tree, None)

    def sequence(self, tree, leg_id):
        """One ordered list of stops (the main route or a leg), followed by its own Add stop button. Each list is a drag-and-drop target."""
        stops = tree.seq.get(leg_id, [])

        with ui.column().classes("w-full gap-1 plan-seq" + ("" if stops else " rounded") + " min-h-4").props(f'data-leg="{"" if leg_id is None else leg_id}"').style("" if stops else "border:1px dashed #bbb"):
            for stop in stops:
                self.stop_item(tree, stop)

        if not stops and leg_id is None:
            ui.label("No stops yet.").classes("text-xs text-gray-600")

        if (left := tree.leftover(leg_id)) and (stops or leg_id is not None): # carried to the end without being dropped off anywhere
            with ui.column().classes("w-full gap-0 px-2 py-1 rounded").style("background:#fff3cd;border:1px solid #e0b84c"):
                ui.label("Still carried at the end, not dropped off anywhere:").classes("text-xs font-bold").style("color:#7a5b00")

                for (kind, name), count in sorted(left.items(), key=lambda kv: (kv[0][0] != "cargo", kv[0][1])):
                    with ui.row().classes("items-center gap-1 no-wrap"):
                        ui.html(icon_html(kind, name, 16)).classes("shrink-0")
                        ui.label(f"{count}× {name.split(' [')[0]}" if kind == "cargo" else f"{name} ({kind})").classes("text-xs")

        if not self.plan_completed and not (stops and tree.is_split(stops[-1])): # nothing follows a split on the same list: its legs carry on from there
            picking = self.pick_mode and self.pick_leg_id == leg_id
            button = ui.button("Click the map to choose… (cancel)" if picking else ("Add stop" if leg_id is None else f"Add stop to leg {dp.leg_letter(tree.legs[leg_id].number)}"), icon="add_location_alt", on_click=lambda: self.toggle_pick_mode(leg_id)).props("dense no-caps" + (" color=warning" if picking else "")).classes("w-full")

            if leg_id is None:
                self.pick_button = button

    def stop_item(self, tree, stop):
        with ui.column().classes("w-full gap-1").props(f'data-id="{stop.id}"'):
            self.stop_row(tree, stop)

            if tree.is_split(stop):
                for leg in tree.legs_of[stop.id]:
                    self.leg_block(tree, leg)

    def leg_block(self, tree, leg):
        color = PLAN_LEG_COLORS[tree.leg_color(leg)][0]

        with ui.column().classes("gap-1 pl-2 min-w-0").style(f"border-left:4px solid {color};margin-left:12px;width:calc(100% - 12px);box-sizing:border-box"):
            with ui.row().classes("w-full items-center gap-1 no-wrap"):
                ui.label(f"Leg {dp.leg_letter(leg.number)}" + (f": {leg.name}" if leg.name else "")).classes("flex-1 min-w-0 text-xs font-bold truncate").style(f"color:{color}")

                if (sent := ", ".join(f"{c.count}× {c.name.split(' [')[0]}" for c in leg.cargo)):
                    ui.label(sent).classes("text-xs text-gray-600 truncate max-w-[10rem]").tooltip("Handed to this leg at the split")

                ui.button(icon="edit", on_click=lambda l=leg: self.rename_leg_dialog(l)).props("flat dense round size=sm").tooltip("Rename leg")
                ui.button(icon="close", on_click=lambda l=leg: self.remove_leg(tree, l)).props("flat dense round size=sm color=negative").tooltip("Remove leg and its stops")

            self.sequence(tree, leg.id)

    def stop_row(self, tree, stop):
        done = stop.completed
        split = tree.is_split(stop)
        number = tree.number(stop)
        color = PLAN_LEG_COLORS[tree.color(stop)][0] if tree.color(stop) else "#c2410c"

        with ui.column().classes("w-full gap-0 px-1 py-1 border rounded bg-white").style("border-color:#d0d0d0" + (";opacity:0.55" if done else "")):
            with ui.row().classes("w-full items-center gap-1 no-wrap"):
                ui.icon("drag_indicator").classes("plan-handle cursor-move text-gray-500")
                ui.label(number).classes("text-white text-xs font-bold rounded-full text-center px-1").style(f"background:{color};min-width:20px;line-height:20px")
                ui.checkbox(value=done, on_change=lambda e, s=stop: self.set_stop_done(s, e.value)).props("dense").tooltip("Done: hides this stop from the map")
                ui.label(self.stop_title(stop)).classes("flex-1 min-w-0 text-sm font-medium truncate" + (" line-through" if done else "")).on("click", lambda s=stop: self.on_select_stop(s.id)).style("cursor:pointer")

                if split:
                    ui.button(icon="alt_route", on_click=lambda s=stop: self.add_leg(s)).props("flat dense round size=sm").tooltip("Add another leg")
                    ui.button(icon="call_merge", on_click=lambda s=stop: self.unsplit(s)).props("flat dense round size=sm").tooltip("Remove the split")
                else:
                    ui.button(icon="call_split", on_click=lambda s=stop: self.split(s)).props("flat dense round size=sm").tooltip("Split here: send cargo / trucks different ways")

                ui.button(icon="edit", on_click=lambda s=stop: self.open_editor(s.id)).props("flat dense round size=sm").tooltip("Edit pickups / drop-offs" + (" and what each leg gets" if split else ""))
                ui.button(icon="close", on_click=lambda s=stop: self.remove_stop(tree, s)).props("flat dense round size=sm color=negative").tooltip("Remove stop" + (" and everything on its legs" if split else ""))

            if (summary := rows_summary(stop)):
                ui.label(summary).classes("text-xs text-gray-700 pl-8")

            if split:
                unassigned, over = tree.balance(stop)

                if over:
                    ui.label("Handed out more than carried: " + ", ".join(f"{n} {k[1]}" for k, n in over.items())).classes("text-xs pl-8").style("color:#b23a48")
                elif unassigned:
                    ui.label("Not sent on a leg: " + ", ".join(f"{n}× {k[1]}" for k, n in unassigned.items())).classes("text-xs text-gray-600 pl-8")

    # ---------------------------------------------------------------------------------------------------------------
    # plan level actions
    # ---------------------------------------------------------------------------------------------------------------

    async def changed(self):
        with self.root: # the element whose handler got us here (a checkbox, a dialog button) may be deleted by the refresh; keep a live UI context for the rest
            await self.on_changed()

    async def choose_plan(self, plan_id):
        if plan_id is None or (visible := await dp.get_visible_plan(self.region)) and visible.id == plan_id:
            return

        await self.set_pick_mode(False)
        await self.on_select_stop(None)

        from database.models import DeliveryPlan

        if (plan := await DeliveryPlan.filter(id=plan_id, region=self.region).first()):
            await dp.set_visible(plan)
            await self.changed()

    async def toggle_show_completed(self, e):
        self.show_completed = e.value
        await self.refresh()

    def stop_title(self, stop):
        """Stop label, with the area abbreviation when it isn't in the area being viewed (always in the region view)."""
        if stop.area_id != self.cur_area_id and (abbrev := self.abbrevs.get(stop.area_id)):
            return f"{stop.label} ({abbrev})"

        return stop.label

    async def new_plan_dialog(self):
        default_name = await dp.default_plan_name(self.region)

        with self.dialog_host, ui.dialog() as dialog, ui.card():
            ui.label("New delivery plan").classes("font-bold")
            name = ui.input("Name", value=default_name).props("autofocus outlined dense")

            async def create():
                plan = await dp.create_plan(self.region, name.value.strip() or default_name)
                await dp.set_visible(plan)
                dialog.close()
                await self.changed()

            name.on("keydown.enter", create)
            ui.timer(0.3, lambda: name.run_method("focus"), once=True)

            with ui.row():
                ui.button("Create", on_click=create)
                ui.button("Cancel", on_click=dialog.close).props("flat")

        dialog.open()

    def rename_dialog(self, plan):
        with self.dialog_host, ui.dialog() as dialog, ui.card():
            ui.label("Rename plan").classes("font-bold")
            name = ui.input("Name", value=plan.name).props("autofocus outlined dense")

            async def rename():
                await dp.rename_plan(plan.id, name.value.strip() or plan.name)
                dialog.close()
                await self.changed()

            name.on("keydown.enter", rename)
            ui.timer(0.3, lambda: name.run_method("focus"), once=True)

            with ui.row():
                ui.button("Rename", on_click=rename)
                ui.button("Cancel", on_click=dialog.close).props("flat")

        dialog.open()

    def delete_dialog(self, plan):
        with self.dialog_host, ui.dialog() as dialog, ui.card():
            ui.label(f'Delete plan "{plan.name}" and all of its stops?')

            async def delete():
                await self.set_pick_mode(False)
                await dp.delete_plan(plan.id)
                dialog.close()
                await self.changed()

            with ui.row():
                ui.button("Delete", on_click=delete).props("color=negative")
                ui.button("Cancel", on_click=dialog.close).props("flat")

        dialog.open()

    async def toggle_plan_completed(self, plan):
        await self.set_pick_mode(False)
        await dp.set_plan_completed(plan.id, not plan.completed)

        if not plan.completed: # it was just completed; keep showing it until the user picks another so the result is visible
            await dp.set_visible(plan)

        await self.changed()

    # ---------------------------------------------------------------------------------------------------------------
    # stops
    # ---------------------------------------------------------------------------------------------------------------

    async def set_stop_done(self, stop, done):
        await dp.set_stop_completed(stop.id, done)
        await self.changed()

    async def remove_stop(self, tree, stop):
        async def delete():
            await self.on_select_stop(None)
            await dp.delete_stop(stop.id)
            await self.changed()

        if tree.is_split(stop) and any(tree.seq.get(leg.id) for leg in tree.legs_of[stop.id]):
            self.confirm_dialog(f"Remove the split at {stop.label} and all the stops on its legs?", "Remove", delete)
        else:
            await delete()

    def confirm_dialog(self, text, button, action):
        with self.dialog_host, ui.dialog() as dialog, ui.card():
            ui.label(text)

            async def go():
                dialog.close()
                await action()

            with ui.row():
                ui.button(button, on_click=go).props("color=negative")
                ui.button("Cancel", on_click=dialog.close).props("flat")

        dialog.open()

    async def handle_reorder(self, leg_id, ids):
        if (visible := await dp.get_visible_plan(self.region)):
            await dp.reorder_stops(visible.id, ids, leg_id or None)
            await self.changed()

    async def handle_move(self, stop_id, leg_id, index):
        """A stop was dragged onto a different list (the main route or another leg)."""
        if await dp.move_stop_to_leg(int(stop_id), int(leg_id) if leg_id else None, index):
            await self.changed()
        else:
            await self.refresh() # refused (a split can't go into its own legs): put the list back as it was

    # ---------------------------------------------------------------------------------------------------------------
    # splits
    # ---------------------------------------------------------------------------------------------------------------

    async def split(self, stop):
        await dp.split_stop(stop.id, 2)
        await self.changed()
        await self.open_editor(stop.id) # the legs are empty: choose what each one gets

    async def add_leg(self, stop):
        await dp.add_leg(stop.id)
        await self.changed()

    async def unsplit(self, stop):
        if await dp.unsplit(stop.id):
            await self.changed()
        else:
            ui.notify("Only one leg may have stops to remove the split.", type="warning")

    async def remove_leg(self, tree, leg):
        async def delete():
            await dp.remove_leg(leg.id)
            await self.changed()

        if tree.seq.get(leg.id):
            self.confirm_dialog(f"Remove leg {dp.leg_letter(leg.number)} and its stops?", "Remove", delete)
        else:
            await delete()

    def rename_leg_dialog(self, leg):
        with self.dialog_host, ui.dialog() as dialog, ui.card():
            ui.label(f"Leg {dp.leg_letter(leg.number)}").classes("font-bold")
            name = ui.input("Name (optional)", value=leg.name).props("autofocus outlined dense")

            async def rename():
                await dp.rename_leg(leg.id, name.value.strip())
                dialog.close()
                await self.changed()

            name.on("keydown.enter", rename)
            ui.timer(0.3, lambda: name.run_method("focus"), once=True)

            with ui.row():
                ui.button("Rename", on_click=rename)
                ui.button("Cancel", on_click=dialog.close).props("flat")

        dialog.open()

    async def set_pick_mode(self, on):
        if self.pick_mode != on:
            self.pick_mode = on
            await ui.run_javascript(f"window.planPickMode = {'true' if on else 'false'}")
            await self.refresh()

    async def toggle_pick_mode(self, leg_id=None):
        """Start picking a stop location for the main route (leg_id None) or one leg; clicking the same button again cancels."""
        if self.pick_mode and self.pick_leg_id == leg_id:
            await self.set_pick_mode(False)
        else:
            self.pick_leg_id = leg_id
            was_on = self.pick_mode
            await self.set_pick_mode(True)

            if was_on: # already picking (for another list): just retarget and redraw the buttons
                await self.refresh()

    async def add_stop_at(self, area_id, x, y, map_item_id=None):
        """Called when the user picked a location on the map while in pick mode."""
        if not self.pick_mode: # several click events can arrive for one click: only the first one counts
            return

        self.pick_mode = False # claimed before any await so a second event can't get in
        leg_id = self.pick_leg_id
        visible = await dp.get_visible_plan(self.region)

        await ui.run_javascript("window.planPickMode = false")
        await self.refresh()

        if not visible:
            return

        stop = await dp.add_stop(visible.id, area_id, x, y, map_item_id, leg_id=leg_id)
        await self.on_select_stop(stop.id)
        await self.changed()
        await self.open_editor(stop.id)

    async def handle_map_point(self, px, py):
        """A click on empty map in pick mode: use the clicked coordinates, snapping to a real location if one is right there."""
        if (loc := self.point_to_location(px, py)):
            area_id, x, y = loc
            snapped = await dp.snap_location(area_id, x, y)
            await self.add_stop_at(area_id, snapped.x if snapped else x, snapped.y if snapped else y, snapped.id if snapped else None)

    async def handle_location_click(self, map_item):
        """A click on an existing entry in pick mode: use that location's real position (not where overlap correction drew it)."""
        if map_item is not None and map_item.x is not None:
            await self.add_stop_at(map_item.area_id, map_item.x, map_item.y, map_item.id)

    async def handle_plan_drag(self, stop_id, px, py):
        """A plan square was dragged on the map and dropped at svg point (px, py)."""
        if not (loc := self.point_to_location(px, py)):
            await self.changed() # dropped off the map: snap back
            return

        area_id, x, y = loc
        snapped = await dp.snap_location(area_id, x, y)
        await dp.move_stop_location(stop_id, area_id, snapped.x if snapped else x, snapped.y if snapped else y, snapped.id if snapped else None)
        await self.changed()

    # ---------------------------------------------------------------------------------------------------------------
    # stop editor
    # ---------------------------------------------------------------------------------------------------------------

    async def open_editor(self, stop_id):
        visible = await dp.get_visible_plan(self.region)
        tree = await dp.get_tree(visible.id) if visible else None
        stop = tree.stops.get(stop_id) if tree else None

        if not stop:
            return

        await self.on_select_stop(stop.id)
        here, others = await dp.pickup_choices(visible, stop, self.region_area_ids)
        drops = await dp.dropoff_choices(visible, stop)
        have = {(c.action, c.kind, c.name): c for c in stop.cargo}

        # rows already on the stop that are no longer offered (e.g. the stop was dragged somewhere else) stay visible so they can be cleared
        offered_pick = {(c.kind, c.name) for c in here + others}
        offered_drop = {(c.kind, c.name) for c in drops}
        here = here + [dp.Choice(c.kind, c.name, None, c.ref_id, "not available here") for (a, k, n), c in have.items() if a == "pickup" and (k, n) not in offered_pick]
        drops = drops + [dp.Choice(c.kind, c.name, None, c.ref_id, "not carried at this point") for (a, k, n), c in have.items() if a == "dropoff" and (k, n) not in offered_drop]
        inputs = [] # (action, choice, number input)

        with self.dialog_host, ui.dialog() as dialog, ui.card().classes("w-[30rem] max-w-full max-h-[85vh] flex flex-col no-wrap gap-2"):
            ui.label(f"Stop {tree.number(stop)}: {self.stop_title(stop)}").classes("font-bold text-lg shrink-0")
            body = ui.column().classes("w-full flex-1 min-h-0 overflow-auto gap-1 no-wrap") # scrolls; the buttons below stay visible
            body.__enter__()

            def section(title, action, choices, empty_text):
                if title:
                    ui.label(title).classes("font-bold mt-2").style(f"color:{ACTION_COLOR[action]}")

                if not choices:
                    ui.label(empty_text).classes("text-xs text-gray-600")

                for choice in choices:
                    with ui.row().classes("w-full items-center gap-2 no-wrap"):
                        ui.html(icon_html(choice.kind, choice.name)).classes("shrink-0")
                        label = choice.name + (f"  ({choice.note})" if choice.note else "")
                        ui.label(label).classes("flex-1 min-w-0 text-sm")
                        current = have.get((action, choice.kind, choice.name))
                        number = ui.number(value=current.count if current else (choice.suggested if not stop.cargo else 0), min=0, max=choice.max_count, step=1, precision=0).props("dense outlined").classes("w-20")

                        if choice.max_count is not None:
                            number.tooltip(f"up to {choice.max_count}")

                        inputs.append((action, choice, number))

            leg_inputs = [] # (leg, choice, number input)

            if tree.is_split(stop): # what each leg gets; based on what the plan carries after this stop as last saved
                carried = Counter(tree.held_before(stop))
                for c in stop.cargo:
                    carried[(c.kind, c.name)] += c.count if c.action == "pickup" else -c.count

                carried = +carried
                ui.label("Send each way").classes("font-bold mt-3")
                ui.label("Based on what is carried after this stop as saved; save and reopen after changing its pick-ups / drop-offs.").classes("text-xs text-gray-600")

                for leg in tree.legs_of[stop.id]:
                    color = PLAN_LEG_COLORS[tree.leg_color(leg)][0]
                    ui.label(f"Leg {dp.leg_letter(leg.number)}" + (f": {leg.name}" if leg.name else "")).classes("font-bold mt-1").style(f"color:{color}")
                    given = {(c.kind, c.name): c for c in leg.cargo}
                    items = dict.fromkeys([*carried, *given])

                    if not items:
                        ui.label("Nothing is carried at this point.").classes("text-xs text-gray-600")

                    for kind, name in items:
                        choice = dp.Choice(kind, name, carried.get((kind, name)), None, "" if (kind, name) in carried else "not carried at this point")

                        with ui.row().classes("w-full items-center gap-2 no-wrap"):
                            ui.html(icon_html(kind, name)).classes("shrink-0")
                            ui.label(name + (f"  ({choice.note})" if choice.note else "")).classes("flex-1 min-w-0 text-sm")
                            number = ui.number(value=given[(kind, name)].count if (kind, name) in given else 0, min=0, max=choice.max_count, step=1, precision=0).props("dense outlined").classes("w-20")

                            if choice.max_count is not None:
                                number.tooltip(f"{choice.max_count} carried")

                        leg_inputs.append((leg, choice, number))

            section("Pick up here", "pickup", here, "Nothing is available at this location.")

            section("Drop off here", "dropoff", drops, "This plan isn't carrying anything at this point.")

            if others: # suggestions come first; the rest of the available cargo is below them
                ui.label("Other cargo currently available (pick up)").classes("font-bold mt-2").style(f"color:{ACTION_COLOR['pickup']}")
                section("", "pickup", others, "")

            body.__exit__(None, None, None)

            async def save():
                rows = []

                for action, choice, number in inputs:
                    if number.value:
                        rows.append((action, choice.kind, choice.name, int(number.value), choice.ref_id))

                await dp.set_stop_cargo(stop.id, rows)

                for leg in tree.legs_of.get(stop.id, []):
                    await dp.set_leg_cargo(leg.id, [(choice.kind, choice.name, int(number.value), None) for lg, choice, number in leg_inputs if lg is leg and number.value])

                dialog.close()
                await self.changed()

            with ui.row().classes("shrink-0"):
                ui.button("Save", on_click=save)
                ui.button("Cancel", on_click=dialog.close).props("flat")

        dialog.open()
