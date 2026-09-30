# VMFScript

A small compiler that translates the **VMFScript 3.0 block language** one-to-one
into a ready **Portal 1** `.vmf` file (Source/HL2 engine) and, optionally, runs
the Portal 1 `vbsp` on top to produce a playable `.bsp`.

Little mini-syntax designed for Portal-1 mappers who don't want to hand-type
long, line-by-line VMF — instead they think in blocks / key-value code.

> **Authorship.** The **compiler implementation** (`scripts/`), this README, and
> the example `.vms`/`.pml` files were **written by Hermes**, an AI coding agent
> (Nous Research), working for the repository owner. The **VMFScript 3.0
> language itself** (`syntax/vmfscript3.0.txt`) is the owner's own specification,
> which the compiler implements one-to-one.

## Quickstart

```bash
python scripts/vmfs3_compile.py examples/test3.vms            # -> testchb_01_button.vmf
python scripts/vmfs3_compile.py examples/test3.vms --compile  # + Portal-1 vbsp (.bsp)
```

## VMFScript 3.0 syntax (mandatory, source `syntax/vmfscript3.0.txt`)

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

Rules: blocks are `name { ... };` | lines are `label["..."];` or
`label[key="val", key2="val"];` | values are quoted | comments are `##` (short)
and `##* ... *##` (long) | `wire` uses the 5-field ESC form with `delay` in the
argument field.

## Layout

```
scripts/
  vmfs3_compile.py            # Compiler 3.0 (complete: block parser + map calls)
  generate_plain_portal_map.py# Map class: winding, solids, entity(), render()
  portalmap.py                # VMFScript 1.0 (ESC separator)
  portalmap2.py               # VMFScript 2.0 (ESC + comma, more mechanics)
examples/                     # .vms + .pml examples
syntax/                       # vmfscript3.0.txt (owner spec) + handover notes
```

## Important: compile with Portal 1 only

```bash
"C:\Program Files (x86)\Steam\steamapps\common\Portal\bin\vbsp.exe" \
  -game "C:\Program Files (x86)\Steam\steamapps\common\Portal\portal" meine.vmf
```

Never use the Portal 2 compiler (`Portal 2\bin\vbsp.exe`) — it aborts with return
code `0x1`. Simple maps need no `env_cubemap`, just `sky_black_nofog` +
`light` entities + spawn / portalgun.

## Status

Compiler `vmfs3_compile.py` + `test3.vms` verified: `.vms` → `.vmf` → Portal 1
`vbsp` → `.bsp` (exit 0). `delay` lives in the connection's argument field —
check in Hammer whether the target method takes a delay parameter.