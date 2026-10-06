"""tempglowd: applies config.json to the hardware in real time and handles overheat alerts."""
import argparse
import logging
import os
import signal
import sys
import time
from datetime import datetime

from . import __version__, config
from .effects import compute_color
from .schedule import active_rules, effective_parts
from .sensors import Overheat, Sensors

log = logging.getLogger("tempglowd")

FPS = 25
TEMP_INTERVAL = 2.0
CONFIG_CHECK = 0.3
HEARTBEAT = 5.0
EXTRA_REFRESH = 60.0
CONNECT_RETRY = 3.0
SERVER_STARTUP_TIMEOUT = 60.0


class Daemon:
    def __init__(self, simulate_hot=False, publish_status=True):
        from .hardware import Hardware  # needs openrgb-python; keep --help working without it

        self.simulate_hot = simulate_hot
        self.publish_status = publish_status
        self.running = True
        if not os.path.exists(config.config_path()):
            config.save(config.DEFAULT)
        self.cfg = config.load()
        self.cfg_mtime = self._mtime()
        orgb = self.cfg["openrgb"]
        self.hw = Hardware(orgb["host"], orgb["port"])
        self.sensors = Sensors()
        self.overheat = Overheat()
        self.server_proc = None
        self.connected = False
        self.error = None
        self.temps = (None, None)

    @staticmethod
    def _mtime():
        try:
            return os.path.getmtime(config.config_path())
        except OSError:
            return None

    # ---------- status for the GUI ----------
    def write_status(self):
        if not self.publish_status:
            return
        config.atomic_write_json(config.status_path(), {
            "version": __version__,
            "pid": os.getpid(),
            "heartbeat": time.time(),
            "openrgb": {
                "connected": self.connected,
                "error": self.error,
                "managed_server": self.server_proc is not None,
            },
            "zones": [z.to_status() for z in self.hw.zones],
            "parts_present": self.hw.parts_present(),
            "temps": {"cpu": self.temps[0], "gpu": self.temps[1]},
            "sensors": self.sensors.describe(),
            "overheat": self.overheat.active,
            "schedules_active": active_rules(self.cfg["schedules"], datetime.now()),
        })

    # ---------- connection ----------
    def connect(self, take_control=True):
        """Connect to OpenRGB, starting a server if allowed. Blocks until connected or stopped."""
        from .server import start_server

        orgb = self.cfg["openrgb"]
        started_at = None
        while self.running:
            if self.hw.try_connect():
                self.connected, self.error = True, None
                break
            self.connected = False
            if orgb["manage_server"] and self.server_proc is None:
                self.server_proc = start_server(orgb["port"], orgb.get("command") or None)
                started_at = time.monotonic()
                if self.server_proc is None:
                    self.error = "openrgb-not-found"
            elif self.server_proc is not None and self.server_proc.poll() is not None:
                self.error = "openrgb-exited"
                self.server_proc = None
            elif started_at and time.monotonic() - started_at > SERVER_STARTUP_TIMEOUT:
                self.error = "openrgb-timeout"
            elif not orgb["manage_server"]:
                self.error = "openrgb-unreachable"
            log.info("Waiting for OpenRGB server (%s)...", self.error or "starting")
            self.write_status()
            time.sleep(CONNECT_RETRY)
        if not self.running:
            return
        self.hw.wait_for_devices()
        self.hw.load_extra_drivers(self.cfg)
        self.hw.setup(self.cfg, take_control=take_control)
        for z in self.hw.zones:
            log.info("zone %-45s -> %s (%d LEDs)", z.key, z.part, z.leds)
        self.write_status()

    # ---------- main loop ----------
    def reload_config(self):
        old = self.cfg
        self.cfg = config.load()
        log.info("Config reloaded")
        if (old["assignments"] != self.cfg["assignments"]
                or old["zone_leds"] != self.cfg["zone_leds"]
                or old["extra_drivers"] != self.cfg["extra_drivers"]):
            if old["extra_drivers"] != self.cfg["extra_drivers"]:
                self.hw.load_extra_drivers(self.cfg)
            self.hw.setup(self.cfg)
            self.write_status()

    def colors(self, t):
        oh = self.cfg["overheat"]
        parts = effective_parts(self.cfg, datetime.now())
        out = {}
        for part in config.PARTS:
            if self.overheat.active and oh["enabled"] and part in oh["parts"]:
                out[part] = config.hex_to_rgb(oh["color"])
            else:
                out[part] = compute_color(parts[part], t)
        return out

    def run(self):
        self.connect()
        start = time.monotonic()
        last_temp = last_cfg = last_beat = 0.0
        last_refresh = time.monotonic()

        while self.running:
            now = time.monotonic()

            if now - last_cfg >= CONFIG_CHECK:
                last_cfg = now
                m = self._mtime()
                if m is not None and m != self.cfg_mtime:
                    self.cfg_mtime = m
                    self.reload_config()

            if now - last_temp >= TEMP_INTERVAL:
                last_temp = now
                cpu, gpu = self.sensors.cpu(), self.sensors.gpu()
                self.temps = (cpu, gpu)
                oh = self.cfg["overheat"]
                if self.simulate_hot:
                    cpu = gpu = 999
                if self.overheat.update(cpu, gpu, oh["cpu_hot"], oh["gpu_hot"], oh["hysteresis"]):
                    log.warning("Overheat %s (CPU=%s°C GPU=%s°C)",
                                "detected" if self.overheat.active else "cleared", *self.temps)

            refresh = now - last_refresh >= EXTRA_REFRESH
            if refresh:
                last_refresh = now
            try:
                self.hw.apply(self.colors(now - start), refresh=refresh)
            except (ConnectionError, OSError) as e:
                log.warning("Lost connection to OpenRGB (%s); reconnecting", e)
                self.connected = False
                self.hw.close()
                self.write_status()
                self.connect()

            if now - last_beat >= HEARTBEAT:
                last_beat = now
                self.write_status()

            time.sleep(1 / FPS)

    def stop(self, *_):
        self.running = False

    def shutdown(self):
        self.hw.close()
        if self.server_proc and self.server_proc.poll() is None:
            self.server_proc.terminate()
            try:
                self.server_proc.wait(10)
            except Exception:
                self.server_proc.kill()
        self.connected = False
        self.write_status()


def list_devices():
    d = Daemon(publish_status=False)  # don't clobber the running service's status file
    d.connect(take_control=False)
    for z in d.hw.zones:
        size = f"{z.leds} LEDs" + (f" (resizable {z.leds_min}-{z.leds_max})" if z.resizable else "")
        print(f"{z.part:5}  {z.key}  [{z.device_type}, {size}]")
    print(f"\nconfig: {config.config_path()}")
    d.hw.close()
    if d.server_proc:
        d.server_proc.terminate()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tempglowd", description=__doc__)
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("--list-devices", action="store_true", help="print detected zones and exit")
    ap.add_argument("--simulate-hot", action="store_true", help="pretend the system is overheating")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    if args.list_devices:
        return list_devices()

    d = Daemon(simulate_hot=args.simulate_hot)
    signal.signal(signal.SIGTERM, d.stop)
    signal.signal(signal.SIGINT, d.stop)
    try:
        d.run()
    finally:
        d.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
