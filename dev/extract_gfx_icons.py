#!/usr/bin/env python3
"""Extract the named icons of gfx.pak's movies as PNG: one file per exported symbol, bitmap or vector.

A symbol is a sprite; if it draws a bitmap that is cut out of its texture (using the movie's sub image rectangle), otherwise its vector shapes are rendered.

    python3 dev/extract_gfx_icons.py OUT_DIR MOVIE [MOVIE ...] [--gfx-pak PATH]       # e.g. icons_lib minimap hud_lib
    python3 dev/extract_gfx_icons.py OUT_DIR icons_lib --only garageImg40 gatewayImg40
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gfx_bundle
import gfx_shapes
from extract_gfx_textures import pct_to_image


def multiply(m, n):
    """Matrix m applied after n (matrices are (a, b, c, d, tx, ty))."""
    a, b, c, d, tx, ty = m
    A, B, C, D, TX, TY = n
    return (a * A + c * B, b * A + d * B, a * C + c * D, b * C + d * D, a * TX + c * TY + tx, b * TX + d * TY + ty)


def vector_parts(movie, cid, matrix=(1, 0, 0, 1, 0, 0), depth=0):
    parts = []

    if cid in movie.sprites and depth < 8:
        for child, child_matrix in movie.sprites[cid]:
            parts += vector_parts(movie, child, multiply(matrix, child_matrix) if child_matrix else matrix, depth + 1)
    elif cid in movie.shapes:
        parts.append(gfx_shapes.shape_artists(*movie.shapes[cid], matrix))

    return parts


def save_symbol(movie, name, out_path, textures, pak, scale):
    if (found := movie.bitmap_of(movie.symbols[name])):
        texture, rect = found

        if texture not in textures:
            textures[texture] = pct_to_image(pak.read(f"[textures]\\ui\\flash_auto\\{texture}.pct"))

        image = textures[texture]
        image.crop(rect if rect else (0, 0) + image.size).save(out_path)
        return "bitmap"

    if not (parts := vector_parts(movie, movie.symbols[name])) or not any(p[1] for p in parts):
        return None

    bounds = (min(p[0][0] for p in parts), min(p[0][1] for p in parts), max(p[0][2] for p in parts), max(p[0][3] for p in parts))
    gfx_shapes.render((bounds, [a for p in parts for a in p[1]]), out_path, scale=scale)
    return "vector"


def main(out_dir, movies, gfx_pak=None, only=None, scale=4):
    pak = gfx_bundle.open_pak(gfx_pak)
    textures = {}

    for movie_name in movies:
        movie = gfx_bundle.Movie(movie_name, gfx_pak)
        folder = Path(out_dir) / movie_name
        folder.mkdir(parents=True, exist_ok=True)
        counts = {"bitmap": 0, "vector": 0, None: 0}

        for name in sorted(only or movie.symbols):
            if name not in movie.symbols:
                continue

            try:
                counts[save_symbol(movie, name, folder / f"{name}.png", textures, pak, scale)] += 1
            except Exception as e: # a symbol with a construct the renderer doesn't know: leave it out
                counts[None] += 1
                print(f"  {movie_name}/{name}: {e}")

        print(f"{movie_name}: {counts['bitmap']} bitmap icons, {counts['vector']} vector icons, {counts[None]} not drawable")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out_dir")
    parser.add_argument("movies", nargs="+")
    parser.add_argument("--gfx-pak")
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--scale", type=float, default=4)
    args = parser.parse_args()
    main(args.out_dir, args.movies, args.gfx_pak, args.only, args.scale)
