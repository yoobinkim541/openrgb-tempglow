#!/usr/bin/env bash
# Build dist/openrgb-tempglow_<version>_all.deb with dpkg-deb (no debhelper needed).
# openrgb-python is not packaged by Debian/Ubuntu, so it is bundled under /usr/lib/openrgb-tempglow.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_ID="io.github.yoobinkim541.OpenRGBTempglow"
OPENRGB_PYTHON="openrgb-python==0.3.7"
VERSION="$(python3 -c "import re;print(re.search(r'__version__ = \"(.+)\"', open('$ROOT/src/openrgb_tempglow/__init__.py').read())[1])")"
PKG="openrgb-tempglow"
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT
STAGE="$BUILD/${PKG}_${VERSION}_all"
LIB="$STAGE/usr/lib/$PKG"
DATA="$ROOT/src/openrgb_tempglow/data"

mkdir -p "$LIB" "$STAGE/usr/bin" "$STAGE/DEBIAN" "$STAGE/usr/share/doc/$PKG"

# App code (without caches) + bundled openrgb-python
cp -r "$ROOT/src/openrgb_tempglow" "$LIB/"
find "$LIB" -name __pycache__ -prune -exec rm -rf {} +
python3 -m pip download --quiet --no-deps --only-binary=:all: -d "$BUILD/wheels" "$OPENRGB_PYTHON"
python3 -m zipfile -e "$BUILD"/wheels/openrgb_python-*.whl "$BUILD/whl"
cp -r "$BUILD/whl/openrgb" "$LIB/"
cp "$BUILD"/whl/openrgb_python-*.dist-info/LICENSE* "$STAGE/usr/share/doc/$PKG/openrgb-python.LICENSE"

for cmd in tempglow:gui tempglowd:daemon tempglow-setup:setup_user; do
    name="${cmd%%:*}" mod="${cmd##*:}"
    cat > "$STAGE/usr/bin/$name" <<SH
#!/bin/sh
PYTHONPATH="/usr/lib/$PKG\${PYTHONPATH:+:\$PYTHONPATH}" exec /usr/bin/python3 -m openrgb_tempglow.$mod "\$@"
SH
    chmod 755 "$STAGE/usr/bin/$name"
done

install -Dm644 "$DATA/$APP_ID.desktop" "$STAGE/usr/share/applications/$APP_ID.desktop"
install -Dm644 "$DATA/$APP_ID.metainfo.xml" "$STAGE/usr/share/metainfo/$APP_ID.metainfo.xml"
install -Dm644 "$DATA/icons/$APP_ID.svg" "$STAGE/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
for png in "$DATA"/icons/*x*/"$APP_ID.png"; do
    size="$(basename "$(dirname "$png")")"
    install -Dm644 "$png" "$STAGE/usr/share/icons/hicolor/$size/apps/$APP_ID.png"
done
sed "s|@TEMPGLOWD@|/usr/bin/tempglowd|" "$DATA/openrgb-tempglow.service.in" \
    | install -Dm644 /dev/stdin "$STAGE/usr/lib/systemd/user/openrgb-tempglow.service"

cat > "$STAGE/usr/share/doc/$PKG/copyright" <<COPY
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: openrgb-tempglow
Source: https://github.com/yoobinkim541/openrgb-tempglow

Files: *
Copyright: 2026 Yoobin Kim
License: GPL-3+

Files: usr/lib/openrgb-tempglow/openrgb/*
Copyright: jath03 and openrgb-python contributors
License: GPL-3

License: GPL-3+
 On Debian systems, the full text is in /usr/share/common-licenses/GPL-3.
COPY

INSTALLED_KB="$(du -sk "$STAGE/usr" | cut -f1)"
cat > "$STAGE/DEBIAN/control" <<CTRL
Package: $PKG
Version: $VERSION
Architecture: all
Maintainer: Yoobin Kim <yoobinkim541@users.noreply.github.com>
Installed-Size: $INSTALLED_KB
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1 (>= 1.5)
Suggests: openrgb
Section: utils
Priority: optional
Homepage: https://github.com/yoobinkim541/openrgb-tempglow
Description: Per-part RGB lighting with temperature alerts, built on OpenRGB
 Groups your PC's lighting into case, fans, graphics card and RAM, gives each
 part its own effect (static, breathing, rainbow) and switches selected parts
 to an alert color when the CPU or graphics card overheats.
 .
 Requires OpenRGB 1.0 or newer (package, Flatpak or AppImage) from openrgb.org.
CTRL

cat > "$STAGE/DEBIAN/postinst" <<'POST'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    # Start the lighting daemon in every user session
    systemctl --global enable openrgb-tempglow.service >/dev/null 2>&1 || true
    echo "openrgb-tempglow: log out and back in (or run 'systemctl --user start openrgb-tempglow')."
    echo "openrgb-tempglow: if devices are missing, run 'tempglow-setup udev' to install OpenRGB's udev rules."
fi
POST
cat > "$STAGE/DEBIAN/prerm" <<'PRERM'
#!/bin/sh
set -e
if [ "$1" = "remove" ]; then
    systemctl --global disable openrgb-tempglow.service >/dev/null 2>&1 || true
fi
PRERM
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/prerm"

mkdir -p "$ROOT/dist"
dpkg-deb --root-owner-group --build "$STAGE" "$ROOT/dist/${PKG}_${VERSION}_all.deb" >/dev/null
echo "$ROOT/dist/${PKG}_${VERSION}_all.deb"
