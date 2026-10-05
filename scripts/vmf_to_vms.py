#!/usr/bin/env python3
"""vmf_to_vms.py - VMF -> VMFScript 5.0 (Portal 2), Rueckrichtung.

Liest eine fertige Portal-2-.vmf und schreibt sie als VMFScript-5.0-Block-
datei zurueck. Entities-only, passend zu map5_compile.py: Geometrie
(Solids, func_detail) wird bewusst nicht uebersetzt, weil die Sprache
keine Geometrie beschreibt.

Beispiel:
    python vmf_to_vms.py map_ref.vmf -o map_ref.vms
    python vmf_to_vms.py map_ref.vmf --preview   # nur auf stdout

Umgekehrte Richtung: map5_compile.py (VMS -> VMF).

Belegte Feld-Belegung der Source-Engine-Verbindung (aus map_ref.vmf):
    Feld 1  Ziel-Entity
    Feld 2  Input
    Feld 3  Parameter
    Feld 4  Delay
    Feld 5  Aufruf-Anzahl (-1 = einmalig)
"""

import argparse
import os
import re
import sys

ESC = chr(27)

# classname -> (blockname, standard-label)
CLASS_MAP = {
    "info_player_start":        ("start", "player"),
    "weapon_portalgun":         ("start", "player_gun"),
    "prop_testchamber_door":    ("door", "door"),
    "prop_dynamic":             ("door", "door"),
    "func_door":                ("door", "door"),
    "func_door_rotating":       ("door", "door"),
    "prop_floor_button":        ("button", "btn"),
    "prop_button":              ("button", "btn"),
    "func_button":              ("button", "btn"),
    "prop_weighted_cube":       ("cube", "cube"),
    "prop_weighted_cube_button": ("cube", "cube"),
    "npc_portal_turret_floor":  ("turret", "turret"),
    "npc_portal_turret_panelled": ("turret", "turret"),
    "light":                    ("lighting", "light"),
    "light_environment":        ("envlight", "amb"),
}

# Entities, die reine Deko sind -> nicht uebersetzen.
# func_detail / func_detailwall / func_brush stehen NICHT mehr hier: sie
# sind Geometrie und werden ueber Geom-Solids in solid{}-Blocke uebersetzt.
GEOM_CLASSES = ("func_detail", "func_detailwall", "func_brush")

SKIP_CLASSES = {
    "prop_static",
    "info_overlay", "info_overlay_transition", "env_texturetoggle",
    "info_viscluster", "info_null", "logic_auto", "math_counter",
    "env_cubemap", "light_spot", "light_dynamic", "env_particlelight",
    "trigger_multiple", "trigger_once", "func_ladder", "env_soundscape",
    "info_pvk2", "func_occluder", "env_test_pvp", "info_landmark",
    "light_spots", "env_lightmap", "func_reflection_volume",
}

# Entities, die in den P2-Referenzmaps WIRES tragen. Nur fuer diese
# ist ein fehlender targetname ein echter Befund: ohne Namen kann die
# Engine kein Ziel aufloesen. info_player_start und light_* brauchen
# keinen targetname und werden deshalb nicht markiert.
WIREABLE_CLASSES = {
    "prop_floor_button", "prop_button", "func_button",
    "prop_testchamber_door", "prop_dynamic", "func_door",
    "func_door_rotating",
    "prop_weighted_cube", "prop_weighted_cube_button",
    "npc_portal_turret_floor", "npc_portal_turret_panelled",
}

# classname -> erlaubter type= in der Sprache
TYPE_VALUES = {
    "prop_testchamber_door": "prop_testchamber_door",
    "prop_dynamic": "prop_dynamic",
    "func_door": "func_door",
    "func_door_rotating": "func_door_rotating",
    "prop_floor_button": "prop_floor_button",
    "prop_button": "prop_button",
    "func_button": "func_button",
    "npc_portal_turret_floor": "npc_portal_turret_floor",
    "npc_portal_turret_panelled": "npc_portal_turret_panelled",
}


# --------------------------------------------------------------------------
# VMF-Parser
# --------------------------------------------------------------------------
def _blocks(text):
    """Liefert Liste (name, body) fuer alle Top-Level-Bloecke."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        m = re.compile(r"\n?([A-Za-z_][\w]*)\s*\n\{").search(text, i)
        if not m:
            break
        ob = text.index("{", m.start())
        depth = 0
        j = ob
        while j < n:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out.append((m.group(1), text[ob + 1:j]))
        i = j + 1
    return out


def _split_entities(text):
    """Liefert nur die entity-Bloecke mit vollem Kontext."""
    return [body for name, body in _blocks(text) if name == "entity"]


def _kv(body):
    """Top-Level-Schluessel-Wert-Paare, ohne nested Bloecke."""
    out = []
    depth = 0
    i = 0
    n = len(body)
    cur = []
    inq = False
    while i < n:
        ch = body[i]
        if ch == '"':
            inq = not inq
        if not inq:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
        if depth == 0:
            if ch == "\n" and not inq:
                if cur:
                    out.append("".join(cur))
                    cur = []
            else:
                cur.append(ch)
        i += 1
    if cur:
        out.append("".join(cur))
    res = {}
    for line in out:
        m = re.match(r'\s*"([^"]+)"\s*"([^"]*)"\s*$', line)
        if m:
            res[m.group(1)] = m.group(2)
    return res


def _connections(body):
    """Liefert [(event, ziel, methode, param, delay, anzahl)]."""
    out = []
    for m in re.finditer(r"connections\s*\n\s*\{(.*?)\n\s*\}", body, re.S):
        for ev, raw in re.findall(r'"([^"]+)"\s+"([^"]*)"', m.group(1)):
            f = raw.split(ESC)
            if len(f) < 5:
                f += [""] * (5 - len(f))
            out.append((ev, f[0], f[1], f[2], f[3], f[4]))
    return out


def _geom_solid(body):
    """BBox und Material eines Brush-Entities (func_detail etc.).

    Nutzt die "plane"-Angaben jeder side und bildet daraus die kleinste
    Huelle. "origin" wird NICHT addiert, weil bei func_detail kein
    Origin-Offset im Spiel ist - die Koordinaten stehen direkt in den planes.
    Liefert (box6, material) oder None.
    """
    mats = re.findall(r'"material"\s+"([^"]+)"', body)
    mat = None
    for m in mats:
        if m.upper() != "TOOLS/TOOLSNODRAW":
            mat = m
            break
    pts = []
    for m in re.finditer(
            r'"plane"\s+"\(([-\d.eE+ ]+)\)\s+\(([-\d.eE+ ]+)\)\s+\(([-\d.eE+ ]+)\)"', body):
        for g in m.groups():
            pts.append(tuple(float(x) for x in g.split()))
    if len(pts) < 4:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)), mat


def _num(v, nd=6):
    """Formatiert eine Zahl ohne ueberfluessige Nullen."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    if f == int(f):
        return str(int(f))
    return ("%.*f" % (nd, f)).rstrip("0").rstrip(".")


# --------------------------------------------------------------------------
# VMF -> VMFScript
# --------------------------------------------------------------------------
class Translator:
    def __init__(self, skyname="sky_black_nofog"):
        self.skyname = skyname
        self.mapname = "translated_map"
        self.blocks = {}          # blockname -> [zeilen]
        self.used = {}            # targetname -> blocklabel
        self.geo = []             # (box6, material) aus func_detail etc.
        self.notes = []           # nicht uebersetzte Entities
        self.orphan_wires = []    # Wires einer Entity ohne targetname
        self.dup_names = []      # doppelt vergebene targetnames
        self._seen_names = set()  # bereits vergebene targetnames
        self._counters = {}

    def _uniq(self, base):
        """Sorgt fuer eindeutige Labels: door, door_02, door_03 ..."""
        if base not in self._counters:
            self._counters[base] = 1
            return base
        while True:
            self._counters[base] += 1
            cand = "%s_%02d" % (base, self._counters[base])
            if cand not in self._counters:
                self._counters[cand] = 1
                return cand

    def _add(self, block, line):
        self.blocks.setdefault(block, []).append(line)

    # -- Entities ------------------------------------------------------
    def entity(self, body):
        kv = _kv(body)
        cls = kv.get("classname", "")
        if not cls:
            return
        if cls in GEOM_CLASSES:
            g = _geom_solid(body)
            if g:
                self.geo.append(g)
            else:
                # Brush ohne auswertbare planes (z. B. Alle-Seiten-nodraw)
                self.notes.append(cls + "(keine Geometrie)")
            return
        if cls in SKIP_CLASSES:
            self.notes.append(cls)
            return
        if cls not in CLASS_MAP:
            self.notes.append(cls)
            return

        block, base = CLASS_MAP[cls]
        # targetname ist case-sensitiv fuer das Label: die Tuer heisst
        # "door1", die Wires zeigen aber auf "Door1". Valve loest
        # case-insensitiv auf, deshalb darf das Label NICHT auf
        # titlecase umgeschrieben werden.
        nameless = not kv.get("targetname")
        raw = kv.get("targetname") or base
        # Doppelter targetname: zwei Entities teilen sich dann EINEN
        # Namen. Valve loest auf den ersten Treffer auf, das zweite
        # Entity ist nicht mehr adressierbar. Solche Faelle werden
        # umbenannt (Label _02) und als dub="1" markiert - die Wires
        # zeigen weiter auf den Originalnamen, denn genau das ist der
        # Fehler im Original.
        dupe = raw in self._seen_names
        label = self._uniq(raw)
        self._seen_names.add(raw)

        parts = []
        # Text: bei Start/Button/Tuer als beschreibender Text
        parts.append('"%s"' % label)

        if "origin" in kv:
            o = kv["origin"].split()
            parts.append('pos="%s %s %s"' % (_num(o[0]), _num(o[1]), _num(o[2])))
        elif cls in ("prop_floor_button", "func_button"):
            parts.append('pos="0 0 0"')

        # Entity OHNE targetname kann keine Wires annehmen. Der
        # Uebersetzer gibt ihr trotzdem einen Namen, damit die Zeile
        # eindeutig bleibt - aber sichtbar gemacht wird, dass der Name
        # erfunden ist. Das betrifft nur Entities, die im Original
        # tatsaechlich verdrahtet sind: info_player_start hat absichtlich
        # keinen targetname und wird nicht markiert.
        has_wires = _connections(body)
        if nameless and (has_wires or cls in WIREABLE_CLASSES):
            parts.append('noname="1"')
        if dupe:
            parts.append('dub="1"')
            self.dup_names.append('%s: "%s" und "%s" teilen sich den '
                                  'Namen (Nr. %d)' % (cls, raw, label,
                                                        len(self.dup_names) + 1))

        ang = kv.get("angles")
        if ang:
            a = ang.split()
            if len(a) >= 2:
                pitch, yaw = _num(a[0]), _num(a[1])
                if _num(pitch) != "0":
                    parts.append('pitch="%s"' % pitch)
                parts.append('yaw="%s"' % yaw)

        if cls in TYPE_VALUES:
            parts.append('type="%s"' % TYPE_VALUES[cls])

        if cls == "light" and "_light" in kv:
            lt = kv["_light"].split()
            if len(lt) == 4:
                parts.append('power="%s"' % _num(lt[3]))
                if not (lt[0] == lt[1] == lt[2] == "255"):
                    parts.append('color="%s %s %s"'
                                 % (_num(lt[0]), _num(lt[1]), _num(lt[2])))
        elif cls == "weapon_portalgun":
            # Eigener Block-Eintrag: gun="1" markiert ihn fuer den Compiler.
            # Kann-Flags uebernehmen, sonst verliert der Roundtrip sie.
            parts = ['"%s"' % label, 'gun="1"']
            if "origin" in kv:
                o = kv["origin"].split()
                parts.append('pos="%s %s %s"'
                             % (_num(o[0]), _num(o[1]), _num(o[2])))
            ang = kv.get("angles")
            if ang:
                a = ang.split()
                if len(a) >= 2:
                    parts.append('yaw="%s"' % _num(a[1]))
            if kv.get("CanFirePortal1") == "1":
                parts.append('fire1="1"')
            if kv.get("CanFirePortal2") == "1":
                parts.append('fire2="1"')
        if cls == "light_environment":
            lt = kv.get("_light", "").split()
            if len(lt) == 4:
                parts.append('power="%s"' % _num(lt[3]))
            if "pitch" in kv:
                parts.append('pitch="%s"' % _num(kv["pitch"]))
            amb = kv.get("_ambient", "").split()
            if len(amb) == 4:
                parts.append('ambient="%s"' % _num(amb[3]))
        if cls == "prop_weighted_cube" and "PaintPower" in kv:
            parts.append('paintpower="%s"' % _num(kv["PaintPower"]))
        if cls.startswith("npc_portal_turret") and "TurretRange" in kv:
            parts.append('range="%s"' % _num(kv["TurretRange"]))
        if cls == "prop_dynamic" and "model" in kv:
            parts.append('model="%s"' % kv["model"])
        if cls == "func_button":
            if "spawnflags" in kv:
                parts.append('spawnflags="%s"' % kv["spawnflags"])
            if "speed" in kv:
                parts.append('speed="%s"' % _num(kv["speed"]))
            if "wait" in kv:
                parts.append('wait="%s"' % _num(kv["wait"]))

        self._add(block, "  %s[%s];" % (label, ", ".join(parts)))
        if kv.get("targetname"):
            self.used[kv["targetname"]] = label
        if cls == "weapon_portalgun":
            self._has_gun = True

        # Verbindungen als wire-zeilen sammeln
        src_tn = kv.get("targetname")
        if not src_tn:
            # Entity OHNE targetname: ihre Wires koennen nicht als
            # "Name.Event" geschrieben werden, weil es keinen Namen
            # gibt. Sie werden als verwaist gemeldet statt stillschweigend
            # verworfen zu werden.
            for ev, ziel, meth, param, delay, anz in _connections(body):
                self.orphan_wires.append(
                    "%s(ohne targetname).%s -> %s.%s" % (cls, ev, ziel, meth))
            return
        for ev, ziel, meth, param, delay, anz in _connections(body):
            self._pending.append((src_tn, ev, ziel, meth, param, delay))

    # -- Aufraeumen ----------------------------------------------------
    def finish(self):
        """Baut die wiring-Bloecke. Verwaiste Wires werden entfernt.

        Die Ziel-Aufloesung ist case-insensitiv: Valve-Connections sind es
        auch. In map_ref.vmf zeigt ein Wire auf "Door1", die Entity heisst
        aber "door1" - das muss trotzdem aufloesen.

        Ein Wire, dessen Ziel oder Quelle nicht als Entity im Block-Set
        existiert, wird verworfen - sonst entstuende eine .vms, die der
        Compiler nicht mehr aufloesen kann.
        """
        # case-insensitive Index: klein -> (original, label)
        idx = {}
        for tn, lbl in self.used.items():
            idx[tn.lower()] = (tn, lbl)

        wires, dropped = [], []
        for src_tn, ev, ziel, meth, param, delay in getattr(self, "_pending", []):
            s = idx.get(src_tn.lower())
            t = idx.get(ziel.lower())
            if s is None:
                dropped.append("%s.%s -> %s (Quelle fehlt)" % (src_tn, ev, ziel))
                continue
            if t is None:
                dropped.append("%s.%s -> %s (Ziel nicht in der Sprache)"
                               % (src_tn, ev, ziel))
                continue
            wires.append('  wire["%s.%s", "%s.%s", param="%s", delay="%s"];'
                         % (s[1], ev, t[1], meth, param, delay))
        if wires:
            self.blocks["wiring"] = wires
        self.dropped_wires = dropped

    def render(self):
        out = []
        out.append("## VMFScript 5.0 - aus Portal-2-VMF zurueckuebersetzt")
        out.append("## Quelle: %s" % getattr(self, "srcname", "?"))
        if self.geo:
            out.append("## Geometrie: %d Brush(es) als solid{}-Blocke enthalten."
                       % len(self.geo))
        else:
            out.append("## Geometrie: keine Brushes in dieser VMF gefunden.")
        if getattr(self, "dropped_wires", None):
            out.append("##")
            out.append("## Verwaiste Verbindungen, die die Sprache nicht kennt")
            out.append("## (Ziel-Entity nicht uebersetzbar) - NICHT enthalten:")
            for d in self.dropped_wires:
                out.append("##   %s" % d)
        if self.orphan_wires:
            out.append("##")
            out.append("## Verbindungen einer Entity OHNE targetname.")
            out.append("## Sie sind im Original wirkungslos (kein Adressat) und")
            out.append("## deshalb hier nicht enthalten - die Entity traegt noname=\"1\":")
            for d in self.orphan_wires:
                out.append("##   %s" % d)
        if self.dup_names:
            out.append("##")
            out.append("## Doppelte targetnames im Original (Befund der Quelle):")
            out.append("## Zwei Entities mit demselben Namen sind nicht getrennt")
            out.append("## ansprechbar. Das zweite Entity traegt dub=\"1\":")
            for d in self.dup_names:
                out.append("##   %s" % d)
        if self.notes:
            seen = {}
            for c in self.notes:
                seen[c] = seen.get(c, 0) + 1
            out.append("##")
            out.append("## Nicht uebersetzte Entities:")
            for c, v in sorted(seen.items()):
                out.append("##   %s x%d" % (c, v))
        out.append("")
        out.append('mapname = "%s";' % self.mapname)
        out.append("")
        # Geometrie zuerst: layout aus der BBox, solid pro Brush.
        if self.geo:
            xs = [g[0][0] for g in self.geo] + [g[0][3] for g in self.geo]
            ys = [g[0][1] for g in self.geo] + [g[0][4] for g in self.geo]
            zs = [g[0][2] for g in self.geo] + [g[0][5] for g in self.geo]
            x0, y0, z0 = min(xs), min(ys), min(zs)
            x1, y1, z1 = max(xs), max(ys), max(zs)
            # Auf 16 runden, damit die Werte lesbar bleiben.
            def r16(v):
                return int(round(v / 16.0)) * 16
            out.append("layout{")
            out.append('  geom["importiert", chambers="0",')
            out.append('        width="%d", length="%d", height="%d",'
                       % (r16(x1 - x0), r16(y1 - y0), r16(z1 - z0)))
            out.append('        origin="%d %d %d"];'
                       % (r16(x0), r16(y0), r16(z0)))
            out.append("}")
            out.append("")
            out.append("##* Geometrie aus der importierten VMF (Brush-BBoxes).")
            out.append("##* Nicht axis-parallele Brushes werden zu Quader")
            out.append("##* vergroessert - fuer exakte Form Hammer nutzen.")
            out.append("solid{")
            for i, (box, mat) in enumerate(self.geo):
                mat_a = ', mat="%s"' % mat if mat else ""
                lo = "%g %g %g" % (box[0], box[1], box[2])
                hi = "%g %g %g" % (box[3], box[4], box[5])
                out.append('  brush_%02d["%s", "%s"%s];'
                           % (i + 1, lo, hi, mat_a))
            out.append("}")
            out.append("")

        order = ["start", "envlight", "lighting", "door", "button",
                 "cube", "turret", "wiring"]
        for blk in order:
            lines = self.blocks.get(blk)
            if not lines:
                continue
            if blk == "start" and getattr(self, "_has_gun", False):
                # Portalgun existiert bereits als eigener Eintrag: den
                # Auto-Gun des Spawns abschalten, sonst gibt es zwei.
                # Nur Eintraege OHNE gun="1" bekommen nogun="1".
                fixed = []
                for l in lines:
                    if ('gun="1"' not in l and 'nogun=' not in l
                            and l.rstrip().endswith("];")):
                        l = l.rstrip()[:-2] + ', nogun="1"];'
                    fixed.append(l)
                lines = fixed
            out.append("%s{" % blk)
            out.extend(lines)
            out.append("}")
            out.append("")
        return "\n".join(out)


def translate(text, srcname="<stdin>", mapname=None, skyname="sky_black_nofog"):
    t = Translator(skyname=skyname)
    t._pending = []
    t.srcname = srcname
    for name, body in _blocks(text):
        if name == "world":
            m = re.search(r'"skyname"\s+"([^"]*)"', body)
            if m:
                t.skyname = m.group(1)
        elif name == "entity":
            t.entity(body)
    t.finish()
    if mapname:
        t.mapname = mapname
    else:
        stem = os.path.splitext(os.path.basename(srcname))[0]
        t.mapname = stem if stem else "translated_map"
    return t.render(), t


def main():
    ap = argparse.ArgumentParser(
        description="VMF -> VMFScript 5.0 (Portal 2), Rueckrichtung")
    ap.add_argument("vmf", help="Portal-2-.vmf")
    ap.add_argument("-o", "--out", help="Zieldatei (.vms)")
    ap.add_argument("--mapname", help="Name in der .vms")
    ap.add_argument("--preview", action="store_true",
                    help="nur auf stdout, keine Datei schreiben")
    args = ap.parse_args()

    if not os.path.exists(args.vmf):
        raise SystemExit("Datei nicht gefunden: %s" % args.vmf)
    text = open(args.vmf, encoding="utf-8", errors="replace").read()
    code, t = translate(text, args.vmf, args.mapname)

    if args.preview or not args.out:
        sys.stdout.write(code + "\n")
    if args.out and not args.preview:
        with open(args.out, "w", newline="\n", encoding="utf-8") as f:
            f.write(code + "\n")

    counts = {k: len(v) for k, v in sorted(t.blocks.items())}
    sys.stderr.write("OK: mapname=%s | Bloecke: %s\n"
                     % (t.mapname, ", ".join("%s=%d" % kv
                                             for kv in counts.items())))
    if t.notes:
        seen = {}
        for c in t.notes:
            seen[c] = seen.get(c, 0) + 1
        sys.stderr.write("nicht uebersetzt (Geometrie/Deko/Fremd-Entity): %s\n"
                         % ", ".join("%s x%d" % (k, v)
                                     for k, v in sorted(seen.items())))


if __name__ == "__main__":
    main()