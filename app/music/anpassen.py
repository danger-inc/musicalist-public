"""Anpassen (Stift oben links neben dem Logo): Leiste unter „steuerung“, Reihenfolge der Bibliothek, Schnellauswahl.
Dazu die Schnellauswahl selbst (Bibliothek, nur Titelbilder)."""
from gi.repository import Gdk, GLib, Gtk

import tui
import engine
from tui import label, hbox, vbox
from widgets import big_thumb, fetch_pixbuf, DotThumb, dither, ink_darker, pixel_on, set_pixel, notify_pixel, PIXEL_LISTENERS, draw_photo
import pixelart

CTL_DEFAULT = ["shuffle", "repeat", "sleep", "mixer", "autoplay", "pixel", "volume"]
CTL_NAMES = {"shuffle": "󰒝 mischen", "repeat": "󰑗 wiederholen", "sleep": "󰒲 schlaf-timer", "mixer": "󰓃 klang / mixer",
             "autoplay": "󰑐 autoplay", "volume": "󰕾 lautstärke", "lyrics": "󰍰 lyrics", "artist": "󰠃 künstler",
             "album": "󰀥 album", "recommend": "󰡉 an freunde empfehlen", "menu": "⋮ titel-menü", "pixel": "󱗼 raster / foto"}
LIB_DEFAULT = ["quick", "konto", "likes", "coll", "local", "stats"]
LIB_NAMES = {"quick": "󰝚 schnellauswahl", "konto": "󰀄 konto", "likes": "󰋑 lieblingssongs (lokal)",
             "coll": "󰲸 sammlung (playlists …)", "local": "󰉋 lokale musik", "stats": "󰄨 hörverhalten"}


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
            if t and t.get("podcastId"):
                self.open_detail("podcast", t["podcastId"])
            elif t and t.get("albumId"):
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
        self.pixel_btn = tui.Button("󱗼", lambda: set_pixel(not pixel_on()),
                                    tooltip="Titelbilder als Raster – an: Punktraster, aus: echtes Foto (überall); Rechtsklick: einstellen")
        self._ctl_widgets = {
            "shuffle": self.shuffle_btn, "repeat": self.repeat_btn, "sleep": self.sleep_btn, "mixer": self.sound_btn,
            "autoplay": self.auto_chk, "volume": self._vol_box,
            "lyrics": tui.Button("󰍰 lyrics", lambda: self.show_tab("lyrics"), tooltip="Liedtext mitlesen"),
            "artist": tui.Button("󰠃 künstler", lambda: cur() and self.open_artist(cur()), tooltip="Künstlerseite"),
            "album": tui.Button("󰀥 album", album, tooltip="Album öffnen"),
            "recommend": tui.Button("󰡉 empfehlen", recommend, tooltip="An alle Freunde empfehlen"),
            "menu": tui.Button("⋮ menü", menu, tooltip="Alles zu diesem Titel"),
            "pixel": self.pixel_btn,
        }
        self.attach_pixel_menu(self.pixel_btn)
        PIXEL_LISTENERS.append(self.sync_pixel_btn)
        self.sync_pixel_btn()
        self.apply_ctl_bar()

    def attach_pixel_menu(self, btn):
        """Rechtsklick (oder langes Drücken) auf einen Raster-Knopf: Raster einstellen wie in der Handy-App."""
        rc = Gtk.GestureClick(button=3)
        rc.connect("pressed", lambda g, *_: (g.set_state(Gtk.EventSequenceState.CLAIMED), self.pixel_menu(btn)))
        btn.add_controller(rc)
        lp = Gtk.GestureLongPress()
        lp.connect("pressed", lambda *_: self.pixel_menu(btn))
        btn.add_controller(lp)

    def pixel_menu(self, anchor):
        pop = self.songs._popover(anchor)
        up = bool(getattr(self, "tv_on", False))             # im Fernseher-Modus sitzt der Knopf unten → Menü nach oben
        pop.set_position(Gtk.PositionType.TOP if up else Gtk.PositionType.BOTTOM)
        holder = vbox(spacing=6)
        for m in ("set_margin_top", "set_margin_bottom", "set_margin_start", "set_margin_end"):
            getattr(holder, m)(10)
        hh = int(max(260, min(640, self.get_height() - 120)))
        if up:
            hh = min(hh, 420)
        pop.set_child(Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, min_content_height=hh, max_content_height=hh,
                                         min_content_width=400, max_content_width=440, propagate_natural_width=True, child=holder))
        timer = {"id": 0}

        def changed(rebuild=True):
            if timer["id"]:
                GLib.source_remove(timer["id"])

            def go():
                timer["id"] = 0
                notify_pixel()
                preview.queue_draw()
                return False
            timer["id"] = GLib.timeout_add(120, go)
            if rebuild:
                fill()

        def put(**kw):
            c = pixelart.cfg()
            c.update(kw)
            pixelart.set_cfg(c)
            changed(rebuild=True)

        def choice(opts, cur, key):
            row = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=6, row_spacing=6, max_children_per_line=6, homogeneous=False)
            row.add_css_class("opts")
            for k, name in opts:
                b = tui.Button(name, lambda k=k: put(**{key: k}))
                if cur == k:
                    b.add_css_class("on")
                row.append(b)
            return row

        def slider(name, key, lo, hi, fmt):
            c = pixelart.cfg()
            val = label(fmt(c[key]), "accent", xalign=1)

            def on(v):
                x = lo + v / 1000 * (hi - lo)
                x = int(round(x)) if key == "res" else round(x, 2)
                cc = pixelart.cfg()
                cc[key] = x
                pixelart.set_cfg(cc)
                val.set_label(fmt(x))
                changed(rebuild=False)
            m = tui.Meter(1000, on, mark=False)
            m.set_value(int((c[key] - lo) / (hi - lo) * 1000))
            holder.append(hbox(label(name, hexpand=True), val))
            holder.append(m)

        preview = Gtk.DrawingArea(content_width=200, content_height=200, halign=Gtk.Align.CENTER)

        def pdraw(_a, cr, w, h):
            t = self.p.current
            pb = None
            if t and t.get("thumb"):
                try:
                    pb = fetch_pixbuf(big_thumb(t["thumb"]))
                except Exception:  # noqa: BLE001
                    pb = None
            side = min(w, h)
            if pb is None:
                return
            if not pixel_on():
                draw_photo(cr, pb, 0, 0, side)
                return
            c = pixelart.cfg()
            pixelart.draw(cr, pixelart.grid(pb, c["res"], c), side, c, flip=ink_darker())
        preview.set_draw_func(pdraw)

        def fill():
            tui.clear(holder)
            c = pixelart.cfg()
            holder.append(label("󱗼  titelbild-raster", "kp-head"))
            holder.append(preview)
            holder.append(tui.Check("als raster zeigen (aus = foto)", pixel_on(), lambda on: (set_pixel(on), preview.queue_draw())))
            holder.append(label("presets", "kp-sub"))
            pr = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=6, row_spacing=6, max_children_per_line=3, homogeneous=False)
            pr.add_css_class("opts")
            for name, p in pixelart.PRESETS:
                b = tui.Button(name, lambda p=p: (pixelart.set_cfg(p), changed()))
                if {k: c[k] for k in p} == p:
                    b.add_css_class("on")
                pr.append(b)
            holder.append(pr)
            holder.append(label("form", "kp-sub"))
            holder.append(choice(pixelart.SHAPES, c["shape"], "shape"))
            slider("auflösung", "res", 16, 112, lambda v: f"{int(v)} × {int(v)}")
            slider("punktgröße", "size", 0.25, 1.0, lambda v: f"{int(v * 100)} %")
            holder.append(label("farbe & helligkeit", "kp-sub"))
            holder.append(choice(pixelart.COLORS, c["color"], "color"))
            slider("kontrast", "contrast", -1.0, 1.0, lambda v: f"{v:+.1f}")
            holder.append(tui.Check("helligkeit ausgleichen", c["eq"], lambda on: put(eq=on)))
            holder.append(tui.Check("umkehren (hell ↔ dunkel)", c["invert"], lambda on: put(invert=on)))
            if c["shape"] in ("quadrat", "punkt"):
                holder.append(label("rasterung", "kp-sub"))
                holder.append(choice(pixelart.DITHERS, c["dither"], "dither"))
                holder.append(tui.Check("aus-punkte schwach zeigen", c["off"], lambda on: put(off=on)))
            holder.append(tui.Button("zurücksetzen (wie bisher)", lambda: (pixelart.set_cfg(None), changed()), danger=True))
        fill()
        pop.popup()

    def sync_pixel_btn(self):
        (self.pixel_btn.add_css_class if pixel_on() else self.pixel_btn.remove_css_class)("on")
        self.pixel_btn.set_tooltip_text("Titelbilder als Raster – an: Punktraster, aus: echtes Foto (überall); Rechtsklick: einstellen")

    def apply_ctl_bar(self):
        opts = self.ctl_opts
        child = opts.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            opts.remove(child)
            child = nxt
        stored = engine.setting("ctl_bar")
        if stored and not engine.setting("ctl_pixel_added"):      # neuer Knopf: einmal zu einer eigenen Leiste dazu
            engine.set_setting("ctl_pixel_added", True)
            stored = list(stored) + ["pixel"] if "pixel" not in stored else stored
            engine.set_setting("ctl_bar", stored)
        bar = [x for x in (stored or CTL_DEFAULT) if x in self._ctl_widgets]
        for k in bar:
            self._ctl_widgets[k].set_halign(Gtk.Align.START)     # nicht auf die Zeilenbreite auseinanderziehen
            opts.append(self._ctl_widgets[k])
            fc = self._ctl_widgets[k].get_parent()
            if fc is not None:
                fc.set_halign(Gtk.Align.START)
                fc.set_hexpand(False)

    # ---------- Bibliothek: Reihenfolge ----------
    def apply_lib_order(self):
        panels = {"quick": self.quick_panel, "konto": self.login_panel, "likes": self.ll_panel,
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
        self.quick_busy = label("", "dim", hexpand=True, ellipsize=True)
        self.quick_set_btn = tui.Button("󰕮", lambda: self.quick_menu(self.quick_set_btn),
                                        tooltip="Anzahl, Größe und Rasterfeinheit der Schnellauswahl einstellen")
        head = hbox(self.quick_busy, self.quick_set_btn, tui.Button("󰑐 neu", self.quick_load, tooltip="Neu mischen lassen"),
                    spacing=6)
        self.quick_panel.body.append(head)
        self.quick_panel.body.append(self.quick_grid)
        self.lib_home_box.insert_child_after(self.quick_panel, None)
        self.quick_tracks = []
        self.quick_load()

    def quick_n(self):
        return max(1, min(50, int(engine.setting("quick_n") or 25)))

    def quick_side(self):
        return max(48, min(200, int(engine.setting("quick_side") or 100)))

    def quick_res(self):
        return max(8, min(64, int(engine.setting("quick_res") or 40)))

    def quick_names(self):
        """Titel und Künstler unter den Kästchen – sobald sie klein genug sind (sonst reicht das Bild)."""
        return self.quick_side() <= 110

    def quick_menu(self, anchor):
        pop = self.songs._popover(anchor)
        pop.set_position(Gtk.PositionType.BOTTOM)
        holder = vbox(spacing=6)
        for m in ("set_margin_top", "set_margin_bottom", "set_margin_start", "set_margin_end"):
            getattr(holder, m)(10)
        pop.set_child(Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, min_content_width=320, max_content_width=360,
                                         propagate_natural_height=True, propagate_natural_width=True, child=holder))
        holder.append(label("󰝚  schnellauswahl", "kp-head"))
        timer = {"id": 0}

        def apply():
            timer["id"] = 0
            self.quick_fill()
            return False

        def slider(name, key, lo, hi, cur, fmt, rebuild_pics=False):
            val = label(fmt(cur), "accent", xalign=1)

            def on(v):
                x = int(round(lo + v / 1000 * (hi - lo)))
                engine.set_setting(key, x)
                val.set_label(fmt(x))
                if timer["id"]:
                    GLib.source_remove(timer["id"])
                timer["id"] = GLib.timeout_add(120, apply)
            m = tui.Meter(1000, on, mark=False)
            m.set_value(int((cur - lo) / (hi - lo) * 1000))
            holder.append(hbox(label(name, hexpand=True), val))
            holder.append(m)
            # feine Schritte: − / + um genau eins
            step = lambda d: (on(max(0, min(1000, (round(lo + m.value / 1000 * (hi - lo)) + d - lo) / (hi - lo) * 1000))),
                              m.set_value(int((int(engine.setting(key)) - lo) / (hi - lo) * 1000)))
            holder.append(hbox(tui.Button("−", lambda: step(-1)), tui.Button("+", lambda: step(1)), spacing=6))
        slider("anzahl", "quick_n", 1, 50, self.quick_n(), lambda v: f"{v} titel")
        slider("größe der kästchen", "quick_side", 48, 200, self.quick_side(), lambda v: f"{v} px")
        slider("raster (punkte je seite)", "quick_res", 8, 64, self.quick_res(), lambda v: f"{v} × {v}")
        holder.append(label("kleine kästchen zeigen titel und künstler darunter (ab 110 px aus).", "dim", wrap=True))
        holder.append(tui.Button("zurücksetzen", lambda: (engine.set_setting("quick_n", None), engine.set_setting("quick_side", None),
                                                          engine.set_setting("quick_res", None), pop.popdown(), self.quick_fill()),
                                 danger=True))
        pop.popup()

    def quick_load(self):
        self.quick_busy.set_label("lädt …")

        def work():
            tr = self.p.music.quick_picks()
            pics = {}
            for t in tr[:50]:
                url = big_thumb(t.get("thumb"), 226)
                if url:
                    try:
                        pics[t["videoId"]] = (fetch_pixbuf(url), None)
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
        """Spaltenzahl folgt der Fensterbreite und der Kästchengröße."""
        if self.quick_panel.get_mapped():
            cols = self._quick_cols_now()
            if cols != self._quick_cols and self.quick_tracks:
                self.quick_fill()
        return True

    def _quick_cols_now(self):
        w = (self.get_width() - 30) if self.get_width() > 30 else 800       # Fensterbreite, nicht Kastenbreite (der blähte sich selbst auf)
        return max(1, (w - 40) // (self.quick_side() + 12))

    def quick_fill(self):
        grid = self.quick_grid
        tui.clear(grid)
        cols = self._quick_cols = self._quick_cols_now()
        side, res, names = self.quick_side(), self.quick_res(), self.quick_names()
        row = None
        tr = self.quick_tracks[:self.quick_n()]
        for i, t in enumerate(tr):
            pb, _x = getattr(self, "_quick_pics", {}).get(t["videoId"], (None, None))
            pic = DotThumb(side)
            pic.res = res
            pic.set_data(pb)
            b = Gtk.Button(child=pic, focus_on_click=False, halign=Gtk.Align.START, hexpand=False)
            b.add_css_class("qtile")
            b.set_size_request(side + 8, side + 8)
            b.set_tooltip_text(f"{t['title']} · {t['artist']}")
            b.connect("clicked", lambda _b, i=i, tr=tr: self.p.play_tracks(tr, start=i, src=("start", "schnellauswahl")))
            rc = Gtk.GestureClick(button=3)
            rc.connect("pressed", lambda g, n, x, y, b=b, t=t: self.songs.menu(b, x, y, t))
            b.add_controller(rc)
            cell = vbox(b, spacing=2)
            cell.set_halign(Gtk.Align.START)
            if names:
                for txt, cls in ((t["title"], ""), (t["artist"], "dim")):
                    l = label(txt, *([cls] if cls else []), ellipsize=True, xalign=0)
                    l.set_max_width_chars(max(6, side // 8))
                    l.set_size_request(side + 8, -1)
                    cell.append(l)
            if i % cols == 0:
                row = hbox(spacing=4)
                row.set_halign(Gtk.Align.START)
                grid.append(row)
            row.append(cell)

    # ---------- Anpassen-Popover ----------
    def build_customize(self):
        btn = tui.Button("󰏫", self.customize_menu, tooltip="Anpassen: Leiste unter „steuerung“, Bibliothek, Schnellauswahl")
        btn.set_valign(Gtk.Align.START)
        self.cust_btn = btn
        # Stift ganz rechts in der Leiste (nicht mehr in der Kopfzeile)
        box = self.ctl_opts.get_parent()
        opts = self.ctl_opts
        nxt = opts.get_prev_sibling()
        box.remove(opts)
        opts.set_hexpand(False)
        row = hbox(opts, label("", hexpand=True), btn, spacing=8)
        box.insert_child_after(row, nxt)
        self.ctl_opts_row = row

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
            holder.append(label("schnellauswahl (mehr: 󰕮 im kasten)", "kp-sub"))
            holder.append(hbox(label(f"{self.quick_n()} titel", hexpand=True),
                               tui.Button("−", lambda: (engine.set_setting("quick_n", max(1, self.quick_n() - 1)), self.quick_fill(), fill())),
                               tui.Button("+", lambda: (engine.set_setting("quick_n", min(50, self.quick_n() + 1)), self.quick_fill(), fill())),
                               spacing=6))
            holder.append(hbox(tui.Button("󰓃 klang / mixer öffnen", lambda: (pop.popdown(), self.sound_menu())),
                               tui.Button("zurücksetzen", lambda: (engine.set_setting("ctl_bar", None), engine.set_setting("lib_order", None),
                                                                   self.apply_ctl_bar(), self.apply_lib_order(), fill()), danger=True),
                               spacing=8))
        fill()
        pop.popup()
