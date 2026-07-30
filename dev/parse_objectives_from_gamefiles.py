#!/usr/bin/env python3
import itertools

from colorama import Fore, Style

from snowrunner_utils import *
from text_data_utils import *


def sq(s):
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]

    return s

re_cargo_words = re.compile(r"([\w\s]+)")


def main():
    truck_lookup = dict(map(itemgetter(1, 2), read_snowrunner_data_tsv_file("level_items_list.generated.tsv")))
    truck_id_lookup = dict(map(itemgetter(1, 2), read_snowrunner_data_tsv_file("snowrunner_truck_trailer_info.generated.tsv")))

    def process_type(fname, objective_type, tasksSettings, indent, missing):
        cur_task_id, cur_loc, cur_item = None, None, None
        region, area = region_area(ed, fname)
        deliveries = []

        for task_id, task in tasksSettings.items():
#            print(f"{indent}{task_id}: {Style.BRIGHT}{Fore.YELLOW}{ed[task_id]}{Style.RESET_ALL}")
            if (stages := task.get("stages")):
                for stage in stages:
                    if (actions := stage.get("actions")):
                        if (zoneToFill := actions.get("zoneToFill")) and (cur_zone := zoneToFill[0].get('uiDesc')):
                            for zone in zoneToFill:
                                to_area = zone["globalZoneId"]["globalZoneId"].split(" || ")[0]

                                if (cargo := zone.get("cargo")):
                                    cname = cargo['name']

                                    if not cargo_names_dict.get(cname):
                                        missing.append((fname, objective_type, task_id, cur_zone, cname))

                                    deliveries.append((region_area(ed, to_area)[1], task_id, zone.get('uiDesc') or cur_zone, "cargo", f"{cargo['count']} {cargo_name(cname)}", cname))

                    if (truckDeliveries := stage.get("truckDelivery")):
                        cur_zone = truckDeliveries[0]['uiDesc']
#                    print(f"\t\t{delivery_location(ed[truckDeliveries[0]['uiDesc']])}")

                        for truckDelivery in truckDeliveries:
                            to_area = truckDelivery["globalZoneDeliveryId"]["globalZoneId"].split(" || ")[0]
                            deliveries.append((region_area(ed, to_area)[1], task_id, cur_zone, "truck", ed[truck_id_lookup[truck_lookup[truckDelivery['truckId']]].upper()], truckDelivery['truckId']))

#                        print(f"\t\t\t{es(truckDelivery['truckId'])}")


        if 0:
            for task_id, trecs in itertools.groupby(deliveries, lambda r: r[0]):
                print(f"{indent}{Style.BRIGHT}{Fore.YELLOW}{ed[task_id]}{Style.RESET_ALL}")

                for loc, lrecs in itertools.groupby(trecs, lambda r: r[1]):
                    print(f"{indent}\t{delivery_location(ed[loc])}")

                    for _, _, item in lrecs:
                        print(f"{indent}\t\t{item}")

        return deliveries

    def es(s):
        return ed.get(s) or s

    ed = get_english_lang_dict()
    missing = []
    indent = "\t\t"
    all_deliveries = []

    for fname, python_data in sorted(iterate_objective_files_basic()):
        print(f"{fname}: {': '.join(region_area(ed,fname))}:")
        for typ, desc in zip(("tasksSettings", "contractsSettings"), ("Task", "Contract")):
            deliveries = process_type(fname, desc, python_data[typ], indent, missing)

            for delivery in deliveries:
                if not delivery[0].startswith("test"):
                    all_deliveries.append((fname, desc) + region_area(ed,fname)[:1] + delivery)

    if missing:
        print("Missing:")
        for fname, objective_type, task_id, zone, cname in missing:
            print(f"    {fname} {' '.join(region_area(ed,fname))}: {objective_type}: {ed[task_id]}: {ed[zone]} {Style.BRIGHT}{Fore.RED}{cname}{Style.RESET_ALL}")

    write_snowrunner_data_tsv_file("all_deliveries_list.generated.tsv", all_deliveries)

    def task_from_rec(rec):
        return f"{ed[rec[4].upper()]} ({rec[1][0]})"

    for region, recs in itertools.groupby(all_deliveries, lambda r: r[2]):
        recs = list(recs)

        with open_snowrunner_data_text_file_for_writing(f"{region} Deliveries By Location.generated.txt") as out_f:
            try:
                area_recs = sorted(((rec[3], delivery_location(ed[rec[5]]), task_from_rec(rec),  rec[-2]) for rec in recs))
            except KeyError:
                ic(area_recs)
                raise

#            ic(region, len(area_recs))
            write_hierarchical_text_to_file(out_f, area_recs)


        with open_snowrunner_data_text_file_for_writing(f"{region} Deliveries By Cargo.generated.txt") as out_f:
            try:
                new_recs = [(parse_cargo_count(rec[-2]) + (rec[3], delivery_location(ed[rec[5]]), task_from_rec(rec), rec[6])) for rec in recs if rec[6]=="cargo"]
                area_recs = sorted(((rec[1], rec[2], rec[3], counted_cargo(rec[0], rec[4])) for rec in new_recs))
            except KeyError:
#                    ic(area_recs)
                raise

            write_hierarchical_text_to_file(out_f, area_recs)


if __name__ == "__main__":
    main()



