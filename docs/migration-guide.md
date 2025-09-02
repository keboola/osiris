# Migration Guide: Load to Write Mode

## Overview

Starting with Osiris v0.2.0, we're standardizing on `write` mode for all data writing operations. The `load` mode is deprecated but still supported for backward compatibility.

## What's Changing

### Terminology
- **Old**: Components used `load` mode for writing data
- **New**: Components use `write` mode for writing data
- **Additional**: Writers now support `discover` mode for schema inspection

### Component Modes
| Component Type | Old Modes | New Modes |
|---------------|-----------|-----------|
| Extractors | `['extract', 'discover']` | `['extract', 'discover']` (unchanged) |
| Writers | `['load']` | `['write', 'discover']` |

## Migration Steps

### 1. Update Pipeline YAML Files

**Before:**
```yaml
name: customer_pipeline
steps:
  - type: mysql.extractor
    mode: extract
    config:
      host: localhost
      database: source_db
      table: customers
      
  - type: supabase.writer
    mode: load  # Old mode
    config:
      url: https://project.supabase.co
      table: customers
```

**After:**
```yaml
name: customer_pipeline
steps:
  - type: mysql.extractor
    mode: extract
    config:
      host: localhost
      database: source_db
      table: customers
      
  - type: supabase.writer
    mode: write  # New mode
    config:
      url: https://project.supabase.co
      table: customers
```

### 2. Update Custom Components

If you've created custom writer components:

**Before:**
```yaml
# components/custom.writer/spec.yaml
name: custom.writer
modes:
  - load
capabilities:
  discover: false
```

**After:**
```yaml
# components/custom.writer/spec.yaml
name: custom.writer
modes:
  - write
  - discover
capabilities:
  discover: true
```

### 3. Update Component Code

If you have custom component implementations:

**Before:**
```python
class CustomWriter:
    def load(self, data):
        # Writing logic
        pass
```

**After:**
```python
class CustomWriter:
    def write(self, data):
        # Writing logic (same as before)
        pass
    
    def discover(self):
        # Optional: Add schema discovery
        return {"tables": [...]}
```

## Backward Compatibility

### Transition Period
- **v0.2.x**: Both `load` and `write` modes are supported
- **v1.0.0**: `load` mode will generate deprecation warnings
- **v2.0.0**: `load` mode will be removed entirely

### Automatic Mapping
During the transition period, Osiris will automatically map:
- `mode: load` → `mode: write` internally
- No changes required for existing pipelines to continue working

## Benefits of the Change

### 1. Consistency
- Clear distinction: `extract` for reading, `write` for writing
- Aligns with modern ETL terminology (Extract, Transform, Write)

### 2. Discovery Capability
- Writers can now inspect target schemas before writing
- Enables better validation and error prevention
- Supports schema evolution and migrations

### 3. LLM Context
- Improved AI understanding with consistent terminology
- Better pipeline generation from natural language
- Clearer intent in conversational interfaces

## CLI Changes

### New Component Commands
```bash
# List all writer components
osiris components list --mode write

# Show writer details
osiris components show mysql.writer

# Validate component specification
osiris components validate mysql.writer

# See example configurations
osiris components config-example mysql.writer
```

## Validation

### Check Your Pipelines
```bash
# Validate existing pipelines
osiris validate --mode strict

# Test with new mode
osiris run pipeline.yaml --dry-run
```

### Component Validation
```bash
# Validate all components
for comp in components/*/; do
  name=$(basename $comp)
  osiris components validate $name
done
```

## FAQ

### Q: Will my existing pipelines break?
**A:** No, existing pipelines with `load` mode will continue to work. The mode is deprecated but still supported.

### Q: When do I need to migrate?
**A:** We recommend migrating before v2.0.0 (planned for late 2025). Start using `write` mode for all new pipelines immediately.

### Q: What about third-party components?
**A:** Component authors should update their specs to use `write` mode. Contact maintainers or submit PRs to update components you depend on.

### Q: How do I know if I'm using deprecated features?
**A:** Run `osiris validate --mode strict` to check for deprecation warnings in your configuration.

## Getting Help

If you encounter issues during migration:

1. Check component specifications: `osiris components show <name>`
2. Validate configurations: `osiris validate --mode strict`
3. Review logs: `osiris logs show --session <id>`
4. Report issues: [GitHub Issues](https://github.com/osiris/issues)

## References

- [ADR-0012: Separate Extractors and Writers](adr/0012-separate-extractors-and-writers.md)
- [Component Specification Reference](components-spec.md)
- [M1a.2 Bootstrap Component Specs](milestones/m1a.2-bootstrap-component-specs.md)
