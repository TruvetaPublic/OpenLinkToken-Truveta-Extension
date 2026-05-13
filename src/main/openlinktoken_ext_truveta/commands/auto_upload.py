"""
Copyright (c) Truveta. All rights reserved.

auto-upload command: initiate exchange, package, and upload in one step.
"""

import argparse
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from openlinktoken_cli.commands.package_command import PackageCommand

from openlinktoken_ext_truveta.commands.initiate_exchange import _initiate_exchange
from openlinktoken_ext_truveta.commands.upload import _upload


def _auto_upload(args: argparse.Namespace) -> int:
    """
    Initiate exchange, package input data, and upload in a single step.

    Steps:
    1. Validate input file exists
    2. Run initiate-exchange to negotiate exchange config
    3. Run the package command directly to tokenize input data
    4. Upload the packaged output via the upload command

    Inputs:
        args: Parsed CLI arguments containing --input.

    Returns:
        Exit code (0 on success, non-zero on first failure).
    """
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        return 1

    if not input_path.is_file():
        print(f"Error: Input path is not a file: {args.input}", file=sys.stderr)
        return 1

    rc = _initiate_exchange(args)
    if rc != 0:
        return rc

    date_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    config_path = Path.cwd() / f"openlinktoken-{date_stamp}.exchange.json"

    input_type = input_path.suffix.lstrip(".") or "csv"
    parquet_name = f"{input_path.stem}_packaged.parquet"

    with tempfile.TemporaryDirectory() as tmp_dir:
        parquet_path = Path(tmp_dir) / parquet_name
        metadata_path = parquet_path.with_suffix(".metadata.json")

        pkg_parser = argparse.ArgumentParser()
        PackageCommand.register_subcommand(pkg_parser.add_subparsers())
        package_args, _ = pkg_parser.parse_known_args(
            [
                "package",
                "--input",
                str(input_path),
                "--output",
                str(parquet_path),
                "--exchange-config",
                str(config_path),
                "--input-type",
                input_type,
                "--output-type",
                "parquet",
            ]
        )
        package_args.input_type = input_type
        package_args.output_type = "parquet"
        rc = PackageCommand.execute(package_args)
        if rc != 0:
            print("Error: package step failed", file=sys.stderr)
            return 1

        upload_args = argparse.Namespace(
            input=str(parquet_path),
            metadata=str(metadata_path) if metadata_path.exists() else None,
        )
        return _upload(upload_args)
