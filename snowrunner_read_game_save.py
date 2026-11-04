#!/usr/bin/env python3
import pprint
import json
import argparse
import os
import re
from collections import namedtuple
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


async def apply_objective_item_progress(save):
    """Set ObjectiveItem.completed from the save's objectiveStates for objectives that are in progress.

    Cargo items are delivered once curValue reaches aimValue; truck/trailer items use isDelivered. Item ids are
    <objective>|<stage>|<index>|<c/t>, matching stagesState[stage].cargoDeliveryActions / truckDeliveryStates[index]."""
    states = save.get("objectiveStates", {})
    changed = []
    delivered = 0

    for item in await ObjectiveItem.filter(objective_id__in=list(states)):
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
