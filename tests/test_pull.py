import json
from pathlib import Path

from scripts.ztools_offline_market import fetch_release_assets, pull_release_assets


def test_pull_release_assets_writes_release_manifest(tmp_path: Path):
    assets = [
        {
            "name": "plugins.json",
            "url": "https://example.invalid/plugins.json",
            "bytes": b'{"plugins": []}',
        },
        {
            "name": "latest",
            "url": "https://example.invalid/latest",
            "bytes": b"v2026.03.23.1338\n",
        },
    ]

    pull_release_assets(assets=assets, output_dir=tmp_path)

    manifest = json.loads((tmp_path / "source-release.json").read_text(encoding="utf-8"))
    assert manifest["assets"][0]["name"] == "plugins.json"
    assert (tmp_path / "plugins.json").read_text(encoding="utf-8") == '{"plugins": []}'


def test_fetch_release_assets_downloads_required_metadata_and_plugin_archives(monkeypatch):
    payloads = {
        "https://github.com/example/repo/releases/download/v1/latest": b"v1\n",
        "https://github.com/example/repo/releases/download/v1/plugins.json": json.dumps(
            {
                "plugins": [
                    {
                        "pluginName": "demo-plugin",
                        "pluginFile": "demo-plugin-1.0.0.zip",
                        "url": "https://downloads.example/demo-plugin-1.0.0.zip",
                    }
                ]
            }
        ).encode("utf-8"),
        "https://github.com/example/repo/releases/download/v1/layout.yaml": b"layout: []\n",
        "https://github.com/example/repo/releases/download/v1/categories.json": b'{"categories": []}\n',
        "https://downloads.example/demo-plugin-1.0.0.zip": b"zip-bytes",
        "https://raw.githubusercontent.com/example/repo/main/plugins/demo-plugin/README.md": b"# Demo Plugin\n",
    }
    requested: list[str] = []

    def fake_download(url: str, timeout: float = 60.0) -> bytes:
        requested.append(url)
        return payloads[url]

    monkeypatch.setattr("scripts.ztools_offline_market.download_bytes", fake_download)

    assets = fetch_release_assets(tag="v1", repo="example/repo")

    assert [asset["name"] for asset in assets] == [
        "latest",
        "plugins.json",
        "layout.yaml",
        "categories.json",
        "plugins/demo-plugin-1.0.0.zip",
        "raw/demo-plugin/README.md",
    ]
    assert requested[-1] == "https://raw.githubusercontent.com/example/repo/main/plugins/demo-plugin/README.md"


def test_pull_release_assets_writes_downloaded_readmes(tmp_path: Path):
    assets = [
        {
            "name": "raw/demo-plugin/README.md",
            "url": "https://raw.githubusercontent.com/example/repo/main/plugins/demo-plugin/README.md",
            "bytes": b"# Demo Plugin\n",
        }
    ]

    pull_release_assets(assets=assets, output_dir=tmp_path)

    assert (tmp_path / "raw" / "demo-plugin" / "README.md").read_text(encoding="utf-8") == "# Demo Plugin\n"


def test_fetch_release_assets_uses_plugin_name_field_for_readme_paths(monkeypatch):
    payloads = {
        "https://github.com/example/repo/releases/download/v1/latest": b"v1\n",
        "https://github.com/example/repo/releases/download/v1/plugins.json": json.dumps(
            {
                "plugins": [
                    {
                        "name": "显示名",
                        "pluginName": "calculation-paper",
                        "pluginFile": "calculation-paper-1.0.0.zip",
                        "url": "https://downloads.example/calculation-paper-1.0.0.zip",
                    }
                ]
            }
        ).encode("utf-8"),
        "https://github.com/example/repo/releases/download/v1/layout.yaml": b"layout: []\n",
        "https://github.com/example/repo/releases/download/v1/categories.json": b'{"categories": []}\n',
        "https://downloads.example/calculation-paper-1.0.0.zip": b"zip-bytes",
        "https://raw.githubusercontent.com/example/repo/main/plugins/calculation-paper/README.md": b"# Calculation Paper\n",
    }
    requested: list[str] = []

    def fake_download(url: str, timeout: float = 60.0) -> bytes:
        requested.append(url)
        return payloads[url]

    monkeypatch.setattr("scripts.ztools_offline_market.download_bytes", fake_download)

    assets = fetch_release_assets(tag="v1", repo="example/repo")

    assert requested[-1] == "https://raw.githubusercontent.com/example/repo/main/plugins/calculation-paper/README.md"
    assert assets[-1]["name"] == "raw/calculation-paper/README.md"


def test_fetch_release_assets_downloads_readme_images_and_rewrites_links(monkeypatch):
    payloads = {
        "https://github.com/example/repo/releases/download/v1/latest": b"v1\n",
        "https://github.com/example/repo/releases/download/v1/plugins.json": json.dumps(
            {
                "plugins": [
                    {
                        "name": "demo-plugin",
                        "pluginFile": "demo-plugin-1.0.0.zip",
                        "url": "https://downloads.example/demo-plugin-1.0.0.zip",
                    }
                ]
            }
        ).encode("utf-8"),
        "https://github.com/example/repo/releases/download/v1/layout.yaml": b"layout: []\n",
        "https://github.com/example/repo/releases/download/v1/categories.json": b'{"categories": []}\n',
        "https://downloads.example/demo-plugin-1.0.0.zip": b"zip-bytes",
        "https://raw.githubusercontent.com/example/repo/main/plugins/demo-plugin/README.md": b"![cover](https://cdn.example/assets/cover.png)\n",
        "https://cdn.example/assets/cover.png": b"png-bytes",
    }

    def fake_download(url: str, timeout: float = 60.0) -> bytes:
        return payloads[url]

    monkeypatch.setattr("scripts.ztools_offline_market.download_bytes", fake_download)

    assets = fetch_release_assets(tag="v1", repo="example/repo")

    assert assets[-2]["name"] == "raw/demo-plugin/README.md"
    assert assets[-2]["bytes"] == b"![cover](assets/cover.png)\n"
    assert assets[-1]["name"] == "raw/demo-plugin/assets/cover.png"
    assert assets[-1]["url"] == "https://cdn.example/assets/cover.png"
    assert assets[-1]["bytes"] == b"png-bytes"


def test_fetch_release_assets_keeps_original_image_url_when_asset_download_fails(monkeypatch):
    payloads = {
        "https://github.com/example/repo/releases/download/v1/latest": b"v1\n",
        "https://github.com/example/repo/releases/download/v1/plugins.json": json.dumps(
            {
                "plugins": [
                    {
                        "name": "demo-plugin",
                        "pluginFile": "demo-plugin-1.0.0.zip",
                        "url": "https://downloads.example/demo-plugin-1.0.0.zip",
                    }
                ]
            }
        ).encode("utf-8"),
        "https://github.com/example/repo/releases/download/v1/layout.yaml": b"layout: []\n",
        "https://github.com/example/repo/releases/download/v1/categories.json": b'{"categories": []}\n',
        "https://downloads.example/demo-plugin-1.0.0.zip": b"zip-bytes",
        "https://raw.githubusercontent.com/example/repo/main/plugins/demo-plugin/README.md": b"![cover](https://cdn.example/assets/cover.png)\n",
    }

    def fake_download(url: str, timeout: float = 60.0) -> bytes:
        if url == "https://cdn.example/assets/cover.png":
            raise OSError("403 Forbidden")
        return payloads[url]

    monkeypatch.setattr("scripts.ztools_offline_market.download_bytes", fake_download)

    assets = fetch_release_assets(tag="v1", repo="example/repo")

    assert assets[-1]["name"] == "raw/demo-plugin/README.md"
    assert assets[-1]["bytes"] == b"![cover](https://cdn.example/assets/cover.png)\n"


def test_fetch_release_assets_keeps_original_image_url_when_asset_url_is_not_ascii(monkeypatch):
    payloads = {
        "https://github.com/example/repo/releases/download/v1/latest": b"v1\n",
        "https://github.com/example/repo/releases/download/v1/plugins.json": json.dumps(
            {
                "plugins": [
                    {
                        "name": "demo-plugin",
                        "pluginFile": "demo-plugin-1.0.0.zip",
                        "url": "https://downloads.example/demo-plugin-1.0.0.zip",
                    }
                ]
            }
        ).encode("utf-8"),
        "https://github.com/example/repo/releases/download/v1/layout.yaml": b"layout: []\n",
        "https://github.com/example/repo/releases/download/v1/categories.json": b'{"categories": []}\n',
        "https://downloads.example/demo-plugin-1.0.0.zip": b"zip-bytes",
        "https://raw.githubusercontent.com/example/repo/main/plugins/demo-plugin/README.md": "![cover](https://cdn.example/assets/截图.png)\n".encode("utf-8"),
    }

    def fake_download(url: str, timeout: float = 60.0) -> bytes:
        if url == "https://cdn.example/assets/截图.png":
            raise UnicodeEncodeError("ascii", "截图", 0, 2, "ordinal not in range")
        return payloads[url]

    monkeypatch.setattr("scripts.ztools_offline_market.download_bytes", fake_download)

    assets = fetch_release_assets(tag="v1", repo="example/repo")

    assert assets[-1]["name"] == "raw/demo-plugin/README.md"
    assert assets[-1]["bytes"] == "![cover](https://cdn.example/assets/截图.png)\n".encode("utf-8")


def test_fetch_release_assets_urlencodes_non_ascii_readme_paths(monkeypatch):
    payloads = {
        "https://github.com/example/repo/releases/download/v1/latest": b"v1\n",
        "https://github.com/example/repo/releases/download/v1/plugins.json": json.dumps(
            {
                "plugins": [
                    {
                        "name": "插件演示",
                        "pluginFile": "demo-plugin-1.0.0.zip",
                        "url": "https://downloads.example/demo-plugin-1.0.0.zip",
                    }
                ]
            }
        ).encode("utf-8"),
        "https://github.com/example/repo/releases/download/v1/layout.yaml": b"layout: []\n",
        "https://github.com/example/repo/releases/download/v1/categories.json": b'{"categories": []}\n',
        "https://downloads.example/demo-plugin-1.0.0.zip": b"zip-bytes",
        "https://raw.githubusercontent.com/example/repo/main/plugins/%E6%8F%92%E4%BB%B6%E6%BC%94%E7%A4%BA/README.md": b"# Demo\n",
    }
    requested: list[str] = []

    def fake_download(url: str, timeout: float = 60.0) -> bytes:
        requested.append(url)
        return payloads[url]

    monkeypatch.setattr("scripts.ztools_offline_market.download_bytes", fake_download)

    assets = fetch_release_assets(tag="v1", repo="example/repo")

    assert requested[-1] == "https://raw.githubusercontent.com/example/repo/main/plugins/%E6%8F%92%E4%BB%B6%E6%BC%94%E7%A4%BA/README.md"
    assert assets[-1]["name"] == "raw/插件演示/README.md"
    assert assets[-1]["bytes"] == b"# Demo\n"
