#!/usr/bin/env python3
"""vmfs4_to_vms.py - VMFScript 4.0 -> VMFScript 5.0 (Portal 2).

Konvertiert eine 4.0-Blockdatei in die 5.0-Syntax, damit alte Beispiele
weiterlaufen, ohne den 5.0-Compiler auf alte Formen aufweichen zu lassen.

Unterschiede, die hier ueberbrueckt werden:

  4.0                                        5.0
  ----------------------------------------   -------------------------------
  layout{ axis["x"]; passage["256"]; }       layout{ chambers="3", width=, ...
  chamber_00{ sizex=[..]; sizey=..; }         Kammern werden ZUSAMMENGEFASST:
  chamber_01{ ... }                           layout{champs=}, Entities wandern
  pos="512, 256, 64"  (Komma)                pos="512 256 64"  (Leerzeichen)
  material{ floor["..hl2.."]; }              Faellt weg: P2-Materialien
  light_01[... power=..]                      lighting{ light_01[...] }
  rotator[...] / prop[...] / button[...]      eigene Bloecke

Belege fuer die Ziel-Syntax:
  syntax/vmfscript5.0_p2_draft.txt
  examples/test_chamber_two.vms  (layout{chambers=}, pos mit Leerzeichen)
  map_ref.vmf                   (Entities, Wire-Format, Materialien)

Beispiel:
    python vmfs4_to_vms.py old.vms -o new.vms
    python vmfs4_to_vms.py old.vms --preview
"""

import argparse
import os
import re
import sys

# ---------------------------------------------------------------- 4.0 lesen
# 4.0 nutzt Komma-getrennte Positionen. Der Parser unten ist absichtlich
# einfach gehalten: 4.0 war ein Entwurf, keine verbreitete Sprache.

STRIP_COMMENTS = re.compile(r"##\*.*?\*##|##[^\n]*", re.S)
BLOCK_RE = re.compile(r"([A-Za-z_]\w*)\s*\{([^}]*)\}", re.S)
ENTRY_RE = re.compile(r"([A-Za-z_]\w*)\s*\[(.*?)\]", re.S)
ATTR_RE = re.compile(r'([A-Za-z_]\w*)\s*=\s*"([^"]*)"')


def parse40(text):
    """-> (mapname, [(blockname, [(label, [attrs])])])

    4.0 hatte ZWEI Schreibweisen fuer Werte, die beide vorkommen:

        sizex["1024"];                     reiner Listenwert
        light_01[pos="512,256,750", ...]   Attribut

    Der erste ENTRY_RE fing nur Attribute und verlor die Listenwerte -
    sizex, player, gun und wire[] waren danach leer. Deshalb wird jeder
    Entry-Text zusaetzlich auffuehrt: quoted-Bits an Position 0 gehen als
    "pos", der Rest als "_v1", "_v2" ... in die Attribute.
    """
    text = STRIP_COMMENTS.sub("", text)
    mn = re.search(r'mapname\s*=\s*"([^"]+)"', text)
    name = mn.group(1) if mn else "converted_map"
    blocks = []
    for m in BLOCK_RE.finditer(text):
        bname = m.group(1).lower()
        if bname == "world":
            continue
        entries = []
        for em in ENTRY_RE.finditer(m.group(2)):
            body = em.group(2)
            attrs = {}
            for am in ATTR_RE.finditer(body):
                attrs[am.group(1).lower()] = am.group(2)
            # 4.0 hatte zwei Schreibweisen gleichzeitig:
            #   sizex["1024"];                    -> reiner Listenwert
            #   button["btn_open", pos="x, y, z"] -> Name als Listenwert
            #   light_01[pos="x, y, z", power=..] -> alles als Attribut
            # Deshalb: das ERSTE bare "..." wird "_name", falls daneben
            # ein Attribut steht. Sonst ist es der Wert selbst.
            leftover = ATTR_RE.sub(" ", body)
            bare = re.findall(r'"([^"]*)"', leftover)
            has_attr = bool(ATTR_RE.search(body))
            if bare and has_attr:
                attrs["_name"] = bare[0]
                for i, v in enumerate(bare[1:], start=2):
                    attrs.setdefault("_v%d" % i, v)
            elif bare:
                attrs["pos"] = bare[0]
                for i, v in enumerate(bare[1:], start=2):
                    attrs.setdefault("_v%d" % i, v)
            entries.append((em.group(1), attrs))
        blocks.append((bname, entries))
    return name, blocks


def pos3(v):
    """'512, 256, 64' -> '512 256 64' (Leerzeichen, wie es die VMF will)."""
    parts = [p.strip() for p in re.split(r"[,;\s]+", v or "") if p.strip()]
    return " ".join(parts)


def num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    return ("%g" % f)


# ------------------------------------------------------------- 5.0 schreiben
class Converter:
    def __init__(self, mapname):
        self.mapname = mapname
        self.start = []
        self.lights = []
        self.doors = []
        self.buttons = []
        self.wires = []
        self.others = []      # Entities, die es in 5.0 nicht gibt
        self.props = []       # -> prop{} (prop_static / prop_dynamic)
        self.rotators = []    # -> rotator{} (func_rotating)
        self.n_chambers = 0
        self.size = {}
        self.lost = []
        self.dupfix = 0
        self._names = {}      # Label -> haeufigste Zaehlung
        self._chamber = 0     # laufender Kammer-Index

    # -- Geometrie ----------------------------------------------------
    def read_layout(self, bname, entries):
        """layout{ axis[..]; passage[..]; } -> chambers/width/length."""
        for label, a in entries:
            v = a.get("pos") or (list(a.values())[0] if a else "")
        # 4.0 legte die Masse je Kammer in chamber_XX ab, nicht im layout.
        # passage/axis steuerten nur die Anordnung und sind in 5.0 fest
        # (+Y, standardmaessig zwei Kammern). Wir zaehlen die Kammern
        # spaeter aus den chamber_XX-Bloecken.

    def read_chamber(self, entries):
        """chamber_00{ sizex=[..]; ... } -> Entities + Geometriemasse."""
        my_index = self.n_chambers
        self.n_chambers += 1
        # Groesse zuerst lesen: sie wird fuer die Kammer-Umrechnung
        # gebraucht, und die Entities stehen in der 4.0-Datei in
        # beliebiger Reihenfolge.
        for label, a in entries:
            lname = label.lower()
            if not lname.startswith("size"):
                continue
            key = {"sizex": "width", "sizey": "length",
                   "sizez": "height"}.get(lname)
            # 4.0: sizex["1024"] -> Wert steht als Listenwert in "pos"
            val = a.get("pos") or ""
            if key and key not in self.size and val:
                self.size[key] = val

        self._chamber = my_index
        for label, a in entries:
            lname = label.lower()
            if lname.startswith("size"):
                continue
            if lname in ("player", "gun", "portalgun"):
                pos = self._chamber_pos(a.get("pos", ""))
                if pos is None:
                    self.lost.append("%s: unlesbare Position %r - "
                                     "auf Kammermitte gesetzt"
                                     % (label, a.get("pos")))
                    pos = "%s %s 64" % (num(float(self.size.get("width", 512) or 512) / 2.0),
                                        num(float(self.size.get("length", 512) or 512) / 2.0))
                if lname == "player":
                    # Portalgun zuerst registrieren, damit der Spawn
                    # nogun="1" bekommt - sonst gibt es zwei Guns.
                    self._gun_pending = True
                    self.start.append('player["player", pos="%s", nogun="%s"];'
                                      % (pos, "1" if self._has_gun() else "0"))
                else:
                    self._gun = True
                    self.start.append('portalgun["portalgun", gun="1", pos="%s"];'
                                      % pos)
                continue
            if lname.startswith("light"):
                self.lights.append(self._light(label, a))
                continue
            if lname.startswith("door"):
                # 4.0: door["door_01"];  -> Listenwert ist der NAME,
                # keine Position. door["x, y, z"] waere eine Position.
                pos = self._chamber_pos(a.get("pos", ""))
                name = a.get("_name") or label
                if pos is None:
                    # Listenwert, der keine Position ist, ist der Name.
                    cand = a.get("pos", "").strip()
                    if cand and re.match(r"^[\w.\-]+$", cand):
                        name = cand
                if pos is None:
                    w = float(self.size.get("width", 512) or 512)
                    ln = float(self.size.get("length", 512) or 512)
                    pos = "%s %s 64" % (num(w / 2.0),
                                        num(ln + my_index * ln))
                    self.lost.append(
                        '%s: 4.0 gibt keine pos= fuer Tueren -> Trennwand-'
                        'Position %s gesetzt (in Hammer pruefen)' % (name, pos))
                u = self.uniq(name)
                self.doors.append('%s["%s", pos="%s", yaw="%s", '
                                  'type="prop_testchamber_door"];'
                                  % (u, u, pos, a.get("yaw", "270")))
                continue
            if lname.startswith("button") or lname.startswith("btn"):
                # 4.0: button["btn_open", pos="..."]; -> Listenwert 1 ist
                # der Name, sonst ist das Wiring unauflösbar.
                # 4.0: button["btn_open", pos="256, 128, 0"];
                # parse40 legt den Listennamen in "_name".
                pos = self._chamber_pos(a.get("pos", "")) or self._mid()
                name = a.get("_name") or label
                if not pos:
                    # Kein pos= : der Listenwert war die Position.
                    pos = self._chamber_pos(name) or self._mid()
                    name = label
                u = self.uniq(name)
                self.buttons.append('%s["%s", pos="%s", type="prop_floor_button"];'
                                    % (u, u, pos))
                continue
            if lname.startswith("prop") or lname.startswith("deko"):
                pos = self._chamber_pos(a.get("pos", "")) or self._mid()
                u = self.uniq(label)
                self.props.append('%s["%s", pos="%s", model="%s"];'
                                  % (u, u, pos, a.get("model", "")))
                continue
            if lname.startswith("rotator") or lname.startswith("spin"):
                pos = self._chamber_pos(a.get("pos", "")) or self._mid()
                u = self.uniq(label)
                self.rotators.append('%s["%s", pos="%s", speed="%s"];'
                                     % (u, u, pos, num(a.get("speed", "20"))))
                self.lost.append(
                    '%s: 4.0-rotator -> func_rotating (P2); axis/speed sind '
                    'nicht 1:1 uebertragbar, bitte in Hammer pruefen' % u)
                continue
            u = self.uniq(label)
            self.others.append('%s["%s", pos="%s"];'
                               % (u, u, self._chamber_pos(a.get("pos", ""))
                                  or self._mid()))

    def uniq(self, base):
        """Macht Labels eindeutig: light_01, light_01_02, ...

        In 4.0 hatte JEDE Kammer eigene Bloecke, aber die Labels wurden
        dort pro Kammer neu vergeben (jede Kammer hatte ihre eigene
        light_01). In 5.0 liegen alle Entities in einem Block - gleiche
        Labels wuerden sich im Compiler ueberschreiben.
        """
        if base not in self._names:
            self._names[base] = 0
            return base
        self._names[base] += 1
        self.dupfix += 1
        return "%s_%02d" % (base, self._names[base] + 1)

    def _has_gun(self):
        return getattr(self, "_gun", False)

    def _chamber_pos(self, entry):
        """Rechnet eine 4.0-Kammer-Position in 5.0-Weltkoordinaten um.

        4.0-Massen waren RELATIV zur Kammer (player["512, 256, 64"] bei
        sizex=1024 -> Mitte). 5.0 baut Kammern als Kette entlang +Y, Kammer
        i liegt bei y = origin.y + i*length. Die Position muss also um den
        Kammer-Offset verschoben werden, sonst landen alle drei Kammern
        ihre Spawns und Lichter uebereinander.
        """
        raw = [p for p in re.split(r"[,;\s]+", entry or "") if p.strip()]
        # 4.0 hatte fuer Tueren/props teils NUR einen Namen als Listenwert:
        #   door["door_01"];   -> "door_01" ist keine Position.
        # Dann liefert _chamber_pos None, und der Aufrufer nutzt den Wert
        # als Entity-Namen.
        if len(raw) < 3:
            return None
        try:
            x, y, z = (float(raw[i]) for i in range(3))
        except ValueError:
            return None
        w = float(self.size.get("width", 512) or 512)
        ln = float(self.size.get("length", 512) or 512)
        oz = float(self.size.get("height", 256) or 256) * 0
        # Kammer-Offset entlang +Y
        yy = y + self._chamber * ln
        # z ist in 4.0 ab Kammmerboden, in 5.0 ab Kammmerboden = oz(0).
        return "%s %s %s" % (num(x), num(yy), num(z + oz))

    def _mid(self):
        """Kammermitte als Rettungsposition fuer unlesbare pos=."""
        w = float(self.size.get("width", 512) or 512)
        ln = float(self.size.get("length", 512) or 512)
        return "%s %s 64" % (num(w / 2.0), num(ln / 2.0))

    def _chamber_center(self):
        w = num(self.size.get("width", 512))
        ln = num(self.size.get("length", 512))
        n = max(1, self.n_chambers)
        # Kammer 0 der Kette
        return "%s %s 0" % (w, ln, ) if False else "%s %s 64" % (w, ln)

    def _light(self, label, a):
        pos = self._chamber_pos(a.get("pos", "")) or self._mid()
        power = a.get("power", "300")
        col = a.get("color")
        if col:
            # "255, 255, 200" -> "255 255 200"
            col = " ".join(p for p in re.split(r"[,;\s]+", col) if p)
        u = self.uniq(label)
        s = '  %s["%s", pos="%s", power="%s"' % (u, u, pos, num(power))
        if col:
            s += ', color="%s"' % col
        s += "];"
        return s

    def read_wiring(self, entries):
        # 4.0-Schreibweise: wire["A.Event", "B.Meth", delay="0"];
        # delay ist ein Attribut, src/tgt stehen als Text im Entry.
        for label, a in entries:
            src = a.get("src") or a.get("from") or ""
            tgt = a.get("target") or a.get("to") or ""
            # 4.0: wire["A.Event", "B.Meth", delay="0"];
            # parse40 legt die beiden Listenwerte als "pos" (1.) und
            # "_v2" (2.) ab.
            if not src:
                src = a.get("_name") or a.get("pos", "")
            if not tgt:
                tgt = a.get("_v2", "")
            if not src or not tgt:
                # Quotes direkt aus dem Entry-Text holen.
                ps = re.findall(r'"([^"]*)"', label)
                if len(ps) >= 2:
                    src, tgt = ps[0], ps[1]
            if not src or not tgt:
                self.lost.append("wire: unlesbare Form %r - uebersprungen"
                                 % label)
                continue
            delay = a.get("delay", "0")
            param = a.get("param", "")
            # "door_01.Open" -> Ziel door_01, Input Open
            if "." in tgt:
                tgt_name, tgt_in = tgt.rsplit(".", 1)
            else:
                tgt_name, tgt_in = tgt, "Open"
            self.wires.append('  wire["%s", "%s.%s", param="%s", delay="%s"];'
                              % (src, tgt_name, tgt_in, param, num(delay)))

    # -- Ausgabe ------------------------------------------------------
    def render(self):
        out = []
        out.append("## VMFScript 5.0 - konvertiert aus 4.0")
        out.append("## Konvertiert von scripts/vmfs4_to_vms.py (Hermes).")
        out.append("## Quelle enthielt %d Kammer(n)." % self.n_chambers)
        if self.lost:
            out.append("##")
            out.append("## Achtung - nicht 1:1 uebertragbar, bitte pruefen:")
            for l in self.lost:
                out.append("##   %s" % l)
        out.append("")
        out.append('mapname = "%s";' % self.mapname)
        out.append("")

        # layout: Kammern in 5.0 sind ein Block, nicht chamber_00/01/02.
        n = self.n_chambers
        if n < 2:
            # 5.0 braucht 2 Kammern fuer ein Portal. Eine einzelne Kammer
            # ohne Durchgang wird auf 2 gesetzt, sonst bricht vvis mit EXIT 1.
            n = 2
        out.append("layout{")
        out.append('  chambers["%d", width="%s", length="%s", height="%s",'
                   % (n, num(self.size.get("width", 512)),
                      num(self.size.get("length", 512)),
                      num(self.size.get("height", 256))))
        out.append('           door_width="64", door_height="96"];')
        out.append("}")
        out.append("")

        def emit(title, lines):
            if not lines:
                return
            out.append("%s{" % title)
            out.extend(lines)
            out.append("}")
            out.append("")

        emit("start", self.start)
        emit("lighting", self.lights)
        emit("door", self.doors)
        emit("button", self.buttons)
        emit("prop", self.props)
        emit("rotator", self.rotators)
        if self.others:
            emit("props", self.others)
        emit("wiring", self.wires)
        return "\n".join(out)


def convert(text, mapname=None):
    name, blocks = parse40(text)
    c = Converter(mapname or name)
    for bname, entries in blocks:
        if bname == "layout":
            c.read_layout(bname, entries)
        elif bname == "material":
            # P1-Materialien existieren in P2 nicht. Sie werden bewusst
            # verworfen - 5.0 hat feste P2-Materialien.
            c.lost.append("material{}: P1-Materialien verworfen "
                          "(P2 hat eigene, z. B. TILE/WHITE_WALL_TILE003B)")
        elif bname == "wiring":
            c.read_wiring(entries)
        elif bname.startswith("chamber"):
            c.read_chamber(entries)
    return c.render(), c


def main():
    ap = argparse.ArgumentParser(
        description="VMFScript 4.0 -> 5.0 (Portal 2)")
    ap.add_argument("vms", help="Eingabe (.vms in 4.0-Syntax)")
    ap.add_argument("-o", "--out", help="Zieldatei (.vms in 5.0-Syntax)")
    ap.add_argument("--mapname", help="Name in der Ausgabe")
    ap.add_argument("--preview", action="store_true", help="nur auf stdout")
    args = ap.parse_args()

    if not os.path.exists(args.vms):
        raise SystemExit("Datei nicht gefunden: %s" % args.vms)
    text = open(args.vms, encoding="utf-8", errors="replace").read()
    code, c = convert(text, args.mapname)

    if args.preview or not args.out:
        sys.stdout.write(code + "\n")
    if args.out and not args.preview:
        d = os.path.dirname(os.path.abspath(args.out))
        if d:
            os.makedirs(d, exist_ok=True)
        with open(args.out, "w", newline="\n", encoding="utf-8") as f:
            f.write(code + "\n")

    sys.stderr.write("OK: %d Kammern -> chambers=%d | %d Entities, %d Wires\n"
                     % (c.n_chambers, max(2, c.n_chambers),
                        len(c.start) + len(c.lights) + len(c.doors)
                        + len(c.buttons) + len(c.props)
                        + len(c.rotators) + len(c.others), len(c.wires)))
    if c.lost:
        sys.stderr.write("Hinweise: %d\n" % len(c.lost))


if __name__ == "__main__":
    main()
