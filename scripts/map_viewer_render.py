#!/usr/bin/env python3
"""Headless-PNG-Renderer fuer die 3D-Vorschau.

Nutzt Kamera- und Rasterizer-Mathes aus map_viewer, schreibt aber direkt
ein PNG statt in ein tkinter-Canvas. Zweck: die Vorschau ohne Fenster
prüfbar zu machen (Screenshot fürs Auge, Regressionstest).

    python map_viewer_render.py map_ref.vmf out.png
    python map_viewer_render.py map_ref.vmf out.png --yaw 1.2 --pitch 0.4
    python map_viewer_render.py map_ref.vmf out.png --no-nodraw
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import map_viewer as V  # noqa: E402

try:
    from PIL import Image
except ImportError:
    raise SystemExit("Pillow noetig: pip install pillow")


def render(text, width=1280, height=800, yaw=None, pitch=None, dist_mul=None,
           include_nodraw=True, hide_ceiling=False,
           bg_top=(0x2a, 0x2d, 0x33),
           bg_bottom=(0x14, 0x16, 0x1a)):
    faces, edges, total, nodraw = V.parse_solids(text, True)
    if not faces:
        raise SystemExit("keine Brush-Geometrie gefunden")
    if not include_nodraw:
        faces = [f for f in faces if not f[5]]

    center, radius = V._scene_bounds(faces, edges)
    cam = V.Camera(center, radius)
    if yaw is not None:
        cam.yaw = yaw
    if pitch is not None:
        cam.pitch = pitch
    if dist_mul is not None:
        cam.dist = radius * dist_mul
    cam.clamp()

    img = Image.new("RGB", (width, height))
    px = img.load()

    # Hintergrund: vertikaler Verlauf
    for y in range(height):
        t = y / (height - 1.0)
        c = tuple(int(bg_top[i] + (bg_bottom[i] - bg_top[i]) * t)
                  for i in range(3))
        for x in range(width):
            px[x, y] = c

    # Derselbe Pfad wie die GUI: build_drawlist -> hinten nach vorn
    # zeichnen. Damit prueft der Screenshot wirklich das Bild, das auch
    # im Fenster erscheint - vorher stand hier noch der alte Z-Buffer,
    # der die Gerber-Mathes inzwischen gar nicht mehr benutzt.
    draw = V.build_drawlist(faces, cam, width, height, hide_ceiling)

    from PIL import ImageDraw
    pen = ImageDraw.Draw(img)
    for x1, y1, x2, y2, x3, y3, col in draw:
        pen.polygon([(x1, y1), (x2, y2), (x3, y3)],
                    fill=col, outline=None)
    for quad in edges:
        pv = []
        for pt in quad:
            v = cam.to_view(pt, width, height)
            if v is None:
                pv = None
                break
            pv.append(v[:2])
        if not pv:
            continue
        for k in range(4):
            pen.line([pv[k], pv[(k + 1) % 4]], fill=V.COLOR_EDGE)

    return img, total, nodraw


def draw_line(px, w, h, x0, y0, x1, y1, col):
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    steps = 0
    while steps < 20000:
        if 0 <= x0 < w and 0 <= y0 < h:
            px[x0, y0] = col
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
        steps += 1


def main():
    ap = argparse.ArgumentParser(description="VMF 3D-Vorschau als PNG")
    ap.add_argument("vmf")
    ap.add_argument("out")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=800)
    ap.add_argument("--yaw", type=float, default=None)
    ap.add_argument("--pitch", type=float, default=None)
    ap.add_argument("--dist", type=float, default=None,
                    help="Vielfaches der Szenen-Distanz")
    ap.add_argument("--no-nodraw", action="store_true")
    ap.add_argument("--no-ceiling", action="store_true",
                    help="Decken ausblenden, Blick in den Raum")
    args = ap.parse_args()

    text = open(args.vmf, encoding="utf-8", errors="replace").read()
    img, total, nodraw = render(text, args.width, args.height,
                               args.yaw, args.pitch, args.dist,
                               not args.no_nodraw, args.no_ceiling)
    img.save(args.out)
    print("%s  %d Brushes%s" % (args.out, total,
                                (" (+%d NODRAW)" % nodraw) if nodraw else ""))


if __name__ == "__main__":
    main()