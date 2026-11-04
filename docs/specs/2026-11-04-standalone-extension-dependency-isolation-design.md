# Standalone Extension Dependency Isolation

**Status:** Proposed; implementation is gated on approval of this written spec.

## Contents

- [Problem](#problem)
- [Goals](#goals)
- [Non-goals](#non-goals)
- [Design](#design)
  - [Release artifacts and manifests](#release-artifacts-and-manifests)
  - [Install and update](#install-and-update)
  - [Command execution](#command-execution)
  - [Compatibility and rollout](#compatibility-and-rollout)
- [Errors and safety](#errors-and-safety)
- [Validation](#validation)
- [Affected repositories](#affected-repositories)

## Problem

The standalone OpenLinkToken binary currently accepts extension wheels only when
their runtime dependencies are already in the binary's bundled-dependency
allowlist. It does not install dependencies from the wheel. The Truveta extension
declares packages such as `requests`, `httpx`, and `pydantic`, so the standalone
install/update smoke test fails before it can invoke an extension command.

Simply adding extension dependencies to the standalone binary is not sufficient:
extensions can require incompatible versions of the same package. The current
frozen loader imports extensions into the CLI process and adds their paths to
global `sys.path`, so those versions cannot be isolated from one another.

## Goals

- Let a standalone binary install and update extensions with arbitrary,
  transitive runtime dependencies from release artifacts, without resolving or
  downloading packages from PyPI at install time.
- Allow different extensions to use conflicting versions of the same
  non-core dependency.
- Pin and verify the complete wheel set for each supported standalone platform
  and embedded Python ABI.
- Keep OpenLinkToken's core dependency versions fixed. An extension must not
  override a core package or require a version incompatible with the core
  runtime.
- Preserve the existing extension command interface, explicit install/update
  behavior, persistent registry semantics, and Python-package installation
  behavior.

## Non-goals

- Sandboxing or restricting extension code. A worker runs with the invoking
  user's permissions, just as extension code does today.
- Supporting conflicting versions of one dependency inside a single extension.
- Resolving dependencies from package indexes, installing source distributions,
  or building packages on end-user machines.
- Allowing an extension to replace or shadow an OpenLinkToken core dependency.
- Changing the extension interface or dependency resolution behavior of the
  Python-package CLI.

## Design

### Release artifacts and manifests

Each extension release publishes a locked runtime bundle per supported
standalone target: Linux x64, Windows x64, and macOS Apple Silicon arm64, each
for the exact embedded CPython ABI used by that standalone build. A bundle
contains the extension wheel, every non-core runtime dependency wheel, and a
`bundle-manifest.json` lock file. Source distributions are not accepted.

The lock manifest lists each wheel's filename, normalized distribution name,
version, compatible wheel tags, and SHA-256 digest. It includes the extension
wheel and the full transitive runtime dependency set after evaluating
environment markers for that target. The build must fail if a dependency cannot
be satisfied by a compatible wheel or by the fixed core runtime.

The release bootstrap and update manifests advance to schema version 2. They
retain the extension version and core compatibility range and add:

- The minimum standalone runtime protocol required by the bundle.
- The extension's top-level command name and help description, so the parent
  CLI can discover commands without importing extension code.
- A list of target-specific bundle URLs and SHA-256 digests.

The bundle digest is checked before extraction; the per-wheel digests and lock
contents are checked before installation. Digests provide integrity relative
to the fetched manifest, not an independent publisher signature.

Each standalone build embeds a machine-readable inventory of core distribution
names and versions, generated from the same pinned runtime lock used to build
that binary. Install-time compatibility checks use this inventory rather than
inferring core ownership from imports.

### Install and update

The standalone installer selects the bundle matching its operating system,
architecture, and embedded Python ABI. It downloads only the manifest and
selected bundle; it never consults a package index. It then verifies the bundle
digest, validates the lock and wheel tags, and checks each extension
`Requires-Dist` entry against the locked wheels and the standalone core-runtime
inventory.

Core-owned distributions are satisfied only by the fixed version in the core
inventory. They must not be duplicated in the extension's private dependency
directory. If an extension requirement conflicts with a core version, or a
locked dependency is missing, incompatible, or inconsistent with its digest,
installation fails with an actionable error. No existing installation is
changed.

Install each wheel using a bundled, standards-compliant wheel installer that
does not resolve dependencies and correctly handles wheel installation
locations, including `.data` members. Bundle the PyPA `installer` library in
the standalone core for this purpose; do not extend the current manual
single-wheel extraction path to handle dependency wheels.

In standalone mode, installing a wheel without its locked runtime bundle is
supported only when all its requirements are satisfied by the fixed core
runtime. Otherwise, fail with a message directing the user to install from a
bundle manifest. The Python-package CLI keeps its current wheel-install
behavior.

Stage a verified extension version in an immutable, versioned directory under
the persistent extension root. After all files are installed and validated,
atomically update the core-managed registry to point to the new directory.
Keep the previous active version intact until that registry update succeeds;
failed downloads, validation, or installation leave the old version usable.
Registry migration must preserve existing entries and must not overwrite an
intentionally empty registry. Replacing the standalone bundle must continue to
leave the persistent registry and installed extensions untouched.

Keep the existing schema-version-1 install/update path available for older
extension releases that satisfy the current bundled-dependency rules. New
release assets use schema version 2 and require a core runtime that supports
the new protocol.

### Command execution

In standalone mode, the parent CLI must not import extension modules to
register or execute their commands. It uses registry and manifest metadata to
display top-level help and route the selected command. For older registry
entries without a help description, the parent launches the worker in a
metadata-only mode; the worker returns the command name and description, which
the parent caches in the registry. Extension code is still never imported in
the parent.

When a registered extension command is selected, the parent starts the same
standalone executable in a private worker mode, passing the extension identity
and the original extension command arguments. It also passes the effective
core invocation context needed by the extension, such as configuration or
profile selection, without repeating parent-only work. The worker loads only
that extension, its source, and its private dependency directory, then uses the
existing extension interface to parse arguments and run the command. Core
modules and their fixed dependencies retain precedence; extension-installed
packages cannot shadow them. No other extension is loaded into the worker.

The worker's stdout, stderr, and exit status are propagated to the parent
unchanged. Command help, nested subcommands, and existing argument spelling
must remain compatible. The Python-package CLI continues to use its existing
in-process loader and is not routed through standalone workers.

### Compatibility and rollout

The change requires one new OpenLinkToken standalone release with worker
dispatch, schema-version-2 manifest handling, a core-runtime dependency
inventory, and offline wheel installation. The extension release workflow
then publishes per-target locked bundles and schema-version-2 manifests.

An older standalone binary must reject a schema or runtime protocol it does
not support with a message directing the user to update the OpenLinkToken
binary. It must not replace or disable an already installed extension because
an update manifest is too new. Existing schema-version-1 extensions remain
usable through the legacy-compatible path in the new core.

After the new core release is available, the Truveta extension can publish a
locked-bundle release independently. Its existing `requires_core` range
continues to gate installation and updates.

## Errors and safety

Unsupported targets, incompatible core versions, core dependency conflicts,
unknown manifest protocols, incomplete locks, invalid wheel tags, and checksum
mismatches must produce a non-zero result and an actionable message. Update
failures must preserve the last known-good installation and registry entry;
they must not be silently treated as success.

Validate archive paths before extraction and reject path traversal or unexpected
files. Worker isolation is for Python dependency isolation only, not a security
boundary: extension code can access the same user files, network, and
credentials as the parent CLI.

## Validation

- Unit-test schema-version-2 parsing, target/ABI selection, lock completeness,
  wheel-tag compatibility, digest checks, and core-version conflict detection.
- Test install/update staging and registry migration, including rollback on a
  corrupt or incomplete bundle and preservation of an intentionally empty
  registry.
- Test worker dispatch, help, nested arguments, stdout/stderr, exit codes, and
  that standalone parent startup never imports an extension module.
- Use two fixture extensions that require different versions of the same
  non-core package; install both and verify each worker imports its own pinned
  version.
- Test that a dependency conflicting with a core-owned package is rejected and
  that tampered or unsupported bundles do not change the active extension.
- Run the frozen-binary release smoke test on every supported platform. Install
  and update the real Truveta extension from its locked bundle, invoke a
  dependency-backed command, and verify core metadata remains unchanged.
- Verify installation works without package-index access and that Python CLI
  installation behavior remains unchanged.

## Affected repositories

- **OpenLinkToken:** standalone extension install/update commands, extension
  loader and interface integration, worker bootstrap/dispatch, runtime
  dependency inventory, frozen-build dependencies, tests, and extension
  compatibility documentation.
- **OpenLinkToken-Truveta-Extension:** per-target wheel-bundle and lock
  generation, schema-version-2 release manifests, release workflow and smoke
  tests, and standalone extension update documentation.
