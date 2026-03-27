from pathlib import Path

from scripts.ztools_offline_market import verify_market_directory


REQUIRED_RELEASE_FILES = ("latest", "plugins.json", "layout.yaml", "categories.json")


def write_required_market_files(market_dir: Path) -> Path:
    latest_dir = market_dir / "releases" / "latest" / "download"
    latest_dir.mkdir(parents=True)
    (latest_dir / "latest").write_text("v2099.01.01.0000\n", encoding="utf-8")
    (latest_dir / "plugins.json").write_text(
        '{"plugins": [{"pluginName": "demo-plugin", "pluginFile": "demo-plugin-1.0.0.zip", "url": "http://intranet/ztools-market/releases/download/v2099.01.01.0000/demo-plugin-1.0.0.zip"}]}',
        encoding="utf-8",
    )
    (latest_dir / "layout.yaml").write_text("layout: []\n", encoding="utf-8")
    (latest_dir / "categories.json").write_text('{"categories": []}', encoding="utf-8")
    (latest_dir / "demo-plugin-1.0.0.zip").write_bytes(b"zip-data")

    for name in REQUIRED_RELEASE_FILES:
        (market_dir / name).write_bytes((latest_dir / name).read_bytes())

    return latest_dir


def write_version_dir(market_dir: Path) -> Path:
    version_dir = market_dir / "releases" / "download" / "v2099.01.01.0000"
    version_dir.mkdir(parents=True)
    for name in REQUIRED_RELEASE_FILES:
        source = market_dir / "releases" / "latest" / "download" / name
        (version_dir / name).write_bytes(source.read_bytes())
    (version_dir / "demo-plugin-1.0.0.zip").write_bytes(b"zip-data")
    return version_dir


def write_manifests(market_dir: Path) -> None:
    manifest_dir = market_dir / "manifests"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "build-info.json").write_text("{}", encoding="utf-8")
    (manifest_dir / "files.sha256").write_text("abc  releases/latest/download/latest\n", encoding="utf-8")


def test_verify_market_directory_reports_success_for_valid_tree(tmp_path: Path):
    market_dir = tmp_path / "market-data"
    latest_dir = write_required_market_files(market_dir)
    write_version_dir(market_dir)
    write_manifests(market_dir)

    result = verify_market_directory(market_dir)

    assert result["ok"] is True
    assert result["errors"] == []


def test_verify_market_directory_reports_missing_required_files(tmp_path: Path):
    market_dir = tmp_path / "market-data"
    latest_dir = market_dir / "releases" / "latest" / "download"
    latest_dir.mkdir(parents=True)

    result = verify_market_directory(market_dir)

    assert result["ok"] is False
    assert result["errors"] == [
        f"missing required file: {market_dir / 'latest'}",
        f"missing required file: {latest_dir / 'latest'}",
        f"missing required file: {market_dir / 'plugins.json'}",
        f"missing required file: {latest_dir / 'plugins.json'}",
        f"missing required file: {market_dir / 'layout.yaml'}",
        f"missing required file: {latest_dir / 'layout.yaml'}",
        f"missing required file: {market_dir / 'categories.json'}",
        f"missing required file: {latest_dir / 'categories.json'}",
        f"missing manifest file: {market_dir / 'manifests' / 'build-info.json'}",
        f"missing manifest file: {market_dir / 'manifests' / 'files.sha256'}",
    ]


def test_verify_market_directory_reports_malformed_plugins_json(tmp_path: Path):
    market_dir = tmp_path / "market-data"
    latest_dir = write_required_market_files(market_dir)
    write_version_dir(market_dir)
    write_manifests(market_dir)
    (latest_dir / "plugins.json").write_text('{"plugins": [}', encoding="utf-8")

    result = verify_market_directory(market_dir)

    assert result["ok"] is False
    assert len(result["errors"]) == 1
    assert result["errors"][0].startswith("malformed plugins.json:")


def test_verify_market_directory_reports_plugin_entry_without_archive_filename(tmp_path: Path):
    market_dir = tmp_path / "market-data"
    latest_dir = write_required_market_files(market_dir)
    write_version_dir(market_dir)
    write_manifests(market_dir)
    (latest_dir / "plugins.json").write_text(
        '{"plugins": [{"name": "demo-plugin", "url": ""}]}',
        encoding="utf-8",
    )

    result = verify_market_directory(market_dir)

    assert result["ok"] is False
    assert result["errors"] == [
        "plugin entry missing archive filename: expected pluginFile or url"
    ]


def test_verify_market_directory_reports_missing_version_archive(tmp_path: Path):
    market_dir = tmp_path / "market-data"
    latest_dir = write_required_market_files(market_dir)
    version_dir = write_version_dir(market_dir)
    write_manifests(market_dir)
    (version_dir / "demo-plugin-1.0.0.zip").unlink()

    result = verify_market_directory(market_dir)

    assert result["ok"] is False
    assert result["errors"] == [
        f"missing versioned plugin archive: {version_dir / 'demo-plugin-1.0.0.zip'}"
    ]
