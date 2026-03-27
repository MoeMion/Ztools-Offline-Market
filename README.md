# Z-Tools Offline Market

A Python-based packager for building a fully static offline mirror of the Z-Tools plugin market without modifying the Z-Tools client.

## What it does

- resolves the latest release tag automatically or uses a tag you provide
- downloads release metadata and plugin archives
- clears stale package output before each rebuild
- mirrors plugin README files when available
- mirrors downloadable README image assets and rewrites README links to local paths when possible
- rewrites exposed plugin, category, README, and source-manifest URLs to local offline paths when possible
- keeps failed external image downloads as original URLs so packaging can continue
- builds a static `market-data` tree compatible with the client
- serves the result with nginx through Docker Compose

## Quick start

Package the market in one Python command:

```bash
python scripts/ztools_offline_market.py package --base-url http://127.0.0.1:18080
```

Serve it in one Docker command:

```bash
docker compose up -d --force-recreate
```

## Common usage

Use the latest upstream release:

```bash
python scripts/ztools_offline_market.py package --base-url http://127.0.0.1:18080
```

Use a specific tag:

```bash
python scripts/ztools_offline_market.py package --tag v2026.03.23.1338 --base-url http://127.0.0.1:18080
```

Write output to a custom directory:

```bash
python scripts/ztools_offline_market.py package --base-url http://127.0.0.1:18080 --output custom-market-data
```

## Repository layout

```text
scripts/
  ztools_offline_market.py   Main CLI

tests/
  test_build.py              Build and package tests
  test_pull.py               Pull and README mirroring tests
  test_verify.py             Output verification tests

docker/
  nginx.conf                 Static nginx config

fixtures/
  sample_release/            Minimal fixture data for tests

docs/
  operations.md              Detailed operations guide
```

## CLI commands

- `package` — one-command workflow for pull + README mirroring + build + verify
- `pull` — download source release assets into a local directory
- `build` — build a publishable static market tree from a source directory
- `verify` — verify a generated market tree

## Notes

- The default output directory is `market-data`.
- When `--tag` is omitted, the tool resolves the latest upstream release automatically.
- Docker serves files from `./market-data`, so if you use a custom output directory you should update `docker-compose.yml` or rename the output directory.
- See `docs/operations.md` for the full operational workflow.

## Vibe Coding Alert

This repository is completely built with Claude Code. 请自行承担可能存在的任何风险。 