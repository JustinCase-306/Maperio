# sign{} / func_brush — Status und Messungen

Stand 2026-10-05. Kurzfassung: **geometrisch korrekt, vbsp baut es nicht,
Ursache nicht gefunden.** Alles hier ist gemessen, nichts geraten.

## Der Fehler

```
Brush 5000: no visible sides on brush   (6x, einmal je Seite)
bmodel 9 has no head node (class 'func_brush', targetname '')
vbsp EXIT=1
```

`no head node` heisst: aus dem Solid wurde kein Koerper. Die Map wird nicht
gebaut, vvis/vrad auch nicht.

## Was funktioniert

| Test | Ergebnis |
|---|---|
| Solid aus der Entity entfernt | **vbsp EXIT 0** |
| Solid aus `map_ref.vmf` in dieselbe Map gesetzt | **vbsp EXIT 0** |
| dasselbe Solid um (+625, +705, +16) verschoben | **vbsp EXIT 0** |
| Referenz-Solid mit `origin 0 0 0` | **vbsp EXIT 0** |

Die func_brush ist also die Ursache, nicht das Solid allein.

## Was nicht hilft

Alle folgenden Varianten: **6× `no visible sides`, EXIT 1.**

| Variable | getestete Werte |
|---|---|
| Material | alle 6 SIGNAGE / alle 6 NODRAW / wie Referenz (5 NODRAW + 1 SIGNAGE) |
| Dicke | 1, 2, 3, 4, 5, 8 in y |
| Groesse | 32×1×32 · 16×1×32 · 8×1×8 · 2×1×2 · **1×1×1** |
| `Solidity` | 0 / 1 |
| `spawnflags` | 0 / 2 |
| `origin` | Mitte korrekt, 0 0 0, jede Achse einzeln |
| Entity-Keys | alle 20 Standard-Keys der Referenz (`solidbsp`, `renderamt`, `disableshadows`, …) |
| IDs | 200er / 300er / 5000er / ohne |
| Seitenreihenfolge | wie Referenz (x,x,y,y,z,z) |
| `uaxis`/`vaxis` | eigene pro Flaeche wie Referenz |
| Punktposition | Halbzahlen 507.5/508.5 gegen Ganzzahlen 508/509 |

**Auch 1×1×1 scheitert.** Das ist der entscheidende Ausschluss: es kann nicht
an der Geometrie liegen.

## Geometrische Pruefung

Mit exakten Bruechen (`fractions.Fraction`) geprueft, keine Naeherung:

- alle 6 Seiten planar (`Abstand p3 zur Ebene == 0`)
- je 4 verschiedene Punkte
- Winding identisch zur Referenz (Kreuzprodukt zeigt bei beiden nach innen)
- keine zwei Seiten teilen sich eine Ebene
- Origin = Mitte der 24 Punkte, exakt

## Der Unterschied, den ich nicht aufloese

Beide Solids sind ein Quader, 32 × 1 × 32, aus 8 Ecken. Die Referenz
funktioniert, meine Geometrie nicht — bei identischer Struktur,
identischen Werten, identischer Winding.

Getestet und verworfen, in dieser Reihenfolge:

1. Materialverteilung
2. Wandstaerke und Brush-Dicke
3. Entity-Keys
4. ID-Bereiche
5. `plane`-Zeilen und Punktreihenfolge
6. `uaxis`/`vaxis` pro Flaeche
7. Entity-Reihenfolge im File

## Was das wahrscheinlich ist

Nicht ermittelt. Zwei Kandidaten, beide unbewiesen:

- **`solidbsp` / `origin`-Semantik:** Bei Entity-Brushes ist `origin`
  nicht die Brush-Mitte, sondern ein Anker, und vbsp rechnet relativ
  dazu. Die Referenz ist ein **decompilierter BSP-Brush** (`map_ref.vmf`
  stammt aus BSPSource), mein Brush ist **neu berechnet**. Das könnte der
  Unterschied sein.
- **`spawnflags 2` plus `Solidity 0`:** verweist auf ein
  Brush-Brush-Verhalten, dessen Solid-Form ich nicht kenne.

Der Weg, der sicher weiterfuehrt: den Block in Hammer bauen, speichern,
den Solid-Dump vergleichen. Dann ist es eine Messung statt einer Vermutung.

## Fuer die Arbeit mit Maperio

`sign{}` ist nicht im Block-Dispatch. Wer es schreibt, bekommt:

```
func_brush mit Brush (block sign{}) baut noch nicht:
vbsp meldet 'no visible sides'.
env_texturetoggle (block toggle{}) funktioniert.
```

Das ist Absicht: eine Entity ohne Brush zu liefern waer schlimmer als
sich zu weigern. `references/map_ref_feature_matrix.md` fuehrt
`func_brush` als fehlend — mit diesem Link.

`toggle{}` ist davon nicht betroffen und verifiziert:
`vbsp/vvis/vrad EXIT 0`, 4 Wires auf den Indikator, kein leaked.