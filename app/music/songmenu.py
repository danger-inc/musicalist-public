# musicalist – Rechtsklick-Menü für jeden Titel (jetzt, warteschlange, suche, bibliothek, hörverlauf) und die
# Playlist-Auswahl („zu playlist hinzufügen“). Im Stil des Kontomenüs (.kpop): Kopf, Rubriken mit Linie,
# Einträge mit Symbol und Taste rechts. Die Playlist-Liste ist eine zweite Seite im selben Popover.
# Außerdem: Maus länger als 0,18 s auf einem Titel → Stream-Adresse vorwärmen (Klick spielt dann sofort).
import subprocess, time

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk

import engine
import tui
from tui import label, hbox, vbox

CSS = """
popover.kpop.smenu > contents { min-width: 270px; }
popover.kpop .kp-title { font-size: 13px; font-weight: bold; margin: 2px 10px 0 10px; }
popover.kpop button.opt.pl-new { color: @primary; }
popover.kpop button.opt.pl-new:hover { color: @on_primary; }
popover.kpop entry.tentry { margin: 2px 8px 4px 8px; }
popover.kpop .kp-empty { color: alpha(@foreground, 0.5); font-size: 11px; margin: 4px 10px; }
"""
PL_TTL = 300          # Playlist-Liste so lange (s) wiederverwenden


class SongMenus:
    def __init__(self, win):
        self.win, self.p = win, win.p
        self.playlists, self.pl_time = None, 0.0
        lp = engine.setting("last_playlist")
        self.last_pl = tuple(lp) if lp else None    # (id, titel) der zuletzt benutzten Playlist – steht oben

    # ---------- an eine Zeile hängen ----------
    def attach(self, row, t, extra=None):
        """Rechtsklick → Menü, Maus drauf → vorwärmen. extra() → zusätzliche Einträge [(symbol, text, fn)]."""
        click = Gtk.GestureClick(button=3)
        click.connect("pressed", lambda g, n, x, y: (g.set_state(Gtk.EventSequenceState.CLAIMED),
                                                    self.menu(g.get_widget(), x, y, t, extra() if extra else [])))
        row.add_controller(click)
        lp = Gtk.GestureLongPress()        # Touchpad/Touch: lange drücken = Rechtsklick
        lp.connect("pressed", lambda g, x, y: self.menu(g.get_widget(), x, y, t, extra() if extra else []))
        row.add_controller(lp)
        mo = Gtk.EventControllerMotion()
        mo.connect("enter", lambda c, x, y: self._hover(c.get_widget(), t, True))
        mo.connect("leave", lambda c: self._hover(c.get_widget(), t, False))
        row.add_controller(mo)

    def _hover(self, w, t, on):
        tid = getattr(w, "_warm_id", None)
        if tid:
            GLib.source_remove(tid)
            w._warm_id = None
        if on:
            def go():
                w._warm_id = None
                self.p.resolver.warm(t.get("videoId"))
                return False
            w._warm_id = GLib.timeout_add(180, go)

    # ---------- Popover-Grundgerüst ----------
    def _popover(self, widget, x=None, y=None):
        pop = Gtk.Popover(has_arrow=False)
        pop.add_css_class("tpop")
        pop.add_css_class("kpop")
        pop.add_css_class("smenu")
        pop.set_parent(widget)
        if x is not None:                    # an der Mausposition: Menü beginnt dort und geht nach rechts
            pop.set_halign(Gtk.Align.START)
            pop.set_position(Gtk.PositionType.BOTTOM)
            r = Gdk.Rectangle()
            r.x, r.y, r.width, r.height = int(x), int(y), 1, 1
            pop.set_pointing_to(r)
        pop.connect("closed", lambda p: GLib.idle_add(lambda: (p.unparent(), False)[1]))
        return pop

    @staticmethod
    def _rub(box, text=""):
        line = Gtk.Box()
        line.add_css_class("kp-line")
        box.append(line)
        if text:
            box.append(label(text, "kp-rub"))

    @staticmethod
    def _item(box, pop, icon, text, fn, key="", danger=False, close=True, cls=None):
        b = Gtk.Button(focus_on_click=False)
        b.add_css_class("opt")
        if danger:
            b.add_css_class("danger")
        if cls:
            b.add_css_class(cls)
        b.set_child(hbox(label(icon, xalign=0.5), label(text, hexpand=True, ellipsize=True), label(key, "kp-key"),
                         spacing=10))

        def go(*_):
            if close:
                pop.popdown()
                GLib.idle_add(lambda: (fn(), False)[1])
            else:
                fn()
        b.connect("clicked", go)
        box.append(b)
        return b

    # ---------- Titel-Menü ----------
    def menu(self, widget, x, y, t, extra=()):
        w, p = self.win, self.p
        pop = self._popover(widget, x, y)
        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, transition_duration=120,
                          vhomogeneous=False, hhomogeneous=True)
        main = vbox(spacing=1)
        head = label(t.get("title") or "?", "kp-title", ellipsize=True)
        head.set_max_width_chars(34)
        main.append(head)
        sub = " · ".join(x for x in (t.get("artist"), t.get("album")) if x)
        if sub:
            s = label(sub, "kp-sub", ellipsize=True)
            s.set_max_width_chars(36)
            main.append(s)
        cur = p.current is not None and p.current.get("videoId") == t.get("videoId")
        it = lambda *a, **k: self._item(main, pop, *a, **k)
        self._rub(main, "abspielen")
        if not cur:
            it("󰐊", "jetzt abspielen", lambda: (p.play_now(t), p.start_radio(t) if p.autoplay else None), "klick")
        it("»", "als nächstes", lambda: (p.add(dict(t), next_=True), w.say(f"» {t['title']}")))
        it("+", "an warteschlange anhängen", lambda: (p.add(dict(t)), w.say(f"+ {t['title']}")))
        it("󰐹", "radio zu diesem titel", lambda: (p.start_radio(t), w.say("radio startet …")))
        self._rub(main, "sammeln")
        it("󰐒", "zu playlist hinzufügen", lambda: self._show_pl(stack, pl_box, pop, [t]), "›", close=False)
        if w.account is not None:
            liked = bool(t.get("liked"))
            it("󰋑" if liked else "󰋕", "gefällt mir nicht mehr" if liked else "gefällt mir",
               lambda: p.rate(t, not liked), "l" if cur else "")
        if t.get("artist") or t.get("albumId"):
            self._rub(main, "öffnen")
            if t.get("artist"):
                it("󰠃", f"künstler · {(t.get('artist') or '').split(',')[0]}", lambda: w.open_artist(t))
            if t.get("albumId"):
                it("󰀥", f"album · {t.get('album') or 'öffnen'}", lambda: w.open_detail("album", t["albumId"]))
        if cur:
            it("󰗊", "lyrics", lambda: w.show_tab("lyrics"), "4")
        self._rub(main)
        url = f"https://music.youtube.com/watch?v={t['videoId']}"
        it("󰆏", "link kopieren", lambda: (Gdk.Display.get_default().get_clipboard().set_content(Gdk.ContentProvider.new_for_value(url)),
                    w.say("link kopiert")))
        it("↗", "im browser öffnen", lambda: engine.open_url(url))
        if extra:
            self._rub(main)
            for e in extra:
                it(e[0], e[1], e[2], danger=len(e) > 3 and e[3])
        stack.add_named(main, "main")
        pl_box = vbox(spacing=1)
        stack.add_named(pl_box, "pl")
        pop.set_child(stack)
        pop.popup()
        return pop

    # ---------- Playlist-Auswahl ----------
    def picker(self, anchor, tracks, x=None, y=None):
        """Eigenes Popover nur mit der Playlist-Liste (Knopf „󰐒 playlist“, Taste a)."""
        tracks = [t for t in tracks if t]
        if not tracks:
            self.win.say("nichts zum hinzufügen")
            return None
        pop = self._popover(anchor, x, y)
        box = vbox(spacing=1)
        pop.set_child(box)
        self._fill_pl(box, pop, tracks, back=None)
        pop.popup()
        return pop

    def _show_pl(self, stack, box, pop, tracks):
        self._fill_pl(box, pop, tracks, back=lambda: stack.set_visible_child_name("main"))
        stack.set_visible_child_name("pl")

    def _fill_pl(self, box, pop, tracks, back):
        tui.clear(box)
        w = self.win
        n = len(tracks)
        what = f"„{tracks[0]['title']}“" if n == 1 else f"{n} titel"
        if back:
            self._item(box, pop, "‹", "zurück", back, close=False)
            self._rub(box)
        head = label("󰐒  zu playlist hinzufügen", "kp-head")
        box.append(head)
        s = label(what, "kp-sub", ellipsize=True)
        s.set_max_width_chars(36)
        box.append(s)
        if w.account is None:
            box.append(label("dafür erst anmelden (󰀄 konto → mit zen / firefox anmelden)", "kp-empty", wrap=True))
            return
        lst = vbox(spacing=1)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True,
                                    max_content_height=320, child=lst)
        box.append(scroll)
        self._rub(box)
        entry = tui.Entry("name der neuen playlist …")
        entry.set_visible(False)
        new_btn = self._item(box, pop, "+", "neue playlist …", lambda: (entry.set_visible(True), entry.grab_focus()),
                             close=False, cls="pl-new")
        box.append(entry)

        def create():
            name = entry.get_text().strip()
            if not name:
                return
            pop.popdown()
            self.create(name, tracks)
        entry.connect("activate", lambda *_: create())
        new_btn.set_tooltip_text("neue (private) playlist mit diesen titeln anlegen")

        def show(pls):
            tui.clear(lst)
            if isinstance(pls, Exception):
                lst.append(label(f"playlists laden ging nicht: {str(pls)[:80]}", "kp-empty", wrap=True))
                return
            if self.last_pl and any(pl["id"] == self.last_pl[0] for pl in pls):
                lst.append(label("zuletzt", "kp-rub"))
                b = self._item(lst, pop, "󰐒", self.last_pl[1], lambda pl=self.last_pl: self.add(pl, tracks))
                GLib.idle_add(lambda: (b.grab_focus(), False)[1])     # „a“, dann Enter
                lst.append(label("alle", "kp-rub"))
            if not pls:
                lst.append(label("noch keine eigenen playlists", "kp-empty"))
            for pl in pls:
                self._item(lst, pop, "󰲸", pl["title"], lambda pl=pl: self.add((pl["id"], pl["title"]), tracks),
                           str(pl.get("count") or ""))
        if self.playlists is not None and time.monotonic() - self.pl_time < PL_TTL:
            show(self.playlists)
        else:
            lst.append(label("lädt playlists …", "kp-empty"))

            def done(res):
                if not isinstance(res, Exception):
                    self.playlists, self.pl_time = res, time.monotonic()
                show(res)
            tui.background(self.p.music.editable_playlists, done=done)

    def add(self, pl, tracks):
        pid, title = pl
        self.last_pl = (pid, title)
        engine.set_setting("last_playlist", [pid, title])
        vids = [t["videoId"] for t in tracks]
        self.win.say(f"füge zu „{title}“ hinzu …")

        def done(res):
            if isinstance(res, Exception):
                self.win.say(f"playlist: {str(res)[:120]}", error=True)
            else:
                added, dup = res
                if added:
                    self.pl_time = 0.0                 # Anzahl hat sich geändert
                if not added:
                    self.win.say(f"󰀦 bereits in „{title}“" if len(vids) == 1 else
                                 f"󰀦 alle {len(vids)} titel bereits in „{title}“", error=True)
                elif dup:
                    self.win.say(f"󰐒 {added} → „{title}“ · {dup} bereits drin")
                else:
                    self.win.say(f"󰐒 {added} titel → „{title}“" if added > 1 else
                                 f"󰐒 „{tracks[0]['title']}“ → „{title}“")
        tui.background(self.p.music.add_to_playlist, pid, vids, done=done)

    def create(self, name, tracks):
        vids = [t["videoId"] for t in tracks]
        self.win.say(f"lege „{name}“ an …")

        def done(res):
            if isinstance(res, Exception):
                self.win.say(f"playlist anlegen: {str(res)[:120]}", error=True)
                return
            self.last_pl = (res, name)
            self.pl_time = 0.0
            self.win.say(f"󰐒 neue playlist „{name}“ mit {len(vids)} titel{'n' if len(vids) != 1 else ''}")
            if self.win.account:
                self.win.load_library()
        tui.background(self.p.music.create_playlist, name, vids, done=done)
