# musicalist

YouTube-Music-Player im Terminal-Look der Suite (GTK4): Suche, Bibliothek, Radio/Autoplay, Songtexte, Spektrum
(cava), Medientasten (MPRIS) und eine **Vorschau-Karte**, die unten mittig hochgleitet, wenn die Maus an den
Bildschirmrand fährt (Leertaste = Pause, ←/→ = Titel zurück/vor).

## Installieren

```bash
git clone https://github.com/invincible-nix/musicalist-public ~/musicalist-src
cd ~/musicalist-src && ./install.sh
```

Braucht Wayland mit Layer-Shell (Hyprland, Sway …), mpv, cava, nodejs. Die Python-Bibliotheken (ytmusicapi,
yt-dlp) landen in einer eigenen Umgebung unter `~/.local/share/rice-apps/music/venv`.

## Hyprland

```lua
-- Autostart (wartet im Hintergrund), innerhalb von hl.on("hyprland.start", function () … end):
hl.exec_cmd(os.getenv("HOME") .. "/.local/bin/rice-music --daemon")
-- ein-/ausblenden:
hl.bind("SUPER + M", hl.dsp.exec_cmd(os.getenv("HOME") .. "/.local/bin/rice-music"))
-- Vorschau-Karte: weich einblenden und Unschärfe dahinter
hl.layer_rule({
    name         = "blur-music-preview",
    match        = { namespace = "^music-preview$" },
    blur         = true,
    ignore_alpha = 0.1,
    animation    = "slide bottom",
})
```

## Anmeldung

Im Player auf „mit zen anmelden“ klicken: musicalist übernimmt die YouTube-Sitzung aus dem Zen/Firefox-Profil.
**Abspielen geht nur mit Anmeldung:** Suchen und Stöbern klappt auch ohne, Titel werden aber erst
wiedergegeben, wenn die Anmeldung bei Google bestätigt ist.

Die Anmeldedaten liegen nur lokal in `~/.local/share/rice-apps/music/auth` (Rechte 600) und werden nirgends
hochgeladen.

## Befehle

`rice-music` (ein/aus) · `rice-music show|hide|play-pause|next|prev` · `rice-music search:begriff+mit+plus`
`./update.sh` aktualisiert, `./uninstall.sh` entfernt alles inklusive Anmeldung.
