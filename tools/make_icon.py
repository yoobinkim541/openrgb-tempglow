#!/usr/bin/env python3
"""Generate the app icon SVG (and PNG sizes) for openrgb-tempglow."""
import colorsys
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ID = "io.github.yoobinkim541.OpenRGBTempglow"
OUT_DIR = os.path.join(ROOT, "src/openrgb_tempglow/data/icons")
CX, CY = 64, 62
RING_R, RING_W = 40, 9
SEGMENTS = 36


def hexcol(h, s=0.85, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return f"#{round(r*255):02x}{round(g*255):02x}{round(b*255):02x}"


def polar(r, deg):
    a = math.radians(deg - 90)
    return CX + r * math.cos(a), CY + r * math.sin(a)


def ring():
    defs, paths = [], []
    step = 360 / SEGMENTS
    for i in range(SEGMENTS):
        a0, a1 = i * step, (i + 1) * step + 0.6  # slight overlap hides seams
        x0, y0 = polar(RING_R, a0)
        x1, y1 = polar(RING_R, a1)
        gid = f"seg{i}"
        defs.append(
            f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="{x0:.2f}" y1="{y0:.2f}" '
            f'x2="{x1:.2f}" y2="{y1:.2f}"><stop offset="0" stop-color="{hexcol(a0/360)}"/>'
            f'<stop offset="1" stop-color="{hexcol(a1/360)}"/></linearGradient>')
        paths.append(f'<path d="M{x0:.2f},{y0:.2f} A{RING_R},{RING_R} 0 0 1 {x1:.2f},{y1:.2f}" '
                     f'stroke="url(#{gid})"/>')
    return defs, paths


def blades():
    out = []
    for i in range(5):
        rot = i * 72
        out.append(
            f'<path transform="rotate({rot} {CX} {CY})" d="M{CX},{CY-9} '
            f'C{CX+4},{CY-20} {CX+18},{CY-30} {CX+12},{CY-33} '
            f'C{CX+2},{CY-36} {CX-10},{CY-28} {CX-7},{CY-12} Z" fill="url(#blade)"/>')
    return out


def svg():
    defs, ring_paths = ring()
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#2b2d3a"/><stop offset="1" stop-color="#14151c"/>
    </linearGradient>
    <linearGradient id="blade" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#c9cfdc"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0.55" stop-color="#ffffff" stop-opacity="0"/>
      <stop offset="0.78" stop-color="#9f7bff" stop-opacity="0.35"/>
      <stop offset="1" stop-color="#9f7bff" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="badge" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ff6b5b"/><stop offset="1" stop-color="#d7263d"/>
    </linearGradient>
    {"".join(defs)}
  </defs>
  <rect x="8" y="10" width="112" height="108" rx="24" fill="#000" opacity="0.25"/>
  <rect x="8" y="6" width="112" height="108" rx="24" fill="url(#bg)"/>
  <circle cx="{CX}" cy="{CY}" r="56" fill="url(#glow)"/>
  <g fill="none" stroke-width="{RING_W}" stroke-linecap="butt">{"".join(ring_paths)}</g>
  <circle cx="{CX}" cy="{CY}" r="{RING_R - RING_W/2 - 1.5}" fill="#1b1c25"/>
  {"".join(blades())}
  <circle cx="{CX}" cy="{CY}" r="9" fill="#2b2d3a" stroke="#ffffff" stroke-width="2.5"/>
  <circle cx="{CX}" cy="{CY}" r="3" fill="#ffffff"/>
  <g transform="translate(96 92)">
    <circle r="17" fill="url(#badge)" stroke="#14151c" stroke-width="3"/>
    <rect x="-3" y="-10" width="6" height="14" rx="3" fill="#ffffff"/>
    <circle cy="6" r="5.5" fill="#ffffff"/>
    <circle cy="6" r="2.8" fill="#d7263d"/>
    <rect x="-1.2" y="-4" width="2.4" height="9" fill="#d7263d"/>
  </g>
</svg>
'''


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{APP_ID}.svg")
    with open(path, "w") as f:
        f.write(svg())
    print(path)
    if "--png" in sys.argv:
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf
        for size in (16, 24, 32, 48, 64, 128, 256, 512):
            pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, size, size)
            out = os.path.join(OUT_DIR, f"{size}x{size}", f"{APP_ID}.png")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            pb.savev(out, "png", [], [])
            print(out)


if __name__ == "__main__":
    main()
