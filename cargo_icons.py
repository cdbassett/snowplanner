"""Cargo stacks and the icon used to draw each cargo type on the maps."""
import re
from collections import namedtuple


class CargoStack(namedtuple("CargoStack", "name,count,text,loaded,note,kind", defaults=(False, None, "cargo"))):
    """A quantity of one cargo type. count None means unlimited. text is the plain-text form used where icons aren't drawn."""
    __slots__ = ()

    def __str__(self):
        return self.text

    @property
    def is_vehicle(self):
        return self.kind != "cargo"

    @property
    def icons(self):
        """Emoji drawn in the square; trailers show a truck followed by the trailer type."""
        if self.kind == "trailer":
            return [TRAILER_LEAD_ICON, vehicle_icon(self.name, self.kind)]

        return [vehicle_icon(self.name, self.kind) if self.is_vehicle else cargo_style(self.name)[0]]

    @property
    def icon(self):
        return "".join(self.icons)

    @property
    def width_factor(self):
        """Width of the square in icon-square widths; trailers are wider to hold two emoji."""
        return TRAILER_WIDTH_FACTOR if len(self.icons) > 1 else 1

    @property
    def fill(self):
        return VEHICLE_FILLS[self.kind] if self.is_vehicle else cargo_style(self.name)[1]

    @property
    def border(self):
        """(color, width) of the icon square's outline."""
        if self.is_vehicle:
            return VEHICLE_BORDERS[self.kind], 2

        return ("blue", 1) if self.loaded else ("#555", 1)

    @property
    def count_text(self):
        if self.is_vehicle:
            return "" if self.count in (None, 1) else str(self.count)

        return "∞" if self.count is None else str(self.count)

    @property
    def tip_sub(self):
        if self.note:
            return self.note

        if self.is_vehicle:
            return self.kind.capitalize()

        return ("Unlimited ∞" if self.count is None else f"Count: {self.count}") + (" (loaded on trailer)" if self.loaded else "")


class Recipe(namedtuple("Recipe", "product,ingredients,text")):
    """What a crafting location makes: product (a CargoStack with the amount crafted per step) from ingredients (CargoStacks)."""
    __slots__ = ()

    def __str__(self):
        return self.text


POWER_NAME = "Power"
_RECIPE_RE = re.compile(r"^\s*(\d+)\s+(.+?)\s*=\s*(.+?)\s*$")
_INGREDIENT_RE = re.compile(r"^\s*(\d+)\s+(.+?)\s*$")
_ENERGY_RE = re.compile(r"^(\d+)\s*energy$", re.I)


def parse_recipe(craft_desc):
    """Parse e.g. '2 Wooden Planks [1]=(1 Long Logs+1 Cement [1])' or '1 Fuel [1]=100 energy'; None if it doesn't fit."""
    if not (m := _RECIPE_RE.match(craft_desc or "")):
        return None

    product_cnt, product_name, rhs = int(m.group(1)), m.group(2), m.group(3)
    product = CargoStack(product_name, product_cnt, craft_desc, note=f"Crafts {product_cnt} per step")
    ingredients = []

    if (em := _ENERGY_RE.match(rhs)):
        ingredients.append(CargoStack(POWER_NAME, int(em.group(1)), rhs, note=f"Needs {em.group(1)} energy per step"))
    else:
        for part in rhs.strip("()").split("+"):
            if not (im := _INGREDIENT_RE.match(part)):
                return None

            ingredients.append(CargoStack(im.group(2), int(im.group(1)), part, note=f"Needs {im.group(1)} per step"))

    return Recipe(product, ingredients, craft_desc)


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
    "transformer": ("🔋", None),
    "power": ("⚡", None),
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

# 🔩🗄📏🗜⛓️➖🔗📦🎞️⚙️🛠️⚙⏣🌑☀️🟨🏖️◉⌬𓏏 ⃣◇🟥🕋🚂🚅🚈🚐🚃🔧𖥕𖦏𓎚✺✴︎𓄧𖣐⚕⎍
# 🥬🥦🥒🥕🫑🌶️🥤🥗🍔🍗🍟🥓🍞🌽

# icons for the generic groups offered in the cargo filter list
GENERIC_STYLES = {
    "logs": ("🪵", None),
    "planks": ("📏", None),
    "pipes": ("⭕", None),
    "concrete": ("🪨", None),
    "metal": ("𓈘", None),
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


TRAILER_WIDTH_FACTOR = 1.6
TRAILER_LEAD_ICON = "🚛"
VEHICLE_FILLS = {"truck": "#e3d2fa", "trailer": "#c9ece6"}
VEHICLE_BORDERS = {"truck": "#6a3fb5", "trailer": "#1b8a7a"}

_TRAILER_WORDS = ("trailer", "semi", "carrier", "flatbed", "platform")
TRAILER_NAMES = {"generator", "turbo generator stator"} # trailers whose names (and database type) don't say so

# first keyword found in the lowercase name wins; vehicles of the same kind get different icons by function
TRAILER_ICONS = [
    ("fuel", "⛽"), ("tanker", "⛽"), ("water", "💧"), ("log", "🌲"), ("construction", "🛠️"),
    ("service", "🔧"), ("maintenance", "🔧"), ("curtainside", "🎪"), ("sideboard", "🔲"),
    ("crane", "🏗️"), ("drill", "⚕"), ("rig", "🗼"), ("coiled", "➰"),
    ("rock", "🪨"), ("fishing", "🎣"), ("boat", "🎣"), ("home", "🏠"),
    ("movie", "🎬"), ("rocket", "🚀"), ("scout", "⛺"), ("stator", "⚡"), ("generator", "🔌"),
    ("flatbed", "𓄧"), ("stepdeck", "➖"), ("gooseneck", "➖"),
]
DEFAULT_TRAILER_ICON = "🔗"

TRUCK_ICONS = [
    ("scout", "🛻"), ("ck1500", "🛻"), ("hummer", "🚙"), ("earthroamer", "🚐"),
    ("jangsu", "🚙"), ("neo falcon", "🚗"), ("cultivator", "🚜"), ("planter", "🚜"),
    ("harvester", "🚜"), ("caterpillar", "🏗️"), ("kirovets", "🚜"),
    ("locomotive", "🚂"), ("generator", "🔌"), ("turbine", "🔌"), ("stator", "🔌"),
    ("cabin", "🏠"), ("rocket", "🚀"), ("grinder", "⚙️"), ("anchor", "⚓"),
    ("pump", "💦"), ("exploration", "🔭"), ("loadstar", "🚐"),
]
DEFAULT_TRUCK_ICON = "🚚"


def vehicle_kind(name):
    key = name.lower()
    return "trailer" if key in TRAILER_NAMES or any(w in key for w in _TRAILER_WORDS) else "truck"


def vehicle_icon(name, kind):
    key = name.lower()
    rules, default = (TRAILER_ICONS, DEFAULT_TRAILER_ICON) if kind == "trailer" else (TRUCK_ICONS, DEFAULT_TRUCK_ICON)
    return next((icon for word, icon in rules if word in key), default)


def vehicle_stack(name, text=None, kind=None, count=None):
    """A truck or trailer drawn as an icon square; kind is guessed from the name unless known."""
    kind = "trailer" if name.lower() in TRAILER_NAMES else kind or vehicle_kind(name)
    return CargoStack(name, count, text or name, kind=kind)
