#!/usr/bin/env python3
import itertools
import pprint

from tortoise.exceptions import IntegrityError, MultipleObjectsReturned
from tortoise import Tortoise, run_async

from icecream import ic
# Set a custom width for indentation and wrapping (default is usually 80)
ic.configureOutput(argToStringFunction=lambda val: pprint.pformat(val, width=192))
from colorama import Style

from snowplanner_utils import *
from database.models import *
from database.config import snowplanner_db_url


type_mapping = {
    "Storage": "source",
    "Crafting": "craft",
    }

areas_by_abbreviation = get_areas_by_abbreviation()
abbreviations_by_area = get_abbreviations_by_area()
area_ids_by_area = get_area_ids_by_area()
areas_by_area_id = get_areas_by_area_id()
#completed_deliveries = get_completed_deliveries() # [area][objective][item] = count, special item ALL
# map_item_positions = get_map_item_positions()
# location_positions = get_location_positions() # [area][location name] = pos
#cargo_initial_counts = get_cargo_initial_counts() # [area][location name][cargo] = count
# delivery_positions = get_delivery_positions() # [area][objective][item] = pos
truck_lookup = dict(map(itemgetter(1, 2), read_snowrunner_data_tsv_file("level_items_list.generated.tsv")))
truck_id_lookup = dict(map(itemgetter(1, 2), read_snowrunner_data_tsv_file("snowrunner_truck_trailer_info.generated.tsv")))

source_name_lookup = dict((parts[1][4:], cargo.loc) for cargo in get_cargo_list_iter() if len(parts := cargo.url.split("?"))>1)
ed = get_english_lang_dict()

# location_positions_by_area_id = dict((area_ids_by_area[area], dct) for area, dct in location_positions.items())


def sq(s):
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]

    return s

def get_x_y(existing_pos):
    if existing_pos and existing_pos != "Unknown":
#        return loc_pos_to_xy_percent(existing_pos)
        return tuple(map(int, loc_pos_to_xy_percent(existing_pos) * (1000, 1000)))
#        return arithtuple(map(float, positions.split(","))) if positions != "Unknown" else arithtuple((.5,.5))

    return None, None

def update_x_y(rec, x, y):
    if rec.x is None and x is not None:
        rec.x = x
        rec.y = y
        return True
    return False

def update_if_null(rec, attr, val):
    if getattr(rec, attr) is None and val is not None:
        setattr(rec, attr, val)
        return True
    return False

def update_if_null_or_diff(rec, attr, val):
    old = getattr(rec, attr)
    if val is not None and (old is None or old != val):
        setattr(rec, attr, val)
        return True
    return False

def update_if_diff(rec, attr, val):
    if getattr(rec, attr) != val and val is not None:
        setattr(rec, attr, val)
        return True
    return False


def get_name_x_y(area_id, loc_id):
    name = source_name_lookup.get(loc_id)

    if not name:
        ic("missing name", area_id, loc_id) # so far only one item missing, can't see it on maprunner
        return None

    # loc_key = (location_positions_by_area_id.get(area_id) or dict()).get(name)
    # x, y = get_x_y(loc_key)
    x, y = None, None
    return name, x, y

def check(loc_id, typ, name):
    if loc_id in ('US_09_01_TRANSIT_02', 'US_09_02_TRANSIT_02'):
        ic(loc_id, typ, name)

async def get_or_create_map_item(loc_id, area_id, item_type, name, x=None, y=None, obj_locker=None, to_area_id=None, to_map_id=None):
        map_item, created = await MapItem.get_or_create(defaults={"id": loc_id, "area_id": area_id, "item_type": item_type, "name": name or loc_id, "x": x, "y": y, "obj_locker": obj_locker, "to_area_id": to_area_id, "to_map_item_id": to_map_id}, id=loc_id)

        if not created:
            if update_x_y(map_item, x, y) or update_if_diff(map_item, "obj_locker", obj_locker):
                await map_item.save()

        return map_item, created

def cargo_cnt_name(cargo):
    try:
        cnt = cargo.get('count')
        if cnt == -1: cnt = None
        return cnt, cargo['name']
    except KeyError:
        ic(cargo)
        raise

async def get_or_create_cargo_item(cargo_id, map_item_id, name, initial_cnt, craft_desc=None):
        cargo_item, created = await SourceCargoItem.get_or_create(defaults={"id": cargo_id, "map_item_id": map_item_id, "name": name, "initial_cnt": initial_cnt, "craft_desc": craft_desc}, id=cargo_id)

        if not created:
            if update_if_diff(cargo_item, "craft_desc", craft_desc):
                await cargo_item.save()

        return cargo_item, created

async def handle_crafting(area_id, loc_id, sub_prop, objective = None):
    if not (res := get_name_x_y(area_id, loc_id)):
#        ic("name not found", area_id, loc_id)
        return

    name, x, y = res
#    check(loc_id, "craft", name)
    if (cargosSettings := sub_prop.get("craftSettings")):
        map_item, created = await get_or_create_map_item(loc_id, area_id, "craft", name, x, y, objective)

        if not created:
            if update_if_diff(map_item, "area_id", area_id):
               await map_item.save()

        for ncargo, cargoSetting in enumerate(cargosSettings):
            cargo_id = map_item.id + "|" + str(ncargo)
#            craftCount = cargoSetting.get("craftCount", 1)
            cnt, cname = cargo_cnt_name(cargoSetting)
            cargo_item, created = await get_or_create_cargo_item(cargo_id, map_item.id, cargo_names_dict.get(cname), cnt, craft_desc=crafted_cargo_desc(cargoSetting))


#            if update_x_y(map_item, x, y):
#                await map_item.save()
#        else: # for now we'll skip child cargo records if main record already exists
#            for cargoSetting in cargosSettings:
#                cnt, cname = cargo_cnt_name(cargoSetting)
#                await SourceCargoItem.create(map_item=map_item, name=cargo_names_dict.get(cname), initial_cnt=cnt, craft_desc=crafted_cargo_ingredients(cargoSetting))
#
#    for cargosSetting in sub_prop["craftSettings"]:
#        cnt = cargosSetting.get('count')
#        if cnt == -1: cnt = None
#        await SourceCargoItem.create(map_item=map_item, name=cargo_names_dict.get(cargosSetting['name']), initial_cnt=cnt, craft_desc=crafted_cargo_ingredients(cargosSetting))


async def handle_storage(area_id, loc_id, sub_prop, objective = None):
    if not (res := get_name_x_y(area_id, loc_id)):
#        ic("name not found", area_id, loc_id)
        return

    name, x, y = res
#    check(loc_id, "source", name)
    if (cargosSettings := sub_prop.get("cargosSettings")):
        map_item, created = await get_or_create_map_item(loc_id, area_id, "source", name, x, y, objective)

        if not created:
            if update_if_diff(map_item, "area_id", area_id):
               await map_item.save()

        for ncargo, cargoSetting in enumerate(cargosSettings):
            cargo_id = map_item.id + "|" + str(ncargo)
            cnt, cname = cargo_cnt_name(cargoSetting)
            cargo_item, created = await get_or_create_cargo_item(cargo_id, map_item.id, cargo_names_dict.get(cname), cnt)

#            if update_x_y(map_item, x, y):
##                await map_item.save()
#        else: # for now we'll skip child cargo records if main record already exists
#            for cargoSetting in cargosSettings:
#                cnt, cname = cargo_cnt_name(cargoSetting)
#                await SourceCargoItem.create(map_item=map_item, name=cargo_names_dict.get(cname), initial_cnt=cnt)
    else:
        ic("storage no cargo", area_id, loc_id, sub_prop.keys())

async def handle_gateway(area_id, loc_id, sub_prop, objective = None):
    to_level, to_map_item_id = sub_prop["levelZoneLink"].split(" || ")
    to_area_id = fname_to_area_id(to_level)
    # center is zero, left is neg, bot is neg
    # x, z, y
    camPos = sub_prop["cameraPos"]
    cx, cy = camPos["x"], camPos["z"]
#    x = (cx/1000 + 1) / 2
#    y = (cy/-1000 + 1) / 2
    x = (int(cx) + 1000) // 2
    y = (-int(cy) + 1000) // 2

#    if area_id in ('US_09_01', 'US_09_02'):
#        ic(area_id, loc_id, sub_prop.keys(), objective,  x, y)

#    if objective and objective.id == "RU_17_01_OPEN_GATE_CONTRACT":
#        ic(area_id, loc_id, x, y)

#    check(loc_id, "gate", None)
    gate_name = f"{get_compass_repr_of_pos_int((x, y))} Gate to {areas_by_area_id[to_area_id]}"
#    map_item, created = await get_or_create_map_item(loc_id, area_id, "gate", gate_name, x, y, objective, to_area_id, to_map_item_id)
    map_item, created = await get_or_create_map_item(loc_id, area_id, "gate", gate_name, x, y, objective, to_area_id)

    if not created:
        if update_if_null(map_item, "to_area_id", to_area_id) or update_if_null(map_item, "to_map_item_id", to_map_item_id) or update_if_diff(map_item, "item_type", "gate") or update_if_diff(map_item, "name", gate_name):
#        if update_if_null(map_item, "to_area_id", to_area_id) or update_if_diff(map_item, "item_type", "gate") or update_if_diff(map_item, "name", gate_name):
            try:
                await map_item.save()
            except IntegrityError:
                ic(loc_id, to_map_item_id)
                raise

def get_rewards(props):
    reward_money, reward_exp, reward_item = None, None, None

    if (rewards := props.get("rewards")):
        if (rewardMoney := rewards.get("ObjectiveRewardMoney")):
            reward_money = rewardMoney["amount"]

        if (rewardExp := rewards.get("ObjectiveRewardExperience")):
            reward_exp = rewardExp["amount"]

        if (rewardItem := rewards.get("ObjectiveRewardItem")):
            reward_item_id = rewardItem["itemName"].upper()
            reward_item = ed.get(reward_item_id) or ed.get(reward_item_id + "_NAME") or ed.get("UI_VEHICLE_" + reward_item_id + "_NAME") or reward_item_id

    return reward_money, reward_exp, reward_item


#@init_memory_sqlite
async def run(area_id_filter=None) -> None:
#    area_id_filter = "US_16_01"
#    area_id_filter = "US_09_01"


    async def populate():
        print("Cargo sources/Gates")

        for fname, python_data in iterate_level_files_basic():
            area_id = fname_to_area_id(fname)
            region, area = region_area(ed, area_id)
            # location_positions_area = location_positions.get(area) or dict()
#                print(fname)

            for loc_id, dct in python_data["zoneDesc"].items():
                s = ed.get(loc_id, loc_id)

                if (props := dct.get("props")):
                    if (sub_prop := props.get("ZonePropertyGateway")):
#                            ic(area_id, loc_id, sub_prop.keys())
                        await handle_gateway(area_id, loc_id, sub_prop)
                    elif (sub_prop := props.get(loc_id)): # at least one-time bug of wrong key
                        await handle_gateway(area_id, loc_id, sub_prop)

                    if "ZonePropertyWatchpoint" in props:
                        pass
#                            camera_pos = ",".join(list(map(str, sub_prop["cameraPosStart"].values()))[:3])
#                            watchtower_records.append([fname[:14], loc_id, camera_pos])
                    elif (sub_prop := props.get("ZonePropertyCargoLoading")):
                        await handle_storage(area_id, loc_id, sub_prop)
                    elif (sub_prop := props.get("ZonePropertyStorehouseCraft")):
                        await handle_crafting(area_id, loc_id, sub_prop)
                    elif "ZonePropertyUpgradesGiver" in props:
                        pass
                    elif (sub_prop := props.get("ZonePropertyMiniObjectiveCargo")): # zurdania worksites, not in tasks list but just a place to dump fuel/repair/parts to unclog a spot
                        if (cargoRequirements := sub_prop.get("cargoRequirements")):
                            name = ed.get(loc_id, "Worksite")
                            reward_money, reward_exp, reward_item = get_rewards(sub_prop)
                            obj_id = loc_id
                            objective, objective_created = await Objective.get_or_create(defaults={"id": obj_id, "area_id": area_id, "name": name, "obj_type": "task", "reward_money": reward_money, "reward_exp": reward_exp, "reward_item": reward_item}, id=obj_id)
                            delivery_map_item, created = await get_or_create_map_item(loc_id, area_id, "delivery", name)

                            for idx, cargo in enumerate(cargoRequirements):
                                cnt, cname = cargo_cnt_name(cargo)
                                item_name = cargo_name(cname)
                                obj_item_id = "|".join(map(str, (objective.id, 0, idx, "c"))) # objective_id + stage index + zone index
                                obj_item, created = await ObjectiveItem.get_or_create(
                                    defaults={"id": obj_item_id, "objective_id": objective.id, "item_type": "cargo", "name": item_name, "count": cnt, "deliver_loc_id": loc_id}, id=obj_item_id)

                                if not created:
                                    if update_if_diff(obj_item, "name", item_name):
                                        await obj_item.save()



        print("Trucks/trailers")

        for area_id, area_recs in itertools.groupby(area_id_filterer(read_snowrunner_data_tsv_file("level_items_list.generated.tsv"), area_id_filter), itemgetter(0)):
            region, area = region_area(ed, area_id)
            # map_item_positions_area = map_item_positions[area]
            objective = None # maybe track trucks locked by objective

            for _, task_id, truck_id, ui_id, item_name, idx, cargo_string in area_recs:
                x, y = None, None
                # x, y = get_x_y(map_item_positions_area.get(f"{item_name}|{idx}"))
                use_id = task_id or f"{area_id}|{truck_id}|{idx}"
                map_item, created = await get_or_create_map_item(use_id, area_id, "trailer" if "trailer" in item_name else "truck", item_name, x, y, objective)

                for ncargo, cargo in enumerate(cargo_string.strip().split("|")):
                    cargo_id = map_item.id + "|" + str(ncargo)
                    cnt, cname = parse_cargo_count(cargo)
#                    if area_id == "US_09_01":
#                        ic(cargo_id, cargo, cnt, cname)

                    if cname:
                        cargo_item, created = await get_or_create_cargo_item(cargo_id, map_item.id, cname, cnt)
#                    else: # this was used to clean up erroneously crated records from blank cargo names
#                        await SourceCargoItem.filter(id=cargo_id).delete()

        print("Objectives")

        for area_id, python_data in sorted(fname_to_area_id_it(iterate_objective_files_basic(), area_id_filter)):
            region, area = region_area(ed, area_id)
#                area_id = fname[:8].upper()
            # location_positions_area = location_positions.get(area) or dict()
#                 print(f"{fname}: {': '.join(region_area(ed,fname))}:")

            for typ, task_type in zip(("tasksSettings", "contractsSettings"), ("Task", "Contract")):
                tasksSettings = python_data[typ]
                obj_type = task_type.lower()

                for obj_id, task in tasksSettings.items():
                    name = f"{ed[obj_id.upper()]} ({task_type[0]})"
                    reward_money, reward_exp, reward_item = get_rewards(task)
                    objective, objective_created = await Objective.get_or_create(defaults={"id": obj_id, "area_id": area_id, "name": name, "obj_type": obj_type, "reward_money": reward_money, "reward_exp": reward_exp, "reward_item": reward_item}, id=obj_id)

                    if (blockerObjectives := task.get("blockerObjectives")):
                        for blockerObjective in blockerObjectives:
                            obj_prereq, created = await ObjectivePrereq.get_or_create(defaults={"objective_id": obj_id, "prereq_obj_id": blockerObjective}, objective_id=obj_id, prereq_obj_id=blockerObjective)

#                            if obj_id == "US_02_03_DRILL_DELIVERY_OBJ":
#                                ic(obj_id, blockerObjective, obj_prereq, created)

                    if not objective_created:
                        if update_if_null_or_diff(objective, "obj_type", obj_type) or update_if_null_or_diff(objective, "reward_money", reward_money) or update_if_null_or_diff(objective, "reward_exp", reward_exp) or update_if_null_or_diff(objective, "reward_item", reward_item):
                            await objective.save()

                    # use this if need to recreate objective item records because format of synthetic id has changed (happened twice already)
#                    if not objective_created: # for now we'll rebuild child records if main record already exists
#                        await ObjectiveItem.filter(objective_id=objective.id).delete()

#                           obj_prereq = await ObjectivePrereq.create(objective=objective, prereq_obj_id=blockerObjective)
#                    if area_id == "RU_17_01":
#                    if obj_id == "RU_17_01_OPEN_GATE_CONTRACT":
#                        ic(obj_id, name)

                    if (rewards := task.get("rewards")):
                        for ObjectiveRewardOpenZoneProperties in (rewards.get(key) for key in ("ObjectiveRewardOpenZoneProperties", "ObjectiveRewardOpenZoneProperties_1", "ObjectiveRewardOpenZoneProperties_2", "ObjectiveRewardUpdateZoneProperties", "ObjectiveRewardUpdateZoneProperties_1", "ObjectiveRewardUpdateZoneProperties_2")):
                            if ObjectiveRewardOpenZoneProperties and (zoneSettings := ObjectiveRewardOpenZoneProperties.get("zoneSettings")):
                                for ZonePropertiesSettingsObjectiveReward in (zoneSettings.get(key) for key in ("ZonePropertiesSettingsObjectiveReward", "ZonePropertiesSettingsObjectiveReward_1", "ZonePropertiesSettingsObjectiveReward_2")):
                                    if ZonePropertiesSettingsObjectiveReward and (props := ZonePropertiesSettingsObjectiveReward.get("props")):
                                        if (zoneId := ZonePropertiesSettingsObjectiveReward.get("zoneId")):
                                            if (sub_prop := props.get("ZonePropertyCargoLoading")):
#                                            ic(area_id, zoneId, sub_prop.keys(), objective)
                                                await handle_storage(fname_to_area_id(zoneId), zoneId, sub_prop, objective)
                                            elif (sub_prop := props.get("ZonePropertyStorehouseCraft")):
                                                await handle_crafting(fname_to_area_id(zoneId), zoneId, sub_prop, objective)
                                            elif (sub_prop := props.get("ZonePropertyGateway")):
                                                use_area_id = fname_to_area_id(ZonePropertiesSettingsObjectiveReward["mapId"])
#                                            if obj_id == "RU_17_01_OPEN_GATE_CONTRACT":
#                                                ic(use_area_id, zoneId, sub_prop)
                                                await handle_gateway(use_area_id, zoneId, sub_prop, objective)

                    if (stages := task.get("stages")):
                        for nstage, stage in enumerate(stages):
                            deliveries = []
                            cargo_deliveries = dict()

                            if (actions := stage.get("actions")):
                                cur_zone = None
#                                if (zoneToFill := actions.get("zoneToFill")) and (cur_zone := zoneToFill[0].get('uiDesc')):
                                if (zoneToFill := actions.get("zoneToFill")):
                                    for nzone, zone in enumerate(zoneToFill):
                                        if zone:
#                                            if obj_id == "US_02_03_MAZUT_OBJ":
#                                                ic(obj_id, nstage, nzone, zone)
                                            try:
                                                to_area_id, other_zone_id = zone["globalZoneId"]["globalZoneId"].split(" || ")
                                            except:
                                                ic(nzone, zone, zoneToFill)
                                                raise
                                            to_area_id = fname_to_area_id(to_area_id)
#                                        if to_area_id.endswith("_new"): to_area_id = to_area_id[:-4]
                                            cur_zone = zone.get('uiDesc') or cur_zone or other_zone_id

                                            if (cargo := zone.get("cargo")):
                                                cnt, cname = cargo_cnt_name(cargo)
#                                            cname = cargo['name']
                                                delivery = (cur_zone, "cargo", cnt, cargo_name(cname), cname, to_area_id, nzone, None)
                                                deliveries.append(delivery)
                                                cargo_deliveries[cname] = (cur_zone, to_area_id)

                            if (livingAreaInfo := stage.get("livingAreaInfo")):
                                livingAreaValue = (" " + str(livingAreaValue)) if (livingAreaValue := livingAreaInfo.get("livingAreaValue")) else ""

                                if (livingAreaGlobalZoneId := livingAreaInfo.get("livingAreaGlobalZoneId")):
                                    if (globalZoneId := livingAreaGlobalZoneId.get("globalZoneId")):
                                        lvl, cur_zone = globalZoneId.split(" || ")
                                        to_area_id = fname_to_area_id(lvl)
                                            # k bc want unique letter for id
                                        delivery = (cur_zone, "kabin", livingAreaInfo['livingAreaValue'], "Cabin [2]", cur_zone, to_area_id, 0, "Cabin Zone" + livingAreaValue)
                                        deliveries.append(delivery)

                            if (repairTrucks := stage.get("repairTruck")):
                                for ntruck, repairTruck in enumerate(repairTrucks):
                                    if repairTruck.get("afterStageFinished") == "REWARD":
                                        truck_id = repairTruck["truckId"]

                                        if (map_item := await MapItem.filter(id=truck_id).first()):
                                            if update_if_diff(map_item, "obj_locker_id", objective.id):
                                                await map_item.save()
                                        else:
                                            print(f"Couldn't find truck {truck_id} to link to object {objective.name}")

                            if (truckDeliveries := stage.get("truckDelivery")):
                                cur_zone = truckDeliveries[0]['uiDesc']

                                for ntruck, truckDelivery in enumerate(truckDeliveries):
                                    to_area_id = fname_to_area_id(truckDelivery["globalZoneDeliveryId"]["globalZoneId"].split(" || ")[0])
                                    truck_id = truckDelivery["truckId"]
                                    delivery = (cur_zone, "truck", None, ed[truck_id_lookup[truck_lookup[truckDelivery['truckId']]].upper()], truck_id, to_area_id, ntruck, None)

                                    if truckDelivery.get("afterStageFinished") == "REWARD":
                                        if (map_item := await MapItem.filter(id=truck_id).first()):
                                            if update_if_diff(map_item, "obj_locker_id", objective.id):
                                                await map_item.save()

#                                    ic(truckDelivery['truckId'])
                                    deliveries.append(delivery)

                            if (spawnCargoOnStageActive := stage.get("spawnCargoOnStageActive")):
                                for nCargo, spawnCargo in enumerate(spawnCargoOnStageActive):
                                    if (cargos := spawnCargo.get("cargos")):
                                        assert len(cargos) == 1
                                        cargo = cargos[0]
                                        cnt, cname = cargo_cnt_name(cargo)
                                        lvl, pickup_id = spawnCargo["zone"]["globalZoneId"].split(" || ")
                                        from_area_id = fname_to_area_id(lvl)

                                        if (cargo_delivery := cargo_deliveries.get(cname)):
                                            item_name = cargo_name(cname)
                                            map_item, created = await get_or_create_map_item(pickup_id, from_area_id, "spawn", item_name)

                                            cur_zone, to_area_id = cargo_delivery
                                            delivery = (cur_zone, "spawn", cnt, item_name, pickup_id, to_area_id, nCargo, None)
                                            deliveries.append(delivery)

#                                        spawned_cargo__map_item, created = await get_or_create_map_item(pickup_id, from_area_id, "spawn", cargo_name(cname), None, None)

                            for delivery in deliveries:
                                deliver_loc_id, item_type, cnt, item_name, pickup_id, to_area_id, idx, loc_name = delivery

                                if not loc_name:
                                    if (dl := ed.get(deliver_loc_id)):
                                        loc_name = delivery_location(dl)
                                    else:
                                        loc_name = deliver_loc_id

                                # if obj_id == "US_02_03_MAZUT_OBJ":
                                #     ic(obj_id, delivery, loc_name)
                                item_name = item_name.replace('“',"").replace('”',"")
                                # this is old, was used to read already create information from data file for db
                                # cargo_area, cargo_pos = get_cargo_delivery_pos(delivery_positions, areas_by_abbreviation, area, name, item_name)
                                cargo_area, cargo_pos = None, None
                                # x, y = get_x_y(location_positions_area.get(loc_name))
                                x, y = None, None

                                if item_type == "truck" and "Trailer" in item_name:
                                    item_type = "trailer"
                                elif item_type == "cargo":
                                    pickup_id = None

                                try:
                                        # map_item is where item can be picked up
                                    delivery_map_item, created = await get_or_create_map_item(deliver_loc_id, to_area_id, "delivery", loc_name, x, y)

                                    if not created and (update_if_diff(delivery_map_item, "area_id", to_area_id) or update_if_diff(delivery_map_item, "name", loc_name)): # fix bug that created map entries for delivery locations with incorrect area ids
                                        if loc_name: delivery_map_item.name = loc_name
                                        await delivery_map_item.save()

                                    obj_item_id = "|".join(map(str, (objective.id, nstage, idx, item_type[0]))) # objective_id + stage index + zone index

#                                    if objective.id == 'US_16_03_BACK_TO_PLACE_CONTRACT':
#                                        ic(obj_item_id, item_type, pickup_id, deliver_loc_id)

                                    try:
                                        obj_item, created = await ObjectiveItem.get_or_create(
                                            defaults={"id": obj_item_id, "objective_id": objective.id, "item_type": item_type, "name": item_name, "count": cnt, "deliver_loc_id": deliver_loc_id, "map_item_id":  pickup_id, "stage":  nstage}, id=obj_item_id)
                                    except IntegrityError:
                                        ic(obj_item_id, deliver_loc_id, pickup_id)
                                        raise
#
                                    if not created:
                                        if update_if_diff(obj_item, "deliver_loc_id", deliver_loc_id) or update_if_diff(obj_item, "map_item_id", pickup_id) or update_if_diff(obj_item, "name", item_name) or update_if_diff(obj_item, "stage", nstage):
                                            try:
                                                await obj_item.save()
                                            except IntegrityError:
                                                ic(deliver_loc_id, pickup_id, obj_item)
                                                raise
                                    if cargo_pos:
                                        if item_type in ("truck", "trailer"):
                                            await obj_item.fetch_related("map_item")
                                            map_item = obj_item.map_item
#                                            map_item = await obj_item.map_item
                                            if not map_item:
                                                ic(obj_item_id, item_type, obj_item.map_item_id)

                                            if update_x_y(map_item, cargo_pos[0], cargo_pos[1]):
                                                await map_item.save()
                                    elif item_type == "Cargo":
                                        pass
                                except IntegrityError:
                                    ic(pickup_id)
                                    raise
                                except MultipleObjectsReturned:
                                    ic(objective.id, pickup_id, item_name, deliver_loc_id)
                                    res = await ObjectiveItem.filter(objective_id=objective.id, deliver_loc_id=deliver_loc_id, name=item_name).values("objective_id", "deliver_loc_id", "name", "area_id", "count")
                                    ic(res)
                                    raise

    if 0:
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["database.models"]})
    else:
#        os.remove(snowplanner_db_filename)
        await Tortoise.init(db_url=snowplanner_db_url, modules={"models": ["database.models"]})

    await Tortoise.generate_schemas()

    await populate()
#    await report()


if __name__ == "__main__":
    print(Style.RESET_ALL)
    run_async(run())

