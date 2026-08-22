# Sync develop after main merge

- [Context](#context)
- [Goals](#goals)
- [Design](#design)
- [Failure behavior](#failure-behavior)
- [Validation](#validation)
- [Stacked PR](#stacked-pr)

## Context

The extension repository uses `develop` for normal work and `main` for releases. The
reference OpenLinkToken PR #457 adds automation that merges `main` into `develop`
after a pull request targeting `main` is merged. This change will apply the same
flow to the extension repository, on top of extension PR #35.

## Goals

- Keep `develop` synchronized after a release or hotfix merges into `main`.
- Use the existing GitHub App credentials so protected branch updates can succeed.
- Keep the change isolated to one workflow file.

## Design

Add `.github/workflows/sync-develop-on-merge.yml` with a
`pull_request_target` trigger for closed pull requests targeting `main`. The job
runs only when the pull request was merged, creates the existing
`APP_TRUVETAPUBLIC_RELEASE_BOT` token, checks out `develop` with full history,
merges `origin/main --no-edit`, and pushes `develop`.

Existing PR retargeting, validation, CI, and release workflows remain unchanged.

## Failure behavior

The merge step uses `set -euo pipefail`. Token, checkout, fetch, merge, and push
failures fail the workflow visibly. Merge conflicts are left for manual
resolution instead of being hidden or force-resolved.

## Validation

Validate the changed workflow with the repository pre-commit hooks and a
workflow/YAML syntax check where available. No application test suite is needed
because this change does not modify runtime code.

## Stacked PR

Create `dev/mattwise-42/sync-develop-on-merge` from
`dev/mattwise-42/dependabot-consolidation-pr29`, the head branch of PR #35. Open
the result as a draft pull request targeting that parent branch, matching the
branch-on-branch flow used by OpenLinkToken PR #457.
