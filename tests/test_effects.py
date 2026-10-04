from openrgb_tempglow.effects import compute_color, period_for


def cfg(**kw):
    base = {"effect": "static", "color": "#ff8000", "brightness": 100, "speed": 50}
    base.update(kw)
    return base


def test_static_uses_color_and_brightness():
    assert compute_color(cfg(), 0) == (255, 128, 0)
    assert compute_color(cfg(brightness=50), 0) == (128, 64, 0)


def test_off_is_black():
    assert compute_color(cfg(effect="off"), 3.2) == (0, 0, 0)


def test_breathing_goes_from_dim_to_full():
    c = cfg(effect="breathing", color="#ffffff", speed=0)
    period = period_for(0)
    dim = compute_color(c, 0)
    full = compute_color(c, period / 2)
    assert dim[0] < 20
    assert full == (255, 255, 255)


def test_rainbow_starts_red_and_changes():
    c = cfg(effect="rainbow")
    assert compute_color(c, 0) == (255, 0, 0)
    assert compute_color(c, period_for(50) / 3)[1] == 255  # green third of the wheel


def test_period_is_clamped():
    assert period_for(-10) == period_for(0)
    assert period_for(500) == period_for(100)
    assert period_for(100) < period_for(0)
