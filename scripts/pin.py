#!/usr/bin/env python3
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
revision = subprocess.check_output(["git", "-C", root, "rev-parse", "HEAD"], text=True).strip()
blue_revision = subprocess.check_output(["git", "-C", root.parent / "blue", "rev-parse", "HEAD"], text=True).strip()
launcher = f'''#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["package-github-dwh-blue", "blue"]
#
# [tool.uv.sources]
# package-github-dwh-blue = {{ git = "https://github.com/getcolors/github-dwh.git", rev = "{revision}" }}
# blue = {{ git = "https://github.com/getcolors/blue.git", rev = "{blue_revision}" }}
# ///
import os
os.environ.setdefault("GITHUB_DWH_PACKAGE_REVISION", "{revision}")
from package_github_dwh_blue import exec, run
__all__ = ["run"]
if __name__ == "__main__": exec()
'''
(root / "skills/package-github-dwh-blue/blue").write_text(launcher)
(root / "skills/package-github-dwh-blue/blue").chmod(0o755)
print(revision)
