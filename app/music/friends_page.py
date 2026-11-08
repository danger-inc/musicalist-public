"""Freunde-Seite (unter Bibliothek): eigener Code, Freund hinzufügen, was sie hören / empfehlen."""
import time

from gi.repository import GLib

import tui
import engine
from tui import label, hbox, vbox
from rows import track_row
import friends as fr


def prof_lines(pf):
    out = [f"diese woche: {pf.get('h')} h · {pf.get('n')} titel · {pf.get('ar')} künstler"]
    if pf.get("art"):
        out.append("top künstler: " + " · ".join(f"{a['n']} ({a['m']} min)" for a in pf["art"]))
    if pf.get("trk"):
        out.append("top titel: " + " · ".join(f"{t['t']} {t['n']}×" for t in pf["trk"]))
    if "pk" in pf:
        out.append(f"am liebsten um {pf['pk']} uhr · überspringt {pf.get('sk', 0)} %")
    return out


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
        self.lib_stack.add_named(page, "friends")
        # Zeile auf der Bibliothek-Startseite
        self.fr_panel = tui.Panel("󰡉 freunde")
        self.fr_row_box = vbox(spacing=0)
        self.fr_panel.body.append(self.fr_row_box)
        self.lib_home_box.insert_child_after(self.fr_panel, self.coll_panel)
        self.update_friends_row()
        self._fr_timer = 0
        f = self.fr
        if f is not None:
            f.say = lambda m: GLib.idle_add(lambda: (self.say(m), False)[1])
            f.listeners.append(lambda: GLib.idle_add(self._fr_changed))

    def _fr_changed(self):
        self.update_friends_row()
        if self.lib_stack.get_visible_child_name() == "friends":
            self.fill_friends()
        return False

    @property
    def fr(self):
        return getattr(self.p, "friends", None)

    def update_friends_row(self):
        from rows import coll_row
        tui.clear(self.fr_row_box)
        f = self.fr
        live = sum(1 for x in f.friends if f.live(x)) if f else 0
        sub = (f"{live} hören gerade" if live else f"{len(f.friends)} freunde") if f and f.friends else "code, hinzufügen, was sie hören"
        self.fr_row_box.append(coll_row("󰡉", "freunde", sub, self.open_friends))

    def open_friends(self):
        self.lib_stack.set_visible_child_name("friends")
        self.show_tab("lib")
        self.nav_note()
        self.fill_friends()
        self.refresh_friends()
        if not self._fr_timer:
            self._fr_timer = GLib.timeout_add_seconds(25, self._fr_tick)

    def _fr_tick(self):
        if self.lib_stack.get_visible_child_name() == "friends" and self.get_visible():
            self.refresh_friends()
            return True
        self._fr_timer = 0
        return False

    def refresh_friends(self):
        f = self.fr
        if not f:
            return

        def done(_):
            self.update_friends_row()
            if self.lib_stack.get_visible_child_name() == "friends":
                self.fill_friends()
        tui.background(f.refresh, done=done)

    def fill_friends(self):
        f = self.fr
        box = self.fr_body
        tui.clear(box)
        if f is None:
            box.append(label("freunde nicht verfügbar", "dim"))
            return
        top = hbox(self._sh(tui.Button("‹ zurück", self.lib_home), "‹ zurück", "‹"), label("", hexpand=True),
                   tui.Button("󰑐", self.refresh_friends, tooltip="neu abfragen"), spacing=8)
        box.append(top)
        # --- ich ---
        me = vbox(spacing=6)
        me.append(label("ich", "accent"))
        chk = tui.Check("meinen stand teilen (läuft gerade, zuletzt gehört, empfehlungen)", f.share,
                        lambda on: (f.set_share(on), self.fill_friends()))
        me.append(chk)
        me.append(label("freunde mit deinem code sehen, was du hörst." if f.share
                        else "aus – niemand sieht etwas. mit einschalten wird dein code aktiv.", "dim", wrap=True))
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
                    self.update_friends_row()
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
            box.append(self._friend_card(x))
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
            on = x["secret"] in self.fr_open

            def tog(s=x["secret"]):
                self.fr_open.symmetric_difference_update({s})
                self.fill_friends()
            card.append(hbox(tui.Button(("‹ zuletzt gehört" if on else f"zuletzt gehört · {len(rec)}"), tog), spacing=8))
            if on:
                section("", rec)
        if pr.get("pf"):
            on = ("pf" + x["secret"]) in self.fr_open

            def tog_pf(s="pf" + x["secret"]):
                self.fr_open.symmetric_difference_update({s})
                self.fill_friends()
            card.append(hbox(tui.Button(("‹ hörprofil" if on else "󰄨 hörprofil"), tog_pf), spacing=8))
            if on:
                for ln in prof_lines(pr["pf"]):
                    card.append(label(ln, "dim", wrap=True))
        if x.get("error") and x.get("at"):
            card.append(label(f"offline: {x['error']}", "dim"))
        card.append(hbox(tui.Button("󰆴 entfernen", lambda s=x["secret"]: (f.remove(s), self.update_friends_row(), self.fill_friends()),
                                    danger=True), spacing=8))

        return card
