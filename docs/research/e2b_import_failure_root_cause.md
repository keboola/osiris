# E2B Import Failure Root Cause Analysis

**Date**: September 29, 2025
**Branch**: debug/codex-test
**Issue**: `fatal import_error: No module named 'osiris.components'`

## Executive Summary

The E2B execution fails immediately on ProxyWorker startup because the `osiris/components/` module is not uploaded to the E2B sandbox. The ProxyWorker attempts to import `ComponentRegistry` from `osiris.components.registry` (line 26 of proxy_worker.py), but this module does not exist in the sandbox environment.

## Timeline of Failure

1. **E2B Sandbox Creation**: Sandbox created successfully
2. **File Upload Phase**: `e2b_transparent_proxy.py` uploads:
   - ProxyWorker script to `/home/user/proxy_worker.py`
   - Core modules to `/home/user/osiris/core/`
   - Driver modules to `/home/user/osiris/drivers/`
   - Connector modules to `/home/user/osiris/connectors/`
   - **MISSING**: `osiris/components/` module
3. **Worker Startup**: ProxyWorker attempts to import ComponentRegistry
4. **Fatal Error**: `ModuleNotFoundError: No module named 'osiris.components'`

## Environment Facts

### File Upload Analysis (e2b_transparent_proxy.py)

The `_upload_worker()` method in `e2b_transparent_proxy.py` creates these directories:
```python
# Line 471-473
await self.sandbox.commands.run(
    "mkdir -p /home/user/osiris/core /home/user/osiris/remote /home/user/osiris/drivers"
)
```

But notably **does not** create `/home/user/osiris/components/`.

### Modules Uploaded

**Core modules** (lines 492-497):
- `core/driver.py`
- `core/execution_adapter.py`
- `core/session_logging.py`
- `core/redaction.py`

**Connector modules** (lines 500-507):
- `connectors/mysql/` (various files)
- `connectors/supabase/` (various files)

**Driver files** (lines 536-541):
- All `*.py` files from `osiris/drivers/`

**NOT uploaded**:
- `components/` directory (containing component specs)
- `osiris/components/` module (containing ComponentRegistry)

### Import Chain

1. **proxy_worker.py:26**: `from osiris.components.registry import ComponentRegistry`
2. **proxy_worker.py:150**: `self.component_registry = ComponentRegistry()`
3. **proxy_worker.py:151**: `self.component_specs = self.component_registry.load_specs()`

## Root Cause

**The single proximate cause**: The `osiris/components/` Python module is not uploaded to the E2B sandbox, but ProxyWorker unconditionally imports it.

### Why This Happened

The Codex AI agent made the ProxyWorker use ComponentRegistry for dynamic driver registration (eliminating hardcoded COMPONENT_MAP). This requires:
1. The ComponentRegistry class from `osiris/components/registry.py`
2. The actual component spec files from `components/` directory

Neither of these are uploaded to the E2B sandbox in the current implementation.

## Minimal Fix Options

### Option A: Upload Components Module and Specs
**Changes needed in `e2b_transparent_proxy.py`**:

```python
# In _upload_worker() method, after line 517:

# Upload components module
await self.sandbox.commands.run("mkdir -p /home/user/osiris/components")

# Upload ComponentRegistry and related modules
components_modules = [
    "components/registry.py",
    "components/error_mapper.py",
    "components/__init__.py"
]
for module_path in components_modules:
    full_path = osiris_root / module_path
    if full_path.exists():
        with open(full_path) as f:
            await self.sandbox.files.write(f"/home/user/osiris/{module_path}", f.read())

# Upload component spec files
components_dir = osiris_root.parent / "components"
if components_dir.exists():
    await self.sandbox.commands.run("mkdir -p /home/user/components")
    for spec_dir in components_dir.iterdir():
        if spec_dir.is_dir():
            spec_file = spec_dir / "spec.yaml"
            if spec_file.exists():
                await self.sandbox.commands.run(f"mkdir -p /home/user/components/{spec_dir.name}")
                with open(spec_file) as f:
                    await self.sandbox.files.write(
                        f"/home/user/components/{spec_dir.name}/spec.yaml",
                        f.read()
                    )
```

**Pros**:
- Maintains the new architecture with dynamic driver registration
- No changes needed to ProxyWorker

**Cons**:
- More files to upload (slower sandbox init)
- Need to handle spec.schema.json as well

### Option B: Fallback to Hardcoded Drivers in E2B
**Changes needed in `proxy_worker.py`**:

```python
# Replace line 26:
try:
    from osiris.components.registry import ComponentRegistry
    HAS_COMPONENT_REGISTRY = True
except ImportError:
    HAS_COMPONENT_REGISTRY = False

# In handle_prepare(), replace lines 150-152:
if HAS_COMPONENT_REGISTRY:
    self.component_registry = ComponentRegistry()
    self.component_specs = self.component_registry.load_specs()
else:
    # Fallback to hardcoded specs
    self.component_specs = self._get_hardcoded_specs()
```

**Pros**:
- Minimal upload changes
- Faster E2B startup

**Cons**:
- Loses dynamic driver capabilities in E2B
- Divergent behavior between local and E2B

### Option C: Bundle Components as Package Data
**Changes needed**:
1. Move component specs into `osiris/components/data/`
2. Use `importlib.resources` to load them
3. Include in package manifest

**Pros**:
- Clean Python package approach
- Works everywhere Python package is available

**Cons**:
- Requires restructuring component organization
- More complex change

## Recommended Fix

**Primary recommendation: Option A** - Upload the components module and spec files to E2B sandbox.

This maintains architectural consistency and the benefits of dynamic driver registration. The upload overhead is minimal (a few KB of YAML files).

**Implementation location**:
- File: `osiris/remote/e2b_transparent_proxy.py`
- Method: `_upload_worker()`
- Insert after line 523 (after connector modules upload)

## Validation Plan

After implementing the fix:

1. **Expected E2B events sequence**:
   - `e2b_diagnostic_info` with `import_tests.osiris.components.success: true`
   - `drivers_registered` with list of registered drivers
   - `dependency_check` showing required modules
   - `execution.start` and subsequent step events

2. **Test commands**:
   ```bash
   cd testing_env
   python ../osiris.py compile ../docs/examples/mysql_duckdb_supabase_demo.yaml
   python ../osiris.py run --last-compile --e2b --e2b-install-deps --dry-run
   ```

3. **Success criteria**:
   - No import errors
   - Driver registration completes
   - Steps begin execution (even if dry-run)

## Diagnostic Code Cleanup

The diagnostic code added to `proxy_worker.py` (lines 137-185) should be removed after fix validation. This was added in commit [current] for investigation only.

---
*Generated by Claude on September 29, 2025*
