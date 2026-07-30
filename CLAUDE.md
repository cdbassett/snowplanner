# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

- Run web application: `python3 snowplanner_app.py`
- Populate database: `python3 snowplanner_populate_db.py`
- Generate database reports: `python3 snowpopulated_db_reports.py` (or `python3 snowplanner_populated_db_reports.py`)
- Game data parsing and utilities: Scripts located in root and `utils/` (e.g. `python3 utils/snowrunner_parse_objectives_from_gamefiles.py`)

## Architecture & Overview

SnowPlanner is a visual planning tool for the game *SnowRunner*, allowing users to plan deliveries across areas and regions rather than just single objectives.

- **Frontend & App Framework**: Built using [NiceGUI](https://nicegui.io/) (`snowplanner_app.py`) integrating D3.js visualization scripts (`d3_init.js`, `d3_brush_selection.js`, assets in `js/`).
- **Database & Models**: Uses Tortoise ORM with SQLite (`snowplanner_models.py`, `snowplanner_migration_settings.py`, and database migrations in `migrations/`).
- **Data Pipelines & Utilities**: A collection of data parsing and extraction scripts in `utils/` (such as `snowrunner_parse_objectives_from_gamefiles.py`, `snowrunner_extract_data_from_data_for_ssl_bin_files.py`, `snowrunner_gen_map_text_svg.py`, etc.) that ingest game files, pak contents, or MapRunner information to populate the SQLite database.
