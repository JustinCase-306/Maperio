#!/usr/bin/env python3
"""portalmap.py - VMFScript-Compiler fuer Portal-1-Maps (v2).

Schreibt einfachen VMFScript-Code (.pml) und uebersetzt ihn in eine fertige,
verdrahtete, kompilierbare .vmf. Im Hintergrund nutzt die bewaehrte Map-Klasse
(generate_plain_portal_map.py) fuer Innen-Winding + Solide.

Nutzung:
    python portalmap.py meine_map.pml [--compile] [--sep comma]
    --sep  Trennzeichen fuer Verbindungen: 'esc' (Standard) oder 'comma'.
           Offizielle Portal-1-Kammern nutzen oft KOMMA-Struktur, deine eigene
           Community-Map nutzte ESC. Beides wird unterstuetzt.
    --compile  Nach der Uebersetzung sofort mit vbsp kompilieren.

VMFScript v2 Befehle (eine Zeile = ein Befehl, # = Kommentar):

  # --- Huelle/Raum ---
  chamber W L H                      Raumgroesse (z.B. chamber 2048 2048 1024)
  material SEITE MAT                 floor/ceiling/wallAB/wallCD
  skyname NAME                       Himmelsname (Standard sky_black_nofog)

  # --- Grund-Logistik ---
  light X Y Z [R G B R]              Raumlicht
  spawn X Y Z                        Spieler-Spawn
  gun X Y Z                          Portal-Gun

  # --- Mechanik ---
  button at X Y Z target NAME        Bodenschalter (portal_button)
  door at X Y Z target NAME          Testkammer-Tuer
  platform at X Y Z move D move D dist D [speed S]   bewegte Plattform
  bumper at X Y Z size W H          func_portal_bumper (Portal kann nicht
                                     darauf befestigt werden - wichtige Mechanik)
  noportal at X Y Z size W H        func_noportal_volume (Volumen ohne Portale)
  rotating at X Y Z                  func_rotating (drehende Props)
  wire SRC.EVENT -> TGT.METHOD [ARG] Verbindung

  # --- Deko ---
  prop MODEL at X Y Z [skin N]       Deko-Prop (Model-Pfad)

Wire-Events: OnPressed, OnUnPressed, OnTrigger, OnStartTouch, OnFullyOpen,
  OnFullyClosed, OnStartTouchLinkedPortal, OnPass
Wire-Methoden: Open, Close, Trigger, Enable, Disable, SetSpeed, SetTextureIndex,
  Start, Stop, Kill, PlaySound, TurnOn/TurnOff

Beispiel (offizielle-Mechanik-Naehe):
  chamber 1024 1024 512
  material floor   concrete/concrete_modular_floor001a
  material ceiling concrete/concrete_modular_ceiling001a
  material wallAB  plastic/plasticwall001b
  material wallCD  plastic/plasticwall001a
  light 300 500 380 255 255 255 200
  spawn 512 512 64
  gun 560 512 64
  button at 420 700 0 target door_btn
  door at 512 990 0 target door_01
  wire door_btn.OnPressed -> door_01.Open
"""

import argparse
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from generate_plain_portal_map import Map

P1_BIN = r"C:\Program Files (x86)\Steam\steamapps\common\Portal\bin"
P1_GAME = r"C:\Program Files (x86)\Steam\steamapps\common\Portal\portal"

ESC = chr(27)  # Trennzeichen fuer das ESC-Format


def conn_line(sep, event, target, method, arg=""):
    """Erzeugt eine Hammer-Verbindungszeile im gewaehlten Format.

    sep='esc':   "OnPressed" "door_01<ESC>Open<ESC><ESC>0<ESC>-1"
    sep='comma': "OnPressed" "door_01,Open,,0,-1"
    """
    if sep == "comma":
        return '\t\t"%s" "%s,%s,%s,0,-1"\n' % (event, target, method, arg)
    return '\t\t"%s" "%s%s%s%s%s%s%s%s"\n' % (
        event, target, ESC, method, ESC, arg, ESC, "0", ESC, "-1")


def num(tok):
    try:
        return float(tok)
    except ValueError:
        raise ValueError("erwartete Zahl, bekam: %r" % tok)


class MapCompiler:
    def __init__(self, sep="esc"):
        self.m = None
        self.queue = []          # (src_targetname, event, tgt, method, arg)
        self.sep = sep

    # --- Befehle -----------------------------------------------------------
    def ensure_map(self):
        if self.m is None:
            raise SystemExit("Kein 'chamber' Befehl vor dem ersten Element!")

    def cmd_chamber(self, args):
        if len(args) != 3:
            raise SystemExit("chamber braucht W L H")
        w, l, h = (int(num(x)) for x in args)
        self.m = Map((w, l, h))
        self.m.add_shell()

    def cmd_material(self, args):
        if len(args) != 2 or self.m is None:
            raise SystemExit("material braucht SEITE MAT")
        side, mat = args[0].lower(), args[1]
        attr = {"floor": "mat_floor", "ceiling": "mat_ceiling",
                "wallab": "mat_wallAB", "walld": "mat_wallCD",
                "wall": "mat_wallAB", "wallcd": "mat_wallCD"}.get(side)
        if attr is None:
            raise SystemExit("unbekannte SEITE: %s" % side)
        setattr(self.m, attr, mat)

    def cmd_skyname(self, args):
        self.ensure_map(); self.m.skyname = args[0]

    def cmd_light(self, args):
        self.ensure_map()
        x, y, z = (num(a) for a in args[:3])
        rgb = [int(num(a)) for a in args[3:6]] if len(args) >= 6 else [255, 255, 255]
        rng = int(num(args[6])) if len(args) >= 7 else 160
        self.m.entity("light", (x, y, z), extra={
            "_light": "%d %d %d %d" % (*rgb, rng),
            "_lightHDR": "-1 -1 -1 1", "_lightscaleHDR": "1",
            "_quadratic_attn": "1"})

    def cmd_spawn(self, args):
        self.ensure_map(); x, y, z = (num(a) for a in args)
        self.m.entity("info_player_start", (x, y, z))

    def cmd_gun(self, args):
        self.ensure_map(); x, y, z = (num(a) for a in args)
        self.m.entity("weapon_portalgun", (x, y, z), extra={
            "spawnflags": "5", "fadescale": "1", "fademindist": "-1",
            "CanFirePortal1": "1", "CanFirePortal2": "1"})

    def _at(self, args):
        """Liest 'at X Y Z' + key value Paare."""
        if not args or args[0].lower() != "at":
            raise SystemExit("erwartet 'at X Y Z', bekam: %r" % args)
        pos = (num(args[1]), num(args[2]), num(args[3]))
        kw, i = {}, 4
        while i < len(args):
            k = args[i]; v = args[i + 1] if i + 1 < len(args) else ""
            kw[k] = v; i += 2
        return pos, kw

    def cmd_button(self, args):
        self.ensure_map()
        pos, kw = self._at(args)
        target = kw.get("target")
        extra = {"model": "models/props/portal_button.mdl"}
        if target:
            extra["targetname"] = target
        self.m.entity("prop_floor_button", pos, extra=extra)

    def cmd_door(self, args):
        self.ensure_map()
        pos, kw = self._at(args)
        target = kw.get("target") or "door_%d" % self.m.eid
        self.m.entity("prop_testchamber_door", pos, angles=kw.get("angles", "0 270 0"),
                      extra={"targetname": target})

    def cmd_platform(self, args):
        self.ensure_map()
        pos, kw = self._at(args)
        movedir = kw.get("move", "0 -90 0")
        dist = int(num(kw.get("dist", 352)))
        speed = int(num(kw.get("speed", 50)))
        self.m.entity("func_movelinear", pos, angles="352 270 0", extra={
            "movedir": movedir, "movedistance": str(dist), "speed": str(speed),
            "startposition": "0", "spawnflags": "0", "renderamt": "255",
            "rendercolor": "255 255 255", "renderfx": "0", "rendermode": "0",
            "blockdamage": "0", "disablereceiveshadows": "0",
            "targetname": "platform_01"})
        self.m.entity("prop_dynamic", pos, extra={
            "model": "models/props/light_rail_platform.mdl",
            "parentname": "platform_01", "MaxAnimTime": "10", "MinAnimTime": "5",
            "skin": "0", "solid": "6", "renderamt": "255",
            "rendercolor": "255 255 255"})

    def cmd_bumper(self, args):
        self.ensure_map()
        # func_portal_bumper - Portal kann nicht auf diese Flaeche; einfache Box.
        pos, kw = self._at(args)
        w = int(num(kw.get("size", kw.get("width", 64))))
        h = int(num(kw.get("height", kw.get("size", 64))))
        origin = pos
        # unsichtbarer Punkt (Event-Ort)
        self.m.entity("func_portal_bumper", origin, extra={})

    def cmd_noportal(self, args):
        self.ensure_map()
        pos, kw = self._at(args)
        self.m.entity("func_noportal_volume", pos, extra={})

    def cmd_rotating(self, args):
        self.ensure_map()
        pos, kw = self._at(args)
        self.m.entity("func_rotating", pos, extra={"spawnflags": "0"})

    def cmd_wire(self, args):
        self.ensure_map()
        text = " ".join(args)
        m = re.match(r"^(\S+)\.(\w+)\s*->\s*(\S+)\.(\w+)(?:\s+(\S+))?$", text)
        if not m:
            raise SystemExit("wire braucht: SRC.EVENT -> TGT.METHOD [ARG]")
        self.queue.append((m.group(1), m.group(2), m.group(3), m.group(4), (m.group(5) or "")))

    def cmd_prop(self, args):
        self.ensure_map()
        model = args[0]
        pos, kw = self._at(args[1:])
        skin = int(kw.get("skin", 0))
        self.m.entity("prop_static", pos, extra={
            "model": model, "skin": str(skin), "solid": "6",
            "renderamt": "255", "rendercolor": "255 255 255"})

    def _apply_wires(self, content):
        for src, event, tgt, method, arg in self.queue:
            pat = re.compile(r'(entity\n\{\n(?:[^\n]*\n)*?\t"targetname" "%s"\n)' % re.escape(src))
            mm = pat.search(content)
            if not mm:
                raise SystemExit("wire-Ziel nicht gefunden: targetname '%s'" % src)
            line = conn_line(self.sep, event, tgt, method, arg)
            chunk = mm.group(1)
            if 'connections\n' in chunk:
                new = chunk.replace('connections\n\t{\n', 'connections\n\t{\n' + line)
            else:
                new = chunk.rstrip('\n') + '\n\tconnections\n\t{\n' + line + '\t}\n'
            content = content.replace(chunk, new)
        return content

    def compile_text(self, text):
        self.m, self.queue = None, []
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            cmd, args = parts[0].lower(), parts[1:]
            handler = getattr(self, "cmd_" + cmd, None)
            if handler is None:
                raise SystemExit("Unbekannter VMFScript-Befehl: %s" % cmd)
            handler(args)
        if self.m is None:
            raise SystemExit("Kein 'chamber' Befehl gefunden.")
        return self._apply_wires("".join(self.m.render()))


def main():
    ap = argparse.ArgumentParser(description="VMFScript -> VMF Compiler fuer Portal-1")
    ap.add_argument("pml", help="VMFScript-Quelldatei (.pml)")
    ap.add_argument("-o", "--out", help="Ausgabe .vmf")
    ap.add_argument("--compile", action="store_true", help="Nach Uebersetzung mit vbsp kompilieren")
    ap.add_argument("--sep", choices=["esc", "comma"], default="esc",
                    help="Verbindungs-Trennzeichen (Standard: esc)")
    args = ap.parse_args()

    if not os.path.exists(args.pml):
        raise SystemExit("Datei nicht gefunden: %s" % args.pml)
    out = args.out or os.path.splitext(args.pml)[0] + ".vmf"
    text = open(args.pml, encoding="utf-8").read()
    comp = MapCompiler(sep=args.sep)
    content = comp.compile_text(text)
    with open(out, "w", newline="\n", encoding="utf-8") as f:
        f.write(content)
    print("OK: %s (%d bytes) sep=%s" % (out, os.path.getsize(out), args.sep))
    print("Entities:", len(re.findall(r'^entity\n', content, re.M)),
          "Solids:", content.count('\tsolid\n'), "Wires:", len(comp.queue))

    if args.compile:
        vbsp = os.path.join(P1_BIN, "vbsp.exe")
        if not os.path.exists(vbsp):
            raise SystemExit("vbsp.exe nicht gefunden: %s" % vbsp)
        subprocess.run([vbsp, "-game", P1_GAME, os.path.abspath(out)], check=False)


if __name__ == "__main__":
    main()
