# VMFScript Übergabe-Stand (neue Session soll hier weiterarbeiten)

## Ziel
Baue für den Nutzer (deutscher Portal-1-Mapper) eine **richtige kleine Programmiersprache
„VMFScript 3.0"**, die aus einfachem Code eine fertige Portal-1-.vmf erzeugt. Der Nutzer hat
im Chat eine eigene Syntax vorgegeben (siehe unten, `vmfscript3.0.txt`). Diese Syntx MUSS
eins-zu-eins übernommen werden.

Der Nutzer will KEINE lange line-by-line VMF tippen, sondern Blöcke/Schlüssel-Wert-Code,
den ein Compiler in die komplette VMF übersetzt.

## Person
- Nutzer baut Portal-1-Karten (nicht Portal 2), Source/HL2-Engine, Hammer/Hammer++.
- Portfolio: `C:\Users\Friedrich\Documents\Portfolio\Hammer\`
- NOTE: Portal 1 nutzt alle HL2-Assets. Doppelklick auf .vmf öffnet den FALSCHEM
  (Portal-2-)Hammer++; Nutzer öffnet Portal-1-Hammer++ manuell.
- Kommunikation auf Deutsch. Der Nutzer ist etwas genervt, weil ich oft „abstürze"
  (siehe Fallstricke). Freundlich, präzise, KEINE leeren Versprechen.

## WICHTIG — warum ich „abstürzte" (MUSS der neuen Session gesagt werden)
- Zu GROSSE Tool-Aufrufe (lange Code-Dateien in einem Rutsch) > Stream-Timeout, Abbruch.
- LÖSUNG: Jeden Tool-Aufruf unter ~8K Tokens halten. Dateien in MEHREREN kleinen
  write_file/patch-Schritten bauen. Nie eine lange .py-Datei in einem einzigen write_file
  über 8K Tokens.
- Zusätzlich rutschten mir beim Beantworten sinnlose Zeichenfragmente in den Text
  (Ahfehler). NICHT nachplappern; sauber und trocken bleiben.
- User dachte der Kontext sei voll → KEINE Sorge um Kontext; das Problem waren große
  Aufrufe. Neue Session + diese Übergabe = frisch.

## Programmiersprache VMFScript 3.0 — SYNTAX (VOM USER, VERBINDLICH)
Quelle: `Documents/Portfolio/Hammer/vmfscript3.0.txt`
```
mapname="testchb_01_button";
material{
	floor["concrete/concrete_modular_floor001a"];
	ceiling["concrete/concrete_modular_ceiling001a"];
	wall["concrete/…"];
};
##* hello this is a Long comment
which
goes
on
and
on
*##
chamber{
	sizex["1024"];
	sizey["512"];
	sizez["1024"];
	player["512, 512, 64"];
	gun["560, 512, 64"];
};
## this is a short comment
lighting{
	light_01[pos="300, 500, 380",power="255",color="255, 255, 200"];
	light_floor_03[..];
};
buttons{
	door_btn[pos="420, 700, 0"];
};
doors{
	door_01[pos="512, 990, 0"];
}; 
wiring{
	wire["door_btn.OnPressed", "door_01.Open", delay="2"]; ## delay in seconds
};
```
Regeln aus diesem Beispiel (als Parser-Anforderung):
- Blöcke: `name { ... };` (mit Semikolon)
- Zeilen in Blöcken: `label["..."];` oder `label[key="val", key2="val"];`
- Werte sind in Anführungszeichen
- Kommentare: `##` bis Zeilenende (short); `##*` ... `*##` (long, mehrzeilig)
- `wiring` nutzt ein Feld `wire["QUELLE.EV", "ZIEL.METHODE", delay="N"]`

## Was der Compiler tun muss
Parse diese Blöcke und erzeuge eine .vmf mit:
- mapname → Dateiname / Mapinfo
- material → World/Floor Materialien
- chamber → Raumgröße + info_player_start + weapon_portalgun
- lighting → light-Entities (light_01 etc.)
- buttons → prop_floor_button (portal_button)
- doors → prop_testchamber_door
- wiring → connections mit korrektem Trenner
Entitäten/Winding-Logik existiert bereits (siehe Dateien unten). NUR der neue Parser für
diese Block-Syntax fehlt noch, plus die Verbindung zur Map-Klasse.

## Dateien auf Platte (Skill-Ordner)
Skill: `C:\Users\Friedrich\AppData\Local\hermes\skills\game-dev\portal-maps-einfach-erstellen\`
- `scripts/portalmap.py`        = VMFScript 1.0 (ESC-Trenner, funktioniert)
- `scripts/portalmap2.py`       = VMFScript 2.0 (ESC+Komma), geschrieben, Test offen
- `scripts/vmfs3_core.py`       = NUR Parser-Kern (Kommentare, Blöcke, key=value) — GESCHRIEBEN
- `scripts/generate_plain_portal_map.py` = Map-Klasse (Winding, Solids, entity(), add_shell(), render())
- `references/demo.pml`         = Beispiel für 1.0
- `references/test2.pml`        = Test für 2.0 (chamber/light/spawn/gun/button/door/wire)

Map-Klasse API (aus generate_plain_portal_map):
- `Map((W,L,H))` + `.add_shell()` → Kammer aus 6 Solids, Innen-Winding
- `.entity(classname, (x,y,z), angles="0 0 0", extra={..}, connections=[(ev,tgt,met,arg),..])`
- Attribute: mat_floor, mat_ceiling, mat_wallAB, mat_wallCD, skyname, eid, sid, fid
- `.render()` → str der ganzen VMF

## Nächste Schritte (in Reihenfolge)
1. Teil 2: neuen Parser-Befehl-Handler schreiben, der vmfs3_core importiert und die
   Blöcke (material/chamber/lighting/buttons/doors/wiring) in Map-Aufrufe übersetzt.
   IN KLEINEN write_file-Schritten.
2. Eine endgültige Beispiel-`test3.vms` (im Stil des Users, mit allen Blöcken + wiring mit
   delay) anlegen.
3. `portalmap3_compile.py` schreiben: liest .vms, ruft Compiler, gibt .vmf, optional vbsp.
4. Test: vms → vmf → mit Portal-1-vbsp kompilieren (Pfade s.u., NICHT Portal 2!).

## Compiler-Pfade (Portal 1 — NICHT Portal 2!)
```
P1_BIN  = r"C:\Program Files (x86)\Steam\steamapps\common\Portal\bin"
P1_GAME = r"C:\Program Files (x86)\Steam\steamapps\common\Portal\portal"
vbsp:  "<P1_BIN>\vbsp.exe" -game "<P1_GAME>" "<pfad>.vmf"
```
Portal 2\bin\vbsp.exe bricht mit return 0x1 und zerstört nichts, aber ist falsch.

## Fallstricke
- VERBINDLICH: kleine Tool-Aufrufe (<~8K Tokens). Große Dateien in Häppchen.
- Portal 1, nicht Portal 2.
- Karte braucht info_player_start + weapon_portalgun + Licht + Himmel, sonst kaputt.
- Winding der Solids muss Innen-Winding sein (Map-Klasse macht das schon).
- Skyname `sky_black_nofog` (einfache Maps). Kein env_cubemap/camera nötig.
