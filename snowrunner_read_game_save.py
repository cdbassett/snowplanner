#!/usr/bin/env python3
import pprint
import json
import argparse

from tortoise import Tortoise, run_async

from icecream import ic
# Set a custom width for indentation and wrapping (default is usually 80)
ic.configureOutput(argToStringFunction=lambda val: pprint.pformat(val, width=192))

from snowplanner_utils import *
from database.models import *
from database.config import snowplanner_db_url


async def run(filename) -> None:
    await Tortoise.init(db_url=snowplanner_db_url, modules={"models": ["database.models"]})
    await Tortoise.generate_schemas()

    with open(filename, 'r', encoding = "utf-8") as infile:
        text = infile.read()
        data = json.loads(text[:-1])
        if 0:
            objectives = data["CompleteSave1"]["SslValue"]["objectiveStates"]
            false_ids = []
            true_ids = []

            for obj_id, obj_data in objectives.items():
                if obj_data["isFinished"]:
                    ic(obj_id)
                    true_ids.append(obj_id)
                else:
                    false_ids.append(obj_id)

            await Objective.filter(id__in=true_ids, completed=False).update(completed=True)
            await Objective.filter(id__in=false_ids, completed=True).update(completed=False)

        finishedObjs = data["CompleteSave1"]["SslValue"]["finishedObjs"]
        await Objective.filter(id__in=finishedObjs, completed=False).update(completed=True)
        await Objective.exclude(id__in=finishedObjs, completed=True).update(completed=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Set objectives from saved game')
    parser.add_argument('game_save')
    args = parser.parse_args()

    run_async(run(args.game_save))

