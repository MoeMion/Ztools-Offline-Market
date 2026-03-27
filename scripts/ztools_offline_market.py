import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import quote, urlparse
from urllib.request import urlopen


DEFAULT_SOURCE_REPO = "ZToolsCenter/ZTools-plugins"
REQUIRED_RELEASE_FILES = ("latest", "plugins.json", "layout.yaml", "categories.json")


class MarketError(Exception):
    pass


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def github_release_asset_url(*, repo: str, tag: str, asset_name: str) -> str:
    return f"https://github.com/{repo}/releases/download/{tag}/{asset_name}"


def github_plugin_readme_url(*, repo: str, plugin_name: str) -> str:
    encoded_plugin_name = quote(plugin_name, safe="")
    return f"https://raw.githubusercontent.com/{repo}/main/plugins/{encoded_plugin_name}/README.md"


def resolve_latest_release_tag(*, repo: str = DEFAULT_SOURCE_REPO, timeout: float = 60.0) -> str:
    latest_url = f"https://github.com/{repo}/releases/latest"
    with urlopen(latest_url, timeout=timeout) as response:
        resolved_path = urlparse(response.url).path.rstrip("/")
    latest_tag = Path(resolved_path).name
    if not latest_tag:
        raise MarketError(f"unable to resolve latest release tag for {repo}")
    return latest_tag


def download_bytes(url: str, timeout: float = 60.0) -> bytes:
    with urlopen(url, timeout=timeout) as response:
        return response.read()


def mirror_readme_assets(*, plugin_name: str, readme_text: str, timeout: float) -> tuple[str, list[dict[str, Any]]]:
    asset_entries: list[dict[str, Any]] = []
    seen_urls: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        url = match.group(1)
        if not url.startswith(("http://", "https://")):
            return match.group(0)
        mirrored_path = seen_urls.get(url)
        if mirrored_path is None:
            file_name = Path(urlparse(url).path).name or f"asset-{len(seen_urls) + 1}"
            mirrored_path = f"assets/{file_name}"
            try:
                asset_bytes = download_bytes(url, timeout=timeout)
            except (OSError, UnicodeEncodeError):
                return match.group(0)
            seen_urls[url] = mirrored_path
            asset_entries.append(
                {
                    "name": f"raw/{plugin_name}/{mirrored_path}",
                    "url": url,
                    "bytes": asset_bytes,
                }
            )
        return match.group(0).replace(url, mirrored_path)

    rewritten = re.sub(r"!\[[^\]]*\]\((https?://[^)]+)\)", replace, readme_text)
    return rewritten, asset_entries


def reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def offline_url_for_asset(*, asset_name: str, base_url: str, tag: str) -> str | None:
    normalized_base_url = normalize_base_url(base_url)
    if asset_name.startswith("plugins/"):
        return f"{normalized_base_url}/releases/download/{tag}/{Path(asset_name).name}"
    if asset_name.startswith("raw/"):
        return f"{normalized_base_url}/{asset_name}"
    if asset_name.startswith("market-assets/"):
        return f"{normalized_base_url}/{asset_name}"
    if asset_name in REQUIRED_RELEASE_FILES:
        return f"{normalized_base_url}/{asset_name}"
    return None


def mirror_json_image_urls(*, json_path: Path, output_dir: Path, base_url: str, timeout: float) -> Any:
    payload = load_json(json_path)
    seen_urls: dict[str, str] = {}

    def rewrite(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: rewrite(item) for key, item in value.items()}
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        if not isinstance(value, str) or not value.startswith(("http://", "https://")):
            return value
        file_name = Path(urlparse(value).path).name
        if not file_name:
            return value
        local_name = seen_urls.get(value)
        if local_name is None:
            try:
                asset_bytes = download_bytes(value, timeout=timeout)
            except (OSError, UnicodeEncodeError):
                return value
            local_name = file_name
            seen_urls[value] = local_name
            target = output_dir / "market-assets" / "categories" / local_name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(asset_bytes)
        return f"{normalize_base_url(base_url)}/market-assets/categories/{local_name}"

    rewritten = rewrite(payload)
    if isinstance(rewritten, dict):
        dump_json(json_path, rewritten)
    else:
        json_path.write_text(json.dumps(rewritten, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rewritten


def rewrite_source_manifest_urls(*, source_manifest: Mapping[str, Any], output_dir: Path, base_url: str, tag: str) -> dict[str, Any]:
    rewritten_assets: list[dict[str, Any]] = []
    for asset in source_manifest.get("assets", []):
        if not isinstance(asset, Mapping):
            continue
        name = str(asset.get("name") or "")
        url = str(asset.get("url") or "")
        offline_url = offline_url_for_asset(asset_name=name, base_url=base_url, tag=tag)
        target_exists = False
        if name.startswith("plugins/"):
            target_exists = (output_dir / "releases" / "download" / tag / Path(name).name).exists()
        elif name.startswith("raw/") or name.startswith("market-assets/") or name in REQUIRED_RELEASE_FILES:
            target_exists = (output_dir / Path(name)).exists()
        if name and offline_url and target_exists:
            rewritten_assets.append({"name": name, "url": offline_url})
        else:
            rewritten_assets.append({"name": name, "url": url})
    return {"assets": rewritten_assets}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_plugins(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [plugin for plugin in payload if isinstance(plugin, dict)]
    if isinstance(payload, dict):
        plugins = payload.get("plugins", [])
        if isinstance(plugins, list):
            return [plugin for plugin in plugins if isinstance(plugin, dict)]
    raise MarketError("unsupported plugins.json structure")


def dump_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_plugin_file(plugin: Mapping[str, Any]) -> str:
    for key in ("pluginFile", "downloadUrl", "url"):
        value = plugin.get(key)
        if key == "pluginFile" and value:
            return str(value)
        if value:
            name = Path(urlparse(str(value)).path).name
            if name:
                return name
    name = str(plugin.get("name") or "").strip()
    version = str(plugin.get("version") or "").strip()
    if name and version:
        return f"{name}-{version}.zip"
    return ""


def fetch_release_assets(*, tag: str, repo: str = DEFAULT_SOURCE_REPO, timeout: float = 60.0) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []

    for name in REQUIRED_RELEASE_FILES:
        url = github_release_asset_url(repo=repo, tag=tag, asset_name=name)
        assets.append({"name": name, "url": url, "bytes": download_bytes(url, timeout=timeout)})

    plugins_payload = json.loads(assets[1]["bytes"].decode("utf-8"))
    seen_archives: set[str] = set()
    seen_readmes: set[str] = set()

    for plugin in iter_plugins(plugins_payload):
        plugin_file = resolve_plugin_file(plugin)
        if not plugin_file:
            raise MarketError("plugin entry missing archive filename while pulling release assets")
        if plugin_file not in seen_archives:
            seen_archives.add(plugin_file)
            plugin_url = str(
                plugin.get("downloadUrl")
                or plugin.get("url")
                or github_release_asset_url(repo=repo, tag=tag, asset_name=plugin_file)
            )
            assets.append(
                {
                    "name": f"plugins/{plugin_file}",
                    "url": plugin_url,
                    "bytes": download_bytes(plugin_url, timeout=timeout),
                }
            )

        plugin_name = str(plugin.get("pluginName") or plugin.get("name") or "").strip()
        if not plugin_name or plugin_name in seen_readmes:
            continue
        readme_url = github_plugin_readme_url(repo=repo, plugin_name=plugin_name)
        try:
            readme_bytes = download_bytes(readme_url, timeout=timeout)
        except (OSError, UnicodeEncodeError):
            continue
        seen_readmes.add(plugin_name)
        readme_text, readme_asset_entries = mirror_readme_assets(
            plugin_name=plugin_name,
            readme_text=readme_bytes.decode("utf-8"),
            timeout=timeout,
        )
        assets.append(
            {
                "name": f"raw/{plugin_name}/README.md",
                "url": readme_url,
                "bytes": readme_text.encode("utf-8"),
            }
        )
        assets.extend(readme_asset_entries)

    return assets


def pull_release_assets(*, assets: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_assets = []

    for asset in assets:
        target = output_dir / asset["name"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(asset["bytes"])
        manifest_assets.append({"name": asset["name"], "url": asset["url"]})

    dump_json(output_dir / "source-release.json", {"assets": manifest_assets})


def mirror_readmes(*, readmes: dict[str, str], output_dir: Path, input_dir: Path | None = None) -> None:
    for plugin_name, readme_text in readmes.items():
        target = output_dir / "raw" / plugin_name / "README.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(readme_text, encoding="utf-8")

        if input_dir is None:
            continue
        source_assets_dir = input_dir / "raw" / plugin_name / "assets"
        target_assets_dir = output_dir / "raw" / plugin_name / "assets"
        if source_assets_dir.exists():
            shutil.copytree(source_assets_dir, target_assets_dir, dirs_exist_ok=True)


def collect_readmes_from_input(input_dir: Path) -> dict[str, str]:
    readmes: dict[str, str] = {}
    raw_dir = input_dir / "raw"
    if not raw_dir.exists():
        return readmes

    for readme_path in raw_dir.glob("*/README.md"):
        readmes[readme_path.parent.name] = readme_path.read_text(encoding="utf-8")
    return readmes


def rewrite_plugin_urls(*, plugins_json_path: Path, base_url: str, tag: str, readme_mode: str) -> Any:
    payload = load_json(plugins_json_path)
    normalized_base_url = normalize_base_url(base_url)

    for plugin in iter_plugins(payload):
        plugin_file = resolve_plugin_file(plugin)
        if plugin_file:
            rewritten_url = f"{normalized_base_url}/releases/download/{tag}/{plugin_file}"
            plugin["pluginFile"] = plugin_file
            plugin["url"] = rewritten_url
            plugin["downloadUrl"] = rewritten_url

        if readme_mode == "mirror":
            plugin_name = str(plugin.get("pluginName") or plugin.get("name") or "").strip()
            if plugin_name:
                plugin["readme"] = f"{normalized_base_url}/raw/{plugin_name}/README.md"

    if isinstance(payload, dict):
        dump_json(plugins_json_path, payload)
    else:
        plugins_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def load_source_manifest(input_dir: Path) -> dict[str, Any]:
    manifest_path = input_dir / "source-release.json"
    if manifest_path.exists():
        return load_json(manifest_path)
    return {"assets": []}


def write_manifests(
    *,
    output_dir: Path,
    source_repo: str,
    tag: str,
    base_url: str,
    plugin_count: int,
    source_manifest: Mapping[str, Any] | None = None,
) -> None:
    manifest_dir = output_dir / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    build_info = {
        "sourceRepo": source_repo,
        "tag": tag,
        "baseUrl": normalize_base_url(base_url),
        "pluginCount": plugin_count,
    }
    dump_json(manifest_dir / "build-info.json", build_info)

    if source_manifest is not None:
        dump_json(
            manifest_dir / "source-release.json",
            rewrite_source_manifest_urls(
                source_manifest=source_manifest,
                output_dir=output_dir,
                base_url=base_url,
                tag=tag,
            ),
        )

    lines: list[str] = []
    for file_path in sorted(p for p in output_dir.rglob("*") if p.is_file() and manifest_dir not in p.parents):
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        relative = file_path.relative_to(output_dir).as_posix()
        lines.append(f"{digest}  {relative}")
    (manifest_dir / "files.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_input_files(input_dir: Path) -> None:
    missing = [name for name in REQUIRED_RELEASE_FILES if not (input_dir / name).exists()]
    if missing:
        raise MarketError(f"missing input files: {', '.join(missing)}")


def build_market_directory(
    *,
    input_dir: Path,
    output_dir: Path,
    base_url: str,
    tag: str,
    readme_mode: str,
    collected_readmes: Mapping[str, str] | dict[str, str] | None = None,
    source_repo: str = DEFAULT_SOURCE_REPO,
) -> None:
    ensure_input_files(input_dir)
    normalized_base_url = normalize_base_url(base_url)

    reset_directory(output_dir)

    root_dir = output_dir
    latest_dir = output_dir / "releases" / "latest" / "download"
    version_dir = output_dir / "releases" / "download" / tag
    latest_dir.mkdir(parents=True, exist_ok=True)
    version_dir.mkdir(parents=True, exist_ok=True)

    latest_marker_text = (input_dir / "latest").read_text(encoding="utf-8").strip()

    for name in REQUIRED_RELEASE_FILES:
        source = input_dir / name
        shutil.copy2(source, root_dir / name)
        shutil.copy2(source, latest_dir / name)
        shutil.copy2(source, version_dir / name)

    mirror_json_image_urls(
        json_path=root_dir / "categories.json",
        output_dir=output_dir,
        base_url=normalized_base_url,
        timeout=60.0,
    )
    shutil.copy2(root_dir / "categories.json", latest_dir / "categories.json")
    shutil.copy2(root_dir / "categories.json", version_dir / "categories.json")

    if latest_marker_text != tag:
        (latest_dir / "latest").write_text(f"{tag}\n", encoding="utf-8")
        (version_dir / "latest").write_text(f"{tag}\n", encoding="utf-8")

    plugin_files: list[Path] = []
    for zip_path in sorted((input_dir / "plugins").glob("*.zip")):
        shutil.copy2(zip_path, root_dir / zip_path.name)
        shutil.copy2(zip_path, latest_dir / zip_path.name)
        shutil.copy2(zip_path, version_dir / zip_path.name)
        plugin_files.append(zip_path)

    rewrite_plugin_urls(
        plugins_json_path=root_dir / "plugins.json",
        base_url=normalized_base_url,
        tag=tag,
        readme_mode=readme_mode,
    )
    latest_payload = rewrite_plugin_urls(
        plugins_json_path=latest_dir / "plugins.json",
        base_url=normalized_base_url,
        tag=tag,
        readme_mode=readme_mode,
    )
    rewrite_plugin_urls(
        plugins_json_path=version_dir / "plugins.json",
        base_url=normalized_base_url,
        tag=tag,
        readme_mode=readme_mode,
    )

    readmes = dict(collected_readmes or {})
    if readme_mode == "mirror":
        readmes = {**collect_readmes_from_input(input_dir), **readmes}
        mirror_readmes(readmes=readmes, output_dir=output_dir, input_dir=input_dir)

    write_manifests(
        output_dir=output_dir,
        source_repo=source_repo,
        tag=tag,
        base_url=normalized_base_url,
        plugin_count=len(iter_plugins(latest_payload)),
        source_manifest=load_source_manifest(input_dir),
    )


def verify_market_directory(market_dir: Path) -> dict[str, Any]:
    errors: list[str] = []
    latest_dir = market_dir / "releases" / "latest" / "download"

    for name in REQUIRED_RELEASE_FILES:
        if not (market_dir / name).exists():
            errors.append(f"missing required file: {market_dir / name}")
        if not (latest_dir / name).exists():
            errors.append(f"missing required file: {latest_dir / name}")

    plugins_json_path = latest_dir / "plugins.json"
    version_dir: Path | None = None
    if (latest_dir / "latest").exists():
        tag_text = (latest_dir / "latest").read_text(encoding="utf-8").strip()
        if not tag_text:
            errors.append(f"empty latest marker: {latest_dir / 'latest'}")
        else:
            version_dir = market_dir / "releases" / "download" / tag_text
            if not version_dir.exists():
                errors.append(f"missing version directory: {version_dir}")
            else:
                for name in REQUIRED_RELEASE_FILES:
                    if not (version_dir / name).exists():
                        errors.append(f"missing required file: {version_dir / name}")

    if plugins_json_path.exists():
        try:
            payload = load_json(plugins_json_path)
            plugins = iter_plugins(payload)
        except (json.JSONDecodeError, MarketError) as exc:
            errors.append(f"malformed plugins.json: {exc}")
        else:
            for plugin in plugins:
                plugin_file = resolve_plugin_file(plugin)
                if not plugin_file:
                    errors.append("plugin entry missing archive filename: expected pluginFile or url")
                    continue

                latest_archive = latest_dir / plugin_file
                if not latest_archive.exists():
                    errors.append(f"missing plugin archive: {plugin_file}")
                elif latest_archive.stat().st_size <= 0:
                    errors.append(f"empty plugin archive: {plugin_file}")

                if version_dir is not None:
                    version_archive = version_dir / plugin_file
                    if not version_archive.exists():
                        errors.append(f"missing versioned plugin archive: {version_archive}")
                    elif version_archive.stat().st_size <= 0:
                        errors.append(f"empty versioned plugin archive: {version_archive}")

    manifest_dir = market_dir / "manifests"
    for manifest_name in ("build-info.json", "files.sha256"):
        if not (manifest_dir / manifest_name).exists():
            errors.append(f"missing manifest file: {manifest_dir / manifest_name}")

    return {"ok": not errors, "errors": errors}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ztools-offline-market")
    subparsers = parser.add_subparsers(dest="command", required=True)

    pull_parser = subparsers.add_parser("pull")
    pull_parser.add_argument("--tag", required=True)
    pull_parser.add_argument("--output", required=True)
    pull_parser.add_argument("--repo", default=DEFAULT_SOURCE_REPO)
    pull_parser.add_argument("--timeout", type=float, default=60.0)

    build_parser_obj = subparsers.add_parser("build")
    build_parser_obj.add_argument("--input", required=True)
    build_parser_obj.add_argument("--base-url", required=True)
    build_parser_obj.add_argument("--output", required=True)
    build_parser_obj.add_argument("--tag", required=True)
    build_parser_obj.add_argument("--readme-mode", choices=("skip", "mirror"), default="skip")
    build_parser_obj.add_argument("--repo", default=DEFAULT_SOURCE_REPO)

    package_parser = subparsers.add_parser("package")
    package_parser.add_argument("--base-url", required=True)
    package_parser.add_argument("--output", default="market-data")
    package_parser.add_argument("--tag")
    package_parser.add_argument("--repo", default=DEFAULT_SOURCE_REPO)
    package_parser.add_argument("--timeout", type=float, default=60.0)
    package_parser.add_argument("--work-dir")

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--market", required=True)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "pull":
            assets = fetch_release_assets(tag=args.tag, repo=args.repo, timeout=args.timeout)
            pull_release_assets(assets=assets, output_dir=Path(args.output))
            print(f"PULL OK: {args.output}")
            return 0

        if args.command == "build":
            build_market_directory(
                input_dir=Path(args.input),
                output_dir=Path(args.output),
                base_url=args.base_url,
                tag=args.tag,
                readme_mode=args.readme_mode,
                source_repo=args.repo,
            )
            print(f"BUILD OK: {args.output}")
            return 0

        if args.command == "package":
            resolved_tag = args.tag or resolve_latest_release_tag(repo=args.repo, timeout=args.timeout)
            work_dir = Path(args.work_dir) if args.work_dir else Path("build") / f"package-source-{resolved_tag}"
            output_dir = Path(args.output)
            reset_directory(work_dir)
            reset_directory(output_dir)
            assets = fetch_release_assets(tag=resolved_tag, repo=args.repo, timeout=args.timeout)
            pull_release_assets(assets=assets, output_dir=work_dir)
            build_market_directory(
                input_dir=work_dir,
                output_dir=output_dir,
                base_url=args.base_url,
                tag=resolved_tag,
                readme_mode="mirror",
                source_repo=args.repo,
            )
            result = verify_market_directory(output_dir)
            if not result["ok"]:
                for error in result["errors"]:
                    print(error)
                return 1
            print(f"PACKAGE OK: {output_dir} ({resolved_tag})")
            return 0

        if args.command == "verify":
            result = verify_market_directory(Path(args.market))
            if result["ok"]:
                print("VERIFY OK")
                return 0
            for error in result["errors"]:
                print(error)
            return 1
    except MarketError as exc:
        print(f"ERROR: {exc}")
        return 1
    except OSError as exc:
        print(f"ERROR: {exc}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"ERROR: {exc}")
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
