"""
Copyright (c) Truveta. All rights reserved.
"""

import argparse
import os

from openlinktoken_cli.extension import OpenLinkTokenExtension

from openlinktoken_ext_truveta.auth import DEFAULT_DOMAIN_URL
from openlinktoken_ext_truveta.commands.initiate_exchange import _initiate_exchange
from openlinktoken_ext_truveta.commands.login import _login
from openlinktoken_ext_truveta.commands.upload import _upload


class TruvetaExtension(OpenLinkTokenExtension):
    """Open Link Token extension that adds Truveta-specific CLI commands."""

    @property
    def command_name(self) -> str:
        """Return the top-level subcommand name owned by this extension."""
        return "truveta"

    @property
    def description(self) -> str:
        """Return a short human-readable description of this extension."""
        return "Truveta-specific Open Link Token commands"

    @property
    def version(self) -> str:
        """Return the SemVer version string for this extension."""
        return "0.1.0"

    def register_subcommand(self, subparsers: argparse._SubParsersAction) -> None:
        """
        Register the ``truveta`` parser and its sub-subcommands.

        Inputs:
            subparsers: The argparse subparsers action to register against.
        """
        parser = subparsers.add_parser(self.command_name, help=self.description)
        self._register_truveta_subcommands(parser)

    def _register_truveta_subcommands(self, parser: argparse.ArgumentParser) -> None:
        """Register the Truveta subcommands on a parser instance."""
        sub = parser.add_subparsers(dest="truveta_subcommand")

        for registrar in (
            _LoginSubcommandRegistrar,
            _InitiateExchangeSubcommandRegistrar,
            _UploadSubcommandRegistrar,
        ):
            registrar.register(sub)

        def _print_truveta_help(_args) -> int:
            parser.print_help()
            return 0

        parser.set_defaults(func=_print_truveta_help)

    @staticmethod
    def _login(args) -> int:
        """
        Authenticate with Truveta services.

        Inputs:
            args: Parsed CLI arguments.

        Returns:
            Exit code (0 on success, non-zero on failure).
        """
        return _login(args)

    @staticmethod
    def _initiate_exchange(args) -> int:
        """
        Authenticate if needed and negotiate exchange configuration.

        Inputs:
            args: Parsed CLI arguments.

        Returns:
            Exit code (0 on success, non-zero on failure).
        """
        return _initiate_exchange(args)

    @staticmethod
    def _upload(args) -> int:
        """
        Upload encrypted token data for overlap analysis.

        Inputs:
            args: Parsed CLI arguments.

        Returns:
            Exit code (0 on success, non-zero on failure).
        """
        return _upload(args)


class _LoginSubcommandRegistrar:
    @staticmethod
    def register(sub: argparse._SubParsersAction) -> None:
        login_parser = sub.add_parser(
            "login", help="Authenticate with Truveta services"
        )
        login_parser.add_argument(
            "--domain",
            default=os.environ.get("TRV_DOMAIN", DEFAULT_DOMAIN_URL),
            metavar="URL",
            help=f"API URL to target (default: {DEFAULT_DOMAIN_URL})",
        )
        login_parser.add_argument(
            "--force",
            action="store_true",
            help="Re-authenticate even if valid cached credentials exist",
        )
        login_parser.set_defaults(func=TruvetaExtension._login)


class _InitiateExchangeSubcommandRegistrar:
    @staticmethod
    def register(sub: argparse._SubParsersAction) -> None:
        initiate_exchange_parser = sub.add_parser(
            "initiate-exchange",
            help="Negotiate exchange config (authenticates first if needed)",
        )
        initiate_exchange_parser.add_argument(
            "--local-dev",
            action="store_true",
            help="Use local Token Service API endpoint (http://localhost:18080)",
        )
        initiate_exchange_parser.set_defaults(func=TruvetaExtension._initiate_exchange)


class _UploadSubcommandRegistrar:
    @staticmethod
    def register(sub: argparse._SubParsersAction) -> None:
        upload_parser = sub.add_parser(
            "upload",
            help="Upload encrypted token data for self-serve overlap analysis",
        )
        upload_parser.add_argument(
            "--file",
            "-f",
            required=True,
            metavar="FILE",
            help="Tokenized output file (CSV or Parquet) to upload",
        )
        upload_parser.add_argument(
            "--metadata",
            metavar="FILE",
            help="Optional metadata JSON file (defaults to auto-discovered <basename>.metadata.json)",
        )
        upload_parser.add_argument(
            "--local-dev",
            action="store_true",
            help="Use local Token Service API endpoint (http://localhost:18080)",
        )
        upload_parser.set_defaults(func=TruvetaExtension._upload)
