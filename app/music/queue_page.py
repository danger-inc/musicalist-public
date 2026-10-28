# musicalist – Warteschlange (Teil von MusicWindow, siehe ui.py). Methoden greifen auf self (das Hauptfenster) zu.

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Graphene, Gtk, Pango, PangoCairo

import tui
from tui import label, hbox, vbox, esc
from engine import fmt
from rows import track_row, coll_row, artist_link


class QueueMixin:

    # ---------- Warteschlange ----------
    def build_queue(self):
        page = vbox(spacing=8)
        page.set_margin_top(6)
        self.queue_panel = tui.Panel("warteschlange")
        self.queue_box = vbox(spacing=0)
        self.queue_empty = label("leer – unter ⁶suchen titel auswählen", "empty", xalign=0.5)
        self.queue_panel.body.append(hbox(label("", hexpand=True),
                                          self._sh(tui.Button("󰒝 mischen", self.p.shuffle_queue), "󰒝 mischen", "󰒝"),
                                          self._sh(tui.Button("󰐹 radio auffüllen", self.p.extend_radio),
                                                     "󰐹 radio auffüllen", "󰐹 radio"),
                                          self._sh(tui.Button("󰐒 als playlist", self.queue_to_playlist,
                                                              tooltip="Ganze Warteschlange in eine Playlist legen"),
                                                   "󰐒 als playlist", "󰐒"),
                                          tui.Button("leeren", lambda: self.p.clear(), danger=True)))
        self.queue_more_top = self.more_button(lambda: self.queue_expand(past=True))
        self.queue_more_bottom = self.more_button(lambda: self.queue_expand())
        self.queue_limit, self.queue_all_past = self.QUEUE_WINDOW, False
        self.queue_panel.body.append(self.queue_more_top)
        self.queue_panel.body.append(self.queue_box)
        self.queue_panel.body.append(self.queue_more_bottom)
        self.queue_panel.body.append(self.queue_empty)
        page.append(self.queue_panel)
        self.add_page("queue", page)

    QUEUE_WINDOW = 100          # so viele Zeilen werden gebaut (jede kostet ~1,5 ms und ~0,3 MB), der Rest auf Wunsch

    def rows_chunked(self, box, items, make, first=60, step=100):
        """Lange Listen portionsweise bauen: erst `first` Zeilen, der Rest über „weitere N anzeigen“.
        make(i, item) → Zeile. (Eine Zeile kostet ~1,5 ms: 500 Titel am Stück ließen das Fenster ruckeln.)"""
        state = {"i": 0, "btn": None}

        def more():
            if state["btn"] is not None:
                box.remove(state["btn"])
                state["btn"] = None
            lo = state["i"]
            hi = min(len(items), lo + (first if lo == 0 else step))
            for i in range(lo, hi):
                box.append(make(i, items[i]))
            state["i"] = hi
            if hi < len(items):
                b = self.more_button(more)
                b.set_label(f"↓ {len(items) - hi} weitere anzeigen")
                b.set_visible(True)
                box.append(b)
                state["btn"] = b
        more()

    @staticmethod
    def more_button(fn):
        b = Gtk.Button(focus_on_click=False)
        b.add_css_class("rowhead")
        b.set_visible(False)
        # Aktion im Leerlauf: sie entfernt/ersetzt den Knopf selbst, das darf nicht mitten in seinem Signal passieren
        b.connect("clicked", lambda *_: GLib.idle_add(lambda: (fn(), False)[1]))
        return b

    def queue_expand(self, past=False):
        if past:
            self.queue_all_past = True
        else:
            self.queue_limit += self.QUEUE_WINDOW
        self.update_queue()

    def queue_range(self):
        """(von, bis) der angezeigten Zeilen: ab kurz vor dem laufenden Titel, QUEUE_WINDOW Stück (wachsend)."""
        n, cur = len(self.p.queue), max(0, self.p.index)
        lo = 0 if self.queue_all_past else max(0, cur - 5)
        hi = min(n, max(lo + self.queue_limit, cur + 20))
        return lo, hi

    def update_queue(self):
        q = self.p.queue
        total = sum(t["duration"] or 0 for t in q)
        self.queue_panel.set_title(f"warteschlange <span alpha='60%'>{len(q)} titel · {fmt(total)}</span>",
                                   markup=True)
        self.queue_empty.set_visible(not q)

        def make(item):
            i, t = item
            row = track_row(t, lambda r=None: self.p.jump(self._qi(t)),
                            [("↑", "Nach oben", lambda: self.p.move(self._qi(t), self._qi(t) - 1)),
                             ("↓", "Nach unten", lambda: self.p.move(self._qi(t), self._qi(t) + 1)),
                             ("✕", "Entfernen", lambda: self.p.remove(self._qi(t)))],
                            menus=self.songs, extra=lambda: self.queue_extra(t))
            self.queue_drag(row, t)
            return row

        def update(row, item):
            i, t = item
            playing = i == self.p.index
            row.mark.set_label("▶" if playing else f"{i + 1}")
            (row.add_css_class if playing else row.remove_css_class)("playing")
            (row.add_css_class if i < self.p.index else row.remove_css_class)("past")
        lo, hi = self.queue_range()
        tui.sync_rows(self.queue_box, list(enumerate(q))[lo:hi], lambda it: id(it[1]), make, update)
        self.queue_more_top.set_visible(lo > 0)
        self.queue_more_top.set_label(f"↑ {lo} bereits gespielt anzeigen")
        self.queue_more_bottom.set_visible(hi < len(q))
        self.queue_more_bottom.set_label(f"↓ {len(q) - hi} weitere anzeigen")

        # "als nächstes" auf der Jetzt-Seite
        nxt = q[self.p.index + 1:self.p.index + 1 + self.upnext_n] if self.p.index >= 0 and self.upnext_n else []
        self.upnext_panel.set_visible(bool(nxt))
        tui.sync_rows(self.upnext, nxt, id, lambda t: track_row(t, lambda: self.p.jump(self._qi(t)), [],
                                                                 menus=self.songs, extra=lambda: self.queue_extra(t)),
                      lambda r, t: r.mark.set_label("›"))

    def queue_drag(self, row, t):
        """Zeile mit der Maus verschieben: ziehen und auf eine andere Zeile loslassen (Linie zeigt das Ziel).
        Die Controller kosten pro Zeile ~0,3 ms – sie werden erst beim ersten Überfahren angehängt."""
        hover = Gtk.EventControllerMotion()
        state = {"armed": True}

        def finish():
            # Erst im Leerlauf: ein Controller darf sich nicht aus seinem eigenen Signal entfernen (GTK stürzt ab)
            if row.get_root() is not None:
                row.remove_controller(hover)
                self._queue_drag_attach(row, t)
            return False

        def attach(*_):
            if state["armed"]:
                state["armed"] = False
                GLib.idle_add(finish)
        hover.connect("enter", attach)
        row.add_controller(hover)

    def _queue_drag_attach(self, row, t):
        src = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        src.set_button(1)
        src.connect("prepare", lambda s, x, y: Gdk.ContentProvider.new_for_value(str(self._qi(t))))

        def begin(s, drag):
            Gtk.DragIcon.set_from_paintable(drag, Gtk.WidgetPaintable(widget=row), 12, 12)
            row.add_css_class("dragging")
        src.connect("drag-begin", begin)
        src.connect("drag-end", lambda *_: row.remove_css_class("dragging"))
        row.add_controller(src)
        dst = Gtk.DropTarget.new(str, Gdk.DragAction.MOVE)

        def where(y):
            return "dropat-end" if y > row.get_height() / 2 else "dropat"

        def motion(d, x, y):
            for c in ("dropat", "dropat-end"):
                row.remove_css_class(c)
            row.add_css_class(where(y))
            return Gdk.DragAction.MOVE
        dst.connect("motion", motion)
        dst.connect("enter", motion)
        dst.connect("leave", lambda *_: [row.remove_css_class(c) for c in ("dropat", "dropat-end")])

        def drop(d, val, x, y):
            for c in ("dropat", "dropat-end"):
                row.remove_css_class(c)
            try:
                a, b = int(val), self._qi(t)
            except ValueError:
                return False
            if a < 0 or b < 0 or a == b:
                return False
            if where(y) == "dropat-end" and a > b:
                b += 1
            elif where(y) == "dropat" and a < b:
                b -= 1
            self.p.move(a, b)
            return True
        dst.connect("drop", drop)
        row.add_controller(dst)

    def queue_reset_window(self):
        self.queue_limit, self.queue_all_past = self.QUEUE_WINDOW, False

    def queue_extra(self, t):
        i = self._qi(t)
        out = []
        if i > self.p.index + 1:
            out.append(("»", "als nächstes (vorziehen)", lambda: self.p.move(self._qi(t), self.p.index + 1)))
        if i > 0:
            out.append(("↑", "nach oben", lambda: self.p.move(self._qi(t), self._qi(t) - 1)))
        if 0 <= i < len(self.p.queue) - 1:
            out.append(("↓", "nach unten", lambda: self.p.move(self._qi(t), self._qi(t) + 1)))
        if i != self.p.index:
            out.append(("󰐊", "hierhin springen", lambda: self.p.jump(self._qi(t))))
        out.append(("✕", "aus der warteschlange", lambda: self.p.remove(self._qi(t)), True))
        return out

    def queue_to_playlist(self):
        rest = self.p.queue[max(0, self.p.index):] if self.p.index >= 0 else self.p.queue
        self.songs.picker(self.queue_panel, rest[:200])

    def _qi(self, t):
        for i, x in enumerate(self.p.queue):
            if x is t:
                return i
        return -1
