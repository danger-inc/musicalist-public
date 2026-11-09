"""Freunde-Seite (unter Bibliothek): eigener Code, Freund hinzufügen, was sie hören / empfehlen."""
import time

from gi.repository import GLib, Gtk

import tui
import engine
from tui import label, hbox, vbox
from rows import track_row
import friends as fr


def prof_lines(pf):
    out = [f"diese woche: {pf.get('h')} h" + (f" · {pf['n']} titel · {pf.get('ar')} künstler" if "n" in pf else "")]
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
    return (pf["h"], f"{pf['h']} h", "") if "h" in pf else None


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
            self._fr_timer = GLib.timeout_add_seconds(25, self._fr_tick)

    def _fr_tick(self):
        if self.friends_visible() and self.get_visible():
            self.refresh_friends()
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

    def fill_friends(self):
        f = self.fr
        box = self.fr_body
        tui.clear(box)
        if f is None:
            box.append(label("freunde nicht verfügbar", "dim"))
            return
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
        if f.share:
            lv = vbox(spacing=4)
            lv.append(label("umfang – was freunde sehen", "dim"))
            row = hbox(spacing=6)
            for key, txt in (("minimal", "minimal"), ("normal", "normal"), ("mehr", "mehr")):
                b = tui.Button(txt, lambda k=key: (f.set_level(k), self.fill_friends()))
                if f.level == key:
                    b.add_css_class("on")
                row.append(b)
            lv.append(row)
            lv.append(label({"minimal": "läuft gerade, letzte 5 titel, gehörte stunden der woche – sonst nichts.",
                             "normal": "dazu empfehlungen, titel-/künstlerzahl, top künstler & titel, lieblingsstunde, skip-rate.",
                             "mehr": "wie normal (gleich viele titel), dazu zahlen aus der analyse: typ, vielfalt, lieblingskünstler-anteil, wiederholer, neue künstler, durchhör-quote, serie."}[f.level], "dim", wrap=True))
            me.append(lv)
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
        card.append(hbox(tui.Button("󰆴 entfernen", lambda s=x["secret"]: (f.remove(s), self.fill_friends()),
                                    danger=True), spacing=8))

        return card
