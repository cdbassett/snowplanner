#!/usr/bin/env python3
import os
import sys
import math
from pathlib import Path
repo_root = str(Path(__file__).resolve().parent.parent)
if repo_root in sys.path:
    sys.path.remove(repo_root)
sys.path.insert(0, repo_root)

from utils.snowrunner_utils import iterate_region_area, slugify_region_area
from PIL import Image, ImageDraw, ImageFont

def main():
    base_dir = Path(__file__).resolve().parent.parent
    map_image_dir = base_dir / "map_images"

    # Group areas by region
    regions_dict = {}
    for ra in iterate_region_area():
        region_name = ra.region
        if region_name not in regions_dict:
            regions_dict[region_name] = []
        regions_dict[region_name].append(ra)

    print(f"Found {len(regions_dict)} total regions.")

    for region_name, areas in regions_dict.items():
        if len(areas) <= 1:
            continue

        print(f"Processing region '{region_name}' with {len(areas)} areas...")

        # Determine output filename early to check if generation is needed
        region_slug = slugify_region_area(region_name)
        output_filename = map_image_dir / f"region_{region_slug}_comparison.png"

        needs_update = True
        if output_filename.exists():
            output_mtime = output_filename.stat().st_mtime
            needs_update = False

        # Load images for each area
        images = []
        for area_info in areas:
            filename = f"{slugify_region_area(area_info.region, area_info.abbrev)}_normal.png"
            img_path = map_image_dir / filename

            if img_path.exists():
                if output_filename.exists() and img_path.stat().st_mtime > output_mtime:
                    needs_update = True

                try:
                    img = Image.open(img_path).convert("RGBA")
                    images.append((area_info.area, img))
                except Exception as e:
                    print(f"  Error opening {img_path}: {e}")
            else:
                print(f"  Warning: Map image not found: {img_path}")

        if not images:
            continue

        if not needs_update:
            print(f"  Region '{region_name}' is up-to-date. Skipping.")
            continue

        # Determine grid dimensions (2 columns)
        n = len(images)
        cols = 2 if n > 1 else 1
        rows = math.ceil(n / cols)

        # Target width for each map image in the grid, preserving aspect ratio
        target_width = 1024

        # Resize images preserving aspect ratio
        processed_images = []
        for area_name, img in images:
            orig_w, orig_h = img.size
            new_height = int(orig_h * (target_width / orig_w))
            img_resized = img.resize((target_width, new_height), Image.Resampling.LANCZOS)
            processed_images.append((area_name, img_resized))

        # Calculate row heights (max height of images in each row)
        row_heights = [0] * rows
        for idx, (area_name, img) in enumerate(processed_images):
            r = idx // cols
            w, h = img.size
            if h > row_heights[r]:
                row_heights[r] = h

        # Create grid canvas
        padding = 40
        header_height = 60
        grid_width = cols * target_width + (cols + 1) * padding

        total_rows_height = sum(row_heights)
        total_headers_height = rows * header_height
        total_padding_height = (rows + 1) * padding
        grid_height = total_rows_height + total_headers_height + total_padding_height

        canvas = Image.new("RGBA", (grid_width, grid_height), (240, 240, 240, 255))
        draw = ImageDraw.Draw(canvas)

        # Try loading a font, fallback to default if not available
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 28)
        except IOError:
            font = ImageFont.load_default()

        # Compute Y offsets for each row
        row_y_offsets = []
        current_y = padding
        for r in range(rows):
            row_y_offsets.append(current_y)
            current_y += header_height + row_heights[r] + padding

        for idx, (area_name, img) in enumerate(processed_images):
            r = idx // cols
            c = idx % cols

            x = padding + c * (target_width + padding)
            y = row_y_offsets[r]

            # Draw header background for area name
            draw.rectangle([x, y, x + target_width, y + header_height], fill=(50, 50, 50, 255))

            # Draw area name text centered in header
            bbox = draw.textbbox((0, 0), area_name, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = x + (target_width - text_width) // 2
            text_y = y + (header_height - text_height) // 2
            draw.text((text_x, text_y), area_name, fill=(255, 255, 255, 255), font=font)

            # Paste map image below header
            canvas.paste(img, (x, y + header_height))

        # Save comparison grid image
        canvas.save(output_filename)
        print(f"  Saved comparison grid preserving aspect ratios to {output_filename}")

if __name__ == "__main__":
    main()
