"""Which objectives build which scene models: the contracts / tasks of the game's scripts have a "model" block (ModelBuildingSettings) with the level and the tag of the placed objects they
bring into the world when done (see utils/level_scene.py). Objectives live in per-objective scripts (<objective id>.sso), in <area>_objects.sso with many objectives each, and a few in
level scripts; the owner of a model block is the objective key that encloses it (or the script's own name)."""
import collections
import re

from utils import gamefiles

LEVEL_RE = re.compile(r'levelName\s*=\s*"level_([a-z]{2}_\d\d_\d\d)')
TAG_RE = re.compile(r'modelTag\s*=\s*"(\w+)"')
KEY_RE = re.compile(r"^(\s{0,3})(\w+)\s+=\s+\{\s*$")


def objective_models(objective_ids):
    """{(area id, tag): sorted objective ids}: the known objectives (objective_ids is the set of ids in the database) whose scripts have a model block for that tag"""
    out = collections.defaultdict(set)

    for fn in gamefiles.list_ps_files(r".*\.sso"):
        text = gamefiles.read_ps_text(fn)

        if "modelTag" not in text:
            continue

        stem = fn[:-4].upper()
        key = None
        level = None

        for line in text.splitlines():
            if (m := KEY_RE.match(line)) and m.group(2).upper() in objective_ids:
                key = m.group(2).upper()

            if m := LEVEL_RE.search(line):
                level = m.group(1).upper()

            if (m := TAG_RE.search(line)) and level:
                owner = key or (stem if stem in objective_ids else None)

                if owner:
                    out[(level, m.group(1))].add(owner)

    return {k: sorted(v) for k, v in out.items()}


ZONE_TOKEN = re.compile(r"\b[A-Z]{2}_\d\d_\d\d_[A-Z0-9_]+\b")


def zone_objectives(objective_ids, zone_ids):
    """({zone id: sorted objective ids that use the zone}, {zone ids that an objective's reward opens up or changes}) for the zones in zone_ids: the zones an objective's script names,
    apart from the ones in its rewards (an unlocked garage, a location that opens ...)"""
    zone_ids = set(zone_ids)
    used = collections.defaultdict(set)
    rewarded = set()

    def finish(key, lines):
        if key not in objective_ids:
            return

        reward_indent = None

        for line in lines:
            indent = len(line) - len(line.lstrip())

            if reward_indent is None and re.match(r"\s*rewards\s+=\s+\{", line):
                reward_indent = indent
                continue

            if reward_indent is not None and indent <= reward_indent and line.lstrip().startswith("}"):
                reward_indent = None
                continue

            for token in ZONE_TOKEN.findall(line):
                if token in zone_ids and token != key:
                    if reward_indent is None:
                        used[token].add(key)
                    else:
                        rewarded.add(token)

    for fn in gamefiles.list_ps_files(r".*\.sso"):
        text = gamefiles.read_ps_text(fn)
        stem = fn[:-4].upper()
        key, lines = (stem if stem in objective_ids else None), []
        indent = None # how far the objectives' own keys are indented in this script; any key at that depth ends the objective before it

        for line in text.splitlines():
            m = KEY_RE.match(line)

            if m and indent is None and m.group(2).upper() in objective_ids:
                indent = len(m.group(1))

            if m and len(m.group(1)) == indent:
                finish(key, lines)
                key, lines = (m.group(2).upper() if m.group(2).upper() in objective_ids else None), []

            lines.append(line)

        finish(key, lines)

    return {z: sorted(o) for z, o in used.items()}, rewarded
