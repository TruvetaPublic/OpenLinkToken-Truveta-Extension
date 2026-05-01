"""
Copyright (c) Truveta. All rights reserved.

Unit tests for TruvetaExtension.
"""

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

from openlinktoken_ext_truveta.auth import AuthError, Credentials
from openlinktoken_ext_truveta.extension import TruvetaExtension

# ---------------------------------------------------------------------------
# Tests: properties
# ---------------------------------------------------------------------------


class TestTruvetaProperties:
    """Tests for TruvetaExtension abstract-property implementations."""

    def setup_method(self):
        self.ext = TruvetaExtension()

    def test_command_name(self):
        assert self.ext.command_name == "truveta"

    def test_description(self):
        assert self.ext.description == "Truveta-specific Open Link Token commands"

    def test_version(self):
        assert self.ext.version == "0.1.0"


# ---------------------------------------------------------------------------
# Tests: register_subcommand
# ---------------------------------------------------------------------------


class TestRegisterSubcommand:
    """Tests that register_subcommand adds the expected parsers."""

    def _build_parser(self):
        root = argparse.ArgumentParser()
        subparsers = root.add_subparsers(dest="command")
        TruvetaExtension().register_subcommand(subparsers)
        return root

    def test_adds_truveta_parser(self):
        root = argparse.ArgumentParser()
        subparsers = root.add_subparsers(dest="command")
        ext = TruvetaExtension()

        ext.register_subcommand(subparsers)

        assert "truveta" in subparsers.choices

    def test_login_subcommand_present(self):
        root = self._build_parser()
        parsed = root.parse_args(["truveta", "login"])
        assert parsed.func == TruvetaExtension._login

    def test_logout_subcommand_removed(self):
        root = self._build_parser()
        with patch("sys.stderr"):
            try:
                root.parse_args(["truveta", "logout"])
            except SystemExit as exc:
                assert exc.code == 2
                return

        raise AssertionError("Expected parse_args to reject removed logout command")

    def test_package_subcommand_removed(self):
        root = self._build_parser()
        with patch("sys.stderr"):
            try:
                root.parse_args(
                    [
                        "truveta",
                        "package",
                        "--input",
                        "input.csv",
                        "--output",
                        "output.csv",
                    ]
                )
            except SystemExit as exc:
                assert exc.code == 2
                return

        raise AssertionError("Expected parse_args to reject removed package command")

    def test_initiate_exchange_subcommand_present(self):
        root = self._build_parser()
        parsed = root.parse_args(["truveta", "initiate-exchange"])
        assert parsed.func == TruvetaExtension._initiate_exchange

    def test_upload_subcommand_present(self):
        root = self._build_parser()
        parsed = root.parse_args(["truveta", "upload", "--file", "input.csv"])
        assert parsed.func == TruvetaExtension._upload

    def test_upload_accepts_optional_metadata_flag(self):
        root = self._build_parser()
        parsed = root.parse_args(
            [
                "truveta",
                "upload",
                "--file",
                "input.csv",
                "--metadata",
                "input.metadata.json",
            ]
        )
        assert parsed.file == "input.csv"
        assert parsed.metadata == "input.metadata.json"

    def test_upload_does_not_accept_removed_optional_flags(self):
        root = self._build_parser()
        with patch("sys.stderr"):
            try:
                root.parse_args(
                    [
                        "truveta",
                        "upload",
                        "--file",
                        "input.csv",
                        "--embassy",
                        "pro",
                    ]
                )
            except SystemExit as exc:
                assert exc.code == 2
                return

        raise AssertionError("Expected parse_args to reject removed upload flags")

    def test_upload_accepts_supported_flags_only(self):
        root = self._build_parser()
        parsed = root.parse_args(
            [
                "truveta",
                "upload",
                "--file",
                "input.csv",
                "--metadata",
                "input.metadata.json",
            ]
        )

        assert parsed.file == "input.csv"
        assert parsed.metadata == "input.metadata.json"

    def test_login_accepts_domain_flag(self):
        root = self._build_parser()
        parsed = root.parse_args(
            ["truveta", "login", "--domain", "https://api.dev.truveta-int.com"]
        )
        assert parsed.domain == "https://api.dev.truveta-int.com"

    def test_initiate_exchange_rejects_domain_override_flags(self):
        root = self._build_parser()

        with patch("sys.stderr"):
            try:
                root.parse_args(
                    [
                        "truveta",
                        "initiate-exchange",
                        "--domain",
                        "https://api.dev.truveta-int.com",
                    ]
                )
            except SystemExit as exc:
                assert exc.code == 2
                return

        raise AssertionError("Expected parse_args to reject initiate-exchange --domain")

    def test_upload_rejects_domain_override_flags(self):
        root = self._build_parser()

        with patch("sys.stderr"):
            try:
                root.parse_args(
                    [
                        "truveta",
                        "upload",
                        "--file",
                        "input.csv",
                        "--domain",
                        "https://api.dev.truveta-int.com",
                    ]
                )
            except SystemExit as exc:
                assert exc.code == 2
                return

        raise AssertionError("Expected parse_args to reject upload --domain")

    def test_login_accepts_force_flag(self):
        root = self._build_parser()
        parsed = root.parse_args(["truveta", "login", "--force"])
        assert parsed.force is True

    def test_login_rejects_auth_domain_flag(self):
        root = self._build_parser()
        with patch("sys.stderr"):
            try:
                root.parse_args(
                    [
                        "truveta",
                        "login",
                        "--domain",
                        "http://localhost:8080",
                        "--auth-domain",
                        "https://api.dev.truveta-int.com",
                    ]
                )
            except SystemExit as exc:
                assert exc.code == 2
                return

        raise AssertionError("Expected parse_args to reject login --auth-domain")

    def test_initiate_exchange_rejects_api_domain_flag(self):
        root = self._build_parser()

        with patch("sys.stderr"):
            try:
                root.parse_args(
                    [
                        "truveta",
                        "initiate-exchange",
                        "--api-domain",
                        "http://localhost:8080",
                    ]
                )
            except SystemExit as exc:
                assert exc.code == 2
                return

        raise AssertionError(
            "Expected parse_args to reject initiate-exchange --api-domain"
        )

    def test_initiate_exchange_accepts_local_dev_flag(self):
        root = self._build_parser()
        parsed = root.parse_args(
            [
                "truveta",
                "initiate-exchange",
                "--local-dev",
            ]
        )

        assert parsed.local_dev is True

    def test_initiate_exchange_rejects_force_flag(self):
        root = self._build_parser()

        with patch("sys.stderr"):
            try:
                root.parse_args(
                    [
                        "truveta",
                        "initiate-exchange",
                        "--force",
                    ]
                )
            except SystemExit as exc:
                assert exc.code == 2
                return

        raise AssertionError("Expected parse_args to reject initiate-exchange --force")

    def test_upload_rejects_api_domain_flag(self):
        root = self._build_parser()

        with patch("sys.stderr"):
            try:
                root.parse_args(
                    [
                        "truveta",
                        "upload",
                        "--file",
                        "input.csv",
                        "--api-domain",
                        "http://localhost:8080",
                    ]
                )
            except SystemExit as exc:
                assert exc.code == 2
                return

        raise AssertionError("Expected parse_args to reject upload --api-domain")

    def test_upload_accepts_local_dev_flag(self):
        root = self._build_parser()
        parsed = root.parse_args(
            [
                "truveta",
                "upload",
                "--file",
                "input.csv",
                "--local-dev",
            ]
        )
        assert parsed.local_dev is True

    def test_upload_rejects_auth_domain_flag(self):
        root = self._build_parser()
        with patch("sys.stderr"):
            try:
                root.parse_args(
                    [
                        "truveta",
                        "upload",
                        "--file",
                        "input.csv",
                        "--auth-domain",
                        "https://api.dev.truveta-int.com",
                    ]
                )
            except SystemExit as exc:
                assert exc.code == 2
                return

        raise AssertionError("Expected parse_args to reject upload --auth-domain")

    def test_pyproject_uses_openlinktoken_entrypoint_only(self):
        pyproject_path = Path(__file__).resolve().parents[3] / "pyproject.toml"
        pyproject_text = pyproject_path.read_text()

        assert '[project.entry-points."openlinktoken.extensions"]' in pyproject_text
        assert '[project.entry-points."opentoken.extensions"]' not in pyproject_text

    def test_no_subcommand_calls_help(self):
        root = self._build_parser()
        parsed = root.parse_args(["truveta"])
        assert callable(parsed.func)


# ---------------------------------------------------------------------------
# Tests: _login dispatch
# ---------------------------------------------------------------------------

_FAKE_ID_TOKEN = (
    "eyJhbGciOiJSUzI1NiJ9"
    ".eyJuYW1lIjoiVGVzdCBVc2VyIiwiZW1haWwiOiJ0ZXN0QGV4YW1wbGUuY29tIiwiZXhwIjo5OTk5OTk5OTk5fQ"
    ".fakesig"
)
_FAKE_CREDS = Credentials(access_token="acc", id_token=_FAKE_ID_TOKEN)


class TestLoginDispatch:
    """Tests for TruvetaExtension._login static method."""

    def test_login_returns_zero_on_success(self, capsys):
        args = MagicMock()
        args.domain = "https://api.truveta.com"
        args.force = False

        with patch(
            "openlinktoken_ext_truveta.commands.login.ensure_auth",
            return_value=_FAKE_CREDS,
        ):
            result = TruvetaExtension._login(args)

        assert result == 0
        assert "successfully logged in" in capsys.readouterr().out

    def test_login_returns_one_on_auth_error(self, capsys):
        args = MagicMock()
        args.domain = "https://api.truveta.com"
        args.force = False

        with patch(
            "openlinktoken_ext_truveta.commands.login.ensure_auth",
            side_effect=AuthError("boom"),
        ):
            result = TruvetaExtension._login(args)

        assert result == 1
        assert "boom" in capsys.readouterr().err


class TestInitiateExchangeDispatch:
    """Tests for TruvetaExtension._initiate_exchange static method."""

    def test_initiate_exchange_returns_zero_on_success(self, capsys):
        args = MagicMock()
        args.domain = "https://api.truveta.com"
        args.force = False

        with (
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.ensure_auth",
                return_value=_FAKE_CREDS,
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.load_or_generate_domain_keys",
                return_value=("private", "public"),
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.call_exchange_endpoint",
                return_value={
                    "exchangeName": "name",
                    "exchangeId": "id",
                    "hashingSecret": "secret",
                    "hashingSecretEncoding": "base64",
                    "serverPublicKey": "key",
                },
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.build_exchange_config",
                return_value={"payload": {}},
            ),
            patch(
                "openlinktoken_ext_truveta.commands.initiate_exchange.write_exchange_config",
                return_value="/tmp/exchange.json",
            ),
        ):
            result = TruvetaExtension._initiate_exchange(args)

        assert result == 0
        out = capsys.readouterr().out
        assert "Exchange config written to:" in out
