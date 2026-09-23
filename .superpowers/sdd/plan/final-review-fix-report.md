# Final Review Fix Wave Report

Date: 2026-09-22
Repository: `TruvetaPublic/OpenLinkToken-Truveta-Extension`
Branch: `agents/update-extension-for-core-library-changes`
Scope: frozen host-distribution metadata and prerelease wheel release handling

## Summary

This wave fixes both final-review findings:

1. The PyInstaller spec now copies the `dist-info` metadata for
   `openlinktoken`, `openlinktoken-cli`, and `openlinktoken-core-ai`. The
   frozen compatibility validator can therefore resolve the exact installed
   host versions. The release workflow also runs a compatible leaf command
   with an isolated temporary home/configuration.
2. The release workflow now discovers and validates the actual wheel emitted by
   `uv build` instead of reconstructing its filename from the raw release
   version. Raw SemVer values, including `1.2.3-rc.1`, remain the version input
   for tags and generated manifests while the normalized wheel filename is
   passed through unchanged.

The existing compatibility range remains exactly `>=2.2.0,<3.0.0`. No normal
wheel dependency policy or unrelated runtime behavior changed.

## Files changed

- `openlinktoken-ext-truveta.spec`
  - Imports PyInstaller `copy_metadata`.
  - Copies metadata for all three required host distributions into the frozen
    bundle.
- `.github/workflows/release.yml`
  - Finds exactly one `dist/*.whl` after `uv build`, verifies it is a file, and
    passes that path to the manifest generator.
  - Adds a Unix and Windows frozen smoke invocation of
    `truveta logout` using temporary home/configuration state.
- `src/test/openlinktoken_ext_truveta/test_standalone_bundle_config.py`
  - Covers metadata collection, normalized wheel discovery, and the non-help
    leaf smoke contract.
- `src/test/openlinktoken_ext_truveta/test_compatibility.py`
  - Covers runtime validation against `dist-info/METADATA` available on the
    frozen search path.
- `src/test/openlinktoken_ext_truveta/util/extension_manifests_test.py`
  - Covers a normalized wheel filename (`1.2.3rc1`) with raw SemVer
    `1.2.3-rc.1` preserved in manifests and release URLs.
- `.superpowers/sdd/plan/final-review-fix-report.md`
  - This implementation and verification report.

## TDD evidence

### RED

Command, run inside the repository devcontainer:

```text
pytest src/test/openlinktoken_ext_truveta/test_standalone_bundle_config.py \
  src/test/openlinktoken_ext_truveta/test_compatibility.py \
  src/test/openlinktoken_ext_truveta/util/extension_manifests_test.py -v
```

Result before the implementation changes:

```text
25 items collected
FAILED test_spec_bundles_core_distribution_metadata
FAILED test_release_workflow_generates_and_publishes_update_manifests
FAILED test_standalone_release_smokes_compatible_leaf_command
22 passed, 3 failed
```

The failures were the intended missing `copy_metadata` contract, the raw
`${VERSION}` wheel path, and the absent leaf-command smoke contract. The
prerelease manifest test itself passed against the already-correct raw-version
behavior; it now protects that behavior while the workflow supplies the
normalized wheel path.

### GREEN

After the spec and workflow changes, the same focused command produced:

```text
25 passed in 0.18s
```

The integrated extension, auto-upload, and runtime-hook tests produced:

```text
59 passed in 0.76s
```

After the final Windows `APPDATA` hardening, the focused regression command
produced:

```text
25 passed in 0.13s
```

## Verification commands and results

All project commands below ran inside the repository devcontainer at
`/workspaces/OpenLinkToken-Truveta-Extension`. The available project
environment was `/home/vscode/.local/share/openlinktoken-ext-truveta/.venv`.

### Python distribution build

```text
python -m build
```

Result:

```text
Successfully built openlinktoken_ext_truveta-1.0.0.tar.gz
and openlinktoken_ext_truveta-1.0.0-py3-none-any.whl
```

### Release manifest generation

The built wheel was passed to the existing generator after discovery:

```text
python -m openlinktoken_ext_truveta.util.extension_manifests \
  --version 1.0.0 \
  --wheel dist/openlinktoken_ext_truveta-1.0.0-py3-none-any.whl \
  --output-dir release-assets
```

Generated assets:

```text
release-assets/openlinktoken_ext_truveta-1.0.0-py3-none-any.whl.sha256
release-assets/openlinktoken-ext-truveta-bootstrap.json
release-assets/openlinktoken-ext-truveta-update.json
```

The generated bootstrap artifact URL used the raw tag version
`v1.0.0` and the actual wheel filename. The prerelease regression asserts the
same contract for raw `1.2.3-rc.1` and wheel
`openlinktoken_ext_truveta-1.2.3rc1-py3-none-any.whl`.

### Frozen PyInstaller build

The default devcontainer Python 3.11 runtime is statically linked and PyInstaller
reported that a shared library is required. The devcontainer also provides a
shared-library Python 3.12 runtime, so a temporary `/tmp` environment was
created inside the devcontainer with the release dependencies and PyInstaller.
The documented ML1 checkout at
`/Users/matthiasw/workspace/OpenLinkToken/resources/inferencing/ml1` was copied
only into the running container's configured empty asset mount for this
validation.

```text
OLT_INFERENCING_ASSETS_SOURCE=/workspaces/OpenLinkToken/resources/inferencing/ml1 \
  pyinstaller --clean --noconfirm openlinktoken-ext-truveta.spec
```

Result:

```text
Build complete! The results are available in:
/workspaces/OpenLinkToken-Truveta-Extension/dist
```

The resulting bundle contained all required metadata files:

```text
dist/olt/_internal/openlinktoken-2.2.0.dist-info/METADATA
dist/olt/_internal/openlinktoken_cli-2.2.0.dist-info/METADATA
dist/olt/_internal/openlinktoken_core_ai-2.2.0.dist-info/METADATA
```

### Standalone compatible leaf smoke

This is the exact class of command added to the release workflow (Unix form):

```text
smoke_home="$(mktemp -d)"
HOME="$smoke_home" XDG_CONFIG_HOME="$smoke_home/.config" \
  ./dist/olt/olt truveta logout
```

Result with the compatible bundled core (`2.2.0`):

```text
No credentials found.
registry -> /tmp/tmp.rpNgsSMGJL/.openlinktoken/extensions/registry.json
```

The command returned exit code 0, exercised the compatibility guard and
`logout` leaf implementation, performed no network request because the
temporary home had no credentials, and proved that the persistent registry was
seeded outside the bundle. This was not a help-only invocation.

### Full test suite

```text
pytest src/test -q
```

Result after the final workflow edit:

```text
404 passed in 1.02s
```

### Exact-file pre-commit hooks

The exact changed source/test/workflow files were passed to:

```text
prek run --files \
  openlinktoken-ext-truveta.spec \
  .github/workflows/release.yml \
  src/test/openlinktoken_ext_truveta/test_standalone_bundle_config.py \
  src/test/openlinktoken_ext_truveta/test_compatibility.py \
  src/test/openlinktoken_ext_truveta/util/extension_manifests_test.py
```

The linked worktree's `.git` file points to a host-only worktree directory
that is not mounted in the devcontainer, so the plain in-container invocation
could not resolve Git. The required hook command was rerun in the same
devcontainer with a temporary in-container `GIT_DIR`/`GIT_WORK_TREE` pair; the
project files and hook execution remained inside the devcontainer.

Result:

```text
ruff.....................................................................Passed
ruff-format..............................................................Passed
prettier.................................................................Passed
trim trailing whitespace.................................................Passed
fix end of files.........................................................Passed
check yaml...............................................................Passed
check for merge conflicts................................................Passed
check for added large files..............................................Passed
```

The report itself was also checked with the repository's Markdown-related
hooks before commit.

## Self-review

- The compatibility range is unchanged and still explicit in the extension.
- All three host distributions receive metadata; the real frozen bundle
  inspection confirmed each `METADATA` file.
- Compatibility failures remain actionable and are not replaced with a
  success-shaped fallback.
- The release workflow preserves raw `VERSION` for the GitHub tag and
  manifest version while passing the actual normalized wheel filename.
- The wheel discovery rejects zero or multiple wheels rather than silently
  selecting an arbitrary artifact.
- The leaf smoke uses no credentials, no network-dependent extension action,
  and isolated filesystem state.
- The Windows smoke sets both `HOME` and `APPDATA` so the platform-specific
  core home resolver also uses temporary state.
- No host package was added to normal wheel dependencies.
- Generated `build/`, `dist/`, `release-assets/`, copied ML1 assets, and
  temporary build environments were removed after verification.

## Concerns and limitations

1. The repository devcontainer's default Python 3.11 is statically linked, so
   PyInstaller cannot build with that interpreter. Validation used the
   devcontainer's shared Python 3.12 runtime in a temporary environment. This
   is an environment concern, not a source regression.
2. The first attempt to hydrate the ML1 assets from
   `ghcr.io/truvetapublic/openlinktoken-ml1-assets:v1` was denied by the
   registry. The local documented OpenLinkToken asset checkout was used only
   as the build input for validation. CI's existing asset checkout path was
   not changed.
3. PyInstaller emitted existing optional-module warnings for missing
   `matplotlib`, `onnx`, and platform-specific libraries; the build completed
   successfully and the compatible leaf smoke passed.
4. The macOS and Windows frozen binaries were not executed in this Linux
   container. Their workflow smoke commands are covered by YAML contract tests;
   the Linux bundle provided the runtime metadata and leaf-command evidence.

Commit: created after this report and the final hook run; the final commit
identifier is returned with the task status.
