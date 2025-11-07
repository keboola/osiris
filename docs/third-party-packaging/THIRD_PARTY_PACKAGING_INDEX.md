# Third-Party Component Packaging - Document Index

## Overview

This directory contains a complete proposal and implementation guide for **Osiris Component Packages (OCPs)** - a mechanism for distributing third-party components independently of core Osiris while maintaining seamless integration.

**Status**: Proposal (November 2025)
**Version**: 1.0.0
**Scope**: Package format, distribution, security, and developer experience

---

## Documents at a Glance

| Document | Length | Audience | Purpose |
|----------|--------|----------|---------|
| **QUICK_REFERENCE.md** | 400 lines | All | 5-minute overview, quick answers |
| **SUMMARY.md** | 500 lines | Leads | Executive summary, key decisions |
| **IMPLEMENTATION_GUIDE.md** | 400 lines | Developers | Step-by-step implementation |
| **PACKAGING_STRATEGY.md** | 1500 lines | Architects | Complete strategy, rationale |
| **PACKAGING_SPEC.md** | 900 lines | Implementers | Technical specification |
| **EXAMPLES.md** | 500 lines | All | Runnable working code |

**Total**: ~3800 lines of documentation + code examples

---

## Reading Paths

### Path 1: "Just Make It Work" (30 minutes)
**For**: Developers who want to create a component NOW

1. Start: **QUICK_REFERENCE.md**
   - TL;DR section (5 min)
   - 5-Minute Setup (10 min)
   - Driver Interface (5 min)
   - Spec.yaml Essentials (5 min)

2. Reference: **EXAMPLES.md** (Example 1)
   - Copy Shopify Extractor as template
   - Modify for your data source

3. Action: Create, test, publish (20 min setup, then 1-2 hours building)

### Path 2: "Understand the Design" (2 hours)
**For**: Architects, technical leads, decision makers

1. Start: **SUMMARY.md**
   - Overview (10 min)
   - Current State Analysis (10 min)
   - Key Design Decisions (10 min)

2. Deep Dive: **PACKAGING_STRATEGY.md**
   - Sections 1-5 (60 min)
   - Implementation Roadmap (10 min)

3. Reference: **PACKAGING_SPEC.md** (Section 1-2)
   - Package Format (10 min)
   - Entry Point Discovery (10 min)

### Path 3: "Implementation Details" (4 hours)
**For**: Core team implementing OCP support

1. Start: **PACKAGING_SPEC.md** (Complete)
   - Read all 8 sections (90 min)
   - Study validation rules (20 min)
   - Review CI/CD template (20 min)

2. Reference: **PACKAGING_STRATEGY.md** (Sections 8-11)
   - Security model (15 min)
   - Testing strategy (15 min)
   - Migration path (20 min)

3. Implement: **IMPLEMENTATION_GUIDE.md** (Steps 1-9)
   - Create test component (60 min)
   - Run tests (20 min)

4. Study: **EXAMPLES.md** (All examples)
   - Understand patterns (30 min)

### Path 4: "Complete Understanding" (6+ hours)
**For**: Everyone who needs to deeply understand OCPs

Read documents in this order:
1. QUICK_REFERENCE.md (30 min)
2. SUMMARY.md (30 min)
3. PACKAGING_STRATEGY.md (90 min)
4. PACKAGING_SPEC.md (60 min)
5. IMPLEMENTATION_GUIDE.md (60 min)
6. EXAMPLES.md (90 min)

---

## Document Details

### 1. THIRD_PARTY_PACKAGING_QUICK_REFERENCE.md

**Length**: ~400 lines
**Time to Read**: 10-15 minutes
**Audience**: Everyone

**What It Contains**:
- TL;DR (2 paragraphs)
- 5-minute setup script
- File checklist
- Entry point format
- Driver interface
- Spec.yaml essentials
- Installation variants
- Testing template
- Build & publish commands
- Release checklist
- Common errors & fixes
- Role reference
- Config schema examples
- Minimal example (30 lines)

**Best For**:
- Quick reference while coding
- Getting unstuck
- Looking up format/syntax
- Copy-paste templates

**Skip**: If you have more than 30 minutes

---

### 2. THIRD_PARTY_PACKAGING_SUMMARY.md

**Length**: ~500 lines
**Time to Read**: 20-30 minutes
**Audience**: Technical leads, decision makers

**What It Contains**:
- Executive overview
- Document guide (what each contains)
- Current architecture analysis (built-in components)
- Issues addressed
- Key design decisions (4 pillars)
- Implementation phases (4-phase roadmap)
- Distribution flow (diagram)
- Minimal component reference (size, time)
- Testing strategy overview
- Distribution recommendations
- Migration strategy for built-in components
- Security considerations
- Comparison table (alternatives)
- Next steps (immediate to long-term)
- Key files in codebase
- Questions & discussion points
- Glossary
- Resource index

**Best For**:
- Understanding "why" we're doing this
- Executive briefing
- Architecture review
- Decision making
- Planning roadmap

**Read This If**: You're deciding whether to implement OCPs

---

### 3. THIRD_PARTY_COMPONENT_IMPLEMENTATION_GUIDE.md

**Length**: ~400 lines
**Time to Read**: 30 minutes (+ 1-2 hours building)
**Audience**: Component developers

**What It Contains**:
- 5-minute quick start
- Detailed steps 1-10:
  1. Create package structure
  2. Create pyproject.toml
  3. Create spec.yaml
  4. Create package __init__.py
  5. Create driver implementation
  6. Create tests
  7. Create documentation
  8. Setup testing environment
  9. Build and test locally
  10. Publish to PyPI
- Common issues & solutions
- E2B testing guide
- Release checklist
- Help resources

**Best For**:
- Following step-by-step
- Getting unstuck during development
- Understanding each file's purpose
- Debugging issues

**Read This When**: Creating your first component

---

### 4. THIRD_PARTY_COMPONENT_PACKAGING_STRATEGY.md

**Length**: ~1500 lines
**Time to Read**: 60-90 minutes
**Audience**: Architects, implementers, maintainers

**What It Contains** (11 Sections):
1. Executive Summary
2. Current State Analysis (detailed)
   - Monolithic structure
   - Registry flow
   - Key file locations
   - Current constraints
3. Proposed Strategy (OCP Model)
   - Package structure
   - Component specification format
   - Entry points
   - Runtime discovery
   - Security model
4. Package Structure (detailed examples)
   - Directory layout
   - Minimal files
5. Component Specification
   - Format with inline examples
   - Extended fields
6. Python Entry Points
   - Registration mechanism
7. Runtime Discovery
   - Algorithm
   - Component loading flow
8. Security Considerations
   - Configuration-based controls
   - Verification strategy
9. Dependency Management
   - Specification requirements
   - Installation variants
   - Conflict detection
10. Testing & Validation
    - Component validation rules
    - Test template
11. Implementation Roadmap
    - Phase 1-4 breakdown
    - Timeline (8 weeks total)
    - File modifications needed

Plus:
- Distribution checklist
- Backwards compatibility approach
- Comparison with alternatives
- References and appendices

**Best For**:
- Understanding complete strategy
- Implementing OCP support in core
- Reviewing architectural decisions
- Planning implementation
- Security review

**Read This When**: Implementing Phase 1 of roadmap

---

### 5. THIRD_PARTY_COMPONENT_PACKAGING_SPEC.md

**Length**: ~900 lines
**Time to Read**: 45-60 minutes
**Audience**: Implementers, QA, package maintainers

**What It Contains** (8 Sections):
1. Package Format
   - PyPI distribution
   - Tarball distribution
   - Entry point requirements
   - Specification requirements
2. Entry Point Discovery
   - Discovery mechanism
   - Conflict resolution
3. Security Model
   - Plugin configuration
   - CLI overrides
   - Verification strategy
   - Signature verification (optional)
4. Dependency Management
   - Specification requirements
   - Installation variants
   - Dependency resolution rules
   - Conflict detection code
5. Testing & Validation
   - Validation rules (12 rules)
   - Test template (complete)
   - CI/CD pipeline (GitHub Actions)
6. Distribution Checklist
   - Pre-publishing checklist (36 items)
7. Compatibility Matrix
   - Version support table
   - Platform support
   - Python version support
8. References & Appendices
   - Migration guide
   - Example package manifest

**Best For**:
- Exact specifications
- Package validation
- CI/CD setup
- Distribution process
- Compatibility matrices

**Read This When**: Creating/validating components for distribution

---

### 6. THIRD_PARTY_COMPONENT_EXAMPLES.md

**Length**: ~500 lines
**Time to Read**: 30-45 minutes (or reference while coding)
**Audience**: All developers

**What It Contains**:
- **Example 1: Shopify Extractor**
  - Full pyproject.toml
  - Complete spec.yaml with all sections
  - Complete driver.py with 4 extraction methods
  - Complete test file with 6 test cases
  - 60 lines of runnable code

- **Example 2: PostgreSQL Writer**
  - Spec.yaml (write modes)
  - Driver implementation
  - 3 write modes (append, replace, upsert)
  - Transactional logic

- **Example 3: DuckDB Transformer**
  - Spec.yaml (transform mode)
  - Driver with SQL execution
  - In-memory processing

- **Example 4: Complete Pipeline**
  - OML pipeline using all 3 components
  - Execution commands
  - Integration example

- **Testing & Troubleshooting**
  - E2B integration test
  - Local sandbox testing
  - Test script template

**Best For**:
- Copy-paste templates
- Understanding patterns
- Quick reference examples
- Testing ideas
- Integration examples

**Read This When**: Building your first component

---

## Cross-References

### By Topic

**Package Structure & Format**:
- QUICK_REFERENCE.md → "Minimal Example"
- PACKAGING_STRATEGY.md → Section 1
- PACKAGING_SPEC.md → Section 1
- EXAMPLES.md → All examples

**Entry Points & Discovery**:
- PACKAGING_STRATEGY.md → Section 8
- PACKAGING_SPEC.md → Section 2
- QUICK_REFERENCE.md → "Entry Point Format"

**Driver Implementation**:
- QUICK_REFERENCE.md → "Driver Interface"
- IMPLEMENTATION_GUIDE.md → Steps 5-6
- PACKAGING_SPEC.md → Section 1.4
- EXAMPLES.md → All examples

**Specification (spec.yaml)**:
- PACKAGING_STRATEGY.md → Section 2
- PACKAGING_SPEC.md → Section 1.3
- QUICK_REFERENCE.md → "Spec.yaml Essentials"
- EXAMPLES.md → All examples

**Testing & Validation**:
- IMPLEMENTATION_GUIDE.md → Steps 6-8
- PACKAGING_SPEC.md → Section 5
- PACKAGING_STRATEGY.md → Section 10
- EXAMPLES.md → Test templates

**Security**:
- PACKAGING_STRATEGY.md → Section 9
- PACKAGING_SPEC.md → Section 3
- SUMMARY.md → Security considerations

**Distribution & Publishing**:
- QUICK_REFERENCE.md → "Build & Publish"
- IMPLEMENTATION_GUIDE.md → Step 10
- PACKAGING_SPEC.md → Section 6
- SUMMARY.md → Distribution flow

---

## Key Concepts

### Osiris Component Package (OCP)
A standalone Python package that provides one or more Osiris components via Python entry points.

**Structure**:
```
src/family_osiris/
├── __init__.py (has load_spec() function)
├── spec.yaml (component metadata)
└── driver.py (implementation)
```

### Entry Point
Python's standard plugin registration mechanism using `pyproject.toml`:
```toml
[project.entry-points."osiris.components"]
"family.role" = "package_name:load_spec"
```

### Component Specification (spec.yaml)
Declarative metadata defining component capabilities, configuration schema, requirements, and LLM hints.

### Driver
Python class with `run()` method that executes component logic in the pipeline.

### Security Configuration
`plugins` section in `.osiris/config.yaml` controlling which components can run.

---

## Implementation Checklist

### Before Reading:
- [ ] Understand current built-in component structure
- [ ] Review ADR-0024 (Component Packaging)
- [ ] Understand entry points concept

### While Reading:
- [ ] Take notes on key decisions
- [ ] Identify questions/concerns
- [ ] Sketch implementation plan

### After Reading:
- [ ] Create proof-of-concept component
- [ ] Run through IMPLEMENTATION_GUIDE.md
- [ ] Test entry point discovery
- [ ] Plan Phase 1 implementation
- [ ] Share with team for review

---

## Common Questions

**Q: Which document should I read?**
A: See "Reading Paths" above. Choose based on your role and time.

**Q: Can I skip some documents?**
A: Yes. QUICK_REFERENCE + EXAMPLES is enough to build a component. But read STRATEGY for understanding.

**Q: What if I'm implementing OCP support in core?**
A: Read SUMMARY → STRATEGY → SPEC in that order.

**Q: What if I just want to create a component?**
A: QUICK_REFERENCE + EXAMPLES + IMPLEMENTATION_GUIDE.

**Q: Are these documents complete?**
A: Yes. They cover design, implementation, examples, and distribution. No additional research needed.

**Q: What's the status?**
A: Proposal (v1.0.0). Ready for team review and implementation.

---

## File Locations in Osiris Codebase

**Current Implementation** (to understand):
- `/Users/padak/github/osiris/osiris/components/registry.py` - Component discovery
- `/Users/padak/github/osiris/osiris/core/driver.py` - Driver registry
- `/Users/padak/github/osiris/components/spec.schema.json` - Specification schema
- `/Users/padak/github/osiris/pyproject.toml` - Build configuration

**Examples of Built-in Components**:
- `/Users/padak/github/osiris/components/mysql.extractor/spec.yaml`
- `/Users/padak/github/osiris/components/supabase.writer/spec.yaml`
- `/Users/padak/github/osiris/osiris/drivers/mysql_extractor_driver.py`
- `/Users/padak/github/osiris/osiris/drivers/supabase_writer_driver.py`

---

## Next Steps

### Immediate (This Week)
1. Choose reading path above (10-30 min)
2. Share SUMMARY.md with team
3. Discuss key design decisions

### Short-term (Next Week)
1. Review feedback from team
2. Create proof-of-concept component
3. Plan Phase 1 implementation

### Medium-term (Weeks 3-4)
1. Implement Phase 1 (entry point discovery)
2. Publish implementation guide
3. Solicit community feedback

### Long-term (Weeks 5+)
1. Create scaffolder CLI tool
2. Ship reference implementation
3. Build component ecosystem

---

## Document Metadata

| Document | Version | Date | Status |
|----------|---------|------|--------|
| QUICK_REFERENCE.md | 1.0.0 | Nov 2025 | Final |
| SUMMARY.md | 1.0.0 | Nov 2025 | Final |
| IMPLEMENTATION_GUIDE.md | 1.0.0 | Nov 2025 | Final |
| PACKAGING_STRATEGY.md | 1.0.0 | Nov 2025 | Final |
| PACKAGING_SPEC.md | 1.0.0 | Nov 2025 | Final |
| EXAMPLES.md | 1.0.0 | Nov 2025 | Final |

**Package Overall**:
- Total Words: ~18,000
- Total Lines: ~3,800
- Code Examples: 15+
- Diagrams: 3
- Tables: 8+

---

## Feedback & Questions

After reviewing these documents, consider:

1. **Design Questions**:
   - Do we need signature verification?
   - Should allowlist be required or optional?
   - E2B sandboxing: optional or default?

2. **Implementation Questions**:
   - Who implements Phase 1?
   - Timeline realistic?
   - Resource allocation?

3. **Community Questions**:
   - How do we encourage adoption?
   - What's the first reference component?
   - Component discovery/registry approach?

---

## How to Use This Package

1. **Share SUMMARY.md** with decision makers
2. **Share QUICK_REFERENCE.md** with developers
3. **Keep IMPLEMENTATION_GUIDE.md** handy during development
4. **Reference EXAMPLES.md** for copy-paste templates
5. **Consult PACKAGING_SPEC.md** for exact requirements
6. **Return to PACKAGING_STRATEGY.md** for design rationale

---

## License & Attribution

These documents are part of the Osiris project.
- **Project**: https://github.com/keboola/osiris
- **License**: Apache-2.0
- **Created**: November 2025

---

**Start Here**: Pick a reading path above and dive in!

Questions? Check QUICK_REFERENCE.md for answers, or refer to the full document indicated in "Cross-References" section.
