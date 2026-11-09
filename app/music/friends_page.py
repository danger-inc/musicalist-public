"""Freunde-Seite (unter Bibliothek): eigener Code, Freund hinzufügen, was sie hören / empfehlen."""
import time

from gi.repository import GLib, Gtk

import tui
import engine
from tui import label, hbox, vbox
from rows import track_row
from widgets import DotCover
import friends as fr


def hmin(pf):
    """Hörzeit der Woche als „2h 16min“ (hm = Minuten; ältere Geräte senden nur h = Stunden auf 0,1 gerundet)."""
    m = int(pf["hm"]) if "hm" in pf else int(round(float(pf.get("h") or 0) * 60))
    h, mm = divmod(m, 60)
    return f"{h}h {mm}min" if h and mm else (f"{h}h" if h else f"{mm}min")


def prof_lines(pf):
    out = [f"diese woche: {hmin(pf)}" + (f" · {pf['n']} titel · {pf.get('ar')} künstler" if "n" in pf else "")]
    if pf.get("art"):
        out.append("top künstler: " + " · ".join(f"{a['n']} ({a['m']} min)" for a in pf["art"]))
    if pf.get("trk"):
        out.append("top titel: " + " · ".join(f"{t['t']} {t['n']}×" for t in pf["trk"]))
    if "pk" in pf:
        out.append(f"am liebsten um {pf['pk']} uhr · überspringt {pf.get('sk', 0)} %")
    if "dv" in pf:
        l = [f"typ: {pf['ct']}" if pf.get("ct") else "", f"vielfalt {pf['dv']} %", f"{pf.get('t1', 0)} % beim lieblingskünstler",
             f"{pf.get('rs', 0)} % wiederholt (3×+)", f"{pf.get('nw', 0)} neue künstler"]
        if "cr" in pf:
            l.append(f"{pf['cr']} % bis zum ende gehört")
        if pf.get("sn"):
            l.append(f"{pf['sn']} tage in folge")
        out.append(" · ".join(x for x in l if x))
    return out


# Rubriken der Wochen-Topliste: (Schlüssel, Name, Wert aus Hörprofil → (Zahl, Text, Zusatz) oder None, absteigend?)
def _v_h(pf):
    return (pf["h"], hmin(pf), "") if "h" in pf else None


def _v_rep(pf):
    t = (pf.get("trk") or [None])[0]
    return (t["n"], f"{t['n']}×", f"{t['t']} – {t['a']}") if t else None


def _v_n(pf):
    return (pf["n"], f"{pf['n']}", "titel") if "n" in pf else None


def _v_ar(pf):
    return (pf["ar"], f"{pf['ar']}", "künstler") if "ar" in pf else None


def _v_art(pf):
    a = (pf.get("art") or [None])[0]
    return (a["m"], f"{a['m']} min", a["n"]) if a else None


def _v_skip(pf):
    return (pf["sk"], f"{pf['sk']} %", "übersprungen") if "sk" in pf else None


def _num(key, unit, extra=""):
    return lambda pf: (pf[key], f"{pf[key]}{unit}", extra) if key in pf and (key != "sn" or pf[key]) else None


RUBRIKEN = [("h", "hörzeit", _v_h, True), ("rep", "wiederholungen", _v_rep, True), ("n", "titel", _v_n, True),
            ("ar", "künstler", _v_ar, True), ("art", "lieblingskünstler", _v_art, True), ("sk", "durchhörer", _v_skip, False),
            ("dv", "vielfalt", _num("dv", " %", "wie breit gestreut"), True), ("nw", "entdecker", _num("nw", "", "neue künstler"), True),
            ("sn", "serie", _num("sn", "", "tage in folge"), True)]


def top_rows(entries, key):
    """entries: [(name, pf, ich)] → sortierte Zeilen [(name, text, zusatz, ich)] der gewählten Rubrik (nur wer die Angabe teilt)."""
    _k, _n, fn, desc = next(r for r in RUBRIKEN if r[0] == key)
    rows = []
    for name, pf, me in entries:
        v = fn(pf) if pf else None
        if v:
            rows.append((v[0], name, v[1], v[2], me))
    rows.sort(key=lambda r: (-r[0] if desc else r[0], r[1]))
    return [(n, t, z, m) for _v, n, t, z, m in rows]


def ago(ms):
    if not ms:
        return "noch nichts gesehen"
    m = int((time.time() * 1000 - ms) / 60000)
    if m < 1:
        return "gerade eben"
    if m < 60:
        return f"vor {m} min"
    if m < 1440:
        return f"vor {m // 60} h"
    return f"vor {m // 1440} tagen"


class FriendsMixin:
    def build_friends(self):
        self.fr_open = set()
        page = vbox(spacing=8)
        page.set_margin_top(6)
        self.fr_head = tui.Panel("󰡉 freunde")
        self.fr_body = vbox(spacing=8)
        self.fr_head.body.append(self.fr_body)
        page.append(self.fr_head)
        self.friends_page = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.EXTERNAL, child=page, vexpand=True)
        self._fr_timer = 0
        f = self.fr
        if f is not None:
            f.say = lambda m: GLib.idle_add(lambda: (self.say(m), False)[1])
            f.listeners.append(lambda: GLib.idle_add(self._fr_changed))

    def friends_visible(self):
        return self.current_tab() == "stats" and getattr(self, "hear_sub", "analyse") == "friends"

    def _fr_changed(self):
        if self.friends_visible():
            self.fill_friends()
        return False

    @property
    def fr(self):
        return getattr(self.p, "friends", None)

    def open_friends(self):
        self.show_tab("stats")
        self.hear_select("friends")

    def friends_shown(self):
        """Tab „freunde“ wurde geöffnet: Stand holen, dann alle 25 s auffrischen, solange er offen ist."""
        self.fill_friends()
        self.refresh_friends()
        if not self._fr_timer:
            self._fr_n = 0
            self._fr_timer = GLib.timeout_add_seconds(8, self._fr_tick)

    def _fr_tick(self):
        """Alle 8 s den Eingang (Chat), alle 24 s zusätzlich den Stand aller Freunde."""
        if self.friends_visible() and self.get_visible():
            self._fr_n += 1
            if self._fr_n % 3 == 0:
                self.refresh_friends()
            elif self.fr:
                f = self.fr
                tui.background(f.poll_inbox, done=lambda n: self._fr_chat_changed(n))
            return True
        self._fr_timer = 0
        return False

    def refresh_friends(self):
        f = self.fr
        if not f:
            return

        def done(_):
            if self.friends_visible():
                self.fill_friends()
        tui.background(f.refresh, done=done)

    def _fr_chat_changed(self, n):
        if n and not isinstance(n, Exception) and self.friends_visible():
            view = getattr(self, "_fr_view", None)
            if view and view[0] == "chat":
                return self._fr_goto(view)
            self.fill_friends()

    def _fr_goto(self, view, note=True):
        """None = Liste · ("chat", code) · ("profile", code)."""
        self._fr_view = view
        if note:
            self.nav_note()
        if view and view[0] == "chat":
            self.fr.mark_read(view[1])
        self.fill_friends()
        end = bool(view and view[0] == "chat")

        def scroll():
            adj = self.friends_page.get_vadjustment()
            adj.set_value(adj.get_upper() - adj.get_page_size() if end else 0)
            return False
        GLib.timeout_add(60, scroll)

    def _detach_entry(self):
        e = getattr(self, "_chat_entry", None)
        if e is not None and e.get_parent() is not None:
            e.get_parent().remove(e)

    def fill_friends(self):
        f = self.fr
        box = self.fr_body
        self._detach_entry()
        tui.clear(box)
        if f is None:
            box.append(label("freunde nicht verfügbar", "dim"))
            return
        view = getattr(self, "_fr_view", None)
        x = next((x for x in f.friends if view and x["secret"] == view[1]), None)
        if view and x is None:
            view = self._fr_view = None
        if view and view[0] == "chat":
            return self._fill_chat(x)
        if view and view[0] == "profile":
            return self._fill_profile(x)
        top = hbox(label("", hexpand=True), tui.Button("󰑐", self.refresh_friends, tooltip="neu abfragen"), spacing=8)
        box.append(top)
        box.append(self._top_list())
        # --- ich ---
        me = vbox(spacing=6)
        me.append(label("ich", "accent"))
        chk = tui.Check("meinen stand teilen (läuft gerade, zuletzt gehört, empfehlungen)", f.share,
                        lambda on: (f.set_share(on), self.fill_friends()))
        me.append(chk)
        me.append(label("freunde mit deinem code sehen, was du hörst." if f.share
                        else "aus – niemand sieht etwas. mit einschalten wird dein code aktiv.", "dim", wrap=True))
        me.append(label("umfang und incognito stellst du in den einstellungen ein.", "dim", wrap=True))
        name = tui.Entry("dein name", text=f.name)
        name.connect("activate", lambda *_: (f.set_name(name.get_text()), self.say("name gespeichert")))
        me.append(name)
        code = label("", "accent")
        code.set_markup(f"<span size='x-large' weight='bold'>{fr.pretty(f.secret)}</span>")
        me.append(label("dein code", "dim"))
        me.append(code)
        me.append(hbox(tui.Button("󰆏 kopieren", lambda: self.copy_text(fr.pretty(f.secret), "code kopiert")),
                       tui.Button("󰑐 neuer code", lambda: (f.renew(), self.say("neuer code – alte freunde sehen dich nicht mehr"),
                                                          self.fill_friends()), danger=True), spacing=8))
        me.append(label("gib den code nur freunden. wer ihn kennt, kann deinen stand lesen – sonst niemand "
                        "(verschlüsselt, nur mit dem code lesbar).", "dim", wrap=True))
        seen = vbox(spacing=2)

        def toggle_seen():
            self._fr_seen = not getattr(self, "_fr_seen", False)
            self.fill_friends()
        seen.append(hbox(tui.Button(("‹ so sehen dich freunde" if getattr(self, "_fr_seen", False) else "󰈈 so sehen dich freunde"),
                                    toggle_seen), spacing=8))
        if getattr(self, "_fr_seen", False):
            p = f._payload()
            seen.append(label("teilen ist an." if f.share else "teilen ist aus – im moment sieht niemand etwas.", "dim"))
            if p.get("now"):
                seen.append(label(("spielt gerade: " if p["pl"] else "zuletzt: ") + f"{p['now']['t']} – {p['now']['a']}", "dim", wrap=True))
            if p["recent"]:
                seen.append(label("zuletzt gehört: " + " · ".join(r["t"] for r in p["recent"]), "dim", wrap=True))
            if p["recs"]:
                seen.append(label("empfehlungen: " + " · ".join(r["t"] for r in p["recs"]), "dim", wrap=True))
            for ln in prof_lines(p["pf"]) if p.get("pf") else []:
                seen.append(label(ln, "dim", wrap=True))
        me.append(seen)
        box.append(me)
        # --- Eingang: direkt geschickte Empfehlungen ---
        ib = f.inbox
        if ib:
            inbox = vbox(spacing=2)
            inbox.append(label("󰋑 für dich empfohlen", "accent"))
            for i, e in enumerate(ib):
                t = fr.to_track(e, e["from"])
                inbox.append(label(f"von {e['from']}", "dim"))
                inbox.append(track_row(t, lambda t=t: self.p.play_tracks([t]),
                                       [("✕", "Ausblenden", lambda i=i: (f.dismiss(i), self.fill_friends()))], menus=self.songs))
            box.append(inbox)
        # --- hinzufügen ---
        add = vbox(spacing=6)
        add.append(label("freund hinzufügen", "accent"))
        e = tui.Entry("code deines freundes")

        def go(*_):
            txt = e.get_text()

            def done(res):
                if isinstance(res, Exception):
                    self.say(str(res), error=True)
                else:
                    self.say(f"{res} hinzugefügt")
                    pass
                    self.fill_friends()
            tui.background(f.add, txt, done=done)
        e.connect("activate", go)
        add.append(hbox(e, tui.Button("+ hinzufügen", go), spacing=8))
        add.append(label("damit er dich auch sieht, schick ihm deinen code.", "dim"))
        box.append(add)
        # --- Freunde ---
        if not f.friends:
            box.append(label("noch niemand – füge oben einen code hinzu.", "dim"))
        for x in f.friends:
            box.append(self._friend_row(x))
        if f.recs:
            mine = vbox(spacing=2)
            mine.append(label("󰋑 meine empfehlungen", "accent"))
            for i, r in enumerate(f.recs):
                t = fr.to_track(r)
                row = track_row(t, lambda t=t: self.p.play_tracks([t]),
                                [("✕", "Empfehlung zurücknehmen", lambda r=r: (f.unrecommend(r["id"]), self.fill_friends()))],
                                menus=self.songs)
                mine.append(row)
            box.append(mine)

    @staticmethod
    def _now_text(x, f):
        """Aktuelles Lied als Text („titel – künstler“) oder Status."""
        pr = x.get("prof") or {}
        now = pr.get("now")
        if fr.inc_active(pr.get("inc")):
            until = int(pr.get("inc") or 0)
            return "󰗹 incognito" + (f" · bis {time.strftime('%H:%M', time.localtime(until))}" if until > 1 else ""), False
        if now and f.live(x):
            return f"󰝚 {now.get('t')} – {now.get('a')}", True
        if x.get("error") and not x.get("at"):
            return x["error"], False
        if not x.get("at"):
            return "noch nichts gesehen – hat er das teilen an?", False
        return f"hört gerade nichts · {ago(x.get('at'))}", False

    def _friend_row(self, x):
        """Container in der Liste: Name + aktuelles Lied (ohne Bild); Klick öffnet den Chat."""
        f = self.fr
        txt, live = self._now_text(x, f)
        row = Gtk.Box()
        row.add_css_class("row")
        row.add_css_class("trk")
        head = Gtk.Button(hexpand=True)
        head.add_css_class("rowhead")
        if live:
            row.add_css_class("frlive")        # Farben umgekehrt: Füllung in der Akzentfarbe
        n = f.unread(x["secret"])
        name = label(("● " if live else "") + x["name"], "accent")
        song = label(txt, "dim", ellipsize=True, hexpand=True, xalign=0)
        inner = hbox(label("󰍡", "glyph"), vbox(name, song, spacing=1), spacing=10)
        inner.get_last_child().set_hexpand(True)
        if n:
            inner.append(label(f"{n} neu", "accent"))
        inner.append(label("›", "accent"))
        head.set_child(inner)
        head.connect("clicked", lambda *_: self._fr_goto(("chat", x["secret"])))
        row.append(head)
        return row

    @staticmethod
    def _clock(ms):
        t = time.localtime(ms / 1000)
        today = time.localtime()
        if (t.tm_year, t.tm_yday) == (today.tm_year, today.tm_yday):
            return time.strftime("%H:%M", t)
        return time.strftime("%d.%m. %H:%M", t)

    def _fill_chat(self, x):
        f = self.fr
        box = self.fr_body
        sec = x["secret"]
        box.append(hbox(tui.Button("‹ freunde", lambda: self._fr_goto(None)), label("", hexpand=True),
                        tui.Button("󰑐", self.refresh_friends, tooltip="neu abfragen"), spacing=8))
        # Kopf: Name + aktuelles Lied mit Bild, Klick → Profil
        txt, live = self._now_text(x, f)
        now = (x.get("prof") or {}).get("now")
        cover = DotCover(56)
        cover.set_content_height(56)
        cover.set_valign(Gtk.Align.START)
        t = fr.to_track(now, x["name"]) if now else None
        cover.show(t["thumb"] if t and t.get("thumb") else None)
        head = Gtk.Button(hexpand=True)
        head.add_css_class("rowhead")
        head.add_css_class("frhead")
        if live:
            head.add_css_class("frlive")
        col = vbox(label(("● " if live else "") + x["name"], "accent"), label(txt, "dim", ellipsize=True, xalign=0),
                   label("profil ›", "dim"), spacing=2)
        col.set_hexpand(True)
        head.set_child(hbox(cover, col, spacing=12))
        head.connect("clicked", lambda *_: self._fr_goto(("profile", sec)))
        box.append(head)
        # Verlauf
        msgs = vbox(spacing=6)
        ms = f.messages(sec)[-80:]
        if not ms:
            msgs.append(label("noch keine nachrichten – schreib etwas oder empfiehl ein lied (rechtsklick auf einen titel → direkt an …).",
                              "dim", wrap=True))
        for m in ms:
            msgs.append(self._chat_msg(m, x))
        box.append(msgs)
        # Eingabe
        if getattr(self, "_chat_entry", None) is None:
            self._chat_entry = tui.Entry("nachricht …")

            def send(*_):
                cur = getattr(self, "_fr_view", None)
                txt2 = self._chat_entry.get_text().strip()
                fx = next((y for y in self.fr.friends if cur and y["secret"] == cur[1]), None)
                if fx and txt2 and self.fr.send_msg(fx, txt2):
                    self._chat_entry.set_text("")
                    self._fr_goto(cur)
                    self._chat_entry.grab_focus()
            self._chat_send = send
            self._chat_entry.connect("activate", send)

        def send_track(tr):
            if tr and f.send_msg(x, "", tr):
                self.say(f"an {x['name']} geschickt")
                self._fr_goto(("chat", sec))
            else:
                self.say("kein titel zum schicken" if not tr else "lokale titel lassen sich nicht schicken", error=bool(tr))
        music = tui.Button("󰝚 musik")
        music.connect("clicked", lambda *_: self._music_menu(music, x, send_track))
        send = tui.Button("senden", lambda: self._chat_send())
        self._chat_entry.set_valign(Gtk.Align.FILL)
        for b in (music, send):                   # Feld und Knöpfe gleich hoch
            b.set_valign(Gtk.Align.FILL)
        box.append(hbox(self._chat_entry, music, send, spacing=8))

    def _music_menu(self, anchor, x, send_track):
        """Menü am „musik“-Knopf: aktueller Titel oder ein anderer (Suche)."""
        pop = Gtk.Popover(has_arrow=False)
        pop.add_css_class("tpop")
        pop.add_css_class("kpop")
        pop.set_parent(anchor)
        pop.connect("closed", lambda p: GLib.idle_add(lambda: (p.unparent(), False)[1]))
        stack = Gtk.Stack(vhomogeneous=False)
        menu = vbox(spacing=2)
        cur = self.p.current

        def item(text, fn, sensitive=True):
            b = Gtk.Button(focus_on_click=False, sensitive=sensitive)
            b.add_css_class("opt")
            b.set_child(label(text, xalign=0))
            b.connect("clicked", lambda *_: fn())
            menu.append(b)
        item(("󰝚 aktueller song" + (f": {cur['title'][:28]}" if cur else "")), lambda: (pop.popdown(), send_track(cur)), bool(cur))
        item("󰍉 anderer song … (suche)", lambda: stack.set_visible_child_name("search"))
        stack.add_named(menu, "menu")
        sbox = vbox(spacing=4)
        e = tui.Entry("titel, künstler …")
        res = vbox(spacing=1)
        sbox.append(e)
        sbox.append(res)
        sbox.set_size_request(340, -1)
        gen = [0]

        def go(*_):
            q = e.get_text().strip()
            gen[0] += 1
            g = gen[0]
            if not q:
                return

            def done(r):
                if g != gen[0] or isinstance(r, Exception):
                    return
                tui.clear(res)
                for t in r[:8]:
                    b = Gtk.Button(focus_on_click=False)
                    b.add_css_class("opt")
                    b.set_child(label(f"{t['title']} – {t['artist']}", xalign=0, ellipsize=True))
                    b.connect("clicked", lambda *_, t=t: (pop.popdown(), send_track(t)))
                    res.append(b)
                if not r:
                    res.append(label("nichts gefunden", "dim"))
            tui.background(lambda: [t for t in map(engine.track, self.p.music.search(q, "songs")) if t], done=done)
        e.connect("activate", go)
        stack.add_named(sbox, "search")
        pop.set_child(stack)
        pop.popup()
        stack.connect("notify::visible-child-name", lambda *_: e.grab_focus() if stack.get_visible_child_name() == "search" else None)

    def _chat_msg(self, m, x):
        """Eigene Nachrichten rechts, gefüllt (Akzentfarbe); fremde links mit Rahmen."""
        me = bool(m.get("me"))
        col = vbox(spacing=2)
        col.set_halign(Gtk.Align.END if me else Gtk.Align.START)
        who = "du" if me else x["name"]
        stamp = self._clock(m.get("at") or 0) + (" · nicht gesendet" if m.get("failed") else "")
        head = hbox(label(f"{who} · {stamp}", "dim"), spacing=8)
        if self.fr.can_unsend(m):
            head.append(tui.Button("󰕌 zurücknehmen", lambda mid=m["mid"]: (self.fr.unsend(x, mid), self._fr_goto(("chat", x["secret"]))),
                                   tooltip="Noch 5 Minuten nach dem Senden möglich"))
        col.append(head)
        if m.get("x"):
            bub = Gtk.Box()
            bub.add_css_class("bub-me" if me else "bub-o")
            l = label(m["x"], wrap=True, xalign=0.0)
            l.set_selectable(True)
            l.set_max_width_chars(48)
            bub.append(l)
            bub.set_halign(Gtk.Align.END if me else Gtk.Align.START)
            col.append(bub)
        if m.get("t"):
            t = fr.to_track(m["t"], None if me else x["name"])
            col.append(label("du empfiehlst:" if me else "empfiehlt:", "dim", xalign=1.0 if me else 0.0))
            row = track_row(t, lambda t=t: self.p.play_tracks([t]),
                            [("+", "An Warteschlange anhängen", lambda t=t: self.p.add(t)),
                             ("»", "Als nächstes spielen", lambda t=t: self.p.add(t, next_=True))], menus=self.songs)
            wrap = Gtk.Box()
            wrap.add_css_class("bub-me-song" if me else "bub-o-song")
            wrap.append(row)
            row.set_hexpand(True)
            col.append(wrap)
        return col

    @staticmethod
    def _bar(frac):
        m = tui.Meter(maximum=100, interactive=False, mark=False, flush=True)
        m.set_value(max(0, min(100, round(frac * 100))))
        m.set_hexpand(True)
        return m

    def _profile_graphic(self, pf):
        """Hörprofil als Grafik: große Hörzeit, Balken für Künstler und Titel, Meter und Kennzahlen (größere Schrift)."""
        box = vbox(spacing=6)
        box.append(label("󰄨 hörprofil · diese woche", "dim"))
        big = label("", "accent")
        big.set_markup(f"<span size='xx-large' weight='bold'>{hmin(pf)}</span>")
        box.append(big)
        box.append(label("hörzeit" + (f" · {pf['n']} titel · {pf.get('ar')} künstler" if "n" in pf else ""), wrap=True))

        def bars(title, rows, unit):
            if not rows:
                return
            box.append(label(title, "dim"))
            top = max(v for _n, v in rows) or 1
            for n, v in rows:
                line = hbox(label(n, hexpand=True, ellipsize=True), label(unit(v), "dim"), spacing=8)
                box.append(line)
                box.append(self._bar(v / top))
        bars("top künstler", [(a["n"], a["m"]) for a in pf.get("art") or []],
             lambda m: f"{m // 60}h {m % 60}min" if m >= 60 else f"{m}min")
        bars("top titel", [(f"{t['t']} – {t['a']}", t["n"]) for t in pf.get("trk") or []], lambda n: f"{n}×")
        for key, name in (("sk", "übersprungen"), ("dv", "vielfalt"), ("t1", "beim lieblingskünstler"), ("rs", "wiederholt (3×+)"),
                          ("cr", "bis zum ende gehört")):
            if key in pf:
                v = max(0, min(100, int(pf[key])))
                box.append(hbox(label(name, hexpand=True), label(f"{v} %", "accent"), spacing=8))
                box.append(self._bar(v / 100))
        chips = []
        if "pk" in pf:
            chips.append(f"{pf['pk']} uhr · lieblingsstunde")
        if pf.get("ct"):
            chips.append(f"typ: {pf['ct']}")
        if "nw" in pf:
            chips.append(f"{pf['nw']} neue künstler")
        if pf.get("sn"):
            chips.append(f"{pf['sn']} tage in folge")
        if chips:
            box.append(label("  ·  ".join(chips), "accent", wrap=True))
        return box

    def _fill_profile(self, x):
        box = self.fr_body
        box.append(hbox(tui.Button("‹ chat", lambda: self._fr_goto(("chat", x["secret"]))), label("", hexpand=True), spacing=8))
        box.append(self._friend_card(x))

    def _top_list(self):
        """Wochen-Topliste aus den geteilten Hörprofilen (ich + Freunde), nach Rubrik wählbar."""
        f = self.fr
        cat = getattr(self, "_fr_cat", "h")
        panel = vbox(spacing=3)
        panel.append(label("󰔷 top-liste · diese woche", "accent"))
        chips = hbox(spacing=6)
        for key, name, _fn, _d in RUBRIKEN:
            b = tui.Button(name, lambda k=key: (setattr(self, "_fr_cat", k), self.fill_friends()))
            if key == cat:
                b.add_css_class("on")
            chips.append(b)
        panel.append(chips)
        entries = []
        mine = f._payload().get("pf") if f.share else None
        entries.append((f.name + " (ich)", mine, True))
        import analyse
        week = analyse.bounds("w", 0)[0] * 1000      # Wochenbeginn (Mo 4 Uhr, wie bei meiner eigenen Rechnung)
        for x in f.friends:
            # Profil-Stand ist ein Schnappschuss vom letzten Senden: älter als diese Woche = noch nichts gehört → nicht die Stunden der Vorwoche zeigen
            fresh = (x.get("at") or 0) >= week
            entries.append((x["name"], (x.get("prof") or {}).get("pf") if fresh else None, False))
        rows = top_rows(entries, cat)
        if not rows:
            panel.append(label("noch keine Angaben – Freunde müssen teilen (umfang normal/mehr für alles außer hörzeit; vielfalt, entdecker, serie nur bei „mehr“).", "dim", wrap=True))
        for i, (n, t, z, me) in enumerate(rows, 1):
            cls = ("accent",) if me else ()
            line = hbox(label(f"{i}.", "accent" if me else "dim"), label(n, *cls, hexpand=True, ellipsize=True),
                        label(t, *cls), spacing=8)
            panel.append(line)
            if z:
                panel.append(label("    " + z, "dim", wrap=True))
        absent = [n for n, pf, _m in entries if not pf]
        if absent:
            panel.append(label("ohne Angabe: " + ", ".join(absent), "dim", wrap=True))
        return panel

    def _friend_card(self, x):
        f = self.fr
        pr = x.get("prof") or {}
        card = vbox(spacing=3)
        live = f.live(x)
        card.append(label(("● " if live else "") + x["name"], "accent"))
        now = pr.get("now")
        if now and (live or x.get("at")):
            card.append(label("spielt gerade" if live else f"zuletzt gespielt · {ago(x.get('at'))}", "accent" if live else "dim"))
            t = fr.to_track(now, x["name"])
            card.append(track_row(t, lambda t=t, n=x["name"]: self.p.play_tracks([t]),
                                  [("+", "An Warteschlange anhängen", lambda t=t: self.p.add(t)),
                                   ("»", "Als nächstes spielen", lambda t=t: self.p.add(t, next_=True))], menus=self.songs))
        else:
            card.append(label(x.get("error") or "noch nichts gesehen – hat er das teilen an?" if not x.get("at")
                              else f"hört gerade nichts · {ago(x.get('at'))}", "dim"))

        def section(title, items):
            if not items:
                return
            card.append(label(title, "dim"))
            tracks = [fr.to_track(r, x["name"]) for r in items]
            for i, t in enumerate(tracks):
                card.append(track_row(t, lambda i=i, tr=tracks: self.p.play_tracks(tr, start=i),
                                      [("+", "An Warteschlange anhängen", lambda t=t: self.p.add(t)),
                                       ("»", "Als nächstes spielen", lambda t=t: self.p.add(t, next_=True))], menus=self.songs))
        section("empfiehlt", pr.get("recs"))
        rec = pr.get("recent") or []
        if rec:
            section(f"zuletzt gehört · {len(rec)}", rec)
        if pr.get("pf"):
            card.append(self._profile_graphic(pr["pf"]))
        if x.get("error") and x.get("at"):
            card.append(label(f"offline: {x['error']}", "dim"))
        card.append(hbox(tui.Button("󰆴 entfernen", lambda s=x["secret"]: (f.remove(s), self._fr_goto(None)),
                                    danger=True), spacing=8))

        return card
