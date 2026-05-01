"""
Copyright (c) Truveta. All rights reserved.

Unit tests for the logout command.
"""

import argparse
from unittest.mock import patch

from openlinktoken_ext_truveta.commands.logout import _logout


def _args() -> argparse.Namespace:
    return argparse.Namespace()


class TestLogoutCommand:
    def test_returns_zero(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.paths.Path.home", lambda: tmp_path
        )
        assert _logout(_args()) == 0

    def test_reports_no_credentials_when_dir_absent(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.paths.Path.home", lambda: tmp_path
        )
        _logout(_args())
        assert "No credentials found" in capsys.readouterr().out

    def test_deletes_single_credentials_file(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.paths.Path.home", lambda: tmp_path
        )
        cred_file = (
            tmp_path / ".openlinktoken" / "truveta" / "truveta.com" / "credentials.json"
        )
        cred_file.parent.mkdir(parents=True)
        cred_file.write_text('{"access_token": "x", "id_token": "y"}')

        with patch("openlinktoken_ext_truveta.commands.logout._revoke_token"):
            _logout(_args())

        assert not cred_file.exists()
        assert "Logged out. Deleted session information." in capsys.readouterr().out

    def test_deletes_multiple_credentials_files(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.paths.Path.home", lambda: tmp_path
        )
        for domain in ("truveta.com", "truveta-int.com"):
            f = tmp_path / ".openlinktoken" / "truveta" / domain / "credentials.json"
            f.parent.mkdir(parents=True)
            f.write_text('{"access_token": "x", "id_token": "y"}')

        with patch("openlinktoken_ext_truveta.commands.logout._revoke_token"):
            _logout(_args())

        out = capsys.readouterr().out
        assert "Logged out. Deleted session information." in out

    def test_deletes_session_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.paths.Path.home", lambda: tmp_path
        )
        session_file = tmp_path / ".openlinktoken" / "truveta" / "session.json"
        session_file.parent.mkdir(parents=True)
        session_file.write_text('{"domain": "truveta.com"}')

        _logout(_args())

        assert not session_file.exists()
