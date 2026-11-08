"""Anpassen (Stift oben links neben dem Logo): Leiste unter „steuerung“, Reihenfolge der Bibliothek, Schnellauswahl.
Dazu die Schnellauswahl selbst (Bibliothek, nur Titelbilder)."""
from gi.repository import Gdk, GLib, Gtk

import tui
import engine
from tui import label, hbox, vbox
from widgets import big_thumb, fetch_pixbuf

CTL_DEFAULT = ["shuffle", "repeat", "sleep", "mixer", "autoplay", "volume"]
CTL_NAMES = {"shuffle": "󰒝 mischen", "repeat": "󰑗 wiederholen", "sleep": "󰒲 schlaf-timer", "mixer": "󰓃 klang / mixer",
             "autoplay": "󰑐 autoplay", "volume": "󰕾 lautstärke", "lyrics": "󰍰 lyrics", "artist": "󰠃 künstler",
             "album": "󰀥 album", "recommend": "󰡉 an freunde empfehlen", "menu": "⋮ titel-menü"}
LIB_DEFAULT = ["quick", "konto", "likes", "friends", "coll", "local", "stats"]
LIB_NAMES = {"quick": "󰝚 schnellauswahl", "konto": "󰀄 konto", "likes": "󰋑 lieblingssongs (lokal)", "friends": "󰡉 freunde",
             "coll": "󰲸 sammlung (playlists …)", "local": "󰉋 lokale musik", "stats": "󰄨 rückblick"}


def _order(key, default):
    o = [x for x in (engine.setting(key) or []) if x in default]
    return o + [x for x in default if x not in o]


class AnpassenMixin:
    # ---------- Leiste unter „steuerung“ ----------
    def build_ctl_extra(self):
        """Zusätzliche Knöpfe für die Leiste (die sechs Standard-Elemente gibt es schon)."""
        def cur():
            return self.p.current

        def album():
            t = cur()
            if t and t.get("albumId"):
                self.open_detail("album", t["albumId"])
            else:
                self.say("zu diesem titel ist kein album bekannt")

        def recommend():
            t = cur()
            if t and getattr(self.p, "friends", None) and self.p.friends.recommend(t):
                self.say("freunde sehen: empfohlen")

        def menu():
            t = cur()
            if t:
                self.songs.menu(self._ctl_widgets["menu"], 0, self._ctl_widgets["menu"].get_height(), t)
        self._ctl_widgets = {
            "shuffle": self.shuffle_btn, "repeat": self.repeat_btn, "sleep": self.sleep_btn, "mixer": self.sound_btn,
            "autoplay": self.auto_chk, "volume": self._vol_box,
            "lyrics": tui.Button("󰍰 lyrics", lambda: self.show_tab("lyrics"), tooltip="Liedtext (4)"),
            "artist": tui.Button("󰠃 künstler", lambda: cur() and self.open_artist(cur()), tooltip="Künstlerseite"),
            "album": tui.Button("󰀥 album", album, tooltip="Album öffnen"),
            "recommend": tui.Button("󰡉 empfehlen", recommend, tooltip="An alle Freunde empfehlen"),
            "menu": tui.Button("⋮ menü", menu, tooltip="Alles zu diesem Titel"),
        }
        self.apply_ctl_bar()

    def apply_ctl_bar(self):
        opts = self.ctl_opts
        child = opts.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            opts.remove(child)
            child = nxt
        bar = [x for x in (engine.setting("ctl_bar") or CTL_DEFAULT) if x in self._ctl_widgets]
        for k in bar:
            opts.append(self._ctl_widgets[k])

    # ---------- Bibliothek: Reihenfolge ----------
    def apply_lib_order(self):
        panels = {"quick": self.quick_panel, "konto": self.login_panel, "likes": self.ll_panel, "friends": self.fr_panel,
                  "coll": self.coll_panel, "local": self.local_panel, "stats": self.stat_panel}
        home = self.lib_home_box
        prev = None
        for k in _order("lib_order", LIB_DEFAULT):
            w = panels[k]
            home.reorder_child_after(w, prev)
            prev = w

    # ---------- Schnellauswahl ----------
    def build_quick(self):
        self.quick_panel = tui.Panel("󰝚 schnellauswahl")
        self.quick_grid = vbox(spacing=4)
        self._quick_cols = 0
        GLib.timeout_add(700, self._quick_resize)
        self.quick_n_lbl = label("", "dim")
        self.quick_busy = label("", "dim", hexpand=True, ellipsize=True)
        head = hbox(self.quick_busy, tui.Button("󰕮", self.quick_cycle, tooltip="Wie viele Titel (10 … 50)"), tui.Button("󰑐 neu", self.quick_load, tooltip="Neu mischen lassen"),
                    spacing=6)
        self.quick_panel.body.append(head)
        self.quick_panel.body.append(self.quick_grid)
        self.lib_home_box.insert_child_after(self.quick_panel, None)
        self.quick_tracks = []
        self.quick_load()

    def quick_n(self):
        return int(engine.setting("quick_n") or 25)

    def quick_cycle(self):
        n = self.quick_n()
        n = 10 if n >= 50 else n + 5
        engine.set_setting("quick_n", n)
        self.say(f"schnellauswahl: {n} titel")
        self.quick_fill()

    def quick_load(self):
        self.quick_busy.set_label("lädt …")

        def work():
            tr = self.p.music.quick_picks()
            pics = {}
            for t in tr[:50]:
                url = big_thumb(t.get("thumb"), 226)
                if url:
                    try:
                        pics[t["videoId"]] = fetch_pixbuf(url)
                    except Exception:  # noqa: BLE001
                        pass
            return tr, pics

        def done(res):
            if isinstance(res, Exception):
                self.quick_busy.set_label(f"schnellauswahl: {engine.explain(res)}")
                return
            self.quick_tracks, self._quick_pics = res
            self.quick_busy.set_label("von youtube music für dich")
            self.quick_fill()
        tui.background(work, done=done)

    def _quick_resize(self):
        """Spaltenzahl folgt der Fensterbreite (Titelbilder 94 px)."""
        if self.quick_panel.get_mapped():
            cols = self._quick_cols_now()
            if cols != self._quick_cols and self.quick_tracks:
                self.quick_fill()
        return True

    def _quick_cols_now(self):
        w = self.quick_panel.get_width() or self.get_width() or 800
        return max(3, (w - 40) // 98)

    def quick_fill(self):
        grid = self.quick_grid
        tui.clear(grid)
        cols = self._quick_cols = self._quick_cols_now()
        row = None
        tr = self.quick_tracks[:self.quick_n()]
        for i, t in enumerate(tr):
            pb = getattr(self, "_quick_pics", {}).get(t["videoId"])
            pic = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.COVER, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                              hexpand=False, vexpand=False)
            pic.set_size_request(86, 86)
            if pb is not None:
                pic.set_paintable(Gdk.Texture.new_for_pixbuf(pb))
            b = Gtk.Button(child=pic, focus_on_click=False, halign=Gtk.Align.START, hexpand=False)
            b.add_css_class("rowhead")
            b.set_size_request(94, 94)
            b.set_tooltip_text(f"{t['title']} · {t['artist']}")
            b.connect("clicked", lambda _b, i=i, tr=tr: self.p.play_tracks(tr, start=i, src=("start", "schnellauswahl")))
            rc = Gtk.GestureClick(button=3)
            rc.connect("pressed", lambda g, n, x, y, b=b, t=t: self.songs.menu(b, x, y, t))
            b.add_controller(rc)
            if i % cols == 0:
                row = hbox(spacing=4)
                row.set_halign(Gtk.Align.START)
                grid.append(row)
            row.append(b)

    # ---------- Anpassen-Popover ----------
    def build_customize(self):
        btn = tui.Button("󰏫", self.customize_menu, tooltip="Anpassen: Leiste unter „steuerung“, Bibliothek, Schnellauswahl")
        btn.set_margin_start(2)
        btn.set_margin_end(10)                       # Abstand zu ¹ jetzt
        top = self.tab_btns[0][1].get_parent()
        top.insert_child_after(btn, top.get_first_child())
        self.cust_btn = btn

    def customize_menu(self, anchor=None):
        anchor = anchor if isinstance(anchor, Gtk.Widget) else self.cust_btn
        pop = self.songs._popover(anchor)
        pop.set_position(Gtk.PositionType.BOTTOM)
        holder = vbox(spacing=0)
        # feste Höhe (passend zum Fenster) statt „natürlicher“: sonst schnitt das Popover die unteren Kästen ab
        hh = int(max(220, min(620, self.get_height() - 120)))
        pop.set_child(Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, min_content_height=hh, max_content_height=hh,
                                         propagate_natural_width=True, child=holder))

        def move(key, default, k, d, ctl):
            cur = (engine.setting(key) or default) if ctl else _order(key, default)
            cur = [x for x in cur]
            if k not in cur:
                return
            i = cur.index(k)
            j = i + d
            if 0 <= j < len(cur):
                cur.insert(j, cur.pop(i))
                engine.set_setting(key, cur)
            fill()
            (self.apply_ctl_bar if ctl else self.apply_lib_order)()

        def toggle(k, on):
            cur = [x for x in (engine.setting("ctl_bar") or CTL_DEFAULT)]
            if on and k not in cur:
                cur.append(k)
            if not on and k in cur:
                cur.remove(k)
            engine.set_setting("ctl_bar", cur)
            fill()
            self.apply_ctl_bar()

        def fill():
            tui.clear(holder)
            holder.append(label("󰏫  anpassen", "kp-head"))
            holder.append(label("leiste unter „steuerung“ (jetzt)", "kp-sub"))
            bar = engine.setting("ctl_bar") or CTL_DEFAULT
            order = [k for k in bar if k in CTL_NAMES] + [k for k in CTL_NAMES if k not in bar]
            for k in order:
                on = k in bar
                holder.append(hbox(tui.Check(CTL_NAMES[k], on, lambda v, k=k: toggle(k, v)), label("", hexpand=True),
                                   *([tui.Button("↑", lambda k=k: move("ctl_bar", CTL_DEFAULT, k, -1, True)),
                                      tui.Button("↓", lambda k=k: move("ctl_bar", CTL_DEFAULT, k, 1, True))] if on else []), spacing=6))
            holder.append(label("bibliothek: reihenfolge", "kp-sub"))
            for k in _order("lib_order", LIB_DEFAULT):
                holder.append(hbox(label(LIB_NAMES[k], hexpand=True),
                                   tui.Button("↑", lambda k=k: move("lib_order", LIB_DEFAULT, k, -1, False)),
                                   tui.Button("↓", lambda k=k: move("lib_order", LIB_DEFAULT, k, 1, False)), spacing=6))
            holder.append(label("schnellauswahl", "kp-sub"))
            holder.append(hbox(label(f"{self.quick_n()} titel", hexpand=True),
                               tui.Button("−", lambda: (engine.set_setting("quick_n", max(5, self.quick_n() - 5)), self.quick_fill(), fill())),
                               tui.Button("+", lambda: (engine.set_setting("quick_n", min(50, self.quick_n() + 5)), self.quick_fill(), fill())),
                               spacing=6))
            holder.append(hbox(tui.Button("󰓃 klang / mixer öffnen", lambda: (pop.popdown(), self.sound_menu())),
                               tui.Button("zurücksetzen", lambda: (engine.set_setting("ctl_bar", None), engine.set_setting("lib_order", None),
                                                                   self.apply_ctl_bar(), self.apply_lib_order(), fill()), danger=True),
                               spacing=8))
        fill()
        pop.popup()
