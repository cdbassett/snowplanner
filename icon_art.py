"""Colored SVG icons (game-icons.net, CC BY 3.0 - see icons/ATTRIBUTION.md) used instead of emoji on the maps.

ART maps a lowercase cargo name to (icon file name, color). Vehicles are matched by keyword like in cargo_icons.py.
Anything not listed here keeps drawing its emoji.
"""
import base64
from functools import lru_cache
from pathlib import Path

ICON_DIR = Path(__file__).parent / "icons" / "game-icons"

WOOD, STEEL, RUST, WATER, FUEL, GREEN, GOLD, HAZARD, STONE, RED = "#8b5a2b", "#5a6b7b", "#b5532a", "#1f78d1", "#d9480f", "#2f9e44", "#e0a800", "#c2a600", "#6b6b6b", "#c92a2a"

CARGO_ART = {
    "short logs": ("log", WOOD), "medium logs": ("log", WOOD), "long logs": ("log", WOOD), "burnt logs": ("log", "#333"),
    "wooden planks": ("planks", "#c68642"), "medium planks": ("planks", "#c68642"), "long planks": ("planks", "#c68642"),
    "small pipes": ("pipes", STEEL), "medium pipes": ("pipes", STEEL), "large pipe": ("straight-pipe", STEEL), "water pipe": ("straight-pipe", WATER),
    "stage 2 fuel tank": ("fuel-tank", RUST), "stage 3 fuel tank": ("fuel-tank", RUST),
    "fuel": ("oil-drum", FUEL), "oil barrels": ("barrel", "#333"), "chemical barrels": ("barrel", HAZARD),
    "bricks": ("brick-pile", RUST), "cabin": ("wood-cabin", WOOD),
    "cellulose": ("rolled-cloth", "#d9d2c0"), "cement": ("concrete-bag", STONE),
    "concrete blocks": ("stone-block", STONE), "concrete slab": ("stone-tablet", STONE), "slate blocks": ("stone-block", "#2b2d33"),
    "consumables": ("cardboard-box", "#c68642"), "drilling equipment": ("drill", STEEL), "drilling spare parts": ("cog", STEEL),
    "fertilizer": ("fertilizer-bag", GREEN), "freezer": ("fridge", "#4dabf7"), "industrial chiller": ("snowflake-1", "#4dabf7"),
    "industrial boiler": ("furnace", RED), "garbage": ("recycle", GREEN),
    "metal beams": ("i-beam", STEEL), "metal rolls": ("metal-disc", STEEL), "mine cart": ("mine-wagon", STEEL),
    "multistage pump": ("oil-pump", STEEL), "oil rig drill": ("oil-rig", STEEL), "oversized cargo": ("cargo-crate", "#c68642"),
    "part of the airplane fuselage": ("airplane", STEEL), "wing fragments with the engine": ("plane-wing", STEEL),
    "potatoes": ("potato", "#c68642"), "cargopotatogmo": ("potato", "#9c36b5"),
    "rail section": ("railway", STEEL), "rails": ("railway", STEEL),
    "service spare parts": ("wrench", STEEL), "repair parts": ("toolbox", RED), "vehicle spare parts": ("hexagonal-nut", STEEL),
    "engine assembly": ("gears", STEEL), "silver": ("metal-bar", "#adb5bd"), "gold": ("gold-bar", GOLD),
    "solar panels": ("solar-power", WATER), "soybeans": ("seedling", GREEN), "special cargo": ("radioactive", HAZARD),
    "transformer": ("car-battery", STEEL), "power": ("lightning-arc", GOLD), "water": ("water-drop", WATER),
    "data buoy": ("buoy", RED), "cistern": ("water-tank", WATER), "sequoia": ("log", "#2b6a3a"),
    "cargo container": ("cargo-crate", RUST), "empty container": ("cardboard-box-closed", "#c68642"), "filled container": ("cardboard-box-closed", "#c68642"),
    "secure container": ("locked-box", STEEL), "forkliftcaravancontainer": ("caravan", GREEN), "cargoforcklift": ("forklift", GOLD),
    "ba-20 armored car": ("jeep", "#556b2f"),
    "cable car": ("bus", RED), "cable drum": ("wire-coil", STEEL), "extended crew cabin": ("wood-cabin", STEEL), "rescue shelter": ("camping-tent", RED),
    "potato samples": ("potato", GOLD), "hay bale": ("wheat", "#d4a017"), "tetrapod": ("caltrops", STONE),
    # generic groups in the cargo filter list
    "logs": ("log", WOOD), "planks": ("planks", "#c68642"), "pipes": ("pipes", STEEL), "concrete": ("stone-block", STONE), "metal": ("i-beam", STEEL),
}
DEFAULT_CARGO_ART = ("cardboard-box", "#c68642")

TRAILER_LEAD_ART = ("truck", "#6a3fb5")
TRAILER_ART = [
    ("fuel", ("fuel-tank", RUST)), ("tanker", ("fuel-tank", RUST)), ("water", ("water-tank", WATER)), ("log", ("log", WOOD)),
    ("service", ("wrench", STEEL)), ("maintenance", ("toolbox", RED)), ("crane", ("cargo-crane", GOLD)), ("drill", ("drill", STEEL)),
    ("rig", ("oil-rig", STEEL)), ("coiled", ("wire-coil", STEEL)), ("boat", ("sailboat", WATER)), ("fishing", ("boat-fishing", WATER)),
    ("home", ("house", WOOD)), ("movie", ("clapperboard", "#333")), ("rocket", ("rocket", RED)), ("scout", ("camping-tent", GREEN)),
    ("stator", ("lightning-arc", GOLD)), ("generator", ("electrical-socket", STEEL)), ("flatbed", ("flatbed", STEEL)),
]
DEFAULT_TRAILER_ART = ("flatbed", STEEL)

TRUCK_ART = [
    ("scout", ("jeep", GREEN)), ("ck1500", ("jeep", GREEN)), ("hummer", ("jeep", "#556b2f")), ("jangsu", ("jeep", "#556b2f")),
    ("cultivator", ("farm-tractor", GREEN)), ("planter", ("farm-tractor", GREEN)), ("harvester", ("farm-tractor", GREEN)),
    ("kirovets", ("farm-tractor", GREEN)), ("futom", ("farm-tractor", GREEN)), ("caterpillar", ("bulldozer", GOLD)),
    ("locomotive", ("steam-locomotive", "#333")), ("rocket", ("rocket", RED)), ("cabin", ("house", WOOD)), ("anchor", ("anchor", STEEL)),
    ("pump", ("oil-pump", STEEL)), ("exploration", ("telescope", STEEL)),
]
DEFAULT_TRUCK_ART = ("truck", "#6a3fb5")


def all_icon_names():
    names = {n for n, _ in CARGO_ART.values()} | {DEFAULT_CARGO_ART[0], TRAILER_LEAD_ART[0], DEFAULT_TRAILER_ART[0], DEFAULT_TRUCK_ART[0]}
    return names | {n for _, (n, _) in TRAILER_ART} | {n for _, (n, _) in TRUCK_ART}


def cargo_art(key):
    """(icon name, color) for a normalized cargo name, or None."""
    return CARGO_ART.get(key)


def vehicle_art(name, kind):
    key = name.lower()
    rules, default = (TRAILER_ART, DEFAULT_TRAILER_ART) if kind == "trailer" else (TRUCK_ART, DEFAULT_TRUCK_ART)
    return next((art for word, art in rules if word in key), default)


@lru_cache(maxsize=None)
def icon_svg(name, color):
    """The icon's SVG text with its color applied, or None if the file hasn't been downloaded."""
    path = ICON_DIR / f"{name}.svg"

    if not path.exists():
        return None

    return path.read_text().replace("currentColor", color)


@lru_cache(maxsize=None)
def icon_data_uri(name, color):
    svg = icon_svg(name, color)
    return svg and "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


# Raster icons: icons/raster/<cargo|trailer|truck>/<file>.png. A trailer/truck with one is drawn with that single icon instead of SVG art.
RASTER_DIR = Path(__file__).parent / "icons" / "raster"
VEHICLE_RASTER = {
    "trailer": [ # first rule whose keyword (or all keywords of a tuple) is in the lowercase name wins, so list specific rules first
        ("curtainside", "curtainside.png"), (("scout", "fuel"), "scout_fuel.png"), (("semi", "fuel"), "semi_fuel.png"), ("fuel", "fuel.png"),
        ("ramp", "ramp.png"), (("wide", "flatbed"), "wide_flatbed.png"), ("flatbed", "flatbed.png"), (("sideboard", "semi"), "sideboard_semi.png"),
        ("sideboard", "sideboard.png"), ("stepdeck", "stepdeck.png"), ("gooseneck", "gooseneck.png"), ("coiled", "coiled_tubing.png"), ("log", "log.png"),
    ],
    "truck": [],
}

# cargo families that share one base raster icon (the size tier is shown by the square's color)
CARGO_RASTER_BASE = {"short logs": "logs", "medium logs": "logs", "long logs": "logs", "burnt logs": "logs",
                     "wooden planks": "planks", "medium planks": "planks", "long planks": "planks"}


def raster_uri(kind, name):
    """Data URI of the PNG for a vehicle name (kind trailer/truck) or normalized cargo name (kind cargo), or None."""
    if kind == "cargo":
        filename = f"{CARGO_RASTER_BASE.get(name, name)}.png"
    else:
        filename = next((f for words, f in VEHICLE_RASTER.get(kind, []) if all(w in name.lower() for w in ((words,) if isinstance(words, str) else words))), None)

    return filename and _png_uri(RASTER_DIR / kind / filename)


_png_cache = {}


def _png_uri(path):
    """Cached by path and file mtime, so new or replaced PNGs are picked up without a restart (a missing file is never cached)."""
    if not path.exists():
        return None

    key = (path, path.stat().st_mtime_ns)

    if key not in _png_cache:
        _png_cache[key] = "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()

    return _png_cache[key]
