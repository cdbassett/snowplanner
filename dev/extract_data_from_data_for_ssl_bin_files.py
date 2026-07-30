#!/usr/bin/env python3
import sys
from itertools import chain, islice
from operator import itemgetter
from collections import Counter, defaultdict, namedtuple

from construct import *
#from tabulate import tabulate
#import pandas as pd
from icecream import ic
from colorama import Fore, Style


#from utilities import ReadFile
from snowrunner_utils import *

dfs_string = PascalString(Int16ul, "utf8")

coord = Float32l
coord_cnt = 12 * 4 // coord.sizeof()


item_struct = Struct(\
    "item_id" / dfs_string,
    "task_id" / dfs_string,
    "some_floats" / coord[coord_cnt],
    "unknown" / Byte[17],
    "masks" / Int32ul[6], # seems to be always FF FF 7F 7F or 7F FF FF 7F 7F, the same value sacrsoss trucks
    "cargo_cnt" / Int32ul,
    "cargo_strings" / dfs_string[this.cargo_cnt],
    "unknown_strings" / dfs_string[7], # 3 * 7 = 21
    "unknown_num" / Int32ul,
    "unknown_string" / dfs_string,
    "dummy" / Byte[18],
    )


dfs_struct = Struct(\
    "magic" / OneOf(Int32ul, (0x13415BE, 20190655)),
    "hdr1" / Int32ul[1],
    "filesize" / Int32ul,
    "hdr2" / Int32ul[1],
    "hdr3" / Int16ul[3],
    "name_id" / dfs_string,
    "name_desc_id" / dfs_string,
    "night_day_strings" / dfs_string[8],
    "night_day_last" / Switch(this.magic, { 0x13415BE: dfs_string, 20190655: Int32ul }),
    "sky_id" / dfs_string,
    "sky_sound_id" / dfs_string,
    "item_cnt" / Int32ul,
    "item_list" / item_struct[this.item_cnt],
    "after_trucks1" / Int32sl, # 4 in 1/5 lvels examined, rest were -1
    "after_trucks2" / Int32sl, # 150-220
    "after_trucks3" / Byte[24], # repeated acros 5 levels
    "after_trucks" / Int32ul[32], # seems to be 4 byte value until prox 1390576 (us_16_01) 1390032 (us_01_01)
    )




bin_dir = Path(snowrunner_data_for_ssl_dir)

def clear(s):
    return s[:-1]

def to_camel_case(snake_str):
    # Split by underscore and capitalize each part
    components = snake_str.split('_')
    if components[-1].isnumeric():
        components = components[:-1]
    return ''.join(x.title() for x in components)

def main():
    ed = get_english_lang_dict()
    truck_id_lookup = dict(map(itemgetter(1,2), read_snowrunner_data_tsv_file("snowrunner_truck_trailer_info.generated.tsv")))

    records = []

    for bin_path in bin_dir.glob("level_??_??_??_data_for_ssl.bin"):
        print(bin_path.name)

        with open(bin_path, "rb") as in_file:
            parsed = dfs_struct.parse_stream(in_file)

            for n, item in enumerate(parsed.item_list):
                task_id, item_id = clear(item.task_id), clear(item.item_id)
                ui_desc = truck_id_lookup.get(item_id)

                if ui_desc: # in testing, not existing was rare and when it didn't, maprunner also didn't show it (trailers)
                    cargo_string = ""
                    if item.cargo_cnt:
#                        if item.cargo_strings[0].startswith("cargo"):
#                            assert all(cargo_string.startswith("cargo") for cargo_string in item.cargo_strings)
                        cargos = [clear(cargo_string) for cargo_string in item.cargo_strings if cargo_string.startswith("cargo")]

                        if cargos:
                            cargos = list(map(to_camel_case, cargos))
                            cargos = [cname for cargo in cargos if (cname := cargo_names_dict.get(cargo, cargo))]

                            if cargos:
                                cargo_counts = Counter(cargos)
                                cargo_string = "|".join(counted_cargo(cnt, cname) for cname, cnt in cargo_counts.items())
#                            ic(ui_desc, cargos)
                                ic(ui_desc, cargo_string)
#                    cargo_list = [counted_cargo() ]

                    records.append([bin_path.name[6:14].upper(), task_id, item_id, ui_desc.upper(), ed[ui_desc.upper()], str(n), cargo_string])
#                print(f"    {item.item_id}: {item.task_id}, {item.unknown_string}")



    if records:
        write_snowrunner_data_tsv_file("level_items_list.generated.tsv", records)

        # fill map_positions with dummy entries if they don't already have one so it can show up in app to be assigned a position
        map_item_positions = get_map_item_positions()
        regions_by_area = get_regions_by_area()
#        truck_id_lookup = dict(map(itemgetter(1, 2), read_snowrunner_tsv_file("snowrunner_truck_trailer_info.generated.tsv")))

        for fname, recs in itertools.groupby(records, itemgetter(0)):
            region, area = region_area(ed, fname)
            map_item_positions_area = get_or_set(map_item_positions, area, dict)
            recs = list(recs)
#            trucks = list(map(itemgetter(4), recs))
#            if len(trucks) != len(set(trucks)):
#                print(f"Warning, duplicate trucks found in {region}, {area}!")

            for item_rec in recs:
                if not item_rec[1]: # not part of an objective
#                    truck = truck_id_lookup[item_rec[2]]
                    truck = f"{item_rec[4]}|{item_rec[-1]}"

                    if not (existing := map_item_positions_area.get(truck)):
                        map_item_positions_area[truck] = "Unknown"

        write_snowrunner_data_yaml_file(f"snowrunner_map_item_positions.yaml", convert_area_dict_to_region_area(map_item_positions, regions_by_area))

if __name__ == "__main__":
    main()

