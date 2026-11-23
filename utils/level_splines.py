"""Rails and pipelines that are splines rather than placed objects: railroad tracks (iron_road ...) and the pipelines of a level, from the start of its [scene]\\data.stg.

Reverse engineered layout (checked on all level paks). Each kind of spline is stored once per level as: u16 length + name + NUL, one more byte, u32 count N, then N splines of
  float length, u32 format, and either
    format 2 (a straight piece): 2 points of (x, width, z, 0) (the last one without the 0), then the length again;
    format 3 (a curve): three channels (x, width, z) of: u32 m (segments), u32 0, m cumulative segment lengths, m + 1 values, 3 * m more floats (the first m of them: the direction (x or z) the track leaves
    each point in).
Positions are world metres, centred on the map like everything else.
"""
import re
import struct
import zipfile

import numpy as np

from utils import gamefiles

HEAD = 2 << 20 # the splines are near the start of the file
WANTED = re.compile(r"^(iron_road|rails_|overlay_rails|pipe_oil_us_01|overlay_water_pipe)")
NAME_RE = re.compile(rb"([a-z][a-z0-9_]{3,40})\x00\x00([\x01-\xff])\x00\x00\x00")
STEP = 4.0 # metres between the points of a curve


def _hermite(points, tangents, step=STEP):
    out = []

    for i in range(len(points) - 1):
        p0, p1 = np.array(points[i]), np.array(points[i + 1])
        length = np.linalg.norm(p1 - p0)
        m0, m1 = np.array(tangents[i]) * length, np.array(tangents[i + 1]) * length
        n = max(2, int(length / step))

        for u in np.linspace(0, 1, n, endpoint=False):
            out.append(tuple((2 * u**3 - 3 * u**2 + 1) * p0 + (u**3 - 2 * u**2 + u) * m0 + (-2 * u**3 + 3 * u**2) * p1 + (u**3 - u**2) * m1))

    out.append(tuple(points[-1]))
    return out


def _parse_spline(data, q):
    """(points [(x, z)], width, offset after the spline) or None"""
    length, fmt = struct.unpack_from("<fI", data, q)

    if not 0 < length < 20000:
        return None

    if fmt == 2:
        a = struct.unpack_from("<3f", data, q + 8)
        b = struct.unpack_from("<3f", data, q + 8 + 16)
        return [(a[0], a[2]), (b[0], b[2])], a[1], q + 8 + 16 + 12 + 4

    if fmt != 3:
        return None

    q += 8
    channels = []

    for _ in range(3):
        m, _ = struct.unpack_from("<II", data, q)

        if not 1 <= m <= 2000:
            return None

        values = struct.unpack_from(f"<{m + 1}f", data, q + 8 + 4 * m)
        slopes = struct.unpack_from(f"<{m}f", data, q + 8 + 4 * m + 4 * (m + 1))
        channels.append((values, slopes))
        q += 8 + 4 * m + 4 * (m + 1) + 12 * m

    (xs, dx), (ws, _), (zs, dz) = channels
    points = list(zip(xs, zs))
    tangents = []

    for i in range(len(points)):
        j = min(i, len(dx) - 1)
        t = np.array([dx[j], dz[j]])
        norm = np.linalg.norm(t)
        tangents.append(tuple(t / norm) if norm > 1e-6 else (0.0, 0.0))

    if len(dx) < len(points): # the last point: the way the last segment arrives
        d = np.array(points[-1]) - np.array(points[-2])
        tangents[-1] = tuple(d / (np.linalg.norm(d) or 1))

    return _hermite(points, tangents), ws[0], q


def parse_splines(data):
    """{name: [(points [(x, z)], width)]} of the wanted splines found in the first part of data.stg bytes"""
    out = {}

    for m in NAME_RE.finditer(data):
        name = m.group(1).decode()
        n = m.start()

        if not WANTED.match(name) or n < 2 or struct.unpack_from("<H", data, n - 2)[0] != len(name) + 1 or name in out:
            continue

        q = m.end() - 4 # the u32 count
        count = struct.unpack_from("<I", data, q)[0]
        q += 4
        found = []

        try:
            for _ in range(count):
                r = _parse_spline(data, q)

                if r is None:
                    found = []
                    break

                pts, width, q = r
                found.append((pts, width))
        except struct.error:
            found = []

        if found and all(abs(x) < 1100 and abs(z) < 1100 for pts, _ in found for x, z in pts):
            out[name] = found

    return out


def load_splines(area_id):
    with zipfile.ZipFile(gamefiles.list_level_paks()[area_id]) as z:
        entry = next(i for i in z.infolist() if i.filename.replace("\\", "/").endswith("data.stg"))

        with z.open(entry) as f:
            return parse_splines(f.read(HEAD))
