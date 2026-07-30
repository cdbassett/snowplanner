#!/usr/bin/env python3
import itertools
from pathlib import Path

from icecream import ic
from colorama import Fore, Style

from snowrunner_utils import *

ed = get_english_lang_dict()

def gen_level(base, start):
    for r in itertools.count(start):
        region_id = f"{base}_{r:0>2d}"

        if not (region := ed.get(region_id)):
            if r > 40:
#                print(f"Stopping area for region {region_id} at {area_id}")
                #            print(f"Stopping region for {base} at {region_id}")
                break

            continue

        for a in itertools.count(1):
            area_id = f"{region_id}_{a:0>2d}"
            try:
                region, area = region_area(ed, area_id)
            except KeyError:
#                print(f"Stopping area for region {region_id} at {area_id}")
                break

            yield region_id, region, area_id, area, area_acronym(area)

def main():
    recs = []

    for base, start in zip(("US", "RU"), (1,2)):
        recs.extend(gen_level(base, start))

    recs = sorted(recs, key=itemgetter(1,3))

    all_areas = list(map(itemgetter(3), recs))
    assert len(all_areas) == len(set(all_areas)), "Area names are not unique across regions! (code using stored dictionaries assumes it is)"


    # fix duplicate abbreviations
    def abbrevs_ok(reg_recs):
        abbrevs = list(map(itemgetter(4), reg_recs))

        if len(set(abbrevs)) < len(abbrevs):
            return False, abbrevs

        return True, abbrevs

    def fix_abbrev(reg_rec):
        if ctr[reg_rec[4]] > 1:
            reg_rec = list(reg_rec)
            reg_rec[4] = reg_rec[3][:2]
            reg_rec = tuple(reg_rec)

        return reg_rec

    fixed_recs = []

    for region, reg_recs in itertools.groupby(recs, itemgetter(1)):
        reg_recs = list(reg_recs)
        ok, abbrevs = abbrevs_ok(reg_recs)

        if not ok:
            print(f"Non-unique abbreviations found in {region}:")
            print(f"\t{abbrevs}:")
            areas = list(map(itemgetter(3), reg_recs))
            print(f"\t{areas}:")

            ctr = Counter(abbrevs)
            reg_recs = list(map(fix_abbrev, reg_recs))
            ok, abbrevs = abbrevs_ok(reg_recs)
            print("New abbreviations:")
            print(f"\t{abbrevs}:")
            assert ok

        fixed_recs.extend(reg_recs)

    recs = fixed_recs

    with open_snowrunner_data_text_file_for_writing(f"snowrunner_region_area.tsv") as out_f:
        for info in recs:
            print("\t".join(info), file=out_f)

    with open_snowrunner_data_text_file_for_writing("all_locations_list.txt") as out_f:
        for region, reg_recs in itertools.groupby(recs, itemgetter(1)):
            print(region, file=out_f)

            for area, area_recs in itertools.groupby(reg_recs, itemgetter(3)):
                print(f"\t{area}", file=out_f)

if __name__ == "__main__":
        main()
