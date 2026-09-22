import hashlib
import json

import pytest

from openlinktoken_ext_truveta.util.extension_manifests import (
    BOOTSTRAP_MANIFEST_NAME,
    UPDATE_MANIFEST_NAME,
    create_extension_release_assets,
    main,
)


def _write_wheel(tmp_path):
    wheel_bytes = b"wheel contents"
    wheel_path = tmp_path / "openlinktoken_ext_truveta-1.2.3-py3-none-any.whl"
    wheel_path.write_bytes(wheel_bytes)
    return wheel_path, wheel_bytes


def test_create_extension_release_assets_writes_checksummed_manifests(tmp_path):
    wheel_path, wheel_bytes = _write_wheel(tmp_path)
    output_dir = tmp_path / "release-assets"

    created_paths = create_extension_release_assets("1.2.3", wheel_path, output_dir)

    assert [path.name for path in created_paths] == [
        f"{wheel_path.name}.sha256",
        BOOTSTRAP_MANIFEST_NAME,
        UPDATE_MANIFEST_NAME,
    ]
    assert (output_dir / f"{wheel_path.name}.sha256").read_text() == (
        f"{hashlib.sha256(wheel_bytes).hexdigest()}  {wheel_path.name}\n"
    )

    bootstrap = json.loads((output_dir / BOOTSTRAP_MANIFEST_NAME).read_text())
    assert bootstrap["schema_version"] == 1
    assert bootstrap["extension"]["name"] == "truveta"
    assert bootstrap["extension"]["version"] == "1.2.3"
    assert bootstrap["extension"]["update_manifest_url"].endswith(
        "/releases/latest/download/openlinktoken-ext-truveta-update.json"
    )
    assert bootstrap["extension"]["artifact_url"].endswith(
        f"/releases/download/v1.2.3/{wheel_path.name}"
    )
    assert bootstrap["extension"]["sha256"] == hashlib.sha256(wheel_bytes).hexdigest()
    assert bootstrap["core"] == {
        "min_version": "2.2.0",
        "max_version": "<3.0.0",
    }

    update = json.loads((output_dir / UPDATE_MANIFEST_NAME).read_text())
    assert update["schema_version"] == 1
    assert update["extension"] == "truveta"
    assert update["latest_version"] == "1.2.3"
    assert update["requires_core"] == ">=2.2.0,<3.0.0"
    assert update["artifacts"][0]["sha256"] == hashlib.sha256(wheel_bytes).hexdigest()
    assert update["artifacts"][0]["version"] == "1.2.3"
    assert update["artifacts"][0]["url"].endswith(
        f"/releases/download/v1.2.3/{wheel_path.name}"
    )


@pytest.mark.parametrize("version", ["", "not-a-version", "1.2"])
def test_create_extension_release_assets_rejects_non_semver_before_writing(
    tmp_path, version
):
    wheel_path, _ = _write_wheel(tmp_path)
    output_dir = tmp_path / "release-assets"

    with pytest.raises(ValueError):
        create_extension_release_assets(version, wheel_path, output_dir)

    assert not output_dir.exists()


def test_main_creates_release_assets(tmp_path):
    wheel_path, _ = _write_wheel(tmp_path)
    output_dir = tmp_path / "release-assets"

    result = main(
        [
            "--version",
            "1.2.3",
            "--wheel",
            str(wheel_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert result == 0
    assert {path.name for path in output_dir.iterdir()} == {
        f"{wheel_path.name}.sha256",
        BOOTSTRAP_MANIFEST_NAME,
        UPDATE_MANIFEST_NAME,
    }
