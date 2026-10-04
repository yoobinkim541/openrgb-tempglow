#!/usr/bin/env bash
# openrgb-tempglow per-user installer (no root needed, except for the optional --udev step).
#
#   ./install.sh            install from this checkout (or from GitHub if run standalone)
#   ./install.sh --udev     also install OpenRGB's udev rules (asks for sudo)
#   ./install.sh --uninstall
set -euo pipefail

REPO="https://github.com/yoobinkim541/openrgb-tempglow"
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/openrgb-tempglow"
VENV="$PREFIX/venv"
BIN="$HOME/.local/bin"
SCRIPTS=(tempglow tempglowd tempglow-setup)

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

distro_hint() {
    if command -v apt-get >/dev/null; then
        echo "sudo apt install python3-venv python3-gi gir1.2-gtk-4.0 gir1.2-adw-1"
    elif command -v dnf >/dev/null; then
        echo "sudo dnf install python3-gobject gtk4 libadwaita"
    elif command -v pacman >/dev/null; then
        echo "sudo pacman -S python-gobject gtk4 libadwaita"
    elif command -v zypper >/dev/null; then
        echo "sudo zypper install python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1"
    else
        echo "install PyGObject, GTK 4 and libadwaita (>= 1.5) with your package manager"
    fi
}

# Same search order as openrgb_tempglow/server.py
have_openrgb() {
    command -v openrgb >/dev/null && return 0
    command -v flatpak >/dev/null && flatpak info org.openrgb.OpenRGB >/dev/null 2>&1 && return 0
    local f
    for f in "$HOME/.local/opt/openrgb/squashfs-root/AppRun" /opt/openrgb/squashfs-root/AppRun \
             "$HOME"/Applications/OpenRGB*.AppImage "$HOME"/.local/bin/OpenRGB*.AppImage \
             "$HOME"/Downloads/OpenRGB*.AppImage /opt/OpenRGB*.AppImage; do
        [[ -e "$f" ]] && return 0
    done
    return 1
}

uninstall() {
    if [[ -x "$VENV/bin/tempglow-setup" ]]; then
        "$VENV/bin/tempglow-setup" uninstall || true
    fi
    for s in "${SCRIPTS[@]}"; do
        [[ -L "$BIN/$s" ]] && rm -f "$BIN/$s"
    done
    rm -rf "$PREFIX"
    say "Uninstalled. Settings are kept in ${XDG_CONFIG_HOME:-$HOME/.config}/openrgb-tempglow"
}

check_deps() {
    command -v python3 >/dev/null || die "python3 not found"
    python3 - <<'EOF' || die "Python 3.10+ is required"
import sys
sys.exit(0 if sys.version_info >= (3, 10) else 1)
EOF
    python3 -c 'import venv, ensurepip' 2>/dev/null || die "python venv support missing. Try: $(distro_hint)"
    if ! python3 - <<'EOF' 2>/dev/null
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw
assert (Adw.get_major_version(), Adw.get_minor_version()) >= (1, 5)
EOF
    then
        warn "GTK 4 / libadwaita >= 1.5 for Python not found; the settings app won't start."
        warn "Install them with: $(distro_hint)"
    fi
    if ! have_openrgb; then
        warn "OpenRGB was not found. Install OpenRGB 1.0+ from https://openrgb.org (package, Flatpak or AppImage)."
    fi
}

main() {
    local udev=0
    for arg in "$@"; do
        case "$arg" in
            --uninstall) uninstall; return ;;
            --udev) udev=1 ;;
            -h|--help) sed -n '2,7p' "$0"; return ;;
            *) die "unknown option: $arg" ;;
        esac
    done

    check_deps

    local src
    src="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || true)"
    if [[ -n "$src" && -f "$src/pyproject.toml" ]]; then
        say "Installing from $src"
    else
        src="git+$REPO"
        say "Installing from $REPO"
    fi

    say "Creating virtual environment in $VENV"
    # System site-packages give the venv access to the distro's PyGObject / GTK bindings
    python3 -m venv --system-site-packages "$VENV"
    "$VENV/bin/python" -m pip install --quiet --upgrade pip
    "$VENV/bin/python" -m pip install --quiet --upgrade "$src"

    mkdir -p "$BIN"
    for s in "${SCRIPTS[@]}"; do
        ln -sf "$VENV/bin/$s" "$BIN/$s"
    done
    case ":$PATH:" in *":$BIN:"*) ;; *) warn "$BIN is not on your PATH; add it to use the commands from a terminal." ;; esac

    say "Installing desktop entry, icons and user service"
    "$VENV/bin/tempglow-setup" install

    if [[ $udev == 1 ]]; then
        say "Installing OpenRGB udev rules"
        "$VENV/bin/tempglow-setup" udev
    fi

    say "Done. Open \"OpenRGB Tempglow\" from your app menu, or run: tempglow"
    [[ $udev == 1 ]] || echo "    If devices are missing, run: tempglow-setup udev   (installs OpenRGB's udev rules)"
}

main "$@"
