import os

from openrgb_tempglow.sensors import Overheat, find_amd_gpu_sensors, find_cpu_sensor, read_millideg


def hwmon(root, idx, name, temps, extra=None):
    d = root / "class" / "hwmon" / f"hwmon{idx}"
    d.mkdir(parents=True)
    (d / "name").write_text(name + "\n")
    for i, (label, value) in enumerate(temps, start=1):
        if label:
            (d / f"temp{i}_label").write_text(label + "\n")
        (d / f"temp{i}_input").write_text(f"{value}\n")
    for rel, text in (extra or {}).items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return d


def test_amd_cpu_prefers_tctl(tmp_path):
    hwmon(tmp_path, 0, "nvme", [("Composite", 40000)])
    hwmon(tmp_path, 1, "k10temp", [("Tccd1", 35000), ("Tctl", 48250)])
    path = find_cpu_sensor(str(tmp_path))
    assert read_millideg(path) == 48.25


def test_intel_cpu_package(tmp_path):
    hwmon(tmp_path, 0, "coretemp", [("Core 0", 50000), ("Package id 0", 61000)])
    assert read_millideg(find_cpu_sensor(str(tmp_path))) == 61.0


def test_no_cpu_sensor(tmp_path):
    os.makedirs(tmp_path / "class" / "hwmon")
    assert find_cpu_sensor(str(tmp_path)) is None
    assert read_millideg(None) is None


def test_integrated_amdgpu_is_ignored(tmp_path):
    hwmon(tmp_path, 0, "amdgpu", [("edge", 70000)], {"device/mem_info_vram_total": str(512 * 1024 ** 2)})
    hwmon(tmp_path, 1, "amdgpu", [("edge", 55000), ("junction", 66000)],
          {"device/mem_info_vram_total": str(16 * 1024 ** 3)})
    paths = find_amd_gpu_sensors(str(tmp_path))
    assert [read_millideg(p) for p in paths] == [66.0]


def test_overheat_hysteresis():
    oh = Overheat()
    assert not oh.update(80, 50, 90, 85, 10)
    assert oh.update(91, 50, 90, 85, 10) and oh.active
    assert not oh.update(85, 50, 90, 85, 10) and oh.active   # still within hysteresis band
    assert oh.update(79, 50, 90, 85, 10) and not oh.active


def test_overheat_gpu_and_missing_sensors():
    oh = Overheat()
    assert oh.update(None, 86, 90, 85, 10) and oh.active
    assert oh.update(None, None, 90, 85, 10) and not oh.active
