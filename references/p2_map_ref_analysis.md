# VMFScript — Portal-2-Analyse von `map_ref.vmf`

Grundlage: `Documents/Portfolio/Hammer/Portal 2 Maps/vmfscript/map_ref.vmf`
(Headerkommentar: „Decompiled by BSPSource v1.4.7 from first_map")

Erstellt: 2026-10-01. Autor der Analyse: Hermes (AI-Coding-Agent).

---

## 1. Warum die Map sich nicht kompilieren ließ / dunkel war

### 1a. „Kann nicht kompilieren" → falscher Ausgabe-Ordner

`vbsp.exe` bricht mit `Can't create LogFile:"<pfad>\<name>.log"` und **EXIT 1** ab,
wenn es nicht im Game-Maps-Ordner läuft.

Nachgewiesen:

| Lauf | CWD / Ziel | Ergebnis |
|---|---|---|
| `Temp\p2compile\map_ref_compiletest.vmf` | Temp-Ordner | `Can't create LogFile` → EXIT 1 |
| `Temp\p2compile\minimal_p2.vmf` (frische Minimal-Map) | Temp-Ordner | `Can't create LogFile` → EXIT 1 |
| `...\Portal 2\portal2\maps\map_ref_compiletest.vmf` | P2-maps-Ordner | **EXIT 0**, `.bsp` 143 880 B |

Merksatz: **Das Verzeichnis der VMF muss der P2-Maps-Ordner sein**
(`C:\Program Files (x86)\Steam\steamapps\common\Portal 2\portal2\maps`),
sonst bricht vbsp vor dem Parsen ab. Der Pfad darf Leerzeichen enthalten,
wenn er als **natives Windows-Format** an `-game` übergeben wird.

### 1b. „Komplett dunkel" → vrad fehlte

`vbsp` erzeugt nur Geometrie + Entities, **keine Lichtmaps**.
Ohne `vrad.exe` (Radiosity) bleibt die Map schwarz.

Nachgewiesen: `vvis` EXIT 0, `vrad` EXIT 0,
`LDR lightdata 603 524 bytes`, `7 direct lights`, `Total triangle count: 288`.

---

## 2. P2-Entities in der Referenzmap (Ist-Bestand)

73 Entities insgesamt, davon 49× `func_detail` (Dekompilierungs-Artefakt),
5× `info_overlay`, 7× `light`.

### Gameplay

| Entity | targetname | origin | Aufgabe |
|---|---|---|---|
| `func_button` | `Door2_button` | -212 292 120 | Wandbutton (Brush-Entity, `spawnflags 1024`, `speed 5`, `wait 3`) |
| `prop_floor_button` | `button1` | -228.9 -340.286 72.36 | Bodenbutton, Modell `models/props/portal_button.mdl` |
| `prop_button` | – | -278.434 -80.997 65.26 | Kleiner Button, `Delay 1` |
| `prop_dynamic` | `Door2` | -208 292 64 | Tür, Modell `models/props_underground/underground_door_dynamic.mdl`, `angles 0 180 0` |
| `prop_testchamber_door` | `door1` | -448 -176 64 | Testkammer-Tür, `angles 0 270 0`, `AreaPortalWindow Door1` |
| `prop_weighted_cube` | `cube1` | -144 -272 83.03 | Companion-Cube, `PaintPower 4` |
| `npc_portal_turret_floor` | `turret1` | -92 110 64 | Bodenturm |
| `weapon_portalgun` | `portalgun` | -108 576 100 | Portalgun |
| `info_player_start` | – | -95.84 -320.22 65 | Spielerstart |

**Kein einziges `func_door`** in der Map — P2 nutzt `prop_dynamic` /
`prop_testchamber_door`. (`func_door` existiert in P2 trotzdem, FGD-Zeile 3671.)

### Licht / Deko

- 7× `light` (`light1`…`light7`), z. B. `light1` mit `_light "255 255 255 350"`,
  `_quadratic_attn 1`.
- 5× `info_overlay` namens `indicator_lights` mit
  `signage/indicator_lights/indicator_lights_wall` bzw. `..._floor`.
- 2× `env_texturetoggle` (`indicator_lights_texturetoggle`,
  `indicator_sign_texturetoggle`) schalten die Overlays.

---

## 3. Verdrahtung — das 5-Feld-Format (Ground Truth)

Alle 4 `connections`-Blöcke der Map:

```
// npc_portal_turret_floor "turret1"
"OnDeploy"  "turret1\x1bFireBullet\x1b\x1b0\x1b-1"
"OnTipped"  "light6\x1bTurnOff\x1b\x1b0\x1b-1"

// func_button "Door2_button"
"OnPressed" "Door2\x1bSetAnimation\x1bOpen\x1b0\x1b-1"
"OnPressed" "Door2_button\x1bKill\x1b\x1b0\x1b-1"

// prop_button
"OnPressed"      "Door1\x1bOpen\x1b\x1b1\x1b-1"
"OnButtonReset"  "door1\x1bLock\x1b\x1b5\x1b-1"

// prop_floor_button "button1"
"OnPressed"   "Door1\x1bOpen\x1b\x1b0.5\x1b-1"
"OnUnPressed" "Door1\x1bClose\x1b\x1b1\x1b-1"
"OnPressed"   "indicator_sign_texturetoggle\x1bSetTextureIndex\x1b1\x1b0.5\x1b-1"
"OnUnPressed" "indicator_sign_texturetoggle\x1bSetTextureIndex\x1b0\x1b1\x1b-1"
"OnPressed"   "indicator_lights_texturetoggle\x1bSetTextureIndex\x1b1\x1b0.5\x1b-1"
"OnUnPressed" "indicator_lights_texturetoggle\x1bSetTextureIndex\x1b0\x1b1\x1b-1"
```

### Feld-Belegung (Source-Engine-Standard)

| # | Inhalt | Beispiel | 3.0-Fehler? |
|---|---|---|---|
| 1 | Ziel-Entity | `Door2` | ✔ korrekt |
| 2 | Input | `SetAnimation` | ✔ korrekt |
| 3 | **Parameter** | `Open`, `1`, `0` | **3.0 legte hier den Delay ab → falsch** |
| 4 | **Delay** (Sekunden) | `0`, `1`, `0.5`, `5` | **in 3.0 nicht belegt** |
| 5 | Unbekannt (`-1` = einmalig) | `-1` | ✔ korrekt |

**Konsequenz:** In VMFScript 3.0 habe ich `delay="2"` in **Feld 3** geschrieben.
Das ist semantisch falsch — der Delay gehört in **Feld 4**,
Feld 3 ist der Parameter (z. B. der Animationsname `Open`).
Das erklärt, warum das Verhalten in Hammer nie geprüft/geklappt hat.

---

## 4. Was die neue P2-Sprache abbilden muss

**Viel kleiner als P1.** Ein Button = 1 Entity + 1 Wire.

```vms
button  = func_button / prop_floor_button / prop_button
door    = prop_dynamic / prop_testchamber_door / func_door
cube    = prop_weighted_cube
turret  = npc_portal_turret_floor
trigger = trigger_once / trigger_multiple
indicator = info_overlay + env_texturetoggle
light   = light  (P2 hat echte Light-Entities)
```

Der Syntaxrahmen (Block-Sprache `name{label["..."];}` + `wire[...]`)
kann **1:1 bleiben** — nur die dahinter liegenden Entity-Klassen ändern sich.

---

## 5. Offen / nächste Schritte

- Sprache als `vmfscript5.0.txt` (P2) entwerfen, vom Nutzer abnehmen.
- Compiler auf P2-Entity-Klassen umstellen (eigener Codepfad, kein P1-Altlast).
- Wire-Semantik: Feld 3 = Parameter, Feld 4 = Delay (3.0 korrigieren).
- Kompilier-Pipeline als Skript: `vbsp` → `vvis` → `vrad`, immer aus `portal2\maps`.