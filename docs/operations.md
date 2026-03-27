# Z-Tools Offline Market Operations

## Prerequisites
- Python 3 installed in the build environment
- Network access to GitHub release assets for pull operations
- Docker with Docker Compose for serving the built market

## 1. Package the complete offline market
Run one Python command to clear any stale output, resolve the release tag, pull release assets, mirror README files and downloadable README images, rewrite exposed metadata URLs to local offline paths when possible, build `market-data`, and verify the final tree.

```bash
python scripts/ztools_offline_market.py package --base-url http://127.0.0.1:18080
```

Specify a tag when you do not want the latest release:

```bash
python scripts/ztools_offline_market.py package --tag v2026.03.23.1338 --base-url http://127.0.0.1:18080
```

Optional flags:
- `--output market-data` to change the publish directory; defaults to `market-data`
- `--repo ZToolsCenter/ZTools-plugins` to change the source repository
- `--timeout 120` to increase the HTTP timeout in seconds
- `--work-dir build/package-source-v2026.03.23.1338` to keep pulled source files in a specific location

Package output includes:
- `market-data/latest`
- `market-data/plugins.json`
- `market-data/categories.json`
- `market-data/layout.yaml`
- `market-data/releases/latest/download/...`
- `market-data/releases/download/<tag>/...`
- `market-data/raw/<plugin>/README.md`
- `market-data/raw/<plugin>/assets/*` for mirrored README images when downloads succeed
- `market-data/market-assets/categories/*` for mirrored category images when downloads succeed
- `market-data/manifests/build-info.json`
- `market-data/manifests/files.sha256`
- `market-data/manifests/source-release.json`

Expected success output:

```text
PACKAGE OK: market-data (v2026.03.23.1338)
```

The command returns a non-zero exit code and prints verification problems if packaging fails.

## 2. Deploy with Docker
Serve the generated `market-data` directory as static files.

```bash
docker compose config
docker compose up -d
```

Smoke test:

```bash
curl http://127.0.0.1:18080/releases/latest/download/latest
curl http://127.0.0.1:18080/releases/latest/download/plugins.json
```

Stop the service:

```bash
docker compose down
```

## 3. Update to a newer tag
Re-run the package command with a specific tag or omit `--tag` to package the latest release again, then restart the static server.

```bash
python scripts/ztools_offline_market.py package --tag v2026.03.24.0000 --base-url http://127.0.0.1:18080
docker compose up -d --force-recreate
```

## Notes
- Keep `market-data` under deployment control; the nginx container is stateless.
- `package` enables README mirroring automatically.
- `package` clears the target output directory and package work directory before rebuilding.
- External README images and category images are mirrored when they can be downloaded; URLs that cannot be mirrored remain unchanged so packaging does not fail.
- `plugins.json`, `categories.json`, mirrored README files, and `manifests/source-release.json` are rewritten to local offline URLs when a local mirrored target exists.
- No Z-Tools client changes are required by this workflow.
