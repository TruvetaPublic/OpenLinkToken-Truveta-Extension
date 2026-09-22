"""Compatibility checks for the OpenLinkToken host distributions."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version

from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion
from packaging.version import Version

SUPPORTED_CORE_SPECIFIER: str = ">=2.2.0,<3.0.0"
CORE_DISTRIBUTIONS: tuple[str, ...] = (
    "openlinktoken",
    "openlinktoken-cli",
    "openlinktoken-core-ai",
)
_COMPATIBILITY_REMEDIATION = (
    "upgrade the extension or install a compatible OpenLinkToken core"
)


class ExtensionCompatibilityError(RuntimeError):
    """Raised when the installed OpenLinkToken host is not supported."""


def installed_distribution_versions() -> dict[str, str]:
    """Return the installed versions of the OpenLinkToken core distributions."""
    installed_versions: dict[str, str] = {}
    for distribution in CORE_DISTRIBUTIONS:
        try:
            installed_versions[distribution] = version(distribution)
        except PackageNotFoundError:
            continue
    return installed_versions


def validate_runtime_compatibility() -> None:
    """Raise an error when a required OpenLinkToken core distribution is unsupported."""
    specifier = SpecifierSet(SUPPORTED_CORE_SPECIFIER)
    problems: list[str] = []

    for distribution in CORE_DISTRIBUTIONS:
        try:
            installed_version = version(distribution)
        except PackageNotFoundError:
            problems.append(
                f"{distribution} <not installed> (requires {SUPPORTED_CORE_SPECIFIER})"
            )
            continue

        try:
            parsed_version = Version(installed_version)
        except InvalidVersion:
            problems.append(
                f"{distribution} {installed_version} (invalid version; "
                f"requires {SUPPORTED_CORE_SPECIFIER})"
            )
            continue

        if parsed_version not in specifier:
            problems.append(
                f"{distribution} {installed_version} (requires {SUPPORTED_CORE_SPECIFIER})"
            )

    if problems:
        details = "; ".join(problems)
        raise ExtensionCompatibilityError(
            f"OpenLinkToken core compatibility check failed: {details}. "
            f"Remediation: {_COMPATIBILITY_REMEDIATION}."
        )
