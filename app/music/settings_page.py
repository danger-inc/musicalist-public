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
                                 tooltip="Standard: an. Aus = im Energiesparmodus (Waybar-Akku oder Design-Einstellungen)\n"
                                         "verschwindet das Spektrum unten auf Seite 1 und cava wird beendet.")
        self.eco_chk.set_margin_top(10)
        panel.body.append(self.eco_chk)
        def set_intern(on):
            engine.set_setting("spec_src", "intern" if on else "auto")
            self.p.set_tap(engine.spec_intern_wanted())
            self.cava.want(None, False)
            self.sync_cava()
        self.intern_chk = tui.Check("spektrum ohne cava berechnen (mpv misst selbst)", engine.setting("spec_src") == "intern",
                                    set_intern,
                                    tooltip="Standard: aus – cava, wenn es da ist und Töne liefert; sonst übernimmt mpv von selbst.\n"
                                            "An: immer die eingebaute Messung (läuft überall, auch ohne PipeWire/cava, unter Windows).")
        panel.body.append(self.intern_chk)
        self.bg_chk = tui.Check("beim schließen im hintergrund weiterspielen", engine.setting("background"),
                                lambda on: engine.set_setting("background", on),
                                tooltip="Aus: ✕ / q beendet musicalist ganz, die Musik stoppt.\n"
                                        "An: das Fenster verschwindet nur, die Musik läuft weiter.")
        self.bg_chk.set_margin_top(10)
        panel.body.append(self.bg_chk)
        self.fr_chk = tui.Check("meinen stand mit freunden teilen", getattr(self.p.friends, "share", True) if getattr(self.p, "friends", None) else True,
                                lambda on: self.p.friends.set_share(on) if getattr(self.p, "friends", None) else None,
                                tooltip="Was läuft, zuletzt gehört, Empfehlungen, Wochenprofil – nur für Freunde mit deinem Code (Bibliothek → freunde).")
        self.fr_chk.set_margin_top(10)
        panel.body.append(self.fr_chk)
        fr_ = getattr(self.p, "friends", None)
        if fr_ is not None:
            panel.body.append(label("umfang – was freunde sehen", "dim", xalign=0))
            self.fr_lv_row = hbox(spacing=6)
            self.fr_lv_btns = {}

            def paint_lv():
                for k, b in self.fr_lv_btns.items():
                    (b.add_css_class if k == fr_.level else b.remove_css_class)("on")
            for k in fr_.LEVELS:
                b = tui.Button(k, lambda k=k: (fr_.set_level(k), paint_lv()))
                self.fr_lv_btns[k] = b
                self.fr_lv_row.append(b)
            paint_lv()
            panel.body.append(self.fr_lv_row)
            panel.body.append(label("minimal: läuft gerade, letzte 5 titel, hörzeit der woche · normal: dazu empfehlungen, top künstler/titel, "
                                    "lieblingsstunde, skip-rate · mehr: dazu typ, vielfalt, wiederholer, neue künstler, durchhör-quote, serie.",
                                    "dim", wrap=True, xalign=0))
            panel.body.append(label("󰗹 incognito – andere sehen nicht, was du hörst (nur dass du incognito bist)", "dim", xalign=0))
            self.fr_inc_state = label("", "dim", wrap=True, xalign=0)

            def paint_inc():
                u = fr_.inc_until
                self.fr_inc_state.set_label("aus." if not u else ("an, bis du es ausschaltest." if u == 1
                                            else f"an bis {time.strftime('%H:%M', time.localtime(u))}."))
            inc_row = hbox(spacing=6)
            for txt, mins in (("15 min", 15), ("30 min", 30), ("bis ich ausschalte", 0)):
                inc_row.append(tui.Button(txt, lambda m=mins: (fr_.set_incognito(m), paint_inc())))
            inc_row.append(tui.Button("aus", lambda: (fr_.set_incognito(None), paint_inc())))
            paint_inc()
            panel.body.append(inc_row)
            panel.body.append(self.fr_inc_state)
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
        page.append(self.build_handy())
        page.append(self.build_spotify())
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
            self.p.journal.cur = None
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

    # ---------- spotify-import (DSGVO-Datenexport → playlists, spotify_import.py) ----------
    def build_spotify(self):
        panel = tui.Panel("󰓇 von spotify importieren")
        b = panel.body
        b.append(label("spotify → privatsphäre → „deine daten herunterladen“ (kontodaten). aus der zip-datei (oder dem entpackten "
                       "ordner) werden playlists und gespeicherte titel gelesen, jeder titel wird in youtube music gesucht und "
                       "als private playlist angelegt. braucht die anmeldung (⚙ → konto).", "dim", wrap=True, xalign=0))
        self.sp_file = label("", "dim", hexpand=True, ellipsize=True, xalign=0)
        self.sp_list = vbox(spacing=2)
        self.sp_sel = {}
        self.sp_state = label("", "accent", wrap=True, xalign=0)
        self.sp_go = tui.Button("󰐊 importieren", self.spotify_go)
        self.sp_go.set_visible(False)
        b.append(hbox(self.sp_file, tui.Button("󰈙 export wählen …", self.spotify_pick),
                      tui.Button("󰉋 ordner …", lambda: self.spotify_pick(True)), spacing=10))
        b.append(self.sp_list)
        b.append(hbox(self.sp_go, self.sp_state, spacing=10))
        self.sp_pls = []
        self.sp_cancel = None
        return panel

    def spotify_pick(self, folder=False):
        dlg = Gtk.FileDialog(title="Spotify-Export wählen")
        home = Gio.File.new_for_path(os.path.expanduser("~/Downloads"))
        if home.query_exists(None):
            dlg.set_initial_folder(home)

        def done(d, res):
            try:
                f = (d.select_folder_finish if folder else d.open_finish)(res)
            except GLib.Error:
                return
            self.spotify_load(f.get_path())
        (dlg.select_folder if folder else dlg.open)(self, None, done)

    def spotify_load(self, path):
        import spotify_import as si
        try:
            self.sp_pls = si.parse(path)
        except Exception as e:  # noqa: BLE001
            self.sp_pls = []
            self.say(f"spotify-export nicht lesbar: {e}", error=True)
        self.sp_file.set_label(os.path.basename(path))
        while (c := self.sp_list.get_first_child()):
            self.sp_list.remove(c)
        self.sp_sel = {}
        if not self.sp_pls:
            self.sp_state.set_label("keine playlists gefunden – ist das der export „kontodaten“ (Playlist1.json)?")
            self.sp_go.set_visible(False)
            return
        for i, p in enumerate(self.sp_pls):
            self.sp_sel[i] = True
            self.sp_list.append(tui.Check(f"{p['name']} · {len(p['tracks'])} titel", True,
                                          lambda on, i=i: self.sp_sel.__setitem__(i, on)))
        self.sp_state.set_label(f"{len(self.sp_pls)} playlists gefunden")
        self.sp_go.set_visible(True)

    def spotify_go(self):
        import spotify_import as si
        if not os.path.exists(engine.BROWSER_JSON):
            self.say("zum importieren erst bei youtube music anmelden", error=True)
            return
        if self.sp_cancel is not None:
            self.sp_cancel.set()
            return
        pick = [p for i, p in enumerate(self.sp_pls) if self.sp_sel.get(i)]
        if not pick:
            return
        import threading
        self.sp_cancel = threading.Event()
        self.sp_go.set_label("󰜺 abbrechen")

        def prog(d, t, txt):
            GLib.idle_add(self.sp_state.set_label, txt)

        def work():
            try:
                rep = si.run(self.p.music, pick, prog, self.sp_cancel)
            except Exception as e:  # noqa: BLE001
                rep = {"made": 0, "tracks": 0, "missing": [], "errors": [engine.explain(e)]}
            GLib.idle_add(fin, rep)

        def fin(rep):
            self.sp_cancel = None
            self.sp_go.set_label("󰐊 importieren")
            txt = f"{rep['made']} playlists angelegt ({rep['tracks']} titel)"
            if rep["missing"]:
                txt += f" · {len(rep['missing'])} nicht gefunden (Liste: {si.MISSING_FILE})"
            if rep["errors"]:
                txt += " · " + "; ".join(rep["errors"][:2])
            self.sp_state.set_label(txt)
            self.say(txt, error=bool(rep["errors"]))
            if rep["made"] and hasattr(self, "refresh_library"):
                try:
                    self.refresh_library()
                except Exception:  # noqa: BLE001
                    pass
        threading.Thread(target=work, daemon=True).start()

    # ---------- handy-app (abgleich im wlan, handy_sync.py) ----------
    def build_handy(self):
        panel = tui.Panel("󰄜 handy-app")
        b = panel.body
        self.handy_info = label("", "dim", wrap=True, xalign=0, hexpand=True)
        self.handy_btn = tui.Button("󰌷 handy koppeln", self.handy_pair,
                                    tooltip="Zeigt einen Code für 3 Minuten – in der Handy-App unter\n"
                                            "einstellungen → pc-abgleich eintippen.")
        b.append(hbox(self.handy_info, self.handy_btn, spacing=10))
        self.handy_code = label("", "accent", xalign=0)
        self.handy_code.set_selectable(True)
        self.handy_code.set_visible(False)
        b.append(self.handy_code)
        self.handy_list = vbox(spacing=4)
        b.append(self.handy_list)
        # weitere rechner: dieser rechner verbindet sich mit einem, auf dem „handy koppeln“ gedrückt wurde
        sep = label("weiteres gerät (pc oder musicalist-handy)", "accent", xalign=0)
        sep.set_margin_top(8)
        b.append(sep)
        self.peer_addr = tui.Entry("adresse des anderen geräts", width=22)
        self.peer_code = tui.Entry("code (8 zeichen)", width=12)
        self.peer_btn = tui.Button("󰌷 verbinden", self.peer_pair,
                                   tooltip="Am anderen Gerät: pc → einstellungen → „handy koppeln“, handy →\n"
                                           "einstellungen → „koppeln lassen“. Adresse und Code hier eintragen.")
        b.append(hbox(self.peer_addr, self.peer_code, self.peer_btn, spacing=8))
        self.peer_list = vbox(spacing=4)
        b.append(self.peer_list)
        b.append(label("das hörprotokoll von handy und allen gekoppelten rechnern wird im wlan zusammengeführt – analyse "
                       "und hörzeit zeigen dann alles, auch über ketten (handy–pc 1–pc 2). auf wunsch übernimmt das handy die youtube-anmeldung von hier. alles verschlüsselt, "
                       f"nur gekoppelte geräte. braucht port {self._handy_port()}/tcp in der firewall "
                       f"(z. b. sudo ufw allow {self._handy_port()}/tcp).", "dim", wrap=True, xalign=0))
        h = getattr(self.p, "handy", None)
        if h is not None:
            h.listeners.append(self.update_handy)
        pe = getattr(self.p, "peers", None)
        if pe is not None:
            pe.listeners.append(self.update_peers)
        self.update_handy()
        self.update_peers()
        return panel

    def peer_pair(self):
        pe = getattr(self.p, "peers", None)
        if pe is None:
            return
        addr, code = self.peer_addr.get_text(), self.peer_code.get_text()
        self.say("verbinde …")

        def done(res):
            if isinstance(res, Exception):
                self.say(str(res), error=True)
            else:
                self.peer_code.set_text("")
                self.say(f"mit {res} verbunden – hörprotokoll wird abgeglichen")
        tui.background(pe.pair, addr, code, done=done)

    def update_peers(self):
        pe = getattr(self.p, "peers", None)
        if pe is None or getattr(self, "peer_list", None) is None:
            return False
        tui.clear(self.peer_list)
        for pid, d in sorted(pe.peers.items(), key=lambda kv: kv[1].get("paired") or 0):
            last = d.get("last")
            when = time.strftime("%d.%m. %H:%M", time.localtime(last)) if last else "noch nie"
            info = f"⚠ {d['error']}" if d.get("error") else f"abgleich {when} · {d.get('got', 0)} einträge"
            self.peer_list.append(hbox(
                label(f"󰟀 {d.get('name') or 'gerät'}", hexpand=True, xalign=0, ellipsize=True),
                label(info, "dim", ellipsize=True),
                tui.Button("jetzt", lambda i=pid: tui.background(pe.sync_peer, i)),
                tui.Button("entfernen", lambda i=pid: pe.remove(i), danger=True), spacing=10))
        return False

    @staticmethod
    def _handy_port():
        import handy_sync
        return handy_sync.PORT

    def handy_pair(self):
        h = getattr(self.p, "handy", None)
        if h is None:
            return
        ok, code, ips = h.start_pairing()
        if not ok:
            self.say(f"abgleich startet nicht: {h.error}")
            return
        self.handy_code.set_label(f"code  {code}   ·   adresse  {', '.join(ips) or '?'}   ·   3 min gültig")
        self.handy_code.set_visible(True)
        until = time.time() + 180

        def tick():
            if h.pairing is None or time.time() > until:
                self.handy_code.set_visible(False)
                h.stop_pairing()
                return False
            return True
        GLib.timeout_add_seconds(2, tick)
        self.update_handy()

    def update_handy(self):
        h = getattr(self.p, "handy", None)
        if h is None or getattr(self, "handy_list", None) is None:
            return False
        tui.clear(self.handy_list)
        if h.pairing is None:
            self.handy_code.set_visible(False)
        if h.error:
            self.handy_info.set_label(f"⚠ {h.error}")
        elif not h.devices:
            self.handy_info.set_label("noch kein handy gekoppelt")
        else:
            self.handy_info.set_label(("● abgleich bereit" if h.running else "○ aus") + f" · {len(h.devices)} gerät(e)")
        for dev_id, d in sorted(h.devices.items(), key=lambda kv: kv[1].get("paired") or 0):
            last = d.get("last")
            when = time.strftime("%d.%m. %H:%M", time.localtime(last)) if last else "noch nie"
            self.handy_list.append(hbox(label(f"󰄜 {d.get('name') or 'handy'}", hexpand=True, xalign=0, ellipsize=True),
                                        label(f"abgleich {when} · {d.get('got', 0)} einträge", "dim"),
                                        tui.Button("entfernen", lambda i=dev_id: h.remove(i), danger=True),
                                        spacing=10))
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
