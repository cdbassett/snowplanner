"""User configuration, read from config.yaml in the project root.

If config.yaml doesn't exist it is generated with the defaults below.
Import `config` for the loaded settings.
"""
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

if sys.platform == "win32":
    DEFAULT_SAVED_GAME_DIR = "~/Documents/My Games/SnowRunner/base/storage"
    DEFAULT_CLIENT_DIR = r"C:\Program Files (x86)\Steam\steamapps\common\SnowRunner\preload\paks\client"
else:
    DEFAULT_SAVED_GAME_DIR = "~/.local/share/Steam/steamapps/compatdata/1465360/pfx/drive_c/users/steamuser/Documents/My Games/SnowRunner/base/storage"
    DEFAULT_CLIENT_DIR = "~/.local/share/Steam/steamapps/common/SnowRunner/preload/paks/client"

CONFIG_HEADER = """\
# SnowPlanner configuration. Generated with defaults if missing; edit as needed.
#
# saved_game_dir:   folder containing SnowRunner save games
# client_dir:       SnowRunner install's preload/paks/client directory
# initial_pak_dir:  directory containing initial.pak; leave null to use client_dir
"""


@dataclass
class Config:
    saved_game_dir: Path
    client_dir: Path
    initial_pak_dir: Path


def _default_values():
    return {
        "saved_game_dir": DEFAULT_SAVED_GAME_DIR,
        "client_dir": DEFAULT_CLIENT_DIR,
        "initial_pak_dir": None,
    }


def write_default_config(path=CONFIG_PATH):
    with open(path, "w", encoding="utf-8") as f:
        f.write(CONFIG_HEADER)
        yaml.safe_dump(_default_values(), f, default_flow_style=False, sort_keys=False, width=1000)


def load_config(path=CONFIG_PATH):
    path = Path(path)

    if not path.exists():
        write_default_config(path)

    with open(path, encoding="utf-8") as f:
        values = _default_values() | (yaml.safe_load(f) or {})

    def to_path(val):
        return Path(val).expanduser()

    client_dir = to_path(values["client_dir"])
    initial_pak_dir = to_path(values["initial_pak_dir"]) if values["initial_pak_dir"] else client_dir

    return Config(to_path(values["saved_game_dir"]), client_dir, initial_pak_dir)


config = load_config()
