"""Freunde-Seite (unter Bibliothek): eigener Code, Freund hinzufügen, was sie hören / empfehlen."""
import os
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
            self.connect("map", lambda *_: GLib.timeout_add(1500, self.ensure_username))   # Pflicht: Nutzername beim (ersten) Start

    def ask_username(self, first=False):
        """Fenster zum Festlegen/Ändern des Nutzernamens. Beim ersten Start Pflicht (nicht schließbar)."""
        f = self.fr
        if f is None or getattr(self, "_name_dlg", None) is not None:
            return
        dlg = Gtk.Window(title="nutzername", modal=True, transient_for=self if isinstance(self, Gtk.Window) else None, resizable=False)
        if first:
            dlg.set_deletable(False)
        dlg.set_default_size(380, 10)
        box = vbox(spacing=8)
        for m in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{m}")(16)
        box.append(label("wähle deinen nutzernamen" if first else "nutzernamen ändern", "accent"))
        box.append(label("so finden dich deine freunde. 3–20 zeichen: buchstaben, ziffern, . _ -  \n"
                         "gekoppelte geräte (handy/pc) teilen sich denselben namen.", "dim", wrap=True))
        e = tui.Entry("nutzername", text=f.name if (f.named and not first) else "")
        status = label("", "dim", wrap=True)
        ok = tui.Button("festlegen")

        def go(*_):
            txt = e.get_text()
            ok.set_sensitive(False)
            status.set_label("prüfe …")

            def done(res):
                ok.set_sensitive(True)
                if isinstance(res, Exception):
                    status.set_label(str(res))
                    return
                self._name_dlg = None
                dlg.destroy()
                self.say(f"nutzername: {f.name}")
                self.fill_friends()
                if getattr(self, "fr_name_lbl", None) is not None:
                    self.fr_name_lbl.set_label(f.name)
                for fn in ("update_peers", "update_handy"):           # Geräteliste zeigt „name (gerät)“
                    getattr(self, fn, lambda: None)()
            tui.background(f.set_username, txt, done=done)
        e.connect("activate", go)
        ok.connect("clicked", go)
        row = hbox(ok, spacing=8)
        if not first:
            row.append(tui.Button("abbrechen", lambda: (setattr(self, "_name_dlg", None), dlg.destroy())))
        box.append(e)
        box.append(status)
        box.append(row)
        pe = getattr(self.p, "peers", None)
        if first and pe is not None:
            # schon ein Gerät mit musicalist (Handy/PC) mit Namen? Dann koppeln – gekoppelte Geräte teilen denselben Namen
            box.append(label("— oder —", "dim"))
            box.append(label("du hast musicalist schon auf einem anderen gerät? koppeln übernimmt dessen namen.\n"
                             "dort: einstellungen → „handy koppeln“ (pc) bzw. „koppeln lassen“ (handy) – das zeigt adresse und code.", "dim", wrap=True))
            addr = tui.Entry("adresse, z. b. 192.168.1.20")
            code = tui.Entry("code, z. b. K7P2-QX9M")
            pst = label("", "dim", wrap=True)
            pb = tui.Button("󰌷 koppeln")

            def pair(*_):
                pb.set_sensitive(False)
                pst.set_label("koppelt …")

                def work():
                    pe.pair(addr.get_text().strip(), code.get_text())
                    return self.fr.named

                def done(res):
                    pb.set_sensitive(True)
                    if isinstance(res, Exception):
                        pst.set_label(str(res))
                    elif res:
                        self._name_dlg = None
                        dlg.destroy()
                        self.say(f"gekoppelt – nutzername: {f.name}")
                        self.fill_friends()
                    else:
                        pst.set_label("gekoppelt – aber das andere gerät hat noch keinen nutzernamen. leg dort zuerst einen fest.")
                tui.background(work, done=done)
            pb.connect("clicked", pair)
            code.connect("activate", pair)
            box.append(addr)
            box.append(code)
            box.append(pb)
            box.append(pst)
        dlg.set_child(box)
        dlg.connect("close-request", lambda *_: (first and not f.named))      # beim ersten Mal nicht schließbar
        dlg.connect("destroy", lambda *_: setattr(self, "_name_dlg", None))
        self._name_dlg = dlg
        dlg.present()
        e.grab_focus()

    def ensure_username(self):
        f = self.fr
        if f is not None and not f.named and self.get_visible():
            self.ask_username(first=True)
        return False

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
            self._fr_timer = GLib.timeout_add_seconds(12, self._fr_tick)

    def _fr_tick(self):
        """Alle 12 s den Eingang (Chat), alle 60 s zusätzlich den Stand aller Freunde."""
        if self.friends_visible() and self.get_visible():
            self._fr_n += 1
            if self._fr_n % 5 == 0:
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

    def open_profile(self):
        """Eigenes Profil (aus Bibliothek-Konto, Kontomenü oder Freunde-Liste)."""
        self.show_tab("stats")
        self.hear_select("friends")
        self._fr_goto(("me", "-"))

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
        if view and view[0] == "recaps":
            return self._fill_recaps()
        if view and view[0] == "me":
            return self._fill_me()
        x = next((x for x in f.friends if view and x["secret"] == view[1]), None)
        if view and x is None:
            view = self._fr_view = None
        if view and view[0] == "chat":
            return self._fill_chat(x)
        if view and view[0] == "profile":
            return self._fill_profile(x)
        rc = getattr(f, "recaps", None)
        top = hbox(label("", hexpand=True), *([tui.Button("󰄨 rückblicke", lambda: self._fr_goto(("recaps", "-")),
                                                         tooltip="Wochen-, Monats- und Jahresbild")] if rc is not None else []),
                   tui.Button("󰑐", self.refresh_friends, tooltip="neu abfragen"), spacing=8)
        box.append(top)
        new = rc.unseen[0] if rc is not None and rc.unseen else None
        if new is not None:               # neues Rückblick-Bild: Hinweis ganz oben
            kinds = {"w": "wochenrückblick", "m": "monatsrückblick", "y": "jahresrückblick"}
            b = Gtk.Button(hexpand=True)
            b.add_css_class("rowhead")
            b.add_css_class("frlive")
            b.set_child(hbox(vbox(label(f"󰄨 neu: {kinds.get(new['k'], 'rückblick')}", "accent"),
                                  label(f"{new['winner']} hat am meisten gehört · {new['win']} – ansehen und herunterladen", "dim", wrap=True),
                                  spacing=2), label("›", "accent"), spacing=10))
            b.connect("clicked", lambda *_: self._fr_goto(("recaps", "-")))
            box.append(b)
        box.append(self._top_list())
        # --- ich: eigenes Profil (gleiche Ansicht wie bei Freunden, plus Profil-Einstellungen) ---
        mb = Gtk.Button(hexpand=True)
        mb.add_css_class("rowhead")
        mb.set_child(hbox(vbox(label("󰀄 mein profil", "accent"),
                               label(f"{f.name} · " + ("teilen an" if f.share else "teilen aus") + " – ansehen und einstellen", "dim", wrap=True),
                               spacing=2), label("›", "accent"), spacing=10))
        mb.connect("clicked", lambda *_: self.open_profile())
        box.append(mb)
        # --- Eingang: direkt geschickte Empfehlungen ---
        ib = f.inbox
        if ib:
            inbox = vbox(spacing=2)
            inbox.append(label("󰋑 für dich empfohlen", "accent"))
            for i, e in enumerate(ib):
                inbox.append(label(f"von {e['from']}", "dim"))
                if self._album_row(e) is not None:
                    inbox.append(self._album_row(e))
                    continue
                t = fr.to_track(e, e["from"])
                inbox.append(track_row(t, lambda t=t: self.p.play_tracks([t]),
                                       [("✕", "Ausblenden", lambda i=i: (f.dismiss(i), self.fill_friends()))], menus=self.songs))
            box.append(inbox)
        # --- Anfragen an mich ---
        reqs = f.requests
        if reqs:
            rb = vbox(spacing=4)
            rb.append(label(f"󰀓 freundschaftsanfragen · {len(reqs)}", "accent"))
            for r in reqs:
                line = hbox(label(f"{r['name']}  ({r['uname']})", hexpand=True, ellipsize=True), spacing=8)

                def acc(r=r):
                    def done(res):
                        self.say(f"{res} ist jetzt dein freund" if not isinstance(res, Exception) else str(res), error=isinstance(res, Exception))
                        self.fill_friends()
                    tui.background(f.accept, r, done=done)
                line.append(tui.Button("annehmen", acc))
                line.append(tui.Button("ablehnen", lambda r=r: (f.decline(r), self.fill_friends()), danger=True))
                rb.append(line)
            box.append(rb)
        # --- hinzufügen: per Nutzername ---
        add = vbox(spacing=6)
        add.append(label("freund hinzufügen", "accent"))
        e = tui.Entry("nutzername deines freundes")

        def go(*_):
            txt = e.get_text()

            def done(res):
                if isinstance(res, Exception):
                    self.say(str(res), error=True)
                else:
                    self.say(f"anfrage an {res} geschickt – sobald die person annimmt, seid ihr befreundet")
                    e.set_text("")
                self.fill_friends()
            tui.background(f.request, txt, done=done)
        e.connect("activate", go)
        add.append(hbox(e, tui.Button("anfrage senden", go), spacing=8))
        for x in f.friends_sent:
            add.append(hbox(label(f"󰔛 an {x['name']} geschickt – wartet auf bestätigung", "dim", hexpand=True, ellipsize=True),
                            tui.Button("✕", lambda u=x["uname"]: (f.cancel_sent(u), self.fill_friends()), tooltip="Anfrage zurückziehen"), spacing=8))
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
                if self._album_row(r) is not None:
                    mine.append(self._album_row(r))
                    continue
                t = fr.to_track(r)
                row = track_row(t, lambda t=t: self.p.play_tracks([t]),
                                [("✕", "Empfehlung zurücknehmen", lambda r=r: (f.unrecommend(r["id"]), self.fill_friends()))],
                                menus=self.songs)
                mine.append(row)
            box.append(mine)

    def _album_row(self, e):
        """Von Freunden empfohlenes Album → Zeile (öffnen; Rechtsklick: speichern, abspielen …) oder None bei normalen Titeln."""
        if not fr.is_album(e):
            return None
        if str(e["id"]).startswith("pl:"):
            row = coll_row("󰲸", e.get("t") or "?", "playlist", lambda b=e["id"][3:]: self.open_detail("playlist", b[2:] if b.startswith("VL") else b))
            return row
        alb = {"browseId": e["id"][4:], "title": e.get("t"), "artist": e.get("a"), "thumb": e.get("th")}
        row = coll_row("󰀥", e.get("t") or "?", "album", lambda b=alb["browseId"]: self.open_detail("album", b), artist=(e.get("a") or "", None))
        self.songs.attach_album(row, alb)
        return row

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
        t = fr.to_track(now, x["name"]) if now and not fr.inc_active((x.get("prof") or {}).get("inc")) else None
        cover.show(t["thumb"] if t and t.get("thumb") else None)
        tile = Gtk.Box(valign=Gtk.Align.START)          # Kachel in der Hintergrundfarbe: das akzentfarbene Raster bliebe auf dem gefüllten Kopf unsichtbar
        tile.add_css_class("frcover")
        tile.append(cover)
        head = Gtk.Button(hexpand=True)
        head.add_css_class("rowhead")
        head.add_css_class("frhead")
        if live:
            head.add_css_class("frlive")
        col = vbox(label(("● " if live else "") + x["name"], "accent"), label(txt, "dim", ellipsize=True, xalign=0),
                   label("profil ›", "dim"), spacing=2)
        col.set_hexpand(True)
        head.set_child(hbox(tile, col, spacing=12))
        head.connect("clicked", lambda *_: self._fr_goto(("profile", sec)))
        box.append(head)
        # Verlauf (Telegram-Stil: Uhrzeit in der Blase, gleiche Person eng beieinander, Tagestrenner)
        msgs = vbox(spacing=0)
        ms = f.messages(sec)[-80:]
        if not ms:
            msgs.append(label("noch keine nachrichten – schreib etwas oder schick ein lied (󰝚 musik).", "dim", wrap=True))
        prev = None
        for m in ms:
            day = time.strftime("%Y%m%d", time.localtime((m.get("at") or 0) / 1000))
            new_day = prev is None or day != time.strftime("%Y%m%d", time.localtime((prev.get("at") or 0) / 1000))
            if new_day:
                chip = label(self._day_label(m.get("at") or 0), "dim")
                chip.add_css_class("day-chip")
                chip.set_halign(Gtk.Align.CENTER)
                chip.set_margin_top(6)
                chip.set_margin_bottom(6)
                msgs.append(chip)
            joined = (not new_day and prev is not None and bool(prev.get("me")) == bool(m.get("me"))
                      and (m.get("at") or 0) - (prev.get("at") or 0) < 5 * 60_000)
            w = self._chat_msg(m, x, joined)
            w.set_margin_top(0 if (prev is None or new_day) else (2 if joined else 8))
            msgs.append(w)
            prev = m
        box.append(msgs)
        # Eingabe: mehrzeilig, wächst mit dem Text (bis ca. 6 Zeilen). Enter sendet, Umschalt+Enter = neue Zeile
        if getattr(self, "_chat_entry", None) is None:
            tv = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=8, bottom_margin=8, left_margin=10, right_margin=10)
            tv.add_css_class("chat-input")
            sw = Gtk.ScrolledWindow(hexpand=True, propagate_natural_height=True, min_content_height=50, max_content_height=150,
                                    hscrollbar_policy=Gtk.PolicyType.NEVER, child=tv)
            sw.add_css_class("chat-input-box")
            self._chat_tv, self._chat_entry = tv, sw

            def send(*_):
                cur = getattr(self, "_fr_view", None)
                buf = self._chat_tv.get_buffer()
                txt2 = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()
                fx = next((y for y in self.fr.friends if cur and y["secret"] == cur[1]), None)
                if fx and txt2 and self.fr.send_msg(fx, txt2):
                    buf.set_text("")
                    self._fr_goto(cur)
                    self._chat_tv.grab_focus()
            self._chat_send = send
            keys = Gtk.EventControllerKey()

            def key(_c, kv, _kc, state):
                from gi.repository import Gdk
                if kv in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and not (state & Gdk.ModifierType.SHIFT_MASK):
                    send()
                    return True
                return False
            keys.connect("key-pressed", key)
            tv.add_controller(keys)

        def send_track(tr):
            if tr and f.send_msg(x, "", tr):
                self.say(f"an {x['name']} geschickt")
                self._fr_goto(("chat", sec))
            else:
                self.say("kein titel zum schicken" if not tr else "lokale titel lassen sich nicht schicken", error=bool(tr))
        music = tui.Button("󰝚 musik")
        music.connect("clicked", lambda *_: self._music_menu(music, x, send_track))
        send = tui.Button("senden", lambda: self._chat_send())
        for b in (music, send):                   # Knöpfe unten, so hoch wie das leere Feld
            b.set_valign(Gtk.Align.END)
            b.set_size_request(-1, 50)
        row = hbox(self._chat_entry, music, send, spacing=8)
        row.set_valign(Gtk.Align.END)
        box.append(row)

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

    @staticmethod
    def _day_label(ms):
        d = time.strftime("%Y%m%d", time.localtime(ms / 1000))
        if d == time.strftime("%Y%m%d"):
            return "heute"
        if d == time.strftime("%Y%m%d", time.localtime(time.time() - 86400)):
            return "gestern"
        return time.strftime("%d.%m.%Y", time.localtime(ms / 1000))

    def _chat_msg(self, m, x, joined=False):
        """Eigene Nachrichten rechts gefüllt (Akzentfarbe), fremde links mit Rahmen; Uhrzeit und ○/● (gelesen) klein in der Blase.
        Rechtsklick oder lange drücken = genauer ansehen."""
        me = bool(m.get("me"))
        stamp = time.strftime("%H:%M", time.localtime((m.get("at") or 0) / 1000))
        state = (" ✕" if m.get("failed") else (" ●" if m.get("rd") else " ○")) if me else ""
        col = vbox(spacing=2)
        col.set_halign(Gtk.Align.END if me else Gtk.Align.START)
        targets = []
        if m.get("x"):
            bub = Gtk.Box(spacing=8)
            bub.add_css_class("bub-me" if me else "bub-o")
            if joined:
                bub.add_css_class("joined")
            l = label(m["x"], wrap=True, xalign=0.0)
            l.set_max_width_chars(48)
            tm = label(stamp + state, "dim")
            tm.add_css_class("bub-time")
            tm.set_valign(Gtk.Align.END)
            bub.append(l)
            bub.append(tm)
            bub.set_halign(Gtk.Align.END if me else Gtk.Align.START)
            col.append(bub)
            targets.append(bub)
        if m.get("t"):
            arow = self._album_row(m["t"])
            t = None if arow is not None else fr.to_track(m["t"], None if me else x["name"])
            if not m.get("x"):
                col.append(label("du empfiehlst" if me else "empfiehlt", "dim", xalign=1.0 if me else 0.0))
            row = arow if arow is not None else track_row(t, lambda t=t: self.p.play_tracks([t]),
                            [("+", "An Warteschlange anhängen", lambda t=t: self.p.add(t)),
                             ("»", "Als nächstes spielen", lambda t=t: self.p.add(t, next_=True))], menus=self.songs)
            wrap = Gtk.Box()
            wrap.add_css_class("bub-me-song" if me else "bub-o-song")
            wrap.append(row)
            row.set_hexpand(True)
            col.append(wrap)
            if not m.get("x"):
                tm = label(stamp + state, "dim", xalign=1.0)
                tm.add_css_class("bub-time-out")
                col.append(tm)
            targets.append(wrap)
        for w in targets:                         # Rechtsklick / langes Drücken → genauer ansehen
            g = Gtk.GestureClick(button=3)
            g.connect("pressed", lambda g_, n, px, py, w=w: self._msg_inspect(w, m, x))
            w.add_controller(g)
            lp = Gtk.GestureLongPress()
            lp.connect("pressed", lambda g_, px, py, w=w: self._msg_inspect(w, m, x))
            w.add_controller(lp)
        return col

    def _msg_inspect(self, widget, m, x):
        """Nachricht genauer ansehen: Zeiten, Lesestatus, Aktionen (wie Apple Nachrichten)."""
        f = self.fr
        pop = Gtk.Popover(has_arrow=False)
        pop.add_css_class("tpop")
        pop.add_css_class("kpop")
        pop.set_parent(widget)
        pop.connect("closed", lambda p: GLib.idle_add(lambda: (p.unparent(), False)[1]))
        box = vbox(spacing=2)
        me = bool(m.get("me"))
        fmt = lambda ms: time.strftime("%d.%m.%Y, %H:%M:%S", time.localtime(ms / 1000))
        box.append(label("deine nachricht" if me else f"nachricht von {x['name']}", "accent"))
        box.append(label(("gesendet: " if me else "empfangen: ") + fmt(m.get("at") or 0) + (" · nicht zugestellt" if m.get("failed") else ""), "dim"))
        if me:
            box.append(label(f"gelesen: {fmt(m['rd'])}" if m.get("rd") else "noch nicht gelesen", "dim"))

        def item(text, fn, danger=False):
            b = Gtk.Button(focus_on_click=False)
            b.add_css_class("opt")
            if danger:
                b.add_css_class("danger")
            b.set_child(label(text, xalign=0))
            b.connect("clicked", lambda *_: (pop.popdown(), GLib.idle_add(lambda: (fn(), False)[1])))
            box.append(b)
        if m.get("x"):
            item("󰆏 text kopieren", lambda: self.copy_text(m["x"], "kopiert"))
        if m.get("t") and fr.is_album(m["t"]):
            item("󰀥 öffnen", lambda: self.open_detail("playlist" if str(m["t"]["id"]).startswith("pl:") else "album", m["t"]["id"].split(":", 1)[1]))
        elif m.get("t"):
            t = fr.to_track(m["t"], None if me else x["name"])
            item("󰐊 jetzt abspielen", lambda: self.p.play_tracks([t]))
            item("» als nächstes", lambda: self.p.add(t, next_=True))
            item("+ an warteschlange anhängen", lambda: self.p.add(t))
        if me:
            if f.can_unsend(m):
                until = time.strftime("%H:%M", time.localtime(((m.get("at") or 0) + f.UNSEND_MS) / 1000))
                item(f"󰕌 zurücknehmen (noch bis {until} uhr)", lambda: (f.unsend(x, m["mid"]), self._fr_goto(("chat", x["secret"]))), danger=True)
            else:
                box.append(label("zurücknehmen ging nur 5 minuten lang", "dim"))
        pop.set_child(box)
        pop.popup()

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

    def _fill_recaps(self):
        """Alle Rückblick-Bilder: ansehen, herunterladen (nach ~/Pictures/musicalist), Ordner öffnen."""
        f = self.fr
        rc = f.recaps
        box = self.fr_body
        box.append(hbox(tui.Button("‹ freunde", lambda: self._fr_goto(None)), label("󰄨 rückblicke", "accent", hexpand=True), spacing=8))
        fresh = {i["key"] for i in rc.unseen}
        rc.mark_seen()
        if not rc.items:
            box.append(label("jeden sonntagabend entsteht dein wochenrückblick, am monatsletzten der monatsrückblick, an silvester der "
                             "jahresrückblick – mit der farbe der person mit der meisten hörzeit, ihrem meistgespielten lied und den ranglisten "
                             "deiner freunde. unter einstellungen → freunde kannst du die bilder automatisch herunterladen lassen.", "dim", wrap=True))
        from gi.repository import GdkPixbuf
        for it in rc.items:
            row = hbox(spacing=12)
            row.add_css_class("bub-me-song" if it["key"] in fresh else "bub-o-song")
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(rc.path(it), 160, 200, True)
                pic = Gtk.Picture.new_for_pixbuf(pb)
                pic.set_size_request(pb.get_width(), pb.get_height())
                pic.set_can_shrink(False)
                row.append(pic)
            except Exception:  # noqa: BLE001
                pass
            col = vbox(spacing=2)
            col.set_hexpand(True)
            col.append(label(it["title"], "accent", wrap=True))
            col.append(label(it["range"], "dim"))
            col.append(label(f"{it['winner']} · {it['win']}" + ("  · neu" if it["key"] in fresh else ""), "accent" if it["key"] in fresh else ""))

            def save(it=it):
                try:
                    p = rc.save_pictures(it)
                    self.say(f"gespeichert: {p}")
                except Exception as e:  # noqa: BLE001
                    self.say(f"speichern geht nicht: {e}", error=True)
            col.append(hbox(tui.Button("ansehen", lambda it=it: self._recap_big(it)), tui.Button("󰇚 herunterladen", save),
                            tui.Button("󰉋 ordner", lambda it=it: (save(), engine.open_url(os.path.join(os.path.expanduser("~"), "Pictures", "musicalist")))),
                            spacing=8))
            row.append(col)
            box.append(row)

    def _recap_big(self, it):
        from gi.repository import GdkPixbuf
        rc = self.fr.recaps
        win = Gtk.Window(title=it["title"], transient_for=self if isinstance(self, Gtk.Window) else None, modal=True)
        pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(rc.path(it), 760, 950, True)
        pic = Gtk.Picture.new_for_pixbuf(pb)
        pic.set_size_request(pb.get_width(), pb.get_height())
        pic.set_can_shrink(False)
        win.set_child(pic)
        win.present()

    def _fill_profile(self, x):
        box = self.fr_body
        box.append(hbox(tui.Button("‹ chat", lambda: self._fr_goto(("chat", x["secret"]))), label("", hexpand=True), spacing=8))
        box.append(self._friend_card(x))
        # alle Musikempfehlungen zwischen uns beiden, aus dem Chat
        msgs = self.fr.messages(x["secret"])
        for title, mine in (("󰋑 von dir empfohlen", True), ("󰋑 hat dir empfohlen", False)):
            items = [m for m in reversed(msgs) if bool(m.get("me")) == mine and m.get("t")]
            if not items:
                continue
            sec = vbox(spacing=2)
            sec.append(label(f"{title} · {len(items)}", "accent"))
            tracks = [fr.to_track(m["t"], x["name"]) for m in items if not fr.is_album(m["t"])]
            ti = -1
            for m in items:
                sec.append(label(time.strftime("%d.%m.%Y, %H:%M", time.localtime((m.get("at") or 0) / 1000)) +
                                 (" · gelesen" if mine and m.get("rd") else ""), "dim"))
                if fr.is_album(m["t"]):
                    sec.append(self._album_row(m["t"]))
                    continue
                ti += 1
                i, t = ti, tracks[ti]
                sec.append(track_row(t, lambda i=i, tr=tracks: self.p.play_tracks(tr, start=i),
                                     [("+", "An Warteschlange anhängen", lambda t=t: self.p.add(t)),
                                      ("»", "Als nächstes spielen", lambda t=t: self.p.add(t, next_=True))], menus=self.songs))
            box.append(sec)

    def _fill_me(self):
        """Mein Profil: genau die Ansicht, die Freunde von mir haben – darunter die Profil-Einstellungen."""
        f, box = self.fr, self.fr_body
        box.append(hbox(tui.Button("‹ freunde", lambda: self._fr_goto(None)), label("", hexpand=True), spacing=8))
        p = f._payload()
        inc = bool(f.inc_until)
        pr = {"now": p.get("now"), "pl": p.get("pl"), "recent": p.get("recent") or [], "recs": p.get("recs") or [],
              "pf": p.get("pf"), "inc": p.get("inc")}
        me = {"name": f.name, "prof": pr, "at": int(time.time() * 1000), "secret": "-"}
        if not f.share:
            box.append(label("teilen ist aus – so siehst nur du dein profil, freunde sehen nichts.", "dim", wrap=True))
        elif inc:
            box.append(label("incognito an – freunde sehen nur, dass du incognito bist.", "dim", wrap=True))
        box.append(self._friend_card(me, me=True))
        box.append(self._me_settings())

    def _me_settings(self):
        f = self.fr
        sb = vbox(spacing=6)
        sb.set_margin_top(10)
        sb.append(label("profil-einstellungen", "accent"))
        sb.append(tui.Check("meinen stand mit freunden teilen (läuft gerade, zuletzt gehört, empfehlungen)", f.share,
                            lambda on: (f.set_share(on), self.fill_friends()),
                            tooltip="Nur für Freunde, die du bestätigt hast."))
        sb.append(label("aus – niemand sieht etwas." if not f.share else "freunde sehen dein profil wie oben.", "dim", wrap=True))
        sb.append(label("nutzername", "dim"))
        nm = label("", "accent")
        nm.set_markup(f"<span size='x-large' weight='bold'>{GLib.markup_escape_text(f.name)}</span>")
        sb.append(nm)
        sb.append(hbox(tui.Button("✎ ändern", self.ask_username), spacing=8))
        sb.append(label("freunde suchen dich mit diesem namen und schicken dir eine anfrage, die du bestätigst.", "dim", wrap=True))
        sb.append(label("umfang – was freunde sehen", "dim"))
        row = hbox(spacing=6)
        btns = {}

        def paint():
            for k, b in btns.items():
                (b.add_css_class if k == f.level else b.remove_css_class)("on")
        for k in f.LEVELS:
            b = tui.Button(k, lambda k=k: (f.set_level(k), paint(), self.fill_friends()))
            btns[k] = b
            row.append(b)
        paint()
        sb.append(row)
        sb.append(label("minimal: läuft gerade, letzte 5 titel, hörzeit der woche · normal: dazu empfehlungen, top künstler/titel, "
                        "lieblingsstunde, skip-rate · mehr: dazu typ, vielfalt, wiederholer, neue künstler, durchhör-quote, serie.",
                        "dim", wrap=True))
        sb.append(tui.Check("lesebestätigungen senden („gelesen“ bei den anderen)", f.read_receipts,
                            lambda on: f.set_read_receipts(on)))
        rc = getattr(f, "recaps", None)
        if rc is not None:
            sb.append(label("󰄨 rückblick-bilder: sonntags ein wochenbild, am monatsletzten ein monatsbild, an silvester ein jahresbild",
                            "dim", wrap=True))
            sb.append(tui.Check("bilder automatisch herunterladen (~/Pictures/musicalist)", rc.auto, lambda on: rc.set_auto(on)))

            def test_recap():
                def done(res):
                    if isinstance(res, Exception):
                        self.say(f"rückblick: {res}", error=True)
                    else:
                        self.say("fertig – unter freunde → 󰄨 rückblicke" if res else "noch keine zahlen für diese woche")
                tui.background(lambda: rc.make("w", force=True), done=done)
            sb.append(hbox(tui.Button("󰄨 wochenbild jetzt testweise", test_recap),
                           tui.Button("󰄨 rückblicke ansehen", lambda: self._fr_goto(("recaps", "-"))), spacing=8))
        sb.append(label("󰗹 incognito – andere sehen nicht, was du hörst (nur dass du incognito bist)", "dim", wrap=True))
        state = label("", "dim", wrap=True)

        def paint_inc():
            u = f.inc_until
            state.set_label("aus." if not u else ("an, bis du es ausschaltest." if u == 1
                                                  else f"an bis {time.strftime('%H:%M', time.localtime(u))}."))
        inc = hbox(spacing=6)
        for txt, mins in (("15 min", 15), ("30 min", 30), ("bis ich ausschalte", 0)):
            inc.append(tui.Button(txt, lambda m=mins: (f.set_incognito(m), paint_inc(), self.fill_friends())))
        inc.append(tui.Button("aus", lambda: (f.set_incognito(None), paint_inc(), self.fill_friends())))
        paint_inc()
        sb.append(inc)
        sb.append(state)
        return sb

    def _top_list(self):
        """Wochen-Topliste aus den geteilten Hörprofilen (ich + Freunde). Rubrik per Dropdown wählen: in der Auswahl steht je
        Rubrik rechts die Person auf Platz 1; gewählt wird die ganze Rangliste gezeigt."""
        f = self.fr
        cat = getattr(self, "_fr_cat", "") or "h"
        menu = getattr(self, "_fr_menu", False)
        panel = vbox(spacing=3)
        panel.append(label("󰔷 top-liste · diese woche", "accent"))
        entries = []
        mine = f._payload().get("pf") if f.share else None
        entries.append((f.name + " (ich)", mine, True))
        import analyse
        week = analyse.bounds("w", 0)[0] * 1000      # Wochenbeginn (Mo 4 Uhr, wie bei meiner eigenen Rechnung)
        for x in f.friends:
            # Profil-Stand ist ein Schnappschuss vom letzten Senden: älter als diese Woche = noch nichts gehört → nicht die Stunden der Vorwoche zeigen
            fresh = (x.get("at") or 0) >= week
            entries.append((x["name"], (x.get("prof") or {}).get("pf") if fresh else None, False))
        names = {k: n for k, n, _f, _d in RUBRIKEN}
        head = Gtk.Button(hexpand=True)
        head.add_css_class("rowhead")
        head.add_css_class("on")
        head.set_child(hbox(label(names[cat], "accent", hexpand=True, xalign=0), label("󰅃" if menu else "󰅀", "dim"), spacing=10))
        head.connect("clicked", lambda *_: (setattr(self, "_fr_menu", not menu), self.fill_friends()))
        panel.append(head)
        if menu:
            for key, name, _fn, _d in RUBRIKEN:
                r = top_rows(entries, key)
                right = label(f"{r[0][0]} · {r[0][1]}", *(("accent",) if r[0][3] else ())) if r else label("–", "dim")
                b = Gtk.Button(hexpand=True)
                b.add_css_class("rowhead")
                if key == cat:
                    b.add_css_class("on")
                b.set_child(hbox(label(name, hexpand=True, xalign=0), right, spacing=10))
                b.connect("clicked", lambda *_, k=key: (setattr(self, "_fr_cat", k), setattr(self, "_fr_menu", False), self.fill_friends()))
                panel.append(b)
        rows = top_rows(entries, cat)
        if not rows:
            panel.append(label("noch keine Angaben – Freunde müssen teilen (umfang normal/mehr für alles außer hörzeit; vielfalt, entdecker, serie nur bei „mehr“).", "dim", wrap=True))
        for i, (n, t, z, me) in enumerate(rows, 1):
            cls = ("accent",) if me else ()
            panel.append(hbox(label(f"{i}.", "accent" if me else "dim"), label(n, *cls, hexpand=True, ellipsize=True),
                              label(t, *cls), spacing=8))
            if z:
                panel.append(label("    " + z, "dim", wrap=True))
        absent = [n for n, pf, _m in entries if not pf]
        if absent:
            panel.append(label("ohne Angabe: " + ", ".join(absent), "dim", wrap=True))
        return panel

    def _friend_card(self, x, me=False):
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
            card.append(label("hörst gerade nichts" if me else
                              x.get("error") or "noch nichts gesehen – hat er das teilen an?" if not x.get("at")
                              else f"hört gerade nichts · {ago(x.get('at'))}", "dim"))

        def section(title, items):
            if not items:
                return
            card.append(label(title, "dim"))
            for r in items:
                if self._album_row(r) is not None:
                    card.append(self._album_row(r))
            tracks = [fr.to_track(r, x["name"]) for r in items if not fr.is_album(r)]
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
        if not me:
            card.append(hbox(tui.Button("󰆴 entfernen", lambda s=x["secret"]: (f.remove(s), self._fr_goto(None)),
                                        danger=True), spacing=8))

        return card
