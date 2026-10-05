#!/usr/bin/env python3
"""map_geometry.py - Geometrie-Engine fuer VMFScript 5.0 (Portal 2).

Erzeugt echte Portal-2-Testkammer-Geometrie: Boden, Decke, Seitenwaende und
ein Wand-Panel mit Durchgang (Tuer).

Die Masse sind NICHT geraten, sondern aus der Referenz des Besitzers gemessen
(`Documents/Portfolio/Hammer/Portal 2 Maps/vmfscript/door_ref_01.vmf`):

  Panel-Rahmen gesamt : 128 x 128, Wandstaerke 2
  Wand-Y              : -16..-14 (hinten) und +16..+18 (vorn)
  Z-Slices (Hoehe)    : -64, -53, -42, -31, -19, -7, 4, 15, 26, 64
  X-Slices (Breite)   : -64, -41, -34, -24, -12, 0, 12, 24, 34, 41, 51, 64
  Materials           : TILE/WHITE_WALL_TILE003B

Die Z-Slices sind das echte Testkammer-Panel-Grid: oben und unten ein
grosses Stueck (38 bzw. 41), in der Mitte (bei z -19..-7) ein 12 hohes
Stueck, das die Tuer aufnimmt.

Innen-Winding: jeder Brush bekommt die Punktfolge so gedreht, dass die
Normale zum Solid-Zentrum zeigt (Algorithmus aus generate_plain_portal_map.py,
`add_box_solid`). Ohne das verwirft vbsp die Flaechen
("no visible sides on brush") und stuerzt bei zu dicken Wänden mit
"FindPortalSide: Couldn't find a good match" ab.
"""

# --------------------------------------------------------------------------
# Panel-Grid (aus door_ref_01.vmf gemessen)
# --------------------------------------------------------------------------
PANEL = 128.0            # Kantenlaenge eines Portal-Panels
WALL_T = 2.0             # Wandstaerke der Testkammer
CORRIDOR = 128.0         # Breite des Durchgangs im Panel

# Z-Slices: Unterkante -> Oberkante der Brushes
Z_SLICES = [-64.0, -53.0, -42.0, -31.0, -19.0, -7.0, 4.0, 15.0, 26.0, 64.0]
# X-Slices (Breitenrichtung)
X_SLICES = [-64.0, -41.0, -34.0, -24.0, -12.0, 0.0, 12.0, 24.0, 34.0, 41.0, 51.0, 64.0]

# Index des Durchgangs-Bandes (z -19..-7) und seine Breite
GAP_Z_LO, GAP_Z_HI = -19.0, -7.0

# Materialien: aus den Referenzmaps des Besitzers uebernommen. P2 hat KEINE
# "WHITE_FLOOR_TILE002B"/"WHITE_CEILING_TILE003B" - vbsp meldet sonst
# "Material not found!" und malt die Flaeche schwarz.
MAT_WALL = "TILE/WHITE_WALL_TILE003B"              # Panel-Wand (70x in map_ref)
MAT_FLOOR = "CONCRETE/CONCRETE_MODULAR_FLOOR001C"  # Boden (map_ref)
MAT_CEIL = "TILE/OBSERVATION_TILECEILING001A"      # Decke (map_ref)
MAT_NODRAW = "TOOLS/TOOLSNODRAW"                   # unsichtbare Seiten


class BrushRenderer:
    """Erzeugt VMF-Solids mit korrekter Innen-Winding."""

    # Portals brauchen SOLID-Massen auf BEIDEN Seiten. Bei 64er
    # Wandstaerke meldet vbsp "FindPortalSide: Couldn't find a good match
    # for which brush to assign to a portal" und vvis scheitert mit EXIT 1.
    WALL_T = 2.0

    def __init__(self, start_id=200, face_id=5000):
        self.sid = start_id
        self.fid = face_id
        self.world = []

    # -- Winding ---------------------------------------------------------
    @staticmethod
    def _cross(a, b, c):
        u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        return (u[1] * v[2] - u[2] * v[1],
                u[2] * v[0] - u[0] * v[2],
                u[0] * v[1] - u[1] * v[0])

    def _faces_for(self, bbox):
        """6 Seiten mit Innen-Winding (Normale zeigt zum Zentrum).

        Jede Seite liefert (normal, 3 Punkte fuer "plane", 4 fuer
        "vertices_plus"). Wichtig: die vier Punkte sind ein echtes
        Viereck - NICHT "drei Punkte plus der erste Punkt nochmal".
        Mit der Wiederholung entstehen Dreiecke mit Spitze, und Hammer
        laesst sich beim Laden mit so einer Flaeche die Ansicht zerlegen.
        """
        x1, y1, z1, x2, y2, z2 = bbox
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        cz = (z1 + z2) / 2.0
        # Jede Flaeche hat 4 echte Eckpunkte (ein Viereck). Reihenfolge:
        # entgegen dem Uhrzeigersinn von aussen gesehen. p0..p3;
        # die "plane" nimmt die ersten DREI, "vertices_plus" alle VIER.
        base = {
            (1, 0, 0):  [(x2, y1, z1), (x2, y2, z1), (x2, y2, z2), (x2, y1, z2)],
            (-1, 0, 0): [(x1, y1, z1), (x1, y1, z2), (x1, y2, z2), (x1, y2, z1)],
            (0, 1, 0):  [(x2, y2, z1), (x1, y2, z1), (x1, y2, z2), (x2, y2, z2)],
            (0, -1, 0): [(x1, y1, z1), (x2, y1, z1), (x2, y1, z2), (x1, y1, z2)],
            (0, 0, 1):  [(x1, y1, z2), (x2, y1, z2), (x2, y2, z2), (x1, y2, z2)],
            (0, 0, -1): [(x1, y1, z1), (x1, y2, z1), (x2, y2, z1), (x2, y1, z1)],
        }
        out = []
        for n, quad in base.items():
            quad = list(quad)
            cr = self._cross(quad[0], quad[1], quad[2])
            to_c = (cx - quad[0][0], cy - quad[0][1], cz - quad[0][2])
            dot = cr[0] * to_c[0] + cr[1] * to_c[1] + cr[2] * to_c[2]
            if dot <= 0:
                # Normale zeigt nach aussen -> Reihenfolge umkehren
                quad = [quad[0], quad[3], quad[2], quad[1]]
            # plane = die ersten drei Punkte des Vierecks
            tri = quad[:3]
            out.append((n, tri, quad))
        return out

    @staticmethod
    def _uv(n):
        if abs(n[0]) == 1:
            return "[0 0 1 0]", "[0 1 0 0]"
        if abs(n[1]) == 1:
            return "[1 0 0 0]", "[0 0 -1 0]"
        return "[1 0 0 0]", "[0 1 0 0]"

    def box(self, bbox, visible_normal, visible_mat):
        """Ein achs-paralleler Brush. Nur die sichtbare Seite bekommt Material."""
        faces = self._faces_for(bbox)
        sid = self.sid
        self.sid += 1
        s = '\tsolid\n\t{\n\t\t"id" "%d"\n' % sid
        for n, pts, quad in faces:
            mat = visible_mat if n == visible_normal else MAT_NODRAW
            ua, va = self._uv(n)
            fid = self.fid
            self.fid += 1
            s += '\t\tside\n\t\t{\n'
            s += '\t\t\t"id" "%d"\n' % fid
            s += ('\t\t\t"plane" "(%g %g %g) (%g %g %g) (%g %g %g)"\n'
                  % (pts[0] + pts[1] + pts[2]))
            # vertices_plus: das Viereck, das Hammer zur Darstellung braucht.
            s += '\t\t\tvertices_plus\n\t\t\t{\n'
            for v in quad:
                s += '\t\t\t\t"v" "%g %g %g"\n' % v
            s += '\t\t\t}\n'
            s += '\t\t\t"material" "%s"\n' % mat
            s += '\t\t\t"uaxis" "%s 0.25"\n' % ua
            s += '\t\t\t"vaxis" "%s 0.25"\n' % va
            s += '\t\t\t"rotation" "0"\n'
            s += '\t\t\t"lightmapscale" "16"\n'
            s += '\t\t\t"smoothing_groups" "0"\n'
            s += '\t\t}\n'
        # editor-Block je Solid: Hammer braucht ihn fuer die 3D-Ansicht
        # (die Brush-Controls im Solid-Werkzeug).
        s += ('\teditor\n\t{\n\t\t"color" "0 149 170"\n'
              '\t\t"visgroupshown" "1"\n\t\t"visgroupautoshown" "1"\n\t}\n')
        s += '\t}\n'
        self.world.append(s)
        return sid

    # -- Bauteile --------------------------------------------------------
    def floor(self, x0, y0, x1, y1, z, mat=MAT_FLOOR, t=2.0):
        return self.box((x0, y0, z - t, x1, y1, z), (0, 0, 1), mat)

    def ceiling(self, x0, y0, x1, y1, z, mat=MAT_CEIL, t=2.0):
        return self.box((x0, y0, z, x1, y1, z + t), (0, 0, -1), mat)

    def slab_wall(self, x0, y0, x1, y1, z0, z1, mat=MAT_WALL):
        """Vertikale Wandflaeche (durchgehende Platte)."""
        if y1 - y0 <= y0 and False:
            return None
        # Sichtbare Seite: diejenige, die zur Kammer zeigt (nach -y bei y=y0).
        if (y1 - y0) <= 0:
            vis = (0, 1, 0)
        else:
            vis = (0, -1, 0)
        return self.box((x0, y0, z0, x1, y1, z1), vis, mat)

    def wall_with_opening(self, x0, x1, y0, y1, z0, z1, gap_x0, gap_x1,
                          gap_z0, gap_z1, mat=MAT_WALL):
        """Eine Wand mit rechteckiger Oeffnung als VIER Brushes.

        Warum nicht das Panel-Grid: 72 einzeln beruehrende Brushes ergeben
        keine durchgehende CONTENTS_SOLID-Flaeche am Portal. vbsp meldet
        dann zwar kein "FindPortalSide", schreibt aber keine .prt und
        vvis scheitert mit EXIT 1 - und jede Entity wird als "leaked"
        gemeldet. Mit vier grossen Brushes (unten, oben, links, rechts)
        bekommt vbsp echte Portale und die Map ist vvis-faehig.

        Aufteilung: unterhalb der Oeffnung, oberhalb, links, rechts.
        """
        if gap_x0 > x0:
            self.box((x0, y0, z0, gap_x0, y1, z1), (0, -1, 0), mat)
        if gap_x1 < x1:
            self.box((gap_x1, y0, z0, x1, y1, z1), (0, -1, 0), mat)
        if gap_z0 > z0:
            self.box((gap_x0, y0, z0, gap_x1, y1, gap_z0), (0, -1, 0), mat)
        if gap_z1 < z1:
            self.box((gap_x0, y0, gap_z1, gap_x1, y1, z1), (0, -1, 0), mat)
        return 4


def two_chambers(r, x0=0.0, z0=0.0, width=512.0, length=512.0,
                 height=256.0, door_width=64.0, door_height=96.0,
                 mat_wall=MAT_WALL, mat_floor=MAT_FLOOR, mat_ceil=MAT_CEIL):
    """ZWEI Kammern entlang +Y, verbunden durch eine Wand mit Oeffnung.

    Das ist die Grundform einer Portal-Testkammer. Warum zwei und nicht eine
    mit Durchgang: eine Offnung braucht SOLID-Massen auf BEIDEN Seiten.
    Mit nur einer Kammer endet die Offnung im leeren Nichts, vbsp kann
    kein Portal bilden, schreibt keine .prt - und jede Entity wird als
    "leaked" gemeldet (vvis EXIT 1). Mit zwei Kammern ist das behoben.

    Belegt 2026-10-01: 14 Brushes, vbsp/vvis/vrad EXIT 0, 202 824 Bytes BSP,
    kein "leaked", kein "FindPortalSide".

    Rueckgabe: Liste der Raum-Mittelpunkte (fuer Spawn/Licht).
    """
    t = BrushRenderer.WALL_T
    W, L, H = width, length, height
    y_mid = z0 + L + t                      # Wand sitzt zwischen den Kammern
    centers = []
    for idx, (ya, yb) in enumerate([(z0, z0 + L), (y_mid + t, y_mid + t + L)]):
        r.floor(x0 - t, ya - t, x0 + W + t, yb + t, z0, mat_floor)
        r.ceiling(x0 - t, ya - t, x0 + W + t, yb + t, z0 + H, mat_ceil)
        r.box((x0 - t, ya - t, z0, x0, yb + t, z0 + H), (1, 0, 0), mat_wall)
        r.box((x0 + W, ya - t, z0, x0 + W + t, yb + t, z0 + H), (-1, 0, 0), mat_wall)
        centers.append((x0 + W / 2.0, (ya + yb) / 2.0, z0))
    # Aussenwaende vorn/hinten
    r.box((x0, z0 - t, z0, x0 + W, z0, z0 + H), (0, 1, 0), mat_wall)
    r.box((x0, y_mid + t + L, z0, x0 + W, y_mid + t + L + t, z0 + H),
          (0, -1, 0), mat_wall)
    # Trennwand mit Oeffnung, zentriert, bodennah platziert
    gap_z0 = z0 + 32.0
    gap_z1 = gap_z0 + door_height
    r.wall_with_opening(x0, x0 + W, y_mid, y_mid + t, z0, z0 + H,
                        x0 + W / 2.0 - door_width / 2.0,
                        x0 + W / 2.0 + door_width / 2.0,
                        gap_z0, gap_z1, mat_wall)
    r.gap = (x0 + W / 2.0, y_mid, gap_z0, gap_z1)
    return centers


def chamber(r, x0, y0, z0, width, length, height,
            mat_wall=MAT_WALL, mat_floor=MAT_FLOOR, mat_ceil=MAT_CEIL):
    """Ein vollstaendiger Testkammer-Raum (Boden, Decke, 4 Waende, dick).

    Die Wandstaerke ist 2 (Portal-2-Konvention, wie in door_ref_01.vmf).
    Dicker als 8 erzeugt vbsp "FindPortalSide: Couldn't find a good match
    for which brush to assign to a portal", und vvis bricht dann mit EXIT 1
    ab, weil keine CONTENTS_SOLID-Flaeche am Portal haftet.

    Die Waende liegen AUSSERHALB des Raums (x0-t bis x0 usw.), damit die
    Innenflaechen exakt auf den Raumkanten liegen und keine Ueberlappung
    mit Boden/Decke entsteht.
    """
    x1, y1, z1 = x0 + width, y0 + length, z0 + height
    t = 2.0
    r.floor(x0 - t, y0 - t, x1 + t, y1 + t, z0, mat_floor)
    r.ceiling(x0 - t, y0 - t, x1 + t, y1 + t, z1, mat_ceil)
    r.box((x0 - t, y0 - t, z0, x0, y1 + t, z1), (1, 0, 0), mat_wall)    # -x
    r.box((x1, y0 - t, z0, x1 + t, y1 + t, z1), (-1, 0, 0), mat_wall)   # +x
    r.box((x0, y0 - t, z0, x1, y0, z1), (0, 1, 0), mat_wall)          # -y
    r.box((x0, y1, z0, x1, y1 + t, z1), (0, -1, 0), mat_wall)         # +y
    return 6