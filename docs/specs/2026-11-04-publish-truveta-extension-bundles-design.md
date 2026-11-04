# Truveta Extension Dependency Bundle Publishing

**Status:** Proposed; implementation is gated on approval of this written spec.

## Contents

- [Problem](#problem)
- [Goals](#goals)
- [Non-goals](#non-goals)
- [Design](#design)
  - [Platform bundles](#platform-bundles)
  - [Release manifests](#release-manifests)
  - [Release workflow](#release-workflow)
  - [Compatibility and rollout](#compatibility-and-rollout)
- [Errors and safety](#errors-and-safety)
- [Validation](#validation)

## Problem

The extension release currently publishes a universal wheel with schema-v1
bootstrap and update manifests. The standalone OpenLinkToken runtime cannot
install that wheel's non-core dependencies in isolation, so the extension
cannot be reliably installed or updated by the standalone CLI.

The OpenLinkToken runtime now defines a schema-v2 manifest and locked bundle
contract. This repository must produce release assets that satisfy that
contract for each supported standalone platform.

## Goals

- Publish a complete, hash-locked extension dependency bundle for each
  supported standalone target.
- Publish schema-v2 bootstrap and update manifests that point to those bundles.
- Build wheels on matching platform runners using the same CPython ABI as the
  standalone release.
- Verify the actual bootstrap and update flow in the existing standalone
  release smoke tests.
- Preserve the Python package's normal installation and entry-point behavior.
- Keep the design document out of the final pull request tree.

## Non-goals

- Changing OpenLinkToken runtime behavior or adding dependencies to its core.
- Bundling source distributions or resolving dependencies on end-user machines.
- Supporting schema-v1 standalone clients for releases that require private
  extension dependencies. Those clients must upgrade to runtime protocol 2.
- Bumping the extension version in this feature pull request.
- Sandboxing extension code.

## Design

### Platform bundles

Build one dependency bundle on each existing standalone target runner:

- Linux x64: `linux-x64`, CPython ABI `cp312`
- macOS Apple Silicon: `macos-arm64`, CPython ABI `cp312`
- Windows x64: `windows-x64`, CPython ABI `cp312`

Each runner uses the universal extension wheel built by the release workflow
and downloads the extension's hash-pinned runtime dependencies from the
existing `requirements.txt`. The editable project entry is excluded because
the already-built wheel is added explicitly. Downloads are restricted to
binary wheels and checked against the pinned hashes. The target runner selects
compatible wheels using its native platform and Python markers; a missing
compatible wheel fails the release.

Each ZIP is flat and contains only `bundle-manifest.json` and wheel files. The
manifest follows the OpenLinkToken bundle contract: schema version 1,
extension name and version, target, Python ABI, and one record per wheel with
its filename, normalized distribution name, version, tags, and SHA-256.
Include the extension wheel and every non-core runtime dependency wheel; do
not include the three OpenLinkToken core distributions.

Publish a ZIP and SHA-256 sidecar for each target, named with the extension
version, target, and ABI. The bundle digest in the outer manifest covers the
complete ZIP; the inner wheel digests are validated by the standalone runtime.

### Release manifests

Generate the existing bootstrap and update asset names as schema-v2 manifests.
The bootstrap manifest includes the extension identity and version, the
existing update-manifest URL, the supported core range, command name
`truveta`, the description already defined by `TruvetaExtension`, minimum
runtime protocol 2, and the complete list of target bundle URLs and SHA-256
digests.

The update manifest carries the extension name, latest version, core range,
the same command metadata and protocol requirement, and the same bundle list.
Both manifests use the release tag version. The stable manifest filenames and
URLs remain unchanged; their schema changes to version 2.

### Release workflow

Restructure the existing release workflow so that:

1. The distribution job builds the wheel and source distribution.
2. A three-platform matrix downloads the wheel, resolves the locked binary
   dependencies, and builds one bundle per target. Each job uploads its bundle
   and checksum as a workflow artifact.
3. A publishing job waits for all three bundles, gathers them with the wheel
   and source distribution, generates both schema-v2 manifests, and uploads
   the complete set of assets to the GitHub Release. It must not publish
   manifests if any target bundle failed.
4. The existing standalone build jobs run after the manifests and bundles are
   published, so their smoke tests exercise the real schema-v2 bootstrap and
   update path.

Keep the wheel, source distribution, standalone ZIPs, and existing release
version source unchanged. Asset replacement remains retry-safe, consistent
with the current release workflow.

### Compatibility and rollout

The existing stable bootstrap and update URLs will serve schema-v2 manifests.
As agreed, installing or updating this dependency-bundled extension requires
an OpenLinkToken standalone runtime with protocol 2. Document this prerequisite
in the developer guide. Python-package users continue to install the ordinary
wheel and do not use the standalone bundle protocol.

Do not change `.bumpversion.cfg`, `pyproject.toml`, or the extension version
in this feature pull request. The normal release process remains responsible
for selecting the next extension version. Before opening the pull request,
remove this design file so it is absent from the final tree.

## Errors and safety

Fail the bundle job when dependency resolution cannot produce a compatible
wheel, a downloaded file does not match its required hash, the extension wheel
is missing, or a core distribution appears in the bundle. Generate manifests
only after all target bundles exist and their digests have been calculated.
The release smoke tests must fail if the standalone runtime cannot bootstrap,
update, or invoke the Truveta extension from the published bundle.

Hashes establish integrity relative to the release manifest; they are not an
independent publisher signature. This change does not add a security boundary
around extension code.

## Validation

- Unit tests verify the flat bundle layout, lock records, and bundle digest
  using synthetic wheel files.
- Manifest tests verify schema-v2 bootstrap and update fields, release URLs,
  core range, command metadata, protocol requirement, and all three bundles.
- Run the repository test suite and build the package in CI.
- Run the existing per-platform standalone release smoke tests against the
  published schema-v2 bootstrap manifest.
- Run pre-commit hooks against the exact changed files.
