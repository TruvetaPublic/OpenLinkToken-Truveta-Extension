"""Smoke-test standalone extension bootstrap and update without changing core."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import shutil
import ssl
import subprocess
import tempfile
from pathlib import Path
from typing import Iterator, Sequence
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen

from local_https_assets import serve_local_https
from openlinktoken_ext_truveta.util.extension_bundles import (
    SUPPORTED_BUNDLE_TARGETS,
)

_BOOTSTRAP_MANIFEST = "openlinktoken-ext-truveta-bootstrap.json"
_UPDATE_MANIFEST = "openlinktoken-ext-truveta-update.json"
_CORE_METADATA_PREFIXES = (
    "openlinktoken-",
    "openlinktoken_cli-",
    "openlinktoken_core_ai-",
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the extension bootstrap and update smoke against release assets."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fresh-core",
        action="store_true",
        help="Test a core CLI without a preinstalled Truveta extension.",
    )
    parser.add_argument(
        "--cli", required=True, type=Path, help="Standalone OLT executable."
    )
    asset_source = parser.add_mutually_exclusive_group(required=True)
    asset_source.add_argument(
        "--manifest-url",
        help="URL of the release's Truveta bootstrap manifest.",
    )
    asset_source.add_argument(
        "--local-assets-dir",
        type=Path,
        help="Directory containing generated bootstrap/update manifests and bundles.",
    )
    parser.add_argument(
        "--target",
        required=True,
        choices=tuple(SUPPORTED_BUNDLE_TARGETS),
        help="Standalone platform target whose bundle should be verified.",
    )
    parser.add_argument(
        "--python-abi",
        required=True,
        choices=tuple(
            sorted({abi for abis in SUPPORTED_BUNDLE_TARGETS.values() for abi in abis})
        ),
        help="Embedded CPython ABI whose bundle should be verified.",
    )
    args = parser.parse_args(argv)

    if args.local_assets_dir is not None:
        with _local_asset_server(args.local_assets_dir) as local_assets:
            return _run_smoke(args, *local_assets)
    return _run_smoke(args, args.manifest_url, None, None)


@contextmanager
def _local_asset_server(
    asset_directory: Path,
) -> Iterator[tuple[str, ssl.SSLContext, Path]]:
    """Stage generated release files and serve them over trusted loopback HTTPS.

    Args:
        asset_directory: Directory containing the generated manifests and bundles.

    Yields:
        The local bootstrap URL, trusted SSL context, and temporary CA certificate.
    """
    with tempfile.TemporaryDirectory(prefix="olt-extension-assets-") as directory:
        staging_directory = Path(directory)
        _stage_local_assets(asset_directory, staging_directory)
        with serve_local_https(staging_directory) as (base_url, ca_certificate):
            _rewrite_local_manifests(staging_directory, base_url)
            ssl_context = ssl.create_default_context(cafile=str(ca_certificate))
            yield (
                f"{base_url}/{_BOOTSTRAP_MANIFEST}",
                ssl_context,
                ca_certificate,
            )


def _stage_local_assets(asset_directory: Path, staging_directory: Path) -> None:
    """Copy the generated manifests and referenced bundles into a temporary directory.

    Args:
        asset_directory: Directory containing the generated release assets.
        staging_directory: Temporary directory used by the local HTTPS server.

    Returns:
        None.
    """
    asset_directory = asset_directory.resolve()
    for manifest_name in (_BOOTSTRAP_MANIFEST, _UPDATE_MANIFEST):
        source = asset_directory / manifest_name
        if not source.is_file():
            raise FileNotFoundError(f"Missing generated release manifest: {source}")
        shutil.copyfile(source, staging_directory / manifest_name)

    bootstrap_path = staging_directory / _BOOTSTRAP_MANIFEST
    bootstrap = json.loads(bootstrap_path.read_text(encoding="utf-8"))
    if not isinstance(bootstrap, dict) or not isinstance(
        bootstrap.get("bundles"), list
    ):
        raise ValueError("Bootstrap manifest has no extension bundle list")
    for bundle in bootstrap["bundles"]:
        if not isinstance(bundle, dict) or not isinstance(bundle.get("url"), str):
            raise ValueError("Bootstrap manifest contains an invalid extension bundle")
        filename = _bundle_filename(bundle["url"])
        source = asset_directory / filename
        if not source.is_file():
            raise FileNotFoundError(f"Missing generated release bundle: {source}")
        shutil.copyfile(source, staging_directory / filename)


def _rewrite_local_manifests(staging_directory: Path, base_url: str) -> None:
    """Point staged manifests and bundle records at the local HTTPS server.

    Args:
        staging_directory: Directory containing staged manifests and bundles.
        base_url: Base URL of the local HTTPS server.

    Returns:
        None.
    """
    for manifest_name in (_BOOTSTRAP_MANIFEST, _UPDATE_MANIFEST):
        manifest_path = staging_directory / manifest_name
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or not isinstance(
            manifest.get("bundles"), list
        ):
            raise ValueError(f"Manifest has no extension bundle list: {manifest_name}")
        for bundle in manifest["bundles"]:
            if not isinstance(bundle, dict) or not isinstance(bundle.get("url"), str):
                raise ValueError(
                    f"Manifest contains an invalid extension bundle: {manifest_name}"
                )
            bundle["url"] = f"{base_url}/{_bundle_filename(bundle['url'])}"
        if manifest_name == _BOOTSTRAP_MANIFEST:
            extension = manifest.get("extension")
            if not isinstance(extension, dict):
                raise ValueError("Bootstrap manifest has no extension metadata")
            extension["update_manifest_url"] = f"{base_url}/{_UPDATE_MANIFEST}"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def _bundle_filename(url: str) -> str:
    """Return a safe local filename from a bundle URL.

    Args:
        url: Bundle URL from a release manifest.

    Returns:
        The final URL path component.
    """
    filename = Path(unquote(urlsplit(url).path)).name
    if filename in ("", ".", ".."):
        raise ValueError(f"Invalid extension bundle URL: {url}")
    return filename


def _run_smoke(
    args: argparse.Namespace,
    manifest_url: str,
    ssl_context: ssl.SSLContext | None,
    ca_certificate: Path | None,
) -> int:
    """Install and update the extension, then verify the standalone CLI is unchanged.

    Args:
        args: Parsed smoke-test options.
        manifest_url: Bootstrap manifest URL.
        ssl_context: Optional SSL context for local generated assets.
        ca_certificate: Optional CA certificate to trust in the CLI subprocess.

    Returns:
        Zero after the full smoke test passes.
    """
    cli_path = args.cli.resolve()
    core_metadata_before = _core_metadata_hashes(cli_path)
    bootstrap = _read_json(manifest_url, ssl_context)
    if bootstrap.get("schema_version") != 2:
        raise ValueError("Expected a schema-v2 bootstrap manifest")
    expected_version = bootstrap["extension"]["version"]
    update_manifest_url = f"{manifest_url.rsplit('/', 1)[0]}/{_UPDATE_MANIFEST}"
    update_manifest = _read_json(update_manifest_url, ssl_context)
    if update_manifest.get("schema_version") != 2:
        raise ValueError("Expected a schema-v2 update manifest")
    if update_manifest["latest_version"] != expected_version:
        raise ValueError(
            "Bootstrap and update manifests disagree on the extension version: "
            f"{expected_version} != {update_manifest['latest_version']}"
        )

    if (
        bootstrap.get("minimum_runtime_protocol") != 2
        or update_manifest.get("minimum_runtime_protocol") != 2
        or bootstrap.get("minimum_runtime_protocol")
        != update_manifest.get("minimum_runtime_protocol")
    ):
        raise ValueError("Bootstrap and update manifests must require protocol 2")

    bootstrap_bundles = bootstrap.get("bundles")
    if not isinstance(
        bootstrap_bundles, list
    ) or bootstrap_bundles != update_manifest.get("bundles"):
        raise ValueError("Bootstrap and update manifests disagree on extension bundles")
    if not all(isinstance(bundle, dict) for bundle in bootstrap_bundles):
        raise ValueError("Manifests contain an invalid extension bundle record")
    bundle_pairs = [
        (bundle.get("target"), bundle.get("python_abi")) for bundle in bootstrap_bundles
    ]
    if not all(
        isinstance(target, str) and isinstance(python_abi, str)
        for target, python_abi in bundle_pairs
    ):
        raise ValueError(
            "Manifests contain an invalid extension bundle target/ABI pair"
        )
    expected_pairs = {
        (target, python_abi)
        for target, python_abis in SUPPORTED_BUNDLE_TARGETS.items()
        for python_abi in python_abis
    }
    if len(bundle_pairs) != len(expected_pairs) or set(bundle_pairs) != expected_pairs:
        raise ValueError(
            "Manifests must contain exactly one bundle for each supported target/ABI pair"
        )
    bundle_by_pair = dict(zip(bundle_pairs, bootstrap_bundles))
    selected_bundle = bundle_by_pair[(args.target, args.python_abi)]
    if not isinstance(selected_bundle.get("url"), str) or not isinstance(
        selected_bundle.get("sha256"), str
    ):
        raise ValueError(
            f"Invalid extension bundle record for {args.target}/{args.python_abi}"
        )
    _verify_artifact_digest(
        selected_bundle["url"], selected_bundle["sha256"], ssl_context
    )

    with tempfile.TemporaryDirectory(prefix="olt-extension-update-") as temp_home:
        extensions_dir = Path(temp_home) / "extensions"
        environment = os.environ.copy()
        environment.update(
            {
                "HOME": temp_home,
                "APPDATA": temp_home,
                "XDG_CONFIG_HOME": str(Path(temp_home) / ".config"),
                "OLT_EXTENSIONS_DIR": str(extensions_dir),
                "OLT_DISABLE_UPDATE_CHECK": "1",
            }
        )
        if ca_certificate is not None:
            environment.update(
                {
                    "SSL_CERT_FILE": str(ca_certificate),
                    "CURL_CA_BUNDLE": str(ca_certificate),
                    "REQUESTS_CA_BUNDLE": str(ca_certificate),
                }
            )

        registry_path = extensions_dir / "registry.json"
        if not args.fresh_core:
            _run_cli(cli_path, ["truveta", "logout"], environment)
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry.pop("truveta", None)
            registry_path.write_text(
                json.dumps(registry, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

        _run_cli(
            cli_path,
            ["extension", "install", "--yes", "--manifest", manifest_url],
            environment,
        )

        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        entry = registry["truveta"]
        if args.fresh_core and (
            entry.get("python_abi") != args.python_abi
            or entry.get("bundle_sha256") != selected_bundle["sha256"]
        ):
            raise RuntimeError("Installation selected the wrong target/ABI bundle")
        installed_location = (
            Path(entry["install_location"]) if args.fresh_core else None
        )
        installed_payload = (
            _payload_hashes(installed_location)
            if installed_location is not None
            else {}
        )
        entry["update_manifest_url"] = update_manifest_url
        entry["version"] = "0.0.0"
        registry_path.write_text(
            json.dumps(registry, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        _run_cli(cli_path, ["extension", "update", "truveta", "--yes"], environment)
        _run_cli(cli_path, ["truveta", "--help"], environment)
        _run_cli(cli_path, ["truveta", "logout"], environment)

        updated_registry = json.loads(registry_path.read_text(encoding="utf-8"))
        if installed_location is not None:
            updated_location = Path(updated_registry["truveta"]["install_location"])
            if (
                updated_location == installed_location
                or not installed_payload
                or _payload_hashes(updated_location) != installed_payload
            ):
                raise RuntimeError("Update did not activate a newly installed payload")
        if updated_registry["truveta"]["version"] != update_manifest["latest_version"]:
            raise RuntimeError(
                "Extension update did not persist the manifest version: "
                f"expected {update_manifest['latest_version']}, "
                f"found {updated_registry['truveta']['version']}"
            )
        if args.fresh_core and (
            updated_registry["truveta"].get("python_abi") != args.python_abi
            or updated_registry["truveta"].get("bundle_sha256")
            != selected_bundle["sha256"]
        ):
            raise RuntimeError("Update selected the wrong target/ABI bundle")

    if _core_metadata_hashes(cli_path) != core_metadata_before:
        raise RuntimeError(
            "The independent extension update changed core distribution metadata"
        )

    print(
        "Validated Truveta bootstrap and explicit extension update to "
        f"{expected_version}; OpenLinkToken core metadata remained unchanged."
    )
    return 0


def _payload_hashes(directory: Path) -> dict[str, str]:
    """Hash installed Python sources to distinguish reinstall from registry edits."""
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.rglob("*.py")
    }


def _run_cli(cli_path: Path, arguments: list[str], environment: dict[str, str]) -> None:
    """Run a standalone CLI command and include diagnostics on failure."""
    result = subprocess.run(
        [str(cli_path), *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if result.returncode:
        raise RuntimeError(
            f"Command {arguments!r} failed with exit code {result.returncode}.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def _read_json(url: str, ssl_context: ssl.SSLContext | None = None) -> dict:
    """Fetch a release manifest and decode its JSON object.

    Args:
        url: Manifest URL to fetch.
        ssl_context: Optional trusted SSL context for local generated assets.

    Returns:
        The decoded manifest object.
    """
    response_context = (
        urlopen(url, timeout=30)
        if ssl_context is None
        else urlopen(url, timeout=30, context=ssl_context)
    )
    with response_context as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object from {url}")
    return payload


def _verify_artifact_digest(
    url: str, expected_digest: str, ssl_context: ssl.SSLContext | None = None
) -> None:
    """Verify the release manifest's SHA-256 against a bundle artifact.

    Args:
        url: Bundle artifact URL.
        expected_digest: SHA-256 recorded in the manifest.
        ssl_context: Optional trusted SSL context for local generated assets.

    Returns:
        None.
    """
    digest = hashlib.sha256()
    response_context = (
        urlopen(url, timeout=30)
        if ssl_context is None
        else urlopen(url, timeout=30, context=ssl_context)
    )
    with response_context as response:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            digest.update(chunk)
    actual_digest = digest.hexdigest()
    if actual_digest != expected_digest:
        raise ValueError(
            f"Bundle SHA-256 mismatch for {url}: "
            f"expected {expected_digest}, found {actual_digest}"
        )


def _core_metadata_hashes(cli_path: Path) -> dict[str, str]:
    """Hash bundled core distribution metadata to detect accidental core changes."""
    internal_dir = cli_path.parent / "_internal"
    metadata_paths = sorted(
        [
            *internal_dir.glob("*.dist-info/METADATA"),
            *internal_dir.glob("*.egg-info/PKG-INFO"),
        ]
    )
    core_metadata = {
        metadata_path.parent.name.replace(".egg-info", "-"): hashlib.sha256(
            metadata_path.read_bytes()
        ).hexdigest()
        for metadata_path in metadata_paths
        if metadata_path.parent.name.replace(".egg-info", "-").startswith(
            _CORE_METADATA_PREFIXES
        )
    }
    found_prefixes = {
        prefix
        for prefix in _CORE_METADATA_PREFIXES
        if any(name.startswith(prefix) for name in core_metadata)
    }
    if found_prefixes != set(_CORE_METADATA_PREFIXES):
        raise RuntimeError(
            f"Expected bundled core distribution metadata under {internal_dir}; "
            f"found {sorted(core_metadata)}"
        )
    return core_metadata


if __name__ == "__main__":
    raise SystemExit(main())
