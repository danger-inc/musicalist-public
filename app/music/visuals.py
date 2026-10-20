# musicalist – Seite „visuals“: große Live-Visualisierung aus dem cava-Spektrum im -ist-Stil.
# Vier Modi, alles aus Zellen/Punkten wie der Rest der Suite (■-Regler, Braille-Cover, btop-Kästen):
#   orbit   – Cover als runder Halbton-Punktraster, ringsum strahlen Spektrum-Zellen, Spitzen als Punkte
#   säulen  – btop-Säulen aus ■-Zellen mit Spiegelung am Boden
#   linien  – gestaffelte Spektrum-Linien der letzten Sekunden („Unknown Pleasures“), vorne hell, hinten blass
#   matrix  – LED-Punktmatrix, Spitzen bleiben kurz stehen
# Gezeichnet wird nur, solange die Seite sichtbar ist (Tick-Callback an map/unmap). v = Modus wechseln,
# f = Vollbild ohne Rahmen (Esc zurück).
import math, time
from collections import deque

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Pango, PangoCairo

import tui
from tui import label, hbox, vbox

MODES = [("orbit", "orbit", "󰽥"), ("saeulen", "säulen", "󰐰"), ("linien", "linien", "󱑽"), ("matrix", "matrix", "󰝘")]

CSS = """
.vz-title { font-size: 26px; }
.vz-artist { font-size: 15px; color: @primary; }
.vz-album { color: alpha(@foreground, 0.55); }
.vz-time { color: alpha(@foreground, 0.55); font-size: 11px; }
.vz-info { padding: 0 4px 6px 4px; }
button.vz-mode { background: none; border: 1px solid transparent; box-shadow: none; padding: 2px 9px;
    border-radius: 4px; color: alpha(@foreground, 0.75); min-height: 0; min-width: 0; outline: none; }
button.vz-mode:hover { background-color: alpha(@primary, 0.12); color: @foreground; }
button.vz-mode:checked { background-color: alpha(@primary, 0.22); border-color: alpha(@primary, 0.55); color: @foreground; }
button.vz-mode .accent { color: @primary; }
.vz-hint { color: alpha(@foreground, 0.4); font-size: 11px; }
"""


def _mix(a, b, t):
    return (a.red + (b.red - a.red) * t, a.green + (b.green - a.green) * t, a.blue + (b.blue - a.blue) * t)


class Canvas(Gtk.DrawingArea):
    BINS = 64

    def __init__(self, owner):
        super().__init__(hexpand=True, vexpand=True)
        self.owner = owner
        self.mode = "orbit"
        self.vals = [0.0] * self.BINS        # geglättet, 0–1
        self.target = [0.0] * self.BINS
        self.peaks = [0.0] * self.BINS
        self.hold = [0.0] * self.BINS        # Haltezeit der Spitzen (matrix)
        self.trail = deque(maxlen=26)        # linien: frühere Spektren
        self.trail_t = 0.0
        self.bass = 0.0
        self.t0 = time.monotonic()
        self.last = self.t0
        self.last_draw = 0.0
        self.cover = None                    # n×n Helligkeiten 0–1 (Halbton) oder None
        self._tick = None
        self.set_draw_func(self._draw)
        self.connect("map", lambda *_: self._start())
        self.connect("unmap", lambda *_: self._stop())

    # ---------- Takt ----------
    def _start(self):
        if self._tick is None:
            self.last = time.monotonic()
            self._tick = self.add_tick_callback(self._on_tick)

    def _stop(self):
        if self._tick is not None:
            self.remove_tick_callback(self._tick)
            self._tick = None

    def set_vals(self, raw):
        n = self.BINS
        if not raw:
            self.target = [0.0] * n
            return
        m = len(raw)
        self.target = [min(1.0, raw[min(m - 1, int(i * m / n))] / 16.0) for i in range(n)]

    def _on_tick(self, _w, clock):
        now = time.monotonic()
        dt = min(0.1, now - self.last)
        self.last = now
        k_up, k_dn = 1 - math.exp(-dt * 28), 1 - math.exp(-dt * 7)
        quiet = True
        for i in range(self.BINS):
            v, t = self.vals[i], self.target[i]
            v += (t - v) * (k_up if t > v else k_dn)
            self.vals[i] = v
            if v > 0.01 or self.peaks[i] > 0.01:
                quiet = False
            if v >= self.peaks[i]:
                self.peaks[i], self.hold[i] = v, 0.35
            elif self.hold[i] > 0:
                self.hold[i] -= dt
            else:
                self.peaks[i] = max(0.0, self.peaks[i] - dt * 0.55)
        self.bass += (sum(self.vals[:6]) / 6 - self.bass) * (1 - math.exp(-dt * 12))
        if now - self.trail_t >= 0.07:
            self.trail_t = now
            self.trail.appendleft(list(self.vals))
        # Stille: nur noch langsam weiterdrehen (spart Strom), sonst jedes Bild
        if not quiet or now - self.last_draw > (0.1 if self.mode == "orbit" else 0.5):
            self.last_draw = now
            self.queue_draw()
        return GLib.SOURCE_CONTINUE

    # ---------- Zeichnen ----------
    def _draw(self, _a, cr, w, h):
        if w < 20 or h < 20:
            return
        c = tui.colors()
        col = {k: c.get(k) for k in ("primary", "secondary", "tertiary", "foreground", "background")}
        if any(v is None for v in col.values()):
            return
        getattr(self, "_draw_" + self.mode, self._draw_orbit)(cr, w, h, col)

    def _sym(self, i, n):
        """Spektrum gespiegelt: Bass in der Mitte, Höhen zu beiden Seiten (symmetrisch, ruhiger)."""
        half = n / 2
        d = abs(i + 0.5 - half) / half          # 0 Mitte … 1 Rand
        f = d * (self.BINS - 1)
        a = int(f)
        b = min(self.BINS - 1, a + 1)
        return self.vals[a] + (self.vals[b] - self.vals[a]) * (f - a), self.peaks[a]

    def _ring(self, i, n):
        """Für orbit: Bass oben und unten, Höhen links und rechts (zweifach symmetrisch)."""
        d = abs(math.sin(2 * math.pi * (i + 0.5) / n))
        f = d * (self.BINS - 1)
        a = int(f)
        b = min(self.BINS - 1, a + 1)
        return self.vals[a] + (self.vals[b] - self.vals[a]) * (f - a), self.peaks[a]

    def _draw_orbit(self, cr, w, h, col):
        p, ter, fg, sec = col["primary"], col["tertiary"], col["foreground"], col["secondary"]
        info_h = self.owner.info_height()
        avail_h = h - info_h - 46                    # oben Modusleiste, unten Titel frei lassen
        cx, cy = w / 2, 40 + avail_h / 2
        R0 = max(24.0, min(w / 2 - 12, avail_h / 2) / 2.62)
        R = R0 * (1 + 0.05 * self.bass)
        rot = (time.monotonic() - self.t0) * 0.06
        # Ringe im Hintergrund (btop-Raster)
        cr.set_line_width(1)
        cr.set_dash([2, 6])
        for k in range(1, 5):
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.07)
            cr.arc(cx, cy, R * (1.12 + 0.42 * k), 0, 2 * math.pi)
            cr.stroke()
        cr.set_dash([])
        # Cover als runder Halbton
        grid = self.cover
        n = len(grid) if grid else 30
        pitch = 2 * R / n
        for y in range(n):
            for x in range(n):
                dx, dy = (x + 0.5) * pitch - R, (y + 0.5) * pitch - R
                if dx * dx + dy * dy > R * R:
                    continue
                b = grid[y][x] if grid else 0.0
                if b > 0.04:
                    cr.set_source_rgba(p.red, p.green, p.blue, 0.35 + 0.65 * b)
                    rad = pitch * (0.16 + 0.32 * b)
                else:
                    cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.08)
                    rad = pitch * 0.14
                cr.arc(cx + dx, cy + dy, rad, 0, 2 * math.pi)
                cr.fill()
        if not grid:
            lay = self.create_pango_layout("♪")
            lay.set_font_description(Pango.FontDescription.from_string(f"{tui.FONT} Bold {int(R / 2.2)}"))
            tw, th = lay.get_pixel_size()
            cr.set_source_rgba(p.red, p.green, p.blue, 0.8)
            cr.move_to(cx - tw / 2, cy - th / 2)
            PangoCairo.show_layout(cr, lay)
        # Rand des Covers pulsiert mit dem Bass
        cr.set_line_width(1.5)
        cr.set_source_rgba(p.red, p.green, p.blue, 0.35 + 0.6 * self.bass)
        cr.arc(cx, cy, R * 1.05, 0, 2 * math.pi)
        cr.stroke()
        # Strahlen aus Zellen
        n_rays = 96
        s = max(2.5, R * 0.055)
        gap = s * 1.55
        r_in = R * 1.14
        reach = R * 1.45
        maxc = max(1, int(reach / gap))
        for i in range(n_rays):
            v, pk = self._ring(i, n_rays)
            a = -math.pi / 2 + (i + 0.5) / n_rays * 2 * math.pi + rot
            ca, sa = math.cos(a), math.sin(a)
            cells = int(v * maxc + 0.5)
            for j in range(cells):
                t = j / maxc
                rr = r_in + j * gap
                cr.set_source_rgba(*_mix(p, ter, t), 0.95 - 0.35 * t)
                cr.save()
                cr.translate(cx + ca * rr, cy + sa * rr)
                cr.rotate(a)
                cr.rectangle(-s / 2, -s / 2, s, s)
                cr.fill()
                cr.restore()
            if pk > 0.03:
                rr = r_in + pk * maxc * gap + gap * 0.3
                cr.set_source_rgba(sec.red, sec.green, sec.blue, 0.85)
                cr.arc(cx + ca * rr, cy + sa * rr, s * 0.32, 0, 2 * math.pi)
                cr.fill()
            elif cells == 0:
                cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.12)
                cr.arc(cx + ca * r_in, cy + sa * r_in, s * 0.25, 0, 2 * math.pi)
                cr.fill()

    def _draw_saeulen(self, cr, w, h, col):
        p, ter, fg = col["primary"], col["tertiary"], col["foreground"]
        info_h = self.owner.info_height()
        cell = 14 if w >= 700 else 10
        sq = cell - 4
        n = max(8, int((w - 24) // cell))
        x0 = (w - n * cell) / 2 + 2
        base = h - info_h - max(30.0, h * 0.16)
        top = 50
        rows = max(4, int((base - top) // cell))
        # Raster
        cr.set_line_width(1)
        cr.set_dash([2, 5])
        for k in (0.25, 0.5, 0.75, 1.0):
            y = base - rows * cell * k
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.06)
            cr.move_to(x0, y)
            cr.line_to(x0 + n * cell - 4, y)
            cr.stroke()
        cr.set_dash([])
        refl = max(0, int((h - base - 6) // cell))
        for i in range(n):
            v, pk = self._sym(i, n)
            lit = int(v * rows + 0.5)
            x = x0 + i * cell
            if lit == 0:
                cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.14)
                cr.rectangle(x, base - 3, sq, 2)
                cr.fill()
            for j in range(lit):
                t = j / rows
                cr.set_source_rgba(*_mix(p, ter, t * t), 1.0)
                cr.rectangle(x, base - (j + 1) * cell + 2, sq, sq)
                cr.fill()
            for j in range(min(lit, refl)):        # Spiegelung, nach unten ausblendend
                a = 0.16 * (1 - j / max(1, refl))
                cr.set_source_rgba(p.red, p.green, p.blue, a)
                cr.rectangle(x, base + j * cell + 4, sq, sq)
                cr.fill()
            pr = int(pk * rows + 0.5)
            if pr > lit:
                cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.85)
                cr.rectangle(x, base - pr * cell + 2, sq, max(2, sq / 3))
                cr.fill()

    def _draw_linien(self, cr, w, h, col):
        p, fg, bg = col["primary"], col["foreground"], col["background"]
        info_h = self.owner.info_height()
        lines = list(self.trail) or [self.vals]
        m = len(lines)
        margin = max(40.0, w * 0.14)
        span = w - 2 * margin
        pts = 72
        bottom = h - info_h - 30
        spacing = max(6.0, (bottom - 60) / (self.trail.maxlen + 4))
        amp = spacing * 5.5
        # hinten (alt, oben) zuerst, vorne (neu, unten) zuletzt – jede Linie verdeckt die dahinter
        for k in range(m - 1, -1, -1):
            vals = lines[k]
            y0 = bottom - k * spacing
            age = k / max(1, self.trail.maxlen - 1)
            cr.new_path()
            cr.move_to(margin, y0)
            for q in range(pts + 1):
                u = q / pts
                d = abs(u - 0.5) * 2                      # Mitte = Bass
                f = d * (len(vals) - 1)
                a = int(f)
                b = min(len(vals) - 1, a + 1)
                v = vals[a] + (vals[b] - vals[a]) * (f - a)
                env = math.exp(-((u - 0.5) / 0.26) ** 2)    # Ränder flach
                wob = 0.03 * math.sin(u * 37 + k * 1.7)     # leichte Unruhe, auch bei Stille
                cr.line_to(margin + u * span, y0 - (v * env + abs(wob) * env) * amp)
            cr.line_to(margin + span, y0)
            path = cr.copy_path()
            cr.set_source_rgba(bg.red, bg.green, bg.blue, 0.94)
            cr.fill()
            cr.append_path(path)
            cr.set_line_width(1.6 if k == 0 else 1.2)
            if k == 0:
                cr.set_source_rgba(p.red, p.green, p.blue, 1.0)
            else:
                cr.set_source_rgba(*_mix(p, fg, age * 0.6), max(0.12, 0.85 - age * 0.8))
            cr.stroke()

    def _draw_matrix(self, cr, w, h, col):
        p, ter, fg, sec = col["primary"], col["tertiary"], col["foreground"], col["secondary"]
        info_h = self.owner.info_height()
        pitch = 13 if w >= 700 else 10
        n = max(8, int((w - 30) // pitch))
        top, bottom = 52, h - info_h - 24
        rows = max(4, int((bottom - top) // pitch))
        x0 = (w - n * pitch) / 2 + pitch / 2
        r = pitch * 0.34
        for i in range(n):
            v, pk = self._sym(i, n)
            lit = int(v * rows + 0.5)
            pr = int(pk * rows + 0.5)
            x = x0 + i * pitch
            for j in range(rows):
                y = bottom - j * pitch - pitch / 2
                if j < lit:
                    t = j / rows
                    cr.set_source_rgba(*_mix(p, ter, t), 0.55 + 0.45 * (j + 1) / max(1, lit))
                    rad = r
                elif j == pr - 1 and pr > lit:
                    cr.set_source_rgba(sec.red, sec.green, sec.blue, 0.9)
                    rad = r
                else:
                    cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.06)
                    rad = r * 0.7
                cr.arc(x, y, rad, 0, 2 * math.pi)
                cr.fill()


class Visuals(Gtk.Overlay):
    """Seite mit Leinwand + Modusleiste oben + Titel unten. player: engine.Player, cover_grid(url, n) → Raster."""

    def __init__(self, player, cava, cover_grid, get_mode, set_mode, on_focus):
        super().__init__(hexpand=True, vexpand=True)
        self.p, self.cava, self.cover_grid = player, cava, cover_grid
        self.set_mode_pref, self.on_focus = set_mode, on_focus
        self.canvas = Canvas(self)
        self.set_child(self.canvas)
        self.url = None

        bar = hbox(spacing=4, halign=Gtk.Align.START, valign=Gtk.Align.START)
        bar.set_margin_top(6)
        self.mode_btns = {}
        group = None
        for mid, name, icon in MODES:
            b = Gtk.ToggleButton(focus_on_click=False, tooltip_text=f"{name} (v wechselt)")
            b.add_css_class("vz-mode")
            b.set_child(hbox(label(icon, "accent"), label(name), spacing=6))
            if group:
                b.set_group(group)
            group = group or b
            b.connect("toggled", lambda btn, m=mid: btn.get_active() and self.set_mode(m))
            bar.append(b)
            self.mode_btns[mid] = b
        self.add_overlay(bar)
        self.bar = bar
        full = tui.Button("󰊓 vollbild", lambda: self.on_focus(None), tooltip="Vollbild ohne Rahmen (f) – Esc zurück")
        full.set_halign(Gtk.Align.END)
        full.set_valign(Gtk.Align.START)
        full.set_margin_top(6)
        self.full_btn = full
        self.add_overlay(full)

        self.title = label("", "vz-title", ellipsize=True)
        self.artist = label("", "vz-artist", ellipsize=True)
        self.album = label("", "vz-album", ellipsize=True)
        self.meter = tui.Meter(1000, self._seek, mark=False)
        self.meter.set_size_request(220, -1)
        self.meter.set_hexpand(False)
        self.pos = label("0:00", "vz-time")
        self.dur = label("0:00", "vz-time")
        info = vbox(self.title, self.artist, self.album,
                    hbox(self.pos, self.meter, self.dur, spacing=8, halign=Gtk.Align.START), spacing=3)
        info.add_css_class("vz-info")
        info.set_halign(Gtk.Align.START)
        info.set_valign(Gtk.Align.END)
        self.info = info
        self.add_overlay(info)
        self.hint = label("v modus · f vollbild", "vz-hint")
        self.hint.set_halign(Gtk.Align.END)
        self.hint.set_valign(Gtk.Align.END)
        self.hint.set_margin_bottom(8)
        self.add_overlay(self.hint)

        self.connect("map", lambda *_: self.cava.want("visuals", True))
        self.connect("unmap", lambda *_: self.cava.want("visuals", False))
        self.set_mode(get_mode() if get_mode() in self.mode_btns else "orbit", save=False)

    def info_height(self):
        return self.info.get_height() + 12 if self.info.get_visible() else 0

    def set_mode(self, mode, save=True):
        if mode not in self.mode_btns:
            return
        self.canvas.mode = mode
        b = self.mode_btns[mode]
        if not b.get_active():
            b.set_active(True)
        if save:
            self.set_mode_pref(mode)
        self.canvas.queue_draw()

    def cycle(self):
        ids = [m[0] for m in MODES]
        self.set_mode(ids[(ids.index(self.canvas.mode) + 1) % len(ids)])

    def set_narrow(self, narrow):
        for mid, b in self.mode_btns.items():
            b.get_child().get_last_child().set_visible(not narrow or b.get_active())
        self.hint.set_visible(not narrow)
        self.full_btn.set_label("󰊓" if narrow else "󰊓 vollbild")
        self.title.remove_css_class("vz-title")
        self.title.add_css_class("np-title" if narrow else "vz-title")

    def on_spectrum(self, vals):
        if self.canvas.get_mapped():
            self.canvas.set_vals(vals)

    def _seek(self, v):
        if self.p.dur:
            self.p.seek(v / 1000 * self.p.dur)

    def update_track(self):
        t = self.p.current
        self.title.set_label(t["title"] if t else "nichts läuft")
        self.artist.set_label(t["artist"] if t else "⁶ suchen → titel wählen")
        self.album.set_label(t.get("album") or "" if t else "")
        self.album.set_visible(bool(t and t.get("album")))
        url = t.get("thumb") if t else None
        if url != self.url:
            self.url = url
            self.canvas.cover = None
            if url:
                def done(res, url=url):
                    if self.url == url and isinstance(res, list):
                        self.canvas.cover = res
                        self.canvas.queue_draw()
                tui.background(self.cover_grid, url, 34, done=done)
        self.update_pos()

    def update_pos(self):
        from engine import fmt
        p = self.p
        dur = p.dur or (p.current or {}).get("duration") or 0
        self.pos.set_label(fmt(p.pos))
        self.dur.set_label(fmt(dur))
        self.meter.set_value(int(p.pos / dur * 1000) if dur else 0)
