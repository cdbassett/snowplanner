#!/usr/bin/env python3
from snowrunner_utils import *
from text_data_utils import *


def remap(line):
#    return (line[-1],) + line[:-1]
    return line[-1:] + (", ".join(line[:2]),) + line[2:-1]

lines = list(read_hierarchical_text(make_snowrunner_data_path("snowrunner_garage_cargo_by_location.txt")))
#print(lines)
lines = sorted(map(remap, lines))

with open_snowrunner_data_text_file_for_writing("snowrunner_garage_cargo_by_cargo.generated.txt") as out_f:
    write_hierarchical_text_to_file(out_f, lines)

