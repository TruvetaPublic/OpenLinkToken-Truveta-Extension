"""
Copyright (c) Truveta. All rights reserved.
"""

import hashlib
import zipfile
from pathlib import Path

import pytest

from openlinktoken_ext_truveta.util.release_assets import (
    _normalize_version,
    _resolve_release_asset_spec,
    _sha256_file,
    create_release_assets,
    main,
)


class TestNormalizeVersion:
    def test_strips_v_prefix(self):
        assert _normalize_version("v1.2.3") == "1.2.3"

    def test_passthrough_without_prefix(self):
        assert _normalize_version("1.2.3") == "1.2.3"

    def test_strips_whitespace(self):
        assert _normalize_version("  v1.0.0  ") == "1.0.0"

    def test_raises_on_empty(self):
        with pytest.raises(ValueError, match="Version cannot be empty"):
            _normalize_version("")

    def test_raises_on_only_v(self):
        with pytest.raises(ValueError, match="Version cannot be empty"):
            _normalize_version("v")


class TestResolveReleaseAssetSpec:
    @pytest.mark.parametrize(
        "runner_os, expected_executable, expected_package_name",
        [
            (
                "Linux",
                "olt",
                "olt-truveta-1.0.0-linux-x64",
            ),
            (
                "macOS",
                "olt",
                "olt-truveta-1.0.0-macos-arm64",
            ),
            (
                "Windows",
                "olt.exe",
                "olt-truveta-1.0.0-windows-x64",
            ),
        ],
    )
    def test_resolves_spec(
        self,
        runner_os,
        expected_executable,
        expected_package_name,
    ):
        spec = _resolve_release_asset_spec("1.0.0", runner_os)
        assert spec.executable_name == expected_executable
        assert spec.package_name == expected_package_name

    def test_case_insensitive_runner_os(self):
        spec_lower = _resolve_release_asset_spec("1.0.0", "linux")
        spec_mixed = _resolve_release_asset_spec("1.0.0", "Linux")
        assert spec_lower == spec_mixed

    def test_raises_on_unsupported_os(self):
        with pytest.raises(ValueError, match="Unsupported runner OS"):
            _resolve_release_asset_spec("1.0.0", "FreeBSD")

    def test_version_with_v_prefix_is_stripped(self):
        spec = _resolve_release_asset_spec("v1.2.3", "linux")
        assert "v1.2.3" not in spec.package_name
        assert "1.2.3" in spec.package_name


class TestCreateReleaseAssets:
    def _make_fake_executable(self, dist_dir: Path, name: str) -> Path:
        exe = dist_dir / name
        exe.write_bytes(b"fake-binary-content-for-testing")
        return exe

    def _make_fake_bundle(self, dist_dir: Path, name: str) -> Path:
        bundle_dir = dist_dir / "olt"
        bundle_dir.mkdir(parents=True)
        self._make_fake_executable(bundle_dir, name)
        (bundle_dir / "_internal").mkdir()
        return bundle_dir

    @pytest.mark.parametrize(
        "runner_os, exe_name",
        [
            ("Linux", "olt"),
            ("macOS", "olt"),
            ("Windows", "olt.exe"),
        ],
    )
    def test_creates_bundle_and_checksum_assets(self, tmp_path, runner_os, exe_name):
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        self._make_fake_bundle(dist_dir, exe_name)

        output_dir = tmp_path / "release-assets"
        assets = create_release_assets("1.0.0", runner_os, dist_dir, output_dir)

        assert len(assets) == 2
        assert assets[0].name.endswith(".zip")
        assert assets[1].name.endswith(".zip.sha256")
        assert sorted(path.name for path in output_dir.iterdir()) == sorted(
            path.name for path in assets
        )

    def test_zip_contains_executable(self, tmp_path):
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        self._make_fake_bundle(dist_dir, "olt")

        output_dir = tmp_path / "release-assets"
        assets = create_release_assets("1.0.0", "Linux", dist_dir, output_dir)

        zip_path = next(p for p in assets if p.suffix == ".zip")
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert any("olt" in n for n in names)

    def test_zip_contains_complete_one_folder_bundle(self, tmp_path):
        dist_dir = tmp_path / "dist"
        bundle_dir = dist_dir / "olt"
        internal_dir = bundle_dir / "_internal" / "openlinktoken"
        internal_dir.mkdir(parents=True)
        self._make_fake_executable(bundle_dir, "olt")
        (internal_dir / "model.onnx.data").write_bytes(b"model-data")

        output_dir = tmp_path / "release-assets"
        assets = create_release_assets("1.0.0", "Linux", dist_dir, output_dir)

        zip_path = next(p for p in assets if p.suffix == ".zip")
        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())

        assert "olt-truveta-1.0.0-linux-x64/olt" in names
        assert (
            "olt-truveta-1.0.0-linux-x64/_internal/openlinktoken/model.onnx.data"
            in names
        )

    def test_sha256_sidecar_content(self, tmp_path):
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        self._make_fake_bundle(dist_dir, "olt")

        output_dir = tmp_path / "release-assets"
        assets = create_release_assets("1.0.0", "Linux", dist_dir, output_dir)

        zip_path = assets[0]
        checksum_file = assets[1]

        expected_hash = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        checksum_content = checksum_file.read_text()
        assert checksum_content.startswith(expected_hash)
        assert zip_path.name in checksum_content

    def test_rejects_raw_executable(self, tmp_path):
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        (dist_dir / "olt").write_bytes(b"raw executable")
        output_dir = tmp_path / "release-assets"

        with pytest.raises(FileNotFoundError, match="one-folder bundle"):
            create_release_assets("1.0.0", "Linux", dist_dir, output_dir)

    def test_raises_when_executable_missing(self, tmp_path):
        dist_dir = tmp_path / "dist"
        (dist_dir / "olt").mkdir(parents=True)
        output_dir = tmp_path / "release-assets"

        with pytest.raises(FileNotFoundError, match="Expected built executable"):
            create_release_assets("1.0.0", "Linux", dist_dir, output_dir)

    def test_rejects_bundle_without_runtime_directory(self, tmp_path):
        dist_dir = tmp_path / "dist"
        bundle_dir = dist_dir / "olt"
        bundle_dir.mkdir(parents=True)
        (bundle_dir / "olt").write_bytes(b"binary")
        output_dir = tmp_path / "release-assets"

        with pytest.raises(FileNotFoundError, match="runtime directory"):
            create_release_assets("1.0.0", "Linux", dist_dir, output_dir)

    def test_output_dir_created_if_absent(self, tmp_path):
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        self._make_fake_bundle(dist_dir, "olt")

        output_dir = tmp_path / "nonexistent" / "release-assets"
        create_release_assets("1.0.0", "Linux", dist_dir, output_dir)

        assert output_dir.is_dir()


class TestSha256File:
    def test_produces_hex_digest(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello")
        digest = _sha256_file(f)
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_consistent_for_same_content(self, tmp_path):
        f1 = tmp_path / "a.bin"
        f2 = tmp_path / "b.bin"
        f1.write_bytes(b"same content")
        f2.write_bytes(b"same content")
        assert _sha256_file(f1) == _sha256_file(f2)

    def test_different_for_different_content(self, tmp_path):
        f1 = tmp_path / "a.bin"
        f2 = tmp_path / "b.bin"
        f1.write_bytes(b"content a")
        f2.write_bytes(b"content b")
        assert _sha256_file(f1) != _sha256_file(f2)


class TestMain:
    def test_main_runs_end_to_end(self, tmp_path):
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        bundle_dir = dist_dir / "olt"
        bundle_dir.mkdir()
        (bundle_dir / "olt").write_bytes(b"binary")
        (bundle_dir / "_internal").mkdir()

        output_dir = tmp_path / "out"
        result = main(
            [
                "--version",
                "1.0.0",
                "--runner-os",
                "Linux",
                "--dist-dir",
                str(dist_dir),
                "--output-dir",
                str(output_dir),
            ]
        )
        assert result == 0
        assert output_dir.is_dir()
        assert len(list(output_dir.iterdir())) == 2
