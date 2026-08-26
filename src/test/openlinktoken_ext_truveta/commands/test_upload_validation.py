"""
Copyright (c) Truveta. All rights reserved.

Unit tests for upload pre-validation.
"""

import zipfile

from openlinktoken_ext_truveta.commands import upload_validation


def test_validate_file_rejects_csv_missing_required_columns(tmp_path):
    data_file = tmp_path / "invalid.csv"
    data_file.write_text("Token\nplain-token\n", encoding="utf-8")

    sample_token, metadata, error = upload_validation.validate_file(data_file)

    assert sample_token is None
    assert metadata is None
    assert error is not None
    assert "Missing required columns" in error


def test_validate_file_rejects_zip_with_invalid_parquet(tmp_path):
    zip_file = tmp_path / "invalid.zip"
    with zipfile.ZipFile(zip_file, "w") as archive:
        archive.writestr("data.parquet", b"not a parquet file")

    sample_token, metadata, error = upload_validation.validate_file(zip_file)

    assert sample_token is None
    assert metadata is None
    assert error


def test_validate_token_encryption_skips_non_jwe_token():
    assert upload_validation.validate_token_encryption("plain-token") is None
