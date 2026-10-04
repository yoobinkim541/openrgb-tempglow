"""Device discovery and color output (OpenRGB SDK + built-in extra drivers)."""
import logging
import time

from openrgb import OpenRGBClient
from openrgb.utils import DeviceType, RGBColor

from .config import NONE, PARTS
from .drivers import colorful_gpu

log = logging.getLogger(__name__)

# Default part per OpenRGB device type. Peripherals (keyboard, mouse, headset, ...) are left alone.
DEFAULT_PART = {
    DeviceType.MOTHERBOARD: "case",
    DeviceType.CASE: "case",
    DeviceType.LEDSTRIP: "case",
    DeviceType.COOLER: "fans",
    DeviceType.GPU: "gpu",
    DeviceType.DRAM: "ram",
}

# Protocol v4+ stalls ~10 s during the handshake with OpenRGB 1.0; v3 has everything we use.
PROTOCOL_VERSION = 3


def zone_key(device_label, zone_name):
    return f"{device_label}::{zone_name}"


class Zone:
    """One controllable zone: an OpenRGB zone or an extra-driver device."""

    def __init__(self, key, device_label, zone_name, device_type, part, leds=1,
                 resizable=False, leds_min=0, leds_max=0, setter=None, refresh=False):
        self.key = key
        self.device_label = device_label
        self.zone_name = zone_name
        self.device_type = device_type
        self.part = part
        self.leds = leds
        self.resizable = resizable
        self.leds_min = leds_min
        self.leds_max = leds_max
        self.setter = setter
        # Extra drivers may lose their color (e.g. after suspend), so they are re-sent periodically
        self.refresh = refresh
        self.last = None

    def to_status(self):
        return {
            "key": self.key, "device": self.device_label, "zone": self.zone_name,
            "device_type": self.device_type, "part": self.part, "leds": self.leds,
            "resizable": self.resizable, "leds_min": self.leds_min, "leds_max": self.leds_max,
        }


class Hardware:
    def __init__(self, host, port):
        self.host, self.port = host, port
        self.client = None
        self.zones = []
        self.extra = []

    # ---------- connection ----------
    def try_connect(self):
        try:
            self.client = OpenRGBClient(self.host, self.port, "openrgb-tempglow",
                                        protocol_version=PROTOCOL_VERSION)
            return True
        except (ConnectionRefusedError, TimeoutError, OSError) as e:
            log.debug("OpenRGB connect failed: %s", e)
            self.client = None
            return False

    def wait_for_devices(self, timeout=30):
        """OpenRGB keeps scanning for a while after start-up; wait until the list settles."""
        deadline = time.monotonic() + timeout
        last_count, stable_since = -1, time.monotonic()
        while time.monotonic() < deadline:
            self.client.update()
            count = len(self.client.devices)
            if count != last_count:
                last_count, stable_since = count, time.monotonic()
            elif count > 0 and time.monotonic() - stable_since >= 3:
                return
            time.sleep(1)

    # ---------- discovery ----------
    def setup(self, cfg, take_control=True):
        """(Re)build the zone list from current devices and the user's assignments.

        take_control=False only inspects devices (no resizing, no mode changes).
        """
        assignments = cfg.get("assignments", {})
        zone_leds = cfg.get("zone_leds", {})
        zones = []

        seen = {}
        for dev in self.client.devices:
            seen[dev.name] = seen.get(dev.name, 0) + 1
            label = dev.name if seen[dev.name] == 1 else f"{dev.name} #{seen[dev.name]}"
            default = DEFAULT_PART.get(dev.type, NONE)
            dev_zones = []
            for i, z in enumerate(dev.zones):
                key = zone_key(label, z.name)
                part = assignments.get(key, default)
                if part not in PARTS:
                    part = NONE
                zd = dev.data.zones[i]
                resizable = zd.leds_min != zd.leds_max
                want = zone_leds.get(key)
                if take_control and resizable and want is not None and want != len(z.leds) and part != NONE:
                    want = max(zd.leds_min, min(zd.leds_max, int(want)))
                    z.resize(want)
                    dev.update()
                    z = dev.zones[i]
                dev_zones.append(Zone(
                    key, label, z.name, dev.type.name.lower(), part, len(z.leds),
                    resizable, zd.leds_min, zd.leds_max, setter=self._zone_setter(z)))
            if take_control and any(z.part != NONE for z in dev_zones):
                self._take_control(dev)
                # Direct mode drives the whole device, so unassigned zones on it are switched off
                # instead of freezing on whatever color they last had.
                for z in dev_zones:
                    if z.part == NONE:
                        z.setter((0, 0, 0))
            zones.extend(dev_zones)

        for drv in self.extra:
            key = zone_key(drv.name, drv.zone_name)
            part = assignments.get(key, "gpu")
            zones.append(Zone(key, drv.name, drv.zone_name, "gpu",
                              part if part in PARTS else NONE, setter=self._driver_setter(drv),
                              refresh=True))
        self.zones = zones

    def load_extra_drivers(self, cfg):
        for drv in self.extra:
            drv.close()
        self.extra = []
        if cfg.get("extra_drivers", {}).get("colorful_gpu", True):
            # Skip if OpenRGB already handles a Colorful card itself
            if not any("colorful" in d.name.lower() or "igame" in d.name.lower()
                       for d in self.client.devices):
                gpu = colorful_gpu.find()
                if gpu:
                    log.info("Colorful GPU found on %s", gpu.bus_path)
                    self.extra.append(gpu)

    @staticmethod
    def _take_control(dev):
        names = [m.name.lower() for m in dev.modes]
        for wanted in ("direct", "static"):
            if wanted in names:
                if dev.active_mode != names.index(wanted):
                    dev.set_mode(dev.modes[names.index(wanted)].name)
                return
        log.warning("%s has no Direct/Static mode; colors may not apply", dev.name)

    @staticmethod
    def _zone_setter(z):
        def setter(rgb):
            if z.leds:
                z.set_color(RGBColor(*rgb), fast=True)
        return setter

    @staticmethod
    def _driver_setter(drv):
        def setter(rgb):
            drv.set_color(*rgb)
        return setter

    # ---------- output ----------
    def apply(self, colors, refresh=False):
        """colors: part -> (r, g, b). Only sends when a zone's color actually changed."""
        for z in self.zones:
            rgb = colors.get(z.part)
            if rgb is None:
                continue
            if z.last == rgb and not (refresh and z.refresh):
                continue
            z.setter(rgb)
            z.last = rgb

    def parts_present(self):
        return {p: any(z.part == p and z.leds for z in self.zones) for p in PARTS}

    def close(self):
        for drv in self.extra:
            drv.close()
        self.extra = []
        if self.client:
            try:
                self.client.disconnect()
            except OSError:
                pass
            self.client = None
