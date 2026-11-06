# home-manager:  imports = [ musicalist.homeManagerModules.default ];  programs.musicalist.enable = true;
self:
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.programs.musicalist;
in
{
  options.programs.musicalist = {
    enable = lib.mkEnableOption "musicalist (YouTube-Music-Player)";
    package = lib.mkOption {
      type = lib.types.package;
      default = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
      defaultText = lib.literalExpression "musicalist.packages.\${system}.default";
      description = "Das musicalist-Paket.";
    };
    autostart = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = ''
        musicalist mit der grafischen Sitzung im Hintergrund starten (Tastenkürzel öffnen dann sofort).
        Braucht eine Sitzung, die graphical-session.target startet (z. B. Hyprland mit systemd-Integration).
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    home.packages = [ cfg.package ];

    systemd.user.services.musicalist = lib.mkIf cfg.autostart {
      Unit = {
        Description = "musicalist (Hintergrund)";
        PartOf = [ "graphical-session.target" ];
        After = [ "graphical-session.target" ];
      };
      Service = {
        Environment = [ "MUSICALIST_FOREGROUND=1" ];
        ExecStart = "${lib.getExe cfg.package} --daemon";
        Restart = "on-failure";
      };
      Install.WantedBy = [ "graphical-session.target" ];
    };
  };
}
