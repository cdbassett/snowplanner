#!/usr/bin/env python3
"""Extract UI textures from client_dir/gfx.pak ([textures]\\ui\\flash_auto\\NAME.pct) as PNG.

Each texture is stored twice: NAME.pct_header is the container header (82 bytes: the reversed magic "PICT" at byte 6, width / height as little-endian
32-bit numbers at byte 16 / 20, a pixel format code at byte 38, number of mip levels at byte 48), NAME.pct is the header followed by the image data
and 6 more bytes. Format codes seen: 12 = BC1 (DXT1), 52 = BC7. Unlike the level maps, these are stored right way up.

    python3 dev/extract_gfx_textures.py OUT_DIR NAME [NAME ...]     # e.g. levelus_0101_i1 trucks_img_lib_i1
"""
import io
import struct
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from snowplanner_config import config

FORMATS = {12: ("bc1", 8), 52: ("bc7", 16)} # code -> (block format, bytes per 4x4 block)
TRAILER = 6
Image.MAX_IMAGE_PIXELS = None


def pct_to_image(data):
    if data[6:10] != b"TCIP":
        raise ValueError("not a PICT texture")

    width, height = struct.unpack_from("<II", data, 16)
    (code,) = struct.unpack_from("<I", data, 38)
    (mips,) = struct.unpack_from("<I", data, 48)
    fourcc, block = FORMATS[code]
    sizes = [((max(1, width >> n) + 3) // 4) * ((max(1, height >> n) + 3) // 4) * block for n in range(mips)]
    start = len(data) - TRAILER - sum(sizes)
    payload = data[start:start + sizes[0]]
    dds = struct.pack("<4sIIIIIII11I", b"DDS ", 124, 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000, height, width, len(payload), 0, 1, *([0] * 11))
    dds += struct.pack("<II4sIIIII", 32, 0x4, b"DX10" if fourcc == "bc7" else b"DXT1", 0, 0, 0, 0, 0) + struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)

    if fourcc == "bc7":
        dds += struct.pack("<IIIII", 98, 3, 0, 1, 0) # DXGI_FORMAT_BC7_UNORM, 2D texture

    image = Image.open(io.BytesIO(dds + payload))
    image.load()
    return image.convert("RGBA")


def main(out_dir, names):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(Path(config.client_dir) / "gfx.pak") as pak:
        entries = {i.filename.replace("\\", "/").rsplit("/", 1)[-1]: i for i in pak.infolist()}

        for name in names:
            image = pct_to_image(pak.read(entries[f"{name}.pct"]))
            image.save(out_dir / f"{name}.png")
            print(f"{name}: {image.size[0]}x{image.size[1]}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)

    main(sys.argv[1], sys.argv[2:])
