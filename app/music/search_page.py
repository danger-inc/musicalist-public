# musicalist – Suche (Vorschläge, Treffer, „meine“) (Teil von MusicWindow, siehe ui.py). Methoden greifen auf self (das Hauptfenster) zu.
import time

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Graphene, Gtk, Pango, PangoCairo

import tui
from tui import label, hbox, vbox, esc
import engine
from engine import fmt
import localmusic
from rows import track_row, coll_row, artist_link
from widgets import Cover, preview_supported, DESK_POS


class SearchMixin:

    # ---------- Suche ----------
    # Beim Tippen: nach 120 ms Vorschläge (erster groß, Tab übernimmt ihn), nach 380 ms schon Ergebnisse.
    # Enter sucht sofort. Ergebnisse bleiben 10 min im Speicher; veraltete Antworten werden verworfen.
    def build_search(self):
        page = vbox(spacing=8)
        page.set_margin_top(6)
        self.query = tui.Entry("suchen … (tippen reicht, enter sofort)", activate=lambda: self.do_search(now=True))
        self.query.connect("changed", lambda *_: self.on_query_changed())
        qk = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        qk.connect("key-pressed", self.on_query_key)
        self.query.add_controller(qk)
        self.kind = tui.Select(lambda k: (self.kind.set_options(self.kind.options, k), self.do_search(now=True)))
        self.kind.set_options([(k, k) for k in ("songs", "alben", "playlists", "künstler", "videos", "podcasts", "lokal", "meine")], "songs")
        self.sugg_row = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=4, row_spacing=2,
                                    max_children_per_line=12, homogeneous=False, halign=Gtk.Align.START)
        self.sugg_row.add_css_class("opts")
        self.sugg_row.add_css_class("sugg-row")
        self.sugg_row.set_visible(False)
        page.append(tui.Panel("󰍉 suche", vbox(hbox(label("/", "accent"), self.query, self.kind, spacing=10),
                                              self.sugg_row, spacing=4)))
        self.top_panel = tui.Panel("bester treffer")
        self.top_box = vbox(spacing=0)
        self.top_panel.body.append(self.top_box)
        self.top_panel.set_visible(False)
        page.append(self.top_panel)
        self.albums_panel = tui.Panel("alben")
        self.albums_box = vbox(spacing=0)
        self.albums_panel.body.append(self.albums_box)
        self.albums_panel.set_visible(False)
        page.append(self.albums_panel)
        self.album_cache = {}
        self.results_panel = tui.Panel("ergebnisse")
        self.results = vbox(spacing=0)
        self.results_panel.body.append(self.results)
        self.results_panel.set_visible(False)
        page.append(self.results_panel)
        self.add_page("search", page)
        self.search_gen = 0
        self.search_cache = {}        # (q, art) → (zeit, ergebnisse)
        self.top_cache = {}
        self.suggs = []
        self._sugg_id = self._search_id = None
        self._sugg_skip = None        # Text, für den keine Vorschläge mehr gezeigt werden (nach Enter/Klick)
        self.shown_q = None

    def on_query_changed(self):
        q = self.query.get_text().strip()
        for sid in ("_sugg_id", "_search_id"):
            if getattr(self, sid):
                GLib.source_remove(getattr(self, sid))
                setattr(self, sid, None)
        if len(q) < 2:
            self.show_suggestions(q, [])
            return
        if q != self._sugg_skip:
            self._sugg_id = GLib.timeout_add(120, self.load_suggestions)
        self._search_id = GLib.timeout_add(380, lambda: (setattr(self, "_search_id", None), self.do_search())[0])

    def load_suggestions(self):
        self._sugg_id = None
        q = self.query.get_text().strip()

        def done(res):
            if q == self.query.get_text().strip() and q != self._sugg_skip:
                self.show_suggestions(q, [] if isinstance(res, Exception) else res[:7])
        tui.background(self.p.music.suggestions, q, done=done)
        return False

    def show_suggestions(self, q, items):
        self.suggs = [x for x in items if x.strip().lower() != q.lower()] if items else []
        if items and items[0].strip().lower() == q.lower():
            self.suggs = items[:1] + self.suggs            # genau getroffen: trotzdem vorn (= Enter-Ziel)
        tui.clear(self.sugg_row)
        for i, text in enumerate(self.suggs):
            b = Gtk.Button(focus_on_click=False)
            b.add_css_class("sugg")
            if i == 0:
                b.add_css_class("first")
                b.set_child(hbox(label("󰍉", "accent"), label(text), label("tab", "kp-key"), spacing=6))
                b.set_tooltip_text("tab übernimmt diesen vorschlag")
            else:
                b.set_child(label(text))
            b.connect("clicked", lambda _b, t=text: self.take_suggestion(t))
            self.sugg_row.append(b)
        self.sugg_row.set_visible(bool(self.suggs))

    def take_suggestion(self, text):
        self._sugg_skip = text
        self.query.set_text(text)
        self.query.set_position(-1)
        self.show_suggestions(text, [])
        self.do_search(now=True)
        self.query.grab_focus()
        self.query.select_region(-1, -1)

    def on_query_key(self, _c, kv, _code, state):
        if kv in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab) and self.suggs and not state & Gdk.ModifierType.SHIFT_MASK:
            self.take_suggestion(self.suggs[0])
            return True
        if kv == Gdk.KEY_Down and self.results.get_first_child() is not None:
            first = self.top_box.get_first_child() if self.top_panel.get_visible() else self.results.get_first_child()
            if first is not None:
                first.child_focus(Gtk.DirectionType.TAB_FORWARD)
                return True
        return False

    def do_search(self, now=False):
        q = self.query.get_text().strip()
        if not q:
            return
        if now:
            self._sugg_skip = q
            self.show_suggestions(q, [])
            if self._search_id:
                GLib.source_remove(self._search_id)
                self._search_id = None
        kind = self.kind.current
        if (q, kind) == self.shown_q and not now:
            return
        self.search_gen += 1
        gen = self.search_gen
        key = (q.lower(), kind)
        hit = self.search_cache.get(key)
        if kind == "meine":                  # kein Netz: Verlauf, Bibliothek, offline, lokal
            self.top_panel.set_visible(False)
            self.albums_panel.set_visible(False)
            self.show_results(self.search_mine(q), kind, q, gen)
        elif kind == "lokal":                # kein Netz: Musikordner durchsuchen
            self.top_panel.set_visible(False)
            self.albums_panel.set_visible(False)
            if not self.p.locallib.tracks:
                self.say("lokale musik: noch nichts eingelesen – einstellungen (,) → lokale musik")
            self.show_results(self.p.locallib.search(q)[:100], kind, q, gen)
        elif hit and time.monotonic() - hit[0] < 600:
            self.show_results(hit[1], kind, q, gen)
        else:
            self.results_panel.set_title(f"ergebnisse <span alpha='60%'>sucht „{esc(q)}“ …</span>", markup=True)

            def done(res):
                if not isinstance(res, Exception):
                    self.search_cache[key] = (time.monotonic(), res)
                    if len(self.search_cache) > 80:
                        self.search_cache.pop(next(iter(self.search_cache)))
                self.show_results(res, kind, q, gen)
            tui.background(self.p.music.search, q, kind, done=done)
        # bester Treffer (eigene Anfrage, parallel) – nur bei „songs“, dort sucht man meist nach etwas Bestimmtem
        if kind == "songs":
            th = self.top_cache.get(q.lower())
            if th and time.monotonic() - th[0] < 600:
                self.show_top(th[1], q, gen)
            else:
                def top_done(res):
                    if not isinstance(res, Exception):
                        self.top_cache[q.lower()] = (time.monotonic(), res)
                    self.show_top(res, q, gen)
                tui.background(self.p.music.top_result, q, done=top_done)
            ah = self.album_cache.get(q.lower())
            if ah and time.monotonic() - ah[0] < 600:
                self.show_albums(ah[1], gen)
            else:
                def alb_done(res):
                    if not isinstance(res, Exception):
                        self.album_cache[q.lower()] = (time.monotonic(), res)
                    self.show_albums(res, gen)
                tui.background(self.p.music.search_albums, q, done=alb_done)
        else:
            self.top_panel.set_visible(False)
            self.albums_panel.set_visible(False)

    def show_albums(self, res, gen):
        if gen != self.search_gen:
            return
        tui.clear(self.albums_box)
        if isinstance(res, Exception) or not res:
            self.albums_panel.set_visible(False)
            return
        for a in res:
            if not a.get("browseId"):
                continue
            ars = [x for x in a.get("artists") or [] if x.get("name")]
            row = coll_row("󰀥", a.get("title", "?"), " · ".join(x for x in (a.get("type"), str(a.get("year") or "")) if x),
                           lambda b=a["browseId"]: self.open_detail("album", b),
                           artist=(", ".join(x["name"] for x in ars), next((x.get("id") for x in ars if x.get("id")), None)))
            head = row.get_first_child().get_child()
            head.prepend(label("ALBUM", "album-badge"))
            self.albums_box.append(row)
        self.albums_panel.set_visible(self.albums_box.get_first_child() is not None)

    def show_top(self, r, q, gen):
        if gen != self.search_gen:
            return
        tui.clear(self.top_box)
        if not r or isinstance(r, Exception):
            self.top_panel.set_visible(False)
            return
        rtype = (r.get("resultType") or "").lower()
        arts = ", ".join(a["name"] for a in r.get("artists") or [] if a.get("name"))
        thumbs = r.get("thumbnails") or []
        cover = Cover(20, 10)
        cover.show(thumbs[-1]["url"] if thumbs else None)
        acts = hbox(spacing=8)
        if rtype in ("song", "video") and r.get("videoId"):
            t = engine.track(r)
            title, kind_txt, sub = t["title"], "titel" if rtype == "song" else "video", arts or t["artist"]
            play = lambda: (self.p.play_now(t), self.p.start_radio(t) if self.p.autoplay else None)
            acts.append(tui.Button("󰐊 abspielen", play))
            acts.append(tui.Button("» als nächstes", lambda: (self.p.add(t, next_=True), self.say(f"» {t['title']}"))))
            acts.append(tui.Button("+", lambda: (self.p.add(t), self.say(f"+ {t['title']}")), tooltip="anhängen"))
            acts.append(tui.Button("󰐒", lambda: self.songs.picker(acts, [t]), tooltip="zu playlist hinzufügen"))
            open_fn = play
        elif rtype == "artist" and r.get("browseId"):
            title, kind_txt, sub = r.get("artist") or arts or "?", "künstler", r.get("subscribers") or ""
            if sub:
                sub = f"{sub} abonnenten"
            open_fn = lambda b=r["browseId"]: self.open_detail("artist", b)
            acts.append(tui.Button("󰠃 öffnen", open_fn))
            t = None
        elif rtype == "album" and r.get("browseId"):
            title, kind_txt, sub = r.get("title") or "?", "album", arts
            open_fn = lambda b=r["browseId"]: self.open_detail("album", b)
            acts.append(tui.Button("󰀥 öffnen", open_fn))
            t = None
        elif rtype == "playlist" and r.get("browseId"):
            b = r["browseId"]
            title, kind_txt, sub = r.get("title") or "?", "playlist", r.get("author") or arts
            open_fn = lambda b=b: self.open_detail("playlist", b[2:] if b.startswith("VL") else b)
            acts.append(tui.Button("󰲸 öffnen", open_fn))
            t = None
        else:
            self.top_panel.set_visible(False)
            return
        tl = label(title, "top-title", ellipsize=True)
        head = Gtk.Button(hexpand=True)
        head.add_css_class("rowhead")
        subw = label(sub, "top-sub", ellipsize=True)
        if rtype in ("song", "video", "album") and arts:
            ars = [a for a in r.get("artists") or [] if a.get("name")]
            subw = artist_link(arts, next((a.get("id") for a in ars if a.get("id")), None), "top-sub", 40)
            subw.set_halign(Gtk.Align.START)
        link = isinstance(subw, Gtk.Button)       # Künstler-Link nicht in den Knopf schachteln (bekäme keinen Klick)
        head.set_child(vbox(label(kind_txt, "top-kind"), tl, None if link else subw, spacing=2))
        head.connect("clicked", lambda *_: open_fn())
        card = hbox(cover, vbox(head, subw if link else None, acts, spacing=6, hexpand=True,
                                valign=Gtk.Align.CENTER), spacing=14)
        card.add_css_class("top-card")
        if t is not None:
            self.songs.attach(card, t)
        self.top_box.append(card)
        self.top_panel.set_visible(True)

    def show_results(self, res, kind, q, gen=None):
        if gen is not None and gen != self.search_gen:
            return                          # inzwischen weitergetippt
        if isinstance(res, Exception):
            self.say(f"suche: {engine.explain(res)}", error=True)
            self.results_panel.set_title("ergebnisse")
            return
        self.shown_q = (q, kind)
        tui.clear(self.results)
        self.results_panel.set_visible(True)
        self.results_panel.set_title(f"ergebnisse <span alpha='60%'>{esc(kind)} · {len(res)}</span>", markup=True)
        if kind == "meine":
            n = len(res["playlists"]) + len(res["tracks"]) + len(res["local"])
            self.results_panel.set_title(f"ergebnisse <span alpha='60%'>meine musik · {n}</span>", markup=True)

            def head(txt):
                h = label(txt, "accent", xalign=0)
                h.set_margin_top(8)
                self.results.append(h)
            if res["playlists"]:
                head("playlists")
                for pl in res["playlists"]:
                    self.results.append(coll_row("󰲸", pl["title"], str(pl["count"] or ""),
                                                 lambda i=pl["id"]: self.open_detail("playlist", i)))
            if res["tracks"]:
                head("gehört / gemerkt")
                for t in res["tracks"]:
                    self.results.append(self.song_row(t, res["tracks"]))
            if res["local"]:
                head("lokale musik")
                for t in res["local"]:
                    self.results.append(self.song_row(t, res["local"]))
            if not n:
                self.results.append(label("nichts gefunden – „meine“ sucht in verlauf, bibliothek, offline "
                                          "und lokalen dateien", "empty", xalign=0.5, wrap=True))
            return
        if kind == "lokal":
            for t in res:
                self.results.append(self.song_row(t, res))
        elif kind in ("songs", "videos"):
            tracks = [t for t in map(engine.track, res) if t]
            for t in tracks:
                self.results.append(self.song_row(t, tracks))
        elif kind == "alben":
            for a in res:
                ars = [x for x in a.get("artists") or [] if x.get("name")]
                self.results.append(coll_row("󰀥", a.get("title", "?"), str(a.get("year") or ""),
                                             lambda b=a["browseId"]: self.open_detail("album", b),
                                             artist=(", ".join(x["name"] for x in ars),
                                                     next((x.get("id") for x in ars if x.get("id")), None))))
        elif kind == "playlists":
            for pl in res:
                self.results.append(coll_row("󰲸", pl.get("title", "?"),
                                             f"{pl.get('author', '')} · {pl.get('itemCount', '')}",
                                             lambda b=pl["browseId"]: self.open_detail(
                                                 "playlist", b[2:] if b.startswith("VL") else b)))
        elif kind == "künstler":
            for a in res:
                self.results.append(coll_row("󰠃", a.get("artist", "?"), "",
                                             lambda b=a["browseId"]: self.open_detail("artist", b)))
        elif kind == "podcasts":
            for a in res:
                pid = a.get("browseId") or a.get("playlistId")
                if pid:
                    au = a.get("author")
                    self.results.append(coll_row("󰦖", a.get("title", "?"),
                                                 au.get("name", "") if isinstance(au, dict) else str(au or ""),
                                                 lambda b=pid: self.open_detail("podcast", b)))
        if not res:
            self.results.append(label("nichts gefunden", "empty", xalign=0.5))

    def search_mine(self, q, cap=40):
        """Ohne Netz: Titel, die ich gehört oder gemerkt habe, meine Playlists und lokale Dateien."""
        words = q.lower().split()
        hit = lambda *parts: all(w in " ".join(p or "" for p in parts).lower() for w in words)
        p = self.p
        seen, tracks = set(), []

        def take(t):
            vid = t.get("videoId")
            if vid and vid not in seen and not localmusic.is_local(vid) and hit(t.get("title"), t.get("artist"),
                                                                                  t.get("album")):
                seen.add(vid)
                tracks.append(t)
        for t in list(p.history.items) + [e["t"] for e in p.offline.plays.values() if e.get("t")] + \
                list(p.offline.pins.values()):
            take({**t, "artistId": t.get("artistId"), "albumId": t.get("albumId"), "liked": False,
                  "thumb": t.get("thumb") or ""})
        for at, vid, title, artist, dur in reversed(p.stats.rows):      # langes Protokoll zuletzt (älteres)
            if len(tracks) >= cap:
                break
            if vid not in seen and not localmusic.is_local(vid) and hit(title, artist):
                take(p.stats.rebuild(vid, title, artist, dur))
        pls = [pl for pl in getattr(self, "lib_playlists", []) if pl["id"] != "LM" and hit(pl["title"])]
        return {"playlists": pls[:10], "tracks": tracks[:cap], "local": p.locallib.search(q)[:30]}

    def song_row(self, t, context):
        return track_row(t, lambda: (self.p.play_now(t), self.p.start_radio(t) if self.p.autoplay else None),
                         [("+", "An Warteschlange anhängen", lambda: (self.p.add(t), self.say(f"+ {t['title']}"))),
                          ("»", "Als nächstes spielen", lambda: (self.p.add(t, next_=True),
                                                                 self.say(f"» {t['title']}"))),
                          ("󰐒", "Zu Playlist hinzufügen", lambda b: self.songs.picker(b, [t]), True),
                          ("󰐹", "Radio zu diesem Titel", lambda: self.p.start_radio(t))],
                         menus=self.songs)
