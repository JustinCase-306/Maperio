# VMFScript

A small toolchain that translates the **VMFScript block language** into ready
**Portal 2** `.vmf` files and back, plus a simple GUI to work with it.

Portal 2 is the target because its engine has real gameplay entities: one
`func_button` and one connection make a working button-and-door, while
Portal 1 (Half-Life 2 engine) needs a whole zoo of entities for the same job.

> **Authorship.** The **compiler implementation** (`scripts/`), this README, and
> the example files were **written by Hermes**, an AI coding agent
> (Nous Research), working for the repository owner. The **VMFScript language
> design** (`syntax/vmfscript3.0.txt` and the 5.0 draft) is the owner's own
> specification, which the compiler implements one-to-one.

## Quickstart

Double-click **`VMFScript.bat`** for the GUI, or use the command line:

```bash
# VMFScript -> VMF
python scripts/vmfs5_compile.py examples/test_floor_button_door.vms

# VMF -> VMFScript
python scripts/vmf_to_vms.py some_map.vmf -o some_map.vms

# VMF -> VMF -> BSP (runs vbsp + vvis + vrad)
python scripts/vmfs5_compile.py examples/test_floor_button_door.vms --compile
```

## Geometry

VMFScript builds complete test chambers. Geometry comes from two blocks:

```vms
layout{
  chambers["2", width="512", length="512", height="256",
           door_width="64", door_height="96", origin="0 0 0"];
}

solid{
  brush_01["0 0 0", "128 0 128", mat="TILE/WHITE_WALL_TILE003B"];
}
```

`layout` builds *n* chambers in a row along +Y, joined by walls with an
opening. `solid` adds individual axis-aligned brushes. `chambers="0"` builds no
chamber at all — that's the import mode, where the `solid` blocks already
describe the exact shape.

Why two chambers instead of one with a doorway: an opening needs solid
geometry on **both** sides. With a single chamber it opens onto empty space,
`vbsp` forms no portal, writes no `.prt`, reports every entity as
`leaked!`, and `vvis` fails with exit 1. Two chambers fix that.

Walls with an opening are built as **four** brushes (below, above, left,
right), not as a fine panel grid — a grid of touching brushes gives `vbsp` no
continuous solid face to attach a portal to.

Verified materials (taken from the reference maps):

| Surface | Material |
|---|---|
| Wall panels | `TILE/WHITE_WALL_TILE003B` |
| Floor | `CONCRETE/CONCRETE_MODULAR_FLOOR001C` |
| Ceiling | `TILE/OBSERVATION_TILECEILING001A` |
| Hidden sides | `TOOLS/TOOLSNODRAW` |

On round trip, `func_detail` / `func_detailwall` / `func_brush` become
`solid` blocks with their bounding boxes and materials. Non-axis-aligned
brushes grow into boxes — build exact shapes in Hammer.

## The GUI

`VMFScript.bat` (or `python scripts/vmfs_gui.py`) opens a plain white window
with a text editor and buttons:

| Button | What it does |
|---|---|
| **VMF → VMFScript** | Loads a `.vmf`, translates it into block syntax, shows it in the editor |
| **VMFScript → VMF** | Loads a `.vms` for editing |
| **Neu** | Fresh template |
| **Speichern / Speichern als…** | Writes the editor content |
| **Testkammer** | Adds a minimal test chamber as geometry |
| **Kompilieren** | Runs `vbsp` → `vvis` → `vrad` and reports the result |

The log pane at the bottom shows what happened, including which entities could
not be translated and why.

## VMFScript 5.0 syntax

```vms
mapname = "test_floor_button_door";

start{
  player["Start", pos="256 512 64", yaw="90"];
}

envlight{
  amb1[pos="512 512 400", power="200", ambient="30"];
}

lighting{
  light_01[pos="256 256 400", power="350"];
}

door{
  door1["Testkammertür", pos="512 1008 0", yaw="270"];
}

button{
  btn["Drücke mich", pos="512 800 8", type="prop_floor_button"];
}

wiring{
  wire["btn.OnPressed", "door1.Open", delay="0.5"];
}
```

Rules: blocks are `name{ … }` | lines are `label["text", key="val"];` |
comments are `##` (short) and `##* … *##` (long) | `wire` takes
`"SOURCE.EVENT", "TARGET.INPUT"` plus optional `param=` and `delay=`.

### Entity types

| Block | Portal 2 class |
|---|---|
| `start` | `info_player_start` (+ `weapon_portalgun`) |
| `button` | `prop_floor_button`, `prop_button`, `func_button` |
| `door` | `prop_testchamber_door`, `prop_dynamic`, `func_door` |
| `cube` | `prop_weighted_cube` |
| `turret` | `npc_portal_turret_floor`, `npc_portal_turret_panelled` |
| `lighting` | `light` |
| `envlight` | `light_environment` |

## The connection format

Every connection is five fields separated by an invisible ESC character
(`\x1b`):

```
"OnPressed"  "door1" ␛ "Open" ␛ "" ␛ "0.5" ␛ "-1"
                 f1       f2    f3     f4      f5
```

| # | Meaning | Value here |
|---|---|---|
| 1 | Target entity | `door1` |
| 2 | Input | `Open` |
| 3 | Parameter | `""` (e.g. an animation name) |
| 4 | **Delay** (seconds) | `0.5` |
| 5 | Repeat count | `-1` (once) |

`delay=` maps to field **4**, `param=` to field **3**. Verified against
`map_ref.vmf`.

## Important: compile from the Portal 2 maps folder

```bash
cd "C:\Program Files (x86)\Steam\steamapps\common\Portal 2\portal2\maps"
"C:\Program Files (x86)\Steam\steamapps\common\Portal 2\bin\vbsp.exe" \
  -game "C:\Program Files (x86)\Steam\steamapps\common\Portal 2\portal2" map
```

Run it from that folder. Anywhere else `vbsp` aborts with
`Can't create LogFile` and exit code 1. Always run `vrad` too — without it the
map has no lightmaps and stays black. `--compile` handles both for you.

## Layout

```
VMFScript.bat              # double-click starter for the GUI
scripts/
  vmfs_gui.py               # GUI: editor, buttons, log pane
  vmfs5_compile.py          # VMFScript 5.0 -> VMF (Portal 2)
  vmf_to_vms.py             # VMF -> VMFScript 5.0 (reverse direction)
  vmfs3_compile.py          # older 3.0 compiler (Portal 1), kept for reference
  generate_plain_portal_map.py  # map class: winding, solids, entity(), render()
  portalmap.py / portalmap2.py   # 1.0 / 2.0, kept for reference
examples/
  test_floor_button_door.vms # 5.0 example: button -> door
  test3.vms                  # 3.0 example
syntax/
  vmfscript5.0_p2_draft.txt  # 5.0 language draft + verified notes
  vmfscript3.0.txt           # owner's 3.0 specification
references/
  p2_map_ref_analysis.md     # analysis of the owner's reference maps
```

## Status

Verified 2026-10-01 with ad-hoc scripts (real runs, script exit 0 — this is
**not** a claim of a green canonical test suite; the project has none):

Geometry round trip (37/37):

- `test_chamber_two.vms` → 15 solids, 7 entities, two chambers with an
  opening → `vbsp`/`vvis`/`vrad` all exit 0 → 350 020-byte `.bsp`,
  no `leaked`, no `FindPortalSide`, no missing material
- `door_ref_01.vmf` → 48 `solid` lines → 48 solids with the source's exact
  panel dimensions (128 × 128, wall thickness 2), `vbsp` exit 0
- `map_ref.vmf` → 49 geometry brushes (48 panels + 1 `func_brush` sign) plus
  all entity blocks intact (7 lights, 2 doors, 3 buttons, 1 cube, 1 turret,
  6 wires)
- `chambers="0"` produces exactly the given `solid` brushes, no extra shell

Entity/toolchain checks (earlier run, 38/38):

- `test_floor_button_door.vms` → 7 entities, 2 wires, all three tools exit 0
- GUI: both directions, test chamber, every error path
- Legacy 3.0 compiler still runs

Known limits: non-axis-aligned brushes become boxes on import. Overlays
(`info_overlay` + `env_texturetoggle`) and `prop_static` decoration are still
not translated. The Entities-only placeholder shell is only used when no
`layout` block is present.