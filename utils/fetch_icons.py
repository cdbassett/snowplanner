"""Download the game-icons.net SVGs (CC BY 3.0) used by icon_art.py into icons/game-icons/. Run: python3 utils/fetch_icons.py"""
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from icon_art import all_icon_names, ICON_DIR

ICON_DIR.mkdir(parents=True, exist_ok=True)
missing = []

for name in sorted(all_icon_names()):
    dest = ICON_DIR / f"{name}.svg"

    if dest.exists():
        continue

    try:
        req = urllib.request.Request(f"https://api.iconify.design/game-icons/{name}.svg", headers={"User-Agent": "snowplanner-icon-fetch"})
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode()
    except Exception as e:
        missing.append(f"{name}: {e}")
        continue

    if "<path" not in body:
        missing.append(f"{name}: not found")
        continue

    dest.write_text(body)
    time.sleep(0.5)

print("missing:", *missing, sep="\n  " if missing else " none\n")
