#!/usr/bin/env python3
import os
import csv
import re
from collections import namedtuple

from icecream import ic

from snowrunner_utils import *


Cargo_old = namedtuple("Cargo", "region,area,location,cargos")
Cargo = namedtuple("Cargo", "region,area,location,cargos,url")

#re_base_location = re.compile(r"\*?([NEWS]{1,2}\s)?(.+?)(\s[A-Z])?\s*\(([\.\d]+,\s*[\.\d]+)\)?")
re_base_location = re.compile(r"\*?(?:[NEWS]{1,2}\s)?(?:First |Second |Third )?(.+?)?(\s[NEWS]{1,2})?\s*\(([\.\d]+,\s*[\.\d]+)\)?")
#re_base_location = re.compile(r"\*?(?:[NEWS]{1,2}\s)?(.+?)?(\s[NEWS]{1,2})?\s*\(([\.\d]+,\s*[\.\d]+)\)?")
re_base_cargo = re.compile(r"\*?(?:\d+\s)?(.+)")


def strip_location(location):
    if (m := re_base_location.match(location)):
        return m.group(1).strip()

    return location

def strip_cargo(cargo):
    if (m := re_base_cargo.match(cargo)):
        return m.group(1).strip()

    return cargo


def strip_cargos(cargos):
#    parsed =
#    if not cargos.startswith("Wooden") and not cargos.startswith("Bricks") and not cargos.endswith("Logs") and not cargos == "Metal Beams [2]":
#        ic(cargos, list(parse_cargo(cargos, skip_star=False)))
    return "_".join(map(strip_cargo, parse_cargo(cargos, skip_star=False)))


def make_key(row):
    region,area,location,cargos,*_ = row
    key = f"{region.strip()}-{area.strip()}-{strip_location(location)}-{strip_cargos(cargos)}"
    return key

def main(old_fname, new_fname, final_fname):
    with open(old_fname) as old_csvFile, open(new_fname) as new_csvFile, open(final_fname, mode="w", newline='') as final_csvFile:
        old_csvreader = csv.reader(old_csvFile, delimiter="\t")
        new_csvreader = csv.reader(new_csvFile, delimiter="\t")
        final_csvwriter = csv.writer(final_csvFile, delimiter="\t")

        dbg_area = "Flooded Foothills"
        dbg_area = None
#        dbg_area = "Black Badger Lake"
#        dbg_area = "Duncan Bay"

        lookup = {}
        regions = set()
        print("Old:")

        for row in old_csvreader:
            try:
                region,area,location,cargos = row
            except ValueError:
                ic(row)
                raise

            if dbg_area:
                if area.strip() == dbg_area and not location.endswith("framing") and not cargos == "Metal Beams [2]":
                    key = make_key(row)
                    lookup[key] = row
                    regions.add(region)
                    ic(location,strip_location(location),key)
            else:
                key = make_key(row)
                lookup[key] = row
                regions.add(region)


        output = []
        unfound = []
        print("New:")

        for row_count, row in enumerate(new_csvreader):
            region,area,location,cargos,url = row

#            if region == "Alaska":
#            if area == "Mountain River":

            if region in regions:
                key = make_key(row)

#                if area == "Grainwoods River" and not location.endswith("framing"):
#                    ic(location,strip_location(location),cargos,key)

                if (old_row := lookup.get(key)):
                    location = old_row[2].strip()
                elif not location.endswith("framing"):
                    unfound.append(row)

                    if (not dbg_area or area.strip() == dbg_area) and not location.endswith("framing") and not cargos == "Metal Beams [2]":
#                    if not location.endswith("framing") and not cargos == "Metal Beams [2]":
                        ic(location,strip_location(location),key)

#            cargo = Cargo(row)
#            print("\t".join(row), file=final_csvFile)
#            print("\t".join((region,area,location,cargos,url)), file=final_csvFile)
            output.append((region,area,location,cargos,url))

        final_csvwriter.writerows(output)

        ic(row_count)
        ic(len(unfound))


if __name__ == "__main__":
    "Merge newly downloaded cargo list and existing one, matching and transferring x, y, url, location name modifications"
    main(make_snowrunner_data_path("snowrunner_cargo_reformatted_org.tsv"), make_snowrunner_data_path("snowrunner_cargo_reformatted.tsv"), make_snowrunner_data_path("snowrunner_cargo.tsv"))

