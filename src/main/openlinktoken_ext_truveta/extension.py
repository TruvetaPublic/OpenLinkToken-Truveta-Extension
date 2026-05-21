"""
Copyright (c) Truveta. All rights reserved.
"""

import argparse
import os

from openlinktoken_cli.extension import OpenLinkTokenExtension

from openlinktoken_ext_truveta.commands.auto_upload import _auto_upload
from openlinktoken_ext_truveta.commands.initiate_exchange import _initiate_exchange
from openlinktoken_ext_truveta.commands.login import _login
from openlinktoken_ext_truveta.commands.logout import _logout
from openlinktoken_ext_truveta.commands.upload import _upload
from openlinktoken_ext_truveta.domain import DEFAULT_DOMAIN


class TruvetaExtension(OpenLinkTokenExtension):
    """Open Link Token extension that adds Truveta-specific CLI commands."""

    @property
    def command_name(self) -> str:
        """
        Return the top-level subcommand name owned by this extension.

        Inputs:
            None.

        Returns:
            The root CLI subcommand string implemented by this extension.
        """
        return "truveta"

    @property
    def description(self) -> str:
        """
        Return a short human-readable description of this extension.

        Inputs:
            None.

        Returns:
            A concise human-readable description for CLI help text.
        """
        return "Truveta-specific Open Link Token commands"

    @property
    def version(self) -> str:
        """
        Return the SemVer version string for this extension.

        Inputs:
            None.

        Returns:
            The semantic version string for the installed extension package.
        """
        return "0.1.0"

    def register_subcommand(self, subparsers: argparse._SubParsersAction) -> None:
        """
        Register the ``truveta`` parser and its sub-subcommands.

        Inputs:
            subparsers: The argparse subparsers action to register against.

        Returns:
            None. The extension command tree is registered on the parser.
        """
        parser = subparsers.add_parser(self.command_name, help=self.description)
        self._register_truveta_subcommands(parser)

    def _register_truveta_subcommands(self, parser: argparse.ArgumentParser) -> None:
        """
        Register the Truveta subcommands on a parser instance.

        Inputs:
            parser: The argparse parser representing the top-level truveta command.

        Returns:
            None. The login, initiate-exchange, and upload subcommands are added.
        """
        sub = parser.add_subparsers(dest="truveta_subcommand")

        for registrar in (
            _AutoUploadSubcommandRegistrar,
            _InitiateExchangeSubcommandRegistrar,
            _LoginSubcommandRegistrar,
            _LogoutSubcommandRegistrar,
            _UploadSubcommandRegistrar,
        ):
            registrar.register(sub)

        def _print_truveta_help(_args) -> int:
            """
            Print help text when no Truveta subcommand is selected.

            Inputs:
                _args: Parsed CLI arguments, unused by the help handler.

            Returns:
                Exit code 0 after printing the truveta command help text.
            """
            parser.print_help()
            return 0

        parser.set_defaults(func=_print_truveta_help)

    @staticmethod
    def _auto_upload(args) -> int:
        """
        Initiate exchange, package, and upload in one step.

        Inputs:
            args: Parsed CLI arguments.

        Returns:
            Exit code (0 on success, non-zero on failure).
        """
        return _auto_upload(args)

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
    def _logout(args) -> int:
        """
        Revoke tokens and clear cached Truveta session state.

        Inputs:
            args: Parsed CLI arguments.

        Returns:
            Exit code (0 on success, non-zero on failure).
        """
        return _logout(args)

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
        """
        Register the login subcommand and its flags.

        Inputs:
            sub: The argparse subparser collection for truveta subcommands.

        Returns:
            None. The login subcommand is added to the parser tree.
        """
        login_parser = sub.add_parser(
            "login", help="Authenticate with Truveta services"
        )
        login_parser.add_argument(
            "--domain",
            default=os.environ.get("OLT_TRV_DOMAIN", DEFAULT_DOMAIN),
            metavar="DOMAIN",
            help=f"Truveta domain to target (default: {DEFAULT_DOMAIN})",
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
        """
        Register the initiate-exchange subcommand and its flags.

        Inputs:
            sub: The argparse subparser collection for truveta subcommands.

        Returns:
            None. The initiate-exchange subcommand is added to the parser tree.
        """
        initiate_exchange_parser = sub.add_parser(
            "initiate-exchange",
            help="Negotiate exchange config (authenticates first if needed)",
        )
        initiate_exchange_parser.set_defaults(func=TruvetaExtension._initiate_exchange)


class _LogoutSubcommandRegistrar:
    @staticmethod
    def register(sub: argparse._SubParsersAction) -> None:
        """
        Register the logout subcommand.

        Inputs:
            sub: The argparse subparser collection for truveta subcommands.

        Returns:
            None. The logout subcommand is added to the parser tree.
        """
        logout_parser = sub.add_parser(
            "logout", help="Revoke tokens and clear cached credentials"
        )
        logout_parser.set_defaults(func=TruvetaExtension._logout)


class _UploadSubcommandRegistrar:
    @staticmethod
    def register(sub: argparse._SubParsersAction) -> None:
        """
        Register the upload subcommand and its flags.

        Inputs:
            sub: The argparse subparser collection for truveta subcommands.

        Returns:
            None. The upload subcommand is added to the parser tree.
        """
        upload_parser = sub.add_parser(
            "upload",
            help="Upload encrypted token data for self-serve overlap analysis",
        )
        upload_parser.add_argument(
            "--input",
            "-i",
            required=True,
            help="Tokenized output file (CSV, Parquet, or ZIP containing one of those) to upload",
        )
        upload_parser.add_argument(
            "--metadata",
            help="Optional metadata JSON file (defaults to auto-discovered <basename>.metadata.json)",
        )
        upload_parser.set_defaults(func=TruvetaExtension._upload)


class _AutoUploadSubcommandRegistrar:
    @staticmethod
    def register(sub: argparse._SubParsersAction) -> None:
        """
        Register the auto-upload subcommand and its flags.

        Inputs:
            sub: The argparse subparser collection for truveta subcommands.

        Returns:
            None. The auto-upload subcommand is added to the parser tree.
        """
        auto_upload_parser = sub.add_parser(
            "auto-upload",
            help="Initiate exchange, package, and upload input data in one step",
        )
        auto_upload_parser.add_argument(
            "--input",
            "-i",
            required=True,
            help="Raw input file (CSV or Parquet) to package and upload",
        )
        auto_upload_parser.set_defaults(func=TruvetaExtension._auto_upload)
