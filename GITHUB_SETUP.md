# GitHub Setup Guide

This project is already connected to:
`https://github.com/synryzen/6X-Protocol`

## 1) Enable GitHub Pages
1. Open repository settings.
2. Go to `Pages`.
3. Set source to `GitHub Actions`.
4. Push to `main` (or run workflow manually).
5. Wait for `Deploy GitHub Pages` workflow to complete.

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
- Branch protection on `main`.
- Require pull request for merges (optional for solo workflow).
- Require CI pass before merge.
- Enable Discussions (optional community channel).

## 6) Public Visibility Checklist
- Remove local/private secrets from config files.
- Confirm no credentials are committed.
- Confirm `.gitignore` is active and caches/artifacts are not tracked.
- Confirm README, LICENSE, SECURITY, CONTRIBUTING are present.
