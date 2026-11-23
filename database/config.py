import os
from pathlib import Path

from database import models


snowplanner_db_dir = Path(__file__).resolve().parent
snowplanner_db_filename = Path(os.environ["SNOWPLANNER_DB_FILE"]) if os.environ.get("SNOWPLANNER_DB_FILE") else snowplanner_db_dir / "snowplanner.sqlite" # the environment variable lets tools work on a copy
# snowplanner_db_filename = snowplanner_db_dir / "snowplanner2.sqlite"
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
    "region_area": models.RegionArea,
    "truck_info": models.TruckInfo,
    "objective": models.Objective,
    "map_item": models.MapItem,
    "task_giver": models.TaskGiver,
    "objective_repair": models.ObjectiveRepair,
    "objective_visit": models.ObjectiveVisit,
    "obj_prereq": models.ObjectivePrereq,
    "obj_item": models.ObjectiveItem,
    "src_cargo_item": models.SourceCargoItem,
    }
