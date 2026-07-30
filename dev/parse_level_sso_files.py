#!/usr/bin/env python3
from icecream import ic

from snowrunner_utils import *


def stored_cargo_desc(cargo):
    cnt = cargo.get('count')
    if cnt == -1: cnt = None
    return counted_cargo(cnt, cargo_names_dict.get(cargo['name']))

def main():
    def es(s):
        return ed.get(s) or s

    ed = get_english_lang_dict()
    cargo_records = []
    gate_records = []
    watchtower_records = []
    all_props = set()

    for fname, python_data in iterate_level_files_basic():
        print(fname)

        for loc_id, dct in python_data["zoneDesc"].items():
            s = ed.get(loc_id, loc_id)
            props = dct.get("props")
            cargo_rec = None

            if props:
                all_props.update(props.keys())

                if (sub_prop := props.get("ZonePropertyGateway")):
                    to_level, to_loc = sub_prop["levelZoneLink"].split(" || ")
                    to_level = to_level[:14]

                    camera_pos = ",".join(list(map(str, sub_prop["cameraPos"].values()))[:3])
                    gate_records.append([fname[:14], loc_id, to_level, to_loc, camera_pos])
                elif (sub_prop := props.get("ZonePropertyWatchpoint")):
                    try:
                        camera_pos = ",".join(list(map(str, sub_prop["cameraPosStart"].values()) )[:3])
                    except TypeError:
                        ic(sub_prop)
                        raise
                    watchtower_records.append([fname[:14], loc_id, camera_pos])
                elif (sub_prop := props.get("ZonePropertyCargoLoading")):
                    cargo_rec = ["Storage", "|".join(map(stored_cargo_desc, sub_prop["cargosSettings"]))]
                elif (sub_prop := props.get("ZonePropertyStorehouseCraft")):
                    cargo_rec = ["Crafting", "|".join(map(crafted_cargo_desc, sub_prop["craftSettings"]))]
                elif "ZonePropertyUpgradesGiver" in props:
                    pass

            if cargo_rec:
                cargo_records.append([fname[:14], loc_id] + cargo_rec)


    if cargo_records:
        write_snowrunner_data_tsv_file("cargo_from_gamefiles.generated.tsv", cargo_records)

    if gate_records:
        write_snowrunner_data_tsv_file("gates_from_gamefiles.generated.tsv", gate_records)

    if watchtower_records:
        write_snowrunner_data_tsv_file("watch_tower_positions_from_gamefiles.generated.tsv", watchtower_records)


if __name__ == "__main__":
    main()



