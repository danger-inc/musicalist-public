# musicalist – Einstellungen-Seite (Teil von MusicWindow, siehe ui.py). Methoden greifen auf self (das Hauptfenster) zu.
import os, time

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Graphene, Gtk, Pango, PangoCairo

import tui
from tui import label, hbox, vbox, esc
import engine
from engine import fmt
from rows import track_row, coll_row, artist_link
from widgets import Cover, preview_supported, DESK_POS


class SettingsMixin:

    # ---------- einstellungen ----------
    def build_settings(self):
        page = vbox(spacing=8)
        page.set_margin_top(6)
        # ganz oben: Konto (Status + Anmeldung neu einlesen) – der Kontoname wird nie gezeigt
        self.set_acct = vbox(spacing=8)
        page.append(tui.Panel("󰀄 konto", self.set_acct))
        self.fill_settings_account()
        page.append(tui.theme_panel())
        panel = tui.Panel("einstellungen")
        self.hover_chk = tui.Check("vorschau-karte am unteren bildschirmrand (hover)", engine.setting("hover"),
                                   self.set_hover,
                                   tooltip="Maus an den unteren Bildschirmrand → kleine Karte mit Titel und Knöpfen")
        panel.body.append(self.hover_chk)
        if preview_supported():
            hint = "braucht wayland mit layer-shell (hyprland, sway …). bei problemen einfach aus lassen."
        else:
            hint = "hier nicht verfügbar: braucht gtk4-layer-shell und einen wayland-compositor mit layer-shell."
            self.hover_chk.set_sensitive(False)
        panel.body.append(label(hint, "dim", wrap=True, xalign=0))
        self.eco_chk = tui.Check("live-spektrum auch im energiesparmodus zeigen", engine.setting("eco_spec"),
                                 lambda on: engine.set_setting("eco_spec", on),
                                 tooltip="Standard: aus – im Energiesparmodus (Waybar-Akku oder Design-Einstellungen)\n"
                                         "verschwindet das Spektrum unten auf Seite 1 und cava wird beendet.")
        self.eco_chk.set_margin_top(10)
        panel.body.append(self.eco_chk)
        self.bg_chk = tui.Check("beim schließen im hintergrund weiterspielen", engine.setting("background"),
                                lambda on: engine.set_setting("background", on),
                                tooltip="Aus: ✕ / q beendet musicalist ganz, die Musik stoppt.\n"
                                        "An: das Fenster verschwindet nur, die Musik läuft weiter.")
        self.bg_chk.set_margin_top(10)
        panel.body.append(self.bg_chk)
        panel.body.append(label("aus: ✕ / q beendet musicalist, die musik stoppt. an: nur das fenster geht zu.",
                                "dim", wrap=True, xalign=0))
        self.hist_chk = tui.Check("hörverlauf führen", engine.setting("history"), self.set_history,
                                  tooltip="An: gehörte Titel landen in der Leiste am linken Rand (h).\n"
                                          "Aus: nichts wird gemerkt, die Leiste ist weg.")
        self.hist_chk.set_margin_top(10)
        panel.body.append(self.hist_chk)
        self.hist_info = label("", "dim", wrap=True, xalign=0)
        panel.body.append(hbox(self.hist_info, tui.Button("verlauf löschen", self.clear_history, danger=True),
                               spacing=10))
        self.hist_info.set_hexpand(True)
        self.update_hist_info()
        self.yt_chk = tui.Check("wiedergaben an youtube melden", engine.setting("yt_history"),
                                lambda on: (engine.set_setting("yt_history", on), on or setattr(self.p, "_ytr", None)),
                                tooltip="Wie die Website: gehörte Titel landen im YouTube-Verlauf und zählen für\n"
                                        "„diesen Monat gehört“, Rückblick und Empfehlungen. Braucht die Anmeldung.")
        self.yt_chk.set_margin_top(10)
        panel.body.append(self.yt_chk)
        panel.body.append(label("ab 10 s wiedergabe landet ein titel im youtube-verlauf, die gehörte zeit wird "
                                "mitgeschickt. nur mit anmeldung.", "dim", wrap=True, xalign=0))
        self.desk_chk = tui.Check("anzeige immer auf dem hintergrundbild", engine.setting("desk"), self.set_desk,
                                  tooltip="Die Karte aus der Vorschau liegt dauerhaft auf dem Desktop –\n"
                                          "unter den Fenstern, sichtbar wo der Hintergrund frei ist.")
        self.desk_chk.set_margin_top(10)
        self.desk_pos = tui.Select(self.set_desk_pos, tooltip="Wo auf dem Bildschirm")
        self.desk_pos.set_options(DESK_POS, engine.setting("desk_pos"))
        panel.body.append(hbox(self.desk_chk, label("", hexpand=True), self.desk_pos, spacing=10))
        if not preview_supported():
            self.desk_chk.set_sensitive(False)
            self.desk_pos.set_sensitive(False)
        page.append(panel)
        page.append(self.build_offline())
        page.append(self.build_local())
        page.append(self.build_ytdlp())
        self.add_page("settings", page)
        self.on_hover_changed = None       # setzt musicd: schaltet die Vorschau live ein/aus
        self.on_desk_changed = None        # setzt musicd: Anzeige auf dem Hintergrund an/aus/verschieben

    def fill_settings_account(self):
        box = getattr(self, "set_acct", None)
        if box is None:
            return
        tui.clear(box)
        if self.account is not None:
            box.append(hbox(label("● angemeldet · youtube music", "accent", hexpand=True, ellipsize=True),
                            tui.Button("󰑐 anmeldung neu einlesen", self.login,
                                       tooltip="Anmeldung erneut aus Zen/Firefox übernehmen"),
                            tui.Button("abmelden", self.do_logout, danger=True), spacing=8))
        elif self.login_expired:
            box.append(hbox(label("⚠ anmeldung abgelaufen", "err", hexpand=True),
                            tui.Button("󰑐 anmeldung neu einlesen", self.login), spacing=8))
        else:
            box.append(hbox(label("○ nicht angemeldet", "dim", hexpand=True),
                            tui.Button("󰍂 mit zen / firefox anmelden", self.login), spacing=8))
        box.append(label("liest die anmeldung aus deinem browser (music.youtube.com) – nötig, wenn likes, "
                         "bibliothek oder radio nicht mehr gehen.", "dim", wrap=True, xalign=0))

    def set_history(self, on):
        engine.set_setting("history", on)
        if not on:
            self.p._hist = None             # laufender Titel wird auch nicht mehr eingetragen
        self.drawer.set_enabled(on)
        self.update_hist_info()
        self.say("hörverlauf an" if on else "hörverlauf aus – es wird nichts mehr gemerkt")

    def clear_history(self):
        self.p.history.clear()
        self.p.emit("history")
        self.update_hist_info()
        self.say("hörverlauf gelöscht")

    # ---------- lokale Musik ----------
    def build_local(self):
        panel = tui.Panel("󰉋 lokale musik")
        self.local_chk = tui.Check("musikdateien aus einem ordner abspielen", engine.setting("local"),
                                   self.set_local_on,
                                   tooltip="mp3, flac, ogg, opus, m4a … – erscheint in der bibliothek und in der suche (lokal)")
        panel.body.append(self.local_chk)
        self.local_dir_lbl = label("", "dim", hexpand=True, ellipsize=True, xalign=0)
        panel.body.append(hbox(self.local_dir_lbl,
                               tui.Button("󰉋 ordner wählen …", self.pick_local_dir),
                               tui.Button("󰑐 neu einlesen", lambda: self.rescan_local(say_done=True)), spacing=10))
        self.local_info = label("", "dim", wrap=True, xalign=0)
        panel.body.append(self.local_info)
        panel.body.append(label("lokale titel haben kein radio, keine likes und keinen youtube-verlauf; "
                                "songtexte werden trotzdem gesucht.", "dim", wrap=True, xalign=0))
        self.update_local_info()
        return panel

    def update_local_info(self):
        lib = self.p.locallib
        d = engine.setting("local_dir") or lib.root or lib.default_root()
        self.local_dir_lbl.set_label(d)
        self.local_info.set_label((f"{len(lib.tracks)} titel gefunden" if self.local_scanned else
                                   "noch nicht eingelesen") if engine.setting("local") else "aus")

    def set_local_on(self, on):
        engine.set_setting("local", on)
        self.update_local_panel()
        if on:
            self.rescan_local(say_done=True)
        self.update_local_info()

    def pick_local_dir(self):
        dlg = Gtk.FileDialog(title="Musikordner wählen")
        cur = engine.setting("local_dir") or self.p.locallib.default_root()
        if os.path.isdir(cur):
            dlg.set_initial_folder(Gio.File.new_for_path(cur))

        def done(d, res):
            try:
                f = d.select_folder_finish(res)
            except GLib.Error:
                return
            engine.set_setting("local_dir", f.get_path())
            self.local_scanned = False
            self.rescan_local(say_done=True)
        dlg.select_folder(self, None, done)

    # ---------- yt-dlp ----------
    def build_ytdlp(self):
        panel = tui.Panel("󰚰 wiedergabe-motor (yt-dlp)")
        self.ytdlp_chk = tui.Check("wöchentlich automatisch aktualisieren", engine.setting("ytdlp_auto"),
                                   lambda on: engine.set_setting("ytdlp_auto", on),
                                   tooltip="YouTube ändert ständig etwas – ein altes yt-dlp spielt dann nichts mehr.")
        self.ytdlp_info = label("", "dim", hexpand=True, xalign=0)
        panel.body.append(self.ytdlp_chk)
        panel.body.append(hbox(self.ytdlp_info,
                               tui.Button("󰑐 jetzt aktualisieren", lambda: (
                                   self.say("prüfe yt-dlp …"), self.p.update_ytdlp(quiet=False),
                                   GLib.timeout_add_seconds(20, self.update_ytdlp_info)),
                                   tooltip="Sofort nach einer neuen Version suchen"), spacing=10))
        panel.body.append(label("geht ein titel plötzlich nicht mehr, aktualisiert musicalist das von selbst "
                                "(höchstens alle 6 h).", "dim", wrap=True, xalign=0))
        self.update_ytdlp_info()
        return panel

    def update_ytdlp_info(self):
        t = engine.setting("ytdlp_checked") or 0
        when = time.strftime("%d.%m. %H:%M", time.localtime(t)) if t else "noch nie"
        self.ytdlp_info.set_label(f"version {engine.ytdlp_version()} · zuletzt geprüft {when}")
        return False

    # ---------- offline (meistgehört) ----------
    def build_offline(self):
        panel = tui.Panel("󰇚 offline · meistgehört")
        b = panel.body
        self.off_chk = tui.Check("meistgehörte titel speichern", engine.setting("offline"), self.set_offline,
                                 tooltip="Die Titel, die du in letzter Zeit am häufigsten hörst, liegen als Datei\n"
                                         "auf dem Rechner: spielen sofort und auch ohne Internet.")
        self.off_n = tui.Select(self.set_offline_n, tooltip="Wie viele Titel")
        self.off_mb = tui.Select(self.set_offline_mb, tooltip="Höchstens so viel Platz belegen")
        b.append(hbox(self.off_chk, label("", hexpand=True), label("anzahl", "dim"), self.off_n,
                      label("limit", "dim"), self.off_mb, spacing=10))
        b.append(label("zählt wie oft du einen titel hörst; was du länger nicht mehr hörst, rutscht von allein "
                       "raus und wird wieder gelöscht. abgleich beim start, alle 6 h und sobald ein titel neu "
                       "in die spitze kommt. braucht den hörverlauf.", "dim", wrap=True, xalign=0))
        self.off_info = label("", "dim", wrap=True, xalign=0, hexpand=True)
        b.append(hbox(self.off_info, tui.Button("󰑐 jetzt abgleichen", self.offline_sync), spacing=10))
        self.off_list = vbox(spacing=0)
        b.append(self.off_list)
        self.p.offline.listeners.append(self.update_offline)
        self.update_offline()
        return panel

    def set_offline(self, on):
        engine.set_setting("offline", on)
        self.p.offline.sync()
        self.update_offline()
        self.say("meistgehörte werden gespeichert" if on else "offline aus – gespeicherte titel werden gelöscht")

    OFF_MB = [(0, "unbegrenzt"), (500, "500 mb"), (1024, "1 gb"), (2048, "2 gb"), (5120, "5 gb"), (10240, "10 gb")]

    def set_offline_mb(self, v):
        engine.set_setting("offline_mb", int(v))
        self.p.offline.sync()
        self.update_offline()

    def set_offline_n(self, v):
        engine.set_setting("offline_n", int(v))
        self.p.offline.sync()
        self.update_offline()

    def offline_sync(self):
        if not self.p.offline.sync():
            self.say("abgleich läuft schon")
        self.update_offline()

    def update_offline(self):
        off = self.p.offline
        on = engine.setting("offline")
        n = engine.setting("offline_n") or 25
        self.off_n.set_options([(str(k), f"top {k}") for k in (10, 25, 50, 100)], str(n))
        self.off_mb.set_options([(str(k), name) for k, name in self.OFF_MB], str(engine.setting("offline_mb") or 0))
        top = off.top(n) if on else []
        have = sum(1 for t, _s, _c in top if off.path(t["videoId"]))
        mb = off.size() / 1e6
        npin = len(off.pins)
        pin_txt = f" · {npin} von dir gemerkt" if npin else ""
        if not on:
            extra = len(off.index) - sum(1 for v in off.pins if v in off.index)
            txt = "aus" + (f" · {extra} dateien werden gelöscht …" if extra > 0 else "") + pin_txt
        elif off.busy and off.status:
            txt = f"{off.status}  ·  {have}/{len(top)} da · {mb:.0f} mb"
        elif not top:
            txt = "noch nichts oft genug gehört – ein titel braucht ≈ 2 wiedergaben in letzter zeit"
        else:
            cap = engine.setting("offline_mb")
            txt = f"{have}/{len(top)} gespeichert · {mb:.0f}" + (f" von {cap} mb" if cap else " mb") + \
                pin_txt + " · nur auf diesem rechner"
        if not engine.setting("history"):
            txt += " · hörverlauf ist aus, es wird nicht mehr gezählt"
        self.off_info.set_label(txt)
        tui.clear(self.off_list)
        if npin:
            head = label("von dir gemerkt (bleiben, bis du sie entfernst)", "accent", xalign=0)
            head.set_margin_top(6)
            self.off_list.append(head)
            for vid, t in list(off.pins.items()):
                mark = "✓" if off.path(vid) else "⟳" if off.current == vid else "·"
                row = Gtk.Box()
                row.add_css_class("row")
                b = Gtk.Button(hexpand=True)
                b.add_css_class("rowhead")
                b.set_child(hbox(label(mark, "accent" if mark != "·" else "dim"),
                                 label(t.get("title") or "?", hexpand=True, ellipsize=True, xalign=0),
                                 label(t.get("artist") or "", "dim", ellipsize=True), spacing=8))
                b.connect("clicked", lambda _b, tt=t: self.p.play_now(dict(tt)))
                row.append(b)
                x = Gtk.Button(label="✕", tooltip_text="Nicht mehr offline halten", valign=Gtk.Align.CENTER)
                x.add_css_class("mini")
                x.connect("clicked", lambda _b, v=vid: self.p.offline.unpin([v]))
                row.append(x)
                self.off_list.append(row)
            if top:
                head = label("meistgehört (automatisch)", "accent", xalign=0)
                head.set_margin_top(6)
                self.off_list.append(head)
        for i, (t, _s, cnt) in enumerate(top):
            vid = t["videoId"]
            mark = "✓" if off.path(vid) else "⟳" if off.current == vid else "·"
            row = Gtk.Button(hexpand=True)
            row.add_css_class("rowhead")
            row.set_child(hbox(label(f"{i + 1:>2}", "dim"), label(mark, "accent" if mark != "·" else "dim"),
                               label(t.get("title") or "?", hexpand=True, ellipsize=True, xalign=0),
                               label(t.get("artist") or "", "dim", ellipsize=True),
                               label(f"{cnt}×", "dim"), spacing=8))
            row.connect("clicked", lambda _b, tt=t: self.p.play_now(dict(tt)))
            self.off_list.append(row)
        return False

    def update_hist_info(self):
        n = len(self.p.history.items)
        on = engine.setting("history")
        self.hist_info.set_label(("leiste am linken rand (h) · " if on else "aus · ") +
                                 (f"{n} titel gespeichert, nur auf diesem rechner" if n else "nichts gespeichert"))

    def set_desk(self, on):
        engine.set_setting("desk", on)
        if self.on_desk_changed:
            self.on_desk_changed()

    def set_desk_pos(self, v):
        self.desk_pos.set_options(DESK_POS, v)
        engine.set_setting("desk_pos", v)
        if self.on_desk_changed:
            self.on_desk_changed()

    def set_hover(self, on):
        engine.set_setting("hover", on)
        if self.on_hover_changed:
            self.on_hover_changed(on)
