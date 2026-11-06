{
  description = "musicalist – YouTube-Music-Player im Terminal-Look (GTK4)";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAll = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      packages = forAll (pkgs: rec {
        musicalist = pkgs.callPackage ./nix/package.nix { };
        default = musicalist;
      });

      apps = forAll (pkgs: {
        default = {
          type = "app";
          program = "${self.packages.${pkgs.stdenv.hostPlatform.system}.default}/bin/musicalist";
        };
      });

      overlays.default = final: _prev: { musicalist = final.callPackage ./nix/package.nix { }; };
      homeManagerModules.default = import ./nix/hm-module.nix self;
      nixosModules.default = import ./nix/nixos-module.nix self;
    };
}
