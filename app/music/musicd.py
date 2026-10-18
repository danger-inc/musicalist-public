#!/usr/bin/env python3
# musicalist: YouTube-Music-Player im TUI-Stil. Läuft dauerhaft im Hintergrund (Start aus hyprland.lua über
# ~/.local/bin/rice-music --daemon), damit Super+M sofort öffnet und die Musik bei geschlossenem Fenster
# weiterspielt. Steuerung über die Leitung $XDG_RUNTIME_DIR/rice-music.fifo:
#   toggle | show | hide | play-pause | next | prev | search:<begriff+mit+plus>
# Braucht LD_PRELOAD=libgtk4-layer-shell.so (für die Vorschau-Karte) – setzt rice-music.
import os, signal, sys, warnings

os.environ.setdefault("GSK_RENDERER", "cairo")  # gleiche Optik, halber Speicher
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE)]
import tui  # noqa: E402
from tui import Gio, GLib, Gtk  # noqa: E402
import engine, sources, ui  # noqa: E402

# Die Layer-Shell-Bibliothek ist jetzt geladen – nicht an gestartete Programme weitervererben
# (Zen stürzt damit ab: "browser"-Knopf; mpv, cava, yt-dlp/node brauchen sie auch nicht).
for _var in ("LD_PRELOAD", "GSK_RENDERER"):
    os.environ.pop(_var, None)

FIFO = engine.RUNTIME + "/rice-music.fifo"
PID_FILE = engine.RUNTIME + "/rice-music.pid"


class App(Gtk.Application):
    def __init__(self, show):
        super().__init__(application_id="de.invincible.Music", flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.show_first = show

    def do_activate(self):
        self.hold()
        tui.Theme.get()
        self.player = engine.Player()
        self.cava = ui.Cava()
        self.sources = sources.Sources()
        self.win = ui.MusicWindow(self, self.player, self.cava, self.sources)
        self.preview = ui.Preview(self, self.player, self.cava, lambda: self.command("show"), self.sources)
        self.player.mpris.on_raise = lambda: self.command("show")
        if os.path.exists(FIFO):
            os.unlink(FIFO)
        os.mkfifo(FIFO, 0o600)
        self.fd = os.open(FIFO, os.O_RDWR | os.O_NONBLOCK)
        GLib.io_add_watch(self.fd, GLib.PRIORITY_HIGH, GLib.IOCondition.IN, self.on_fifo)
        with open(PID_FILE, "w") as f:
            f.write(f"{os.getpid()}\n")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for sig in (signal.SIGTERM, signal.SIGINT):
                GLib.unix_signal_add(GLib.PRIORITY_HIGH, sig, self.stop)
        if self.show_first:
            self.command("show")
        else:
            GLib.idle_add(lambda: self.win.realize() and False)  # erstes Öffnen ohne Verzögerung

    def on_fifo(self, fd, _cond):
        try:
            data = os.read(fd, 4096).decode(errors="ignore")
        except BlockingIOError:
            return True
        for cmd in data.split():
            self.command(cmd)
        return True

    def command(self, cmd):
        w, p = self.win, self.player
        if cmd == "toggle":
            if w.get_visible() and w.is_active():
                w.set_visible(False)
            else:
                self.preview.hide()
                w.present()
        elif cmd == "show" or cmd.startswith("show:"):  # show:lyrics öffnet direkt einen Tab
            self.preview.hide()
            w.present()
            if ":" in cmd:
                w.show_tab(cmd.split(":", 1)[1])
        elif cmd == "hide":
            w.set_visible(False)
        elif cmd == "play-pause":
            p.toggle()
        elif cmd == "next":
            p.next()
        elif cmd == "prev":
            p.prev()
        elif cmd.startswith("search:"):  # rice-music search:daft+punk
            w.query.set_text(cmd[7:].replace("+", " "))
            self.preview.hide()
            w.present()
            w.show_tab("search")
            w.do_search()

    def stop(self):
        self.player.shutdown()
        for path in (PID_FILE, FIFO):
            try:
                os.unlink(path)
            except OSError:
                pass
        self.quit()
        return False


if __name__ == "__main__":
    sys.exit(App("--show" in sys.argv).run(None))
