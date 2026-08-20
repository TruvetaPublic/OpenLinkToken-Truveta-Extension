"""
Copyright (c) Truveta. All rights reserved.

Unit tests for the auto-upload command.
"""

import argparse
from pathlib import Path
from unittest.mock import patch

from openlinktoken_ext_truveta.commands.auto_upload import _auto_upload

_PACKAGE_EXECUTE = (
    "openlinktoken_ext_truveta.commands.auto_upload.PackageCommand.execute"
)
_INITIATE_EXCHANGE = "openlinktoken_ext_truveta.commands.auto_upload._initiate_exchange"
_UPLOAD = "openlinktoken_ext_truveta.commands.auto_upload._upload"


def _args(file_path: str) -> argparse.Namespace:
    return argparse.Namespace(input=file_path)


class TestAutoUploadCommand:
    def test_happy_path_returns_zero(self, tmp_path):
        input_file = tmp_path / "demo_input.csv"
        input_file.write_text("RecordId,FirstName\n1,Alice")

        with (
            patch(_INITIATE_EXCHANGE, return_value=0),
            patch(_PACKAGE_EXECUTE, return_value=0),
            patch(_UPLOAD, return_value=0),
        ):
            result = _auto_upload(_args(str(input_file)))

        assert result == 0

    def test_input_file_not_found_returns_one_without_network_calls(self, capsys):
        with (
            patch(_INITIATE_EXCHANGE) as mock_initiate,
            patch(_PACKAGE_EXECUTE) as mock_package,
        ):
            result = _auto_upload(_args("/nonexistent/path/input.csv"))

        assert result == 1
        mock_initiate.assert_not_called()
        mock_package.assert_not_called()
        assert "not found" in capsys.readouterr().err

    def test_input_path_is_directory_returns_one(self, tmp_path, capsys):
        with patch(_INITIATE_EXCHANGE) as mock_initiate:
            result = _auto_upload(_args(str(tmp_path)))

        assert result == 1
        mock_initiate.assert_not_called()
        assert "not a file" in capsys.readouterr().err

    def test_initiate_exchange_failure_aborts_early(self, tmp_path):
        input_file = tmp_path / "input.csv"
        input_file.write_text("data")

        with (
            patch(_INITIATE_EXCHANGE, return_value=1),
            patch(_PACKAGE_EXECUTE) as mock_package,
            patch(_UPLOAD) as mock_upload,
        ):
            result = _auto_upload(_args(str(input_file)))

        assert result == 1
        mock_package.assert_not_called()
        mock_upload.assert_not_called()

    def test_package_failure_aborts_before_upload(self, tmp_path):
        input_file = tmp_path / "input.csv"
        input_file.write_text("data")

        with (
            patch(_INITIATE_EXCHANGE, return_value=0),
            patch(_PACKAGE_EXECUTE, return_value=1),
            patch(_UPLOAD) as mock_upload,
        ):
            result = _auto_upload(_args(str(input_file)))

        assert result == 1
        mock_upload.assert_not_called()

    def test_upload_failure_propagated(self, tmp_path):
        input_file = tmp_path / "input.csv"
        input_file.write_text("data")

        with (
            patch(_INITIATE_EXCHANGE, return_value=0),
            patch(_PACKAGE_EXECUTE, return_value=0),
            patch(_UPLOAD, return_value=1),
        ):
            result = _auto_upload(_args(str(input_file)))

        assert result == 1

    def test_package_receives_correct_args(self, tmp_path):
        input_file = tmp_path / "demo_input.csv"
        input_file.write_text("data")

        captured_package_args = {}

        def _capture_package(package_args):
            captured_package_args["args"] = package_args
            return 0

        with (
            patch(_INITIATE_EXCHANGE, return_value=0),
            patch(_PACKAGE_EXECUTE, side_effect=_capture_package),
            patch(_UPLOAD, return_value=0),
        ):
            _auto_upload(_args(str(input_file)))

        pa = captured_package_args["args"]
        assert pa.input_path == str(input_file)
        assert "demo_input_packaged.parquet" in pa.output_path
        assert pa.exchange_config is not None

    def test_upload_receives_parquet_path(self, tmp_path):
        input_file = tmp_path / "demo_input.csv"
        input_file.write_text("data")

        captured_upload_args = {}

        def _capture_upload(upload_args):
            captured_upload_args["input"] = upload_args.input
            return 0

        with (
            patch(_INITIATE_EXCHANGE, return_value=0),
            patch(_PACKAGE_EXECUTE, return_value=0),
            patch(_UPLOAD, side_effect=_capture_upload),
        ):
            _auto_upload(_args(str(input_file)))

        assert captured_upload_args["input"].endswith(".parquet")
        assert "demo_input_packaged" in captured_upload_args["input"]

    def test_upload_receives_metadata_path_when_present(self, tmp_path):
        input_file = tmp_path / "demo_input.csv"
        input_file.write_text("data")

        captured_upload_args = {}

        def _write_metadata_and_capture(package_args):
            Path(package_args.output_path).with_suffix(".metadata.json").write_text(
                "{}"
            )
            return 0

        def _capture_upload(upload_args):
            captured_upload_args["metadata"] = upload_args.metadata
            return 0

        with (
            patch(_INITIATE_EXCHANGE, return_value=0),
            patch(_PACKAGE_EXECUTE, side_effect=_write_metadata_and_capture),
            patch(_UPLOAD, side_effect=_capture_upload),
        ):
            _auto_upload(_args(str(input_file)))

        assert captured_upload_args["metadata"] is not None
        assert captured_upload_args["metadata"].endswith(
            "demo_input_packaged.metadata.json"
        )

    def test_upload_metadata_is_none_when_not_present(self, tmp_path):
        input_file = tmp_path / "demo_input.csv"
        input_file.write_text("data")

        captured_upload_args = {}

        def _capture_upload(upload_args):
            captured_upload_args["metadata"] = upload_args.metadata
            return 0

        with (
            patch(_INITIATE_EXCHANGE, return_value=0),
            patch(_PACKAGE_EXECUTE, return_value=0),
            patch(_UPLOAD, side_effect=_capture_upload),
        ):
            _auto_upload(_args(str(input_file)))

        assert captured_upload_args["metadata"] is None

    def test_temp_dir_cleaned_up_on_success(self, tmp_path):
        input_file = tmp_path / "input.csv"
        input_file.write_text("data")

        observed_tmp_dirs = []

        def _capture_package(package_args):
            observed_tmp_dirs.append(Path(package_args.output_path).parent)
            return 0

        with (
            patch(_INITIATE_EXCHANGE, return_value=0),
            patch(_PACKAGE_EXECUTE, side_effect=_capture_package),
            patch(_UPLOAD, return_value=0),
        ):
            _auto_upload(_args(str(input_file)))

        assert observed_tmp_dirs, "Expected package to be called"
        assert not observed_tmp_dirs[0].exists(), "Temp dir should be cleaned up"

    def test_temp_dir_cleaned_up_on_package_failure(self, tmp_path):
        input_file = tmp_path / "input.csv"
        input_file.write_text("data")

        observed_tmp_dirs = []

        def _capture_package(package_args):
            observed_tmp_dirs.append(Path(package_args.output_path).parent)
            return 1

        with (
            patch(_INITIATE_EXCHANGE, return_value=0),
            patch(_PACKAGE_EXECUTE, side_effect=_capture_package),
            patch(_UPLOAD, return_value=0),
        ):
            _auto_upload(_args(str(input_file)))

        assert observed_tmp_dirs, "Expected package to be called"
        assert not observed_tmp_dirs[0].exists(), "Temp dir should be cleaned up"
