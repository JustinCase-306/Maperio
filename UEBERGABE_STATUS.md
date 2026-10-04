# VMFScript — Stand 2026-09-30 (Ende der Arbeitssession)

Kurze Notiz fuer den naechsten Start. Alles hier ist **belegt** durch
tatsaechliche Laeufe, nicht behauptet.

## Worum es geht

VMFScript ist eine eigene Block-Sprache, die in Valve-`.vmf` uebersetzt wird.
Stand ist **Version 5.0 fuer Portal 2**.

Der Grund fuer den Sprung 3.0 -> 5.0: In Portal 1 (Half-Life-2-Engine) ist ein
Button ein Entity-Zoo aus `prop_static` + `prop_dynamic` + mehreren
`trigger_`-Entities + `logic_`-Steuerung + Licht + Sound. In Portal 2 ist ein
Button **eine** Entity und **ein** Wire:

    "OnPressed" "Door1<ESC>Open<ESC><ESC>0.5<ESC>-1"

Das ist derselbe Puzzle-Ausdruck mit einem Zehntel der Entities.

## Heute geaendert

### 1. `scripts/vmf_to_vms.py` — VMF -> VMFScript (Rueckrichtung)

Drei echte Befunde an der Uebersetzung wurden behoben:

- **Entity ohne targetname** (`prop_button` in `map_ref.vmf`) bekommt jetzt
  `noname="1"`, und ihre Wires werden im Header als verwaist gelistet statt
  stillschweigend verworfen. Vorher taten die Wires so, als waeren sie
  uebersetzt worden — dabei sind sie im Original wirkungslos, weil es keinen
  Adressaten gibt.
- **Doppelter targetname** (`light6` kommt zweimal vor) wird als `dub="1"`
  markiert und im Header gemeldet. Zwei Entities mit gleichem Namen sind
  getrennt nicht ansprechbar; das ist ein Befund der Quelle, kein Fehler des
  Uebersetzers.
- **Namen bleiben case-sensitiv.** Die Tuer heisst `door1`, die Wires zeigen
  auf `Door1`. Valve loest case-insensitiv auf, deshalb wird nichts
  umgeschrieben.

Wichtige Selbstkorrektur: Ich hatte zuerst behauptet, `door1` statt `Door1` sei
ein Bug. Das war **falsch** — Valve loest case-insensitiv auf, der Code war
korrekt. Ebenso war meine Behauptung "die func_detail sind nur unsichtbare
Stuetzen" zu grob: 48 von 288 Flaechen sind sichtbares
`TILE/WHITE_WALL_TILE003B`, der Rest ist `TOOLS/TOOLSNODRAW`.

### 2. `scripts/vmfs5_compile.py` — geschlossene Huelle im Import-Modus

**Das war der eigentliche Bug.** Bei `chambers="0"` (Import-Modus) baut der
Compiler die `solid{}`-Brushes als einzelne, nicht geschlossene Bloecke.
Folge war:

    vbsp EXIT=0   aber  **** leaked ****
                        Entity prop_weighted_cube (-144 -272 83) leaked!
    vvis EXIT=1   LoadPortals: couldn't read ....prt
    vrad EXIT=0

Kein Portal, keine `.prt`, vvis scheitert.

Fix: bei `chambers="0"` wird ein duinner, geschlossener Mantel (8 Einheiten
Staerke, `TOOLS/TOOLSNODRAW`) um das Gesamtvolumen aus **Brushes und Entities**
gelegt. Die importierten Brushes bleiben unveraendert, es kommt nur ein Mantel
dazu. Padding 64 nach allen Seiten, +128 nach oben.

Zwei Fehler passierten dabei und sind behoben:

- Der Fix stand an der falschen Stelle und war toter Code: `_build_geometry`
  hat fuer `n <= 0` einen eigenen Zweig mit eigenem `return`, der Code dahinter
  wurde nie erreicht. Deshalb blieb die VMF byte-identisch.
- `L["solids"]` ist `[(box6, mat), ...]`. Mit `[b[0][0] for b, _ in ...` wurde
  `b` doppelt entpackt -> `TypeError: 'float' object is not subscriptable`.

## Verifikationsstand (alles wirklich ausgefuehrt)

Roundtrip `map_ref.vmf -> .vms -> .vmf`, danach die echten Portal-2-Tools mit
`-game "C:\Program Files (x86)\Steam\steamapps\common\Portal 2\portal2"`:

| Map | vbsp | vvis | vrad | BSP |
|---|---|---|---|---|
| `map_ref` (Roundtrip aus der echten P2-Referenzmap) | 0 | 0 | 0 | 134.920 |
| `test_chamber_two` | 0 | 0 | 0 | 338.144 |
| `test_floor_button_door` | 0 | 0 | 0 | 942.136 |

Kein "leaked", `.prt` wird geschrieben. Die VMF muss im P2-Maps-Ordner liegen,
sonst bricht vbsp mit "Can't create LogFile" und EXIT 1 ab.

`map_ref`-Roundtrip: 16 Entities, 6 Wires, 49 Brushes, Geometrie X −544..32,
Y −544..800, Z 0..352.

## Erledigt seit der ersten Fassung dieser Notiz

### `test4.vms` laeuft wieder — ueber einen Konverter (NEU)

Statt die 4.0-Datei zu loeschen oder den 5.0-Compiler auf alte Formen
aufweichen zu lassen, gibt es `scripts/vmfs4_to_vms.py`:

    python scripts/vmfs4_to_vms.py examples/test4.vms -o examples/test4_converted.vms

Ueberbrueckt: Komma-Positionen -> Leerzeichen, `chamber_00/01/02` werden zu
einem `layout{chambers="3", ...}`, Labels werden pro Kammer eindeutig
(`light_01`, `light_01_02`, `light_01_03`), Tuer-Namen aus dem Listenwert
gerettet (`door["door_01"]` -> `door_01[...]`), Kammer-Positionen werden um
den Kammern-Offset verschoben (`512 256` -> `512 768` -> `512 1280`).

Nicht 1:1, im Ausgabekopf gemeldet: `material{}` verworfen (P1-Materialien
gibt es in P2 nicht), Tueren ohne `pos=` bekommen eine berechnete
Trennwand-Position, `rotator axis=/speed=` geht nicht 1:1 auf `func_rotating`.

### Zwei Bloecke im 5.0-Compiler ergaenzt (NEU)

`prop{}` und `rotator{}` gab es vorher nicht. Der Konverter brauchte sie,
weil 4.0 `prop` und `rotator` kannte — ohne sie entstand ein Block
`props`, den der Compiler mit `Unbekannter Block: props` ablehnte.

- `prop{ name["...", pos="x y z", model="models/..."]; }` -> `prop_static`
  (Default) oder `prop_dynamic`. `model=` ist Pflicht, sonst bricht es ab.
- `rotator{ spin["...", pos="x y z", speed="20"]; }` -> `func_rotating`,
  Drehung um Z, speed in Grad/Sekunde.

Blockliste des Compilers ist jetzt:
`layout, solid, start, envlight, lighting, door, button, cube, turret,
prop, rotator, wiring`. Alles andere -> `Unbekannter Block: X`.

### Drei Parser-Fehler, die beim Konverter erst aufliefen

1. **Listenwerte gingen verloren.** Der erste `ENTRY_RE` las nur
   `key="wert"`. Dadurch waren `sizex["1024"]`, `player["512, 256, 64"]`
   und `wire["a", "b"]` leer. 4.0 nutzt drei Schreibweisen:
   `sizex["1024"]` (Listeneintrag), `button["btn_open", pos=...]` (Name im
   Listeneintrag) und `light_01[pos=..., power=...]` (alles Attribut).
2. **`door["door_01"]` crashte** mit
   `ValueError: could not convert string to float: 'door_01'`, weil der
   Listenwert als Position gelesen wurde. `_chamber_pos` gibt jetzt `None`
   zurueck, wenn kein Zahlen-Tripel vorliegt, und der Aufrufer nutzt den
   Wert als Entity-Namen.
3. **Kammern lagen uebereinander.** 4.0-Massen waren relativ zur Kammer,
   5.0 baut eine Kette entlang +Y. Ohne Offset lagen alle drei Kammern
   an derselben Stelle.

## Was ich FALSCH behauptet habe (bitte nicht uebernehmen)

1. "`door1` statt `Door1` ist ein Bug, die Tuer oeffnet nie." -> **falsch**.
   Valve loest Connections case-insensitiv auf.
2. "Die 48 func_detail sind unsichtbare Stuetzen." -> **zu grob**. Sie haben je
   genau eine sichtbare `TILE/WHITE_WALL_TILE003B`-Flaeche, der Rest
   (236 von 288) ist `TOOLS/TOOLSNODRAW`.
3. "Die Material-Zuordnung im Uebersetzer ist falsch." -> **falsch**. Jeder
   Brush hat genau ein sichtbares Material; `_geom_solid` greift korrekt.

## Offen fuer naechste Sitzung

1. ~~`test4.vms` schlaegt fehl~~ -> **geloest**, siehe `vmfs4_to_vms.py` oben.
2. ~~`vmfs4_compile.py` existiert nicht mehr~~ -> **geloest**, die Syntax wird
   jetzt vom Konverter bedient statt von einem eigenen Compiler.
3. `test3.vms` ist eine 3.0-Datei (`material`-Block) und wird vom
   5.0-Compiler mit "Unbekannter Block: material" abgelehnt. Das ist
   inhaltlich korrekt, aber die Meldung ist nackt. Besser waere ein
   Hinweis auf `vmfs3_compile.py` bzw. auf den Portal-1-Weg.
4. Die offenen Designfragen aus `syntax/vmfscript5.0_p2_draft.txt`
   (Abschnitt 10) sind unbeantwortet: Tuer-Typ (`prop_testchamber_door` vs.
   `func_door`), baut der Compiler Geometrie selbst, `pos="x y z"` vs.
   `pos=[x,y,z]`, Delay-Format.
5. Der Geometrie-Import ist noch nicht geprueft: der Roundtrip
   importiert 49 Brushes exakt, aber die sichtbaren Wand-Panels sind
   Einzelflaechen. Ob das in Hammer sauber aussieht, ist ungetestet — dafuer
   braucht es einen Blick in Hammer.
6. `vmfs_gui.py` und `VMFSCRIPT.bat` kennen die neuen Werkzeuge noch nicht.
   Die GUI kann weder 4.0-Dateien konvertieren noch `prop`/`rotator`.

## Wichtige Pfade

- Compiler: `scripts/vmfs5_compile.py` (5.0, P2)
- Uebersetzer: `scripts/vmf_to_vms.py` (VMF -> VMS)
- Syntax-Entwurf: `syntax/vmfscript5.0_p2_draft.txt`
- Referenzmaps: `C:\Users\Friedrich\Documents\Portfolio\Hammer\Portal 2 Maps\vmfscript\map_ref.vmf`, `door_ref_01.vmf`
- Der Compiler schreibt seine `.vmf` in das **Home-Verzeichnis**
  (`C:\Users\Friedrich\`), nicht in den Skill-Ordner. Das ist beim Testen
  leicht zu übersehen.

## Git

Keine Git-Operationen ausgefuehrt. Dateien wurden nur abgelegt.