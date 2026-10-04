"""tempglow-setup: install the desktop entry, icons and systemd user service for the current user.

Used after `pipx install` / `pip install` and by install.sh. The .deb package ships these
files system-wide and does not need this.
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys

from . import APP_ID, SERVICE_NAME

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _xdg(var, default):
    return os.environ.get(var) or os.path.expanduser(default)


def _paths():
    data_home = _xdg("XDG_DATA_HOME", "~/.local/share")
    config_home = _xdg("XDG_CONFIG_HOME", "~/.config")
    return {
        "desktop": os.path.join(data_home, "applications", f"{APP_ID}.desktop"),
        "icons": os.path.join(data_home, "icons", "hicolor"),
        "unit": os.path.join(config_home, "systemd", "user", SERVICE_NAME),
    }


def find_script(name):
    """Prefer the script next to this interpreter (venv / pipx), then PATH."""
    candidate = os.path.join(os.path.dirname(sys.executable), name)
    if os.access(candidate, os.X_OK):
        return candidate
    return shutil.which(name)


def _systemctl(*args):
    return subprocess.run(["systemctl", "--user", *args], check=False).returncode


def install(enable=True):
    p = _paths()
    gui, daemon = find_script("tempglow"), find_script("tempglowd")
    if not gui or not daemon:
        sys.exit("tempglow / tempglowd not found next to this Python or on PATH")

    os.makedirs(os.path.dirname(p["desktop"]), exist_ok=True)
    with open(os.path.join(DATA, f"{APP_ID}.desktop")) as f:
        desktop = f.read().replace("Exec=tempglow", f"Exec={gui}")
    with open(p["desktop"], "w") as f:
        f.write(desktop)

    scalable = os.path.join(p["icons"], "scalable", "apps")
    os.makedirs(scalable, exist_ok=True)
    shutil.copy(os.path.join(DATA, "icons", f"{APP_ID}.svg"), scalable)
    for png in glob.glob(os.path.join(DATA, "icons", "*x*", f"{APP_ID}.png")):
        size = os.path.basename(os.path.dirname(png))
        dest = os.path.join(p["icons"], size, "apps")
        os.makedirs(dest, exist_ok=True)
        shutil.copy(png, dest)

    os.makedirs(os.path.dirname(p["unit"]), exist_ok=True)
    with open(os.path.join(DATA, "openrgb-tempglow.service.in")) as f:
        unit = f.read().replace("@TEMPGLOWD@", daemon)
    with open(p["unit"], "w") as f:
        f.write(unit)

    subprocess.run(["update-desktop-database", os.path.dirname(p["desktop"])], check=False,
                   stderr=subprocess.DEVNULL)
    subprocess.run(["gtk-update-icon-cache", "-qtf", p["icons"]], check=False,
                   stderr=subprocess.DEVNULL)
    _systemctl("daemon-reload")
    if enable:
        _systemctl("enable", "--now", SERVICE_NAME)
    print(f"Installed desktop entry, icons and {SERVICE_NAME}")


def uninstall():
    p = _paths()
    _systemctl("disable", "--now", SERVICE_NAME)
    for path in [p["desktop"], p["unit"],
                 os.path.join(p["icons"], "scalable", "apps", f"{APP_ID}.svg"),
                 *glob.glob(os.path.join(p["icons"], "*", "apps", f"{APP_ID}.png"))]:
        if os.path.exists(path):
            os.remove(path)
    _systemctl("daemon-reload")
    print("Removed desktop entry, icons and service (settings in ~/.config/openrgb-tempglow kept)")


def udev():
    """Install OpenRGB's own udev rules (needs sudo) so devices work without root."""
    from .server import find_openrgb_command

    argv, env = find_openrgb_command()
    if not argv:
        sys.exit("OpenRGB not found. Install OpenRGB 1.0+ first: https://openrgb.org")
    rules = subprocess.run(argv + ["--print-udev-rules"], capture_output=True, text=True,
                           env={**os.environ, **env}).stdout
    if "uaccess" not in rules:
        sys.exit("This OpenRGB version can't print udev rules (needs 1.0+). See https://openrgb.org/udev")
    target = "/etc/udev/rules.d/60-openrgb.rules"
    print(f"Writing {target} (sudo password may be requested)")
    r = subprocess.run(["sudo", "tee", target], input=rules, text=True, stdout=subprocess.DEVNULL)
    if r.returncode == 0:
        subprocess.run(["sudo", "udevadm", "control", "--reload-rules"], check=False)
        subprocess.run(["sudo", "udevadm", "trigger"], check=False)
        print("udev rules installed")
    return r.returncode


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tempglow-setup", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("install", help="install desktop entry, icons and user service")
    i.add_argument("--no-enable", action="store_true", help="don't enable/start the service")
    sub.add_parser("uninstall", help="remove what `install` added")
    sub.add_parser("udev", help="install OpenRGB udev rules (sudo)")
    args = ap.parse_args(argv)
    if args.cmd == "install":
        install(enable=not args.no_enable)
    elif args.cmd == "uninstall":
        uninstall()
    else:
        return udev()
    return 0


if __name__ == "__main__":
    sys.exit(main())
