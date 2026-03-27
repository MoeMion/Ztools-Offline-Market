import json
import shutil
from pathlib import Path

import pytest

from scripts.ztools_offline_market import (
    build_market_directory,
    build_parser,
    main,
    mirror_readmes,
)


FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "sample_release"


def test_mirror_readmes_writes_plugin_readme_files(tmp_path: Path):
    mirror_readmes(
        readmes={"demo-plugin": "# Demo Plugin\n\nOffline README\n"},
        output_dir=tmp_path,
    )

    assert (
        tmp_path / "raw" / "demo-plugin" / "README.md"
    ).read_text(encoding="utf-8") == "# Demo Plugin\n\nOffline README\n"


def test_build_parser_exposes_pull_build_verify_commands():
    parser = build_parser()

    assert parser.parse_args(["pull", "--tag", "v2099.01.01.0000", "--output", "out"]).command == "pull"
    assert parser.parse_args(
        [
            "build",
            "--input",
            "in",
            "--base-url",
            "http://intranet/ztools-market",
            "--output",
            "out",
            "--tag",
            "v2099.01.01.0000",
        ]
    ).command == "build"
    assert parser.parse_args(["verify", "--market", "market-data"]).command == "verify"


def test_build_parser_requires_build_arguments():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["build"])


def test_build_market_directory_creates_latest_and_versioned_layout(tmp_path: Path):
    output_dir = tmp_path / "market-data"

    build_market_directory(
        input_dir=FIXTURES_DIR,
        output_dir=output_dir,
        base_url="http://intranet/ztools-market/",
        tag="v2099.01.01.0000",
        readme_mode="skip",
    )

    latest_file = output_dir / "releases" / "latest" / "download" / "latest"
    versioned_zip = output_dir / "releases" / "download" / "v2099.01.01.0000" / "demo-plugin-1.0.0.zip"

    assert latest_file.read_text(encoding="utf-8").strip() == "v2099.01.01.0000"
    assert versioned_zip.exists()

    plugins = json.loads((output_dir / "releases" / "latest" / "download" / "plugins.json").read_text(encoding="utf-8"))
    assert plugins["plugins"][0]["url"] == "http://intranet/ztools-market/releases/download/v2099.01.01.0000/demo-plugin-1.0.0.zip"

    build_info = json.loads((output_dir / "manifests" / "build-info.json").read_text(encoding="utf-8"))
    assert build_info["pluginCount"] == 1
    assert build_info["tag"] == "v2099.01.01.0000"
    sha_lines = (output_dir / "manifests" / "files.sha256").read_text(encoding="utf-8").splitlines()
    assert any(line.endswith("releases/latest/download/plugins.json") for line in sha_lines)


def test_build_market_directory_mirrors_readmes(tmp_path: Path):
    output_dir = tmp_path / "market-data"
    input_dir = tmp_path / "input"
    shutil.copytree(FIXTURES_DIR, input_dir)
    readme_dir = input_dir / "raw" / "demo-plugin" / "assets"
    readme_dir.mkdir(parents=True)
    (input_dir / "raw" / "demo-plugin" / "README.md").write_text(
        "![cover](assets/cover.png)\n",
        encoding="utf-8",
    )
    (readme_dir / "cover.png").write_bytes(b"png-bytes")

    build_market_directory(
        input_dir=input_dir,
        output_dir=output_dir,
        base_url="http://intranet/ztools-market",
        tag="v2099.01.01.0000",
        readme_mode="mirror",
    )

    assert (
        output_dir / "raw" / "demo-plugin" / "README.md"
    ).read_text(encoding="utf-8") == "![cover](assets/cover.png)\n"
    assert (output_dir / "raw" / "demo-plugin" / "assets" / "cover.png").read_bytes() == b"png-bytes"

    plugins = json.loads((output_dir / "releases" / "latest" / "download" / "plugins.json").read_text(encoding="utf-8"))
    assert plugins["plugins"][0]["readme"] == "http://intranet/ztools-market/raw/demo-plugin/README.md"


def test_main_build_command_runs_end_to_end(tmp_path: Path, capsys):
    output_dir = tmp_path / "market-data"

    exit_code = main(
        [
            "build",
            "--input",
            str(FIXTURES_DIR),
            "--base-url",
            "http://intranet/ztools-market",
            "--output",
            str(output_dir),
            "--tag",
            "v2099.01.01.0000",
            "--readme-mode",
            "skip",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "BUILD OK" in captured.out
    assert (output_dir / "manifests" / "build-info.json").exists()


def test_build_parser_exposes_package_command_with_defaults():
    parser = build_parser()

    args = parser.parse_args([
        "package",
        "--base-url",
        "http://intranet/ztools-market",
    ])

    assert args.command == "package"
    assert args.base_url == "http://intranet/ztools-market"
    assert args.tag is None
    assert args.output == "market-data"


def test_main_package_command_uses_latest_tag_and_default_output(tmp_path: Path, monkeypatch, capsys):
    requested: dict[str, object] = {}
    output_dir = tmp_path / "cwd"
    output_dir.mkdir()
    monkeypatch.chdir(output_dir)

    def fake_resolve_latest_tag(*, repo: str, timeout: float) -> str:
        requested["repo"] = repo
        requested["timeout"] = timeout
        return "v2099.01.01.0000"

    def fake_fetch_release_assets(*, tag: str, repo: str, timeout: float):
        requested["fetch"] = {"tag": tag, "repo": repo, "timeout": timeout}
        return [{"name": "latest", "url": "https://example.invalid/latest", "bytes": b"v2099.01.01.0000\n"}]

    def fake_pull_release_assets(*, assets, output_dir: Path) -> None:
        requested["pull_output"] = output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, content in {
            "latest": "v2099.01.01.0000\n",
            "plugins.json": '{"plugins": []}\n',
            "layout.yaml": "layout: []\n",
            "categories.json": '{"categories": []}\n',
        }.items():
            (output_dir / name).write_text(content, encoding="utf-8")

    def fake_build_market_directory(*, input_dir: Path, output_dir: Path, base_url: str, tag: str, readme_mode: str, source_repo: str) -> None:
        requested["build"] = {
            "input_dir": input_dir,
            "output_dir": output_dir,
            "base_url": base_url,
            "tag": tag,
            "readme_mode": readme_mode,
            "source_repo": source_repo,
        }
        output_dir.mkdir(parents=True, exist_ok=True)

    def fake_verify_market_directory(path: Path) -> dict[str, object]:
        requested["verify"] = path
        return {"ok": True, "errors": []}

    monkeypatch.setattr("scripts.ztools_offline_market.resolve_latest_release_tag", fake_resolve_latest_tag)
    monkeypatch.setattr("scripts.ztools_offline_market.fetch_release_assets", fake_fetch_release_assets)
    monkeypatch.setattr("scripts.ztools_offline_market.pull_release_assets", fake_pull_release_assets)
    monkeypatch.setattr("scripts.ztools_offline_market.build_market_directory", fake_build_market_directory)
    monkeypatch.setattr("scripts.ztools_offline_market.verify_market_directory", fake_verify_market_directory)

    exit_code = main([
        "package",
        "--base-url",
        "http://intranet/ztools-market",
    ])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PACKAGE OK" in captured.out
    assert requested["fetch"] == {"tag": "v2099.01.01.0000", "repo": "ZToolsCenter/ZTools-plugins", "timeout": 60.0}
    assert requested["build"]["output_dir"] == Path("market-data")
    assert requested["verify"] == Path("market-data")


def test_resolve_latest_release_tag_reads_redirect_target(monkeypatch):
    class FakeResponse:
        def __init__(self, url: str):
            self.url = url

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(url: str, timeout: float = 60.0):
        assert url == "https://github.com/example/repo/releases/latest"
        return FakeResponse("https://github.com/example/repo/releases/tag/v2099.01.01.0000")

    monkeypatch.setattr("scripts.ztools_offline_market.urlopen", fake_urlopen)

    from scripts.ztools_offline_market import resolve_latest_release_tag

    assert resolve_latest_release_tag(repo="example/repo") == "v2099.01.01.0000"


def test_build_market_directory_rewrites_source_release_manifest_urls(tmp_path: Path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "market-data"
    input_dir.mkdir()
    (input_dir / "latest").write_text("v1\n", encoding="utf-8")
    (input_dir / "plugins.json").write_text(
        json.dumps(
            {
                "plugins": [
                    {
                        "pluginName": "demo-plugin",
                        "pluginFile": "demo-plugin-1.0.0.zip",
                        "downloadUrl": "https://downloads.example/demo-plugin-1.0.0.zip",
                        "readme": "https://raw.githubusercontent.com/example/repo/main/plugins/demo-plugin/README.md",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (input_dir / "layout.yaml").write_text("layout: []\n", encoding="utf-8")
    (input_dir / "categories.json").write_text('{"categories": []}\n', encoding="utf-8")
    (input_dir / "plugins").mkdir()
    (input_dir / "plugins" / "demo-plugin-1.0.0.zip").write_bytes(b"zip")
    (input_dir / "raw" / "demo-plugin").mkdir(parents=True)
    (input_dir / "raw" / "demo-plugin" / "README.md").write_text("# Demo\n", encoding="utf-8")
    (input_dir / "source-release.json").write_text(
        json.dumps(
            {
                "assets": [
                    {"name": "plugins/demo-plugin-1.0.0.zip", "url": "https://downloads.example/demo-plugin-1.0.0.zip"},
                    {
                        "name": "raw/demo-plugin/README.md",
                        "url": "https://raw.githubusercontent.com/example/repo/main/plugins/demo-plugin/README.md",
                    },
                ]
            }
        ),
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


def test_build_market_directory_rewrites_category_image_urls(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "market-data"
    input_dir.mkdir()
    (input_dir / "latest").write_text("v1\n", encoding="utf-8")
    (input_dir / "plugins.json").write_text('{"plugins": []}\n', encoding="utf-8")
    (input_dir / "layout.yaml").write_text("layout: []\n", encoding="utf-8")
    (input_dir / "categories.json").write_text(
        json.dumps({"categories": [{"key": "demo", "icon": "https://cdn.example/icons/demo.png"}]}),
        encoding="utf-8",
    )
    (input_dir / "source-release.json").write_text('{"assets": []}\n', encoding="utf-8")

    def fake_download(url: str, timeout: float = 60.0) -> bytes:
        if url == "https://cdn.example/icons/demo.png":
            return b"png"
        raise AssertionError(url)

    monkeypatch.setattr("scripts.ztools_offline_market.download_bytes", fake_download)

    build_market_directory(
        input_dir=input_dir,
        output_dir=output_dir,
        base_url="http://intranet/ztools-market",
        tag="v1",
        readme_mode="mirror",
    )

    categories = json.loads((output_dir / "categories.json").read_text(encoding="utf-8"))
    assert categories["categories"][0]["icon"] == "http://intranet/ztools-market/market-assets/categories/demo.png"
    assert (output_dir / "market-assets" / "categories" / "demo.png").read_bytes() == b"png"


def test_build_market_directory_keeps_original_category_image_url_when_download_fails(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "market-data"
    input_dir.mkdir()
    (input_dir / "latest").write_text("v1\n", encoding="utf-8")
    (input_dir / "plugins.json").write_text('{"plugins": []}\n', encoding="utf-8")
    (input_dir / "layout.yaml").write_text("layout: []\n", encoding="utf-8")
    original_url = "https://cdn.example/icons/demo.png"
    (input_dir / "categories.json").write_text(
        json.dumps({"categories": [{"key": "demo", "icon": original_url}]}),
        encoding="utf-8",
    )
    (input_dir / "source-release.json").write_text('{"assets": []}\n', encoding="utf-8")

    def fake_download(url: str, timeout: float = 60.0) -> bytes:
        raise OSError("403 Forbidden")

    monkeypatch.setattr("scripts.ztools_offline_market.download_bytes", fake_download)

    build_market_directory(
        input_dir=input_dir,
        output_dir=output_dir,
        base_url="http://intranet/ztools-market",
        tag="v1",
        readme_mode="mirror",
    )

    categories = json.loads((output_dir / "categories.json").read_text(encoding="utf-8"))
    assert categories["categories"][0]["icon"] == original_url


def test_build_market_directory_rewrites_manifest_urls_only_for_mirrored_assets(tmp_path: Path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "market-data"
    input_dir.mkdir()
    (input_dir / "latest").write_text("v1\n", encoding="utf-8")
    (input_dir / "plugins.json").write_text('{"plugins": []}\n', encoding="utf-8")
    (input_dir / "layout.yaml").write_text("layout: []\n", encoding="utf-8")
    (input_dir / "categories.json").write_text('{"categories": []}\n', encoding="utf-8")
    (input_dir / "source-release.json").write_text(
        json.dumps(
            {
                "assets": [
                    {"name": "plugins/missing.zip", "url": "https://downloads.example/missing.zip"},
                    {"name": "raw/missing/README.md", "url": "https://raw.githubusercontent.com/example/repo/main/plugins/missing/README.md"},
                ]
            }
        ),
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
        {"name": "plugins/missing.zip", "url": "https://downloads.example/missing.zip"},
        {"name": "raw/missing/README.md", "url": "https://raw.githubusercontent.com/example/repo/main/plugins/missing/README.md"},
    ]


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

    def fake_build_market_directory(*, input_dir: Path, output_dir: Path, base_url: str, tag: str, readme_mode: str, source_repo: str) -> None:
        assert not (output_dir / "stale.txt").exists()
        output_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("scripts.ztools_offline_market.pull_release_assets", fake_pull_release_assets)
    monkeypatch.setattr("scripts.ztools_offline_market.build_market_directory", fake_build_market_directory)
    monkeypatch.setattr("scripts.ztools_offline_market.verify_market_directory", lambda path: {"ok": True, "errors": []})

    assert main(["package", "--base-url", "http://intranet/ztools-market"]) == 0
