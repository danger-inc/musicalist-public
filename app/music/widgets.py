# musicalist – Bild-Bausteine (Cover als Braille/Punkte, Halbton) und Layer-Shell-Prüfung für ui.py und die Seiten.
import re, urllib.request

import cairo

import gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango, PangoCairo
try:   # nur für die Vorschau-Karte; ohne gtk4-layer-shell (oder unter GNOME/X11) läuft der Player trotzdem
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell as Layer
except (ImportError, ValueError):
    Layer = None

import tui
from tui import label, hbox, vbox, esc
import engine
import pixelart


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
        _thumbs.pop(next(iter(_thumbs)))        # ältesten Eintrag verwerfen (nicht alles auf einmal)
    _thumbs[url] = pb
    return pb

BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]

DOTS = [(0, 0, 0x01), (0, 1, 0x02), (0, 2, 0x04), (1, 0, 0x08), (1, 1, 0x10), (1, 2, 0x20), (0, 3, 0x40), (1, 3, 0x80)]

def ink_darker():
    """Helles Design: die Punkte (Akzentfarbe) sind dunkler als der Hintergrund → dunkle Bildstellen bekommen Punkte,
    sonst wirkt das Cover wie ein Negativ."""
    c = tui.colors()
    p, bg = c.get("primary"), c.get("background")
    if p is None or bg is None:
        return False
    lum = lambda x: 0.299 * x.red + 0.587 * x.green + 0.114 * x.blue
    return lum(p) < lum(bg)


def dither(pb, w, h, flip=False):
    """Bild → w×h Punkte (True = an): Histogramm-Ausgleich + Bayer-Rasterung. flip: dunkle Stellen = an."""
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
    return [[(1 - rank[lum[y][x]] if flip else rank[lum[y][x]]) * 16 > BAYER[y % 4][x % 4] + 0.5 for x in range(w)] for y in range(h)]

def braille(pb, cols, rows, flip=False):
    """Bild → Braille-Zeichen (2×4 Punkte je Zeichen)."""
    # Cover sind quadratisch; Zeichen sind ~2× so hoch wie breit → Braille passt (2×4 Punkte) 1:1
    on = dither(pb, cols * 2, rows * 4, flip)
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

# ---------- Raster an/aus (wie in der Handy-App): gilt überall, wo ein Titelbild gezeigt wird ----------
PIXEL_LISTENERS = []

def pixel_on():
    return engine.setting("pixel") is not False          # Standard: Raster


def set_pixel(on):
    engine.set_setting("pixel", bool(on))
    for fn in list(PIXEL_LISTENERS):
        fn()


def notify_pixel():
    for fn in list(PIXEL_LISTENERS):
        fn()


def draw_photo(cr, pb, x, y, side):
    """Foto quadratisch (mittig beschnitten) in ein side×side-Feld zeichnen."""
    w, h = pb.get_width(), pb.get_height()
    m = min(w, h)
    k = side / m
    cr.save()
    cr.rectangle(x, y, side, side)
    cr.clip()
    cr.translate(x - (w - m) / 2 * k, y - (h - m) / 2 * k)
    cr.scale(k, k)
    Gdk.cairo_set_source_pixbuf(cr, pb, 0, 0)
    cr.paint()
    cr.restore()


class DotThumb(Gtk.DrawingArea):
    """Kleines quadratisches Titelbild als Raster (oder Foto bei ausgeschaltetem Raster) – für Raster-Listen."""
    N = 22

    def __init__(self, side=86):
        super().__init__(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.side, self.pb, self._g, self.res = side, None, None, None
        self.set_content_width(side)
        self.set_content_height(side)
        self.set_draw_func(self._draw)
        PIXEL_LISTENERS.append(self.queue_draw)
        self.connect("destroy", lambda *_: PIXEL_LISTENERS.remove(self.queue_draw) if self.queue_draw in PIXEL_LISTENERS else None)

    def set_data(self, pb, _unused=None):
        self.pb, self._g = pb, None
        self.queue_draw()

    def _draw(self, _a, cr, width, height):
        side = min(width, height)
        if self.pb is None:
            c = tui.colors()
            p, fg = c.get("primary"), c.get("foreground")
            n = self.N
            for y in range(n):
                for x in range(n):
                    cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.10)
                    cr.arc((x + 0.5) * side / n, (y + 0.5) * side / n, side / n * 0.36, 0, 6.2832)
                    cr.fill()
            return
        if not pixel_on():
            draw_photo(cr, self.pb, 0, 0, side)
            return
        c = pixelart.cfg()
        res = self.res or (min(c["res"], 44) if pixelart.custom() else self.N)
        k = (pixelart.key(c), res)
        if self._g is None or self._g[0] != k:
            self._g = (k, pixelart.grid(self.pb, res, c))
        pixelart.draw(cr, self._g[1], side, c, flip=ink_darker())


class Cover(Gtk.Box):
    """Titelbild als Braille-Zeichen (Raster an) oder als Foto (Raster aus, siehe set_pixel)."""
    def __init__(self, cols, rows, small=False):
        super().__init__(valign=Gtk.Align.START)
        self.lbl = Gtk.Label(xalign=0, yalign=0, valign=Gtk.Align.START)
        self.lbl.add_css_class("cover")
        if small:
            self.lbl.add_css_class("small")
        self.pic = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.COVER, valign=Gtk.Align.START, halign=Gtk.Align.START,
                               visible=False)
        self.append(self.lbl)
        self.append(self.pic)
        self.cols, self.rows, self.url, self.pb = cols, rows, None, None
        self.lbl.set_label(placeholder(cols, rows))
        self._size_pic()
        PIXEL_LISTENERS.append(self.apply)
        self.connect("destroy", lambda *_: PIXEL_LISTENERS.remove(self.apply) if self.apply in PIXEL_LISTENERS else None)

    def _size_pic(self):
        side = int(self.cols * 5.4)
        self.pic.set_size_request(side, side)

    def set_label(self, text):                 # alter Name (Label) – Aufrufer setzen nur Text
        self.lbl.set_label(text)

    def apply(self):
        photo = self.pb is not None and not pixel_on()
        drawn = self.pb is not None and pixel_on() and pixelart.custom()      # eigenes Raster: gezeichnet statt Braille
        if drawn:
            side = int(self.cols * 5.4)
            c = pixelart.cfg()
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, side, side)
            cr = cairo.Context(surf)
            pixelart.draw(cr, pixelart.grid(self.pb, c["res"], c), side, c, flip=ink_darker())
            self.pic.set_paintable(Gdk.Texture.new_for_pixbuf(Gdk.pixbuf_get_from_surface(surf, 0, 0, side, side)))
        elif photo:
            self.pic.set_paintable(Gdk.Texture.new_for_pixbuf(self.pb))
        self.pic.set_visible(photo or drawn)
        self.lbl.set_visible(not (photo or drawn))

    def set_size(self, cols, rows):
        if (cols, rows) == (self.cols, self.rows):
            return
        self.cols, self.rows = cols, rows
        self._size_pic()
        url, self.url = self.url, None
        self.show(url)  # neu rastern (Bild kommt aus dem Zwischenspeicher)

    def show(self, url):
        if url == self.url:
            return
        self.url = url
        if not url:
            self.pb = None
            self.lbl.set_label(placeholder(self.cols, self.rows))
            self.apply()
            return
        flip = ink_darker()
        cols, rows = self.cols, self.rows

        def work():
            pb = fetch_pixbuf(big_thumb(url))
            return braille(pb, cols, rows, flip), pb

        def done(res):
            if self.url == url and isinstance(res, tuple):
                self.lbl.set_label(res[0])
                self.pb = res[1]
                self.apply()
        tui.background(work, done=done)

class DotCover(Gtk.DrawingArea):
    """Cover als gezeichnetes Punktraster (Braille-Look), immer quadratisch und so hoch, wie die Zeile
    es zulässt – damit es oben und unten genau mit den Nachbarn abschließt. Aus-Punkte bleiben schwach
    sichtbar, so ist das Quadrat auch bei dunklen Covern klar begrenzt."""
    DOTS = 36

    def __init__(self, size=88):
        super().__init__(valign=Gtk.Align.FILL, halign=Gtk.Align.START)
        self.url, self.on, self.pb = None, None, None
        PIXEL_LISTENERS.append(self.queue_draw)
        self.connect("destroy", lambda *_: PIXEL_LISTENERS.remove(self.queue_draw) if self.queue_draw in PIXEL_LISTENERS else None)
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
        self.url, self.on, self.pb = url, None, None
        self.queue_draw()
        if not url:
            return

        def done(res):
            if self.url == url and not isinstance(res, Exception):
                self.pb, self._g = res, None
                self.on = True
                self.queue_draw()
        tui.background(lambda: fetch_pixbuf(big_thumb(url)), done=done)

    def _draw(self, _a, cr, width, height):
        c = tui.colors()
        p, fg = c.get("primary"), c.get("foreground")
        n = self.DOTS
        side = min(width, height - self.top - self.bottom)
        cr.translate(0, self.top)
        if self.pb is not None and not pixel_on():
            draw_photo(cr, self.pb, 0, 0, side)
            return
        if self.pb is not None:
            c = pixelart.cfg()
            res = c["res"] if pixelart.custom() else self.DOTS
            k = (pixelart.key(c), res)
            if getattr(self, "_g", None) is None or self._g[0] != k:
                self._g = (k, pixelart.grid(self.pb, res, c))
            pixelart.draw(cr, self._g[1], side, c, flip=ink_darker())
            return
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

# ---------- Vorschau unten mittig ----------
def preview_supported():
    """Vorschau-Karte braucht gtk4-layer-shell (geladen per LD_PRELOAD) und einen Compositor mit Layer-Shell."""
    try:
        return Layer is not None and Layer.is_supported()
    except Exception:
        return False

DESK_POS = [("bottom", "unten mittig"), ("bottom-left", "unten links"), ("bottom-right", "unten rechts"),
            ("top-left", "oben links"), ("top-right", "oben rechts")]
