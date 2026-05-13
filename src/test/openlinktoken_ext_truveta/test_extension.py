"""
Copyright (c) Truveta. All rights reserved.

Unit tests for TruvetaExtension.
"""

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

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

    def test_logout_subcommand_present(self):
        root = self._build_parser()
        parsed = root.parse_args(["truveta", "logout"])
        assert parsed.func == TruvetaExtension._logout

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
        parsed = root.parse_args(["truveta", "upload", "--input", "input.csv"])
        assert parsed.func == TruvetaExtension._upload

    def test_upload_accepts_optional_metadata_flag(self):
        root = self._build_parser()
        parsed = root.parse_args(
            [
                "truveta",
                "upload",
                "--input",
                "input.csv",
                "--metadata",
                "input.metadata.json",
            ]
        )
        assert parsed.input == "input.csv"
        assert parsed.metadata == "input.metadata.json"

    def test_upload_does_not_accept_removed_optional_flags(self):
        root = self._build_parser()
        with patch("sys.stderr"):
            try:
                root.parse_args(
                    [
                        "truveta",
                        "upload",
                        "--input",
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
                "--input",
                "input.csv",
                "--metadata",
                "input.metadata.json",
            ]
        )

        assert parsed.input == "input.csv"
        assert parsed.metadata == "input.metadata.json"

    def test_login_accepts_domain_flag(self):
        root = self._build_parser()
        parsed = root.parse_args(
            ["truveta", "login", "--domain", "dev.truveta-int.com"]
        )
        assert parsed.domain == "dev.truveta-int.com"

    def test_initiate_exchange_rejects_domain_override_flags(self):
        root = self._build_parser()

        with patch("sys.stderr"):
            try:
                root.parse_args(
                    [
                        "truveta",
                        "initiate-exchange",
                        "--domain",
                        "dev.truveta-int.com",
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
                        "--input",
                        "input.csv",
                        "--domain",
                        "dev.truveta-int.com",
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
                        "dev.truveta-int.com",
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

    def test_initiate_exchange_rejects_local_dev_flag(self):
        root = self._build_parser()

        with patch("sys.stderr"):
            try:
                root.parse_args(
                    [
                        "truveta",
                        "initiate-exchange",
                        "--local-dev",
                    ]
                )
            except SystemExit as exc:
                assert exc.code == 2
                return

        raise AssertionError(
            "Expected parse_args to reject initiate-exchange --local-dev"
        )

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
                        "--input",
                        "input.csv",
                        "--api-domain",
                        "http://localhost:8080",
                    ]
                )
            except SystemExit as exc:
                assert exc.code == 2
                return

        raise AssertionError("Expected parse_args to reject upload --api-domain")

    def test_upload_rejects_local_dev_flag(self):
        root = self._build_parser()

        with patch("sys.stderr"):
            try:
                root.parse_args(
                    [
                        "truveta",
                        "upload",
                        "--input",
                        "input.csv",
                        "--local-dev",
                    ]
                )
            except SystemExit as exc:
                assert exc.code == 2
                return

        raise AssertionError("Expected parse_args to reject upload --local-dev")

    def test_upload_rejects_auth_domain_flag(self):
        root = self._build_parser()
        with patch("sys.stderr"):
            try:
                root.parse_args(
                    [
                        "truveta",
                        "upload",
                        "--input",
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


class TestLoginDispatch:
    """Tests for TruvetaExtension._login static method."""

    def test_login_dispatches_to_command_handler(self):
        args = MagicMock()

        with patch(
            "openlinktoken_ext_truveta.extension._login",
            return_value=0,
        ) as mock_login:
            result = TruvetaExtension._login(args)

        assert result == 0
        mock_login.assert_called_once_with(args)


class TestInitiateExchangeDispatch:
    """Tests for TruvetaExtension._initiate_exchange static method."""

    def test_initiate_exchange_dispatches_to_command_handler(self):
        args = MagicMock()

        with patch(
            "openlinktoken_ext_truveta.extension._initiate_exchange",
            return_value=0,
        ) as mock_initiate_exchange:
            result = TruvetaExtension._initiate_exchange(args)

        assert result == 0
        mock_initiate_exchange.assert_called_once_with(args)


class TestLogoutDispatch:
    """Tests for TruvetaExtension._logout static method."""

    def test_logout_dispatches_to_command_handler(self):
        args = MagicMock()

        with patch(
            "openlinktoken_ext_truveta.extension._logout",
            return_value=0,
        ) as mock_logout:
            result = TruvetaExtension._logout(args)

        assert result == 0
        mock_logout.assert_called_once_with(args)
