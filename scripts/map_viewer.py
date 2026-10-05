#!/usr/bin/env python3
"""map_viewer.py - 3D-Vorschau der Brush-Geometrie einer VMF.

Zeichnet die Solids einer .vmf in ein tkinter-Canvas, aehnlich zur 3D-Ansicht
in Hammer. Nur Geometrie, keine Entity-Modelle - die Bruecke zu echten
3D-Modellen ist bewusst nicht gebaut.

Kern ist ein Scanline-Rasterizer mit Z-Buffer: fuer jede Bildzeile werden
die Dreieckskanten geschnitten, pro Pixel gewinnt die kleinste Tiefe. Das
ist in Software ein echter Z-Buffer und damit auch fuer verschachtelte
Import-Brushes korrekt - blosses Sortieren der Dreiecke schimmert durch.

Kamera: Orbit um den Szenenmittelpunkt, Maus ziehen = drehen, Mausrad =
zoom, mittlere Taste = verschieben. Echte Pinhole-Projektion mit festem
vertikalem Bildwinkel.

Keine externen Abhaengigkeiten: nur Standardbibliothek.
"""

import math
import re
import time
import tkinter as tk
from tkinter import ttk

try:
    from PIL import Image, ImageTk
    HAVE_PIL = True
except ImportError:                      # Pillow ist optional
    Image = None
    ImageTk = None
    HAVE_PIL = False

# Farben je Material. weiss / grau / dunkelgrau, wie gewuenscht.
# NODRAW ist die unsichtbare Rueckseite - heller als die Wand, damit sie
# die Sicht nicht verdeckt, aber dunkel genug zum Unterscheiden.
MAT_COLORS = {
    "TILE/WHITE_WALL_TILE003B": (226, 228, 232),
    "CONCRETE/CONCRETE_MODULAR_FLOOR001C": (154, 157, 163),
    "TILE/OBSERVATION_TILECEILING001A": (196, 198, 203),
    "SIGNAGE/SIGNAGE_DOORSTATE": (168, 170, 176),
}
COLOR_NODRAW = (118, 121, 128)
COLOR_DEFAULT = (208, 208, 212)
COLOR_EDGE = (58, 61, 69)

BG_TOP_RGB = (0x2a, 0x2d, 0x33)
BG_BOTTOM_RGB = (0x14, 0x16, 0x1a)
BG_TOP = "#%02x%02x%02x" % BG_TOP_RGB
BG_BOTTOM = "#%02x%02x%02x" % BG_BOTTOM_RGB

# Lichtrichtung fuer die einfache Schattierung (zeigt nach oben)
LIGHT = (-0.35, -0.45, 0.82)


# --------------------------------------------------------------------------
# VMF parsen
# --------------------------------------------------------------------------
def _blocks(text, name):
    """Alle Bloecke namens `name`, verschachtelt korrekt gezaehlt."""
    out = []
    for m in re.finditer(r'\b%s\s*\{' % re.escape(name), text):
        i = m.end() - 1
        depth = 0
        j = i
        while j < len(text):
            if text[j] == '{':
                depth += 1
            elif text[j] == '}':
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out.append(text[i:j + 1])
    return out


def _norm(v):
    ln = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (v[0] / ln, v[1] / ln, v[2] / ln) if ln else (0.0, 0.0, 0.0)


def _tri(a, b, c, mat, hidden):
    u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    n = (u[1] * v[2] - u[2] * v[1],
         u[2] * v[0] - u[0] * v[2],
         u[0] * v[1] - u[1] * v[0])
    return (a, b, c, n, mat, hidden)


def parse_solids(text, include_nodraw=True):
    """Solids -> (dreiecke, kanten, anzahl_solids, anzahl_nodraw).

    Ein Solid hat mehrere `side`-Bloecke, jeder mit eigenem
    `vertices_plus` (4 Eckpunkte) und eigenem Material. Deshalb wird
    pro side geparst, nicht pro Solid - sonst haette man die Eckpunkte
    aller sechs Flaechen in einem Polygon.

    Dreieck: (a, b, c, normale, material, ist_nodraw).
    """
    faces = []
    edges = []
    total = 0
    nodraw = 0
    for solid in _blocks(text, "solid"):
        sides = _blocks(solid, "side")
        if not sides:
            continue
        total += 1
        mat = ""
        m = re.search(r'"material"\s+"([^"]*)"', sides[0])
        if m:
            mat = m.group(1)
        hidden = mat == "TOOLS/TOOLSNODRAW"
        if hidden:
            nodraw += 1
        if hidden and not include_nodraw:
            continue
        for side in sides:
            vs = [tuple(map(float, v.split()))
                  for v in re.findall(r'"v"\s+"([-\d.eE ]+)"', side)]
            if len(vs) < 3:
                continue
            sm = re.search(r'"material"\s+"([^"]*)"', side)
            smat = sm.group(1) if sm else mat
            shid = smat == "TOOLS/TOOLSNODRAW"
            if len(vs) == 4:
                edges.append(tuple(vs))
                faces.append(_tri(vs[0], vs[1], vs[2], smat, shid))
                faces.append(_tri(vs[0], vs[2], vs[3], smat, shid))
            else:
                for k in range(1, len(vs) - 1):
                    faces.append(_tri(vs[0], vs[k], vs[k + 1], smat, shid))
    return faces, edges, total, nodraw


def _scene_bounds(faces, edges):
    pts = [v for f in faces for v in f[:3]] + [v for e in edges for v in e]
    if not pts:
        return (0.0, 0.0, 0.0), 1.0
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    c = ((min(xs) + max(xs)) / 2.0,
         (min(ys) + max(ys)) / 2.0,
         (min(zs) + max(zs)) / 2.0)
    r = max(max(xs) - min(xs),
            max(ys) - min(ys),
            max(zs) - min(zs)) / 2.0
    return c, max(r, 1.0)


# --------------------------------------------------------------------------
# Kamera
# --------------------------------------------------------------------------
class Camera:
    """Orbit-Kamera. self.cx/cy/cz ist der Zielpunkt, self.dist der Abstand.

    Die Basis ist orthonormal: right, up und eye_dir stehen paarweise
    senkrecht aufeinander. Wichtig, weil die Projektion sonst schiefe
    Bilder liefert.
    """

    def __init__(self, center, radius):
        self.cx, self.cy, self.cz = center
        self.yaw = -0.9
        self.pitch = 0.30
        self.fov = math.radians(45.0)
        self.tan_half_fov = math.tan(self.fov * 0.5)
        self.dist = radius * 3.2 + 1.0
        self.min_dist = radius * 0.35
        self.max_dist = radius * 40.0

    def basis(self):
        cy = math.cos(self.yaw)
        sy = math.sin(self.yaw)
        cp = math.cos(self.pitch)
        sp = math.sin(self.pitch)
        # Blickrichtung von der Kamera in die Szene
        d = (sy * cp, -cy * cp, -sp)
        # right = up_welt x d, mit up_welt = (0,0,1)
        r = (-d[1], d[0], 0.0)
        ln = math.sqrt(r[0] * r[0] + r[1] * r[1]) or 1.0
        r = (r[0] / ln, r[1] / ln, 0.0)
        # up = d x right  (dadurch automatisch orthonormal)
        u = (d[1] * r[2] - d[2] * r[1],
             d[2] * r[0] - d[0] * r[2],
             d[0] * r[1] - d[1] * r[0])
        return r, u, d

    def eye(self):
        _r, _u, d = self.basis()
        return (self.cx - d[0] * self.dist,
                self.cy - d[1] * self.dist,
                self.cz - d[2] * self.dist)

    def frame(self, w, h):
        """(right, up, eye_dir, eye) einmal fuer ein ganzes Bild.

        to_view() braucht die Kamera-Basis fuer jeden Eckpunkt. Sie
        vorher je Punkt neu zu berechnen kostete 10 930 Aufrufe pro
        Frame - das war der groesste Einzelposten. Jetzt einmal pro Bild.
        """
        r, u, d = self.basis()
        e = (self.cx - d[0] * self.dist,
             self.cy - d[1] * self.dist,
             self.cz - d[2] * self.dist)
        return r, u, d, e

    @staticmethod
    def project(p, r, u, d, e, w, h, tan_half, fovy):
        """Punkt mit vorberechneter Basis projizieren."""
        ex = p[0] - e[0]
        ey = p[1] - e[1]
        ez = p[2] - e[2]
        vz = ex * d[0] + ey * d[1] + ez * d[2]
        if vz <= 1e-3:
            return None
        vx = ex * r[0] + ey * r[1] + ez * r[2]
        vy = ex * u[0] + ey * u[1] + ez * u[2]
        f = fovy / (vz * tan_half)
        return (w * 0.5 + vx * f, h * 0.5 - vy * f, vz, f)

    def to_view(self, p, w, h):
        """Bequemlichkeits-Wrapper - rechnet die Basis selbst."""
        r, u, d, e = self.frame(w, h)
        return self.project(p, r, u, d, e, w, h,
                            self.tan_half_fov, h * 0.5)

    def clamp(self):
        self.pitch = max(-1.45, min(1.45, self.pitch))
        self.dist = max(self.min_dist, min(self.max_dist, self.dist))


# --------------------------------------------------------------------------
# Rasterizer
# --------------------------------------------------------------------------
def rasterize(polys, w, h):
    """polys: [(vs_3punkte, farbe)] -> {y: {x: farbe}}.

    Scanline mit baryzentrischem Test, Z-Buffer pro Pixel.
    """
    zbuf = {}
    for vs, col in polys:
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = vs
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-9:
            continue
        inv = 1.0 / area
        y_lo = max(0, int(math.floor(min(y0, y1, y2))))
        y_hi = min(h - 1, int(math.ceil(max(y0, y1, y2))))
        for y in range(y_lo, y_hi + 1):
            yc = y + 0.5
            xa = max(0, int(math.floor(min(x0, x1, x2))))
            xb = min(w - 1, int(math.ceil(max(x0, x1, x2))))
            for x in range(xa, xb + 1):
                xc = x + 0.5
                a = ((x1 - x0) * (yc - y0) - (y1 - y0) * (xc - x0)) * inv
                b = ((x2 - x1) * (yc - y1) - (y2 - y1) * (xc - x1)) * inv
                c = 1.0 - a - b
                if a < -1e-6 or b < -1e-6 or c < -1e-6:
                    continue
                pz = a * z0 + b * z1 + c * z2
                row = zbuf.setdefault(y, {})
                cur = row.get(x)
                if cur is None or pz < cur[0]:
                    row[x] = (pz, col)
    return zbuf


def _mid_z(tri):
    return sum(p[2] for p in tri[:3]) / 3.0


def _ceiling_cut(faces):
    """z-Wert, oberhalb dessen horizontale Flaechen als Decke gelten.

    Boden und Decke sind beides horizontale Platten mit +z-Normale. Die
    Grente sitzt in der Mitte zwischen unterster und oberster solcher
    Flaeche - damit faellt die Decke weg und der Boden bleibt, unabhaengig
    von der Kameraposition.
    """
    zs = [_mid_z(t) for t in faces if _norm(t[3])[2] > 0.7]
    return (min(zs) + max(zs)) / 2.0 if zs else 0.0


def _rasterize_numpy(polys, w, h):
    """Z-Buffer mit numpy: alle Dreiecke vektorisiert.

    Pro Dreieck wird ein Gitter ueber seine Bildflaeche erzeugt, die
    baryzentrischen Gewichte werden mit einer Maske auf die Flaeche
    beschraenkt und nur die gültigen Pixel geschrieben. Damit laeuft
    die innere Schleife in C statt in Python - das ist der Unterschied
    zwischen ~450 ms und ~20 ms bei 1200x795.
    """
    import numpy as np

    depth = np.full(w * h, np.inf, dtype=np.float32)
    idx = np.full(w * h, -1, dtype=np.int32)

    ys_all = np.arange(h, dtype=np.float32)
    xs_all = np.arange(w, dtype=np.float32)

    for ci, (vs, _col) in enumerate(polys):
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = vs
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-9:
            continue
        inv = np.float32(1.0 / area)

        y_lo = max(0, int(min(y0, y1, y2)))
        y_hi = min(h - 1, int(max(y0, y1, y2)) + 1)
        x_lo = max(0, int(min(x0, x1, x2)))
        x_hi = min(w - 1, int(max(x0, x1, x2)) + 1)
        if y_hi < y_lo or x_hi < x_lo:
            continue

        gy = ys_all[y_lo:y_hi + 1, None] + np.float32(0.5)
        gx = xs_all[x_lo:x_hi + 1][None, :] + np.float32(0.5)

        l0 = ((x2 - x1) * (gy - y1) - (y2 - y1) * (gx - x1)) * inv
        l1 = ((x0 - x2) * (gy - y2) - (y0 - y2) * (gx - x2)) * inv
        l2 = 1.0 - l0 - l1

        m = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
        if not m.any():
            continue

        pz = l0 * z0 + l1 * z1 + l2 * z2
        rows = (np.arange(y_lo, y_hi + 1, dtype=np.int64)[:, None] * w
                + np.arange(x_lo, x_hi + 1, dtype=np.int64)[None, :])
        flat = rows[m]
        pzf = pz[m]
        better = pzf < depth[flat]
        if better.any():
            tgt = flat[better]
            depth[tgt] = pzf[better]
            idx[tgt] = ci

    return idx.reshape(h, w)


def rasterize_index(polys, w, h, n_colors=None):
    """Z-Buffer -> Farb-Index je Pixel (-1 = kein Brush getroffen)."""
    try:
        import numpy  # noqa: F401
    except ImportError:
        zb = rasterize(polys, w, h)
        out = [[-1] * w for _ in range(h)]
        for y, row in zb.items():
            for x, (_z, col) in row.items():
                for ci, (_vs, c) in enumerate(polys):
                    if c == col:
                        out[y][x] = ci
                        break
        return out
    return _rasterize_numpy(polys, w, h)


def build_drawlist(faces, cam, w, h, hide_upfacing=False):
    """Sichtbare Dreiecke als nach hinten sortierte Zeichenliste.

    Das ist der ganze Renderer: eine Liste von (x1,y1,x2,y2,x3,y3,farbe),
    sortiert von hinten nach vorn. tkinter zeichnet dann mit
    create_polygon - ein Aufruf je Dreieck, statt einer Schleife je Pixel.

    Rueckseiten fallen weg, Decken optional. Sortiert wird nach mittlerer
    Tiefe; das reicht fuer Brush-Geometrie, weil die Objekte sich nicht
    gegenseitig durchdringen - ein echter Z-Buffer waere nur noetig,
    wenn sich Dreiecke wirklich schneiden.
    """
    r, u, d, e = cam.frame(w, h)
    cut = _ceiling_cut(faces) if hide_upfacing else 0.0
    tan_h = cam.tan_half_fov
    half = h * 0.5
    out = []
    for tri in faces:
        if hide_upfacing and _norm(tri[3])[2] > 0.7 and _mid_z(tri) > cut:
            continue
        # Sichtbarkeit nach MATERIAL, nicht nach Blickrichtung.
        # 2026-10-04: die alte Regel (dot(n, eye_dir) >= 0 -> Rueckseite)
        # hat 16 von 26 sichtbaren Flaechen verworfen, weil der Compiler
        # die Materialflaechen konsequent nach INNEN wendet. Bei einem
        # geschlossenen Solid zeigen alle Aussenkanten nach aussen, aber
        # der Compiler setzt die sichtbare Flaeche als "Innenseite" -
        # Hammer akzeptiert beides, vbsp auch.
        #
        # Die verlaessliche Aussage steht im Material:
        #   NODRAW  = verdeckte Innenseite, nicht zeichnen
        #   Material = die Flaeche, die man wirklich sieht
        if tri[5]:
            continue                        # NODRAW: verdeckt
        n = _norm(tri[3])                   # fuer das Shading noetig
        pts = []
        ok = True
        depth = 0.0
        for p in tri[:3]:
            v = cam.project(p, r, u, d, e, w, h, tan_h, half)
            if v is None:
                ok = False
                break
            pts.append(v)
            depth += v[2]
        if not ok:
            continue
        lam = max(0.0, -(n[0] * LIGHT[0] + n[1] * LIGHT[1]
                        + n[2] * LIGHT[2]))
        k = 0.62 + 0.38 * lam
        base = COLOR_NODRAW if tri[5] else MAT_COLORS.get(tri[4],
                                                         COLOR_DEFAULT)
        col = tuple(min(255, int(c * k)) for c in base)
        out.append(((pts[0][0], pts[0][1], pts[1][0], pts[1][1],
                     pts[2][0], pts[2][1], col), depth / 3.0))
    # hinten zuerst zeichnen
    out.sort(key=lambda t: -t[1])
    return [t[0] for t in out]


def build_polys(faces, cam, w, h, hide_upfacing=False):
    """Dreiecke projizieren, Rueckseiten wegwerfen, Farbe bestimmen.

    hide_upfacing blendet die Decke aus, damit man in den Raum sieht -
    das Gegenstueck zu Hammerc Clipping. Nur was ueber der Szenenmitte
    liegt und nach oben zeigt; der Boden bleibt sichtbar.
    """
    _r, _u, d = cam.basis()
    _cut_z = _ceiling_cut(faces) if hide_upfacing else 0.0
    polys = []
    for tri in faces:
        # Decke ausblenden. Boden und Decke tragen BEIDE eine nach oben
        # zeigende Normale - sie sind beide horizontale Platten, von oben
        # sichtbar. Die Normale kann sie nicht unterscheiden, nur die
        # Hoehe: Decke ist das oberste horizontale Brett, Boden das
        # unterste. Die Grenze kommt deshalb aus der Szene selbst
        # (_upright_span), unabhaengig davon, wohin die Kamera schaut.
        if hide_upfacing and _norm(tri[3])[2] > 0.7 \
                and _mid_z(tri) > _cut_z:
            continue
        vs = []
        ok = True
        for p in tri[:3]:
            v = cam.to_view(p, w, h)
            if v is None:
                ok = False
                break
            vs.append(v[:3])
        if not ok:
            continue
        n = _norm(tri[3])
        if n[0] * d[0] + n[1] * d[1] + n[2] * d[2] >= -1e-6:
            continue                        # Rueckseite
        lam = max(0.0, -(n[0] * LIGHT[0] + n[1] * LIGHT[1]
                        + n[2] * LIGHT[2]))
        k = 0.62 + 0.38 * lam
        base = COLOR_NODRAW if tri[5] else MAT_COLORS.get(tri[4],
                                                         COLOR_DEFAULT)
        polys.append((vs, tuple(min(255, int(c * k)) for c in base)))
    return polys


# --------------------------------------------------------------------------
# tkinter-Widget
# --------------------------------------------------------------------------
class Viewer(tk.Frame):
    """3D-Vorschau als tkinter-Widget mit Maus-Steuerung."""

    def __init__(self, master, height=520):
        super().__init__(master)
        self.canvas = tk.Canvas(self, height=height, bg=BG_BOTTOM,
                                highlightthickness=0)
        self.canvas.focus_set()
        self.canvas.pack(fill="both", expand=True)
        self.faces = []
        self.edges = []
        self.total = 0
        self.nodraw = 0
        self.camera = None
        self._drag = None
        self._pan = None
        self._pending = None
        self._last_draw = 0.0
        self._frame_ms = 33          # hoechstens 30 fps waehrend des Drehens
        self._bg_key = None
        self._bg_photo = None
        self._bg_img = None
        self.status = tk.StringVar(value="keine Geometrie geladen")
        self.include_nodraw = True
        self._cache = []

        bar = tk.Frame(self)
        bar.pack(fill="x", side="bottom")
        ttk.Label(bar, textvariable=self.status).pack(side="left", padx=6, pady=2)
        self.ceil_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Decke aus", variable=self.ceil_var,
                        command=self._draw_now).pack(side="right", padx=2)
        ttk.Button(bar, text="NODRAW", command=self.toggle_nodraw).pack(
            side="right", padx=2)
        ttk.Button(bar, text="Draufsicht", command=self.top_view).pack(
            side="right", padx=2)
        ttk.Button(bar, text="Zentrieren", command=self.reset_view).pack(
            side="right", padx=2)

        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<Button-1>", self._down)
        self.canvas.bind("<B1-Motion>", self._move)
        self.canvas.bind("<ButtonRelease-1>", self._up)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-2>", self._pan_down)
        self.canvas.bind("<B2-Motion>", self._pan_move)
        self.canvas.bind("<ButtonRelease-2>", self._up)
        self.canvas.bind("<Key>", self._key)

    # -- Maus -----------------------------------------------------------
    def _down(self, e):
        self.canvas.focus_set()
        self._drag = (e.x, e.y)
        self.canvas.configure(cursor="fleur")

    def _up(self, e):
        self._drag = None
        self._pan = None
        self._pending = None
        if self._pending is not None:
            try:
                self.after_cancel(self._pending)
            except Exception:
                pass
            self._pending = None
        self._draw_now()

    def _move(self, e):
        if not self._drag or not self.camera:
            return
        dx = e.x - self._drag[0]
        dy = e.y - self._drag[1]
        self._drag = (e.x, e.y)
        self.camera.yaw += dx * 0.012
        self.camera.pitch -= dy * 0.010
        self.camera.clamp()
        self._request_draw()

    def _request_draw(self):
        """Redraw oeber einen Timer: maximal ein Frame je _frame_ms.

        tkinter feuert bei jedem Mouse-Move ein eigenes Event. Ohne
        diese Bremse wuerde der Rasterizer pro Pixel des Wegs laufen -
        das ist genau das Ruckeln, das man beim Ziehen spuert.
        """
        now = time.monotonic() * 1000.0
        if now - self._last_draw < self._frame_ms:
            if self._pending is None:
                self._pending = self.after(self._frame_ms, self._draw_now)
            return
        # Zeitstempel JETZT setzen, nicht erst im Callback - sonst ist
        # die verstrichene Zeit 0 und die Bremse greift nie.
        self._last_draw = now
        self._pending = None
        self.redraw()

    def _draw_now(self):
        self._pending = None
        self._last_draw = time.monotonic() * 1000.0
        self.redraw()

    def _wheel(self, e):
        if not self.camera:
            return
        f = 1.15 if e.delta < 0 else 1 / 1.15
        self.camera.dist *= f
        self.camera.clamp()
        self._draw_now()

    def _pan_down(self, e):
        if not self.camera:
            return
        self._pan = (e.x, e.y, self.camera.cx, self.camera.cy,
                     self.camera.cz)
        self.canvas.configure(cursor="hand2")

    def _pan_move(self, e):
        if not self._pan or not self.camera:
            return
        x0, y0, cx, cy, cz = self._pan
        cam = self.camera
        # Weltweite Verschiebung pro Pixel anhand der Projektionsfaktors
        r, u, d = cam.basis()
        eye = cam.eye()
        vz = sum((cam.cx - eye[i]) * d[i] for i in range(3)) or 1.0
        f = (max(self.canvas.winfo_height(), 1) * 0.5) \
            / (vz * cam.tan_half_fov)
        dx = -(e.x - x0) / f
        dy = (e.y - y0) / f
        cam.cx = cx + r[0] * dx + u[0] * dy
        cam.cy = cy + r[1] * dx + u[1] * dy
        cam.cz = cz + r[2] * dx + u[2] * dy
        self.redraw()

    def _key(self, e):
        k = e.keysym.lower()
        if k == "c":
            self.ceil_var.set(not self.ceil_var.get())
            self.redraw()
        elif k == "n":
            self.toggle_nodraw()
        elif k == "t":
            self.top_view()
        elif k == "r":
            self.reset_view()

    # -- Ansichten -------------------------------------------------------
    def top_view(self):
        if self.camera:
            self.camera.pitch = 1.40
            self.camera.yaw = 0.0
            self.camera.clamp()
            self.redraw()

    def reset_view(self):
        if self.faces:
            c, r = _scene_bounds(self.faces, self.edges)
            self.camera = Camera(c, r)
            self.redraw()

    def toggle_nodraw(self):
        self.include_nodraw = not self.include_nodraw
        if self.faces:
            self._reload_from_cache()
        else:
            self.redraw()

    def _reload_from_cache(self):
        """faces mit include_nodraw neu filtern."""
        keep = self._cache
        self.faces = [f for f in keep if self.include_nodraw or not f[5]]
        extra = (" (+%d NODRAW)" % self.nodraw) if self.include_nodraw else ""
        self.status.set("%d Brushes%s" % (self.total, extra))
        self.redraw()

    # -- Laden -----------------------------------------------------------
    def load_vmf_text(self, text, include_nodraw=True):
        try:
            faces, edges, total, nodraw = parse_solids(text, True)
        except Exception as exc:
            self.status.set("Fehler beim Lesen der Geometrie: %s" % exc)
            return False
        if not faces:
            self.faces, self.edges = [], []
            self.camera = None
            self.status.set("keine Brush-Geometrie in dieser VMF")
            self.redraw()
            return False
        self._cache = faces
        self.edges = edges
        self.total = total
        self.nodraw = nodraw
        self.include_nodraw = include_nodraw
        self.faces = faces if include_nodraw else [f for f in faces
                                                  if not f[5]]
        c, r = _scene_bounds(faces, edges)
        self.camera = Camera(c, r)
        extra = (" (+%d NODRAW)" % nodraw) if include_nodraw else ""
        self.status.set("%d Brushes%s" % (total, extra))
        self.redraw()
        return True

    # -- Zeichnen --------------------------------------------------------
    def redraw(self):
        """Bild neu aufbauen.

        Der alte Weg (ein create_rectangle je Pixel) kostete bei 1400x900
        rund 8 Sekunden allein fuer die Canvas-Aktualisierung. Jetzt wird
        das fertige Bild als EIN PhotoImage uebergeben - das ist rund
        fuenfzigmal schneller. Ohne Pillow gibt es den alten Weg als
        Rueckfall.
        """
        cv = self.canvas
        w = cv.winfo_width()
        h = cv.winfo_height()
        if w <= 1 or h <= 1:
            return

        if not self.faces or not self.camera:
            self._paint_background(cv, w, h)
            cv.create_text(w / 2, h / 2, text="keine Geometrie geladen",
                           fill="#6a6e78", font=("Segoe UI", 11))
            return

        draw = build_drawlist(self.faces, self.camera, w, h,
                              self.ceil_var.get())
        self._last_poly_count = len(draw)
        cv.delete("all")
        bg = self._paint_background(cv, w, h)
        if bg is not None:
            cv.create_image(0, 0, image=bg, anchor="nw")
        for x1, y1, x2, y2, x3, y3, col in draw:
            cv.create_polygon(x1, y1, x2, y2, x3, y3,
                              fill="#%02x%02x%02x" % col, outline="")
        self._draw_edges(cv, w, h)
        cv.create_text(10, h - 24,
                       text="Ziehen: drehen   Mausrad: zoom   "
                            "Mittlere Taste: verschieben",
                       fill="#5c6068", font=("Segoe UI", 8), anchor="w")

    def _draw_edges(self, cv, w, h):
        """Brush-Umrisse als EIN create_line mit allen Segmenten.

        tkinter nimmt eine flache Koordinatenliste. Statt vier Linien je
        Viereck ist das ein einziger Aufruf - bei 13 Brushes also 1
        statt 78 Objekte.
        """
        flat = []
        r, u, d, e = self.camera.frame(w, h)
        tan_h = self.camera.tan_half_fov
        half = h * 0.5
        for quad in self.edges:
            pv = []
            for pt in quad:
                v = self.camera.project(pt, r, u, d, e, w, h,
                                        tan_h, half)
                if v is None:
                    pv = None
                    break
                pv.append(v[:2])
            if not pv:
                continue
            for k in range(4):
                flat.extend((pv[k][0], pv[k][1],
                             pv[(k + 1) % 4][0], pv[(k + 1) % 4][1]))
        if flat:
            cv.create_line(*flat, fill="#%02x%02x%02x" % COLOR_EDGE)

    def _paint_background(self, cv, w, h):
        """Hintergrundverlauf, pro Groessenaenderung einmal gebaut.

        Als 20 create_rectangle kostete das ~15 ms pro Frame - bei
        23 ms Gesamtzeit also zwei Drittel. Der Verlauf ist statisch,
        wird also einmal erzeugt, als PhotoImage zwischengespeichert
        und danach nur noch als EIN Bild angezeigt.
        """
        key = (w, h)
        if key != getattr(self, "_bg_key", None):
            top = BG_TOP_RGB
            bot = BG_BOTTOM_RGB
            strip = []
            for i in range(32):
                t = i / 31.0
                strip.append(tuple(int(top[k] + (bot[k] - top[k]) * t)
                                   for k in range(3)))
            if HAVE_PIL:
                try:
                    import numpy as np
                    ramp = (np.arange(h, dtype=np.float32)
                            / max(h - 1, 1))[:, None]
                    top_a = np.array(top, dtype=np.float32)
                    bot_a = np.array(bot, dtype=np.float32)
                    arr = (top_a + (bot_a - top_a) * ramp).astype(np.uint8)
                    arr = np.repeat(arr[:, None, :], w, axis=1)
                    self._bg_img = Image.fromarray(arr, "RGB")
                    self._bg_key = key
                    self._bg_photo = ImageTk.PhotoImage(self._bg_img)
                    self._bg_ref = self._bg_photo
                    return self._bg_photo
                except Exception:
                    pass
            self._bg_key = key
            self._bg_photo = None
        if getattr(self, "_bg_photo", None) is not None:
            return self._bg_photo
        # Rueckfall ohne Pillow
        for i, c in enumerate(strip):
            cv.create_rectangle(0, h * i / 32.0, w, h * (i + 1) / 32.0 + 1,
                                fill="#%02x%02x%02x" % c, outline="")
        return None

    # ---- entfernter Z-Buffer-Pfad (siehe Commit-Historie) ----

    @staticmethod
    def _lerp(a, b, t):
        return "#%02x%02x%02x" % tuple(
            int(int(a[i:i + 2], 16) + (int(b[i:i + 2], 16)
                                       - int(a[i:i + 2], 16)) * t)
            for i in (1, 3, 5))


def _bg_gradient(h, top=None, bottom=None):
    """Senkrechter Verlauf als Liste aus h RGB-Tupeln."""
    top = top or BG_TOP_RGB
    bottom = bottom or BG_BOTTOM_RGB
    out = []
    for y in range(h):
        t = y / (h - 1.0) if h > 1 else 0.0
        out.append(tuple(int(top[i] + (bottom[i] - top[i]) * t)
                        for i in range(3)))
    return out


def open_viewer(parent, vmf_text, title="3D-Vorschau", include_nodraw=True):
    """Popup-Fenster mit der Vorschau. Gibt (fenster, viewer) zurueck."""
    win = tk.Toplevel(parent)
    win.title(title)
    win.geometry("1000x660")
    v = Viewer(win, height=600)
    v.pack(fill="both", expand=True)
    v.load_vmf_text(vmf_text, include_nodraw)
    return win, v


def main():
    import argparse
    ap = argparse.ArgumentParser(description="3D-Vorschau einer VMF")
    ap.add_argument("vmf", nargs="?")
    ap.add_argument("--no-nodraw", action="store_true")
    args = ap.parse_args()

    root = tk.Tk()
    root.title("VMFScript 3D-Vorschau")
    root.geometry("1040x700")
    v = Viewer(root, height=640)
    v.pack(fill="both", expand=True)
    if args.vmf:
        v.load_vmf_text(open(args.vmf, encoding="utf-8",
                             errors="replace").read(),
                        not args.no_nodraw)
    root.mainloop()


if __name__ == "__main__":
    main()