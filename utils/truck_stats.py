"""Capacities of a truck's stock parts, from its definition in the game files: how many repair points a fully damaged truck needs and how much fuel its tank holds."""
import functools
import re

from utils import gamefiles

SOCKET_RE = re.compile(r'<(?:Engine|Gearbox|Suspension)Socket\b[^>]*>', re.S)
FOLDERS = {"Engine": "engines", "Gearbox": "gearboxes", "Suspension": "suspensions"}


def attr(tag, name):
    m = re.search(rf'\b{name}="([^"]*)"', tag)
    return m.group(1) if m else None


@functools.cache
def component_files():
    """{(folder, file stem): name in the pak}"""
    out = {}

    for name in gamefiles.initial_pak().all_names():
        if (m := re.match(r"\[media\]/(?:_dlc/[^/]+/)?classes/(engines|gearboxes|suspensions)/([^/]+)\.xml$", name)):
            out[(m.group(1), m.group(2))] = name

    return out


def part_damage_capacity(folder, file_stem, part_name):
    """DamageCapacity of the part called part_name in the part file (its own value, or the one of its template), or None."""
    if not (path := component_files().get((folder, file_stem))):
        return None

    text = gamefiles.initial_pak().read(path).decode("utf-8", errors="replace")

    for m in re.finditer(r'<(\w+)\b[^>]*?\bName="%s"[^>]*>' % re.escape(part_name), text, re.S):
        if (cap := attr(m.group(0), "DamageCapacity")):
            return float(cap)

        if (template := attr(m.group(0), "_template")) and (t := re.search(rf'<{re.escape(template)}\b[^>]*>', text, re.S)) and (cap := attr(t.group(0), "DamageCapacity")):
            return float(cap)

    return None


@functools.cache
def truck_stats(truck_id):
    """(repair points of a completely damaged truck, fuel tank liters) of a stock truck, or None when it can't be worked out. The points are the damage capacities of its engine, gearbox,
    suspension and fuel tank (checked against Kenworth 963: 180 + 230 + 260 + 50 = 720)."""
    pak = gamefiles.initial_pak()
    path = next((n for n in pak.all_names() if re.match(rf"\[media\]/(?:_dlc/[^/]+/)?classes/trucks/{re.escape(truck_id)}\.xml$", n)), None)

    if not path:
        return None

    text = pak.read(path).decode("utf-8", errors="replace")
    total = 0

    for socket in SOCKET_RE.findall(text):
        kind = re.match(r"<(\w+?)Socket", socket).group(1)
        default, stem = attr(socket, "Default"), attr(socket, "Type")
        cap = next((c for st in (stem or "").split(",") if default and (c := part_damage_capacity(FOLDERS[kind], st.strip(), default)) is not None), None) # the socket accepts parts from several files

        if cap is None:
            return None

        total += cap

    tank = re.search(r"<FuelTank\b[^>]*DamageCapacity=\"([\d.]+)\"", text)
    fuel = re.search(r'\bFuelCapacity="([\d.]+)"', text)

    if not tank or not fuel:
        return None

    return total + float(tank.group(1)), float(fuel.group(1))
