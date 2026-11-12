#!/usr/bin/env python3
import pprint
import json
import argparse
import os
import re
from collections import namedtuple, defaultdict
from pathlib import Path

from tortoise import Tortoise, run_async

from icecream import ic
# Set a custom width for indentation and wrapping (default is usually 80)
ic.configureOutput(argToStringFunction=lambda val: pprint.pformat(val, width=192))

from snowplanner_utils import *
from database.models import *
from database.config import snowplanner_db_url
from snowplanner_config import config
from utils.snowrunner_utils import cargo_names_dict


SAVE_NAME_RE = re.compile(r"CompleteSave\d*\.cfg$", re.I) # the game's own slots; not "- Copy" files or .cfg.mod/.json leftovers


def _candidate_saves(save_dir):
    """Game save files directly in save_dir; if there are none, search below it, skipping backup folders (slow on a network share)."""
    saves = [p for p in save_dir.iterdir() if SAVE_NAME_RE.match(p.name) and p.is_file()]

    if saves:
        return saves

    for root, dirs, files in os.walk(save_dir):
        dirs[:] = [d for d in dirs if "backup" not in d.lower()]
        saves.extend(Path(root) / f for f in files if SAVE_NAME_RE.match(f))

    return saves


def list_game_saves(save_dir=None):
    """All game save slots, newest first."""
    return sorted(_candidate_saves(Path(save_dir or config.saved_game_dir)), key=lambda p: p.stat().st_mtime, reverse=True)


def find_newest_game_save(save_dir=None):
    """Return the most recently modified save file in the configured saved game dir."""
    save_dir = Path(save_dir or config.saved_game_dir)

    if not (saves := _candidate_saves(save_dir)):
        raise FileNotFoundError(f"No CompleteSave*.cfg game save found under {save_dir}")

    return max(saves, key=lambda p: p.stat().st_mtime)


def load_save_data(filename):
    """The SslValue dict of a CompleteSave*.cfg file."""
    with open(filename, 'r', encoding = "utf-8") as infile:
        text = infile.read()

    data = json.loads(text[:-1])  # drop trailing NUL
    return data[next(k for k in data if k.startswith("CompleteSave"))]["SslValue"]


class SaveResult(namedtuple("SaveResult", "finished_objs,source_items,source_unmatched,obj_items")):
    """Counts of what a save load did: finished objectives, source cargo rows set from the save, save entries that matched no source row, objective items marked delivered."""
    __slots__ = ()


async def apply_source_counts(save):
    """Set SourceCargoItem.current_cnt from the save's cargoLoadingCounts (zone id -> {cargo type: remaining}); -1 means unlimited, and rows the save doesn't mention are untouched stock (current_cnt None).

    Returns (rows set from the save, save entries with no matching row)."""
    wanted = {} # (map item id, display name) -> remaining count or None
    unmatched = 0

    for zone, counts in save.get("cargoLoadingCounts", {}).items():
        map_item_id = zone.split(" || ")[-1]

        for cargo_type, remaining in counts.items():
            name = cargo_names_dict.get(cargo_type)
            wanted[(map_item_id, name)] = None if remaining < 0 else remaining

    matched = set()
    changed = []

    for item in await SourceCargoItem.all():
        key = (item.map_item_id, item.name)
        new_cnt = wanted.get(key) if item.initial_cnt is not None else None # unlimited sources have no count to track

        if key in wanted:
            matched.add(key)

        if item.current_cnt != new_cnt:
            item.current_cnt = new_cnt
            changed.append(item)

    if changed:
        await SourceCargoItem.bulk_update(changed, fields=["current_cnt"])

    return len(matched), len(wanted) - len(matched)


SPAWN_PAIR_RE = re.compile(r"_(\d+)_(?:SPAWN|S)$|_(?:SPAWN|S)_(\d+)$", re.I)


def spawn_pair_key(zone_id):
    """The number that ties a spawn zone to its delivery zone (US_12_01_WATER_PROBE_02_SPAWN and ..._02_S share '02'); None if there isn't one."""
    if zone_id and (m := SPAWN_PAIR_RE.search(zone_id)):
        return m.group(1) or m.group(2)

    return None


async def sync_spawn_completion(objective_ids):
    """Mark the spawn items of these objectives spent or not from their cargo deliveries (which come from the save or from ticking the objective tree).

    Neither says whether a spawned cargo was picked up. A spawn is spent once its delivery is done, matched by the number in the zone names
    (..._02_SPAWN / ..._02_S); without such a pairing, as many spawns count as spent as deliveries were made."""
    cargo_done = defaultdict(list) # (objective, stage, name) -> [(pairing key, delivered)]
    spawns = defaultdict(list)

    for item in await ObjectiveItem.filter(objective_id__in=list(objective_ids)):
        key = (item.objective_id, item.id.split("|")[-3], item.name)

        if item.item_type == "spawn":
            spawns[key].append(item)
        elif item.item_type == "cargo":
            cargo_done[key].append((spawn_pair_key(item.deliver_loc_id), item.completed))

    changed = []

    for key, group in spawns.items():
        if not (deliveries := cargo_done.get(key)):
            continue

        by_key = dict(deliveries)
        group.sort(key=lambda i: i.id)

        if len(by_key) == len(deliveries) and None not in by_key and all(spawn_pair_key(i.map_item_id) in by_key for i in group):
            states_for = [by_key[spawn_pair_key(i.map_item_id)] for i in group]
        else:
            spent = sum(d for _, d in deliveries)
            states_for = [n < spent for n in range(len(group))]

        for spawn, done in zip(group, states_for):
            if spawn.completed != done:
                spawn.completed = done
                changed.append(spawn)

    if changed:
        await ObjectiveItem.bulk_update(changed, fields=["completed"])


async def apply_objective_item_progress(save):
    """Set ObjectiveItem.completed from the save's objectiveStates for objectives that are in progress.

    Cargo items are delivered once curValue reaches aimValue; truck/trailer items use isDelivered. Item ids are
    <objective>|<stage>|<index>|<c/t>, matching stagesState[stage].cargoDeliveryActions / truckDeliveryStates[index]."""
    states = save.get("objectiveStates", {})
    changed = []
    delivered = 0

    items = await ObjectiveItem.filter(objective_id__in=list(states))

    for item in items:
        stage_no, idx, kind = item.id.split("|")[-3:]

        try:
            stage = states[item.objective_id]["stagesState"][int(stage_no)]

            if kind == "c":
                cargo_state = stage["cargoDeliveryActions"][int(idx)]["cargoState"]
                done = cargo_state["curValue"] >= cargo_state["aimValue"]
            elif kind == "t":
                done = bool(stage["truckDeliveryStates"][int(idx)]["isDelivered"])
            else:
                continue
        except (KeyError, IndexError, ValueError):
            continue

        delivered += done

        if item.completed != done:
            item.completed = done
            changed.append(item)

    if changed:
        await ObjectiveItem.bulk_update(changed, fields=["completed"])

    await sync_spawn_completion(list(states))
    return delivered


async def apply_game_save(filename):
    """Update the DB from the game save: finished objectives, objective item deliveries and source cargo counts.

    Assumes Tortoise is already initialized. Returns a SaveResult."""
    save = load_save_data(filename)
    finishedObjs = save["finishedObjs"]
    await Objective.filter(id__in=finishedObjs, completed=False).update(completed=True)
    await Objective.exclude(id__in=finishedObjs).filter(completed=True).update(completed=False)
    source_items, source_unmatched = await apply_source_counts(save)
    obj_items = await apply_objective_item_progress(save)
    return SaveResult(len(finishedObjs), source_items, source_unmatched, obj_items)


def apply_game_save_summary(result):
    return (f"{result.finished_objs} finished objectives, {result.source_items} source cargo counts set "
            f"({result.source_unmatched} save entries matched no source), {result.obj_items} objective items delivered")


async def run(filename=None) -> None:
    await Tortoise.init(db_url=snowplanner_db_url, modules={"models": ["database.models"]})
    await Tortoise.generate_schemas()
    filename = filename or find_newest_game_save()
    print(filename, apply_game_save_summary(await apply_game_save(filename)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Set objectives from saved game (default: newest save in configured saved_game_dir)')
    parser.add_argument('game_save', nargs='?')
    args = parser.parse_args()

    run_async(run(args.game_save))
