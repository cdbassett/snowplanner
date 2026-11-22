#!/usr/bin/env python3
"""The icons of tasks, contracts, contests and vehicle types, and where an objective's markers are on the map.

Icon tables (all from the game's scripts):
  * objective list states (new / viewed / active / tracked / locked / completed) of contracts, contests and tasks (minimap_ui_sidepanel_controller.sso),
  * the icon of each kind of objective stage (objective_stage_header_icons.sso) and of the compass bar marker (popup_objective_ui_controller.sso):
    FIND, CARGO_DELIVERY, TRUCK_DELIVERY, REPAIR, MISC, CHANGE_TRUCK,
  * vehicle type icons (truck_type_ui_desc.sso) and the recommended truck icons (minimap_ui_sidepanel_view.sso), and a few more.
Where: a stage's marker is at its zone: cargo to deliver (zoneToFill), vehicle to deliver (truckDelivery), places to visit (visitAllZones),
actions / farming / living areas (MISC), a repair truck's spawn; a task or contest is started at its giver zone.

    python3 dev/marker_icons.py OUT_DIR [--gfx-pak PATH]

writes OUT_DIR/marker_icon_map.tsv, OUT_DIR/marker_icons_by_objective.tsv and the PNGs in OUT_DIR/icons/<movie>/.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import extract_gfx_icons
from utils import gamefiles, level_data
from utils.snowrunner_utils import fname_to_area_id, iterate_objective_files_basic, parse_sso

STAGE_KINDS = ("FIND", "CARGO_DELIVERY", "TRUCK_DELIVERY", "REPAIR", "MISC", "CHANGE_TRUCK")


def values(table):
    """{key: symbol} from a table like {KEY: {__value: "symbol"}}"""
    return {k: v["__value"] for k, v in (table or {}).items() if isinstance(v, dict) and "__value" in v}


def icon_tables():
    """[(category, key, symbol)]"""
    rows = []
    sidepanel = parse_sso(gamefiles.read_ps_text("minimap_ui_sidepanel_controller.sso"))

    for category in ("contractIcons", "contestIcons", "taskIcons"):
        rows += [(category, k, v) for k, v in values(sidepanel.get(category)).items()]

    view = parse_sso(gamefiles.read_ps_text("minimap_ui_sidepanel_view.sso"))
    rows += [("recommendedTruckIcons", k, v) for k, v in values(view.get("recommendedTruckIcons")).items()]
    rows += [("sidepanelTab", str(n), v) for n, v in enumerate(view.get("tabsIconLinkage", []))]
    rows += [("sidepanel", k, view[k]) for k in ("notifyIconName", "blockerZoneIcon", "regionalProgressIcon") if k in view]
    rows += [("stageIcon", k, v) for k, v in values(parse_sso(gamefiles.read_ps_text("objective_stage_header_icons.sso")).get("icons")).items()]
    rows += [("compassBarMarker", k, v) for k, v in values(parse_sso(gamefiles.read_ps_text("popup_objective_ui_controller.sso")).get("iconsByType")).items()]
    truck_types = parse_sso(gamefiles.read_ps_text("truck_type_ui_desc.sso"))
    rows += [("truckType40", k, v) for k, v in values(truck_types.get("truckTypeLinkage")).items()]
    rows += [("truckType30", k, v) for k, v in values(truck_types.get("truckType30Linkage")).items()]
    current = parse_sso(gamefiles.read_ps_text("current_objective_ui_controller.sso"))
    rows += [("currentObjective", k, current[k]) for k in ("taskIcon", "contestIcon") if k in current]
    log = parse_sso(gamefiles.read_ps_text("game_log_controller.sso"))
    rows += [("gameLogObjective", k, v) for k, v in values(log.get("gameLogObjectiveIcons")).items()]
    return rows


def zone_ref(value):
    while isinstance(value, dict):
        value = value.get("globalZoneId")

    return value if isinstance(value, str) and " || " in value else None


def stage_zones(stage):
    """[(stage kind, 'level || ZONE')] of a stage"""
    out = []

    for zone in ((stage.get("actions") or {}).get("zoneToFill")) or ():
        if zone and (ref := zone_ref(zone.get("globalZoneId"))):
            out.append(("CARGO_DELIVERY", ref))

    for delivery in stage.get("truckDelivery") or ():
        if delivery and (ref := zone_ref(delivery.get("globalZoneDeliveryId"))):
            out.append(("TRUCK_DELIVERY", ref))

    for repair in stage.get("repairTruck") or ():
        if repair and (ref := zone_ref(repair.get("globalZoneSpawnId"))):
            out.append(("REPAIR", ref))

    for key, kind in (("visitAllZones", "FIND"), ("makeActionInZone", "MISC")):
        for zone in ((stage.get(key) or {}).get("zones")) or ():
            if zone and (ref := zone_ref(zone.get("globalZoneId"))):
                out.append((kind, ref))

    if (farming := stage.get("farmingInfo")) and (ref := zone_ref(farming.get("farmingZone"))):
        out.append(("MISC", ref))

    if (living := stage.get("livingAreaInfo")) and (ref := zone_ref(living.get("livingAreaGlobalZoneId"))):
        out.append(("MISC", ref))

    if "changeTruck" in stage:
        out.append(("CHANGE_TRUCK", ""))

    return out


def main(out_dir, gfx_pak=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    table = icon_tables()
    stage_icon = {k: v for c, k, v in table if c == "stageIcon"}
    compass_icon = {k: v for c, k, v in table if c == "compassBarMarker"}
    giver_icon = {"tasksSettings": "taskImg40", "contestSettings": "contestImg"}

    with open(out_dir / "marker_icon_map.tsv", "w", encoding="utf-8") as f:
        f.write("category\tkey\tsymbol\n")
        f.writelines("\t".join(r) + "\n" for r in table)

    levels = {}

    def position(ref):
        """(area id, zone id, x, y) of 'level || ZONE'"""
        level, zone_id = (s.strip() for s in ref.split("||"))
        area_id = fname_to_area_id(level)

        if area_id not in levels:
            try:
                data = gamefiles.read_data_for_ssl(area_id)
                zones = level_data.parse_level_zones(data)
                levels[area_id] = (data, zones, level_data.area_half_span(data, zones))
            except Exception:
                levels[area_id] = None

        if not levels[area_id]:
            return area_id, zone_id, "", ""

        data, zones, half = levels[area_id]
        placement = level_data.zone_placement(data, zones[zone_id]) if zone_id in zones else level_data.placement_by_id(data, zone_id)

        if placement and abs(placement.x) < 3000 and abs(placement.z) < 3000:
            x, y = level_data.world_to_db(placement.x, placement.z, half)
            return area_id, zone_id, x, y

        return area_id, zone_id, "", ""

    rows = []

    for _, data in iterate_objective_files_basic():
        for kind, obj_type in (("tasksSettings", "task"), ("contractsSettings", "contract"), ("contestSettings", "contest")):
            for obj_id, objective in data.get(kind, {}).items():
                if kind in giver_icon and (ref := zone_ref(objective.get("taskGiverZone"))):
                    area_id, zone_id, x, y = position(ref)
                    rows.append((obj_id, obj_type, area_id, "", "GIVER", giver_icon[kind], "", zone_id, str(x), str(y)))

                for n, stage in enumerate(objective.get("stages") or ()):
                    for stage_kind, ref in stage_zones(stage or {}):
                        area_id, zone_id, x, y = position(ref) if ref else ("", "", "", "")
                        rows.append((obj_id, obj_type, area_id, str(n), stage_kind, stage_icon.get(stage_kind, ""), compass_icon.get(stage_kind, ""), zone_id, str(x), str(y)))

    with open(out_dir / "marker_icons_by_objective.tsv", "w", encoding="utf-8") as f:
        f.write("objective_id\tobjective_type\tarea_id\tstage\tkind\tmap_icon\tcompass_icon\tzone_id\tx\ty\n")
        f.writelines("\t".join(r) + "\n" for r in rows)

    symbols = sorted({v for _, _, v in table} | set(giver_icon.values()))

    for movie in ("icons_lib", "minimap", "hud_lib"):
        extract_gfx_icons.main(out_dir / "icons", [movie], gfx_pak, only=symbols)

    print(f"{len(rows)} markers of {len({r[0] for r in rows})} objectives")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out_dir")
    parser.add_argument("--gfx-pak")
    args = parser.parse_args()
    main(args.out_dir, args.gfx_pak)
