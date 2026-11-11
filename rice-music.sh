#!/usr/bin/env bash
# musicalist (~/.local/share/rice-apps/music): Super+M = rice-music (ein/aus).
#   rice-music [toggle|show|hide|play-pause|next|prev|quit|search:<begriff+mit+plus>]  – sofort
#   rice-music --daemon                                  – Hintergrund-Prozess starten (Autostart)
# MUSICALIST_DIR / MUSICALIST_PYTHON / MUSICALIST_LAYER_SHELL: von Paketen (Nix) gesetzt, sonst die Installation hier
dir=${MUSICALIST_DIR:-$HOME/.local/share/rice-apps/music}
run=${XDG_RUNTIME_DIR:-/tmp/musicalist-$UID}
mkdir -p "$run" 2>/dev/null
fifo=$run/rice-music.fifo

# gtk4-layer-shell (nur für die Vorschau-Karte) – liegt je nach Distribution woanders; fehlt sie, startet
# musicalist ohne Vorschau.
layer_shell() {
    local p
    [[ -n $MUSICALIST_LAYER_SHELL ]] && { echo "$MUSICALIST_LAYER_SHELL"; return; }
    for p in /usr/lib/libgtk4-layer-shell.so.0 /usr/lib64/libgtk4-layer-shell.so.0 \
             /usr/lib/*-linux-gnu/libgtk4-layer-shell.so.0 /usr/local/lib/libgtk4-layer-shell.so.0 \
             /usr/local/lib/*-linux-gnu/libgtk4-layer-shell.so.0 /usr/local/lib64/libgtk4-layer-shell.so.0 \
             /usr/lib/libgtk4-layer-shell.so; do
        [[ -e $p ]] && { echo "$p"; return; }
    done
}

start() {
    local py=${MUSICALIST_PYTHON:-$dir/venv/bin/python}
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
    # MUSICALIST_FOREGROUND=1: im Vordergrund bleiben (systemd-Dienst, Ausgabe ins Journal)
    [[ -n $MUSICALIST_FOREGROUND ]] && XDG_RUNTIME_DIR=$run exec "$py" "$dir/musicd.py" "$@"
    rm -f "$run/rice-music.pid" "$run/rice-music.spawn"
    XDG_RUNTIME_DIR=$run setsid -f sh -c 'echo $$ > "$1/rice-music.spawn"; shift; exec "$@"' sh "$run" "$py" "$dir/musicd.py" "$@" >"$run/rice-music.log" 2>&1 </dev/null
    # Rückmeldung: kommt der Hintergrundprozess nicht hoch, steht der Grund hier (statt nur im Logfile)
    local i sp
    for i in $(seq 1 60); do
        [[ -s $run/rice-music.pid ]] && return 0
        # Prozess schon wieder weg (Absturz beim Import o. ä.)? Dann nicht erst bis zum Ende warten
        { read -r sp < "$run/rice-music.spawn"; } 2>/dev/null
        [[ -n $sp ]] && ! kill -0 "$sp" 2>/dev/null && break
        sleep 0.25
    done
    echo "musicalist startet nicht – letzte Meldungen aus $run/rice-music.log:" >&2
    tail -n 15 "$run/rice-music.log" >&2 2>/dev/null
    command -v notify-send >/dev/null && notify-send musicalist "Startet nicht – Details: $run/rice-music.log"
    return 1
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
