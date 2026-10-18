#!/usr/bin/env bash
# musicalist installieren (ins eigene Benutzerverzeichnis).   ./install.sh [--update]
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RICE="$HOME/.local/share/rice-apps"
DIR="$RICE/music"
UPDATE=0; [[ "${1:-}" == "--update" ]] && UPDATE=1
if (( ! UPDATE )); then
    read -rp "Systempakete (GTK4, gtk4-layer-shell, mpv, cava, nodejs, playerctl) installieren? [J/n] " a
    if [[ ! "${a,,}" =~ ^n ]]; then
        if command -v pacman >/dev/null; then
            sudo pacman -S --needed --noconfirm gtk4 gtk4-layer-shell python-gobject python-cairo mpv cava nodejs playerctl || true
        elif command -v apt >/dev/null; then
            sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-4.0 libgtk4-layer-shell-dev gir1.2-gtk4layershell-1.0 \
                mpv cava nodejs playerctl python3-venv || true
        elif command -v dnf >/dev/null; then
            sudo dnf install -y python3-gobject gtk4 gtk4-layer-shell mpv cava nodejs playerctl || true
        fi
    fi
fi
mkdir -p "$DIR" "$HOME/.local/bin" "$HOME/.local/share/applications"
cp -f "$SRC"/app/music/*.py "$DIR/"
cp -f "$SRC/app/tui.py" "$SRC/app/glass.py" "$RICE/"          # gemeinsame Bausteine der Suite
if [ ! -x "$DIR/venv/bin/python" ]; then
    echo "Lege Python-Umgebung an …"
    python3 -m venv --system-site-packages "$DIR/venv"
fi
"$DIR/venv/bin/pip" install -q --upgrade -r "$SRC/requirements.txt"
install -m 755 "$SRC/rice-music.sh" "$HOME/.local/bin/rice-music"
ln -sf "$HOME/.local/bin/rice-music" "$HOME/.local/bin/musicalist"
rm -f "$HOME/.local/bin/musicminus"      # alter Name bis 2026-10
sed "s|@EXEC@|$HOME/.local/bin/rice-music|g" "$SRC/musicalist.desktop.in" > \
    "$HOME/.local/share/applications/de.invincible.Music.desktop"
"$HOME/.local/bin/rice-music" --daemon || true
echo "Fertig. Hyprland-Einstellungen dazu stehen in der README (Autostart, Super+M, Vorschau-Leiste)."
