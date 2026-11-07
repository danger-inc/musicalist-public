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
    openFirewall = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Ports 37526/tcp (Abgleich mit der Handy-App), 37530/tcp (Jam) und mDNS in der Firewall öffnen.";
    };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ cfg.package ];
    networking.firewall = lib.mkIf cfg.openFirewall {
      allowedTCPPorts = [ 37526 37530 ];
      allowedUDPPorts = [ 5353 ];
    };
  };
}
