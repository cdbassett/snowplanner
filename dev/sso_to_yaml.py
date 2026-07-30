#!/usr/bin/env python3
import pprint

from icecream import ic
# Set a custom width for indentation and wrapping (default is usually 80)
ic.configureOutput(argToStringFunction=lambda val: pprint.pformat(val, width=192))

from snowrunner_utils import *


ed = get_english_lang_dict()

for area_id, python_data in fname_to_area_id_it(iterate_objective_files_basic()):
    region, area = region_area(ed, area_id)
    write_snowrunner_data_yaml_file(f"{area_id} obj - {region} = {area}.generated.yaml", python_data)

for area_id, python_data in fname_to_area_id_it(iterate_level_files_basic()):
    region, area = region_area(ed, area_id)
    write_snowrunner_data_yaml_file(f"{area_id} level - {region} = {area}.generated.yaml", python_data)

