# Gemeinsame Bausteine für die TUI-artigen Einstellungs-Apps (audio, netz, bluetooth):
# Glas-Fenster wie die Konsole, Kästen mit Titel im Rahmen (wie btop), Tabs mit ¹²³-Tasten,
# ASCII-Regler aus ■-Zellen, [ knöpfe ], [■]-Schalter und eine Statuszeile unten.
# Farben kommen live aus matugen (~/.cache/matugen/colors.css, Super+W).
import math, os, re, threading, time

import gi
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango, PangoCairo

import glass


def load_icon_font():
    """Mitgelieferte Symbolschrift (fonts/notes-icons.ttf, Familie "Notes Icons") nur für diesen Prozess laden –
    so erscheinen die Icons auch ohne (passende) Nerd Font auf dem System. Pango ≥ 1.56 kann das selbst,
    sonst über fontconfig."""
    here = os.path.dirname(os.path.realpath(__file__))
    for path in (os.path.join(here, "fonts", "notes-icons.ttf"),
                 os.path.join(os.path.dirname(here), "fonts", "notes-icons.ttf")):
        if os.path.exists(path):
            break
    else:
        return False
    try:
        fm = PangoCairo.FontMap.get_default()
        if hasattr(fm, "add_font_file"):
            return bool(fm.add_font_file(path))
    except Exception:
        pass
    try:
        import ctypes, ctypes.util
        fc = ctypes.CDLL(ctypes.util.find_library("fontconfig") or "libfontconfig.so.1")
        fc.FcConfigGetCurrent.restype = ctypes.c_void_p
        fc.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        return bool(fc.FcConfigAppFontAddFile(fc.FcConfigGetCurrent(), path.encode()))
    except Exception:
        return False


load_icon_font()

MATUGEN_CSS = os.path.expanduser("~/.cache/matugen/colors.css")
FALLBACK = """@define-color background #1a120d; @define-color foreground #f0dfd7;
@define-color primary #ffb68e; @define-color on_primary #532200; @define-color secondary #e5bfa9;
@define-color tertiary #cdc98f; @define-color surface_container #271e19; @define-color outline #9e8d84;
@define-color color9 #ffb68e;"""
FONT = "JetBrainsMono Nerd Font, JetBrains Mono, Notes Icons, monospace"
SUP = "⁰¹²³⁴⁵⁶⁷⁸⁹"

CSS = """
window.tui { color: @foreground; }
window.tui:not(.glass) { background-color: @background; }
window.tui * { font-family: "JetBrainsMono Nerd Font", "JetBrains Mono", "Notes Icons", monospace; font-weight: bold; }
window.tui label { font-size: 13px; }

.topbar { padding: 10px 14px 6px 14px; }
.brand { background-color: @primary; color: @on_primary; padding: 1px 9px; border-radius: 4px; margin-right: 10px; }
button.tab, button.tbtn, button.glass-toggle, button.flat, button.rowhead, button.check {
    background: none; border: none; box-shadow: none; min-height: 0; min-width: 0; outline: none;
}
button.tab { padding: 2px 9px; border-radius: 4px; color: alpha(@foreground, 0.8); }
button.tab .key { color: @primary; }
button.tab:hover { background-color: alpha(@primary, 0.12); color: @foreground; }
button.tab:checked { background-color: alpha(@primary, 0.22); color: @foreground; }
button.tab:checked .key { color: @foreground; }

menubutton.tbtn > button { background: none; border: none; box-shadow: none; padding: 0; min-height: 0;
    color: inherit; }
button.tbtn, menubutton.tbtn, button.glass-toggle {
    border: 1px solid alpha(@primary, 0.55); border-radius: 4px; padding: 1px 8px; color: @foreground;
}
button.glass-toggle:checked { background-color: alpha(@primary, 0.22); color: @foreground; }
button.tbtn:hover, menubutton.tbtn:hover, button.glass-toggle:hover, button.tbtn:focus-visible {
    background-color: @primary; color: @on_primary; border-color: @primary;
}
menubutton.tbtn:hover .accent { color: @on_primary; }
menubutton.tbtn { padding: 1px 8px; }
button.tbtn.danger { border-color: alpha(@tertiary, 0.6); color: @tertiary; }
button.tbtn.danger:hover { background-color: @tertiary; color: @background; }
button.tbtn.on { background-color: alpha(@primary, 0.22); }
button.tbtn:disabled { opacity: 0.45; }
button.close { border-color: transparent; padding: 1px 6px; }
button.close:hover { background-color: @tertiary; border-color: @tertiary; color: @background; }

button.check { padding: 1px 4px; border-radius: 4px; color: @foreground; }
button.check .box { color: @primary; }
button.check:hover, button.check:focus-visible { background-color: alpha(@primary, 0.14); }

button.flat { padding: 0 4px; border-radius: 4px; color: @primary; }
button.flat:hover, button.flat:focus-visible { background-color: alpha(@primary, 0.18); }
button.flat.off { color: alpha(@foreground, 0.55); }
button.flat.news { color: @primary; border: 1px solid alpha(@primary, 0.55); }

.panel { margin: 2px 0; }
.pbody { border: 1px solid alpha(@primary, 0.45); border-top-width: 0; border-radius: 0 0 6px 6px;
         padding: 2px 12px 10px 12px; }
.panel.active > .pbody { border-color: @primary; }

button.rowhead { padding: 4px 6px; border-radius: 4px; color: @foreground; }
button.rowhead:hover, button.rowhead:focus-visible { background-color: alpha(@primary, 0.1); }
.row.open > button.rowhead { background-color: alpha(@primary, 0.16); }
.rowbody { padding: 4px 6px 8px 30px; }
.row + .row { border-top: 1px dashed alpha(@primary, 0.18); }

.dim { color: @secondary; }
.accent { color: @primary; }
.warn { color: @tertiary; }
.big, button.big label { font-size: 18px; }
.glyph { font-size: 17px; color: @primary; min-width: 24px; }
.mono-pct { min-width: 46px; }
.key-hint { color: @secondary; }
.key-hint .k { color: @primary; }

entry.tentry {
    background-color: alpha(@background, 0.45); border: 1px solid alpha(@primary, 0.45); border-radius: 4px;
    color: @foreground; box-shadow: none; min-height: 22px; padding: 0 8px; outline: none;
}
entry.tentry:focus-within { border-color: @primary; }
entry.tentry:disabled { opacity: 0.4; }
entry.tentry > text > placeholder { color: alpha(@secondary, 0.8); }

.statusbar { padding: 4px 14px 8px 14px; }
.statusbar .msg.err { color: @tertiary; }

popover.tpop > contents {
    background-color: alpha(@background, 0.92); border: 1px solid @primary; border-radius: 6px;
    padding: 4px; box-shadow: none;
}
popover.tpop > arrow { background: none; border: none; }
popover.tpop button.opt { background: none; border: none; box-shadow: none; padding: 3px 10px;
    border-radius: 4px; color: @foreground; min-height: 0; }
popover.tpop button.opt:hover, popover.tpop button.opt:focus-visible { background-color: @primary; color: @on_primary; }
popover.tpop button.opt.sel { color: @primary; }
popover.tpop button.opt.sel:hover { color: @on_primary; }

scrolledwindow > scrollbar { background: none; border: none; }
scrolledwindow > scrollbar slider { background-color: alpha(@primary, 0.45); min-width: 4px; border-radius: 2px; }
.empty { color: @secondary; padding: 14px 0; }
.banner { background-color: alpha(@primary, 0.18); border: 1px solid @primary; border-radius: 6px; padding: 8px 12px; margin: 4px 0; }
"""


# ---------- Farben ----------
_colors = {}


def colors():
    return _colors


def _parse_colors(text):
    out = {}
    for name, val in re.findall(r"@define-color\s+(\w+)\s+(#[0-9a-fA-F]{6})", text):
        rgba = Gdk.RGBA()
        rgba.parse(val)
        out[name] = rgba
    return out


class Theme:
    """CSS + Farben laden und bei Super+W (neue matugen-Farben) live nachladen."""

    def __init__(self):
        self.provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self.listeners = []
        self.load()
        self.mon = Gio.File.new_for_path(MATUGEN_CSS).monitor_file(Gio.FileMonitorFlags.NONE, None)
        self.mon.connect("changed", lambda *_: GLib.timeout_add(150, self._reload))

    _shared = None

    @classmethod
    def get(cls):
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    def _reload(self):
        self.load()
        for fn in self.listeners:
            fn()

        def redraw(w):  # selbst gezeichnete Rahmen und Regler holen sich die Farben beim Zeichnen
            w.queue_draw()
            c = w.get_first_child()
            while c:
                redraw(c)
                c = c.get_next_sibling()
        for win in Gtk.Window.list_toplevels():
            redraw(win)
        return False

    def load(self):
        css = FALLBACK
        try:
            css += "\n" + open(MATUGEN_CSS).read()
        except OSError:
            pass
        _colors.clear()
        _colors.update(_parse_colors(css))
        self.provider.load_from_string(css + glass.GLASS_CSS + CSS)


# ---------- Hilfen ----------
def label(text="", *classes, xalign=0, hexpand=False, ellipsize=False, markup=False, wrap=False):
    lbl = Gtk.Label(xalign=xalign, hexpand=hexpand)
    if markup:
        lbl.set_markup(text)
    else:
        lbl.set_label(text)
    if ellipsize:
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
    if wrap:
        lbl.set_wrap(True)
        lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    for c in classes:
        lbl.add_css_class(c)
    return lbl


def esc(text):
    return GLib.markup_escape_text(str(text))


def hbox(*children, spacing=8, **kw):
    b = Gtk.Box(spacing=spacing, **kw)
    for c in children:
        if c is not None:
            b.append(c)
    return b


def vbox(*children, spacing=4, **kw):
    b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing, **kw)
    for c in children:
        if c is not None:
            b.append(c)
    return b


def clear(box):
    """Alle Kinder entfernen und freigeben (die entfernten Widgets sind danach nicht mehr verwendbar)."""
    gone = []
    while (c := box.get_first_child()):
        box.remove(c)
        gone.append(c)
    release_later(*gone)


def release_later(*widgets):
    """Entfernte Widgets kurz danach freigeben (siehe release_tree). Das Wurzel-Widget behält seine Attribute,
    falls noch Code darauf zeigt – nur seine Handler und alles darunter werden gelöst."""
    if widgets:
        GLib.idle_add(lambda: ([release_tree(w, keep_root_dict=True) for w in widgets], False)[1])


def _die_with_parent():
    """Kindprozess (pactl subscribe, nmcli monitor, parec) endet mit dem App-Prozess."""
    import ctypes, signal as _s
    ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, _s.SIGTERM)  # PR_SET_PDEATHSIG


def spawn_watch(cmd, **kw):
    import subprocess, sys
    if sys.platform.startswith("linux"):
        kw["preexec_fn"] = _die_with_parent
    return subprocess.Popen(cmd, **kw)


def background(fn, *args, done=None):
    """fn(*args) im Thread ausführen, done(ergebnis) danach im GTK-Thread."""
    def work():
        try:
            res = fn(*args)
        except Exception as e:  # noqa: BLE001 – Fehler landen in der Statuszeile
            res = e
        if done:
            GLib.idle_add(lambda: done(res) and False)
    threading.Thread(target=work, daemon=True).start()


def bars(level, steps=4):
    """Signal 0–100 als ▂▄▆█ – Markup, fehlende Stufen gedimmt."""
    glyphs = "▂▄▆█"[:steps]
    n = 0 if level <= 0 else min(steps, 1 + int(level * steps / 101))
    return f"<span>{glyphs[:n]}</span><span alpha='30%'>{glyphs[n:]}</span>"


def battery(pct, cells=5):
    n = round(pct * cells / 100)
    return f"<span>{'▰' * n}</span><span alpha='35%'>{'▱' * (cells - n)}</span> {pct}%"


def _track_handlers():
    """GObject.connect merkt sich je Objekt die IDs der Python-Handler, damit release_tree genau diese trennt.
    (Alle Handler zu löschen träfe auch GTK-eigene – GTK warnt dann beim Abbau „no handler with id“.)"""
    from gi.repository import GObject
    if getattr(GObject.Object, "_tracks_handlers", False):
        return
    for name in ("connect", "connect_after"):
        orig = getattr(GObject.Object, name)

        def wrapped(self, *args, _orig=orig, **kw):
            hid = _orig(self, *args, **kw)
            try:
                self.__dict__.setdefault("_py_handler_ids", []).append(hid)
            except AttributeError:
                pass
            return hid
        setattr(GObject.Object, name, wrapped)
    GObject.Object._tracks_handlers = True


_track_handlers()


def _drop_handlers(obj):
    from gi.repository import GObject
    ids = obj.__dict__.pop("_py_handler_ids", None) if hasattr(obj, "__dict__") else None
    for hid in ids or ():
        try:
            if GObject.signal_handler_is_connected(obj, hid):
                obj.disconnect(hid)
        except Exception:
            pass


def release_tree(root, keep_root_dict=False):
    """Widget-Baum eines geschlossenen Fensters/Tabs wirklich freigeben.
    PyGObject-Falle: Signal-Handler, Zeichenfunktionen und Attribute der Kind-Widgets zeigen per Lambda/
    gebundener Methode auf Fenster/Tab zurück. Diese Kreise laufen über C-Referenzen, die Pythons GC nicht
    sieht – ohne Aufräumen bleibt alles samt Bildern für immer im Speicher. Getrennt werden nur die eigenen
    (Python-)Handler, GTK-interne bleiben. Danach ist der Baum unbrauchbar."""
    from gi.repository import GObject
    nodes, stack = [], [root]
    while stack:
        w = stack.pop()
        nodes.append(w)
        c = w.get_first_child()
        while c is not None:
            stack.append(c)
            c = c.get_next_sibling()
    for w in nodes:
        objs = [w]
        try:
            ctrls = w.observe_controllers()
            objs += [ctrls.get_item(i) for i in range(ctrls.get_n_items())]
        except Exception:
            pass
        # keine Modelle: die können mehrere Fenster teilen
        for getter in ("get_adjustment", "get_hadjustment", "get_vadjustment", "get_buffer", "get_factory",
                       "get_popover", "get_sorter"):
            fn = getattr(w, getter, None)
            if fn is None:
                continue
            try:
                o = fn()
            except Exception:
                continue
            if isinstance(o, GObject.Object):
                objs.append(o)
        if isinstance(w, Gtk.ColumnView):                    # Spalten haben eigene Zellen-Fabriken
            cols = w.get_columns()
            for i in range(cols.get_n_items()):
                col = cols.get_item(i)
                objs += [col, col.get_factory()]
        if hasattr(w, "list_actions") and hasattr(w, "lookup_action"):     # eigene Aktionen (win.* …)
            try:
                objs += [w.lookup_action(n) for n in w.list_actions()]
            except Exception:
                pass
        try:
            for prefix in w.list_action_prefixes():
                grp = w.get_action_group(prefix)
                if grp is not None and hasattr(grp, "lookup_action"):
                    objs += [grp.lookup_action(n) for n in grp.list_actions()]
        except Exception:
            pass
        for o in objs:
            if o is not None:
                _drop_handlers(o)
        if isinstance(w, Gtk.DrawingArea):
            try:
                w.set_draw_func(None)
            except Exception:
                pass
        if isinstance(w, (Gtk.FlowBox, Gtk.ListBox)):
            for setter in ("set_sort_func", "set_filter_func"):
                try:
                    getattr(w, setter)(None)
                except Exception:
                    pass
        d = getattr(w, "__dict__", None)
        if d and not (keep_root_dict and w is root):
            d.clear()
    # zuletzt die Listen leeren: GTK baut die (jetzt handlerlosen) Zeilen ab
    for w in nodes:
        if isinstance(w, (Gtk.ListView, Gtk.GridView, Gtk.ColumnView)):
            try:
                w.set_model(None)
            except Exception:
                pass


def trim_memory():
    """Freigegebenen Speicher an das System zurückgeben (glibc behält ihn sonst für spätere Anfragen)."""
    import gc
    gc.collect()
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass                       # kein glibc (z. B. Windows/musl): egal


# ---------- Widgets ----------
class Button(Gtk.Button):
    """[ text ] – umrandeter Textknopf."""

    def __init__(self, text, callback=None, danger=False, tooltip=None):
        super().__init__(label=text, valign=Gtk.Align.CENTER)
        self.add_css_class("tbtn")
        if danger:
            self.add_css_class("danger")
        if tooltip:
            self.set_tooltip_text(tooltip)
        if callback:
            self.connect("clicked", lambda *_: callback())


class Check(Gtk.Button):
    """[■] text / [ ] text – Schalter. callback(neuer_zustand)."""

    def __init__(self, text, active=False, callback=None, tooltip=None):
        super().__init__(valign=Gtk.Align.CENTER)
        self.add_css_class("check")
        self.box = label("", "box")
        self.text = label(text)
        self.set_child(hbox(self.box, self.text, spacing=6))
        if tooltip:
            self.set_tooltip_text(tooltip)
        self.callback = callback
        self.active = None
        self.set_active(active)
        self.connect("clicked", self._clicked)

    def set_active(self, on):
        on = bool(on)
        if on != self.active:
            self.active = on
            self.box.set_label("[■]" if on else "[ ]")

    def _clicked(self, *_):
        self.set_active(not self.active)
        if self.callback:
            self.callback(self.active)


class Select(Gtk.MenuButton):
    """‹ wert ▾ › – Auswahl aus einer Liste (Popover im selben Stil). options: [(id, text)]."""

    def __init__(self, callback, tooltip=None, max_chars=26):
        super().__init__(valign=Gtk.Align.CENTER)
        self.add_css_class("tbtn")
        self.callback = callback
        self.lbl = label("")
        self.lbl.set_ellipsize(Pango.EllipsizeMode.END)
        self.lbl.set_max_width_chars(max_chars)
        self.set_child(hbox(self.lbl, label("▾", "accent"), spacing=6))
        if tooltip:
            self.set_tooltip_text(tooltip)
        self.pop = Gtk.Popover(has_arrow=False)
        self.pop.add_css_class("tpop")
        self.list = vbox(spacing=1)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True,
                                    max_content_height=360, child=self.list)
        self.pop.set_child(scroll)
        self.set_popover(self.pop)
        self.options, self.current = None, None

    def set_options(self, options, current):
        if options != self.options or current != self.current:
            self.options, self.current = list(options), current
            clear(self.list)
            for oid, text in self.options:
                b = Gtk.Button()
                b.add_css_class("opt")
                b.set_child(label(("● " if oid == current else "  ") + text))
                if oid == current:
                    b.add_css_class("sel")
                b.connect("clicked", self._pick, oid)
                self.list.append(b)
        self.lbl.set_label(next((t for o, t in self.options if o == current), "–"))

    def _pick(self, _b, oid):
        self.pop.popdown()
        if oid != self.current:
            self.callback(oid)


class Entry(Gtk.Entry):
    def __init__(self, placeholder="", password=False, text="", width=None, activate=None):
        super().__init__(placeholder_text=placeholder, text=text, hexpand=width is None)
        self.add_css_class("tentry")
        if password:
            self.set_visibility(False)
            self.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        if width:
            self.set_width_chars(width)
        if activate:
            self.connect("activate", lambda *_: activate())


class Panel(Gtk.Box):
    """Kasten mit Titel im oberen Rahmen (wie btop):  ╭─ titel ──────────╮
    Die obere Kante samt Titel wird gezeichnet, Seiten und Boden kommen aus CSS (.pbody)."""
    H = 22

    def __init__(self, title="", child=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("panel")
        self.markup = ""
        self.head = Gtk.DrawingArea(content_height=self.H)
        self.head.set_draw_func(self._draw)
        self.append(self.head)
        self.body = vbox(spacing=4)
        self.body.add_css_class("pbody")
        self.append(self.body)
        self.font = Pango.FontDescription.from_string(f"{FONT} Bold 10")
        self.set_title(title)
        if child is not None:
            self.body.append(child)

    def set_title(self, text, markup=False):
        text = text if markup else esc(text)
        if text != self.markup:
            self.markup = text
            self.head.queue_draw()

    def set_active(self, on):
        (self.add_css_class if on else self.remove_css_class)("active")
        self.head.queue_draw()

    def _draw(self, _area, cr, w, h):
        c = colors()
        p = c.get("primary")
        layout = self.head.create_pango_layout("")
        layout.set_font_description(self.font)
        layout.set_markup(f" {self.markup} ", -1)
        tw, th = layout.get_pixel_size()
        r, y, x0, x1 = 6, h / 2, 0.5, w - 0.5
        tx = 12
        cr.set_line_width(1)
        cr.set_source_rgba(p.red, p.green, p.blue, 1.0 if self.has_css_class("active") else 0.45)
        cr.move_to(x0, h)
        cr.line_to(x0, y + r)
        cr.arc(x0 + r, y + r, r, math.pi, 1.5 * math.pi)
        cr.line_to(tx, y)
        cr.move_to(tx + tw, y)
        cr.line_to(x1 - r, y)
        cr.arc(x1 - r, y + r, r, 1.5 * math.pi, 2 * math.pi)
        cr.line_to(x1, h)
        cr.stroke()
        cr.set_source_rgba(p.red, p.green, p.blue, 1)
        cr.move_to(tx, (h - th) / 2)
        PangoCairo.show_layout(cr, layout)


class Row(Gtk.Box):
    """Listeneintrag: Kopfzeile (klickbar) + aufklappbarer Detailbereich."""

    def __init__(self, on_toggle=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("row")
        self.head = Gtk.Button()
        self.head.add_css_class("rowhead")
        self.head.connect("clicked", lambda *_: self.toggle())
        self.append(self.head)
        self.rev = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN, transition_duration=120)
        self.body = vbox(spacing=6)
        self.body.add_css_class("rowbody")
        self.rev.set_child(self.body)
        self.append(self.rev)
        self.on_toggle = on_toggle

    def set_head(self, widget):
        self.head.set_child(widget)

    @property
    def is_open(self):
        return self.rev.get_reveal_child()

    def toggle(self, open_=None):
        open_ = (not self.is_open) if open_ is None else open_
        self.rev.set_reveal_child(open_)
        (self.add_css_class if open_ else self.remove_css_class)("open")
        if self.on_toggle:
            self.on_toggle(self, open_)


def sync_rows(box, items, key, make, update):
    """Einträge in box mit items abgleichen: vorhandene Zeilen bleiben (samt Aufklapp-Zustand),
    neue werden erzeugt, alte entfernt, Reihenfolge wie items. box.rows = {key: row}."""
    rows = getattr(box, "rows", {})
    keys = [key(i) for i in items]
    for k in list(rows):
        if k not in keys:
            row = rows.pop(k)
            box.remove(row)
            release_later(row)
    prev = None
    for k, item in zip(keys, items):
        row = rows.get(k)
        if row is None:
            row = rows[k] = make(item)
            box.append(row)
        update(row, item)
        if row.get_prev_sibling() is not prev:
            box.reorder_child_after(row, prev)
        prev = row
    box.rows = rows


class Meter(Gtk.DrawingArea):
    """ASCII-Regler aus Zellen: ■■■■■■■■····  Ziehen/Klicken/Scrollen/Pfeiltasten.
    Über 100 % (max > 100) werden die Zellen in @tertiary gezeichnet, bei 100 % steht ein │.
    interactive=False: reine Anzeige (z. B. Pegel)."""

    def __init__(self, maximum=100, callback=None, interactive=True, glyph="■", empty=None, small=False,
                 mark=True, flush=False):
        super().__init__(hexpand=True)
        self.flush = flush  # True: erste/letzte Zelle sitzen genau an den Rändern (bündig mit Nachbarn)
        self.mark = mark  # False: keine 100-%-Marke (z. B. Fortschrittsbalken mit maximum=1000)
        self.maximum, self.callback, self.interactive = maximum, callback, interactive
        self.glyph, self.empty_glyph = glyph, empty or glyph
        self.value, self.muted = 0, False
        self.busy_until, self.pending = 0, None
        self.font = Pango.FontDescription.from_string(f"{FONT} Bold {9 if small else 11}")
        self.set_content_height(12 if small else 18)
        self.set_draw_func(self._draw)
        if interactive:
            self.set_focusable(True)
            self.set_cursor(Gdk.Cursor.new_from_name("pointer"))
            drag = Gtk.GestureDrag()
            drag.connect("drag-begin", lambda g, x, y: self._set_from_x(x))
            drag.connect("drag-update", lambda g, dx, dy: self._set_from_x(g.get_start_point()[1] + dx))
            self.add_controller(drag)
            scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
            scroll.connect("scroll", lambda c, dx, dy: self._user_set(self.value - dy * 2) or True)
            self.add_controller(scroll)
            keys = Gtk.EventControllerKey()
            keys.connect("key-pressed", self._key)
            self.add_controller(keys)
            focus = Gtk.EventControllerFocus()
            focus.connect("enter", lambda *_: self.queue_draw())
            focus.connect("leave", lambda *_: self.queue_draw())
            self.add_controller(focus)

    def _key(self, _c, kv, _code, _state):
        step = {Gdk.KEY_Left: -2, Gdk.KEY_Right: 2, Gdk.KEY_Page_Down: -10, Gdk.KEY_Page_Up: 10,
                Gdk.KEY_Home: -999, Gdk.KEY_End: 999}.get(kv)
        if step is None:
            return False
        self._user_set(self.value + step)
        return True

    def _cells(self):
        layout = self.create_pango_layout(self.glyph)
        layout.set_font_description(self.font)
        cw, ch = layout.get_pixel_size()
        return max(1, int(self.get_width() // max(cw, 1))), cw, ch

    def _set_from_x(self, x):
        n, cw, _ = self._cells()
        span = self.get_width() if self.flush else n * cw
        self._user_set(round(max(0.0, min(1.0, x / max(span, 1))) * self.maximum))
        self.grab_focus()

    def _user_set(self, v):
        v = int(max(0, min(self.maximum, round(v))))
        if v == self.value:
            return
        self.value = v
        self.busy_until = time.monotonic() + 0.6
        self.queue_draw()
        if self.callback:
            if self.pending is None:  # höchstens alle 40 ms ans System schicken
                GLib.timeout_add(40, self._flush)
            self.pending = v

    def _flush(self):
        if self.pending is not None:
            self.callback(self.pending)
        self.pending = None
        return False

    def set_value(self, v, muted=False):
        if self.muted != muted:
            self.muted = muted
            self.queue_draw()
        if time.monotonic() < self.busy_until:  # Nutzer zieht gerade
            return
        v = max(0, min(self.maximum, v))
        if v != self.value:
            self.value = v
            self.queue_draw()

    def square_inset(self):
        """Abstand der Quadrate zur Ober-/Unterkante (zum Bündig-Ausrichten von Nachbarn)."""
        _n, cw, ch = self._cells()
        return (self.get_content_height() - max(2, min(cw - 2, ch * 0.5))) / 2

    def _draw(self, _area, cr, width, height):
        c = colors()
        n, cw, ch = self._cells()
        filled = round(self.value / self.maximum * n) if self.maximum else 0
        full = round(100 / self.maximum * n) if self.maximum > 100 and self.mark else n
        fg = c.get("foreground")
        acc = fg if self.muted else c.get("primary")
        over = c.get("tertiary", acc)
        size = max(2, min(cw - 2, ch * 0.5))       # Quadrat pro Zelle, mit Lücke
        y = (height - size) / 2
        step = (width - size) / max(n - 1, 1) if self.flush else cw
        for i in range(n):
            x = i * step if self.flush else i * cw + (cw - size) / 2
            if i == full and self.maximum > 100 and self.mark:   # 100-%-Marke
                cr.set_source_rgba(over.red, over.green, over.blue, 0.8)
                cr.rectangle(i * cw - 1, 1, 1, height - 2)
                cr.fill()
            if i < filled:
                col = over if i >= full else acc
                cr.set_source_rgba(col.red, col.green, col.blue, 0.5 if self.muted else 1.0)
            else:
                cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.14)
            cr.rectangle(x, y, size, size)
            cr.fill()
        if self.interactive and self.has_focus():
            p = c.get("primary")
            cr.set_source_rgba(p.red, p.green, p.blue, 0.8)
            cr.rectangle(0, height - 1, width if self.flush else n * cw, 1)
            cr.fill()


class Spark(Gtk.Label):
    """Verlauf als ▁▂▃▄▅▆▇█ (z. B. Netzwerk-Durchsatz)."""
    TICKS = "▁▂▃▄▅▆▇█"

    def __init__(self, length=24):
        super().__init__(xalign=0)
        self.add_css_class("accent")
        self.values = [0.0] * length
        self.set_label(self.TICKS[0] * length)

    def push(self, v):
        self.values = self.values[1:] + [v]
        top = max(self.values) or 1
        self.set_label("".join(self.TICKS[min(7, round(x / top * 7))] for x in self.values))


# ---------- Fenster ----------
class TuiWindow(Gtk.ApplicationWindow):
    """Rahmenloses Glas-Fenster: Kopfzeile mit Marke + Tabs, Inhalt (Stack), Statuszeile.
    Tasten: 1–9 Tab, Esc schließen (außer ESC_CLOSES = False), Strg+R neu laden (self.on_refresh)."""
    ESC_CLOSES = True

    def __init__(self, app, brand, tabs, size=(760, 600), hints=(), icons_only=False):
        # Schließen = verstecken (App läuft weiter, nächster Start ist sofort da). Windows hat kein D-Bus, ein
        # neuer Start fände die versteckte Instanz nicht – dort wirklich schließen.
        super().__init__(application=app, title=brand, hide_on_close=os.name != "nt")
        # Alle drei Apps laufen in einem Prozess (rice-tui.py); jedes Fenster bekommt trotzdem
        # seine eigene Wayland-App-ID (Hyprland-Fensterregel, Icon).
        # GTK setzt die App-ID bei jedem Einblenden selbst; direkt danach (vor dem ersten Bild) überschreiben
        self.connect("map", self._on_map)
        self.connect("unmap", lambda *_: self.on_hide())
        self.set_default_size(*getattr(glass, "fit_size", lambda w, h: (w, h))(*size))   # passt auf kleine Bildschirme
        getattr(glass, "frame_window", lambda w: w.set_decorated(False))(self)   # Kachel-WM: rahmenlos
        self.add_css_class("pb-window")
        self.add_css_class("tui")
        self.theme = Theme.get()
        self.on_refresh = None
        self.on_tab = None

        top = hbox(spacing=2)
        top.add_css_class("topbar")
        top.append(label(brand, "brand"))
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=90,
                               vexpand=True)
        self.tab_btns = []
        group = None
        self.tab_names = {}
        self.icons_only = icons_only  # Tabs nur als ¹󰝚 ²󰲸 … (Name als Tooltip)
        for i, tab in enumerate(tabs):
            tid, name = tab[0], tab[1]
            icon = tab[2] if len(tab) > 2 else None  # Symbol für schmale Fenster
            b = Gtk.ToggleButton(tooltip_text=name)
            b.add_css_class("tab")
            name_lbl = label(name)
            icon_lbl = label(icon or "", "accent")
            icon_lbl.set_visible(bool(icons_only and icon))
            name_lbl.set_visible(not (icons_only and icon))
            b.set_child(hbox(label(SUP[i + 1] if i < 9 else "", "key"), icon_lbl, name_lbl, spacing=1))
            self.tab_names[tid] = (name_lbl, icon_lbl if icon else None)
            if group:
                b.set_group(group)
            group = group or b
            b.connect("toggled", self._tab_toggled, tid)
            self.tab_btns.append((tid, b))
            top.append(b)
        top.append(label("", hexpand=True))
        self.header_extra = hbox(spacing=6)
        top.append(self.header_extra)
        gt = glass.GlassToggle(self)
        gt.set_margin_start(6)
        top.append(gt)
        close = Button("✕", self.close, tooltip="Schließen (Esc)")
        close.add_css_class("close")
        close.set_margin_start(4)
        top.append(close)
        handle = Gtk.WindowHandle(child=top)

        self.status = label("", "msg", hexpand=True, ellipsize=True)
        self.status.set_selectable(True)  # Fehlermeldungen lassen sich markieren und kopieren
        bottom = hbox(self.status, spacing=12)
        self.hint_box = hbox(spacing=12)
        for k, v in (("1-%d" % len(tabs), "tab"),) + tuple(hints) + ((("esc", "zu"),) if self.ESC_CLOSES else ()):
            self.hint_box.append(hbox(label(k, "accent"), label(v, "dim"), spacing=5))
        bottom.append(self.hint_box)
        self.compact = None
        bottom.add_css_class("statusbar")
        self._status_id = None

        self.content = vbox(spacing=0)
        self.content.set_margin_start(14)
        self.content.set_margin_end(14)
        self.content.append(self.stack)
        self.topbar, self.statusbar = handle, bottom  # für Apps, die ihren Platz selbst einteilen
        # .root = echter Inhalt; get_child() kann die Glas-Unterlage (Overlay, glass.underlay) liefern
        self.root = vbox(handle, self.content, bottom, spacing=0)
        self.set_child(self.root)

        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._key)
        self.add_controller(keys)

    APP_ID = None

    def _on_map(self, *_):
        # on_show() darf nie daran scheitern, dass das App-ID-Setzen nicht klappt
        try:
            self._set_app_id()
        finally:
            self.on_show()

    def _set_app_id(self, *_):
        if self.APP_ID:
            try:
                gi.require_version("GdkWayland", "4.0")
                from gi.repository import GdkWayland
                surf = self.get_surface()
                # neuere GTK-Versionen haben set_application_id nicht mehr
                if isinstance(surf, GdkWayland.WaylandToplevel) and hasattr(surf, "set_application_id"):
                    surf.set_application_id(self.APP_ID)
            except (ValueError, ImportError, AttributeError):
                pass

    def on_show(self):
        """Fenster wird sichtbar: Daten holen, Timer starten (in den Apps überschrieben)."""

    def on_hide(self):
        """Fenster versteckt: Timer/Pegel/Suche anhalten."""

    def add_page(self, tid, widget, scroll=True):
        if scroll:
            widget = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, child=widget, vexpand=True)
        self.stack.add_named(widget, tid)
        if len(self.tab_btns) and self.stack.get_visible_child_name() == tid:
            self.tab_btns[0][1].set_active(True)

    def show_tab(self, tid):
        for t, b in self.tab_btns:
            if t == tid:
                b.set_active(True)

    def current_tab(self):
        return self.stack.get_visible_child_name()

    # ---------- schmale Fenster (z. B. gekachelt) ----------
    COMPACT_W = 820

    def do_size_allocate(self, width, height, baseline):
        Gtk.ApplicationWindow.do_size_allocate(self, width, height, baseline)
        compact = width < self.COMPACT_W
        if compact != self.compact or (width, height) != getattr(self, "_last_size", None):
            self._last_size = (width, height)
            if compact != self.compact:
                self.compact = compact
                GLib.idle_add(self._apply_compact)
            GLib.idle_add(lambda: self.on_resize(width, height) and False)

    def _apply_compact(self):
        """Schmal: Tabs nur noch mit Symbol (aktiver Tab mit Namen), keine Tastenhinweise unten."""
        cur = self.current_tab()
        for tid, (name_lbl, icon_lbl) in self.tab_names.items():
            if icon_lbl is not None and not self.icons_only:
                icon_lbl.set_visible(self.compact)
                name_lbl.set_visible(not self.compact or tid == cur)
        self.hint_box.set_visible(not self.compact)
        self.on_compact(self.compact)
        return False

    def on_compact(self, compact):
        """Für Apps: eigene Anpassungen bei schmalem Fenster."""

    def on_resize(self, width, height):
        """Für Apps: bei jeder Größenänderung."""

    def _tab_toggled(self, btn, tid):
        if btn.get_active():
            self.stack.set_visible_child_name(tid)   # erst wechseln, dann Beschriftung (sonst alter Tab)
            if self.compact and not self.icons_only:
                self._apply_compact()
            if self.on_tab:
                self.on_tab(tid)

    def _key(self, _c, kv, _code, state):
        focus = self.get_focus()
        in_entry = isinstance(focus, Gtk.Text) or isinstance(focus, Gtk.Entry)
        if kv == Gdk.KEY_Escape:
            if in_entry:
                self.set_focus(None)
            elif self.ESC_CLOSES:
                self.close()
            return True
        if state & Gdk.ModifierType.CONTROL_MASK and kv in (Gdk.KEY_r, Gdk.KEY_R):
            if self.on_refresh:
                self.on_refresh()
            return True
        if not in_entry and not state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            if Gdk.KEY_1 <= kv <= Gdk.KEY_9:
                i = kv - Gdk.KEY_1
                if i < len(self.tab_btns):
                    self.tab_btns[i][1].set_active(True)
                    return True
            if kv in (Gdk.KEY_q,):
                self.close()
                return True
        return False

    def add_changelog(self, key, folder, brand=None):
        """Versions-Knopf „v1.2.0“ oben rechts → Changelog-Fenster (folder enthält VERSION + CHANGELOG.md).
        Nach einem Update steht beim ersten Zeigen einmal ein Hinweis in der Statuszeile."""
        try:
            version = open(os.path.join(folder, "VERSION")).read().strip()
        except OSError:
            version = ""
        path = os.path.join(folder, "CHANGELOG.md")
        brand = brand or key
        b = Gtk.Button(label=f"v{version}" if version else "changelog", tooltip_text="changelog – was ist neu?",
                       valign=Gtk.Align.CENTER, focus_on_click=False)
        b.add_css_class("flat")
        b.add_css_class("off")

        def show(*_):
            import changelog
            changelog.open_window(self, brand, path, key=key, version=version or None)
            b.remove_css_class("news")
        b.connect("clicked", show)
        self.header_extra.append(b)
        self.changelog_btn = b
        try:
            import changelog
            if version and changelog.check_new(key, version):
                b.add_css_class("news")
                b.remove_css_class("off")
                b.set_label(f"󰋚 v{version}")

                def tell(*_):
                    self.say(f"neu in v{version} – klick oben rechts auf „v{version}“ für den changelog", seconds=12)
                    if self._news_id:
                        self.disconnect(self._news_id)
                        self._news_id = None
                self._news_id = self.connect("map", lambda *_: GLib.timeout_add(500, lambda: (tell(), False)[1]))
                if self.get_mapped():
                    tell()
        except Exception as e:
            import sys
            print("changelog:", e, file=sys.stderr)

    _news_id = None

    def say(self, text, error=False, seconds=6):
        """Meldung in der Statuszeile (▸ ok / ✗ fehler). Fehler stehen zusätzlich im Log (stderr)."""
        if error:
            import sys
            print(time.strftime("%H:%M:%S"), "fehler:", text, file=sys.stderr, flush=True)
            seconds = max(seconds, 20)
        self.status.set_label(("✗ " if error else "▸ ") + str(text).strip().replace("\n", " "))
        (self.status.add_css_class if error else self.status.remove_css_class)("err")
        if self._status_id:
            GLib.source_remove(self._status_id)
        self._status_id = GLib.timeout_add_seconds(seconds, self._clear_status)

    def _clear_status(self):
        self.status.set_label("")
        self._status_id = None
        return False
