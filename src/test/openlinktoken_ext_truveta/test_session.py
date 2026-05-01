"""
Copyright (c) Truveta. All rights reserved.

Unit tests for session persistence helpers.
"""

import json

from openlinktoken_ext_truveta.session import (
    clear_session,
    read_session_domain,
    write_session_domain,
)


class TestSessionPersistence:
    def test_write_and_read_session_domain(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.paths.Path.home",
            lambda: tmp_path,
        )

        write_session_domain("dev.truveta-int.com")

        assert read_session_domain() == "dev.truveta-int.com"

    def test_write_session_domain_preserves_existing_fields(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.paths.Path.home",
            lambda: tmp_path,
        )
        session_file = tmp_path / ".openlinktoken" / "truveta" / "session.json"
        session_file.parent.mkdir(parents=True, exist_ok=True)
        session_file.write_text(json.dumps({"login_hint": "alice@example.com"}))

        write_session_domain("truveta.com")

        session_data = json.loads(session_file.read_text())
        assert session_data["domain"] == "truveta.com"
        assert session_data["login_hint"] == "alice@example.com"

    def test_read_session_domain_returns_none_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.paths.Path.home",
            lambda: tmp_path,
        )

        assert read_session_domain() is None

    def test_clear_session_removes_session_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "openlinktoken_ext_truveta.paths.Path.home",
            lambda: tmp_path,
        )

        write_session_domain("truveta.com")
        clear_session()

        assert read_session_domain() is None
