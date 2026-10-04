import os

from openrgb_tempglow.drivers import colorful_gpu


def pci_with_i2c(root, pci_name, vendor, subvendor, subdevice, bus):
    pci = root / "devices" / pci_name
    (pci / f"i2c-{bus}" / "i2c-dev" / f"i2c-{bus}").mkdir(parents=True)
    (pci / "vendor").write_text(vendor + "\n")
    (pci / "subsystem_vendor").write_text(subvendor + "\n")
    (pci / "subsystem_device").write_text(subdevice + "\n")
    cls = root / "class" / "i2c-dev"
    cls.mkdir(parents=True, exist_ok=True)
    entry = cls / f"i2c-{bus}"
    entry.mkdir()
    os.symlink(pci / f"i2c-{bus}", entry / "device")


def test_only_colorful_nvidia_buses_are_candidates(tmp_path):
    pci_with_i2c(tmp_path, "0000:01:00.0", "0x10de", "0x7377", "0x1501", 2)   # Colorful
    pci_with_i2c(tmp_path, "0000:02:00.0", "0x10de", "0x1043", "0x89d7", 3)   # ASUS
    pci_with_i2c(tmp_path, "0000:03:00.0", "0x1002", "0x7377", "0x0001", 4)   # not NVIDIA
    assert colorful_gpu.candidate_buses(str(tmp_path)) == [("/dev/i2c-2", "0x1501")]


def test_checksum():
    pkt = colorful_gpu._with_checksum([0xAA, 0xEF, 0x12, 0x03, 0x01, 0xFF, 255, 255, 255])
    s = 0xAA + 0xEF + 0x12 + 0x03 + 0x01 + 0xFF + 255 * 3
    assert pkt[-2:] == bytes([s & 0xFF, s >> 8])
