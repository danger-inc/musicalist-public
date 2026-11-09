# musicalist – Rückblick-Bilder (PNG 1080 × 1350): Woche (sonntags), Monat (am Monatsletzten), Jahr (31.12.).
# Gleiches Aussehen und gleiche Regeln wie in der Handy-App (Recap.kt): Farbe = Akzentfarbe der Person mit der meisten Hörzeit,
# Cover = ihr meistgespieltes Lied, Ranglisten = hörzeit / titel / künstler aus der Freundesliste (nur Geteiltes, Incognito fehlt).
# Gezeichnet mit cairo + Pango; läuft im Hintergrund-Thread des Players.
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import date, datetime, timedelta

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import GdkPixbuf, Pango, PangoCairo  # noqa: E402

import engine  # noqa: E402

W, H = 1080, 1350
U = W / 100.0
GREEN = (0x5F / 255, 0xD3 / 255, 0x8D / 255, 1.0)
FONT = "JetBrains Mono, JetBrainsMono Nerd Font Mono, monospace"
KINDS = {"w": "wochenrückblick", "m": "monatsrückblick", "y": "jahresrückblick"}


# ---------------- Farben ----------------
def hsl(h, s, l, a=1.0):
    c = (1 - abs(2 * l - 1)) * s
    hp = (h % 360) / 60.0
    x = c * (1 - abs(hp % 2 - 1))
    m = l - c / 2
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][min(int(hp), 5)]
    return (r + m, g + m, b + m, a)


def hue_of(c):
    r, g, b = c[:3]
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    if d == 0:
        return 0.0
    h = ((g - b) / d % 6) if mx == r else ((b - r) / d + 2) if mx == g else ((r - g) / d + 4)
    return h * 60


def light_of(c):
    return (max(c[:3]) + min(c[:3])) / 2


def alpha(c, a):
    return (c[0], c[1], c[2], a)


def parse_hex(s):
    try:
        s = (s or "").strip().lstrip("#")
        if len(s) == 6:
            return (int(s[0:2], 16) / 255, int(s[2:4], 16) / 255, int(s[4:6], 16) / 255, 1.0)
    except ValueError:
        pass
    return None


def hmin(m):
    h, mm = divmod(int(m), 60)
    return f"{h}h {mm}min" if h and mm else (f"{h}h" if h else f"{mm}min")


# ---------------- Daten ----------------
def own_accent():
    """Akzentfarbe dieser App (aus dem aktuellen Design) als #rrggbb."""
    try:
        import tui
        c = tui.colors().get("primary")
        if c is not None:
            return "#%02x%02x%02x" % (round(c.red * 255), round(c.green * 255), round(c.blue * 255))
    except Exception:  # noqa: BLE001
        pass
    return ""


def collect(fr, kind):
    """Zahlen des laufenden Zeitraums für dich und deine Freunde → dict oder None. kind = w | m | y."""
    import analyse
    import friends as frm
    lo, _hi, title, sub = analyse.bounds(kind, 0)
    r = analyse.analyse(fr.p.journal.load() or [], kind, 0)
    people = []
    if not r.get("empty") and r["base"]["secs"] > 0:
        a0 = (r.get("artists") or [None])[0]
        t0 = (r.get("tracks") or [None])[0]
        people.append({"name": fr.name, "ac": parse_hex(own_accent()), "hm": round(r["base"]["secs"] / 60),
                       "n": r["base"]["tracks"], "ar": r["base"]["artists"],
                       "artist": (a0["name"], round(a0["secs"] / 60)) if a0 else None,
                       "song": {"t": t0["t"], "a": t0["a"], "n": t0["plays"], "id": t0.get("id")} if t0 else None, "me": True})
    for x in fr.friends:
        prof = x.get("prof") or {}
        pf = prof.get("pf")
        if not pf or frm.inc_active(prof.get("inc")) or (x.get("at") or 0) < lo * 1000:
            continue                    # nichts geteilt / incognito / Schnappschuss einer früheren Periode
        src = pf if kind == "w" else pf.get("mo" if kind == "m" else "yr")
        if not src:
            continue
        hm = int(src["hm"]) if "hm" in src else round(float(src.get("h") or 0) * 60)
        if hm <= 0:
            continue
        if kind == "w":
            a = (pf.get("art") or [None])[0]
            artist = (a["n"], a["m"]) if a else None
            s = (pf.get("trk") or [None])[0]
            song = {"t": s["t"], "a": s["a"], "n": s["n"], "id": s.get("i")} if s else None
        else:
            a = src.get("a")
            artist = (a["n"], a["m"]) if a else None
            s = src.get("s")
            song = {"t": s["t"], "a": s["a"], "n": s["n"], "id": s.get("i")} if s else None
        people.append({"name": x["name"], "ac": parse_hex(pf.get("ac")), "hm": hm, "n": src.get("n"), "ar": src.get("ar"),
                       "artist": artist, "song": song, "me": False})
    if not people:
        return None
    key = kind + "-" + re.sub(r"[^a-z0-9äöü]+", "-", title.lower()).strip("-")
    return {"kind": kind, "key": key, "label": title, "range": "das ganze jahr" if kind == "y" else sub, "people": people}


def rubriken(d):
    def top(sel):
        rows = [(p["name"], sel(p)) for p in d["people"] if sel(p) is not None]
        return sorted(rows, key=lambda r: (-r[1], r[0]))[:3]
    out = [("hörzeit", top(lambda p: p["hm"]), hmin), ("titel", top(lambda p: p["n"]), str),
           ("künstler·innen", top(lambda p: p["ar"]), str)]
    return [r for r in out if r[1]]


# ---------------- Zeichnen ----------------
class Pen:
    def __init__(self, cr):
        self.cr = cr

    def _layout(self, s, size_u, bold, spacing):
        lay = PangoCairo.create_layout(self.cr)
        fd = Pango.FontDescription(FONT)
        fd.set_weight(Pango.Weight.BOLD if bold else Pango.Weight.NORMAL)
        fd.set_absolute_size(size_u * U * Pango.SCALE)
        lay.set_font_description(fd)
        lay.set_text(s, -1)
        if spacing:
            at = Pango.AttrList()
            at.insert(Pango.attr_letter_spacing_new(int(spacing * size_u * U * Pango.SCALE)))
            lay.set_attributes(at)
        return lay

    def width(self, s, size_u, bold=False, spacing=0.0):
        return self._layout(s, size_u, bold, spacing).get_pixel_size()[0] / U

    def text(self, s, x, y, size, color, bold=False, spacing=0.0, max_u=None, right=False):
        lay = self._layout(s, size, bold, spacing)
        if max_u is not None and lay.get_pixel_size()[0] > max_u * U:
            t = s
            while len(t) > 1:
                t = t[:-1]
                lay = self._layout(t + "…", size, bold, spacing)
                if lay.get_pixel_size()[0] <= max_u * U:
                    break
        w = lay.get_pixel_size()[0]
        base = lay.get_baseline() / Pango.SCALE
        self.cr.set_source_rgba(*color)
        self.cr.move_to(x * U - (w if right else 0), y * U - base)
        PangoCairo.show_layout(self.cr, lay)


def _grid_pixbuf(pb, g=36):
    w, h = pb.get_width(), pb.get_height()
    s = min(w, h)
    pb = pb.new_subpixbuf((w - s) // 2, (h - s) // 2, s, s).scale_simple(g, g, GdkPixbuf.InterpType.BILINEAR)
    px, rs, n = pb.get_pixels(), pb.get_rowstride(), pb.get_n_channels()
    return [[(px[y * rs + x * n] * .3 + px[y * rs + x * n + 1] * .59 + px[y * rs + x * n + 2] * .11) / 255 for x in range(g)] for y in range(g)]


def _grid_fallback(hue, g=36):
    """Erzeugtes Farbbild als Ersatz für das Cover (ohne Netz / ohne Lied-Kennung)."""
    sf = cairo.ImageSurface(cairo.FORMAT_ARGB32, g, g)
    c = cairo.Context(sf)
    c.scale(g / 96.0, g / 96.0)
    lg = cairo.LinearGradient(0, 0, 96, 96)
    for off, col in ((0, hsl(hue + 330, .7, .16)), (.55, hsl(hue, .78, .46)), (1, hsl(hue + 40, .85, .7))):
        lg.add_color_stop_rgba(off, *col)
    c.set_source(lg)
    c.paint()
    c.set_source_rgba(1, 1, 1, .9)
    c.arc(48, 44, 16, 0, 7)
    c.fill()
    c.set_source_rgba(*hsl(hue + 330, .7, .14))
    c.arc(48, 44, 9.6, 0, 7)
    c.fill()
    sf.flush()
    d = sf.get_data()
    st = sf.get_stride()
    return [[(d[y * st + x * 4 + 2] * .3 + d[y * st + x * 4 + 1] * .59 + d[y * st + x * 4] * .11) / 255 for x in range(g)] for y in range(g)]


def cover_grid(song, hue):
    vid = (song or {}).get("id")
    if vid and len(str(vid)) == 11:
        try:
            from widgets import fetch_pixbuf
            return _grid_pixbuf(fetch_pixbuf(f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"))
        except Exception as e:  # noqa: BLE001
            engine.log(f"rückblick: cover {e!r}")
    return _grid_fallback(hue)


def draw_dots(cr, grid, x, y, size, fg, bg, dim, circle=False):
    g = len(grid)
    cr.save()
    if circle:
        cr.arc(x + size / 2, y + size / 2, size / 2, 0, 2 * math.pi)
        cr.clip()
    if bg is not None:
        cr.set_source_rgba(*bg)
        cr.rectangle(x, y, size, size)
        cr.fill()
    cell = size / g
    for j in range(g):
        for i in range(g):
            l = grid[j][i]
            cr.set_source_rgba(*(alpha(fg, .35 + l * .65) if l > .2 else alpha(dim, .55)))
            cr.arc(x + i * cell + cell / 2, y + j * cell + cell / 2, cell * (.12 + .4 * l), 0, 2 * math.pi)
            cr.fill()
    cr.restore()


def rect(cr, x, y, w, h, color):
    cr.set_source_rgba(*color)
    cr.rectangle(x * U, y * U, w * U, h * U)
    cr.fill()


def squares(cr, x, y, frac, on, off, n=12):
    k = max(0, min(n, round(frac * n)))
    for i in range(n):
        rect(cr, x + i * 2.45, y - 2.0, 1.9, 2.0, on if i < k else off)


def section_list(cr, pen, d, start, step, ac, fg, dim, line, first=5.1, stride=4.2):
    y = start
    for label, rows, show in rubriken(d):
        pen.text(label, 6.5, y, 2.4, dim, spacing=.12)
        pen.text(f"TOP {len(rows)}", 93.5, y, 2.4, dim, spacing=.12, right=True)
        rect(cr, 6.5, y + 1.1, 87, .25, line)
        mx = max(rows[0][1], 1)
        for i, (name, v) in enumerate(rows):
            by = y + first + i * stride
            pen.text(str(i + 1), 6.5, by, 2.7, ac if i == 0 else dim, bold=i == 0)
            pen.text(name, 10.7, by, 2.7, ac if i == 0 else fg, bold=i == 0, max_u=24)
            squares(cr, 38, by, v / mx, ac, line)
            pen.text(show(v), 93.5, by, 2.7, ac if i == 0 else dim, bold=i == 0, right=True)
        y += step


def _footer(cr, pen, win, ac, dim, label):
    rect(cr, 6.5, 117.9, 1.8, 2.1, ac)
    pen.text(f"{win['name']} gibt die farbe vor", 9.6, 120, 2.3, dim, spacing=.08)
    pen.text(label, 93.5, 120, 2.3, dim, spacing=.08, right=True)


def terminal(cr, pen, d, win, ac, hue, grid):
    bg, fg, dim, line = hsl(hue, .22, .07), hsl(hue, .12, .9), hsl(hue, .10, .58), hsl(hue, .14, .22)
    cr.set_source_rgba(*bg)
    cr.paint()
    pen.text("MUSICALIST", 6.5, 9, 2.5, dim, spacing=.14)
    pen.text(f"{d['label'].split(' ·')[0].upper()} · {d['range'].upper()}", 93.5, 9, 2.5, dim, spacing=.14, right=True, max_u=70)
    pen.text("wochenrückblick", 6.5, 20, 8.6, ac, bold=True, spacing=-.04)
    top, sz = 25, 36
    draw_dots(cr, grid, 6.5 * U, top * U, sz * U, ac, bg, hsl(hue, .14, .2))
    mx, mw = 48, 45.5
    pen.text("meistgehört", mx, top + 4, 2.6, dim)
    s = win.get("song")
    if s:
        pen.text(s["t"], mx, top + 9.3, 3.6, fg, bold=True, max_u=mw)
        pen.text(s["a"], mx, top + 13.6, 3.6, fg, bold=True, max_u=mw)
        pen.text(f"{s['n']}× gespielt · {win['name']}", mx, top + 17.6, 2.6, ac, max_u=mw)
    pen.text("die meiste hörzeit", mx, top + 24, 2.6, dim)
    pen.text(win["name"], mx, top + 28.8, 3.6, fg, bold=True, max_u=mw)
    pen.text(hmin(win["hm"]), mx, top + 33, 2.6, ac)
    section_list(cr, pen, d, 65.5, 17.6, ac, fg, dim, line, first=4.7, stride=3.9)
    _footer(cr, pen, win, ac, dim, d["label"].split(" ·")[0].upper())


def poster(cr, pen, d, win, ac, hue, grid):
    ink = hsl(hue, .45, .09) if light_of(ac) > .55 else hsl(hue, .30, .97)
    cr.set_source_rgba(*ac)
    cr.paint()
    pen.text(f"MUSICALIST · {d['label'].upper()}", 6, 9, 2.6, ink, spacing=.14, max_u=88)
    pen.text("hörte am meisten", 6, 17, 2.6, alpha(ink, .75), spacing=.1)
    pen.text(win["name"], 6, 23.5, 5.6, ink, bold=True, spacing=-.02, max_u=60)
    num = str(win["hm"] // 60)
    size = min(46, 84 / (len(num) * .6 + .45))
    pen.text(num, 4.2, 58, size, ink, bold=True, spacing=-.06)
    pen.text("h", 4.2 + pen.width(num, size, True, -.06) + 1, 58, size * .3, ink, bold=True)
    pen.text(f"{win['hm'] % 60} min dazu", 6, 65, 3, ink, spacing=.1)
    rect(cr, 6, 66.6, 9, .45, ink)
    r, cx, cy = 13, 84, 76
    cr.set_source_rgba(0, 0, 0, .27)
    cr.arc(cx * U, (cy + .6) * U, r * U, 0, 2 * math.pi)
    cr.fill()
    draw_dots(cr, grid, (cx - r) * U, (cy - r) * U, 2 * r * U, ac, ink, alpha(ac, .35), circle=True)
    cr.set_source_rgba(*ac)
    cr.arc(cx * U, cy * U, 1.8 * U, 0, 2 * math.pi)
    cr.fill()
    s = win.get("song")
    if s:
        pen.text("meistgehört", 6, 74, 2.2, alpha(ink, .75), spacing=.1)
        pen.text(s["t"], 6, 79.6, 4.2, ink, bold=True, max_u=60)
        pen.text(f"{s['a']} · {s['n']}×", 6, 83.8, 2.6, alpha(ink, .8), max_u=60)
    rect(cr, 6, 94, 88, .45, ink)
    for ci, (label, rows, show) in enumerate(rubriken(d)):
        x = 6 + ci * 29.6
        pen.text(label.upper(), x, 99.4, 2.1, ink, spacing=.14, max_u=27)
        for i, (name, v) in enumerate(rows):
            y = 103.2 + i * 6.3
            pen.text(show(v), x, y, 2.1, alpha(ink, .75), max_u=27)
            pen.text(name, x, y + 3.3, 3.1, ink, bold=True, max_u=27)


def year(cr, pen, d, win, ac, hue, grid):
    bg, fg, dim, line = hsl(hue, .22, .07), hsl(hue, .12, .9), hsl(hue, .10, .58), hsl(hue, .14, .22)
    cr.set_source_rgba(*bg)
    cr.paint()
    pen.text("MUSICALIST", 6.5, 9, 2.5, dim, spacing=.14)
    pen.text(f"JAHRESRÜCKBLICK {d['label']}", 93.5, 9, 2.5, dim, spacing=.14, right=True)
    num = str(win["hm"] // 60)
    size = min(34, 58 / (len(num) * .6 + .5))
    pen.text(num, 5.5, 37, size, ac, bold=True, spacing=-.06)
    pen.text("h", 5.5 + pen.width(num, size, True, -.06) + .8, 37, size * .3, ac, bold=True)
    draw_dots(cr, grid, 66 * U, 14 * U, 27.5 * U, ac, bg, hsl(hue, .14, .2))
    pen.text(f"{win['name']} hörte am meisten", 6.5, 46, 3.2, fg, bold=True, max_u=85)
    s = win.get("song")
    if s:
        pen.text(f"meistgehört: {s['t']} – {s['a']} · {s['n']}×", 6.5, 50.6, 2.6, dim, max_u=87)
    rect(cr, 6.5, 53.5, 87, .25, line)
    section_list(cr, pen, d, 60.5, 19.2, ac, fg, dim, line)
    _footer(cr, pen, win, ac, dim, d["label"])


def render(d, path):
    win = max(d["people"], key=lambda p: p["hm"])
    ac = win.get("ac") or GREEN
    hue = hue_of(ac)
    sf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(sf)
    cr.set_antialias(cairo.ANTIALIAS_BEST)
    pen = Pen(cr)
    grid = cover_grid(win.get("song"), hue)
    {"m": poster, "y": year}.get(d["kind"], terminal)(cr, pen, d, win, ac, hue, grid)
    sf.write_to_png(path)
    return win


# ---------------- Verwaltung: Ablage, Stichtage, Meldung ----------------
class Recaps:
    def __init__(self, friends):
        self.f = friends
        self.dir = os.path.join(engine.DATA, "recaps")
        os.makedirs(self.dir, exist_ok=True)
        self.lock = threading.Lock()
        self.items = self._load()

    def _load(self):
        try:
            with open(os.path.join(self.dir, "index.json")) as f:
                return [i for i in json.load(f) if os.path.exists(os.path.join(self.dir, i["file"]))]
        except (OSError, ValueError):
            return []

    def _save(self):
        tmp = os.path.join(self.dir, "index.json.tmp")
        with open(tmp, "w") as f:
            json.dump(self.items, f, ensure_ascii=False)
        os.replace(tmp, os.path.join(self.dir, "index.json"))

    @property
    def unseen(self):
        return [i for i in self.items if not i.get("seen")]

    def path(self, item):
        return os.path.join(self.dir, item["file"])

    def mark_seen(self):
        with self.lock:
            if any(not i.get("seen") for i in self.items):
                for i in self.items:
                    i["seen"] = True
                self._save()

    @property
    def auto(self):
        return bool(engine.setting("recap_auto"))      # Standard: aus

    def set_auto(self, on):
        engine.set_setting("recap_auto", bool(on))

    def make(self, kind, force=False):
        """Bild für kind jetzt erzeugen (blockierend) → Eintrag oder None (keine Zahlen). force = Test, ersetzt nichts Echtes."""
        d = collect(self.f, kind)
        if d is None:
            return None
        if not force and any(i["key"] == d["key"] for i in self.items):
            return next(i for i in self.items if i["key"] == d["key"])
        name = ("test-" if force else "") + d["key"]
        file = name + ".png"
        win = render(d, os.path.join(self.dir, file))
        item = {"k": kind, "key": name, "title": f"{KINDS[kind]} · {d['label']}", "range": d["range"], "at": int(time.time() * 1000),
                "file": file, "seen": False, "winner": win["name"], "win": hmin(win["hm"])}
        with self.lock:
            self.items = ([item] + [i for i in self.items if i["key"] != name])[:80]
            self._save()
        if self.auto:
            try:
                self.save_pictures(item)
            except Exception as e:  # noqa: BLE001
                engine.log(f"rückblick: speichern {e!r}")
        for fn in list(self.f.listeners):
            try:
                fn()
            except Exception:  # noqa: BLE001
                pass
        return item

    def save_pictures(self, item):
        """Kopie in ~/Pictures/musicalist (Download) → Pfad."""
        pics = os.path.join(os.path.expanduser("~"), "Pictures", "musicalist")
        os.makedirs(pics, exist_ok=True)
        dest = os.path.join(pics, f"musicalist-{item['key']}.png")
        shutil.copyfile(self.path(item), dest)
        return dest

    def check(self):
        """Stichtage: Sonntag / Monatsletzter / 31.12., jeweils ab 20 Uhr bis 4 Uhr früh (die Woche der Analyse wechselt um 4 Uhr)."""
        now = datetime.now()
        if 4 <= now.hour < 20:
            return
        day = now.date() - timedelta(days=1) if now.hour < 4 else now.date()
        due = []
        if day.weekday() == 6:
            due.append("w")
        if (day + timedelta(days=1)).day == 1:
            due.append("m")
        if day.month == 12 and day.day == 31:
            due.append("y")
        keys = {"w": f"{day.isocalendar()[0]}-{day.isocalendar()[1]}", "m": f"{day.year}-{day.month}", "y": f"{day.year}"}
        done = list(engine.setting("recap_done") or [])
        todo = [k for k in due if k + keys[k] not in done]
        if not todo:
            return
        try:
            self.f.refresh()                      # frische Stände der Freunde
        except Exception:  # noqa: BLE001
            pass
        for k in todo:
            item = None
            try:
                item = self.make(k)
            except Exception as e:  # noqa: BLE001
                engine.log(f"rückblick: {e!r}")
            done.append(k + keys[k])
            engine.set_setting("recap_done", done[-40:])
            if item:
                self.notify(item)

    def notify(self, item):
        try:
            subprocess.Popen(["notify-send", "-a", "musicalist", "-i", self.path(item), f"dein {KINDS[item['k']]} ist da",
                              f"{item['winner']} hat am meisten gehört ({item['win']}) · {item['range']}"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass
