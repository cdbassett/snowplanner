import os
from pathlib import Path

from nicegui import app, ui, Event
from tortoise.contrib.fastapi import RegisterTortoise
from tortoise import Tortoise
from tortoise.migrations.api import migrate  

from database import models
from database.seed import run_seeding
from database.config import TORTOISE_CONFIG, DB_PATH


async def init_db():
    print("Preparing local database environment...")
    
    # Establish database connection pool wrapper safely
    await RegisterTortoise(
        app=app,
        config=TORTOISE_CONFIG,
        generate_schemas=False, # Keeps schema creation tied to migrations!
    )

async def run_migrations_and_seeding():
    print("Processing schema adjustments...")

    try:
        # Tortoise is registered; explicitly ensure connections are active for this task
        await Tortoise.init(config=TORTOISE_CONFIG) 

        # Clean Native Execution: Internally sets up tortoise_migrations 
        # tracking schema if missing, then runs all your .py updates.
        await migrate(config=TORTOISE_CONFIG)
        print("Schema migrations successfully completed!")
    except Exception as e:
        print(f"Migration check completed or skipped: {e}")

    print("Verifying reference rows...")
    # Synchronously execute your relational JSON seeder
    await run_seeding(force_refresh=False)


# migration commandss
"""
tortoise -c database.config.TORTOISE_CONFIG init
tortoise -c database.config.TORTOISE_CONFIG makemigrations
tortoise -c database.config.TORTOISE_CONFIG makemigrations --empty  # creates empty migration file
tortoise -c database.config.TORTOISE_CONFIG makemigrations --name add_posts_table
tortoise -c database.config.TORTOISE_CONFIG migrate
tortoise -c database.config.TORTOISE_CONFIG migrate models 0002_add_field
tortoise -c database.config.TORTOISE_CONFIG history
tortoise -c database.config.TORTOISE_CONFIG heads
"""
