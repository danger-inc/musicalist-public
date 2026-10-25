# musicalist

youtube music player in the terminal look of the suite (gtk4): search, library, radio/autoplay, lyrics, spectrum
(cava), media keys (mpris) and, if you want, a **preview card** that slides up at the bottom when the mouse
hits the screen edge (space = pause, ←/→ = previous/next track).

## install

the repository is public – no account needed:

```bash
git clone https://github.com/danger-inc/musicalist-public ~/musicalist-src
cd ~/musicalist-src && ./install.sh
```

the installer asks for the password once (for the system packages: gtk4, mpv, cava, playerctl), sets up its own
python environment for ytmusicapi/yt-dlp (`~/.local/share/rice-apps/music/venv`) and installs the command
`musicalist` and an application menu entry. packages that don't exist on your distribution are skipped
and listed at the end – everything else is installed anyway.

start with `musicalist` or from the application menu. calling it again shows/hides the window;
✕ / `q` exits musicalist completely and the music stops. to keep playing with the window closed:
settings (⚙ or `,`) → "beim schließen im hintergrund weiterspielen".

## runs on

| system | status |
| --- | --- |
| ubuntu 24.04+, linux mint 22+, debian 13 | tested (ubuntu 24.04) |
| fedora 39+ | tested (fedora 44) |
| arch, endeavouros, cachyos, manjaro | tested (arch) |
| openSUSE Tumbleweed | should work (untested) |
| windows | core features (player, search, library, lyrics); no hover preview, spectrum or media keys – run install-windows.bat |
| macos | no |

required is **gtk 4.12 or newer** (older systems like ubuntu 22.04 / mint 21 / debian 12 are too old).
`mpv` plays the audio. `cava` (spectrum) and `playerctl` are optional.

## settings (⚙ or `,`)

* **preview card at the bottom edge (hover)** – **off** by default. needs wayland with layer-shell
(hyprland, sway, kde plasma …) and the package `gtk4-layer-shell`; not available on gnome and x11.
if it causes trouble: just leave it off.

## login

in the tab "bibliothek" click "mit zen/firefox anmelden": musicalist takes over the youtube session from your
zen, firefox or librewolf profile (snap/flatpak too). log in at music.youtube.com there first.
chrome/chromium don't work (they encrypt their cookies).
**playback needs a login:** searching and browsing work without, but tracks only play once
the google login is confirmed.

the login data stays local in `~/.local/share/rice-apps/music/auth` (permissions 600) and is never
uploaded anywhere.

## keys

space play/pause · n/p next/previous · ←/→ seek · +/− volume · l ♥ · a add to playlist · / search · 1–6 tabs ·
h history bar · v/f visuals mode/fullscreen · ? all keys · q closes (not esc – so you don't close it by accident).

## hyprland (optional)

```lua
-- autostart (waits in the background), inside hl.on("hyprland.start", function () … end):
hl.exec_cmd(os.getenv("HOME") .. "/.local/bin/rice-music --daemon")
-- show/hide:
hl.bind("SUPER + M", hl.dsp.exec_cmd(os.getenv("HOME") .. "/.local/bin/rice-music"))
-- preview card (if enabled): fade in and blur behind it
hl.layer_rule({
    name         = "blur-music-preview",
    match        = { namespace = "^music-preview$" },
    blur         = true,
    ignore_alpha = 0.1,
    animation    = "slide bottom",
})
```

other desktops: bind a shortcut to the command `musicalist` (gnome: settings → keyboard →
custom shortcuts; kde: system settings → shortcuts).

## commands

`musicalist` (toggle) · `musicalist show|hide|play-pause|next|prev` · `musicalist search:term+with+plus`

## update / remove

```bash
cd ~/musicalist-src && ./update.sh      # fetches the new version, restarts musicalist
./uninstall.sh                          # removes everything including the login
```

## problems?

* **no sound / "wiedergabe fehlgeschlagen":** is `mpv` installed? (`mpv --version`). then run `./install.sh` again.
* **`musicalist: command not found`:** `~/.local/bin` is missing in `PATH` – the installer says at the end what belongs
in `~/.bashrc`. from the application menu it starts anyway.
* **boxes instead of symbols:** `./update.sh` (the icon font comes along and is loaded automatically).
* **doesn't start:** `cat $XDG_RUNTIME_DIR/rice-music.log` shows the error message.
