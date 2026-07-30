#!/usr/bin/env python3
import json
import os
import asyncio

from tortoise import Tortoise

from database import models  # Import your models file
from database.config import TABLE_ORDER, FIXTURE_PATH, snowplanner_db_url


async def dump_data():
    print("Connecting to local SQLite database...")
    await Tortoise.init(
        db_url=snowplanner_db_url,
        modules={'models': ['database.models']}
    )

    snapshot = {}

    print("Extracting data from tables...")

    for table, model in TABLE_ORDER.items():
        # Pull raw dictionary rows for fast processing
        rows = await model.all().values()

        # Sanitize data: reset "completed" fields for the reference baseline
        if rows:
            if "completed" in rows[0]:
                for row in rows:
                    row["completed"] = False

            if table == "src_cargo_item":                    
                for row in rows:
                    row["current_cnt"] = row["initial_cnt"]

            # season 18 data is not yet complete, after it is tajke this out and existing installatiosn will add the new data
            if 1:
                for field in ("area_id", "objective_id", "map_item_id"):
                    if field in rows[0]:
                        rows = [row for row in rows if (v := row[field]) and not v.startswith("US_18_")]


        snapshot[table] = rows
        print(f" -> Captured and sanitized {len(rows)} rows from '{table}'")

    os.makedirs(os.path.dirname(FIXTURE_PATH), exist_ok=True)

    print(f"Writing snapshot to {FIXTURE_PATH}...")

    with open(FIXTURE_PATH, "w", encoding="utf-8") as f:
        # indent=2 keeps it highly scannable and diffable on GitHub
        json.dump(snapshot, f, indent=2, default=str)

    print("Dump complete! Ready to commit to Git.")
    await Tortoise.close_connections()

if __name__ == "__main__":
    asyncio.run(dump_data())

