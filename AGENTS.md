# Open Link Token Truveta Extension — Agent Instructions

- [Scope](#scope)
- [Project Snapshot](#project-snapshot)
- [Repository Map](#repository-map)
- [Coding Rules](#coding-rules)
  - [Python Guidelines](#python-guidelines)
  - [Error Handling](#error-handling)
- [Testing & Validation](#testing--validation)
- [Dependency & Packaging Rules](#dependency--packaging-rules)
- [Documentation Rules](#documentation-rules)
- [Quick Commands](#quick-commands)

## Scope

These instructions apply to all work in this repository. Prioritize minimal, targeted changes that preserve existing behavior and public CLI interfaces.

## Project Snapshot

- Language: Python (>=3.10)
- Package: `openlinktoken-ext-truveta`
- Source root: `src/main/openlinktoken_ext_truveta/`
- Tests root: `src/test/openlinktoken_ext_truveta/`
- Tooling: `pytest`, `flake8`, `autoflake`, `build`

## Repository Map

- `src/main/openlinktoken_ext_truveta/commands/`: CLI command implementations.
- `src/main/openlinktoken_ext_truveta/api/`: API integration modules.
- `src/main/openlinktoken_ext_truveta/exchange/`: exchange/config/key logic.
- `src/main/openlinktoken_ext_truveta/openlink_token_service_client/`: service client + types.
- `docs/developer-guide.md`: dev workflows (setup, test, build, release).

## Coding Rules

### Python Guidelines

- Keep functions focused and side effects explicit.
- Preserve existing module boundaries and naming conventions.
- Prefer clear type hints for new/updated public functions.
- Avoid broad refactors unless required for the task.

### Error Handling

- Avoid broad `try/except Exception` or bare `except:` blocks.
- Catch specific exceptions and include actionable error messages.
- Re-raise when context should not be swallowed.

## Testing & Validation

- When editing Python files, run `pytest` for changed tests first.
- If behavior changes cross module boundaries, run the full test suite: `pytest src/test -v`.
- Add or update tests when fixing bugs or changing observable behavior.
- Do not claim tests passed unless they were executed in this workspace.

## Dependency & Packaging Rules

- Manage dependencies in `pyproject.toml`.
- Keep pins consistent with current project style.
- Ensure entry point behavior under `[project.entry-points."openlinktoken.extensions"]` remains intact unless intentionally changed.

## Documentation Rules

- Keep documentation concise and task-focused.
- For Markdown files, include a Table of Contents near the top.
- Update `README.md` or `docs/developer-guide.md` when user-visible workflows change.

## Quick Commands

- Install dev deps (uv): `uv pip install -e ".[dev]"`
- Install dev deps (pip): `pip install -e ".[dev]"`
- Run tests: `pytest src/test -v`
- Build artifacts: `python -m build`
