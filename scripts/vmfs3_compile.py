#!/usr/bin/env python3
"""vmfs3_compile.py - VMFScript 3.0 -> VMF Compiler (Portal 1).

Uebersetzt die Block-Syntax aus vmfscript3.0.txt EINS-ZU-EINS in eine
fertige Portal-1-.vmf (Spawn, Portal-Gun, Licht, Knopf->Tuer, wiring).

Verbindliche Syntax (aus vmfscript3.0.txt):
    mapname="name";
    material { floor["mat"]; ceiling["mat"]; wall["mat"]; };
    chamber  { sizex["1024"]; sizey["512"]; sizez["1024"];
               player["512, 512, 64"]; gun["560, 512, 64"]; };
    lighting { light_01[pos="300, 500, 380", power="255", color="255, 255, 200"]; };
    buttons  { door_btn[pos="420, 700, 0"]; };
    doors    { door_01[pos="512, 990, 0"]; };
    wiring   { wire["door_btn.OnPressed", "door_01.Open", delay="2"]; };
Kommentare:  ## bis Zeilenende (kurz),  ##* ... *##  (lang, mehrzeilig)

Nutzung:
    python vmfs3_compile.py kammer.vms            # -> kammer.vmf
    python vmfs3_compile.py kammer.vms -o aus.vmf
    python vmfs3_compile.py kammer.vms --compile  # + Portal-1-vbsp

Hinweis delay: landet im Argument-Feld der 5-Feld-ESC-Verbindung
(target\\x1bMethode\\x1bARG\\x1b0\\x1b-1). Bitte in Hammer pruefen, falls eine
echte Puzzle-Verzoegerung gewuenscht ist (nicht alle Tuer-Methoden nehmen das).
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

# --------------------------------------------------------------------------
# Text-Vorbereitung: Kommentare entfernen
def strip_comments(text):
    """Entfernt ##* ... *## (mehrzeilig) und ## ... (bis Zeilenende)."""
    text = re.sub(r"##\*.*?\*##", "", text, flags=re.S)
    out = []
    for ln in text.splitlines():
        i = ln.find("##")
        if i >= 0:
            ln = ln[:i]
        out.append(ln)
    return "\n".join(out)


def split_outside(text, sep=","):
    """Teilt an sep, aber NICHT innerhalb von Anfuehrungszeichen."""
    parts, cur, inq = [], [], False
    for ch in text:
        if ch == '"':
            inq = not inq
        if ch == sep and not inq:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur).strip())
    return [p for p in parts if p]


# --------------------------------------------------------------------------
# Block-Tokenizer
BLOCK_RE = re.compile(r"(?ms)^\s*([A-Za-z_]\w*)\s*\{(.*?)\}\s*;")
NAME_RE = re.compile(r'(?ms)^\s*mapname\s*=\s*"([^"]*)"\s*;')


def parse_entries(block_body):
    """Zerlegt den Inhalt eines Blocks in Eintraege.

    Liefert Liste von Dicts:
      {"label": str, "pos": str|None, "positives": [str,...],
       "attrs": {key: val}, "placeholder": bool}
    Ein Eintrag ist 'label[...];'. Beispiel:
      light_01[pos="300, 500, 380", power="255", color="255, 255, 200"];
      floor["concrete/..."];
      light_floor_03[..];        # '..' = Platzhalter (Defaults)
    """
    entries = []
    for raw in block_body.split(";"):
        raw = raw.strip()
        if not raw:
            continue
        m = re.match(r"^([A-Za-z_]\w*)\s*\[(.*)\]\s*$", raw, flags=re.S)
        if not m:
            raise SystemExit("Unbekannte Zeile im Block: %r" % raw)
        label, inside = m.group(1), m.group(2).strip()
        ent = {"label": label, "pos": None, "positives": [],
               "attrs": {}, "placeholder": inside in ("", "..")}
        if ent["placeholder"]:
            entries.append(ent)
            continue
        for tok in split_outside(inside):
            km = re.match(r'^(\w+)\s*=\s*"([^"]*)"$', tok)
            if km:
                ent["attrs"][km.group(1)] = km.group(2)
            else:
                vm = re.match(r'^"([^"]*)"$', tok)
                if vm:
                    ent["positives"].append(vm.group(1))
                    if ent["pos"] is None:
                        ent["pos"] = vm.group(1)
                else:
                    raise SystemExit("Unlesbarer Eintrag in %r" % raw)
        entries.append(ent)
    return entries


def parse_blocks(text):
    """Liefert (mapname, {blockname: [entries]})."""
    text = strip_comments(text)
    mn = NAME_RE.search(text)
    name = mn.group(1) if mn else "vmfs3_map"
    blocks = {}
    for m in BLOCK_RE.finditer(text):
        blocks.setdefault(m.group(1).lower(), []).extend(parse_entries(m.group(2)))
    return name, blocks

# ================= VMFS3-COMPILER =================

def _vec(v):
    return tuple(float(x.strip()) for x in v.split(","))


class Compiler3:
    """Uebersetzt geparste VMFScript-3.0-Bloecke in eine Map + VMF."""

    def __init__(self, name="vmfs3_map"):
        self.name = name
        self.m = None
        self.wires = []
        self.player = None
        self.gun = None

    # --- Einstieg ---
    def compile_blocks(self, blocks):
        # 1) chamber: erst alle Groessen sammeln, dann Map bauen
        size = [1024, 512, 1024]
        player = gun = None
        for e in blocks.get("chamber", []):
            l = e["label"].lower()
            if l == "sizex":
                size[0] = int(float(e["pos"]))
            elif l == "sizey":
                size[1] = int(float(e["pos"]))
            elif l == "sizez":
                size[2] = int(float(e["pos"]))
            elif l == "player":
                player = _vec(e["pos"])
            elif l == "gun":
                gun = _vec(e["pos"])
        self.m = base.Map(tuple(size))
        self.m.add_shell()
        self.player = player or (size[0] // 2, size[1] // 2, 64)
        self.gun = gun or (self.player[0] + 64, self.player[1], 64)
        self.m.entity("info_player_start", self.player)
        self.m.entity("weapon_portalgun", self.gun,
                      extra={"spawnflags": "5", "CanFirePortal1": "1",
                             "CanFirePortal2": "1"})

        # 2) restliche Bloecke (Reihenfolge egal, wiring am Ende)
        for key in ("material", "lighting", "buttons", "doors", "wiring"):
            for e in blocks.get(key, []):
                getattr(self, "blk_" + key)(e)

    def _need_map(self):
        if self.m is None:
            raise SystemExit("Kein 'chamber'-Block.")

    # --- Block-Handler ---
    def blk_material(self, e):
        self._need_map()
        mat = e["pos"]
        lbl = e["label"].lower()
        if lbl == "floor":
            self.m.mat_floor = mat
        elif lbl == "ceiling":
            self.m.mat_ceiling = mat
        elif lbl == "wall":
            self.m.mat_wallAB = self.m.mat_wallCD = mat
        else:
            raise SystemExit("material-Typ unbekannt: %s" % e["label"])

    def blk_lighting(self, e):
        self._need_map()
        attrs = e["attrs"]
        pos = e["pos"] or attrs.get("pos")
        if pos:
            x, y, z = _vec(pos)
        else:  # Standard: Raummitte auf ~80% Hoehe (falls [..])
            W, L, H = self.m.size
            x, y, z = W / 2, L / 2, int(H * 0.8)
        rng = int(float(attrs.get("power", "160")))
        cold = attrs.get("color")
        r = g = b = 255
        if cold:
            r, g, b = (int(float(v)) for v in cold.split(","))
        self.m.entity("light", (x, y, z),
                      extra={"_light": "%d %d %d %d" % (r, g, b, rng),
                             "_lightHDR": "-1 -1 -1 1", "_lightscaleHDR": "1",
                             "_quadratic_attn": "1"})

    def blk_buttons(self, e):
        self._need_map()
        pos = e["pos"] or e["attrs"].get("pos")
        if not pos:
            raise SystemExit("button %s braucht pos" % e["label"])
        self.m.entity("prop_floor_button", _vec(pos),
                      extra={"model": "models/props/portal_button.mdl",
                             "targetname": e["label"]})

    def blk_doors(self, e):
        self._need_map()
        pos = e["pos"] or e["attrs"].get("pos")
        if not pos:
            raise SystemExit("door %s braucht pos" % e["label"])
        angles = e["attrs"].get("angles", "0 270 0")
        self.m.entity("prop_testchamber_door", _vec(pos), angles=angles,
                      extra={"targetname": e["label"]})

    def blk_wiring(self, e):
        self._need_map()
        ps = e["positives"]
        if not ps:
            raise SystemExit("wire braucht 'QUELLE.EV', 'ZIEL.METHODE'")
        src = ps[0]
        tgt = ps[1] if len(ps) > 1 else e["attrs"].get("target")
        delay = e["attrs"].get("delay", "")
        if "." not in src or "." not in (tgt or ""):
            raise SystemExit("wire falsch: 'SRC.EV' -> 'TGT.METH': %r %r" % (src, tgt))
        src_lbl, ev = src.rsplit(".", 1)
        tgt_lbl, meth = tgt.rsplit(".", 1)
        self.wires.append((src_lbl, ev, tgt_lbl, meth, delay))

    # --- Wire-Injektion + Render ---
    def _apply_wires(self, content):
        for src_lbl, ev, tgt_lbl, meth, delay in self.wires:
            pat = re.compile(r'(entity\n\{\n(?:[^\n]*\n)*?\t"targetname" "%s"\n)'
                             % re.escape(src_lbl))
            mm = pat.search(content)
            if not mm:
                raise SystemExit("wire-Quelle nicht gefunden: targetname '%s'"
                                 % src_lbl)
            chunk = mm.group(1)
            line = '\t\t"%s" "%s\x1b%s\x1b%s\x1b0\x1b-1"\n' % (ev, tgt_lbl, meth, delay)
            if "connections\n" in chunk:
                new = chunk.replace("connections\n\t{\n", "connections\n\t{\n" + line)
            else:
                new = chunk.rstrip("\n") + "\n\tconnections\n\t{\n" + line + "\t}\n"
            content = content.replace(chunk, new)
        return content

    def render(self):
        self._need_map()
        content = "".join(self.m.render())
        return self._apply_wires(content)


def main():
    ap = argparse.ArgumentParser(description="VMFScript 3.0 -> VMF Compiler (Portal 1)")
    ap.add_argument("vms", help=".vms-Datei im VMFScript-3.0-Format")
    ap.add_argument("-o", "--out", help="Zieldatei (Standard: mapname.vmf)")
    ap.add_argument("--compile", action="store_true",
                    help="+ Portal-1-vbsp aufrufen (NICHT Portal 2!)")
    args = ap.parse_args()

    if not os.path.exists(args.vms):
        raise SystemExit("Datei nicht gefunden: %s" % args.vms)
    text = open(args.vms, encoding="utf-8").read()
    name, blocks = parse_blocks(text)
    comp = Compiler3(name)
    comp.compile_blocks(blocks)
    content = comp.render()

    out = args.out or (name + ".vmf")
    with open(out, "w", newline="\n", encoding="utf-8") as f:
        f.write(content)
    print("OK: %s (%d bytes)" % (out, os.path.getsize(out)))
    print("Solids:", content.count("\tsolid\n"),
          "| Entities:", content.count("entity\n{"),
          "| Wires:", len(comp.wires))

    if args.compile:
        vbsp = os.path.join(P1_BIN, "vbsp.exe")
        if not os.path.exists(vbsp):
            raise SystemExit("vbsp.exe fehlt: %s" % vbsp)
        subprocess.run([vbsp, "-game", P1_GAME, os.path.abspath(out)], check=False)


if __name__ == "__main__":
    main()