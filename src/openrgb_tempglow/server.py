"""Locate and launch an OpenRGB SDK server when none is running."""
import glob
import logging
import os
import shutil
import subprocess
import time

log = logging.getLogger(__name__)
FLATPAK_ID = "org.openrgb.OpenRGB"


def find_openrgb_command():
    """Return (argv, env_overrides) for the first OpenRGB install found, or (None, None)."""
    exe = shutil.which("openrgb")
    if exe:
        return [exe], {}

    flatpak = shutil.which("flatpak")
    if flatpak:
        r = subprocess.run([flatpak, "info", FLATPAK_ID], capture_output=True)
        if r.returncode == 0:
            return [flatpak, "run", FLATPAK_ID], {}

    home = os.path.expanduser("~")
    for apprun in (os.path.join(home, ".local/opt/openrgb/squashfs-root/AppRun"),
                   "/opt/openrgb/squashfs-root/AppRun"):
        if os.access(apprun, os.X_OK):
            return [apprun], {}

    for pattern in ("~/Applications/OpenRGB*.AppImage", "~/.local/bin/OpenRGB*.AppImage",
                    "~/Downloads/OpenRGB*.AppImage", "/opt/OpenRGB*.AppImage"):
        found = sorted(glob.glob(os.path.expanduser(pattern)))
        if found:
            # Works without libfuse2, which recent distros no longer ship
            return [found[-1]], {"APPIMAGE_EXTRACT_AND_RUN": "1"}
    return None, None


def _supports(argv, env, flag):
    try:
        out = subprocess.run(argv + ["--help"], capture_output=True, text=True, timeout=30,
                             env={**os.environ, **env})
        return flag in (out.stdout + out.stderr)
    except (OSError, subprocess.SubprocessError):
        return False


def _pending_i2c_buses():
    """I2C buses udev will grant to the logged-in user (uaccess) but hasn't yet."""
    pending = []
    for dev in glob.glob("/dev/i2c-*"):
        try:
            st = os.stat(dev)
            with open(f"/run/udev/data/c{os.major(st.st_rdev)}:{os.minor(st.st_rdev)}") as f:
                if "G:uaccess" not in f.read().split("\n"):
                    continue
        except OSError:
            continue
        if not os.access(dev, os.R_OK | os.W_OK):
            pending.append(dev)
    return pending


def wait_for_i2c_access(timeout=30.0, interval=0.5):
    """At boot the user service can start before logind applies the uaccess ACLs to
    /dev/i2c-*; OpenRGB scans I2C only once, so it would miss DRAM and GPU controllers."""
    deadline = time.monotonic() + timeout
    pending = _pending_i2c_buses()
    if pending:
        log.info("Waiting for access to %s...", " ".join(sorted(pending)))
    while pending and time.monotonic() < deadline:
        time.sleep(interval)
        pending = _pending_i2c_buses()
    if pending:
        log.warning("No access to %s; I2C devices (RAM, GPU) may not be detected",
                    " ".join(sorted(pending)))


def start_server(port, command=None):
    """Start `openrgb --server`; returns the Popen or None."""
    if command:
        argv, env = list(command), {}
    else:
        argv, env = find_openrgb_command()
    if not argv:
        log.error("OpenRGB not found. Install it from https://openrgb.org (1.0 or newer recommended).")
        return None
    args = argv + ["--server", "--server-port", str(port)]
    # 1.0+: don't make the headless server try to connect to other servers
    if _supports(argv, env, "--noautoconnect"):
        args.append("--noautoconnect")
    wait_for_i2c_access()
    log.info("Starting OpenRGB server: %s", " ".join(args))
    return subprocess.Popen(args, env={**os.environ, **env},
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
