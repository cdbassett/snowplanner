import itertools
from operator import itemgetter

from icecream import ic

def get_line_level(line):
    line = line.replace("└── ", "    ").replace("\t", "    ")
    len_dif = len(line) - len(line.lstrip())
    return len_dif // 4

def read_hierarchical_text(fpath):
    with open(fpath) as in_file:
        lines = list(in_file)
        part_count = max(map(get_line_level, lines))+1
        parts = [""] * part_count
        last_part = part_count - 1

        for line_no, line in enumerate(lines, 1):
            line_level = get_line_level(line)
            line = line.strip()
            try:
                parts[line_level] = line
            except IndexError:
                ic(parts,line_level,line)
                raise

            if line_level == last_part:
                yield tuple(parts)


def write_hierarchical_text_to_file(out_file, lines):
    def one_gen(input, level):
        indent = "    " * level

        if level == last_part:
            try:
                for part in input:
                    yield indent + part[last_part]
            except TypeError:
                ic(part, level)
                raise
        else:
            for part, recs in itertools.groupby(input, getters[level]):
                yield indent + part
                yield from one_gen(recs, level+1)

    part_count = len(lines[0])
    last_part = part_count-1
#    ic(part_count)
    getters = [itemgetter(n) for n in range(part_count)]

    for line in one_gen(lines, 0):
        print(line, file=out_file)


def write_hierarchical_text(fpath, lines):
    with open(fpath, mode="w", encoding="utf-8") as out_file:
        write_hierarchical_text_to_file(out_file, lines)
