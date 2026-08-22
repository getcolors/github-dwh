#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
cmp "$root/skills/package-github-dwh-blue/blue" "$root/test/expected-launcher" >/dev/null || {
  echo "launcher does not match pinned expected launcher" >&2
  exit 1
}
