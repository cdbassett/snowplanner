# Steps to take when a new season is released

+ make new map images for each area
+ extract initial.pak using SnowPakTool.exe
+ extract e.g. level_ru_17_02_data_for_ssl file from e.g. level_ru_17_01.pak
+ run snowrunner_update_cargo_list_from_maprunner.py
    + cargo sources need to be in same order as before
+ run snowrunner_parse_truck_info_from_gamefiles
+ run snowrunner_generate_region_area_file.py
+ run snowrunner_extract_data_from_data_for_ssl_bin_files
+ run snowplanner_populate_db
+ run python3 -m database.dump_data to generate new json data for import into sqlitedb for other users 



