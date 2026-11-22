#!/usr/bin/env python3
"""Crop the (portrait) vehicle store images to squares of the same width, placed so the vehicle fits in the square as much as possible.

The vehicle is where the picture has fine detail (the backgrounds are blurred): the rows of a smoothed Laplacian detail map are summed, and the square is
centred on the band holding 2% .. 97% of that detail (a little lower, as wheels and mud have less detail than the cab, and never ending above the band's end plus a margin so tyres are kept), clamped to the picture. (GrabCut
was tried first; it took sky and buildings for part of the vehicle and missed wheels.)

    python3 dev/square_truck_images.py IN_DIR OUT_DIR       # IN_DIR from extract_truck_images.py; writes OUT_DIR/<id>.png and OUT_DIR/square_crops.tsv
"""
import sys
from pathlib import Path

import cv2
import numpy as np

LOW, HIGH = 0.02, 0.995 # share of the detail above / below the band the square is centred on
BIAS = 0.03 # shift down, in square widths
BOTTOM_MARGIN = 0.04 # the square always reaches this far (in square widths) below the detail band, so the tyres are not cut off


def detail_map(bgr, power=1.5):
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    detail = cv2.GaussianBlur(np.abs(cv2.Laplacian(cv2.GaussianBlur(gray, (0, 0), 1.0), cv2.CV_32F)), (0, 0), 4)
    return (detail / (detail.max() + 1e-6)) ** power


def best_square(bgr):
    """(top row of the square, share of the detail inside it, first and last row of the detail band)"""
    h, w = bgr.shape[:2]
    rows = detail_map(bgr).sum(axis=1)
    cum = np.cumsum(rows) / rows.sum()
    first, last = int(np.searchsorted(cum, LOW)), int(np.searchsorted(cum, HIGH))
    top = max((first + last) / 2 + BIAS * w - w / 2, last + BOTTOM_MARGIN * w - w)
    top = int(round(min(max(top, 0), h - w)))
    return top, rows[top:top + w].sum() / rows.sum(), (first, last)


def main(in_dir, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []

    for path in sorted(Path(in_dir).glob("*.png")):
        image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        top, share, (first, last) = best_square(image[:, :, :3])
        w = image.shape[1]
        cv2.imwrite(str(out_dir / path.name), image[top:top + w])
        rows.append((path.stem, top, image.shape[0], f"{share:.2f}", first, last))

    with open(out_dir / "square_crops.tsv", "w") as f:
        f.write("truck_id\ttop\timage_height\tdetail_share_in_square\tdetail_first_row\tdetail_last_row\n")
        f.writelines("\t".join(map(str, r)) + "\n" for r in rows)

    print(f"{len(rows)} images written to {out_dir}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)

    main(*sys.argv[1:])
