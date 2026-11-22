#!/usr/bin/env python3
"""Extract the vehicle store images (and write which image / icon belongs to which vehicle).

Every truck definition in initial.pak has UiIcon328x458 (the store image), TruckImage (the garage list strip) and UiIcon30x30 / UiIcon40x40 (the truck class icons).
The first two are symbols of gfx.pak's trucks_img_lib movie, which says which texture (and which rectangle of it) a symbol draws.

    python3 dev/extract_truck_images.py OUT_DIR [--gfx-pak PATH]

writes OUT_DIR/<truck file id>.png (328x458) and OUT_DIR/truck_image_map.tsv.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gfx_bundle
from extract_gfx_textures import pct_to_image
from utils import gamefiles

TRUCK_XML = re.compile(r"\[media\]/(?:_dlc/[^/]+/)?classes/trucks/([^/]+)\.xml$")


def attribute(text, name):
    m = re.search(name + r'="([^"]*)"', text)
    return m.group(1) if m else ""


def main(out_dir, gfx_pak=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    movie = gfx_bundle.Movie("trucks_img_lib", gfx_pak)
    pak = gfx_bundle.open_pak(gfx_pak)
    textures = {}
    rows = []
    initial = gamefiles.initial_pak()

    for name in sorted(initial.all_names()):
        if not (m := TRUCK_XML.match(name)):
            continue

        text = initial.read(name).decode("utf-8", errors="replace")
        store, garage = attribute(text, "UiIcon328x458"), attribute(text, "TruckImage")

        if not store or store not in movie.symbols:
            continue

        texture, rect = movie.symbol_bitmap(store)
        garage_texture, garage_rect = movie.symbol_bitmap(garage) if garage in movie.symbols else ("", None)

        if texture not in textures:
            textures[texture] = pct_to_image(pak.read(f"[textures]\\ui\\flash_auto\\{texture}.pct"))

        image = textures[texture]
        image.crop(rect if rect else (0, 0) + image.size).save(out_dir / f"{m.group(1)}.png")
        rows.append((m.group(1), store, texture, garage, garage_texture or "", ",".join(map(str, garage_rect or ())), attribute(text, "UiIcon30x30"), attribute(text, "UiIcon40x40")))

    with open(out_dir / "truck_image_map.tsv", "w", encoding="utf-8") as f:
        f.write("truck_id\tstore_symbol\tstore_texture\tgarage_symbol\tgarage_texture\tgarage_crop_xyxy\ticon30\ticon40\n")
        f.writelines("\t".join(row) + "\n" for row in rows)

    print(f"{len(rows)} vehicles")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out_dir")
    parser.add_argument("--gfx-pak", help="a (local) copy of gfx.pak; default: client_dir/gfx.pak")
    args = parser.parse_args()
    main(args.out_dir, args.gfx_pak)
