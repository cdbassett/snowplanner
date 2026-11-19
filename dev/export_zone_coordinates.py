#!/usr/bin/env python3
"""Write the zone positions found in every level's data_for_ssl.bin (plus how well they agree with the positions already in the database)
to data/zone_coordinates_from_game.tsv and data/zone_coordinates_area_summary.tsv, to judge whether they can seed the positions of new locations.

db_x / db_y convert to the app's 0-1000 scale like the gates do (x = (world_x + 1000) / 2, y = (1000 - world_z) / 2) for the usual 2000-unit-wide map;
areas whose zones all lie within +-500 are 1000 units wide and use half the span (map_span_assumed says which)."""
import csv
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from database.config import snowplanner_db_filename
from utils import gamefiles, level_data

DATA = Path(__file__).resolve().parent.parent / "data"


def main():
    con = sqlite3.connect(f"file:{snowplanner_db_filename}?mode=ro", uri=True)
    db = {r[0]: r for r in con.execute("select id, area_id, item_type, name, x, y from map_item")}
    strings = gamefiles.english_strings_first()
    rows = []
    fits = {}

    for area_id in sorted(gamefiles.list_level_paks()):
        data = gamefiles.read_data_for_ssl(area_id)
        placed = []

        for zone_id, zone in level_data.parse_level_zones(data).items():
            p = level_data.zone_placement(data, zone)

            if abs(p.x) < 3000 and abs(p.z) < 3000: # the sky / day-night records have the same shape but no position
                placed.append((zone_id, zone, p))

        # some areas are only 1000 world units wide instead of 2000: every zone then lies within +-500
        max_abs = max([max(abs(p.x), abs(p.z)) for _, z, p in placed] or [0])
        half = 500 if max_abs <= 520 else 1000
        area_rows = []

        for zone_id, zone, p in placed:
            fx, fy = (p.x + half) / (2 * half) * 1000, (half - p.z) / (2 * half) * 1000
            rec = db.get(zone_id)
            dx, dy = (rec[4], rec[5]) if rec else (None, None)
            err = round(math.hypot(fx - dx, fy - dy)) if dx is not None and dy is not None else None
            area_rows.append([area_id, zone_id, rec[2] if rec else "", rec[3] if rec else "", zone.model, zone.model_kind, zone.name_key, strings.get(zone.name_key.upper(), ""),
                              round(p.x, 2), round(p.z, 2), round(p.dir_x, 2), round(p.dir_z, 2), round(p.width, 2), round(p.depth, 2), round(p.height, 2), round(fx, 1), round(fy, 1),
                              dx if dx is not None else "", dy if dy is not None else "", err if err is not None else "", half * 2])

        rows.extend(area_rows)
        known = [r for r in area_rows if r[17] != "" and r[18] != "" and r[2] != "gate"] # gates are placed by formula, not by hand, so they prove nothing
        entry = dict(zones=len(area_rows), known=len(known), max_abs=max_abs, span=str(half * 2))

        if known:
            errs = [r[19] for r in known]
            entry.update(median_err=float(np.median(errs)), within_15=sum(e <= 15 for e in errs), within_40=sum(e <= 40 for e in errs))
            # the hand-placed position of a zone is sometimes next to a *different* zone's coordinates (same-named sources lettered in another order), so also count the nearest zone of any kind
            pts = np.array([[r[15], r[16]] for r in area_rows], float)
            nearest = [float(np.min(np.hypot(pts[:, 0] - r[17], pts[:, 1] - r[18]))) for r in known]
            entry.update(near_15=sum(d <= 15 for d in nearest), near_30=sum(d <= 30 for d in nearest))

        if len(known) >= 3: # best linear fit per axis, to check the assumed width of the map
            wx, wz = np.array([r[8] for r in known]), np.array([r[9] for r in known])
            dbx, dby = np.array([r[17] for r in known], float), np.array([r[18] for r in known], float)
            ax, ay = np.polyfit(wx, dbx, 1), np.polyfit(wz, dby, 1)
            entry.update(fit_x=ax, fit_y=ay, resid_x=float(np.abs(np.polyval(ax, wx) - dbx).mean()), resid_y=float(np.abs(np.polyval(ay, wz) - dby).mean()))

        fits[area_id] = entry

    header = ["area_id", "zone_id", "db_type", "db_name", "model", "model_kind", "name_key", "name", "world_x", "world_z", "dir_x", "dir_z", "width", "depth", "height",
              "db_x", "db_y", "existing_db_x", "existing_db_y", "error_vs_existing", "map_span_assumed"]

    with open(DATA / "zone_coordinates_from_game.tsv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(header)
        w.writerows(rows)

    with open(DATA / "zone_coordinates_area_summary.tsv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["area_id", "zones_in_file", "zones_with_hand_placed_position", "median_error", "within_15", "within_40", "fit_x(slope,offset)", "fit_y(slope,offset)", "fit_resid_x", "fit_resid_y", "map_span_assumed", "max_abs_world_coordinate", "within_15_of_any_zone", "within_30_of_any_zone"])

        for area_id, e in fits.items():
            w.writerow([area_id, e["zones"], e["known"], round(e.get("median_err", float("nan")), 1) if "median_err" in e else "", e.get("within_15", ""), e.get("within_40", ""),
                        "%.3f,%.0f" % tuple(e["fit_x"]) if "fit_x" in e else "", "%.3f,%.0f" % tuple(e["fit_y"]) if "fit_y" in e else "",
                        round(e["resid_x"], 1) if "resid_x" in e else "", round(e["resid_y"], 1) if "resid_y" in e else "", e["span"], round(e["max_abs"]), e.get("near_15", ""), e.get("near_30", "")])

    print(len(rows), "zones written")


if __name__ == "__main__":
    main()
