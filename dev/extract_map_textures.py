#!/usr/bin/env python3
"""Extract the level map textures ([textures]\\pct\\level_xx_nn_mm_map.pct in client_dir/shared_textures.pak) as PNG.

A .pct file is not DDS: it starts with a small container header (the magic "PICT" is stored reversed, "TCIP", at byte 6; the width and height are
little-endian 32-bit numbers at byte 16 and 20, the number of mip levels at byte 48). The image data is plain BC3 (DXT5) compressed blocks, the
largest mip level first, ending 6 bytes before the end of the file (the header length varies, so the data's start is counted back from the end). Rows are stored bottom to top, so the image is flipped to match the in-game map.

    python3 dev/extract_map_textures.py OUT_DIR level_us_12_04 level_ru_02_03     # specific levels
    python3 dev/extract_map_textures.py OUT_DIR                                   # all of them
"""
import io
import re
import struct
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from snowplanner_config import config

TRAILER = 6 # bytes after the last mip level
Image.MAX_IMAGE_PIXELS = None


def pct_to_image(data):
    if data[6:10] != b"TCIP":
        raise ValueError("not a PICT texture")

    width, height = struct.unpack_from("<II", data, 16)
    (mips,) = struct.unpack_from("<I", data, 48)
    sizes = [((max(1, width >> n) + 3) // 4) * ((max(1, height >> n) + 3) // 4) * 16 for n in range(mips)]
    start = len(data) - TRAILER - sum(sizes)
    payload = data[start:start + sizes[0]] # first (largest) mip level only
    dds = struct.pack("<4sIIIIIII11I", b"DDS ", 124, 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000, height, width, len(payload), 0, 1, *([0] * 11))
    dds += struct.pack("<II4sIIIII", 32, 0x4, b"DXT5", 0, 0, 0, 0, 0) + struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)
    image = Image.open(io.BytesIO(dds + payload))
    image.load()
    return ImageOps.flip(image.convert("RGB"))


def main(out_dir, levels):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(Path(config.client_dir) / "shared_textures.pak") as pak:
        entries = {i.filename.replace("\\", "/").rsplit("/", 1)[-1]: i for i in pak.infolist() if re.search(r"level_.*_map\.pct$", i.filename, re.I)}

        for name in levels or sorted(re.sub(r"_map\.pct$", "", n) for n in entries):
            entry = entries[f"{name}_map.pct"]
            image = pct_to_image(pak.read(entry))
            image.save(out_dir / f"{name}_map.png")
            print(f"{name}: {image.size[0]}x{image.size[1]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)

    main(sys.argv[1], sys.argv[2:])
