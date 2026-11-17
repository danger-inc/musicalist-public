# musicalist – Songtexte (Teil von MusicWindow, siehe ui.py). Methoden greifen auf self (das Hauptfenster) zu.

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Graphene, Gtk, Pango, PangoCairo

import tui
from tui import label, hbox, vbox, esc
from engine import fmt
from rows import track_row, coll_row, artist_link


def _eco():
    """Energy-saving mode (istheme.eco): animations off."""
    try:
        import istheme
        return istheme.eco()
    except Exception:      # noqa: BLE001
        return False



class LyricsMixin:

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
        self.lyr_offset = 0.0
        bar = hbox(label("", hexpand=True), tui.Button("󰍬 karaoke", self.karaoke, tooltip="Karaoke: ganzer Bildschirm, aktuelle Zeile füllt sich (k)"), spacing=8)
        bar.set_margin_top(4)
        self.add_page("lyrics", vbox(bar, self.lyr_scroll, spacing=0), scroll=False)

    def karaoke(self):
        """Karaoke-Fenster (Vollbild): aktuelle Zeile groß, füllt sich bis zur nächsten Zeile in der Akzentfarbe;
        davor die letzte Zeile blass, danach die nächsten zwei. Esc/Klick/k = schließen."""
        if getattr(self, "_kara", None) is not None:
            self._kara.close()
            return
        self.load_lyrics()                         # auch aus anderen Reitern (k): Text des laufenden Titels
        if not self.lyr_synced or not self.lyric_lines:
            self.say("karaoke geht nur mit songtext mit zeitstempeln", error=True)
            return
        win = Gtk.Window(title="musicalist · karaoke", transient_for=self)
        win.add_css_class("karaoke")
        da = Gtk.DrawingArea(hexpand=True, vexpand=True)
        win.set_child(da)

        def draw(_a, cr, w, h):
            c = tui.colors()
            bg, fg, ac = c.get("background"), c.get("foreground"), c.get("primary")
            if (self.p.current or {}).get("videoId") != self.lyrics_vid:
                self.load_lyrics()                 # Titelwechsel während Karaoke
            cr.set_source_rgb(bg.red, bg.green, bg.blue)
            cr.paint()
            lines = [(s, l.get_label()) for s, l in self.lyric_lines]
            pos = self.p.pos + 0.15 - getattr(self, "lyr_offset", 0.0)
            i = max([k for k, (s, _t) in enumerate(lines) if s is not None and s <= pos] or [-1])
            cur = lines[i] if i >= 0 else None
            nxt = lines[i + 1] if i + 1 < len(lines) else None
            frac = 0.0 if cur is None else 1.0 if nxt is None else max(0.0, min(1.0, (pos - cur[0]) / max(0.5, nxt[0] - cur[0])))

            def text(t, size, y, col, alpha, bold=False, clip=None):
                lay = PangoCairo.create_layout(cr)
                lay.set_font_description(Pango.FontDescription.from_string(f"{tui.FONT} {'Bold ' if bold else ''}{int(size)}"))
                lay.set_width(int((w - 80) * Pango.SCALE))
                lay.set_alignment(Pango.Alignment.CENTER)
                lay.set_wrap(Pango.WrapMode.WORD_CHAR)
                lay.set_text(t or "♪", -1)
                tw, th = lay.get_pixel_size()
                cr.save()
                if clip is not None:      # nur der schon gesungene Teil (von links)
                    ink, _log = lay.get_pixel_extents()
                    x0 = 40 + ink.x
                    cr.rectangle(x0, y - 2, ink.width * clip, th + 4)
                    cr.clip()
                cr.set_source_rgba(col.red, col.green, col.blue, alpha)
                cr.move_to(40, y)
                PangoCairo.show_layout(cr, lay)
                cr.restore()
                return th
            big = max(22, h / 14)
            y = h / 2 - big
            if i > 0:
                text(lines[i - 1][1], big * 0.55, y - big * 1.6, fg, 0.35)
            line = cur[1] if cur else "♪ …"
            th = text(line, big, y, fg, 0.4, True)
            text(line, big, y, ac, 1.0, True, clip=frac)
            yy = y + th + big * 0.5
            for k in (1, 2):
                if i + k < len(lines):
                    yy += text(lines[i + k][1], big * (0.65 if k == 1 else 0.55), yy, fg, 0.7 if k == 1 else 0.4) + big * 0.3
            t = self.p.current or {}
            text(f"{t.get('title', '')} · {t.get('artist', '')}", 12, 24, fg, 0.5)
        da.set_draw_func(draw)
        da.add_tick_callback(lambda w, _c: (w.queue_draw(), True)[1])
        click = Gtk.GestureClick()
        click.connect("released", lambda *_: win.close())
        da.add_controller(click)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", lambda _c, kv, *_: (win.close(), True)[1] if kv in (Gdk.KEY_Escape, Gdk.KEY_k, Gdk.KEY_q) else False)
        win.add_controller(keys)
        win.connect("close-request", lambda *_: (setattr(self, "_kara", None), False)[1])
        self._kara = win
        win.fullscreen()
        win.present()

    def _lyr_user_scroll(self, *_):
        self.lyr_manual_until = GLib.get_monotonic_time() + 4_000_000  # 4 s selbst scrollen lassen
        return False

    def lyr_message(self, text):
        tui.clear(self.lyr_box)
        self.lyric_lines = []
        self.lyr_box.append(label(text, "empty", xalign=0.5))

    def load_lyrics(self):
        """Songtext des aktuellen Titels anzeigen. Geladen wird er schon beim Titelwechsel (engine.Lyrics.preload),
        meist liegt er hier also schon bereit."""
        t = self.p.current
        if not t or t["videoId"] == self.lyrics_vid:
            return
        vid = self.lyrics_vid = t["videoId"]
        self.lyr_src.set_label("")
        self._lyr_cur = None
        self.lyr_offset = 0.0
        cached = self.p.lyrics.cached(vid)
        if cached is not False:
            self.show_lyrics(vid, cached)
            return
        self.lyr_message("lädt …")
        tui.background(self.p.lyrics.fetch, t, self.p.dur or 0, done=lambda res: self.show_lyrics(vid, res))

    def show_lyrics(self, vid, res):
        if vid != self.lyrics_vid:
            return
        if isinstance(res, Exception) or not res or not res.get("lyrics"):
            self.lyr_message("kein songtext gefunden")
            return
        tui.clear(self.lyr_box)
        self.lyric_lines = []
        lyr = res["lyrics"]
        self.lyr_synced = bool(res.get("synced")) and not isinstance(lyr, str)
        lines = lyr if self.lyr_synced else [(None, x) for x in (lyr if isinstance(lyr, str) else
                                                                  "\n".join(x for _s, x in lyr)).splitlines()]
        for start, text in lines:
            lbl = label(text or "♪", "lyric", xalign=0.5, wrap=True)
            lbl.set_justify(Gtk.Justification.CENTER)
            if not self.lyr_synced:
                lbl.add_css_class("plain")
            self.lyric_lines.append((start, lbl))
            self.lyr_box.append(lbl)
        self.lyr_source = res.get("source") or ""
        self.update_lyr_src()
        if self.lyr_synced:
            GLib.idle_add(lambda: self.sync_lyrics(jump=True) and False)
        else:                                      # ohne Zeitstempel: nichts raten, oben anfangen
            GLib.idle_add(lambda: self.lyr_scroll.get_vadjustment().set_value(0) and False)

    def update_lyr_src(self):
        # Quelle (lrclib …) wird bewusst nicht mehr angezeigt – nur Hinweise, die etwas zu tun geben
        src = ""
        if not self.lyr_synced:
            src = "ohne zeitstempel – zum mitlesen scrollen"
        elif self.lyr_offset:
            src = f"versatz {self.lyr_offset:+.2f} s  ( [ ] )"
        self.lyr_src.set_label(src)
        self.lyr_src.set_visible(bool(src))

    def shift_lyrics(self, d):
        if not self.lyr_synced or not self.lyric_lines:
            self.say("dieser songtext hat keine zeitstempel")
            return
        self.lyr_offset = round(getattr(self, "lyr_offset", 0.0) + d, 2)
        self.update_lyr_src()
        self.say(f"lyrics {'später' if self.lyr_offset > 0 else 'früher'}: {self.lyr_offset:+.2f} s"
                 if self.lyr_offset else "lyrics-versatz zurückgesetzt")
        self.sync_lyrics(jump=True)

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
        if not self.lyr_synced:
            return None                            # ohne Zeitstempel wird nichts markiert (früher geraten → falsch)
        pos = self.p.pos + 0.25 - getattr(self, "lyr_offset", 0.0)   # Zeile kurz vor dem Einsatz zeigen
        cur = None
        for i, (start, _l) in enumerate(self.lyric_lines):
            if start <= pos:
                cur = i
            else:
                break
        return cur if cur is not None else 0

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
        if _eco():                      # energy-saving mode: no scroll animation
            adj.set_value(target)
            return
        if self.lyr_anim:
            self.lyr_scroll.remove_tick_callback(self.lyr_anim)
        self.lyr_anim = self.lyr_scroll.add_tick_callback(step)
