#!/usr/bin/env python3
import pprint
import json
import argparse
from pathlib import Path

from tortoise import Tortoise, run_async

from icecream import ic
# Set a custom width for indentation and wrapping (default is usually 80)
ic.configureOutput(argToStringFunction=lambda val: pprint.pformat(val, width=192))

from snowplanner_utils import *
from database.models import *
from database.config import snowplanner_db_url
from snowplanner_config import config


def find_newest_game_save(save_dir=None):
    """Return the most recently modified save file under the configured saved game dir."""
    save_dir = Path(save_dir or config.saved_game_dir)
    saves = [p for p in save_dir.rglob("CompleteSave*.cfg") if p.is_file()]

    if not saves:
        raise FileNotFoundError(f"No CompleteSave*.cfg game save found under {save_dir}")

    return max(saves, key=lambda p: p.stat().st_mtime)


async def apply_game_save(filename):
    """Mark objectives completed/not completed in the DB according to the game save.

    Assumes Tortoise is already initialized."""
    with open(filename, 'r', encoding = "utf-8") as infile:
        text = infile.read()

    data = json.loads(text[:-1])  # drop trailing NUL
    save_key = next(k for k in data if k.startswith("CompleteSave"))
    finishedObjs = data[save_key]["SslValue"]["finishedObjs"]
    await Objective.filter(id__in=finishedObjs, completed=False).update(completed=True)
    await Objective.exclude(id__in=finishedObjs).filter(completed=True).update(completed=False)
    return len(finishedObjs)


async def run(filename=None) -> None:
    await Tortoise.init(db_url=snowplanner_db_url, modules={"models": ["database.models"]})
    await Tortoise.generate_schemas()
    await apply_game_save(filename or find_newest_game_save())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Set objectives from saved game (default: newest save in configured saved_game_dir)')
    parser.add_argument('game_save', nargs='?')
    args = parser.parse_args()

    run_async(run(args.game_save))
