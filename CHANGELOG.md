# Changelog

## 0.2.0 — 2026-10-07

- New **Schedule** tab: during daily time windows, turn selected parts off, dim them, or switch them to a different effect and color — e.g. lights off from midnight to 9 AM, or only the fans on at night. Pick the weekdays for each schedule; windows can cross midnight. Overheat alerts still show during schedules

## 0.1.1 — 2026-10-05

- Fix RAM and graphics card lighting not detected after boot: wait for the login session's I2C access before starting the OpenRGB server, since OpenRGB scans I2C only once

## 0.1.0 — 2026-10-05

First public release.

- Per-part lighting (case, fans, graphics card, RAM) with static, breathing, rainbow and off effects
- Overheat alert with configurable limits, alert color, affected parts and hysteresis
- Automatic OpenRGB device discovery, zone-to-part assignment and ARGB LED count in the app
- Starts an OpenRGB server automatically (package, Flatpak or AppImage)
- Built-in driver for Colorful iGame NVIDIA cards not yet listed in OpenRGB
- GTK 4 / libadwaita settings app (English, Korean)
- Packages: .deb, install script, PyPI (pipx)
