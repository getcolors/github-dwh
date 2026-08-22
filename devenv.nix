{ pkgs, ... }: {
  languages.ansible.enable = true;
  languages.opentofu.enable = true;
  packages = with pkgs; [ uv shellcheck ];
}
