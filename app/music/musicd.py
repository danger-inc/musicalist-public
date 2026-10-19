#!/usr/bin/env python3
# musicalist: YouTube-Music-Player im TUI-Stil. Läuft dauerhaft im Hintergrund (Start aus hyprland.lua über
# ~/.local/bin/rice-music --daemon), damit Super+M sofort öffnet und die Musik bei geschlossenem Fenster
# weiterspielt. Steuerung über die Leitung $XDG_RUNTIME_DIR/rice-music.fifo:
#   toggle | show | hide | play-pause | next | prev | quit | search:<begriff+mit+plus>
#   token:<xdg-activation-token> davor: Startberechtigung vom Desktop (GNOME/KDE), damit das Fenster nach vorn darf.
# Fenster schließen (✕ / q / Alt+F4) beendet musicalist ganz – außer „im hintergrund weiterspielen“ ist an.
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

def _use_token(token):
    """Startberechtigung des Desktops an GTK geben (dann fragt present() nicht selbst an und blockiert nicht)."""
    try:
        gi = sys.modules["gi"]
        gi.require_version("GdkWayland", "4.0")
        from gi.repository import Gdk, GdkWayland
        display = Gdk.Display.get_default()
        if isinstance(display, GdkWayland.WaylandDisplay):
            display.set_startup_notification_id(token)
            return True
    except (ImportError, ValueError, AttributeError, KeyError):
        pass
    return False


FIFO = engine.RUNTIME + "/rice-music.fifo"
PID_FILE = engine.RUNTIME + "/rice-music.pid"


class App(Gtk.Application):
    def __init__(self, show):
        super().__init__(application_id="de.invincible.Music", flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.show_first = show
        self.token = None        # Startberechtigung aus dem Launcher (XDG_ACTIVATION_TOKEN)

    def do_activate(self):
        self.hold()
        tui.Theme.get()
        self.player = engine.Player()
        self.cava = ui.Cava()
        self.sources = sources.Sources()
        self.win = ui.MusicWindow(self, self.player, self.cava, self.sources)
        if ui.preview_supported():
            self.preview = ui.Preview(self, self.player, self.cava, lambda: self.command("show"), self.sources)
        else:
            self.preview = ui.NoPreview()
        self.win.on_hover_changed = self.preview.set_enabled
        self.player.mpris.on_raise = lambda: self.command("show")
        self.player.mpris.on_quit = self.stop
        self.win.connect("close-request", self.on_close)
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

    def on_close(self, _win):
        """✕ / q / Alt+F4: ganz beenden (Musik aus) – oder nur verstecken, wenn das so eingestellt ist."""
        if engine.setting("background"):
            return False                      # Standardverhalten des Fensters: verstecken, Musik läuft weiter
        self.stop()
        return True

    def show_window(self):
        """Fenster zeigen und nach vorn holen.
        Nicht einfach present(): GTK fragt dafür beim Compositor eine Startberechtigung an und wartet
        blockierend auf die Antwort – unter GNOME (mutter) kommt die nicht, und musicalist hing für immer
        (ließ sich nur einmal öffnen). Hyprland antwortet zuverlässig, dort bleibt present()."""
        w = self.win
        self.preview.hide()
        getattr(tui.glass, "bring_here", lambda w: None)(w)   # auf aktuellen Arbeitsbereich holen
        token, self.token = self.token, None
        if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
            w.present()
        elif token and _use_token(token):     # vom Desktop mitgegeben → GTK muss nicht warten
            w.present()
        elif not w.get_visible():
            w.set_visible(True)               # frisch gezeigte Fenster bekommen ohnehin den Fokus
        else:                                 # offen, aber hinten: einmal neu zeigen holt es nach vorn
            w.set_visible(False)
            w.set_visible(True)

    def command(self, cmd):
        w, p = self.win, self.player
        if cmd.startswith("token:"):
            self.token = cmd[6:] or None
        elif cmd == "toggle":
            if w.get_visible() and w.is_active():
                w.set_visible(False)
            else:
                self.show_window()
        elif cmd == "show" or cmd.startswith("show:"):  # show:lyrics öffnet direkt einen Tab
            self.show_window()
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
        elif cmd == "quit":
            self.stop()
        elif cmd.startswith("search:"):  # rice-music search:daft+punk
            w.query.set_text(cmd[7:].replace("+", " "))
            self.show_window()
            w.show_tab("search")
            w.do_search()

    def stop(self):
        if getattr(self, "stopped", False):
            return False
        self.stopped = True
        self.player.shutdown()                # mpv beenden → Musik aus
        if self.cava.proc is not None:
            self.cava.proc.terminate()
        for path in (PID_FILE, FIFO):
            try:
                os.unlink(path)
            except OSError:
                pass
        self.quit()
        return False


if __name__ == "__main__":
    app = App("--show" in sys.argv)
    tok = os.environ.pop("XDG_ACTIVATION_TOKEN", None)   # Startberechtigung nicht an Kindprozesse vererben
    os.environ.pop("DESKTOP_STARTUP_ID", None)
    if tok and "--show" in sys.argv:
        app.token = tok
    sys.exit(app.run(None))
