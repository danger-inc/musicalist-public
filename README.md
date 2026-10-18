# musicalist

YouTube-Music-Player im Terminal-Look der Suite (GTK4): Suche, Bibliothek, Radio/Autoplay, Songtexte, Spektrum
(cava), Medientasten (MPRIS) und auf Wunsch eine **Vorschau-Karte**, die unten mittig hochgleitet, wenn die Maus an
den Bildschirmrand fährt (Leertaste = Pause, ←/→ = Titel zurück/vor).

## Installieren

```bash
git clone https://github.com/invincible-nix/musicalist-public ~/musicalist-src
cd ~/musicalist-src && ./install.sh
```

Der Installer fragt einmal nach dem Passwort (für die Systempakete: GTK4, mpv, cava, playerctl), legt eine eigene
Python-Umgebung für ytmusicapi/yt-dlp an (`~/.local/share/rice-apps/music/venv`), installiert den Befehl
`musicalist` und einen Eintrag im Anwendungsmenü. Pakete, die es auf deiner Distribution nicht gibt, werden
übersprungen und am Ende genannt – der Rest wird trotzdem installiert.

Starten: `musicalist` oder über das Anwendungsmenü. Nochmal aufrufen blendet das Fenster ein/aus;
die Musik läuft weiter, wenn das Fenster zu ist (ganz beenden: `./uninstall.sh` oder abmelden).

## Läuft auf

| System | Status |
|---|---|
| Ubuntu 24.04+, Linux Mint 22+, Debian 13 | getestet (Ubuntu 24.04) |
| Fedora 39+ | getestet (Fedora 44) |
| Arch, EndeavourOS, CachyOS, Manjaro | getestet (Arch) |
| openSUSE Tumbleweed | sollte gehen (ungetestet) |
| Windows / macOS | nein – musicalist braucht Linux (mpv-Steuerung, MPRIS, Layer-Shell) |

Nötig ist **GTK 4.12 oder neuer** (ältere Systeme wie Ubuntu 22.04 / Mint 21 / Debian 12 sind zu alt).
Das Programm `mpv` spielt den Ton ab. `cava` (Spektrum) und `playerctl` sind optional.

## Einstellungen (Tab 6 bzw. ⚙)

- **Vorschau-Karte am unteren Bildschirmrand (Hover)** – standardmäßig **aus**. Braucht Wayland mit Layer-Shell
  (Hyprland, Sway, KDE Plasma …) und das Paket `gtk4-layer-shell`; unter GNOME und X11 nicht verfügbar.
  Wenn sie Probleme macht: einfach ausgeschaltet lassen.

## Anmeldung

Im Tab „bibliothek“ auf „mit zen/firefox anmelden“ klicken: musicalist übernimmt die YouTube-Sitzung aus deinem
Zen-, Firefox- oder LibreWolf-Profil (auch Snap/Flatpak). Vorher dort bei music.youtube.com einloggen.
Chrome/Chromium gehen nicht (die verschlüsseln ihre Cookies).
**Abspielen geht nur mit Anmeldung:** Suchen und Stöbern klappt auch ohne, Titel werden aber erst
wiedergegeben, wenn die Anmeldung bei Google bestätigt ist.

Die Anmeldedaten liegen nur lokal in `~/.local/share/rice-apps/music/auth` (Rechte 600) und werden nirgends
hochgeladen.

## Tasten

Leertaste Play/Pause · n/p weiter/zurück · ←/→ spulen · +/− Lautstärke · l ♥ · / Suche · 1–6 Tabs ·
q schließt das Fenster (Esc nicht – damit man es nicht aus Versehen zumacht).

## Hyprland (optional)

```lua
-- Autostart (wartet im Hintergrund), innerhalb von hl.on("hyprland.start", function () … end):
hl.exec_cmd(os.getenv("HOME") .. "/.local/bin/rice-music --daemon")
-- ein-/ausblenden:
hl.bind("SUPER + M", hl.dsp.exec_cmd(os.getenv("HOME") .. "/.local/bin/rice-music"))
-- Vorschau-Karte (falls eingeschaltet): weich einblenden und Unschärfe dahinter
hl.layer_rule({
    name         = "blur-music-preview",
    match        = { namespace = "^music-preview$" },
    blur         = true,
    ignore_alpha = 0.1,
    animation    = "slide bottom",
})
```

Andere Oberflächen: eine Tastenkombination auf den Befehl `musicalist` legen (GNOME: Einstellungen → Tastatur →
Eigene Tastenkürzel; KDE: Systemeinstellungen → Kurzbefehle).

## Befehle

`musicalist` (ein/aus) · `musicalist show|hide|play-pause|next|prev` · `musicalist search:begriff+mit+plus`

## Aktualisieren / entfernen

```bash
cd ~/musicalist-src && ./update.sh      # holt die neue Version, startet musicalist neu
./uninstall.sh                          # entfernt alles inklusive Anmeldung
```

## Probleme?

- **Kein Ton / „wiedergabe fehlgeschlagen“:** `mpv` installiert? (`mpv --version`). Danach `./install.sh` erneut.
- **`musicalist: Befehl nicht gefunden`:** `~/.local/bin` fehlt im PATH – der Installer sagt am Ende, was in die
  `~/.bashrc` gehört. Über das Anwendungsmenü startet es auch so.
- **Kästchen statt Symbolen:** `./update.sh` (die Symbolschrift kommt jetzt mit und wird automatisch geladen).
- **Startet nicht:** `cat $XDG_RUNTIME_DIR/rice-music.log` zeigt die Fehlermeldung.
