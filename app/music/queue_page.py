# musicalist – Warteschlange (Teil von MusicWindow, siehe ui.py). Methoden greifen auf self (das Hauptfenster) zu.

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Graphene, Gtk, Pango, PangoCairo

import tui
from tui import label, hbox, vbox, esc
import engine
from engine import fmt
from jam import host_name as jam_host_name
from rows import track_row, coll_row, artist_link


class QueueMixin:

    # ---------- Warteschlange ----------
    def build_queue(self):
        page = vbox(spacing=8)
        page.set_margin_top(6)
        self.queue_panel = tui.Panel("warteschlange")
        self.queue_box = vbox(spacing=0)
        self.queue_empty = label("leer – unter ⁴suchen titel auswählen", "empty", xalign=0.5)
        self.queue_panel.body.append(hbox(label("", hexpand=True),
                                          self._sh(tui.Button("󰒝 mischen", self.p.shuffle_queue), "󰒝 mischen", "󰒝"),
                                          self._sh(tui.Button("󰐹 radio auffüllen", self.p.extend_radio),
                                                     "󰐹 radio auffüllen", "󰐹 radio"),
                                          self._sh(tui.Button("󰐒 als playlist", self.queue_to_playlist,
                                                              tooltip="Ganze Warteschlange in eine Playlist legen"),
                                                   "󰐒 als playlist", "󰐒"),
                                          tui.Button("leeren", lambda: self.p.clear(), danger=True)))
        self.queue_more_top = self.more_button(lambda: self.queue_expand(past=True))
        self.queue_more_bottom = self.more_button(lambda: self.queue_expand())
        self.queue_limit, self.queue_all_past = self.QUEUE_WINDOW, False
        self.queue_panel.body.append(self.queue_more_top)
        self.queue_panel.body.append(self.queue_box)
        self.queue_panel.body.append(self.queue_more_bottom)
        self.queue_panel.body.append(self.queue_empty)
        # Rückgängig-Leiste (3 s nach dem Entfernen)
        self.undo_lbl = label("", hexpand=True, ellipsize=True)
        self.undo_bar = hbox(self.undo_lbl, tui.Button("rückgängig", self.undo_remove_click), spacing=10)
        self.undo_bar.add_css_class("loginbox")
        self.undo_bar.set_visible(False)
        self._undo_timer = 0
        self.jam_panel = self.build_jam()          # sitzt auf Seite „jetzt“ (ui.py)
        page.append(self.undo_bar)
        page.append(self.queue_panel)
        self.add_page("queue", page)

    def remove_undo(self, t):
        """Aus der Warteschlange entfernen und kurz „rückgängig“ anbieten."""
        self.p.remove(self._qi(t))
        lr = self.p.last_removed
        if lr:
            self.undo_lbl.set_label(f"„{lr[0].get('title') or '?'}“ entfernt")
            self.undo_bar.set_visible(True)
            if self._undo_timer:
                GLib.source_remove(self._undo_timer)
            self._undo_timer = GLib.timeout_add(3000, self._undo_hide)

    def _undo_hide(self):
        self._undo_timer = 0
        self.undo_bar.set_visible(False)
        return False

    def undo_remove_click(self):
        t = self.p.undo_remove()
        if t:
            self.say(f"„{t.get('title') or '?'}“ zurückgeholt")
        self._undo_hide()

    # ---------- Jam (jam.py) ----------
    def build_jam(self):
        panel = tui.Panel("󰀂 marmelade")
        self.jam_box = vbox(spacing=6)
        panel.body.append(self.jam_box)
        self.jam_form = None
        self.jam_remote = None          # letzter Zustand des Gastgebers (als Gast)
        j = self.p.jam
        if j is not None:
            j.say = self.say
            c = tui.colors()

            def hx(name, fb):
                v = c.get(name)
                return "#%02x%02x%02x" % (int(v.red * 255), int(v.green * 255), int(v.blue * 255)) if v else fb
            j.colors = (hx("background", "#faf8ff"), hx("on_background", hx("foreground", "#1b1b21")), hx("primary", "#4c5c92"))
            j.listeners.append(self.update_jam)
            j.watch()
        self.update_jam()
        GLib.timeout_add_seconds(3, self._jam_poll)
        return panel

    def _jam_poll(self):
        j = self.p.jam
        if j is not None and j.joined is not None and self.get_visible():
            self.jam_remote = j.remote          # liest jam.py im Hintergrund mit (auch für „läuft“)
            self.update_jam()
        return True

    def update_jam(self):
        j = self.p.jam
        box = getattr(self, "jam_box", None)
        if box is None:
            return False
        tui.clear(box)
        if j is None:
            box.append(label("marmelade nicht verfügbar", "dim"))
            return False
        jm = __import__("jam")
        collapsed = bool(engine.setting("jam_collapsed"))
        if not j.hosting and j.joined is None:
            for oname, o in list(j.offers.items()):            # gekoppeltes Gerät hat eine Marmelade gestartet → mitmachen
                def take(oname=oname, o=o):
                    self.say(f"tritt der marmelade von {o['who']} bei …")

                    def done(res):
                        if isinstance(res, Exception):
                            self.say(f"beitreten ging nicht: {res}")
                        else:
                            self.say(f"󰀂 du spielst jetzt mit {res}")
                        self.update_jam()
                    tui.background(lambda: j.accept_offer(oname), done=done)
                box.append(hbox(label("󰀂", "accent"), label(f"{o['who']} hat eine marmelade gestartet", hexpand=True, ellipsize=True),
                                tui.Button("mitmachen", take),
                                tui.Button("✕", lambda oname=oname: (j.offers.pop(oname, None), self.update_jam()), danger=True, tooltip="ignorieren")))

        def fold():
            engine.set_setting("jam_collapsed", not collapsed)
            self.update_jam()
        fold_btn = tui.Button("󰅀" if collapsed else "󰅃", fold, tooltip="marmelade auf-/zuklappen")
        if j.hosting:
            n_guests = len(j._groups())          # nach Person gezählt: Geräte desselben Kontos = eine Person, eigene Geräte gar nicht
            head = hbox(label(jm.jam_title(), "accent", ellipsize=True, hexpand=True),
                        label(f"code {j.code[:3]} {j.code[3:]} · " + (f"{n_guests} gäste" if n_guests else "noch keine gäste"), "dim"),
                        tui.Button("󰏫", self.jam_rename_form, tooltip="marmelade umbenennen"), fold_btn)
            box.append(head)
            if getattr(self, "jam_rename", None) is not None:
                box.append(self.jam_rename)
            import time as _t
            from rows import who_chip
            for key, k in list(j.knocks.items()):
                if k["state"] != "wait" or _t.time() - k["at"] > 120:
                    continue
                box.append(hbox(label("󰌹", "accent"), who_chip(k["name"]), label("möchte beitreten", hexpand=True),
                                tui.Button("reinlassen", lambda key=key: (j.answer_knock(key, True), self.update_jam())),
                                tui.Button("✕", lambda key=key: (j.answer_knock(key, False), self.update_jam()), danger=True,
                                           tooltip="ablehnen")))
            if collapsed:
                return False
            url = j.url() if j.lan_ok else None
            qr = __import__("jam").qr_matrix(url) if url else None
            info = vbox(spacing=2)
            info.append(label("code", "dim"))
            big = label(j.code, "accent")
            big.set_markup(f"<span size='xx-large' weight='bold'>{j.code[:3]} {j.code[3:]}</span>")
            info.append(big)
            info.append(label("app (handy oder pc): marmelade beitreten → code – klappt überall, auch übers internet. "
                              "browser ohne app: qr-code, nur im selben wlan.", "dim", wrap=True))
            info.append(label("internet: " + (j.net_status or "startet …"), "accent" if j.net_status == "verbunden" else "dim"))
            if url:
                a = label(url.split("/?")[0], "dim")
                a.set_selectable(True)
                info.append(a)
            info.set_hexpand(True)
            row = hbox(spacing=16)
            if qr:
                n = len(qr)
                cell = max(3, 168 // n)
                area = Gtk.DrawingArea(content_width=n * cell, content_height=n * cell)
                # Farben des Designs, aber in der Richtung, die jede Kamera liest: dunkle Module auf heller Fläche
                # (die hellere von Vordergrund/Hintergrund ist die Fläche) – nie reines Weiß, nie hell auf dunkel
                dark, light = __import__("jam").qr_palette(tui.colors().get("foreground"), tui.colors().get("background"))

                def draw(_a, cr, _w, _h, m=qr, cell=cell, dark=dark, light=light):
                    cr.set_source_rgb(light.red, light.green, light.blue) if light is not None else cr.set_source_rgb(1, 1, 1)
                    cr.paint()
                    cr.set_source_rgb(dark.red, dark.green, dark.blue) if dark is not None else cr.set_source_rgb(0, 0, 0)
                    for y, line in enumerate(m):
                        for x, on in enumerate(line):
                            if on:
                                cr.rectangle(x * cell, y * cell, cell, cell)
                    cr.fill()
                area.set_draw_func(draw)
                area.set_valign(Gtk.Align.START)
                row.append(area)
            row.append(info)
            box.append(row)
            if not j.guests:
                box.append(label("noch keine gäste", wrap=True))
            for key, g in sorted(j.guests.items(), key=lambda kv: (kv[1].get("name") or "").lower()):
                admin = j.is_admin(key)
                tr = bool(g.get("dev")) and g["dev"] in jm.trusted()
                row = hbox(label("󰓎" if j.is_ultra(key) else "󰌆" if admin else "󰀄", "accent" if admin else "dim"),
                           __import__("rows").who_chip(g.get("name") or "gast"), label("", hexpand=True),
                           label(f"{g.get('added', 0)} titel" if g.get("added") else "", "dim"),
                           label("gemerkt" if tr else "", "accent"))
                row.append(tui.Button("rechte weg" if admin else "󰌆 rechte", lambda k=key, a=admin: (j.set_admin(k, not a), self.update_jam()),
                                      tooltip="gastgeber-rechte: überspringen, pause, titel entfernen"))
                ultra = j.is_ultra(key)
                row.append(tui.Button("ultra weg" if ultra else "󰓎 ultra", lambda k=key, u=ultra: (j.set_ultra(k, not u), self.update_jam()),
                                      tooltip="ultra: alle rechte wie du – zusätzlich zu überspringen/pause/entfernen auch titel sofort\n"
                                              "abspielen (ein klick) und in der warteschlange anspringen. gilt nur für diese marmelade."))
                if g.get("dev"):
                    row.append(tui.Button("vergessen" if tr else "merken", lambda k=key, t=tr: (j.trust(k, not t), self.update_jam()),
                                          tooltip="gerät merken: hat in jeder deiner marmeladen sofort rechte"))
                row.append(tui.Button("entfernen", lambda k=key: (j.kick(k), self.update_jam()), danger=True,
                                      tooltip="aus der marmelade entfernen (kann bis zum ende dieser marmelade nicht wieder beitreten)"))
                box.append(row)
            for e in j.events[:3]:
                box.append(label(f"‣ {e}", "dim", ellipsize=True))
            box.append(hbox(label(j.error or f"für browser-gäste im wlan: port {__import__('jam').PORT}/tcp in der firewall "
                                  f"öffnen (sudo ufw allow {__import__('jam').PORT}/tcp)", "dim", wrap=True, hexpand=True),
                            tui.Button("marmelade beenden", lambda: (j.stop(), self.say("marmelade beendet")), danger=True)))
        elif j.joined is not None:
            st = self.jam_remote
            via = " · übers internet" if j.joined.get("net") else ""
            title = (st or {}).get("title") or f"marmelade von {j.joined['host_name']}"
            admin = j.am_admin(st)
            ultra = j.am_ultra(st)
            now = (st or {}).get("now")
            box.append(hbox(label(f"● {title}{via}", "accent", ellipsize=True, hexpand=True),
                            label(f"läuft: {now.get('t')}" if collapsed and now else "", "dim", ellipsize=True), fold_btn))

            def ctl(op, vid=None):
                def done(res):
                    if isinstance(res, Exception):
                        self.say(f"marmelade: {res}", error=True)
                    j.poke()
                    GLib.timeout_add(1800 if j.joined and j.joined.get("net") else 600, lambda: self._jam_poll() and False)
                tui.background(j.ctl_remote, op, vid, done=done)
            if admin:
                playing = bool((st or {}).get("playing"))
                box.append(hbox(label("󰓎 du bist ultra: alle rechte des gastgebers – ein klick spielt sofort" if ultra
                                      else "󰌆 du hast gastgeber-rechte", "accent", hexpand=True),
                                tui.Button("󰒮", lambda: ctl("prev"), tooltip="zurück"),
                                tui.Button("󰏤" if playing else "󰐊", lambda: ctl("toggle"), tooltip="pause/weiter"),
                                tui.Button("󰒭", lambda: ctl("next"), tooltip="überspringen")))
            if collapsed:
                return False
            if st is None:
                box.append(label("wartet auf den stand vom gastgeber …", "dim"))
            else:
                if now:
                    box.append(label(f"läuft: {now.get('t')} · {now.get('a')}", ellipsize=True))
                ppl = st.get("people") or [{"n": n, "a": False} for n in st.get("guests") or []]
                if ppl:
                    from rows import who_chip
                    pr = hbox(label("gäste:", "dim"), spacing=6)
                    for p_ in ppl[:12]:
                        pr.append(who_chip(p_["n"], " 󰓎" if p_.get("u") else " 󰌆" if p_.get("a") else ""))
                    box.append(pr)
                box.append(label("„läuft“ und die warteschlange unten zeigen, was beim gastgeber spielt.", "dim", wrap=True))
            box.append(hbox(label("abspielen spielt sofort beim gastgeber (du bist ultra); „als nächstes“ und „+“ reihen ein." if ultra else
                                  "abspielen, „als nächstes“ und „+“ schicken titel jetzt in die marmelade.", "dim", wrap=True,
                                  hexpand=True),
                            tui.Button("verlassen", lambda: (j.leave(), setattr(self, "jam_remote", None)), danger=True)))
        else:
            box.append(hbox(tui.Button("󰀂 marmelade starten", self.jam_start,
                                       tooltip="Andere im WLAN (Handy-App oder Browser) können Titel hinzufügen"),
                            tui.Button("󰌹 marmelade beitreten", self.jam_join_form), label("", hexpand=True)))
            if self.jam_form is not None:
                box.append(self.jam_form)
        return False

    def jam_rename_form(self):
        if getattr(self, "jam_rename", None) is not None:
            self.jam_rename = None
            self.update_jam()
            return
        jm = __import__("jam")
        e = tui.Entry(f"marmelade von {jm.host_name()}", text=engine.setting("jam_title") or "")

        def save(*_):
            self.p.jam.rename(e.get_text())
            self.jam_rename = None
            self.say(f"marmelade heißt jetzt „{jm.jam_title()}“")
            self.update_jam()
        e.connect("activate", save)
        self.jam_rename = hbox(e, tui.Button("speichern", save), tui.Button("abbrechen", self.jam_rename_form))
        self.update_jam()

    def jam_start(self):
        j = self.p.jam
        if j.start():
            self.say(f"marmelade läuft – code {j.code}")
        else:
            self.say(f"marmelade startet nicht: {j.error}", error=True)
        self.update_jam()

    def jam_join_form(self):
        j = self.p.jam
        form = vbox(spacing=6)
        found_box = vbox(spacing=4)
        found_box.append(label("sucht marmeladen im wlan …", "dim"))
        name = tui.Entry("dein name", text=engine.setting("jam_name") or jam_host_name())
        code = tui.Entry("code (6 zeichen)", width=10)
        addr = tui.Entry("adresse im wlan (optional)")
        picked = {"f": None}

        def join():
            f = picked["f"]
            more = list(f[3]) if f and len(f) > 3 else []
            host, port = (f[1], f[2]) if f else (addr.get_text().split(":")[0].strip(), (addr.get_text().split(":") + [""])[1] or 37530)
            c = __import__("jam").norm_code(code.get_text())
            if len(c) != 6:
                self.say("der code hat 6 zeichen", error=True)
                return
            engine.set_setting("jam_name", name.get_text().strip())

            def go(host=host, port=port, c=c, nm=name.get_text(), more=more):
                # im WLAN gefunden/angegeben → direkt; sonst (oder wenn das WLAN Geräte trennt) übers Internet
                lan_err = None
                if host:
                    try:
                        return j.join(host, port, c, nm, more)
                    except Exception as e:  # noqa: BLE001
                        lan_err = e
                        if str(e) in ("code falsch", "kicked"):
                            raise
                try:
                    return j.join_net(c, nm)
                except Exception as e:  # noqa: BLE001
                    raise RuntimeError(f"wlan: {lan_err} · internet: {e}" if lan_err else str(e)) from None

            def done(res):
                if isinstance(res, Exception):
                    self.say(f"marmelade: {res}", error=True)
                else:
                    self.jam_form = None
                    self.say(f"󰀂 in der marmelade von {res}")
                    self.update_jam()
            tui.background(go, done=done)

        state = label("", "accent", wrap=True)
        state.set_visible(False)

        def show_state(txt):
            state.set_label(txt or "")
            state.set_visible(bool(txt))

        def tap(f):
            """Gefundene Marmelade anklicken: mit Code gleich beitreten, sonst anklopfen (Gastgeber lässt rein)."""
            picked["f"] = f
            if len(__import__("jam").norm_code(code.get_text())) == 6:
                join()
                return
            engine.set_setting("jam_name", name.get_text().strip())
            show_state(f"klopft bei „{f[0]}“ an …")

            def done(res):
                show_state(None)
                if isinstance(res, Exception):
                    self.say(f"marmelade: {res}", error=True)
                else:
                    self.jam_form = None
                    self.say(f"󰀂 in der marmelade von {res}")
                    self.update_jam()
            tui.background(j.knock_join, f, name.get_text(),
                           lambda s: GLib.idle_add(lambda: show_state(s) and False), done=done)

        def found(res):
            tui.clear(found_box)
            res = [] if isinstance(res, Exception) else res
            if not res:
                found_box.append(label("keine marmelade im wlan gefunden – mit dem code geht es übers internet", "dim"))
                return
            found_box.append(label("im wlan – anklicken zum beitreten (ohne code klopfst du an, der gastgeber lässt dich rein):", "dim", wrap=True))
            for f in res:
                found_box.append(tui.Button(f"󰀂 {f[0]}", lambda f=f: tap(f), tooltip="beitreten"))
        tui.background(j.discover, done=found)
        form.append(found_box)
        form.append(state)
        form.append(hbox(name, code))
        form.append(addr)
        form.append(hbox(tui.Button("beitreten", join), tui.Button("abbrechen", lambda: (setattr(self, "jam_form", None),
                                                                                         self.update_jam())),
                         label("", hexpand=True)))
        code.connect("activate", lambda *_: join())
        self.jam_form = form
        self.update_jam()

    QUEUE_WINDOW = 100          # so viele Zeilen werden gebaut (jede kostet ~1,5 ms und ~0,3 MB), der Rest auf Wunsch

    def rows_chunked(self, box, items, make, first=60, step=100):
        """Lange Listen portionsweise bauen: erst `first` Zeilen, der Rest über „weitere N anzeigen“.
        make(i, item) → Zeile. (Eine Zeile kostet ~1,5 ms: 500 Titel am Stück ließen das Fenster ruckeln.)"""
        state = {"i": 0, "btn": None}

        def more():
            if state["btn"] is not None:
                box.remove(state["btn"])
                state["btn"] = None
            lo = state["i"]
            hi = min(len(items), lo + (first if lo == 0 else step))
            for i in range(lo, hi):
                box.append(make(i, items[i]))
            state["i"] = hi
            if hi < len(items):
                b = self.more_button(more)
                b.set_label(f"↓ {len(items) - hi} weitere anzeigen")
                b.set_visible(True)
                box.append(b)
                state["btn"] = b
        more()

    @staticmethod
    def more_button(fn):
        b = Gtk.Button(focus_on_click=False)
        b.add_css_class("rowhead")
        b.set_visible(False)
        # Aktion im Leerlauf: sie entfernt/ersetzt den Knopf selbst, das darf nicht mitten in seinem Signal passieren
        b.connect("clicked", lambda *_: GLib.idle_add(lambda: (fn(), False)[1]))
        return b

    def queue_expand(self, past=False):
        if past:
            self.queue_all_past = True
        else:
            self.queue_limit += self.QUEUE_WINDOW
        self.update_queue()

    def queue_range(self):
        """(von, bis) der angezeigten Zeilen: ab kurz vor dem laufenden Titel, QUEUE_WINDOW Stück (wachsend)."""
        n, cur = len(self.p.queue), max(0, self.p.index)
        lo = 0 if self.queue_all_past else max(0, cur - 5)
        hi = min(n, max(lo + self.queue_limit, cur + 20))
        return lo, hi

    def update_queue(self):
        q = self.p.queue
        total = sum(t["duration"] or 0 for t in q)
        self.queue_panel.set_title(f"warteschlange <span alpha='60%'>{len(q)} titel · {fmt(total)}</span>",
                                   markup=True)
        self.queue_empty.set_visible(not q)

        def make(item):
            i, t = item
            row = track_row(t, lambda r=None: self.p.jump(self._qi(t)),
                            [("↑", "Nach oben", lambda: self.p.move(self._qi(t), self._qi(t) - 1)),
                             ("↓", "Nach unten", lambda: self.p.move(self._qi(t), self._qi(t) + 1)),
                             ("✕", "Entfernen", lambda: self.remove_undo(t))],
                            menus=self.songs, extra=lambda: self.queue_extra(t))
            self.queue_drag(row, t)
            return row

        def update(row, item):
            i, t = item
            playing = i == self.p.index
            row.mark.set_label("▶" if playing else f"{i + 1}")
            (row.add_css_class if playing else row.remove_css_class)("playing")
            (row.add_css_class if i < self.p.index else row.remove_css_class)("past")
        lo, hi = self.queue_range()
        tui.sync_rows(self.queue_box, list(enumerate(q))[lo:hi], lambda it: id(it[1]), make, update)
        self.queue_more_top.set_visible(lo > 0)
        self.queue_more_top.set_label(f"↑ {lo} bereits gespielt anzeigen")
        self.queue_more_bottom.set_visible(hi < len(q))
        self.queue_more_bottom.set_label(f"↓ {len(q) - hi} weitere anzeigen")

        if getattr(self, "tv_on", False):
            self.tv.refresh_queue()
        # "als nächstes" auf der Jetzt-Seite
        nxt = q[self.p.index + 1:self.p.index + 1 + self.upnext_n] if self.p.index >= 0 and self.upnext_n else []
        self.upnext_panel.set_visible(bool(nxt))
        tui.sync_rows(self.upnext, nxt, id, lambda t: track_row(t, lambda: self.p.jump(self._qi(t)), [],
                                                                 menus=self.songs, extra=lambda: self.queue_extra(t)),
                      lambda r, t: r.mark.set_label("›"))

    def queue_drag(self, row, t):
        """Zeile mit der Maus verschieben: ziehen und auf eine andere Zeile loslassen (Linie zeigt das Ziel).
        Die Controller kosten pro Zeile ~0,3 ms – sie werden erst beim ersten Überfahren angehängt."""
        hover = Gtk.EventControllerMotion()
        state = {"armed": True}

        def finish():
            # Erst im Leerlauf: ein Controller darf sich nicht aus seinem eigenen Signal entfernen (GTK stürzt ab)
            if row.get_root() is not None:
                row.remove_controller(hover)
                self._queue_drag_attach(row, t)
            return False

        def attach(*_):
            if state["armed"]:
                state["armed"] = False
                GLib.idle_add(finish)
        hover.connect("enter", attach)
        row.add_controller(hover)

    def _queue_drag_attach(self, row, t):
        src = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        src.set_button(1)
        src.connect("prepare", lambda s, x, y: Gdk.ContentProvider.new_for_value(str(self._qi(t))))

        def begin(s, drag):
            Gtk.DragIcon.set_from_paintable(drag, Gtk.WidgetPaintable(widget=row), 12, 12)
            row.add_css_class("dragging")
        src.connect("drag-begin", begin)
        src.connect("drag-end", lambda *_: row.remove_css_class("dragging"))
        row.add_controller(src)
        dst = Gtk.DropTarget.new(str, Gdk.DragAction.MOVE)

        def where(y):
            return "dropat-end" if y > row.get_height() / 2 else "dropat"

        def motion(d, x, y):
            for c in ("dropat", "dropat-end"):
                row.remove_css_class(c)
            row.add_css_class(where(y))
            return Gdk.DragAction.MOVE
        dst.connect("motion", motion)
        dst.connect("enter", motion)
        dst.connect("leave", lambda *_: [row.remove_css_class(c) for c in ("dropat", "dropat-end")])

        def drop(d, val, x, y):
            for c in ("dropat", "dropat-end"):
                row.remove_css_class(c)
            try:
                a, b = int(val), self._qi(t)
            except ValueError:
                return False
            if a < 0 or b < 0 or a == b:
                return False
            if where(y) == "dropat-end" and a > b:
                b += 1
            elif where(y) == "dropat" and a < b:
                b -= 1
            self.p.move(a, b)
            return True
        dst.connect("drop", drop)
        row.add_controller(dst)

    def queue_reset_window(self):
        self.queue_limit, self.queue_all_past = self.QUEUE_WINDOW, False

    def queue_extra(self, t):
        i = self._qi(t)
        out = []
        if i > self.p.index + 1:
            out.append(("»", "als nächstes (vorziehen)", lambda: self.p.move(self._qi(t), self.p.index + 1)))
        if i > 0:
            out.append(("↑", "nach oben", lambda: self.p.move(self._qi(t), self._qi(t) - 1)))
        if 0 <= i < len(self.p.queue) - 1:
            out.append(("↓", "nach unten", lambda: self.p.move(self._qi(t), self._qi(t) + 1)))
        if i != self.p.index:
            out.append(("󰐊", "hierhin springen", lambda: self.p.jump(self._qi(t))))
        out.append(("✕", "aus der warteschlange", lambda: self.remove_undo(t), True))
        return out

    def queue_to_playlist(self):
        rest = self.p.queue[max(0, self.p.index):] if self.p.index >= 0 else self.p.queue
        self.songs.picker(self.queue_panel, rest[:200])

    def _qi(self, t):
        for i, x in enumerate(self.p.queue):
            if x is t:
                return i
        return -1
