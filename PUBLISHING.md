# Publishing Guide

This document explains how to publish `loko` to PyPI and TestPyPI.

## Overview

The project uses a two-stage publishing process:
1. **TestPyPI** - Test the package in a safe environment
2. **PyPI** - Publish to production after verification

## Prerequisites

### 1. TestPyPI Account Setup
1. Create an account at https://test.pypi.org/account/register/
2. Verify your email address
3. Generate an API token:
   - Go to https://test.pypi.org/manage/account/token/
   - Click "Add API token"
   - Token name: `loko-github-actions`
   - Scope: "Entire account" (or project-specific after first upload)
   - **Save the token securely** - you can only see it once!

### 2. PyPI Account Setup (Production)
1. Create an account at https://pypi.org/account/register/
2. Verify your email address
3. Configure trusted publishing (recommended) or create an API token

### 3. GitHub Secrets Configuration
Add these secrets to your GitHub repository (`Settings > Secrets and variables > Actions`):

- **`TEST_PYPI_API_TOKEN`** (Required)
  - Your TestPyPI API token from step 1
  - Format: `pypi-...`

- **`PYPI_API_TOKEN`** (Optional - only if not using trusted publishing)
  - Your PyPI API token
  - Format: `pypi-...`

### 4. GitHub Environments Setup (For Manual Approval)

1. Go to `Settings > Environments`
2. Create two environments:

#### TestPyPI Environment
- Name: `testpypi`
- Protection rules: None (auto-deploy)
- Environment secrets: None needed (uses repository secret)

#### PyPI Environment (Production)
- Name: `pypi`
- Protection rules:
  - ✅ Required reviewers (add yourself or team members)
  - ⏰ Wait timer: 10 minutes (optional - time to test TestPyPI version)
- Environment secrets: None needed if using trusted publishing

## Publishing Workflows

### Workflow 1: Full Release (TestPyPI → PyPI)

**File:** `.github/workflows/publish.yml`

**Trigger:** Creating a GitHub Release

**Process:**
```
1. Build package
2. Publish to TestPyPI (automatic)
3. Wait for manual approval (if configured)
4. Publish to PyPI (after approval)
```

**Steps:**
1. Update version in `pyproject.toml`:
   ```bash
   # Example: 0.1.0 → 0.2.0
   sed -i 's/version = "0.1.0"/version = "0.2.0"/' pyproject.toml
   git add pyproject.toml
   git commit -m "chore: bump version to 0.2.0"
   git push
   ```

2. Create a new release on GitHub:
   - Go to https://github.com/bojanraic/loko/releases/new
   - Tag: `v0.2.0`
   - Title: `v0.2.0`
   - Description: Release notes
   - Click "Publish release"

3. Monitor the workflow:
   - Go to Actions tab
   - Watch "Build and Publish" workflow
   - Package is published to TestPyPI automatically
   - Approve the PyPI deployment when ready

4. Test from TestPyPI:
   ```bash
   pip install --index-url https://test.pypi.org/simple/ \
               --extra-index-url https://pypi.org/simple/ \
               loko
   ```

5. After testing, approve the PyPI deployment in GitHub Actions

### Workflow 2: Manual TestPyPI Publish (Development Testing)

**File:** `.github/workflows/publish-testpypi.yml`

**Trigger:** Manual workflow dispatch

**Use case:** Test package builds without creating a release

**Steps:**
1. Go to Actions → "Publish to TestPyPI (Manual)"
2. Click "Run workflow"
3. Enter version suffix (e.g., `dev1`, `rc1`, `beta1`)
   - This will publish as `0.1.0.dev1` to avoid conflicts
4. Click "Run workflow"
5. Monitor the build and publish

**Testing the dev version:**
```bash
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ \
            loko==0.1.0.dev1
```

## Version Management

### Versioning Scheme
Follow [Semantic Versioning](https://semver.org/):
- `MAJOR.MINOR.PATCH` (e.g., `1.2.3`)
- `MAJOR.MINOR.PATCH.devN` (development/pre-release)
- `MAJOR.MINOR.PATCH.rcN` (release candidate)

### Version Update Checklist
- [ ] Update `version` in `pyproject.toml`
- [ ] Update `CHANGELOG.md` (if exists)
- [ ] Commit changes
- [ ] Create Git tag matching version
- [ ] Create GitHub release

## Testing Published Packages

### From TestPyPI
```bash
# Install
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ \
            loko

# Verify
loko --help
loko --version
```

### From PyPI (Production)
```bash
# Install
pip install loko

# Verify
loko --help
loko --version
```

## Troubleshooting

### "File already exists" on TestPyPI
- TestPyPI doesn't allow re-uploading the same version
- Increment the version or add a dev suffix (e.g., `0.1.0.dev2`)

### Missing dependencies when installing from TestPyPI
- Use `--extra-index-url https://pypi.org/simple/` to fetch dependencies from PyPI
- TestPyPI may not have all your dependencies

### Trusted Publishing Not Working
- Verify environment name matches exactly: `pypi`
- Check that PyPI project has trusted publishing configured
- See: https://docs.pypi.org/trusted-publishers/

### Token Authentication Issues
- Verify secret name: `TEST_PYPI_API_TOKEN`
- Ensure token hasn't expired
- Check token has correct scope (entire account or project)

## Security Notes

- **Never commit API tokens** to the repository
- Use GitHub Secrets for all tokens
- Prefer trusted publishing over API tokens for PyPI
- Regularly rotate API tokens
- Use environment protection rules for production deployments

## References

- [PyPI Documentation](https://pypi.org/)
- [TestPyPI Documentation](https://test.pypi.org/)
- [GitHub Actions Publishing](https://docs.github.com/en/actions/automating-builds-and-tests/building-and-testing-python#publishing-to-package-registries)
- [Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
