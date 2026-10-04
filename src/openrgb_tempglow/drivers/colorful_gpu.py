"""Colorful (iGame) NVIDIA graphics cards over I2C.

Protocol ported from OpenRGB's ColorfulGPUController (GPL-2.0-or-later).
Used for cards OpenRGB does not list yet (e.g. iGame RTX 5080, subsystem 7377:1501).

Safety: only I2C adapters that belong to an NVIDIA PCI device with Colorful's
subsystem vendor ID are probed, so nothing is written to other vendors' cards.
"""
import fcntl
import glob
import os

NVIDIA_VENDOR = "0x10de"
COLORFUL_SUBVENDOR = "0x7377"
I2C_SLAVE = 0x0703
ADDR = 0x61
HANDSHAKE = bytes([0xAA, 0xEF, 0x81, 0x02, 0x1C, 0x02])
HANDSHAKE_REPLY = bytes([0xAA, 0xEF, 0x81])


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _with_checksum(pkt):
    s = sum(pkt)
    return bytes(pkt) + bytes([s & 0xFF, (s >> 8) & 0xFF])


def candidate_buses(sysfs="/sys"):
    """I2C adapters that sit on a Colorful-branded NVIDIA card."""
    buses = []
    for dev in sorted(glob.glob(os.path.join(sysfs, "class/i2c-dev/i2c-*"))):
        pci = os.path.realpath(os.path.join(dev, "device", ".."))
        if (_read(os.path.join(pci, "vendor")) == NVIDIA_VENDOR
                and _read(os.path.join(pci, "subsystem_vendor")) == COLORFUL_SUBVENDOR):
            buses.append(("/dev/" + os.path.basename(dev), _read(os.path.join(pci, "subsystem_device"))))
    return buses


class ColorfulGPU:
    name = "Colorful GPU (I2C)"
    zone_name = "GPU"

    def __init__(self, bus_path, subsystem_device=None):
        self.bus_path = bus_path
        self.subsystem_device = subsystem_device
        self.fd = os.open(bus_path, os.O_RDWR)
        fcntl.ioctl(self.fd, I2C_SLAVE, ADDR)

    def handshake(self):
        os.write(self.fd, HANDSHAKE)
        return os.read(self.fd, 0x40)[:3] == HANDSHAKE_REPLY

    def set_color(self, r, g, b):
        os.write(self.fd, _with_checksum([0xAA, 0xEF, 0x12, 0x03, 0x01, 0xFF, r, g, b]))

    def close(self):
        os.close(self.fd)


def find(sysfs="/sys"):
    for bus, subdev in candidate_buses(sysfs):
        try:
            gpu = ColorfulGPU(bus, subdev)
        except OSError:
            continue
        try:
            if gpu.handshake():
                return gpu
        except OSError:
            pass
        gpu.close()
    return None
