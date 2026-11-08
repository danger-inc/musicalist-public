# musicalist – einstellbares Titelbild-Raster (wie „titelbild-raster“ in der Handy-App): Form, Auflösung, Punktgröße,
# Farbe, Kontrast, Rasterung. Reine Rechnung + Zeichnen, ohne eigene Fenster; die Einstellung liegt in settings.json
# ("pixel_cfg"). Fehlt sie, bleibt der bisherige Look (runde Punkte, schwach angedeutete Aus-Punkte).
import math

from gi.repository import GdkPixbuf

import engine
import tui

SHAPES = [("quadrat", "■ quadrate"), ("punkt", "● punkte"), ("pixel", "▦ pixel"), ("halbton", "◍ halbton")]
COLORS = [("akzent", "akzent"), ("schrift", "schrift"), ("cover", "cover-farben"), ("gameboy", "gameboy")]
DITHERS = [("bayer", "bayer"), ("fehler", "fehlerstreuung"), ("schwelle", "schwelle")]
GAMEBOY = [(0x0f / 255, 0x38 / 255, 0x0f / 255), (0x30 / 255, 0x62 / 255, 0x30 / 255),
           (0x8b / 255, 0xac / 255, 0x0f / 255), (0x9b / 255, 0xbc / 255, 0x0f / 255)]
BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]

# Bisheriger Look der App (Vorgabe, solange nichts eingestellt wurde)
BASE = {"shape": "punkt", "res": 36, "size": 0.72, "color": "akzent", "off": True, "contrast": 0.0, "invert": False,
        "dither": "bayer", "eq": True}
PRESETS = [
    ("󰍹 wie bisher", dict(BASE)),
    ("󰝤 fein", dict(BASE, shape="quadrat", res=72, size=0.6, off=False, dither="fehler")),
    ("󰄰 punktraster", dict(BASE, res=44, size=0.78)),
    ("󰊴 gameboy", dict(BASE, shape="pixel", res=40, size=0.92, color="gameboy", off=False, contrast=0.2)),
    ("󰏘 8-bit farbig", dict(BASE, shape="pixel", res=32, size=1.0, color="cover", off=False, eq=False)),
    ("󰈙 zeitung", dict(BASE, shape="halbton", res=46, size=1.0, color="schrift", off=False, contrast=0.25)),
]


def custom():
    """True, wenn der Nutzer das Raster verstellt hat (dann zeichnen alle Titelbilder mit dieser Einstellung)."""
    return isinstance(engine.setting("pixel_cfg"), dict)


def cfg():
    out = dict(BASE)
    s = engine.setting("pixel_cfg")
    if isinstance(s, dict):
        out.update({k: s[k] for k in BASE if k in s})
    out["res"] = int(max(16, min(112, out["res"])))
    out["size"] = float(max(0.25, min(1.0, out["size"])))
    out["contrast"] = float(max(-1.0, min(1.0, out["contrast"])))
    return out


def set_cfg(c):
    engine.set_setting("pixel_cfg", dict(c) if c is not None else None)


def key(c=None):
    c = c or cfg()
    return tuple(sorted(c.items()))


def _square(pb):
    w, h = pb.get_width(), pb.get_height()
    m = min(w, h)
    return pb.new_subpixbuf((w - m) // 2, (h - m) // 2, m, m)


def grid(pb, res, c):
    """Foto → (Helligkeit res×res 0–1 nach Ausgleich/Kontrast, Farben je Zelle (r,g,b) 0–1)."""
    small = _square(pb).scale_simple(res, res, GdkPixbuf.InterpType.BILINEAR)
    px, stride, n = small.get_pixels(), small.get_rowstride(), small.get_n_channels()
    lum, rgb = [], []
    for y in range(res):
        lr, cr_ = [], []
        for x in range(res):
            i = y * stride + x * n
            r, g, b = px[i] / 255, px[i + 1] / 255, px[i + 2] / 255
            lr.append(0.299 * r + 0.587 * g + 0.114 * b)
            cr_.append((r, g, b))
        lum.append(lr)
        rgb.append(cr_)
    if c["eq"]:       # Histogramm-Ausgleich mit mittlerem Rang (große einfarbige Flächen = Halbton)
        flat = sorted(v for row in lum for v in row)
        tot, rank, first = len(flat), {}, {}
        for i, v in enumerate(flat):
            first.setdefault(v, i)
            rank[v] = (first[v] + i) / 2 / tot
        lum = [[rank[v] for v in row] for row in lum]
    k = c["contrast"]
    if k:
        f = 1 + 2 * k if k > 0 else 1 + k
        lum = [[max(0.0, min(1.0, (v - 0.5) * f + 0.5)) for v in row] for row in lum]
    if c["invert"]:
        lum = [[1 - v for v in row] for row in lum]
    return lum, rgb


def _bits(lum, res, c, flip):
    """An/Aus je Zelle für quadrat/punkt."""
    d = c["dither"]
    if flip:
        lum = [[1 - v for v in row] for row in lum]
    if d == "schwelle":
        return [[v > 0.5 for v in row] for row in lum]
    if d == "fehler":
        a = [row[:] for row in lum]
        out = [[False] * res for _ in range(res)]
        for y in range(res):
            for x in range(res):
                old = a[y][x]
                new = 1.0 if old > 0.5 else 0.0
                out[y][x] = new > 0
                e = old - new
                if x + 1 < res:
                    a[y][x + 1] += e * 7 / 16
                if y + 1 < res:
                    if x > 0:
                        a[y + 1][x - 1] += e * 3 / 16
                    a[y + 1][x] += e * 5 / 16
                    if x + 1 < res:
                        a[y + 1][x + 1] += e * 1 / 16
        return out
    return [[lum[y][x] * 16 > BAYER[y % 4][x % 4] + 0.5 for x in range(res)] for y in range(res)]


def _mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def draw(cr, data, side, c, flip=False, x0=0.0, y0=0.0):
    """Raster in ein side×side-Feld zeichnen. data = grid()-Ergebnis."""
    lum, rgb = data
    res = len(lum)
    cols = tui.colors()
    p, fg, bg = cols.get("primary"), cols.get("foreground"), cols.get("background")
    base = (p.red, p.green, p.blue) if c["color"] != "schrift" else (fg.red, fg.green, fg.blue)
    bgc = (bg.red, bg.green, bg.blue) if bg else (0, 0, 0)
    cell = side / res
    shape, size = c["shape"], c["size"]
    if shape in ("quadrat", "punkt"):
        bits = _bits(lum, res, c, flip)
        for y in range(res):
            for x in range(res):
                cx, cy = x0 + (x + 0.5) * cell, y0 + (y + 0.5) * cell
                if bits[y][x]:
                    col = rgb[y][x] if c["color"] == "cover" else GAMEBOY[3] if c["color"] == "gameboy" else base
                    cr.set_source_rgba(col[0], col[1], col[2], 1.0)
                elif c["off"]:
                    cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.10)
                else:
                    continue
                if shape == "punkt":
                    cr.arc(cx, cy, cell * size / 2, 0, 6.2832)
                else:
                    s = cell * size
                    cr.rectangle(cx - s / 2, cy - s / 2, s, s)
                cr.fill()
        return
    for y in range(res):
        for x in range(res):
            v = lum[y][x]
            cx, cy = x0 + (x + 0.5) * cell, y0 + (y + 0.5) * cell
            if shape == "pixel":
                q = min(3, int(v * 4))
                if c["color"] == "gameboy":
                    col = GAMEBOY[q]
                elif c["color"] == "cover":
                    col = rgb[y][x]
                else:
                    col = _mix(bgc, base, (0.12, 0.42, 0.72, 1.0)[q])
                cr.set_source_rgba(col[0], col[1], col[2], 1.0)
                s = cell * size
                cr.rectangle(cx - s / 2, cy - s / 2, s + 0.5, s + 0.5)
                cr.fill()
            else:   # halbton: Punktgröße nach Helligkeit
                col = rgb[y][x] if c["color"] == "cover" else GAMEBOY[3] if c["color"] == "gameboy" else base
                cr.set_source_rgba(col[0], col[1], col[2], 1.0)
                cr.arc(cx, cy, cell * 0.5 * size * math.sqrt(max(0.0, v)), 0, 6.2832)
                cr.fill()


def background(c):
    """Hintergrund für „gameboy“ (sonst keiner)."""
    return GAMEBOY[0] if c["color"] == "gameboy" and c["shape"] in ("pixel",) else None
