# NixOS:  imports = [ musicalist.nixosModules.default ];  programs.musicalist.enable = true;
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
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ cfg.package ];
  };
}
