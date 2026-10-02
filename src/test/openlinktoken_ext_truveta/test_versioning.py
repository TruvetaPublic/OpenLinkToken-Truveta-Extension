"""
Copyright (c) Truveta. All rights reserved.

Regression tests for release version configuration.
"""

from configparser import ConfigParser
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_bumpversion_search_targets_exist_in_repository() -> None:
    """Ensure every configured version replacement has a current marker."""
    config = ConfigParser(interpolation=None)
    config.read(REPOSITORY_ROOT / ".bumpversion.cfg")
    current_version = config["bumpversion"]["current_version"]

    assert "bumpversion:file:.bumpversion.cfg" in config

    for section in config.sections():
        if not section.startswith("bumpversion:file:"):
            continue

        relative_path = section.removeprefix("bumpversion:file:")
        search_text = config[section]["search"].replace(
            "{current_version}", current_version
        )
        file_contents = (REPOSITORY_ROOT / relative_path).read_text()

        assert search_text in file_contents, (
            f"{relative_path} does not contain the configured version marker {search_text!r}"
        )
