#!/usr/bin/env python3
"""map_gui.py - Kleine GUI fuer VMFScript 5.0 (Portal 2).

Weisses Fenster, Texteditor, Buttons. Drei Aufgaben:

  1. VMF laden und nach VMFScript uebersetzen
  2. VMFScript laden und nach VMF uebersetzen
  3. Text bearbeiten und speichern
  Bonus: vms -> vmf -> vbis -> vvis -> vrad (--compile)

Start:
    python map_gui.py

Kein externes GUI-Paket noetig (tkinter, Standardbibliothek).
"""

import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import vmf_to_vms
import map5_compile as v5
import map_viewer

P2_BIN = r"C:\Program Files (x86)\Steam\steamapps\common\Portal 2\bin"
P2_GAME = r"C:\Program Files (x86)\Steam\steamapps\common\Portal 2\portal2"
P2_MAPS = os.path.join(P2_GAME, "maps")


class MaperioGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VMFScript 5.0 - Portal 2")
        self.geometry("1000x700")
        self.minsize(760, 520)

        self.current_path = None   # .vms oder .vmf, je nachdem was geladen ist
        self.current_kind = None   # "vms" | "vmf"

        self._build()

    # ------------------------------------------------------------------
    def _build(self):
        # Muss VOR _build() existieren, weil die Toolbar es benutzt.
        self._testroom_var = tk.BooleanVar(value=False)

        # --- Toolbar ---
        bar = ttk.Frame(self, padding=(8, 8, 8, 4))
        bar.pack(fill="x")

        ttk.Button(bar, text="VMF -> VMFScript",
                   command=self.load_vmf).pack(side="left", padx=(0, 6))
        ttk.Button(bar, text="VMFScript -> VMF",
                   command=self.load_vms).pack(side="left", padx=(0, 6))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(bar, text="Speichern",
                   command=self.save).pack(side="left", padx=(0, 6))
        ttk.Button(bar, text="Speichern als...",
                   command=self.save_as).pack(side="left", padx=(0, 6))
        ttk.Button(bar, text="Neu", command=self.new_file).pack(side="left")

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Checkbutton(bar, text="Testkammer", variable=self._testroom_var
                        ).pack(side="left")
        ttk.Button(bar, text="Kompilieren (vbsp/vvis/vrad)",
                   command=self.compile_map).pack(side="left", padx=(8, 0))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(bar, text="3D-Vorschau",
                   command=self.show_viewer).pack(side="left")

        # --- Dateileiste ---
        frow = ttk.Frame(self, padding=(8, 0, 8, 4))
        frow.pack(fill="x")
        ttk.Label(frow, text="Datei:").pack(side="left")
        self.lbl_path = ttk.Label(frow, text="(neu)", foreground="#555555")
        self.lbl_path.pack(side="left", padx=(6, 0))

        # --- Editor ---
        wrap = ttk.Frame(self, padding=(8, 0, 8, 8))
        wrap.pack(fill="both", expand=True)
        self.txt = tk.Text(wrap, wrap="none", undo=True, font=("Consolas", 11))
        ys = ttk.Scrollbar(wrap, orient="vertical", command=self.txt.yview)
        xs = ttk.Scrollbar(wrap, orient="horizontal", command=self.txt.xview)
        self.txt.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.txt.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        # --- Log ---
        lrow = ttk.Frame(self, padding=(8, 0, 8, 8))
        lrow.pack(fill="x")
        self.log = tk.Text(lrow, height=8, wrap="word", state="disabled",
                           font=("Consolas", 9), background="#f4f4f4")
        self.log.pack(fill="both", expand=False)

        self.new_file()

    # ------------------------------------------------------------------
    # Helfer
    # ------------------------------------------------------------------
    def _log_geometry(self, comp, vmf_path):
        """Logt die erzeugte Geometrie: Kammern, Brushes, Öffnungen."""
        lay = getattr(comp, "layout", None)
        solids = getattr(comp, "geo", None)
        n = len(solids.world) if solids is not None else 0
        if lay is None:
            self._log("Geometrie: keine layout-Sektion "
                      "(Platzhalter-Huelle um die Entities)")
            return
        parts = ["Geometrie: chambers=%d" % lay["chambers"],
                 "%dx%dx%d" % (lay["width"], lay["length"], lay["height"]),
                 "%d Solid(s)" % n]
        if lay["solids"]:
            parts.append("%d solid{-Block(s)}" % len(lay["solids"]))
        self._log("  " + ", ".join(parts))

    def _log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_text(self, content):
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", content)

    def _get_text(self):
        return self.txt.get("1.0", "end-1c")

    def _editor_matches_disk(self, path):
        """True, wenn der Editor exakt den Inhalt der Datei zeigt."""
        try:
            with open(path, encoding="utf-8") as f:
                return f.read() == self._get_text()
        except (OSError, UnicodeDecodeError):
            return False

    def _mark(self, path, kind):
        self.current_path = path
        self.current_kind = kind
        self.lbl_path.configure(text=path or "(neu)")
        self.title("VMFScript 5.0 - Portal 2"
                   + (" - " + os.path.basename(path) if path else ""))

    def new_file(self):
        self._set_text('mapname = "meine_kammer";\n\n'
                       'start{\n'
                       '  player["Start", pos="256 512 64", yaw="90"];\n'
                       '}\n')
        self._mark(None, None)
        self._log("Neue Datei. Syntax-Rahmen: Bloecke + wire[]. "
                  "Siehe syntax/vmfscript5.0_p2_draft.txt")

    # ------------------------------------------------------------------
    # 1. VMF -> VMFScript
    # ------------------------------------------------------------------
    def load_vmf(self):
        path = filedialog.askopenfilename(
            title="Portal-2-VMF laden (wird nach VMFScript uebersetzt)",
            filetypes=[("VMF-Dateien", "*.vmf"), ("Alle Dateien", "*.*")])
        if not path:
            return
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
            code, tr = vmf_to_vms.translate(text, path)
        except Exception as exc:                      # noqa: BLE001
            self._log("FEHLER: %s" % exc)
            messagebox.showerror("VMF laden", str(exc))
            return
        self._set_text(code)
        out = os.path.splitext(path)[0] + ".vms"
        self._mark(out, "vms")
        counts = {k: len(v) for k, v in sorted(tr.blocks.items())}
        self._log("VMF -> VMFScript: %s" % os.path.basename(path))
        self._log("  Bloecke: %s" % ", ".join("%s=%d" % kv for kv in counts.items()))
        if tr.notes:
            seen = {}
            for c in tr.notes:
                seen[c] = seen.get(c, 0) + 1
            self._log("  nicht uebersetzt: %s"
                      % ", ".join("%s x%d" % kv for kv in sorted(seen.items())))
        self._log("  Geometrie (Solids/func_detail) ist NICHT enthalten.")

    # ------------------------------------------------------------------
    # 2. VMFScript -> VMF
    # ------------------------------------------------------------------
    def load_vms(self):
        path = filedialog.askopenfilename(
            title="VMFScript-Datei laden",
            filetypes=[("VMFScript", "*.vms"), ("Alle Dateien", "*.*")])
        if not path:
            return
        try:
            self._set_text(open(path, encoding="utf-8").read())
        except Exception as exc:                      # noqa: BLE001
            self._log("FEHLER: %s" % exc)
            messagebox.showerror("VMFScript laden", str(exc))
            return
        self._mark(path, "vms")
        self._log("VMFScript geladen: %s" % os.path.basename(path))

    def to_vmf(self):
        """Uebersetzt den Editor-Inhalt in eine .vmf. Gibt den Pfad zurueck.

        Der Editor-Inhalt ist die Quelle der Wahrheit. Die Datei auf der
        Platte wird nur dann gelesen, wenn der Editor unveraendert ist UND
        eine .vms geladen wurde - sonst wuerde eine bearbeitete Datei
        stillschweigend verworfen.
        """
        tmp_vms = None
        try:
            src = self.current_path
            use_disk = (src and self.current_kind == "vms"
                        and os.path.exists(src) and self._editor_matches_disk(src))
            if use_disk:
                vms_path = src
            else:
                tmp_vms = os.path.join(
                    os.environ.get("TEMP", _HERE), "_map_gui_tmp.vms")
                with open(tmp_vms, "w", newline="\n", encoding="utf-8") as f:
                    f.write(self._get_text())
                vms_path = tmp_vms
            out_vmf = os.path.splitext(vms_path)[0] + ".vmf"
            if os.path.abspath(out_vmf) == os.path.abspath(
                    os.path.join(P2_MAPS, os.path.basename(out_vmf))):
                raise SystemExit("Ziel liegt im Portal-2-maps-Ordner. "
                                 "Bitte anderswo speichern.")
            name, blocks = v5.parse_blocks(open(vms_path, encoding="utf-8").read())
            comp = v5.Compiler5(name)
            comp.testroom = self._testroom_var.get()
            order = ["layout", "solid", "start", "envlight", "lighting",
                     "door", "button", "cube", "turret", "wiring"]
            for key in order:
                h = getattr(comp, "blk_" + key, None)
                if h is None:
                    continue
                for e in blocks.get(key, []):
                    h(e)
            for key in blocks:
                if key not in order:
                    raise SystemExit("Unbekannter Block: %s" % key)
            content = comp.render()
            with open(out_vmf, "w", newline="\n", encoding="utf-8") as f:
                f.write(content)
            self._log("VMF erzeugt: %s (%d Bytes, %d Entities, %d Wires)"
                      % (out_vmf, os.path.getsize(out_vmf),
                         len(comp.ents), len(comp.wires)))
            self._log_geometry(comp, out_vmf)
            return out_vmf
        except SystemExit as e:
            # Klare Compiler-Meldung (z. B. falscher Dateityp) als Dialog zeigen.
            msg = str(e) if str(e) else "Unbekannter Fehler."
            self._log("FEHLER: " + msg.splitlines()[0])
            messagebox.showerror("VMF erzeugen", msg)
            return None
        except Exception as exc:                      # noqa: BLE001
            self._log("FEHLER: %s" % exc)
            messagebox.showerror("VMF erzeugen", str(exc))
            return None
        finally:
            if tmp_vms and os.path.exists(tmp_vms):
                try:
                    os.remove(tmp_vms)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # 3. Kompilieren
    # ------------------------------------------------------------------
    def show_viewer(self):
        """3D-Vorschau der aktuellen Geometrie.

        Quelle ist, was gerade im Editor steht: bei einer .vms wird der
        Compiler im Speicher befragt (keine Datei geschrieben), bei einer
        .vmf direkt die Datei. So sieht man die Vorschau immer fuer den
        Stand, der wirklich editiert wird.
        """
        text = None
        quelle = ""

        if self.current_kind == "vmf" and self.current_path and \
                os.path.exists(self.current_path):
            try:
                with open(self.current_path, encoding="utf-8",
                          errors="replace") as f:
                    text = f.read()
                quelle = os.path.basename(self.current_path)
            except OSError as exc:
                self._log("Vorschau: Datei nicht lesbar: %s" % exc)
                return
        else:
            # Aus dem Editor-Text uebersetzen
            vms = self._get_text()
            if not vms.strip():
                self._log("Vorschau: Editor ist leer.")
                return
            name = "vorschau"
            if self.current_path:
                name = os.path.splitext(os.path.basename(self.current_path))[0]
            try:
                text = v5.render_vmf(vms, name) if hasattr(v5, "render_vmf") \
                    else self._compile_to_text(vms, name)
            except Exception as exc:
                self._log("Vorschau: Uebersetzen fehlgeschlagen: %s" % exc)
                return
            quelle = name + " (aus Editor)"

        if not text or "solid" not in text:
            self._log("Vorschau: keine Brush-Geometrie gefunden.")
            return

        win = tk.Toplevel(self)
        win.title("3D-Vorschau - " + quelle)
        win.geometry("1040x700")
        v = map_viewer.Viewer(win, height=620)
        v.pack(fill="both", expand=True)
        # Decke aus: sonst verdeckt sie alles
        v.ceil_var.set(True)
        if v.load_vmf_text(text, include_nodraw=True):
            self._log("Vorschau: %s geoeffnet." % quelle)
        else:
            self._log("Vorschau: keine Brush-Geometrie in %s." % quelle)

    def _compile_to_text(self, vms, name):
        """Compiler im Speicher befragen, ohne Datei zu schreiben."""
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), "_map_preview.vms")
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(vms + "\n")
        try:
            import io
            import contextlib
            buf = io.StringIO()
            argv = sys.argv
            sys.argv = ["map5_compile.py", tmp, "-o",
                        os.path.join(tempfile.gettempdir(),
                                     "_map_preview.vmf")]
            try:
                with contextlib.redirect_stdout(buf):
                    v5.main()
            finally:
                sys.argv = argv
            out = sys.argv[3] if len(sys.argv) > 3 else None
            vmffile = os.path.join(tempfile.gettempdir(), "_map_preview.vmf")
            with open(vmffile, encoding="utf-8", errors="replace") as f:
                return f.read()
        finally:
            for suf in (".vms", ".vmf"):
                p = os.path.join(tempfile.gettempdir(), "_map_preview" + suf)
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass

    def compile_map(self):
        if not os.path.isdir(P2_MAPS):
            self._log("P2-maps-Ordner fehlt: %s" % P2_MAPS)
            messagebox.showerror("Kompilieren", "P2-maps-Ordner fehlt.")
            return
        vmf = self.to_vmf()
        if not vmf:
            return
        stem = os.path.splitext(os.path.basename(vmf))[0]
        target = os.path.join(P2_MAPS, stem + ".vmf")
        if os.path.abspath(vmf) != os.path.abspath(target):
            import shutil
            shutil.copyfile(vmf, target)
        for tool in ("vbsp", "vvis", "vrad"):
            exe = os.path.join(P2_BIN, tool + ".exe")
            if not os.path.exists(exe):
                self._log("%s.exe fehlt: %s" % (tool, exe))
                messagebox.showerror("Kompilieren", "%s.exe fehlt." % tool)
                return
            self._log("--- %s (in %s) ---" % (tool, P2_MAPS))
            try:
                p = subprocess.run([exe, "-game", P2_GAME, stem],
                                   cwd=P2_MAPS, capture_output=True, text=True)
            except Exception as exc:                  # noqa: BLE001
                self._log("FEHLER beim Start von %s: %s" % (tool, exc))
                return
            for line in (p.stdout + p.stderr).splitlines():
                if line.strip():
                    self._log("   " + line)
            self._log("%s EXIT %d" % (tool, p.returncode))
            if p.returncode != 0:
                messagebox.showerror(
                    "Kompilieren", "%s endete mit EXIT %d.\n\n%s"
                    % (tool, p.returncode, (p.stdout + p.stderr)[-1500:]))
                return
        bsp = os.path.join(P2_MAPS, stem + ".bsp")
        self._log("FERTIG: %s (%d Bytes)" % (bsp, os.path.getsize(bsp)))
        messagebox.showinfo("Kompilieren",
                            "Fertig.\n\n%s\n\n%d Bytes\n\n"
                            "Start in Portal 2 mit: map %s"
                            % (bsp, os.path.getsize(bsp), stem))

    # ------------------------------------------------------------------
    # Speichern
    # ------------------------------------------------------------------
    def save(self):
        if not self.current_path:
            return self.save_as()
        try:
            with open(self.current_path, "w", newline="\n",
                      encoding="utf-8") as f:
                f.write(self._get_text())
        except Exception as exc:                      # noqa: BLE001
            messagebox.showerror("Speichern", str(exc))
            return None
        self._log("Gespeichert: %s" % self.current_path)
        return self.current_path

    def save_as(self):
        ext = ".vms" if self.current_kind != "vmf" else ".vmf"
        path = filedialog.asksaveasfilename(
            title="Speichern als", defaultextension=ext,
            filetypes=[("VMFScript", "*.vms"), ("VMF", "*.vmf"),
                       ("Alle Dateien", "*.*")])
        if not path:
            return None
        self._mark(path, "vms" if path.lower().endswith(".vms") else "vmf")
        return self.save()


def main():
    app = MaperioGui()
    app.mainloop()


if __name__ == "__main__":
    main()