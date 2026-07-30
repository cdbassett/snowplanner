import os
import io
import re
import csv
from pathlib import Path
from lxml import etree
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict, namedtuple
import itertools
import functools
import random

from xmldiff import main as xml_main, formatting, patch, actions as xml_actions
from icecream import ic

from utils.utilities import ReadFile, FileCache, read_tsv_file
from utils.iter_utils import arithtuple
from utils.text_data_utils import *
from utils.yaml_utils import *

snowrunner_main_dir = Path(__file__).resolve().parent.parent

snowrunner_doc_dir = Path("~/Documents/SnowRunner").expanduser()
snowrunner_doc_dir.mkdir(exist_ok=True)
snowrunner_data_dir = snowrunner_main_dir / "data"
snowrunner_initial_pak_dir = snowrunner_doc_dir / "initialpak"
snowrunner_initial_pak_dir = "/mnt/nas_docs/Games/snowrunner/initialpak"
snowrunner_data_for_ssl_dir = snowrunner_doc_dir / "data_for_ssl_files"
snowrunner_data_for_ssl_dir = "/mnt/nas_docs/Games/snowrunner/data_for_ssl_files"

def make_snowrunner_doc_path(fname):
    return os.path.join(snowrunner_doc_dir, fname)


def make_snowrunner_data_path(fname):
    return os.path.join(snowrunner_data_dir, fname)


def open_snowrunner_data_text_file_for_reading(fname):
    return open(os.path.join(snowrunner_data_dir, fname), encoding="utf-8")

def open_snowrunner_data_text_file_for_writing(fname):
    return open(os.path.join(snowrunner_data_dir, fname), mode="w", encoding="utf-8")


def write_snowrunner_data_tsv_file(fname, data):
    with open_snowrunner_data_text_file_for_writing(fname) as out_f:
        for line in data:
            print("\t".join(line), file=out_f)

def read_snowrunner_data_tsv_file(fname):
    with open_snowrunner_data_text_file_for_reading(fname) as in_f:
        reader = csv.reader(in_f, delimiter="\t")
        yield from reader


def read_snowrunner_data_yaml_file(fname):
    with open_snowrunner_data_text_file_for_reading(fname) as in_f:
        data = yaml.safe_load(in_f)

    return data

def write_snowrunner_data_yaml_file(fname, data):
    with open_snowrunner_data_text_file_for_writing(fname) as out_f:
        outputYAMLtoOpenFile(out_f, data)


abbreviations_cache = FileCache(make_snowrunner_data_path("abbreviations.tsv"), lambda fname: dict(read_tsv_file(fname)))

def abbreviate_line(s):
    word_abbreviations, cached = abbreviations_cache.get_content(True)
#    if not cached:
#        print("abbreviate_line refresh")
#        ic(word_abbreviations)

    def proc_word(s):
        if (t := word_abbreviations.get(s.lower())):
            return (t[0].upper() if s[0].isupper() else t[0].lower()) + t[1:]

        return s

    return " ".join(map(proc_word, s.split()))


def convert_region_area_dict_to_area(dct):
    return dict((k.split("|")[1], d) for k, d in dct.items())

def convert_area_dict_to_region_area(dct, regions_by_area):
    return dict((f"{regions_by_area[k]}|{k}", d) for k, d in dct.items())


def convert_to_simple_dicts(dct):
    return dict((k, dict(d)) for k, d in dct.items())


def convert_to_defaultdicts(dct, typ):
    return dict((k, defaultdict(typ, d)) for k, d in dct.items())

def convert_to_dict(it, key_idx, val_idx):
    return dict(map(itemgetter(key_idx, val_idx), it))

# act like defaultdict in a regular dict
def get_or_set(dct, key, func):
    if not (value := dct.get(key)):
        value = dct[key] = func()

    return value

# [area][location name] = pos
def get_location_positions():
    return convert_region_area_dict_to_area(read_snowrunner_data_yaml_file("snowrunner_location_positions.yaml"))

def get_location_position_area(location_positions_area, location):
    try:
        return location_positions_area[location]
#    except TypeError:
#        ic(location)
#        raise
    except KeyError:
        return None

def get_location_position(location_positions, area, location):
    return get_location_position_area(location_positions[area], location)

def get_random_pos_1_axis():
    return (random.random() * 0.8) + .1

def get_random_position():
    return f"{get_random_pos_1_axis()},{get_random_pos_1_axis()}"



# parse individual cargo items out of all in one line from maprunner.info uses

def parse_cargo(cargos, skip_star = True):
    built = []

    for s in cargos.split():
        built.append(s)

        if s.endswith("]") or s == "Logs":
            item = " ".join(built)

            if not skip_star or not item.startswith("*"):
                yield item

            built = []

    if built:
        yield " ".join(built)

re_cargo_count = re.compile(r"(\d+)\s*(.+)")
re_cargo_count2 = re.compile(r"(.+?)\s+x(\d+)")

def parse_cargo_count(cargo):
    if (m := re_cargo_count.match(cargo)):
#        ic(m.groups(1, 2))
        return int(m.group(1)), m.group(2)
    elif (m := re_cargo_count2.match(cargo)):
        return int(m.group(2)), m.group(1)

    return None, cargo

def counted_cargo(cnt, s):
    return f"{(str(cnt)+' ' if cnt else '')}{s}"

def counted_cargo_none(cnt, s):
    return f"{(str(cnt)+' ' if cnt is not None else '')}{s}"


def comment_skipper(it):
    for l in it:
        if l and not l[0].startswith("#"):
            yield l


def region_filterer(it, region):
    for l in it:
        if l[0] == region:
            yield l

def area_id_filterer(it, area_id):
    if area_id:
        for l in it:
            if l[0] == area_id:
                yield l
    else:
        yield from it

def fname_to_area_id_it(it, area_id_filter=None):
    if area_id_filter:
        for line in it:
            area_id = fname_to_area_id(line[0])

            if area_id == area_id_filter:
                yield (area_id,) + tuple(line[1:])
#                yield [area_id] + line[1:]
    else:
        for line in it:
            area_id = fname_to_area_id(line[0])
            yield (area_id,) + tuple(line[1:])
#            area_id = line[0][:8].upper()
#            yield [area_id] + line[1:]

def line_cleaner(line):
#    return tuple(map(str.strip, line))
    return list(map(str.strip, line))

def line_cleaner_iter(it):
    yield from map(line_cleaner, it)


def location_uniquer_iter(it, old=False):
    for (region, area), recs in itertools.groupby(it, itemgetter(0, 1)):
        recs = list(recs)
        ctr = Counter(map(itemgetter(2), recs))
        name_ctr = Counter()

        for rec in sorted(recs):
            parts = rec[2].split("(")
            loc = parts[0].strip()
                # rename if dup names
            if ctr[loc] > 1:
                loc_name = loc + " " + chr(ord("A") + name_ctr[loc])
                name_ctr[loc] += 1
                parts[0] = loc_name

#                if len(parts) > 1:
#                    parts[1] = parts[1].strip()

                # old format still has location in name so has to run after location has been stripped
                if old:
                    rec = rec._replace(loc=" (".join(parts))
#                    ic(rec)
                else:
                    rec[2] = " (".join(parts)

            yield rec

re_percent_loc = re.compile(r"(.+?)\s*\((0?.\d+,\s*0?.\d+)\)")
re_area_percent_loc = re.compile(r"(.+?)\s*\((?:([\w\s]+):\s*)?(0?.\d+,\s*0?.\d+)\)")
re_name_loc = re.compile(r"(.+?)\s*\((?:([\w\s]+):\s*)?([\w\s]+)\)")
re_unique_name = re.compile(r"(.+?)\s[A-Z]$")


# take back off letter used to unique
def strip_unique(s):
    if (m := re_unique_name.match(s)):
        return m.group(1)

    return s

OldCargo = namedtuple("OldCargo", "region,area,loc,pos,cargos,url")
Cargo = namedtuple("Cargo", "region,area,loc,cargos,url")


def get_old_cargo_rec(line):
    parts = line[:3] + [""] + line[3:]

    if (loc_match := re_percent_loc.search(line[2])):
        parts[2:4] = loc_match.groups()

    return OldCargo(*parts)

def get_cargo_rec(line):
    parts = line[:3] + [line[3].split("|")] + line[4:]
#    parts = line[:4] + [line[4]] + line[5:]
#    ic(parts)
    return Cargo(*parts)


def get_cargo_list_iter(region_filter=None, old=False):
    if old:
#        assert not region_filter
        fname = make_snowrunner_data_path(r"snowrunner_cargo.tsv")

        with open(fname) as csvFile:
            reader = csv.reader(csvFile, delimiter="\t")
            reader = line_cleaner_iter(reader)
            reader = comment_skipper(reader)
            if region_filter:
                reader = region_filterer(reader, region_filter)
            reader = map(get_old_cargo_rec, reader)
            reader = location_uniquer_iter(reader, old=True)
            yield from reader
    else:
        fname = make_snowrunner_data_path(r"snowrunner_cargo_new.tsv")

        with open(fname) as csvFile:
            reader = csv.reader(csvFile, delimiter="\t")

            if region_filter:
                reader = region_filterer(reader, region_filter)

            reader = location_uniquer_iter(reader)
            yield from map(get_cargo_rec, reader)




def determine_cargo_pos(cargo_item, location_positions, cur_area, areas_by_abbreviation):
    if (pos_match := re_area_percent_loc.search(cargo_item)):
        cargo_label, match_area,  cur_pos = pos_match.groups()

        if match_area:
#            ic(match_area)
            cur_area = areas_by_abbreviation.get(match_area) or match_area
    elif (loc_match := re_name_loc.search(cargo_item)):
        match_area = loc_match.group(2)

        if match_area:
#            ic(match_area)
            cur_area = areas_by_abbreviation.get(match_area) or match_area
#            cur_area = areas_by_abbreviation.get(area_acronym(match_area)) or match_area

        if (cur_pos := location_positions[cur_area].get(loc_match.group(3))):
            cargo_label = loc_match.group(1)
        else:
            print(f"Couldn't find location '{loc_match.group(3)}' in {cur_area} for {cargo_item}!")
#            ic(areas_by_abbreviation)
            cargo_label, cur_pos = cargo_item, None
    else:
        cargo_label, cur_pos = cargo_item, None

    return cargo_label, cur_area, cur_pos


OldDelivery = namedtuple("Delivery", "area,loc,pos,task,cargo")
Delivery = namedtuple("Delivery", "area,loc,task,cargo")

def get_delivery_list_iter(region, old=False, all_locations=False):
    try:
        if old:
            fname = f"{region} Deliveries.txt"
#            ic(fname)

            with open_snowrunner_data_text_file_for_reading(fname) as deliveries_file:
                try:
                    for line_no, line in enumerate(deliveries_file, 1):
                        if not (line := line.replace("(.,.)", "").rstrip()):
                            continue

                        line_level = get_line_level(line)
                        line = line.strip()

                        if line_level == 0:
                            cur_area = line
                        elif line_level == 1:
                            cur_loc_name, cur_pos = line, None

                            if (loc_match := re_percent_loc.search(line)):
                                cur_loc_name, cur_pos = loc_match.group(1), loc_match.group(2)

                            if all_locations:
                                yield OldDelivery(cur_area, cur_loc_name, cur_pos, None, None)
                        elif line_level == 2:
                            cur_task = line
                        elif line_level == 3:
                            cur_cargo = line.strip()
                            yield OldDelivery(cur_area, cur_loc_name, cur_pos, cur_task, cur_cargo)
                        else:
                            raise Exception(f"Unknown level in {fname}, line {line_no}.")
                except UnboundLocalError:
                    ic(line_level, cur_area, cur_loc_name, cur_pos)
                    raise
        else:
            fname = f"{region} Deliveries_new.txt"

            with open_snowrunner_data_text_file_for_reading(fname) as deliveries_file:
                for line_no, line in enumerate(deliveries_file, 1):
                    if not (line := line.rstrip()):
                        continue

                    line_level = get_line_level(line)
                    line = line.strip()

                    if line_level == 0:
                        cur_area = line
                    elif line_level == 1:
                        cur_loc_name = line
                    elif line_level == 2:
                        cur_task = line.split("|")[0]
                    elif line_level == 3:
                        cur_cargo = line.strip()
                        yield Delivery(cur_area, cur_loc_name, cur_task, cur_cargo)
                    else:
                        raise Exception(f"Unknown level in {fname}, line {line_no}.")

    except FileNotFoundError:
        print(f"Couldn't find file '{fname}', skipping.")


def determine_location_positions(recs, location_positions):
    areas = []

    for area, area_recs in itertools.groupby(recs, lambda r: r.area):
        areas.append(area)

        for area_rec in area_recs:
            if area_rec.pos:
                location_positions[area][area_rec.loc] = area_rec.pos

re_delivery_location = re.compile(r".+?<y>(.+?)</y?>")
re_delivery_location2 = re.compile(r"Deliver to (?:the )?(.+)")

def delivery_location(s):
    if (m := re_delivery_location.match(s)):
        return m.group(1)
    elif (m := re_delivery_location2.match(s)):
        return m.group(1)

    return s


def get_area_abbreviations_and_location_positions(recs, location_positions):
    areas_by_abbreviation, areas = dict(), []

    for area, area_recs in itertools.groupby(recs, lambda r: r.area):
        areas_by_abbreviation[area_acronym(area)] = area
        areas.append(area)

        for area_rec in area_recs:
            if area_rec.pos:
                location_positions[area][area_rec.loc] = area_rec.pos

    assert len(areas) == len(areas_by_abbreviation)
    return areas_by_abbreviation




re_loc = re.compile(r"(.+?)\s*\((?:([A-zAZ]{1,3})\|)?(\w+(?:\-\w+)*)\)")

def convert_compass_to_percent(line):
    def loc_dir_to_xy(positions):
#    ic("loc_dir_to_xy", positions)
        a = loc_dir_map[positions[0]]

        for b in positions[1:]:
            a = a + loc_dir_map[b]

        return a / len(positions)


    loc_dir_map = {
        "C": (1, 1),
#        "Ctr": (1, 1),
        "N": (1, 0),
        "S": (1, 2),
        "W": (0, 1),
        "E": (2, 1),
        }


    loc_dir_map = dict((k, arithtuple(t)) for k, t in loc_dir_map.items())


    for a, b in itertools.product('NS', 'EW'):
        loc_dir_map[a+b] = arithtuple((loc_dir_map[b][0], loc_dir_map[a][1]))


    margin = 0.1
    margin_tuple = (margin, margin)
    double_margin = margin*2
    scale = (1 - margin * 2) / 2 # compass coords are given in range 0-2


    if (loc_match := re_loc.search(line)):
        cur_loc_name, cur_area, cur_loc = loc_match.groups()
        positions = cur_loc.split("-")
        try:
            pos = loc_dir_to_xy(positions)
        except KeyError:
            ic(cur_loc_name, cur_area, cur_loc, positions)
            raise
        use_pos = pos * scale + margin # compass ratios are 0-2, we want 0-1
#        ic(cur_loc_name, cur_area, cur_loc, use_pos)
#        return line[:loc_match.start(2)], f"{round(use_pos[0],4)},{round(use_pos[1],4)}"
        return cur_loc_name, cur_area, f"{round(use_pos[0],4)},{round(use_pos[1],4)}"


def loc_pos_to_xy_percent(positions):
#    ic("loc_dir_to_xy", positions)
    return arithtuple(map(float, positions.split(","))) if positions != "Unknown" else arithtuple((.5,.5))


def third(f):
    return int(3 * f)


def get_compass_repr_of_pos(pos):
    if isinstance(pos, str):
        pos = loc_pos_to_xy_percent(pos)

    try:
        h = "W E"[third(pos[0])]
        v = "N S"[third(pos[1])]
    except IndexError:
        ic(pos)
        raise
    comb = (v + h).strip() or "C"
    return comb

def third_int(i):
#    ic(i, i // 333)
    return i // 333


def get_compass_repr_of_pos_int(pos):
    if pos[0] is None:
        return ""

    try:
        h = "W E"[third_int(pos[0])]
        v = "N S"[third_int(pos[1])]
    except (IndexError, TypeError):
        ic(pos)
        raise
    comb = (v + h).strip() or "C"
    return comb


pos_symbols = dict(zip(
    "N,S,W,E,C,NW,SW,SE,NE".split(","),
#    "⬖⬗⬘⬙▣◰◱◲◳"
#    "▲▼◀▶🞉◰◱◲◳"
#    "▲▼◀▶⚫" + "◤◣◢◥"
    "▲▼◀▶🞉" + "◤◣◢◥"
    ))


#    "⯅⯆⯇⯈"
#print(pos_symbols)


def get_symbol_repr_of_pos(pos):
    compass = get_compass_repr_of_pos(pos)
    return pos_symbols[compass]


def get_extended_repr_of_pos(pos):
    if pos == "Unknown":
        return "(Unknown)"

#    ic(pos)
    return f"({pos} {get_compass_repr_of_pos(pos)} {get_symbol_repr_of_pos(pos)})" if pos else ""


def build_location_names_by_pos(location_positions_area):
    return dict((pos, loc_name) for loc_name, pos in location_positions_area.items())

# [area][pos] = loc_name
def build_all_location_names(location_positions):
    return dict((area, build_location_names_by_pos(location_positions_area)) for area, location_positions_area in location_positions.items())

def get_location_name_or_extended_repr_of_pos(pos, location_names):
    if (loc_name := location_names.get(pos)):
        return f"({loc_name} {get_compass_repr_of_pos(pos)})"

    return get_extended_repr_of_pos(pos)


def get_location_name_or_compass_of_pos(pos, location_names):
    if (loc_name := location_names.get(pos)):
        return f"{loc_name} {get_compass_repr_of_pos(pos)}"

    return get_compass_repr_of_pos(pos)


def DiffFormatter_handle_action(self, action):
    action_type = type(action)
    method = getattr(self, "_handle_" + action_type.__name__)

    with io.StringIO() as csvfile:
        w = csv.writer(csvfile)
        w.writerow(method(action))
        return csvfile.getvalue().strip()

# monkey patch formatter to properly escape attribute values
formatting.DiffFormatter.handle_action = DiffFormatter_handle_action

# we don't want to throw an error when attrib is already there, some manul mods have mistakes like duplciated attributes
def Patcher_handle_InsertAttrib(self, action, tree):
    res = tree.xpath(action.node, namespaces=self.nsmap)
    try:
        node = res[0]
    except IndexError as e:
        ic(action, res)
    # This should not be used to update existing attributes.
#    assert action.name not in node.attrib
    node.attrib[action.name] = action.value


patch.Patcher._handle_InsertAttrib = Patcher_handle_InsertAttrib


def read(fname):
    with open(fname, encoding="utf8") as f:
        return f.read()

def read_path(path):
    with path.open(encoding="utf8") as f:
        return f.read()


def write(fname, s):
    with open(fname, "w", encoding="utf8") as f:
        f.write(s)

# SnowRunner XML is not well-formed, it can contain multiple root elements
# we make it parseable by enclosing in our own root element
def encapsulate(xml):
    # also some ford trucks contain illegal ":" characters in tag names
    return "<root>\n" + xml.replace("region:", "region_") + "\n</root>"

# but then of course we have to undo that
def unencapsulate(xml):
    return "\n".join(xml.replace("region_", "region:").strip().split("\n")[1:-1])

def parse_xml(xml):
#    xml = "\n".join(line.strip() for line in xml.split("\n"))

    parser = etree.XMLParser(ns_clean=True, recover=True, remove_blank_text=True)
#    mod_xml = "<root>\n" + xml + "\n<root/>"
    xml_root = etree.fromstring(xml, parser)

    if 1:
        for elem in xml_root.iter('*'):
            if elem.text is not None:
                elem.text = elem.text.strip()
            if elem.tail is not None:
                elem.tail = elem.tail.strip()
#    ic(xml_root, etree.tostring(xml_root))
    return xml_root

def parse_xml_to_tree(xml):
    xml_root = parse_xml(xml)
    tree = etree.ElementTree(xml_root)
    return tree

def to_xml_string(el):
    return etree.tostring(el, encoding="unicode", pretty_print=True)


def parse_xml_ET(xml):
    return ET.fromstring(xml)

def to_xml_string_ET(el):
    return ET.tostring(el, encoding="unicode")


# this parses xml in recover mode so things like duplicated attributes don't throw an error
def patch_text(actions_string, xml):
    """Takes a string with XML and a string with actions"""
    actions = xml_main.patch.DiffParser().parse(actions_string)
    tree = parse_xml_to_tree(xml)
    new_tree = xml_main.patch_tree(actions, tree)
    new_xml = to_xml_string(new_tree)
    return new_xml

idstring = "_x_id_x_" # something not likely to b e a real attribute since we're kludging in an attribtue to improve matchoign for our purposes

def insert_ids(tree):
    root = tree.getroot()

    for element in tree.getiterator():
        if element.tag is etree.Comment:
            continue

#        ic(element)
        if 0:
            parent = element.getparent()
            # path and tag but not position
            # we want reasonable matches for most cases
            # if and addon isnerts elements of the same type, the diff will jsut have more udpates for that case
            # but everything else will have more minimal updates, deletes, inserts and no renames
            path = (tree.getelementpath(parent) if parent else "") + "/" + element.tag
        else:
            path = tree.getelementpath(element)
        element.set(idstring, path)

def remove_ids(tree):
#    root = tree.getroot()

    for element in tree.getiterator():
        if element.tag is etree.Comment:
            continue

        element.attrib.pop(idstring, None)


def remove_id_attrib_inserts(actions):
#    ic(actions)
    actions = [action for action in actions if not isinstance(action, xml_actions.InsertAttrib) or action.name != idstring]
#    ic(actions)
    return actions


###################################################


def convert_mapping_line(s):
    k, v = s.replace("\t\t", "\t").replace("\t\t", "\t").strip().split("\t")
    return k.upper(), v[1:-1]

@functools.cache
def get_english_lang_dict():
    with open(Path(snowrunner_initial_pak_dir, "[strings]", "strings_english.str"), encoding="utf-16") as english_file:
        lines = list(english_file)
#        print(seq(lines).map(convert_mapping_line).take(10))
#        lines = seq(english_file).map(str.split).list()
#        print(lines[:10])
#        return seq(lines).dict()
        #return seq(lines).map(convert_mapping_line).dict()
        return dict(map(convert_mapping_line, lines))

def area_string(ed, level):
    level = (ed.get("LEVEL_"+level) or ed.get("LEVEL_"+level+"_NAME") or ed.get(level+"_NAME") or ed.get(level+"_NEW_NAME") or ed[level]).split(",")[0]
    return level


def area_acronym(area):
    return "".join(s[0] for s in area.split())

def slugify(s):
    return s.replace(' ', '_').lower()

def slugify_region_area(region, abbrev=None):
    if not abbrev:
        return region.replace(' ', '_').lower()

#    area = area_acronym(area.replace('"', "").replace("\\", "").strip())
    return f"{region}_{abbrev}".replace(' ', '_').lower()


re_level = re.compile(r"(?:level_)?(.._\d\d_\d\d)")

def fname_to_area_id(fname):
    if not (m := re_level.match(fname)):
        ic(fname)
        raise Exception()
        return None, None

    level = m.group(1).upper()
    return level

def region_area(ed, fname):
    level = fname_to_area_id(fname)
    region = level[:5]
    region = ed[region].split(",")[0].strip()
    level = area_string(ed, level).replace('"', "").replace("\\", "").strip()
#        level = (ed.get("LEVEL_"+level) or ed.get("LEVEL_"+level+"_NAME") or ed.get(level+"_NAME") or ed.get(level+"_NEW_NAME") or ed[level]).split(",")[0]
    return region, level



RegionArea = namedtuple("RegionArea", "region_id,region,area_id,area,abbrev,partial_abbrev")

area_reductions = [
    ("Selten River", "SR"),
    ("National Forest", "NF"),
#    ("National Park", "NP"),
    ("North Peak", "NP"),
    ("Nature Reserve", "NR"),
    ("Valley", "V"),
    ("Northern Aegis", "NA"),
    ("Island", "Isl."),
]

def get_abbrev_area(area):
    for area_reduction in area_reductions:
        area = area.replace(*area_reduction)

    return area

def build_region_area(line):
#    return line + [get_abbrev_area(line[-1])]
    return RegionArea(*(line + [get_abbrev_area(line[-2])]))

@functools.cache
def get_region_area_lines():
    fname = make_snowrunner_data_path("snowrunner_region_area.tsv")

    with open(fname) as csvFile:
        reader = csv.reader(csvFile, delimiter="\t")
        lines = tuple(map(build_region_area, reader))
#        lines = tuple(itertools.starmap(RegionArea, reader))

    return lines

def get_areas_by_abbreviation():
    areas_by_abbreviation = dict(map(itemgetter(4,3), get_region_area_lines()))
    return areas_by_abbreviation

def get_abbreviations_by_area():
    areas_by_abbreviation = dict(map(itemgetter(3,4), get_region_area_lines()))
    return areas_by_abbreviation

def get_abbreviations_by_area_id():
    areas_by_abbreviation = dict(map(itemgetter(2,4), get_region_area_lines()))
    return areas_by_abbreviation

def get_regions_by_area():
    areas_by_abbreviation = dict(map(itemgetter(3,1), get_region_area_lines()))
    return areas_by_abbreviation


def get_area_ids_by_area():
    area_ids_by_area = convert_to_dict(get_region_area_lines(), 3, 2)
#    ic(area_ids_by_area)
    return area_ids_by_area

def get_areas_by_area_id():
    area_ids_by_area = convert_to_dict(get_region_area_lines(), 2, 3)
#    ic(area_ids_by_area)
    return area_ids_by_area

#print(get_region_area_lines())

def iterate_region_area():
    yield from get_region_area_lines()


def iterate_region():
    for region, recs in itertools.groupby(iterate_region_area(), lambda r: r.region):
        yield region

def iterate_region_and_ids():
    for region_id, recs in itertools.groupby(iterate_region_area(), lambda r: r.region_id):
        yield list(recs)[0].region, region_id


re_lua_to_json = re.compile(r"\b(\w+)   =   ")
re_commas1 = re.compile(r'(")(\n\s*")')
re_boolean1 = re.compile(r'\bTrue\b')
re_boolean2 = re.compile(r'\bFalse\b')
#re_commas2 = re.compile(r'(["\)\]\}\d]|True|False)(\s*?\n\s*["\(\[\{])')
re_commas2 = re.compile(r'(["\)\]\}\d])(\s*?\n\s*["\(\[\{])')

def parse_sso(s):
    s = "{" + s + "}"

    if 1:

        import json
        converted = re_lua_to_json.sub(r'"\1": ', s)
#        converted = re_commas1.sub(r'\1,\2', converted)
#        print(converted[:1000])
        converted = re_boolean1.sub(r'1', converted)
        converted = re_boolean2.sub(r'0', converted)

        converted = re_commas2.sub(r'\1,\2', converted)
#        for n, s in enumerate(converted[:2000].split("\n"), 1):
#            print(f"{n}: {s}")
        return json.loads(converted)
    else:
        from slpp import slpp
        return slpp.decode(s)


def strip_trailing_obj(s):
    return re.sub("(_obj|_tsk|_contract|_cnt)+$", "", s)


mis_named_obj_files = {
    'US_01_01_BOATMAN_TOOLS_DELIVERY_TSK': "US_01_01_BOATMAN__TOOLS_DELIVERY_TSK",
    'US_01_04_BUILD_A_BRIDGE_OBJ_2': "US_01_04_BUILD_A_BRIDGE_TSK_2",
    'US_01_04_LOST_CARGO_DELIVERY_TSK': "US_01_04_LOST_CARGO_TSK",
    'US_01_04_SUPPLIES_FOR_REGION_2_OBJ': "US_01_04_SUPPLIES_FOR_REGION_OBJ",
    'US_01_03_POWER_WIRES_1_CONTRACT_OBJ': "US_01_03_POWER_WIRES_1_CONTRACT",
}


def iterate_objective_files_basic():
    p = Path(snowrunner_initial_pak_dir) / "[ps]"
    paths = [p / "objective_settings.sso"] + list(p.glob('??_??_??_objects.sso')) + list(p.glob('level_??_??_??_objects.sso'))
#    ic("iterate_objective_files_basic")

    for fpath in paths:
#        ic(fpath)
        fname = fpath.name
        file_text = ReadFile(fpath)
        python_data = parse_sso(file_text)

        # early levels contain a bunch in this file then parcelled out to individual files for individual task
        # so special handlign to make it act like the others
        if fname == "objective_settings.sso":
            broken_out = defaultdict(dict)

            for typ in ("tasksSettings", "contractsSettings", "contestSettings"):
#                ic(python_data[typ].keys())
                for area_id, items in itertools.groupby(python_data[typ].items(), lambda x: x[0][:8]):
                    if area_id.startswith("test"): continue
                    items = list(items)
#                    ic(items)
#                    ic(area_id, typ)
                    area_dict = broken_out[area_id][typ] = dict()
#                    keys = list(map(itemgetter(0), items))
#                    ic(len(keys))
#                    area_dict.update(item for item in items if not item[0].startswith("test"))
                    area_dict.update(items)

                    for objid, obj in area_dict.items():
                        __type = obj.pop("__type")
                        if not obj:
#                            ic("ext", objid)
                            try:
#                            if objid == "RU_02_02_STUCK_TRUCK_02_TSK":
                                fname = mis_named_obj_files.get(objid, objid) + ".sso"
                                obj_data = parse_sso(ReadFile(p / fname))
                                obj.update(obj_data)

#                            if objid == "RU_02_02_STUCK_TRUCK_02_TSK":
#                                ic(obj_data)
#                            ic("read file", objid +".sso")
#                            ic("inserted", objid)
                            except FileNotFoundError: # not all objectives are in separate files
#                                ic(objid)
                                pass
                        if not obj:
                            ic("notfound", objid)

#            ic(fname, len(broken_out.items()))
            for area_id, dct in broken_out.items():
#                ic(fname, area_id, len(dct))
                yield area_id, dct
        else:
            for typ in ("tasksSettings", "contractsSettings", "contestSettings"):
                items = python_data[typ].items()

                for objid, obj in items:
                    try:
#                        if objid == "RU_02_02_STUCK_TRUCK_02_TSK":
#                            ic(objid)
                        obj_data = parse_sso(ReadFile(p / (objid +".sso")))

#                        if objid == "RU_02_02_STUCK_TRUCK_02_TSK":
#                            ic(obj_data)
#                            ic("read file", objid +".sso")
                        obj.update(obj_data)
#                        ic("inserted", objid)
                    except FileNotFoundError: # not all objectives are in separate files
                        pass

            yield fname, python_data


def iterate_objective_files(ed, region_filter=None, area_filter=None):
    for fname, python_data in iterate_objective_files_basic():
        region, area = region_area(ed, fname)

        if region_filter and region != region_filter:
            continue

        if area_filter and area_filter != area:
            continue

        yield fname, python_data, region, area


def cargo_component(cargo_component):
    return counted_cargo(cargo_component.get('count', '1'), cargo_names_dict[cargo_component['name']])

def crafted_cargo_ingredients(cargo):
    if (components := cargo.get('cargoComponents')):
        equals = f"({'+'.join(map(cargo_component, components))})"
    elif (energy := cargo.get('energy')):
        equals = counted_cargo(energy, "energy")
    else:
        ic("unknown cargo craft type!", cargo)
        equals = "Unknown"
    return equals

def crafted_cargo_desc(cargo):
#    if (components := cargo.get('cargoComponents')):
#        equals = f"({'+'.join(map(cargo_component, components))})"
#    elif (energy := cargo.get('energy')):
#        equals = counted_cargo(energy, "energy")
#    else:
#        ic("unknown cargo craft type!", cargo)
    return f"{counted_cargo(cargo.get('craftCount', '1'), cargo_names_dict[cargo['name']])}={crafted_cargo_ingredients(cargo)}"

def iterate_level_files_basic():
    p = Path(snowrunner_initial_pak_dir) / "[ps]"
    paths = list(f for f in p.glob('level_??_??_??*.sso') if not f.stem.endswith("objects"))

    for fpath in paths:
        fname = fpath.name
#        continue

        file_text = fpath.read_text()
        python_data = parse_sso(file_text)
        yield fname, python_data





cargo_names_str = """
Bricks [1]
Burnt logs
Cabin [2]
Cable Car [2]
Cargo Container [2]
Cellulose [1]
Cement [1]
Concrete Blocks [1]
Concrete Slab [2]
Consumables [1]
Drilling Equipment [4]
Drilling Spare Parts [1]
Empty Container
Empty Container Transformer
Fertilizer [1]
Freezer
Fuel [1]
Garbage [2]
Hay Bale [1]
Industrial Chiller
Industrial boiler [5]
Large Pipe [4]
Long Logs
Long Planks [4]
Medium Logs
Medium Pipes [2]
Medium Planks [2]
Metal Beams [2]
Metal Rolls [1]
Mine Cart [2]
Multistage Pump [2]
Oil Barrels [1]
Oil Rig Drill [5]
Oversized Cargo [4]
Packaged Sand [1]
Potato Samples [1]
Potatoes [1]
Rail Section [5]
Secure Container [1]
Service Spare Parts [1]
Short Logs
Silver [1]
Slate Blocks [2]
Small Pipes [2]
Solar Panels [1]
Soybeans [1]
Special Cargo [2]
Vehicle Spare Parts [1]
Water
Water Pipe [3]
Wooden Planks [1]
"""

cargo_names_dict = {
    "CargoBricks":"Bricks [1]",
    "CargoLogsMedium_Burnt":"Burnt logs",
    "CargoForkliftCaravanContainer2":"Cabin [2]",
    "CargoCableCar":"Cable Car [2]",
    "CargoContainerSmall":"Cargo Container [2]",
    "CargoCellulose":"Cellulose [1]",
    "CargoBarrelsChemicals":"Chemical Barrels [1]",
    "CargoBags":"Cement [1]",
    "CargoConcreteBlocks":"Concrete Blocks [1]",
    "CargoConcreteSlab":"Concrete Slab [2]",
    "CargoCrateLarge":"Consumables [1]",
    "CargoContainerLargeDrilling":"Drilling Equipment [4]",
    "CargoServiceSparePartsSpecial":"Drilling Spare Parts [1]",
    "CargoMetalJunkOpen":"Empty Container",
    "CargoMetalJunk":"Filled Container",
    "CargoEmptyContainerTransformer":"Empty Container Transformer",
    "CargoFertilizer":"Fertilizer [1]",
    "CargoReeferContainer":"Freezer",
    "CargoBarrels":"Fuel [1]",
    "CargoGold":"Gold [1]",
    "CargoTrash":"Garbage [2]",
    "CargoSensoryBuoy":" Data Buoy [2]",
    "CargoSensoryBuoyAdd2":" Data Buoy [2]",
    "CargoSensoryBuoyAdd3":" Data Buoy [2]",
    "CargoSensoryBuoyAdd4":" Data Buoy [2]",
    "CargoStack":"Hay Bale [1]",
    "CargoIndustrialChiller":"Industrial Chiller",
    "CargoBoiler":"Industrial boiler [5]",
    "CargoChiller":"Industrial Chiller",
    "CargoPipeLarge":"Large Pipe [4]",
    "CargoLogsLong":"Long Logs",
    "CargoWoodenPlanks4":"Long Planks [4]",
    "CargoLogsMedium":"Medium Logs",
    "CargoPipesMedium":"Medium Pipes [2]",
    "CargoWoodenPlanks2":"Medium Planks [2]",
    "CargoMetalPlanks":"Metal Beams [2]",
    "CargoMetalRoll":"Metal Rolls [1]",
    "CargoMineCart":"Mine Cart [2]",
    "CargoNPPPump":"Multistage Pump [2]",
    "CargoBarrelsOil":"Oil Barrels [1]",
    "CargoBigDrill":"Oil Rig Drill [5]",
    "CargoContainerLarge":"Oversized Cargo [4]",
    "CargoBags2":"Packaged Sand [1]",
    "CargoPotatoSamples":"Potato Samples [1]",
    "CargoPotatoUS":"Potatoes [1]",
    "CargoPotato":"Potatoes [1]",
    "CargoRailway":"Rail Section [5]",
    "CargoIronRoad":"Rails [4]",
    "CargoConsumableFuel":"Fuel",
    "CargoConsumableRepairs":"Repair Parts",
    "CargoRadioactive":"Secure Container [1]",
    "CargoSequoia":"Sequoia [5]",
    "CargoServiceSpareParts":"Service Spare Parts [1]",
    "CargoLogsShort":"Short Logs",
    "CargoSilver":"Silver [1]",
    "CargoStoneBlock":"Slate Blocks [2]",
    "CargoPipesSmall":"Small Pipes [2]",
    "CargoSolarPanel":"Solar Panels [1]",
    "CargoSoyabean":"Soybeans [1]",
    "CargoContainerSmallSpecial":"Special Cargo [2]",
    "CargoTransformer":"Transformer",
    "CargoVehiclesSpareParts":"Vehicle Spare Parts [1]",
    "CargoWater":"Water",
    "CargoWaterPipe":"Water Pipe [3]",
    "CargoWoodenPlanks":"Wooden Planks [1]",
    "CargoPlane":"Part of the airplane fuselage [5]",
    "CargoWing1":"Wing fragments with the engine [5]",
    "CargoWing2":"Part of the airplane fuselage [5]",
    "CargoWing3":"Piece of the airplane wing [4]",
    "CargoBA20":"BA-20 armored car [2]",
    "CargoBA20Add":"BA-20 armored car [2]",
    "CargoRocketEngine":"Engine Assembly [1]",
    "CargoRocketPart2":"Stage 2 Fuel Tank [3]",
    "CargoRocketPart1":"Stage 3 Fuel Tank [3]",
    "CargoBigbar":"Cistern [5]",
    "CargoMinecart":"Mine Cart [2]",

    "CargoTetrapod": "Tetrapod",
    "CargoForkliftCaravanContainer": "ForkliftCaravanContainer",
    "CargoFertilizerUs14": "Fertilizer",
#    "CargoFertilizerUs14": "Fertilizer [1]",

    "CargoLogsMediumTrailerLog": "Medium Logs",
}

cargo_names_set = set(cargo_names_dict.values())
cargo_names_set.add("Data Buoy [2]")

missing_cargo_name_reported = set()

def cargo_name(s):
    name = cargo_names_dict.get(s)

    if not name and s not in missing_cargo_name_reported:
#        print(f"Cargo name {Style.BRIGHT}{Fore.RED}{s}{Style.RESET_ALL} not found in cargo_names_dict")
#        missing_cargo_name_reported.add(s)
        return s

    return name

#re_cargo_name = re.compile(r"(.+?(?: \[\d\])?)\s*\[[\w\s]+\]")
re_cargo_name = re.compile(r"(.+?)\s*\[[^\d]+\]?")

def cargo_is_vehicle(cargo):
#    ic(cargo)
#    sys.exit(1)
    cargo_name = (m := re_cargo_name.match(cargo)) and m.group(1) or cargo
#    ic(cargo_name)
    return cargo_name not in cargo_names_set

def add_region_area_args(parser, optional=True):
    if optional:
        parser.add_argument('region', nargs='?')
        parser.add_argument('area', nargs='?')
    else:
        parser.add_argument('region')
        parser.add_argument('area')


#ic(cargo_is_vehicle(""))
