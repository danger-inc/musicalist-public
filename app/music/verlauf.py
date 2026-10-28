# musicalist – Hörverlauf als Leiste am LINKEN Fensterrand (wie die Apps-Leiste in scourge und „zuletzt“
# in notist): Maus an den Rand → gleitet herein, Verlassen/Esc/Klick daneben schließt; 󰐃 heftet sie als
# eigene Spalte an. Inhalt: Zeitachse – Uhrzeit │ Punkt auf der Schiene │ titel · künstler (einzeilig, damit
# viel draufpasst), nach Tagen gruppiert; läuft der oberste Titel gerade, pulsiert sein Punkt.
# Klick = abspielen, + / » beim Überfahren = anhängen / als nächstes. Daten: engine.History (history.json).
import datetime, math, time

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Pango

import tui
from tui import label, hbox, vbox


def _eco():
    """Energy-saving mode (istheme.eco): animations off."""
    try:
        import istheme
        return istheme.eco()
    except Exception:      # noqa: BLE001
        return False


EDGE = 6
WIDTH = 290
ROWS = 120
ROW_H = 22

CSS = """
.hv-drawer { background-color: @background; border: 1px solid alpha(@primary, 0.55); border-left: none;
    border-radius: 0 6px 6px 0; padding: 8px 4px 6px 6px; box-shadow: 6px 0 22px rgba(0,0,0,0.28); }
.hv-drawer.pinned { border: 1px solid alpha(@primary, 0.45); border-radius: 6px; box-shadow: none;
    background: none; margin: 0 10px 0 0; }
.hv-head { margin: 0 2px 4px 4px; }
.hv-head .hv-title { color: @primary; font-size: 13px; }
.hv-head .hv-count { color: alpha(@foreground, 0.45); font-size: 11px; }
.hv-day { color: @secondary; font-size: 10px; margin: 6px 0 1px 4px; }
.hv-day .hv-dash { color: alpha(@primary, 0.6); font-size: 10px; }
button.hv-item { background: none; border: 1px solid transparent; box-shadow: none; border-radius: 4px;
    padding: 0 4px 0 2px; min-height: 0; color: @foreground; outline: none; }
button.hv-item:hover, button.hv-item:focus-visible { border-color: alpha(@primary, 0.55); background-color: alpha(@primary, 0.10); }
button.hv-item .hv-time { color: alpha(@foreground, 0.42); font-size: 10px; }
button.hv-item .hv-title { font-size: 12px; }
button.hv-item .hv-artist { font-size: 11px; color: alpha(@foreground, 0.5); }
button.hv-item.now .hv-title, button.hv-item.now .hv-time { color: @primary; }
.hv-acts button.mini { padding: 0 4px; }
.hv-foot { color: alpha(@foreground, 0.38); font-size: 10px; margin: 4px 4px 0 4px; }
.hv-edge { background: none; }
"""


def day_name(ts):
    d = datetime.date.fromtimestamp(ts)
    today = datetime.date.today()
    if d == today:
        return "heute"
    if d == today - datetime.timedelta(days=1):
        return "gestern"
    wd = ("mo", "di", "mi", "do", "fr", "sa", "so")[d.weekday()]
    return f"{wd} {d.day}.{d.month}."


class Rail(Gtk.DrawingArea):
    """Stück Zeitachse: senkrechte Linie + Punkt. first/last kappen die Linie, now = pulsierender Punkt."""

    def __init__(self, first, last, now):
        super().__init__(content_width=12, content_height=ROW_H)
        self.first, self.last, self.now = first, last, now
        self.set_draw_func(self._draw)
        self._tick = None
        if now:
            self.connect("map", lambda *_: self._run(True))
            self.connect("unmap", lambda *_: self._run(False))

    def _pulse(self, *_):
        t = time.monotonic()
        if _eco() and t - getattr(self, "_pt", 0) < 0.5:     # energy-saving mode: dot pulses only twice per second
            return True
        self._pt = t
        self.queue_draw()
        return True

    def _run(self, on):
        if on and self._tick is None:
            self._tick = self.add_tick_callback(self._pulse)
        elif not on and self._tick is not None:
            self.remove_tick_callback(self._tick)
            self._tick = None

    def _draw(self, _a, cr, w, h):
        c = tui.colors()
        p, bg = c.get("primary"), c.get("background")
        if p is None:
            return
        cx, cy = w / 2 + 0.5, h / 2
        cr.set_line_width(1)
        cr.set_source_rgba(p.red, p.green, p.blue, 0.35)
        cr.move_to(cx, 0 if not self.first else cy)
        cr.line_to(cx, h if not self.last else cy)
        cr.stroke()
        if self.now:
            pulse = 0.5 + 0.5 * math.sin(time.monotonic() * 4)
            cr.set_source_rgba(p.red, p.green, p.blue, 0.28 * pulse)
            cr.arc(cx, cy, 5.5, 0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgba(p.red, p.green, p.blue, 1)
            cr.arc(cx, cy, 3, 0, 2 * math.pi)
            cr.fill()
        else:
            cr.arc(cx, cy, 2.4, 0, 2 * math.pi)
            if bg is not None:
                cr.set_source_rgba(bg.red, bg.green, bg.blue, 1)
                cr.fill_preserve()
            cr.set_source_rgba(p.red, p.green, p.blue, 0.8)
            cr.stroke()


class HistoryDrawer:
    """self.widget ersetzt den Inhalt (content) im Fenster: Box[ angeheftet | Overlay(content + Kante + Leiste) ]."""

    def __init__(self, win, content, player, is_pinned, set_pinned):
        self.win, self.p = win, player
        self.is_pinned, self.set_pinned = is_pinned, set_pinned
        self.narrow = False
        self.enabled = True          # Einstellung „hörverlauf führen“ – aus: keine Kante, keine Leiste
        self._close_id = None
        self.widget = Gtk.Box(vexpand=True, hexpand=True)
        self.pin_rev = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_RIGHT, transition_duration=160,
                                    reveal_child=False, hexpand=False)   # sonst erbt sie hexpand vom Inhalt
        self.pin_panel, self.pin_list = self._panel(pinned=True)
        self.pin_panel.set_margin_start(10)
        self.pin_panel.set_margin_bottom(8)
        self.pin_rev.set_child(self.pin_panel)
        self.widget.append(self.pin_rev)
        self.overlay = Gtk.Overlay(child=content, hexpand=True, vexpand=True)
        self.widget.append(self.overlay)

        self.edge = Gtk.Box(halign=Gtk.Align.START, valign=Gtk.Align.FILL, width_request=EDGE)
        self.edge.add_css_class("hv-edge")
        m = Gtk.EventControllerMotion()
        m.connect("enter", lambda *_: self.open())
        # über die Kante gleich aus dem Fenster hinaus (ohne die Leiste zu berühren) → wieder zu
        m.connect("leave", lambda *_: self.is_open() and self._leave())
        self.edge.add_controller(m)
        self.overlay.add_overlay(self.edge)

        self.rev = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_RIGHT, transition_duration=160,
                                halign=Gtk.Align.START, valign=Gtk.Align.FILL, reveal_child=False,
                                margin_top=2, margin_bottom=8)
        self.rev.set_can_target(False)
        self.panel, self.list = self._panel(pinned=False)
        pm = Gtk.EventControllerMotion()
        pm.connect("leave", lambda *_: self._leave())
        pm.connect("enter", lambda *_: self._cancel_close())
        self.panel.add_controller(pm)
        self.rev.set_child(self.panel)
        self.overlay.add_overlay(self.rev)

        click = Gtk.GestureClick(button=0)
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click.connect("pressed", self._outside_click)
        self.overlay.add_controller(click)
        player.listeners.append(self._on_player)
        self._apply(animate=False)

    def _panel(self, pinned):
        panel = vbox(spacing=0)
        panel.add_css_class("hv-drawer")
        panel.set_size_request(WIDTH, -1)
        if pinned:
            panel.add_css_class("pinned")
        head = hbox(spacing=6)
        head.add_css_class("hv-head")
        head.append(label("󰋚  hörverlauf", "hv-title"))
        count = label("", "hv-count", hexpand=True)
        head.append(count)
        pin = Gtk.Button(label="󰐄" if pinned else "󰐃", tooltip_text="lösen" if pinned else "anheften",
                         focus_on_click=False)
        pin.add_css_class("mini")
        pin.connect("clicked", lambda *_: self.pin(not self.is_pinned()))
        head.append(pin)
        panel.append(head)
        lst = vbox(spacing=0)
        sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True, child=lst)
        panel.append(sc)
        foot = hbox(label("klick spielt · h öffnet/schließt", "hv-foot", hexpand=True, ellipsize=True), spacing=4)
        clr = Gtk.Button(label="leeren", tooltip_text="hörverlauf löschen", focus_on_click=False)
        clr.add_css_class("mini")
        clr.connect("clicked", lambda *_: self._clear())
        foot.append(clr)
        panel.append(foot)
        lst.count = count
        return panel, lst

    # ---------- offen / zu ----------
    def is_open(self):
        return self.rev.get_reveal_child()

    def set_enabled(self, on):
        self.enabled = bool(on)
        if not on:
            self.close()
        self._apply(animate=False)

    def open(self):
        self._cancel_close()
        if not self.enabled:
            return
        if self.is_pinned() and not self.narrow:
            return
        if not self.is_open():
            self._fill(self.list)
            self.rev.set_can_target(True)
            self.rev.set_reveal_child(True)

    def close(self):
        self._cancel_close()
        if self.is_open():
            self.rev.set_reveal_child(False)
            self.rev.set_can_target(False)

    def toggle(self):
        if self.is_pinned() and not self.narrow:
            self.pin(False)
        elif self.is_open():
            self.close()
        else:
            self.open()

    def _leave(self):
        self._cancel_close()
        self._close_id = GLib.timeout_add(260, self._close_now)

    def _close_now(self):
        self._close_id = None
        self.close()
        return False

    def _cancel_close(self):
        if self._close_id:
            GLib.source_remove(self._close_id)
            self._close_id = None

    def _outside_click(self, g, n, x, y):
        if self.is_open() and x > self.panel.get_width() + 2:   # Leiste liegt links bündig
            self.close()

    # ---------- angeheftet ----------
    def pin(self, on):
        self.close()
        self.set_pinned(on)
        self._apply()

    def set_narrow(self, on):
        if on != self.narrow:
            self.narrow = on
            self._apply()

    def _apply(self, animate=True):
        show = self.is_pinned() and not self.narrow and self.enabled
        self.pin_rev.set_transition_duration(160 if animate else 0)
        if show:
            self._fill(self.pin_list)
        self.pin_rev.set_reveal_child(show)
        self.edge.set_visible(not show and self.enabled)

    # ---------- Inhalt ----------
    def _on_player(self, what):
        if what in ("history", "track", "state"):
            if self.is_open():
                self._fill(self.list)
            if self.pin_rev.get_reveal_child():
                self._fill(self.pin_list)

    def _remove(self, it):
        items = self.p.history.items
        for i, x in enumerate(items):
            if x is it:
                self.p.history.remove(i)
                break
        self._on_player("history")

    def _clear(self):
        self.p.history.clear()
        self._on_player("history")

    def _fill(self, lst):
        tui.clear(lst)
        items = self.p.history.items[:ROWS]
        n = len(self.p.history.items)
        lst.count.set_label(f"{n} titel" if n else "")
        if not items:
            lst.append(label("noch nichts gehört – titel landen\nhier nach 5 s wiedergabe.", "hv-foot",
                             xalign=0, wrap=True))
            return
        cur = self.p.current
        playing = bool(cur and self.p.started and not self.p.paused and items[0]["videoId"] == cur.get("videoId"))
        day = None
        first = True
        for i, it in enumerate(items):
            dn = day_name(it.get("at", 0))
            if dn != day:
                day = dn
                first = True
                head = hbox(label("──", "hv-dash"), label(dn), spacing=6)
                head.add_css_class("hv-day")
                lst.append(head)
            nxt = items[i + 1] if i + 1 < len(items) else None
            last = nxt is None or day_name(nxt.get("at", 0)) != dn
            lst.append(self._row(it, first=first, last=last, now=(i == 0 and playing)))
            first = False

    def _row(self, it, first, last, now):
        t = {k: it.get(k) for k in ("videoId", "title", "artist", "album", "duration", "thumb")}
        b = Gtk.Button(focus_on_click=False, hexpand=True)
        b.add_css_class("hv-item")
        if now:
            b.add_css_class("now")
        tl = label("jetzt" if now else time.strftime("%H:%M", time.localtime(it.get("at", 0))), "hv-time")
        tl.set_width_chars(5)
        tl.set_xalign(1)
        title = label(t["title"] or "?", "hv-title")
        title.set_ellipsize(Pango.EllipsizeMode.END)
        artist = label(t["artist"] or "", "hv-artist")
        artist.set_ellipsize(Pango.EllipsizeMode.END)
        artist.set_width_chars(4)
        artist.set_hexpand(True)
        text = hbox(title, artist, spacing=6, hexpand=True)
        text.set_valign(Gtk.Align.CENTER)
        b.set_child(hbox(tl, Rail(first, last, now), text, spacing=5))
        b.set_tooltip_text(" · ".join(x for x in (t["title"], t["artist"], t.get("album")) if x))
        p = self.p
        b.connect("clicked", lambda *_: (p.play_now(t), p.start_radio(t) if p.autoplay else None))
        acts = hbox(spacing=0, valign=Gtk.Align.CENTER)
        acts.add_css_class("hv-acts")
        for glyph, tip, fn in (("+", "an warteschlange anhängen", lambda: p.add(t)),
                               ("»", "als nächstes spielen", lambda: p.add(t, next_=True))):
            mb = Gtk.Button(label=glyph, tooltip_text=tip, focus_on_click=False)
            mb.add_css_class("mini")
            mb.connect("clicked", lambda _b, f=fn: f())
            acts.append(mb)
        acts.set_visible(False)
        row = hbox(b, acts, spacing=0)
        songs = getattr(self.win, "songs", None)
        if songs is not None:          # Rechtsklick-Menü wie überall + Vorwärmen beim Überfahren
            songs.attach(row, t, lambda: [("✕", "aus dem verlauf entfernen", lambda: self._remove(it), True)])
        mo = Gtk.EventControllerMotion()
        mo.connect("enter", lambda c, x, y: c.get_widget().get_last_child().set_visible(True))
        mo.connect("leave", lambda c: c.get_widget().get_last_child().set_visible(False))
        row.add_controller(mo)
        return row
