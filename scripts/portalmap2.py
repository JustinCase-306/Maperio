#!/usr/bin/env python3
"""portalmap2.py - VMFScript 2.0: Mini-Compiler fuer Portal-1-Kammern.

Erweitert um Erkenntnisse aus den 20 offiziellen Portal-1-Kammern:
  * beide Verbindungs-Trenner: ESC (Community-Maps) ODER Komma (offiziell) --comma
  * offizielle Testkammer-Materialien (plastic/concrete/metal)
  * neue Mechanik-Entities: func_portal_bumper, func_rotating, func_noportal_volume, light_spot

Nutzung:
  python portalmap2.py kammer.pml            # ESC (Standard)
  python portalmap2.py kammer.pml --comma    # Komma (wie offizielle Kammern)
  python portalmap2.py kammer.pml --compile  # + sofort vbsp

PML-Befehle (eine Zeile je Befehl, # = Kommentar):
  chamber W L H
  material SEITE MAT            # floor/ceiling/wallAB/wallCD (oder Kurzname)
  skyname NAME
  light X Y Z [R G B REICHWEITE]
  spotlight X Y Z angles P Y R cone C
  spawn X Y Z
  gun X Y Z
  button at X Y Z target NAME
  door at X Y Z target NAME
  platform at X Y Z move DX DY DZ dist D [speed S]
  bumper at X Y Z X2 Y2 Z2 [target NAME]
  rotator at X Y Z axis AX AY AZ speed S [target NAME]
  noportal at X Y Z X2 Y2 Z2 [target NAME]
  wire QUELLE.EVENT -> ZIEL.METHODE [ARG]
  prop MODELL at X Y Z [skin N]

Wire-Events: OnPressed, OnUnPressed, OnTrigger, OnStartTouch, OnPass
Methoden:   Open, Close, SetSpeed, Enable, Disable, Trigger, Kill, Start,
            SetAnimation, SetTextureIndex, PlaySound
"""

import argparse
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import generate_plain_portal_map as base

P1_BIN = r"C:\Program Files (x86)\Steam\steamapps\common\Portal\bin"
P1_GAME = r"C:\Program Files (x86)\Steam\steamapps\common\Portal\portal"

MATERIALS = {
    "floor": "concrete/concrete_modular_floor001a",
    "ceiling": "concrete/concrete_modular_ceiling001a",
    "wall": "plastic/plasticwall001b",
    "wallAB": "plastic/plasticwall001b",
    "wallCD": "plastic/plasticwall001a",
    "metal": "metal/metalwall_bts_005a",
    "panel": "plastic/plastic_light002a",
    "glass": "glass/glasswindow_refract01",
    "white": "lights/white009",
    "obsfloor": "concrete/observationwall_001a",
}


def conn_line(event, target, method, arg, comma):
    if comma:
        return '\t\t"%s" "%s,%s,%s,0,-1"\n' % (event, target, method, arg)
    return '\t\t"%s" "%s\x1b%s\x1b%s\x1b0\x1b-1"\n' % (event, target, method, arg)


class Compiler2:
    def __init__(self, comma=False):
        self.m = None
        self.comma = comma
        self.queue = []

    def _num(self, t):
        try:
            return float(t)
        except ValueError:
            raise SystemExit("erwartet Zahl, kam: %r" % t)

    # --- Befehle ---
    def cmd_chamber(self, a):
        self.m = base.Map((int(self._num(a[0])), int(self._num(a[1])), int(self._num(a[2]))))
        self.m.add_shell()

    def cmd_material(self, a):
        self._need_map()
        side, mat = a[0].lower(), a[1]
        mat = MATERIALS.get(mat, mat)
        attr = {"floor": "mat_floor", "ceiling": "mat_ceiling",
                "wallab": "mat_wallAB", "walld": "mat_wallCD",
                "wall": "mat_wallAB", "wallcd": "mat_wallCD"}.get(side)
        if attr is None:
            raise SystemExit("unbekannte SEITE: %s" % side)
        setattr(self.m, attr, mat)

    def cmd_skyname(self, a):
        self._need_map()
        self.m.skyname = a[0]

    def cmd_light(self, a):
        self._need_map()
        x, y, z = (self._num(v) for v in a[0:3])
        rgb = [int(self._num(v)) for v in a[3:6]] if len(a) >= 6 else [255, 255, 255]
        rng = int(self._num(a[6])) if len(a) >= 7 else 160
        self.m.entity("light", (x, y, z),
                      extra={"_light": "%d %d %d %d" % (*rgb, rng),
                             "_lightHDR": "-1 -1 -1 1", "_lightscaleHDR": "1",
                             "_quadratic_attn": "1"})

    def cmd_spotlight(self, a):
        self._need_map()
        x, y, z = (self._num(v) for v in a[0:3])
        angles, cone = "0 0 0", 45
        i = 3
        while i < len(a):
            if a[i] == "angles":
                angles = "%s %s %s" % (a[i+1], a[i+2], a[i+3]); i += 4
            elif a[i] == "cone":
                cone = int(self._num(a[i+1])); i += 2
            else:
                i += 1
        self.m.entity("light_spot", (x, y, z), angles=angles,
                      extra={"_light": "255 255 255 250", "_cone": str(cone),
                             "_inner_cone": str(max(cone // 3, 5)),
                             "_quadratic_attn": "1", "_exponent": "1",
                             "spawnflags": "0", "style": "0"})

    def cmd_spawn(self, a):
        self._need_map()
        self.m.entity("info_player_start", (self._num(a[0]), self._num(a[1]), self._num(a[2])))

    def cmd_gun(self, a):
        self._need_map()
        self.m.entity("weapon_portalgun", (self._num(a[0]), self._num(a[1]), self._num(a[2])),
                      extra={"spawnflags": "5", "CanFirePortal1": "1", "CanFirePortal2": "1"})

    def _at(self, a):
        if not a or a[0].lower() != "at":
            raise SystemExit("erwartet 'at X Y Z', bekam %r" % a)
        pos = (self._num(a[1]), self._num(a[2]), self._num(a[3]))
        kw = {}
        i = 4
        while i < len(a):
            k = a[i]; i += 1
            kw[k] = a[i] if i < len(a) else ""
            i += 1
        return pos, kw

    def cmd_button(self, a):
        self._need_map()
        pos, kw = self._at(a)
        extra = {"model": "models/props/portal_button.mdl"}
        if "target" in kw:
            extra["targetname"] = kw["target"]
        self.m.entity("prop_floor_button", pos, extra=extra)

    def cmd_door(self, a):
        self._need_map()
        pos, kw = self._at(a)
        angles = kw.get("angles", "0 270 0")
        target = kw.get("target", "door_%d" % self.m.eid)
        self.m.entity("prop_testchamber_door", pos, angles=angles,
                      extra={"targetname": target})

    def cmd_platform(self, a):
        self._need_map()
        pos, kw = self._at(a)
        move = kw.get("move", "0 -90 0")
        dist = int(self._num(kw.get("dist", 352)))
        speed = int(self._num(kw.get("speed", 50)))
        self.m.entity("func_movelinear", pos, angles="352 270 0",
                      extra={"movedir": move, "movedistance": str(dist),
                             "speed": str(speed), "startposition": "0",
                             "spawnflags": "0", "renderamt": "255",
                             "rendercolor": "255 255 255", "renderfx": "0",
                             "rendermode": "0", "blockdamage": "0",
                             "disablereceiveshadows": "0",
                             "targetname": "platform_01"})
        self.m.entity("prop_dynamic", pos,
                      extra={"model": "models/props/light_rail_platform.mdl",
                             "parentname": "platform_01", "MaxAnimTime": "10",
                             "MinAnimTime": "5", "skin": "0", "solid": "6",
                             "renderamt": "255", "rendercolor": "255 255 255"})

    def _volume(self, cls, pos, vol, kw):
        """Volumen-Brush-Entity (bumper/noportal) als unsichtbare Kiste."""
        from generate_plain_portal_map import P
        x1, y1, z1 = [int(self._num(v)) for v in pos[:3]]
        x2, y2, z2 = [int(self._num(v)) for v in vol]
        faces = {
            (1, 0, 0):  [(x2, y1, z1), (x2, y2, z1), (x2, y2, z2)],
            (-1, 0, 0): [(x1, y1, z1), (x1, y1, z2), (x1, y2, z2)],
            (0, 1, 0):  [(x2, y2, z1), (x1, y2, z1), (x1, y2, z2)],
            (0, -1, 0): [(x1, y1, z1), (x2, y1, z1), (x2, y1, z2)],
            (0, 0, 1):  [(x1, y1, z2), (x2, y1, z2), (x2, y2, z2)],
            (0, 0, -1): [(x1, y1, z1), (x1, y2, z1), (x2, y2, z1)],
        }
        solid = '\tsolid\n\t{\n\t\t"id" "%d"\n' % self.m.sid
        for n, pts in faces.items():
            fid = self.m.fid; self.m.fid += 1
            solid += '\t\tside\n\t\t{\n\t\t\t"id" "%d"\n' % fid
            solid += '\t\t\t"plane" "%s %s %s"\n' % (P(pts[0]), P(pts[1]), P(pts[2]))
            solid += '\t\t\t"material" "tools/toolsinvisible"\n'
            solid += '\t\t\t"uaxis" "[1 0 0 0] 0.25"\n\t\t\t"vaxis" "[0 1 0 0] 0.25"\n'
            solid += '\t\t\t"rotation" "0"\n\t\t\t"lightmapscale" "16"\n\t\t\t"smoothing_groups" "0"\n\t\t}\n'
        solid += '\t}\n'
        self.m.sid += 1
        ox, oy, oz = x1 + (x2 - x1) / 2.0, y1 + (y2 - y1) / 2.0, z1 + (z2 - z1) / 2.0
        e = 'entity\n{\n\t"id" "%d"\n' % self.m.eid
        e += '\t"classname" "%s"\n' % cls
        e += '\t"origin" "%g %g %g"\n' % (ox, oy, oz)
        if "target" in kw:
            e += '\t"targetname" "%s"\n' % kw["target"]
        e += '\t"renderamt" "255"\n\t"rendercolor" "255 255 255"\n\t"spawnflags" "0"\n'
        e += solid
        e += '\teditor\n\t{\n\t\t"color" "220 30 220"\n\t\t"visgroupshown" "1"\n\t\t"visgroupautoshown" "1"\n\t}\n}\n'
        self.m.entities.append(e)
        self.m.eid += 1

    def cmd_bumper(self, a):
        self._need_map()
        pos, kw = self._at(a)
        if len(a) < 10:
            raise SystemExit("bumper braucht: at X Y Z X2 Y2 Z2")
        self._volume("func_portal_bumper", pos, a[7:10], kw)

    def cmd_noportal(self, a):
        self._need_map()
        pos, kw = self._at(a)
        if len(a) < 10:
            raise SystemExit("noportal braucht: at X Y Z X2 Y2 Z2")
        self._volume("func_noportal_volume", pos, a[7:10], kw)

    def cmd_rotator(self, a):
        self._need_map()
        pos, kw = self._at(a)
        speed = kw.get("speed", "10")
        axis = kw.get("axis", "0 0 1")
        extra = {"axis": axis, "speed": speed, "spawnflags": "0",
                 "renderamt": "255", "rendercolor": "255 255 255"}
        if "target" in kw:
            extra["targetname"] = kw["target"]
        self.m.entity("func_rotating", pos, extra=extra)

    def cmd_wire(self, a):
        self._need_map()
        text = " ".join(a)
        m = re.match(r"^(\S+)\.(\w+)\s*->\s*(\S+)\.(\w+)(?:\s+(\S+))?$", text)
        if not m:
            raise SystemExit("wire braucht: SRC.EVENT -> TGT.METHOD [ARG]")
        self.queue.append((m.group(1), m.group(2), m.group(3), m.group(4), (m.group(5) or "")))

    def cmd_prop(self, a):
        self._need_map()
        model = a[0]
        pos, kw = self._at(a[1:])
        self.m.entity("prop_static", pos,
                      extra={"model": model, "skin": kw.get("skin", "0"),
                             "solid": "6", "renderamt": "255", "rendercolor": "255 255 255"})

    def _need_map(self):
        if self.m is None:
            raise SystemExit("Kein 'chamber' vor diesem Befehl!")

    def _apply_wires(self, content):
        for src, ev, tgt, meth, arg in self.queue:
            pat = re.compile(r'(entity\n\{\n(?:[^\n]*\n)*?\t"targetname" "%s"\n)' % re.escape(src))
            mm = pat.search(content)
            if not mm:
                raise SystemExit("wire-Ziel nicht gefunden: targetname '%s'" % src)
            chunk = mm.group(1)
            line = conn_line(ev, tgt, meth, arg, self.comma)
            if 'connections\n' in chunk:
                new = chunk.replace('connections\n\t{\n', 'connections\n\t{\n' + line)
            else:
                new = chunk.rstrip('\n') + '\n\tconnections\n\t{\n' + line + '\t}\n'
            content = content.replace(chunk, new)
        return content

    def compile_text(self, text):
        self.m = None
        self.queue = []
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            cmd, args = parts[0].lower(), parts[1:]
            handler = getattr(self, "cmd_" + cmd, None)
            if handler is None:
                raise SystemExit("Unbekannter Befehl: %s" % cmd)
            handler(args)
        if self.m is None:
            raise SystemExit("Kein 'chamber' Befehl.")
        content = "".join(self.m.render())
        content = self._apply_wires(content)
        return content


def main():
    ap = argparse.ArgumentParser(description="VMFScript 2.0 -> VMF Compiler")
    ap.add_argument("pml")
    ap.add_argument("-o", "--out")
    ap.add_argument("--comma", action="store_true",
                    help="Verbindungen mit Komma statt ESC (offizielle Kammern)")
    ap.add_argument("--compile", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.pml):
        raise SystemExit("Datei nicht gefunden: %s" % args.pml)
    out = args.out or os.path.splitext(args.pml)[0] + ".vmf"

    text = open(args.pml, encoding="utf-8").read()
    comp = Compiler2(comma=args.comma)
    content = comp.compile_text(text)
    with open(out, "w", newline="\n", encoding="utf-8") as f:
        f.write(content)
    print("OK: %s (%d bytes)" % (out, os.path.getsize(out)))
    print("Entities:", len(re.findall(r'^entity\n', content, re.M)),
          "| Solids:", content.count('\tsolid\n'),
          "| Wires:", len(comp.queue),
          "| Trenner:", "KOMMA" if args.comma else "ESC")

    if args.compile:
        vbsp = os.path.join(P1_BIN, "vbsp.exe")
        if not os.path.exists(vbsp):
            raise SystemExit("vbsp.exe fehlt: %s" % vbsp)
        subprocess.run([vbsp, "-game", P1_GAME, os.path.abspath(out)], check=False)


if __name__ == "__main__":
    main()
