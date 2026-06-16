"""
Copyright (c) Truveta. All rights reserved.

Unit tests for shared path helpers.
"""

from datetime import date

from openlinktoken_ext_truveta.paths import (
    openlinktoken_root_dir,
    private_key_path,
    public_key_path,
    session_file_path,
    truveta_root_dir,
)


class TestOpenLinkTokenRootResolution:
    def test_uses_cli_home_resolver(self, tmp_path, monkeypatch):
        expected_home = tmp_path / "cli-home"
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.paths.get_openlinktoken_home",
            lambda: expected_home,
            raising=False,
        )

        assert openlinktoken_root_dir() == expected_home

    def test_derives_child_paths_from_cli_home(self, tmp_path, monkeypatch):
        expected_home = tmp_path / "cli-home"
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.paths.get_openlinktoken_home",
            lambda: expected_home,
            raising=False,
        )
        key_date = date(2026, 4, 27)

        assert truveta_root_dir() == expected_home / "truveta"
        assert session_file_path() == expected_home / "truveta" / "session.json"
        assert private_key_path(key_date=key_date) == (
            expected_home / "openlinktoken-2026-04-27.private.pem"
        )
        assert public_key_path(key_date=key_date) == (
            expected_home / "openlinktoken-2026-04-27.public.pem"
        )
