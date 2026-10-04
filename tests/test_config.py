import json

from openrgb_tempglow import config


def test_missing_file_gives_defaults(tmp_path):
    assert config.load(str(tmp_path / "nope.json")) == config.DEFAULT


def test_partial_file_is_merged_with_defaults(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"parts": {"fans": {"color": "#00ff00"}}, "assignments": {"a::b": "fans"}}))
    cfg = config.load(str(p))
    assert cfg["parts"]["fans"]["color"] == "#00ff00"
    assert cfg["parts"]["fans"]["effect"] == "breathing"  # default kept
    assert cfg["assignments"] == {"a::b": "fans"}
    assert cfg["overheat"]["cpu_hot"] == 90


def test_corrupt_file_gives_defaults(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{not json")
    assert config.load(str(p)) == config.DEFAULT


def test_save_roundtrip(tmp_path):
    p = str(tmp_path / "sub" / "c.json")
    cfg = config.load(p)
    cfg["parts"]["gpu"]["effect"] = "rainbow"
    config.save(cfg, p)
    assert config.load(p)["parts"]["gpu"]["effect"] == "rainbow"


def test_hex_roundtrip():
    assert config.hex_to_rgb("#0a14ff") == (10, 20, 255)
    assert config.rgb_to_hex(10, 20, 255) == "#0a14ff"
