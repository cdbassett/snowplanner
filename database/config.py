from pathlib import Path

from database import models


snowplanner_db_dir = Path(__file__).resolve().parent
snowplanner_db_filename = snowplanner_db_dir / "snowplanner.sqlite"
snowplanner_db_url = "sqlite://" + str(snowplanner_db_filename)
DB_PATH = snowplanner_db_filename


TORTOISE_CONFIG = {
    "connections": {
        "default": snowplanner_db_url,
    },
    "apps": {
        "models": { # app name
            "models": ["database.models"],
            "default_connection": "default",
            "migrations": "database.migrations",
        }
    },
}


FIXTURE_PATH = snowplanner_db_dir / "fixtures/reference_snapshot.json"


# Define execution order to respect Foreign Key constraints
TABLE_ORDER = {
    "objective": models.Objective,
    "map_item": models.MapItem,
    "obj_prereq": models.ObjectivePrereq,
    "obj_item": models.ObjectiveItem,
    "src_cargo_item": models.SourceCargoItem,
    }
