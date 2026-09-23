from importlib.metadata import PackageNotFoundError

import pytest

from openlinktoken_ext_truveta.compatibility import (
    CORE_DISTRIBUTIONS,
    SUPPORTED_CORE_SPECIFIER,
    ExtensionCompatibilityError,
    installed_distribution_versions,
    validate_runtime_compatibility,
)


def test_declares_supported_core_contract():
    """The extension declares the supported core version range and distributions."""
    assert SUPPORTED_CORE_SPECIFIER == ">=2.2.0,<3.0.0"
    assert CORE_DISTRIBUTIONS == (
        "openlinktoken",
        "openlinktoken-cli",
        "openlinktoken-core-ai",
    )


def test_accepts_core_distributions_in_supported_range(monkeypatch):
    """Runtime validation accepts every required distribution in the supported range."""
    versions = {
        "openlinktoken": "2.2.0",
        "openlinktoken-cli": "2.4.1",
        "openlinktoken-core-ai": "2.9.0",
    }
    monkeypatch.setattr(
        "openlinktoken_ext_truveta.compatibility.version",
        versions.__getitem__,
    )

    validate_runtime_compatibility()


def test_rejects_core_distribution_outside_supported_range(monkeypatch):
    """Runtime validation reports a required distribution outside the supported range."""
    versions = {
        "openlinktoken": "3.0.0",
        "openlinktoken-cli": "2.2.0",
        "openlinktoken-core-ai": "2.2.0",
    }
    monkeypatch.setattr(
        "openlinktoken_ext_truveta.compatibility.version",
        versions.__getitem__,
    )

    with pytest.raises(ExtensionCompatibilityError, match="openlinktoken 3.0.0"):
        validate_runtime_compatibility()


def test_rejects_missing_core_distribution(monkeypatch):
    """Runtime validation reports a required distribution that is not installed."""

    def missing(name):
        if name == "openlinktoken-cli":
            raise PackageNotFoundError(name)
        return "2.2.0"

    monkeypatch.setattr(
        "openlinktoken_ext_truveta.compatibility.version",
        missing,
    )

    with pytest.raises(ExtensionCompatibilityError, match="openlinktoken-cli"):
        validate_runtime_compatibility()


def test_lists_only_installed_core_distribution_versions(monkeypatch):
    """Version discovery returns only the installed distributions in the core contract."""
    versions = {
        "openlinktoken": "2.2.0",
        "openlinktoken-cli": "2.4.1",
        "openlinktoken-core-ai": "2.9.0",
    }
    monkeypatch.setattr(
        "openlinktoken_ext_truveta.compatibility.version",
        versions.__getitem__,
    )

    assert installed_distribution_versions() == versions


def test_rejects_invalid_core_distribution_version(monkeypatch):
    """Runtime validation reports an installed distribution with an invalid version."""
    versions = {
        "openlinktoken": "not-a-version",
        "openlinktoken-cli": "2.2.0",
        "openlinktoken-core-ai": "2.2.0",
    }
    monkeypatch.setattr(
        "openlinktoken_ext_truveta.compatibility.version",
        versions.__getitem__,
    )

    with pytest.raises(
        ExtensionCompatibilityError, match="openlinktoken not-a-version"
    ):
        validate_runtime_compatibility()


def test_accepts_core_metadata_available_on_frozen_search_path(tmp_path, monkeypatch):
    """Runtime validation reads distribution metadata copied into a frozen bundle."""
    for distribution, installed_version in {
        "openlinktoken": "2.2.0",
        "openlinktoken-cli": "2.4.1",
        "openlinktoken-core-ai": "2.9.0",
    }.items():
        metadata_dir = (
            tmp_path / f"{distribution.replace('-', '_')}-{installed_version}.dist-info"
        )
        metadata_dir.mkdir()
        (metadata_dir / "METADATA").write_text(
            f"Metadata-Version: 2.1\nName: {distribution}\nVersion: {installed_version}\n",
            encoding="utf-8",
        )

    monkeypatch.syspath_prepend(str(tmp_path))

    validate_runtime_compatibility()
