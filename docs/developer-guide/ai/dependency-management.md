# Dependency Management for Components

## Overview

Components must declare all Python dependencies to work in both local and E2B environments.

## requirements.txt Structure

Each component that needs external packages should have dependencies declared.

### Where to Declare

**Option 1: Project-level** (most common)
File: `/Users/padak/github/osiris/requirements.txt`

Add your dependencies to the main file:
```txt
# Existing dependencies
pandas>=1.5.0
pyyaml>=6.0
requests>=2.28.0

# Your component dependencies
stripe>=5.0.0  # For stripe.extractor
graphql-core>=3.2.0  # For graphql.extractor
```

**Option 2: Component-level** (future)
File: `components/myservice.extractor/requirements.txt`

Currently not supported, but planned for M2.

### Dependency Guidelines

**DO:**
- ✅ Pin major versions: `requests>=2.28.0,<3.0.0`
- ✅ Use stable packages from PyPI
- ✅ Declare ALL imports (even transitive)
- ✅ Test with fresh venv

**DON'T:**
- ❌ Use local packages not on PyPI
- ❌ Rely on system-installed packages
- ❌ Use unpinned versions (no `requests`)
- ❌ Forget transitive dependencies

## Virtual Environment Setup

### Creating venv

```bash
# Create virtual environment
python3 -m venv .venv

# Activate (macOS/Linux)
source .venv/bin/activate

# Activate (Windows)
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Verify
pip list
```

### Testing with Clean venv

Before committing component:
```bash
# Deactivate current venv
deactivate

# Remove old venv
rm -rf .venv

# Create fresh venv
python3 -m venv .venv
source .venv/bin/activate

# Install and test
pip install -r requirements.txt
pytest tests/drivers/test_myservice_*

# If tests pass, dependencies are complete!
```

## Common Dependencies by Component Type

### REST API Components
```txt
requests>=2.28.0
urllib3>=1.26.0
```

### GraphQL Components
```txt
gql>=3.4.0
graphql-core>=3.2.0
```

### Database Components
```txt
# MySQL
pymysql>=1.0.0
mysqlclient>=2.1.0  # Optional, better performance

# PostgreSQL
psycopg2-binary>=2.9.0

# Supabase
supabase>=1.0.0
```

### Data Processing
```txt
pandas>=1.5.0
numpy>=1.23.0
```

## E2B Considerations

E2B cloud sandbox:
- Only has Python + dependencies in requirements.txt
- No system packages (apt, brew)
- Clean environment on each run

**Test E2B compatibility:**
```bash
# Run in E2B
osiris run pipeline.yaml --e2b

# Check logs for import errors
osiris logs --e2b --last | grep "ModuleNotFoundError"
```

## Troubleshooting

### Error: "ModuleNotFoundError: No module named 'X'"

**Local environment:**
```bash
pip install X
pip freeze | grep X >> requirements.txt
```

**E2B environment:**
1. Add to requirements.txt
2. Commit and push
3. Test with `--e2b` flag

### Error: "Conflicting dependencies"

**Fix:**
```bash
# Check conflicts
pip check

# Resolve by pinning versions
pip install "package>=X.Y,<X+1.0"
```

### Error: "Package not found on PyPI"

**Fix:**
- Use alternative package from PyPI
- Or vendor the code (copy into codebase)
- Do NOT use git+https:// URLs

## Best Practices

1. **Minimal dependencies**: Use standard library when possible
2. **Version pinning**: Always pin major versions
3. **Test clean install**: Fresh venv before commit
4. **Document extras**: If optional features need packages, note in README

## Related Documentation

- e2b-compatibility.md - E2B sandbox requirements
- build-new-component.md - Component structure
