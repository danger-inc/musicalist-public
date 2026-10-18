#!/usr/bin/env bash
# musicalist entfernen – inklusive Anmeldung (auth/) und Python-Umgebung.
set -euo pipefail
{ read -r pid < "${XDG_RUNTIME_DIR:-/tmp/musicalist-$UID}/rice-music.pid" && kill "$pid"; } 2>/dev/null || true
RICE="$HOME/.local/share/rice-apps"
rm -rf "$RICE/music"
rm -f "$HOME/.local/bin/rice-music" "$HOME/.local/bin/musicalist" \
      "$HOME/.local/share/applications/de.invincible.Music.desktop" \
      "$HOME/.local/share/icons/hicolor/scalable/apps/musicalist.svg"
# gemeinsame Bausteine nur entfernen, wenn keine andere Suite-App (datist) sie noch braucht
if [ ! -d "$RICE/calendar" ]; then
    rm -rf "$RICE/fonts" "$RICE/tui.py" "$RICE/glass.py" "$RICE/__pycache__"
    rmdir "$RICE" 2>/dev/null || true
fi
echo "musicalist entfernt."
