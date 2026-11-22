"""Render the vector icons of a GFX movie (DefineShape tags) to images with matplotlib.

Handles solid fills, strokes and (as their first colour) gradient fills; bitmap fills are drawn by the caller. Coordinates are twips (1/20 pixel).
"""
import struct

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MPath

from gfx_bundle import BitReader, read_matrix, skip_rect


def read_rgba(data, pos, alpha):
    return ((data[pos] / 255, data[pos + 1] / 255, data[pos + 2] / 255, (data[pos + 3] / 255) if alpha else 1.0), pos + (4 if alpha else 3))


def read_fill_styles(data, pos, kind):
    """([style], new pos); a style is ('solid', rgba) / ('bitmap', id) / ('gradient', rgba of its first stop)."""
    alpha = kind in (32, 83)
    count = data[pos]
    pos += 1

    if count == 0xFF:
        (count,) = struct.unpack_from("<H", data, pos)
        pos += 2

    styles = []

    for _ in range(count):
        ftype = data[pos]
        pos += 1

        if ftype == 0:
            color, pos = read_rgba(data, pos, alpha)
            styles.append(("solid", color))
        elif ftype in (0x10, 0x12, 0x13):
            r = BitReader(data, pos)
            r.bits(1), r.bits(1), r.bits(5) # not a matrix: gradient matrix follows; parse generically below
            r = BitReader(data, pos)
            read_matrix_bits(r)
            r.align()
            pos = r.pos

            if ftype == 0x13:
                pos += 2 # focal point

            n = data[pos] & 0x0F
            pos += 1
            first = None

            for k in range(n):
                color, pos2 = read_rgba(data, pos + 1, alpha)
                first = first or color
                pos = pos2

            styles.append(("gradient", first or (0, 0, 0, 1)))
        elif ftype >= 0x40:
            (bitmap,) = struct.unpack_from("<H", data, pos)
            pos += 2
            r = BitReader(data, pos)
            read_matrix_bits(r)
            r.align()
            pos = r.pos
            styles.append(("bitmap", bitmap))
        else:
            raise ValueError(f"fill style {ftype:#x}")

    return styles, pos


def read_matrix_bits(r):
    if r.bits(1):
        n = r.bits(5)
        r.signed(n), r.signed(n)

    if r.bits(1):
        n = r.bits(5)
        r.signed(n), r.signed(n)

    n = r.bits(5)
    r.signed(n), r.signed(n)


def read_line_styles(data, pos, kind):
    """([(width in twips, rgba)], new pos)"""
    alpha = kind in (32, 83)
    count = data[pos]
    pos += 1

    if count == 0xFF:
        (count,) = struct.unpack_from("<H", data, pos)
        pos += 2

    styles = []

    for _ in range(count):
        (width,) = struct.unpack_from("<H", data, pos)
        pos += 2

        if kind == 83: # LINESTYLE2
            flags = struct.unpack_from("<H", data, pos)[0]
            pos += 2

            if (flags >> 8) & 0x03 == 2: # miter join
                pos += 2

            if flags & 0x08:
                styles.append((width, (0, 0, 0, 1)))
                pos += 1 + 0
                # fill-style based line: skip the embedded fill style
                _, pos = read_fill_styles(data, pos - 1, kind)
                continue

        color, pos = read_rgba(data, pos, alpha)
        styles.append((width, color))

    return styles, pos


def parse_shape(kind, body):
    """(bounds (xmin, ymin, xmax, ymax) in twips, fill styles, line styles, edges); an edge is (fill0, fill1, line, segment), a segment ('L', x0, y0, x1, y1) or ('Q', x0, y0, cx, cy, x1, y1)."""
    r = BitReader(body, 2)
    n = r.bits(5)
    bounds = [r.signed(n) for _ in range(4)]
    xmin, xmax, ymin, ymax = bounds

    r.align()

    if kind == 83:
        skip_rect(r)
        r.align()
        r.bits(8)

    r.align()
    fills, pos = read_fill_styles(body, r.pos, kind)
    lines, pos = read_line_styles(body, pos, kind)
    r = BitReader(body, pos)
    fill_bits, line_bits = r.bits(4), r.bits(4)
    x = y = 0
    fill0 = fill1 = line = 0
    edges = []
    all_fills, all_lines = [list(fills)], [list(lines)]

    while True:
        if r.bits(1): # edge record
            if r.bits(1): # straight
                nbits = r.bits(4) + 2

                if r.bits(1):
                    dx, dy = r.signed(nbits), r.signed(nbits)
                elif r.bits(1):
                    dx, dy = 0, r.signed(nbits)
                else:
                    dx, dy = r.signed(nbits), 0

                edges.append((fill0, fill1, line, ("L", x, y, x + dx, y + dy), len(all_fills) - 1))
                x, y = x + dx, y + dy
            else:
                nbits = r.bits(4) + 2
                cx, cy = x + r.signed(nbits), y + r.signed(nbits)
                ax, ay = cx + r.signed(nbits), cy + r.signed(nbits)
                edges.append((fill0, fill1, line, ("Q", x, y, cx, cy, ax, ay), len(all_fills) - 1))
                x, y = ax, ay
        else:
            flags = r.bits(5)

            if not flags:
                break

            if flags & 1: # move to
                nbits = r.bits(5)
                x, y = r.signed(nbits), r.signed(nbits)

            if flags & 2:
                fill0 = r.bits(fill_bits)

            if flags & 4:
                fill1 = r.bits(fill_bits)

            if flags & 8:
                line = r.bits(line_bits)

            if flags & 16: # new styles
                r.align()
                fills, pos = read_fill_styles(body, r.pos, kind)
                lines, pos = read_line_styles(body, pos, kind)
                r = BitReader(body, pos)
                fill_bits, line_bits = r.bits(4), r.bits(4)
                all_fills.append(fills)
                all_lines.append(lines)
                fill0 = fill1 = line = 0

    return (xmin, ymin, xmax, ymax), all_fills, all_lines, edges


def stitch(segments):
    """Join segments (each (start, end, path ops)) into closed contours; returns a list of ops lists."""
    by_start = {}

    for seg in segments:
        by_start.setdefault(seg[0], []).append(seg)

    contours = []

    while by_start:
        start = next(iter(by_start))
        seg = by_start[start].pop()

        if not by_start[start]:
            del by_start[start]

        ops = [("M",) + seg[0], seg[2]]
        end = seg[1]

        while end != ops[0][1:] and end in by_start:
            nxt = by_start[end].pop()

            if not by_start[end]:
                del by_start[end]

            ops.append(nxt[2])
            end = nxt[1]

        contours.append(ops)

    return contours


def segment_ops(seg, reverse):
    if seg[0] == "L":
        _, x0, y0, x1, y1 = seg
        return ((x1, y1), (x0, y0), ("L", x0, y0)) if reverse else ((x0, y0), (x1, y1), ("L", x1, y1))

    _, x0, y0, cx, cy, x1, y1 = seg
    return ((x1, y1), (x0, y0), ("Q", cx, cy, x0, y0)) if reverse else ((x0, y0), (x1, y1), ("Q", cx, cy, x1, y1))


def to_path(contours, matrix):
    """matplotlib Path from contours in twips, transformed by matrix (pixel units; y down)."""
    a, b, c, d, tx, ty = matrix
    verts, codes = [], []

    def tf(x, y):
        x, y = x / 20, y / 20
        return (a * x + c * y + tx, a * 0 + b * x + d * y + ty)

    for ops in contours:
        for op in ops:
            if op[0] == "M":
                verts.append(tf(op[1], op[2])), codes.append(MPath.MOVETO)
            elif op[0] == "L":
                verts.append(tf(op[1], op[2])), codes.append(MPath.LINETO)
            else:
                verts.append(tf(op[1], op[2])), codes.append(MPath.CURVE3)
                verts.append(tf(op[3], op[4])), codes.append(MPath.CURVE3)

        verts.append(verts[-1]), codes.append(MPath.CLOSEPOLY)

    return MPath(verts, codes) if verts else None


def shape_artists(kind, body, matrix=(1, 0, 0, 1, 0, 0)):
    """[(PathPatch kwargs, Path)] for a shape: its fills, then its strokes."""
    bounds, all_fills, all_lines, edges = parse_shape(kind, body)
    out = []

    for set_no, fills in enumerate(all_fills):
        for fill_no, style in enumerate(fills, 1):
            segs = []

            for f0, f1, ln, seg, s in edges:
                if s != set_no:
                    continue

                if f1 == fill_no:
                    segs.append(segment_ops(seg, False))

                if f0 == fill_no:
                    segs.append(segment_ops(seg, True))

            if segs and style[0] != "bitmap":
                if (path := to_path(stitch(segs), matrix)):
                    out.append((dict(facecolor=style[1], edgecolor="none", linewidth=0), path))

    for set_no, lines in enumerate(all_lines):
        for line_no, (width, color) in enumerate(lines, 1):
            segs = [segment_ops(seg, False) for f0, f1, ln, seg, s in edges if s == set_no and ln == line_no]

            if segs:
                contours = []

                for start, end, op in segs:
                    contours.append([("M",) + start, op])

                path = to_path(contours, matrix)
                out.append((dict(facecolor="none", edgecolor=color, linewidth=max(width / 20 * 0.72, 0.3)), path))

    return [((x1 := bounds)[0] / 20, bounds[1] / 20, bounds[2] / 20, bounds[3] / 20), out]


def render(artists_with_bounds, path, scale=2.0, margin=1.0):
    """Draw [(PathPatch kwargs, Path)] into a transparent PNG; bounds (xmin, ymin, xmax, ymax) in pixels."""
    (xmin, ymin, xmax, ymax), artists = artists_with_bounds
    width, height = max(xmax - xmin, 1) + 2 * margin, max(ymax - ymin, 1) + 2 * margin
    fig = plt.figure(figsize=(width * scale / 100, height * scale / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(xmin - margin, xmax + margin)
    ax.set_ylim(ymax + margin, ymin - margin)
    ax.axis("off")

    for kwargs, mpath in artists:
        ax.add_patch(PathPatch(mpath, **kwargs))

    fig.savefig(path, transparent=True)
    plt.close(fig)
