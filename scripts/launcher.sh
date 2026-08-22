#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
test -L "$root/blue"
test "$(readlink "$root/blue")" = "skills/package-github-dwh-blue/blue"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cp "$root/skills/package-github-dwh-blue/blue" "$tmp/blue"
chmod +x "$tmp/blue"
if command -v uv >/dev/null 2>&1 && git ls-remote https://github.com/getcolors/github-dwh.git >/dev/null 2>&1; then
  "$tmp/blue" help | grep -F 'Usage: blue'
fi
