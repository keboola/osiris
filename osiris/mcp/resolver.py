"""
Resource resolver for Osiris MCP server.

Maps Osiris URIs to actual resources and handles resource operations.
"""

import json
from pathlib import Path

from mcp import types

from osiris.mcp.errors import ErrorFamily, OsirisError


class ResourceResolver:
    """
    Resolver for Osiris MCP resources.

    All resources are under the osiris://mcp/ namespace:
    - osiris://mcp/schemas/...  -> data/schemas/ (read-only, from package)
    - osiris://mcp/prompts/...  -> data/prompts/ (read-only, from package)
    - osiris://mcp/usecases/... -> data/usecases/ (read-only, from package)
    - osiris://mcp/discovery/... -> cache/ (runtime, from config)
    - osiris://mcp/drafts/...    -> cache/ (runtime, from config)
    - osiris://mcp/memory/...    -> memory/ (runtime, from config)
    - osiris://mcp/aiop/...      -> aiop/ (runtime, from config, read-only via tools)
    """

    def __init__(self, config=None):
        """
        Initialize the resource resolver.

        Args:
            config: MCPConfig instance (if None, will load from osiris.yaml)
        """
        # Import here to avoid circular dependency
        if config is None:
            from osiris.mcp.config import get_config  # noqa: PLC0415  # Lazy import

            config = get_config()

        # Read-only data directory (schemas, prompts, usecases) - from package
        self.data_dir = Path(__file__).parent / "data"

        # Runtime state directories - from config (filesystem contract)
        self.cache_dir = config.cache_dir  # For discovery and drafts
        self.memory_dir = config.memory_dir  # For memory capture

        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def _parse_uri(self, uri: str) -> tuple[str, Path]:
        """
        Parse an Osiris URI and return the resource type and path.

        Args:
            uri: Osiris URI (e.g., osiris://mcp/schemas/oml/v0.1.0.json)

        Returns:
            Tuple of (resource_type, relative_path)

        Raises:
            OsirisError: If URI is invalid
        """
        if not uri.startswith("osiris://mcp/"):
            raise OsirisError(
                ErrorFamily.SEMANTIC, f"Invalid URI scheme: {uri}", path=["uri"], suggest="Use osiris://mcp/... URIs"
            )

        # Remove prefix and split
        path_part = uri[len("osiris://mcp/") :]
        parts = path_part.split("/", 1)

        if len(parts) < 2:
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Invalid URI format: {uri}",
                path=["uri"],
                suggest="Use format osiris://mcp/<type>/<path>",
            )

        resource_type = parts[0]
        relative_path = Path(parts[1])

        return resource_type, relative_path

    def _get_physical_path(self, uri: str) -> Path:
        """
        Get the physical file path for a URI.

        Validates that resolved path stays within the allowed root directory
        to prevent path traversal attacks (CWE-22).

        Args:
            uri: Osiris URI

        Returns:
            Physical file path

        Raises:
            OsirisError: If resource type is unknown or path escapes sandbox
        """
        resource_type, relative_path = self._parse_uri(uri)

        # Map resource types to directories
        if resource_type in ["schemas", "prompts", "usecases"]:
            # Read-only data resources (from package)
            allowed_root = self.data_dir / resource_type
            physical_path = allowed_root / relative_path
        elif resource_type in ["discovery", "drafts"]:
            # Runtime cache resources (from config)
            allowed_root = self.cache_dir
            physical_path = allowed_root / relative_path
        elif resource_type == "memory":
            # Memory resources (from config)
            allowed_root = self.memory_dir
            physical_path = allowed_root / relative_path
        else:
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Unknown resource type: {resource_type}",
                path=["uri", "type"],
                suggest="Valid types: schemas, prompts, usecases, discovery, drafts, memory",
            )

        # Normalize path to resolve .. and symlinks, then validate containment
        try:
            resolved_path = physical_path.resolve()
            allowed_root_resolved = allowed_root.resolve()
        except (OSError, RuntimeError) as e:
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Failed to resolve path: {str(e)}",
                path=["uri"],
                suggest="Check for invalid symlinks or filesystem issues",
            ) from e

        # Validate path stays within allowed root (prevent path traversal)
        try:
            # Check if resolved path is relative to allowed root
            resolved_path.relative_to(allowed_root_resolved)
        except ValueError:
            # Path is outside allowed root - path traversal attempt detected
            raise OsirisError(
                ErrorFamily.POLICY,
                f"Path traversal attempt detected: {uri}",
                path=["uri", "path"],
                suggest="URIs must not escape the resource directory using .. or absolute paths",
            ) from None

        return physical_path

    async def list_resources(self) -> list[types.Resource]:
        """
        List all available resources.

        Returns:
            List of MCP Resource objects
        """
        resources = []

        # Add schema resources
        resources.append(
            types.Resource(
                uri="osiris://mcp/schemas/oml/v0.1.0.json",
                name="OML v0.1.0 Schema",
                description="JSON Schema for OML pipeline format version 0.1.0",
                mimeType="application/json",
            )
        )

        # Add instruction resources (inline content)
        resources.append(
            types.Resource(
                uri="osiris://instructions/workflow",
                name="Osiris MCP Workflow",
                description="Step-by-step workflow for creating OML pipelines via MCP",
                mimeType="text/markdown",
            )
        )

        resources.append(
            types.Resource(
                uri="osiris://instructions/oml-syntax",
                name="OML Syntax Guide",
                description="OML v0.1.0 syntax reference and structure",
                mimeType="text/markdown",
            )
        )

        resources.append(
            types.Resource(
                uri="osiris://instructions/best-practices",
                name="OML Best Practices",
                description="Best practices for writing OML pipelines",
                mimeType="text/markdown",
            )
        )

        # Add prompt resources
        resources.append(
            types.Resource(
                uri="osiris://mcp/prompts/oml_authoring_guide.md",
                name="OML Authoring Guide",
                description="Guide for authoring OML pipelines",
                mimeType="text/markdown",
            )
        )

        # Add usecase resources
        resources.append(
            types.Resource(
                uri="osiris://mcp/usecases/catalog.yaml",
                name="Use Case Catalog",
                description="Catalog of OML pipeline use cases and templates",
                mimeType="application/x-yaml",
            )
        )

        return resources

    async def read_resource(self, uri: str) -> types.ReadResourceResult:
        """
        Read a resource by URI.

        Args:
            uri: Resource URI

        Returns:
            Resource content

        Raises:
            OsirisError: If resource not found or cannot be read
        """
        # Handle inline instruction resources
        if uri.startswith("osiris://instructions/"):
            return await self._get_instruction_resource(uri)

        # Get physical path
        try:
            file_path = self._get_physical_path(uri)
        except OsirisError:
            raise

        # Check if file exists
        if not file_path.exists():
            # Check if it's a discovery artifact that should be generated
            if "discovery" in uri:
                return await self._generate_discovery_artifact(uri)

            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Resource not found: {uri}",
                path=["uri"],
                suggest="Check the resource URI or run discovery first",
            )

        # Read the file
        try:
            if file_path.suffix == ".json":
                with open(file_path) as f:
                    content = json.load(f)
                    text = json.dumps(content, indent=2)
                mime_type = "application/json"
            else:
                with open(file_path) as f:
                    text = f.read()
                mime_type = "text/plain"

            return types.ReadResourceResult(
                contents=[types.TextResourceContents(uri=uri, mimeType=mime_type, text=text)]
            )

        except (OSError, json.JSONDecodeError) as e:
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Failed to read resource: {str(e)}",
                path=["uri"],
                suggest="Check resource permissions and format",
            ) from e

    async def _generate_discovery_artifact(self, uri: str) -> types.ReadResourceResult:
        """
        Generate a discovery artifact on-demand.

        Args:
            uri: Discovery artifact URI

        Returns:
            Generated artifact content
        """
        # Parse discovery URI format: osiris://mcp/discovery/{disc_id}/{artifact}.json
        # Split gives: ['osiris:', '', 'mcp', 'discovery', 'disc_id', 'artifact.json']
        parts = uri.split("/")
        if len(parts) < 6:
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Invalid discovery URI format: {uri}",
                path=["uri"],
                suggest="Use format osiris://mcp/discovery/<id>/<artifact>.json",
            )

        discovery_id = parts[4]
        artifact_name = parts[5].replace(".json", "")

        # Generate placeholder content based on artifact type
        if artifact_name == "overview":
            content = {
                "discovery_id": discovery_id,
                "timestamp": "2025-10-14T00:00:00Z",
                "connection": "unknown",
                "database": "unknown",
                "tables_count": 0,
                "total_rows": 0,
            }
        elif artifact_name == "tables":
            content = {"discovery_id": discovery_id, "tables": []}
        elif artifact_name == "samples":
            content = {"discovery_id": discovery_id, "samples": {}}
        else:
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Unknown discovery artifact: {artifact_name}",
                path=["uri", "artifact"],
                suggest="Valid artifacts: overview, tables, samples",
            )

        return types.ReadResourceResult(
            contents=[
                types.TextResourceContents(uri=uri, mimeType="application/json", text=json.dumps(content, indent=2))
            ]
        )

    async def _get_instruction_resource(self, uri: str) -> types.ReadResourceResult:
        """
        Get inline instruction resources.

        Args:
            uri: Instruction resource URI (osiris://instructions/...)

        Returns:
            Instruction content

        Raises:
            OsirisError: If instruction not found
        """
        if uri == "osiris://instructions/workflow":
            content = """# Osiris MCP Workflow

## CRITICAL: Always Follow This Pattern

### Step 1: Get OML Schema FIRST
Before creating any pipeline, ALWAYS call `oml_schema_get` to understand the OML v0.1.0 structure.

### Step 2: Ask Clarifying Questions
Never assume business logic. Ask the user to define:
- "TOP X" → Top by what metric? (sales, rating, revenue, date)
- "recent" → What timeframe? (last day, week, month, year)
- "best" → Best according to what criteria?
- Filters and transformations should be explicit

### Step 3: Discovery (if needed)
Use `discovery_request` to explore schemas and sample data

### Step 4: Create OML Draft
Draft the pipeline following the schema structure

### Step 5: ALWAYS Validate
Call `oml_validate` to verify the OML before saving

### Step 6: Save Only After Validation
Only call `oml_save` if validation passes

### Step 7: Capture Learnings
Use `memory_capture` to save successful patterns, business decisions, user preferences

## Validation Rules
- Steps with write_mode='replace' or 'upsert' REQUIRE 'primary_key' field
- Connection references must use '@family.alias' format
- All step IDs must be unique

## Common Mistakes to Avoid
- ❌ Skipping oml_schema_get
- ❌ Skipping oml_validate
- ❌ Assuming what "top" means
- ❌ Not asking clarifying questions
"""

        elif uri == "osiris://instructions/oml-syntax":
            content = """# OML v0.1.0 Syntax Guide

## Document Structure

```yaml
oml_version: "0.1.0"
name: pipeline-name
description: Optional description
steps:
  - id: step1
    component: component.name
    mode: read|write|transform
    config:
      # Component-specific configuration
```

## Required Top-Level Keys
- `oml_version` (string) - Must be "0.1.0"
- `name` (string) - Pipeline name (kebab-case recommended)
- `steps` (array) - List of pipeline steps

## Step Structure

Each step requires:
- `id` (string) - Unique identifier for the step
- `component` (string) - Component name from registry (e.g., "mysql.extractor")
- `mode` (enum) - One of: `read`, `write`, `transform`
- `config` (object) - Component configuration

Optional step fields:
- `needs` (array) - List of step IDs this step depends on
- `description` (string) - Step description

## Modes Explained

- **read** - Extract data from a source (extractors)
- **write** - Write data to a destination (writers)
- **transform** - Transform data in-memory (transformers)

## Connection References

Use the `@family.alias` format to reference configured connections:

```yaml
config:
  connection: "@mysql.production"
  table: users
```

Never inline credentials - always use connection references.

## Common Components

### Database Extractors
- `mysql.extractor` - Extract from MySQL
- `supabase.extractor` - Extract from Supabase

Requires: `connection` + (`query` OR `table`)

### Database Writers
- `mysql.writer` - Write to MySQL
- `supabase.writer` - Write to Supabase

Requires: `connection`, `table`
Optional: `write_mode` (append|replace|upsert), `primary_key`

### Transformers
- `duckdb.transformer` - Transform with SQL

Requires: `query`

### Filesystem Components
- `filesystem.csv_reader` - Read CSV files
- `filesystem.csv_writer` - Write CSV files
- `filesystem.json_reader` - Read JSON files
- `filesystem.json_writer` - Write JSON files

Requires: `path`

## Write Modes

For writer components:
- `append` (default) - Insert new rows
- `replace` - Replace all rows (REQUIRES `primary_key`)
- `upsert` - Insert or update (REQUIRES `primary_key`)

## Dependencies

Use `needs` to specify step execution order:

```yaml
steps:
  - id: extract
    component: mysql.extractor
    mode: read
    config:
      connection: "@mysql.db"
      table: users

  - id: write
    component: supabase.writer
    mode: write
    needs: [extract]  # Runs after extract
    config:
      connection: "@supabase.db"
      table: users_copy
```

## Forbidden Keys

These are legacy v0.0.x keys and will cause validation errors:
- `version` (use `oml_version` instead)
- `connectors`
- `tasks`
- `outputs`
"""

        elif uri == "osiris://instructions/best-practices":
            content = """# OML Best Practices

## Pipeline Design

### 1. Use Descriptive IDs
```yaml
# Good
steps:
  - id: extract_active_users
  - id: transform_user_metrics
  - id: write_to_warehouse

# Avoid
steps:
  - id: step1
  - id: step2
```

### 2. Add Descriptions
```yaml
name: user-analytics-pipeline
description: Daily aggregation of user activity metrics for reporting

steps:
  - id: extract_events
    description: Extract last 24h of user events from production DB
    ...
```

### 3. Specify Write Modes Explicitly
```yaml
# Always specify write_mode for clarity
config:
  connection: "@supabase.warehouse"
  table: daily_metrics
  write_mode: upsert  # Explicit intent
  primary_key: [date, user_id]
```

## Security

### 1. Never Inline Secrets
```yaml
# ❌ WRONG - Inline credentials
config:
  host: db.example.com
  user: admin
  password: secret123  # FORBIDDEN

# ✅ CORRECT - Use connection reference
config:
  connection: "@mysql.production"
```

### 2. Don't Override Security Fields
```yaml
# ❌ WRONG - Override forbidden fields
config:
  connection: "@mysql.production"
  password: different_password  # Validation error

# ✅ CORRECT - Only override allowed fields
config:
  connection: "@mysql.production"
  schema: analytics  # Allowed override
```

## Component Selection

### 1. Use Appropriate Components
- **Extractors** for reading data sources
- **Transformers** for data manipulation
- **Writers** for persisting results

### 2. Choose SQL vs Code Transforms
```yaml
# Prefer SQL transformers for data operations
- id: aggregate
  component: duckdb.transformer
  mode: transform
  config:
    query: |
      SELECT user_id, COUNT(*) as event_count
      FROM events
      GROUP BY user_id
```

## Performance

### 1. Limit Data Early
```yaml
# Good - Filter at source
config:
  query: |
    SELECT * FROM events
    WHERE created_at >= NOW() - INTERVAL 1 DAY
    LIMIT 10000

# Avoid - Extracting everything then filtering
```

### 2. Use Dependencies Wisely
```yaml
# Parallel execution (no dependencies)
steps:
  - id: extract_users
    ...
  - id: extract_orders
    ...

# Sequential when needed
steps:
  - id: extract_users
    ...
  - id: enrich_users
    needs: [extract_users]
    ...
```

## Validation

### 1. Always Validate Before Saving
```
1. Call oml_validate
2. Fix any errors
3. Call oml_save
```

### 2. Check Component Requirements
Each component has specific required fields - consult component specs or discovery results.

### 3. Handle Primary Keys
```yaml
# For replace/upsert, always specify primary_key
config:
  write_mode: upsert
  primary_key: [id]  # Required!
```

## Testing

### 1. Start with Small Data
Use LIMIT clauses during development:
```yaml
config:
  query: SELECT * FROM large_table LIMIT 100
```

### 2. Test Incrementally
1. Test extract step alone
2. Add transform
3. Add write step

### 3. Use Appropriate Environments
```yaml
# Development
config:
  connection: "@mysql.dev"

# Production (after testing)
config:
  connection: "@mysql.production"
```

## Maintainability

### 1. Document Complex Logic
```yaml
steps:
  - id: complex_transform
    description: |
      Calculates 7-day rolling average of user activity.
      Excludes inactive users (no activity in 30 days).
      Aggregates by user_id and date.
    component: duckdb.transformer
    ...
```

### 2. Keep Pipelines Focused
One pipeline = one concern. Split large workflows into multiple pipelines.

### 3. Use Consistent Naming
- Pipeline names: `kebab-case`
- Step IDs: `snake_case` or `kebab-case`
- Table names: Match your database conventions
"""

        else:
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Unknown instruction resource: {uri}",
                path=["uri"],
                suggest="Valid instructions: workflow, oml-syntax, best-practices",
            )

        return types.ReadResourceResult(
            contents=[types.TextResourceContents(uri=uri, mimeType="text/markdown", text=content)]
        )

    async def write_resource(self, uri: str, content: str) -> bool:
        """
        Write a resource (for runtime resources only).

        Args:
            uri: Resource URI
            content: Content to write

        Returns:
            True if successful

        Raises:
            OsirisError: If resource is read-only or write fails
        """
        resource_type, _ = self._parse_uri(uri)

        # Check if resource type is writable
        if resource_type in ["schemas", "prompts", "usecases"]:
            raise OsirisError(
                ErrorFamily.POLICY,
                f"Cannot write to read-only resource type: {resource_type}",
                path=["uri", "type"],
                suggest="Only discovery, drafts, and memory resources are writable",
            )

        # Get physical path and ensure parent directory exists
        file_path = self._get_physical_path(uri)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the content
        try:
            with open(file_path, "w") as f:
                f.write(content)
            return True
        except OSError as e:
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Failed to write resource: {str(e)}",
                path=["uri"],
                suggest="Check file permissions and disk space",
            ) from e

    def validate_uri(self, uri: str) -> bool:
        """
        Validate that a URI follows the correct format.

        Args:
            uri: URI to validate

        Returns:
            True if valid
        """
        try:
            self._parse_uri(uri)
            return True
        except OsirisError:
            return False
