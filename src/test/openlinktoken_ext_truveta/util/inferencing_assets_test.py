import hashlib
import json

import pytest

from openlinktoken_ext_truveta.util.inferencing_assets import (
    ML1_ASSET_FILES,
    copy_ml1_assets,
    validate_ml1_assets,
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
    (source_dir / "asset-manifest.json").write_text(
        json.dumps({"assets": assets}),
        encoding="utf-8",
    )


def _asset_contents():
    return {
        "model.onnx": b"model",
        "model.onnx.data": b"external-data",
        "tokenizer.json": b"tokenizer",
    }


def test_validates_oci_ml1_assets(tmp_path):
    _write_manifest(tmp_path, _asset_contents())

    paths = validate_ml1_assets(tmp_path)

    assert [path.name for path in paths] == list(ML1_ASSET_FILES)


def test_copies_verified_oci_ml1_assets_into_runtime_directory(tmp_path):
    source_dir = tmp_path / "oci-assets"
    source_dir.mkdir()
    asset_contents = _asset_contents()
    _write_manifest(source_dir, asset_contents)

    installed_paths = copy_ml1_assets(source_dir, tmp_path / "runtime" / "tokens")

    assert [path.name for path in installed_paths] == list(ML1_ASSET_FILES)
    assert installed_paths[0].read_text(encoding="utf-8") == json.dumps(
        {
            "assets": {
                name: {
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size": len(content),
                }
                for name, content in asset_contents.items()
            }
        }
    )
    for filename, content in asset_contents.items():
        assert (tmp_path / "runtime" / "tokens" / filename).read_bytes() == content


def test_rejects_missing_oci_asset(tmp_path):
    _write_manifest(tmp_path, _asset_contents())
    (tmp_path / "model.onnx.data").unlink()

    with pytest.raises(FileNotFoundError, match="model.onnx.data"):
        validate_ml1_assets(tmp_path)


def test_rejects_unhydrated_lfs_pointer(tmp_path):
    _write_manifest(tmp_path, _asset_contents())
    (tmp_path / "model.onnx.data").write_text(
        "version https://git-lfs.github.com/spec/v1\n"
        "oid sha256:placeholder\n"
        "size 1340579840\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="model.onnx.data"):
        validate_ml1_assets(tmp_path)


def test_rejects_invalid_manifest_shape(tmp_path):
    (tmp_path / "asset-manifest.json").write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="no valid assets map"):
        validate_ml1_assets(tmp_path)


def test_rejects_invalid_manifest_digest(tmp_path):
    _write_manifest(tmp_path, _asset_contents())
    manifest_path = tmp_path / "asset-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assets"]["tokenizer.json"]["sha256"] = "not-a-digest"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid SHA-256"):
        validate_ml1_assets(tmp_path)


def test_rejects_manifest_size_mismatch(tmp_path):
    _write_manifest(tmp_path, _asset_contents())
    manifest_path = tmp_path / "asset-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assets"]["model.onnx"]["size"] += 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="has size"):
        validate_ml1_assets(tmp_path)
