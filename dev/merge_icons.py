import os
from PIL import Image

def merge_and_resize_icons():
    # Get all files in the current working directory
    files = os.listdir('.')

    for filename in files:
        # Target only PNG files with "normal" in the name
        if filename.endswith('.png') and 'normal' in filename:

            # Generate the corresponding filenames
            icons_filename = os.path.join("icons_only", filename.replace('normal', 'icons_only'))
            merged_filename = filename.replace('normal', 'icon')

            # Skip if the merged file already exists
            if os.path.exists(merged_filename):
                print(f"Skipping: {merged_filename} already exists.")
                continue

            # Verify the matching icons_only file exists before proceeding
            if not os.path.exists(icons_filename):
                print(f"Warning: Found '{filename}' but '{icons_filename}' is missing. Skipping.")
                continue

            try:
                # Open both images in RGBA mode for transparency support
                base_img = Image.open(filename).convert("RGBA")
                icon_img = Image.open(icons_filename).convert("RGBA")

                # Check if sizes match; if not, resize the icon image to match the base image
                if base_img.size != icon_img.size:
                    # Resampling.LANCZOS ensures high quality during resizing
                    icon_img = icon_img.resize(base_img.size, Image.Resampling.LANCZOS)

                # Overlay the icons onto the base image
                merged_img = Image.alpha_composite(base_img, icon_img)

                # Save the result
                merged_img.save(merged_filename, "PNG")
                print(f"Created: {merged_filename}")

            except Exception as e:
                print(f"Error processing {filename}: {e}")

if __name__ == "__main__":
    merge_and_resize_icons()
