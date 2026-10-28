import json
import os

from tortoise import transactions
from tortoise import Tortoise
from icecream import ic

from database.config import TABLE_ORDER, FIXTURE_PATH
from database import models
from utils.timer_utils import timefunction

USER_STATE_COLUMNS = {"completed", "current_cnt"} # set by playing, never overwritten from the fixture

@timefunction
async def run_seeding(force_refresh: bool = False):
    if not os.path.exists(FIXTURE_PATH):
        return

    # Skip heavy execution if data already exists and a quarterly overwrite isn't forced
    if not force_refresh and await models.MapItem.all().count() > 0:
        return

    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Use the official Tortoise 1.x global context manager for atomic database loops
    # This automatically opens, manages, and flushes a high-speed SQLite transaction block
    async with transactions.in_transaction("default") as txn:
        if force_refresh:
            print("Purging legacy reference rows...")
            # Execute deletions in reverse order to prevent Foreign Key constraint crashes
            for table in reversed(TABLE_ORDER):
                await txn.execute_script(f"DELETE FROM `{table}`;")

        print("Executing bulk reference upserts")

        for table, model in TABLE_ORDER.items():
            rows = data.get(table, [])

            if not rows:
                continue

            # Dynamically look up column keys from your JSON object rows
            columns = list(rows[0].keys())
            col_string = ", ".join([f"`{c}`" for c in columns])
            placeholders = ", ".join([f":{c}" for c in columns])

            # Upsert on ID keys. Not INSERT OR REPLACE: that deletes the existing row first, and with foreign keys on, the
            # ON DELETE CASCADE wipes every child row not in the fixture (e.g. all objective items) and resets user progress.
            updates = ", ".join(f"`{c}`=excluded.`{c}`" for c in columns if c != "id" and c not in USER_STATE_COLUMNS)
            query = f"INSERT INTO `{table}` ({col_string}) VALUES ({placeholders}) ON CONFLICT(`id`) DO UPDATE SET {updates}"

            # Execute batch inserts natively on the transaction pool connection
            await txn.execute_many(query, rows)

    print("Reference data validation complete!")