# musicalist – gemeinsame Zeilen-Bausteine (Titelzeile, Sammlungszeile, Künstler-Link) für ui.py und die Seiten.
# ARTIST_OPEN / OFFLINE_HAS setzt MusicWindow beim Start (set_hooks).
from gi.repository import GLib, Gtk, Pango

from tui import label, hbox, vbox, esc
from engine import fmt


def set_hooks(artist_open, offline_has):
    global ARTIST_OPEN, OFFLINE_HAS
    ARTIST_OPEN, OFFLINE_HAS = artist_open, offline_has


# ---------- Listen ----------
ARTIST_OPEN = None      # setzt MusicWindow: Klick auf einen Künstlernamen → Künstlerseite
OFFLINE_HAS = None      # setzt MusicWindow: videoId → liegt offline gespeichert?


def track_row(t, on_play, actions, menus=None, extra=None):
    """Zeile: ▶ titel  künstler  album  3:45  [+] [»] …  actions: [(glyph, tooltip, fn)].
    menus (songmenu.SongMenus): Rechtsklick-Menü + Vorwärmen beim Überfahren; extra() → weitere Menüeinträge."""
    row = Gtk.Box()
    row.add_css_class("row")
    head = Gtk.Button(hexpand=True)
    head.add_css_class("rowhead")
    row.mark = label("", "trk-mark")
    row.title = label(t["title"], "trk-title", hexpand=True, ellipsize=True)
    row.artist = label(t["artist"], "dim", ellipsize=True)
    row.artist.set_max_width_chars(24)
    row.artist.set_width_chars(6)
    # Künstler = eigener Knopf (öffnet die Künstlerseite), der Rest der Zeile spielt den Titel
    art = Gtk.Button(child=row.artist, focus_on_click=False, valign=Gtk.Align.CENTER,
                     tooltip_text=f"Künstlerseite: {t['artist']}" if t["artist"] else None)
    art.add_css_class("artlink")
    art.set_cursor_from_name("pointer")
    art.connect("clicked", lambda *_: ARTIST_OPEN and ARTIST_OPEN(t))
    art.set_sensitive(bool(t["artist"]))
    row.dur = label(fmt(t["duration"]) if t["duration"] else "", "dim", xalign=1)
    row.dur.set_width_chars(6)
    off = None
    if OFFLINE_HAS and OFFLINE_HAS(t.get("videoId")):
        off = label("󰇚", "dim")
        off.set_tooltip_text("offline gespeichert (meistgehört)")
    # Knöpfe nicht ineinander schachteln (der innere bekam keinen Klick, es startete immer der Titel):
    # Titel | Künstler | Dauer sind drei Geschwister, alle außer dem Künstler spielen den Titel.
    row.add_css_class("trk")
    head.set_child(hbox(row.mark, row.title, off, spacing=10))
    head.connect("clicked", lambda *_: on_play())
    dur_btn = Gtk.Button(child=row.dur, focus_on_click=False, valign=Gtk.Align.FILL)
    dur_btn.add_css_class("rowhead")
    dur_btn.connect("clicked", lambda *_: on_play())
    row.append(head)
    art.set_margin_start(4)
    art.set_margin_end(4)
    row.append(art)
    row.append(dur_btn)
    for glyph, tip, fn, *opt in actions:      # opt: (True,) = fn bekommt den Knopf (Popover daran)
        b = Gtk.Button(label=glyph, tooltip_text=tip, valign=Gtk.Align.CENTER)
        b.add_css_class("mini")
        b.connect("clicked", (lambda _b, f=fn: f(_b)) if opt and opt[0] else (lambda _b, f=fn: f()))
        row.append(b)
    row.track = t
    if menus is not None:
        menus.attach(row, t, extra)
    return row


def artist_link(name, artist_id=None, css="dim", chars=24):
    """Künstlername als Knopf → Künstlerseite (ohne ID per Suche nach dem Namen)."""
    lab = label(name, css, ellipsize=True)
    lab.set_max_width_chars(chars)
    b = Gtk.Button(child=lab, focus_on_click=False, valign=Gtk.Align.CENTER, tooltip_text=f"Künstlerseite: {name}")
    b.add_css_class("artlink")
    b.set_cursor_from_name("pointer")
    b.connect("clicked", lambda *_: ARTIST_OPEN and ARTIST_OPEN({"artist": name, "artistId": artist_id}))
    b.set_sensitive(bool(name))
    return b


def coll_row(glyph, title, sub, on_open, artist=None):
    """artist: (name, id) → Künstler als eigener Link statt Text in sub."""
    row = Gtk.Box()
    row.add_css_class("row")
    head = Gtk.Button(hexpand=True)
    head.add_css_class("rowhead")
    # Künstler-Link steht neben dem Knopf, nicht darin (verschachtelte Knöpfe bekamen keinen Klick)
    head.set_child(hbox(label(glyph, "glyph"), label(title, hexpand=True, ellipsize=True), spacing=10))
    head.connect("clicked", lambda *_: on_open())
    row.add_css_class("trk")
    row.append(head)
    if artist and artist[0]:
        al = artist_link(*artist)
        al.set_margin_start(4)
        al.set_margin_end(4)
        row.append(al)
    tail = Gtk.Button(child=hbox(label(sub, "dim"), label("›", "accent"), spacing=10), focus_on_click=False)
    tail.add_css_class("rowhead")
    tail.connect("clicked", lambda *_: on_open())
    row.append(tail)
    return row
