import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "tools" / "check_python_docstrings.py"


class CheckPythonDocstringsTests(unittest.TestCase):
    def check_source(self, source: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example.py"
            path.write_text(source, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(CHECKER), str(path)],
                capture_output=True,
                check=False,
                text=True,
            )

    def test_reports_missing_class_and_method_docstrings(self) -> None:
        result = self.check_source(
            "class Example:\n    def run(self):\n        return 1\n"
        )

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("class 'Example' is missing a docstring", result.stderr)
        self.assertIn("method 'run' is missing a docstring", result.stderr)

    def test_requires_parameter_and_return_documentation(self) -> None:
        result = self.check_source(
            'def transform(source, strict=False):\n    """Transform source text."""\n    return source\n'
        )

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("source, strict", result.stderr)
        self.assertIn("missing a non-empty Returns section", result.stderr)

    def test_accepts_args_and_inputs_sections(self) -> None:
        result = self.check_source(
            "def transform(source: str) -> str:\n"
            '    """Transform source text.\n\n'
            "    Inputs:\n"
            "        source: The text to transform.\n\n"
            "    Returns:\n"
            "        The transformed text.\n"
            '    """\n'
            "    return source\n"
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_none_return_does_not_require_returns_section(self) -> None:
        result = self.check_source(
            "def notify(message: str) -> None:\n"
            '    """Send a notification.\n\n'
            "    Args:\n"
            "        message: The notification text.\n"
            '    """\n'
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_generators_require_yields_section(self) -> None:
        result = self.check_source(
            "def names():\n"
            '    """Yield names.\n\n'
            "    Returns:\n"
            "        The names.\n"
            '    """\n'
            '    yield "name"\n'
        )

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("missing a non-empty Yields section", result.stderr)

    def test_static_method_documents_parameter_named_self(self) -> None:
        result = self.check_source(
            "class Encoder:\n"
            '    """Encode values."""\n'
            "    @staticmethod\n"
            "    def encode(self: str) -> str:\n"
            '        """Encode a value.\n\n'
            "        Args:\n"
            "            self: The value to encode.\n\n"
            "        Returns:\n"
            "            The encoded value.\n"
            '        """\n'
            "        return self\n"
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_nested_function_return_is_not_counted_for_outer_function(self) -> None:
        result = self.check_source(
            "def outer():\n"
            '    """Run a local helper."""\n'
            "    def inner() -> int:\n"
            '        """Return a value.\n\n'
            "        Returns:\n"
            "            The helper result.\n"
            '        """\n'
            "        return 1\n"
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reports_invalid_python_syntax(self) -> None:
        result = self.check_source("def broken(:\n    pass\n")

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("invalid Python syntax", result.stderr)

    def test_quoted_no_return_annotations_do_not_require_returns_section(self) -> None:
        for annotation in ("NoReturn", "Never", "typing.NoReturn"):
            with self.subTest(annotation=annotation):
                result = self.check_source(
                    f'def fail() -> "{annotation}":\n'
                    '    """Raise an error."""\n'
                    '    raise RuntimeError("failed")\n'
                )

                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
