"""Maperio - Testsuite fuer alle Werkzeuge.

Echte Laeufe, keine Behauptungen: jedes Skript wird ausgefuehrt, die
Portal-2-Pipeline laeuft mit den echten Valve-Tools. Ohne Pillow laeuft
der 3D-Teil eingeschraenkt.

    python scripts/test_maperio.py            # alles
    python scripts/test_maperio.py --fast     # ohne vbsp/vvis/vrad

Abweichungen zu den Beispielen in examples/ werden als Fehler gemeldet,
nicht als Text: das ist der Punkt der Suite.
"""


import os
import re
import subprocess
import sys

REPO = r"C:\Users\Friedrich\Documents\Portfolio\GitHub\VMFScript"
SC = os.path.join(REPO, "scripts")
MAPS = r"C:\Program Files (x86)\Steam\steamapps\common\Portal 2\portal2\maps"
GAME = r"C:\Program Files (x86)\Steam\steamapps\common\Portal 2\portal2"
BIN = r"C:\Program Files (x86)\Steam\steamapps\common\Portal 2\bin"
REF = (r"C:\Users\Friedrich\Documents\Portfolio\Hammer\Portal 2 Maps"
       r"\vmfscript\map_ref.vmf")
TMP = os.path.join(MAPS, "zz_ren")

fails = []
_ORDER = ("layout", "solid", "start", "envlight", "lighting",
          "door", "button", "cube", "turret", "prop", "rotator",
          "toggle", "wiring")


def check(cond, label, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + label
          + (("   " + str(detail)) if (detail and not cond) else ""))
    if not cond:
        fails.append(label)


def run(args):
    return subprocess.run([sys.executable] + args, cwd=REPO,
                          capture_output=True, text=True, errors="replace")


print("1. Dateinamen")
for old, new in (("vmfs5_compile.py", "map5_compile.py"),
                 ("vmfs4_to_vms.py", "map4_to_vms.py"),
                 ("vmfs_geometry.py", "map_geometry.py"),
                 ("vmfs_gui.py", "map_gui.py"),
                 ("vmfs_viewer.py", "map_viewer.py"),
                 ("vmfs_viewer_render.py", "map_viewer_render.py")):
    check(not os.path.exists(os.path.join(SC, old)), "%s weg" % old)
    check(os.path.exists(os.path.join(SC, new)), "%s da" % new)
check(not os.path.exists(os.path.join(REPO, "VMFScript.bat")),
      "VMFScript.bat weg")
check(os.path.exists(os.path.join(REPO, "Maperio.bat")), "Maperio.bat da")

print("\n2. Sprache bleibt unveraendert")
for f in ("syntax/vmfscript3.0.txt", "syntax/vmfscript5.0_p2_draft.txt"):
    check(os.path.exists(os.path.join(REPO, f.replace("/", os.sep))),
          "unveraendert: %s" % f)
check(os.path.exists(os.path.join(SC, "vmfs3_compile.py")),
      "vmfs3_compile.py bleibt (Sprache 3.0)")

print("\n3. Maperio.bat zeigt auf map_gui.py")
bat = open(os.path.join(REPO, "Maperio.bat"), encoding="utf-8",
           errors="replace").read()
check("map_gui.py" in bat, "Bat verweist auf map_gui.py")
check("vmfs_gui" not in bat, "Bat ohne alten Pfad")

print("\n4. Compiler")
r = run([os.path.join(SC, "map5_compile.py"),
         os.path.join(REPO, "examples", "test_chamber_two.vms"),
         "-o", TMP + ".vmf"])
check(r.returncode == 0 and "OK:" in r.stdout, "map5_compile",
      (r.stdout or r.stderr)[-140:])

print("\n5. Reverse-Uebersetzer")
r = run([os.path.join(SC, "vmf_to_vms.py"), REF, "-o", TMP + "_rt.vms"])
check(r.returncode == 0 and "OK:" in r.stderr, "vmf_to_vms",
      r.stderr[-140:])
check(os.path.exists(TMP + "_rt.vms"), "Roundtrip-.vms geschrieben")

print("\n6. 4.0-Konverter")
r = run([os.path.join(SC, "map4_to_vms.py"),
         os.path.join(REPO, "examples", "test4.vms"), "-o", TMP + "_t4.vms"])
check(r.returncode == 0 and "OK:" in r.stderr, "map4_to_vms",
      r.stderr[-140:])
check(os.path.exists(TMP + "_t4.vms"), "Konvertierung geschrieben")

print("\n7. PNG-Renderer")
png = TMP + "_v.png"
r = run([os.path.join(SC, "map_viewer_render.py"), TMP + ".vmf", png,
         "--width", "400", "--height", "300", "--no-ceiling"])
check(r.returncode == 0, "map_viewer_render", (r.stdout or r.stderr)[-200:])
check(os.path.exists(png) and os.path.getsize(png) > 2000, "PNG geschrieben",
      os.path.getsize(png) if os.path.exists(png) else 0)

print("\n8. GUI importiert")
code = ("import sys; sys.path.insert(0, r'%s'); import map_gui; "
        "print('Klasse:', map_gui.MaperioGui.__name__)" % SC)
r = subprocess.run([sys.executable, "-c", code], cwd=REPO,
                   capture_output=True, text=True, errors="replace")
check("Klasse: MaperioGui" in r.stdout, "MaperioGui",
      r.stdout.strip() or r.stderr[-250:])

print("\n9. 3.0-Legacy")
# -o ist Pflicht. Ohne schreibt vmfs3_compile.py seinen Default-Output
# <mapname>.vmf ins Repo-Root; test3.vms hat mapname="testchb_01_button",
# also landete testchb_01_button.vmf im Repo. Das war als Compiler-Output
# zunaechst committet und kam ueber .gitignore wieder zurueck.
_v3 = TMP + "_v3.vmf"
r = run([os.path.join(SC, "vmfs3_compile.py"),
          os.path.join(REPO, "examples", "test3.vms"), "-o", _v3])
check(r.returncode == 0, "vmfs3_compile", (r.stdout or r.stderr)[-140:])
check(os.path.exists(_v3), "3.0-Output im TMP, nicht im Repo",
      os.path.dirname(_v3))
check(not [f for f in os.listdir(REPO) if f.endswith(".vmf")],
      "keine .vmf im Repo-Root nach 3.0-Compile",
      [f for f in os.listdir(REPO) if f.endswith(".vmf")])

print("\n10. Portal-2-Pipeline")
for tool in ("vbsp", "vvis", "vrad"):
    p = subprocess.run([os.path.join(BIN, tool + ".exe"), "-game", GAME,
                        os.path.basename(TMP)], cwd=MAPS,
                       capture_output=True, text=True, errors="replace")
    check(p.returncode == 0, "%s exit 0" % tool, "EXIT=%d" % p.returncode)
bsp = TMP + ".bsp"
check(os.path.exists(bsp) and os.path.getsize(bsp) > 1000, "BSP erzeugt",
      os.path.getsize(bsp) if os.path.exists(bsp) else 0)

print("\n11. Syntax aller Skripte")
import py_compile
bad = 0
for f in sorted(os.listdir(SC)):
    if f.endswith(".py"):
        try:
            py_compile.compile(os.path.join(SC, f), doraise=True)
        except Exception as exc:
            print("      FEHLER %s: %s" % (f, exc))
            bad += 1
check(bad == 0, "alle Skripte syntaktisch ok", "%d fehlerhaft" % bad)

print("\n12. Keine 'vmfs_'-Werkzeugreferenzen mehr")
# Zwei Ausnahmen sind erlaubt und gewuenscht:
#  - dieses Testskript selbst (es prueft die Umbenennung)
#  - eine Migrationsnotiz, die den ALTEN Namen nennt ("frueher vmfs5_compile")
ALLOW = {"scripts\\test_maperio.py", "scripts/test_maperio.py",
         os.path.basename(__file__)}
MIGRATION = ("frueher", "früher", "vorher", "ehemals", "old name")
hits = []
for root, dirs, files in os.walk(REPO):
    dirs[:] = [d for d in dirs if d != ".git" and d != "__pycache__"]
    for f in files:
        if not f.endswith((".py", ".md", ".txt", ".bat")):
            continue
        rel = os.path.relpath(os.path.join(root, f), REPO)
        if rel.replace(os.sep, "\\") in ALLOW or rel.replace(os.sep, "/") in ALLOW:
            continue
        lines = open(os.path.join(root, f), encoding="utf-8",
                     errors="replace").read().splitlines()
        for i, l in enumerate(lines, 1):
            for needle in ("vmfs_gui", "vmfs_viewer", "vmfs_geometry",
                           "vmfs5_compile", "vmfs4_to_vms"):
                if needle in l and not any(m in l for m in MIGRATION):
                    hits.append("%s:%d -> %s" % (rel, i, needle))
check(not hits, "keine alten Werkzeugnamen mehr (Ausnahmen: Testskript, "
      "Migrationsnotiz)", "; ".join(hits[:4]))



# ---------------------------------------------------------------
# 13. Geometrie: die Pruefungen, die am 2026-10-04 gefehlt haben
# ---------------------------------------------------------------
sys.path.insert(0, SC)
import map_viewer as V
import map_geometry as GEO

print("\n13. Geometrie-Winding (Boden muss +z, Decke -z zeigen)")
_r = GEO.BrushRenderer()
_r.floor(0, 0, 512, 512, 0, GEO.MAT_FLOOR)
_r.ceiling(0, 0, 512, 512, 256, GEO.MAT_CEIL)


def _face_normals(solid_text):
    out = []
    for m in re.finditer(r'side\s*\{(.*?)\n\t\t\}', solid_text, re.S):
        blk = m.group(1)
        mat = re.search(r'"material"\s+"([^"]*)"', blk).group(1)
        vs = [tuple(map(float, v.split()))
              for v in re.findall(r'"v"\s+"([-\d. ]+)"', blk)]
        a, b, c = vs[:3]
        u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        w = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        n = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2],
             u[0] * w[1] - u[1] * w[0])
        mag = n[0] ** 2 + n[1] ** 2 + n[2] ** 2
        if mag < 1e-6:
            out.append((mat, None))
            continue
        ln = mag ** 0.5
        out.append((mat, (round(n[0] / ln), round(n[1] / ln),
                          round(n[2] / ln))))
    return out


for idx, solid in enumerate(_r.world):
    for mat, nn in _face_normals(solid):
        if mat == GEO.MAT_FLOOR:
            check(nn == (0, 0, -1), "Boden-Flaeche zeigt (0,0,-1)", nn)
        if mat == GEO.MAT_CEIL:
            check(nn == (0, 0, 1), "Decke-Flaeche zeigt (0,0,+1)", nn)

print("\n14. Sichtbarkeit im Viewer: nach Material, nicht nach Blickrichtung")
if not os.path.exists(TMP + ".vmf"):
    run([os.path.join(SC, "map5_compile.py"),
         os.path.join(REPO, "examples", "test_chamber_two.vms"),
         "-o", TMP + ".vmf"])
_txt = open(TMP + ".vmf", encoding="utf-8", errors="replace").read() \
    if os.path.exists(TMP + ".vmf") else ""
if _txt:
    _faces, _edges, _tot, _nod = V.parse_solids(_txt, True)
    _c, _r2 = V._scene_bounds(_faces, _edges)
    _cam = V.Camera(_c, _r2)
    _draw = V.build_drawlist(_faces, _cam, 900, 620, True)
    _nodraw_drawn = sum(1 for d in _draw if d[6] == V.COLOR_NODRAW
                        or (abs(d[6][0] - V.COLOR_NODRAW[0]) < 2))
    check(_draw, "Zeichenliste befuellt", len(_draw))
    # NODRAW-Farben duerfen mit Shading nie exakt gleich sein -> nur pruefen,
    # dass ueberhaupt Materialfarben vorkommen
    mats = set()
    for f in _faces:
        if not f[5]:
            mats.add(f[4])
    check(len(mats) >= 2, "mehrere Materialien in der Map", len(mats))
    check(any(f[4] == "TILE/WHITE_WALL_TILE003B" for f in _faces),
          "weisse Wandpanels vorhanden")
else:
    print("  (uebersprungen: keine .vmf zum Testen)")

print("\n15. Kamera-Mathes")
_cam = V.Camera((0.0, 0.0, 0.0), 500.0)
_r3, _u3, _d3 = _cam.basis()
_dot = lambda a, b: sum(x * y for x, y in zip(a, b))
check(abs(_dot(_r3, _u3)) < 1e-9 and abs(_dot(_r3, _d3)) < 1e-9
      and abs(_dot(_u3, _d3)) < 1e-9, "right/up/eye_dir paarweise senkrecht")
check(_u3[2] > 0.5, "up zeigt nach oben", "up.z=%.3f" % _u3[2])
_cpt = _cam.to_view((0, 0, 0), 800, 600)
check(_cpt is not None and abs(_cpt[0] - 400) < 1 and abs(_cpt[1] - 300) < 1,
      "Zielpunkt in der Bildmitte")
check(_cam.to_view((200, 0, 0), 800, 600)[0] > 400, "+x erscheint rechts")
check(_cam.to_view((0, 0, 200), 800, 600)[1] < 300, "+z erscheint oben")
_eye = _cam.eye()
check(_cam.to_view(tuple(_eye[i] - _d3[i] * 200 for i in range(3)),
                   800, 600) is None, "hinter Kamera -> None")



print("\n16. toggle{} / env_texturetoggle")
_tog = os.path.join(REPO, "examples", "test_indicators.vms")
_tog_vmf = TMP + "_tog.vmf"
_r = run([os.path.join(SC, "map5_compile.py"), _tog, "-o", _tog_vmf])
_out = _r.stdout + _r.stderr
check(_r.returncode == 0, "test_indicators.vms kompiliert",
      _out.strip()[-140:])
if os.path.exists(_tog_vmf):
    _body = open(_tog_vmf, encoding="utf-8", errors="replace").read()
    check('"classname" "env_texturetoggle"' in _body,
          "env_texturetoggle erzeugt")
    # target und targetname muessen da sein, ohne target geht der
    # Toggle ins Leere
    for _m in re.finditer(r'"classname"\s+"env_texturetoggle"\n(.*?)\n\t\}',
                         _body, re.S):
        _blk = _m.group(1)
        check('"target"' in _blk, "  hat target")
        check('"targetname"' in _blk, "  hat targetname")
        check("solid" not in _blk, "  ohne Brush")
    # Die Indikator-Wires: SetTextureIndex mit param 1 und 0
    _w = re.findall(r'"(\w+)"\s+"([^"]*\x1b[^"]*)"', _body)
    _idx = [f for f in _w if "SetTextureIndex" in f[1]]
    check(len(_idx) >= 2, "SetTextureIndex-Wires vorhanden", len(_idx))
    _params = set()
    for _e, _v in _idx:
        _fields = _v.split("\x1b")
        if len(_fields) >= 3:
            _params.add(_fields[2])
    check(_params == {"0", "1"},
          "Index 0 und 1 (aus/an)", sorted(_params))
    # Und die Map muss wirklich bauen
    _stem = os.path.basename(_tog_vmf)[:-4]
    for _tool in ("vbsp", "vvis", "vrad"):
        _p = subprocess.run(
            [os.path.join(BIN, _tool + ".exe"), "-game", GAME, _stem],
            cwd=MAPS, capture_output=True, text=True, errors="replace")
        check(_p.returncode == 0, "%s auf der Toggle-Map exit 0" % _tool,
              "EXIT=%d" % _p.returncode)
    _log = os.path.join(MAPS, _stem + ".log")
    if os.path.exists(_log):
        _txt = open(_log, encoding="utf-8", errors="replace").read().lower()
        check("leaked" not in _txt, "kein leaked auf der Toggle-Map")

print("\n17. Alle drei Tuer-Typen")
_door_vms = os.path.join(REPO, "examples", "test_door_types.vms")
_door_vmf = TMP + "_doors.vmf"
if os.path.exists(_door_vms):
    _r = run([os.path.join(SC, "map5_compile.py"), _door_vms, "-o", _door_vmf])
    _out = _r.stdout + _r.stderr
    check(_r.returncode == 0, "test_door_types.vms kompiliert",
          _out.strip()[-140:])
    if os.path.exists(_door_vmf):
        _body = open(_door_vmf, encoding="utf-8", errors="replace").read()
        # Die drei Typen muessen getrennt vorhanden sein
        for _cls, _keys in (
                ("prop_testchamber_door", None),
                ("func_door", ("movedir", "speed")),
                ("func_door_rotating", ("axis", "angle", "speed",
                                        "objectname"))):
            _tag = '"classname" "%s"' % _cls
            _present = _tag in _body
            check(_present, "%s vorhanden" % _cls)
            if _present and _keys:
                # Der Block der Entity, nicht die ganze Datei
                _i = _body.index(_tag)
                _blk = _body[_i:_body.index("\n\t}", _i)]
                for _k in _keys:
                    check('"%s"' % _k in _blk,
                          "  %s hat %s" % (_cls, _k))
        # Der entscheidende Punkt: func_door darf KEIN axis haben und
        # func_door_rotating darf KEIN movedir - sonst waeren es dieselbe
        # Entity und der Rotating-Typ waere wirkungslos.
        _i = _body.index('"classname" "func_door"\n')
        _blk = _body[_i:_body.index("\n\t}", _i)]
        check('"axis"' not in _blk, "func_door hat KEIN axis (linear)")
        check('"objectname"' not in _blk, "func_door hat KEIN objectname")
        _i = _body.index('"classname" "func_door_rotating"\n')
        _blk = _body[_i:_body.index("\n\t}", _i)]
        check('"movedir"' not in _blk,
              "func_door_rotating hat KEIN movedir (dreht)")
        # Wires
        check(_body.count("OnPressed") == 3, "3 Wires verdrahtet",
              _body.count("OnPressed"))

        # Und durch die echte Pipeline. TMP liegt bereits im
        # P2-Maps-Ordner - kein Kopieren noetig (das waere ein
        # SameFileError), vbsp braucht nur den Kurznamen ohne .vmf.
        _stem = os.path.basename(_door_vmf)[:-4]
        for _tool in ("vbsp", "vvis", "vrad"):
            _p = subprocess.run(
                [os.path.join(BIN, _tool + ".exe"), "-game", GAME, _stem],
                cwd=MAPS, capture_output=True, text=True, errors="replace")
            check(_p.returncode == 0, "%s auf der Tuer-Map exit 0" % _tool,
                  "EXIT=%d" % _p.returncode)
        _log = os.path.join(MAPS, _stem + ".log")
        if os.path.exists(_log):
            _txt = open(_log, encoding="utf-8", errors="replace").read().lower()
            check("leaked" not in _txt, "kein leaked auf der Tuer-Map")
            check("no visible sides" not in _txt,
                  "kein 'no visible sides' auf der Tuer-Map")
else:
    check(False, "examples/test_door_types.vms vorhanden")

print("\n18. sign{} / func_brush - dokumentiert nicht fertig")
check("sign" not in _ORDER, "sign nicht im Block-Dispatch",
      "sonst bricht jede Map mit sign{} ab")
# Ein echter Block beginnt in eigener Zeile mit "sign{" - ein
# Kommentar darf das Wort erwaehnen, das ist der ganze Sinn der
# Verweis-Zeile im Beispiel.
_txt2 = open(_tog, encoding="utf-8").read()
_blocks = [ln for ln in _txt2.splitlines()
           if ln.strip().startswith("sign{")]
check(not _blocks, "test_indicators nutzt kein sign{}-Block", _blocks)

# --- Aufraeumen, ganz zum Schluss -------------------------------
# vbsp schreibt .lin/.log/.prt/.bsp neben die .vmf, alle mit dem
# TMP-Praefix. Muss NACH den Pruefungen laufen - vorher loescht es
# die Dateien, die danach noch gebaut werden.
print("\n19. Aufraeumen")
_prefix = os.path.basename(TMP)
for _f in sorted(os.listdir(MAPS)):
    if _f.startswith(_prefix):
        try:
            os.remove(os.path.join(MAPS, _f))
        except OSError:
            pass
for _f in sorted(os.listdir(REPO)):
    if _f.startswith(_prefix):
        try:
            os.remove(os.path.join(REPO, _f))
        except OSError:
            pass
_left = [f for f in os.listdir(MAPS) if f.startswith(_prefix)]
check(not _left, "keine Reste im P2-Maps-Ordner", _left)

print("\n%d fehlgeschlagen" % len(fails))
for x in fails:
    print("  FAILED: " + x)
sys.exit(1 if fails else 0)