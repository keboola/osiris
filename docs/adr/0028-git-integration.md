# ADR-0028: Git Project Structure & Reproducibility

## Status
Proposed

## Context

Currently, Osiris projects lack a standard structure for version control and team collaboration. Users struggle with:
- No canonical way to organize Osiris projects in Git repositories
- Difficulty sharing pipeline configurations across teams
- Inconsistent secret management across environments
- No standard for reproducing environments from Git
- Manual setup required for each team member

The problem impacts:
- **Team Collaboration**: Each developer has different local setup
- **CI/CD Integration**: No standard structure for automation
- **Reproducibility**: Cannot reliably recreate environments
- **Onboarding**: New team members need extensive setup help
- **Versioning**: Pipeline changes not properly tracked

Organizations need:
- Standardized project layout for Osiris pipelines
- Git-friendly configuration management
- **Reproducible environments**: Clone Osiris + user's Git repo + secrets = identical environment restored
- Clear separation of code, config, and secrets
- Integration with existing Git workflows

## Decision

Define a canonical Git repository structure for Osiris projects with clear conventions for organizing pipelines, configurations, connections, and components. Provide tooling to initialize projects and restore environments from Git.

### Canonical Project Structure
```
my-osiris-project/
├── .gitignore                 # Osiris-specific ignores
├── README.md                  # Project documentation
├── osiris.yaml                # Main configuration (versioned)
├── osiris_connections.yaml    # Connection configs (no secrets)
├── .env.example              # Example environment variables
├── .env                      # Local secrets (git ignored)
│
├── pipelines/                # OML pipeline definitions
│   ├── daily/
│   │   ├── customer_sync.oml
│   │   └── order_refresh.oml
│   ├── hourly/
│   │   └── metrics_update.oml
│   └── adhoc/
│       └── data_migration.oml
│
├── compiled/                 # Compiled manifests (git ignored)
│   └── ...
│
├── components/               # Custom components (versioned)
│   └── custom_transformer/
│       ├── spec.yaml
│       ├── driver.py
│       └── README.md
│
├── tests/                    # Pipeline tests
│   ├── unit/
│   └── integration/
│
├── scripts/                  # Utility scripts
│   ├── setup.sh             # Environment setup
│   └── validate.sh          # Pre-commit validation
│
├── logs/                     # Session logs (git ignored)
│   └── ...
│
├── output/                   # Pipeline outputs (git ignored)
│   └── ...
│
└── .osiris/                  # Osiris metadata
    ├── version              # Project version
    ├── schema.json          # Project schema
    └── hooks/               # Git hooks
        └── pre-commit       # Validation hook
```

### Project Initialization
```bash
# Create new Osiris project
osiris project init [--name my-project] [--template basic|advanced]

# This will:
# 1. Create directory structure
# 2. Generate osiris.yaml with defaults
# 3. Create osiris_connections.yaml template
# 4. Add .gitignore with Osiris patterns
# 5. Create .env.example with required variables
# 6. Generate README.md with setup instructions
# 7. Install Git hooks for validation
```

### Environment Reproduction
```bash
# Clone and setup Osiris project
git clone https://github.com/org/osiris-pipelines.git
cd osiris-pipelines

# Restore environment from Git
osiris project restore

# This will:
# 1. Verify Osiris version compatibility
# 2. Install custom components
# 3. Validate configuration files
# 4. Check for required environment variables
# 5. Run connection health checks
# 6. Report any missing dependencies
```

### Configuration Management

TODO: Define configuration precedence and management:

1. **osiris.yaml** (versioned)
   ```yaml
   version: "2.0"
   project:
     name: "data-pipeline"
     description: "Production data pipelines"
     owner: "data-team@company.com"

   defaults:
     llm_provider: "openai"
     execution_target: "local"
     log_level: "INFO"

   paths:
     pipelines: "./pipelines"
     components: "./components"
     compiled: "./compiled"
     logs: "./logs"

   validation:
     pre_commit: true
     strict_mode: true
   ```

2. **osiris_connections.yaml** (versioned, no secrets)
   ```yaml
   connections:
     mysql:
       primary:
         host: "${MYSQL_HOST:-db.example.com}"
         port: 3306
         database: "production"
         user: "${MYSQL_USER:-readonly}"
         # Password from environment: MYSQL_PASSWORD
         options:
           ssl: required
           timeout: 30
         default: true

     supabase:
       analytics:
         url: "${SUPABASE_URL}"
         # Key from environment: SUPABASE_KEY
         schema: "public"
   ```

3. **.env.example** (versioned template)
   ```bash
   # MySQL Connection
   MYSQL_HOST=db.example.com
   MYSQL_USER=readonly
   MYSQL_PASSWORD=  # Required: MySQL password

   # Supabase Connection
   SUPABASE_URL=    # Required: Supabase project URL
   SUPABASE_KEY=    # Required: Supabase service key

   # LLM Configuration
   OPENAI_API_KEY=  # Required for chat mode
   ```

4. **.env** (git ignored, local secrets)
   ```bash
   MYSQL_PASSWORD=actual-secret-password
   SUPABASE_KEY=actual-service-key
   OPENAI_API_KEY=sk-actual-api-key
   ```

### Git Integration Features

TODO: Implement Git-aware features:

1. **Version Compatibility**
   ```bash
   # Check project compatibility
   osiris project check

   # Output:
   # ✓ Osiris version 2.0.0 compatible
   # ✓ All required components available
   # ✓ Configuration schema valid
   # ⚠ Missing environment variable: MYSQL_PASSWORD
   ```

2. **Git Hooks**
   ```bash
   # Pre-commit hook (installed by init)
   #!/bin/bash
   # .osiris/hooks/pre-commit

   # Validate OML files
   osiris oml validate pipelines/**/*.oml

   # Check for secrets in code
   osiris security scan

   # Validate connections (dry run)
   osiris connections validate --dry-run
   ```

3. **Diff-Friendly Formats**
   - YAML with consistent ordering
   - Sorted keys in configurations
   - No auto-generated timestamps
   - Stable component ordering

4. **Branch-Aware Execution**
   ```bash
   # Use branch-specific configs
   osiris run pipeline.oml --branch feature/new-pipeline

   # Automatic environment switching
   # dev branch -> dev connections
   # main branch -> prod connections
   ```

### CI/CD Integration

TODO: Support for CI/CD pipelines:

```yaml
# .github/workflows/osiris.yml
name: Osiris Pipeline Validation

on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Setup Osiris
        run: |
          pip install osiris-pipeline
          osiris project restore

      - name: Validate Pipelines
        run: |
          osiris oml validate pipelines/**/*.oml

      - name: Test Connections
        run: |
          osiris connections doctor --dry-run

      - name: Run Tests
        run: |
          pytest tests/
```

## Consequences

### Positive
- **Standardization**: Consistent project structure across teams
- **Reproducibility**: Environments can be recreated from Git
- **Collaboration**: Teams can share pipelines effectively
- **Version Control**: Pipeline changes properly tracked
- **CI/CD Ready**: Standard structure enables automation
- **Security**: Clear separation of secrets from code

### Negative
- **Migration Effort**: Existing projects need restructuring
- **Learning Curve**: Teams need to learn new structure
- **Rigidity**: Standard structure may not fit all use cases
- **Complexity**: Additional tooling and commands

### Neutral
- **Tool Dependencies**: Requires Git for full functionality
- **Convention Enforcement**: Teams must follow conventions
- **Maintenance**: Project structure needs documentation

## Implementation Approach

TODO: Implementation phases:

### Phase 1: Project Structure
- Define canonical structure
- Create project templates
- Implement `osiris project init`
- Generate .gitignore patterns

### Phase 2: Environment Management
- Implement `osiris project restore`
- Version compatibility checking
- Component installation
- Dependency validation

### Phase 3: Git Integration
- Git hooks implementation
- Branch-aware configuration
- Diff-friendly formatting
- CI/CD templates

### Phase 4: Migration Tools
- Migration guide for existing projects
- Automated migration script
- Validation and testing
- Documentation

## Migration Strategy

TODO: Migration from existing projects:

```bash
# Analyze existing project
osiris project analyze ./old-project

# Generate migration plan
osiris project migrate --plan

# Execute migration
osiris project migrate --execute

# Validate migrated project
osiris project validate
```

## References
- Issue #XXX: Standardize project structure
- ADR-0020: Connection resolution (related)
- ADR-0029: Memory store (integration needed)
- Git best practices documentation
- 12-factor app methodology
