# Osiris Core Concepts

> **Audience**: Developers new to Osiris who need to understand the foundational architecture before building components.

## Overview

Osiris is an **LLM-first conversational ETL pipeline system** built around self-describing components. This document explains the core concepts and how they fit together.

---

## The Five Key Abstractions

### 1. Component

**What**: A self-describing building block for data pipelines.

**Purpose**: Declares *what* operations are possible, *what* configuration is needed, and *what* capabilities are supported.

**File**: `components/<name>/spec.yaml` (declarative YAML)

**Example**: `mysql.extractor` component declares:
- "I can extract data from MySQL databases"
- "I need: host, database, user, password, query"
- "I support: discovery mode, batch operations"

**Key Properties**:
- **Modes**: What operations? (`extract`, `write`, `transform`, `discover`)
- **Capabilities**: What features? (`discover: true`, `streaming: false`)
- **Config Schema**: JSON Schema defining required/optional fields
- **Secrets**: Which fields contain sensitive data (passwords, keys)

**Lifecycle**: Loaded by Registry → Validated → Used by Compiler → Referenced at Runtime

---

### 2. Connector

**What**: Database/API client managing connections and low-level protocol details.

**Purpose**: Handles *where* to connect and *how* to authenticate.

**Location**: `osiris/connectors/<family>/connection.py` (Python module)

**Example**: `MySQLConnector` provides:
- Connection pooling
- Query execution
- Transaction management
- Error handling

**Key Responsibilities**:
- Establish connections using resolved credentials
- Provide query/command execution methods
- Health checking (`doctor()` method)
- Connection lifecycle management

**Relationship**: A connector is *used by* one or more drivers.

---

### 3. Driver

**What**: Executable logic that performs a specific data operation.

**Purpose**: Implements *how* to execute a pipeline step (extract, write, transform).

**Location**: `osiris/drivers/<name>_driver.py` (Python class)

**Example**: `MySQLExtractorDriver` implements:
```python
def run(self, *, step_id, config, inputs, ctx) -> dict:
    # 1. Get resolved connection from config
    # 2. Build SQL query
    # 3. Execute query via connector
    # 4. Emit metrics (rows_read)
    # 5. Return {"df": DataFrame}
```

**Protocol**: Must implement `Driver` protocol from `osiris/core/driver.py`

**Key Responsibilities**:
- Validate configuration
- Execute data operation (extract/write/transform)
- Emit metrics and events via context
- Handle errors gracefully
- Return structured output (`{"df": DataFrame}` or `{}`)

**Relationship**: A driver *uses* a connector and *implements* a component's runtime behavior.

---

### 4. Registry

**What**: Centralized catalog of all component specifications.

**Purpose**: Single source of truth for component metadata, schemas, and capabilities.

**Location**: `osiris/components/registry.py`

**Key Functions**:
- **Load specs**: Scan `components/` directory for `spec.yaml` files
- **Validate specs**: Check against JSON Schema and semantic rules
- **Query components**: List available components, filter by mode/capability
- **Provide metadata**: Supply config schemas, secrets, examples to compiler

**CLI Interface**:
```bash
osiris components list              # All components
osiris components list --runnable   # Only components with drivers
osiris components show mysql.extractor  # Detailed spec
osiris components validate mysql.extractor --level strict
```

**Relationship**: Registry *loads* components and *validates* specs. Used by Compiler and CLI.

---

### 5. Runner

**What**: Orchestrator that executes compiled pipelines step-by-step.

**Purpose**: Coordinates driver execution, manages state, collects artifacts.

**Location**: `osiris/core/runner_v0.py`

**Execution Flow**:
1. **Load manifest**: Read compiled pipeline (manifest.yaml)
2. **Resolve connections**: Convert `@mysql.default` → actual credentials
3. **Create session**: Initialize logging, artifacts directory
4. **Execute steps**: For each step:
   - Resolve inputs from upstream outputs
   - Instantiate driver
   - Call `driver.run(step_id, config, inputs, ctx)`
   - Collect outputs, emit events/metrics
5. **Cleanup**: Finalize artifacts, write status.json

**Adapters**: Runner uses execution adapters for different environments:
- **LocalAdapter**: Execute on host machine
- **E2BTransparentProxy**: Execute in cloud sandbox (E2B)

**Relationship**: Runner *uses* Registry to discover drivers, *calls* driver.run(), and *manages* execution lifecycle.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER / LLM COMPILER                       │
└────────────────────────────┬────────────────────────────────────┘
                             │ creates
                             ▼
                    ┌─────────────────┐
                    │  OML Pipeline   │ (YAML file)
                    │ pipeline.yaml   │
                    └────────┬────────┘
                             │ compiles via
                             ▼
                    ┌─────────────────┐
                    │ Component       │◄──────┐
                    │ Registry        │       │ loads specs
                    └────────┬────────┘       │
                             │ validates      │
                             │                │
         ┌───────────────────┼────────────────┤
         │                   │                │
         ▼                   ▼                ▼
┌─────────────────┐  ┌─────────────┐  ┌──────────────┐
│ Component Spec  │  │  Component  │  │  Component   │
│ mysql.extractor │  │supabase.writer  │duckdb.processor
│   spec.yaml     │  │  spec.yaml  │  │  spec.yaml   │
└─────────────────┘  └─────────────┘  └──────────────┘
         │                   │                │
         │ x-runtime.driver  │                │
         ▼                   ▼                ▼
┌─────────────────┐  ┌─────────────┐  ┌──────────────┐
│  Driver Impl    │  │   Driver    │  │   Driver     │
│MySQLExtractorDriver│SupabaseWriterDr│DuckDBProcessor│
│  (Python class) │  │(Python class)   │(Python class)│
└────────┬────────┘  └──────┬──────┘  └──────┬───────┘
         │                   │                │
         │ uses              │ uses           │
         ▼                   ▼                ▼
┌─────────────────┐  ┌─────────────┐  ┌──────────────┐
│  Connector      │  │ Connector   │  │  DuckDB      │
│ MySQLConnector  │  │SupabaseClient   │  Engine      │
│(connection mgmt)│  │(REST client)│  │ (SQL engine) │
└─────────────────┘  └─────────────┘  └──────────────┘
         │                   │                │
         │ connects to       │ calls          │
         ▼                   ▼                ▼
    ┌─────────┐         ┌─────────┐     ┌─────────┐
    │ MySQL   │         │Supabase │     │In-Memory│
    │Database │         │  API    │     │  Data   │
    └─────────┘         └─────────┘     └─────────┘

                             ▲
                             │ orchestrates
                    ┌────────┴────────┐
                    │     Runner      │
                    │  (Executor)     │
                    └─────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
      ┌─────────────┐ ┌─────────────┐ ┌────────────┐
      │LocalAdapter │ │ E2BTransparent│ │Future:    │
      │ (host exec) │ │ Proxy (cloud) │ │K8sAdapter │
      └─────────────┘ └─────────────┘ └────────────┘
```

---

## Key Differences

### Component vs Driver

| Aspect | Component (spec.yaml) | Driver (Python class) |
|--------|----------------------|----------------------|
| **Nature** | Declarative metadata | Imperative code |
| **Purpose** | Describe capabilities | Implement behavior |
| **Location** | `components/<name>/spec.yaml` | `osiris/drivers/<name>_driver.py` |
| **Consumed By** | Compiler, Registry, CLI | Runner |
| **Example** | "I support discovery mode" | `def discover(config): ...` |
| **Validation** | JSON Schema validation | Runtime protocol check |

**Relationship**: Component spec *declares* what the driver *implements*.

---

### Component vs Connector

| Aspect | Component | Connector |
|--------|-----------|-----------|
| **Scope** | Single data operation | Multiple operations |
| **Reusability** | One component = one operation | One connector = many components |
| **Configuration** | Operation-specific (query, table) | Connection-specific (host, credentials) |
| **Example** | `mysql.extractor` (reads data) | `MySQLConnector` (manages connections) |
| **Files** | `spec.yaml` + driver | `connection.py` + utils |

**Relationship**: Multiple components (extractor, writer) can *share* the same connector (MySQLConnector).

**Example**:
- `mysql.extractor` → uses `MySQLConnector`
- `mysql.writer` → uses same `MySQLConnector`

---

### Driver vs Connector

| Aspect | Driver | Connector |
|--------|--------|-----------|
| **Layer** | Business logic | Infrastructure |
| **Knows About** | Pipeline steps, DataFrames, metrics | Connections, protocols, retries |
| **Entry Point** | `run(step_id, config, inputs, ctx)` | `connect()`, `execute()`, `close()` |
| **Error Handling** | Step-level errors, retry logic | Connection errors, timeouts |
| **State** | Stateless (per-step) | Stateful (connection pooling) |

**Relationship**: Driver *calls* connector methods to perform I/O.

**Example Flow**:
```python
# In MySQLExtractorDriver.run()
connector = MySQLConnector(config["resolved_connection"])
df = connector.execute_query(config["query"])
ctx.log_metric("rows_read", len(df))
return {"df": df}
```

---

### Registry vs Runner

| Aspect | Registry | Runner |
|--------|----------|--------|
| **Phase** | Compile-time | Runtime |
| **Purpose** | Validate and catalog components | Execute pipeline steps |
| **Input** | Component specs (YAML) | Compiled manifest (JSON) |
| **Output** | Validated specs, metadata | Executed steps, artifacts |
| **Mutability** | Read-only | Writes artifacts, logs |

**Relationship**: Runner *queries* Registry to discover available drivers, then *executes* them.

---

## Component Lifecycle

### 1. Development Phase

```
Developer writes:
  components/mycomp/spec.yaml   (what it does)
  osiris/drivers/mycomp_driver.py  (how it works)
  osiris/connectors/mydb/connection.py  (where it connects)
```

### 2. Registration Phase

```
Registry.load_specs() →
  Validate spec.yaml against JSON Schema →
  Check semantic rules (secrets, aliases) →
  Store in memory cache →
  ✓ Component available
```

### 3. Compilation Phase

```
User writes pipeline.yaml (OML) →
Compiler queries Registry for component specs →
Validates config against component's configSchema →
Resolves connections (@mysql.default) →
Generates manifest.yaml →
✓ Pipeline ready to run
```

### 4. Execution Phase

```
Runner loads manifest.yaml →
For each step:
  1. DriverRegistry.get(component_name) → Driver instance
  2. Driver.run(step_id, config, inputs, ctx)
     - Driver calls Connector methods
     - Connector executes database operations
     - Driver emits metrics (rows_read, duration_ms)
  3. Runner collects outputs, logs events
✓ Pipeline complete
```

---

## Data Flow Example

**Scenario**: Extract from MySQL, write to Supabase

### OML Pipeline (User Input)
```yaml
oml_version: "0.1.0"
name: "mysql_to_supabase"
steps:
  - id: extract_users
    component: mysql.extractor
    mode: extract
    config:
      connection: "@mysql.default"
      query: "SELECT * FROM users"

  - id: write_users
    component: supabase.writer
    mode: write
    inputs:
      df: "${extract_users.df}"
    config:
      connection: "@supabase.main"
      table: "users"
```

### Compilation Flow

1. **Registry lookup**:
   - Load `components/mysql.extractor/spec.yaml`
   - Validate `config.query` against `configSchema`
   - Load `components/supabase.writer/spec.yaml`
   - Validate `config.table` against `configSchema`

2. **Connection resolution**:
   - `@mysql.default` → `{host: localhost, database: mydb, user: admin, password: $MYSQL_PASSWORD}`
   - `@supabase.main` → `{url: https://..., key: $SUPABASE_KEY}`

3. **Manifest generation**:
   - Create `manifest.yaml` with resolved connections
   - Store in `logs/compile_<timestamp>/`

### Execution Flow

1. **Step 1: extract_users**
   ```
   Runner → DriverRegistry.get("mysql.extractor")
           → MySQLExtractorDriver instance
           → driver.run(
               step_id="extract_users",
               config={
                 "query": "SELECT * FROM users",
                 "resolved_connection": {host, database, user, password}
               },
               inputs=None,
               ctx=ExecutionContext
             )

   Inside driver.run():
     connector = MySQLConnector(resolved_connection)
     df = connector.execute_query(query)
     ctx.log_metric("rows_read", len(df))
     return {"df": df}

   Runner stores: outputs["extract_users"] = {"df": DataFrame(100 rows)}
   ```

2. **Step 2: write_users**
   ```
   Runner → Resolve inputs: df = outputs["extract_users"]["df"]
           → DriverRegistry.get("supabase.writer")
           → SupabaseWriterDriver instance
           → driver.run(
               step_id="write_users",
               config={
                 "table": "users",
                 "resolved_connection": {url, key}
               },
               inputs={"df": DataFrame(100 rows)},
               ctx=ExecutionContext
             )

   Inside driver.run():
     client = SupabaseClient(resolved_connection)
     records = inputs["df"].to_dict("records")
     client.insert(table, records)
     ctx.log_metric("rows_written", len(records))
     return {}

   Runner emits events: step_complete, rows_written=100
   ```

---

## When to Create What

### Create a Component Spec when:
- Adding a new data source or destination
- Defining a new transformation type
- Exposing new capabilities to the LLM compiler

**Files to create**:
- `components/<name>/spec.yaml`

### Create a Driver when:
- Implementing the runtime behavior for a component
- Executing extract/write/transform logic

**Files to create**:
- `osiris/drivers/<name>_driver.py`

### Create a Connector when:
- Supporting a new database/API type
- Reusing connection logic across multiple drivers

**Files to create**:
- `osiris/connectors/<family>/connection.py`
- `osiris/connectors/<family>/utils.py`

### Extend the Registry when:
- Adding new validation rules
- Implementing new discovery patterns
- Supporting new component metadata

**Files to modify**:
- `osiris/components/registry.py`

### Extend the Runner when:
- Adding new execution phases
- Implementing new orchestration patterns
- Supporting new artifact types

**Files to modify**:
- `osiris/core/runner_v0.py`

---

## Common Patterns

### Pattern 1: Extractor Component
```
Component Spec (mysql.extractor/spec.yaml)
  ↓ declares
Driver (mysql_extractor_driver.py)
  ↓ uses
Connector (connectors/mysql/connection.py)
  ↓ connects to
MySQL Database
```

### Pattern 2: Writer Component
```
Component Spec (supabase.writer/spec.yaml)
  ↓ declares
Driver (supabase_writer_driver.py)
  ↓ uses
Connector (connectors/supabase/connection.py)
  ↓ calls
Supabase REST API
```

### Pattern 3: Processor Component
```
Component Spec (duckdb.processor/spec.yaml)
  ↓ declares
Driver (duckdb_processor_driver.py)
  ↓ uses
DuckDB Engine (in-memory)
  ↓ transforms
DataFrame
```

---

## Key Takeaways

1. **Components are declarative**, Drivers are imperative
2. **Connectors are reusable** across multiple drivers
3. **Registry validates at compile-time**, Runner executes at runtime
4. **Specs describe capabilities**, Drivers implement behavior
5. **One connector** can serve multiple components (extractor + writer)

---

## Next Steps

- **Build a Component**: See [`COMPONENT_DEVELOPER_AUDIT.md`](../COMPONENT_DEVELOPER_AUDIT.md)
- **Understand Drivers**: See [`module-drivers.md`](module-drivers.md)
- **Understand Registry**: See [`module-components.md`](module-components.md)
- **Understand Connectors**: See [`module-connectors.md`](module-connectors.md)
- **Understand Runner**: See [`module-runtime.md`](module-runtime.md)

---

**Remember**: Component = What, Driver = How, Connector = Where, Registry = Catalog, Runner = Executor.
