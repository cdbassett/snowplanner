#!/usr/bin/env python3
from snowrunner_utils import *
from text_data_utils import *


ed = get_english_lang_dict()
cargo_list = []

for in_cargo in read_snowrunner_data_tsv_file("cargo_from_gamefiles.generated.tsv"):
    area_id, loc, type, cargo = in_cargo

    if type == "Storage":
        base = region_area(ed, area_id) + (loc,)

        for cnt, cname in map(parse_cargo_count, cargo.split("|")):
            if not cnt:
                cargo_list.append((cname,) + base)

cargo_list = sorted(cargo_list)
#write_snowrunner_tsv_file("all_cargo_by_cargo.generated.tsv", cargo_list)

#write_hierarchical_text(make_snowrunner_doc_path("snowrunner_garage_cargo_by_cargo.txt"), lines)

with open_snowrunner_data_text_file_for_writing("all_cargo_by_cargo.generated.txt") as out_f:
    write_hierarchical_text_to_file(out_f, cargo_list)




