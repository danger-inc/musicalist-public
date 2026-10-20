# musicalist – Oberfläche: Hauptfenster (Tabs jetzt/warteschlange/bibliothek/lyrics/visuals/suchen) und die
# Vorschau-Karte unten mittig (erscheint, wenn die Maus an den unteren Bildschirmrand in der Mitte fährt).
# Alles im TUI-Stil aus ../tui.py: Cover als Braille-Pixelbild, Spektrum aus ▁▂▃▅▇ (cava), ■-Regler.
import json, os, re, socket, subprocess, threading, time, urllib.request

import gi
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Graphene, Gtk, Pango, PangoCairo
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
import sources
import swipe
import verlauf
import visuals

RUNTIME = GLib.get_user_runtime_dir()

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
.row.playing > button.rowhead { background-color: alpha(@primary, 0.16); }
.row.playing .trk-title { color: @primary; }
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
""" + sources.CSS + visuals.CSS + verlauf.CSS
TICKS = " ▁▂▃▄▅▆▇█"


# ---------- Cover als Braille ----------
_thumbs = {}


def big_thumb(url, size=300):
    return re.sub(r"=w\d+-h\d+", f"=w{size}-h{size}", url) if url else url


def fetch_pixbuf(url):
    if url in _thumbs:
        return _thumbs[url]
    data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": engine.UA}), timeout=8).read()
    loader = GdkPixbuf.PixbufLoader()
    loader.write(data)
    loader.close()
    pb = loader.get_pixbuf()
    if len(_thumbs) > 60:
        _thumbs.clear()
    _thumbs[url] = pb
    return pb


BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
DOTS = [(0, 0, 0x01), (0, 1, 0x02), (0, 2, 0x04), (1, 0, 0x08), (1, 1, 0x10), (1, 2, 0x20), (0, 3, 0x40), (1, 3, 0x80)]


def dither(pb, w, h):
    """Bild → w×h Punkte (True = an): Histogramm-Ausgleich + Bayer-Rasterung."""
    pb = pb.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR)
    px, stride, nch = pb.get_pixels(), pb.get_rowstride(), pb.get_n_channels()
    lum = [[0.0] * w for _ in range(h)]
    for y in range(h):
        o = y * stride
        for x in range(w):
            i = o + x * nch
            lum[y][x] = 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2]
    # Histogramm-Ausgleich: jede Helligkeit bekommt ihren Rang (0–1) → auch dunkle Cover zeigen Details
    flat = sorted(v for row in lum for v in row)
    total = len(flat)
    rank, first = {}, {}
    for i, v in enumerate(flat):   # gleiche Helligkeit → mittlerer Rang (große einfarbige Flächen = Halbton)
        first.setdefault(v, i)
        rank[v] = (first[v] + i) / 2 / total
    return [[rank[lum[y][x]] * 16 > BAYER[y % 4][x % 4] + 0.5 for x in range(w)] for y in range(h)]


def braille(pb, cols, rows):
    """Bild → Braille-Zeichen (2×4 Punkte je Zeichen)."""
    # Cover sind quadratisch; Zeichen sind ~2× so hoch wie breit → Braille passt (2×4 Punkte) 1:1
    on = dither(pb, cols * 2, rows * 4)
    lines = []
    for cy in range(rows):
        line = []
        for cx in range(cols):
            bits = 0
            for dx, dy, bit in DOTS:
                if on[cy * 4 + dy][cx * 2 + dx]:
                    bits |= bit
            line.append(chr(0x2800 + bits))
        lines.append("".join(line))
    return "\n".join(lines)


def halftone(url, n):
    """Cover → n×n Helligkeiten 0–1 (Histogramm-Ausgleich wie dither(), aber stufenlos) für visuals „orbit“."""
    pb = fetch_pixbuf(big_thumb(url)).scale_simple(n, n, GdkPixbuf.InterpType.BILINEAR)
    px, stride, nch = pb.get_pixels(), pb.get_rowstride(), pb.get_n_channels()
    lum = [[0.299 * px[y * stride + x * nch] + 0.587 * px[y * stride + x * nch + 1] + 0.114 * px[y * stride + x * nch + 2]
            for x in range(n)] for y in range(n)]
    flat = sorted(v for row in lum for v in row)
    total = len(flat)
    rank, first = {}, {}
    for i, v in enumerate(flat):
        first.setdefault(v, i)
        rank[v] = (first[v] + i) / 2 / total
    return [[rank[v] for v in row] for row in lum]


def placeholder(cols, rows):
    """Leeres Cover: ein Notensymbol aus Rahmenzeichen."""
    lines = []
    for y in range(rows):
        if y in (0, rows - 1):
            lines.append(("╭" if y == 0 else "╰") + "─" * (cols - 2) + ("╮" if y == 0 else "╯"))
        elif y == rows // 2:
            mid = "♪ nichts läuft"
            pad = cols - 2 - len(mid)
            lines.append("│" + " " * (pad // 2) + mid + " " * (pad - pad // 2) + "│")
        else:
            lines.append("│" + " " * (cols - 2) + "│")
    return "\n".join(lines)


class Cover(Gtk.Label):
    def __init__(self, cols, rows, small=False):
        super().__init__(xalign=0, yalign=0, valign=Gtk.Align.START)
        self.add_css_class("cover")
        if small:
            self.add_css_class("small")
        self.cols, self.rows, self.url = cols, rows, None
        self.set_label(placeholder(cols, rows))

    def set_size(self, cols, rows):
        if (cols, rows) == (self.cols, self.rows):
            return
        self.cols, self.rows = cols, rows
        url, self.url = self.url, None
        self.show(url)  # neu rastern (Bild kommt aus dem Zwischenspeicher)

    def show(self, url):
        if url == self.url:
            return
        self.url = url
        if not url:
            self.set_label(placeholder(self.cols, self.rows))
            return

        def work():
            return braille(fetch_pixbuf(big_thumb(url)), self.cols, self.rows)

        def done(res):
            if self.url == url and isinstance(res, str):
                self.set_label(res)
        tui.background(work, done=done)


class DotCover(Gtk.DrawingArea):
    """Cover als gezeichnetes Punktraster (Braille-Look), immer quadratisch und so hoch, wie die Zeile
    es zulässt – damit es oben und unten genau mit den Nachbarn abschließt. Aus-Punkte bleiben schwach
    sichtbar, so ist das Quadrat auch bei dunklen Covern klar begrenzt."""
    DOTS = 36

    def __init__(self, size=88):
        super().__init__(valign=Gtk.Align.FILL, halign=Gtk.Align.START)
        self.url, self.on = None, None
        self.top = self.bottom = 0.0   # Abstand zur sichtbaren Kante der Nachbarn (Schrift/Balken)
        self.set_content_width(size)
        self.set_draw_func(self._draw)
        self.connect("resize", self._resized)

    def set_insets(self, top, bottom):
        self.top, self.bottom = top, bottom
        h = self.get_height()
        if h > 0:
            self._resized(None, self.get_width(), h)
        self.queue_draw()

    def _resized(self, _a, w, h):
        side = round(h - self.top - self.bottom)
        if h > 0 and w != side:   # Breite = sichtbare Höhe; nicht mitten in der Größenberechnung ändern
            GLib.idle_add(lambda: self.set_content_width(side) and False)

    def show(self, url):
        if url == self.url:
            return
        self.url, self.on = url, None
        self.queue_draw()
        if not url:
            return

        def done(res):
            if self.url == url and isinstance(res, list):
                self.on = res
                self.queue_draw()
        tui.background(lambda: dither(fetch_pixbuf(big_thumb(url)), self.DOTS, self.DOTS), done=done)

    def _draw(self, _a, cr, width, height):
        c = tui.colors()
        p, fg = c.get("primary"), c.get("foreground")
        n = self.DOTS
        side = min(width, height - self.top - self.bottom)
        cr.translate(0, self.top)
        pitch = side / n
        r = pitch * 0.36
        on = self.on
        for y in range(n):
            for x in range(n):
                lit = on is not None and on[y][x]
                col, a = (p, 1.0) if lit else (fg, 0.10)
                cr.set_source_rgba(col.red, col.green, col.blue, a)
                cr.arc((x + 0.5) * pitch, (y + 0.5) * pitch, r, 0, 6.2832)
                cr.fill()
        if on is None:          # nichts läuft / lädt noch: Note in der Mitte
            layout = self.create_pango_layout("♪" if not self.url else "⠿")
            layout.set_font_description(Pango.FontDescription.from_string(f"{tui.FONT} Bold {max(8, int(side / 4))}"))
            tw, th = layout.get_pixel_size()
            cr.set_source_rgba(p.red, p.green, p.blue, 0.85)
            cr.move_to((side - tw) / 2, (side - th) / 2)
            PangoCairo.show_layout(cr, layout)


# ---------- Spektrum (cava) ----------
class Cava:
    """cava im Raw-Modus: liefert Balkenhöhen 0–16. Läuft nur, solange jemand zuschaut (ref-Zählung)."""

    def __init__(self, bars=64):
        self.bars, self.users, self.proc = bars, set(), None
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

    def want(self, who, on):
        (self.users.add if on else self.users.discard)(who)
        if self.users and self.proc is None:
            if not shutil.which("cava"):
                return                      # cava fehlt → Spektrum bleibt einfach leer
            self.proc = tui.spawn_watch(["cava", "-p", self.cfg], stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True)
            threading.Thread(target=self.read, args=(self.proc,), daemon=True).start()
        elif not self.users and self.proc is not None:
            self.proc.terminate()
            self.proc = None

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


# ---------- Listen ----------
def track_row(t, on_play, actions):
    """Zeile: ▶ titel  künstler  album  3:45  [+] [»] …  actions: [(glyph, tooltip, fn)]"""
    row = Gtk.Box()
    row.add_css_class("row")
    head = Gtk.Button(hexpand=True)
    head.add_css_class("rowhead")
    row.mark = label("", "trk-mark")
    row.title = label(t["title"], "trk-title", hexpand=True, ellipsize=True)
    row.artist = label(t["artist"], "dim", ellipsize=True)
    row.artist.set_max_width_chars(24)
    row.artist.set_width_chars(6)
    row.dur = label(fmt(t["duration"]) if t["duration"] else "", "dim", xalign=1)
    row.dur.set_width_chars(6)
    head.set_child(hbox(row.mark, row.title, row.artist, row.dur, spacing=10))
    head.connect("clicked", lambda *_: on_play())
    row.append(head)
    for glyph, tip, fn in actions:
        b = Gtk.Button(label=glyph, tooltip_text=tip, valign=Gtk.Align.CENTER)
        b.add_css_class("mini")
        b.connect("clicked", lambda _b, f=fn: f())
        row.append(b)
    row.track = t
    return row


def coll_row(glyph, title, sub, on_open):
    row = Gtk.Box()
    row.add_css_class("row")
    head = Gtk.Button(hexpand=True)
    head.add_css_class("rowhead")
    head.set_child(hbox(label(glyph, "glyph"), label(title, hexpand=True, ellipsize=True), label(sub, "dim"),
                        label("›", "accent"), spacing=10))
    head.connect("clicked", lambda *_: on_open())
    row.append(head)
    return row


# ---------- Hauptfenster ----------
class MusicWindow(tui.TuiWindow):
    APP_ID = "de.invincible.Music"
    TABS = [("now", "jetzt", "󰝚"), ("queue", "warteschlange", "󰲸"), ("lib", "bibliothek", "󰋑"),
            ("lyrics", "lyrics", "󰗊"), ("visuals", "visuals", "󱑽"), ("search", "suchen", "󰍉"),
            ("settings", "einstellungen", "󰒓")]   # einstellungen: kein Tab, sondern ⚙ oben rechts
    ESC_CLOSES = False          # Esc soll den Player nicht zumachen (nur Super+M / q / ✕)

    def __init__(self, app, player, cava, srcs):
        super().__init__(app, "󰝚 musicalist", [(t, n, i) for t, n, i in self.TABS],
                         size=(900, 700), icons_only=True, hints=(("leer", "play"), ("n/p", "weiter/zurück"), ("/", "suche"),
                                                 ("l", "♥")))
        self.p, self.cava, self.srcs = player, cava, srcs
        css = Gtk.CssProvider()
        css.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        self.account = None
        self.lyrics_vid = None
        self.lyric_lines = []
        self.detail_tracks = []

        self.tier = 0                  # 0 breit … 3 sehr schmal (Achtel-Kachel), setzt on_resize
        self.focus_mode = False
        self.detail_key, self.detail_names = None, {}
        self._shorten = []             # (knopf, lang, kurz) – schmale Fenster bekommen die kurze Beschriftung
        self.build_header()
        self.add_changelog("musicalist", os.path.dirname(os.path.realpath(__file__)))
        self.header_extra.reorder_child_after(self.changelog_btn, self.np_chip)

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
                                     where=self.nav_where, target=self.nav_target)
        self.content.prepend(self.swipe.widget)
        # Hörverlauf-Leiste am rechten Rand (verlauf.py) um den ganzen Inhalt
        root = self.get_child()
        root.remove(self.content)
        self.drawer = verlauf.HistoryDrawer(self, self.content, player,
                                            lambda: bool(engine.setting("history_pinned")),
                                            lambda on: engine.set_setting("history_pinned", on))
        root.insert_child_after(self.drawer.widget, self.topbar)
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
        first = self.hint_box.get_first_child()
        if first is not None and first.get_first_child() is not None:
            first.get_first_child().set_label(f"1-{len(self.TABS) - 1}")
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
        item("󰋚", "hörverlauf", self.drawer.toggle, "h")
        rub("")
        item("󰒓", "einstellungen", lambda: self.show_tab("settings"), ",")
        item("↗", "youtube music im browser", lambda: subprocess.Popen(["xdg-open", "https://music.youtube.com"],
                                                                         start_new_session=True))
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
        self.changelog_btn.set_visible(tier == 0)
        if self.glass_btn is not None:
            self.glass_btn.set_visible(tier < 3)
        self.gear_btn.set_visible(tier < 3)
        for b, long, short in self._shorten:
            b.set_label(short if tier >= 2 else long)
        for chk in (self.hover_chk, self.bg_chk):
            chk.text.set_wrap(tier >= 1)
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
            return self.detail_names.get(loc[1:], {"album": "album", "artist": "künstler",
                                                    "history": "verlauf"}.get(loc[1], "playlist"))
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
        self.visuals.bar.set_visible(not on)
        self.visuals.full_btn.set_visible(not on)
        self.visuals.hint.set_label("esc zurück" if on else "v modus · f vollbild")
        (self.fullscreen if on else self.unfullscreen)()
        self.schedule_relayout()
        self.update_tab_labels()

    # ---------- einstellungen ----------
    def build_settings(self):
        page = vbox(spacing=8)
        page.set_margin_top(6)
        # ganz oben: Konto (Status + Anmeldung neu einlesen) – der Kontoname wird nie gezeigt
        self.set_acct = vbox(spacing=8)
        page.append(tui.Panel("󰀄 konto", self.set_acct))
        self.fill_settings_account()
        panel = tui.Panel("einstellungen")
        self.hover_chk = tui.Check("vorschau-karte am unteren bildschirmrand (hover)", engine.setting("hover"),
                                   self.set_hover,
                                   tooltip="Maus an den unteren Bildschirmrand → kleine Karte mit Titel und Knöpfen")
        panel.body.append(self.hover_chk)
        if preview_supported():
            hint = "braucht wayland mit layer-shell (hyprland, sway …). bei problemen einfach aus lassen."
        else:
            hint = "hier nicht verfügbar: braucht gtk4-layer-shell und einen wayland-compositor mit layer-shell."
            self.hover_chk.set_sensitive(False)
        panel.body.append(label(hint, "dim", wrap=True, xalign=0))
        self.bg_chk = tui.Check("beim schließen im hintergrund weiterspielen", engine.setting("background"),
                                lambda on: engine.set_setting("background", on),
                                tooltip="Aus: ✕ / q beendet musicalist ganz, die Musik stoppt.\n"
                                        "An: das Fenster verschwindet nur, die Musik läuft weiter.")
        self.bg_chk.set_margin_top(10)
        panel.body.append(self.bg_chk)
        panel.body.append(label("aus: ✕ / q beendet musicalist, die musik stoppt. an: nur das fenster geht zu.",
                                "dim", wrap=True, xalign=0))
        page.append(panel)
        self.add_page("settings", page)
        self.on_hover_changed = None       # setzt musicd: schaltet die Vorschau live ein/aus

    def fill_settings_account(self):
        box = getattr(self, "set_acct", None)
        if box is None:
            return
        tui.clear(box)
        if self.account is not None:
            box.append(hbox(label("● angemeldet · youtube music", "accent", hexpand=True, ellipsize=True),
                            tui.Button("󰑐 anmeldung neu einlesen", self.login,
                                       tooltip="Anmeldung erneut aus Zen/Firefox übernehmen"),
                            tui.Button("abmelden", self.do_logout, danger=True), spacing=8))
        else:
            box.append(hbox(label("○ nicht angemeldet", "dim", hexpand=True),
                            tui.Button("󰍂 mit zen / firefox anmelden", self.login), spacing=8))
        box.append(label("liest die anmeldung aus deinem browser (music.youtube.com) – nötig, wenn likes, "
                         "bibliothek oder radio nicht mehr gehen.", "dim", wrap=True, xalign=0))

    def set_hover(self, on):
        engine.set_setting("hover", on)
        if self.on_hover_changed:
            self.on_hover_changed(on)

    # ---------- jetzt ----------
    def build_now(self):
        page = vbox(spacing=10)
        page.set_margin_top(8)
        self.cover = Cover(36, 18)
        self.title = label("", "np-title", wrap=True)
        self.title.set_lines(2)
        self.title.set_ellipsize(Pango.EllipsizeMode.END)
        self.artist = label("", "np-artist", ellipsize=True)
        self.album = label("", "np-album", ellipsize=True)
        self.info = label("", "dim", ellipsize=True)
        self.like_btn = tui.Button("", lambda: self.p.like(), tooltip="Gefällt mir (l)")
        self.radio_btn = tui.Button("󰐹 radio", lambda: (self.p.start_radio(), self.say("radio startet …")),
                                    tooltip="Ähnliche Titel als Warteschlange")
        self.web_btn = tui.Button("↗ browser", self.open_web, tooltip="In YouTube Music öffnen")
        acts = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=8, row_spacing=6,
                           max_children_per_line=6, homogeneous=False, halign=Gtk.Align.START)
        acts.add_css_class("opts")
        for w in (self.like_btn, self.radio_btn, self.web_btn):
            acts.append(w)
        self.np_gap = label("")
        self.np_acts = acts
        side = vbox(self.title, self.artist, self.album, self.np_gap, self.info, acts, spacing=4, hexpand=True)
        self.np_side = side
        self.np_box = hbox(self.cover, side, spacing=18)
        self.np_panel = tui.Panel("󰝚 läuft", self.np_box)
        page.append(self.np_panel)
        side.set_valign(Gtk.Align.CENTER)

        self.pos_lbl = label("0:00", "mono-pct")
        self.dur_lbl = label("0:00", "mono-pct", xalign=1)
        self.seek = tui.Meter(1000, self.on_seek, mark=False)
        self.prev_btn = tui.Button("󰒮", self.p.prev, tooltip="Zurück (p)")
        self.play_btn = tui.Button("󰐊", self.p.toggle, tooltip="Play/Pause (Leertaste)")
        self.next_btn = tui.Button("󰒭", lambda: self.p.next(), tooltip="Weiter (n)")
        for b in (self.prev_btn, self.play_btn, self.next_btn):
            b.add_css_class("ctl")
        self.play_btn.add_css_class("play")
        self.shuffle_btn = tui.Button("󰒝 mischen", self.p.shuffle_queue, tooltip="Warteschlange mischen")
        self.repeat_btn = tui.Button("", self.p.cycle_repeat, tooltip="Wiederholen: aus / alle / eins")
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
        for w in (self.shuffle_btn, self.repeat_btn, self.auto_chk,
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
        self.shuffle_btn.set_label("󰒝" if narrow else "󰒝 mischen")
        if t is not None:
            self.np_chip_lbl.set_label(f"{t['title']} · {t['artist']}")

    def on_seek(self, v):
        if self.p.dur:
            self.p.seek(v / 1000 * self.p.dur)

    def set_autoplay(self, on):
        self.p.autoplay = on
        self.p.save_soon()

    def open_web(self):
        t = self.p.current
        if t:
            subprocess.Popen(["xdg-open", f"https://music.youtube.com/watch?v={t['videoId']}"],
                             start_new_session=True)

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

    # ---------- Warteschlange ----------
    def build_queue(self):
        page = vbox(spacing=8)
        page.set_margin_top(6)
        self.queue_panel = tui.Panel("warteschlange")
        self.queue_box = vbox(spacing=0)
        self.queue_empty = label("leer – unter ⁶suchen titel auswählen", "empty", xalign=0.5)
        self.queue_panel.body.append(hbox(label("", hexpand=True),
                                          self._sh(tui.Button("󰒝 mischen", self.p.shuffle_queue), "󰒝 mischen", "󰒝"),
                                          self._sh(tui.Button("󰐹 radio auffüllen", self.p.extend_radio),
                                                     "󰐹 radio auffüllen", "󰐹 radio"),
                                          tui.Button("leeren", lambda: self.p.clear(), danger=True)))
        self.queue_panel.body.append(self.queue_box)
        self.queue_panel.body.append(self.queue_empty)
        page.append(self.queue_panel)
        self.add_page("queue", page)

    def update_queue(self):
        q = self.p.queue
        total = sum(t["duration"] or 0 for t in q)
        self.queue_panel.set_title(f"warteschlange <span alpha='60%'>{len(q)} titel · {fmt(total)}</span>",
                                   markup=True)
        self.queue_empty.set_visible(not q)

        def make(item):
            i, t = item
            return track_row(t, lambda r=None: self.p.jump(self._qi(t)),
                             [("↑", "Nach oben", lambda: self.p.move(self._qi(t), self._qi(t) - 1)),
                              ("↓", "Nach unten", lambda: self.p.move(self._qi(t), self._qi(t) + 1)),
                              ("✕", "Entfernen", lambda: self.p.remove(self._qi(t)))])

        def update(row, item):
            i, t = item
            playing = i == self.p.index
            row.mark.set_label("▶" if playing else f"{i + 1}")
            (row.add_css_class if playing else row.remove_css_class)("playing")
            (row.add_css_class if i < self.p.index else row.remove_css_class)("past")
        tui.sync_rows(self.queue_box, list(enumerate(q)), lambda it: id(it[1]), make, update)

        # "als nächstes" auf der Jetzt-Seite
        nxt = q[self.p.index + 1:self.p.index + 1 + self.upnext_n] if self.p.index >= 0 and self.upnext_n else []
        self.upnext_panel.set_visible(bool(nxt))
        tui.sync_rows(self.upnext, nxt, id, lambda t: track_row(t, lambda: self.p.jump(self._qi(t)), []),
                      lambda r, t: r.mark.set_label("›"))

    def _qi(self, t):
        for i, x in enumerate(self.p.queue):
            if x is t:
                return i
        return -1

    # ---------- Suche ----------
    def build_search(self):
        page = vbox(spacing=8)
        page.set_margin_top(6)
        self.query = tui.Entry("suchen … (enter)", activate=self.do_search)
        self.kind = tui.Select(lambda k: (self.kind.set_options(self.kind.options, k), self.do_search()))
        self.kind.set_options([(k, k) for k in ("songs", "alben", "playlists", "künstler", "videos")], "songs")
        page.append(tui.Panel("󰍉 suche", hbox(label("/", "accent"), self.query, self.kind, spacing=10)))
        self.results_panel = tui.Panel("ergebnisse")
        self.results = vbox(spacing=0)
        self.results_panel.body.append(self.results)
        self.results_panel.set_visible(False)
        page.append(self.results_panel)
        self.add_page("search", page)

    def do_search(self):
        q = self.query.get_text().strip()
        if not q:
            return
        kind = self.kind.current
        self.say(f"suche „{q}“ …", seconds=20)
        tui.background(self.p.music.search, q, kind, done=lambda r: self.show_results(r, kind, q))

    def show_results(self, res, kind, q):
        if isinstance(res, Exception):
            self.say(f"suche: {res}", error=True)
            return
        self.say(f"{len(res)} treffer")
        tui.clear(self.results)
        self.results_panel.set_visible(True)
        self.results_panel.set_title(f"ergebnisse <span alpha='60%'>{esc(kind)} · {len(res)}</span>", markup=True)
        if kind in ("songs", "videos"):
            tracks = [t for t in map(engine.track, res) if t]
            for t in tracks:
                self.results.append(self.song_row(t, tracks))
        elif kind == "alben":
            for a in res:
                arts = ", ".join(x["name"] for x in a.get("artists", []) if x.get("name"))
                self.results.append(coll_row("󰀥", a.get("title", "?"), f"{arts} · {a.get('year', '')}",
                                             lambda b=a["browseId"]: self.open_detail("album", b)))
        elif kind == "playlists":
            for pl in res:
                self.results.append(coll_row("󰲸", pl.get("title", "?"),
                                             f"{pl.get('author', '')} · {pl.get('itemCount', '')}",
                                             lambda b=pl["browseId"]: self.open_detail(
                                                 "playlist", b[2:] if b.startswith("VL") else b)))
        elif kind == "künstler":
            for a in res:
                self.results.append(coll_row("󰠃", a.get("artist", "?"), "",
                                             lambda b=a["browseId"]: self.open_detail("artist", b)))
        if not res:
            self.results.append(label("nichts gefunden", "empty", xalign=0.5))

    def song_row(self, t, context):
        return track_row(t, lambda: (self.p.play_now(t), self.p.start_radio(t) if self.p.autoplay else None),
                         [("+", "An Warteschlange anhängen", lambda: (self.p.add(t), self.say(f"+ {t['title']}"))),
                          ("»", "Als nächstes spielen", lambda: (self.p.add(t, next_=True),
                                                                 self.say(f"» {t['title']}"))),
                          ("󰐹", "Radio zu diesem Titel", lambda: self.p.start_radio(t))])

    # ---------- Bibliothek ----------
    def build_lib(self):
        self.lib_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, transition_duration=120)
        home = vbox(spacing=8)
        home.set_margin_top(6)
        self.login_panel = tui.Panel("󰀄 konto")
        self.login_body = vbox(spacing=8)
        self.login_body.add_css_class("loginbox")
        self.login_panel.body.append(self.login_body)
        home.append(self.login_panel)
        self.coll_panel = tui.Panel("sammlung")
        self.coll = vbox(spacing=0)
        self.coll_panel.body.append(self.coll)
        home.append(self.coll_panel)
        self.lib_stack.add_named(home, "home")

        detail = vbox(spacing=8)
        detail.set_margin_top(6)
        self.detail_panel = tui.Panel("")
        self.detail_box = vbox(spacing=0)
        self.detail_panel.body.append(hbox(
            self._sh(tui.Button("‹ zurück", self.lib_home), "‹ zurück", "‹"),
            label("", hexpand=True),
            self._sh(tui.Button("󰐊 abspielen", lambda: self.p.play_tracks(self.detail_tracks)), "󰐊 abspielen", "󰐊"),
            self._sh(tui.Button("󰒝 zufällig", lambda: self.p.play_tracks(self.detail_tracks, shuffle=True)),
                       "󰒝 zufällig", "󰒝"),
            self._sh(tui.Button("+ alle anhängen", lambda: [self.p.add(t) for t in self.detail_tracks]),
                       "+ alle anhängen", "+ alle"), spacing=8))
        self.detail_panel.body.append(self.detail_box)
        detail.append(self.detail_panel)
        self.lib_stack.add_named(detail, "detail")
        self.add_page("lib", self.lib_stack)

    def refresh_account(self):
        authed = os.path.exists(engine.BROWSER_JSON)
        self.p.music.reset()
        if not authed:
            self.account = None
            self.fill_login()
            return
        self.acct_lbl.set_label("󰀄 …")
        tui.background(engine.account_name, done=self.account_done)

    def account_done(self, res):
        if isinstance(res, Exception):
            self.account = None
            self.say(f"anmeldung abgelaufen? {str(res)[:120]}", error=True, seconds=12)
        else:
            self.account = res
        self.fill_login()
        if self.account:
            self.load_library()

    def fill_login(self):
        self.fill_settings_account()
        tui.clear(self.login_body)
        if self.account:
            # Kontoname wird bewusst nirgends angezeigt – nur der Status
            self.acct_lbl.set_label("󰀄 ●")
            self.acct_lbl.set_tooltip_text("Angemeldet")
            self.login_body.append(hbox(label("● angemeldet", "accent", hexpand=True),
                                        tui.Button("neu einlesen", self.login),
                                        tui.Button("abmelden", self.do_logout, danger=True), spacing=8))
        else:
            self.acct_lbl.set_label("󰀄 ○")
            self.acct_lbl.set_tooltip_text("Nicht angemeldet")
            self.login_body.append(label(
                "melde dich in zen oder firefox bei music.youtube.com an und klicke dann hier. der player übernimmt die "
                "anmeldung aus dem browser – dein passwort sieht er nie. ohne anmeldung gehen suche und abspielen trotzdem.",
                "dim", wrap=True))
            self.login_body.append(hbox(tui.Button("󰈹 mit zen/firefox anmelden", self.login), spacing=8))
            tui.clear(self.coll)
            self.coll_panel.set_visible(False)

    def login(self):
        self.say("lese anmeldung aus dem browser …", seconds=30)

        def done(res):
            if isinstance(res, Exception):
                self.say(str(res), error=True, seconds=15)
                return
            self.say("angemeldet")
            self.p.music.reset()
            self.p.resolver.reset()
            self.account_done(res)
        tui.background(engine.login_from_browser, done=done)

    def do_logout(self):
        engine.logout()
        self.p.music.reset()
        self.p.resolver.reset()
        self.account = None
        self.fill_login()
        self.say("abgemeldet")

    def load_library(self):
        self.coll_panel.set_visible(True)
        tui.clear(self.coll)
        self.coll.append(coll_row("󰋑", "lieblingssongs", "", lambda: self.open_detail("playlist", "LM")))
        self.coll.append(coll_row("󰋚", "verlauf", "", lambda: self.open_detail("history", "")))

        def done(res):
            if isinstance(res, Exception):
                self.say(f"bibliothek: {res}", error=True)
                return
            for pl in res:
                if pl["id"] == "LM":
                    continue
                self.coll.append(coll_row("󰲸", pl["title"], str(pl["count"] or ""),
                                          lambda i=pl["id"]: self.open_detail("playlist", i)))
        tui.background(self.p.music.library, done=done)

    def open_detail(self, kind, ident):
        self.detail_key = (kind, ident)
        self.show_tab("lib")
        self.lib_stack.set_visible_child_name("detail")
        self.nav_note()
        self.detail_panel.set_title("lädt …")
        tui.clear(self.detail_box)
        fn = {"playlist": self.p.music.playlist, "album": self.p.music.album,
              "artist": self.p.music.artist_songs, "history": lambda _i: ("verlauf", self.p.music.history())}[kind]

        def done(res):
            if isinstance(res, Exception):
                self.say(f"laden: {res}", error=True)
                self.detail_panel.set_title("fehler")
                return
            title, tracks = res
            self.detail_names[(kind, ident)] = title
            self.detail_tracks = tracks
            total = sum(t["duration"] or 0 for t in tracks)
            self.detail_panel.set_title(f"{esc(title)} <span alpha='60%'>{len(tracks)} · {fmt(total)}</span>",
                                        markup=True)
            for i, t in enumerate(tracks):
                row = track_row(t, lambda i=i: self.p.play_tracks(tracks, start=i),
                                [("+", "An Warteschlange anhängen", lambda t=t: self.p.add(t)),
                                 ("»", "Als nächstes spielen", lambda t=t: self.p.add(t, next_=True))])
                row.mark.set_label(str(i + 1))
                self.detail_box.append(row)
        tui.background(fn, ident, done=done)

    # ---------- Songtext ----------
    def build_lyrics(self):
        # Songtext mittig gesetzt; die aktuelle Zeile wird weich in die Fenstermitte gescrollt.
        # Ober-/Unterkante bekommen je eine halbe Fensterhöhe Luft, damit auch Zeile 1 und die
        # letzte Zeile in die Mitte können.
        self.lyr_top = Gtk.Box()
        self.lyr_bottom = Gtk.Box()
        self.lyr_box = vbox(spacing=2)
        self.lyr_src = label("", "dim", xalign=0.5)
        inner = vbox(self.lyr_top, self.lyr_box, self.lyr_src, self.lyr_bottom, spacing=0)
        self.lyr_inner = inner
        self.lyr_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, child=inner, vexpand=True)
        self.lyr_scroll.add_css_class("lyrics")
        sc = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
        sc.connect("scroll", self._lyr_user_scroll)
        self.lyr_scroll.add_controller(sc)
        self.lyr_manual_until = 0
        self.lyr_anim = None
        self._lyr_cur = None
        self.lyr_synced = False
        self.add_page("lyrics", self.lyr_scroll, scroll=False)

    def _lyr_user_scroll(self, *_):
        self.lyr_manual_until = GLib.get_monotonic_time() + 4_000_000  # 4 s selbst scrollen lassen
        return False

    def lyr_message(self, text):
        tui.clear(self.lyr_box)
        self.lyric_lines = []
        self.lyr_box.append(label(text, "empty", xalign=0.5))

    def load_lyrics(self):
        t = self.p.current
        if not t or t["videoId"] == self.lyrics_vid:
            return
        vid = self.lyrics_vid = t["videoId"]
        self.lyr_src.set_label("")
        self._lyr_cur = None
        self.lyr_message("lädt …")

        def done(res):
            if vid != self.lyrics_vid:
                return
            if isinstance(res, Exception) or not res or not res.get("lyrics"):
                self.lyr_message("kein songtext verfügbar")
                return
            tui.clear(self.lyr_box)
            self.lyric_lines = []
            lyr = res["lyrics"]
            self.lyr_synced = not isinstance(lyr, str)
            lines = [(ln.start_time / 1000, ln.text) for ln in lyr] if self.lyr_synced else \
                [(None, x) for x in lyr.splitlines()]
            for start, text in lines:
                lbl = label(text or "♪", "lyric", xalign=0.5, wrap=True)
                lbl.set_justify(Gtk.Justification.CENTER)
                self.lyric_lines.append((start, lbl))
                self.lyr_box.append(lbl)
            src = (res.get("source") or "").lower()
            self.lyr_src.set_label(src + ("" if self.lyr_synced else "  ·  ohne zeitstempel – position geschätzt"))
            GLib.idle_add(lambda: self.sync_lyrics(jump=True) and False)
        tui.background(self.p.music.lyrics, vid, done=done)

    def lyrics_pad(self):
        """Halbe Fensterhöhe Luft oben/unten. True = hat sich geändert (Layout erst im nächsten Bild)."""
        half = max(0, self.lyr_scroll.get_height() // 2 - 20)
        if self.lyr_top.get_size_request()[1] == half:
            return False
        self.lyr_top.set_size_request(-1, half)
        self.lyr_bottom.set_size_request(-1, half)
        return True

    def current_lyric(self):
        n = len(self.lyric_lines)
        if not n:
            return None
        if self.lyr_synced:
            pos = self.p.pos + 0.3
            cur = None
            for i, (start, _l) in enumerate(self.lyric_lines):
                if start <= pos:
                    cur = i
            return cur if cur is not None else 0
        dur = self.p.dur or (self.p.current or {}).get("duration") or 0
        return min(n - 1, int(self.p.pos / dur * n)) if dur else 0

    def sync_lyrics(self, jump=False):
        cur = self.current_lyric()
        if cur is None:
            return
        if cur != self._lyr_cur or jump:
            self._lyr_cur = cur
            for i, (_s, lbl) in enumerate(self.lyric_lines):
                want = "now" if i == cur else "past" if i < cur else ""
                for c in ("now", "past"):
                    (lbl.add_css_class if c == want else lbl.remove_css_class)(c)
            GLib.idle_add(lambda: self.center_lyric(jump) and False)  # nach dem Neu-Layout (größere Schrift)

    def center_lyric(self, jump=False):
        if self._lyr_cur is None or self._lyr_cur >= len(self.lyric_lines):
            return
        if not jump and GLib.get_monotonic_time() < self.lyr_manual_until:
            return
        if self.lyrics_pad() or self.lyr_box.get_height() == 0:  # erst neu layouten lassen, dann zentrieren
            GLib.timeout_add(40, lambda: self.center_lyric(jump) and False)
            return
        lbl = self.lyric_lines[self._lyr_cur][1]
        ok, pt = lbl.compute_point(self.lyr_inner, Graphene.Point().init(0, 0))
        if not ok:
            return
        adj = self.lyr_scroll.get_vadjustment()
        target = pt.y + lbl.get_height() / 2 - adj.get_page_size() / 2
        target = max(adj.get_lower(), min(target, adj.get_upper() - adj.get_page_size()))
        if jump:
            adj.set_value(target)
            return
        start, t0 = adj.get_value(), None

        def step(_w, clock):  # 300 ms, easeOutCubic
            nonlocal t0
            now = clock.get_frame_time()
            t0 = t0 or now
            k = min(1.0, (now - t0) / 300_000)
            adj.set_value(start + (target - start) * (1 - (1 - k) ** 3))
            if k >= 1.0:
                self.lyr_anim = None
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE
        if self.lyr_anim:
            self.lyr_scroll.remove_tick_callback(self.lyr_anim)
        self.lyr_anim = self.lyr_scroll.add_tick_callback(step)

    # ---------- Zustand ----------
    def on_player(self, what):
        if what == "track":
            self.update_track()
        elif what in ("state", "volume"):
            self.update_state()
        elif what == "pos":
            self.update_pos()
        elif what == "queue":
            self.update_queue()
            self.schedule_relayout()
        elif what.startswith("error:"):
            self.say(what[6:], error=True, seconds=10)

    def update_track(self):
        if hasattr(self, "_relayout_id"):
            self.schedule_relayout()
        t = self.p.current
        self.cover.show(t["thumb"] if t else None)
        self.title.set_label(t["title"] if t else "nichts läuft")
        self.artist.set_label(t["artist"] if t else "super+m · ⁶suchen")
        self.album.set_label(t["album"] if t else "")
        self.update_track_labels()
        if hasattr(self, "visuals"):
            self.visuals.update_track()
        if hasattr(self, "np_chip"):
            self.update_tab_labels()
        (self.like_btn.add_css_class if t and t.get("liked") else self.like_btn.remove_css_class)("on")
        for b in (self.like_btn, self.radio_btn, self.web_btn):
            b.set_sensitive(t is not None)
        self.like_btn.set_sensitive(t is not None and self.account is not None)
        self.update_queue()
        self.update_pos()
        if self.get_visible() and self.current_tab() == "lyrics":
            self.load_lyrics()

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

    def on_compact(self, compact):
        pass

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
            self.drawer.toggle()
        elif kv == Gdk.KEY_comma:
            self.show_tab("settings")
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


# ---------- Vorschau unten mittig ----------
def preview_supported():
    """Vorschau-Karte braucht gtk4-layer-shell (geladen per LD_PRELOAD) und einen Compositor mit Layer-Shell."""
    try:
        return Layer is not None and Layer.is_supported()
    except Exception:
        return False


class NoPreview:
    """Ersatz, wenn die Vorschau nicht geht – gleiche Schnittstelle, tut nichts."""
    def hide(self):
        pass

    def set_enabled(self, on):
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

    def __init__(self, app, player, cava, open_player, srcs):
        self.p, self.cava, self.open_player, self.srcs = player, cava, open_player, srcs
        self.show_id = self.hide_id = self.watch_id = None
        self.outside_ms = 0

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

        self.card = Gtk.Window(application=app)
        self.card.add_css_class("preview")
        Layer.init_for_window(self.card)
        Layer.set_namespace(self.card, "music-preview")
        Layer.set_layer(self.card, Layer.Layer.OVERLAY)
        Layer.set_anchor(self.card, Layer.Edge.BOTTOM, True)
        Layer.set_margin(self.card, Layer.Edge.BOTTOM, 10)
        Layer.set_exclusive_zone(self.card, 0)
        Layer.set_keyboard_mode(self.card, Layer.KeyboardMode.NONE)   # Tastatur nur, solange die Karte offen ist
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
        title_btn.connect("clicked", lambda *_: (self.hide(), self.open_player()))
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
                               mark=False, flush=True)
        self.spec = Spectrum(rows=1, cell=8, height=16, flush=True)
        right = vbox(hbox(title_btn, self.like, spacing=8),
                     hbox(self.prev, self.play, self.next, label("", hexpand=True), self.pos, spacing=6),
                     self.seek, spacing=8, hexpand=True)
        box.append(hbox(self.cover, right, spacing=14))
        box.append(self.spec)
        # Was sonst gerade Ton macht (früher das mpris-Modul in der Waybar)
        self.src_list = sources.SourceList(srcs, limit=3)
        self.src_list.add_css_class("src-sep")
        box.append(self.src_list)
        self.card.set_child(box)
        # Cover oben bündig mit der Oberkante der Titelschrift, unten mit den Balkenquadraten
        ink = self.title.create_pango_layout("Hdlk").get_pixel_extents()[0]
        self.cover.set_insets(ink.y, self.seek.square_inset())
        # Größe gleich passend vorgeben (sonst springt es beim ersten Einblenden einmal)
        h = right.measure(Gtk.Orientation.VERTICAL, -1)[1]
        self.cover.set_content_width(max(40, round(h - self.cover.top - self.cover.bottom)))

        self.p.listeners.append(self.on_player)
        cava.listeners.append(self.on_spectrum)
        self.enabled = False
        self.set_enabled(engine.setting("hover"))

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
        if keyval in (Gdk.KEY_Right, Gdk.KEY_l):
            self.p.next()
            return True
        if keyval in (Gdk.KEY_Left, Gdk.KEY_h):
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
        self.artist.set_label(t["artist"] if t else "super+m öffnet den player")
        self.like.set_label("󰋑" if t and t.get("liked") else "󰋕")
        self.play.set_label("󰏤" if not p.paused and p.started else "󰐊")
        dur = p.dur or (t or {}).get("duration") or 0
        self.pos.set_label(f"{fmt(p.pos)} / {fmt(dur)}")
        self.seek.set_value(int(p.pos / dur * 1000) if dur else 0)
