"""Read SnowRunner game data straight from the game's own packs (client_dir), with nothing extracted to disk.

initial.pak is a zip. Most of the game's scripts ([ps]\\*.sso, [strings]\\*.str ...) are packed once more inside it, in
initial.cache_block, a custom container (format as implemented by snow_patcher's TidyPatcher_MultiTweak.py).
Each level has its own level_xx_nn_mm.pak (a zip) whose [scene]\\data_for_ssl.bin holds the level's placed items and zones.
"""
import functools
import re
import struct
import zipfile
from pathlib import Path

from snowplanner_config import config

CACHE_BLOCK_NAME = "initial.cache_block"
CACHE_BLOCK_SIG_LEN = 64

NON_AREA_LEVELS = re.compile(r"level_(main_menu|trial|.*test)", re.I)
AREA_LEVEL_PAK = re.compile(r"level_([a-z]{2}_\d\d_\d\d)(?:_crop|_new)?\.pak$", re.I)


def client_dir():
    return Path(config.client_dir)


def parse_cache_block(data):
    """[(internal name, bytes)] in file order from an initial.cache_block blob."""
    p = CACHE_BLOCK_SIG_LEN
    ver, b1, count, four, b2 = struct.unpack_from("<iBiiB", data, p)
    p += 14
    names = []

    for _ in range(count):
        (ln,) = struct.unpack_from("<i", data, p)
        p += 4
        names.append(data[p:p + ln].decode("cp437"))
        p += ln

    p += 1
    offs = struct.unpack_from(f"<{count}q", data, p)
    p += 8 * count + 1
    sizes = struct.unpack_from(f"<{count}i", data, p)
    p += 4 * count + 1
    p += 4 * count # zeroes
    return [(n, data[p + o:p + o + sz]) for n, o, sz in zip(names, offs, sizes)]


def cache_internal_to_rel(name):
    """'<ps>:file' -> '[ps]/file' ;  '<ps>\\dir\\file' -> '[ps]/dir/file'"""
    m = re.match(r"^<([^>]+)>(?:(\\.+\\)|:)([^\\]+)$", name)

    if not m:
        raise ValueError(f"Unexpected cache_block entry name: {name!r}")

    ps, d, fn = m.group(1), m.group(2) or "\\", m.group(3)
    return f"[{ps}]{d}{fn}".replace("\\", "/")


class InitialPak:
    """Everything in initial.pak, with the entries of the nested cache block merged in. Names use '/' and keep their [folder] prefix."""
    def __init__(self, path):
        self.path = Path(path)
        self.zip = zipfile.ZipFile(self.path)
        self.names = {i.filename.replace("\\", "/"): i for i in self.zip.infolist() if not i.is_dir()}
        self.cache = {}

        if CACHE_BLOCK_NAME in self.names:
            for name, data in parse_cache_block(self.zip.read(self.names[CACHE_BLOCK_NAME])):
                self.cache[cache_internal_to_rel(name)] = data

    def all_names(self):
        return list(self.names) + list(self.cache)

    def read(self, name):
        """Bytes of a file by its '[folder]/file' name; the zip is checked first, then the cache block."""
        if name in self.names:
            return self.zip.read(self.names[name])

        try:
            return self.cache[name]
        except KeyError:
            pass

        if (lower := name.lower()) != name: # the game's script names are lower case, ids from the data are upper case
            return self.read(lower)

        raise FileNotFoundError(name)

    def exists(self, name):
        return name in self.names or name in self.cache or name.lower() in self.names or name.lower() in self.cache

    def glob(self, folder_prefix, pattern):
        """Names directly under folder_prefix (e.g. '[ps]/') whose file part matches the regex pattern."""
        rx = re.compile(pattern, re.I)
        return sorted(n for n in self.all_names() if n.startswith(folder_prefix) and "/" not in n[len(folder_prefix):] and rx.fullmatch(n[len(folder_prefix):]))


@functools.cache
def initial_pak(path=None):
    return InitialPak(path or client_dir() / "initial.pak")


def read_ps_text(fname):
    """Text of a [ps] script (level / objective .sso files)."""
    return initial_pak().read("[ps]/" + fname).decode("utf-8", errors="replace")


def list_ps_files(pattern):
    """File names (without the [ps]/ prefix) of [ps] scripts matching the regex."""
    return [n[len("[ps]/"):] for n in initial_pak().glob("[ps]/", pattern)]


def parse_strings(data, first_wins=False):
    """key (upper case) -> text from the bytes of a strings_*.str file (UTF-16, KEY <tabs> "value").

    Some keys appear more than once. The last one is what the app has always used for objective text; the game itself
    shows the first one for location names (e.g. UI_COMMON_LOG_STATION_NAME is "Log Station" first, "Sawmill" later)."""
    out = {}
    line_re = re.compile(r'^\s*("[^"]+"|\S+)\s+"(.*)"\s*$')

    for line in data.decode("utf-16").splitlines():
        if (m := line_re.match(line)):
            key = m.group(1).upper() # quoted keys keep their quotes, as the app has always read them

            if not (first_wins and key in out):
                out[key] = m.group(2) # left as written in the file (escapes included), as the app has always read it

    return out


@functools.cache
def english_strings():
    """The game's English text: upper case key -> text."""
    return parse_strings(initial_pak().read("[strings]/strings_english.str"))


@functools.cache
def english_strings_first():
    """Like english_strings() but a key that appears more than once keeps its first text (what the game shows for location names)."""
    return parse_strings(initial_pak().read("[strings]/strings_english.str"), first_wins=True)


def list_level_paks():
    """{area id: path} of the level paks that are real map areas (not menus, tests or trials)."""
    out = {}

    for p in sorted(client_dir().glob("level_*.pak")):
        if not NON_AREA_LEVELS.match(p.name) and (m := AREA_LEVEL_PAK.match(p.name)):
            out[m.group(1).upper()] = p

    return out


def read_data_for_ssl(area_id):
    """Bytes of [scene]\\data_for_ssl.bin from the area's level pak."""
    with zipfile.ZipFile(list_level_paks()[area_id]) as z:
        names = {i.filename.replace("\\", "/"): i for i in z.infolist()}
        return z.read(names["[scene]/data_for_ssl.bin"])
