# Osiris Architecture

**Date:** 2025-09-22
**Version:** v0.2.0
**Status:** Milestone M1 — Component Registry & Runner (release)
**Purpose:** A lightweight overview of how Osiris compiles conversational intent into deterministic, production‑ready data pipelines.

---

## System Overview

Osiris turns business intent into a deterministic pipeline you can run locally or in an E2B cloud sandbox with identical behavior.

```
Intent (chat / YAML) → OML (v0.1.0) → Compile (deterministic manifest) → Run (Local | E2B) → Logs & HTML report
```

### High‑level flow

```mermaid
flowchart TD
    User([User / CLI])
    Chat{{Chat<br/>OML input}}
    OML([OML v0.1.0])
    Compiler[[Compiler]]
    Manifest([Deterministic Manifest<br/>SHA-256 fingerprint])
    Runner([Runner])
    subgraph Adapter_Proxy["Adapters / Proxy"]
      direction LR
      LocalAdapter([Local Adapter])
      Proxy([E2B Transparent Proxy])
    end
    Observations(["Events · Metrics · Artifacts"])
    HTMLReport(["HTML Report<br/>osiris logs html --open"])

    User -- "describe outcome" --> Chat
    Chat --> OML
    OML --> Compiler
    Compiler --> Manifest
    Manifest --> Runner
    Runner --> LocalAdapter
    Runner --> Proxy
    LocalAdapter --> Observations
    Proxy --> Observations
    Observations --> HTMLReport

    %% Optional: Style nodes for emphasis
    style User fill:#ddeeff,stroke:#222
    style Observations fill:#ffeebb,stroke:#b96
    style HTMLReport fill:#e7fde7,stroke:#585

```

---

## Core Concepts

### OML (Osiris Markup Language) — v0.1.0
A concise, YAML‑based pipeline spec. It references connections by alias (e.g. `@mysql.db_movies`) and uses self‑describing components.

- **Deterministic input** to the compiler
- **Versioned** alongside your code
- **No secrets** inside (only references)

### Deterministic Compiler
Validates the OML against component specs, resolves dependencies, and emits a **fingerprinted manifest**. Same inputs → same manifest, every time.

- JSON Schema validation against the **Component Registry**
- Secrets remain references; never embedded in artifacts
- Produces a plan the Runner can execute anywhere

### Runner & Execution Adapters
One runner, multiple environments with **full parity**:

- **Local Adapter:** executes on your machine
- **E2B Transparent Proxy:** spins an ephemeral sandbox and streams live events back

Both paths yield the **same logs, metrics, and artifacts**.

### Component Registry (Self‑describing)
Components declare capabilities and config via JSON Schema. The registry powers:

- Strict validation & guardrails
- Human‑readable errors
- LLM context generation (for chat)

### Connections & Secrets
Non‑secret connection metadata lives in `osiris_connections.yaml` (versioned). Secrets are provided via environment variables. The compiler and runtime resolve `@family.alias` at execution time.

### Observability by Default
Every run produces a structured session:

```
logs/<session>/
  ├─ events.jsonl
  ├─ metrics.jsonl
  └─ artifacts/
```

`osiris logs html --open` renders an interactive report with **rows processed, durations, per‑step details**, and environment badges (Local / E2B).

### Security Boundaries
- **SQL Safety**: Context-aware validation - read-only for extractors, controlled writes for loaders. See [SQL safety rules](reference/sql-safety.md).
- **Secrets Isolation**: Never stored in OML or compiled manifests, resolved at runtime only.
- **Connection Validation**: Driver-level enforcement of permissions per execution context.

---

## Architecture at a Glance

```mermaid
flowchart TB
  %% === Authoring ===
  subgraph A["**Authoring**"]
    I1@{shape: stadium, label: "Chat / OML"}
    V1@{shape: diamond, label: "Validator\n(JSON Schema)\nOML v0.1.0"}
    I1 --> V1
  end

  %% === Compilation ===
  subgraph C["**Compilation**"]
    V1 --> C1@{shape: hex, label: "Compiler"}
    C1 --> MF@{shape: tag-rect, label: "Manifest + Fingerprint"}
  end

  %% === Execution ===
  subgraph E["**Execution**"]
    MF --> RR@{shape: fr-rect, label: "Runner"}
    RR --> A1@{shape: rect, label: "Local Adapter"}
    RR --> A2@{shape: rect, label: "E2B Proxy"}
    A1 --> OUT@{shape: bow-rect, label: "Events • Metrics • Artifacts"}
    A2 --> OUT
  end

  %% === Observability ===
  subgraph O["**Observability**"]
    OUT --> RPT@{shape: doc, label: "HTML Report\n(osiris logs html --open)"}
  end

  %% === Registry ===
  subgraph R["**Registry**"]
    REG@{shape: cyl, label: "Component Registry\nSelf-describing specs"}
  end

  REG -.-> V1
  REG -.-> C1

  %% Optional styling
  classDef key fill:#e7f7ff,stroke:#002244,stroke-width:2px;
  classDef main fill:#f9fff3,stroke:#35510a,stroke-width:2px;
  class I1,V1,C1,MF,RR,A1,A2,OUT,RPT key
  class REG main

  %% Descriptive titles for easier navigation
  %% (Descriptions and tooltips could be added if desired)



```

---

## What's in v0.2.0 (M1)

- ✅ **Compiler** for OML v0.1.0 → deterministic manifests (with SHA‑256)
- ✅ **Runner** with **Local** and **E2B Transparent Proxy** adapters (full parity)
- ✅ **Component Registry** with JSON Schema specs (MySQL extractor, Supabase writer, CSV writer, …)
- ✅ **Connections & Secrets** via `osiris_connections.yaml` + environment variables
- ✅ **Observability**: structured events/metrics, HTML reports, environment badges
- ✅ **Row totals normalization** and **verbose streaming** parity (Local ↔ E2B)

### Not in this version (tracked in ADRs)

- ⏭️ **Streaming I/O** / RowStream API (ADR‑0022)
- ⏭️ **Remote object store writers** (S3/Azure/GCS) (ADR‑0023)
- ⏳ **Run export/context bundle** (ADR‑0027) — foundation exists; integration planned for M2

---

## CLI Quick Reference

```bash
# Compile OML to a deterministic manifest
osiris compile path/to/pipeline.yaml

# Run last compiled manifest locally (verbose)
osiris run --last-compile --verbose

# Run in E2B sandbox (installs deps in sandbox on first run)
osiris run --last-compile --e2b --e2b-install-deps --verbose

# Open HTML report for the last run
osiris logs html --open

# List components and connections
osiris components list
osiris connections list
```

---

## Detailed Architecture Diagrams

### Conversational Agent Architecture

The `osiris chat` command implements a sophisticated AI agent that orchestrates multiple subsystems.

#### High-Level Agent Architecture

This overview shows the main components and data flow:

```mermaid
graph LR
    User[User] --> Chat[Osiris Chat<br/>Agent]

    Chat --> LLM[LLM<br/>Providers]
    Chat --> Discover[Discovery<br/>System]
    Chat --> Registry[Component<br/>Registry]
    Chat --> State[State<br/>Management]

    Discover --> DB[(Databases)]
    State --> Session[(Session<br/>Store)]

    Chat --> OML[OML<br/>Generator]
    OML --> Pipeline[Pipeline<br/>YAML]

    style Chat fill:#f9f,stroke:#333,stroke-width:3px
    style OML fill:#9f9,stroke:#333,stroke-width:2px
```

#### Detailed Component Interactions

Here's how the agent orchestrates its subsystems:

```mermaid
graph TB
    subgraph "Osiris Chat Agent"
        User[User Input] --> Agent[Conversational Agent]

        Agent --> LLMRouter[LLM Router]

        subgraph "LLM Providers"
            OpenAI[OpenAI<br/>GPT-4/GPT-4o]
            Claude[Anthropic<br/>Claude 3.5]
            Gemini[Google<br/>Gemini]
        end

        LLMRouter --> OpenAI
        LLMRouter --> Claude
        LLMRouter --> Gemini

        subgraph "System Prompts"
            ConvPrompt[conversation_system.txt]
            SQLPrompt[sql_generation_system.txt]
            UserPrompt[user_prompt_template.txt]
        end

        Agent --> ConvPrompt
        Agent --> SQLPrompt
        Agent --> UserPrompt

        subgraph "Discovery Subsystem"
            Discovery[Discovery Agent]
            SchemaCache[(Schema Cache<br/>SQLite)]
            Fingerprint[Cache Fingerprint<br/>SHA-256]

            Discovery --> SchemaCache
            Discovery --> Fingerprint
            Fingerprint --> |Invalidate| SchemaCache
        end

        Agent --> Discovery

        subgraph "Component Registry"
            Registry[Component Registry]
            Specs[Component Specs<br/>JSON Schema]
            Context[LLM Context Builder]

            Registry --> Specs
            Registry --> Context
        end

        Agent --> Registry
        Context --> |Component Context| Agent

        subgraph "State Management"
            StateStore[(Session Store<br/>SQLite)]
            SessionLog[Session Logger]
            Events[events.jsonl]
            Metrics[metrics.jsonl]

            StateStore --> |Persist| Agent
            Agent --> SessionLog
            SessionLog --> Events
            SessionLog --> Metrics
        end

        Agent --> StateStore

        subgraph "OML Generation"
            OMLGen[OML Generator]
            Validator[OML Validator<br/>v0.1.0 Schema]
            Regenerate[Regeneration<br/>Logic]

            OMLGen --> Validator
            Validator --> |Failed| Regenerate
            Regenerate --> OMLGen
        end

        Agent --> OMLGen

        subgraph "Data Sources"
            MySQL[(MySQL)]
            Supabase[(Supabase)]
            CSV[CSV Files]
        end

        Discovery --> MySQL
        Discovery --> Supabase
        Discovery --> CSV
    end

    OMLGen --> Output[OML Pipeline<br/>output/pipeline.yaml]

    style Agent fill:#f9f,stroke:#333,stroke-width:4px
    style LLMRouter fill:#bbf,stroke:#333,stroke-width:2px
    style Discovery fill:#fbf,stroke:#333,stroke-width:2px
    style Registry fill:#bfb,stroke:#333,stroke-width:2px
    style OMLGen fill:#ffb,stroke:#333,stroke-width:2px
```

#### LLM Integration Layer

The agent supports multiple LLM providers with dynamic routing:

```mermaid
graph LR
    Agent[Conversational<br/>Agent] --> Router{LLM<br/>Router}

    Router --> |Config: OpenAI| GPT[GPT-4/4o]
    Router --> |Config: Anthropic| Claude[Claude 3.5]
    Router --> |Config: Google| Gemini[Gemini Pro]

    subgraph "Prompt Templates"
        Conv[conversation_system.txt]
        SQL[sql_generation.txt]
        User[user_template.txt]
    end

    Conv --> Agent
    SQL --> Agent
    User --> Agent

    subgraph "Pro Mode"
        Custom[Custom<br/>Prompts]
    end

    Custom -.->|--pro-mode| Agent

    style Agent fill:#bbf,stroke:#333,stroke-width:2px
    style Router fill:#fbf,stroke:#333,stroke-width:2px
```

#### Discovery & Caching System

Intelligent database exploration with fingerprint-based caching:

```mermaid
graph TB
    Agent[Agent] --> Discovery[Discovery<br/>Agent]

    Discovery --> Check{Cache<br/>Valid?}

    Check -->|No| Explore[Explore<br/>Database]
    Check -->|Yes| Load[Load from<br/>Cache]

    Explore --> Tables[Get Tables]
    Tables --> Columns[Get Columns]
    Columns --> Sample[Sample Data]
    Sample --> Fingerprint[Generate<br/>SHA-256]

    Fingerprint --> Store[(Store in<br/>SQLite Cache)]
    Load --> Return[Return<br/>Schema]
    Store --> Return

    subgraph "Cache Key"
        Host[Host]
        DB[Database]
        User[Username]
        Options[Options]
    end

    Host --> Fingerprint
    DB --> Fingerprint
    User --> Fingerprint
    Options --> Fingerprint

    style Discovery fill:#fbf,stroke:#333,stroke-width:2px
    style Fingerprint fill:#ff9,stroke:#333,stroke-width:2px
```

#### State & Session Management

Persistent conversation state with recovery capabilities:

```mermaid
graph LR
    subgraph "Session Lifecycle"
        Create[Create<br/>Session] --> Active[Active<br/>Conversation]
        Active --> Save[Save<br/>State]
        Save --> Active
        Active --> End[End<br/>Session]
    end

    subgraph "Persistence Layer"
        SQLite[(Session<br/>Store)]
        Events[events.jsonl]
        Metrics[metrics.jsonl]
        Artifacts[artifacts/]
    end

    Save --> SQLite
    Active --> Events
    Active --> Metrics
    Active --> Artifacts

    subgraph "Recovery"
        Interrupt[Interrupted] --> Resume[Resume<br/>from State]
        Resume --> Active
    end

    SQLite --> Resume

    style Active fill:#9f9,stroke:#333,stroke-width:2px
    style SQLite fill:#99f,stroke:#333,stroke-width:2px
```

#### OML Generation Pipeline

The synthesis and validation loop for pipeline creation:

```mermaid
graph LR
    Intent[User Intent] --> Context[Build Context]

    subgraph "Context Assembly"
        Schema[Database<br/>Schema]
        Components[Available<br/>Components]
        Examples[Component<br/>Examples]
    end

    Schema --> Context
    Components --> Context
    Examples --> Context

    Context --> Generate[Generate<br/>OML]
    Generate --> Validate{Validate<br/>v0.1.0}

    Validate -->|Pass| Save[Save to<br/>output/]
    Validate -->|Fail| Regen{Retry<br/>Count?}

    Regen -->|< 1| Fix[Fix & Regenerate]
    Regen -->|>= 1| Error[Show Error<br/>to User]

    Fix --> Generate

    Save --> Complete[Pipeline<br/>Ready]

    style Generate fill:#ffb,stroke:#333,stroke-width:2px
    style Validate fill:#f99,stroke:#333,stroke-width:2px
    style Complete fill:#9f9,stroke:#333,stroke-width:2px
```

#### Component Registry Integration

How the agent leverages component specifications:

```mermaid
graph TB
    Registry[Component<br/>Registry] --> Load[Load Specs]

    Load --> Parse[Parse<br/>YAML Specs]
    Parse --> Schema[Extract<br/>JSON Schema]
    Parse --> Examples[Extract<br/>Examples]

    Schema --> Builder[Context<br/>Builder]
    Examples --> Builder

    Builder --> Context[LLM Context<br/>Document]

    Context --> |Includes| List[Component List]
    Context --> |Includes| Config[Config Schemas]
    Context --> |Includes| Samples[Usage Examples]

    Agent[Agent] --> Request[Request<br/>Context]
    Request --> Context
    Context --> Agent

    style Registry fill:#bfb,stroke:#333,stroke-width:2px
    style Builder fill:#fbf,stroke:#333,stroke-width:2px
```

### Agent Capabilities and Interactions

The Conversational Agent orchestrates multiple sophisticated capabilities:

#### 1. **Multi-Provider LLM Integration**
- Routes requests to appropriate LLM provider based on configuration
- Supports OpenAI (GPT-4, GPT-4o), Anthropic (Claude 3.5), Google (Gemini)
- Handles provider-specific prompt optimization
- Manages token usage and rate limiting

#### 2. **Dynamic Prompt System**
- Loads system prompts from configurable templates
- Supports pro mode with custom prompts (`--pro-mode`)
- Combines conversation, SQL generation, and user context prompts
- Adapts prompts based on conversation state

#### 3. **Intelligent Discovery**
- **Progressive Profiling**: Explores only needed tables/columns
- **Cache Management**: SHA-256 fingerprinting prevents stale data
- **Automatic Invalidation**: Detects schema changes
- **Lazy Loading**: Fetches data only when required
- **Sample Data**: Retrieves example rows for context

#### 4. **Component Context Building**
- Reads component specifications from registry
- Builds LLM-friendly context with available components
- Includes examples and configuration schemas
- Validates component availability before OML generation

#### 5. **State Persistence**
- **Session Management**: SQLite-based conversation history
- **Recovery**: Resumes interrupted conversations
- **Context Preservation**: Maintains discovery results across turns
- **Audit Trail**: Complete conversation logging

#### 6. **OML Synthesis Loop**
- **Generation**: Creates OML based on user intent
- **Validation**: Checks against v0.1.0 schema
- **Regeneration**: One retry attempt on validation failure
- **Deterministic Output**: Same conversation produces same pipeline

#### 7. **Observability Integration**
- Structured event logging for each state transition
- Performance metrics collection
- Error tracking with context
- Session artifacts preservation

### Chat to OML State Machine

The conversational flow follows a deterministic state machine:

```mermaid
stateDiagram-v2
    [*] --> INIT
    INIT --> INTENT_CAPTURED: User describes need
    INTENT_CAPTURED --> DISCOVERY: Schema exploration
    DISCOVERY --> OML_SYNTHESIS: Generate pipeline
    OML_SYNTHESIS --> VALIDATE_OML: Validate syntax
    VALIDATE_OML --> REGENERATE_ONCE: Validation failed
    REGENERATE_ONCE --> VALIDATE_OML: Retry
    VALIDATE_OML --> COMPILE: Valid OML
    COMPILE --> RUN: Execute pipeline
    RUN --> COMPLETE: Success

    note right of DISCOVERY
        Progressive profiling
        Cache fingerprinting
        Discovery snapshots
    end note

    note right of OML_SYNTHESIS
        OML v0.1.0 schema
        Required/forbidden keys
        Connection resolution
    end note
```

### Compilation Pipeline

The compilation process ensures deterministic, secret-free artifacts:

```mermaid
graph LR
    subgraph "Compilation Process"
        OML[OML File] --> Parser[Parse & Validate]
        Parser --> Resolver[Resolve Connections]
        Resolver --> Fingerprint[Generate Fingerprints]
        Fingerprint --> Manifest[Deterministic Manifest]

        Config[osiris_connections.yaml] --> Resolver
        Env[Environment Variables] --> Resolver
    end

    style OML fill:#f9f,stroke:#333,stroke-width:2px
    style Manifest fill:#9f9,stroke:#333,stroke-width:2px
```

### Runtime Execution Flow

Pipeline execution adapts to local or E2B environments:

```mermaid
graph TB
    subgraph "Runtime Execution"
        Start[Start Runner] --> Adapter{Local or E2B?}

        Adapter -->|Local| LocalRun[LocalAdapter]
        Adapter -->|E2B| E2BRun[E2BTransparentProxy]

        LocalRun --> Drivers[Load Drivers]
        E2BRun --> Sandbox[Create Sandbox]
        Sandbox --> ProxyWorker[Deploy ProxyWorker]
        ProxyWorker --> Drivers

        Drivers --> Execute[Execute Steps]
        Execute --> Artifacts[Generate Artifacts]
        Artifacts --> Logs[Session Logs]

        Logs --> Complete[Pipeline Complete]
    end

    style Start fill:#f9f,stroke:#333,stroke-width:2px
    style Complete fill:#9f9,stroke:#333,stroke-width:2px
```

---

## Design Principles (Why it works)

1. **Determinism** — compilers over ad‑hoc glue; identical inputs → identical outputs
2. **Parity** — same behavior locally and in cloud sandboxes
3. **Transparency** — self‑describing components, explainable failures, rich logs
4. **Separation of concerns** — specs in the registry, secrets out of artifacts
5. **Open by default** — Apache 2.0 core; adopt gradually and run anywhere

---
