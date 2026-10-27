"""Cargo stacks and the icon used to draw each cargo type on the maps."""
import re
from collections import namedtuple


class CargoStack(namedtuple("CargoStack", "name,count,text,loaded", defaults=(False,))):
    """A quantity of one cargo type. count None means unlimited. text is the plain-text form used where icons aren't drawn."""
    __slots__ = ()

    def __str__(self):
        return self.text

    @property
    def icon(self):
        return cargo_style(self.name)[0]

    @property
    def fill(self):
        return cargo_style(self.name)[1]

    @property
    def count_text(self):
        return "∞" if self.count is None else str(self.count)


DEFAULT_ICON = "📦"
DEFAULT_FILL = "white"

# The same size tiers are used for every cargo family (logs, planks, pipes, fuel tanks) so size reads the same everywhere
TIER_FILLS = {
    "S": "#8fcbff", # short / small
    "M": "#9be58f", # medium
    "L": "#ff9a9a", # long / large
    "burnt": "#a0a0a0",
}
TIER_LEGEND = [("S", "short / small"), ("M", "medium"), ("L", "long / large")]

# keyed by lowercase name without the trailing "[size]" marker: (emoji, size tier or None)
CARGO_STYLES = {
    "short logs": ("🪵", "S"),
    "medium logs": ("🪵", "M"),
    "long logs": ("🪵", "L"),
    "burnt logs": ("🪵", "burnt"),
    "wooden planks": ("📏", "S"),
    "medium planks": ("📏", "M"),
    "long planks": ("📏", "L"),
    "small pipes": ("⭕", "S"),
    "medium pipes": ("⭕", "M"),
    "large pipe": ("⭕", "L"),
    "water pipe": ("🇴", None),
    "stage 2 fuel tank": ("⛽", "M"),
    "stage 3 fuel tank": ("⛽", "L"),
    "fuel": ("🛢️", None),
    "bricks": ("🧱", None),
    "cabin": ("🏠", None),
    "cable car": ("🚡", None),
    "cellulose": ("🧻", None),
    "cement": ("🪣", None),
    "chemical barrels": ("☣️", None),
    "concrete blocks": ("⬜️", None),
    "concrete slab": ("➖", None),
    "consumables": ("🌽", None),
    "drilling equipment": ("🔌", None),
    "drilling spare parts": ("🛠️", None),
    "fertilizer": ("🌱", None),
    "freezer": ("🧊", None),
    "garbage": ("♻️", None),
    "hay bale": ("🌾", None),
    "industrial chiller": ("❄️", None),
    "industrial boiler": ("🔥", None),
    "metal beams": ("𓈘", None),
    "metal rolls": ("🔘", None),
    "mine cart": ("⛏️", None),
    "multistage pump": ("⛲", None),
    "oil barrels": ("🛢", None),
    "oil rig drill": ("🗼", None),
    "oversized cargo": ("🚚", None),
    "packaged sand": ("🟨", None),
    "part of the airplane fuselage": ("✈️", None),
    "wing fragments with the engine": ("🛩️", None),
    "potatoes": ("🥔", None),
    "cargopotatogmo": ("🍠", None),
    "rail section": ("🛤️", None),
    "rails": ("🚃", None),
    "service spare parts": ("🔧", None),
    "repair parts": ("🧰", None),
    "vehicle spare parts": ("⚙️", None),
    "engine assembly": ("🔩", None),
    "silver": ("🥈", None),
    "gold": ("🥇", None),
    "slate blocks": ("⬛", None),
    "solar panels": ("🟦", None),
    "soybeans": ("🫘", None),
    "special cargo": ("☢", None),
    "tetrapod": ("🔺", None),
    "transformer": ("⚡", None),
    "water": ("💧", None),
    "data buoy": ("⚓", None),
    "cistern": ("🫙", None),
    "sequoia": ("🌲", None),
    "cargo container": ("🎞️", None),
    "empty container": ("🥡", None),
    "filled container": ("📦", None),
    "secure container": ("🔒", None),
    "forkliftcaravancontainer": ("🏕️", None),
    "cargoforcklift": ("🚜", None),
    "ba-20 armored car": ("🚙", None),
}

# 🔩🗄📏🗜⛓️➖🔗📦🎞️⚙️🛠️⚙⏣🌑☀️🟨🏖️◉⌬𓏏 ⃣◇🟥🕋🚂🚅🚈🚐
# 🥬🥦🥒🥕🫑🌶️🥤🥗🍔🍗🍟🥓🍞🌽

# icons for the generic groups offered in the cargo filter list
GENERIC_STYLES = {
    "logs": ("🪵", None),
    "planks": ("📏", None),
    "pipes": ("⭕", None),
    "concrete": ("🪨", None),
    "metal": ("🏗️", None),
}


def normalize_cargo_name(name):
    return re.sub(r"\s*\[\d+\]\s*$", "", name).strip().lower()


def _style(emoji, tier):
    return emoji, TIER_FILLS.get(tier, DEFAULT_FILL)


def cargo_style(name):
    """(emoji, fill color) for a cargo name."""
    key = normalize_cargo_name(name)

    if (style := CARGO_STYLES.get(key) or GENERIC_STYLES.get(key)):
        return _style(*style)

    return _style(DEFAULT_ICON, None)


def has_cargo_style(name):
    """True if the name has a specific icon (not just the fallback)."""
    key = normalize_cargo_name(name)
    return key in CARGO_STYLES or key in GENERIC_STYLES
