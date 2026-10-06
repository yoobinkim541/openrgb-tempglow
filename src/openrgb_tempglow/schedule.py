"""Timed lighting rules: during a daily time window, change what selected parts show.

Only the standard library is used here so the GUI can import it without openrgb-python.
"""
import copy

from .config import PARTS

ACTIONS = ("off", "dim", "lighting")
ALL_DAYS = list(range(7))  # 0 = Monday, as datetime.weekday()

RULE_DEFAULT = {
    "enabled": True,
    "name": "",
    "start": "00:00",
    "end": "09:00",
    "days": ALL_DAYS,
    "parts": list(PARTS),
    # "off": lights off; "dim": scale the usual brightness to `dim` percent;
    # "lighting": show `lighting` instead of the usual settings
    "action": "off",
    "dim": 20,
    "lighting": {"effect": "static", "color": "#ffffff", "brightness": 100, "speed": 50},
}


def new_rule(**kw):
    rule = copy.deepcopy(RULE_DEFAULT)
    rule.update(kw)
    return rule


def normalize(rules):
    """Fill missing fields so older or hand-edited configs don't break the daemon or GUI."""
    out = []
    for r in rules if isinstance(rules, list) else []:
        if not isinstance(r, dict):
            continue
        rule = new_rule(**{k: v for k, v in r.items() if k in RULE_DEFAULT})
        rule["lighting"] = {**RULE_DEFAULT["lighting"], **(r.get("lighting") or {})}
        out.append(rule)
    return out


def parse_hhmm(s):
    """'HH:MM' -> minutes since midnight."""
    h, m = s.split(":")
    h, m = int(h), int(m)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(f"invalid time: {s!r}")
    return h * 60 + m


def is_active(rule, now):
    """Whether the rule applies at datetime `now`.

    The window may cross midnight; `days` refers to the day the window starts on.
    start == end means the whole day.
    """
    if not rule.get("enabled"):
        return False
    try:
        start, end = parse_hhmm(rule["start"]), parse_hhmm(rule["end"])
    except (KeyError, ValueError, AttributeError):
        return False
    minute, day = now.hour * 60 + now.minute, now.weekday()
    days = rule.get("days", ALL_DAYS)
    if start < end:
        return start <= minute < end and day in days
    if start == end:
        return day in days
    if minute >= start:
        return day in days
    return minute < end and (day - 1) % 7 in days


def active_rules(rules, now):
    return [i for i, r in enumerate(rules) if is_active(r, now)]


def effective_parts(cfg, now):
    """Per-part settings after applying active rules in order (later rules win)."""
    out = {p: dict(cfg["parts"][p]) for p in PARTS}
    for rule in cfg.get("schedules", []):
        if not is_active(rule, now):
            continue
        for part in rule.get("parts", []):
            if part not in out:
                continue
            action = rule.get("action")
            if action == "off":
                out[part]["effect"] = "off"
            elif action == "dim":
                b = out[part].get("brightness", 100) * max(0, min(100, rule.get("dim", 100))) / 100
                out[part]["brightness"] = b
            elif action == "lighting":
                out[part] = dict(rule["lighting"])
    return out
