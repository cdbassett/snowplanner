# Scripts to analyze, maintain or import data

Importing new seasons / regions is done by `import_new_regions.py` in the project root (see `update steps.md`).

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
sso_to_yaml.py
    reads in game sso files and writes the contents to more readable ymal files

