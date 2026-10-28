# musicalist – Bibliothek: Konto, Playlists, Künstler, Detailseiten, Rückblick, lokale Musik (Teil von MusicWindow, siehe ui.py). Methoden greifen auf self (das Hauptfenster) zu.
import os, random

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Graphene, Gtk, Pango, PangoCairo

import tui
from tui import label, hbox, vbox, esc
import engine
from engine import fmt
from rows import track_row, coll_row, artist_link


class LibraryMixin:

    # ---------- Bibliothek ----------
    def build_lib(self):
        self.lib_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, transition_duration=120)
        home = vbox(spacing=8)
        home.set_margin_top(6)
        self.login_panel = tui.Panel("󰀄 konto")
        self.login_body = vbox(spacing=8)
        self.login_body.add_css_class("loginbox")
        self.login_panel.body.append(self.login_body)
        home.append(self.login_panel)
        self.coll_panel = tui.Panel("sammlung")
        self.coll = vbox(spacing=0)
        self.coll_panel.body.append(self.coll)
        home.append(self.coll_panel)
        self.local_panel = tui.Panel("󰉋 lokale musik")
        self.local_box = vbox(spacing=0)
        self.local_panel.body.append(self.local_box)
        self.local_panel.set_visible(False)
        home.append(self.local_panel)
        self.stat_panel = tui.Panel("󰄨 rückblick")
        self.stat_panel.body.append(coll_row("󰄨", "was ich gehört habe", "",
                                             lambda: self.open_detail("stats", "")))
        home.append(self.stat_panel)
        self.lib_stack.add_named(home, "home")

        detail = vbox(spacing=8)
        detail.set_margin_top(6)
        self.detail_panel = tui.Panel("")
        self.detail_box = vbox(spacing=0)
        self.detail_panel.body.append(hbox(
            self._sh(tui.Button("‹ zurück", self.lib_home), "‹ zurück", "‹"),
            label("", hexpand=True),
            self._sh(tui.Button("󰐊 abspielen", lambda: self.p.play_tracks(self.detail_tracks)), "󰐊 abspielen", "󰐊"),
            self._sh(tui.Button("󰒝 zufällig", self.detail_shuffle),
                       "󰒝 zufällig", "󰒝"),
            self._sh(tui.Button("+ alle anhängen", lambda: [self.p.add(t) for t in self.detail_tracks]),
                       "+ alle anhängen", "+ alle"), spacing=8))
        self.detail_tools = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=8, row_spacing=6,
                                        max_children_per_line=8, homogeneous=False, halign=Gtk.Align.START)
        self.detail_tools.add_css_class("opts")
        self.detail_tools.set_margin_top(6)
        self.detail_tools.set_margin_bottom(6)
        self.detail_panel.body.append(self.detail_tools)
        self.detail_panel.body.append(self.detail_box)
        detail.append(self.detail_panel)
        self.lib_stack.add_named(detail, "detail")
        self.add_page("lib", self.lib_stack)

    def refresh_account(self):
        authed = os.path.exists(engine.BROWSER_JSON)
        self.p.music.reset()
        if not authed:
            self.account = None
            self.fill_login()
            return
        self.acct_lbl.set_label("󰀄 …")
        tui.background(engine.account_name, done=self.account_done)

    def account_done(self, res):
        if isinstance(res, Exception):
            self.account = None
            if not self.login_expired and not getattr(self, "_relogin_tried", False):
                # abgelaufen: leise im Browser-Profil nachsehen – ist man dort noch angemeldet, geht es von allein weiter
                self._relogin_tried = True
                self.login_expired = True
                tui.background(engine._login_once, done=lambda r: self.account_done(r))
                return
            self.login_expired = True
            self.say("anmeldung abgelaufen – einstellungen (,) → anmeldung neu einlesen, "
                     "vorher in zen/firefox bei music.youtube.com einloggen", error=True, seconds=20)
        else:
            self.account = res
            self.login_expired = False
            self._relogin_tried = False
        self.fill_login()
        if self.account:
            self.load_library()

    def fill_login(self):
        self.fill_settings_account()
        tui.clear(self.login_body)
        if self.account:
            # Kontoname wird bewusst nirgends angezeigt – nur der Status
            self.acct_lbl.set_label("󰀄 ●")
            self.acct_lbl.set_tooltip_text("Angemeldet")
            self.login_body.append(hbox(label("● angemeldet", "accent", hexpand=True),
                                        tui.Button("neu einlesen", self.login),
                                        tui.Button("abmelden", self.do_logout, danger=True), spacing=8))
        elif self.login_expired:
            self.acct_lbl.set_label("󰀄 !")
            self.acct_lbl.set_tooltip_text("Anmeldung abgelaufen – Einstellungen → Anmeldung neu einlesen")
            self.login_body.append(label("⚠ die anmeldung ist abgelaufen. in zen/firefox bei music.youtube.com "
                                         "einloggen, dann hier neu einlesen.", "err", wrap=True))
            self.login_body.append(hbox(tui.Button("󰑐 anmeldung neu einlesen", self.login), spacing=8))
            tui.clear(self.coll)
            self.coll_panel.set_visible(False)
        else:
            self.acct_lbl.set_label("󰀄 ○")
            self.acct_lbl.set_tooltip_text("Nicht angemeldet")
            self.login_body.append(label(
                "melde dich in zen oder firefox bei music.youtube.com an und klicke dann hier. der player übernimmt die "
                "anmeldung aus dem browser – dein passwort sieht er nie. ohne anmeldung gehen suche und abspielen trotzdem.",
                "dim", wrap=True))
            self.login_body.append(hbox(tui.Button("󰈹 mit zen/firefox anmelden", self.login), spacing=8))
            tui.clear(self.coll)
            self.coll_panel.set_visible(False)

    def login(self):
        self.say("lese anmeldung aus dem browser … (falls nötig öffnet sich der browser zum einloggen)", seconds=240)

        def done(res):
            if isinstance(res, Exception):
                self.say(str(res), error=True, seconds=15)
                return
            self.say("angemeldet")
            self.p.music.reset()
            self.p.resolver.reset()
            self.account_done(res)
        tui.background(lambda: engine.login_from_browser(
            progress=lambda t: GLib.idle_add(lambda: self.say(t, seconds=240) and False)), done=done)

    def do_logout(self):
        engine.logout()
        self.login_expired = False
        self.p.music.reset()
        self.p.resolver.reset()
        self.account = None
        self.fill_login()
        self.say("abgemeldet")

    def load_library(self):
        self.coll_panel.set_visible(True)
        tui.clear(self.coll)
        self.coll.append(coll_row("󰋑", "lieblingssongs", "", lambda: self.open_detail("playlist", "LM")))
        self.coll.append(coll_row("󰋚", "verlauf", "", lambda: self.open_detail("history", "")))
        self.coll.append(coll_row("󰠃", "abonnierte künstler", "", lambda: self.open_detail("subs", "")))
        self.coll.append(coll_row("󰎈", "neu von deinen künstlern", "", lambda: self.open_detail("new", "")))
        self.coll.append(coll_row("󰦖", "podcasts", "", lambda: self.open_detail("podlib", "")))
        new_pl = tui.Button("󰐒 neue playlist", lambda: self.new_playlist_popover(new_pl),
                            tooltip="Leere Playlist in YouTube Music anlegen")
        new_pl.set_halign(Gtk.Align.START)
        new_pl.set_margin_top(6)
        self.coll_newpl = new_pl

        def done(res):
            if isinstance(res, Exception):
                self.say(f"bibliothek: {engine.explain(res)}", error=True)
                return
            self.editable_ids = {pl["id"] for pl in res if pl["id"] not in ("LM", "SE")}
            self.lib_playlists = res
            for pl in res:
                if pl["id"] == "LM":
                    continue
                self.coll.append(coll_row("󰲸", pl["title"], str(pl["count"] or ""),
                                          lambda i=pl["id"]: self.open_detail("playlist", i)))
            self.coll.append(self.coll_newpl)
        tui.background(self.p.music.library, done=done)

    def new_playlist_popover(self, anchor):
        pop = self.songs._popover(anchor)
        box = vbox(spacing=4)
        pop.set_child(box)
        box.append(label("󰐒  neue playlist", "kp-head"))
        entry = tui.Entry("name …")
        box.append(entry)

        def create():
            name = entry.get_text().strip()
            if not name:
                return
            pop.popdown()
            self.say(f"lege „{name}“ an …")

            def done(res):
                if isinstance(res, Exception):
                    self.say(f"playlist anlegen: {engine.explain(res)}", error=True)
                    return
                self.say(f"playlist „{name}“ angelegt")
                self.load_library()
            tui.background(self.p.music.create_playlist, name, [], done=done)
        entry.connect("activate", lambda *_: create())
        pop.popup()
        entry.grab_focus()

    def open_artist(self, t):
        """Künstlerseite zum Titel t – ohne gespeicherte ID per Suche nach dem Namen."""
        if not t:
            return
        if t.get("artistId"):
            self.open_detail("artist", t["artistId"])
            return
        self.say(f"suche künstler {t['artist']} …")

        def done(res):
            if isinstance(res, Exception) or not res:
                self.say(f"künstler nicht gefunden: {t['artist']}", error=True)
                return
            t["artistId"] = res
            self.open_detail("artist", res)
        tui.background(self.p.music.artist_id, t["artist"], done=done)

    def fill_artist(self, ident, d):
        """Künstlerseite: Top-Titel, dann Alben, Singles, ähnliche Künstler."""
        self.detail_names[("artist", ident)] = d["name"]
        tracks = d["tracks"]
        self.detail_tracks = tracks
        sub = f" · {d['subscribers']} abonnenten" if d["subscribers"] else ""
        self.detail_panel.set_title(f"󰠃 {esc(d['name'])} <span alpha='60%'>künstler{esc(sub)}</span>", markup=True)
        box = self.detail_box
        btns = hbox(spacing=8)
        if d.get("radio"):
            btns.append(tui.Button("󰐹 radio", lambda: self.play_playlist_id(d["radio"], "radio"),
                                   tooltip="Mix aus diesem Künstler und ähnlicher Musik"))
        if d.get("all_songs"):
            btns.append(tui.Button("alle titel ›", lambda: self.open_detail("playlist", d["all_songs"])))
        if d.get("channelId") and self.account is not None:
            sub = tui.Button("", None)
            state = {"on": d.get("subscribed")}

            def paint():
                sub.set_label("󰄬 abonniert" if state["on"] else "󰐕 abonnieren")
                (sub.add_css_class if state["on"] else sub.remove_css_class)("on")
            paint()

            def toggle(*_):
                want = not state["on"]
                sub.set_sensitive(False)

                def done(res):
                    sub.set_sensitive(True)
                    if isinstance(res, Exception):
                        self.say(f"abonnieren: {engine.explain(res)}", error=True)
                        return
                    state["on"] = want
                    paint()
                    self.say(("abonniert: " if want else "abo beendet: ") + d["name"])
                tui.background(self.p.music.subscribe, d["channelId"], want, done=done)
            sub.connect("clicked", toggle)
            btns.append(sub)
        box.append(btns)

        def head(txt):
            h = label(txt, "accent", xalign=0)
            h.set_margin_top(10)
            box.append(h)
        if tracks:
            head("top-titel")
        for i, t in enumerate(tracks):
            row = track_row(t, lambda i=i: self.p.play_tracks(tracks, start=i),
                            [("+", "An Warteschlange anhängen", lambda t=t: self.p.add(t)),
                             ("»", "Als nächstes spielen", lambda t=t: self.p.add(t, next_=True))],
                            menus=self.songs)
            row.mark.set_label(str(i + 1))
            box.append(row)
        for key, title, glyph, kind in (("albums", "alben", "󰀥", "album"), ("singles", "singles & eps", "󰀥", "album"),
                                        ("related", "ähnliche künstler", "󰠃", "artist")):
            if d.get(key):
                head(title)
                for c in d[key]:
                    box.append(coll_row(glyph, c["title"], c["sub"], lambda k=kind, i=c["id"]: self.open_detail(k, i)))

    def play_playlist_id(self, pid, name):
        def done(res):
            if isinstance(res, Exception) or not res[1]:
                self.say(f"{name}: nichts gefunden", error=True)
                return
            self.p.play_tracks(res[1], start=0)
        tui.background(self.p.music.watch_list, pid, done=done)

    COLL_KINDS = {"subs": ("󰠃 abonnierte künstler", "artist", "󰠃"),
                  "podlib": ("󰦖 podcasts", "podcast", "󰦖"),
                  "new": ("󰎈 neu von deinen künstlern", "album", "󰀥")}
    DETAIL_NAMES = {"album": "album", "artist": "künstler", "history": "verlauf", "podcast": "podcast",
                    "subs": "abos", "podlib": "podcasts", "new": "neu", "local": "lokal", "stats": "rückblick"}
    LOCAL_SHOWN, LOCAL_QUEUE = 150, 300

    def detail_shuffle(self):
        pool = self.detail_pool or self.detail_tracks
        if len(pool) > self.LOCAL_QUEUE:
            pool = random.sample(pool, self.LOCAL_QUEUE)
        self.p.play_tracks(pool, shuffle=True)

    def copy_text(self, text, msg="link kopiert"):
        Gdk.Display.get_default().get_clipboard().set_content(Gdk.ContentProvider.new_for_value(text))
        self.say(msg)

    @staticmethod
    def detail_url(kind, ident):
        base = "https://music.youtube.com/"
        if kind == "playlist":
            return f"{base}playlist?list={ident}"
        if kind == "podcast":
            return f"{base}playlist?list={ident[4:] if ident.startswith('MPSP') else ident}"
        if kind == "artist":
            return f"{base}channel/{ident}"
        if kind == "album":
            return f"{base}browse/{ident}"
        return None

    def set_tools(self, *widgets):
        tui.clear(self.detail_tools)
        for w in widgets:
            self.detail_tools.append(w)
        self.detail_tools.set_visible(bool(widgets))

    def open_detail(self, kind, ident):
        self.detail_key = (kind, ident)
        self.show_tab("lib")
        self.lib_stack.set_visible_child_name("detail")
        self.nav_note()
        self.detail_panel.set_title("lädt …")
        tui.clear(self.detail_box)
        self.detail_pool = None
        self.detail_tracks = []
        url = self.detail_url(kind, ident)
        self.set_tools(*([tui.Button("󰆏 link", lambda: self.copy_text(url), tooltip="Link in die Zwischenablage")]
                         if url else []))
        if kind == "local":
            self.fill_local(ident)
            return
        if kind == "stats":
            self.fill_stats()
            return
        fn = {"playlist": self.p.music.playlist, "album": self.p.music.album, "podcast": self.p.music.podcast,
              "artist": self.p.music.artist, "history": lambda _i: ("verlauf", self.p.music.history()),
              "subs": lambda _i: self.p.music.subscriptions(), "podlib": lambda _i: self.p.music.podcast_library(),
              "new": lambda _i: self.p.music.new_releases()}[kind]

        def done(res):
            if self.detail_key != (kind, ident):     # inzwischen woanders hin
                return
            if isinstance(res, Exception):
                self.say(f"laden: {engine.explain(res)}", error=True)
                self.detail_panel.set_title("fehler")
                return
            if kind == "artist":
                self.fill_artist(ident, res)
                return
            if kind in self.COLL_KINDS:
                title, opens, glyph = self.COLL_KINDS[kind]
                self.detail_names[(kind, ident)] = title.split(" ", 1)[1]
                self.detail_panel.set_title(f"{esc(title)} <span alpha='60%'>{len(res)}</span>", markup=True)
                for c in res:
                    self.detail_box.append(coll_row(glyph, c["title"], c["sub"],
                                                    lambda k=opens, i=c["id"]: self.open_detail(k, i)))
                if not res:
                    self.detail_box.append(label("nichts da" + ("" if kind != "new" else
                                                                " – erst künstler abonnieren (auf der künstlerseite)"),
                                                 "empty", xalign=0.5))
                return
            title, tracks = res
            self.detail_names[(kind, ident)] = title
            self.detail_tracks = tracks
            total = sum(t["duration"] or 0 for t in tracks)
            self.detail_panel.set_title(f"{esc(title)} <span alpha='60%'>{len(tracks)} · {fmt(total)}</span>",
                                        markup=True)
            editable = kind == "playlist" and ident in self.editable_ids
            tools = [tui.Button("󰆏 link", lambda: self.copy_text(url))] if url else []
            if editable:
                tools += [self.pl_tool("✎ umbenennen", lambda b: self.rename_playlist(b, ident, title)),
                          self.pl_tool("󰆴 löschen", lambda b: self.delete_playlist(b, ident, title), danger=True)]
            if tracks and kind != "history":
                tools.append(self.offline_tool(tracks))
            self.set_tools(*tools)
            def make(i, t):
                acts = [("+", "An Warteschlange anhängen", lambda t=t: self.p.add(t)),
                        ("»", "Als nächstes spielen", lambda t=t: self.p.add(t, next_=True))]
                holder = []
                if editable and t.get("setVideoId"):
                    acts.append(("✕", "Aus der Playlist entfernen",
                                 lambda t=t, h=holder: self.remove_from_playlist(ident, t, h[0])))
                row = track_row(t, lambda i=i: self.p.play_tracks(tracks, start=i), acts, menus=self.songs)
                holder.append(row)
                row.mark.set_label(str(i + 1))
                return row
            self.rows_chunked(self.detail_box, tracks, make)
        tui.background(fn, ident, done=done)

    def offline_tool(self, tracks):
        """„󰇚 offline speichern“ für die ganze Liste; ist schon alles gemerkt, entfernt der Knopf sie wieder."""
        off = self.p.offline
        shown = tracks[:off.PIN_MAX]
        btn = tui.Button("", None)

        def paint():
            allp = all(off.is_pinned(t["videoId"]) for t in shown)
            btn.set_label("󰇚 offline entfernen" if allp else f"󰇚 offline speichern ({len(shown)})")
            btn.set_tooltip_text("Alle Titel dieser Liste behalten – auch ohne Internet" if not allp else
                                 "Die gemerkten Titel dieser Liste wieder freigeben")
        paint()

        def click(*_):
            if all(off.is_pinned(t["videoId"]) for t in shown):
                off.unpin([t["videoId"] for t in shown])
                self.say("offline: freigegeben")
            else:
                n = off.pin(shown)
                self.say(f"offline: {n} titel werden geladen …" if n else "offline: nichts Neues")
            paint()
            self.update_offline()
        btn.connect("clicked", click)
        return btn

    @staticmethod
    def pl_tool(text, fn, danger=False):
        b = tui.Button(text, None, danger=danger)
        b.connect("clicked", lambda *_: fn(b))
        return b

    def rename_playlist(self, anchor, pid, old):
        pop = self.songs._popover(anchor)
        box = vbox(spacing=4)
        pop.set_child(box)
        box.append(label("✎  umbenennen", "kp-head"))
        entry = tui.Entry("neuer name …")
        entry.set_text(old)
        box.append(entry)

        def go():
            name = entry.get_text().strip()
            if not name or name == old:
                pop.popdown()
                return
            pop.popdown()

            def done(res):
                if isinstance(res, Exception):
                    self.say(f"umbenennen: {engine.explain(res)}", error=True)
                    return
                self.say(f"umbenannt: {name}")
                self.detail_names[("playlist", pid)] = name
                if self.detail_key == ("playlist", pid):
                    self.open_detail("playlist", pid)
                self.load_library()
            tui.background(self.p.music.rename_playlist, pid, name, done=done)
        entry.connect("activate", lambda *_: go())
        pop.popup()
        entry.grab_focus()
        entry.select_region(0, -1)

    def delete_playlist(self, anchor, pid, title):
        pop = self.songs._popover(anchor)
        box = vbox(spacing=4)
        pop.set_child(box)
        box.append(label("󰆴  playlist löschen?", "kp-head"))
        t = label(f"„{title}“ wird bei youtube music gelöscht – das geht nicht rückgängig.", "kp-sub", wrap=True)
        t.set_max_width_chars(34)
        box.append(t)
        self.songs._item(box, pop, "󰆴", "ja, löschen", lambda: self._do_delete_playlist(pid, title), danger=True)
        self.songs._item(box, pop, "‹", "abbrechen", lambda: None)
        pop.popup()

    def _do_delete_playlist(self, pid, title):
        def done(res):
            if isinstance(res, Exception):
                self.say(f"löschen: {engine.explain(res)}", error=True)
                return
            self.say(f"„{title}“ gelöscht")
            if self.detail_key == ("playlist", pid):
                self.lib_home()
            self.load_library()
        tui.background(self.p.music.delete_playlist, pid, done=done)

    def remove_from_playlist(self, pid, t, row):
        def done(res):
            if isinstance(res, Exception):
                self.say(f"entfernen: {engine.explain(res)}", error=True)
                return
            self.say(f"entfernt: {t['title']}")
            if t in self.detail_tracks:
                self.detail_tracks.remove(t)
            if row.get_parent() is not None:
                row.get_parent().remove(row)
        tui.background(self.p.music.remove_from_playlist, pid, [t], done=done)

    # ---------- Rückblick ----------
    STAT_PERIODS = [("7", "7 tage"), ("30", "30 tage"), ("365", "1 jahr"), ("0", "gesamt")]
    BLOCKS = " ▁▂▃▄▅▆▇█"

    @classmethod
    def spark(cls, vals):
        top = max(vals) or 1
        return "".join(cls.BLOCKS[min(8, int(round(v / top * 8)))] if v else cls.BLOCKS[0] for v in vals)

    @staticmethod
    def hours_text(sec):
        h, m = divmod(int(sec) // 60, 60)
        return f"{h} h {m:02d} min" if h else f"{m} min"

    def fill_stats(self, period=None):
        self.detail_names[("stats", "")] = "rückblick"
        period = period or getattr(self, "stat_period", "30")
        self.stat_period = period
        sel = tui.Select(lambda v: self.fill_stats(v), tooltip="Zeitraum")
        sel.set_options(self.STAT_PERIODS, period)
        clear = tui.Button("protokoll löschen", self.clear_stats, danger=True,
                           tooltip="Löscht nur den Rückblick (nicht den Verlauf links)")
        self.set_tools(sel, clear)
        tui.clear(self.detail_box)
        days = int(period)
        r = self.p.stats.report(days or None)
        title = dict(self.STAT_PERIODS)[period]
        self.detail_tracks = [self.p.stats.rebuild(vid, t, a, d) for _n, vid, t, a, d in r["top_titles"]]
        self.detail_panel.set_title(f"󰄨 rückblick <span alpha='60%'>{esc(title)}</span>", markup=True)
        box = self.detail_box
        if not r["plays"]:
            box.append(label("in diesem zeitraum noch nichts gehört – der rückblick füllt sich beim hören "
                             "(hörverlauf muss an sein)", "empty", xalign=0.5, wrap=True))
            return

        def head(txt):
            h = label(txt, "accent", xalign=0)
            h.set_margin_top(10)
            h.set_margin_bottom(2)
            box.append(h)

        def line(txt, cls=None):
            box.append(label(txt, *([cls] if cls else []), xalign=0, wrap=True))
        per_day = r["plays"] / max(1, r["span_days"])
        line(f"{r['plays']} wiedergaben · bis zu {self.hours_text(r['seconds'])} musik · {r['unique']} verschiedene "
             f"titel · {r['artists_n']} künstler")
        line(f"an {r['days_active']} von {r['span_days']} tagen gehört · Ø {per_day:.1f} titel pro tag", "dim")

        def bars(rows, name_w=30):
            top = rows[0][0] if rows else 1
            for n, text, play in rows:
                row = Gtk.Box()
                row.add_css_class("row")
                b = Gtk.Button(hexpand=True)
                b.add_css_class("rowhead")
                bar = "█" * max(1, round(n / top * 14))
                b.set_child(hbox(label(f"{n:>3}×", "dim"), label(bar, "accent"),
                                 label(text, hexpand=True, ellipsize=True, xalign=0), spacing=10))
                if play:
                    b.connect("clicked", lambda _b, f=play: f())
                row.append(b)
                box.append(row)
        head("meistgehörte titel")
        tracks = self.detail_tracks
        bars([(n, f"{t} · {a}" if a else t, lambda i=i: self.p.play_tracks(tracks, start=i))
              for i, (n, _vid, t, a, _d) in enumerate(r["top_titles"])])
        head("meistgehörte künstler")
        bars([(n, a, (lambda a=a: self.open_artist({"artist": a, "artistId": None}))) for n, a in r["top_artists"]])
        head("tageszeit  (0 – 23 uhr)")
        line(self.spark(r["hours"]), "mono-pct")
        best = max(range(24), key=lambda h: r["hours"][h])
        line(f"am meisten um {best} uhr", "dim")
        head("wochentag  (mo – so)")
        line(self.spark(r["wdays"]), "mono-pct")
        names = ["montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"]
        line(f"am meisten am {names[max(range(7), key=lambda d: r['wdays'][d])]}", "dim")

    def clear_stats(self):
        self.p.stats.clear()
        self.say("rückblick gelöscht")
        self.fill_stats()

    # ---------- lokale Musik ----------
    def update_local_panel(self):
        on = engine.setting("local")
        self.local_panel.set_visible(bool(on))
        tui.clear(self.local_box)
        if not on:
            return
        lib = self.p.locallib
        n = len(lib.tracks)
        sub = f"{n} titel" if self.local_scanned else "…"
        self.local_box.append(coll_row("󰉋", os.path.basename((lib.root or "").rstrip("/")) or "musikordner", sub,
                                       lambda: self.open_detail("local", "")))

    def rescan_local(self, say_done=False):
        if not engine.setting("local"):
            self.update_local_panel()
            return

        def done(res):
            self.local_scanned = True
            if isinstance(res, Exception):
                self.say(f"lokale musik: {res}", error=True)
            elif say_done:
                self.say(f"lokale musik: {len(res)} titel in {self.p.locallib.root}")
            self.update_local_panel()
            if hasattr(self, "local_info"):
                self.update_local_info()
            if self.detail_key == ("local", "") and hasattr(self, "local_list"):
                self.render_local()
        self.p.scan_local(done)
        return False

    def fill_local(self, _ident):
        self.detail_names[("local", "")] = "lokal"
        self.local_entry = tui.Entry("filtern (titel, künstler, album) …")
        self.local_entry.connect("changed", lambda *_: self.render_local())
        self.local_list = vbox(spacing=0)
        self.detail_box.append(self.local_entry)
        self.detail_box.append(self.local_list)
        if not self.local_scanned:
            self.detail_panel.set_title("󰉋 lokale musik <span alpha='60%'>liest ein …</span>", markup=True)
            self.rescan_local()
        else:
            self.render_local()

    def render_local(self):
        lib = self.p.locallib
        q = self.local_entry.get_text()
        tr = lib.search(q)
        self.detail_pool = tr
        self.detail_tracks = tr[:self.LOCAL_QUEUE]
        total = sum(t["duration"] or 0 for t in tr)
        self.detail_panel.set_title(f"󰉋 lokale musik <span alpha='60%'>{len(tr)} · {fmt(total)}</span>",
                                    markup=True)
        tui.clear(self.local_list)
        for i, t in enumerate(tr[:self.LOCAL_SHOWN]):
            row = track_row(t, lambda i=i: self.p.play_tracks(tr[i:i + self.LOCAL_QUEUE]),
                            [("+", "An Warteschlange anhängen", lambda t=t: self.p.add(t)),
                             ("»", "Als nächstes spielen", lambda t=t: self.p.add(t, next_=True))],
                            menus=self.songs)
            row.mark.set_label(str(i + 1))
            self.local_list.append(row)
        if len(tr) > self.LOCAL_SHOWN:
            self.local_list.append(label(f"… {len(tr) - self.LOCAL_SHOWN} weitere – oben filtern", "empty",
                                         xalign=0.5))
        if not tr:
            self.local_list.append(label("nichts gefunden" if q else
                                         f"keine musikdateien in {lib.root} – ordner in den einstellungen ändern",
                                         "empty", xalign=0.5))
