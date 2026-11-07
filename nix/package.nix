# musicalist als Nix-Paket. Der Code liegt schreibgeschützt im Store – musicalist merkt das und legt
# Anmeldung, Einstellungen und Verlauf in ~/.local/share/musicalist ab (yt-dlp-Updates dort in pylibs/).
{
  lib,
  stdenvNoCC,
  python3,
  wrapGAppsHook4,
  gobject-introspection,
  makeWrapper,
  gtk4,
  gtk4-layer-shell,
  glib,
  pango,
  gdk-pixbuf,
  graphene,
  librsvg,
  adwaita-icon-theme,
  mpv,
  cava,
  playerctl,
  pulseaudio,
  nodejs,
  libnotify,
  xdg-utils,
  util-linux,
  coreutils,
}:

let
  py = python3.withPackages (p: [
    p.pygobject3
    p.pycairo
    p.ytmusicapi
    p.yt-dlp
    p.yt-dlp-ejs
    p.requests
    p.mutagen
    p.zeroconf # Handy-App findet den PC im WLAN
    p.qrcode # QR-Code der Jam
    p.pip # für die eingebaute yt-dlp-Aktualisierung (nach ~/.local/share/musicalist/pylibs)
  ]);
  src = lib.cleanSourceWith {
    src = ./..;
    filter = path: _type: !(lib.hasSuffix ".nix" path || lib.hasSuffix "flake.lock" path);
  };
in
stdenvNoCC.mkDerivation {
  pname = "musicalist";
  version = lib.strings.trim (builtins.readFile ../app/music/VERSION);
  inherit src;

  nativeBuildInputs = [
    wrapGAppsHook4
    gobject-introspection
    makeWrapper
  ];
  buildInputs = [
    gtk4
    gtk4-layer-shell
    glib
    pango
    gdk-pixbuf
    graphene
    librsvg
    adwaita-icon-theme
  ];
  dontWrapGApps = true; # selbst gewickelt (unten), damit nur der Starter die GTK-Umgebung bekommt
  dontBuild = true;

  installPhase = ''
    runHook preInstall
    share=$out/share/musicalist
    mkdir -p $share $out/bin $out/libexec/musicalist
    cp -r app $share/
    ${py}/bin/python3 -m compileall -q $share/app
    install -m755 rice-music.sh $out/libexec/musicalist/rice-music
    install -Dm644 musicalist.svg $out/share/icons/hicolor/scalable/apps/musicalist.svg
    mkdir -p $out/share/applications
    substitute musicalist.desktop.in $out/share/applications/de.invincible.Music.desktop \
      --replace-fail @EXEC@ $out/bin/musicalist
    runHook postInstall
  '';

  postFixup = ''
    makeWrapper $out/libexec/musicalist/rice-music $out/bin/musicalist \
      "''${gappsWrapperArgs[@]}" \
      --set MUSICALIST_DIR $out/share/musicalist/app/music \
      --set MUSICALIST_PYTHON ${py}/bin/python3 \
      --set MUSICALIST_LAYER_SHELL ${gtk4-layer-shell}/lib/libgtk4-layer-shell.so.0 \
      --set IST_PACKAGED nix \
      --prefix PATH : ${
        lib.makeBinPath [
          py
          mpv
          cava
          playerctl
          pulseaudio
          nodejs
          libnotify
          xdg-utils
          util-linux
          coreutils
        ]
      }
    ln -s musicalist $out/bin/rice-music
  '';

  meta = {
    description = "YouTube-Music-Player im Terminal-Look (GTK4)";
    mainProgram = "musicalist";
    platforms = lib.platforms.linux;
  };
}
