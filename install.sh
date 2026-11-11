#!/usr/bin/env bash
# musicalist installieren (ins eigene Benutzerverzeichnis, root nur für Systempakete).
#   ./install.sh            normal (fragt nach Systempaketen)
#   ./install.sh --update   ohne Rückfragen (von update.sh)
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SRC/pkg.sh"
RICE="$HOME/.local/share/rice-apps"
DIR="$RICE/music"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/scalable/apps"
UPDATE=0; [[ "${1:-}" == "--update" ]] && UPDATE=1

say "== musicalist installieren =="
# Fehlt Wichtiges (z. B. weil eine ältere Installation bei apt abgebrochen ist), installiert auch
# ./update.sh die Systempakete nach – sonst fragt nur die normale Installation.
# System-Python (nicht pyenv/conda/asdf!): nur der hat PyGObject (gi). Eine mit pyenv angelegte Umgebung findet gi nicht.
SYSPY0=python3; [ -x /usr/bin/python3 ] && SYSPY0=/usr/bin/python3
basics_missing() {
    command -v mpv >/dev/null 2>&1 || return 0
    "$SYSPY0" -c 'import ensurepip, gi; gi.require_version("Gtk", "4.0")' 2>/dev/null || return 0
    return 1
}
if { (( UPDATE )) && basics_missing && say "Es fehlen Systempakete – werden nachinstalliert …"; } \
   || ask "Systempakete installieren (GTK4, mpv, cava, playerctl …)?"; then
    pkg_install \
        "gtk4 gtk4-layer-shell python python-gobject python-cairo mpv cava playerctl adwaita-icon-theme libpulse" \
        "python3 python3-venv python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-gtk4layershell-1.0 libgtk4-layer-shell0 mpv cava playerctl adwaita-icon-theme pulseaudio-utils" \
        "python3 python3-gobject python3-cairo gtk4 gtk4-layer-shell mpv cava playerctl adwaita-icon-theme pulseaudio-utils" \
        "python3 python3-gobject python3-gobject-cairo python3-gobject-Gdk typelib-1_0-Gtk-4_0 typelib-1_0-Gtk4LayerShell-1_0 mpv cava playerctl adwaita-icon-theme pulseaudio-utils" \
        || warn "Paketinstallation nicht vollständig – weiter."
fi
echo

# cava (Live-Spektrum) gehört fest dazu: fehlt es – auch im Update-Modus, ohne Rückfrage – wird es einzeln
# nachinstalliert. Ubuntu/Mint: cava liegt in „universe“; ist das aus, wird es eingeschaltet.
ensure_cava() {
    command -v cava >/dev/null 2>&1 && return 0
    say "cava (Live-Spektrum) fehlt – wird installiert …"
    pkg_install "cava" "cava" "cava" "cava" || true
    command -v cava >/dev/null 2>&1 && return 0
    if command -v apt-get >/dev/null 2>&1 && command -v add-apt-repository >/dev/null 2>&1; then
        warn "cava nicht in den Paketquellen – schalte „universe“ ein …"
        as_root add-apt-repository -y universe >/dev/null 2>&1 || true
        pkg_install "cava" "cava" "cava" "cava" || true
    fi
    command -v cava >/dev/null 2>&1 || warn "cava konnte nicht installiert werden (Paket „cava“) – musicalist rechnet das Spektrum dann selbst (mpv)."
}
if ! command -v cava >/dev/null 2>&1 && pkg_manager >/dev/null 2>&1; then ensure_cava; echo; fi

# alten Hintergrundprozess beenden – notfalls hart (alte Versionen konnten unter GNOME hängen);
# lief er, wird er am Ende neu gestartet
was_running=0
{ read -r pid < "${XDG_RUNTIME_DIR:-/tmp/musicalist-$UID}/rice-music.pid" && kill "$pid" && was_running=1; } 2>/dev/null || true
if command -v pgrep >/dev/null 2>&1 && pgrep -u "$(id -u)" -f "rice-apps/music/musicd.py" >/dev/null; then
    was_running=1
    pkill -u "$(id -u)" -f "rice-apps/music/musicd.py" || true
    sleep 1
    pkill -9 -u "$(id -u)" -f "rice-apps/music/musicd.py" 2>/dev/null || true
fi

say "Kopiere musicalist nach $DIR …"
mkdir -p "$DIR" "$RICE/fonts" "$BIN" "$APPS" "$ICONS"
cp -f "$SRC"/app/music/*.py "$SRC"/app/music/VERSION "$SRC"/app/music/CHANGELOG.md "$DIR/"
cp -f "$SRC/app/tui.py" "$SRC/app/glass.py" "$SRC/app/istheme.py" "$SRC/app/ist-swipe.py" "$SRC/app/changelog.py" "$SRC/app/swipe.py" "$RICE/"             # gemeinsame Bausteine der Suite
cp -f "$SRC"/app/fonts/* "$RICE/fonts/"                           # Symbolschrift (Icons ohne Nerd Font)

say "Python-Umgebung (ytmusicapi, yt-dlp) …"
pick_python() {
    local p
    for p in /usr/bin/python3 /usr/local/bin/python3 /usr/bin/python3.[0-9]* /usr/bin/python3.[0-9][0-9]; do
        [ -x "$p" ] && "$p" -c 'import gi' 2>/dev/null && { echo "$p"; return; }
    done
    echo "$SYSPY0"
}
SYSPY=$(pick_python)
if ! "$SYSPY" -c 'import gi' 2>/dev/null; then
    warn "Das System-Python ($SYSPY) hat kein PyGObject (gi). Installiere python3-gi / python-gobject (siehe oben) – dann ./install.sh erneut."
    exit 1
fi
echo "  Python: $SYSPY ($("$SYSPY" -c 'import sys; print("%d.%d" % sys.version_info[:2])'))"
if [ ! -x "$DIR/venv/bin/python" ] || ! "$DIR/venv/bin/python" -c "import gi, pip" 2>/dev/null; then
    rm -rf "$DIR/venv"
    if ! "$SYSPY" -m venv --system-site-packages "$DIR/venv"; then
        warn "Konnte keine Python-Umgebung anlegen. Debian/Ubuntu/Mint: sudo apt install python3-venv – dann ./install.sh erneut."
        exit 1
    fi
fi
"$DIR/venv/bin/python" -m pip install -q --disable-pip-version-check --upgrade -r "$SRC/requirements.txt"

install -m 755 "$SRC/rice-music.sh" "$BIN/rice-music"
ln -sf "$BIN/rice-music" "$BIN/musicalist"
rm -f "$BIN/musicminus"                                            # alter Name bis 2026-10
sed "s|@EXEC@|$BIN/rice-music|g" "$SRC/musicalist.desktop.in" > "$APPS/de.invincible.Music.desktop"
cp -f "$SRC/musicalist.svg" "$ICONS/musicalist.svg"
refresh_desktop

echo
say "Prüfe …"
check_gtk || true
for t in mpv cava playerctl pactl; do
    if command -v "$t" >/dev/null 2>&1; then echo "  $t: ok"
    else
        case $t in
            mpv) warn "  mpv: FEHLT – ohne mpv kein Ton (Paket „mpv“)";;
            cava) echo "  cava: fehlt – das Spektrum wird dann von mpv berechnet";;
            playerctl) echo "  playerctl: fehlt – optional";;
            pactl) echo "  pactl: fehlt – nur „andere quellen“ bleibt leer";;
        esac
    fi
done
"$DIR/venv/bin/python" -c "import ytmusicapi, yt_dlp" && echo "  ytmusicapi/yt-dlp: ok"
GI_TYPELIB_PATH=$(ls -d /usr/local/lib/girepository-1.0 /usr/local/lib*/*/girepository-1.0 2>/dev/null | paste -sd: -)${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH} \
"$DIR/venv/bin/python" - <<'PY'
try:
    import gi
    gi.require_version("Gtk4LayerShell", "1.0")
    print("  vorschau-karte (gtk4-layer-shell): möglich – in den einstellungen einschaltbar")
except Exception:
    print("  vorschau-karte: nicht verfügbar (gtk4-layer-shell fehlt) – der player läuft trotzdem")
PY
echo

(( was_running )) && [ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ] && { "$BIN/rice-music" --daemon || true; }
path_hint
say "Fertig!  Starten mit:  musicalist   (oder über das Anwendungsmenü)"
echo "Tastenkürzel/Autostart für Hyprland & Co.: siehe README.   Aktualisieren: ./update.sh   Entfernen: ./uninstall.sh"
