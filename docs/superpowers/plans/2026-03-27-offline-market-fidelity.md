# Offline Market Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `package` produce a fully offline market tree that matches ZTools client expectations for plugin downloads and README rendering, rewrites all exposed external URLs to local ones where possible, and clears stale output before each run.

**Architecture:** Keep the existing single-file CLI structure, but extract the current README-only mirroring into a generalized URL collection + mirroring + rewrite flow. Treat `plugins.json`, `categories.json`, `raw/<plugin>/README.md`, and `manifests/source-release.json` as rewrite targets, while preserving graceful fallback for resources that cannot be mirrored.

**Tech Stack:** Python 3, `urllib.request`, `json`, `re`, `pathlib`, `pytest`

---

## File structure

- Modify `scripts/ztools_offline_market.py`
  - Add helpers to clear directories before package generation
  - Add helpers to mirror and rewrite URLs in JSON payloads and README content
  - Align README URL generation with ZTools client behavior
  - Rewrite manifest/category/plugin URLs to offline-local paths
- Modify `tests/test_pull.py`
  - Add failing tests for category image rewriting, source manifest rewriting, package directory cleanup, and client-aligned README path handling
- Modify `tests/test_build.py`
  - Add failing tests for output cleanup behavior and manifest rewrite output where build/package owns the transformation
- Modify `docs/operations.md`
  - Document full offline rewrite scope and output clearing behavior
- Modify `README.md`
  - Document the same user-facing behavior succinctly

### Task 1: Align pull/package behavior with client download/readme expectations

**Files:**
- Modify: `scripts/ztools_offline_market.py`
- Test: `tests/test_pull.py`

- [ ] **Step 1: Write the failing test**

```python
def test_fetch_release_assets_uses_plugin_name_field_for_remote_readme_url(monkeypatch):
    payloads = {
        "https://github.com/example/repo/releases/download/v1/latest": b"v1\n",
        "https://github.com/example/repo/releases/download/v1/plugins.json": json.dumps(
            {
                "plugins": [
                    {
                        "name": "display-name",
                        "pluginName": "repo-slug",
                        "pluginFile": "demo-plugin-1.0.0.zip",
                        "downloadUrl": "https://downloads.example/demo-plugin-1.0.0.zip",
                    }
                ]
            }
        ).encode("utf-8"),
        "https://github.com/example/repo/releases/download/v1/layout.yaml": b"layout: []\n",
        "https://github.com/example/repo/releases/download/v1/categories.json": b'{"categories": []}\n',
        "https://downloads.example/demo-plugin-1.0.0.zip": b"zip-bytes",
        "https://raw.githubusercontent.com/example/repo/main/plugins/repo-slug/README.md": b"# Demo\n",
    }
    requested = []

    def fake_download(url: str, timeout: float = 60.0) -> bytes:
        requested.append(url)
        return payloads[url]

    monkeypatch.setattr("scripts.ztools_offline_market.download_bytes", fake_download)

    fetch_release_assets(tag="v1", repo="example/repo")

    assert requested[-1] == "https://raw.githubusercontent.com/example/repo/main/plugins/repo-slug/README.md"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest C:/Users/Mion/Desktop/1/tests/test_pull.py::test_fetch_release_assets_uses_plugin_name_field_for_remote_readme_url -q`
Expected: FAIL because the implementation still prefers `name` and requests the wrong README path.

- [ ] **Step 3: Write minimal implementation**

```python
plugin_name = str(plugin.get("pluginName") or plugin.get("name") or "").strip()
```

Apply that precedence consistently anywhere the remote README source path should match ZTools client expectations.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest C:/Users/Mion/Desktop/1/tests/test_pull.py::test_fetch_release_assets_uses_plugin_name_field_for_remote_readme_url -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_pull.py scripts/ztools_offline_market.py
git commit -m "fix: align readme source paths with client metadata"
```

### Task 2: Rewrite all exposed metadata URLs to offline-local addresses

**Files:**
- Modify: `scripts/ztools_offline_market.py`
- Test: `tests/test_pull.py`
- Test: `tests/test_build.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_build_market_directory_rewrites_source_release_manifest_urls(tmp_path: Path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "market-data"
    input_dir.mkdir()
    (input_dir / "latest").write_text("v1\n", encoding="utf-8")
    (input_dir / "plugins.json").write_text(
        json.dumps({
            "plugins": [{
                "pluginName": "demo-plugin",
                "pluginFile": "demo-plugin-1.0.0.zip",
                "downloadUrl": "https://downloads.example/demo-plugin-1.0.0.zip",
                "readme": "https://raw.githubusercontent.com/example/repo/main/plugins/demo-plugin/README.md",
            }]
        }),
        encoding="utf-8",
    )
    (input_dir / "layout.yaml").write_text("layout: []\n", encoding="utf-8")
    (input_dir / "categories.json").write_text('{"categories": []}\n', encoding="utf-8")
    (input_dir / "plugins").mkdir()
    (input_dir / "plugins" / "demo-plugin-1.0.0.zip").write_bytes(b"zip")
    (input_dir / "source-release.json").write_text(
        json.dumps({"assets": [
            {"name": "plugins/demo-plugin-1.0.0.zip", "url": "https://downloads.example/demo-plugin-1.0.0.zip"},
            {"name": "raw/demo-plugin/README.md", "url": "https://raw.githubusercontent.com/example/repo/main/plugins/demo-plugin/README.md"},
        ]}),
        encoding="utf-8",
    )

    build_market_directory(
        input_dir=input_dir,
        output_dir=output_dir,
        base_url="http://intranet/ztools-market",
        tag="v1",
        readme_mode="mirror",
    )

    manifest = json.loads((output_dir / "manifests" / "source-release.json").read_text(encoding="utf-8"))
    assert manifest["assets"] == [
        {"name": "plugins/demo-plugin-1.0.0.zip", "url": "http://intranet/ztools-market/releases/download/v1/demo-plugin-1.0.0.zip"},
        {"name": "raw/demo-plugin/README.md", "url": "http://intranet/ztools-market/raw/demo-plugin/README.md"},
    ]
```

```python
def test_build_market_directory_rewrites_category_image_urls(tmp_path: Path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "market-data"
    input_dir.mkdir()
    (input_dir / "latest").write_text("v1\n", encoding="utf-8")
    (input_dir / "plugins.json").write_text('{"plugins": []}\n', encoding="utf-8")
    (input_dir / "layout.yaml").write_text("layout: []\n", encoding="utf-8")
    (input_dir / "categories.json").write_text(
        json.dumps({
            "categories": [{"key": "demo", "icon": "https://cdn.example/icons/demo.png"}]
        }),
        encoding="utf-8",
    )
    (input_dir / "source-release.json").write_text('{"assets": []}\n', encoding="utf-8")

    def fake_download(url: str, timeout: float = 60.0) -> bytes:
        if url == "https://cdn.example/icons/demo.png":
            return b"png"
        raise AssertionError(url)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("scripts.ztools_offline_market.download_bytes", fake_download)
    try:
        build_market_directory(
            input_dir=input_dir,
            output_dir=output_dir,
            base_url="http://intranet/ztools-market",
            tag="v1",
            readme_mode="mirror",
        )
    finally:
        monkeypatch.undo()

    categories = json.loads((output_dir / "categories.json").read_text(encoding="utf-8"))
    assert categories["categories"][0]["icon"] == "http://intranet/ztools-market/market-assets/categories/demo.png"
    assert (output_dir / "market-assets" / "categories" / "demo.png").read_bytes() == b"png"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest C:/Users/Mion/Desktop/1/tests/test_build.py -k "source_release_manifest_urls or category_image_urls" -q`
Expected: FAIL because only `plugins.json` is rewritten today.

- [ ] **Step 3: Write minimal implementation**

Add helpers in `scripts/ztools_offline_market.py` to:

```python
def rewrite_source_manifest_urls(*, source_manifest: Mapping[str, Any], base_url: str, tag: str) -> dict[str, Any]:
    ...

def mirror_json_image_urls(*, payload: Any, output_dir: Path, base_url: str, asset_prefix: str, timeout: float) -> Any:
    ...
```

Use them so that build output rewrites:
- plugin archives → `/releases/download/<tag>/<file>`
- mirrored readmes → `/raw/<plugin>/README.md`
- mirrored JSON image assets → `/market-assets/categories/<file>` (or stable deduplicated file name)
- manifest asset URLs → matching offline-local URLs when the asset is present in the final tree

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest C:/Users/Mion/Desktop/1/tests/test_build.py -k "source_release_manifest_urls or category_image_urls" -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_build.py scripts/ztools_offline_market.py
git commit -m "feat: rewrite exposed market metadata to offline urls"
```

### Task 3: Clear output and work directories before package generation

**Files:**
- Modify: `scripts/ztools_offline_market.py`
- Test: `tests/test_build.py`

- [ ] **Step 1: Write the failing test**

```python
def test_main_package_command_clears_existing_output_and_work_dirs(tmp_path: Path, monkeypatch):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    output_dir = cwd / "market-data"
    work_dir = cwd / "build" / "package-source-v1"
    output_dir.mkdir(parents=True)
    work_dir.mkdir(parents=True)
    (output_dir / "stale.txt").write_text("stale", encoding="utf-8")
    (work_dir / "stale.txt").write_text("stale", encoding="utf-8")

    monkeypatch.setattr("scripts.ztools_offline_market.resolve_latest_release_tag", lambda **_: "v1")
    monkeypatch.setattr("scripts.ztools_offline_market.fetch_release_assets", lambda **_: [])

    def fake_pull_release_assets(*, assets, output_dir: Path) -> None:
        assert not (output_dir / "stale.txt").exists()
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, content in {
            "latest": "v1\n",
            "plugins.json": '{"plugins": []}\n',
            "layout.yaml": "layout: []\n",
            "categories.json": '{"categories": []}\n',
            "source-release.json": '{"assets": []}\n',
        }.items():
            (output_dir / name).write_text(content, encoding="utf-8")

    def fake_build_market_directory(*, input_dir: Path, output_dir: Path, **kwargs) -> None:
        assert not (output_dir / "stale.txt").exists()
        output_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("scripts.ztools_offline_market.pull_release_assets", fake_pull_release_assets)
    monkeypatch.setattr("scripts.ztools_offline_market.build_market_directory", fake_build_market_directory)
    monkeypatch.setattr("scripts.ztools_offline_market.verify_market_directory", lambda path: {"ok": True, "errors": []})

    assert main(["package", "--base-url", "http://intranet/ztools-market"]) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest C:/Users/Mion/Desktop/1/tests/test_build.py::test_main_package_command_clears_existing_output_and_work_dirs -q`
Expected: FAIL because stale files still exist.

- [ ] **Step 3: Write minimal implementation**

Add a helper like:

```python
def reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
```

Call it from the `package` branch before `pull_release_assets(...)` and before `build_market_directory(...)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest C:/Users/Mion/Desktop/1/tests/test_build.py::test_main_package_command_clears_existing_output_and_work_dirs -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_build.py scripts/ztools_offline_market.py
git commit -m "fix: clear stale package directories before rebuild"
```

### Task 4: Cover README and category fallback behavior without breaking packaging

**Files:**
- Modify: `scripts/ztools_offline_market.py`
- Test: `tests/test_pull.py`
- Test: `tests/test_build.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_build_market_directory_keeps_original_category_image_url_when_download_fails(tmp_path: Path, monkeypatch):
    ...
```

```python
def test_build_market_directory_rewrites_manifest_urls_only_for_mirrored_assets(tmp_path: Path):
    ...
```

The first test should verify that failed category image downloads leave the original URL untouched. The second should verify that manifest entries without a local mirrored target retain their original source URL instead of being rewritten to a broken local path.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest C:/Users/Mion/Desktop/1/tests/test_build.py -k "category_image_url_when_download_fails or manifest_urls_only_for_mirrored_assets" -q`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Ensure the new URL rewrite helpers only rewrite URLs when a concrete local file exists or was successfully mirrored. Keep the current graceful-fallback behavior for failed downloads.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest C:/Users/Mion/Desktop/1/tests/test_build.py -k "category_image_url_when_download_fails or manifest_urls_only_for_mirrored_assets" -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_build.py scripts/ztools_offline_market.py
git commit -m "test: preserve external urls when offline mirroring fails"
```

### Task 5: Update user-facing docs and run full verification

**Files:**
- Modify: `README.md`
- Modify: `docs/operations.md`
- Test: `tests/test_build.py`
- Test: `tests/test_pull.py`
- Test: `tests/test_verify.py`

- [ ] **Step 1: Update README behavior description**

Add concise text stating that `package`:
- clears stale output before rebuilding
- rewrites plugin/readme/category/source-manifest URLs to local offline paths where possible
- preserves original external URLs only when a specific resource cannot be mirrored

- [ ] **Step 2: Update operations guide**

Document the same behavior in `docs/operations.md` and mention category-image mirroring.

- [ ] **Step 3: Run targeted tests**

Run: `python -m pytest C:/Users/Mion/Desktop/1/tests/test_pull.py C:/Users/Mion/Desktop/1/tests/test_build.py C:/Users/Mion/Desktop/1/tests/test_verify.py -q`
Expected: PASS

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest C:/Users/Mion/Desktop/1/tests -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add README.md docs/operations.md tests/test_pull.py tests/test_build.py tests/test_verify.py scripts/ztools_offline_market.py
git commit -m "docs: describe fully offline market packaging"
```
