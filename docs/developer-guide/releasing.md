# Osiris Release Process

This guide covers how to release new versions of Osiris to PyPI, making it available for users to install with `pip install osiris-pipeline` or `uvx osiris-pipeline`.

## Prerequisites

1. **PyPI Account & Tokens**
   - Create account at https://pypi.org
   - Create account at https://test.pypi.org (for testing)
   - Generate API tokens:
     - PyPI: https://pypi.org/manage/account/token/
     - TestPyPI: https://test.pypi.org/manage/account/token/
   - Store tokens in `~/.pypirc`:
     ```ini
     [pypi]
     username = __token__
     password = pypi-AgE...your-token-here...

     [testpypi]
     username = __token__
     password = pypi-AgE...your-test-token...
     repository = https://test.pypi.org/legacy/
     ```

2. **GitHub Secrets** (for automated publishing)
   - Go to repository Settings → Secrets and variables → Actions
   - Add secrets:
     - `PYPI_API_TOKEN` - Production PyPI token
     - `TEST_PYPI_API_TOKEN` - TestPyPI token

3. **Development Tools**
   ```bash
   pip install -e ".[dev]"  # Includes build, twine
   ```

## Version Bumping

Before releasing, update version in these files:

1. **pyproject.toml** (line 7):
   ```toml
   version = "0.5.1"
   ```

2. **osiris/__init__.py** (line 17):
   ```python
   __version__ = "0.5.1"
   ```

3. **CHANGELOG.md** - Add new section:
   ```markdown
   ## [0.5.1] - 2025-11-XX
   ### Added
   - New feature description
   ### Fixed
   - Bug fix description
   ```

4. **README.md** - Update current version in roadmap if needed

## Release Workflow

### Option 1: Test on TestPyPI First (Recommended)

#### 1. Build and Test Locally

```bash
# Clean previous builds
make clean

# Build distribution
make build

# Check package is valid
make check-dist

# Verify components are included
unzip -l dist/*.whl | grep -E "components/"
# Should show: components/mysql.extractor/spec.yaml, etc.
```

#### 2. Test Installation Locally

```bash
# Install from wheel
pip install dist/osiris_pipeline-*.whl

# Verify version
osiris --version

# Test components load
python -c "from osiris.components.registry import ComponentRegistry; r = ComponentRegistry(); print(r.list_components())"

# Should output: ['mysql.extractor', 'mysql.writer', 'supabase.extractor', ...]
```

#### 3. Publish to TestPyPI

```bash
# Upload to TestPyPI
make upload-test

# Or manually:
# twine upload --repository testpypi dist/*
```

#### 4. Test from TestPyPI

```bash
# Create test environment
python -m venv test-venv
source test-venv/bin/activate

# Install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  osiris-pipeline

# Note: --extra-index-url needed for dependencies

# Test it works
osiris --version
osiris init
osiris mcp run --selftest

# Test with uvx
uvx --from https://test.pypi.org/simple/ osiris-pipeline --version

# Cleanup
deactivate
rm -rf test-venv
```

#### 5. Publish to Production PyPI

If TestPyPI testing passed:

```bash
# Clean and rebuild (ensures fresh dist/)
make clean
make build

# Upload to PyPI with confirmation prompt
make upload-pypi
# Type 'yes' when prompted

# Or manually:
# twine upload dist/*
```

### Option 2: Automated via GitHub Release

1. **Create and Push Git Tag**
   ```bash
   git tag -a v0.5.1 -m "Release v0.5.1"
   git push origin v0.5.1
   ```

2. **Create GitHub Release**
   - Go to https://github.com/keboola/osiris/releases/new
   - Select tag: `v0.5.1`
   - Title: `v0.5.1`
   - Description: Copy from CHANGELOG.md
   - Click "Publish release"

3. **GitHub Actions Auto-Publishes**
   - Workflow runs automatically
   - Builds package
   - Publishes to PyPI
   - Check status: https://github.com/keboola/osiris/actions

### Option 3: Manual Trigger via GitHub Actions

For testing without creating a release:

1. Go to https://github.com/keboola/osiris/actions/workflows/publish-pypi.yml
2. Click "Run workflow"
3. Select target:
   - `testpypi` - Publish to TestPyPI
   - `pypi` - Publish to production PyPI
4. Click "Run workflow"

## Verification After Publishing

### 1. Check PyPI Page

- Production: https://pypi.org/project/osiris-pipeline/
- TestPyPI: https://test.pypi.org/project/osiris-pipeline/

Verify:
- Version number is correct
- README renders correctly
- All classifiers are shown
- Dependencies are listed

### 2. Test Installation

```bash
# Fresh environment
python -m venv verify-venv
source verify-venv/bin/activate

# Install from PyPI
pip install osiris-pipeline

# Verify
osiris --version  # Should show new version
osiris mcp run --selftest  # Should pass

# Test with uvx (doesn't need venv)
uvx osiris-pipeline --version
uvx osiris-pipeline init

# Cleanup
deactivate
rm -rf verify-venv
```

### 3. Test Component Loading

Critical check - components must be in package:

```bash
python -c "
from osiris.components.registry import ComponentRegistry
r = ComponentRegistry()
components = r.list_components()
print(f'Found {len(components)} components: {components}')
assert len(components) >= 8, 'Missing component specs!'
"
```

Expected output:
```
Found 8 components: ['mysql.extractor', 'mysql.writer', 'supabase.extractor', 'supabase.writer', 'duckdb.processor', 'graphql.extractor', 'filesystem.csv_extractor', 'filesystem.csv_writer']
```

## Troubleshooting

### Components Not Found After Install

**Problem**: `ComponentRegistry` can't find specs

**Fix**: Verify packaging:
```bash
# Check wheel contents
unzip -l dist/*.whl | grep components/

# Should see:
# components/mysql.extractor/spec.yaml
# components/mysql.writer/spec.yaml
# ...
```

If missing, check:
1. `pyproject.toml` has `[tool.setuptools.package-data]` section
2. `MANIFEST.in` includes `recursive-include components *.yaml`

### Upload Fails with 403 Forbidden

**Problem**: Authentication failed

**Fix**:
1. Verify `~/.pypirc` has correct tokens
2. Token format: `pypi-AgE...` (starts with `pypi-`)
3. Generate new token if needed
4. For GitHub Actions, check repository secrets

### Version Already Exists

**Problem**: `File already exists` error

**Fix**: You cannot overwrite existing versions on PyPI
1. Bump version number in `pyproject.toml` and `osiris/__init__.py`
2. Rebuild: `make clean && make build`
3. Upload again

### TestPyPI Installation Fails with Missing Dependencies

**Problem**: TestPyPI doesn't have all dependencies

**Solution**: Use both indexes:
```bash
pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  osiris-pipeline
```

## Post-Release Checklist

After successful release:

- [ ] Verify PyPI page looks correct
- [ ] Test `pip install osiris-pipeline`
- [ ] Test `uvx osiris-pipeline init`
- [ ] Announce on GitHub Discussions/social media
- [ ] Update documentation if needed
- [ ] Close related GitHub issues/PRs
- [ ] Update project board/milestones

## Quick Reference

```bash
# Local testing
make clean && make build && make check-dist

# Upload to TestPyPI
make upload-test

# Upload to PyPI (production)
make upload-pypi

# Test from TestPyPI
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ osiris-pipeline

# Test from PyPI
pip install osiris-pipeline
uvx osiris-pipeline --version
```

## Related Documentation

- [PyPI Publishing Guide](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
- [PEP 517 - Build Backend Interface](https://peps.python.org/pep-0517/)
- [PEP 621 - Project Metadata](https://peps.python.org/pep-0621/)
- [Twine Documentation](https://twine.readthedocs.io/)
