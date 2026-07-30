#!/usr/bin/env python3
import pprint

from tortoise import Tortoise, run_async

from icecream import ic
# Set a custom width for indentation and wrapping (default is usually 80)
ic.configureOutput(argToStringFunction=lambda val: pprint.pformat(val, width=192))
from colorama import Style

from snowplanner_utils import *
from database.models import *
from database.config import snowplanner_db_url


areas_by_abbreviation = get_areas_by_abbreviation()
abbreviations_by_area = get_abbreviations_by_area()
area_ids_by_area = get_area_ids_by_area()
#truck_lookup = dict(map(itemgetter(1, 2), read_snowrunner_tsv_file("level_items_list.generated.tsv")))
#truck_id_lookup = dict(map(itemgetter(1, 2), read_snowrunner_tsv_file("snowrunner_truck_trailer_info.generated.tsv")))

ed = get_english_lang_dict()

def report_singles(title, src, first_text):
    print(title, len(src))

    for item in src:
#            print(first_text.format(**item._asdict()))
        print("    " + first_text.format(**item.__dict__)+ ":")

def report_relation(title, src, first_text, attr_name, second_text):
    print(f"{title}: ({len(src)})")

    for item in src:
#            print(first_text.format(**item._asdict()))
        print("    " + first_text.format(**item.__dict__)+ ":")

        for rec in getattr(item, attr_name):
            print("       " + second_text.format(**rec.__dict__))

async def report():
#        print(await MapItem.first())
#        print(await MapItem.filter(area_id="US_09_01").values("id", "name", "x", "y"))
#    print("RU_04_04 crafts")
#    print(await MapItem.filter(area_id="RU_04_04", item_type="craft").first().prefetch_related("cargo_items").values("name", "cargo_items__name", "cargo_items__craft_desc"))
#        report_relation("US_16_01 sources", await MapItem.filter(area_id="US_16_01", item_type="source").prefetch_related("cargo_items"), "{name}, ({x}, {y})", "cargo_items", "{name}")
#    report_relation("US_16_01 trucks", await MapItem.filter(area_id="US_16_01", item_type="truck").prefetch_related("obj_items"), "{name}, ({x}, {y})", "obj_items", "{name}, ({x}, {y})")
#        report_relation("US_16_01 map items", await MapItem.filter(area_id="US_16_01").prefetch_related("cargo_items"), "{name}, {item_type}", "cargo_items", "{name}, {craft_desc}")
#    report_relation("US_09_01 map source items", sorted(await MapItem.filter(area_id="US_09_01", item_type="source").prefetch_related("cargo_items"), key=lambda x: x.name), "{name}, {item_type}, ({x},{y}), locker: {obj_locker_id}", "cargo_items", "{name}")
    report_singles("US_09_01 map gate items", sorted(await MapItem.filter(area_id="US_09_01", item_type="gate"), key=lambda x: x.name), "{name}, {item_type}, ({x},{y}), locker: {obj_locker_id}")
    report_singles("US_09_02 map gate items", sorted(await MapItem.filter(area_id="US_09_02", item_type="gate"), key=lambda x: x.name), "{name}, {item_type}, ({x},{y}), locker: {obj_locker_id}")
    report_singles("RU_17_01 map gate items", sorted(await MapItem.filter(area_id="RU_17_01", item_type="gate"), key=lambda x: x.name), "{name}, {item_type}, ({x},{y}), locker: {obj_locker_id}")
    report_singles("RU_17_02 map gate items", sorted(await MapItem.filter(area_id="RU_17_02", item_type="gate"), key=lambda x: x.name), "{name}, {item_type}, ({x},{y}), locker: {obj_locker_id}")
#    print("US_09_01 obj_items")
#    print(await Objective.filter(area_id="US_09_01",).first().prefetch_related("obj_items").values("id", "name", "obj_items__name", "obj_items__deliver_loc_name"))
#        print(await Objective.filter(area_id="US_09_02",).prefetch_related("obj_items").filter(obj_items__item_type="truck").first().values("id", "name", "obj_items__item_type", "obj_items__name", "obj_items__deliver_loc_name", "obj_items__x"))
    print("Objective items with positions:", await Objective.all().prefetch_related("obj_items__deliver_loc").filter(obj_items__deliver_loc__x__isnull = False).count())
#    print("US_16_01 Objective items with positions:", await Objective.filter(area_id="US_16_03").prefetch_related("obj_items").filter(obj_items__x__isnull = False).count())
#        print("Objective items with positions:")
#    report_relation("Objective items with positions US_16_01", await MapItem.filter(area_id="US_16_01").prefetch_related("obj_items"), "{name}, ({x}, {y})", "obj_items", "{name}, {deliver_loc_name}: ({x}, {y})")
#    report_relation("Objective items with positions US_02_03", await MapItem.filter(area_id="US_02_03").prefetch_related("obj_items__deliver_loc"), "{name}, ({x}, {y})", "obj_items", "{name}, {deliver_loc__name}: ({x}, {y})")
#    report_relation("Objective items with positions US_16_03", await MapItem.filter(area_id="US_16_03").prefetch_related("obj_items"), "{name}, ({x}, {y})", "obj_items", "{name}, {deliver_loc_name}: ({x}, {y})")

    report_relation("Objectives with items US_02_03", await Objective.all().order_by("name").prefetch_related("obj_items__deliver_loc").filter(obj_items__deliver_loc__area_id="US_02_03").distinct(), "{name}", "obj_items", "{name}")

    report_relation("Objective prereqs US_09_02_SEISMO_SCOUT_CONTRACT", await Objective.filter(id="US_09_02_SEISMO_SCOUT_CONTRACT").prefetch_related("obj_prereqs"), "{id}, {name}", "obj_prereqs", "{id}")
    report_relation("Objective prereqs US_02_03_DRILL_DELIVERY_OBJ", await Objective.filter(id="US_02_03_DRILL_DELIVERY_OBJ").prefetch_related("obj_prereqs"), "{id}, {name}", "obj_prereqs", "{id}")
#    report_relation("Map objective items FAILED_MOVE_01", await MapItem.filter(id="FAILED_MOVE_01").prefetch_related("obj_item"), "{id}, {name}", "obj_item", "{name}")
#        report_relation("Map US_16_01 objective items", await MapItem.filter(area_id='US_16_01').prefetch_related("obj_items"), "{id}, {name}, ({x}, {y})", "obj_items", "{name}, ({x}, {y})")

#        print(await MapItem.all().values_list("id", flat=True))

#    report_singles("Source items outside area", await Objective.all().prefetch_related("obj_items__map_item").exclude(area_id = F("obj_items__map_item__area_id")), "{id}, {area_id}, {obj_items__map_item__area_id}, {name}")
#    report_singles("Source items outside area", await Objective.all().prefetch_related("obj_items__map_item").exclude(area_id = F("obj_items__map_item__area_id")), "{id}, {area_id}, {obj_items.map_item.area_id}, {name}")
#    ic(await Objective.all().prefetch_related("obj_items__map_item").exclude(area_id = F("obj_items__map_item__area_id")) \
#        .values_list("id", "area_id", "obj_items__map_item__area_id", "name"))
#    print(await Objective.all().prefetch_related("obj_items__map_item").filter(Q(area_id=area_id) | Q(obj_items__map_item__area_id=area_id)) \


async def run(area_id_filter=None) -> None:
    await Tortoise.init(db_url=snowplanner_db_url, modules={"models": ["__main__"]})
    await Tortoise.generate_schemas()

    await report()


if __name__ == "__main__":
    print(Style.RESET_ALL)
    run_async(run())

