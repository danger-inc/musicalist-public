#!/usr/bin/env bash
# musicalist (~/.local/share/rice-apps/music): Super+M = rice-music (ein/aus).
#   rice-music [toggle|show|hide|play-pause|next|prev|quit|search:<begriff+mit+plus>]  – sofort
#   rice-music --daemon                                  – Hintergrund-Prozess starten (Autostart)
dir=$HOME/.local/share/rice-apps/music
run=${XDG_RUNTIME_DIR:-/tmp/musicalist-$UID}
mkdir -p "$run" 2>/dev/null
fifo=$run/rice-music.fifo

# gtk4-layer-shell (nur für die Vorschau-Karte) – liegt je nach Distribution woanders; fehlt sie, startet
# musicalist ohne Vorschau.
layer_shell() {
    local p
    for p in /usr/lib/libgtk4-layer-shell.so.0 /usr/lib64/libgtk4-layer-shell.so.0 \
             /usr/lib/*-linux-gnu/libgtk4-layer-shell.so.0 /usr/local/lib/libgtk4-layer-shell.so.0 \
             /usr/local/lib/*-linux-gnu/libgtk4-layer-shell.so.0 /usr/local/lib64/libgtk4-layer-shell.so.0 \
             /usr/lib/libgtk4-layer-shell.so; do
        [[ -e $p ]] && { echo "$p"; return; }
    done
}

start() {
    local py=$dir/venv/bin/python
    if [[ ! -x $py ]]; then
        echo "musicalist ist nicht (vollständig) installiert – bitte ./install.sh im Quellordner ausführen." >&2
        command -v notify-send >/dev/null && notify-send musicalist "Nicht vollständig installiert – ./install.sh ausführen."
        exit 1
    fi
    local pre; pre=$(layer_shell)
    # nur unter Wayland vorladen (unter X11 hilft es nichts)
    [[ -n $WAYLAND_DISPLAY && -n $pre ]] && export LD_PRELOAD=$pre${LD_PRELOAD:+:$LD_PRELOAD}
    # selbst gebaut (/usr/local): Python findet die Typelib dort sonst nicht
    if [[ $pre == /usr/local/* ]]; then
        local d=${pre%/*}/girepository-1.0
        [[ -d $d ]] && export GI_TYPELIB_PATH=$d${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}
    fi
    XDG_RUNTIME_DIR=$run setsid -f "$py" "$dir/musicd.py" "$@" >"$run/rice-music.log" 2>&1 </dev/null
}
{ read -r pid < "$run/rice-music.pid"; } 2>/dev/null
running() { [[ -n $pid && -p $fifo ]] && kill -0 "$pid" 2>/dev/null; }
if [[ $1 == --daemon ]]; then
    if running; then
        kill "$pid"; sleep 0.6
        kill -0 "$pid" 2>/dev/null && { sleep 1; kill -9 "$pid" 2>/dev/null; }   # hängt → hart beenden
    fi
    start
elif running; then
    # Startberechtigung vom Desktop (GNOME/KDE) mitgeben, damit das Fenster nach vorn darf
    echo "${XDG_ACTIVATION_TOKEN:+token:$XDG_ACTIVATION_TOKEN }${1:-toggle}" > "$fifo"
else
    start --show
fi
