"""What a level's [scene]\\data_for_ssl.bin holds: the trucks / trailers placed in the level and its named zones."""
import re
import struct
from collections import Counter, namedtuple

from construct import *

from utils import gamefiles

dfs_string = PascalString(Int16ul, "utf8")

coord = Float32l
coord_cnt = 12 * 4 // coord.sizeof()

item_struct = Struct(
    "item_id" / dfs_string,
    "task_id" / dfs_string,
    "some_floats" / coord[coord_cnt],
    "unknown" / Byte[17],
    "masks" / Int32ul[6], # seems to be always FF FF 7F 7F or 7F FF FF 7F 7F, the same value across trucks
    "cargo_cnt" / Int32ul,
    "cargo_strings" / dfs_string[this.cargo_cnt],
    "unknown_strings" / dfs_string[7],
    "unknown_num" / Int32ul,
    "unknown_string" / dfs_string,
    "dummy" / Byte[18],
    )

dfs_struct = Struct(
    "magic" / OneOf(Int32ul, (0x13415BE, 20190655)),
    "hdr1" / Int32ul[1],
    "filesize" / Int32ul,
    "hdr2" / Int32ul[1],
    "hdr3" / Int16ul[3],
    "name_id" / dfs_string,
    "name_desc_id" / dfs_string,
    "night_day_strings" / dfs_string[8],
    "night_day_last" / Switch(this.magic, {0x13415BE: dfs_string, 20190655: Int32ul}),
    "sky_id" / dfs_string,
    "sky_sound_id" / dfs_string,
    "item_cnt" / Int32ul,
    "item_list" / item_struct[this.item_cnt],
    )


LevelItem = namedtuple("LevelItem", "item_id,task_id,index,cargo_strings,x,z") # a placed truck / trailer; task_id is empty when it is not part of an objective; x, z are its world position
Zone = namedtuple("Zone", "zone_id,model,model_kind,name_key,offset") # zone_id is the location's id; name_key is the key of its display name in the game's strings; offset is where the record starts in the file


def clear(s):
    return s[:-1] if s.endswith("\0") else s # the strings in the file keep their terminating NUL


def parse_level_items(data):
    """The trucks and trailers placed in a level (data_for_ssl.bin bytes)."""
    parsed = dfs_struct.parse(data)
    items = []

    for n, item in enumerate(parsed.item_list):
        x, height, z = struct.unpack("<fff", bytes(item.unknown[:12])) # the position follows the 3x4 orientation matrix (checked against hand-placed trucks)
        items.append(LevelItem(clear(item.item_id), clear(item.task_id), n, [clear(s) for s in item.cargo_strings], x, z))

    return items


ZONE_ID_RE = re.compile(rb"[A-Za-z0-9_]{4,}\x00")
PLAIN_STRING_RE = re.compile(rb"[\x20-\x7e]+")


def parse_level_zones(data):
    """{zone id: Zone} for the named zones: each is stored as four consecutive length-prefixed strings (id, model, model kind, display name key)."""
    zones = {}
    size = len(data)

    for m in ZONE_ID_RE.finditer(data):
        start = m.start()

        if start < 2 or struct.unpack_from("<H", data, start - 2)[0] != len(m.group()):
            continue

        p = start - 2
        strings = []

        for _ in range(4):
            if p + 2 > size:
                break

            ln = struct.unpack_from("<H", data, p)[0]
            s = data[p + 2:p + 2 + ln]

            if ln < 2 or not s.endswith(b"\0") or not PLAIN_STRING_RE.fullmatch(s[:-1]):
                break

            strings.append(s[:-1].decode("ascii"))
            p += 2 + ln

        if len(strings) == 4:
            zones.setdefault(strings[0], Zone(*strings, start - 2))

    return zones


def zone_display_name(zone, strings=None):
    """The in-game name of a zone, or None when its name key has no text."""
    return (strings or gamefiles.english_strings_first()).get(zone.name_key.upper())


Placement = namedtuple("Placement", "x,z,dir_x,dir_z,width,depth,height")


def zone_placement(data, zone):
    """Where the zone sits in the level, from the floats just before its record: world x / z (centered on the map; the same system as the gates' cameraPos), a facing direction, and the zone's size.

    Layout (float32 at these distances before the record): width -40, depth -36, height -32, x -20, z -16, direction x -12, direction z -8."""
    def f(back):
        return struct.unpack_from("<f", data, zone.offset - back)[0] if zone.offset >= back else float("nan")

    return Placement(f(20), f(16), f(12), f(8), f(40), f(36), f(32))


def placement_by_id(data, zone_id):
    """Placement of a zone found by its id alone (e.g. spawn points, whose records don't have the four-string shape parse_level_zones looks for), or None."""
    k = data.find(struct.pack("<H", len(zone_id) + 1) + zone_id.encode() + b"\0")
    return zone_placement(data, Zone(zone_id, "", "", "", k)) if k >= 0 else None


def area_half_span(data, zones=None):
    """Half the width of the area's map in world units: 1000 for the usual map, 500 for the few small ones (all their zones lie within +-500)."""
    zones = zones if zones is not None else parse_level_zones(data)
    coords = [c for zone in zones.values() for c in zone_placement(data, zone)[:2] if abs(c) < 3000]
    return 500 if coords and max(abs(c) for c in coords) <= 520 else 1000


def world_to_db(x, z, half=1000):
    """World position -> the app's 0-1000 map coordinates (same conversion as the gates), clamped to the map."""
    return max(0, min(1000, round((x + half) / (2 * half) * 1000))), max(0, min(1000, round((half - z) / (2 * half) * 1000)))


_UI_DESC = re.compile(r'uiDesc\s*=\s*"([^"]+)"(?=(.{0,400}))', re.S)
_ZONE_REF = re.compile(r'globalZone(?:Delivery)?Id\s*=\s*(?:\{\s*globalZoneId\s*=\s*)?"([^"|]+?)\s*\|\|\s*([^"]+)"')


def delivery_zones():
    """{delivery location id: {(area id, zone id): None, ...} in file order} from the objective scripts: a delivery's id is the uiDesc of its zoneToFill / truckDelivery entry
    and the zone it sits in is the zone reference next to it (after it for cargo, before it for truck deliveries). Zones that only block or give tasks are ignored."""
    from utils.snowrunner_utils import fname_to_area_id

    out = {}

    for fname in gamefiles.list_ps_files(r".*"):
        text = gamefiles.read_ps_text(fname)

        for m in _UI_DESC.finditer(text):
            ui, tail = m.group(1), m.group(2).split("uiDesc")[0]
            back = text[max(0, m.start() - 350):m.start()].split("uiDesc")[-1]
            found = list(_ZONE_REF.finditer(back))
            ref = found[-1] if found else _ZONE_REF.search(tail)

            if ref and "GIVER" not in ref.group(2):
                try:
                    out.setdefault(ui, {})[(fname_to_area_id(ref.group(1)), ref.group(2))] = None # insertion order: the first zone is the one that keeps the uiDesc as its id
                except Exception:
                    pass # test levels and the like

    return out
