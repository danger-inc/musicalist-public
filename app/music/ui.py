# musicalist – Oberfläche: Hauptfenster (Tabs jetzt/warteschlange/bibliothek/lyrics/visuals/suchen) und die
# Vorschau-Karte unten mittig (erscheint, wenn die Maus an den unteren Bildschirmrand in der Mitte fährt).
# Alles im TUI-Stil aus ../tui.py: Cover als Braille-Pixelbild, Spektrum aus ▁▂▃▅▇ (cava), ■-Regler.
import json, os, socket, subprocess, threading, time

import gi
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Graphene, Gtk, Pango, PangoCairo
try:   # nur für die Vorschau-Karte; ohne gtk4-layer-shell (oder unter GNOME/X11) läuft der Player trotzdem
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell as Layer
except (ImportError, ValueError):
    Layer = None
import shutil

import tui
from tui import label, hbox, vbox, esc
import engine
from engine import fmt
import songmenu
import sources
import swipe
import verlauf
import visuals
from rows import track_row, coll_row, artist_link
from widgets import (Layer, Cover, DotCover, big_thumb, fetch_pixbuf, dither, braille, halftone, placeholder,
                     preview_supported, DESK_POS, TICKS, DOTS, BAYER)
import rows
from settings_page import SettingsMixin
from queue_page import QueueMixin
from search_page import SearchMixin
from library_page import LibraryMixin
from lyrics_page import LyricsMixin
from sound_page import SoundMixin

RUNTIME = engine.RUNTIME

CSS = """
.cover { font-family: "JetBrainsMono Nerd Font", monospace; font-size: 9px; line-height: 1; color: @primary; }
.cover.small { font-size: 6px; }
.spectrum { font-size: 13px; line-height: 0.9; color: @primary; }
.spectrum.small { font-size: 10px; }
.np-title { font-size: 20px; }
.np-artist { font-size: 14px; color: @primary; }
.np-album { color: @secondary; }
button.ctl { font-size: 18px; padding: 2px 12px; }
button.ctl label { font-size: 18px; }
button.ctl.play label { font-size: 22px; }
.lyric { font-size: 16px; color: alpha(@foreground, 0.5); padding: 4px 24px; }
.lyric.now { color: @primary; font-size: 21px; }
.lyric.past { color: alpha(@foreground, 0.28); }
.trk-mark { color: @primary; min-width: 18px; }
flowbox.opts > flowboxchild { padding: 0; min-width: 0; min-height: 0; }
.album-badge { font-size: 9px; font-weight: bold; letter-spacing: 1px; color: @on_primary; background: @primary;
               border-radius: 4px; padding: 0 5px; }
.row.trk:hover { background-color: alpha(@primary, 0.1); border-radius: 4px; }
.row.trk > button.rowhead:hover { background: none; }
button.artlink { background: none; background-image: none; border: none; box-shadow: none; padding: 0 2px;
    min-height: 0; min-width: 0; border-radius: 3px; }
button.artlink:hover label { color: @primary; text-decoration: underline; }
button.artlink:disabled label { color: alpha(@foreground, 0.5); }
label.np-artist.link:hover { text-decoration: underline; }
.row.playing > button.rowhead { background-color: alpha(@primary, 0.16); }
.row.playing .trk-title { color: @primary; }
.row.dropat { box-shadow: inset 0 2px 0 @primary; }
.row.dropat-end { box-shadow: inset 0 -2px 0 @primary; }
.row.dragging { opacity: 0.4; }
button.mini { padding: 0 6px; border-radius: 4px; color: alpha(@foreground, 0.7); background: none; border: none;
    box-shadow: none; min-height: 0; min-width: 0; }
button.mini:hover { background-color: @primary; color: @on_primary; }
.loginbox { padding: 6px 0; }
/* ganz durchsichtig (none/transparent) bringt die Layer-Größe durcheinander (200×200) – 1 % reicht */
window.preview-trigger { background-color: rgba(0, 0, 0, 0.01); }
window.preview { background: none; backdrop-filter: blur(10px); }
.pcard { background-color: alpha(@background, 0.6); border: 2px solid @primary; border-radius: 15px;
    padding: 11px 14px 14px; color: @foreground; }   /* oben 3 px weniger: Schrift bringt eigenen Freiraum mit */
.pcard * { font-family: "JetBrainsMono Nerd Font", "JetBrains Mono", "Notes Icons", monospace; font-weight: bold; }
.pcard label { font-size: 12px; }
.pcard .np-title { font-size: 15px; }
.pcard .np-artist { font-size: 12px; }
/* Titel ohne Innenabstand: linke Kante = Kante der Steuerknöpfe; Hover färbt nur den Titel */
.pcard button.ptitle, .pcard button.plike { padding: 0; margin: 0; min-height: 0; min-width: 0; border: none;
    background: none; box-shadow: none; }
.pcard button.ptitle:hover .np-title { color: @primary; }
/* das Herz-Symbol ist breiter als sein Platz – so schließt es rechts mit Zeit und Balken ab */
.pcard button.plike label { font-size: 15px; color: @primary; margin-right: 3px; }
.pcard button.plike:hover label { color: @foreground; }
.pcard .src-sep { border-top: 1px solid alpha(@primary, 0.25); padding-top: 10px; }
.pcard button.mini { padding: 0 4px; }
/* Kopfleiste im aktuellen -ist-Stil (wie notist): umrandete Symbolknöpfe, aktiver Tab mit Namen */
button.npchip { background: none; border: 1px solid transparent; box-shadow: none; padding: 1px 8px;
    border-radius: 4px; color: alpha(@foreground, 0.75); min-height: 0; outline: none; }
button.npchip:hover { border-color: alpha(@primary, 0.55); background-color: alpha(@primary, 0.10); color: @foreground; }
button.npchip .accent { color: @primary; }
button.ibtn, menubutton.ibtn > button { min-width: 0; min-height: 0; padding: 1px 7px; }
menubutton.ibtn { padding: 0; }
menubutton.ibtn > button { background: none; border: none; box-shadow: none; color: inherit; }
popover.kpop > contents { padding: 6px 4px; min-width: 250px; }
popover.kpop .kp-head { color: @primary; font-size: 13px; margin: 2px 10px 0 10px; }
popover.kpop .kp-sub { color: alpha(@foreground, 0.6); font-size: 11px; margin: 0 10px 4px 10px; }
popover.kpop .kp-rub { color: @secondary; font-size: 11px; margin: 6px 10px 2px 10px; }
popover.kpop .kp-line { border-top: 1px solid alpha(@primary, 0.3); margin: 0 2px; min-height: 0; }
popover.kpop button.opt .kp-key { color: alpha(@foreground, 0.45); font-size: 11px; }
popover.kpop button.opt:hover .kp-key { color: @on_primary; }
popover.kpop button.opt.danger { color: @tertiary; }
popover.kpop button.opt.danger:hover { background-color: @tertiary; color: @background; }
/* Suche: Vorschläge beim Tippen (erster größer), bester Treffer als großer Kasten */
.sugg-row { margin: 2px 0 0 18px; }
button.sugg { background: none; border: 1px solid transparent; box-shadow: none; border-radius: 4px; padding: 0 7px;
    min-height: 0; color: alpha(@foreground, 0.62); font-size: 12px; }
button.sugg:hover, button.sugg:focus-visible { border-color: alpha(@primary, 0.55); background-color: alpha(@primary, 0.10);
    color: @foreground; }
button.sugg.first { color: @foreground; font-size: 15px; font-weight: bold; border-color: alpha(@primary, 0.45); padding: 1px 9px; }
button.sugg.first .accent { color: @primary; }
.top-card { padding: 2px 0 4px 0; }
.top-card .top-kind { color: @secondary; font-size: 11px; }
.top-card .top-title { font-size: 19px; font-weight: bold; }
.top-card .top-sub { color: @primary; font-size: 13px; }
.lyric.plain { color: alpha(@foreground, 0.8); }
/* Tastenliste (?) */
popover.kpop .kp-grid label { font-size: 12px; }
popover.kpop .kp-grid .k { color: @primary; }
""" + sources.CSS + visuals.CSS + verlauf.CSS + songmenu.CSS






















# ---------- Spektrum (cava) ----------
class Cava:
    """cava im Raw-Modus: liefert Balkenhöhen 0–16. Läuft nur, solange jemand zuschaut (ref-Zählung)."""

    def __init__(self, bars=64):
        self.bars, self.users, self.proc = bars, set(), None
        # Nur bei laufender Musik: cava hört den Ausgang ab und hält ihn damit wach – Kopfhörer rauschen dann
        # auch bei Pause/Stille (der Verstärker geht nie in den Ruhezustand). set_playing() schaltet das.
        self.playing = False
        self.listeners = []
        self.lock = threading.Lock()
        self.latest, self.last_t, self.scheduled = [], 0.0, False
        GLib.timeout_add(250, self.watchdog)
        self.cfg = RUNTIME + "/rice-music-cava.conf"
        with open(self.cfg, "w") as f:
            f.write(f"""[general]
bars = {bars}
framerate = 30
sleep_timer = 1
[input]
method = pipewire
source = auto
[output]
method = raw
raw_target = /dev/stdout
data_format = ascii
ascii_max_range = 16
bar_delimiter = 59
frame_delimiter = 10
[smoothing]
noise_reduction = 70
""")

    def set_playing(self, on):
        if bool(on) != self.playing:
            self.playing = bool(on)
            self.want(None, False)

    def want(self, who, on):
        if who is not None:
            (self.users.add if on else self.users.discard)(who)
        if self.users and self.playing and self.proc is None:
            if not shutil.which("cava"):
                return                      # cava fehlt → Spektrum bleibt einfach leer
            self.proc = tui.spawn_watch(["cava", "-p", self.cfg], stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True)
            threading.Thread(target=self.read, args=(self.proc,), daemon=True).start()
        elif (not self.users or not self.playing) and self.proc is not None:
            self.proc.terminate()
            self.proc = None
            self.latest = []
            for fn in self.listeners:          # Anzeige fällt sofort auf die Grundlinie
                fn([])

    def read(self, proc):
        # Neuester Wert liegt in self.latest; höchstens ein idle-Aufruf gleichzeitig (Lock gegen Wettlauf,
        # früher konnte die Anzeige dadurch für immer stehen bleiben).
        for line in proc.stdout:
            try:
                vals = [int(v) for v in line.strip().strip(";").split(";")]
            except ValueError:
                continue
            with self.lock:
                self.latest, self.last_t = vals, time.monotonic()
                schedule = not self.scheduled
                self.scheduled = True
            if schedule:
                GLib.idle_add(self.deliver)

    def deliver(self):
        with self.lock:
            vals, self.scheduled = self.latest, False
        for fn in self.listeners:
            fn(vals)
        return False

    def watchdog(self):
        """cava schweigt bei Stille (sleep_timer) – dann einmal auf die Grundlinie fallen."""
        if self.users and self.latest and time.monotonic() - self.last_t > 0.4:
            self.latest = []
            for fn in self.listeners:
                fn([])
        return True


class Spectrum(Gtk.DrawingArea):
    """Live-Spektrum aus Blockzeichen-Stufen (▁▂▃▄▅▆▇█, je Zeile 8 Stufen). Gezeichnet statt als Text,
    damit es sich jeder Fensterbreite anpasst. Ohne Ton: gedimmte Grundlinie ▁▁▁▁."""

    def __init__(self, rows=2, cell=9, height=None, flush=False):
        super().__init__(hexpand=True)
        self.rows, self.cell, self.flush = rows, cell, flush
        self.row_h = (height or rows * 16) / rows
        self.set_content_height(int(self.row_h * rows))
        self.vals = []
        self.set_draw_func(self._draw)

    def set_vals(self, vals):
        self.vals = vals or []
        self.queue_draw()

    def set_height(self, h):
        self.rows = max(1, round(h / 16))
        self.row_h = h / self.rows
        self.set_content_height(int(h))

    def _draw(self, _a, cr, width, height):
        c = tui.colors()
        p, fg = c.get("primary"), c.get("foreground")
        n = max(2, int(width // self.cell))
        x0 = (width - n * self.cell) / 2
        vals, m = self.vals, len(self.vals)
        bw = self.cell - 2
        step = (width - bw) / (n - 1)   # flush: erster/letzter Balken genau an den Rändern
        for i in range(n):
            v = vals[min(m - 1, int(i * m / n))] if m else 0
            eighths = round(v / 16 * self.rows * 8)  # cava liefert 0–16
            x = i * step if self.flush else x0 + i * self.cell + 1
            if eighths <= 0:
                cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.18)
                cr.rectangle(x, height - self.row_h / 8, bw, self.row_h / 8)
                cr.fill()
                continue
            h = eighths / 8 * self.row_h
            # oben heller Akzent, unten volle Farbe – wie die btop-Graphen
            cr.set_source_rgba(p.red, p.green, p.blue, 1.0)
            cr.rectangle(x, height - h, bw, h)
            cr.fill()




# ---------- Hauptfenster ----------
class MusicWindow(SettingsMixin, QueueMixin, SearchMixin, LibraryMixin, LyricsMixin, SoundMixin, tui.TuiWindow):
    APP_ID = "de.invincible.Music"
    TABS = [("now", "jetzt", "󰝚"), ("queue", "warteschlange", "󰲸"), ("lib", "bibliothek", "󰋑"),
            ("lyrics", "lyrics", "󰗊"), ("visuals", "visuals", "󱑽"), ("search", "suchen", "󰍉"),
            ("settings", "einstellungen", "󰒓")]   # einstellungen: kein Tab, sondern ⚙ oben rechts
    ESC_CLOSES = False          # Esc soll den Player nicht zumachen (nur Tastenkürzel aus der Config / q / ✕)

    def __init__(self, app, player, cava, srcs):
        super().__init__(app, "󰝚 musicalist", [(t, n, i) for t, n, i in self.TABS],
                         size=(900, 700), icons_only=True, hints=())
        self.p, self.cava, self.srcs = player, cava, srcs
        self.songs = songmenu.SongMenus(self)
        rows.set_hooks(self.open_artist, player.offline.has)
        css = Gtk.CssProvider()
        css.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        self.account = None
        self.login_expired = False
        GLib.timeout_add_seconds(4, self.rescan_local)       # Musikordner im Hintergrund einlesen
        self.lyrics_vid = None
        self.lyric_lines = []
        self.detail_tracks = []

        self.tier = 0                  # 0 breit … 3 sehr schmal (Achtel-Kachel), setzt on_resize
        self.focus_mode = False
        self.detail_key, self.detail_names = None, {}
        self.detail_pool, self.editable_ids, self.local_scanned = None, set(), False
        self._shorten = []             # (knopf, lang, kurz) – schmale Fenster bekommen die kurze Beschriftung
        self.build_header()
        self.add_changelog("musicalist", os.path.dirname(os.path.realpath(__file__)))
        self.header_extra.reorder_child_after(self.changelog_btn, self.np_chip)
        if getattr(self, "update_btn", None):
            self.header_extra.reorder_child_after(self.update_btn, self.changelog_btn)

        self.build_now()
        self.build_queue()
        self.build_search()
        self.build_lib()
        self.build_lyrics()
        self.build_visuals()
        self.build_settings()
        self.spec = Spectrum(rows=2, cell=9, height=34)
        self.spec.set_margin_top(6)
        self.spec.set_tooltip_text("live-spektrum (cava)")
        self.content.append(self.spec)

        # 2-Finger-Zurück (swipe.py, Seitenstapel): Kette endet immer auf Seite 1 „jetzt“
        self.nav_back, self.nav_cur, self._nav_id, self._nav_skip = [], ("tab", "now"), None, False
        self.content.remove(self.stack)
        self.swipe = swipe.SwipeBack(self.stack, self.nav_can_back, self.nav_go_back,
                                     blocked=lambda w: isinstance(w, tui.Meter),
                                     where=self.nav_where, target=self.nav_target,
                                     goto=self.nav_goto)
        self.content.prepend(self.swipe.widget)
        # Hörverlauf-Leiste am rechten Rand (verlauf.py) um den ganzen Inhalt
        root = self.root
        root.remove(self.content)
        self.drawer = verlauf.HistoryDrawer(self, self.content, player,
                                            lambda: bool(engine.setting("history_pinned")),
                                            lambda on: engine.set_setting("history_pinned", on))
        root.insert_child_after(self.drawer.widget, self.topbar)
        self.drawer.set_enabled(engine.setting("history"))
        self.show_tab("now")
        self.update_tab_labels()

        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key)
        self.add_controller(keys)
        self.on_tab = self.tab_changed
        self.on_refresh = self.refresh_account

        player.listeners.append(self.on_player)
        cava.listeners.append(self.on_spectrum)
        self.update_track()
        self.update_state()
        self.update_queue()
        self.refresh_account()

    # ---------- Kopfleiste ----------
    def build_header(self):
        """[󰝚 musicalist] ¹󰝚 jetzt ²󰲸 ³󰋑 ⁴󰗊 ⁵󱑽 ⁶󰍉 ……… [󰝚 titel · künstler] v1.2 [󰀄 ●] [󰒓] [◐] ✕"""
        top = self.topbar.get_child()
        self.brand_lbl = top.get_first_child()
        # Kopfleiste darf schmaler werden als ihr Inhalt (Achtel-Kachel) – set_tier() räumt dann auf.
        # Ohne das bestimmt sie die Mindestbreite des Fensters (~500 px), Hyprland und GTK streiten → Ruckeln.
        self.topbar.set_child(None)
        self.topbar.set_child(Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.EXTERNAL,
                                                 vscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_width=True,
                                                 propagate_natural_height=True, child=top))
        self.glass_btn = next((w for w in self._children(top) if isinstance(w, tui.glass.GlassToggle)), None)
        for tid, b in self.tab_btns:
            if tid == "settings":
                b.set_visible(False)
        self.fill_hints()
        # was läuft – nur wenn nicht auf Seite 1 und genug Platz
        self.np_chip = Gtk.Button(focus_on_click=False, tooltip_text="läuft – zu ¹ jetzt")
        self.np_chip.add_css_class("npchip")
        self.np_chip_lbl = label("", ellipsize=True)
        self.np_chip_lbl.set_max_width_chars(30)
        self.np_chip.set_child(hbox(label("󰝚", "accent"), self.np_chip_lbl, spacing=6))
        self.np_chip.connect("clicked", lambda *_: self.show_tab("now"))
        self.header_extra.append(self.np_chip)
        # Konto
        self.acct_lbl = label("󰀄 ○")
        self.acct_btn = Gtk.MenuButton(child=self.acct_lbl, tooltip_text="konto", valign=Gtk.Align.CENTER)
        self.acct_btn.add_css_class("tbtn")
        self.acct_btn.add_css_class("ibtn")
        pop = Gtk.Popover(has_arrow=False)
        pop.add_css_class("tpop")
        pop.add_css_class("kpop")
        self.acct_box = vbox(spacing=1)
        pop.set_child(self.acct_box)
        pop.connect("show", lambda *_: self.fill_account_menu())
        self.acct_btn.set_popover(pop)
        self.acct_pop = pop
        self.header_extra.append(self.acct_btn)
        self.gear_btn = tui.Button("󰒓", lambda: self.show_tab("settings"), tooltip="einstellungen (,)")
        self.gear_btn.add_css_class("ibtn")
        self.header_extra.append(self.gear_btn)

    # Tastenhinweise unten: breit alle, halbes Fenster die wichtigsten, schmal keine; ? zeigt immer alle
    HINTS = [(0, "1-6", "tab"), (1, "leer", "play"), (1, "n/p", "weiter/zurück"), (1, "/", "suche"),
             (0, "l", "♥"), (0, "a", "playlist"), (1, "?", "alle tasten")]
    KEYS = [("leertaste", "play / pause"), ("n · p", "nächster / voriger titel"), ("← →", "5 s spulen"),
            ("+ −", "lauter / leiser"), ("l", "gefällt mir"), ("a", "titel zu playlist hinzufügen"),
            ("1 – 6", "tabs"), ("/", "suchen (tab übernimmt den 1. vorschlag)"), ("h", "hörverlauf-leiste"),
            (",", "einstellungen"), ("[ ]", "lyrics früher / später"), ("s", "sleep-timer"), ("e", "klang: equalizer / überblenden"), ("v · f", "visuals: modus / vollbild"),
            ("rechtsklick", "mehr zu jedem titel"), ("q", "schließen"), ("?", "diese liste"),
            ("super+alt+n / p", "weiter / zurück – auch wenn musicalist zu ist"),
            ("super+alt+leertaste", "play / pause von überall")]

    def fill_hints(self):
        tui.clear(self.hint_box)
        self.hint_items = []
        for level, k, v in self.HINTS:
            w = hbox(label(k, "accent"), label(v, "dim"), spacing=5)
            w.level = level
            self.hint_box.append(w)
            self.hint_items.append(w)

    def on_compact(self, compact):
        self.apply_hints()

    def apply_hints(self):
        tier = getattr(self, "tier", 0)
        self.hint_box.set_visible(tier <= 1 and not getattr(self, "focus_mode", False))
        for w in getattr(self, "hint_items", []):
            w.set_visible(tier == 0 or w.level == 1)

    def show_keys(self):
        """Liste aller Tasten (?) als Popover über der Statuszeile."""
        pop = self.songs._popover(self.statusbar)
        pop.set_position(Gtk.PositionType.TOP)
        box = vbox(spacing=2)
        box.append(label("󰌌  tastenkürzel", "kp-head"))
        grid = Gtk.Grid(column_spacing=14, row_spacing=3)
        grid.add_css_class("kp-grid")
        grid.set_margin_start(10)
        grid.set_margin_end(10)
        grid.set_margin_top(6)
        grid.set_margin_bottom(6)
        for i, (k, v) in enumerate(self.KEYS):
            grid.attach(label(k, "k", xalign=1), 0, i, 1, 1)
            grid.attach(label(v, xalign=0), 1, i, 1, 1)
        box.append(grid)
        pop.set_child(box)
        pop.popup()

    def add_page(self, tid, widget, scroll=True):
        """Wie tui.TuiWindow.add_page, aber waagerecht EXTERNAL statt NEVER: die Seite zwingt dem Fenster
        keine Mindestbreite auf (schmale Kacheln), set_tier() sorgt dafür, dass der Inhalt trotzdem passt."""
        if scroll:
            widget = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.EXTERNAL, child=widget, vexpand=True)
        tui.TuiWindow.add_page(self, tid, widget, scroll=False)

    @staticmethod
    def _children(w):
        c = w.get_first_child()
        while c is not None:
            yield c
            c = c.get_next_sibling()

    def fill_account_menu(self):
        """Kontomenü im Stil des notist-Dateimenüs. Der Kontoname wird bewusst nie gezeigt."""
        box = self.acct_box
        tui.clear(box)
        on = self.account is not None
        box.append(label("󰀄  konto", "kp-head"))
        box.append(label("● angemeldet · youtube music" if on else "○ nicht angemeldet – suche geht trotzdem",
                         "kp-sub", wrap=True))

        def rub(text):
            line = Gtk.Box()
            line.add_css_class("kp-line")
            box.append(line)
            if text:
                box.append(label(text, "kp-rub"))

        def item(icon, text, fn, key="", danger=False):
            b = Gtk.Button(focus_on_click=False)
            b.add_css_class("opt")
            if danger:
                b.add_css_class("danger")
            b.set_child(hbox(label(icon, xalign=0.5), label(text, hexpand=True), label(key, "kp-key"), spacing=10))
            b.connect("clicked", lambda *_: (self.acct_pop.popdown(), fn()))
            box.append(b)

        rub("anmeldung")
        if on:
            item("󰑐", "anmeldung neu einlesen", self.login)
        else:
            item("󰍂", "mit zen / firefox anmelden", self.login)
        rub("bibliothek")
        if on:
            item("󰋑", "lieblingssongs", lambda: self.open_detail("playlist", "LM"))
        item("󰲸", "playlists & sammlung", self.lib_home, "³")
        if engine.setting("history"):
            item("󰋚", "hörverlauf", self.drawer.toggle, "h")
        rub("")
        item("󰒓", "einstellungen", lambda: self.show_tab("settings"), ",")
        item("↗", "youtube music im browser", lambda: engine.open_url("https://music.youtube.com"))
        if on:
            item("󰍃", "abmelden", self.do_logout, danger=True)

    def update_tab_labels(self):
        """Aktiver Tab mit Namen (wie notist), die anderen nur Symbol; sehr schmal: alle nur Symbol."""
        cur = self.current_tab()
        for tid, (name_lbl, icon_lbl) in self.tab_names.items():
            name_lbl.set_visible(tid == cur and self.tier < 2)
            name_lbl.set_margin_start(5)
        chip = self.p.current is not None and cur != "now" and self.tier == 0 and not self.focus_mode
        self.np_chip.set_visible(chip)

    def set_tier(self, tier):
        if tier == self.tier:
            return
        self.tier = tier
        self.brand_lbl.set_label("󰝚" if tier >= 2 else "󰝚 musicalist")
        self.changelog_btn.set_visible(tier <= 1)          # auch im halben Fenster
        if getattr(self, "update_btn", None):
            self.update_btn.set_visible(tier <= 1)
        if self.glass_btn is not None:
            self.glass_btn.set_visible(tier < 3)
        self.gear_btn.set_visible(tier < 3)
        for b, long, short in self._shorten:
            b.set_label(short if tier >= 2 else long)
        for chk in (self.hover_chk, self.bg_chk, self.hist_chk):
            chk.text.set_wrap(tier >= 1)
        self.apply_hints()
        self.set_ctl_narrow(tier >= 2)
        self.visuals.set_narrow(tier >= 2)
        self.drawer.set_narrow(tier >= 2)
        self.update_track_labels()
        self.update_tab_labels()

    def _sh(self, btn, long, short):
        self._shorten.append((btn, long, short))
        return btn

    # ---------- Navigation (2-Finger-Zurück) ----------
    TAB_SUP = {"now": "¹ ", "queue": "² ", "lib": "³ ", "lyrics": "⁴ ", "visuals": "⁵ ", "search": "⁶ ", "settings": ""}

    def nav_loc(self):
        tab = self.current_tab() or "now"
        if tab == "lib" and self.lib_stack.get_visible_child_name() == "detail" and self.detail_key:
            return ("detail",) + self.detail_key
        return ("tab", tab)

    def nav_title(self, loc):
        if loc[0] == "detail":
            return self.detail_names.get(loc[1:], self.DETAIL_NAMES.get(loc[1], "playlist"))
        names = {t: n for t, n, _i in self.TABS}
        return self.TAB_SUP.get(loc[1], "") + names.get(loc[1], loc[1])

    def nav_where(self):
        loc = self.nav_loc()
        return loc, self.nav_title(loc)

    def nav_note(self):
        if self._nav_id is None and hasattr(self, "nav_back"):
            self._nav_id = GLib.idle_add(self.nav_commit)

    def nav_commit(self):
        self._nav_id = None
        loc = self.nav_loc()
        skip, self._nav_skip = self._nav_skip, False
        if loc == self.nav_cur:
            return False
        if loc == ("tab", "now"):
            self.nav_back = []                 # Seite 1 ist immer das Ende der Zurück-Kette
        elif not skip and (not self.nav_back or self.nav_back[-1] != self.nav_cur):
            self.nav_back.append(self.nav_cur)
            del self.nav_back[:-40]
        self.nav_cur = loc
        return False

    def nav_can_back(self):
        return self.nav_loc() != ("tab", "now") and not self.focus_mode

    def _nav_next(self, pop):
        cur = self.nav_loc()
        stack = self.nav_back if pop else list(self.nav_back)
        while stack:
            loc = stack.pop()
            if loc != cur:
                return loc
        return ("tab", "now")

    def nav_target(self):
        loc = self._nav_next(pop=False)
        return loc, self.nav_title(loc)

    def nav_go_back(self):
        loc = self._nav_next(pop=True)
        self._nav_skip = True
        if loc[0] == "detail":
            self.open_detail(loc[1], loc[2])
        else:
            if loc[1] == "lib":
                self.lib_stack.set_visible_child_name("home")
            self.show_tab(loc[1])
        self.nav_note()

    def nav_goto(self, loc):
        self._nav_skip = False
        if loc[0] == "detail":
            self.open_detail(loc[1], loc[2])
        else:
            self.show_tab(loc[1])
        self.nav_note()
        return True

    def lib_home(self):
        self.lib_stack.set_visible_child_name("home")
        self.show_tab("lib")
        self.nav_note()

    # ---------- visuals ----------
    def build_visuals(self):
        self.visuals = visuals.Visuals(self.p, self.cava, halftone, lambda: engine.setting("visual"),
                                       lambda m: engine.set_setting("visual", m), lambda _x: self.toggle_focus())
        self.visuals.set_margin_top(4)
        self.add_page("visuals", self.visuals, scroll=False)
        self.visuals.update_track()

    def toggle_focus(self, on=None):
        """Vollbild nur mit der Visualisierung (f, Esc zurück)."""
        on = (not self.focus_mode) if on is None else on
        if on == self.focus_mode:
            return
        self.focus_mode = on
        if on and self.current_tab() != "visuals":
            self.show_tab("visuals")
        for w in (self.topbar, self.statusbar):
            w.set_visible(not on)
        self.apply_hints()
        self.visuals.bar.set_visible(not on)
        self.visuals.full_btn.set_visible(not on)
        self.visuals.hint.set_label("esc zurück" if on else "v modus · f vollbild")
        (self.fullscreen if on else self.unfullscreen)()
        self.schedule_relayout()
        self.update_tab_labels()

    # ---------- jetzt ----------
    def build_now(self):
        page = vbox(spacing=10)
        page.set_margin_top(8)
        self.cover = Cover(36, 18)
        self.title = label("", "np-title", wrap=True)
        self.title.set_lines(2)
        self.title.set_ellipsize(Pango.EllipsizeMode.END)
        self.artist = label("", "np-artist", ellipsize=True)
        self.artist.add_css_class("link")
        self.artist.set_cursor_from_name("pointer")
        self.artist.set_tooltip_text("Künstlerseite öffnen")
        ac = Gtk.GestureClick()
        ac.connect("released", lambda *_: self.open_artist(self.p.current))
        self.artist.add_controller(ac)
        self.album = label("", "np-album", ellipsize=True)
        self.info = label("", "dim", ellipsize=True)
        self.like_btn = tui.Button("", lambda: self.p.like(), tooltip="Gefällt mir (l)")
        self.radio_btn = tui.Button("󰐹 radio", lambda: (self.p.start_radio(), self.say("radio startet …")),
                                    tooltip="Ähnliche Titel als Warteschlange")
        self.web_btn = tui.Button("↗ browser", self.open_web, tooltip="In YouTube Music öffnen")
        self.pl_btn = tui.Button("󰐒 playlist", lambda: self.songs.picker(self.pl_btn, [self.p.current]),
                                 tooltip="Zu einer Playlist hinzufügen (a)")
        acts = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=8, row_spacing=6,
                           max_children_per_line=6, homogeneous=False, halign=Gtk.Align.START)
        acts.add_css_class("opts")
        for w in (self.like_btn, self.pl_btn, self.radio_btn, self.web_btn):
            acts.append(w)
        self.np_gap = label("")
        self.np_acts = acts
        side = vbox(self.title, self.artist, self.album, self.np_gap, self.info, acts, spacing=4, hexpand=True)
        self.np_side = side
        self.np_box = hbox(self.cover, side, spacing=18)
        self.np_panel = tui.Panel("󰝚 läuft", self.np_box)
        page.append(self.np_panel)
        rc = Gtk.GestureClick(button=3)          # Rechtsklick auf „läuft“ = Menü zum aktuellen Titel
        rc.connect("pressed", lambda g, n, x, y: self.p.current and self.songs.menu(self.np_box, x, y, self.p.current))
        self.np_box.add_controller(rc)
        side.set_valign(Gtk.Align.CENTER)

        self.pos_lbl = label("0:00", "mono-pct")
        self.dur_lbl = label("0:00", "mono-pct", xalign=1)
        self.seek = tui.Meter(1000, self.on_seek, mark=False, scroll="h")
        self.prev_btn = tui.Button("󰒮", self.p.prev, tooltip="Zurück (p)")
        self.play_btn = tui.Button("󰐊", self.p.toggle, tooltip="Play/Pause (Leertaste)")
        self.next_btn = tui.Button("󰒭", lambda: self.p.next(), tooltip="Weiter (n)")
        for b in (self.prev_btn, self.play_btn, self.next_btn):
            b.add_css_class("ctl")
        self.play_btn.add_css_class("play")
        self.shuffle_btn = tui.Button("󰒝 mischen", self.p.shuffle_queue, tooltip="Warteschlange mischen")
        self.repeat_btn = tui.Button("", self.p.cycle_repeat, tooltip="Wiederholen: aus / alle / eins")
        self.sleep_btn = tui.Button("󰒲", self.sleep_menu, tooltip="Sleep-Timer (s)")
        self.sound_btn = tui.Button("󰓃", self.sound_menu, tooltip="Klang: Equalizer und Überblendung (e)")
        self.auto_chk = tui.Check("autoplay", self.p.autoplay, self.set_autoplay,
                                  tooltip="Am Ende der Warteschlange ähnliche Titel weiterspielen")
        self.vol = tui.Meter(100, self.p.set_volume)
        self.vol.set_size_request(120, -1)
        self.vol.set_hexpand(False)
        self.vol_lbl = label("", "mono-pct", xalign=1)
        opts = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=8, row_spacing=6,
                           max_children_per_line=12, homogeneous=False, halign=Gtk.Align.START)
        opts.add_css_class("opts")
        self.ctl_opts = opts
        for w in (self.shuffle_btn, self.repeat_btn, self.sleep_btn, self.sound_btn, self.auto_chk,
                  hbox(label("󰕾", "accent"), self.vol, self.vol_lbl, spacing=8)):
            opts.append(w)
        self.seek_box = hbox(self.pos_lbl, self.seek, self.dur_lbl, spacing=8, hexpand=True)
        self.ctl_row = hbox(self.prev_btn, self.play_btn, self.next_btn, self.seek_box, spacing=8)
        ctl = vbox(self.ctl_row, opts, spacing=10)
        self.ctl_box = ctl
        self.ctl_panel = tui.Panel("steuerung", ctl)
        page.append(self.ctl_panel)

        # Andere Quellen (Zen, Spotify, Spiele …) – nur sichtbar, wenn gerade etwas da ist
        self.src_list = sources.SourceList(self.srcs, limit=4)
        self.src_panel = tui.Panel("󰓃 andere quellen", self.src_list)
        self.src_panel.set_visible(bool(self.srcs.items))
        self.src_list.on_change = self.on_sources
        page.append(self.src_panel)

        self.upnext = vbox(spacing=0)
        self.upnext_panel = tui.Panel("als nächstes", self.upnext)
        self.upnext_panel.set_vexpand(True)   # Kasten reicht bis zum Spektrum, kein loser Leerraum
        page.append(self.upnext_panel)
        self.now_page = page
        self.upnext_n = 3      # wie viele "als nächstes" passen – setzt relayout()
        self.short = 0         # wie stark verdichtet (0 = alles zeigen)
        self._relayout_id = None
        self.add_page("now", page)

    def set_ctl_narrow(self, narrow):
        """Sehr schmal: Zeitleiste in eine eigene Zeile unter Zurück/Play/Weiter."""
        inrow = self.seek_box.get_parent() is self.ctl_row
        if narrow and inrow:
            self.ctl_row.remove(self.seek_box)
            self.ctl_box.insert_child_after(self.seek_box, self.ctl_row)
        elif not narrow and not inrow:
            self.ctl_box.remove(self.seek_box)
            self.ctl_row.append(self.seek_box)

    def update_track_labels(self):
        t = self.p.current
        narrow = self.tier >= 2
        liked = bool(t and t.get("liked"))
        self.like_btn.set_label(("󰋑" if liked else "󰋕") + ("" if narrow else " gefällt mir"))
        self.radio_btn.set_label("󰐹" if narrow else "󰐹 radio")
        self.web_btn.set_label("↗" if narrow else "↗ browser")
        self.pl_btn.set_label("󰐒" if narrow else "󰐒 playlist")
        self.shuffle_btn.set_label("󰒝" if narrow else "󰒝 mischen")
        if t is not None:
            self.np_chip_lbl.set_label(f"{t['title']} · {t['artist']}")

    def on_seek(self, v):
        if self.p.dur:
            self.p.seek(v / 1000 * self.p.dur)

    # ---------- Sleep-Timer ----------
    SLEEP_OPTS = [(15, "15 minuten"), (30, "30 minuten"), (45, "45 minuten"), (60, "1 stunde"), (90, "1,5 stunden")]

    def sleep_menu(self, anchor=None):
        anchor = anchor if isinstance(anchor, Gtk.Widget) else (
            self.sleep_btn if self.sleep_btn.get_mapped() else self.statusbar)
        pop = self.songs._popover(anchor)
        if anchor is self.statusbar:
            pop.set_position(Gtk.PositionType.TOP)
        box = vbox(spacing=1)
        pop.set_child(box)
        box.append(label("󰒲  sleep-timer", "kp-head"))
        left = self.p.sleep_left()
        box.append(label("pausiert die musik – die letzten 10 s werden leiser", "kp-sub"))
        for m, name in self.SLEEP_OPTS:
            self.songs._item(box, pop, "󰔟", name, lambda m=m: self.p.set_sleep(m))
        self.songs._item(box, pop, "󰒭", "nach diesem titel", lambda: self.p.set_sleep(after_track=True))
        if left is not None or self.p.sleep_track:
            self.songs._rub(box)
            self.songs._item(box, pop, "✕", "timer aus", lambda: self.p.set_sleep(), danger=True)
        pop.popup()

    def update_sleep(self):
        left = self.p.sleep_left()
        if left is not None:
            m, s = divmod(int(left) + (1 if left % 1 else 0), 60)
            txt, on = f"󰒲 {m}:{s:02d}", True
        elif self.p.sleep_track:
            txt, on = "󰒲 titel", True
        else:
            txt, on = "󰒲", False
            if getattr(self, "_sleep_was", False) and not self.p.sleep_track:
                self.say("sleep-timer: pausiert" if self.p.paused else "sleep-timer aus")
        self._sleep_was = on
        self.sleep_btn.set_label(txt)
        (self.sleep_btn.add_css_class if on else self.sleep_btn.remove_css_class)("accent")

    def set_autoplay(self, on):
        self.p.autoplay = on
        self.p.save_soon()

    def open_web(self):
        t = self.p.current
        if t:
            engine.open_url(f"https://music.youtube.com/watch?v={t['videoId']}")

    def on_spectrum(self, vals):
        if self.get_visible():
            if self.current_tab() == "visuals":
                self.visuals.on_spectrum(vals)
            else:
                self.spec.set_vals(vals)

    def on_sources(self, items):
        if self.src_panel.get_visible() != bool(items):
            self.src_panel.set_visible(bool(items))
        self.schedule_relayout()

    # ---------- Zustand ----------
    def on_player(self, what):
        if what == "track":
            self.update_track()
        elif what in ("state", "volume"):
            self.update_state()
        elif what == "pos":
            self.update_pos()
        elif what == "queue_new":
            self.queue_reset_window()           # neue Warteschlange: Fenster wieder klein
        elif what == "queue":
            self.update_queue()
            self.schedule_relayout()
        elif what == "history":
            self.update_hist_info()
        elif what == "sleep":
            self.update_sleep()
        elif what.startswith("error:"):
            self.say(what[6:], error=True, seconds=10)
        elif what.startswith("notice:"):
            if what[7:]:
                self.say(what[7:], seconds=8)
            if hasattr(self, "ytdlp_info"):
                self.update_ytdlp_info()

    def update_track(self):
        if hasattr(self, "_relayout_id"):
            self.schedule_relayout()
        t = self.p.current
        self.cover.show(t["thumb"] if t else None)
        self.title.set_label(t["title"] if t else "nichts läuft")
        self.artist.set_label(t["artist"] if t else "⁶suchen")
        self.album.set_label(t["album"] if t else "")
        self.update_track_labels()
        if hasattr(self, "visuals"):
            self.visuals.update_track()
        if hasattr(self, "np_chip"):
            self.update_tab_labels()
        (self.like_btn.add_css_class if t and t.get("liked") else self.like_btn.remove_css_class)("on")
        for b in (self.like_btn, self.radio_btn, self.web_btn, self.pl_btn):
            b.set_sensitive(t is not None)
        self.like_btn.set_sensitive(t is not None and self.account is not None)
        self.update_queue()
        self.update_pos()
        self.load_lyrics()                         # liegt meist schon bereit (vorgeladen beim Titelwechsel)

    def update_state(self):
        p = self.p
        self.play_btn.set_label("󰏤" if not p.paused and p.started else "󰐊")
        self.repeat_btn.set_label({"aus": "󰑗 aus", "alle": "󰑖 alle", "eins": "󰑘 eins"}[p.repeat])
        self.vol.set_value(p.volume)
        self.vol_lbl.set_label(f"{p.volume}%")
        s = p.stream_info
        bits = []
        if p.loading:
            bits.append("⠿ lädt …")
        if s:
            bits.append(f"{(s['codec'] or '').split('.')[0]} {round(s['abr'] or 0)} kbps")
        if p.current and not p.started:
            bits.append("pausiert · leertaste zum fortsetzen")
        self.info.set_label("  ·  ".join(bits))

    def update_pos(self):
        p = self.p
        dur = p.dur or (p.current or {}).get("duration") or 0
        self.pos_lbl.set_label(fmt(p.pos))
        self.dur_lbl.set_label(fmt(dur))
        self.seek.set_value(int(p.pos / dur * 1000) if dur else 0)
        tab = self.current_tab()
        if tab == "lyrics":
            self.sync_lyrics()
        elif tab == "visuals":
            self.visuals.update_pos()

    # ---------- Fenster ----------
    def on_show(self):
        self.cava.want("window", True)
        self.srcs.want("window", True)
        self.update_track()
        self.update_state()

    def on_hide(self):
        self.cava.want("window", False)
        self.srcs.want("window", False)

    # ---------- Platz einteilen: Tab 1 passt immer genau ins Fenster ----------
    SPEC_MIN, SPEC_MAX = 28, 64   # Spektrum bleibt flach, den Platz bekommt "als nächstes"

    def schedule_relayout(self):
        if self._relayout_id is None:
            self._relayout_id = GLib.idle_add(self.relayout)

    def _h(self, w, width):
        return w.measure(Gtk.Orientation.VERTICAL, width)[1] if w.get_visible() else 0

    def set_short(self, level):
        """0: alles · 1: ohne Album/Leerzeile/Format · 2: Titel einzeilig, Panel-Titel kompakt"""
        self.short = level
        for w in (self.album, self.np_gap, self.info):
            w.set_visible(level == 0 and (w is not self.album or bool(self.album.get_label())))
        self.title.set_lines(1 if level >= 2 else 2)

    @staticmethod
    def _fit_flow(flow, fallback):
        """Knopfreihen (FlowBox) nebeneinander halten, solange sie passen. GTK 4.14 (Ubuntu 24.04) stapelt sie
        sonst untereinander, und sie ragen aus dem Kasten heraus."""
        width = flow.get_parent().get_width() or fallback
        spacing = flow.get_column_spacing()
        n = used = 0
        c = flow.get_first_child()
        while c is not None:
            if c.get_visible():
                need = c.measure(Gtk.Orientation.HORIZONTAL, -1)[1] + (spacing if n else 0)
                if used + need > width:
                    break
                used += need
                n += 1
            c = c.get_next_sibling()
        n = max(1, n)
        if flow.get_min_children_per_line() != n:
            flow.set_min_children_per_line(n)

    def relayout(self):
        self._relayout_id = None
        W, H = self.get_width(), self.get_height()
        if W <= 0 or H <= 0:
            return False
        # Cover: breit groß links, schmal kleiner rechts im "läuft"-Kasten
        wide = W >= 760
        first = self.np_box.get_first_child()
        if wide and first is not self.cover:
            self.np_box.reorder_child_after(self.cover, None)
        elif not wide and first is self.cover:
            self.np_box.reorder_child_after(self.cover, self.np_side)
        self.cover.set_halign(Gtk.Align.START if wide else Gtk.Align.END)
        self.cover.set_valign(Gtk.Align.CENTER)

        inner = W - 28                                   # Inhalt ohne Fensterränder
        for flow in (self.np_acts, self.ctl_opts):
            self._fit_flow(flow, inner - 60)
        avail = H - self.topbar.get_height() - self.statusbar.get_height() - 6 - 8 - 4   # Spektrum-Abstand, Seitenrand, Luft
        now = self.current_tab() == "now"
        if now:
            # Erst so viel weglassen wie nötig, damit "läuft" + "steuerung" + kleinstes Spektrum passen
            for level in (0, 1, 2):
                self.set_short(level)
                side_w = inner - 26 - (0 if not self.cover.get_visible() else 0)
                cols = 36 if wide else max(12, min(30, int(W * 0.32 / 5.5)))
                # Cover nicht höher als der Text daneben (sonst bläht es den Kasten auf)
                text_h = self._h(self.np_side, side_w - cols * 5.5)
                if level == 0:          # genug Platz: Cover in voller Größe
                    rows = cols // 2
                else:                   # eng: nicht höher als der Text daneben
                    rows = max(6, min(cols // 2, int(text_h / 9.5)))
                self.cover.set_size(rows * 2, rows)
                core = self._h(self.np_panel, inner) + self._h(self.ctl_panel, inner) + 10 + 8
                if self.src_panel.get_visible():
                    core += self._h(self.src_panel, inner) + 10
                if core + self.SPEC_MIN <= avail:
                    break
            left = max(0, avail - core - self.SPEC_MIN)
            # Rest: Spektrum wächst etwas (max. SPEC_MAX), alles andere bekommt "als nächstes"
            upcoming = max(0, len(self.p.queue) - self.p.index - 1) if self.p.index >= 0 else 0
            first = self.upnext.get_first_child()
            row_h = max(20, self._h(first, inner - 40)) if first else 28   # echte Zeilenhöhe messen
            chrome = 22 + 12 + 10 + 4                        # Kasten-Kopf/-Boden/Abstand
            spec_extra = min(self.SPEC_MAX - self.SPEC_MIN, int(left * 0.15))
            fit = max(0, int((left - spec_extra - chrome) // row_h)) if left - spec_extra >= chrome + row_h else 0
            fit = min(fit, 40)
            if fit > upcoming and self.p.autoplay and self.p.current:
                self.p.extend_radio()  # Platz für mehr: Warteschlange mit passenden Titeln auffüllen
            n = min(upcoming, fit)
            used = (chrome + n * row_h) if n else 0
            spec_extra = min(self.SPEC_MAX - self.SPEC_MIN, max(0, left - used))
            if n != self.upnext_n:
                self.upnext_n = n
                self.update_queue()
            self.spec.set_height(self.SPEC_MIN + max(0, spec_extra))
            self._fix_tries = 0
            GLib.timeout_add(60, self.fix_overflow, row_h, upcoming)
        else:
            self.spec.set_height(max(self.SPEC_MIN, min(96, int(H * 0.09))))
        self.spec.set_visible(H >= 300 and self.current_tab() != "visuals" and not self.focus_mode)
        return False

    def fix_overflow(self, row_h, upcoming):
        """Schätzung exakt machen: steht Tab 1 über (Scrollbalken) → Zeilen weg; ist unten Platz → dazu."""
        if self.current_tab() != "now" or not self.upnext_panel.get_visible() and self.upnext_n == 0:
            return False
        adj = self.now_page.get_parent().get_vadjustment() if isinstance(self.now_page.get_parent(), Gtk.Viewport) \
            else self.now_page.get_ancestor(Gtk.ScrolledWindow).get_vadjustment()
        over = adj.get_upper() - adj.get_page_size()
        n = self.upnext_n
        if over > 0.5 and n > 0:
            n = max(0, n - max(1, int(-(-over // row_h))))
        elif over <= 0.5:
            free = adj.get_page_size() - self.now_page.measure(Gtk.Orientation.VERTICAL, self.now_page.get_width())[1]
            if free >= row_h and n < upcoming:
                n = min(upcoming, n + int(free // row_h))
        self._fix_tries += 1
        if n != self.upnext_n and self._fix_tries <= 4:
            self.upnext_n = n
            self.update_queue()
            GLib.timeout_add(60, self.fix_overflow, row_h, upcoming)
        return False

    def on_resize(self, width, height):
        # Stufen: so passt musicalist auch in eine Achtel-Kachel (360 px) – vorher war das Fenster
        # mindestens ~530 px breit, Hyprland und GTK stritten dann um die Größe (ruckeln).
        self.set_tier(0 if width >= 820 else 1 if width >= 600 else 2 if width >= 440 else 3)
        self.schedule_relayout()
        if self.current_tab() == "lyrics":
            self.center_lyric(jump=True)

    def tab_changed(self, tab):
        self.schedule_relayout()
        self.nav_note()
        self.update_tab_labels()
        if tab == "visuals":
            self.visuals.update_track()
        if tab == "lyrics":
            self.load_lyrics()
            GLib.timeout_add(60, lambda: self.sync_lyrics(jump=True) and False)
        if tab == "search":
            GLib.idle_add(lambda: self.query.grab_focus() and False)

    def _key(self, c, kv, code, state):
        """Vor tui.TuiWindow._key (das Esc sonst immer schluckt): Vollbild/Leiste schließen."""
        if state & Gdk.ModifierType.ALT_MASK and not state & Gdk.ModifierType.CONTROL_MASK:
            # Alt+1…6 wechselt den Tab immer – auch während man im Suchfeld tippt
            i = {Gdk.KEY_1: 0, Gdk.KEY_2: 1, Gdk.KEY_3: 2, Gdk.KEY_4: 3, Gdk.KEY_5: 4, Gdk.KEY_6: 5,
                 Gdk.KEY_7: 6, Gdk.KEY_8: 7, Gdk.KEY_9: 8}.get(kv)
            tabs = [t for t, _n, _i in self.TABS if t != "settings"]
            if i is not None and i < len(tabs):
                if isinstance(self.get_focus(), (Gtk.Text, Gtk.Entry)) and tabs[i] != "search":
                    self.set_focus(None)
                self.show_tab(tabs[i])
                return True
        if kv == Gdk.KEY_Escape and getattr(self, "focus_mode", False):
            self.toggle_focus(False)
            return True
        if kv == Gdk.KEY_Escape and hasattr(self, "drawer") and self.drawer.is_open():
            self.drawer.close()
            return True
        return tui.TuiWindow._key(self, c, kv, code, state)

    def on_key(self, _c, kv, _code, state):
        focus = self.get_focus()
        if isinstance(focus, (Gtk.Text, Gtk.Entry)) or state & (Gdk.ModifierType.CONTROL_MASK |
                                                                 Gdk.ModifierType.ALT_MASK):
            return False
        if kv == Gdk.KEY_space:
            self.p.toggle()
        elif kv == Gdk.KEY_n:
            self.p.next()
        elif kv == Gdk.KEY_p:
            self.p.prev()
        elif kv == Gdk.KEY_l:
            self.p.like()
        elif kv == Gdk.KEY_slash:
            self.show_tab("search")
        elif kv == Gdk.KEY_h:
            if engine.setting("history"):
                self.drawer.toggle()
            else:
                self.say("hörverlauf ist aus – einschalten unter einstellungen (,)")
        elif kv == Gdk.KEY_a:
            if self.p.current:
                anchor = self.pl_btn if self.current_tab() == "now" and self.pl_btn.get_mapped() else self.statusbar
                pop = self.songs.picker(anchor, [self.p.current])
                if pop is not None and anchor is self.statusbar:
                    pop.set_position(Gtk.PositionType.TOP)
        elif kv in (Gdk.KEY_question, Gdk.KEY_F1):
            self.show_keys()
        elif kv in (Gdk.KEY_bracketleft, Gdk.KEY_bracketright):
            self.shift_lyrics(-0.25 if kv == Gdk.KEY_bracketleft else 0.25)
        elif kv == Gdk.KEY_comma:
            self.show_tab("settings")
        elif kv == Gdk.KEY_s:
            self.sleep_menu()
        elif kv == Gdk.KEY_e:
            self.sound_menu()
        elif kv == Gdk.KEY_f and self.current_tab() == "visuals":
            self.toggle_focus()
        elif kv == Gdk.KEY_v and self.current_tab() == "visuals":
            self.visuals.cycle()
        elif kv in (Gdk.KEY_Left, Gdk.KEY_Right) and not isinstance(focus, tui.Meter):
            self.p.seek(-5 if kv == Gdk.KEY_Left else 5, relative=True)
        elif kv in (Gdk.KEY_plus, Gdk.KEY_KP_Add, Gdk.KEY_equal):
            self.p.set_volume(self.p.volume + 5)
        elif kv in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            self.p.set_volume(self.p.volume - 5)
        else:
            return False
        return True




class NoPreview:
    """Ersatz, wenn die Vorschau nicht geht – gleiche Schnittstelle, tut nichts."""
    def hide(self):
        pass

    def set_enabled(self, on):
        pass

    def apply_desk(self):
        pass


def cursor_pos():
    """Zeigerposition (logische Pixel) direkt vom Hyprland-Socket – None, wenn das nicht klappt."""
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not sig:
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            s.connect(f"{RUNTIME}/hypr/{sig}/.socket.sock")
            s.sendall(b"j/cursorpos")
            data = b""
            while chunk := s.recv(4096):
                data += chunk
        d = json.loads(data)
        return d["x"], d["y"]
    except (OSError, ValueError, KeyError):
        return None




class Preview:
    """Unsichtbarer Streifen am unteren Bildschirmrand (Mitte). Maus drauf → Karte mit Titel, Fortschritt
    und Knöpfen gleitet hoch; Maus weg → verschwindet wieder. Klick auf den Titel öffnet den Player."""
    WIDTH = 520

    def __init__(self, app, player, cava, open_player, srcs, desk=False):
        self.p, self.cava, self.open_player, self.srcs = player, cava, open_player, srcs
        self.show_id = self.hide_id = self.watch_id = None
        self.outside_ms = 0
        self.desk = desk
        if desk:                       # Anzeige auf dem Hintergrundbild: nur die Karte, immer da
            self.trigger = None
            self.build_card(app)
            self.p.listeners.append(self.on_player)
            cava.listeners.append(self.on_spectrum)
            self.enabled = False
            return

        self.trigger = Gtk.Window(application=app)
        self.trigger.add_css_class("preview-trigger")
        Layer.init_for_window(self.trigger)
        Layer.set_namespace(self.trigger, "music-trigger")
        Layer.set_layer(self.trigger, Layer.Layer.OVERLAY)  # OVERLAY: liegt auch über Vollbild-Fenstern
        Layer.set_anchor(self.trigger, Layer.Edge.BOTTOM, True)
        Layer.set_exclusive_zone(self.trigger, 0)
        Layer.set_keyboard_mode(self.trigger, Layer.KeyboardMode.NONE)
        self.trigger.set_child(Gtk.Box(width_request=360, height_request=3))
        self.trigger.set_default_size(360, 3)
        self.trigger.set_size_request(360, 3)
        self.trigger.set_resizable(False)
        m = Gtk.EventControllerMotion()
        m.connect("enter", lambda *_: self.arm())
        m.connect("leave", lambda *_: self.disarm())
        self.trigger.add_controller(m)
        self.build_card(app)
        self.p.listeners.append(self.on_player)
        cava.listeners.append(self.on_spectrum)
        self.enabled = False
        self.set_enabled(engine.setting("hover"))

    def build_card(self, app):
        desk = self.desk
        self.card = Gtk.Window(application=app)
        self.card.add_css_class("preview")
        Layer.init_for_window(self.card)
        Layer.set_namespace(self.card, "music-desk" if desk else "music-preview")
        # Hintergrund: BOTTOM = über dem Hintergrundbild, unter allen Fenstern
        Layer.set_layer(self.card, Layer.Layer.BOTTOM if desk else Layer.Layer.OVERLAY)
        if desk:
            self.place_desk()
        else:
            Layer.set_anchor(self.card, Layer.Edge.BOTTOM, True)
            Layer.set_margin(self.card, Layer.Edge.BOTTOM, 10)
        Layer.set_exclusive_zone(self.card, 0)
        Layer.set_keyboard_mode(self.card, Layer.KeyboardMode.NONE)   # Tastatur nur, solange die Karte offen ist
        self.card.set_default_size(self.WIDTH, 1)     # sonst ist die Fläche teils zu hoch (leerer Rest unten)
        self.card.set_resizable(False)
        if not desk:
            # CAPTURE: vor den Knöpfen – sonst "klickt" die Leertaste den fokussierten Knopf (z. B. den Titel,
            # der den Player öffnet), statt Play/Pause auszulösen
            keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
            keys.connect("key-pressed", self.on_key)
            self.card.add_controller(keys)
            m = Gtk.EventControllerMotion()
            m.connect("enter", lambda *_: self.cancel_hide())
            m.connect("leave", lambda *_: self.hide_soon(350))
            self.card.add_controller(m)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.add_css_class("pcard")
        box.set_size_request(self.WIDTH, -1)
        self.cover = DotCover()
        self.title = label("", "np-title", ellipsize=True, hexpand=True)
        self.artist = label("", "np-artist", ellipsize=True)
        title_btn = Gtk.Button(hexpand=True)
        title_btn.add_css_class("ptitle")
        title_btn.set_child(vbox(self.title, self.artist, spacing=3))
        title_btn.set_tooltip_text("Player öffnen")
        title_btn.connect("clicked", lambda *_: (self.desk or self.hide(), self.open_player()))
        self.prev = tui.Button("󰒮", self.p.prev)
        self.play = tui.Button("󰐊", self.p.toggle)
        self.next = tui.Button("󰒭", lambda: self.p.next())
        for b in (self.prev, self.play, self.next):
            b.add_css_class("ctl")
        self.like = Gtk.Button(valign=Gtk.Align.START)
        self.like.add_css_class("plike")
        self.like.connect("clicked", lambda *_: self.p.like())
        self.pos = label("", "dim", xalign=1)
        self.seek = tui.Meter(1000, lambda v: self.p.dur and self.p.seek(v / 1000 * self.p.dur), small=True,
                               mark=False, flush=True, scroll="h")
        self.spec = Spectrum(rows=1, cell=8, height=16, flush=True)
        right = vbox(hbox(title_btn, self.like, spacing=8),
                     hbox(self.prev, self.play, self.next, label("", hexpand=True), self.pos, spacing=6),
                     self.seek, spacing=8, hexpand=True)
        box.append(hbox(self.cover, right, spacing=14))
        box.append(self.spec)
        # Was sonst gerade Ton macht (früher das mpris-Modul in der Waybar)
        if not desk:                   # auf dem Hintergrund nicht: das hieße dauernd pactl abfragen
            self.src_list = sources.SourceList(self.srcs, limit=3)
            self.src_list.add_css_class("src-sep")
            box.append(self.src_list)
        self.card.set_child(box)
        # Cover oben bündig mit der Oberkante der Titelschrift, unten mit den Balkenquadraten
        ink = self.title.create_pango_layout("Hdlk").get_pixel_extents()[0]
        self.cover.set_insets(ink.y, self.seek.square_inset())
        # Größe gleich passend vorgeben (sonst springt es beim ersten Einblenden einmal)
        h = right.measure(Gtk.Orientation.VERTICAL, -1)[1]
        self.cover.set_content_width(max(40, round(h - self.cover.top - self.cover.bottom)))

    def place_desk(self):
        pos = engine.setting("desk_pos") or "bottom"
        for e in (Layer.Edge.TOP, Layer.Edge.BOTTOM, Layer.Edge.LEFT, Layer.Edge.RIGHT):
            Layer.set_anchor(self.card, e, False)
        edges = {"bottom": (Layer.Edge.BOTTOM,), "bottom-left": (Layer.Edge.BOTTOM, Layer.Edge.LEFT),
                 "bottom-right": (Layer.Edge.BOTTOM, Layer.Edge.RIGHT), "top-left": (Layer.Edge.TOP, Layer.Edge.LEFT),
                 "top-right": (Layer.Edge.TOP, Layer.Edge.RIGHT)}.get(pos, (Layer.Edge.BOTTOM,))
        for e in edges:
            Layer.set_anchor(self.card, e, True)
            Layer.set_margin(self.card, e, 24 if e != Layer.Edge.BOTTOM or len(edges) > 1 else 10)

    def apply_desk(self):
        """Einstellungen „anzeige immer auf dem hintergrundbild“ / Position übernehmen."""
        on = bool(engine.setting("desk"))
        self.place_desk()
        self.enabled = on
        if on:
            self.update()
            self.card.set_visible(True)
        else:
            self.card.set_visible(False)
        self.cava.want("desk", on)

    def set_enabled(self, on):
        """Vorschau an/aus (Einstellungen). Aus = kein Auslöse-Streifen am Bildschirmrand."""
        self.enabled = bool(on)
        if self.enabled:
            self.trigger.present()
        else:
            if self.show_id is not None:
                GLib.source_remove(self.show_id)
                self.show_id = None
            self.watch_id = None
            self.hide_now()
            self.trigger.set_visible(False)

    # ----- ein/aus -----
    def arm(self):
        if not self.enabled:
            return
        self.cancel_hide()
        if self.show_id is None and not self.card.get_visible():
            self.show_id = GLib.timeout_add(140, self.show)  # kurz verweilen: kein Aufpoppen im Vorbeiziehen

    def disarm(self):
        if self.show_id is not None:
            GLib.source_remove(self.show_id)
            self.show_id = None
        if self.card.get_visible():
            self.hide_soon(900)  # Zeit, um mit der Maus auf die Karte zu fahren

    def show(self):
        self.show_id = None
        self.update()
        # solange die Karte offen ist, gehört ihr die Tastatur: Leertaste = Play/Pause
        Layer.set_keyboard_mode(self.card, Layer.KeyboardMode.EXCLUSIVE)
        self.card.set_visible(True)
        self.card.set_focus(None)        # kein Knopf vorausgewählt
        self.cava.want("preview", True)
        # Enter/Leave der Karte sind unter Hyprland unzuverlässig (falsches "leave" mitten auf der Karte,
        # danach keins mehr) – deshalb selbst nachsehen, wo der Zeiger ist.
        if self.watch_id is None and cursor_pos() is not None:
            self.outside_ms = -750           # anfangs Zeit, um vom Streifen auf die Karte zu fahren
            self.watch_id = GLib.timeout_add(150, self.watch)
        self.srcs.want("preview", True)
        return False

    def hide_soon(self, ms):
        self.cancel_hide()
        self.hide_id = GLib.timeout_add(ms, self.hide)

    def cancel_hide(self):
        if self.hide_id is not None:
            GLib.source_remove(self.hide_id)
            self.hide_id = None

    def pointer_inside(self):
        pos = cursor_pos()
        if pos is None:
            return None
        surf = self.card.get_surface()
        mon = surf and self.card.get_display().get_monitor_at_surface(surf)
        if not mon:
            return None
        g = mon.get_geometry()
        w, h = self.card.get_width(), self.card.get_height()
        x0, y1 = g.x + (g.width - w) / 2, g.y + g.height          # Karte sitzt unten mittig, 10 px Abstand
        pad = 6
        # Karte plus der Spalt darunter bis zum Bildschirmrand (dort liegt der Auslöse-Streifen)
        return x0 - pad <= pos[0] <= x0 + w + pad and y1 - 10 - h - pad <= pos[1] <= y1

    def watch(self):
        if not self.card.get_visible():
            self.watch_id = None
            return False
        inside = self.pointer_inside()
        if inside is None:             # Socket weg → wieder den Enter/Leave-Ereignissen überlassen
            self.watch_id = None
            return False
        if inside:
            self.outside_ms = min(self.outside_ms, 0)
            self.cancel_hide()
        else:
            self.outside_ms += 150
            if self.outside_ms >= 300:
                self.watch_id = None
                self.hide()
                return False
        return True

    def hide(self):
        self.hide_id = None
        if self.watch_id is not None and self.pointer_inside():
            return False               # Zeiger ist noch auf der Karte – offen lassen
        Layer.set_keyboard_mode(self.card, Layer.KeyboardMode.NONE)   # Fokus zurück an das Fenster darunter
        self.card.set_visible(False)
        self.cava.want("preview", False)
        self.srcs.want("preview", False)
        return False

    def on_key(self, ctrl, keyval, code, state):
        if keyval in (Gdk.KEY_space, Gdk.KEY_KP_Space):
            self.p.toggle()
            return True
        if keyval in (Gdk.KEY_Right, Gdk.KEY_l, Gdk.KEY_n):
            self.p.next()
            return True
        if keyval in (Gdk.KEY_Left, Gdk.KEY_h, Gdk.KEY_p):
            self.p.prev()
            return True
        if keyval == Gdk.KEY_Escape:
            self.watch_id = None
            self.hide_now()
            return True
        return False

    def hide_now(self):
        self.cancel_hide()
        Layer.set_keyboard_mode(self.card, Layer.KeyboardMode.NONE)
        self.card.set_visible(False)
        self.cava.want("preview", False)
        self.srcs.want("preview", False)

    # ----- Inhalt -----
    def on_player(self, what):
        if self.card.get_visible() and what in ("track", "state", "pos"):
            self.update()

    def on_spectrum(self, vals):
        if self.card.get_visible():
            self.spec.set_vals(vals)

    def update(self):
        p, t = self.p, self.p.current
        self.cover.show(t["thumb"] if t else None)
        self.title.set_label(t["title"] if t else "nichts läuft")
        self.artist.set_label(t["artist"] if t else "musicalist")
        self.like.set_label("󰋑" if t and t.get("liked") else "󰋕")
        self.play.set_label("󰏤" if not p.paused and p.started else "󰐊")
        dur = p.dur or (t or {}).get("duration") or 0
        self.pos.set_label(f"{fmt(p.pos)} / {fmt(dur)}")
        self.seek.set_value(int(p.pos / dur * 1000) if dur else 0)
