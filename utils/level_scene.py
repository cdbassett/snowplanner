"""The placed 3D objects of a level, from its [scene]\\data_for_ssl.bin (see also utils/level_data.py for zones and vehicles).

Layout found by reverse engineering (checked on all level paks):
  * a list of landmark models with their instance positions (u32 count, then per model: u16 length + "landmarks/<name>_lmk\\0", u32 instances, 28 bytes each)
  * the model library: u32 count, then per model: u16 length + name, u16 length + landmark path (often empty), 6 floats of bounding box (min xyz, max xyz) and 64 bytes of matrix
  * every placed object: u32 count, then per object: u32 index into the library, 4x4 float matrix (rows x / y / z axes scaled by the object's size, the last row is the position), a tag string and a
    second string (u16 length + text + NUL each) and one more byte. The tag is the contract model that the object belongs to (e.g. US_15_01_BRIDGE_BID_01):
    these objects are what a contract builds, so they only exist once that objective has been done.
"""
import collections
import struct

from utils import gamefiles

Scene = collections.namedtuple("Scene", "library objects")  # library: [(name, landmark path, bounding box (6 floats))]; objects: [Obj]
Obj = collections.namedtuple("Obj", "name x y z axes tag")  # x, z = world position, y = height; axes: ((xx, xy, xz), (yx, yy, yz), (zx, zy, zz)) basis rows; tag: contract model or ""


def _chain_end(data):
    """Offset just after the first list of landmark models (where the model library starts), or None."""
    first = data.find(b"landmarks/")

    if first < 0:
        return None

    q = first - 6
    count = struct.unpack_from("<I", data, q)[0]
    q += 4

    for _ in range(count):
        ln = struct.unpack_from("<H", data, q)[0]
        name = data[q + 2:q + 2 + ln]

        if not name.startswith(b"landmarks/") or not name.endswith(b"\0"):
            return None

        q += 2 + ln
        q += 4 + struct.unpack_from("<I", data, q)[0] * 28

    return q


def parse_scene(data):
    q = _chain_end(data)

    if q is None:
        raise ValueError("no landmark list")

    count = struct.unpack_from("<I", data, q)[0]
    q += 4
    library = []

    for _ in range(count):
        strings = []

        for _ in range(2):
            ln = struct.unpack_from("<H", data, q)[0]
            strings.append(data[q + 2:q + 1 + ln].decode("latin1"))
            q += 2 + ln

        library.append((strings[0], strings[1], struct.unpack_from("<6f", data, q)))
        q += 24 + 64

    count = struct.unpack_from("<I", data, q)[0]
    q += 4
    objects = []

    for _ in range(count):
        index = struct.unpack_from("<I", data, q)[0]
        m = struct.unpack_from("<16f", data, q + 4)
        q += 68
        strings = []

        for _ in range(2):
            ln = struct.unpack_from("<H", data, q)[0]
            strings.append(data[q + 2:q + 1 + ln].decode("latin1"))
            q += 2 + ln

        q += 1

        if index >= len(library):
            raise ValueError("object with an unknown model")

        objects.append(Obj(library[index][0], m[12], m[13], m[14], (m[0:3], m[4:7], m[8:11]), strings[0]))

    return Scene(library, objects)


def load_scene(area_id):
    return parse_scene(gamefiles.read_data_for_ssl(area_id))
