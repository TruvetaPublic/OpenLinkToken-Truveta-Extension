# Standalone Release Model Asset Distribution

- [Goal and scope](#goal-and-scope)
- [Design](#design)
- [Release and installer flow](#release-and-installer-flow)
- [Compatibility and extension updates](#compatibility-and-extension-updates)
- [Validation](#validation)
- [Documentation](#documentation)

## Goal and scope

Align the Truveta standalone release bundles with OpenLinkToken PR
[#532](https://github.com/TruvetaPublic/OpenLinkToken/pull/532) by removing ML1
payloads from Truveta release ZIPs while retaining the official installer’s
working first-run experience. This is a separate follow-up stacked on Truveta
PR #70, whose head is `dev/mattwise-42/update-extension-for-core-library-changes`.
Do not expand PR #70 or modify OpenLinkToken.

Keep PR #70’s core compatibility range `>=2.2.1,<3.0.0`, development CLI source
`develop`, and release package/model source `main`. The standalone platform
matrix is Linux x64, macOS Apple Silicon arm64, and Windows x64. Intel macOS is
not supported.

## Design

The release ZIP contains the frozen CLI and Truveta extension but none of the
ML1 model payload files (`asset-manifest.json`, `model.onnx`,
`model.onnx.data`, or `tokenizer.json`). PyInstaller must not collect those
files, and release-asset creation must guard against accidentally including
them.

The official platform installers retrieve model assets from the public OCI
artifact `ghcr.io/truvetapublic/openlinktoken-ml1-assets:v1`. They download
ORAS 1.3.3 for the host platform, verify its pinned SHA-256 digest, pull the
selected model tag, validate the required files and each manifest-declared
size and SHA-256, then place the files at
`_internal/openlinktoken/core/ai/tokens` in the staged bundle before
installation. The default model tag is `v1`; installers expose the same
`OLT_ML1_MODEL_TAG` / model-tag override supported upstream.

Manually extracting a release ZIP does not install ML1. Documentation will
direct users to the official installer for a complete first-run installation,
and describe the OCI setup requirement for users who choose manual extraction.

## Release and installer flow

Remove the LFS checkout and asset-source environment variable from the
standalone release job. Build only Linux x64, `macos-15` arm64, and Windows
x64. Release validation will confirm that the ZIP excludes all four ML1 files,
pull the model OCI artifact, verify its manifest metadata, copy it into a
temporary extracted bundle, and smoke-test ML1 tokenization against that
bundle.

Both the POSIX and PowerShell installers will stage the release archive and
validated model files before promoting the installation. Failed downloads or
verification must abort installation with an actionable error and must not
promote a partially prepared bundle.

## Compatibility and extension updates

Keep the extension-only bootstrap, registry seeding, and explicit update paths
unchanged. In particular, do not replace or rewrite the core-managed persistent
extension registry while installing model files. A standalone core bundle can
be replaced without silently replacing an independently installed or updated
Truveta extension.

## Validation

Add regression coverage that:

- inspects generated ZIP contents and rejects inclusion of any ML1 payload file;
- asserts the supported platform matrix has no Intel macOS target;
- exercises OCI asset retrieval/manifest validation with controlled test data,
  including size and digest failure cases; and
- verifies installer and release workflow wiring for the supported OCI/model
  tag and verification steps.

Run focused tests, then the full `pytest src/test -v` suite if dependencies are
available, and run `prek run --files` for every changed file in the configured
devcontainer. Do not push a branch or create a pull request without explicit
user approval.

## Documentation

Update the README and developer guide together to state that official
installers retrieve and verify model assets from OCI, direct ZIP extraction
omits ML1 and requires manual setup, and the supported macOS platform is
Apple Silicon only. Update release and local-build instructions to remove
the Git-LFS model checkout requirement while retaining the existing source
refs and compatibility contract.
