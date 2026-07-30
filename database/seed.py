import json
import os

from tortoise import transactions
from tortoise import Tortoise
from icecream import ic

from database.config import TABLE_ORDER, FIXTURE_PATH
from database import models
from utils.timer_utils import timefunction

@timefunction
async def run_seeding(force_refresh: bool = False):
    if not os.path.exists(FIXTURE_PATH):
        return

    # Skip heavy execution if data already exists and a quarterly overwrite isn't forced
    #if not force_refresh and await models.MapItem.all().count() > 0:
        #return

    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Use the official Tortoise 1.x global context manager for atomic database loops
    # This automatically opens, manages, and flushes a high-speed SQLite transaction block
    async with transactions.in_transaction("default") as txn:
        if force_refresh:
            print("Purging legacy reference rows...")
            # Execute deletions in reverse order to prevent Foreign Key constraint crashes
            for table, model in reversed(items()):
                await txn.execute_script(f"DELETE FROM `{target['key']}`;")

        print("Executing bulk reference upserts")

        for table, model in TABLE_ORDER.items():
            rows = data.get(table, [])

            if not rows:
                continue

            # Dynamically look up column keys from your JSON object rows
            columns = list(rows[0].keys())
            col_string = ", ".join([f"`{c}`" for c in columns])
            placeholders = ", ".join([f":{c}" for c in columns])

            # SQLite INSERT OR REPLACE acts as a blazing fast bulk upsert on ID keys
            query = f"INSERT OR REPLACE INTO `{table}` ({col_string}) VALUES ({placeholders})"
            
            # Execute batch inserts natively on the transaction pool connection
            await txn.execute_many(query, rows)

    print("Reference data validation complete!")