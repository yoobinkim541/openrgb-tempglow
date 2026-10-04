from types import SimpleNamespace

from openrgb.utils import DeviceType

from openrgb_tempglow import hardware


class FakeZone:
    def __init__(self, name, leds):
        self.name = name
        self.leds = [None] * leds
        self.sent = []
        self.resized = None

    def set_color(self, color, fast=False):
        self.sent.append((color.red, color.green, color.blue))

    def resize(self, n):
        self.resized = n
        self.leds = [None] * n


class FakeDevice:
    def __init__(self, name, type_, zones, modes=("Direct", "Static")):
        self.name = name
        self.type = type_
        self.zones = zones
        self.modes = [SimpleNamespace(name=m) for m in modes]
        self.active_mode = len(modes) - 1
        self.data = SimpleNamespace(zones=[
            SimpleNamespace(leds_min=0, leds_max=1024) if z.name.startswith("ARGB")
            else SimpleNamespace(leds_min=len(z.leds), leds_max=len(z.leds)) for z in zones])
        self.mode_set = None

    def set_mode(self, name):
        self.mode_set = name

    def update(self):
        pass


def make_hw(devices):
    hw = hardware.Hardware("127.0.0.1", 0)
    hw.client = SimpleNamespace(devices=devices)
    return hw


def test_default_parts_by_device_type():
    board = FakeDevice("Board", DeviceType.MOTHERBOARD, [FakeZone("LED_C", 1), FakeZone("ARGB_1", 0)])
    ram1 = FakeDevice("Kingston", DeviceType.DRAM, [FakeZone("DRAM", 8)])
    ram2 = FakeDevice("Kingston", DeviceType.DRAM, [FakeZone("DRAM", 8)])
    kb = FakeDevice("Keyboard", DeviceType.KEYBOARD, [FakeZone("Keys", 104)])
    hw = make_hw([board, ram1, ram2, kb])
    hw.setup({"assignments": {}, "zone_leds": {}})
    parts = {z.key: z.part for z in hw.zones}
    assert parts == {
        "Board::LED_C": "case", "Board::ARGB_1": "case",
        "Kingston::DRAM": "ram", "Kingston #2::DRAM": "ram",
        "Keyboard::Keys": "none",
    }
    assert board.mode_set == "Direct"
    assert kb.mode_set is None  # unassigned peripherals are left alone
    assert kb.zones[0].sent == []


def test_unassigned_zone_on_controlled_device_is_switched_off():
    spare = FakeZone("ARGB_3", 4)
    board = FakeDevice("Board", DeviceType.MOTHERBOARD, [FakeZone("LED_C", 1), spare])
    hw = make_hw([board])
    hw.setup({"assignments": {"Board::ARGB_3": "none"}, "zone_leds": {}})
    assert spare.sent == [(0, 0, 0)]


def test_assignment_resize_and_apply():
    fan = FakeZone("ARGB_2", 0)
    board = FakeDevice("Board", DeviceType.MOTHERBOARD, [FakeZone("LED_C", 1), fan])
    hw = make_hw([board])
    hw.setup({"assignments": {"Board::ARGB_2": "fans"}, "zone_leds": {"Board::ARGB_2": 40}})
    assert fan.resized == 40
    hw.apply({"case": (255, 255, 255), "fans": (10, 0, 0)})
    hw.apply({"case": (255, 255, 255), "fans": (10, 0, 0)})  # unchanged -> not resent
    assert board.zones[0].sent == [(255, 255, 255)]
    assert fan.sent == [(10, 0, 0)]
    assert hw.parts_present() == {"case": True, "fans": True, "gpu": False, "ram": False}


def test_inspect_only_does_not_touch_devices():
    fan = FakeZone("ARGB_2", 0)
    board = FakeDevice("Board", DeviceType.MOTHERBOARD, [fan])
    hw = make_hw([board])
    hw.setup({"assignments": {}, "zone_leds": {"Board::ARGB_2": 40}}, take_control=False)
    assert fan.resized is None and board.mode_set is None


def test_unknown_assignment_falls_back_to_none():
    board = FakeDevice("Board", DeviceType.MOTHERBOARD, [FakeZone("LED_C", 1)])
    hw = make_hw([board])
    hw.setup({"assignments": {"Board::LED_C": "bogus"}, "zone_leds": {}})
    assert hw.zones[0].part == "none"
