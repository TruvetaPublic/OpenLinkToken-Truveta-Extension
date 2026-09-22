"""
Copyright (c) Truveta. All rights reserved.

Regression tests for persistent registry seeding in frozen bundles.
"""

from pathlib import Path

from openlinktoken_ext_truveta.standalone_runtime_hook import (
    _seed_persistent_registry,
)


REPOSITORY_ROOT = Path(__file__).parents[3]
RUNTIME_HOOK_PATH = (
    REPOSITORY_ROOT
    / "src"
    / "main"
    / "openlinktoken_ext_truveta"
    / "standalone_runtime_hook.py"
)


def _write_embedded_registry(bundle_root: Path, content: bytes) -> Path:
    embedded_registry = bundle_root / "openlinktoken" / "extensions" / "registry.json"
    embedded_registry.parent.mkdir(parents=True)
    embedded_registry.write_bytes(content)
    return embedded_registry


def test_seeds_missing_persistent_registry(monkeypatch, tmp_path):
    """A missing persistent registry is copied from the frozen bundle."""
    content = b'{"truveta": {"version": "1.0.0"}}\n'
    _write_embedded_registry(tmp_path / "bundle", content)
    monkeypatch.setenv("OLT_EXTENSIONS_DIR", str(tmp_path / "persistent"))

    _seed_persistent_registry(tmp_path / "bundle")

    assert (tmp_path / "persistent" / "registry.json").read_bytes() == content


def test_preserves_existing_persistent_registry(monkeypatch, tmp_path):
    """An existing registry is not replaced by the embedded bundle registry."""
    embedded_content = b'{"truveta": {"version": "1.0.0"}}\n'
    updated_content = b'{"truveta": {"version": "1.1.0", "disabled": true}}\n'
    _write_embedded_registry(tmp_path / "bundle", embedded_content)
    persistent_registry = tmp_path / "persistent" / "registry.json"
    persistent_registry.parent.mkdir(parents=True)
    persistent_registry.write_bytes(updated_content)
    monkeypatch.setenv("OLT_EXTENSIONS_DIR", str(persistent_registry.parent))

    _seed_persistent_registry(tmp_path / "bundle")

    assert persistent_registry.read_bytes() == updated_content


def test_preserves_existing_empty_persistent_registry(monkeypatch, tmp_path):
    """An existing empty registry remains empty so an explicit uninstall persists."""
    _write_embedded_registry(tmp_path / "bundle", b'{"truveta": {}}\n')
    persistent_registry = tmp_path / "persistent" / "registry.json"
    persistent_registry.parent.mkdir(parents=True)
    persistent_registry.touch()
    monkeypatch.setenv("OLT_EXTENSIONS_DIR", str(persistent_registry.parent))

    _seed_persistent_registry(tmp_path / "bundle")

    assert persistent_registry.read_bytes() == b""


def test_runtime_hook_does_not_assign_extensions_directory():
    """The runtime hook leaves extension-directory selection to the core CLI."""
    source = RUNTIME_HOOK_PATH.read_text(encoding="utf-8")

    assert "OLT_EXTENSIONS_DIR" not in source
