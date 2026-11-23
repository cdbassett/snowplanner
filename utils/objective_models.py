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
