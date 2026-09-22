#!/usr/bin/env python3
"""generate-plain-portal-map.py - Ein-Klick-Generator fuer eine einfache Portal-1-Map.

Erzeugt eine FERTIGE, verdrahtete, spielbare Portal-Map (.vmf) aus ein paar
Befehlszeilen-Argumenten. Nimmt dir die laestigen Dinge ab:

  * ESC-Wiring-Format (chr(27)) korrekt encoden
  * Raum-Huelle (6 Solide) mit Innen-Winding + toolsnodraw-Aussenflaechen
  * eindeutige IDs (id / solid-id / side-id)
  * sky_black_nofog statt black (kein env_cubemap noetig)
  * optionale Mechaniken: Bodenschalter->Tuer, Plattform, Anzeige-Lichter

Nutzung (Beispiele):
  python generate-plain-portal-map.py out.vmf --size 2048 2048 1024
  python generate-plain-portal-map.py out.vmf --button-door
  python generate-plain-portal-map.py out.vmf --button-door --platform --lights 3
  python generate-plain-portal-map.py out.vmf --help

Tipp: Angaben sind in Hammer-Einheiten (1 tile = 64). Standard-Raum 2048x2048x1024
= 32x32 Tiles, 16 hoch - grosszuegig. Verkleinern fuer schnelle Tests (z.B. 1024 1024 512).
"""

import argparse
import os
import sys

# --------------------------------------------------------------------------
# PWM = die 5-Feld-Verbindung. Alles wird automatisch mit chr(27)=ESC verbunden.
ESC = chr(27)  # 0x1b, das Tremzeichen in Hammer-Verbindungen


def conn(event, target, method, arg=""):
    # Echte ESC-Zeichen (0x1b) konkatenieren - NICHT "\x1b" als Text schreiben!
    return '\t"{e}" "{t}{e1}{m}{e2}{a}{e3}0{e4}-1"\n'.format(
        e=event, t=target, m=method, a=arg,
        e1=ESC, e2=ESC, e3=ESC, e4=ESC)


def wconn(event, target, method, arg=""):
    return '\t\t"%s" "%s%s%s%s%s%s%s%s" \n' % (
        event, target, ESC, method, ESC, arg, ESC, "0", ESC, "-1")


class Map:
    def __init__(self, size, skyname="sky_black_nofog"):
        self.size = size
        self.skyname = skyname
        self.sid = 100       # solid ids
        self.fid = 1000      # face ids
        self.eid = 1000      # entity ids
        self.world = []
        self.entities = []
        # Materialversehen je Flaeche - per 'material' im PML ueberschreibbar
        self.mat_floor    = "concrete/concrete_modular_floor001a"
        self.mat_ceiling  = "concrete/concrete_modular_ceiling001a"
        self.mat_wallAB   = "plastic/plasticwall001b"   # +x und -x Wände
        self.mat_wallCD   = "plastic/plasticwall001a"   # +y und -y Wände

    # spatial helpers -------------------------------------------------------
    def W(self):
        return self.size[0]

    def L(self):
        return self.size[1]

    def H(self):
        return self.size[2]

    def P(self, p):
        return "(%g %g %g)" % tuple(float(v) for v in p)

    def tex(self, n):
        if abs(n[0]) == 1:
            return "[0 0 1 0]", "[0 1 0 0]"
        if abs(n[1]) == 1:
            return "[1 0 0 0]", "[0 0 -1 0]"
        return "[1 0 0 0]", "[0 1 0 0]"

    # solids ---------------------------------------------------------------
    def add_shell(self):
        W, L, H = self.size
        Th = 64  # Wand-/Boden-/Deckendicke

        # bbox (x1,y1,z1,x2,y2,z2), sichtbare Normale, sichtbares Material
        specs = [
            ((0, 0, -Th, W, L, 0),       (0, 0, 1),  self.mat_floor),
            ((0, 0, H, W, L, H + Th),     (0, 0, -1), self.mat_ceiling),
            ((-Th, 0, 0, 0, L, H),        (1, 0, 0),  self.mat_wallAB),
            ((W, 0, 0, W + Th, L, H),     (-1, 0, 0), self.mat_wallAB),
            ((0, -Th, 0, W, 0, H),        (0, 1, 0),  self.mat_wallCD),
            ((0, L, 0, W, L + Th, H),     (0, -1, 0), self.mat_wallCD),
        ]
        for bbox, vis_n, vis_m in specs:
            self.add_box_solid(bbox, vis_n, vis_m)

    def add_box_solid(self, bbox, vis_n, vis_m):
        # Innen-Winding: fuer jede Seite wird die Normale (Kreuzprodukt der
        # ersten 2 Kanten) gegen das Solid-Zentrum geprueft und die Punktfolge
        # geflippt, falls sie nach aussen zeigt. Ohne das verwirft vbsp die
        # Seite ("no visible sides on brush") - gleiche Logik wie build3.py.
        x1, y1, z1, x2, y2, z2 = bbox
        center = ((x1 + x2) / 2.0, (y1 + y2) / 2.0, (z1 + z2) / 2.0)
        base = {
            (1, 0, 0):  [(x2, y1, z1), (x2, y2, z1), (x2, y2, z2)],
            (-1, 0, 0): [(x1, y1, z1), (x1, y1, z2), (x1, y2, z2)],
            (0, 1, 0):  [(x2, y2, z1), (x1, y2, z1), (x1, y2, z2)],
            (0, -1, 0): [(x1, y1, z1), (x2, y1, z1), (x2, y1, z2)],
            (0, 0, 1):  [(x1, y1, z2), (x2, y1, z2), (x2, y2, z2)],
            (0, 0, -1): [(x1, y1, z1), (x1, y2, z1), (x2, y2, z1)],
        }
        # Kreuzprodukt
        def cross(pts):
            a, b, cc = pts
            u = (b[0]-a[0], b[1]-a[1], b[2]-a[2])
            v = (cc[0]-a[0], cc[1]-a[1], cc[2]-a[2])
            return (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
        faces = []
        for n, pts in base.items():
            pts = list(pts)
            cr = cross(pts)
            toC = tuple(center[i] - pts[0][i] for i in range(3))
            dot = cr[0]*toC[0] + cr[1]*toC[1] + cr[2]*toC[2]
            if dot <= 0:  # zeigt nach aussen -> Punktfolge umdrehen
                pts = [pts[0], pts[2], pts[1]]
            faces.append((n, pts))
        solid_id = self.sid; self.sid += 1
        s = '\tsolid\n\t{\n\t\t"id" "%d"\n' % solid_id
        for n, pts in faces:
            mat = vis_m if n == vis_n else "tools/toolsnodraw"
            ua, va = self.tex(n)
            fid = self.fid; self.fid += 1
            s += '\t\tside\n\t\t{\n'
            s += '\t\t\t"id" "%d"\n' % fid
            s += '\t\t\t"plane" "%s %s %s"\n' % (self.P(pts[0]), self.P(pts[1]), self.P(pts[2]))
            s += '\t\t\t"material" "%s"\n' % mat
            s += '\t\t\t"uaxis" "%s 0.5"\n' % ua
            s += '\t\t\t"vaxis" "%s 0.5"\n' % va
            s += '\t\t\t"rotation" "0"\n'
            s += '\t\t\t"lightmapscale" "16"\n'
            s += '\t\t\t"smoothing_groups" "0"\n'
            s += '\t\t}\n'
        s += '\t}\n'
        self.world.append(s)
        return solid_id

    def entity(self, cls, origin, angles="0 0 0", extra=None, connections=None):
            eid = self.eid; self.eid += 1
            s = 'entity\n{\n\t"id" "%d"\n' % eid
            if cls:
                s += '\t"classname" "%s"\n' % cls
            s += '\t"origin" "%g %g %g"\n' % tuple(float(v) for v in origin)
            s += '\t"angles" "%s"\n' % angles
            for k, v in (extra or {}).items():
                if k in ("origin", "angles", "classname", "id"):
                    continue
                s += '\t"%s" "%s"\n' % (k, v)
            if connections:
                s += '\tconnections\n\t{\n'
                for trig, tgt, method, arg in connections:
                    s += conn(trig, tgt, method, arg)
                s += '\t}\n'
            s += '\teditor\n\t{\n\t\t"color" "220 30 220"\n\t\t"visgroupshown" "1"\n\t\t"visgroupautoshown" "1"\n\t}\n'
            s += '}\n'
            self.entities.append(s)
            return eid

    # hochstufige Mechaniken ------------------------------------------------
    def add_player_gun(self):
        cx, cy = self.W() // 2, self.L() // 2
        self.entity("info_player_start", (cx, cy, 64))
        self.entity("weapon_portalgun", (cx + 64, cy, 64),
                    extra={"spawnflags": "5", "fadescale": "1", "fademindist": "-1",
                           "CanFirePortal1": "1", "CanFirePortal2": "1"})

    def add_lights(self, n=2, bright=False):
        W, L, H = self.size
        for i in range(n):
            x = W * (i + 1) // (n + 1)
            y = L // 2
            rng = 300 if bright else 160
            self.entity("light", (x, y, int(H * 0.8)),
                        extra={"_light": "255 255 255 %d" % rng,
                               "_lightHDR": "-1 -1 -1 1", "_lightscaleHDR": "1",
                               "_quadratic_attn": "1"})

    def add_button_door(self, door_pos=None):
        """Bodenschalter -> Tuer. Legt eine Testkammer-Tuer + Schalter an und
        verdrahtet sie: Druck = Oeffnen. (Relay/Anzeige optional spaeter.)"""
        W, L = self.W(), self.L()
        if door_pos is None:
            door_pos = (W // 2, L - 128)
        self.entity("prop_testchamber_door", (door_pos[0], door_pos[1], 0),
                    angles="0 270 0", extra={"targetname": "door_01"})
        # Schalter auf Boden, mittig, nah vor der Tuer
        bx, by = door_pos[0], door_pos[1] - 200
        self.entity("prop_floor_button", (bx, by, 0),
                    extra={"targetname": "door_button_01",
                           "model": "models/props/portal_button.mdl"},
                    connections=[("OnPressed", "door_01", "Open", "")])
    def add_platform(self, move="0 -90 0", dist=352, speed=50):
        """Bewegte Plattform (func_movelinear): schickt eine Plattform gerade
        auf und ab. Die Plattform selbst ist ein prop_dynamic, der als Kind
        ('parentname') der func_movelinear haengt - so bewegt sich die sichtbare
        Plattform mit dem unsichtbaren Fahrer. Aufruf: --platform"""
        W, L = self.W(), self.L()
        cx, cy = W // 2, L // 2
        # unsichtbarer 'Fahrer' - bewegt entlang move
        self.entity("func_movelinear", (cx - 128, cy, 248),
                    angles="352 270 0",
                    extra={"movedir": move, "movedistance": str(dist),
                           "speed": str(speed), "startposition": "0",
                           "spawnflags": "0", "renderamt": "255",
                           "rendercolor": "255 255 255", "renderfx": "0",
                           "rendermode": "0", "blockdamage": "0",
                           "disablereceiveshadows": "0",
                           "targetname": "platform_01"})
        # sichtbare Plattform haengt am Fahrer
        self.entity("prop_dynamic", (cx - 128, cy, 216),
                    extra={"model": "models/props/light_rail_platform.mdl",
                           "parentname": "platform_01",
                           "MaxAnimTime": "10", "MinAnimTime": "5",
                           "skin": "0", "solid": "6", "renderamt": "255",
                           "rendercolor": "255 255 255"})


    def render(self):
        out = []
        out.append('versioninfo\n{\n\t"editorversion" "400"\n\t"editorbuild" "8870"\n'
                   '\t"mapversion" "1"\n\t"formatversion" "100"\n\t"prefab" "0"\n}')
        out.append('visgroups\n{\n}')
        out.append('viewsettings\n{\n\t"bSnapToGrid" "1"\n\t"bShowGrid" "1"\n'
                   '\t"bShowLogicalGrid" "0"\n\t"nGridSpacing" "64"\n\t"bShow3DGrid" "0"\n}')
        out.append('world\n{')
        out.append('\t"id" "1"\n\t"mapversion" "1"\n\t"classname" "worldspawn"')
        out.append('\t"skyname" "%s"' % self.skyname)
        out.append('\t"maxpropscreenwidth" "-1"\n\t"detailvbsp" "detail.vbsp"\n'
                   '\t"detailmaterial" "detail/detailsprites"')
        out.extend(self.world)
        out.append('}')
        out.extend(self.entities)
        return "".join(out)


def main():
    ap = argparse.ArgumentParser(description="Einfache Portal-1-Map generieren.")
    ap.add_argument("out", help="Zieldatei, z.B. meine_map.vmf")
    ap.add_argument("--size", nargs=3, type=int, default=[2048, 2048, 1024],
                    metavar=("W", "L", "H"), help="Raumgroesse (Standard 2048 2048 1024)")
    ap.add_argument("--skyname", default="sky_black_nofog")
    ap.add_argument("--lights", type=int, default=2, help="Anzahl Lichter (Standard 2)")
    ap.add_argument("--bright", action="store_true", help="Helle Lichter (Reichweite 300)")
    ap.add_argument("--button-door", action="store_true", help="Bodenschalter->Tuer Mechanik")
    ap.add_argument("--platform", action="store_true", help="Bewegte Plattform (func_movelinear)")
    ap.add_argument("--no-gun", action="store_true", help="Keine Portal-Gun/start (nur Koerper)")
    args = ap.parse_args()

    m = Map(args.size, args.skyname)
    m.add_shell()
    if not args.no_gun:
        m.add_player_gun()
    m.add_lights(args.lights, args.bright)
    if args.button_door:
        m.add_button_door()
    if args.platform:
        m.add_platform()

    content = m.render()
    with open(args.out, "w", newline="\n", encoding="utf-8") as f:
        f.write(content)
    print("OK: %s (%d bytes)" % (args.out, os.path.getsize(args.out)))
    print("Entities:", m.eid - 1000, "| Solids:", m.sid - 100)
    print("Kompilieren: vbsp.exe -game <Portal\\portal> %s" % args.out)


if __name__ == "__main__":
    main()