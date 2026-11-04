"""Generate release assets for independently updateable extension installs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Sequence

from packaging.version import InvalidVersion
from packaging.version import Version

from openlinktoken_ext_truveta import (
    EXTENSION_COMMAND_NAME,
    EXTENSION_DESCRIPTION,
)
from openlinktoken_ext_truveta.compatibility import SUPPORTED_CORE_SPECIFIER
from openlinktoken_ext_truveta.util.extension_bundles import (
    SUPPORTED_BUNDLE_TARGETS,
)

UPDATE_MANIFEST_NAME = "openlinktoken-ext-truveta-update.json"
BOOTSTRAP_MANIFEST_NAME = "openlinktoken-ext-truveta-bootstrap.json"
DEFAULT_REPOSITORY = "TruvetaPublic/OpenLinkToken-Truveta-Extension"

_MINIMUM_RUNTIME_PROTOCOL = 2
_BUNDLE_MANIFEST_NAME = "bundle-manifest.json"
_SEMVER_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?"
    r"(?:\+(?P<build>[0-9A-Za-z.-]+))?$"
)


def create_extension_release_assets(
    version: str,
    wheel_path: Path,
    bundle_paths: Sequence[Path],
    output_dir: Path,
    repository: str = DEFAULT_REPOSITORY,
) -> list[Path]:
    """Create the wheel checksum and schema-v2 extension manifests.

    Args:
        version: Semantic version of the extension release.
        wheel_path: Built extension wheel to publish.
        bundle_paths: Platform-specific dependency bundles to publish.
        output_dir: Directory where release assets are written.
        repository: GitHub repository in OWNER/REPOSITORY form.

    Returns:
        Paths to the wheel checksum and generated manifests.
    """
    normalized_version = _validate_version(version)
    wheel_path = Path(wheel_path)
    bundle_paths = [Path(path) for path in bundle_paths]
    output_dir = Path(output_dir)
    if not wheel_path.is_file():
        raise FileNotFoundError(f"Wheel not found: {wheel_path}")
    bundles = _load_bundle_records(bundle_paths, normalized_version, repository)

    output_dir.mkdir(parents=True, exist_ok=True)
    wheel_sha256 = _sha256_file(wheel_path)
    checksum_path = output_dir / f"{wheel_path.name}.sha256"
    checksum_path.write_text(f"{wheel_sha256}  {wheel_path.name}\n", encoding="utf-8")

    update_manifest_url = (
        f"https://github.com/{repository}/releases/latest/download/"
        f"{UPDATE_MANIFEST_NAME}"
    )
    bootstrap_manifest = {
        "schema_version": 2,
        "extension": {
            "name": EXTENSION_COMMAND_NAME,
            "version": normalized_version,
            "update_manifest_url": update_manifest_url,
        },
        "core": _core_version_bounds(),
        "minimum_runtime_protocol": _MINIMUM_RUNTIME_PROTOCOL,
        "command_name": EXTENSION_COMMAND_NAME,
        "description": EXTENSION_DESCRIPTION,
        "bundles": bundles,
    }
    update_manifest = {
        "schema_version": 2,
        "extension": EXTENSION_COMMAND_NAME,
        "latest_version": normalized_version,
        "requires_core": SUPPORTED_CORE_SPECIFIER,
        "minimum_runtime_protocol": _MINIMUM_RUNTIME_PROTOCOL,
        "command_name": EXTENSION_COMMAND_NAME,
        "description": EXTENSION_DESCRIPTION,
        "bundles": bundles,
    }

    bootstrap_path = output_dir / BOOTSTRAP_MANIFEST_NAME
    update_path = output_dir / UPDATE_MANIFEST_NAME
    _write_json(bootstrap_path, bootstrap_manifest)
    _write_json(update_path, update_manifest)

    return [checksum_path, bootstrap_path, update_path]


def _load_bundle_records(
    bundle_paths: Sequence[Path],
    version: str,
    repository: str,
) -> list[dict[str, str]]:
    """Validate bundle locks and create their release URL records.

    Args:
        bundle_paths: Bundle ZIPs created for the supported targets.
        version: Validated release version.
        repository: GitHub repository in OWNER/REPOSITORY form.

    Returns:
        Bundle records sorted by the supported target order.
    """
    expected_pairs = set(SUPPORTED_BUNDLE_TARGETS.items())
    bundle_records: dict[tuple[str, str], dict[str, str]] = {}
    for bundle_path in bundle_paths:
        if not bundle_path.is_file():
            raise FileNotFoundError(f"Extension bundle not found: {bundle_path}")
        bundle_manifest = _read_bundle_manifest(bundle_path)
        if bundle_manifest["extension"] != {
            "name": EXTENSION_COMMAND_NAME,
            "version": version,
        }:
            raise ValueError(
                f"Bundle extension identity does not match release version: "
                f"{bundle_path.name}"
            )

        target = bundle_manifest["target"]
        python_abi = bundle_manifest["python_abi"]
        pair = (target, python_abi)
        if pair not in expected_pairs:
            raise ValueError(
                f"Unsupported extension bundle target/ABI: {target}/{python_abi}"
            )
        if pair in bundle_records:
            raise ValueError(
                f"Duplicate extension bundle target/ABI: {target}/{python_abi}"
            )
        expected_filename = (
            f"openlinktoken-ext-{EXTENSION_COMMAND_NAME}-"
            f"{version}-{target}-{python_abi}.zip"
        )
        if bundle_path.name != expected_filename:
            raise ValueError(
                "Bundle filename does not match its target and release version: "
                f"{bundle_path.name}"
            )

        bundle_records[pair] = {
            "target": target,
            "python_abi": python_abi,
            "url": (
                f"https://github.com/{repository}/releases/download/"
                f"v{version}/{bundle_path.name}"
            ),
            "sha256": _sha256_file(bundle_path),
        }

    if set(bundle_records) != expected_pairs:
        missing = sorted(expected_pairs - set(bundle_records))
        raise ValueError(f"Missing extension bundle targets: {missing}")

    return [
        bundle_records[(target, python_abi)]
        for target, python_abi in SUPPORTED_BUNDLE_TARGETS.items()
    ]


def _read_bundle_manifest(bundle_path: Path) -> dict[str, object]:
    """Read and validate the identity and wheel list in a bundle ZIP.

    Args:
        bundle_path: Bundle ZIP to inspect.

    Returns:
        Parsed bundle manifest fields.
    """
    try:
        with zipfile.ZipFile(bundle_path) as archive:
            names = archive.namelist()
            if names.count(_BUNDLE_MANIFEST_NAME) != 1:
                raise ValueError(
                    f"Bundle '{bundle_path.name}' must contain exactly one "
                    f"{_BUNDLE_MANIFEST_NAME}"
                )
            payload = json.loads(archive.read(_BUNDLE_MANIFEST_NAME).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError(
                    f"Bundle '{bundle_path.name}' manifest must be a JSON object"
                )
            schema_version = payload.get("schema_version")
            extension = payload.get("extension")
            target = payload.get("target")
            python_abi = payload.get("python_abi")
            wheels = payload.get("wheels")
            if (
                isinstance(schema_version, bool)
                or not isinstance(schema_version, int)
                or schema_version != 1
                or not isinstance(extension, dict)
                or not isinstance(target, str)
                or not isinstance(python_abi, str)
                or not isinstance(wheels, list)
                or not wheels
            ):
                raise ValueError(f"Bundle '{bundle_path.name}' has an invalid manifest")
            if not all(isinstance(wheel, dict) for wheel in wheels):
                raise ValueError(
                    f"Bundle '{bundle_path.name}' has invalid wheel records"
                )
            wheel_filenames = [wheel.get("filename") for wheel in wheels]
            if not all(
                isinstance(filename, str)
                and filename.endswith(".whl")
                and Path(filename).name == filename
                and "\\" not in filename
                for filename in wheel_filenames
            ):
                raise ValueError(
                    f"Bundle '{bundle_path.name}' has invalid wheel filenames"
                )
            if (
                len(names) != len(set(names))
                or len(wheel_filenames) != len(set(wheel_filenames))
                or set(names) != {_BUNDLE_MANIFEST_NAME, *wheel_filenames}
            ):
                raise ValueError(
                    f"Bundle '{bundle_path.name}' contents do not match its lock"
                )
            return {
                "extension": extension,
                "target": target,
                "python_abi": python_abi,
            }
    except (UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Invalid extension bundle: {bundle_path}") from exc


def main(argv: Sequence[str] | None = None) -> int:
    """Generate extension release assets from a wheel and platform bundles.

    Args:
        argv: Optional command-line arguments.

    Returns:
        Exit status.
    """
    parser = argparse.ArgumentParser(
        description="Create extension checksum and schema-v2 manifests."
    )
    parser.add_argument("--version", required=True, help="Extension SemVer.")
    parser.add_argument("--wheel", required=True, type=Path, help="Built wheel path.")
    parser.add_argument(
        "--bundle",
        required=True,
        action="append",
        type=Path,
        help="Built platform-specific extension dependency bundle; repeat for each target.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory where release assets are written.",
    )
    parser.add_argument(
        "--repository",
        default=DEFAULT_REPOSITORY,
        help="GitHub repository in OWNER/REPOSITORY form.",
    )
    args = parser.parse_args(argv)

    for path in create_extension_release_assets(
        args.version,
        args.wheel,
        args.bundle,
        args.output_dir,
        args.repository,
    ):
        print(path)
    return 0


def _validate_version(version: str) -> str:
    """Validate and return a semantic version without normalizing it.

    Args:
        version: Version string to validate.

    Returns:
        The validated version string.
    """
    if not isinstance(version, str):
        raise ValueError("Version must be a semantic version string")

    if not version:
        raise ValueError("Version cannot be empty")
    if version != version.strip():
        raise ValueError("Version must not contain surrounding whitespace")

    try:
        Version(version)
    except InvalidVersion as exc:
        raise ValueError(f"Invalid semantic version: {version!r}") from exc

    match = _SEMVER_PATTERN.fullmatch(version)
    if match is None:
        raise ValueError(f"Version is not semantic: {version!r}")

    prerelease = match.group("prerelease")
    build = match.group("build")
    if any(
        not identifier
        for identifiers in (prerelease, build)
        if identifiers is not None
        for identifier in identifiers.split(".")
    ):
        raise ValueError(f"Version is not semantic: {version!r}")

    if prerelease is not None and any(
        identifier.isdigit() and len(identifier) > 1 and identifier.startswith("0")
        for identifier in prerelease.split(".")
    ):
        raise ValueError(f"Version is not semantic: {version!r}")

    return version


def _core_version_bounds() -> dict[str, str]:
    """Split the shared core specifier into the bootstrap schema fields.

    Returns:
        Bootstrap manifest minimum and maximum core versions.
    """
    specifiers = SUPPORTED_CORE_SPECIFIER.split(",")
    minimum = next(
        specifier.removeprefix(">=")
        for specifier in specifiers
        if specifier.startswith(">=")
    )
    maximum = next(specifier for specifier in specifiers if specifier.startswith("<"))
    return {"min_version": minimum, "max_version": maximum}


def _sha256_file(path: Path) -> str:
    """Return a file's SHA-256 digest using bounded memory.

    Args:
        path: File to hash.

    Returns:
        Hex-encoded SHA-256 digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict) -> None:
    """Write a JSON payload with stable formatting.

    Args:
        path: Destination file.
        payload: JSON-serializable content.
    """
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
