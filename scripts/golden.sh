#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cp "$root/test/fixtures/colors.yml" "$tmp/colors.yml"
(cd "$tmp" && BLUE_LIB_ROOT="$root/../blue" uv run --project "$root" python -m package_github_dwh_blue build >/dev/null)
diff -ru "$root/test/resources/golden" "$tmp/.colors/github-dwh-test"
