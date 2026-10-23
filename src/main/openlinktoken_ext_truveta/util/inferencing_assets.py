"""
Copyright (c) Truveta. All rights reserved.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ML1_ASSET_DESTINATION = "openlinktoken/core/ai/tokens"
ML1_ASSET_FILES = (
    "asset-manifest.json",
    "model.onnx",
    "model.onnx.data",
    "tokenizer.json",
)


def validate_ml1_assets(source_dir: str | Path) -> list[Path]:
    """Validate the required ML1 files against their asset manifest.

    Inputs:
        source_dir: Directory containing an OCI pull of ML1 assets.

    Returns:
        Paths to the validated manifest and model files.
    """
    source_path = Path(source_dir).expanduser()
    manifest_path = source_path / "asset-manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"ML1 asset manifest not found at {manifest_path}")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"ML1 asset manifest is not valid JSON: {manifest_path}"
        ) from exc

    if not isinstance(manifest, dict):
        raise ValueError(f"ML1 asset manifest has no valid assets map: {manifest_path}")

    asset_metadata = manifest.get("assets")
    if not isinstance(asset_metadata, dict):
        raise ValueError(f"ML1 asset manifest has no valid assets map: {manifest_path}")

    asset_paths: list[Path] = [manifest_path]
    for filename in ML1_ASSET_FILES:
        if filename == "asset-manifest.json":
            continue
        asset_path = source_path / filename
        if not asset_path.is_file() or asset_path.stat().st_size == 0:
            raise FileNotFoundError(f"Missing ML1 asset: {asset_path}")
        _validate_asset(asset_path, asset_metadata.get(filename))
        asset_paths.append(asset_path)

    return asset_paths


def copy_ml1_assets(source_dir: str | Path, destination_dir: str | Path) -> list[Path]:
    """Validate ML1 files and copy them into a runtime model directory.

    Inputs:
        source_dir: Directory containing an OCI pull of ML1 assets.
        destination_dir: Runtime directory where the assets will be installed.

    Returns:
        Paths to the installed manifest and model files.
    """
    source_paths = validate_ml1_assets(source_dir)
    destination_path = Path(destination_dir)
    destination_path.mkdir(parents=True, exist_ok=True)
    installed_paths = []
    for source_path in source_paths:
        installed_path = destination_path / source_path.name
        shutil.copy2(source_path, installed_path)
        installed_paths.append(installed_path)
    return installed_paths


def _validate_asset(asset_path: Path, metadata: object) -> None:
    """Verify an ML1 asset matches the size and digest in its manifest.

    Inputs:
        asset_path: Asset file to verify.
        metadata: Expected size and SHA-256 digest from the asset manifest.
    """
    if not isinstance(metadata, dict):
        raise ValueError(f"ML1 asset manifest has no metadata for {asset_path.name}")

    expected_size = metadata.get("size")
    expected_sha256 = metadata.get("sha256")
    if (
        not isinstance(expected_size, int)
        or isinstance(expected_size, bool)
        or expected_size <= 0
    ):
        raise ValueError(
            f"ML1 asset manifest has an invalid size for {asset_path.name}"
        )
    if (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(
            character not in "0123456789abcdefABCDEF" for character in expected_sha256
        )
    ):
        raise ValueError(
            f"ML1 asset manifest has an invalid SHA-256 for {asset_path.name}"
        )

    actual_size = asset_path.stat().st_size
    if actual_size != expected_size:
        raise ValueError(
            f"ML1 asset {asset_path.name} has size {actual_size}; expected {expected_size}"
        )

    actual_sha256 = _sha256_file(asset_path)
    if actual_sha256.lower() != expected_sha256.lower():
        raise ValueError(
            f"ML1 asset {asset_path.name} has SHA-256 {actual_sha256}; expected {expected_sha256}"
        )


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 digest for a file.

    Inputs:
        path: File whose digest to calculate.

    Returns:
        The lowercase hexadecimal SHA-256 digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
