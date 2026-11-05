"""Build locked dependency bundles for standalone extension releases."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from email.parser import BytesParser
from pathlib import Path
from typing import Sequence

from packaging.utils import canonicalize_name
from packaging.utils import parse_wheel_filename
from packaging.version import InvalidVersion
from packaging.version import Version

from openlinktoken_ext_truveta import (
    EXTENSION_COMMAND_NAME,
    EXTENSION_DISTRIBUTION_NAME,
)

SUPPORTED_BUNDLE_TARGETS = {
    "linux-x64": ("cp311", "cp312"),
    "macos-arm64": ("cp311", "cp312"),
    "windows-x64": ("cp311", "cp312"),
}
_CORE_DISTRIBUTIONS = frozenset(
    {
        "openlinktoken",
        "openlinktoken-cli",
        "openlinktoken-core-ai",
    }
)


def create_extension_bundle_assets(
    version: str,
    target: str,
    python_abi: str,
    extension_wheel: Path,
    dependency_wheel_dir: Path,
    output_dir: Path,
) -> list[Path]:
    """Create a locked bundle ZIP and its checksum for one standalone target.

    Args:
        version: Semantic version of the extension release.
        target: Supported standalone target name.
        python_abi: CPython ABI used by the target runtime.
        extension_wheel: Built extension wheel to include.
        dependency_wheel_dir: Directory containing downloaded dependency wheels.
        output_dir: Directory where the bundle and checksum are written.

    Returns:
        Paths to the bundle ZIP and checksum sidecar.
    """
    normalized_version = _validate_version(version)
    if python_abi not in SUPPORTED_BUNDLE_TARGETS.get(target, ()):
        raise ValueError(
            f"Unsupported extension bundle target/ABI: {target}/{python_abi}"
        )

    extension_wheel = Path(extension_wheel)
    dependency_wheel_dir = Path(dependency_wheel_dir)
    output_dir = Path(output_dir)
    if not extension_wheel.is_file():
        raise FileNotFoundError(f"Extension wheel not found: {extension_wheel}")
    if not dependency_wheel_dir.is_dir():
        raise FileNotFoundError(
            f"Dependency wheel directory not found: {dependency_wheel_dir}"
        )

    dependency_files = sorted(
        path for path in dependency_wheel_dir.iterdir() if path.is_file()
    )
    non_wheels = [path.name for path in dependency_files if path.suffix != ".whl"]
    if non_wheels:
        raise ValueError(
            "Dependency bundle input contains non-wheel files: " + ", ".join(non_wheels)
        )

    wheel_paths = [extension_wheel, *dependency_files]
    wheel_records = [_wheel_record(path, normalized_version) for path in wheel_paths]
    _validate_wheel_set(wheel_records)

    bundle_manifest = {
        "schema_version": 1,
        "extension": {
            "name": EXTENSION_COMMAND_NAME,
            "version": version,
        },
        "target": target,
        "python_abi": python_abi,
        "wheels": sorted(wheel_records, key=lambda record: record["name"]),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = output_dir / (
        f"openlinktoken-ext-{EXTENSION_COMMAND_NAME}-{version}-{target}-{python_abi}.zip"
    )
    with zipfile.ZipFile(
        bundle_path, mode="w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        archive.writestr(
            "bundle-manifest.json",
            json.dumps(bundle_manifest, indent=2, sort_keys=True) + "\n",
        )
        for wheel_path in sorted(wheel_paths, key=lambda path: path.name):
            archive.write(wheel_path, arcname=wheel_path.name)

    checksum_path = Path(f"{bundle_path}.sha256")
    checksum_path.write_text(
        f"{_sha256_file(bundle_path)}  {bundle_path.name}\n",
        encoding="utf-8",
    )
    return [bundle_path, checksum_path]


def main(argv: Sequence[str] | None = None) -> int:
    """Create standalone extension dependency bundle assets.

    Args:
        argv: Optional command-line arguments.

    Returns:
        Exit status.
    """
    parser = argparse.ArgumentParser(
        description="Build a locked standalone extension dependency bundle."
    )
    parser.add_argument("--version", required=True, help="Extension SemVer.")
    parser.add_argument(
        "--target",
        required=True,
        choices=sorted(SUPPORTED_BUNDLE_TARGETS),
        help="Standalone platform target.",
    )
    parser.add_argument(
        "--python-abi",
        required=True,
        choices=sorted(
            {abi for abis in SUPPORTED_BUNDLE_TARGETS.values() for abi in abis}
        ),
        help="Embedded CPython ABI.",
    )
    parser.add_argument(
        "--extension-wheel",
        required=True,
        type=Path,
        help="Built Truveta extension wheel.",
    )
    parser.add_argument(
        "--dependency-wheel-dir",
        required=True,
        type=Path,
        help="Directory containing hash-verified dependency wheels.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory where the bundle and checksum are written.",
    )
    args = parser.parse_args(argv)

    for path in create_extension_bundle_assets(
        args.version,
        args.target,
        args.python_abi,
        args.extension_wheel,
        args.dependency_wheel_dir,
        args.output_dir,
    ):
        print(path)
    return 0


def _validate_version(version: str) -> Version:
    """Parse the release version used by the extension wheel.

    Args:
        version: Extension version string.

    Returns:
        Parsed PEP 440 version.
    """
    try:
        return Version(version)
    except InvalidVersion as exc:
        raise ValueError(f"Invalid extension version: {version!r}") from exc


def _wheel_record(path: Path, extension_version: Version) -> dict[str, object]:
    """Read wheel identity and calculate its lock record.

    Args:
        path: Wheel file to inspect.
        extension_version: Version expected for the Truveta extension wheel.

    Returns:
        Lock record containing the wheel filename, identity, tags, and digest.
    """
    try:
        filename_name, filename_version, _, tags = parse_wheel_filename(path.name)
    except ValueError as exc:
        raise ValueError(f"Invalid wheel filename: {path.name}") from exc

    try:
        with zipfile.ZipFile(path) as wheel:
            metadata_files = [
                name
                for name in wheel.namelist()
                if name.endswith(".dist-info/METADATA")
            ]
            if len(metadata_files) != 1:
                raise ValueError(
                    f"Wheel '{path.name}' must contain exactly one METADATA file"
                )
            metadata = BytesParser().parsebytes(wheel.read(metadata_files[0]))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Wheel '{path.name}' is not a valid ZIP archive") from exc

    metadata_name = metadata.get("Name")
    metadata_version = metadata.get("Version")
    if not isinstance(metadata_name, str) or not isinstance(metadata_version, str):
        raise ValueError(f"Wheel '{path.name}' has incomplete distribution metadata")
    try:
        parsed_metadata_version = Version(metadata_version)
    except InvalidVersion as exc:
        raise ValueError(
            f"Wheel '{path.name}' has an invalid metadata version"
        ) from exc

    normalized_name = canonicalize_name(metadata_name)
    if (
        normalized_name != canonicalize_name(str(filename_name))
        or parsed_metadata_version != filename_version
    ):
        raise ValueError(f"Wheel filename does not match metadata for '{path.name}'")
    if (
        normalized_name == canonicalize_name(EXTENSION_DISTRIBUTION_NAME)
        and parsed_metadata_version != extension_version
    ):
        raise ValueError(
            f"Extension wheel version {parsed_metadata_version} does not match "
            f"release version {extension_version}"
        )

    return {
        "filename": path.name,
        "name": normalized_name,
        "version": str(parsed_metadata_version),
        "tags": sorted(str(tag) for tag in tags),
        "sha256": _sha256_file(path),
    }


def _validate_wheel_set(wheel_records: list[dict[str, object]]) -> None:
    """Require one extension wheel and no core or duplicate distributions.

    Args:
        wheel_records: Records that will be written into the bundle lock.
    """
    extension_name = canonicalize_name(EXTENSION_DISTRIBUTION_NAME)
    core_distributions = {canonicalize_name(name) for name in _CORE_DISTRIBUTIONS}
    names = [str(record["name"]) for record in wheel_records]
    if len(names) != len(set(names)):
        raise ValueError("Bundle contains duplicate distributions")
    if core_distributions.intersection(names):
        raise ValueError("Bundle must not include OpenLinkToken core distributions")
    if names.count(extension_name) != 1:
        raise ValueError("Bundle must contain exactly one Truveta extension wheel")


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


if __name__ == "__main__":
    raise SystemExit(main())
