# Steps to take when a new season is released

+ `python3 import_new_regions.py --dry-run` to see what it would import
+ `python3 import_new_regions.py`
    + reads `client_dir` from config.yaml directly: initial.pak (strings, scripts, trucks) and the level_*.pak files
      (placed trucks, zone names); no website and no extracted files needed
    + adds new areas / regions, trucks, cargo sources, crafts, gates, objectives and the places where tasks are activated (task_giver table) for anything not completely in the database
      yet (existing rows are never renamed, so it can be run again at any time)
    + creates placeholder map images (map_images/) and a placeholder home page image (assets/) for new areas / regions;
      replace them with real ones
    + new cargo types are listed with the names the game gives them; add them to `cargo_names_dict`
      (utils/snowrunner_utils.py) with their size, e.g. "Bricks [1]", if you want the size shown
+ restart the app, position the new locations in edit mode
+ `python3 -m database.dump_data` to generate new json data for import into sqlitedb for other users
    + data of seasons in `UNFINISHED_SEASONS` (database/dump_data.py) is left out of the fixture
