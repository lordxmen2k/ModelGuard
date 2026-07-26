# Publishing AI Model Guard to PyPI

This document walks you through the complete process of building, testing, and publishing AI Model Guard to the Python Package Index (PyPI) so it can be installed with `pip install aimodelguard`.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Initial Setup](#initial-setup)
3. [Pre-Publish Checklist](#pre-publish-checklist)
4. [Building the Package](#building-the-package)
5. [Testing on TestPyPI](#testing-on-testpypi)
6. [Publishing to PyPI](#publishing-to-pypi)
7. [Post-Publish](#post-publish)
8. [Updating the Package](#updating-the-package)
9. [Troubleshooting](#troubleshooting)
10. [GitHub Actions Automation](#github-actions-automation)

---

## Prerequisites

Before you can publish to PyPI, you need:

### 1. Python 3.11 or higher

```bash
python --version
# Should show: Python 3.11.x or higher
```

If you need to install Python, download it from [python.org](https://www.python.org/downloads/).

### 2. Build tools

Install the necessary tools for building and publishing:

```bash
pip install --upgrade build twine setuptools wheel
```

### 3. PyPI Account

Create accounts on both TestPyPI and PyPI:

- **TestPyPI:** https://test.pypi.org/account/register/
- **PyPI:** https://pypi.org/account/register/

### 4. API Tokens

Generate API tokens for secure authentication:

1. Go to https://pypi.org/manage/account/token/
2. Click "Add API token"
3. Give it a name (e.g., "aimodelguard-upload")
4. Set scope: "Entire account" (or limit to a project after first upload)
5. Copy the token immediately (you won't see it again!)

**Important:** Save the token in a secure location. You'll need it for uploading.

For TestPyPI, generate a separate token at https://test.pypi.org/manage/account/token/

---

## Initial Setup

### 1. Clone the repository

```bash
git clone https://github.com/lordxmen2k/aimodelguard.git
cd AI Model Guard
```

### 2. Install in development mode

```bash
pip install -e ".[dev]"
```

This installs AI Model Guard in editable mode with all development dependencies (pytest, build, twine, etc.).

### 3. Run tests to verify everything works

```bash
pytest tests/ -v
```

Or if you don't have pytest installed:

```bash
python tests/test_basic.py
```

All tests should pass. If they don't, **do not publish** until you fix them.

### 4. Configure PyPI credentials

Create a `~/.pypirc` file with your credentials:

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-YOUR-TOKEN-HERE

[testpypi]
username = __token__
password = pypi-YOUR-TESTPYPI-TOKEN-HERE
```

Replace `pypi-YOUR-TOKEN-HERE` with your actual PyPI token.

**Security note:** Never commit this file to git. Add it to `.gitignore` if not already there.

---

## Pre-Publish Checklist

Before publishing, verify:

- [ ] All tests pass (`pytest tests/ -v`)
- [ ] Version number is updated in `setup.py` and `pyproject.toml`
- [ ] CHANGELOG.md is updated (if you have one)
- [ ] README.md is up to date
- [ ] LICENSE file is present and correct
- [ ] Git status is clean (commit all changes)
- [ ] Git tag is created for the version (e.g., `v0.1.0`)
- [ ] No sensitive information in the code (API keys, passwords, etc.)
- [ ] All dependencies are listed in `install_requires`

---

## Building the Package

### 1. Clean previous builds

```bash
rm -rf build/ dist/ *.egg-info aimodelguard.egg-info
```

### 2. Build the distribution packages

```bash
python -m build
```

This creates both source distribution (`.tar.gz`) and wheel (`.whl`) in the `dist/` directory.

**Expected output:**

```
dist/
  aimodelguard-0.1.0-py3-none-any.whl
  aimodelguard-0.1.0.tar.gz
```

### 3. Verify the build

```bash
ls -lh dist/
```

You should see two files:
- `aimodelguard-0.1.0-py3-none-any.whl` (~20-30 KB)
- `aimodelguard-0.1.0.tar.gz` (~15-20 KB)

### 4. Inspect the package contents

```bash
# Check the wheel
unzip -l dist/aimodelguard-0.1.0-py3-none-any.whl

# Check the source distribution
tar -tzf dist/aimodelguard-0.1.0.tar.gz
```

Verify that all your files are included.

### 5. Validate the package metadata

```bash
twine check dist/*
```

This checks that your package metadata is valid and renders correctly on PyPI.

**Expected output:**

```
Checking dist/aimodelguard-0.1.0-py3-none-any.whl: PASSED
Checking dist/aimodelguard-0.1.0.tar.gz: PASSED
```

If you see any warnings or errors, fix them before proceeding.

---

## Testing on TestPyPI

**Always test on TestPyPI first!** This is a separate instance of PyPI where you can safely test your upload process without affecting the real PyPI.

### 1. Upload to TestPyPI

```bash
twine upload --repository testpypi dist/*
```

You'll be prompted for credentials (or use `~/.pypirc`).

**Expected output:**

```
Uploading distributions to https://test.pypi.org/legacy/
Uploading aimodelguard-0.1.0-py3-none-any.whl
100%|████████████| XX/XX [00:01<00:00, XX.XkB/s]
Uploading aimodelguard-0.1.0.tar.gz
100%|████████████| XX/XX [00:01<00:00, XX.XkB/s]

View at:
https://test.pypi.org/project/aimodelguard/0.1.0/
```

### 2. Test the installation

Create a fresh virtual environment and test:

```bash
# Create a test environment
python -m venv test-env
source test-env/bin/activate  # On Windows: test-env\Scripts\activate

# Install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ aimodelguard

# Test the command
aimodelguard --version
aimodelguard --help

# Run the tests
pytest tests/ -v
# (The CLI workflow test uses the hardcoded password 'test_password_123'
#  internally — you do NOT need to type a password when running the tests.)

# Clean up
deactivate
rm -rf test-env
```

### 3. Verify the package page

Visit https://test.pypi.org/project/aimodelguard/ and check:
- README renders correctly
- Metadata is correct
- Links work
- License is detected

---

## Publishing to PyPI

**Once you've verified everything works on TestPyPI:**

### 1. Upload to PyPI

```bash
twine upload dist/*
```

**Expected output:**

```
Uploading distributions to https://upload.pypi.org/legacy/
Uploading aimodelguard-0.1.0-py3-none-any.whl
100%|████████████| XX/XX [00:01<00:00, XX.XkB/s]
Uploading aimodelguard-0.1.0.tar.gz
100%|████████████| XX/XX [00:01<00:00, XX.XkB/s]

View at:
https://pypi.org/project/aimodelguard/
```

### 2. Verify the release

Visit https://pypi.org/project/aimodelguard/ and check:
- Package page looks correct
- README renders properly
- All metadata is accurate
- Download links work

### 3. Test the public installation

```bash
# In a fresh environment
python -m venv verify-env
source verify-env/bin/activate

pip install aimodelguard
aimodelguard --version

deactivate
rm -rf verify-env
```

### 4. Announce the release

- Create a GitHub release: https://github.com/lordxmen2k/aimodelguard/releases/new
- Tag: `v0.1.0`
- Title: "AI Model Guard v0.1.0 — Initial Alpha Release"
- Description: Copy from CHANGELOG.md or write release notes
- Attach the built files from `dist/` (optional)

---

## Post-Publish

### 1. Tag the release in Git

```bash
git tag -a v0.1.0 -m "Release version 0.1.0"
git push origin v0.1.0
```

### 2. Update the version

In `setup.py` and `pyproject.toml`, bump to the next development version:

```python
version="0.1.0.dev0"  # or "0.2.0a1" for alpha
```

### 3. Clean up build artifacts

```bash
rm -rf build/ dist/ *.egg-info
```

### 4. Monitor for issues

- Watch the GitHub issue tracker
- Monitor PyPI download statistics
- Check for bug reports
- Respond to user questions

---

## Updating the Package

To release a new version:

### 1. Make your changes

```bash
git checkout -b feature/new-feature
# Make your changes
git add -A
git commit -m "feat: add new feature"
git push origin feature/new-feature
```

### 2. Update the version

In `setup.py` and `pyproject.toml`:

```python
version="0.1.1"  # or "0.2.0", "1.0.0", etc.
```

### 3. Update CHANGELOG.md

```markdown
## [0.1.1] - 2026-XX-XX

### Added
- New feature X

### Fixed
- Bug Y

### Changed
- Updated Z
```

### 4. Run tests

```bash
pytest tests/ -v
```

### 5. Commit and tag

```bash
git add -A
git commit -m "chore: bump version to 0.1.1"
git tag -a v0.1.1 -m "Release version 0.1.1"
git push origin main --tags
```

### 6. Build and publish

```bash
# Clean
rm -rf build/ dist/ *.egg-info

# Build
python -m build

# Test on TestPyPI
twine upload --repository testpypi dist/*

# Verify
# (test in a fresh environment)

# Publish to PyPI
twine upload dist/*
```

---

## Troubleshooting

### Error: "File already exists"

If you try to upload the same version twice, PyPI will reject it.

**Solution:** You cannot re-upload the same version. You must:
1. Increment the version number
2. Rebuild the package
3. Upload the new version

To yank a broken release, go to PyPI → Your Project → Release History → Select version → "Yank".

### Error: "Invalid distribution filename"

The package name or version format is incorrect.

**Solution:** Ensure:
- Name is lowercase with hyphens (e.g., `aimodelguard`, not `AI Model Guard`)
- Version follows PEP 440 (e.g., `1.0.0`, `0.1.0a1`, `1.0.0.dev0`)

### Error: "Missing required field"

Your `pyproject.toml` or `setup.py` is missing required metadata.

**Solution:** Add all required fields:
- name
- version
- author
- description
- license
- python_requires

### Error: "Invalid classifier"

A classifier in your list is not recognized by PyPI.

**Solution:** Check the official classifier list: https://pypi.org/classifiers/

### Error: "Long description has invalid syntax"

Your README.md has formatting issues that break reStructuredText or Markdown.

**Solution:**
- Ensure `long_description_content_type = "text/markdown"` is set
- Validate your Markdown syntax
- Run `twine check dist/*` to identify the issue

### Error: "Package metadata is missing 'License'"

The license field is not set or not recognized.

**Solution:** Use the SPDX identifier in `pyproject.toml`:
```toml
license = {text = "Apache-2.0"}
```

Or in `setup.py`:
```python
license="Apache-2.0"
```

### Error: "Authentication required"

Your credentials are not configured correctly.

**Solution:**
1. Verify `~/.pypirc` exists and has correct format
2. Use `__token__` as username
3. Use the full token (including `pypi-` prefix) as password
4. Or pass credentials directly: `twine upload -u __token__ -p pypi-YOUR-TOKEN dist/*`

---

## GitHub Actions Automation

To automate publishing on every GitHub release, create `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install build twine

    - name: Build package
      run: python -m build

    - name: Check package
      run: twine check dist/*

    - name: Publish to TestPyPI
      env:
        TWINE_USERNAME: __token__
        TWINE_PASSWORD: ${{ secrets.TEST_PYPI_TOKEN }}
      run: twine upload --repository testpypi dist/*

    - name: Publish to PyPI
      if: success()
      env:
        TWINE_USERNAME: __token__
        TWINE_PASSWORD: ${{ secrets.PYPI_TOKEN }}
      run: twine upload dist/*
```

### Setup steps:

1. Go to your GitHub repository settings
2. Click "Secrets and variables" → "Actions"
3. Add two secrets:
   - `TEST_PYPI_TOKEN` — your TestPyPI API token
   - `PYPI_TOKEN` — your PyPI API token
4. Create a new release on GitHub
5. The workflow will automatically build and publish to both TestPyPI and PyPI

---

## Quick Reference

### Complete publish workflow (copy-paste)

```bash
# 1. Clean and test
rm -rf build/ dist/ *.egg-info
pytest tests/ -v

# 2. Update version in setup.py and pyproject.toml

# 3. Build
python -m build

# 4. Validate
twine check dist/*

# 5. Upload to TestPyPI
twine upload --repository testpypi dist/*

# 6. Test the TestPyPI installation
python -m venv test-env && source test-env/bin/activate
pip install --index-url https://test.pypi.org/simple/ aimodelguard
aimodelguard --version
deactivate && rm -rf test-env

# 7. Upload to PyPI
twine upload dist/*

# 8. Tag the release
git tag -a v0.1.0 -m "Release version 0.1.0"
git push origin v0.1.0

# 9. Create GitHub release
# Go to: https://github.com/lordxmen2k/aimodelguard/releases/new

# 10. Clean up
rm -rf build/ dist/ *.egg-info
```

---

## Additional Resources

- **PyPI Help:** https://pypi.org/help/
- **Packaging Guide:** https://packaging.python.org/
- **Twine Documentation:** https://twine.readthedocs.io/
- **GitHub Actions:** https://docs.github.com/en/actions

---

## License

This document is part of AI Model Guard, licensed under Apache 2.0.

Copyright 2026 Gerald Enrique Nelson Mc Kenzie
