# musicalist – andere Audioquellen (Ersatz für das mpris-Modul in der Waybar):
# MPRIS-Player (Zen, Spotify, …) mit Titel und Steuerung, dazu Apps, die gerade hörbar Ton ausgeben,
# aber kein MPRIS haben (Spiele, Discord, …). Fragt nur ab, solange jemand zuschaut (want()).
import json, subprocess, threading

import tui
from tui import Gio, GLib, Gtk
from tui import label, hbox, vbox

OWN = "musicalist"
ICONS = {"zen": "󰈹", "firefox": "", "chromium": "", "chrome": "", "helium": "", "spotify": "",
         "vlc": "󰕼", "mpv": "", "discord": "󰙯", "vesktop": "󰙯", "steam": "", "telegram": ""}
CSS = """
.src-row { padding: 1px 0; }
.src-icon { color: @primary; min-width: 18px; }
.src-row.paused .src-icon, .src-row.paused .src-text { opacity: 0.55; }
"""


def icon_for(*names):
    for n in names:
        n = (n or "").lower()
        for k, ic in ICONS.items():
            if k in n:
                return ic
    return "󰕾"


class Sources:
    """Hält self.items aktuell: [{key, icon, app, text, playing, bus, can_next}]; meldet Änderungen an listeners."""
    INTERVAL = 1200

    def __init__(self):
        self.items, self.listeners, self.wanted = [], [], set()
        self.timer = None
        self.busy = False
        self.bus = None

    def want(self, who, on):
        (self.wanted.add if on else self.wanted.discard)(who)
        if self.wanted and self.timer is None:
            self.poll()
            self.timer = GLib.timeout_add(self.INTERVAL, self.poll)
        elif not self.wanted and self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None

    def poll(self):
        if not self.busy:
            self.busy = True
            threading.Thread(target=self._work, daemon=True).start()
        return True

    def _work(self):
        try:
            items = self.collect()
        except Exception:
            items = self.items
        GLib.idle_add(self._done, items)

    def _done(self, items):
        self.busy = False
        if items != self.items:
            self.items = items
            for fn in self.listeners:
                fn(items)
        return False

    # ----- Abfrage (läuft im Thread) -----
    def _props(self, name, iface):
        r = self.bus.call_sync(name, "/org/mpris/MediaPlayer2", "org.freedesktop.DBus.Properties", "GetAll",
                               GLib.Variant("(s)", (iface,)), None, Gio.DBusCallFlags.NONE, 500, None)
        return r.unpack()[0]

    def collect(self):
        if self.bus is None:
            self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        names = self.bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                                   "ListNames", None, None, Gio.DBusCallFlags.NONE, 500, None).unpack()[0]
        players = []
        for name in sorted(n for n in names if n.startswith("org.mpris.MediaPlayer2.")):
            inst = name[len("org.mpris.MediaPlayer2."):]
            if inst.split(".")[0] in (OWN, "playerctld"):   # playerctld spiegelt nur andere Player
                continue
            try:
                root = self._props(name, "org.mpris.MediaPlayer2")
                pl = self._props(name, "org.mpris.MediaPlayer2.Player")
            except GLib.Error:
                continue
            status = pl.get("PlaybackStatus", "Stopped")
            if status == "Stopped":
                continue
            md = pl.get("Metadata", {})
            artist = ", ".join(md.get("xesam:artist") or [])
            title = md.get("xesam:title") or ""
            app = root.get("Identity") or inst.split(".")[0]
            app = app.replace("Mozilla ", "").strip()
            app = app[:1].upper() + app[1:]
            players.append({"key": name, "bus": name, "icon": icon_for(root.get("DesktopEntry"), app, inst),
                            "app": app, "match": {(root.get("DesktopEntry") or "").lower(), app.lower(),
                                                  inst.split(".")[0].lower()},
                            "text": " – ".join(x for x in (artist, title) if x) or "ohne titel",
                            "playing": status == "Playing", "can_next": bool(pl.get("CanGoNext")),
                            "can_raise": bool(root.get("CanRaise"))})
        # Apps, die gerade Ton ausgeben (nicht stummgeschaltet/pausiert)
        try:
            out = subprocess.run(["pactl", "-f", "json", "list", "sink-inputs"], capture_output=True, text=True,
                                 timeout=2).stdout
            streams = json.loads(out or "[]")
        except Exception:
            streams = []
        loose = {}
        for s in streams:
            if s.get("corked") or s.get("mute"):
                continue
            pr = s.get("properties", {})
            app = pr.get("application.name") or pr.get("application.process.binary") or "unbekannt"
            binary = (pr.get("application.process.binary") or "").lower()
            if OWN in (app.lower(), binary):
                continue
            hit = [p for p in players if any(m and (m in app.lower() or m in binary) for m in p["match"])]
            if hit:
                continue      # gehört zu einem MPRIS-Player, der schon in der Liste steht
            media = pr.get("media.name") or ""
            if media in ("(null)", "audio stream", "Playback", "AudioStream"):
                media = ""
            e = loose.setdefault(app.lower(), {"key": "pa:" + app.lower(), "bus": None,
                                               "icon": icon_for(binary, app), "app": app, "text": media,
                                               "playing": True, "can_next": False, "can_raise": False})
            if not e["text"] and media:
                e["text"] = media
        for p in players:
            p.pop("match")
        # Laufende zuerst
        return sorted(players, key=lambda p: not p["playing"]) + list(loose.values())


def control(bus, method):
    """MPRIS-Befehl an einen anderen Player (PlayPause, Next, Previous, Raise)."""
    iface = "org.mpris.MediaPlayer2" if method == "Raise" else "org.mpris.MediaPlayer2.Player"
    Gio.bus_get_sync(Gio.BusType.SESSION, None).call(
        bus, "/org/mpris/MediaPlayer2", iface, method, None, None, Gio.DBusCallFlags.NONE, 1000, None, None)


class SourceList(Gtk.Box):
    """Zeilen „󰈹 Zen  Dua Lipa – Levitating  [⏯] [⏭]“ – eine pro Quelle."""

    def __init__(self, sources, limit=4, show_app=True):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.limit, self.show_app = limit, show_app
        self.on_change = None
        sources.listeners.append(self.fill)
        self.fill(sources.items)

    def fill(self, items):
        tui.clear(self)
        for it in items[:self.limit]:
            self.append(self.row(it))
        self.set_visible(bool(items))
        if self.on_change:
            self.on_change(items)

    def row(self, it):
        icon = label(it["icon"], "src-icon")
        text = label(it["text"], "src-text", ellipsize=True, hexpand=True)
        parts = [icon]
        if self.show_app:
            parts.append(label(it["app"], "accent"))
        parts.append(text)
        r = hbox(*parts, spacing=8)
        r.add_css_class("src-row")
        r.set_tooltip_text(f"{it['app']}: {it['text']}" if it["text"] else it["app"])
        if not it["playing"]:
            r.add_css_class("paused")
        if it["bus"]:
            bus = it["bus"]
            pp = tui.Button("󰏤" if it["playing"] else "󰐊", lambda: control(bus, "PlayPause"),
                            tooltip="Pause/Weiter")
            pp.add_css_class("mini")
            r.append(pp)
            if it["can_next"]:
                nx = tui.Button("󰒭", lambda: control(bus, "Next"), tooltip="Nächster Titel")
                nx.add_css_class("mini")
                r.append(nx)
            if it["can_raise"]:
                click = Gtk.GestureClick()
                click.connect("released", lambda *_: control(bus, "Raise"))
                text.add_controller(click)
        else:
            r.append(label("󰕾", "accent"))
        return r
