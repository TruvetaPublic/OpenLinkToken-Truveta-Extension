import hashlib
import json

import pytest

from openlinktoken_ext_truveta.util.inferencing_assets import (
    ML1_ASSET_DESTINATION,
    collect_ml1_assets,
)


def _write_manifest(source_dir, asset_contents):
    assets = {}
    for filename, content in asset_contents.items():
        path = source_dir / filename
        path.write_bytes(content)
        assets[filename] = {
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        }
    (source_dir / "asset-manifest.json").write_text(json.dumps({"assets": assets}))


def test_collect_ml1_assets_returns_all_runtime_files(tmp_path):
    asset_contents = {
        "model.onnx": b"model",
        "model.onnx.data": b"external-data",
        "tokenizer.json": b"tokenizer",
    }
    _write_manifest(tmp_path, asset_contents)

    assets = collect_ml1_assets(tmp_path)

    assert assets == [
        (str(tmp_path / "asset-manifest.json"), ML1_ASSET_DESTINATION),
        (str(tmp_path / "model.onnx"), ML1_ASSET_DESTINATION),
        (str(tmp_path / "model.onnx.data"), ML1_ASSET_DESTINATION),
        (str(tmp_path / "tokenizer.json"), ML1_ASSET_DESTINATION),
    ]


def test_collect_ml1_assets_rejects_unhydrated_lfs_pointer(tmp_path):
    asset_contents = {
        "model.onnx": b"model",
        "model.onnx.data": b"external-data",
        "tokenizer.json": b"tokenizer",
    }
    _write_manifest(tmp_path, asset_contents)
    (tmp_path / "model.onnx.data").write_text(
        "version https://git-lfs.github.com/spec/v1\n"
        "oid sha256:placeholder\n"
        "size 1340579840\n"
    )

    with pytest.raises(ValueError, match="model.onnx.data"):
        collect_ml1_assets(tmp_path)


def test_collect_ml1_assets_rejects_invalid_manifest_shape(tmp_path):
    (tmp_path / "asset-manifest.json").write_text("[]")

    with pytest.raises(ValueError, match="no valid assets map"):
        collect_ml1_assets(tmp_path)
