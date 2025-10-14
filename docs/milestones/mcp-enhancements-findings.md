# MCP CLI-First Adapter Implementation Plan

**Generated**: 2025-10-14
**Author**: Tech Lead Analysis
**Objective**: Implement CLI-first adapter for Osiris MCP so that MCP tools delegate to existing Osiris CLI commands (JSON mode) instead of handling secrets or connection resolution directly.

---

## 1. Repository Scan & Current CLI Surface

### 1.1 Available CLI Commands with JSON Support

Based on repository scan, the following CLI commands exist with `--json` support:

| Command | JSON Support | Purpose |
|---------|-------------|---------|
| `osiris connections list` | ✅ Yes | List all configured connections |
| `osiris connections doctor` | ✅ Yes | Test connectivity for connections |
| `osiris connections doctor --family X --alias Y` | ✅ Yes | Test specific connection |
| `osiris components list` | ✅ Yes | List available components |
| `osiris components show <name>` | ❌ No | Show component details |
| `osiris components discover <name> --config FILE` | ⚠️ Partial | Run discovery (not fully implemented) |
| `osiris oml validate <file>` | ✅ Yes | Validate OML file |
| `osiris logs list` | ✅ Yes | List session logs |
| `osiris init` | ✅ Yes | Initialize project |

### 1.2 Missing CLI Commands Needed for MCP

The following MCP tools have NO direct CLI equivalent and need new commands or adaptations:

| MCP Tool | Current Implementation | Needed CLI Command |
|----------|----------------------|-------------------|
| `oml_schema_get` | Returns OML JSON schema | `osiris oml schema --json` (NEW) |
| `oml_save` | Saves OML draft | `osiris oml save --session <id> --file <path> --json` (NEW) |
| `guide_start` | Returns guidance | `osiris guide start --context <json> --json` (NEW) |
| `memory_capture` | Captures session memory | `osiris memory capture --session <id> --json` (NEW) |
| `usecases_list` | Lists use case templates | `osiris usecases list --json` (NEW) |
| `discovery_request` | Runs database discovery | Use `osiris components discover` with enhanced options |

### 1.3 Current MCP Tools Reading Environment Directly

Analysis of `osiris/mcp/tools/` shows these tools directly access environment/secrets:

1. **connections.py**:
   - Calls `load_connections_yaml()` which expects env vars to be resolved
   - Directly tests connections requiring secrets

2. **discovery.py**:
   - Uses connection configs to run discovery
   - Needs database passwords to connect

3. **memory.py**:
   - Writes directly to filesystem paths
   - Uses `OSIRIS_HOME` environment variable

4. **oml.py**:
   - Saves/loads files from filesystem
   - Validates OML in-process

---

## 2. CLI Bridge Design

### 2.1 Architecture

```python
# osiris/mcp/cli_bridge.py

import json
import subprocess
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from osiris.core.config import OsirisConfig
from osiris.mcp.errors import OsirisError, ErrorFamily

class CLIErrorCode(Enum):
    """Maps CLI exit codes to MCP error families."""
    SUCCESS = 0
    VALIDATION_ERROR = 1  # → SCHEMA
    CONNECTION_ERROR = 2  # → DISCOVERY
    NOT_FOUND = 3        # → SEMANTIC
    TIMEOUT = 4          # → RUNTIME
    INTERNAL_ERROR = 5   # → PLATFORM

@dataclass
class CLIResult:
    """Result from CLI invocation."""
    success: bool
    data: Optional[Dict[str, Any]]
    error: Optional[str]
    exit_code: int
    duration_ms: float
    correlation_id: str

class CLIBridge:
    """
    Bridge between MCP tools and Osiris CLI commands.

    Responsibilities:
    - Spawn CLI subprocesses with proper environment
    - Use filesystem.base_path from config as working directory
    - Parse JSON responses
    - Map CLI errors to MCP error taxonomy
    - Centralize logging
    """

    def __init__(self, debug: bool = False):
        self.debug = debug
        self.config = self._load_config()
        self.base_path = self._resolve_base_path()
        self.mcp_logs_dir = self._resolve_mcp_logs_dir()
        self._ensure_directories()

    def _load_config(self) -> OsirisConfig:
        """Load osiris.yaml configuration."""
        # Find osiris.yaml using standard search paths
        config_path = self._find_config_file()
        if not config_path:
            # Fall back to environment
            return self._config_from_env()
        return OsirisConfig.from_yaml(config_path)

    def _resolve_base_path(self) -> Path:
        """Resolve base_path from config or environment."""
        if self.config and self.config.filesystem.base_path:
            return Path(self.config.filesystem.base_path).resolve()

        # Fallback to OSIRIS_HOME or repo root
        import os
        if 'OSIRIS_HOME' in os.environ:
            self._log_warning("Using OSIRIS_HOME env var as fallback (config preferred)")
            return Path(os.environ['OSIRIS_HOME']).resolve()

        # Default to repo root
        return self._find_repo_root()

    def _resolve_mcp_logs_dir(self) -> Path:
        """Resolve MCP logs directory from config."""
        if self.config and hasattr(self.config.filesystem, 'mcp_logs_dir'):
            # Relative to base_path
            return self.base_path / self.config.filesystem.mcp_logs_dir

        # Default location
        return self.base_path / '.osiris' / 'mcp' / 'logs'

    async def run_cli_json(
        self,
        args: List[str],
        stdin: Optional[str] = None,
        timeout_s: float = 30.0,
        env_override: Optional[Dict[str, str]] = None
    ) -> CLIResult:
        """
        Run Osiris CLI command with JSON output.

        Args:
            args: CLI arguments (e.g., ['connections', 'list', '--json'])
            stdin: Optional stdin data
            timeout_s: Timeout in seconds
            env_override: Additional environment variables

        Returns:
            CLIResult with parsed JSON or error
        """
        import time
        import uuid

        correlation_id = f"mcp_{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        # Build command
        python_exe = sys.executable
        osiris_cli = self.base_path / 'osiris.py'
        cmd = [python_exe, str(osiris_cli)] + args

        # Ensure --json is included
        if '--json' not in args:
            cmd.append('--json')

        # Setup environment (inherit current + overrides)
        env = os.environ.copy()
        if env_override:
            env.update(env_override)

        # Log invocation
        self._log_audit({
            'event': 'cli_bridge_call',
            'correlation_id': correlation_id,
            'command': ' '.join(cmd),
            'cwd': str(self.base_path),
            'timeout_s': timeout_s
        })

        try:
            # Run subprocess
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE if stdin else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.base_path),
                env=env
            )

            # Communicate with timeout
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(stdin.encode() if stdin else None),
                timeout=timeout_s
            )

            duration_ms = (time.time() - start_time) * 1000

            # Parse result
            if proc.returncode == 0:
                try:
                    data = json.loads(stdout_bytes.decode())
                    return CLIResult(
                        success=True,
                        data=data,
                        error=None,
                        exit_code=0,
                        duration_ms=duration_ms,
                        correlation_id=correlation_id
                    )
                except json.JSONDecodeError as e:
                    return CLIResult(
                        success=False,
                        data=None,
                        error=f"Invalid JSON response: {e}",
                        exit_code=proc.returncode,
                        duration_ms=duration_ms,
                        correlation_id=correlation_id
                    )
            else:
                # CLI error
                error_msg = stderr_bytes.decode().strip() or stdout_bytes.decode().strip()
                return CLIResult(
                    success=False,
                    data=None,
                    error=error_msg,
                    exit_code=proc.returncode,
                    duration_ms=duration_ms,
                    correlation_id=correlation_id
                )

        except asyncio.TimeoutError:
            duration_ms = (time.time() - start_time) * 1000
            return CLIResult(
                success=False,
                data=None,
                error=f"Command timed out after {timeout_s}s",
                exit_code=CLIErrorCode.TIMEOUT.value,
                duration_ms=duration_ms,
                correlation_id=correlation_id
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return CLIResult(
                success=False,
                data=None,
                error=str(e),
                exit_code=CLIErrorCode.INTERNAL_ERROR.value,
                duration_ms=duration_ms,
                correlation_id=correlation_id
            )
        finally:
            # Log result
            self._log_audit({
                'event': 'cli_bridge_result',
                'correlation_id': correlation_id,
                'success': result.success if 'result' in locals() else False,
                'exit_code': result.exit_code if 'result' in locals() else -1,
                'duration_ms': duration_ms if 'duration_ms' in locals() else -1
            })

    def map_cli_error_to_mcp(self, result: CLIResult) -> OsirisError:
        """Map CLI error to MCP error taxonomy."""
        # Map exit codes to error families
        if result.exit_code == CLIErrorCode.VALIDATION_ERROR.value:
            family = ErrorFamily.SCHEMA
        elif result.exit_code == CLIErrorCode.CONNECTION_ERROR.value:
            family = ErrorFamily.DISCOVERY
        elif result.exit_code == CLIErrorCode.NOT_FOUND.value:
            family = ErrorFamily.SEMANTIC
        elif result.exit_code == CLIErrorCode.TIMEOUT.value:
            family = ErrorFamily.RUNTIME
        else:
            family = ErrorFamily.PLATFORM

        return OsirisError(
            family=family,
            message=result.error or "CLI command failed",
            correlation_id=result.correlation_id
        )
```

### 2.2 JSON Response Envelope

All CLI commands returning JSON should follow this structure:

```json
{
  "session_id": "string",        // Unique session identifier
  "success": true,               // Overall success status
  "data": {},                    // Command-specific payload
  "error": null,                 // Error message if failed
  "metadata": {                  // Optional metadata
    "duration_ms": 123.45,
    "timestamp": "2025-10-14T12:00:00Z"
  }
}
```

---

## 3. MCP to CLI Mapping Table

| MCP Tool Name | CLI Invocation | Args Mapping | Output Mapping | Error Mapping |
|---------------|----------------|--------------|----------------|---------------|
| `connections_list` | `osiris connections list --json` | None | `data.connections` → MCP result | Exit 2 → DISCOVERY error |
| `connections_doctor` | `osiris connections doctor [--family X] [--alias Y] --json` | `connection_id` → parse to `--family` and `--alias` | `data.results` → MCP result | Exit 2 → CONNECTION error |
| `components_list` | `osiris components list --json` | None | JSON array → MCP result | Exit 1 → SCHEMA error |
| `discovery_request` | `osiris components discover <component> --config <tmpfile> --json` | Write config to temp file with connection_id | Parse discovery results | Exit 2 → DISCOVERY error |
| `oml_schema_get` | `osiris oml schema --json` (NEW) | None | `data.schema` → MCP result | Exit 1 → SCHEMA error |
| `oml_validate` | `osiris oml validate <tmpfile> --json` | Write OML to temp file | `data.diagnostics` → MCP result | Exit 1 → VALIDATION error |
| `oml_save` | `osiris oml save --session <id> --file <path> --json` (NEW) | `session_id`, `oml`, `filename` → CLI args | `data.uri` → MCP result | Exit 1 → SCHEMA error |
| `guide_start` | `osiris guide start --context <tmpfile> --json` (NEW) | Write context to temp JSON file | `data.guidance` → MCP result | Exit 1 → SEMANTIC error |
| `memory_capture` | `osiris memory capture --session <id> --json` (NEW) | `session_id`, `consent` → CLI args | `data.memory_uri` → MCP result | Exit 3 → POLICY error |
| `usecases_list` | `osiris usecases list --json` (NEW) | `category` → `--category` flag | `data.usecases` → MCP result | Exit 1 → SCHEMA error |

---

## 4. File-Level Change Plan

### 4.1 New Files to Create

#### `osiris/mcp/cli_bridge.py`
```python
# Full implementation as shown in Section 2.1
```

#### `osiris/cli/oml_cmd.py` (Extend existing)
```python
def cmd_schema(args):
    """Return OML v0.1.0 JSON schema."""
    schema_path = Path(__file__).parent.parent / 'data' / 'schemas' / 'oml_v0.1.0.json'

    if args.json:
        with open(schema_path) as f:
            schema = json.load(f)
        print(json.dumps({
            'session_id': f'oml_schema_{int(time.time())}',
            'success': True,
            'data': {
                'schema': schema,
                'version': 'v0.1.0',
                'uri': 'osiris://schemas/oml/v0.1.0.json'
            }
        }))
    else:
        # Human-readable output
        console.print("[green]OML Schema v0.1.0[/green]")
        console.print(f"Location: {schema_path}")

def cmd_save(args):
    """Save OML pipeline draft."""
    import uuid

    session_id = args.session or str(uuid.uuid4())
    file_path = args.file

    # Read OML content from stdin or file
    if args.stdin:
        content = sys.stdin.read()
    else:
        with open(file_path) as f:
            content = f.read()

    # Save to drafts directory
    base_path = get_base_path_from_config()
    drafts_dir = base_path / '.osiris' / 'drafts' / 'oml'
    drafts_dir.mkdir(parents=True, exist_ok=True)

    draft_file = drafts_dir / f"{session_id}.yaml"
    draft_file.write_text(content)

    if args.json:
        print(json.dumps({
            'session_id': f'oml_save_{int(time.time())}',
            'success': True,
            'data': {
                'uri': f'osiris://drafts/oml/{session_id}.yaml',
                'session_id': session_id,
                'path': str(draft_file)
            }
        }))
```

#### `osiris/cli/guide_cmd.py` (NEW)
```python
"""Guidance CLI commands for OML authoring."""

def main(args):
    """Guide command main entry point."""
    if args.subcommand == 'start':
        return cmd_start(args)

def cmd_start(args):
    """Provide guided next steps."""
    # Read context from file or stdin
    if args.context == '-':
        context = json.loads(sys.stdin.read())
    else:
        with open(args.context) as f:
            context = json.load(f)

    # Generate guidance (simplified)
    guidance = generate_guidance(context)

    if args.json:
        print(json.dumps({
            'session_id': f'guide_{int(time.time())}',
            'success': True,
            'data': {
                'guidance': guidance,
                'examples': get_examples_for_context(context)
            }
        }))
```

### 4.2 Files to Modify

#### `osiris/mcp/tools/connections.py`
```python
# Replace direct implementation with CLI delegation

from osiris.mcp.cli_bridge import CLIBridge

class ConnectionsTools:
    def __init__(self):
        self.bridge = CLIBridge()

    async def list_connections(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """List connections via CLI."""
        result = await self.bridge.run_cli_json(['connections', 'list'])

        if result.success:
            return result.data['connections']
        else:
            raise self.bridge.map_cli_error_to_mcp(result)

    async def doctor_connection(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Test connection via CLI."""
        connection_id = args.get('connection_id', '')

        # Parse connection_id format: @family.alias
        cli_args = ['connections', 'doctor']
        if connection_id:
            parts = connection_id.strip('@').split('.')
            if len(parts) == 2:
                cli_args.extend(['--family', parts[0], '--alias', parts[1]])

        result = await self.bridge.run_cli_json(cli_args)

        if result.success:
            return result.data
        else:
            raise self.bridge.map_cli_error_to_mcp(result)
```

#### `osiris/mcp/tools/discovery.py`
```python
# Replace with CLI delegation

import tempfile

class DiscoveryTools:
    def __init__(self):
        self.bridge = CLIBridge()

    async def request_discovery(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Run discovery via CLI."""
        connection_id = args['connection_id']
        component_id = args.get('component_id', 'mysql.extractor')
        samples = args.get('samples', 0)

        # Create temp config file
        config = {
            'connection_id': connection_id,
            'samples': samples
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            config_file = f.name

        try:
            cli_args = ['components', 'discover', component_id, '--config', config_file]
            result = await self.bridge.run_cli_json(cli_args, timeout_s=60.0)

            if result.success:
                return result.data
            else:
                raise self.bridge.map_cli_error_to_mcp(result)
        finally:
            Path(config_file).unlink(missing_ok=True)
```

#### `osiris/cli/main.py`
```python
# Add new subcommands to CLI router

def main():
    # ... existing code ...

    # Add new commands
    subparsers.add_parser('guide', help='Guided OML authoring assistance')
    subparsers.add_parser('memory', help='Session memory management')
    subparsers.add_parser('usecases', help='OML use case templates')

    # ... in command routing ...

    elif args.command == 'guide':
        from .guide_cmd import main as guide_main
        guide_main(command_args)
    elif args.command == 'memory':
        from .memory_cmd import main as memory_main
        memory_main(command_args)
    elif args.command == 'usecases':
        from .usecases_cmd import main as usecases_main
        usecases_main(command_args)
```

#### `osiris/core/config.py`
```python
# Add MCP-specific config loading

@dataclass
class FilesystemConfig:
    base_path: str = ""
    mcp_logs_dir: str = ".osiris/mcp/logs"  # NEW
    # ... existing fields ...

def get_mcp_logs_dir() -> Path:
    """Get MCP logs directory from config."""
    config = load_config()
    base_path = Path(config.filesystem.base_path or find_repo_root())
    mcp_logs_dir = config.filesystem.get('mcp_logs_dir', '.osiris/mcp/logs')
    return base_path / mcp_logs_dir
```

### 4.3 Update `osiris init` to Write MCP Config

#### `osiris/cli/init.py`
```python
def create_osiris_yaml(project_dir: Path, **kwargs) -> None:
    """Create osiris.yaml with filesystem contract."""

    config = {
        'version': '2.0',
        'filesystem': {
            'base_path': str(project_dir.resolve()),  # Absolute path
            'mcp_logs_dir': '.osiris/mcp/logs',       # NEW
            # ... rest of filesystem config ...
        }
    }

    # Write config
    config_path = project_dir / 'osiris.yaml'
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    # Create MCP logs directory
    mcp_logs_dir = project_dir / '.osiris' / 'mcp' / 'logs'
    mcp_logs_dir.mkdir(parents=True, exist_ok=True)
```

---

## 5. Implementation Plan (Phased)

### Phase A: CLI Bridge Foundation (Day 1, Morning)
**Duration**: 4 hours

1. Create `osiris/mcp/cli_bridge.py` with core functionality
2. Add config loading for `filesystem.base_path` and `mcp_logs_dir`
3. Implement `run_cli_json()` with timeout and error handling
4. Add audit logging to centralized MCP logs directory
5. Write unit tests for bridge

**Files**:
- NEW: `osiris/mcp/cli_bridge.py`
- NEW: `tests/mcp/test_cli_bridge.py`

### Phase B: Wire Existing CLI Commands (Day 1, Afternoon)
**Duration**: 3 hours

1. Update `connections.py` to use CLI bridge
2. Update `components.py` to use CLI bridge
3. Update `discovery.py` to use enhanced components discover
4. Test with existing CLI commands

**Files**:
- MODIFY: `osiris/mcp/tools/connections.py`
- MODIFY: `osiris/mcp/tools/components.py`
- MODIFY: `osiris/mcp/tools/discovery.py`
- NEW: `tests/mcp/test_cli_bridge_connections.py`

### Phase C: Add Missing CLI Commands (Day 2, Morning)
**Duration**: 4 hours

1. Add `osiris oml schema --json`
2. Add `osiris oml save --session <id> --file <path> --json`
3. Add `osiris guide start --context <file> --json`
4. Add `osiris memory capture --session <id> --json`
5. Add `osiris usecases list --json`

**Files**:
- MODIFY: `osiris/cli/oml_cmd.py`
- NEW: `osiris/cli/guide_cmd.py`
- NEW: `osiris/cli/memory_cmd.py`
- NEW: `osiris/cli/usecases_cmd.py`
- MODIFY: `osiris/cli/main.py`

### Phase D: Logging Unification (Day 2, Afternoon)
**Duration**: 2 hours

1. Update `osiris init` to write `mcp_logs_dir` config
2. Centralize all MCP logging to use config paths
3. Remove ad-hoc session directories from tools
4. Add log rotation/cleanup

**Files**:
- MODIFY: `osiris/cli/init.py`
- MODIFY: `osiris/mcp/server.py`
- MODIFY: `osiris/core/config.py`

### Phase E: Testing & Documentation (Day 2, Late Afternoon)
**Duration**: 2 hours

1. End-to-end MCP tests with CLI delegation
2. Test with no environment variables
3. Update ADR-0036 with addendum
4. Update milestone docs

**Files**:
- NEW: `tests/mcp/test_cli_delegation_e2e.py`
- MODIFY: `docs/adr/0036-mcp-interface.md`
- MODIFY: `docs/milestones/mcp-final.md`

---

## 6. Test Plan

### 6.1 New Test Files

1. **`tests/mcp/test_cli_bridge.py`**
   - Test `run_cli_json()` with mock subprocess
   - Test timeout handling
   - Test error mapping
   - Test config path resolution

2. **`tests/mcp/test_cli_bridge_connections.py`**
   - Mock `subprocess.run` to return golden JSON
   - Test connections list mapping
   - Test connections doctor with various args
   - Test error scenarios

3. **`tests/mcp/test_cli_bridge_discovery.py`**
   - Test discovery delegation
   - Test temp file creation/cleanup
   - Test timeout handling for long discovery

4. **`tests/mcp/test_filesystem_contract_mcp.py`**
   - Assert logs written to correct directories
   - Test with/without config file
   - Test environment variable fallback warnings

5. **`tests/mcp/test_cli_delegation_e2e.py`**
   - Full end-to-end test with real CLI
   - Test with no env variables set
   - Verify secrets resolved by CLI layer

### 6.2 Modified Test Files

- `tests/mcp/test_server_boot.py` - Update to use CLI bridge
- `tests/mcp/test_tools_connections.py` - Update expectations for delegation
- `tests/mcp/test_tools_discovery.py` - Update for CLI delegation

---

## 7. Documentation Updates

### 7.1 ADR-0036 Addendum

Add to end of ADR-0036:

```markdown
## Addendum: CLI-First Adapter Pattern (October 2025)

After initial implementation, we refined the MCP architecture to maintain Osiris's CLI-first design:

### Key Decision: No Secrets in MCP

The MCP server operates as a **thin adapter** that delegates all connection-dependent operations to the Osiris CLI. This ensures:

1. **Security**: Secrets never flow through MCP or client configurations
2. **Consistency**: Single source of truth for connection resolution
3. **Simplicity**: MCP tools don't duplicate CLI logic

### Implementation Pattern

All MCP tools that require database connections or secrets delegate to CLI commands:
- `connections_list` → `osiris connections list --json`
- `connections_doctor` → `osiris connections doctor --json`
- `discovery_request` → `osiris components discover --json`

The CLI bridge (`osiris/mcp/cli_bridge.py`) handles:
- Subprocess spawning with proper environment
- JSON parsing and error mapping
- Centralized logging to filesystem contract paths
```

### 7.2 Milestone Update

Add to mcp-final.md:

```markdown
## CLI-First Adapter Implementation

The MCP server delegates to CLI commands for all operations requiring secrets:

- **Bridge Module**: `osiris/mcp/cli_bridge.py` spawns CLI subprocesses
- **No Secrets in MCP**: All secret resolution happens in CLI process
- **Filesystem Contract**: Logs centralized to `<base_path>/<mcp_logs_dir>/`
- **New CLI Commands**: Added minimal commands for MCP delegation
  - `osiris oml schema --json`
  - `osiris guide start --json`
  - `osiris memory capture --json`
  - `osiris usecases list --json`
```

---

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| CLI subprocess overhead | Performance degradation | Cache frequently-used results; use connection pooling |
| Temp file cleanup failures | Disk space issues | Use context managers; cleanup in finally blocks |
| JSON parsing errors | Tool failures | Validate JSON schema; add retry logic |
| CLI API changes | Breaking changes | Version CLI outputs; add compatibility layer |
| Windows path issues | Cross-platform failures | Use pathlib everywhere; test on Windows |

---

## 9. Ready-to-Run Command Checklist

After implementation, verify with these commands:

```bash
# 1. Initialize project with MCP config
cd testing_env
python ../osiris.py init --force

# 2. Verify config has filesystem.mcp_logs_dir
grep mcp_logs_dir osiris.yaml

# 3. Test CLI commands with JSON
python ../osiris.py connections list --json
python ../osiris.py connections doctor --json
python ../osiris.py components list --json

# 4. Test new CLI commands
python ../osiris.py oml schema --json
echo "test" | python ../osiris.py oml save --session test123 --stdin --json
python ../osiris.py guide start --context guide_context.json --json
python ../osiris.py usecases list --json

# 5. Run MCP server with no env variables
unset MYSQL_PASSWORD SUPABASE_SERVICE_ROLE_KEY SUPABASE_PASSWORD
python ../osiris.py mcp run --selftest

# 6. Check logs in correct location
ls -la .osiris/mcp/logs/

# 7. Test from different directory
cd /tmp
python /path/to/osiris.py mcp run --selftest

# 8. Run test suite
cd /path/to/osiris
pytest tests/mcp/test_cli_bridge*.py -v
```

---

## 10. Success Criteria

✅ Implementation is complete when:

1. **No secrets in MCP**: All connection-dependent tools work via CLI delegation
2. **Runs from any CWD**: Paths resolved via osiris.yaml, not process CWD
3. **Centralized logging**: All logs under `<base_path>/.osiris/mcp/logs/`
4. **Claude Desktop works**: Config from `osiris mcp clients` works without env vars
5. **Tests pass**: All new and existing MCP tests green
6. **Selftest < 2s**: Including at least one delegated tool call
7. **No regressions**: Existing osiris commands unchanged

---

## Summary

This plan implements a **CLI-first adapter pattern** for Osiris MCP, ensuring:
- MCP remains a thin layer over existing CLI
- Secrets stay in the CLI process
- Filesystem paths follow the contract
- Implementation can be done in ~15 hours (2 days)

The key insight is that MCP tools should **delegate, not duplicate** existing Osiris functionality. This maintains architectural consistency while enabling AI integration through the Model Context Protocol.