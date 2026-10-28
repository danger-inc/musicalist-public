# musicalist – Klang-Popover (Teil von MusicWindow, siehe ui.py): Überblendung und Equalizer.
import audiofx
import engine
from gi.repository import GLib, Gtk

import tui
from tui import label, hbox, vbox


class SoundMixin:
    EQ_DEBOUNCE_MS = 150

    def sound_menu(self, anchor=None):
        p = self.p
        anchor = anchor if isinstance(anchor, Gtk.Widget) else (
            self.sound_btn if self.sound_btn.get_mapped() else self.statusbar)
        pop = self.songs._popover(anchor)
        pop.set_position(Gtk.PositionType.TOP)      # die Liste ist hoch: nach oben aufgehen, dort ist Platz
        st = {"eq": dict(p.eq, gains=list(p.eq["gains"])), "id": None}
        box = vbox(spacing=4)
        box.append(label("󰓃  klang", "kp-head"))

        # ----- Überblendung -----
        cf = tui.Select(lambda v: (p.set_crossfade(int(v)),
                                   self.say("überblenden aus" if int(v) == 0 else f"überblenden: {v} s")),
                        tooltip="Der nächste Titel startet unter dem Ende des aktuellen")
        cf.set_options([(str(s), name) for s, name in audiofx.CROSSFADE_CHOICES], str(engine.setting("crossfade") or 0))
        box.append(hbox(label("überblenden", hexpand=True), cf, spacing=10))
        box.append(label("YouTube-Titel nur, wenn der nächste schon geladen ist; sonst normaler Wechsel.",
                         "kp-sub", wrap=True))
        self.songs._rub(box, "equalizer")

        # ----- Equalizer -----
        meters, vals = [], []

        def commit():
            st["id"] = None
            p.set_eq(st["eq"])
            return False

        def changed():                       # entprellt: beim Ziehen nicht jede Stufe an mpv schicken
            if st["id"] is not None:
                GLib.source_remove(st["id"])
            st["id"] = GLib.timeout_add(self.EQ_DEBOUNCE_MS, commit)

        def paint():
            for i, (m, v) in enumerate(zip(meters, vals)):
                g = st["eq"]["gains"][i] if i < 10 else st["eq"]["pre"]
                m.busy_until = 0
                m.set_value(g + audiofx.GAIN_MAX)
                v.set_label(f"{g:+.0f} dB")
            name = audiofx.preset_name(st["eq"]["gains"])
            preset.set_options([(n, n) for n in audiofx.PRESETS] + [("eigene", "eigene")], name)

        def on_toggle(on):
            st["eq"]["on"] = on
            changed()

        def on_preset(name):
            if name in audiofx.PRESETS:
                st["eq"]["gains"] = [float(x) for x in audiofx.PRESETS[name]]
                st["eq"]["on"] = True
                chk.set_active(True)
                paint()
                changed()

        def on_band(i, v):
            g = float(v - audiofx.GAIN_MAX)
            if i < 10:
                st["eq"]["gains"][i] = g
            else:
                st["eq"]["pre"] = g
            vals[i].set_label(f"{g:+.0f} dB")
            if not st["eq"]["on"]:
                st["eq"]["on"] = True
                chk.set_active(True)
            if i < 10:
                preset.set_options([(n, n) for n in audiofx.PRESETS] + [("eigene", "eigene")],
                                   audiofx.preset_name(st["eq"]["gains"]))
            changed()

        chk = tui.Check("an", st["eq"]["on"], on_toggle, tooltip="Equalizer ein/aus")
        preset = tui.Select(on_preset, tooltip="Voreinstellung")
        box.append(hbox(chk, label("", hexpand=True), preset, spacing=10))
        grid = vbox(spacing=0)
        for i in range(11):
            name = (audiofx.LABELS[i] + " Hz") if i < 10 else "vorverstärker"
            m = tui.Meter(2 * audiofx.GAIN_MAX, lambda v, i=i: on_band(i, v), mark=False)
            m.set_size_request(170, -1)
            v = label("", "mono-pct", xalign=1)
            v.set_width_chars(6)
            nm = label(name, "dim", xalign=0)
            nm.set_width_chars(12)
            meters.append(m)
            vals.append(v)
            if i == 10:
                grid.append(label("", xalign=0))
            grid.append(hbox(nm, m, v, spacing=8))
        box.append(grid)
        paint()
        box.append(hbox(label("", hexpand=True),
                        tui.Button("zurücksetzen", lambda: (st["eq"].update(gains=[0.0] * 10, pre=0.0),
                                                            paint(), changed())), spacing=8))
        box.append(label("Anhebungen senken den Gesamtpegel etwas (Übersteuerungsschutz).", "kp-sub", wrap=True))
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True,
                                    max_content_height=520, child=box)
        pop.set_child(scroll)
        pop.connect("closed", lambda *_: st["id"] is not None and (GLib.source_remove(st["id"]), commit()))
        pop.popup()

