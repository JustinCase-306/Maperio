#!/usr/bin/env python3
"""vmfs5_compile.py - VMFScript 5.0 -> VMF Compiler (Portal 2).

Entwirft Entities fuer die Portal-2-Engine. Entities-only: die Sprache
setzt Spielobjekte auf eine Geometrie, die im Hammer gebaut wurde.

Warum P2 und nicht P1: P1 ist Half-Life-2-basiert, dort ist ein Button ein
Entity-Zoo (prop_static + prop_dynamic + trigger_ + logic_ + Licht + Sound).
P2 hat echte Entities mit fertigen Inputs:

    "OnPressed" "door1\\x1bOpen\\x1b\\x1b0.5\\x1b-1"

Verbindliche Syntax (syntax/vmfscript5.0_p2_draft.txt):
    mapname = "test_door";
    start   { player["Start"; pos="-95 -320 65"; yaw="90";] }
    button  { btn["Druecke mich"; pos="-228 -340 72"; type="prop_floor_button";] }
    door    { door1["Testkammertuer"; pos="0 2 -64"; yaw="270";] }
    lighting{ light_01[pos="0 0 96"; power="350";] }
    wiring  { wire["btn.OnPressed", "door1.Open", delay="0.5"]; }

Kommentare:  ## bis Zeilenende (kurz),  ##* ... *##  (lang, mehrzeilig)

Nutzung:
    python vmfs5_compile.py map.vms                 # -> map.vmf
    python vmfs5_compile.py map.vms --compile       # + vbsp/vvis/vrad
    python vmfs5_compile.py map.vms --testroom      # + minimale Testkammer

Wichtig: --compile legt die VMF im Portal-2-maps-Ordner ab und laeuft von
dort. Ausserhalb bricht vbsp mit "Can't create LogFile" und EXIT 1 ab.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import generate_plain_portal_map as base
import vmfs_geometry as G

ESC = chr(27)
P2_BIN = r"C:\Program Files (x86)\Steam\steamapps\common\Portal 2\bin"
P2_GAME = r"C:\Program Files (x86)\Steam\steamapps\common\Portal 2\portal2"
P2_MAPS = os.path.join(P2_GAME, "maps")

# --------------------------------------------------------------------------
# Parser (Rahmen unveraendert gegenueber 3.0)
# --------------------------------------------------------------------------
def strip_comments(text):
    text = re.sub(r"##\*.*?\*##", "", text, flags=re.S)
    out = []
    for ln in text.splitlines():
        i = ln.find("##")
        if i >= 0:
            ln = ln[:i]
        out.append(ln)
    return "\n".join(out)


def split_outside(text, sep=","):
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


BLOCK_RE = re.compile(r"(?ms)^\s*([A-Za-z_]\w*)\s*\{(.*?)\}\s*;?")
NAME_RE = re.compile(r'(?ms)^\s*mapname\s*=\s*"([^"]*)"\s*;')


def split_entries(body):
    """Teilt einen Block-Inhalt an ';', aber NICHT innerhalb von [ ] oder " "."""
    parts, cur, depth, inq = [], [], 0, False
    for ch in body:
        if ch == '"':
            inq = not inq
        if not inq:
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
        if ch == ";" and not inq and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def parse_entries(body):
    entries = []
    for raw in split_entries(body):
        raw = raw.strip()
        if not raw:
            continue
        m = re.match(r"^([A-Za-z_]\w*)\s*\[(.*)\]\s*$", raw, flags=re.S)
        if not m:
            raise SystemExit("Unbekannte Zeile im Block: %r" % raw)
        label, inside = m.group(1), m.group(2).strip()
        ent = {"label": label, "attrs": {}, "positives": [], "text": None}
        if inside in ("", ".."):
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
                    if ent["text"] is None:
                        ent["text"] = vm.group(1)
                else:
                    raise SystemExit("Unlesbarer Eintrag in %r" % raw)
        entries.append(ent)
    return entries


def looks_like_vms(text):
    """Prueft, ob der Text wirklich VMFScript ist (und nicht VMF/HTML/Random).

    Eine VMF enthaelt top-level-Bloecke wie versioninfo{, world{, entity{,
    solid{ und Zeilen der Form "key" "value". VMFScript hat mapname = "..."
    und Bloecke mit label[...];-Eintraegen. Der Test faellt bewusst streng aus.
    """
    head = text[:4000]
    if '"classname"' in head or '"editorversion"' in head:
        return False
    if not re.search(r'(?m)^\s*mapname\s*=\s*"[^"]*"\s*;', head):
        return False
    return bool(re.search(r'(?m)^\s*[A-Za-z_]\w*\s*\{', head))


def parse_blocks(text):
    """Zerlegt VMFScript in Bloecke.

    Erkennt zusaetzlich VMF-/Fremd-Inhalt und bricht mit einer klaren
    Meldung ab, statt kryptische Parser-Fehler zu werfen.
    """
    if not looks_like_vms(text):
            head = text.lstrip()[:200].replace("\n", " ")
            raise SystemExit(
                "Das sieht nicht nach VMFScript aus.\n\n"
                "Erwartet wird eine Datei mit 'mapname = \"...\";' und Bloecken "
                "wie 'door{ ... }'.\n\n"
                "Gefunden am Anfang: " + head + "\n\n"
                "Tipp: Mit 'VMF -> VMFScript' eine VMF zuerst uebersetzen.")
    text = strip_comments(text)
    mn = NAME_RE.search(text)
    name = mn.group(1) if mn else "vmfs5_map"
    blocks = {}
    for m in BLOCK_RE.finditer(text):
        blocks.setdefault(m.group(1).lower(), []).extend(parse_entries(m.group(2)))
    return name, blocks


# --------------------------------------------------------------------------
# Entity-Vorlagen (belegt an map_ref.vmf / door_ref_01.vmf)
# --------------------------------------------------------------------------
BUTTON_TYPES = ("prop_floor_button", "prop_button", "func_button")
DOOR_TYPES = ("prop_testchamber_door", "prop_dynamic", "func_door")
TURRET_TYPES = ("npc_portal_turret_floor", "npc_portal_turret_panelled")

DOOR_MODEL = "models/props_underground/underground_door_dynamic.mdl"
BUTTON_MODEL = "models/props/portal_button.mdl"


def _vec(v):
    return tuple(float(x) for x in re.split(r"[,\s]+", v.strip()) if x)


def _angles(attrs):
    if "angles" in attrs:
        return attrs["angles"]
    yaw = attrs.get("yaw", attrs.get("yawpitchroll", "0"))
    pitch = attrs.get("pitch", "0")
    return "%s %s 0" % (pitch, yaw)


def _add_testroom_shell(m, mat="TILE/WHITE_WALL_TILE003B", pad=64,
                        size=None, origin=None):
    """Geschlossene Raum-Huelle mit duennen Wänden (Th=8).

    Dünn ist Pflicht: bei 64er Wandstärke meldet vbsp "FindPortalSide:
    Couldn't find a good match for which brush to assign to a portal" und vvis
    bricht mit EXIT 1 ab. Eine einzelne Bodenfläche reicht auch nicht - ohne
    Wände gibt es keine Portale ("LoadPortals: couldn't read .prt").

    Ohne size/origin wird die Huelle aus m.ents abgeleitet, damit sie die
    Szene umschliesst - Entities ausserhalb der Box erzeugen sonst genau
    die FindPortalSide-Fehler.
    """
    if size is None or origin is None:
        ents = getattr(m, "ents", None)
        if ents:
            origin, size = _bounds_of(ents, pad)
        else:
            origin, size = (0, 0, 0), (512, 512, 256)
    x0, y0, z0 = origin
    W, L, H = size
    m.size = (W, L, H)
    Th = 8
    x1, y1, z1 = x0 + W, y0 + L, z0 + H
    specs = [
        ((x0, y0, z0 - Th, x1, y1, z0),      (0, 0, 1),  mat),   # Boden
        ((x0, y0, z1, x1, y1, z1 + Th),      (0, 0, -1), mat),   # Decke
        ((x0 - Th, y0, z0, x0, y1, z1),      (1, 0, 0),  mat),   # -x
        ((x1, y0, z0, x1 + Th, y1, z1),      (-1, 0, 0), mat),   # +x
        ((x0, y0 - Th, z0, x1, y0, z1),      (0, 1, 0),  mat),   # -y
        ((x0, y1, z0, x1, y1 + Th, z1),      (0, -1, 0), mat),   # +y
    ]
    for bbox, vis_n, vis_m in specs:
        m.add_box_solid(bbox, vis_n, vis_m)


def _bounds_of(ents, pad=64):
    """Kleinste Box, die alle Entities umschliesst.

    ALLE Entities zaehlen - auch Lichter. Ein `light` ausserhalb der Box
    erzeugt "Entity light (...) leaked!" und vbsp schreibt dann keine .prt,
    woran vvis mit EXIT 1 scheitert. light_environment wird mitgerechnet,
    weil es in importierten Maps ueber der Szene sitzt.

    Rueckgabe: (ursprung, (W, L, H)) - der Ursprung ist noetig, weil
    importierte Maps negative Koordinaten haben (map_ref.vmf: x bis -512).
    """
    if not ents:
        return (0, 0, 0), (512, 512, 256)
    xs = [e["origin"][0] for e in ents]
    ys = [e["origin"][1] for e in ents]
    zs = [e["origin"][2] for e in ents]
    # Das Padding muss nach ALLEN Seiten wirken, nicht nur unten/links:
    # eine Entity exakt auf der Innenflaeche gilt vbsp als "leaked".
    # Genau das passierte mit light6 auf x1 bei X-Padding 64.
    x0, y0, z0 = int(min(xs)) - pad, int(min(ys)) - pad, int(min(zs)) - pad
    x1 = int(max(xs)) + pad
    y1 = int(max(ys)) + pad
    # Nach oben mehr Luft: light_environment sitzt ueber der Szene, und die
    # Decke darf es nicht beruehren.
    z1 = int(max(zs)) + pad + 128
    return (x0, y0, z0), (x1 - x0, y1 - y0, z1 - z0)


class Compiler5:
    def __init__(self, name="vmfs5_map"):
        self.name = name
        self.ents = []          # dicts: cls, origin, angles, keys, order
        self.wires = []         # (src_lbl, ev, tgt_lbl, meth, param, delay)
        self._n = 0
        self.layout = None
        self.testroom = False

    def _add(self, cls, origin, angles, keys):
        self._n += 1
        self.ents.append({
            "cls": cls, "origin": origin, "angles": angles,
            "keys": keys, "order": self._n,
        })

    # --- Geometrie -----------------------------------------------------
    def blk_layout(self, e):
        """layout{ ... } - die Geometrie der Map.

        chambers="n", width=, length=, height=, door_width=, door_height=
            n Kammern hintereinander entlang +Y, verbunden durch Waende
            mit Offnung (Durchgang).
        origin="x y z"
            Ursprung der Geometrie (Standard 0 0 0).

        Ohne layout-Block bleibt es beim Entities-only-Platzhalter.
        """
        a = e["attrs"]
        # chambers kann als Attribut chambers="2" ODER als erstes
        # Listen-Element chambers["2", ...] kommen - beide Formen lesen.
        n_ch = a.get("chambers")
        if n_ch is None and e["positives"]:
            n_ch = e["positives"][0]
        self.layout = {
            "chambers": int(float(n_ch if n_ch is not None else "0")),
            "width": float(a.get("width", "512")),
            "length": float(a.get("length", "512")),
            "height": float(a.get("height", "256")),
            "door_width": float(a.get("door_width", "64")),
            "door_height": float(a.get("door_height", "96")),
            "origin": _vec(a["origin"]) if "origin" in a else (0.0, 0.0, 0.0),
            "solids": [],
        }

    def blk_solid(self, e):
        """solid["x0 y0 z0", "x1 y1 z1", mat="..."] - ein Brush.

        Einziger Geometrie-Block neben layout: damit lassen sich einzelne
        achs-parallele Brushes setzen (Podeste, Deko, Kabel). Mehrere
        solid-Zeilen sind erlaubt und werden in Reihenfolge gebaut.
        """
        ps = e["positives"]
        if len(ps) < 2:
            raise SystemExit('solid braucht "x0 y0 z0", "x1 y1 z1"')
        if self.layout is None:
            # solid{} ganz ohne layout{}: Import-Modus mit Default-Massen.
            self.layout = {
                "chambers": 0, "width": 512.0, "length": 512.0,
                "height": 256.0, "door_width": 64.0, "door_height": 96.0,
                "origin": (0.0, 0.0, 0.0), "solids": [],
            }
        lo = _vec(ps[0])
        hi = _vec(ps[1])
        # Normalisieren, damit lo/hi in beliebiger Reihenfolge erlaubt sind.
        box = (min(lo[0], hi[0]), min(lo[1], hi[1]), min(lo[2], hi[2]),
               max(lo[0], hi[0]), max(lo[1], hi[1]), max(lo[2], hi[2]))
        mat = e["attrs"].get("mat", G.MAT_WALL)
        self.layout["solids"].append((box, mat))

    # --- Bloecke ---------------------------------------------------------
    def blk_start(self, e):
        """start{ player[...] }  -> info_player_start (+ optional Portalgun)
           start{ gun[...] }     -> nur weapon_portalgun (fuer importierte Maps)

        Ein "gun"-Eintrag unterdrueckt den Auto-Gun des Spawns, damit beim
        Zurueckuebersetzen einer VMF kein Portalgun doppelt entsteht.
        Erkennung ueber das Attribut gun="1", nicht ueber den Label-Namen -
        eine importierte Entity kann beliebig heissen (z. B. "portalgun").
        """
        a = e["attrs"]
        pos = a.get("pos")
        if a.get("gun"):
            if pos:
                self._add("weapon_portalgun", _vec(pos), _angles(a),
                          {"targetname": e["label"],
                           "CanFirePortal1": a.get("fire1", "1"),
                           "CanFirePortal2": a.get("fire2", "1"),
                           "fadescale": "1", "fademindist": "-1"})
            return
        if not pos:
            raise SystemExit("start %s braucht pos" % e["label"])
        if not a.get("nogun"):
            # Auto-Gun: neben dem Spawn, Zielname <spawn>_gun
            gx, gy, gz = _vec(pos)
            self._add("weapon_portalgun", (gx + 64, gy, gz), "0 0 0", {
                "targetname": e["label"] + "_gun",
                "CanFirePortal1": "1", "CanFirePortal2": "1",
                "fadescale": "1", "fademindist": "-1",
            })
        self._add("info_player_start", _vec(pos), _angles(a),
                  {"targetname": e["label"]})

    def blk_button(self, e):
        a = e["attrs"]
        pos = a.get("pos")
        if not pos:
            raise SystemExit("button %s braucht pos" % e["label"])
        typ = a.get("type", "prop_floor_button")
        if typ not in BUTTON_TYPES:
            raise SystemExit("Unbekannter Button-Typ: %s" % typ)
        keys = {"targetname": e["label"]}
        if typ == "prop_floor_button":
            keys["model"] = a.get("model", BUTTON_MODEL)
        elif typ == "prop_button":
            # prop_button (kleines Panel, z. B. Notlicht-Schalter in map_ref.vmf)
            keys["model"] = a.get("model", BUTTON_MODEL)
            if "delay" in a:
                keys["Delay"] = a["delay"]
        else:
            # func_button: Brush-Entity, Standardwerte aus map_ref.vmf
            keys["spawnflags"] = a.get("spawnflags", "1024")
            keys["speed"] = a.get("speed", "5")
            keys["wait"] = a.get("wait", "3")
            keys["lip"] = a.get("lip", "0")
            keys["movedir"] = a.get("movedir", "0 0 0")
        self._add(typ, _vec(pos), _angles(a), keys)

    def blk_door(self, e):
        a = e["attrs"]
        pos = a.get("pos")
        if not pos:
            raise SystemExit("door %s braucht pos" % e["label"])
        typ = a.get("type", "prop_testchamber_door")
        if typ not in DOOR_TYPES:
            raise SystemExit("Unbekannter Tuer-Typ: %s" % typ)
        keys = {"targetname": e["label"]}
        if typ == "prop_dynamic":
            keys["model"] = a.get("model", DOOR_MODEL)
            keys["solid"] = a.get("solid", "6")
            keys["MaxAnimTime"] = a.get("MaxAnimTime", "10")
            keys["MinAnimTime"] = a.get("MinAnimTime", "5")
        elif typ == "func_door":
            keys["movedir"] = a.get("movedir", "0 0 100")
            keys["speed"] = a.get("speed", "100")
        for k in ("AreaPortalWindow",):
            if k in a:
                keys[k] = a[k]
        self._add(typ, _vec(pos), _angles(a), keys)

    def blk_cube(self, e):
        a = e["attrs"]
        pos = a.get("pos")
        if not pos:
            raise SystemExit("cube %s braucht pos" % e["label"])
        self._add("prop_weighted_cube", _vec(pos), _angles(a), {
            "targetname": e["label"],
            "PaintPower": a.get("paintpower", "4"),
            "allowfunnel": a.get("allowfunnel", "1"),
        })

    def blk_prop(self, e):
        """prop{ name["...", pos="x y z", model="..."]; }

        Deko-Prop mit Modell. In P2 ist das fast immer prop_static: es
        bewegt sich nicht, sendet keine Outputs und ist damit ueber
        Hammer nicht verdrahtbar. Fuer bewegliche Props prop_dynamic.
        """
        a = e["attrs"]
        pos = a.get("pos")
        if not pos:
            raise SystemExit("prop %s braucht pos" % e["label"])
        model = a.get("model", "")
        if not model:
            raise SystemExit("prop %s braucht model=" % e["label"])
        typ = a.get("type", "prop_static")
        if typ not in ("prop_static", "prop_dynamic"):
            raise SystemExit("Unbekannter prop-Typ: %s" % typ)
        keys = {"model": model, "solid": a.get("solid", "0")}
        if typ == "prop_dynamic":
            keys["MinAnimTime"] = a.get("minanimtime", "1")
            keys["MaxAnimTime"] = a.get("maxanimtime", "1")
        self._add(typ, _vec(pos), _angles(a), keys)

    def blk_rotator(self, e):
        """rotator{ spin["...", pos="x y z", speed="20"]; } -> func_rotating

        P2-Drehdinge. func_rotating dreht um seine Z-Achse; speed ist
        Grad/Sekunde. targetname erlaubt Wires (z. B. Stop).
        """
        a = e["attrs"]
        pos = a.get("pos")
        if not pos:
            raise SystemExit("rotator %s braucht pos" % e["label"])
        self._add("func_rotating", _vec(pos), _angles(a), {
            "targetname": e["label"],
            "speed": a.get("speed", "20"),
            "sounds": a.get("sounds", ""),
        })

    def blk_turret(self, e):
        a = e["attrs"]
        pos = a.get("pos")
        if not pos:
            raise SystemExit("turret %s braucht pos" % e["label"])
        typ = a.get("type", TURRET_TYPES[0])
        if typ not in TURRET_TYPES:
            raise SystemExit("Unbekannter Turret-Typ: %s" % typ)
        self._add(typ, _vec(pos), _angles(a), {
            "targetname": e["label"],
            "TurretRange": a.get("range", "1024"),
        })

    def blk_lighting(self, e):
        a = e["attrs"]
        pos = a.get("pos")
        if not pos:
            raise SystemExit("light %s braucht pos" % e["label"])
        rng = int(float(a.get("power", "350")))
        col = a.get("color", "255 255 255")
        rgb = [int(float(v)) for v in re.split(r"[,\s]+", col.strip())][:3]
        while len(rgb) < 3:
            rgb.append(255)
        self._add("light", _vec(pos), _angles(a), {
            "targetname": e["label"],
            "_light": "%d %d %d %d" % (rgb[0], rgb[1], rgb[2], rng),
            "_lightHDR": "-1 -1 -1 1",
            "_lightscaleHDR": "1",
            "_quadratic_attn": "1",
        })

    def blk_envlight(self, e):
        """light_environment - Sonne + Himmel.

        Laut base.fgd (Zeile 2951) noetig:
            pitch        integer, -90 = senkrecht nach unten
            _light       color255  "255 255 255 200"
            _ambient     color255  "255 255 255 20"
        Ohne _ambient bleibt der Raum ohne Grundhelligkeit.
        Wichtig: KEIN "angles"-Key schreiben - pitch wird separat gesetzt
        und ein zweites "pitch" ueberschriebe es sonst.
        """
        a = e["attrs"]
        pos = a.get("pos", "0 0 128")
        rng = int(float(a.get("power", "200")))
        amb = int(float(a.get("ambient", "20")))
        pitch = a.get("pitch", "-90")
        self._add("light_environment", _vec(pos), None, {
            "pitch": str(int(float(pitch))),
            "_light": "255 255 255 %d" % rng,
            "_ambient": "255 255 255 %d" % amb,
            "_lightHDR": "-1 -1 -1 1",
            "_lightscaleHDR": "1",
            "_ambientHDR": "-1 -1 -1 1",
            "_AmbientScaleHDR": "1",
        })

    def blk_wiring(self, e):
        """wire["SRC.EV", "TGT.METH", param="...", delay="0.5"];

        Erzeugt das 5-Feld-ESC-Format der Source-Engine:
            Feld 1  Ziel-Entity
            Feld 2  Input
            Feld 3  Parameter   (hier: der Wert aus param=)
            Feld 4  Delay       (hier: der Wert aus delay=)
            Feld 5  -1

        Gegenueber 3.0 behoben: delay gehoert in Feld 4, NICHT in Feld 3.
        Belegt durch map_ref.vmf:
            "OnPressed" "Door2\\x1bSetAnimation\\x1bOpen\\x1b0\\x1b-1"
            Feld 3 = "Open" (Param), Feld 4 = "0" (Delay)
        """
        ps = e["positives"]
        if len(ps) < 2:
            raise SystemExit(
                'wire braucht "SRC.EV", "TGT.METH" (nur "%s" gefunden)' % ps)
        src, tgt = ps[0], ps[1]
        param = e["attrs"].get("param", ps[2] if len(ps) > 2 else "")
        delay = e["attrs"].get("delay", "0")
        if "." not in src:
            raise SystemExit("wire-Quelle falsch (erwartet SRC.EVENT): %r" % src)
        if "." not in tgt:
            raise SystemExit("wire-Ziel falsch (erwartet ZIEL.INPUT): %r" % tgt)
        src_lbl, ev = src.rsplit(".", 1)
        tgt_lbl, meth = tgt.rsplit(".", 1)
        self.wires.append((src_lbl, ev, tgt_lbl, meth, param, delay))

    # --- Rendern ---------------------------------------------------------
    def _conn_lines(self):
        """Baut die connections-Bloecke. Aufloesung ueber targetname."""
        by_name = {}
        for ent in self.ents:
            tn = ent["keys"].get("targetname")
            if tn:
                by_name.setdefault(tn, []).append(ent)
        for src, ev, tgt, meth, param, delay in self.wires:
            srcs = by_name.get(src)
            tgts = by_name.get(tgt)
            if not srcs:
                raise SystemExit("wire-Quelle unbekannt: %r" % src)
            if not tgts:
                raise SystemExit("wire-Ziel unbekannt: %r" % tgt)
            line = '\t\t"%s" "%s%s%s%s%s%s%s%s"\n' % (
                ev, tgt, ESC, meth, ESC, param, ESC, delay, ESC + "-1")
            for ent in srcs:
                ent.setdefault("conn", []).append(line)
            for ent in tgts:
                ent.setdefault("used_by", []).append(src)

    def _build_geometry(self):
        """Baut die Solids aus dem layout-Block.

        Kammern werden als Kette entlang +Y gebaut, jede mit Boden, Decke und
        Seitenwaenden; dazwischen eine Wand mit rechteckiger Offnung.
        Wichtig: eine Offnung braucht SOLID-Massen auf BEIDEN Seiten, sonst
        kann vbsp kein Portal bilden, schreibt keine .prt und vvis scheitert
        mit EXIT 1 ("Entity ... leaked!"). Deshalb sind es standardmaessig
        zwei Kammern, nicht eine mit Durchgang.
        """
        L = self.layout
        r = G.BrushRenderer()
        ox, oy, oz = L["origin"]
        n = L["chambers"]
        if n <= 0:
            # chambers="0": keine Kammern bauen. Wird fuer importierte
            # Geometrie benutzt, wo die solid{}-Bloecke die Form bereits
            # exakt beschreiben - eine zusaetzliche Huelle wuerde die
            # Geometrie veraendern statt nur zu ergaenzen.
            for box, mat in L["solids"]:
                r.box(box, (0, 0, 1), mat)
            # Import-Modus: die solid{}-Brushes sind einzelne, NICHT
            # geschlossene Bloecke. Damit gibt es kein Portal, vbsp
            # schreibt keine .prt und vvis scheitert mit EXIT 1
            # ("LoadPortals: couldn't read .prt"). Ausserdem meldet vbsp
            # jede Entity ausserhalb einer geschlossenen Huelle als
            # "leaked". Loesung: einen duennen, geschlossenen Mantel um
            # das Gesamtvolumen aus Brushes UND Entities legen. Die
            # Brushes bleiben unveraendert, es kommt nur ein Mantel dazu.
            if L["solids"]:
                # L["solids"] ist [(box6, mat), ...]; box6 = (x0,y0,z0,x1,y1,z1)
                boxes = [b for b, _ in L["solids"]]
                xs = [b[0] for b in boxes] + [b[3] for b in boxes]
                ys = [b[1] for b in boxes] + [b[4] for b in boxes]
                zs = [b[2] for b in boxes] + [b[5] for b in boxes]
                for e in getattr(self, "ents", []):
                    xs.append(e["origin"][0])
                    ys.append(e["origin"][1])
                    zs.append(e["origin"][2])
                pad = 64
                x0 = int(min(xs)) - pad
                y0 = int(min(ys)) - pad
                z0 = int(min(zs)) - pad
                x1 = int(max(xs)) + pad
                y1 = int(max(ys)) + pad
                z1 = int(max(zs)) + pad + 128
                Th = 8
                for bbox, nrm in (
                        ((x0, y0, z0 - Th, x1, y1, z0), (0, 0, 1)),
                        ((x0, y0, z1, x1, y1, z1 + Th), (0, 0, -1)),
                        ((x0 - Th, y0, z0, x0, y1, z1), (1, 0, 0)),
                        ((x1, y0, z0, x1 + Th, y1, z1), (-1, 0, 0)),
                        ((x0, y0 - Th, z0, x1, y0, z1), (0, 1, 0)),
                        ((x0, y1, z0, x1, y1 + Th, z1), (0, -1, 0))):
                    r.box(bbox, nrm, G.MAT_NODRAW)
                r.size = (x1 - x0, y1 - y0, z1 - z0)
            self.geo = r
            return r.world
        if n == 1:
            # Eine Kammer bekommt keine Offnung - sie waere ein "leaked"-Fall.
            G.chamber(r, ox, oy, oz, L["width"], L["length"], L["height"])
        else:
            # Kette: jede Kammer hinter der Wand der vorigen.
            #
            # KOORDINATEN (in Hammer-Einheiten, 1 Tile = 64):
            #   Der Boden der Kammer liegt auf oz, der Innenraum geht bis
            #   oz + H. Die Trennwand ist t dick und sitzt INNERHALB des
            #   Kammerbereichs, damit keine Wand aus dem Raum ragt:
            #       y = ya + Ln - t  ..  ya + Ln
            #   Legt man die Wand ausserhalb (y = ya + Ln .. ya + Ln + t),
            #   stehen ihre Flaechen quer im Raum und Hammer zeigt die
            #   schraegen Dreiecke - deshalb innen anlegen.
            t = G.BrushRenderer.WALL_T
            W, Ln, H = L["width"], L["length"], L["height"]
            dw, dh = L["door_width"], L["door_height"]
            #
            # Aufteilung: Kammer i belegt y von oy + i*Ln bis oy+(i+1)*Ln.
            # Die Trennwand sitzt am Ende jeder Kammer INNERHALB (t dick,
            # y von ende-t bis ende). Boden und Decke der Kammer enden
            # genau an der Wand, damit nichts ueberlappt.
            y_wall = None
            for i in range(n):
                y0 = oy + i * Ln
                y1 = y0 + Ln                       # Kammer-Bereich
                y_w = y1 - t                      # Wand beginnt
                r.floor(ox - t, y0 - t, ox + W + t, y_w, oz, G.MAT_FLOOR)
                r.ceiling(ox - t, y0 - t, ox + W + t, y_w, oz + H,
                          G.MAT_CEIL)
                # Seitenwaende: JEDE Kammer bekommt ihre beiden
                # Seitenwaende ueber die volle Kammertiefe (y0-t..y_w).
                # Zwischen zwei Kammern entsteht dadurch eine Wand, die
                # 2*t dick ist - das ist korrekt und kein Duplikat, weil
                # sie zu zwei verschiedenen Kammern gehoert.
                r.box((ox - t, y0 - t, oz, ox, y_w, oz + H), (1, 0, 0),
                      G.MAT_WALL)
                r.box((ox + W, y0 - t, oz, ox + W + t, y_w, oz + H),
                      (-1, 0, 0), G.MAT_WALL)
                if i < n - 1:
                    r.wall_with_opening(ox, ox + W, y_w, y1, oz, oz + H,
                                        ox + W / 2.0 - dw / 2.0,
                                        ox + W / 2.0 + dw / 2.0,
                                        oz, oz + dh, G.MAT_WALL)
                    y_wall = y_w
                else:
                    r.box((ox, y_w, oz, ox + W, y1, oz + H), (0, -1, 0),
                          G.MAT_WALL)
            # Vorderwand: nur Kammer 0, sie liegt bei y = oy.
            if n:
                r.box((ox, oy - t, oz, ox + W, oy, oz + H), (0, 1, 0),
                      G.MAT_WALL)
            # Kammer-Mittelpunkte fuer Spawn/Licht
            r.chamber_centers = [(ox + W / 2.0, oy + i * Ln + Ln / 2.0, oz)
                                 for i in range(n)]
            r.door_gap = (ox + W / 2.0,
                          y_wall if y_wall is not None else oy + Ln - t,
                          oz, oz + dh)
        # Einzelne solid-Brushes
        for box, mat in L["solids"]:
            r.box(box, (0, 0, 1), mat)
        self.geo = r
        return r.world

    def render(self):
        self._conn_lines()
        # Vollstaendiger Header inkl. world-Block. Der world-Block MUSS in
        # jeder Map stehen; viewsettings/palette_plus/light_plus braucht
        # Hammer fuer Gitter, 3D-Ansicht und Light-Modus. Ohne sie fehlt
        # die Editor-UI, und ein fehlender world-Block laesst Hammer stuerzen.
        out = [vmf_header(mapversion=2, skyname="sky_black_nofog", grid=64)]
        if self.layout is not None:
            out.extend(self._build_geometry())
        elif self.testroom:
            m = base.Map((1024, 1024, 512))
            _add_testroom_shell(m, origin=(0, 0, 0), size=(1024, 1024, 512))
            out.extend(m.world)
        else:
            # Kein layout-Block: Entities-only. Dann braucht die Map trotzdem
            # eine geschlossene Huelle, weil eine VMF ganz ohne Brushes vbsp
            # abstuerzen laesst (Exit 0xC0000005) und eine einzelne Bodenflaeche
            # vvis keine Portale gibt ("LoadPortals: couldn't read .prt").
            m = base.Map((512, 512, 256))
            m.ents = self.ents
            _add_testroom_shell(m)
            out.extend(m.world)
        out.append('}')
        eid = 1000
        for ent in sorted(self.ents, key=lambda x: x["order"]):
            eid += 1
            s = 'entity\n{\n\t"id" "%d"\n' % eid
            s += '\t"classname" "%s"\n' % ent["cls"]
            s += '\t"origin" "%g %g %g"\n' % tuple(float(v) for v in ent["origin"])
            if ent["angles"] is not None:
                s += '\t"angles" "%s"\n' % ent["angles"]
            for k, v in ent["keys"].items():
                s += '\t"%s" "%s"\n' % (k, v)
            if ent.get("conn"):
                s += '\tconnections\n\t{\n'
                for line in ent["conn"]:
                    s += line
                s += '\t}\n'
            s += '\teditor\n\t{\n\t\t"color" "220 30 220"\n'
            s += '\t\t"visgroupshown" "1"\n\t\t"visgroupautoshown" "1"\n\t}\n}\n'
            out.append(s)
        return "".join(out)

def vmf_header(mapversion=1, skyname="sky_black_nofog", grid=64):
    """Vollstaendiger VMF-Header, wie Hammer ihn zum Laden erwartet.

    Wichtig: der world-Block muss in JEDER Map stehen, und die Bloecke
    viewsettings/palette_plus/light_plus/postprocess_plus sind das, was
    Hammer fuer Gitter, 3D-Ansicht und Light-Modus braucht. Ohne sie
    fehlt die Editor-UI (Gitter/3D-View). Werte aus door_ref_01.vmf.
    """
    palette = "".join('\t"color%d" "255 255 255"\n' % i for i in range(16))
    return (
        'versioninfo\n{\n\t"editorversion" "400"\n\t"editorbuild" "8870"\n'
        '\t"mapversion" "%d"\n\t"formatversion" "100"\n\t"prefab" "0"\n}\n'
        'visgroups\n{\n}\n'
        'viewsettings\n{\n\t"bSnapToGrid" "1"\n\t"bShowGrid" "1"\n'
        '\t"bShowLogicalGrid" "0"\n\t"nGridSpacing" "%d"\n'
        '\t"bShow3DGrid" "0"\n}\n'
        'palette_plus\n{\n%s}\n'
        'colorcorrection_plus\n{\n%s}\n'
        'light_plus\n{\n\t"samples_sun" "6"\n\t"samples_ambient" "40"\n'
        '\t"samples_vis" "256"\n\t"texlight" ""\n'
        '\t"incremental_delay" "0"\n\t"bake_dist" "1024"\n'
        '\t"radius_scale" "1"\n\t"brightness_scale" "1"\n\t"ao_scale" "0"\n'
        '\t"bounced" "1"\n\t"incremental" "1"\n\t"supersample" "0"\n'
        '\t"bleed_hack" "1"\n\t"soften_cosine" "0"\n\t"debug" "0"\n'
        '\t"cubemap" "1"\n}\n'
        'postprocess_plus\n{\n\t"enable" "1"\n\t"bloom_scale" "1"\n'
        '\t"bloom_exponent" "2.5"\n\t"bloom_saturation" "1"\n'
        '\t"auto_exposure_min" "0.5"\n\t"auto_exposure_max" "2"\n'
        '\t"tonemap_percent_target" "60"\n'
        '\t"tonemap_percent_bright_pixels" "2"\n'
        '\t"tonemap_min_avg_luminance" "3"\n\t"tonemap_rate" "1"\n'
        '\t"vignette_enable" "1"\n\t"vignette_start" "1"\n'
        '\t"vignette_end" "2"\n\t"vignette_blur" "0"\n}\n'
        'bgimages_plus\n{\n}\n'
        'world\n{\n\t"id" "1"\n\t"mapversion" "%d"\n'
        '\t"classname" "worldspawn"\n'
        '\t"detailmaterial" "detail/detailsprites"\n'
        '\t"detailvbsp" "detail.vbsp"\n\t"maxblobcount" "250"\n'
        '\t"maxpropscreenwidth" "-1"\n\t"skyname" "%s"\n'
        % (mapversion, grid, palette,
           "".join('\t"weight%d" "1"\n' % i for i in range(16)),
           mapversion, skyname))




def main():
    ap = argparse.ArgumentParser(
        description="VMFScript 5.0 -> VMF Compiler (Portal 2)")
    ap.add_argument("vms", help=".vms-Datei im VMFScript-5.0-Format")
    ap.add_argument("-o", "--out", help="Zieldatei (Standard <mapname>.vmf)")
    ap.add_argument("--testroom", action="store_true",
                    help="minimale Testkammer als Geometrie erzeugen")
    ap.add_argument("--compile", action="store_true",
                    help="vbsp + vvis + vrad ausfuehren (im P2-maps-Ordner)")
    args = ap.parse_args()

    if not os.path.exists(args.vms):
        raise SystemExit("Datei nicht gefunden: %s" % args.vms)
    name, blocks = parse_blocks(open(args.vms, encoding="utf-8").read())

    comp = Compiler5(name)
    comp.testroom = args.testroom
    order = ["layout", "solid", "start", "envlight", "lighting", "door",
             "button", "cube", "turret", "prop", "rotator", "wiring"]
    for key in order:
        handler = getattr(comp, "blk_" + key, None)
        if handler is None:
            continue
        for e in blocks.get(key, []):
            handler(e)
    for key in blocks:
        if key not in order:
            # 3.0-Dateien haben "material" und "chamber". Das ist kein
            # Tippfehler, sondern die alte Portal-1-Syntax - der Weg
            # dahin ist ein anderer Compiler.
            hint = ""
            if key in ("material", "chamber"):
                hint = ("\n\nDas sieht nach VMFScript 3.0 (Portal 1) aus. "
                        "Diese Syntax gehoert zu vmfs3_compile.py bzw. zu "
                        "Portal 1:\n"
                        '  vbsp -game "C:\\...\\Steam\\steamapps\\common\\'
                        'Portal\\portal" name.vmf\n'
                        "VMFScript 5.0 ist Portal 2 und kennt kein "
                        "material{}-Block.")
            raise SystemExit("Unbekannter Block: %s%s" % (key, hint))

    content = comp.render()

    out = args.out or (name + ".vmf")
    with open(out, "w", newline="\n", encoding="utf-8") as f:
        f.write(content)
    print("OK: %s (%d bytes)" % (out, os.path.getsize(out)))
    print("Entities:", len(comp.ents), "| Wires:", len(comp.wires))

    if args.compile:
        if not os.path.isdir(P2_MAPS):
            raise SystemExit("P2-maps-Ordner fehlt: %s" % P2_MAPS)
        target = os.path.join(P2_MAPS, os.path.basename(out))
        if os.path.abspath(out) != os.path.abspath(target):
            shutil.copyfile(out, target)
        stem = os.path.splitext(os.path.basename(target))[0]
        for tool in ("vbsp", "vvis", "vrad"):
            exe = os.path.join(P2_BIN, tool + ".exe")
            if not os.path.exists(exe):
                raise SystemExit("%s.exe fehlt: %s" % (tool, exe))
            print("--- %s ---" % tool)
            r = subprocess.run([exe, "-game", P2_GAME, stem], cwd=P2_MAPS)
            if r.returncode != 0:
                raise SystemExit("%s EXIT %d" % (tool, r.returncode))
        print("FERTIG: %s" % os.path.join(P2_MAPS, stem + ".bsp"))


if __name__ == "__main__":
    main()
