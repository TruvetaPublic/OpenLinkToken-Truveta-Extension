"""Generate release assets for independently updateable extension installs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Sequence

from packaging.version import InvalidVersion
from packaging.version import Version

from openlinktoken_ext_truveta.compatibility import SUPPORTED_CORE_SPECIFIER

UPDATE_MANIFEST_NAME = "openlinktoken-ext-truveta-update.json"
BOOTSTRAP_MANIFEST_NAME = "openlinktoken-ext-truveta-bootstrap.json"
DEFAULT_REPOSITORY = "TruvetaPublic/OpenLinkToken-Truveta-Extension"

_EXTENSION_NAME = "truveta"
_SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def create_extension_release_assets(
    version: str,
    wheel_path: Path,
    output_dir: Path,
    repository: str = DEFAULT_REPOSITORY,
) -> list[Path]:
    """Create the wheel checksum, bootstrap manifest, and update manifest."""
    normalized_version = _validate_version(version)
    wheel_path = Path(wheel_path)
    output_dir = Path(output_dir)
    if not wheel_path.is_file():
        raise FileNotFoundError(f"Wheel not found: {wheel_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    wheel_sha256 = _sha256_file(wheel_path)
    checksum_path = output_dir / f"{wheel_path.name}.sha256"
    checksum_path.write_text(f"{wheel_sha256}  {wheel_path.name}\n", encoding="utf-8")

    update_manifest_url = (
        f"https://github.com/{repository}/releases/latest/download/"
        f"{UPDATE_MANIFEST_NAME}"
    )
    wheel_url = (
        f"https://github.com/{repository}/releases/download/"
        f"v{normalized_version}/{wheel_path.name}"
    )
    bootstrap_manifest = {
        "schema_version": 1,
        "extension": {
            "name": _EXTENSION_NAME,
            "version": normalized_version,
            "update_manifest_url": update_manifest_url,
            "artifact_url": wheel_url,
            "sha256": wheel_sha256,
        },
        "core": _core_version_bounds(),
    }
    update_manifest = {
        "schema_version": 1,
        "extension": _EXTENSION_NAME,
        "latest_version": normalized_version,
        "requires_core": SUPPORTED_CORE_SPECIFIER,
        "artifacts": [
            {
                "url": wheel_url,
                "version": normalized_version,
                "sha256": wheel_sha256,
            }
        ],
    }

    bootstrap_path = output_dir / BOOTSTRAP_MANIFEST_NAME
    update_path = output_dir / UPDATE_MANIFEST_NAME
    _write_json(bootstrap_path, bootstrap_manifest)
    _write_json(update_path, update_manifest)

    return [checksum_path, bootstrap_path, update_path]


def main(argv: Sequence[str] | None = None) -> int:
    """Generate extension release assets from a built wheel."""
    parser = argparse.ArgumentParser(
        description="Create extension checksum and update manifests."
    )
    parser.add_argument("--version", required=True, help="Extension SemVer.")
    parser.add_argument("--wheel", required=True, type=Path, help="Built wheel path.")
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
        args.version, args.wheel, args.output_dir, args.repository
    ):
        print(path)
    return 0


def _validate_version(version: str) -> str:
    """Validate and return a normalized semantic version."""
    if not isinstance(version, str):
        raise ValueError("Version must be a semantic version string")

    normalized_version = version.strip()
    if not normalized_version:
        raise ValueError("Version cannot be empty")

    try:
        Version(normalized_version)
    except InvalidVersion as exc:
        raise ValueError(f"Invalid semantic version: {version!r}") from exc

    if _SEMVER_PATTERN.fullmatch(normalized_version) is None:
        raise ValueError(f"Version is not semantic: {version!r}")

    return normalized_version


def _core_version_bounds() -> dict[str, str]:
    """Split the shared core specifier into the bootstrap schema fields."""
    specifiers = SUPPORTED_CORE_SPECIFIER.split(",")
    minimum = next(
        specifier.removeprefix(">=")
        for specifier in specifiers
        if specifier.startswith(">=")
    )
    maximum = next(specifier for specifier in specifiers if specifier.startswith("<"))
    return {"min_version": minimum, "max_version": maximum}


def _sha256_file(path: Path) -> str:
    """Return a file's SHA-256 digest using bounded memory."""
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict) -> None:
    """Write a JSON payload with stable formatting."""
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
