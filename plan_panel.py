"""The "Delivery Plans" tab: choose / create plans, edit their ordered stops, and pick stop locations on the map.

One PlanPanel lives in each open region or area page. All edits go through delivery_plans (the DB) and then call on_changed, which the page uses to refresh itself and tell every other open view.
"""
from nicegui import ui

import delivery_plans as dp
from cargo_icons import CargoStack

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

        stops = await dp.get_stops(visible.id)

        with self.stops_box:
            with ui.column().classes("w-full gap-1").props('id="plan-stops"'):
                for stop in stops:
                    self.stop_row(stop)

            if not stops:
                ui.label("No stops yet.").classes("text-xs text-gray-600")

            self.pick_button = ui.button("Click the map to choose… (cancel)" if self.pick_mode else "Add stop", icon="add_location_alt", on_click=self.toggle_pick_mode).props("dense no-caps" + (" color=warning" if self.pick_mode else "")).classes("w-full")
            self.pick_button.set_visibility(not visible.completed)

    def stop_row(self, stop):
        done = stop.completed

        with ui.column().classes("w-full gap-0 px-1 py-1 border rounded bg-white").props(f'data-id="{stop.id}"').style("border-color:#d0d0d0" + (";opacity:0.55" if done else "")):
            with ui.row().classes("w-full items-center gap-1 no-wrap"):
                ui.icon("drag_indicator").classes("plan-handle cursor-move text-gray-500")
                ui.label(str(stop.position + 1)).classes("text-white text-xs font-bold rounded-full text-center").style("background:#c2410c;min-width:20px;line-height:20px")
                ui.checkbox(value=done, on_change=lambda e, s=stop: self.set_stop_done(s, e.value)).props("dense").tooltip("Done: hides this stop from the map")
                ui.label(self.stop_title(stop)).classes("flex-1 min-w-0 text-sm font-medium truncate" + (" line-through" if done else "")).on("click", lambda s=stop: self.on_select_stop(s.id)).style("cursor:pointer")
                ui.button(icon="edit", on_click=lambda s=stop: self.open_editor(s.id)).props("flat dense round size=sm").tooltip("Edit pickups / drop-offs")
                ui.button(icon="close", on_click=lambda s=stop: self.remove_stop(s)).props("flat dense round size=sm color=negative").tooltip("Remove stop")

            if (summary := rows_summary(stop)):
                ui.label(summary).classes("text-xs text-gray-700 pl-8")

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

    async def remove_stop(self, stop):
        await self.on_select_stop(None)
        await dp.delete_stop(stop.id)
        await self.changed()

    async def handle_reorder(self, ids):
        if (visible := await dp.get_visible_plan(self.region)):
            await dp.reorder_stops(visible.id, ids)
            await self.changed()

    async def set_pick_mode(self, on):
        if self.pick_mode != on:
            self.pick_mode = on
            await ui.run_javascript(f"window.planPickMode = {'true' if on else 'false'}")
            await self.refresh()

    async def toggle_pick_mode(self):
        await self.set_pick_mode(not self.pick_mode)

    async def add_stop_at(self, area_id, x, y, map_item_id=None):
        """Called when the user picked a location on the map while in pick mode."""
        if not self.pick_mode: # several click events can arrive for one click: only the first one counts
            return

        self.pick_mode = False # claimed before any await so a second event can't get in
        visible = await dp.get_visible_plan(self.region)

        await ui.run_javascript("window.planPickMode = false")
        await self.refresh()

        if not visible:
            return

        stop = await dp.add_stop(visible.id, area_id, x, y, map_item_id)
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
        stop = next((s for s in await dp.get_stops(visible.id) if s.id == stop_id), None) if visible else None

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
            ui.label(f"Stop {stop.position + 1}: {self.stop_title(stop)}").classes("font-bold text-lg shrink-0")
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
                dialog.close()
                await self.changed()

            with ui.row().classes("shrink-0"):
                ui.button("Save", on_click=save)
                ui.button("Cancel", on_click=dialog.close).props("flat")

        dialog.open()
