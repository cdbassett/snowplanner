#!/usr/bin/env python3
"""Hover text for the game's map icons, keyed by zone id: data/zone_tips.tsv (zone id, title, subtitle), written by `python3 utils/zone_tips.py`.

Today it holds the upgrade each upgrade station gives (named from the game's English text); add other kinds of zones to build_zone_tips() to get tooltips for their icons too."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import gamefiles
from utils.snowrunner_utils import iterate_level_files_basic

TIPS_FILE = Path(__file__).resolve().parent.parent / "data" / "zone_tips.tsv"
_NAME = re.compile(r'\sName="([^"]+)"')
KIND_NAMES = {"engines": "Engine", "suspensions": "Suspension", "gearboxes": "Gearbox", "awds": "AWD", "winches": "Winch"}
_UI_NAME = re.compile(r'UiName="([^"]+)"')


def upgrade_ui_names():
    """{upgrade id (engine, suspension, gearbox, ... variant 'Name'): (its UiName text key, kind of part)}, from the class files in initial.pak"""
    out = {}
    pak = gamefiles.initial_pak()

    for fname in pak.all_names():
        if not (fname.startswith("[media]/classes/") and fname.endswith(".xml")):
            continue

        text = pak.read(fname).decode("utf-8", "replace")

        for m in _NAME.finditer(text):
            ui = _UI_NAME.search(text, m.end(), m.end() + 1500) # the UiName inside this element (before the next one starts)
            nxt = _NAME.search(text, m.end())

            if ui and (not nxt or ui.start() < nxt.start()):
                out.setdefault(m.group(1), (ui.group(1), fname.split("/")[2]))

    return out


def build_zone_tips():
    """[(zone id, title, subtitle)]"""
    strings = gamefiles.english_strings()
    ui_names = upgrade_ui_names()
    rows, missing = [], []

    for fname, data in iterate_level_files_basic():
        for zone_id, zone in data["zoneDesc"].items():
            giver = (zone.get("props") or {}).get("ZonePropertyUpgradesGiver")

            if giver is None:
                continue

            names, subs = [], []

            for upgrade in giver.get("upgrades", ()):
                key, kind = ui_names.get(upgrade, ("", ""))
                text = strings.get(key.upper())
                pretty = upgrade.replace("_", " ")

                if text: # generic names (Raised, Tuned Custom ...) are per truck: say which
                    names.append(text.replace("\\n", " "))
                    subs.append(f"{KIND_NAMES.get(kind, kind.capitalize())} upgrade ({pretty})")
                else:
                    names.append(pretty)
                    subs.append("Upgrade")
                    missing.append(upgrade)

            rows.append((zone_id, ", ".join(names) or "Upgrade", "; ".join(dict.fromkeys(subs)) or "Upgrade"))

    return rows, missing


def read_zone_tips():
    """{zone id: (title, subtitle)}"""
    out = {}

    if TIPS_FILE.exists():
        for line in TIPS_FILE.read_text(encoding="utf-8").splitlines()[1:]:
            zone_id, title, sub = (line.split("\t") + ["", ""])[:3]
            out[zone_id] = (title, sub)

    return out


if __name__ == "__main__":
    rows, missing = build_zone_tips()
    TIPS_FILE.write_text("zone_id\ttitle\tsubtitle\n" + "".join("\t".join(r) + "\n" for r in sorted(rows)), encoding="utf-8")
    print(f"{len(rows)} zone tips written to {TIPS_FILE}; {len(set(missing))} upgrade ids without an English name: {sorted(set(missing))[:15]}")
