#!/usr/bin/env python3
import os
import zipfile
from pathlib import Path

# --- CONFIGURATION ---
# Folder containing your ZIP files
zip_directory = Path(r'Q:\SteamLibrary\steamapps\common\SnowRunner\preload\paks\client')
# The exact name of the file inside the ZIP you want to extract
path_to_extract = Path(r'[scene]\data_for_ssl.bin')
file_to_extract = path_to_extract.name
#path_to_extract = str(path_to_extract)
path_to_extract = path_to_extract.as_posix()

# Folder where you want to save the renamed files
output_directory = Path(r'O:\Games\snowrunner\data_for_ssl_files')
# ---------------------

def process_zips():
    # Create output folder if it doesn't exist
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    for zip_path in zip_directory.glob('level_??_??_??*.pak'):
        # Get the base name of the zip file (e.g., 'archive1.zip' -> 'archive1')
        zip_base_name = zip_path.stem[:14]

        # Define new filename based on the zip file name
        # Example: archive1_data.csv
        new_file_name = f"{zip_base_name}_{file_to_extract}"
        target_path = output_directory / new_file_name

        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Check if target file exists in zip
                if path_to_extract in zip_ref.namelist():
                    # Extract the file's data
                    with zip_ref.open(path_to_extract) as source_file:
                        # Write it to output with the new name
                        with open(target_path, 'wb') as target_file:
                            target_file.write(source_file.read())
                    print(f"Extracted: {path_to_extract} -> {new_file_name}")
                else:
                    print(f"File '{path_to_extract}' not found in {zip_path.name}")

        except zipfile.BadZipFile:
            print(f"Error: {filename} is not a valid zip file.")
#        break

if __name__ == "__main__":
    process_zips()

