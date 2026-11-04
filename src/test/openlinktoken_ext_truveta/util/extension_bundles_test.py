import hashlib
import json
import zipfile

import pytest

from openlinktoken_ext_truveta.util.extension_bundles import (
    create_extension_bundle_assets,
)


def _write_wheel(path, distribution_name, version):
    normalized_name = distribution_name.replace("-", "_")
    dist_info = f"{normalized_name}-{version}.dist-info"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{dist_info}/METADATA",
            f"Metadata-Version: 2.1\nName: {distribution_name}\nVersion: {version}\n",
        )
    return path


def test_create_extension_bundle_assets_writes_flat_hash_locked_bundle(tmp_path):
    extension_wheel = _write_wheel(
        tmp_path / "openlinktoken_ext_truveta-1.2.3-py3-none-any.whl",
        "openlinktoken-ext-truveta",
        "1.2.3",
    )
    dependency_wheel_dir = tmp_path / "dependencies"
    dependency_wheel_dir.mkdir()
    dependency_wheel = _write_wheel(
        dependency_wheel_dir / "requests-2.0.0-py3-none-any.whl",
        "requests",
        "2.0.0",
    )

    bundle_path, checksum_path = create_extension_bundle_assets(
        "1.2.3",
        "linux-x64",
        "cp312",
        extension_wheel,
        dependency_wheel_dir,
        tmp_path / "assets",
    )

    assert bundle_path.name == "openlinktoken-ext-truveta-1.2.3-linux-x64-cp312.zip"
    assert checksum_path.read_text(encoding="utf-8") == (
        f"{hashlib.sha256(bundle_path.read_bytes()).hexdigest()}  {bundle_path.name}\n"
    )
    with zipfile.ZipFile(bundle_path) as archive:
        assert set(archive.namelist()) == {
            "bundle-manifest.json",
            extension_wheel.name,
            dependency_wheel.name,
        }
        manifest = json.loads(archive.read("bundle-manifest.json"))
        records = {record["name"]: record for record in manifest["wheels"]}
        assert manifest["schema_version"] == 1
        assert manifest["extension"] == {"name": "truveta", "version": "1.2.3"}
        assert manifest["target"] == "linux-x64"
        assert manifest["python_abi"] == "cp312"
        assert records["openlinktoken-ext-truveta"]["filename"] == extension_wheel.name
        assert records["openlinktoken-ext-truveta"]["tags"] == ["py3-none-any"]
        assert records["openlinktoken-ext-truveta"]["version"] == "1.2.3"
        assert (
            records["openlinktoken-ext-truveta"]["sha256"]
            == hashlib.sha256(extension_wheel.read_bytes()).hexdigest()
        )
        assert records["requests"]["version"] == "2.0.0"
        assert records["requests"]["tags"] == ["py3-none-any"]
        assert (
            records["requests"]["sha256"]
            == hashlib.sha256(dependency_wheel.read_bytes()).hexdigest()
        )


def test_create_extension_bundle_assets_rejects_core_distributions(tmp_path):
    extension_wheel = _write_wheel(
        tmp_path / "openlinktoken_ext_truveta-1.2.3-py3-none-any.whl",
        "openlinktoken-ext-truveta",
        "1.2.3",
    )
    dependency_wheel_dir = tmp_path / "dependencies"
    dependency_wheel_dir.mkdir()
    _write_wheel(
        dependency_wheel_dir / "openlinktoken-2.2.1-py3-none-any.whl",
        "openlinktoken",
        "2.2.1",
    )
    output_dir = tmp_path / "assets"

    with pytest.raises(ValueError, match="must not include OpenLinkToken core"):
        create_extension_bundle_assets(
            "1.2.3",
            "linux-x64",
            "cp312",
            extension_wheel,
            dependency_wheel_dir,
            output_dir,
        )

    assert not output_dir.exists()


def test_create_extension_bundle_assets_rejects_extension_version_mismatch(
    tmp_path,
):
    extension_wheel = _write_wheel(
        tmp_path / "openlinktoken_ext_truveta-9.9.9-py3-none-any.whl",
        "openlinktoken-ext-truveta",
        "9.9.9",
    )
    dependency_wheel_dir = tmp_path / "dependencies"
    dependency_wheel_dir.mkdir()

    with pytest.raises(ValueError, match="does not match release version"):
        create_extension_bundle_assets(
            "1.2.3",
            "linux-x64",
            "cp312",
            extension_wheel,
            dependency_wheel_dir,
            tmp_path / "assets",
        )
