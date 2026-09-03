"""
Copyright (c) Truveta. All rights reserved.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ML1_ASSET_DESTINATION = "openlinktoken/core/ai/tokens"
ML1_ASSET_FILES = (
    "asset-manifest.json",
    "model.onnx",
    "model.onnx.data",
    "tokenizer.json",
)


def collect_ml1_assets(source_dir: str | Path) -> list[tuple[str, str]]:
    """Validate and return ML1 files for inclusion in a PyInstaller build."""
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

    asset_paths = []
    for filename in ML1_ASSET_FILES:
        asset_path = source_path / filename
        if not asset_path.is_file():
            raise FileNotFoundError(f"Missing ML1 asset: {asset_path}")
        if filename != "asset-manifest.json":
            _validate_asset(asset_path, asset_metadata.get(filename))
        asset_paths.append((str(asset_path), ML1_ASSET_DESTINATION))

    return asset_paths


def _validate_asset(asset_path: Path, metadata: Any) -> None:
    """Verify an ML1 asset matches the size and digest in its manifest."""
    if not isinstance(metadata, dict):
        raise ValueError(f"ML1 asset manifest has no metadata for {asset_path.name}")

    expected_size = metadata.get("size")
    expected_sha256 = metadata.get("sha256")
    actual_size = asset_path.stat().st_size
    if actual_size != expected_size:
        raise ValueError(
            f"ML1 asset {asset_path.name} has size {actual_size}; expected {expected_size}. "
            "The Git-LFS asset may not be hydrated."
        )

    actual_sha256 = _sha256_file(asset_path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"ML1 asset {asset_path.name} has SHA-256 {actual_sha256}; expected {expected_sha256}"
        )


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
