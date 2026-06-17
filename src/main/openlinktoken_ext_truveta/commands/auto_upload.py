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

_STEP_WIDTH = 72
_GRAY = "\033[90m"
_RESET = "\033[0m"


def _print_step_banner(
    step: int, total: int, label: str, command: str | None = None
) -> None:
    """
    Print a visual separator that announces a numbered pipeline step.

    Inputs:
        step: 1-based step number.
        total: Total number of steps in the pipeline.
        label: Short human-readable name for the step.
        command: Optional equivalent CLI command shown in gray under the banner.
    """
    prefix = f"── Step {step}/{total}: {label} "
    print(f"\n{prefix}{('─' * max(0, _STEP_WIDTH - len(prefix)))}")
    if command:
        print(f"{_GRAY}   $ {command}{_RESET}")


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

    _print_step_banner(1, 3, "Initiate Exchange", "olt truveta initiate-exchange")
    rc = _initiate_exchange(args)
    if rc != 0:
        return rc

    date_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    config_path = Path.cwd() / f"openlinktoken-{date_stamp}.exchange.json"

    zip_name = f"{input_path.stem}_packaged.zip"

    _print_step_banner(
        2,
        3,
        "Package",
        f"olt package --input {input_path} --output {zip_name}"
        f" --exchange-config {config_path}",
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        zip_path = Path(tmp_dir) / zip_name

        pkg_parser = argparse.ArgumentParser()
        PackageCommand.register_subcommand(pkg_parser.add_subparsers())
        package_args, _ = pkg_parser.parse_known_args(
            [
                "package",
                "--input",
                str(input_path),
                "--output",
                str(zip_path),
                "--exchange-config",
                str(config_path),
            ]
        )
        rc = PackageCommand.execute(package_args)
        if rc != 0:
            print("Error: package step failed", file=sys.stderr)
            return 1

        _print_step_banner(
            3,
            3,
            "Upload",
            f"olt truveta upload --input {zip_path}",
        )

        upload_args = argparse.Namespace(
            input=str(zip_path),
            metadata=None,
        )
        return _upload(upload_args)
