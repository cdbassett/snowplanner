"""Reference tables the app needs synchronously at import time (regions/areas, trucks).

They live in the database; a database that doesn't have them yet (a fresh install, or one from before the tables existed)
falls back to the same tables in the reference fixture, which is also what seeds them on startup."""
import json
import sqlite3

from database.config import snowplanner_db_filename, FIXTURE_PATH


def _db_rows(table, columns, order):
    if not snowplanner_db_filename.exists():
        return []

    try:
        con = sqlite3.connect(f"file:{snowplanner_db_filename}?mode=ro", uri=True)

        try:
            return con.execute(f"select {', '.join(columns)} from {table} order by {order}").fetchall()
        finally:
            con.close()
    except sqlite3.Error: # no such table yet
        return []


def _fixture_rows(table, columns, order):
    try:
        with open(FIXTURE_PATH, encoding="utf-8") as f:
            rows = json.load(f).get(table, [])
    except OSError:
        return []

    return [tuple(r.get(c) for c in columns) for r in sorted(rows, key=lambda r: r[order])]


def reference_rows(table, columns, order):
    return _db_rows(table, columns, order) or _fixture_rows(table, columns, order)


def region_area_rows():
    """[(region_id, region, area_id, area, abbrev)] in display order."""
    return reference_rows("region_area", ("region_id", "region", "area_id", "area", "abbrev"), "seq")


def truck_info_rows():
    """[(kind, id, ui_key, name, truck_type)]"""
    return reference_rows("truck_info", ("kind", "id", "ui_key", "name", "truck_type"), "id")
