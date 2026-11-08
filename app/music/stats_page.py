# musicalist – Tab „analyse“: Hörverhalten genau auswerten, mit Wochen-, Monats- und Jahresrückblick
# (Teil von MusicWindow, siehe ui.py). Rechnet analyse.py im Hintergrund über das Hörprotokoll (engine.Journal).
import math
import os

from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo

import tui
from tui import label, hbox, vbox
import analyse as A
import engine
from engine import Stats
from rows import artist_link

CSS = """
.an-title { font-size: 15px; font-weight: bold; color: @primary; }
.an-story { font-size: 13px; }
flowboxchild.kpi-c { padding: 0; }
.kpi { border: 1px solid alpha(@outline, 0.35); border-radius: 6px; padding: 6px 10px; }
.kpi-num { font-size: 18px; font-weight: bold; }
.kpi-lbl { font-size: 11px; color: @secondary; }
.kpi-up { font-size: 11px; color: @primary; }
.kpi-down { font-size: 11px; color: @tertiary; }
.kpi-flat { font-size: 11px; color: alpha(@foreground, 0.5); }
.an-sub { color: @secondary; margin-top: 8px; }
.an-badge { font-size: 9px; font-weight: bold; letter-spacing: 1px; color: @on_primary; background: @primary;
            border-radius: 3px; padding: 0 4px; }
.an-rank { color: alpha(@foreground, 0.45); min-width: 22px; }
.an-bar { color: @primary; font-family: monospace; }
"""
ART_OPTS = [("w", "woche"), ("m", "monat"), ("y", "jahr"), ("a", "gesamt")]
EIGHTHS = " ▏▎▍▌▋▊▉█"


def bar_text(frac, width=14):
    """Balken aus Achtel-Blöcken (genauer als ganze █)."""
    cells = max(0.0, min(1.0, frac)) * width
    full = int(cells)
    rest = int(round((cells - full) * 8))
    s = "█" * full + (EIGHTHS[rest] if rest and full < width else "")
    return (s or "▏").ljust(width)


def _rgba(name, fallback=(0.9, 0.7, 0.55)):
    c = tui.colors().get(name)
    return (c.red, c.green, c.blue) if c else fallback


# ---------- gezeichnete Diagramme ----------
class BarChart(Gtk.DrawingArea):
    """Säulen (z. B. Hörzeit je Tag/Monat), Beschriftung darunter, genaue Werte als Tooltip."""

    def __init__(self, height=118):
        super().__init__(content_height=height, hexpand=True, has_tooltip=True)
        self.items = []
        self.set_draw_func(self._draw)
        self.connect("query-tooltip", self._tip)

    def set_items(self, items):
        """items: [{"v": wert, "short": beschriftung, "tip": text, "now": bool, "future": bool}]"""
        self.items = items
        self.queue_draw()

    def _slot(self, w):
        return (w - 2) / max(1, len(self.items))

    def _draw(self, _a, cr, w, h):
        if not self.items:
            return
        p, fg = _rgba("primary"), _rgba("foreground", (0.9, 0.9, 0.9))
        lay = self.create_pango_layout("")
        lay.set_font_description(Pango.FontDescription.from_string(f"{tui.FONT} 8"))
        lab_h, top = 15, 14
        ch = h - lab_h - top
        vmax = max(i["v"] for i in self.items) or 1
        slot = self._slot(w)
        bw = max(2.0, slot * 0.72)
        # Hilfslinie + größter Wert oben links
        cr.set_source_rgba(*fg, 0.12)
        cr.set_line_width(1)
        for frac in (0.5, 1.0):
            y = top + ch * (1 - frac) + 0.5
            cr.move_to(0, y)
            cr.line_to(w, y)
        cr.stroke()
        lay.set_text(A.dur(vmax), -1)
        cr.set_source_rgba(*fg, 0.45)
        cr.move_to(2, 0)
        PangoCairo.show_layout(cr, lay)
        # Beschriftung: nur jede k-te, damit nichts überlappt
        widest = max(len(i["short"]) for i in self.items) * 6.2 + 6
        k = max(1, math.ceil(widest / max(1, slot)))
        for n, it in enumerate(self.items):
            x = 1 + n * slot + (slot - bw) / 2
            bh = (it["v"] / vmax) * ch if it["v"] else 0
            if it.get("future"):
                cr.set_source_rgba(*fg, 0.10)
                cr.rectangle(x, top + ch - 2, bw, 2)
                cr.fill()
            elif bh:
                cr.set_source_rgba(*p, 1.0 if it.get("now") else 0.72)
                cr.rectangle(x, top + ch - max(1.5, bh), bw, max(1.5, bh))
                cr.fill()
            else:
                cr.set_source_rgba(*fg, 0.18)
                cr.rectangle(x, top + ch - 1, bw, 1)
                cr.fill()
            if n % k == 0 or it.get("now"):
                lay.set_text(it["short"], -1)
                tw, _th = lay.get_pixel_size()
                cr.set_source_rgba(*(p if it.get("now") else fg), 1.0 if it.get("now") else 0.55)
                cr.move_to(1 + n * slot + slot / 2 - tw / 2, h - lab_h + 2)
                PangoCairo.show_layout(cr, lay)

    def _tip(self, _w, x, _y, _kb, tip):
        if not self.items:
            return False
        n = int((x - 1) / self._slot(self.get_width()))
        if 0 <= n < len(self.items):
            tip.set_text(self.items[n]["tip"])
            return True
        return False


class Heat(Gtk.DrawingArea):
    """Raster (Zeilen × Spalten), Farbstärke = Wert. Wochentag × Stunde oder Kalender (Tage × Wochen)."""

    def __init__(self, rows, cols, row_labels, col_labels, cell_h=13, left=26, center=False):
        super().__init__(hexpand=True, has_tooltip=True, content_height=rows * cell_h + 16)
        self.rows, self.cols, self.cell_h, self.left = rows, cols, cell_h, left
        self.row_labels, self.col_labels = row_labels, col_labels     # col_labels: {spalte: text}
        self.center = center                                          # Spaltenbeschriftung mittig
        self.vals = [[0.0] * cols for _ in range(rows)]
        self.tips = {}
        self.mark = None
        self.set_draw_func(self._draw)
        self.connect("query-tooltip", self._tip)

    def set_data(self, vals, tips, mark=None):
        self.vals, self.tips, self.mark = vals, tips, mark
        self.queue_draw()

    def _cell(self, w):
        return (w - self.left) / self.cols

    def _draw(self, _a, cr, w, h):
        p, fg = _rgba("primary"), _rgba("foreground", (0.9, 0.9, 0.9))
        lay = self.create_pango_layout("")
        lay.set_font_description(Pango.FontDescription.from_string(f"{tui.FONT} 8"))
        cw, chh = self._cell(w), self.cell_h
        vmax = max((v for row in self.vals for v in row if v is not None), default=0) or 1
        gap = 2 if cw > 7 else 1
        for r in range(self.rows):
            if self.row_labels[r]:
                lay.set_text(self.row_labels[r], -1)
                cr.set_source_rgba(*fg, 0.55)
                cr.move_to(0, r * chh + (chh - 11) / 2)
                PangoCairo.show_layout(cr, lay)
            for c in range(self.cols):
                v = self.vals[r][c]
                if v is None:                    # außerhalb des Zeitraums
                    continue
                x, y = self.left + c * cw, r * chh
                if v:
                    cr.set_source_rgba(*p, 0.18 + 0.82 * (v / vmax) ** 0.6)
                else:
                    cr.set_source_rgba(*fg, 0.07)
                cr.rectangle(x, y, cw - gap, chh - gap)
                cr.fill()
                if self.mark == (r, c):
                    cr.set_source_rgba(*fg, 0.9)
                    cr.set_line_width(1)
                    cr.rectangle(x + 0.5, y + 0.5, cw - gap - 1, chh - gap - 1)
                    cr.stroke()
        for c, text in self.col_labels.items():
            lay.set_text(text, -1)
            tw, _th = lay.get_pixel_size()
            cr.set_source_rgba(*fg, 0.55)
            cr.move_to(self.left + c * cw + ((cw - tw) / 2 if self.center else 0), self.rows * chh + 2)
            PangoCairo.show_layout(cr, lay)

    def _tip(self, _w, x, y, _kb, tip):
        c = int((x - self.left) / self._cell(self.get_width()))
        r = int(y / self.cell_h)
        text = self.tips.get((r, c))
        if text:
            tip.set_text(text)
            return True
        return False


# ---------- Seite ----------
class StatsMixin:
    """Tab „analyse“. Zustand: an_art (w/m/y/a), an_off (0 = laufender Zeitraum), an_res (letzte Auswertung)."""

    def build_stats(self):
        css = Gtk.CssProvider()
        css.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_USER + 2)
        self.an_art = engine.setting("analyse_art") or "w"
        if self.an_art not in dict(ART_OPTS):
            self.an_art = "w"
        self.an_off, self.an_res, self.an_gen, self.an_dirty = 0, None, 0, True
        self.an_more = set()                 # aufgeklappte Listen
        self.an_clear_armed = 0
        self._an_refresh_id = None
        self.an_sel = tui.Select(self.an_set_art, tooltip="Zeitraum (w / m / j / g)")
        self.an_sel.set_options(ART_OPTS, self.an_art)
        self.an_prev = tui.Button("‹", lambda: self.an_step(-1), tooltip="Früherer Zeitraum (Bild ↑)")
        self.an_next = tui.Button("›", lambda: self.an_step(1), tooltip="Späterer Zeitraum (Bild ↓)")
        self.an_today = tui.Button("jetzt", lambda: self.an_go(0), tooltip="Zum laufenden Zeitraum (Pos1)")
        self.an_title = label("", "an-title", ellipsize=True)
        self.an_sub = label("", "dim", ellipsize=True)
        bar = hbox(self.an_sel, self.an_prev, vbox(self.an_title, self.an_sub, spacing=0, hexpand=True),
                   self.an_today, self.an_next, spacing=8)
        bar.set_margin_bottom(6)
        self.an_box = vbox(spacing=10)
        self.an_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.EXTERNAL, child=self.an_box,
                                            vexpand=True)
        self.add_page("stats", vbox(bar, self.an_scroll, spacing=0), scroll=False)
        self.p.journal.listeners.append(self.an_changed)
        GLib.timeout_add_seconds(6, lambda: self.an_check_review() and False)
        GLib.timeout_add_seconds(3600, lambda: self.an_check_review() or True)    # läuft als Daemon tagelang

    # ----- Steuerung -----
    def an_set_art(self, art):
        self.an_art, self.an_off = art, 0
        self.an_sel.set_options(ART_OPTS, art)
        engine.set_setting("analyse_art", art)
        self.an_refresh(top=True)

    def an_step(self, d):
        r = self.an_res
        if d < 0 and r is not None and not r.get("older") and not r.get("empty"):
            return
        if d > 0 and self.an_off >= 0:
            return
        self.an_go(self.an_off + d)

    def an_go(self, off):
        self.an_off = min(0, off)
        self.an_refresh(top=True)

    def an_key(self, kv):
        """Tasten im Tab analyse (nur ohne Fokus im Eingabefeld)."""
        keys = {Gdk.KEY_Page_Up: lambda: self.an_step(-1), Gdk.KEY_Page_Down: lambda: self.an_step(1),
                Gdk.KEY_Home: lambda: self.an_go(0), Gdk.KEY_w: lambda: self.an_set_art("w"),
                Gdk.KEY_m: lambda: self.an_set_art("m"), Gdk.KEY_j: lambda: self.an_set_art("y"),
                Gdk.KEY_g: lambda: self.an_set_art("a")}
        fn = keys.get(kv)
        if fn:
            fn()
            return True
        return False

    def an_changed(self):
        """Neuer Eintrag im Hörprotokoll: sichtbar → gleich (gebündelt) neu rechnen, sonst beim nächsten Öffnen."""
        self.an_dirty = True
        if self.current_tab() == "stats" and self._an_refresh_id is None:
            self._an_refresh_id = GLib.timeout_add_seconds(3, self._an_refresh_later)

    def _an_refresh_later(self):
        self._an_refresh_id = None
        if self.current_tab() == "stats":
            self.an_refresh()
        return False

    def an_shown(self):
        """Tab wurde geöffnet."""
        pend = getattr(self, "an_pending", None)
        if pend:                                   # neuer Rückblick wartet → direkt dorthin
            self.an_pending = None
            art, key = pend
            seen = dict(engine.setting("review_seen") or {})
            seen[art] = key
            engine.set_setting("review_seen", seen)
            self.an_art, self.an_off = art, -1
            self.an_sel.set_options(ART_OPTS, art)
            self.an_refresh(top=True)
        elif self.an_dirty or self.an_res is None:
            self.an_refresh()

    def an_refresh(self, top=False):
        self.an_dirty = False
        self.an_gen += 1
        gen, art, off = self.an_gen, self.an_art, self.an_off
        if self.an_res is None:
            tui.clear(self.an_box)
            self.an_box.append(label("rechne …", "empty", xalign=0.5))
        pos = 0 if top else self.an_scroll.get_vadjustment().get_value()

        def work():
            rows = list(self.p.journal.load())
            return A.analyse(rows, art, off)

        def done(res):
            if gen != self.an_gen:
                return
            if isinstance(res, Exception):
                engine.log(f"analyse: {res}")
                tui.clear(self.an_box)
                self.an_box.append(label(f"auswertung fehlgeschlagen: {res}", "empty", xalign=0.5, wrap=True))
                return
            self.an_res = res
            self.an_render(res)
            GLib.idle_add(lambda: self.an_scroll.get_vadjustment().set_value(pos) and False)
        tui.background(work, done=done)

    # ----- Rückblick-Hinweis: neue Woche/Monat/Jahr -----
    @staticmethod
    def _period_key(art, lo):
        import datetime as dt
        d = dt.date.fromtimestamp(lo + 3600 * 12)
        return {"w": "%d-W%02d" % d.isocalendar()[:2], "m": f"{d.year}-{d.month:02d}", "y": str(d.year)}[art]

    def an_check_review(self):
        """Ist ein Zeitraum (Jahr > Monat > Woche) frisch zu Ende und noch nicht angesehen → Hinweis."""
        if not engine.setting("history"):
            return False

        def work():
            rows = self.p.journal.load()
            for art in ("y", "m", "w"):
                lo, hi, title, _sub = A.bounds(art, -1)
                if any(lo <= e["at"] < hi for e in reversed(rows[-20000:])):
                    key = self._period_key(art, lo)
                    seen = (engine.setting("review_seen") or {}).get(art)
                    if seen is None:             # erster Start mit dieser Version: still als gesehen merken
                        return ("init", art, key, title)
                    if seen != key:
                        return ("new", art, key, title)
            return None

        def done(res):
            if not res or isinstance(res, Exception):
                return
            kind, art, key, title = res
            if kind == "init":
                seen = dict(engine.setting("review_seen") or {})
                for a in ("w", "m", "y"):
                    lo, _hi, _t, _s = A.bounds(a, -1)
                    seen.setdefault(a, self._period_key(a, lo))
                engine.set_setting("review_seen", seen)
                return
            if getattr(self, "an_pending", None) == (art, key):
                return                           # schon gemeldet, noch nicht angesehen
            self.an_pending = (art, key)
            what = {"w": "wochen", "m": "monats", "y": "jahres"}[art]
            self.say(f"󰄨 dein {what}rückblick ist da ({title}) – tab 7 „analyse“", seconds=12)
        tui.background(work, done=done)
        return False

    # ----- Darstellung -----
    def an_render(self, r):
        self.an_title.set_label(r["title"])
        self.an_sub.set_label(r["sub"] + ("  · läuft noch" if r.get("running") and r["art"] != "a" else ""))
        self.an_prev.set_sensitive(bool(r.get("older")) or (r.get("empty") and r["art"] != "a"))
        self.an_next.set_sensitive(self.an_off < 0 and r["art"] != "a")
        self.an_today.set_visible(self.an_off < 0 and r["art"] != "a")
        self.an_prev.set_visible(r["art"] != "a")
        self.an_next.set_visible(r["art"] != "a")
        box = self.an_box
        tui.clear(box)
        if r.get("empty"):
            if not engine.setting("history"):
                msg = "der hörverlauf ist aus (einstellungen) – dann wird nichts protokolliert"
            elif not r["total_rows"]:
                msg = "noch nichts gehört – die analyse füllt sich beim hören"
            else:
                msg = "in diesem zeitraum nichts gehört"
            box.append(label(msg, "empty", xalign=0.5, wrap=True))
            box.append(self._an_log_panel(r))
            return
        for fn in (self._an_overview, self._an_timeline, self._an_top_tracks, self._an_top_artists,
                   self._an_top_albums, self._an_discover, self._an_habits, self._an_sessions, self._an_behaviour,
                   self._an_sources, self._an_variety, self._an_taste, self._an_milestones, self._an_log_panel):
            try:
                w = fn(r)
            except Exception as e:  # noqa: BLE001 – ein kaputter Abschnitt darf nicht die ganze Seite kosten
                engine.log(f"analyse {fn.__name__}: {type(e).__name__}: {e}")
                w = None
            if w is not None:
                box.append(w)

    # kleine Bausteine
    @staticmethod
    def _panel(title, *children):
        p = tui.Panel(title)
        for c in children:
            if c is not None:
                p.body.append(c)
        return p

    @staticmethod
    def _line(text, *cls, markup=False):
        return label(text, *cls, xalign=0, wrap=True, markup=markup)

    @staticmethod
    def _sub(text):
        return label(text, "an-sub", xalign=0, wrap=True)

    @staticmethod
    def _kv(rows):
        """Zweispaltige Liste: [(name, wert)]."""
        g = Gtk.Grid(column_spacing=16, row_spacing=2)
        for i, (k, v) in enumerate(rows):
            g.attach(label(k, "dim", xalign=0), 0, i, 1, 1)
            g.attach(label(v, xalign=0, wrap=True, hexpand=True), 1, i, 1, 1)
        return g

    def _bars(self, rows, width=14):
        """[(anteil 0–1, text oder widget, rechts, klick)] → Zeilen mit Balken. Schmale Fenster: kürzere Balken,
        rechte Angabe wird notfalls gekürzt (Tooltip zeigt sie ganz)."""
        if getattr(self, "tier", 0) >= 2:
            width = min(width, 6)
        box = vbox(spacing=0)
        for frac, text, right, click in rows:
            mid = text if isinstance(text, Gtk.Widget) else label(text, hexpand=True, ellipsize=True, xalign=0)
            mid.set_hexpand(True)
            rl = label(right, "dim", ellipsize=True, xalign=1)
            rl.set_tooltip_text(right)
            inner = hbox(label(bar_text(frac, width), "an-bar"), mid, rl, spacing=10)
            if click:
                b = Gtk.Button(child=inner, hexpand=True)
                b.add_css_class("rowhead")
                b.connect("clicked", lambda _b, f=click: f())
                row = Gtk.Box()
                row.add_css_class("row")
                row.append(b)
                box.append(row)
            else:
                inner.set_margin_start(6)
                inner.set_margin_end(6)
                box.append(inner)
        return box

    def _more_btn(self, key, n_all, shown):
        if n_all <= shown and key not in self.an_more:
            return None
        on = key in self.an_more
        b = tui.Button("weniger" if on else f"alle {n_all} zeigen", lambda: self._toggle_more(key))
        b.set_halign(Gtk.Align.START)
        return b

    def _toggle_more(self, key):
        self.an_more ^= {key}
        self._an_rerender()

    def _an_rerender(self):
        if self.an_res:
            pos = self.an_scroll.get_vadjustment().get_value()
            self.an_render(self.an_res)
            GLib.idle_add(lambda: self.an_scroll.get_vadjustment().set_value(pos) and False)

    @staticmethod
    def _badge(text):
        return label(text, "an-badge")

    @staticmethod
    def _day(d):
        """„mo, 3. nov“ – mit Jahr, wenn es nicht das laufende ist."""
        y = f" {d.year}" if d.year != A.day_key(GLib.get_real_time() / 1e6).year else ""
        return f"{A.WD[d.weekday()]}, {d.day}. {A.MON[d.month - 1]}{y}"

    # ----- Abschnitte -----
    def _an_overview(self, r):
        b, prev, dl = r["base"], r["prev"], r["deltas"]
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, min_children_per_line=2,
                           max_children_per_line=5, column_spacing=6, row_spacing=6)

        def tile(num, lbl, delta=None, delta_text=None, tip=None):
            box = vbox(label(num, "kpi-num"), label(lbl, "kpi-lbl"), spacing=0)
            box.add_css_class("kpi")
            if delta_text is None and delta is not None:
                delta_text = A.delta_text(delta)
            if delta_text:
                cls = "kpi-flat" if delta is None or abs(delta) < 0.5 else "kpi-up" if delta > 0 else "kpi-down"
                box.append(label(delta_text, cls))
            if tip:
                box.set_tooltip_text(tip)
            child = Gtk.FlowBoxChild(child=box, focusable=False)
            child.add_css_class("kpi-c")
            flow.append(child)
        vs = f"vergleich: {prev['title']}" + (" bis zum gleichen zeitpunkt" if prev and prev.get("partial") else "") \
            if prev else None
        tile(A.dur(b["secs"]), "hörzeit", dl.get("secs"), tip=vs)
        tile(str(b["plays"]), "wiedergaben", dl.get("plays"),
             tip=f"{b['starts']} titel angespielt, {b['plays']} davon ≥ 30 s oder halb gehört")
        tile(str(b["tracks"]), "verschiedene titel", dl.get("tracks"), tip=vs)
        tile(str(b["artists"]), "künstler", dl.get("artists"), tip=vs)
        tile(str(b["albums"]), "alben", dl.get("albums"), tip=vs)
        tile(f"{b['days']}/{r['span_days']}", "tage gehört", dl.get("days"))
        tile(A.dur(r["per_day"]), "ø pro tag", tip=f"ø {A.dur(r['per_active_day'])} an tagen, an denen du gehört hast")
        if b["skip"] is not None:
            d = b["skip"] - prev["skip"] if prev and prev.get("skip") is not None else None
            tile(f"{b['skip']:.0f} %", "übersprungen", None if d is None else -d,
                 delta_text=None if d is None else f"{'▲' if d > 0 else '▼'} {abs(d):.0f} pp",
                 tip="anteil der angespielten titel, die du vor 80 % weitergeklickt hast")
        if b["complete"] is not None:
            tile(f"{b['complete']:.0f} %", "bis zum ende", tip="anteil der titel, die bis (fast) zum schluss liefen")
        story = vbox(*[label(s, "an-story", xalign=0, wrap=True) for s in r["story"]], spacing=3)
        story.set_margin_bottom(8)
        return self._panel("󰄨 überblick", story, flow)

    def _an_timeline(self, r):
        chart = BarChart()
        items = []
        for b in r["timeline"]:
            tip = f"{b['long']} · {A.dur(b['secs'])} · {b['plays']} wiedergaben"
            if b["artist"]:
                tip += f"\nmeist: {b['artist']}"
            if b["track"] and b["track"][0]:
                tip += f"\ntitel: {b['track'][0]}"
            items.append({"v": b["secs"], "short": b["short"], "tip": tip, "now": b["now"], "future": b["future"]})
        chart.set_items(items)
        d, v = r["best_day"]
        parts = [chart, self._line(f"stärkster tag: {self._day(d)} mit {A.dur(v)}  ·  ø {A.dur(r['per_day'])} "
                                   f"pro tag, ø {A.dur(r['per_active_day'])} an hör-tagen", "dim")]
        if r["art"] in ("y", "a", "m"):
            parts.insert(1, self._calendar(r))
        return self._panel("󰕾 verlauf", *parts)

    def _month_calendar(self, r):
        """Monat als Kalenderblatt: Zeilen = Wochen, Spalten = mo–so."""
        import datetime as dt
        lo, hi = A.day_key(r["lo"]), A.day_key(r["hi"] - 1)
        start = lo - dt.timedelta(days=lo.weekday())
        weeks = (hi - start).days // 7 + 1
        today = A.day_key(GLib.get_real_time() / 1e6)
        vals = [[None] * 7 for _ in range(weeks)]
        tips, mark = {}, None
        for i in range(weeks * 7):
            d = start + dt.timedelta(days=i)
            row, c = i // 7, i % 7
            if lo <= d <= hi:
                v = r["days"].get(d.isoformat(), 0.0)
                vals[row][c] = v if d <= today else None
                tips[(row, c)] = f"{self._day(d)} · {A.dur(v) if v else 'nichts gehört'}"
                if d == today:
                    mark = (row, c)
        labels = [f"kw {(start + dt.timedelta(weeks=w)).isocalendar()[1]}" for w in range(weeks)]
        h = Heat(weeks, 7, labels, {c: A.WD[c] for c in range(7)}, cell_h=24, left=44, center=True)
        h.set_data(vals, tips, mark)
        h.set_hexpand(False)
        h.set_halign(Gtk.Align.START)
        h.set_size_request(44 + 7 * 36, -1)
        h.set_margin_top(6)
        return h

    def _calendar(self, r):
        """Kalender-Heatmap (wie bei GitHub): Spalten = Wochen, Zeilen = mo–so."""
        import datetime as dt
        if r["art"] == "m":
            return self._month_calendar(r)
        lo, hi = A.day_key(r["lo"]), A.day_key(min(r["hi"], r["lo"] + 400 * 86400 if r["art"] != "a" else r["hi"]) - 1)
        if r["art"] == "a":
            lo = max(lo, A.day_key(r["hi"] - 1) - dt.timedelta(days=370))
        start = lo - dt.timedelta(days=lo.weekday())
        weeks = (hi - start).days // 7 + 1
        vals = [[None] * weeks for _ in range(7)]
        tips, cols, last_m = {}, {}, None
        today = A.day_key(GLib.get_real_time() / 1e6)
        mark = None
        for i in range((hi - start).days + 1):
            d = start + dt.timedelta(days=i)
            c, row = i // 7, d.weekday()
            if d < lo or d > hi:
                continue
            v = r["days"].get(d.isoformat(), 0.0)
            vals[row][c] = v if d <= today else None
            tips[(row, c)] = f"{self._day(d)} · {A.dur(v) if v else 'nichts gehört'}"
            if d.month != last_m:
                cols[c] = A.MON[d.month - 1]
                last_m = d.month
            if d == today:
                mark = (row, c)
        h = Heat(7, weeks, ["mo", "", "mi", "", "fr", "", "so"], cols, cell_h=12)
        h.set_data(vals, tips, mark)
        h.set_margin_top(6)
        return h

    def _play_list(self, items, i, title):
        tracks = []
        for t in items:
            x = Stats.rebuild(t["id"], t["t"] or "?", t["a"] or "", t.get("d") or 0)
            if t.get("aid"):
                x["artistId"] = t["aid"]
            if t.get("al"):
                x["album"], x["albumId"] = t["al"], t.get("alid")
            tracks.append(x)
        self.p.play_tracks(tracks, start=i, src=("analyse", title))

    def _an_top_tracks(self, r):
        by_time = getattr(self, "an_track_sort", "plays") == "secs"
        items = r["tracks_time"] if by_time else r["tracks"]
        n = len(items) if "tracks" in self.an_more else 10
        shown = items[:min(n, 100)]
        top = (shown[0]["secs"] if by_time else shown[0]["plays"]) or 1
        rows = []
        narrow = getattr(self, "tier", 0) >= 2
        for i, t in enumerate(shown):
            mid = hbox(label(f"{i + 1}", "an-rank"), label(t["t"] or "?", ellipsize=True), spacing=6)
            mid.append(label("" if narrow else t["a"] or "", "dim", ellipsize=True, hexpand=True, xalign=0))
            mid.set_tooltip_text(f"{t['t']} · {t['a']}")
            if t["new"]:
                mid.append(self._badge("NEU"))
            right = f"{t['plays']}× · {A.dur(t['secs'])}"
            if t["det"] and t["skips"]:
                right += f" · {t['skips']}× übersprungen"
            if narrow:
                right = f"{t['secs'] // 60:.0f} min" if by_time else f"{t['plays']}×"
            rows.append(((t["secs"] if by_time else t["plays"]) / top, mid, right,
                         lambda i=i: self._play_list(shown, i, r["title"])))
        sort = tui.Select(self._set_track_sort, tooltip="Sortierung")
        sort.set_options([("plays", "nach wiedergaben"), ("secs", "nach hörzeit")], "secs" if by_time else "plays")
        sort.set_halign(Gtk.Align.START)
        top50 = items[:50]

        def shuffled():
            import random
            l = list(top50)
            random.shuffle(l)
            self._play_list(l, 0, r["title"])

        def to_playlist():
            if self.account is None:
                return self.say("dafür musst du angemeldet sein (einstellungen)", error=True)
            name = f"musicalist · top {len(top50)} · {r['title']}"
            self.say("playlist wird angelegt …")

            def done(res):
                self.say(f"playlist „{name}“ angelegt" if not isinstance(res, Exception) else f"playlist: {engine.explain(res)}",
                         error=isinstance(res, Exception))
            tui.background(self.p.music.create_playlist, name, [t["id"] for t in top50], done=done)
        acts = hbox(tui.Button(f"󰐊 top {len(top50)} spielen", lambda: self._play_list(top50, 0, r["title"])),
                    tui.Button("󰒝 mischen", shuffled), tui.Button("󰐒 als playlist", to_playlist,
                                                                  tooltip="Die meistgehörten Titel als neue Playlist in YouTube Music speichern"),
                    spacing=8)
        acts.set_halign(Gtk.Align.START)
        return self._panel(f"󰝚 top titel · {len(items)}", sort, acts, self._bars(rows), self._more_btn("tracks", len(items), 10))

    def _set_track_sort(self, v):
        self.an_track_sort = v
        self._an_rerender()

    def _an_top_artists(self, r):
        items = r["artists"]
        n = len(items) if "artists" in self.an_more else 10
        shown = items[:min(n, 100)]
        top = shown[0]["secs"] or 1
        rows = []
        for i, x in enumerate(shown):
            mid = hbox(label(f"{i + 1}", "an-rank"), label(x["name"], ellipsize=True, hexpand=True, xalign=0),
                       spacing=6)
            if x["new"]:
                mid.append(self._badge("NEU"))
            right = f"{A.dur(x['secs'])} · {x['share']:.1f} % · {x['tracks']} titel · {x['ndays']} tage"
            if getattr(self, "tier", 0) >= 2:
                right = f"{x['share']:.0f} %"
            rows.append((x["secs"] / top, mid, right,
                         lambda x=x: self.open_artist({"artist": x["name"], "artistId": x["aid"]})))
        return self._panel(f"󰠃 top künstler · {len(items)}", self._bars(rows), self._more_btn("artists", len(items), 10))

    def _an_top_albums(self, r):
        items = r["albums"]
        if not items:
            return None
        n = len(items) if "albums" in self.an_more else 6
        shown = items[:min(n, 60)]
        top = shown[0]["secs"] or 1
        rows = []
        for i, y in enumerate(shown):
            mid = hbox(label(f"{i + 1}", "an-rank"), label(y["al"], ellipsize=True),
                       label(y["a"], "dim", ellipsize=True, hexpand=True, xalign=0), spacing=6)
            ok = (y.get("alid") or "").startswith("MPRE")
            rows.append((y["secs"] / top, mid, f"{A.dur(y['secs'])} · {y['tracks']} titel",
                         (lambda a=y["alid"]: self.open_detail("album", a)) if ok else None))
        return self._panel(f"󰀥 top alben · {len(items)}", self._bars(rows), self._more_btn("albums", len(items), 6))

    def _an_discover(self, r):
        parts = []
        nt, na = r["new_tracks"], r["new_artists"]
        if not r.get("know_new") and r["art"] != "a":
            parts.append(self._line("hier beginnt dein protokoll – was neu für dich war, zeigt sich ab dem nächsten zeitraum",
                                    "dim"))
        if r.get("know_new"):
            parts.append(self._line(f"{len(nt)} titel und {len(na)} künstler zum ersten mal gehört – "
                                    f"{r['new_share']:.0f} % deiner hörzeit war neue musik"))
            if na:
                parts.append(self._sub("neue künstler"))
                top = na[0]["secs"] or 1
                parts.append(self._bars([(x["secs"] / top, x["name"], f"{A.dur(x['secs'])} · {x['tracks']} titel",
                                          lambda x=x: self.open_artist({"artist": x["name"], "artistId": x["aid"]}))
                                         for x in na[:6]]))
            if r["comebacks"]:
                parts.append(self._sub("comebacks · über 3 monate nicht gehört"))
                box = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=6, column_spacing=4)
                for x in r["comebacks"][:12]:
                    box.append(artist_link(x["name"], x["aid"], css="accent", chars=22))
                parts.append(box)
        kv = []
        if r.get("obsession"):
            t, d, n = r["obsession"]
            kv.append(("obsession", f"„{t['t']}“ – {n}× am {self._day(d)}"))
        if r.get("earworm"):
            t, n = r["earworm"]
            kv.append(("ohrwurm", f"„{t['t']}“ – {n} tage in folge"))
        if r.get("evergreen") and r["evergreen"]["ndays"] > 1:
            t = r["evergreen"]
            kv.append(("dauerbrenner", f"„{t['t']}“ – an {t['ndays']} verschiedenen tagen"))
        if kv:
            parts.append(self._sub("auffällig"))
            parts.append(self._kv(kv))
        return self._panel("󰎈 entdeckungen", *parts) if parts else None

    def _an_habits(self, r):
        tips = {}
        for d in range(7):
            for hr in range(24):
                v = r["heat"][d][hr]
                tips[(d, hr)] = f"{A.WDAYS[d]}, {hr}–{hr + 1} uhr · {A.dur(v) if v else 'nichts'}"
        h = Heat(7, 24, A.WD, {c: str(c) for c in range(0, 24, 3)}, cell_h=15)
        h.set_data(r["heat"], tips)
        tot = r["base"]["secs"] or 1
        parts = [h, self._sub(f"tageszeit · typ: {r['chronotype']}")]
        parts.append(self._bars([(p / 100, name, f"{p:.0f} % · {A.dur(v)}", None) for name, v, p in r["dayparts"]]))
        wd = r["wdays"]
        top = max(wd) or 1
        parts.append(self._sub("wochentag"))
        parts.append(self._bars([(v / top, A.WDAYS[i], f"{v / tot * 100:.0f} % · {A.dur(v)}", None)
                                 for i, v in enumerate(wd)]))
        kv = [("typischer start", f"{r['typ_first']} uhr (median der ersten wiedergabe am tag)"),
              ("typisches ende", f"{r['typ_last']} uhr"),
              ("frühester start", f"{r['earliest'][1]} uhr am {self._day(r['earliest'][0])}"),
              ("spätestes ende", f"{r['latest'][1]} uhr am {self._day(r['latest'][0])}")]
        if r.get("workday_avg") is not None and r.get("weekend_avg") is not None:
            kv.append(("werktag / wochenende", f"ø {A.dur(r['workday_avg'])} / ø {A.dur(r['weekend_avg'])} pro tag"))
        parts += [self._sub("rhythmus"), self._kv(kv)]
        return self._panel("󰥔 wann du hörst", *parts)

    def _an_sessions(self, r):
        s = r["session_longest"]
        st = A.datetime.fromtimestamp(s["start"])
        en = A.datetime.fromtimestamp(s["end"])
        kv = [("sitzungen", f"{r['sessions']} (neue sitzung nach {A.SESSION_GAP // 60} min pause)"),
              ("ø länge", f"{A.dur(r['session_avg'])} · ø {r['session_tracks']:.1f} titel"),
              ("längste", f"{A.dur(s['secs'])} am {self._day(st.date())}, {st:%H:%M}–{en:%H:%M} ({s['n']} titel)")]
        n, a, b = r["streak"]
        if n > 1:
            kv.append(("längste serie", f"{n} tage am stück ({self._day(a)} – {self._day(b)})"))
        if r.get("streak_now"):
            kv.append(("aktuelle serie", f"{r['streak_now']} {'tag' if r['streak_now'] == 1 else 'tage'}"))
        if r["longest_gap"]:
            kv.append(("längste pause", f"{r['longest_gap']} {'tag' if r['longest_gap'] == 1 else 'tage'} ohne musik"))
        hist = r["session_hist"]
        top = max(hist) or 1
        names = ["unter 10 min", "10–30 min", "30–60 min", "1–2 stunden", "über 2 stunden"]
        return self._panel("󰔛 sitzungen & serien", self._kv(kv), self._sub("länge der sitzungen"),
                           self._bars([(v / top, names[i], f"{v}×", None) for i, v in enumerate(hist)]))

    def _an_behaviour(self, r):
        if not r.get("det_n"):
            return self._panel("󰒭 hörverhalten", self._line(
                "dafür fehlen noch daten – überspringen, spulen und pausen werden erst seit version 1.16 protokolliert", "dim"))
        kv = [("übersprungen", f"{r['skip_rate']:.0f} % der titel" +
               (f", meist nach {A.dur(r['skip_after'])}" if r.get("skip_after") else "") +
               f" · {r['early_skip']:.0f} % schon in den ersten 10 s"),
              ("bis zum ende", f"{r['complete_rate']:.0f} %"),
              ("zurückgesprungen", f"{r['back_rate']:.0f} %"),
              ("gespult", f"ø {r['seeks']:.2f}× pro titel"),
              ("pausen", f"{r['pauses']}× · zusammen {A.dur(r['pause_secs'])}"),
              ("direkt wiederholt", f"{r['repeats']}×"),
              ("ø titellänge", A.dur(r["avg_len"]))]
        if r.get("volume") is not None:
            kv.append(("ø lautstärke", f"{r['volume']:.0f} %"))
        kv.append(("geliked gehört", f"{r['liked_share']:.0f} % der hörzeit"))
        if r.get("shuffle_share"):
            kv.append(("zufallswiedergabe", f"{r['shuffle_share']:.0f} % der titel"))
        if r.get("xf_n"):
            kv.append(("überblendungen", f"{r['xf_n']}×"))
        if r.get("errors"):
            kv.append(("ladefehler", f"{r['errors']}×"))
        parts = [self._kv(kv)]
        if r.get("most_skipped"):
            parts.append(self._sub("am häufigsten übersprungen"))
            top = r["most_skipped"][0]["skips"]
            parts.append(self._bars([(t["skips"] / top, f"{t['t']} · {t['a']}", f"{t['skips']} von {t['starts']}×", None)
                                     for t in r["most_skipped"]]))
        if r.get("skip_artists"):
            parts.append(self._sub("künstler: am ehesten weggeklickt · am treuesten durchgehört"))
            g = Gtk.Grid(column_spacing=24, row_spacing=2, column_homogeneous=True)
            for i, x in enumerate(r["skip_artists"]):
                g.attach(label(f"{x['skip']:.0f} %  {x['name']}", xalign=0, ellipsize=True), 0, i, 1, 1)
            for i, x in enumerate(r.get("loyal_artists") or []):
                g.attach(label(f"{x['skip']:.0f} %  {x['name']}", xalign=0, ellipsize=True), 1, i, 1, 1)
            parts.append(g)
        return self._panel("󰒭 hörverhalten", *parts)

    def _an_sources(self, r):
        if not r.get("sources"):
            return None
        parts = [self._sub("woher die musik kam"),
                 self._bars([(p / 100, n, f"{p:.0f} % · {A.dur(v)}", None) for n, v, p in r["sources"][:9]])]
        if r.get("named_sources"):
            parts.append(self._sub("meistgenutzte playlists, alben, radios, suchen"))
            top = r["named_sources"][0][2] or 1
            parts.append(self._bars([(v / top, f"{name}  ·  {kind}", A.dur(v), None)
                                     for kind, name, v in r["named_sources"]]))
        if r.get("outputs") and any(n != "?" for n, _v, _p in r["outputs"]):
            parts.append(self._sub("gehört über"))
            parts.append(self._bars([(p / 100, n if n != "?" else "unbekannt", f"{p:.0f} %", None)
                                     for n, _v, p in r["outputs"]]))
        if r.get("kinds"):
            parts.append(self._sub("gespielt von"))
            names = {"stream": "youtube (stream)", "offline": "offline-kopie", "lokal": "lokale dateien"}
            parts.append(self._bars([(p / 100, names.get(n, n), f"{p:.0f} %", None) for n, _v, p in r["kinds"]]))
        return self._panel("󰋋 quellen & geräte", *parts)

    def _an_variety(self, r):
        dv = r["diversity"]
        word = ("sehr abwechslungsreich" if dv >= 85 else "abwechslungsreich" if dv >= 70 else "ausgewogen"
                if dv >= 55 else "fokussiert" if dv >= 35 else "sehr fokussiert")
        kv = [("abwechslung", f"{dv:.0f} / 100 – {word}"),
              ("nr. 1 künstler", f"{r['top1_share']:.0f} % der hörzeit"),
              ("top 5 künstler", f"{r['top5_share']:.0f} % der hörzeit"),
              ("lieblinge", f"{r['repeat_share']:.0f} % der wiedergaben waren titel, die du ≥ 3× gehört hast"),
              ("einmal gehört", f"{r['one_off']} titel")]
        if r.get("longest_full"):
            t = r["longest_full"]
            kv.append(("längster ganz gehört", f"„{t['t']}“ ({A.dur(t['d'])})"))
        tip = ("abwechslung = wie gleichmäßig sich deine hörzeit auf künstler verteilt (normierte entropie): "
               "100 = alle gleich viel, 0 = nur eine·r")
        g = self._kv(kv)
        g.set_tooltip_text(tip)
        return self._panel("󰹩 vielfalt", self._line(bar_text(dv / 100, 30), "an-bar"), g)

    def _an_taste(self, r):
        rows = [b for b in r["timeline"] if b["artist"]]
        if len(rows) < 2:
            return None
        g = Gtk.Grid(column_spacing=14, row_spacing=2)
        for i, b in enumerate(rows):
            g.attach(label(b["long"], "dim", xalign=0), 0, i, 1, 1)
            g.attach(label(b["artist"], "accent", xalign=0, ellipsize=True), 1, i, 1, 1)
            g.attach(label(f"„{b['track'][0]}“" if b["track"] and b["track"][0] else "", xalign=0, ellipsize=True,
                           hexpand=True), 2, i, 1, 1)
            g.attach(label(A.dur(b["secs"]), "dim", xalign=1), 3, i, 1, 1)
        unit = {"w": "tag", "m": "tag", "y": "monat", "a": "zeitabschnitt"}[r["art"]]
        return self._panel(f"󰃭 geschmack im verlauf · pro {unit}", g)

    def _an_milestones(self, r):
        kv = []
        for n, e in r["milestones"]:
            d = A.datetime.fromtimestamp(e["at"])
            kv.append((f"{n}. wiedergabe" if n > 1 else "allererste", f"„{e['t']}“ · {e['a']} – {d.day}. {A.MON[d.month - 1]} {d.year}"))
        for n, e in r["hour_milestones"]:
            d = A.datetime.fromtimestamp(e["at"])
            kv.append((f"{n} stunden musik", f"erreicht mit „{e['t']}“ – {d.day}. {A.MON[d.month - 1]} {d.year}"))
        f, la = r["first"], r["last"]
        fd, ld = A.datetime.fromtimestamp(f["at"]), A.datetime.fromtimestamp(la["at"])
        kv.append(("erster titel", f"„{f['t']}“ · {f['a']} ({fd.day}. {A.MON[fd.month - 1]}, {fd:%H:%M})"))
        kv.append(("letzter titel", f"„{la['t']}“ · {la['a']} ({ld.day}. {A.MON[ld.month - 1]}, {ld:%H:%M})"))
        return self._panel("󰄬 meilensteine", self._kv(kv))

    def _an_log_panel(self, r):
        rows = self.p.journal.rows or []
        old = sum(1 for e in rows if e.get("alt"))
        info = f"{len(rows)} einträge" + (f", davon {old} aus dem alten rückblick (ohne details)" if old else "")
        path = engine.JOURNAL.replace(os.path.expanduser("~"), "~")
        txt = self._line(f"{info} · nur auf diesem gerät: {path}\n"
                         "protokolliert wird nur bei eingeschaltetem hörverlauf (einstellungen).", "dim")
        btn = tui.Button("protokoll löschen", self._an_clear, danger=True,
                         tooltip="Löscht die ganze Analyse (nicht den Verlauf links). Zweimal klicken.")
        btn.set_halign(Gtk.Align.START)
        self.an_clear_btn = btn
        return self._panel("󰋊 protokoll", txt, btn)

    def _an_clear(self):
        now = GLib.get_monotonic_time()
        if now - self.an_clear_armed > 4_000_000:
            self.an_clear_armed = now
            self.an_clear_btn.set_label("wirklich löschen?")
            return
        self.an_clear_armed = 0
        self.p.journal.clear()
        self.p.stats.clear()
        self.an_res = None
        self.say("hörprotokoll gelöscht")
        self.an_refresh(top=True)
