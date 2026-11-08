# musicalist – Fernseher-Modus: dieselbe Oberfläche wie Seite „jetzt“, nur groß genug für die Couch (Vollbild am PC,
# Knopf 󰔂 oben rechts oder Taste t). Alle Funktionen sind da: gefällt mir / gefällt mir nicht, Playlist, Radio,
# Spulen, Lautstärke, Sleep-Timer, Klang, Autoplay, mitlaufende Lyrics, „als nächstes“, andere Quellen, Spektrum.
# Die Seite hat keinen eigenen Zustand – MusicWindow ruft refresh_*() auf, wenn sich etwas ändert.
import time

from gi.repository import Gdk, GLib, Gtk, Pango

import engine
import sources
import tui
from tui import label, hbox, vbox
from engine import fmt
from rows import track_row
from widgets import DotCover

Panel_HEAD = tui.Panel.H
LYR_BEFORE, LYR_AFTER = 1, 3          # Zeilen vor / nach der aktuellen Lyrics-Zeile (höchstens; bei wenig Höhe weniger)


class TvCover(DotCover):
    """Das Punkt-Cover der App, nur feiner gerastert – auf dem Fernseher ist es groß."""
    DOTS = 60

    def set_side(self, px):
        self.set_content_width(px)
        self.set_content_height(px)
        self.queue_draw()


def css(s):
    """CSS für Skalierung s (1.0 = Fenster ab ~800 px Höhe, wächst mit der Auflösung)."""
    f = lambda px: f"{round(px * s)}px"
    return f"""
.tv .tv-brand {{ font-size: {f(16)}; font-weight: bold; color: @primary; }}
.tv .tv-clock {{ font-size: {f(16)}; color: alpha(@foreground, 0.7); }}
.tv .tv-title {{ font-size: {f(36)}; font-weight: bold; }}
.tv .tv-artist {{ font-size: {f(22)}; color: @primary; }}
.tv .tv-album {{ font-size: {f(16)}; color: alpha(@foreground, 0.65); }}
.tv .tv-info {{ font-size: {f(13)}; color: alpha(@foreground, 0.5); }}
.tv button.bx {{ background: @background; border: 1px solid alpha(@primary, 0.6); border-radius: 6px; padding: 0; box-shadow: none; }}
.tv button.bx label {{ color: @foreground; }}
.tv button.bx.big {{ min-height: {f(60)}; }}
.tv button.bx.big label {{ font-size: {f(32)}; }}
.tv button.bx.small {{ min-height: {f(46)}; min-width: 0; }}
.tv button.bx.small label {{ font-size: {f(20)}; }}
.tv button.bx:hover {{ border-color: @primary; background: alpha(@primary, 0.14); }}
.tv button.bx.fill, .tv button.bx.on {{ background: @primary; border-color: @primary; }}
.tv button.bx.fill label, .tv button.bx.on label {{ color: @on_primary; }}
.tv button.bx:disabled {{ opacity: 0.45; }}
.tv button.tbtn {{ font-size: {f(15)}; padding: {f(5)} {f(14)}; }}
.tv button.tbtn label {{ font-size: {f(15)}; }}
.tv .check label {{ font-size: {f(15)}; }}
.tv .mono-pct {{ font-size: {f(15)}; }}
.tv .tvlyric {{ font-size: {f(20)}; color: alpha(@foreground, 0.42); padding: {f(3)} {f(8)}; }}
.tv .tvlyric.now {{ font-size: {f(32)}; font-weight: bold; color: @primary; }}
.tv .tvlyric.msg {{ font-size: {f(16)}; font-style: italic; }}
.tv .trk-title {{ font-size: {f(18)}; }}
.tv .trk-mark {{ font-size: {f(18)}; }}
.tv .row .dim, .tv .row .artlink label {{ font-size: {f(16)}; }}
.tv .pbody .dim {{ font-size: {f(14)}; }}
.tv .row .dim {{ font-size: {f(18)}; }}
.tv .tv-msg {{ font-size: {f(15)}; color: @primary; }}
.tv .tv-msg.err {{ color: @tertiary; }}
"""


class TvPage(Gtk.Box):
    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.w, self.p = win, win.p
        self.add_css_class("tv")
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self._scale, self._css = 0.0, Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self._css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_USER + 2)
        self._lyr_key = None
        self.lyr_after = LYR_AFTER

        # --- Kopfzeile des Modus: Marke, Uhr, Ausstieg ---
        self.clock = label("", "tv-clock")
        exit_btn = tui.Button("✕ fernseher beenden", lambda: win.tv_mode(False), tooltip="Zurück zum Fenster (t · Esc)")
        self.msg = label("", "tv-msg", ellipsize=True)
        self._msg_id = None
        self.vol = tui.Meter(100, self.p.set_volume)
        self.vol.set_size_request(200, -1)
        self.vol.set_hexpand(False)
        self.vol.set_content_height(22)
        self.vol_lbl = label("", "mono-pct", xalign=1)
        self.vol_lbl.set_width_chars(4)
        vol = hbox(label("󰕾", "accent"), self.vol, self.vol_lbl, spacing=8)
        self.edit_btn = tui.Button("󰏫", lambda: self.bar_edit(), tooltip="Leiste mit den Symbol-Kästen bearbeiten (auch: Rechtsklick auf die Leiste)")
        self.jam_btn = tui.Button("󰀂 marmelade", self.jam_open, tooltip="Marmelade: gemeinsam Musik hören – starten, Code/QR zeigen")
        self._jam_pop = None
        if self.p.jam is not None:
            self.p.jam.listeners.append(lambda *_: self.refresh_jam())
        self.vol_box = vol
        top = hbox(label("󰝚 musicalist", "tv-brand"), label("󰔂 fernseher", "dim"), label("", hexpand=True),
                   self.msg, self.edit_btn, self.jam_btn, self.clock, exit_btn, spacing=14)
        self.append(top)

        # --- läuft: Cover links, Titel + Knöpfe rechts ---
        self.cover = TvCover(260)
        self.cover.set_valign(Gtk.Align.START)
        self.title = label("", "tv-title", wrap=True)
        self.title.set_lines(2)
        self.title.set_ellipsize(Pango.EllipsizeMode.END)
        self.artist = label("", "tv-artist", ellipsize=True)
        self.artist.set_cursor_from_name("pointer")
        ac = Gtk.GestureClick()
        ac.connect("released", lambda *_: self._open_artist())
        self.artist.add_controller(ac)
        self.album = label("", "tv-album", ellipsize=True)
        self.info = label("", "tv-info", ellipsize=True)

        def bx(glyph, cb, tip, big=False):
            """Kasten wie in der Handy-App (BoxBtn): umrandet, abgerundet, nur Symbol; aktiv = gefüllt."""
            btn = Gtk.Button(label=glyph, hexpand=True, focus_on_click=False, tooltip_text=tip)
            btn.add_css_class("bx")
            btn.add_css_class("big" if big else "small")
            btn.connect("clicked", lambda *_: cb())
            return btn
        from widgets import pixel_on, set_pixel, PIXEL_LISTENERS
        self.prev_btn = bx("󰒮", self.p.prev, "Zurück (p)", True)
        self.play_btn = bx("󰐊", self.p.toggle, "Play/Pause (Leertaste)", True)
        self.play_btn.add_css_class("fill")
        self.next_btn = bx("󰒭", lambda: self.p.next(), "Weiter (n)", True)
        self.shuffle_btn = bx("󰒝", self.p.shuffle_queue, "Warteschlange mischen")
        self.repeat_btn = bx("󰑗", self.p.cycle_repeat, "Wiederholen: aus / alle / eins")
        self.like_btn = bx("󰋕", lambda: self.p.like(), "Gefällt mir (l)")
        self.dislike_btn = bx("󰔒", lambda: self.p.dislike(), "Gefällt mir nicht (d)")
        self.pl_btn = bx("󰐒", lambda: win.songs.picker(self.pl_btn, [self.p.current]) if self.p.current else None,
                         "Zu einer Playlist hinzufügen (a)")
        self.radio_btn = bx("󰐹", lambda: (self.p.start_radio(), win.say("radio startet …")), "Ähnliche Titel als Warteschlange")
        self.web_btn = bx("↗", win.open_web, "In YouTube Music öffnen")
        self.menu_btn = bx("⋮", lambda: self.p.current and win.songs.menu(self.menu_btn, 0, self.menu_btn.get_height(), self.p.current),
                           "Alles zu diesem Titel")
        self.pixel_btn = bx("󱗼", lambda: set_pixel(not pixel_on()), "Titelbilder: Raster / Foto – Rechtsklick: einstellen")
        win.attach_pixel_menu(self.pixel_btn)
        self.sleep_btn = bx("󰒲", lambda: win.sleep_menu(self.sleep_btn), "Sleep-Timer")
        self.sound_btn = bx("󰓃", lambda: win.sound_menu(self.sound_btn), "Klang: Equalizer und Überblendung")
        self.auto_btn = bx("󰑐", self._toggle_autoplay, "Autoplay: am Ende ähnliche Titel weiterspielen")
        self.artist_btn = bx("󰠃", self._open_artist, "Künstlerseite")
        self.album_btn = bx("󰀥", self._open_album, "Album öffnen")
        self.rec_btn = bx("󰡉", self._recommend, "An alle Freunde empfehlen")
        self.bar_all = {
            "shuffle": (self.shuffle_btn, "󰒝 mischen"), "repeat": (self.repeat_btn, "󰑗 wiederholen"),
            "like": (self.like_btn, "󰋑 gefällt mir"), "dislike": (self.dislike_btn, "󰔒 gefällt mir nicht"),
            "playlist": (self.pl_btn, "󰐒 playlist"), "radio": (self.radio_btn, "󰐹 radio"),
            "browser": (self.web_btn, "↗ browser"), "menu": (self.menu_btn, "⋮ titel-menü"),
            "pixel": (self.pixel_btn, "󱗼 raster / foto"), "sleep": (self.sleep_btn, "󰒲 schlaf-timer"),
            "mixer": (self.sound_btn, "󰓃 klang / mixer"), "autoplay": (self.auto_btn, "󰑐 autoplay"),
            "artist": (self.artist_btn, "󰠃 künstler"), "album": (self.album_btn, "󰀥 album"),
            "recommend": (self.rec_btn, "󰡉 empfehlen"),
        }

        def sync_pix():
            self.pixel_btn.set_label("󱗼" if pixel_on() else "󰋩")
            (self.pixel_btn.add_css_class if pixel_on() else self.pixel_btn.remove_css_class)("on")
        PIXEL_LISTENERS.append(sync_pix)
        sync_pix()

        self.pos_lbl = label("0:00", "mono-pct")
        self.dur_lbl = label("0:00", "mono-pct", xalign=1)
        self.seek = tui.Meter(1000, win.on_seek, mark=False, scroll="h")
        self.seek.set_content_height(26)
        seek_row = hbox(self.pos_lbl, self.seek, self.dur_lbl, spacing=12, hexpand=True)
        big = hbox(self.prev_btn, self.play_btn, self.next_btn, spacing=10, homogeneous=True, hexpand=True)
        self.small = hbox(spacing=8, homogeneous=True, hexpand=True)
        small = self.small
        rc2 = Gtk.GestureClick(button=3)                 # Rechtsklick auf die Leiste = bearbeiten
        rc2.connect("pressed", lambda *_: self.bar_edit())
        small.add_controller(rc2)
        self.apply_bar()

        side = vbox(self.title, self.artist, self.album, self.info, spacing=6, hexpand=True)
        side.set_valign(Gtk.Align.CENTER)
        self.vol_box.set_valign(Gtk.Align.START)
        self.vol_box.set_halign(Gtk.Align.END)
        now_row = hbox(self.cover, side, self.vol_box, spacing=26)
        now_row.set_margin_bottom(4)
        self.now_panel = tui.Panel("󰝚 läuft", vbox(now_row, seek_row, big, small, spacing=12))
        rc = Gtk.GestureClick(button=3)           # Rechtsklick auf „läuft“ = Menü zum Titel
        rc.connect("pressed", lambda g, n, x, y: self.p.current and win.songs.menu(now_row, x, y, self.p.current))
        now_row.add_controller(rc)
        self.append(self.now_panel)

        # --- unten: Lyrics | als nächstes (+ andere Quellen) ---
        self.lyr_lines = [label("", "tvlyric", xalign=0.5, wrap=True) for _ in range(LYR_BEFORE + 1 + LYR_AFTER)]
        for l in self.lyr_lines:
            l.set_justify(Gtk.Justification.CENTER)
            l.set_visible(False)
        self.lyr_src = label("", "dim", xalign=0.5)
        self.lyr_panel = tui.Panel("󰍰 lyrics", vbox(*self.lyr_lines, self.lyr_src, spacing=2, valign=Gtk.Align.CENTER, vexpand=True))
        self.lyr_panel.set_hexpand(True)
        self.lyr_panel.set_vexpand(True)
        self.upnext = vbox(spacing=0)
        self.upnext_panel = tui.Panel("als nächstes", self.upnext)
        self.src_list = sources.SourceList(win.srcs, limit=3)
        self.src_panel = tui.Panel("󰓃 andere quellen", self.src_list)
        self.src_panel.set_visible(bool(win.srcs.items))
        self.src_list.on_change = lambda items: self.src_panel.set_visible(bool(items))
        right = vbox(self.upnext_panel, self.src_panel, spacing=10, hexpand=True)
        right.set_vexpand(True)
        self.upnext_panel.set_vexpand(True)
        self.upnext_panel.body.set_vexpand(True)       # Kasten bis ganz unten, genau so hoch wie „lyrics“
        self.lyr_panel.body.set_vexpand(True)

        def clip(w):
            # Mindesthöhe klein halten: sonst bestimmt der Inhalt die Fensterhöhe (und das Fenster passt nie auf 720 p)
            return Gtk.ScrolledWindow(child=w, hscrollbar_policy=Gtk.PolicyType.NEVER, vscrollbar_policy=Gtk.PolicyType.NEVER,
                                      min_content_height=40, propagate_natural_height=False, vexpand=True, hexpand=True)
        self.lyr_clip, self.right_clip = clip(self.lyr_panel), clip(right)
        # Wie viel hineinpasst, richtet sich nach der Höhe, die der Platz wirklich hat (nicht nach der Fensterhöhe)
        self.lyr_clip.get_vadjustment().connect("notify::page-size", self._fit_lyrics)
        self.right_clip.get_vadjustment().connect("notify::page-size", self._fit_upnext)
        self.mid = hbox(self.lyr_clip, self.right_clip, spacing=14, homogeneous=True)
        self.mid.set_vexpand(True)
        self.append(self.mid)

        # --- Spektrum über die ganze Breite ---
        from ui import Spectrum
        self.spec = Spectrum(rows=3, cell=11, height=72)
        self.spec.set_margin_top(2)
        self.append(self.spec)

        self.refresh_jam()
        self.resize(1280, 800)

    # ---------- Größe ----------
    def resize(self, width, height):
        s = max(1.0, round(min(height / 800, width / 1280) * 8) / 8)
        if s != self._scale:
            self._scale = s
            self._css.load_from_string(css(s))
        side = int(max(120, min(height * 0.27, width * 0.2)))
        self.cover.set_side(side)
        self.spec.set_margin_top(2)
        self.spec.set_height(int(max(48, min(height * 0.09, 140))))

    def _fit_lyrics(self, adj, _p=None):
        h = adj.get_page_size() / max(self._scale, 1.0)
        after = 3 if h >= 270 else 2 if h >= 215 else 1 if h >= 175 else 0
        self.lyr_src.set_visible(after >= 2)
        if after != self.lyr_after:
            self.lyr_after, self._lyr_key = after, None
            self.refresh_lyrics(force=True)

    def _fit_upnext(self, adj, _p=None):
        page = adj.get_page_size()
        first = self.upnext.get_first_child()
        rowh = first.measure(Gtk.Orientation.VERTICAL, -1)[1] if first is not None else 42 * self._scale
        used = Panel_HEAD + 14 + (self.src_panel.get_height() + 10 if self.src_panel.get_visible() else 0)
        n = int(max(1, min(10, (page - used - 8) // max(rowh + 1, 20))))
        if n != getattr(self, "upnext_n", 0):
            self.upnext_n = n
            self.refresh_queue()

    # ---------- Zustand ----------
    def refresh_all(self):
        self.refresh_track()
        self.refresh_state()
        self.refresh_pos()
        self.refresh_queue()
        self.refresh_sleep()
        self.refresh_clock()

    # ---------- Leiste bearbeiten ----------
    BAR_DEFAULT = ["shuffle", "repeat", "like", "dislike", "playlist", "radio", "browser", "menu", "pixel"]

    def bar_ids(self):
        cur = engine.setting("tv_bar")
        return [x for x in (cur if isinstance(cur, list) else self.BAR_DEFAULT) if x in self.bar_all]

    def apply_bar(self):
        child = self.small.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.small.remove(child)
            child = nxt
        for k in self.bar_ids():
            self.small.append(self.bar_all[k][0])
        if hasattr(self, "spec"):                       # erst nach dem Aufbau der Seite
            self.refresh_state()
            self.refresh_track()
            self.refresh_sleep()

    def bar_edit(self):
        pop = self.w.songs._popover(self.edit_btn)
        pop.set_position(Gtk.PositionType.BOTTOM)
        holder = vbox(spacing=2)
        for m in ("set_margin_top", "set_margin_bottom", "set_margin_start", "set_margin_end"):
            getattr(holder, m)(10)
        hh = int(max(240, min(560, self.w.get_height() - 140)))
        pop.set_child(Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, min_content_height=hh, max_content_height=hh,
                                         min_content_width=300, child=holder))

        def save(cur):
            engine.set_setting("tv_bar", cur)
            self.apply_bar()
            fill()

        def toggle(k, on):
            cur = self.bar_ids()
            if on and k not in cur:
                cur.append(k)
            if not on and k in cur:
                cur.remove(k)
            save(cur)

        def move(k, d):
            cur = self.bar_ids()
            i = cur.index(k)
            j = i + d
            if 0 <= j < len(cur):
                cur.insert(j, cur.pop(i))
                save(cur)

        def fill():
            tui.clear(holder)
            holder.append(label("󰏫  leiste bearbeiten", "kp-head"))
            holder.append(label("haken = anzeigen, ← → ordnen", "kp-sub"))
            bar = self.bar_ids()
            for k in bar + [x for x in self.bar_all if x not in bar]:
                on = k in bar
                row = hbox(tui.Check(self.bar_all[k][1], on, lambda v, k=k: toggle(k, v)), label("", hexpand=True), spacing=6)
                if on:
                    row.append(tui.Button("←", lambda k=k: move(k, -1)))
                    row.append(tui.Button("→", lambda k=k: move(k, 1)))
                holder.append(row)
            holder.append(tui.Button("zurücksetzen", lambda: (engine.set_setting("tv_bar", None), self.apply_bar(), fill()), danger=True))
        fill()
        pop.popup()

    def _toggle_autoplay(self):
        self.w.set_autoplay(not self.p.autoplay)
        self.refresh_state()

    def _open_album(self):
        t = self.p.current
        if t and t.get("albumId"):
            self.w.tv_mode(False)
            self.w.open_detail("album", t["albumId"])
        else:
            self.w.say("zu diesem titel ist kein album bekannt")

    def _recommend(self):
        t = self.p.current
        fr = getattr(self.p, "friends", None)
        if t and fr and fr.recommend(t):
            self.w.say("freunde sehen: empfohlen")

    # ---------- Marmelade (Jam) ----------
    def refresh_jam(self):
        j = self.p.jam
        if j is None:
            self.jam_btn.set_visible(False)
            return
        if j.hosting:
            txt = f"󰀂 {j.code[:3]} {j.code[3:]}" + (f" · {len(j.guests)}" if j.guests else "")
        elif j.joined is not None:
            txt = "󰀂 verbunden"
        else:
            txt = "󰀂 marmelade"
        self.jam_btn.set_label(txt)
        (self.jam_btn.add_css_class if (j.hosting or j.joined is not None) else self.jam_btn.remove_css_class)("accent")
        if self._jam_pop is not None and self._jam_pop.get_visible():
            self._fill_jam(self._jam_pop)

    def jam_open(self):
        j = self.p.jam
        if j is None:
            return
        if not j.hosting and j.joined is None and not j.start():
            self.w.say(f"marmelade startet nicht: {j.error}", error=True)
            return
        pop = self.w.songs._popover(self.jam_btn)
        pop.set_position(Gtk.PositionType.BOTTOM)
        self._jam_pop = pop
        self._fill_jam(pop)
        self.refresh_jam()
        pop.popup()

    def _fill_jam(self, pop):
        j = self.p.jam
        jm = __import__("jam")
        box = vbox(spacing=10)
        for m in ("set_margin_top", "set_margin_bottom", "set_margin_start", "set_margin_end"):
            getattr(box, m)(12)
        pop.set_child(box)
        if j.hosting:
            box.append(label("󰀂  " + jm.jam_title(), "kp-head"))
            big = label("")
            big.set_markup(f"<span size='300%' weight='bold'>{j.code[:3]} {j.code[3:]}</span>")
            big.set_xalign(0.5)
            box.append(label("code – in der app (handy oder pc): marmelade beitreten", "dim", xalign=0.5))
            box.append(big)
            url = j.url() if j.lan_ok else None
            qr = jm.qr_matrix(url) if url else None
            if qr:
                n = len(qr)
                cell = max(4, 240 // n)
                area = Gtk.DrawingArea(content_width=n * cell, content_height=n * cell, halign=Gtk.Align.CENTER)
                fg, bg = tui.colors().get("on_background") or tui.colors().get("foreground"), tui.colors().get("background")

                def draw(_a, cr, _w, _h, m=qr, cell=cell):
                    cr.set_source_rgb(bg.red, bg.green, bg.blue) if bg else cr.set_source_rgb(1, 1, 1)
                    cr.paint()
                    cr.set_source_rgb(fg.red, fg.green, fg.blue) if fg else cr.set_source_rgb(0, 0, 0)
                    for y, line in enumerate(m):
                        for x, on in enumerate(line):
                            if on:
                                cr.rectangle(x * cell, y * cell, cell, cell)
                    cr.fill()
                area.set_draw_func(draw)
                box.append(area)
                box.append(label("qr-code: browser ohne app, nur im selben wlan", "dim", xalign=0.5))
            box.append(label("internet: " + (j.net_status or "startet …"), "accent" if j.net_status == "verbunden" else "dim", xalign=0.5))
            import time as _t
            for key, k in list(j.knocks.items()):
                if k["state"] == "wait" and _t.time() - k["at"] <= 120:
                    box.append(hbox(label("󰌹 " + k["name"] + " möchte beitreten", hexpand=True),
                                    tui.Button("reinlassen", lambda key=key: (j.answer_knock(key, True), self.refresh_jam())),
                                    tui.Button("✕", lambda key=key: (j.answer_knock(key, False), self.refresh_jam()), danger=True)))
            names = [g.get("name") or "gast" for g in j.guests.values()]
            box.append(label(("gäste: " + ", ".join(names)) if names else "noch keine gäste", "dim", xalign=0.5, wrap=True))
            box.append(tui.Button("marmelade beenden", lambda: (j.stop(), pop.popdown(), self.refresh_jam(), self.w.say("marmelade beendet")),
                                  danger=True))
        else:
            box.append(label("󰀂  du bist in einer marmelade", "kp-head"))
            box.append(tui.Button("verlassen", lambda: (j.leave(), pop.popdown(), self.refresh_jam()), danger=True))

    def toast(self, text, error=False, seconds=6):
        """Meldungen der Statuszeile (Like, Playlist, Fehler …) – die Statuszeile ist im Fernseher-Modus weg."""
        self.msg.set_label(("✗ " if error else "▸ ") + str(text).strip().replace("\n", " "))
        (self.msg.add_css_class if error else self.msg.remove_css_class)("err")
        if self._msg_id:
            GLib.source_remove(self._msg_id)
        self._msg_id = GLib.timeout_add_seconds(max(seconds, 20) if error else seconds, self._msg_clear)

    def _msg_clear(self):
        self.msg.set_label("")
        self._msg_id = None
        return False

    def refresh_clock(self):
        self.clock.set_label(time.strftime("%H:%M"))
        return True

    def _open_artist(self):
        if self.p.current:
            self.w.open_artist(self.p.current)

    def refresh_track(self):
        t = self.p.current
        self.cover.show(t["thumb"] if t else None)
        self.title.set_label(t["title"] if t else "nichts läuft")
        self.artist.set_label(t["artist"] if t else "")
        self.album.set_label(t["album"] if t and t.get("album") else "")
        liked = bool(t and t.get("liked"))
        self.like_btn.set_label("󰋑" if liked else "󰋕")
        (self.like_btn.add_css_class if liked else self.like_btn.remove_css_class)("on")
        dis = bool(t and engine.is_disliked(t.get("videoId")))
        self.dislike_btn.set_label("󰔑" if dis else "󰔒")
        (self.dislike_btn.add_css_class if dis else self.dislike_btn.remove_css_class)("on")
        guest = self.p._mirror is not None
        for b in (self.like_btn, self.dislike_btn, self.pl_btn, self.radio_btn, self.web_btn, self.menu_btn):
            b.set_sensitive(t is not None and not (guest and b is not self.menu_btn))
        self.refresh_queue()
        self.refresh_lyrics(force=True)

    def refresh_state(self):
        p = self.p
        self.play_btn.set_label("󰏤" if not p.paused and p.started else "󰐊")
        self.repeat_btn.set_label({"aus": "󰑗", "alle": "󰑖", "eins": "󰑘"}[p.repeat])
        (self.repeat_btn.add_css_class if p.repeat != "aus" else self.repeat_btn.remove_css_class)("on")
        (self.auto_btn.add_css_class if p.autoplay else self.auto_btn.remove_css_class)("on")
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
        guest = p._mirror is not None
        can = not guest or (p.jam is not None and p.jam.am_admin(p.jam.remote))
        if guest:
            bits = ["󰀂 läuft beim gastgeber" + (" · du darfst steuern" if can else " · steuern nur mit rechten")]
        for x in (self.prev_btn, self.play_btn, self.next_btn, self.seek):
            x.set_sensitive(can)
        for x in (self.shuffle_btn, self.repeat_btn, self.radio_btn):
            x.set_sensitive(not guest)
        self.info.set_label("  ·  ".join(bits))

    def refresh_pos(self):
        p = self.p
        dur = p.dur or (p.current or {}).get("duration") or 0
        self.pos_lbl.set_label(fmt(p.pos))
        self.dur_lbl.set_label(fmt(dur))
        self.seek.set_value(int(p.pos / dur * 1000) if dur else 0)
        self.refresh_lyrics()

    def refresh_sleep(self):
        on = self.w.sleep_btn.has_css_class("accent")
        (self.sleep_btn.add_css_class if on else self.sleep_btn.remove_css_class)("on")
        lbl = self.w.sleep_btn.get_label() or "󰒲"
        self.sleep_btn.set_label(lbl if on else "󰒲")

    def refresh_queue(self):
        p = self.p
        n = getattr(self, "upnext_n", 4)
        nxt = p.queue[p.index + 1:p.index + 1 + n] if p.index >= 0 else []
        self.upnext_panel.set_visible(bool(nxt))
        w = self.w
        tui.sync_rows(self.upnext, nxt, id,
                      lambda t: track_row(t, lambda: p.jump(w._qi(t)), [], menus=w.songs, extra=lambda: w.queue_extra(t)),
                      lambda r, t: r.mark.set_label("›"))

    # ---------- Lyrics: aktuelle Zeile groß, ein paar davor/danach ----------
    def refresh_lyrics(self, force=False):
        w = self.w
        lines = w.lyric_lines
        if not lines:
            # Meldung der Lyrics-Seite („lädt …“, „kein songtext gefunden“) übernehmen
            msg = ""
            first = w.lyr_box.get_first_child()
            if first is not None and isinstance(first, Gtk.Label):
                msg = first.get_label()
            key = ("msg", msg)
            if key != self._lyr_key or force:
                self._lyr_key = key
                for l in self.lyr_lines:
                    l.set_visible(False)
                mid = self.lyr_lines[LYR_BEFORE]
                mid.set_label(msg or "")
                mid.set_visible(bool(msg))
                mid.remove_css_class("now")
                mid.add_css_class("msg")
                self.lyr_src.set_label("")
            return
        if not w.lyr_synced:
            key = ("plain", w.lyrics_vid)
            if key != self._lyr_key or force:
                self._lyr_key = key
                for l in self.lyr_lines:
                    l.set_visible(False)
                mid = self.lyr_lines[LYR_BEFORE]
                mid.set_label("songtext ohne zeitstempel – zum mitlesen im tab ⁴ lyrics")
                mid.add_css_class("msg")
                mid.remove_css_class("now")
                mid.set_visible(True)
                self.lyr_src.set_label(getattr(w, "lyr_source", ""))
            return
        cur = w.current_lyric()
        if cur is None:
            return
        key = ("sync", w.lyrics_vid, cur, w.lyr_offset)
        if key == self._lyr_key and not force:
            return
        self._lyr_key = key
        for i, l in enumerate(self.lyr_lines):
            idx = cur - LYR_BEFORE + i
            l.remove_css_class("msg")
            if 0 <= idx < len(lines) and i <= LYR_BEFORE + self.lyr_after:
                l.set_label(lines[idx][1].get_label())
                l.set_visible(True)
                (l.add_css_class if idx == cur else l.remove_css_class)("now")
            else:
                l.set_visible(False)
        self.lyr_src.set_label(getattr(w, "lyr_source", ""))

    def on_spectrum(self, vals):
        self.spec.set_vals(vals)
