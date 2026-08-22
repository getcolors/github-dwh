from __future__ import annotations

import asyncio
import sys
from blue.cli import find_up, run_cli
from .workflow import github_dwh_workflow

USAGE = "Usage: blue <build|create|run|delete> [-f|--file colors.yml] [--dry-run]"


def default_args(args: list[str]) -> list[str]:
    if any(a in ("-f", "--file") or a.startswith("--file=") for a in args):
        return args
    return [*args, "-f", find_up("colors.yml") or "colors.yml"]


async def run(*input: str) -> dict:
    args = default_args(list(input))
    command = args[0] if args else None
    if command in ("help", "--help", "-h"):
        return {"blue/exit": 0, "blue/err": USAGE}
    if command not in ("build", "create", "run", "delete"):
        return {"blue/exit": 2, "blue/err": USAGE}
    return await run_cli(github_dwh_workflow, args, allowed_events=["build", "create", "run", "delete"])


def exec(args: list[str] | None = None) -> None:
    result = asyncio.run(run(*(sys.argv[1:] if args is None else args)))
    if result.get("blue/err"):
        print(result["blue/err"], file=sys.stdout if (result.get("blue/exit") or 0) == 0 else sys.stderr)
    raise SystemExit(result.get("blue/exit") or 0)
