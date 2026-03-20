# GitHub Setup Guide

This project is already connected to:
`https://github.com/synryzen/6X-Protocol`

## 1) Enable GitHub Pages
1. Open repository settings.
2. Go to `Pages`.
3. Set source to `GitHub Actions`.
4. Push to `main` (or run workflow manually).
5. Wait for `Deploy GitHub Pages` workflow to complete.

If the repository is private:
- GitHub Pages requires a plan that supports private Pages.
- If deployment fails, verify plan access first, then re-run `Deploy GitHub Pages`.

Expected URL:
`https://synryzen.github.io/6X-Protocol/`

## 2) Enable Security Reporting
1. Go to `Security` tab.
2. Enable `Private vulnerability reporting`.

## 3) Create First Public Release
1. Commit/push current stable state.
2. Create tag:
```bash
git tag -a v0.1.0 -m "6X-Protocol Studio v0.1.0"
git push origin v0.1.0
```
3. The `Build Release Packages` workflow will auto-build and attach:
   - `.deb` installer
   - portable `.tar.gz`
   - `.AppImage`
   - `.flatpak` bundle
   - `SHA256SUMS.txt`
4. Open the release in GitHub and verify assets are attached.
5. Publish/edit release notes.

## 4) Build Installers Locally (Optional)
```bash
./scripts/build_packages.sh
```
Artifacts are written to `dist/`.

## 5) Recommended Repo Settings
### Branch Protection (Strongly Recommended)
Use `Settings` -> `Rules` -> `Rulesets` -> `New ruleset` (or branch protection rule on `main`):
- Target: `main`.
- Require a pull request before merging.
- Require approvals: `1` (or `0` for solo mode if you prefer speed).
- Dismiss stale approvals when new commits are pushed.
- Require status checks to pass before merging:
  - `compile` (from `CI` workflow).
- Require conversation resolution before merging.
- Block force pushes.
- Block deletions.

### Optional Strict Mode
- Require branch to be up to date before merge.
- Require linear history.
- Restrict direct pushes to `main` (allow only maintainers/admin bypass).

### Why `compile` Check
The `CI` workflow currently exposes one job named `compile` that runs:
- `python -m compileall src main.py`
- `python -m unittest discover -s tests -p "test_*.py" -v`

If you rename the job in `.github/workflows/ci.yml`, update the required check name in Rules.

## 6) Labels + Triage Automation
This repo now includes:
- `.github/labels.yml` + `.github/workflows/labels.yml` (sync label taxonomy).
- `.github/labeler.yml` + `.github/workflows/triage.yml` (auto area labels for PRs + `needs-triage` on new issues/PRs).

After enabling Actions, run once manually:
1. `Actions` tab -> `Sync Labels` -> `Run workflow`.
2. Confirm labels were created in `Issues` -> `Labels`.
3. Open a test issue/PR to confirm triage labels apply.

## 7) Public Visibility Checklist
- Remove local/private secrets from config files.
- Confirm no credentials are committed.
- Confirm `.gitignore` is active and caches/artifacts are not tracked.
- Confirm README, LICENSE, SECURITY, CONTRIBUTING are present.
