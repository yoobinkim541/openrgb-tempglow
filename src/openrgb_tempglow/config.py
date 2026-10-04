"""Configuration and status files shared by the daemon and the GUI.

Only the standard library is used here so the GUI can import it without openrgb-python.
"""
import copy
import json
import os

PARTS = ("case", "fans", "gpu", "ram")
EFFECTS = ("static", "breathing", "rainbow", "off")
NONE = "none"


def config_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "openrgb-tempglow")


def config_path():
    return os.path.join(config_dir(), "config.json")


def status_path():
    return os.path.join(config_dir(), "status.json")


DEFAULT = {
    "version": 2,
    "parts": {
        "case": {"effect": "static", "color": "#ffffff", "brightness": 100, "speed": 50},
        "fans": {"effect": "breathing", "color": "#ffffff", "brightness": 100, "speed": 30},
        "gpu": {"effect": "static", "color": "#ffffff", "brightness": 100, "speed": 50},
        "ram": {"effect": "static", "color": "#ffffff", "brightness": 100, "speed": 50},
    },
    "overheat": {
        "enabled": True,
        "color": "#ff0000",
        "cpu_hot": 90,
        "gpu_hot": 85,
        "hysteresis": 10,
        "parts": ["fans"],
    },
    # "<device>::<zone>" -> part name or "none". Zones missing here use the type-based default.
    "assignments": {},
    # "<device>::<zone>" -> LED count for resizable (addressable) zones
    "zone_leds": {},
    "openrgb": {
        "host": "127.0.0.1",
        "port": 6742,
        # Start an OpenRGB server automatically when none is reachable
        "manage_server": True,
        # Explicit command (list) to start OpenRGB; empty = auto-detect
        "command": [],
    },
    # Built-in drivers for hardware OpenRGB does not support yet
    "extra_drivers": {"colorful_gpu": True},
}


def merge(base, override):
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k not in ("assignments", "zone_leds"):
            out[k] = merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load(path=None):
    path = path or config_path()
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return copy.deepcopy(DEFAULT)
    return merge(DEFAULT, data)


def atomic_write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)  # readers never see a half-written file


def save(cfg, path=None):
    atomic_write_json(path or config_path(), cfg)


def load_status(path=None):
    try:
        with open(path or status_path()) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"invalid color: {h!r}")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(r, g, b):
    return f"#{r:02x}{g:02x}{b:02x}"
