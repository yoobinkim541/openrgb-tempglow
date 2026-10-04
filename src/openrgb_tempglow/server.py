"""Locate and launch an OpenRGB SDK server when none is running."""
import glob
import logging
import os
import shutil
import subprocess

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
    log.info("Starting OpenRGB server: %s", " ".join(args))
    return subprocess.Popen(args, env={**os.environ, **env},
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
