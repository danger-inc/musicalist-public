#!/usr/bin/env bash
# musicalist (~/.local/share/rice-apps/music): Super+M = rice-music (ein/aus).
#   rice-music [toggle|show|hide|play-pause|next|prev|search:<begriff+mit+plus>]  – sofort
#   rice-music --daemon                                  – Hintergrund-Prozess starten (hyprland.lua)
dir=$HOME/.local/share/rice-apps/music
fifo=$XDG_RUNTIME_DIR/rice-music.fifo
start() {
    LD_PRELOAD=/usr/lib/libgtk4-layer-shell.so setsid -f "$dir/venv/bin/python" "$dir/musicd.py" "$@" \
        >"$XDG_RUNTIME_DIR/rice-music.log" 2>&1 </dev/null
}
{ read -r pid < "$XDG_RUNTIME_DIR/rice-music.pid"; } 2>/dev/null
running() { [[ -n $pid && -p $fifo ]] && kill -0 "$pid" 2>/dev/null; }
if [[ $1 == --daemon ]]; then
    running && { kill "$pid"; sleep 0.6; }
    start
elif running; then
    echo "${1:-toggle}" > "$fifo"
else
    start --show
fi
