#!/usr/bin/env bash
# musicalist entfernen – inklusive Anmeldung (auth/) und Python-Umgebung.
set -euo pipefail
{ read -r pid < "${XDG_RUNTIME_DIR:-/tmp}/rice-music.pid" && kill "$pid"; } 2>/dev/null || true
rm -rf "$HOME/.local/share/rice-apps/music"
rm -f "$HOME/.local/bin/rice-music" "$HOME/.local/bin/musicalist" "$HOME/.local/share/applications/de.invincible.Music.desktop"
echo "musicalist entfernt."
