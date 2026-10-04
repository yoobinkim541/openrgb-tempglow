<p align="center">
  <img src="https://raw.githubusercontent.com/yoobinkim541/openrgb-tempglow/main/src/openrgb_tempglow/data/icons/128x128/io.github.yoobinkim541.OpenRGBTempglow.png" width="96" alt="">
</p>

<h1 align="center">OpenRGB Tempglow</h1>

<p align="center">
  Simple per-part RGB lighting for Linux PCs — with fans that turn red when things get too hot.<br>
  <a href="https://github.com/yoobinkim541/openrgb-tempglow/blob/main/README.ko.md">한국어</a>
</p>

---

OpenRGB can talk to almost every RGB controller, but setting up "white case, slowly breathing
fans, red when overheating" means juggling devices, zones and profiles. Tempglow sits on top of
[OpenRGB](https://openrgb.org) and turns your PC into four simple parts:

| Part | Typical hardware |
|---|---|
| **Case / Motherboard** | on-board LEDs, case strips |
| **Fans** | ARGB fan headers, coolers |
| **Graphics card** | GPU lighting |
| **RAM** | memory sticks |

Each part gets its own effect (**static**, **breathing**, **rainbow**, **off**), color, brightness and
speed — or change everything at once. A small background service applies your settings and watches
CPU/GPU temperatures; past the limit, the parts you choose switch to an alert color, and switch back
once things cool down.

<p align="center">
  <img src="https://raw.githubusercontent.com/yoobinkim541/openrgb-tempglow/main/docs/screenshot-lighting.png" width="32%" alt="Lighting tab">
  <img src="https://raw.githubusercontent.com/yoobinkim541/openrgb-tempglow/main/docs/screenshot-devices.png" width="32%" alt="Devices tab">
  <img src="https://raw.githubusercontent.com/yoobinkim541/openrgb-tempglow/main/docs/screenshot-alerts.png" width="32%" alt="Alerts tab">
</p>

## Features

- Per-part and all-at-once lighting control, applied live as you drag a slider
- Overheat alert with hysteresis (CPU via `k10temp`/`zenpower`/`coretemp`, GPU via `nvidia-smi` or discrete `amdgpu`)
- Automatic device discovery; assign any OpenRGB zone to a part and set ARGB LED counts in the **Devices** tab
- Starts an OpenRGB server for you (installed package, Flatpak or AppImage) when none is running
- Built-in driver for **Colorful iGame** NVIDIA cards that OpenRGB doesn't list yet (e.g. RTX 5080)
- GTK 4 / libadwaita app, English and Korean UI

## Requirements

- Linux with systemd (user services)
- [OpenRGB](https://openrgb.org) **1.0 or newer** — distro package, Flatpak or AppImage
- Python 3.10+, PyGObject, GTK 4 and libadwaita **1.5+** (Ubuntu 24.04+, Fedora 40+, Debian 13+, Arch)

## Install

### Ubuntu / Debian (.deb)

Download `openrgb-tempglow_*_all.deb` from the [latest release](https://github.com/yoobinkim541/openrgb-tempglow/releases/latest):

```sh
sudo apt install ./openrgb-tempglow_*_all.deb
systemctl --user start openrgb-tempglow   # or log out and back in
```

### Any distro (install script)

```sh
git clone https://github.com/yoobinkim541/openrgb-tempglow
cd openrgb-tempglow
./install.sh            # add --udev to also install OpenRGB's udev rules
```

Everything goes into your home directory (`~/.local`); no root is needed except for `--udev`.
Remove it with `./install.sh --uninstall`.

### pipx

```sh
pipx install --system-site-packages openrgb-tempglow   # system site-packages provide PyGObject/GTK
tempglow-setup install                                  # desktop entry, icon and user service
```

## First run

1. **Permissions.** OpenRGB needs udev rules to reach devices without root. If the Devices tab is
   empty or missing hardware, run `tempglow-setup udev` (uses OpenRGB's own rules, asks for sudo),
   then reboot or replug.
2. **Assign zones.** Open **OpenRGB Tempglow** → **Devices**. Zones get a part based on the device
   type (motherboard → case, RAM → RAM, cooler → fans, GPU → graphics card); fan headers usually
   need to be set to **Fans** by hand. For ARGB headers, set **LED count** to the number of LEDs
   connected. Keyboards, mice and other peripherals are left alone unless you assign them.
3. **Pick colors** on the **Lighting** tab, and alert settings on **Alerts**.

Tip: not sure which header is which? Give each one a different color under **Lighting** and look
inside the case.

## Command line

```text
tempglowd --list-devices    show every zone and the part it belongs to (read-only)
tempglowd --simulate-hot    run in the foreground pretending the PC is overheating
tempglowd -v                foreground with debug logging
tempglow-setup install|uninstall|udev
journalctl --user -u openrgb-tempglow -f     service log
```

Settings live in `~/.config/openrgb-tempglow/config.json` (edited by the app; the service reloads
it automatically). `status.json` next to it is written by the service.

## Troubleshooting

**RAM isn't detected (AMD boards, often Gigabyte).** Check `sudo dmesg | grep -i "ACPI.*conflict"`.
If you see `SystemIO range ... conflicts with OpRegion ... SMBI`, the BIOS has claimed the SMBus and
the `i2c_piix4` driver can't bind. The usual fix (also recommended by OpenRGB) is adding the kernel
parameter `acpi_enforce_resources=lax`:

```sh
echo 'GRUB_CMDLINE_LINUX_DEFAULT="$GRUB_CMDLINE_LINUX_DEFAULT acpi_enforce_resources=lax"' \
  | sudo tee /etc/default/grub.d/99-openrgb.cfg && sudo update-grub   # then reboot
```

This lets the kernel use a bus the firmware also uses; understand the trade-off before enabling it.

**"OpenRGB was not found".** Install OpenRGB 1.0+. AppImages are picked up from `~/Applications`,
`~/.local/bin` or `~/Downloads`; anything else can be set via `openrgb.command` in `config.json`,
e.g. `"command": ["/opt/openrgb/openrgb"]`.

**Using the OpenRGB app at the same time.** Tempglow connects to whatever server is listening on
port 6742, so you can keep the OpenRGB window open with its SDK server enabled. Don't run another
tool that also drives the same devices continuously.

## How it works

```
 tempglow (GTK app) ── writes ──▶ config.json ◀── watches ── tempglowd (systemd user service)
                                                                │  25 fps effects, temps every 2 s
                                       OpenRGB SDK server ◀─────┤
                                       extra I2C drivers  ◀─────┘
```

## Contributing

Bug reports and pull requests are welcome. Run the tests with:

```sh
python3 -m venv --system-site-packages .venv && .venv/bin/pip install -e '.[test]'
.venv/bin/pytest
```

New hardware that OpenRGB doesn't support is best added to OpenRGB itself; small built-in drivers
here are a stop-gap (see `src/openrgb_tempglow/drivers/`).

## License

GPL-3.0-or-later. Built on [OpenRGB](https://gitlab.com/CalcProgrammer1/OpenRGB) (GPL-2.0-or-later)
and [openrgb-python](https://github.com/jath03/openrgb-python) (GPL-3.0). The Colorful GPU protocol
is ported from OpenRGB's `ColorfulGPUController`.
