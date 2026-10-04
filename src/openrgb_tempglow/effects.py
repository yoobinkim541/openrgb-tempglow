"""Lighting effects: map a part's settings and the current time to one RGB color."""
import colorsys
import math

from .config import hex_to_rgb

BREATH_MIN = 0.05  # dimmest point of the breathing cycle, as a fraction of full brightness


def period_for(speed):
    """Speed 0..100 -> cycle length 12s..1.5s."""
    speed = max(0, min(100, speed))
    return 12.0 - (speed / 100) * 10.5


def compute_color(part_cfg, t):
    effect = part_cfg.get("effect", "static")
    if effect == "off":
        return (0, 0, 0)
    k = max(0, min(100, part_cfg.get("brightness", 100))) / 100
    if effect == "rainbow":
        hue = (t / period_for(part_cfg.get("speed", 50))) % 1.0
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        return (round(r * 255 * k), round(g * 255 * k), round(b * 255 * k))
    r, g, b = hex_to_rgb(part_cfg.get("color", "#ffffff"))
    if effect == "breathing":
        phase = (t / period_for(part_cfg.get("speed", 50))) % 1.0
        k *= BREATH_MIN + (1 - BREATH_MIN) * (1 - math.cos(2 * math.pi * phase)) / 2
    return (round(r * k), round(g * k), round(b * k))
