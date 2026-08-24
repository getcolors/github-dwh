# CLAUDE.md

## Repository

`github-dwh` is a Blue Package Skill for a single-host GitHub organization warehouse. OpenTofu provisions one Vultr VM and Cloudflare DNS; Ansible converges ClickHouse, PocketBase, Caddy, a systemd dispatcher, and the Blue/dlt/dbt runtime. Git owns desired state and the workflow graph. PocketBase owns schedules and whole-run history only.

## Commands

```sh
uv sync
uv run pytest
./scripts/golden.sh
./scripts/launcher.sh
./blue build
./blue create --dry-run
```

Never read `.envrc.private`, edit `.colors/`, export `COLORS_PAR_PROFILE`, or weaken `compute-prevent-destroy`. Real create/delete requires explicit authorization. `run` loads GitHub data and is a real external side effect unless `--dry-run` is present.

## Boundaries

One PocketBase run is one `./blue run`. PocketBase must never acquire task DAGs, per-step queues, sensors, XCom-like values, or retry policy. systemd supervises processes; Blue owns workflow routing; journald owns full logs.

## Documentation

`index.html` is this repository's landing page and carries two analytics tags:
GA4 measurement ID `G-4VKP1WY4QJ`, whose explicit `page_title` must exactly
equal the decoded HTML `<title>` and stay distinct and stable so one Analytics
property can separate repositories, and the self-hosted Rybbit snippet
`<script src="https://rybbit.getcolors.ai/api/script.js" data-site-id="9fb9c41a6d49" defer></script>`,
which shares one site ID across every page because `getcolors.github.io/<repo>/`
paths already encode the repository. Never add one tag without the other.

## Git

Work on the current branch. Do not commit or push unless explicitly authorized.
