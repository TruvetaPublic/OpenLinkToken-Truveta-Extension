"""
Copyright (c) Truveta. All rights reserved.

Unit tests for TruvetaExtension.
"""

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from openlinktoken.core.ai.tokens.ml1_inference_config import ML1InferenceConfig
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
        from importlib.metadata import version as _pkg_version

        assert self.ext.version == _pkg_version("openlinktoken-ext-truveta")


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


class TestAutoUploadSubcommand:
    """Tests for the auto-upload subcommand parser and flags."""

    def _build_parser(self):
        root = argparse.ArgumentParser()
        subparsers = root.add_subparsers(dest="command")
        TruvetaExtension().register_subcommand(subparsers)
        return root

    def test_auto_upload_subcommand_present(self):
        root = self._build_parser()
        parsed = root.parse_args(["truveta", "auto-upload", "--input", "input.csv"])
        assert parsed.func == TruvetaExtension._auto_upload

    def test_auto_upload_short_input_flag(self):
        root = self._build_parser()
        parsed = root.parse_args(["truveta", "auto-upload", "-i", "input.csv"])
        assert parsed.input == "input.csv"

    def test_auto_upload_accepts_package_inferencing_flags(self):
        root = self._build_parser()
        parsed = root.parse_args(
            [
                "truveta",
                "auto-upload",
                "--input",
                "input.csv",
                "--disable-inferencing",
                "--inferencing-batch-size",
                "32",
                "--inferencing-num-threads",
                "2",
            ]
        )

        assert parsed.disable_inferencing is True
        assert parsed.inferencing_batch_size == 32
        assert parsed.inferencing_num_threads == 2

    def test_auto_upload_uses_package_inferencing_defaults(self):
        root = self._build_parser()
        parsed = root.parse_args(["truveta", "auto-upload", "--input", "input.csv"])

        assert parsed.disable_inferencing is False
        assert parsed.inferencing_batch_size == ML1InferenceConfig.DEFAULT_BATCH_SIZE
        assert parsed.inferencing_num_threads is None

    @pytest.mark.parametrize("subcommand", ["upload", "auto-upload"])
    def test_missing_input_prints_same_help_as_help_flag(self, subcommand, capsys):
        root = self._build_parser()

        with pytest.raises(SystemExit) as missing_input:
            root.parse_args(["truveta", subcommand])
        missing_output = capsys.readouterr()

        with pytest.raises(SystemExit) as explicit_help:
            root.parse_args(["truveta", subcommand, "--help"])
        help_output = capsys.readouterr()

        assert missing_input.value.code == 0
        assert explicit_help.value.code == 0
        assert missing_output == help_output

    def test_auto_upload_accepts_format_flag_rejected(self):
        root = self._build_parser()
        with patch("sys.stderr"):
            try:
                root.parse_args(
                    [
                        "truveta",
                        "auto-upload",
                        "--input",
                        "input.csv",
                        "--format",
                        "parquet",
                    ]
                )
            except SystemExit as exc:
                assert exc.code == 2
                return
        raise AssertionError("Expected parse_args to reject removed --format flag")

    def test_auto_upload_has_no_format_attribute(self):
        root = self._build_parser()
        parsed = root.parse_args(["truveta", "auto-upload", "--input", "input.csv"])
        assert not hasattr(parsed, "format")

    def test_auto_upload_rejects_local_dev_flag(self):
        root = self._build_parser()
        with patch("sys.stderr"):
            try:
                root.parse_args(
                    ["truveta", "auto-upload", "--input", "input.csv", "--local-dev"]
                )
            except SystemExit as exc:
                assert exc.code == 2
                return
        raise AssertionError("Expected parse_args to reject auto-upload --local-dev")

    def test_auto_upload_rejects_domain_override_flag(self):
        root = self._build_parser()
        with patch("sys.stderr"):
            try:
                root.parse_args(
                    [
                        "truveta",
                        "auto-upload",
                        "--input",
                        "input.csv",
                        "--domain",
                        "dev.truveta-int.com",
                    ]
                )
            except SystemExit as exc:
                assert exc.code == 2
                return
        raise AssertionError("Expected parse_args to reject auto-upload --domain")


class TestAutoUploadDispatch:
    """Tests for TruvetaExtension._auto_upload static method."""

    def test_auto_upload_dispatches_to_command_handler(self):
        args = MagicMock()

        with patch(
            "openlinktoken_ext_truveta.extension._auto_upload",
            return_value=0,
        ) as mock_auto_upload:
            result = TruvetaExtension._auto_upload(args)

        assert result == 0
        mock_auto_upload.assert_called_once_with(args)


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
        with patch(
            "openlinktoken_ext_truveta.extension._logout",
            return_value=0,
        ) as mock_logout:
            result = TruvetaExtension._logout(MagicMock())

        assert result == 0
        mock_logout.assert_called_once_with()
