# Parameter Propagation Issues Analysis: MCP → CLI → Core

## Executive Summary

This analysis traces parameter flow through three architectural layers: MCP tools → CLI commands → Core functions. Multiple parameter propagation issues were identified where parameters are accepted in some layers but not properly passed or handled in others.

---

## Issue 1: Discovery - component_id Parameter Lost

**Severity:** HIGH  
**Type:** Parameter Transformation Issue

### Problem Statement
The MCP `discovery_request()` tool accepts a `component_id` parameter, but this parameter is **never passed to the CLI command** and instead is **derived from the connection family** in the CLI layer.

### Parameter Flow

```
MCP Tool (discovery.py)
├─ Accepts: connection_id, component_id, samples, idempotency_key
│
├─ CLI Bridge: run_cli_json()
│  ├─ Command: ["mcp", "discovery", "run", "--connection-id", "@family.alias", "--samples", "10"]
│  └─ NOTE: component_id is NOT passed to CLI
│
└─ CLI Command (discovery_cmd.py)
   └─ discovery_run(connection_id, samples, json_output, session_id, logs_dir)
      ├─ component_name = f"{family}.extractor"  # Derived from connection_id, ignoring MCP parameter
      └─ Passed to Core: ProgressiveDiscovery(component_type=component_name, ...)
```

### Code Evidence

**MCP Tool (osiris/mcp/tools/discovery.py, lines 25-82):**
```python
async def request(self, args: dict[str, Any]) -> dict[str, Any]:
    connection_id = args.get("connection_id")
    component_id = args.get("component_id")  # Accepted from MCP
    samples = args.get("samples", 0)
    idempotency_key = args.get("idempotency_key")
    
    # ... validation ...
    
    cli_args = [
        "mcp", "discovery", "run",
        "--connection-id", connection_id,
        "--samples", str(samples),
    ]
    # component_id is NOT included in cli_args!
    result = await run_cli_json(cli_args)
```

**CLI Command (osiris/cli/discovery_cmd.py, lines 60-66, 124-125, 134):**
```python
def discovery_run(
    connection_id: str,
    samples: int = 10,
    json_output: bool = False,
    session_id: str | None = None,
    logs_dir: str | None = None,
):  # No component_id parameter
    # ...
    family, alias = parts  # Extracted from connection_id
    component_name = f"{family}.extractor"  # DERIVED, ignoring MCP value
```

**MCP Server Registration (osiris/mcp/server.py, lines 87-104):**
```python
types.Tool(
    name="discovery_request",
    description="Discover database schema and optionally sample data",
    inputSchema={
        "type": "object",
        "properties": {
            "connection_id": {"type": "string", "description": "Database connection ID"},
            "component_id": {"type": "string", "description": "Component ID for discovery"},
            "samples": {"type": "integer", ...},
            "idempotency_key": {"type": "string", ...},
        },
        "required": ["connection_id", "component_id"],
    },
),
```

### Impact Assessment

- **Functional Impact:** MCP clients cannot override the component type for discovery. For non-standard extractors (e.g., "mysql.extractor_v2", "postgresql.extractor"), the hard-coded derivation fails.
- **API Contract Violation:** MCP schema declares `component_id` as required, but it's not actually used.
- **Future Extensibility:** Adding support for alternative component types is blocked.
- **Testing:** Can't test discovery with different component implementations.

### Suggested Fix

**Option A: Pass component_id through CLI chain**

```bash
# CLI command line
["mcp", "discovery", "run", "--connection-id", "@mysql.main", "--component-id", "mysql.extractor_v2", "--samples", "10"]

# CLI function signature
def discovery_run(
    connection_id: str,
    samples: int = 10,
    json_output: bool = False,
    session_id: str | None = None,
    logs_dir: str | None = None,
    component_id: str | None = None,  # NEW
):
    # ...
    if component_id is None:
        component_name = f"{family}.extractor"  # Default behavior
    else:
        component_name = component_id  # Use provided value
```

**Option B: Remove component_id from MCP schema** (if it's genuinely unused)

```python
# Update MCP server tool schema
types.Tool(
    name="discovery_request",
    inputSchema={
        "properties": {
            "connection_id": {"type": "string"},
            "samples": {"type": "integer"},
            "idempotency_key": {"type": "string"},
        },
        "required": ["connection_id"],  # Remove component_id
    },
),
```

---

## Issue 2: Memory Capture - Content Parameters Not Passed

**Severity:** MEDIUM  
**Type:** Missing Parameter Propagation

### Problem Statement
The MCP `memory_capture()` tool accepts 11 parameters including `intent`, `actor_trace`, `decisions`, `artifacts`, `oml_uri`, `error_report`, and `notes`, but the CLI delegation **does not pass any of these parameters** to the CLI command.

### Parameter Flow

```
MCP Tool (memory.py)
├─ Accepts: consent, session_id, retention_days, intent, actor_trace, 
│           decisions, artifacts, oml_uri, error_report, notes
│
├─ Processing in MCP tool directly
│  ├─ Creates memory_entry with all 10 parameters
│  ├─ Applies PII redaction
│  └─ Saves to disk (no CLI delegation!)
│
└─ Result: CLI command never invoked for memory capture
```

### Code Evidence

**MCP Tool (osiris/mcp/tools/memory.py, lines 25-98):**
```python
async def capture(self, args: dict[str, Any]) -> dict[str, Any]:
    consent = args.get("consent", False)
    session_id = args.get("session_id")
    retention_days = args.get("retention_days", 365)
    intent = args.get("intent", "")
    actor_trace = args.get("actor_trace", [])
    decisions = args.get("decisions", [])
    artifacts = args.get("artifacts", [])
    oml_uri = args.get("oml_uri")
    error_report = args.get("error_report")
    notes = args.get("notes", "")
    
    memory_entry = {
        "timestamp": ...,
        "session_id": session_id,
        "retention_days": retention_days,
        "intent": intent,              # Used in MCP
        "actor_trace": actor_trace,    # Used in MCP
        "decisions": decisions,        # Used in MCP
        "artifacts": artifacts,        # Used in MCP
        "oml_uri": oml_uri,           # Used in MCP
        "error_report": error_report,  # Used in MCP
        "notes": notes,                # Used in MCP
    }
    
    redacted_entry = self._redact_pii(memory_entry)
    memory_id = self._save_memory(redacted_entry)  # Saved in MCP, not CLI
```

**CLI Stub (osiris/cli/memory_cmd.py, lines 14-60):**
```python
def memory_capture(session_id: str | None = None, consent: bool = False, json_output: bool = False):
    # Only accepts 3 parameters!
    # No intent, actor_trace, decisions, artifacts, oml_uri, error_report, notes
    if not consent:
        # ... error handling ...
    if not session_id:
        # ... error handling ...
    # Stub implementation - would implement PII redaction and storage
```

**MCP CLI Command (osiris/cli/mcp_cmd.py, lines 558-566):**
```python
def cmd_memory(args):
    parser.add_argument("--session-id", required=False, help="Session ID")
    parser.add_argument("--consent", action="store_true", help="User consent flag")
    # NO OTHER ARGUMENTS!
    
    from osiris.cli.memory_cmd import memory_capture
    exit_code = memory_capture(
        session_id=parsed_args.session_id,
        consent=parsed_args.consent,
        json_output=parsed_args.json,
    )
```

**MCP Server Registration (osiris/mcp/server.py, lines 169-192):**
```python
types.Tool(
    name="memory_capture",
    description="Capture session memory with consent",
    inputSchema={
        "type": "object",
        "properties": {
            "consent": {"type": "boolean"},
            "retention_days": {"type": "integer", "default": 365},
            "session_id": {"type": "string"},
            "actor_trace": {"type": "array", "items": {"type": "object"}},
            "intent": {"type": "string"},
            "decisions": {"type": "array", "items": {"type": "object"}},
            "artifacts": {"type": "array", "items": {"type": "string"}},
            "oml_uri": {"type": ["string", "null"]},
            "error_report": {"type": ["object", "null"]},
            "notes": {"type": "string"},
        },
        "required": ["consent", "session_id", "intent"],
    },
),
```

### Impact Assessment

- **Functional Gap:** Only `consent` and `session_id` are usable; all contextual parameters (intent, decisions, artifacts, error report) are ignored.
- **Data Loss:** Valuable debugging information (actor_trace, error_report) is discarded.
- **Incomplete Implementation:** Memory capture exists in MCP tool but not in CLI, violating the "CLI-first" architecture principle.
- **No CLI Reusability:** CLI command is a stub and can't be used standalone.

### Suggested Fix

**Implement full memory capture in CLI:**

```python
# osiris/cli/memory_cmd.py
def memory_capture(
    session_id: str | None = None,
    consent: bool = False,
    json_output: bool = False,
    retention_days: int = 365,
    intent: str = "",
    actor_trace: list[dict] | None = None,
    decisions: list[dict] | None = None,
    artifacts: list[str] | None = None,
    oml_uri: str | None = None,
    error_report: dict | None = None,
    notes: str = "",
):
    """Capture session memory with all context."""
    if not consent:
        return 1
    if not session_id:
        return 2
    
    memory_entry = {
        "timestamp": ...,
        "session_id": session_id,
        "retention_days": retention_days,
        "intent": intent,
        "actor_trace": actor_trace or [],
        "decisions": decisions or [],
        "artifacts": artifacts or [],
        "oml_uri": oml_uri,
        "error_report": error_report,
        "notes": notes,
    }
    
    # Save to disk...
```

**Update MCP → CLI bridge:**

```python
# osiris/mcp/tools/memory.py
async def capture(self, args: dict[str, Any]) -> dict[str, Any]:
    # Delegate to CLI with ALL parameters
    import json
    cli_args = [
        "mcp", "memory", "capture",
        "--session-id", args.get("session_id"),
        "--consent" if args.get("consent") else "--no-consent",
        "--retention-days", str(args.get("retention_days", 365)),
        "--intent", args.get("intent", ""),
        # ... other args ...
    ]
    result = await run_cli_json(cli_args)
```

---

## Issue 3: OML Validate - strict Parameter Accepted but Validation Mode Not Used

**Severity:** LOW  
**Type:** Unused Parameter

### Problem Statement
The MCP tool schema includes a `strict` parameter for OML validation, but the CLI delegation chain may not properly propagate this to control validation behavior.

### Parameter Flow

```
MCP Tool (oml.py)
├─ Accepts: oml_content, strict (default: true)
│
├─ CLI Bridge: run_cli_json()
│  ├─ Command: ["mcp", "oml", "validate", "--pipeline", "..."]
│  └─ NOTE: --strict flag may not be passed
│
└─ CLI Command (oml_validate.py)
   └─ validate_oml_command(pipeline_path, json_output, verbose)
      ├─ No strict parameter handling
      └─ Passed to Core: OMLValidator.validate()
```

### Code Evidence

**MCP Tool (osiris/mcp/tools/oml.py, lines 95-107):**
```python
async def validate(self, args: dict[str, Any]) -> dict[str, Any]:
    oml_content = args.get("oml_content")
    strict = args.get("strict", True)  # Accepted
    
    if not oml_content:
        raise OsirisError(...)
    
    try:
        # Check for known bad indentation pattern
        if "name: test\n  bad_indent" in oml_content:
            # ...
        
        # Pre-process YAML
        import re
        preprocessed = re.sub(r"(@[\w\.]+)(?=\s|$)", r'"\1"', oml_content)
        
        # Parse YAML
        try:
            oml_data = yaml.safe_load(preprocessed)
        except yaml.YAMLError as e:
            # ...
        
        # Validate using the actual OML validator if available
        diagnostics = await self._validate_oml(oml_data, strict)  # strict is used here
```

**MCP Server → CLI Command (osiris/cli/mcp_cmd.py, lines 449-457):**
```python
elif parsed_args.action == "validate":
    if not parsed_args.pipeline:
        console.print("[red]Error: --pipeline required for validate[/red]")
        sys.exit(2)
    from osiris.cli.oml_validate import validate_oml_command
    
    # strict parameter NOT passed!
    validate_oml_command(parsed_args.pipeline, json_output=True, verbose=False)
```

**CLI Command (assuming osiris/cli/oml_validate.py):**
```python
def validate_oml_command(pipeline_path: str, json_output: bool = False, verbose: bool = False):
    # No strict parameter
    # ...
```

### Impact Assessment

- **Functional Impact:** When using MCP, the `strict` parameter is ignored if OML validation delegates through CLI.
- **Testing Issues:** Lenient validation (`strict=False`) for development can't be used via MCP.
- **API Inconsistency:** MCP schema declares the parameter but it's not functional for all code paths.

### Suggested Fix

**Add strict parameter to CLI command chain:**

```bash
# CLI mcp_cmd.py
parser.add_argument("--strict", action="store_true", default=True, help="Enable strict validation")

# Pass to CLI command
validate_oml_command(
    parsed_args.pipeline,
    json_output=True,
    verbose=False,
    strict=not parsed_args.no_strict,  # if --no-strict is provided
)
```

---

## Issue 4: Connections Doctor - connection_id Parameter Transformation

**Severity:** MEDIUM  
**Type:** Parameter Format Transformation

### Problem Statement
The CLI `doctor_connections()` function accepts `--connection-id` but internally converts it to `--family` and `--alias` parameters. This transformation is implicit and could cause issues if the format changes.

### Parameter Flow

```
MCP Tool (connections.py)
├─ Accepts: connection_id (e.g., "@mysql.default")
│
├─ CLI Bridge: run_cli_json()
│  ├─ Command: ["mcp", "connections", "doctor", "--connection-id", "@mysql.default"]
│  └─ Passes through as-is
│
└─ CLI Command (connections_cmd.py)
   ├─ doctor_connections(args)
   ├─ Parses args with argparse for --connection-id
   ├─ Lines 499-508: Transforms "@mysql.default" → family="mysql", alias="default"
   └─ Uses parsed family/alias for tests
```

### Code Evidence

**CLI Command (osiris/cli/connections_cmd.py, lines 430-515):**
```python
def doctor_connections(args: list) -> None:
    parser = argparse.ArgumentParser(description="Test connections", add_help=False)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--family", help="Test only connections for this family")
    parser.add_argument("--alias", help="Test only this specific connection")
    parser.add_argument("--connection-id", help="Test specific connection by reference (e.g., @mysql.test)")
    
    parsed_args, _ = parser.parse_known_args(args)
    
    # Handle --connection-id by parsing it into --family and --alias
    if parsed_args.connection_id:
        from osiris.core.config import parse_connection_ref  # noqa: PLC0415
        
        try:
            connection_ref = parsed_args.connection_id
            if not connection_ref.startswith("@"):
                connection_ref = f"@{connection_ref}"
            family, alias = parse_connection_ref(connection_ref)  # Transformation happens here
            parsed_args.family = family
            parsed_args.alias = alias
        except Exception as e:
            # Error handling...
```

### Impact Assessment

- **Low Risk:** Transformation is explicit and contained within one function.
- **Potential Issue:** If `parse_connection_ref()` is removed or changes, the implicit dependency breaks.
- **No Parameter Loss:** All information is preserved through transformation.

### Note
This is not a critical issue but follows a pattern that could cause brittleness if the parsing logic changes.

---

## Issue 5: Discovery Cache - idempotency_key Parameter Not Used in CLI

**Severity:** MEDIUM  
**Type:** Partial Implementation

### Problem Statement
The MCP `discovery_request()` tool accepts `idempotency_key` for caching, but this parameter is **handled only in the MCP layer** and never reaches the CLI command.

### Parameter Flow

```
MCP Tool (discovery.py)
├─ Accepts: connection_id, component_id, samples, idempotency_key
│
├─ Cache Check (in MCP):
│  ├─ IF idempotency_key provided AND cached result exists:
│  │  └─ Return cached result directly
│  └─ ELSE:
│     └─ Invoke CLI discovery_run()
│
├─ CLI Bridge: run_cli_json()
│  └─ Command: ["mcp", "discovery", "run", ...]
│     (idempotency_key NOT passed to CLI)
│
└─ CLI Command (discovery_cmd.py)
   ├─ Performs fresh discovery
   └─ Does not implement idempotency check
```

### Code Evidence

**MCP Tool (osiris/mcp/tools/discovery.py, lines 58-87):**
```python
async def request(self, args: dict[str, Any]) -> dict[str, Any]:
    connection_id = args.get("connection_id")
    component_id = args.get("component_id")
    samples = args.get("samples", 0)
    idempotency_key = args.get("idempotency_key")
    
    # Check cache first (optional optimization)
    if idempotency_key:
        cached_result = await self.cache.get(connection_id, component_id, samples, idempotency_key)
        
        if cached_result:
            logger.info(f"Discovery cache hit for {connection_id}/{component_id}")
            return {
                "discovery_id": cached_result.get("discovery_id"),
                "cached": True,
                "status": "success",
                "artifacts": self._get_artifact_uris(cached_result.get("discovery_id")),
            }
    
    # Delegate to CLI: osiris mcp discovery run
    cli_args = [
        "mcp", "discovery", "run",
        "--connection-id", connection_id,
        "--samples", str(samples),
    ]
    # NOTE: idempotency_key is NOT included in CLI args
    
    result = await run_cli_json(cli_args)
    
    # Cache the result if idempotency_key provided
    if idempotency_key and result.get("discovery_id"):
        await self.cache.set(connection_id, component_id, samples, result, idempotency_key)
```

**MCP Server Registration (osiris/mcp/server.py, lines 100-101):**
```python
"idempotency_key": {"type": "string", "description": "Key for deterministic caching"},
# ... required fields do NOT include idempotency_key
```

**CLI Command (osiris/cli/discovery_cmd.py, lines 60-66):**
```python
def discovery_run(
    connection_id: str,
    samples: int = 10,
    json_output: bool = False,
    session_id: str | None = None,
    logs_dir: str | None = None,
):
    # No idempotency_key parameter
```

### Impact Assessment

- **Functional Gap:** CLI cannot implement caching independently.
- **Two-Tier Caching:** Cache checking only works when called through MCP, not from CLI.
- **Testing Limitation:** Can't verify idempotency without going through MCP layer.
- **Architectural Inconsistency:** Breaks "CLI-first" principle - CLI should be self-contained.

### Suggested Fix

**Propagate idempotency_key through CLI chain:**

```python
# MCP tool
cli_args = [
    "mcp", "discovery", "run",
    "--connection-id", connection_id,
    "--samples", str(samples),
    "--idempotency-key", idempotency_key,  # NEW
]

# CLI command
def discovery_run(
    connection_id: str,
    samples: int = 10,
    json_output: bool = False,
    session_id: str | None = None,
    logs_dir: str | None = None,
    idempotency_key: str | None = None,  # NEW
):
    # Implement cache check here, not just in MCP
    if idempotency_key:
        cached = check_discovery_cache(connection_id, samples, idempotency_key)
        if cached:
            return cached
```

---

## Issue 6: Guide Start - Context Parameters Accepted but Not Used

**Severity:** LOW  
**Type:** Partial Implementation

### Problem Statement
The MCP `guide_start()` tool accepts 5 context parameters for guidance determination, but these are **processed only in MCP** and not persisted or available to CLI.

### Parameter Flow

```
MCP Tool (guide.py)
├─ Accepts: intent, known_connections, has_discovery, has_previous_oml, has_error_report
│
├─ Processing in MCP:
│  ├─ Uses intent to determine next_step
│  ├─ Uses context flags to tailor recommendations
│  └─ Returns guidance
│
└─ No CLI delegation (tool is self-contained)
   └─ NOTE: No option to call guide from CLI standalone
```

### Code Evidence

**MCP Server Registration (osiris/mcp/server.py, lines 150-167):**
```python
types.Tool(
    name="guide_start",
    description="Get guided next steps for OML authoring",
    inputSchema={
        "type": "object",
        "properties": {
            "intent": {"type": "string"},
            "known_connections": {"type": "array", "items": {"type": "string"}},
            "has_discovery": {"type": "boolean"},
            "has_previous_oml": {"type": "boolean"},
            "has_error_report": {"type": "boolean"},
        },
        "required": ["intent"],
    },
),
```

**MCP Tool (osiris/mcp/tools/guide.py, lines 20-83):**
```python
async def start(self, args: dict[str, Any]) -> dict[str, Any]:
    intent = args.get("intent", "")
    known_connections = args.get("known_connections", [])
    has_discovery = args.get("has_discovery", False)
    has_previous_oml = args.get("has_previous_oml", False)
    has_error_report = args.get("has_error_report", False)
    
    # All parameters used in logic
    next_step, objective, example = self._determine_next_step(
        intent, known_connections, has_discovery, has_previous_oml, has_error_report
    )
```

**CLI Implementation (osiris/cli/mcp_cmd.py, lines 502-515):**
```python
if parsed_args.action == "start":
    from osiris.cli.guide_cmd import guide_start
    
    exit_code = guide_start(
        context_file=parsed_args.context_file,
        json_output=parsed_args.json,
    )
    # guide_cmd.py not found - guide_start doesn't exist in CLI
```

### Impact Assessment

- **Functional Gap:** Guide can only be used through MCP, not via CLI.
- **No CLI Reusability:** Users cannot run guidance from command line.
- **Inconsistent Architecture:** Violates "CLI-first" principle where all functionality should be accessible from CLI.

### Suggested Fix

**Create CLI guide command that duplicates MCP logic:**

```python
# osiris/cli/guide_cmd.py
def guide_start(
    context_file: str | None = None,
    intent: str | None = None,
    json_output: bool = False,
):
    """Get guidance for OML authoring from CLI."""
    
    # Load context from file if provided
    known_connections = []
    has_discovery = False
    has_previous_oml = False
    has_error_report = False
    
    if context_file:
        import json
        with open(context_file) as f:
            context = json.load(f)
            known_connections = context.get("known_connections", [])
            has_discovery = context.get("has_discovery", False)
            has_previous_oml = context.get("has_previous_oml", False)
            has_error_report = context.get("has_error_report", False)
    
    # Reuse guide tool logic
    from osiris.mcp.tools.guide import GuideTools
    
    tools = GuideTools()
    result = asyncio.run(tools.start({
        "intent": intent or "",
        "known_connections": known_connections,
        "has_discovery": has_discovery,
        "has_previous_oml": has_previous_oml,
        "has_error_report": has_error_report,
    }))
```

---

## Summary Table

| Issue | Component | Parameter | Status | Severity | Type |
|-------|-----------|-----------|--------|----------|------|
| 1 | Discovery | component_id | Lost in CLI delegation | HIGH | Missing |
| 2 | Memory Capture | intent, actor_trace, decisions, artifacts, oml_uri, error_report, notes | Lost in CLI | MEDIUM | Missing |
| 3 | OML Validate | strict | Not propagated to CLI | LOW | Partial |
| 4 | Connections Doctor | connection_id | Transformed implicitly | MEDIUM | Transformation |
| 5 | Discovery | idempotency_key | Cache only in MCP, not CLI | MEDIUM | Partial |
| 6 | Guide Start | known_connections, has_discovery, has_previous_oml, has_error_report | Not available in CLI | LOW | Missing |

---

## Architectural Recommendation

The "CLI-first" security architecture requires that:

1. **All functionality must be accessible from CLI** - MCP should delegate to CLI, not implement independently
2. **CLI must be self-contained** - CLI commands shouldn't require special environment or context from MCP
3. **Parameters must flow uniformly** - No information should be lost in layer transitions
4. **Caching decisions belong at CLI layer** - Not MCP (though MCP can add its own caching on top)

**Priority Actions:**

1. **HIGH:** Fix discovery component_id propagation
2. **MEDIUM:** Implement full memory_capture in CLI with all parameters
3. **MEDIUM:** Add idempotency_key support to CLI discovery command
4. **LOW:** Fix strict parameter propagation in OML validation
5. **LOW:** Create CLI guide_start command

All of these align with the documented "CLI-first" principle in CLAUDE.md.

