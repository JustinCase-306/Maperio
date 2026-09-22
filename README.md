# VMFScript

Minispielparser: übersetzt die **VMFScript-3.0-Block-Sprache** eins-zu-eins in eine
fertige **Portal-1**.vmf (Source/HL2-Engine) und optional direkt weiter mit dem
Portal-1-`vbsp` zu einer `.bsp`.

Entstanden für den deutschen Portal-1-Mapper, der nicht mehr lange, zeilenweise
VMF von Hand tippen will, sondern in Blöcken/Schlüssel-Wert-Code denkt.

## Schnellstart

```bash
python scripts/vmfs3_compile.py examples/test3.vms            # -> testchb_01_button.vmf
python scripts/vmfs3_compile.py examples/test3.vms --compile  # + Portal-1-vbsp (bsp)
```

## VMFScript 3.0 Syntax (verbindlich, Quelle `syntax/vmfscript3.0.txt`)

```python
mapname="testchb_01_button";
material{
    floor["concrete/concrete_modular_floor001a"];
    ceiling["concrete/concrete_modular_ceiling001a"];
    wall["plastic/plasticwall001b"];
};

##* hello this is a Long comment
which goes on and on
*##

chamber{
    sizex["1024"]; sizey["512"]; sizez["1024"];
    player["512, 512, 64"]; gun["560, 512, 64"];
};
## short comment
lighting{
    light_01[pos="300, 500, 380", power="255", color="255, 255, 200"];
};
buttons{  door_btn[pos="420, 700, 0"]; };
doors{    door_01[pos="512, 990, 0"]; };
wiring{
    wire["door_btn.OnPressed", "door_01.Open", delay="2"]; ## delay in seconds
};
```

Blöcke: `name { ... };` | Zeilen: `label["..."];` oder `label[key="val", key2="val"];`
| Werte in Anführungszeichen | Kommentare: `##` kurz, `##* ... *##` lang | `wire`:
5-Feld-ESC mit `delay` im Argument-Feld.

## Struktur

```
scripts/
  vmfs3_compile.py            # Compiler 3.0 (komplett, Block-Parser + Map-Aufrufe)
  generate_plain_portal_map.py# Map-Klasse: Winding, Solids, entity(), render()
  portalmap.py                # VMFScript 1.0 (ESC-Trenner)
  portalmap2.py               # VMFScript 2.0 (ESC+Komma, mehr Mechaniken)
examples/                     # .vms + .pml Beispiele
syntax/                       # vmfscript3.0.txt (Nutzer-Spezifikation) + Übergabe
```

## Wichtig: nur Portal 1 kompilieren

```bash
"C:\Program Files (x86)\Steam\steamapps\common\Portal\bin\vbsp.exe" \
  -game "C:\Program Files (x86)\Steam\steamapps\common\Portal\portal" meine.vmf
```

NIE den Portal-2-Compiler (`Portal 2\bin\vbsp.exe`) — der bricht mit Returncode
`0x1` ab. Einfache Maps brauchen keinen `env_cubemap`, nur `sky_black_nofog` +
`light`-Entities + Spawn/Portalgun.

## Status
Compiler `vmfs3_compile.py` + `test3.vms` verifiziert: `.vms` → `.vmf` →
Portal-1-`vbsp` → `.bsp` (EXIT 0). `delay` steht im Argument-Feld der
Verbindung — in Hammer zu prüfen, ob die Ziel-Methode einen Verzögerungsparameter nimmt.