import hashlib
import json
import subprocess
import sys
import zipfile

import pytest
from packaging.version import Version

from openlinktoken_ext_truveta import EXTENSION_DESCRIPTION
from openlinktoken_ext_truveta.util.extension_bundles import (
    SUPPORTED_BUNDLE_TARGETS,
    create_extension_bundle_assets,
)
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


def _write_bundle_set(tmp_path, version):
    bundle_input_dir = tmp_path / "bundle-inputs"
    dependency_wheel_dir = bundle_input_dir / "dependencies"
    dependency_wheel_dir.mkdir(parents=True)
    wheel_version = str(Version(version))
    extension_wheel = bundle_input_dir / (
        f"openlinktoken_ext_truveta-{wheel_version}-py3-none-any.whl"
    )
    with zipfile.ZipFile(extension_wheel, "w") as archive:
        archive.writestr(
            f"openlinktoken_ext_truveta-{wheel_version}.dist-info/METADATA",
            "Metadata-Version: 2.1\n"
            "Name: openlinktoken-ext-truveta\n"
            f"Version: {version}\n",
        )
    dependency_wheel = dependency_wheel_dir / "requests-2.0.0-py3-none-any.whl"
    with zipfile.ZipFile(dependency_wheel, "w") as archive:
        archive.writestr(
            "requests-2.0.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: requests\nVersion: 2.0.0\n",
        )

    bundle_paths = []
    for target, python_abi in SUPPORTED_BUNDLE_TARGETS.items():
        bundle_path, _ = create_extension_bundle_assets(
            version,
            target,
            python_abi,
            extension_wheel,
            dependency_wheel_dir,
            tmp_path / "bundles" / target,
        )
        bundle_paths.append(bundle_path)
    return bundle_paths


def test_create_extension_release_assets_writes_checksummed_manifests(tmp_path):
    wheel_path, wheel_bytes = _write_wheel(tmp_path)
    bundle_paths = _write_bundle_set(tmp_path, "1.2.3")
    output_dir = tmp_path / "release-assets"

    created_paths = create_extension_release_assets(
        "1.2.3", wheel_path, bundle_paths, output_dir
    )

    assert [path.name for path in created_paths] == [
        f"{wheel_path.name}.sha256",
        BOOTSTRAP_MANIFEST_NAME,
        UPDATE_MANIFEST_NAME,
    ]
    assert (output_dir / f"{wheel_path.name}.sha256").read_text() == (
        f"{hashlib.sha256(wheel_bytes).hexdigest()}  {wheel_path.name}\n"
    )

    bootstrap = json.loads((output_dir / BOOTSTRAP_MANIFEST_NAME).read_text())
    assert bootstrap["schema_version"] == 2
    assert bootstrap["extension"]["name"] == "truveta"
    assert bootstrap["extension"]["version"] == "1.2.3"
    assert bootstrap["extension"]["update_manifest_url"].endswith(
        "/releases/latest/download/openlinktoken-ext-truveta-update.json"
    )
    assert "artifact_url" not in bootstrap["extension"]
    assert "sha256" not in bootstrap["extension"]
    assert bootstrap["core"] == {
        "min_version": "2.2.1",
        "max_version": "<3.0.0",
    }
    assert bootstrap["minimum_runtime_protocol"] == 2
    assert bootstrap["command_name"] == "truveta"
    assert bootstrap["description"] == EXTENSION_DESCRIPTION
    assert [bundle["target"] for bundle in bootstrap["bundles"]] == list(
        SUPPORTED_BUNDLE_TARGETS
    )
    for bundle, bundle_path in zip(bootstrap["bundles"], bundle_paths):
        assert bundle["python_abi"] == SUPPORTED_BUNDLE_TARGETS[bundle["target"]]
        assert bundle["url"].endswith(f"/releases/download/v1.2.3/{bundle_path.name}")
        assert bundle["sha256"] == hashlib.sha256(bundle_path.read_bytes()).hexdigest()

    update = json.loads((output_dir / UPDATE_MANIFEST_NAME).read_text())
    assert update["schema_version"] == 2
    assert update["extension"] == "truveta"
    assert update["latest_version"] == "1.2.3"
    assert update["requires_core"] == ">=2.2.1,<3.0.0"
    assert update["minimum_runtime_protocol"] == 2
    assert update["command_name"] == "truveta"
    assert update["description"] == EXTENSION_DESCRIPTION
    assert update["bundles"] == bootstrap["bundles"]


def test_prerelease_manifest_preserves_raw_version_and_normalized_wheel_name(
    tmp_path,
):
    wheel_bytes = b"prerelease wheel contents"
    wheel_path = tmp_path / "openlinktoken_ext_truveta-1.2.3rc1-py3-none-any.whl"
    wheel_path.write_bytes(wheel_bytes)
    bundle_paths = _write_bundle_set(tmp_path, "1.2.3-rc.1")
    output_dir = tmp_path / "release-assets"

    create_extension_release_assets("1.2.3-rc.1", wheel_path, bundle_paths, output_dir)

    bootstrap = json.loads((output_dir / BOOTSTRAP_MANIFEST_NAME).read_text())
    assert bootstrap["extension"]["version"] == "1.2.3-rc.1"
    assert bootstrap["bundles"][0]["url"].endswith(
        f"/releases/download/v1.2.3-rc.1/{bundle_paths[0].name}"
    )

    update = json.loads((output_dir / UPDATE_MANIFEST_NAME).read_text())
    assert update["latest_version"] == "1.2.3-rc.1"
    assert update["bundles"] == bootstrap["bundles"]


@pytest.mark.parametrize(
    "version",
    [
        "",
        "not-a-version",
        "1.2",
        "1.2.3-01",
        "1.2.3-foo..bar",
        "1.2.3+foo..bar",
        "1.2.3-.foo",
        "1.2.3+foo.",
        " 1.2.3 ",
    ],
)
def test_create_extension_release_assets_rejects_non_semver_before_writing(
    tmp_path, version
):
    wheel_path, _ = _write_wheel(tmp_path)
    output_dir = tmp_path / "release-assets"

    with pytest.raises(ValueError):
        create_extension_release_assets(version, wheel_path, [], output_dir)

    assert not output_dir.exists()


def test_create_extension_release_assets_writes_deterministic_bytes(tmp_path):
    wheel_path, _ = _write_wheel(tmp_path)
    bundle_paths = _write_bundle_set(tmp_path, "1.2.3")
    first_output_dir = tmp_path / "first-release-assets"
    second_output_dir = tmp_path / "second-release-assets"

    create_extension_release_assets("1.2.3", wheel_path, bundle_paths, first_output_dir)
    create_extension_release_assets(
        "1.2.3", wheel_path, bundle_paths, second_output_dir
    )

    first_assets = sorted(first_output_dir.iterdir(), key=lambda path: path.name)
    second_assets = sorted(second_output_dir.iterdir(), key=lambda path: path.name)
    assert [path.name for path in first_assets] == [path.name for path in second_assets]
    assert [path.read_bytes() for path in first_assets] == [
        path.read_bytes() for path in second_assets
    ]


def test_create_extension_release_assets_requires_each_target_bundle(tmp_path):
    wheel_path, _ = _write_wheel(tmp_path)
    bundle_paths = _write_bundle_set(tmp_path, "1.2.3")
    output_dir = tmp_path / "release-assets"

    with pytest.raises(ValueError, match="Missing extension bundle targets"):
        create_extension_release_assets(
            "1.2.3", wheel_path, bundle_paths[:-1], output_dir
        )

    assert not output_dir.exists()


def test_create_extension_release_assets_rejects_duplicate_target_bundles(tmp_path):
    wheel_path, _ = _write_wheel(tmp_path)
    bundle_paths = _write_bundle_set(tmp_path, "1.2.3")
    output_dir = tmp_path / "release-assets"

    with pytest.raises(ValueError, match="Duplicate extension bundle target"):
        create_extension_release_assets(
            "1.2.3", wheel_path, [*bundle_paths, bundle_paths[0]], output_dir
        )

    assert not output_dir.exists()


def test_create_extension_release_assets_rejects_missing_wheel_before_writing(
    tmp_path,
):
    output_dir = tmp_path / "release-assets"

    with pytest.raises(FileNotFoundError, match="Wheel not found"):
        create_extension_release_assets(
            "1.2.3", tmp_path / "missing.whl", [], output_dir
        )

    assert not output_dir.exists()


def test_version_validation_rejects_pathological_prerelease_without_backtracking():
    value = "0.0.0-0." + "--." * 2_000

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys\n"
                "from openlinktoken_ext_truveta.util.extension_manifests "
                "import _validate_version\n"
                "try:\n"
                "    _validate_version(sys.argv[1])\n"
                "except ValueError:\n"
                "    print('rejected')\n"
                "else:\n"
                "    print('accepted')\n"
            ),
            value,
        ],
        check=False,
        capture_output=True,
        timeout=1,
    )

    assert result.returncode == 0
    assert result.stdout == b"rejected\n"


def test_main_creates_release_assets(tmp_path):
    wheel_path, _ = _write_wheel(tmp_path)
    bundle_paths = _write_bundle_set(tmp_path, "1.2.3")
    output_dir = tmp_path / "release-assets"

    arguments = [
        "--version",
        "1.2.3",
        "--wheel",
        str(wheel_path),
    ]
    for bundle_path in bundle_paths:
        arguments.extend(["--bundle", str(bundle_path)])
    arguments.extend(["--output-dir", str(output_dir)])

    result = main(arguments)

    assert result == 0
    assert {path.name for path in output_dir.iterdir()} == {
        f"{wheel_path.name}.sha256",
        BOOTSTRAP_MANIFEST_NAME,
        UPDATE_MANIFEST_NAME,
    }
