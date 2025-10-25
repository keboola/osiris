# Component Documentation Index

Complete guide to Osiris component architecture, patterns, and creation.

## Quick Navigation

### For Different Audiences

**I want to create a new component**
1. Start: [Component Creation Guide](./component-creation-guide.md) (11KB, 7-step walkthrough)
2. Reference: [Quick Reference Checklist](./component-spec-quickref.md) (9KB, copy-paste templates)
3. Deep Dive: [Full Analysis](./component-specs-analysis.md) (26KB, detailed patterns)

**I want to understand component design**
1. Start: [Quick Reference](./component-spec-quickref.md) (9KB, key patterns)
2. Deep Dive: [Full Analysis](./component-specs-analysis.md) (26KB, all patterns)

**I want to review a component spec**
1. Reference: [Full Analysis](./component-specs-analysis.md) (sections 2-3)
2. Checklist: [Quick Reference](./component-spec-quickref.md) (Validation Checklist)

**I want to learn about security**
1. Start: [Full Analysis, Section 2](./component-specs-analysis.md) - 3-layer security model
2. Checklist: [Quick Reference](./component-spec-quickref.md) - Security Field Settings

## Document Overview

### 1. Component Creation Guide (11KB)
**File:** `component-creation-guide.md`

Complete step-by-step walkthrough for creating new components:
- Step 1: Choose component type & complexity
- Step 2: Create directory structure
- Step 3: Write spec.yaml (with all sections)
- Step 4: Implement driver class
- Step 5: Create tests
- Step 6: Validation checklist
- Step 7: Integration checklist

**Best for:** Teams implementing new components

**Key Sections:**
- Templates for Tier 1, 2, and 3 components
- Driver implementation patterns
- Pre-commit checklist
- Common issues and solutions

**Time to read:** 15-20 minutes

### 2. Quick Reference Checklist (9KB)
**File:** `component-spec-quickref.md`

Condensed reference guide with checklists and templates:
- Required/recommended fields
- Naming conventions
- Security field settings
- Authentication patterns (3 types)
- Constraints patterns
- LLM hints template
- Capabilities flags
- Complexity tiers
- Common mistakes

**Best for:** Quick lookup while creating components

**Key Sections:**
- Copy-paste templates for all component patterns
- Security field settings table
- Complexity tier comparison
- Common mistakes with fixes

**Time to read:** 5-10 minutes (lookup-focused)

### 3. Full Analysis Report (26KB)
**File:** `component-specs-analysis.md`

Comprehensive analysis of 7 production components with detailed patterns:
- Architecture overview
- Required vs optional spec fields
- Three exemplar components (Tier 1, 2, 3)
- Common patterns and conventions
- Anti-patterns to avoid
- Template structure for new specs
- Complexity checklist
- Key takeaways

**Best for:** Deep understanding of component system

**Key Sections:**
- Section 1: Component structure overview
- Section 2: Required vs optional fields (detailed)
- Section 3: Three exemplars with full specs (Tier 1, 2, 3)
- Section 4: Common patterns and conventions (40+ patterns documented)
- Section 5: Anti-patterns (8 detailed examples)
- Section 6: Template structure (copy-paste ready)
- Section 7: Complexity checklist
- Section 8: Key takeaways

**Time to read:** 45-60 minutes for full understanding

## Components Analyzed

### Tier 1: Simple (Complexity 1/5)
- **filesystem.csv_writer** - File-based CSV output
  - 0 secrets
  - 9 configuration fields
  - 1 mode (write)
  - 1 constraint
  - 2 examples
  - No authentication

### Tier 2: Medium (Complexity 3/5)
- **mysql.extractor** - SQL database extraction
  - 1 auth method
  - 17 configuration fields
  - 2 modes (extract, discover)
  - 1 constraint
  - 2 examples
  
- **mysql.writer** - SQL database writing
  - 1 auth method
  - 15 configuration fields
  - 1 mode (write)
  - 1 constraint
  - 2 examples
  
- **supabase.extractor** - REST API extraction via Supabase
  - 1 auth method
  - 15 configuration fields
  - 2 modes (extract, discover)
  - 1 constraint
  - 2 examples

### Tier 3: Complex (Complexity 5/5)
- **graphql.extractor** - Generic GraphQL API extraction
  - 4 auth methods (bearer, basic, api_key, none)
  - 28 configuration fields
  - 1 mode (extract)
  - 4 constraints
  - 4 real-world examples (GitHub, Shopify, Hasura, custom)
  - Pagination support
  - JSONPath extraction
  
- **supabase.writer** - REST API writing via Supabase
  - 1 auth method
  - 18 configuration fields
  - 1 mode (write)
  - 2 constraints
  - 2 examples
  - Upsert with composite keys

- **duckdb.processor** - In-memory SQL transformation
  - 0 secrets
  - 1 configuration field
  - 1 mode (transform)
  - 0 constraints
  - 2 examples
  - Custom SQL support

## Key Patterns Documented

### Component Structure (7 patterns)
- Namespace.type naming
- Modes (extract, write, discover, transform)
- Capabilities flags (8 always present)
- Configuration schema (JSON Schema format)
- Driver implementation pattern
- x-runtime configuration
- Compatibility declaration

### Security Model (8+ patterns)
- Secret declaration (secrets + x-secret arrays)
- Connection field override policies (allowed/forbidden/warning)
- Redaction strategy (masking)
- Sensitive path tracking
- Credential masking for logging
- Password validation
- Secret isolation

### Validation (6+ patterns)
- Either-or fields (table XOR query)
- Conditional requirements (when/must/error)
- Multi-condition validation
- Field constraints (min/max, enum, pattern)
- additionalProperties: false
- Error message formatting

### LLM Integration (4+ patterns)
- Input aliases for natural language mapping
- Prompt guidance paragraphs
- YAML snippet generation
- Common pattern naming
- Multiple auth method documentation
- Conditional constraint explanation

### Examples (3 tiers)
- Simple tier: 1-2 examples
- Medium tier: 2 examples
- Complex tier: 3-4 real-world examples

## Standards & Conventions

### Naming
```
Component: {namespace}.{type}
- namespace: mysql, supabase, graphql, duckdb, filesystem, etc.
- type: extractor, writer, processor, connection, action, etc.

Fields: snake_case
- Connections: host, port, user, password, database, schema
- Auth: auth_type, auth_token, auth_username, auth_header_name
- Modes: mode (MySQL) or write_mode (Supabase) for disambiguation
- Pagination: pagination_enabled, pagination_path, pagination_cursor_field
```

### Security Levels
```
Level 1: Critical (forbidden override)
- password, api_key, auth_token, service_key

Level 2: Sensitive (forbidden override)
- user, username, auth_username

Level 3: Metadata (allowed override)
- host, port, url, project_id, schema

Level 4: Mixed (warning override)
- headers, environment variables
```

### Default Values
```
- Ports: 3306 (MySQL), 5432 (PostgreSQL)
- Batch sizes: 1000 (writers), 10000 (extractors)
- Timeouts: 30 seconds
- Retries: 3 attempts
- Booleans: false for dangerous operations
```

### Limits
```
- maxRows: 1-100M (depends on type)
- maxSizeMB: 1-10GB (API: 1GB, DB: 10GB)
- maxDurationSeconds: 60-3600 (API: 1800, DB: 3600)
- maxConcurrency: 3-5 (API limited, DB unlimited)
```

## Statistics

| Metric | Value |
|--------|-------|
| Components Analyzed | 7 |
| Avg Config Fields | 12 |
| Avg Examples | 2.4 |
| Avg Constraints | 1.4 |
| Patterns Documented | 50+ |
| Security Patterns | 8+ |
| Anti-patterns | 8 |
| Required Fields | 8 |
| Highly Recommended Fields | 10 |
| Total Lines of Analysis | 1373 |
| Total Lines of Documentation | 500+ |

## How to Use This Documentation

### Scenario 1: Creating New Component
```
1. Read: Component Creation Guide (step by step)
2. Choose: Appropriate tier (Tier 1, 2, or 3)
3. Copy: Template from Quick Reference
4. Reference: Full Analysis for detailed patterns
5. Validate: Using checklists
```

### Scenario 2: Code Review
```
1. Check: Against Quick Reference validation checklist
2. Compare: Against exemplar in Full Analysis
3. Verify: All required fields present
4. Validate: Security patterns followed
5. Test: Against test template
```

### Scenario 3: Understanding Patterns
```
1. Read: Quick Reference section 4-6
2. Reference: Full Analysis sections 4-5
3. Compare: Against exemplar specs in /components/
4. Study: Driver patterns in /osiris/drivers/
5. Run: Tests in /tests/
```

### Scenario 4: LLM Integration
```
1. Understand: llmHints section in Full Analysis
2. Review: inputAliases patterns
3. Study: promptGuidance examples
4. Check: yamlSnippets generation
5. Test: LLM config generation with spec
```

## Related Documentation

- **Component Specs:** `/docs/reference/components-spec.md` (existing reference)
- **CLI Architecture:** `/docs/architecture/` (command implementation)
- **MCP Server:** `/docs/mcp/` (Model Context Protocol integration)
- **Testing:** `/docs/testing/` (test patterns)

## Version History

- **v1.0** (Oct 25, 2025) - Initial comprehensive analysis
  - 7 components analyzed
  - 50+ patterns documented
  - 3 exemplar tiers identified
  - 8 anti-patterns identified
  - 3 documentation files created

## Contributing

When creating new components:
1. Follow patterns from appropriate exemplar tier
2. Use templates from Quick Reference
3. Reference Full Analysis for detailed patterns
4. Validate using provided checklists
5. Update this index if new patterns emerge

---

**Last Updated:** October 25, 2025
**Status:** Production Ready
**Maintenance:** Keep synchronized with component changes

---

## Quick Links

- [Component Creation Guide](./component-creation-guide.md) - Step-by-step walkthrough
- [Quick Reference Checklist](./component-spec-quickref.md) - Copy-paste templates
- [Full Analysis Report](./component-specs-analysis.md) - Detailed patterns and analysis

**Total Documentation:** 56 KB across 3 documents  
**Reading Time:** 5 minutes (quickref) to 2+ hours (full study)
