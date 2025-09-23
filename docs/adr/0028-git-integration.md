# ADR-0028: Git Integration & Autopilot Mode

## Status
Proposed

## Context

Currently, Osiris projects lack a standard structure for version control and team collaboration. Users struggle with:
- No canonical way to organize Osiris projects in Git repositories
- Difficulty sharing pipeline configurations across teams
- Inconsistent secret management across environments
- No standard for reproducing environments from Git
- Manual setup required for each team member
- Complex Git workflows intimidating non-technical users

The problem impacts:
- **Team Collaboration**: Each developer has different local setup
- **CI/CD Integration**: No standard structure for automation
- **Reproducibility**: Cannot reliably recreate environments
- **Onboarding**: New team members need extensive setup help
- **Versioning**: Pipeline changes not properly tracked
- **User Experience**: Git concepts (branches, PRs) confuse data analysts

Organizations need:
- Standardized project layout for Osiris pipelines
- Git-friendly configuration management
- **Reproducible environments**: Clone Osiris + user's Git repo + secrets = identical environment restored
- Clear separation of code, config, and secrets
- Integration with existing Git workflows
- **Simple interface hiding Git complexity from end-users**

## Decision

Define a canonical Git repository structure for Osiris projects with clear conventions for organizing pipelines, configurations, connections, and components. Provide **Autopilot Mode** that abstracts Git complexity behind simple `osiris git save/publish/undo/history` commands, while maintaining full Git compatibility for advanced users.

### Repository Model

Osiris uses a **two-repository model**:

1. **Osiris Repository** (`github.com/keboola/osiris`)
   - Framework code, drivers, core functionality
   - Read-only for users
   - Users install via pip/docker

2. **Project Repository** (user's Git repo)
   - Pipelines, configurations, build outputs
   - User-owned and controlled
   - Contains all project-specific assets

### Canonical Project Structure

```
my-osiris-project/                    # User's project repo
├── .gitignore                       # Osiris-specific ignores
├── .gitattributes                   # LFS patterns for large files
├── README.md                        # Project documentation
├── osiris.yaml                      # Main configuration (versioned)
├── osiris_connections.example.yaml  # Example connections (versioned)
├── osiris_connections.yaml          # Actual connections (git ignored)
├── .env.example                     # Example environment variables
├── .env                             # Local secrets (git ignored)
│
├── pipelines/                       # OML pipeline definitions
│   ├── daily/
│   │   ├── customer_sync.oml
│   │   └── order_refresh.oml
│   ├── hourly/
│   │   └── metrics_update.oml
│   └── adhoc/
│       └── data_migration.oml
│
├── components/                      # Custom components (versioned)
│   └── custom_transformer/
│       ├── spec.yaml
│       ├── driver.py
│       └── README.md
│
├── build/                           # Deterministic build outputs (versioned)
│   ├── manifest.json               # Compiled manifest
│   └── ir/                         # Intermediate representations
│       └── pipeline_abc123.json
│
├── plan/                           # Execution plans (versioned)
│   ├── plan.json                  # Machine-readable plan
│   └── plan.md                    # Human-readable plan
│
├── reports/                        # Summary reports (versioned)
│   ├── summary.json               # Machine-readable summary
│   └── summary.md                 # Human-readable summary
│
├── artifacts/                      # Large artifacts metadata
│   └── index.json                 # Manifest with URLs + checksums
│
├── tests/                          # Pipeline tests with fixtures
│   ├── unit/
│   │   └── test_transform.py
│   └── fixtures/                  # Small test data (< 1MB)
│       └── sample.csv
│
├── docs/                           # Documentation (versioned)
│   ├── adr/                       # Architecture decisions
│   └── milestones/                # Project milestones
│
├── logs/                          # Runtime logs (git ignored)
├── cache/                         # Caches (git ignored)
├── tmp/                           # Temporary files (git ignored)
├── output/                        # Pipeline outputs (git ignored)
└── data/                          # Raw data (git ignored)
```

### Autopilot Mode

Autopilot Mode provides a simple interface for non-technical users, hiding Git complexity behind intuitive commands:

#### User Commands (Simple Interface)
```bash
# Save work locally (git add + commit)
osiris git save [--message "Updated customer pipeline"]

# Publish to team (git push / create PR)
osiris git publish

# View history (git log)
osiris git history [--limit 10]

# Undo last change (git revert)
osiris git undo [--last]
```

#### Autopilot Strategies

**1. Solo Mode** (direct to trunk)
```yaml
# osiris.yaml
git:
  autopilot:
    mode: solo
    auto_tag: true           # Creates ap-YYYYMMDD.N tags
    ci_validation: true      # Run CI before push
    rollback: revert         # Rollback via git revert
```

Workflow:
- `osiris git save` → git commit to main
- `osiris git publish` → git push (with auto-tag)
- `osiris git undo` → git revert HEAD

**2. Team-Safe Mode** (shadow branches + auto-PR)
```yaml
# osiris.yaml
git:
  autopilot:
    mode: team_safe
    shadow_branch: osiris/ap/{timestamp}-{slug}
    draft_pr: true
    auto_merge: true         # Merge when CI green
    rollback: revert_merge   # Rollback merge commits
```

Workflow:
- `osiris git save` → commit to shadow branch
- `osiris git publish` → create/update PR, auto-merge on green
- `osiris git undo` → revert merge commit

#### Example User Journey
```bash
# Data analyst updates pipeline
$ osiris git save "Fixed customer data extraction"
✓ Changes saved locally (3 files modified)

$ osiris git publish
✓ Publishing changes...
✓ Running validation... passed
✓ Creating pull request #42
✓ Running CI checks... passed
✓ Auto-merging... done
✓ Published successfully!

$ osiris git history
┌────────────────────────────────────────────────┐
│ Recent Changes                                 │
├────────────────────────────────────────────────┤
│ • Fixed customer data extraction (2 hours ago) │
│ • Updated order pipeline (yesterday)           │
│ • Added new metrics (3 days ago)              │
└────────────────────────────────────────────────┘

$ osiris git undo
⚠ This will undo: "Fixed customer data extraction"
Continue? [y/N]: y
✓ Change reverted successfully
```

### Configuration Management

#### Configuration Precedence
```
CLI flags > Environment variables ($OSIRIS_*) > osiris.yaml > built-in defaults
```

#### Complete osiris.yaml Example
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
  build: "./build"
  reports: "./reports"

# Git Autopilot Configuration
git:
  autopilot:
    mode: team_safe              # solo | team_safe
    shadow_branch: "osiris/ap/{timestamp}-{slug}"
    auto_tag: true
    tag_format: "ap-{date}.{sequence}"

  commit:
    conventional: true            # Use conventional commits
    sign: true                   # GPG sign commits

  pr:
    required_checks:             # CI checks before merge
      - "osiris/validate"
      - "osiris/test"
      - "security/scan"
    auto_merge: true             # Auto-merge when green
    reviewers:                   # Auto-assign reviewers
      - "@data-team"
    use_codeowners: true         # Respect CODEOWNERS file

# CI/CD Configuration
ci:
  provider: github_actions       # github_actions | gitlab_ci | jenkins

  semver:
    enabled: true
    rules:
      - pattern: "feat:"         # feat: → minor version
        bump: minor
      - pattern: "fix:"          # fix: → patch version
        bump: patch
      - pattern: "BREAKING"      # BREAKING → major version
        bump: major

  publish:
    queue:
      max_inflight: 3            # Max parallel publishes
      promotion:                 # Environment promotion
        - dev
        - staging
        - prod

  release:
    artifacts:                   # Attach to releases
      - "build/manifest.json"
      - "reports/summary.md"
      - "artifacts/index.json"

  backport:
    enabled: true
    target_branches:
      - "release/*"
      - "hotfix/*"

# AIOP Configuration (if enabled)
aiop:
  enabled: true
  policy: core
```

### Files in Git

#### Files to Commit
```gitignore
# Osiris Project - COMMIT these files

# Pipeline definitions
pipelines/**/*.oml

# Custom components
components/**

# Configuration
osiris.yaml
osiris_connections.example.yaml

# Tests with small fixtures (< 1MB)
tests/**

# Documentation
docs/**
README.md

# Deterministic build artifacts
build/manifest.json
build/ir/**

# Plans (machine and human readable)
plan/plan.json
plan/plan.md

# Reports (summaries only)
reports/summary.json
reports/summary.md

# Artifact index (metadata only, not data)
artifacts/index.json
```

#### Files NOT to Commit (.gitignore)
```gitignore
# Osiris Project - IGNORE these files

# Secrets and credentials
.env
osiris_connections.yaml
**/credentials.json
**/*.key
**/*.pem

# Runtime artifacts
logs/
cache/
tmp/
.osiris_cache/
.osiris_sessions/

# Large data files
data/
output/
*.csv
*.parquet
*.avro

# Compiled/derived files
compiled/
*.pyc
__pycache__/

# IDE
.vscode/
.idea/
*.swp
```

#### Git LFS Configuration (.gitattributes)
```gitattributes
# Large file patterns for Git LFS
*.pkl filter=lfs diff=lfs merge=lfs -text
*.model filter=lfs diff=lfs merge=lfs -text
*.tar.gz filter=lfs diff=lfs merge=lfs -text
docs/images/*.png filter=lfs diff=lfs merge=lfs -text
```

### Environment Reproduction

```bash
# Clone and setup Osiris project
git clone https://github.com/org/data-pipelines.git
cd data-pipelines

# Restore environment from Git
osiris project restore

# This will:
# 1. Verify Osiris version compatibility
# 2. Install custom components
# 3. Validate configuration files
# 4. Check for required environment variables
# 5. Run connection health checks
# 6. Report any missing dependencies

# Output:
# ✓ Osiris version 2.0.0 compatible
# ✓ Custom components installed (3)
# ✓ Configuration validated
# ⚠ Missing environment variable: MYSQL_PASSWORD
# ✓ Connections validated (dry run)
#
# To complete setup:
#   1. Copy .env.example to .env
#   2. Fill in missing secrets
#   3. Run: osiris connections doctor
```

### Team Collaboration Features

#### Conflict Resolution
```bash
# Team-safe mode handles conflicts automatically
$ osiris git publish
⚠ Conflicts detected with main branch
→ Starting merge wizard...

Select resolution strategy:
1. Keep your changes (theirs will be in history)
2. Keep team changes (yours will be saved)
3. Manual merge (opens editor)
Choice [1-3]: 1

✓ Conflicts resolved
✓ Publishing changes...
```

#### Audit Trail
Every Autopilot action is logged with:
- User identity (from git config)
- Timestamp (UTC)
- Action type (save/publish/undo)
- Files affected
- Commit SHA
- PR number (if applicable)

```bash
$ osiris audit --last 10
┌─────────────────────────────────────────────────────┐
│ Action  │ User    │ Time     │ Changes │ Reference │
├─────────────────────────────────────────────────────┤
│ publish │ alice   │ 2h ago   │ 3 files │ PR #42    │
│ save    │ alice   │ 3h ago   │ 3 files │ abc123    │
│ undo    │ bob     │ 1d ago   │ 2 files │ def456    │
└─────────────────────────────────────────────────────┘
```

## Consequences

### Positive
- **Simplicity**: Non-technical users never see Git complexity
- **Standardization**: Consistent project structure across teams
- **Reproducibility**: Environments can be recreated from Git
- **Collaboration**: Teams can share pipelines effectively
- **Version Control**: All changes properly tracked with audit trail
- **CI/CD Ready**: Standard structure enables automation
- **Security**: Clear separation of secrets from code
- **Rollback**: Easy undo for any published change

### Negative
- **Migration Effort**: Existing projects need restructuring
- **Learning Curve**: Teams need to learn Autopilot commands
- **Rigidity**: Standard structure may not fit all edge cases
- **Complexity**: Additional abstraction layer over Git
- **Storage**: Build artifacts increase repo size (mitigated by Git LFS)

### Neutral
- **Tool Dependencies**: Requires Git for full functionality
- **Convention Enforcement**: Teams must follow conventions
- **Maintenance**: Autopilot logic needs ongoing maintenance
- **Compatibility**: Must maintain compatibility with existing Git workflows

## Alternatives Considered

1. **Direct Git Usage**: Require users to learn Git
   - ❌ Too complex for data analysts
   - ❌ Error-prone for non-technical users

2. **Database Storage**: Store everything in database
   - ❌ No version control benefits
   - ❌ Cannot integrate with CI/CD

3. **Custom VCS**: Build proprietary version control
   - ❌ Massive engineering effort
   - ❌ No ecosystem integration

4. **Single Repository**: Osiris + projects in same repo
   - ❌ Couples framework to user code
   - ❌ Permission management issues

## Risks and Mitigations

### Risk: Merge Conflicts
**Mitigation**:
- Guided conflict resolution wizard in team_safe mode
- Automatic conflict detection before publish
- Clear rollback path via undo command

### Risk: Repository Bloat
**Mitigation**:
- Large artifacts stored externally (S3/GCS)
- Git LFS for binary files
- artifacts/index.json contains only metadata
- Regular cleanup commands provided

### Risk: Secret Exposure
**Mitigation**:
- Pre-commit hooks scan for secrets
- .gitignore prevents credential commits
- osiris_connections.yaml excluded by default
- CI validates no secrets in PR

### Risk: Autopilot Mistakes
**Mitigation**:
- All actions reversible via undo
- Dry-run mode for testing
- Comprehensive audit logging
- Manual override always available

## Implementation Approach

### Phase 1: Core Structure
- Define canonical project layout
- Implement `osiris project init`
- Create .gitignore templates
- Basic `osiris git save/publish` commands

### Phase 2: Autopilot Solo Mode
- Implement solo strategy
- Auto-tagging system
- Basic `osiris git undo` functionality
- Audit logging

### Phase 3: Team-Safe Mode
- Shadow branch management
- PR automation
- Auto-merge on CI green
- Conflict resolution wizard

### Phase 4: Advanced Features
- CODEOWNERS integration
- Semver automation
- Release artifacts
- Backport policies

## Migration Strategy

```bash
# Analyze existing project
osiris project analyze ./old-project

# Generate migration plan
osiris project migrate --plan

# Review migration plan
cat migration-plan.md

# Execute migration (dry-run)
osiris project migrate --dry-run

# Execute migration (real)
osiris project migrate --execute

# Validate migrated project
osiris project validate
```

## References
- Issue #XXX: Standardize project structure
- ADR-0020: Connection resolution (related)
- ADR-0027: AIOP integration
- ADR-0029: Memory store (integration needed)
- Git best practices documentation
- Conventional Commits specification
- 12-factor app methodology
