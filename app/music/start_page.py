"""Reiter „start“: Startseite im Stil von YT Music.
Oben Stimmungs-Chips (filtern die ganze Seite), darunter die Schnellauswahl als 3×3-Raster zum Durchblättern
(‹ › oder seitlich wischen/scrollen), dann eigene Regale aus dem Hörprotokoll (zuletzt gehört, Freund·innen hören,
wiederentdecken) und danach die Regale von YT Music."""
import time
from concurrent.futures import ThreadPoolExecutor

from gi.repository import Gtk

import tui
import engine
from tui import label, hbox, vbox
from widgets import big_thumb, fetch_pixbuf, DotThumb

PAGE = 9            # 3×3
# ytmusicapi bleibt auf Englisch (sonst findet die Suche nichts) → Chip-Namen nur für die Anzeige übersetzen
CHIP_DE = {"relax": "entspannen", "workout": "workout", "energize": "power", "feel good": "gute laune", "party": "party",
           "romance": "romantik", "commute": "unterwegs", "sad": "traurig", "focus": "konzentration", "sleep": "einschlafen"}


def chip_name(name):
    return CHIP_DE.get(name.lower(), name.lower())
TILE = 104          # px je Kästchen


def recent_tracks(rows, n=20):
    """Zuletzt wirklich gehörte Titel (nicht übersprungen), neueste zuerst, jeder einmal."""
    seen, out = set(), []
    for e in reversed(rows):
        vid, p, d = e.get("id") or "", e.get("p") or 0, e.get("d") or 0
        if len(vid) != 11 or vid in seen or not (p >= 30 or (d and p >= d / 2)):
            continue
        seen.add(vid)
        out.append(_jt(e))
        if len(out) >= n:
            break
    return out


def again_tracks(rows, now=None, n=20):
    """Wiederentdecken: oft gehört (≥ 4×), aber seit 45 Tagen nicht mehr."""
    now = now or time.time()
    st = {}
    for e in rows:
        vid, p, d = e.get("id") or "", e.get("p") or 0, e.get("d") or 0
        if len(vid) != 11 or not (e.get("alt") == 1 or p >= 30 or (d and p >= d / 2)):
            continue
        s = st.setdefault(vid, [0, 0, e])
        s[0] += 1
        s[1] = max(s[1], e.get("at") or 0)
        s[2] = e
    old = [s for s in st.values() if s[0] >= 4 and now - s[1] > 45 * 86400]
    return [_jt(s[2]) for s in sorted(old, key=lambda s: -s[0])[:n]]


def _jt(e):
    vid = e["id"]
    return {"videoId": vid, "title": e.get("t") or "?", "artist": e.get("a") or "", "artistId": e.get("aid"), "album": e.get("al") or "",
            "albumId": e.get("alid"), "duration": e.get("d") or 0, "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"}


def item_of(d):
    """Eintrag eines YT-Regals → ("song", track) | ("album"|"artist"|"playlist", id, titel, untertitel, bild)."""
    if d.get("videoId"):
        t = engine.track(d)
        return ("song", t) if t else None
    thumbs = d.get("thumbnails") or []
    th = thumbs[-1]["url"] if thumbs else ""
    bid = d.get("browseId") or ""
    sub = d.get("description") or d.get("subscribers") or d.get("year") or ""
    if bid.startswith("MPRE"):
        return ("album", bid, d.get("title") or "", str(sub), th)
    if bid.startswith("UC"):
        return ("artist", bid, d.get("title") or "", str(sub), th)
    if d.get("playlistId"):
        return ("playlist", d["playlistId"], d.get("title") or "", str(sub), th)
    return None


class StartMixin:
    def build_start(self):
        page = vbox(spacing=10)
        page.set_margin_top(6)
        self.st_sel = None                 # (name, params) der gewählten Stimmung, None = für dich
        self.st_chips = []
        self.st_moods = {}                 # name → (zeit, regale)
        self.st_home = None                # (zeit, regale) „für dich“
        self.st_pics = {}
        self.st_gen = 0
        self.st_chip_box = hbox(spacing=6)
        sc = Gtk.ScrolledWindow(vscrollbar_policy=Gtk.PolicyType.NEVER, hscrollbar_policy=Gtk.PolicyType.AUTOMATIC, child=self.st_chip_box)
        page.append(sc)

        self.st_quick = tui.Panel("󰝚 schnellauswahl")
        self.st_info = label("lädt …", "dim", hexpand=True, ellipsize=True)
        self.st_dots = label("", "accent")
        self.st_new = tui.Button("󰑐 neu", lambda: self.st_load(force=True), tooltip="Neu laden lassen")
        self.st_quick.body.append(hbox(self.st_info, tui.Button("‹", lambda: self.st_page(-1), tooltip="vorige Seite"), self.st_dots,
                                       tui.Button("›", lambda: self.st_page(1), tooltip="nächste Seite"), self.st_new, spacing=6))
        self.st_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, transition_duration=180, hhomogeneous=True,
                                  vhomogeneous=True, halign=Gtk.Align.START)
        # Touchpad: zwei Finger seitlich = blättern
        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.HORIZONTAL | Gtk.EventControllerScrollFlags.DISCRETE)
        scroll.connect("scroll", lambda _c, dx, _dy: (self.st_page(1 if dx > 0 else -1), True)[1] if abs(dx) > 0.3 else False)
        self.st_stack.add_controller(scroll)
        swipe = Gtk.GestureSwipe()
        swipe.connect("swipe", lambda _g, vx, vy: self.st_page(1 if vx < 0 else -1) if abs(vx) > abs(vy) and abs(vx) > 300 else None)
        self.st_stack.add_controller(swipe)
        self.st_quick.body.append(self.st_stack)
        page.append(self.st_quick)
        self.st_shelves = vbox(spacing=10)
        page.append(self.st_shelves)
        self.st_grid_tracks, self.st_pages = [], 0
        self.add_page("start", page)

    def start_shown(self):
        sel = self.st_sel
        cache = self.st_moods.get(sel[0]) if sel else self.st_home
        if cache is None or time.time() - cache[0] > 30 * 60:
            self.st_load()

    # ----- Laden -----
    def st_load(self, force=False):
        self.st_gen += 1
        gen, sel = self.st_gen, self.st_sel
        self.st_info.set_label("lädt …")
        music, journal, fr = self.p.music, self.p.journal, getattr(self, "fr", None)
        cache = self.st_moods.get(sel[0]) if sel else self.st_home

        def work():
            if cache is not None and not force and time.time() - cache[0] < 30 * 60:
                shelves, chips = cache[1], None
            else:
                shelves, chips = music.home_full(params=sel[1] if sel else None, limit=8 if sel is None else 6)
            own = []
            if sel is None:
                rows = list(journal.load())
                rec = recent_tracks(rows)
                if rec:
                    own.append(("󰋚 zuletzt gehört", [("song", t) for t in rec]))
                live = []
                for f in list(getattr(fr, "friends", None) or []):
                    now = (f.get("prof") or {}).get("now") or {}
                    vid = now.get("id") or ""
                    if len(vid) == 11:
                        t = {"videoId": vid, "title": now.get("t") or "?", "artist": now.get("a") or "",
                             "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg", "_who": f.get("name") or ""}
                        live.append(("song", t))
                if live:
                    own.append(("󰀄 freund·innen hören", live))
                ag = again_tracks(rows)
                if ag:
                    own.append(("󰑖 wiederentdecken", [("song", t) for t in ag]))
            yt = []
            for sh in shelves:
                items = [x for x in map(item_of, sh.get("contents") or []) if x]
                if items:
                    yt.append((sh.get("title") or "", items))
            quick = next((s for s in yt if any(w in s[0].lower() for w in ("schnell", "quick"))), None)
            grid = [x[1] for s in ([quick] if quick else yt) for x in s[1] if x[0] == "song"]
            if len(grid) < PAGE:
                # Stimmungsseiten (und YT ohne Anmeldung) liefern oft nur Playlists → Raster aus der ersten Playlist füllen
                pl = next((x[1] for s in yt for x in s[1] if x[0] == "playlist"), None)
                if pl:
                    try:
                        grid += music.playlist(pl)[1][:27]
                    except Exception:  # noqa: BLE001
                        pass
            seen = set()
            grid = [t for t in grid if not (t["videoId"] in seen or seen.add(t["videoId"]))][:27]
            rest = [s for s in yt if s is not quick]
            # Bilder vorab (parallel), damit die Seite in einem Rutsch erscheint
            urls = {t["videoId"]: t.get("thumb") for t in grid}
            for _n, items in own + rest[:8]:
                for x in items[:14]:
                    k = x[1]["videoId"] if x[0] == "song" else x[1]
                    urls[k] = x[1].get("thumb") if x[0] == "song" else x[4]
            pics = {}

            def one(kv):
                k, u = kv
                url = big_thumb(u, 226) if u else None
                try:
                    return k, fetch_pixbuf(url) if url else None
                except Exception:  # noqa: BLE001
                    return k, None
            with ThreadPoolExecutor(8) as ex:
                for k, pb in ex.map(one, [kv for kv in urls.items() if kv[0] not in self.st_pics]):
                    pics[k] = pb
            return shelves, chips, grid, own, rest, pics

        def done(res):
            if gen != self.st_gen:
                return
            if isinstance(res, Exception):
                self.st_info.set_label(f"startseite: {engine.explain(res)}")
                return
            shelves, chips, grid, own, rest, pics = res
            self.st_pics.update(pics)
            if sel is None:
                self.st_home = (time.time() if chips is not None or self.st_home is None else self.st_home[0], shelves)
            else:
                self.st_moods[sel[0]] = (time.time() if chips is not None else self.st_moods.get(sel[0], (time.time(),))[0], shelves)
            if chips:
                self.st_chips = chips
            self.st_fill_chips()
            self.st_quick.set_title(f"󰝚 {chip_name(sel[0])}" if sel else "󰝚 schnellauswahl")
            self.st_info.set_label("antippen = radio · rechtsklick = menü" if grid else "nichts da")
            self.st_fill_grid(grid)
            self.st_fill_shelves(own + rest[:8] if sel is None else rest)
        tui.background(work, done=done)

    # ----- Chips -----
    def st_fill_chips(self):
        tui.clear(self.st_chip_box)
        sel = self.st_sel[0] if self.st_sel else None
        b = tui.Button(("■ " if sel is None else "") + "󰋜 für dich", lambda: self.st_pick(None))
        if sel is None:
            b.add_css_class("active")
        self.st_chip_box.append(b)
        for name, params in self.st_chips:
            b = tui.Button(("■ " if sel == name else "") + chip_name(name), lambda c=(name, params): self.st_pick(None if self.st_sel and self.st_sel[0] == c[0] else c))
            if sel == name:
                b.add_css_class("active")
            self.st_chip_box.append(b)

    def st_pick(self, chip):
        self.st_sel = chip
        self.st_fill_chips()
        self.st_load()

    # ----- 3×3-Raster -----
    def st_fill_grid(self, tracks):
        for c in list(self._children_of(self.st_stack)):
            self.st_stack.remove(c)
        self.st_grid_tracks = tracks
        self.st_pages = (len(tracks) + PAGE - 1) // PAGE
        for p in range(self.st_pages):
            grid = Gtk.Grid(column_spacing=8, row_spacing=6)
            for i, t in enumerate(tracks[p * PAGE:(p + 1) * PAGE]):
                grid.attach(self._st_tile(t, lambda t=t: self._st_radio(t), TILE), i % 3, i // 3, 1, 1)
            self.st_stack.add_named(grid, f"p{p}")
        self.st_page(0, absolute=True)

    def st_page(self, d, absolute=False):
        if not self.st_pages:
            self.st_dots.set_label("")
            return
        cur = 0 if absolute else int((self.st_stack.get_visible_child_name() or "p0")[1:]) + d
        cur = max(0, min(self.st_pages - 1, cur))
        self.st_stack.set_visible_child_name(f"p{cur}")
        self.st_dots.set_label(" ".join("●" if i == cur else "○" for i in range(self.st_pages)))

    def _st_radio(self, t):
        self.p.play_tracks([t], src=("start", chip_name(self.st_sel[0]) if self.st_sel else "schnellauswahl"))
        self.p.start_radio(t)

    # ----- Regale -----
    def st_fill_shelves(self, shelves):
        tui.clear(self.st_shelves)
        for title, items in shelves:
            panel = tui.Panel(title.lower())
            row = hbox(spacing=10)
            row.set_halign(Gtk.Align.START)
            songs = [x[1] for x in items if x[0] == "song"]
            src = ("start", title.split(" ", 1)[-1] if title[:1] in "󰋚󰀄󰑖" else title)
            for x in items[:14]:
                if x[0] == "song":
                    t = x[1]
                    i = songs.index(t)
                    row.append(self._st_tile(t, lambda i=i: self.p.play_tracks(songs, start=i, src=src), 120, sub=t.get("_who")))
                else:
                    kind, ident, name, sub, _th = x
                    row.append(self._st_tile({"videoId": ident, "title": name, "artist": sub}, lambda k=kind, i=ident: self.open_detail(k, i),
                                             120, menu=False))
            sw = Gtk.ScrolledWindow(vscrollbar_policy=Gtk.PolicyType.NEVER, hscrollbar_policy=Gtk.PolicyType.AUTOMATIC, child=row)
            panel.body.append(sw)
            if songs:
                panel.body.append(hbox(tui.Button("󰐊 alle", lambda s=songs: self.p.play_tracks(s, src=src)),
                                       tui.Button("󰒝 mischen", lambda s=songs: self.p.play_tracks(s, shuffle=True, src=src)), spacing=8))
            self.st_shelves.append(panel)
        if not shelves:
            self.st_shelves.append(label("keine regale", "empty"))

    def _st_tile(self, t, on_click, side, sub=None, menu=True):
        pic = DotThumb(side)
        pic.set_data(self.st_pics.get(t["videoId"]))
        b = Gtk.Button(child=pic, focus_on_click=False, halign=Gtk.Align.START, hexpand=False)
        b.add_css_class("qtile")
        b.set_tooltip_text(f"{t['title']} · {t.get('artist', '')}")
        b.connect("clicked", lambda *_: on_click())
        if menu:
            rc = Gtk.GestureClick(button=3)
            rc.connect("pressed", lambda g, n, x, y, b=b, t=t: self.songs.menu(b, x, y, t))
            b.add_controller(rc)
        cell = vbox(b, spacing=2)
        cell.set_halign(Gtk.Align.START)
        for txt, cls in ((t["title"], ""), ((f"{sub} · " if sub else "") + (t.get("artist") or ""), "dim")):
            lb = label(txt, *([cls] if cls else []), ellipsize=True, xalign=0)
            lb.set_max_width_chars(max(6, side // 8))
            lb.set_size_request(side + 8, -1)
            cell.append(lb)
        return cell

    @staticmethod
    def _children_of(w):
        c = w.get_first_child()
        while c is not None:
            nxt = c.get_next_sibling()
            yield c
            c = nxt
