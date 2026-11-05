"""Smoke-test standalone extension bootstrap and update without changing core."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence
from urllib.request import urlopen

from openlinktoken_ext_truveta.util.extension_bundles import (
    SUPPORTED_BUNDLE_TARGETS,
)

_CORE_METADATA_PREFIXES = (
    "openlinktoken-",
    "openlinktoken_cli-",
    "openlinktoken_core_ai-",
)


def main(argv: Sequence[str] | None = None) -> int:
    """Install and update the Truveta extension from release manifests."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cli", required=True, type=Path, help="Standalone OLT executable."
    )
    parser.add_argument(
        "--manifest-url",
        required=True,
        help="URL of the release's Truveta bootstrap manifest.",
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

    cli_path = args.cli.resolve()
    core_metadata_before = _core_metadata_hashes(cli_path)
    bootstrap = _read_json(args.manifest_url)
    if bootstrap.get("schema_version") != 2:
        raise ValueError("Expected a schema-v2 bootstrap manifest")
    expected_version = bootstrap["extension"]["version"]
    update_manifest_url = (
        f"{args.manifest_url.rsplit('/', 1)[0]}/openlinktoken-ext-truveta-update.json"
    )
    update_manifest = _read_json(update_manifest_url)
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
    _verify_artifact_digest(selected_bundle["url"], selected_bundle["sha256"])

    with tempfile.TemporaryDirectory(prefix="olt-extension-update-") as temp_home:
        extensions_dir = Path(temp_home) / "extensions"
        environment = os.environ.copy()
        environment.update(
            {
                "HOME": temp_home,
                "APPDATA": temp_home,
                "XDG_CONFIG_HOME": str(Path(temp_home) / ".config"),
                "OLT_EXTENSIONS_DIR": str(extensions_dir),
            }
        )

        _run_cli(cli_path, ["truveta", "logout"], environment)
        registry_path = extensions_dir / "registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry.pop("truveta", None)
        registry_path.write_text(
            json.dumps(registry, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        _run_cli(
            cli_path,
            ["extension", "install", "--yes", "--manifest", args.manifest_url],
            environment,
        )

        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        entry = registry["truveta"]
        entry["update_manifest_url"] = update_manifest_url
        entry["version"] = "0.0.0"
        registry_path.write_text(
            json.dumps(registry, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        _run_cli(cli_path, ["extension", "update", "truveta", "--yes"], environment)
        _run_cli(cli_path, ["truveta", "logout"], environment)

        updated_registry = json.loads(registry_path.read_text(encoding="utf-8"))
        if updated_registry["truveta"]["version"] != update_manifest["latest_version"]:
            raise RuntimeError(
                "Extension update did not persist the manifest version: "
                f"expected {update_manifest['latest_version']}, "
                f"found {updated_registry['truveta']['version']}"
            )

    if _core_metadata_hashes(cli_path) != core_metadata_before:
        raise RuntimeError(
            "The independent extension update changed core distribution metadata"
        )

    print(
        "Validated Truveta bootstrap and explicit extension update to "
        f"{expected_version}; OpenLinkToken core metadata remained unchanged."
    )
    return 0


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


def _read_json(url: str) -> dict:
    """Fetch a release manifest and decode its JSON object."""
    with urlopen(url, timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object from {url}")
    return payload


def _verify_artifact_digest(url: str, expected_digest: str) -> None:
    """Verify the release manifest's SHA-256 against a bundle artifact."""
    digest = hashlib.sha256()
    with urlopen(url, timeout=30) as response:
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
    metadata_paths = sorted(internal_dir.glob("*.dist-info/METADATA"))
    core_metadata = {
        metadata_path.parent.name: hashlib.sha256(
            metadata_path.read_bytes()
        ).hexdigest()
        for metadata_path in metadata_paths
        if metadata_path.parent.name.startswith(_CORE_METADATA_PREFIXES)
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
