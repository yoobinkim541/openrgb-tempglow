from datetime import datetime

from openrgb_tempglow import config
from openrgb_tempglow.schedule import active_rules, effective_parts, is_active, new_rule, normalize

# 2026-10-05 is a Monday (weekday 0)
MON = datetime(2026, 10, 5)


def at(day_offset, hh, mm=0):
    return MON.replace(day=MON.day + day_offset, hour=hh, minute=mm)


def test_same_day_window():
    r = new_rule(start="00:00", end="09:00")
    assert is_active(r, at(0, 0)) and is_active(r, at(0, 8, 59))
    assert not is_active(r, at(0, 9)) and not is_active(r, at(0, 23))


def test_window_across_midnight_uses_start_day():
    r = new_rule(start="23:00", end="07:00", days=[4])  # Friday night
    assert is_active(r, at(4, 23, 30))  # Fri 23:30
    assert is_active(r, at(5, 6, 59))   # Sat 06:59, still Friday's window
    assert not is_active(r, at(5, 23, 30))
    assert not is_active(r, at(4, 6))   # Fri morning belongs to Thursday's window


def test_equal_start_end_is_whole_day_and_disabled_never_applies():
    assert is_active(new_rule(start="10:00", end="10:00"), at(2, 3))
    assert not is_active(new_rule(enabled=False), at(0, 1))
    assert not is_active(new_rule(start="bad"), at(0, 1))


def test_effective_parts_actions_and_order():
    cfg = config.load("/nonexistent")
    cfg["schedules"] = [
        new_rule(action="dim", dim=50, parts=["case", "fans"]),
        new_rule(action="off", parts=["gpu"]),
        new_rule(action="lighting", parts=["fans"],
                 lighting={"effect": "static", "color": "#ff0000", "brightness": 40, "speed": 50}),
        new_rule(action="off", parts=["ram"], start="12:00", end="13:00"),
    ]
    parts = effective_parts(cfg, at(0, 1))
    assert parts["case"]["brightness"] == 50
    assert parts["case"]["effect"] == cfg["parts"]["case"]["effect"]
    assert parts["gpu"]["effect"] == "off"
    assert parts["fans"]["color"] == "#ff0000" and parts["fans"]["brightness"] == 40  # later rule wins
    assert parts["ram"] == cfg["parts"]["ram"]
    assert active_rules(cfg["schedules"], at(0, 1)) == [0, 1, 2]
    assert effective_parts(cfg, at(0, 10)) == cfg["parts"]


def test_normalize_fills_defaults_and_drops_junk():
    rules = normalize([{"start": "22:00", "lighting": {"color": "#00ff00"}}, "junk", None])
    assert len(rules) == 1
    assert rules[0]["end"] == "09:00" and rules[0]["days"] == list(range(7))
    assert rules[0]["lighting"]["color"] == "#00ff00" and rules[0]["lighting"]["effect"] == "static"
    assert normalize("junk") == []
