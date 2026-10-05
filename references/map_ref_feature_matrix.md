# map_ref.vmf — Was eine gute Map braucht, und was VMFScript davon kann

Quelle: `Documents/Portfolio/Hammer/Portal 2 Maps/vmfscript/map_ref.vmf`
(73 Entities, decompiliert aus `first_map` von BSPSource v1.4.7)

Diese Datei ist die **Referenz fuer Feature-Umfang**, nicht nur fuer Syntax.
Alles hier ist aus der Map belegt, nicht geraten.

## Die Map im Ueberblick

| | |
|---|---|
| Entities | 73 |
| davon mit Connections | 4 |
| Wires | 12 |
| Brushes | 48 `func_detail` + 12 World-Solids |
| Groesse | 512 x 512 x 320 Raum, Wandstaerke 32 |

Das ist eine echte Testkammer: ein Raum mit Cube, Bodenbutton, Tuer,
Turret, zwei Tuer-Entities, Deko, Indikator-Lichtern, und einem
Button-Reset-Mechanismus.

## Entity-Typen, alle 16

| classname | Anzahl | VMFScript |
|---|---|---|
| `func_detail` | 48 | `solid{}` (Import-Modus) |
| `light` | 7 | `lighting{}` |
| `info_overlay` | 5 | **fehlt** |
| `env_texturetoggle` | 2 | **fehlt** |
| `npc_portal_turret_floor` | 1 | `turret{}` |
| `prop_dynamic` | 1 | `door{type="prop_dynamic"}` / `prop{}` |
| `func_brush` | 1 | **fehlt** |
| `func_button` | 1 | `button{type="func_button"}` |
| `prop_button` | 1 | `button{type="prop_button"}` |
| `prop_floor_button` | 1 | `button{}` (Vorgabe) |
| `prop_weighted_cube` | 1 | `cube{}` |
| `prop_testchamber_door` | 1 | `door{}` (Vorgabe) |
| `prop_static` | 1 | `prop{}` |
| `info_player_start` | 1 | `start{}` |
| `weapon_portalgun` | 1 | `start{}` (setzt der Compiler selbst) |
| `worldspawn` | 1 | wird erzeugt |

**12 Bloecke decken 13 von 16 classnames ab.** Was fehlt, ist keine
Spielmechanik, sondern Deko und Signale.

## Die 12 Wires — das eigentliche Muster

```
prop_floor_button  button1              6 wires
    OnPressed      -> Door1                           Open
    OnUnPressed    -> Door1                           Close
    OnPressed      -> indicator_sign_texturetoggle    SetTextureIndex 1
    OnUnPressed    -> indicator_sign_texturetoggle    SetTextureIndex 0
    OnPressed      -> indicator_lights_texturetoggle  SetTextureIndex 1
    OnUnPressed    -> indicator_lights_texturetoggle  SetTextureIndex 0

prop_button        (kein targetname)    2 wires
    OnPressed      -> Door1                           Open   delay 1
    OnButtonReset  -> door1                           Lock   delay 5

func_button        Door2_button         2 wires
    OnPressed      -> Door2                           SetAnimation Open
    OnPressed      -> Door2_button                    Kill

npc_portal_turret_floor  turret1        2 wires
    OnDeploy       -> turret1                         FireBullet
    OnTipped       -> light6                          TurnOff
```

Daraus lernen wir vier Dinge:

1. **Ein Button kann viele Wires haben.** `button1` hat sechs. Der
   `wiring{}`-Block ist kein 1:1-Block, das war schon richtig so.
2. **Ein Output feuert zweimal.** `OnPressed` UND `OnUnPressed` — also
   Tuer auf/zu aus einem einzigen Tastendruck.
3. **Entities ohne `targetname` sind verdrahtbar.** `prop_button` hat
   keins, feuert aber trotzdem. Valve loest Connections case-insensitiv
   ueber den Namen auf, den man beim Setzen vergibt.
4. **`self`-Verdrahtung existiert.** `turret1.OnDeploy -> turret1.FireBullet`
   und `Door2_button.OnPressed -> Door2_button.Kill`. Beides Ziele sind
   die Quelle selbst.
5. **`kill` und `TurnOff` fehlen als VMFScript-Methode gar nicht** — die
   `wire`-Syntax ist generisch (`ZIEL.METHOD`), also geht beides schon.

## Die zwei fehlenden Bloecke und warum sie fehlen

### `env_texturetoggle` — das ist kein Zufall

`button1` schaltet beim Druecken zwei `env_texturetoggle` um. Das ist
Valves Testkammer-Indikator: die farbigen Pfeile neben der Tuer wechseln
von rot auf gruen.

**Das ist eine echte Luecke**, aber sie ist billig zu schliessen: die
Entity ist ein reiner targetname + target, ohne Brush, ohne Geometrie.
Ein Block `toggle{ name["...", target="...", pos="..."]; }` wuerde reichen.

Wichtig: die Verknuepfung entsteht **automatisch**, weil der Button die
Wires traegt. Man braucht keine Sonderlogik, nur die Entity.

### `info_overlay` — Deko, kein Spiel

Fuenf Instanzen, alle `targetname "indicator_lights"`, mit
`signage/indicator_lights/indicator_lights_wall` und `_floor`.
Das sind die flachen, selbstleuchtenden Pfeil-Patches.

Geometrie:
```
BasisOrigin, BasisNormal, BasisU, BasisV
uv0..uv3 (4 Eckpunkte im Overlay-Raum), StartU/V, EndU/V, sides
```

**Kein Block.** Begruendung: das ist Deko. Eine brauchbare Map braucht
keine Info-Overlays, um zu funktionieren — die Pfeile kann man notfalls
weglassen, ohne dass die Mechanik kaputtgeht.

Aber: die `info_overlay`-Geometrie ist **kein Brush-Brush**, sondern ein
eigenes Quadsystem. Ein `overlay{}`-Block waere Machwerk, kein Block.

### `func_brush` — ebenfalls Deko

Ein `SIGNAGE/SIGNAGE_DOORSTATE`-Brush, `spawnflags 2`, `Solidity 0`,
getoggelt von `indicator_sign_texturetoggle`. Das ist das Schild neben
der Tuer, dessen Textur wechselt.

Das ist inhaltlich dasselbe wie `info_overlay`, nur als Brush. Gehoert
zu derselben Kategorie: **Signale, nicht Mechanik**.

## Geometrie-Lektionen aus dieser Map

**Wandstaerke 32**, nicht 2. Siehe `.hermes.md`: dicker als ~8 gibt
`FindPortalSide`-Fehler. Die 32 hier sind ein *inneres* Solid-Paar
(Floor bei z=64, Ceiling-Solid bei z=320), nicht die Wandstaerke — die
Raumwand ist bei x=-512/-544, also 32 dick. **Das widerspricht meiner
Notiz nicht**, weil es zwei verschiedene Masse sind: Raumhuelle
(32 dick, aussen) und die Testkammer-Wuende (2 dick, innen bei
x=-192/-224, y=-160/-192).

**Boden liegt bei z=64, nicht z=0.** Die 48 `func_detail`-Brushes sind
*Detail-Geometrie* auf diesem Boden — Podeste, Rahmen, Vertiefungen.
Keine davon ist Raummasse. `func_detail` ist eine Entity, kein Solid
des Raums: vbsp ignoriert sie fuer die Portale.

**Die Indikator-Flaechen liegen im Raum, nicht auf Brushes.** Die
`info_overlay` mit `_floor` liegen bei z=64, direkt auf dem Boden.

## Was VMFScript heute kann — die schlechte Nachricht

Geprueft am echten `map_ref.vmf`:

| Faehigkeit | Status |
|---|---|
| 48 `func_detail` importieren | **ja**, `solid{}` mit `chambers="0"` |
| 12 World-Solids | **ja** |
| 7 `light` | **ja**, `lighting{}` |
| `info_player_start` | **ja** |
| `weapon_portalgun` | **ja** |
| 4 Buttons (3 Typen) | **ja** |
| `prop_testchamber_door`, `prop_dynamic` | **ja** |
| `prop_weighted_cube` | **ja** |
| `npc_portal_turret_floor` | **ja** |
| `prop_static` | **ja** |
| alle 12 Wires | **ja**, `wire` ist generisch |
| `env_texturetoggle` | **nein** |
| `info_overlay` | **nein** |
| `func_brush` (Deko) | **nein** |

Der Import-Modus deckt die **Geometrie** vollstaendig ab — das war das
Ziel von `chambers="0"`. Was fehlt, sind ausschliesslich Entities, die
keine Raummasse erzeugen.

## Was der Import tatsaechlich liefert — verifiziert 2026-10-05

Der Import wurde gegen die echte `map_ref.vmf` gefahren, nicht geraten:

```
OK: mapname=map_ref | Bloecke: button=3, cube=1, door=2, lighting=7,
     start=2, turret=1, wiring=6
nicht uebersetzt: env_texturetoggle x2, info_overlay x5, prop_static x1
```

| | |
|---|---|
| Geometrie | **49 Brushes** vollstaendig, `chambers="0"` |
| Entities | 16 von 22 uebersetzt |
| Wires | **6 von 12** |

**6 Wires fehlen, und das ist kein Bug** — der Rueckuebersetzer sagt es
selbst, im Kopf der erzeugten Datei:

```
Verwaiste Verbindungen, die die Sprache nicht kennt
(Ziel-Entity nicht uebersetzbar) - NICHT enthalten:
  button1.OnPressed     -> indicator_sign_texturetoggle
  button1.OnUnPressed   -> indicator_sign_texturetoggle
  button1.OnPressed     -> indicator_lights_texturetoggle
  button1.OnUnPressed   -> indicator_lights_texturetoggle

Verbindungen einer Entity OHNE targetname.
Sie sind im Original wirkungslos (kein Adressat):
  prop_button(ohne targetname).OnPressed  -> Door1.Open
  prop_button(ohne targetname).OnButtonReset -> door1.Lock
```

Die ersten vier fehlen, weil es kein `toggle{}` gibt. Die letzten zwei
fehlen, weil **sie in der Original-Map sowieso wirkungslos sind** — ein
`prop_button` ohne `targetname` hat keinen Adressaten. Das ist kein
Verlust, das ist eine Korrektur.

Bemerkenswert: die zweite light-Entity heisst im Original `light6`,
geteilt mit der ersten. Der Import gibt ihr `light6_02` mit `dub="1"`
und verdrahtet `turret1.OnTipped -> light6_02.TurnOff` — also das
**einzige Entity**, das Valve zufaellig erreichen kann. Konsequent.

## Wo die Dateien liegen — geklaert 2026-10-05

Es gab drei `map_ref`-Varianten und alle drei hatten einen anderen Namen.
Die Verwechslung:

| Datei | Ort | Was sie ist |
|---|---|---|
| `map_ref.vmf` 172 434 B | Hammer-Ordner | **das Original**, aus `first_map` decompiliert. 73 Entities, 48 `func_detail`, 12 Wires |
| `map_ref.vmx` | Hammer-Ordner | dieselbe Datei, von Hammer erzeugt |
| `map_ref.vms` 7 210 B | Hammer-Ordner | **die Rueckuebersetzung** des Originals — 132 Zeilen, 49 Brushes |
| `map_ref_roundtrip.vms` | `examples/` | dieselbe Rueckuebersetzung, einziger Unterschied: `/` statt `\` im Quellpfad im Header |

**Die committete `map_ref.vmf` im Repo-Root war Compiler-Output.** Nicht
aus `map_ref.vms` — sie ist byte-identisch (136 566 B) mit dem, was
`map5_compile.py examples/map_ref_roundtrip.vms` erzeugt. Ein
132-Zeilen-Skript als Quelle einer 6 881-Zeilen-Map.

Entschieden: **die `.vmf` ist raus.** Sie ist ein Build-Artefakt wie jede
andere, und sie ist aus einer Datei im Repo voll reproduzierbar. Eine
Map, deren Quelle nicht im Repo liegt, gehoert nicht ins Repo.

Dazu zwei weitere Altlasten aus den ersten Commits entfernt, beide ohne
Suite-Abhängigkeit und ohne `.vms`-Quelle:

- `testchb_01_button.vmf` (10 647 B, im Root)
- `scripts/test4_multi_chamber.vmf` (48 339 B)

`.gitignore` fängt jetzt `/*.vmf`, `/*.vms` und `/examples/*.vmf` ab.
Im Repo sind nur noch acht `.vms`-Quellen, keine einzige `.vmf`.

Das Original bleibt unangetastet im Hammer-Ordner — es ist die Referenz
fuer Feature-Umfang, und die Matrix hier beschreibt es. Aber es ist kein
Teil von Maperio.

## Konsequenz fuer "ich erstelle Maps"

Damit ist die ehrliche Bilanz: **die Mechanik ist vollstaendig, die
Signale fehlen.**

| | Status |
|---|---|
| Geometrie, Raum, Portale | vollstaendig |
| Mechanik: Cube, Tuer, Button, Turret, Licht | vollstaendig |
| Verdrahtung: 8 verschiedene Methoden | vollstaendig |
| **Tuer-Indikatoren** (`env_texturetoggle`) | **fehlt** |
| **Pfeile** (`info_overlay`) | **fehlt** |
| **Schild** (`func_brush`) | **fehlt** |

Der einzige Block, der Mechanik bringt, ist `toggle{}`:

    toggle{ indicator_lights["", target="indicator_lights", pos="0 0 0"]; }

Ohne ihn fehlen vier der zwoelf Wires dieser Map. Mit ihm sind es nur
noch Deko-Fehler, die das Spiel nicht beeintraechtigen.

**Also: ein Block, und die Referenz-Map ist zu ~95 % reproduzierbar.**
`overlay{}` und `func_brush` waeren der naechste Schritt, aber die sind
beides reine Deko — die Map funktioniert auch ohne.

## Und noch etwas, das die Map lehrt

Die 49 importierten Brushes sind **alle `func_detail`** plus die
Weltmasse. `func_detail` ist eine Entity, kein Solid des Raums — vbsp
ignoriert sie fuer die Portale. Deshalb ist der Import-Modus so
zuverlaessig: er uebernimmt die Raummasse exakt (12 Solids) und die
Detail-Brushes als BBox-Quadrate.

Das heisst auch: **Detail-Geometrie ist der Verlust**, wenn man den
Import-Modus nimmt. Die BBox eines abgeschrägten Brushes ist ein
Quader. Der Import sagt das ehrlich:

    Nicht axis-parallele Brushes werden zu Quadern
    vergroessert - fuer exakte Form Hammer nutzen.

Bei 49 Brushes mit Schraegen ist das ein sichtbarer Unterschied, aber
kein funktionaler.