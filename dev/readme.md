# Scripts to analyze, maintain or import data

Importing new seasons / regions is done by `import_new_regions.py` in the project root (see `update steps.md`).
`import_game_maps.py` (root) takes the area maps (1000 px, hillshaded from the level's height map; water depth overlays as *_water.png, utils/terrain_maps.py) and the map icons (assets/map_icons, data/map_zone_icons.tsv) from the game files; `import_new_regions.py --reset-positions` sets every map item's position from the game files.

analyze_data_for_ssl_bin.py
    Uses Construct to try to determine structure of data_for_ssl.bin files
gen_map_text_svg.py:
    Pull in cargo list, deliveries, and background image for areas in regions, then generate svg files that show all
    cargo pickups and mission/task deliveries (including lines between pickup objects like trailers and their
    destination when on the same map).
    Also used by snowplanner.py to generate internal svg
generate_mission_constraint_graphs.py
    Read objective files
    Generates png files of form f"{region} {area} Constraints" that show mission and task dependencies for areas 
parse_level_sso_files.py
    Parses level sso (objective) files
    generates cargo_from_gamefiles.generated.tsv, gates_from_gamefiles.generated.tsv, watch_tower_positions_from_gamefiles.generated.tsv
parse_objectives_from_gamefiles.py
    Reads objective files (needs the level_items_list.generated.tsv and truck info files from before the one-step import; may need updating)
    Generates "all_deliveries_list.generated.tsv", f"{region} Deliveries By Location.generated.txt", f"{region} Deliveries By Cargo.generated.txt"
    Generate base text files for deliveries (need to add positions of locations for them to render in
    snowrunner_gen_map_text_svg.py, uses different filenames for deliveries so it doesn't overwrite current work on adding information
extract_map_textures.py
    Level map textures (shared_textures.pak, [textures]\pct\level_*_map.pct) -> PNG (BC3 data in a "PICT" container, flipped vertically)
extract_gfx_textures.py
    UI textures of gfx.pak (BC1 / BC7 in the same container) -> PNG, by texture name
gfx_bundle.py / gfx_shapes.py
    Read the UI movies (Flash-style "GFX" files) in gfx.pak's gfxbundle: exported symbols -> bitmaps / vector shapes (gfx_shapes renders vectors with matplotlib)
extract_truck_images.py
    Vehicle store images (UiIcon328x458 of each truck definition) and a table of which image / icons belong to which vehicle
extract_gfx_icons.py
    Every exported symbol of a movie (icons_lib, minimap, hud_lib ...) as a named PNG
square_truck_images.py
    Crops the portrait vehicle store images to squares positioned on the vehicle (OpenCV GrabCut finds it)
marker_icons.py
    Icons of tasks / contracts / contests / objective stage kinds / vehicle types, and where each objective's markers are (marker_icons_by_objective.tsv)
map_icons.py
    Which icon the game uses for each kind of map zone (garage, gateway, watch tower, ...) and where those zones are in every area (map_icons_by_area.tsv)
sso_to_yaml.py
    reads in game sso files and writes the contents to more readable ymal files


utils/level_objects.py (used by import_game_maps.py)
    Reverse engineered placed objects of a level's data.stg (not documented anywhere): a table of object type names near the start (u32 count, then u16 length + name + NUL + 1 byte
    each; trees, bushes, rocks, twigs, signs, fences, barrels, vehicles ...) and 32 byte instance records anywhere in the file: float32 x, height, z (world metres), the marker u32 0x40000000,
    4 orientation bytes + 0xff, 4 bytes (last one looks like a scale), 3 tint bytes + flag, and a u32 whose third byte is the index in the name table. Records are found by the marker and
    kept when their height is within 2 m of the level's height map. Crown sizes / colours per tree family are estimates (TREE_FAMILIES). Bridges and buildings are not found yet.

### utils/level_scene.py, utils/level_structures.py
`level_scene.load_scene(area_id)` reads every placed 3D object of a level (model library + per-object matrix and contract tag) from data_for_ssl.bin. `level_structures` picks the bridges, rails and
pipelines out of it and draws them from above; `python3 import_game_maps.py --structures-only` redoes just those (see the notes on objective_models.py below).
`utils/level_splines.py` reads the rails (`iron_road*`, `rails_*`) and pipelines (`pipe_oil_us_01`, `overlay_water_pipe`) that are splines in the start of data.stg, not placed objects.
`utils/objective_models.py` links each contract model tag of the scene to the objectives whose scripts build it. `import_game_maps.py` draws the always-present bridges, rails and pipelines into `map_images/<slug>_normal.png` (and cuts the water overlay transparent under them; the plain pictures are kept in `extracted_map_textures/plain/`, so `--structures-only` takes about a minute), and writes `data/built_structures/<area id>.json`: per contract model tag the objective ids and the vector shapes of what it builds. The area page draws a tag's shapes when one of its objectives is completed, or all of them when "All" is checked.
`objective_models.zone_objectives` finds which objectives use each map zone (the zones an objective's script names, outside its rewards). `data/map_zone_icons.tsv` lists them per icon (`objectives`) with `keep`=1 for icons that stay when the objectives are done: zones that a reward opens up, and permanent places (garage, watch tower, gateway ...: `PERMANENT_ICONS` in import_game_maps.py). The area page hides an icon whose objectives are all completed unless "All" is checked.
