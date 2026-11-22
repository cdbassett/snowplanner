"""Read the UI (Scaleform "GFX") movies the game keeps in client_dir/gfx.pak, in [gfx]\\gfxbundle.gfxbundle.

The bundle is a list of file names followed by the files themselves ("GFX" files are Flash movies: a sequence of tags). What we need from a movie:
  * its exported symbols (SymbolClass tag): name -> sprite id, e.g. "shopImgKenworth963" or "garageImg40",
  * the sprites (DefineSprite) and the shapes (DefineShape*) they place,
  * the images: tags 1009 (external image: id, size, texture name "trucks_img_lib_ic4.tga", which is the NAME.pct texture in gfx.pak) and 1008 (sub image: a rectangle of an external image).
    A bitmap fill of a shape refers to one of these.
"""
import re
import struct
import sys
import zipfile
from functools import cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from snowplanner_config import config

DEFINE_SHAPE_TAGS = (2, 22, 32, 83) # DefineShape, 2, 3, 4


def gfx_pak_path(path=None):
    return Path(path or Path(config.client_dir) / "gfx.pak")


@cache
def open_pak(path=None):
    return zipfile.ZipFile(gfx_pak_path(path))


@cache
def bundle(path=None):
    """(bytes of the bundle, {file name: (offset, length)})"""
    data = open_pak(path).read("[gfx]\\gfxbundle.gfxbundle")
    names = [n.decode() for n in re.findall(rb"[\w\-]+\.gfx", data[:20000])]
    starts, pos = [], 0
    pattern = re.compile(rb"[GC]FX[\x01-\x20]")

    while (m := pattern.search(data, pos)):
        i = m.start()
        length = struct.unpack_from("<I", data, i + 4)[0]

        if 8 < length < len(data) - i + 8 and length < 80_000_000:
            starts.append((i, length))
            pos = i + max(length, 8)
        else:
            pos = i + 1

    return data, dict(zip(names, starts))


def read_tags(data):
    """[(tag type, body)] of an uncompressed GFX file."""
    nbits = data[8] >> 3
    pos = 8 + (5 + nbits * 4 + 7) // 8 + 4 # header, frame RECT, frame rate, frame count
    tags = []

    while pos < len(data):
        (head,) = struct.unpack_from("<H", data, pos)
        pos += 2
        kind, length = head >> 6, head & 0x3F

        if length == 0x3F:
            (length,) = struct.unpack_from("<I", data, pos)
            pos += 4

        tags.append((kind, data[pos:pos + length]))
        pos += length

    return tags


class Movie:
    """One GFX movie of the bundle."""
    def __init__(self, name, pak=None):
        data, files = bundle(pak)
        offset, length = files[name if name.endswith(".gfx") else name + ".gfx"]
        self.name = name
        self.tags = read_tags(data[offset:offset + length])
        self.external = {} # image id -> texture name (without .tga)
        self.sub_images = {} # image id -> (external image id, (x1, y1, x2, y2))
        self.shapes = {} # character id -> (tag type, body)
        self.sprites = {} # character id -> [(character id placed, matrix or None)]
        self.symbols = {} # exported name -> character id

        for kind, body in self.tags:
            if kind == 1009:
                (cid,) = struct.unpack_from("<H", body, 0)
                texture = body[12:12 + body[11]].decode()
                self.external[cid] = texture[:-4] if texture.endswith(".tga") else texture
            elif kind == 1008:
                cid, base = struct.unpack_from("<HH", body, 0)
                self.sub_images[cid] = (base, struct.unpack_from("<4H", body, 4) if len(body) >= 12 else None)
            elif kind in DEFINE_SHAPE_TAGS:
                self.shapes[struct.unpack_from("<H", body, 0)[0]] = (kind, body)
            elif kind == 39:
                self.sprites[struct.unpack_from("<H", body, 0)[0]] = self._sprite_children(body)
            elif kind == 76:
                (count,) = struct.unpack_from("<H", body, 0)
                pos = 2

                for _ in range(count):
                    (cid,) = struct.unpack_from("<H", body, pos)
                    end = body.index(0, pos + 2)
                    self.symbols[body[pos + 2:end].decode()] = cid
                    pos = end + 1

    @staticmethod
    def _sprite_children(body):
        children, pos = [], 4

        while pos < len(body):
            (head,) = struct.unpack_from("<H", body, pos)
            pos += 2
            kind, length = head >> 6, head & 0x3F

            if length == 0x3F:
                (length,) = struct.unpack_from("<I", body, pos)
                pos += 4

            tag = body[pos:pos + length]
            pos += length

            if kind == 26 and tag[0] & 2: # PlaceObject2: flags, depth, [character id], [matrix]
                children.append((struct.unpack_from("<H", tag, 3)[0], read_matrix(tag, 5) if tag[0] & 4 else None))
            elif kind == 70 and tag[0] & 2: # PlaceObject3: flags, flags2, depth, [class name], [character id], [matrix]
                children.append((struct.unpack_from("<H", tag, 4)[0], read_matrix(tag, 6) if tag[0] & 4 else None))
            elif kind == 0:
                break

        return children

    def bitmap_of(self, cid, depth=0):
        """(texture name, crop rectangle or None) of the first bitmap the character draws, or None (it is vector graphics)."""
        if depth > 6:
            return None

        for child, _ in self.sprites.get(cid, ()):
            if (found := self.bitmap_of(child, depth + 1)):
                return found

        if cid in self.shapes and (bitmap := shape_bitmap_id(*self.shapes[cid])) is not None:
            if bitmap in self.sub_images:
                base, rect = self.sub_images[bitmap]

                if base in self.external:
                    return self.external[base], rect
            elif bitmap in self.external:
                return self.external[bitmap], None

        return None

    def symbol_bitmap(self, name):
        return self.bitmap_of(self.symbols[name]) or (None, None)


class BitReader:
    def __init__(self, data, pos=0):
        self.data, self.bit = data, pos * 8

    def bits(self, n):
        value = 0

        for _ in range(n):
            value = (value << 1) | ((self.data[self.bit >> 3] >> (7 - (self.bit & 7))) & 1)
            self.bit += 1

        return value

    def signed(self, n):
        value = self.bits(n)
        return value - (1 << n) if n and value >> (n - 1) else value

    def align(self):
        self.bit = (self.bit + 7) & ~7

    @property
    def pos(self):
        return (self.bit + 7) >> 3


def read_matrix(data, pos):
    """Matrix (a, b, c, d, tx, ty) in pixels (translation) from a MATRIX record at pos."""
    r = BitReader(data, pos)
    a, d = 1.0, 1.0
    b = c = 0.0

    if r.bits(1):
        n = r.bits(5)
        a, d = r.signed(n) / 65536, r.signed(n) / 65536

    if r.bits(1):
        n = r.bits(5)
        b, c = r.signed(n) / 65536, r.signed(n) / 65536

    n = r.bits(5)
    tx, ty = r.signed(n) / 20, r.signed(n) / 20
    return (a, b, c, d, tx, ty)


def shape_bitmap_id(kind, body):
    """Id of the bitmap the shape's first fill style uses, or None."""
    r = BitReader(body, 2)
    skip_rect(r)
    r.align()

    if kind == 83:
        skip_rect(r)
        r.align()
        r.bits(8)

    r.align()
    pos = r.pos
    count = body[pos]
    pos += 1

    if count == 0xFF:
        (count,) = struct.unpack_from("<H", body, pos)
        pos += 2

    if count and body[pos] >= 0x40:
        return struct.unpack_from("<H", body, pos + 1)[0]

    return None


def skip_rect(r):
    n = r.bits(5)

    for _ in range(4):
        r.signed(n)
