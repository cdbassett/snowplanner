# Scripts to analyze, maintain or import data

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
generate_region_area_file.py
    Generates snowrunner_region_area.tsv, which contains region and area information
extract_data_from_data_for_ssl_bin_files.py
    Reads snowrunner_truck_trailer_info.generated.tsv
    Parses level data_for_ssl.bin files to get trucks, trailers, cargo, etc. for level
    Generates level_items_list.generated.tsv, snowrunner_map_item_positions.yaml
parse_level_sso_files.py
    Parses level sso (objective) files
    generates cargo_from_gamefiles.generated.tsv, gates_from_gamefiles.generated.tsv, watch_tower_positions_from_gamefiles.generated.tsv
parse_objectives_from_gamefiles.py
    Reads objective files, level_items_list.generated.tsv, snowrunner_truck_trailer_info.generated.tsv
    Generates "all_deliveries_list.generated.tsv", f"{region} Deliveries By Location.generated.txt", f"{region} Deliveries By Cargo.generated.txt"
    Generate base text files for deliveries (need to add positions of locations for them to render in
    snowrunner_gen_map_text_svg.py, uses different filenames for deliveries so it doesn't overwrite current work on adding information
parse_truck_info_from_gamefiles.py
    Reads truck xml files from initial_pak dir
    Renerates "snowrunner_truck_trailer_info.generated.tsv"
update_cargo_list_from_maprunner.py
    update cargo list from maprunner.info, uses some caching to avoid frequent hits
    Generates snowrunner_cargo_reformatted.tsv
merge_cargo_lists.py
    Read snowrunner_cargo_reformatted_org.tsv, snowrunner_cargo_reformatted.tsv
    Merge newly downloaded cargo list and existing one, matching and transferring x, y, url, location name modifications
    attempt to merge current work on cargo list with updated maprunner info
    Generates snowrunner_cargo.tsv
populate_db.py
    Reads objective files, level_items_list.generated.tsv, snowrunner_truck_trailer_info.generated.tsv, snowrunner_cargo_new.tsv
    fills records in sqlite db
sso_to_yaml.py
    reads in game sso files and writes the contents to more readable ymal files

