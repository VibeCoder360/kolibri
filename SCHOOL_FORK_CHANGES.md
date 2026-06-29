# School Fork Customizations (VibeCoder360/kolibri)

This file documents all build/CI customizations on the `VibeCoder360/kolibri` fork that differ from upstream `learningequality/kolibri`. It exists so future-you (or any agent) can re-apply these changes after syncing from upstream.

**Why this exists**: The upstream release pipeline assumes Learning Equality's signing certificates, PyPI/Play Store/GCS credentials, and LE Bot GitHub App. None of those exist on this fork, so the upstream workflows fail loudly on every trigger. The customizations below replace them with a stripped-down pipeline that produces **unsigned Windows EXE** and **debug-signed Android APK** artifacts for free (no secrets required) — sufficient for internal school use.

## Files modified or added on `develop`

### Added

| File | Purpose |
|------|---------|
| `.github/workflows/release_school.yml` | Fork-specific release workflow. Replaces `release_kolibri.yml` for this fork. Builds WHL, TAR, PEX, unsigned EXE, debug APK only. No signing, no publishing. |
| `SCHOOL_FORK_CHANGES.md` | This file. |

### Disabled (auto-trigger replaced with `workflow_dispatch:`)

These workflows all require Learning Equality org secrets (`LE_BOT_APP_ID`/`LE_BOT_PRIVATE_KEY`, `CROWDIN_API_KEY`, `SLACK_*`, GCP, Docker Hub) and fail noisily on the fork. Each has its `on:` block reduced to `workflow_dispatch:` only (manual trigger, never auto-fires). The body of each file is untouched.

| File | Original trigger | Why disabled |
|------|------------------|--------------|
| `release_kolibri.yml` | `release: [published]` | Replaced by `release_school.yml`. Full-pipeline version needs Azure/Apple/PyPI/GCS/Play Store secrets. |
| `call-manage-issue-header.yml` | `issues: [...]` | Calls LE Bot shared workflow. |
| `call-pull-request-target.yml` | `pull_request_target: [...]` | Calls LE Bot shared workflow. |
| `call-contributor-issue-comment.yml` | `issue_comment: [created]` | Calls LE Bot + Slack. |
| `call-contributor-pr-reply.yml` | `pull_request_target: [opened]` | Calls LE Bot + Slack. |
| `call-update-pr-spreadsheet.yml` | `pull_request_target: [...]` | Calls LE Bot + GCP + Google Sheets. |
| `community-contribution-label.yml` | `issues: [assigned, unassigned]` | Calls LE Bot shared workflow. |
| `update_contributors.yml` | `schedule: monthly cron` | Uses LE Bot to commit to repo. |
| `update_h5p.yml` | `schedule: weekly cron` | Uses LE Bot for PR. |
| `npm_version_comment.yml` | `workflow_run: [...]` | Uses LE Bot for PR comment. |
| `pr_labels.yml` | `pull_request_target` | Uses LE Bot token. |
| `npm_publish.yml` | `push` to `develop` (package.json paths) | Auto-publishes to npm; removed `push:` trigger, kept `workflow_dispatch:` for manual use. |

### Other customizations (pre-existing on `develop`)

These were committed before this doc existed and are preserved as-is:

| File | Customization |
|------|---------------|
| `.github/workflows/build_whl.yml` | Removed webpack + cext cache restore steps (caches were primed by `warm_build_cache.yml`, which is not present on this fork). |
| `.github/workflows/build_whl.yml` | Added "Set Kolibri version from tag (fork override)" step that sets `SETUPTOOLS_SCM_PRETEND_VERSION` from the GitHub ref, converting `v0.19.4-schoolN` → `0.19.4.postN`. The upstream `pyproject.toml` `tag_regex` only accepts `vX.Y.Z` or `vX.Y.Z-{alpha,beta,rc}N`, so school tags would otherwise fail at parse time under setuptools-scm 9.x. |
| `.github/workflows/container_image_publish.yml` | Stripped to remove Docker Hub dependency. |
| `.github/workflows/warm_build_cache.yml` | Not present on this fork (was deleted). |

> **Note on the previous Windows installer fork**: commit `984f36dd` (Jun 24) previously pointed the EXE build at `VibeCoder360/kolibri-installer-windows@main` with Python 3.10. That repo has since been deleted, so both `release_kolibri.yml` and `release_school.yml` now point back at the upstream `learningequality/kolibri-installer-windows@v1.6.9` (Python 3.8). To restore the Python 3.10 behavior, re-create the fork at `VibeCoder360/kolibri-installer-windows` and revert these references.

## Workflows that already auto-disable on forks

GitHub marks these as `disabled_fork` automatically — no action needed:
- `codeql.yml`
- `container_image_cleanup.yml`
- `morango_integration.yml`
- `postgres.yml`
- `unassign-inactive.yaml`

## Workflows intentionally left alone

These work fine on the fork with only the auto-injected `GITHUB_TOKEN`:
- `pr_build_kolibri.yml`, `pr_build_comment.yml` — PR asset builds (the workhorse)
- `pre-commit.yml`, `frontend-tests.yml`, `tox.yml`, `check_docs.yml`, `check_licenses.yml`, `no_zombies.yml` — tests/lint
- `build_whl.yml`, `build_pex.yml`, `upload_github_release_asset.yml` — release building blocks
- `npm_version_check.yml` — harmless check
- `i18n-upload.yml`, `i18n-download.yml` — already `workflow_dispatch` only, harmless
- `pypi_upload.yml`, `container_image_publish.yml` — only invoked via `workflow_call`, harmless now that `release_kolibri.yml` is disabled

## How to re-apply after syncing from upstream

When you merge `upstream/develop` into `fork/develop`, conflicts will most likely appear on the 12 disabled workflow files above (each has a 1-line `on: workflow_dispatch:` change). For each conflict:

1. Take `ours` (fork version) — keep `on: workflow_dispatch:`.
2. Re-apply the comment header (`# Disabled on school fork — ...`).

```bash
git merge upstream/develop
# For each conflicted .github/workflows/*.yml file:
git checkout --ours .github/workflows/<file>.yml
git add .github/workflows/<file>.yml
# If release_kolibri.yml gets a meaningful upstream update you want,
# manually re-apply ONLY the `on: workflow_dispatch:` change to the new version.
git commit
```

`release_school.yml` and `SCHOOL_FORK_CHANGES.md` should never conflict because they don't exist upstream.

## Branch hygiene for future upstream PRs

**Never PR `fork/develop` → `upstream/develop` directly.** It contains all the workflow customizations above, which Learning Equality does not want.

To contribute code changes (e.g. QR login) upstream:

```bash
# From a clean working tree
git remote add upstream https://github.com/learningequality/kolibri.git  # if not present
git fetch upstream

# Branch from UPSTREAM develop, not fork develop
git checkout -b feature/<your-feature> upstream/develop

# Cherry-pick or re-apply ONLY the code changes (no .github/workflows/*, no SCHOOL_FORK_CHANGES.md)
git cherry-pick <commit-sha>...

# Push to your fork and PR
git push -u fork feature/<your-feature>
# Then open PR: VibeCoder360:feature/<your-feature> → learningequality:develop
```

This guarantees the upstream PR diff contains only code changes, none of the fork-specific CI customization.

## Verifying a release build

After pushing changes to `fork/develop`:

1. Tag a new release: e.g. `git tag v0.19.4-schoolN && git push fork v0.19.4-schoolN`
2. Create the release in the GitHub UI (or `gh release create v0.19.4-schoolN --title "..." --notes "..."`)
3. Watch `release_school.yml` run: `https://github.com/VibeCoder360/kolibri/actions`
4. Expected artifacts on the release page:
   - `kolibri-<version>-py2.py3-none-any.whl`
   - `kolibri-<version>.tar.gz`
   - `kolibri-<version>.pex`
   - `kolibri-<version>-windows-setup-unsigned.exe` (SmartScreen warning is expected; click "More info → Run anyway")
   - `kolibri-<version>-<android-version>-debug.apk` (enable "Install unknown apps" on the tablet)

If any artifact is missing, check the failed job's logs at the link above.
