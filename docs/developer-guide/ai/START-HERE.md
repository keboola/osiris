# AI Component Development - START HERE

## Purpose

Single entry point for AI-assisted component development in Osiris. This guide routes you to the right documents based on your specific task.

## How This Works

1. Identify your task below
2. Follow the recommended path
3. Load only the documents you need
4. Don't read everything - be selective

## Task Router

### Task 1: "Build a new component from scratch"

**Path to follow:**

1. **Choose your API type** → Read `decision-trees/api-type-selector.md`
   - REST API component
   - GraphQL API component
   - SQL database component

2. **Select authentication** → Read `decision-trees/auth-selector.md`
   - API keys, OAuth, Basic auth, etc.

3. **Handle pagination** (if API-based) → Read `decision-trees/pagination-selector.md`
   - Offset, cursor, page-based, link-header

4. **Use the recipe template** → Read `recipes/[chosen-type]-extractor.md`
   - Copy the complete working example
   - Adapt to your specific API

5. **Validate your work** → Read `checklists/COMPONENT_AI_CHECKLIST.md`
   - Run through all validation steps
   - Ensure nothing is missed

6. **Final build** → Read `build-new-component.md`
   - Complete implementation guide
   - All required files and structure

### Task 2: "Debug a failing component"

**Path to follow:**

1. **Identify the error** → Read `error-patterns.md`
   - Find your error pattern
   - Understand root cause

2. **Apply the fix** → Follow troubleshooting section in error-patterns.md
   - Step-by-step resolution
   - Common pitfalls

3. **Validate the fix** → Run component doctor
   ```bash
   osiris connections doctor <connection-name>
   ```

4. **Verify discovery** (if applicable) → Read `checklists/discovery_contract.md`
   - Ensure discovery mode works
   - Check all discovery requirements

### Task 3: "Understand component architecture"

**Path to follow (in order):**

1. **Schema reference** → Read `../../reference/components-spec.md`
   - Complete schema documentation
   - All required fields

2. **Core concepts** → Read `../human/CONCEPTS.md`
   - Fundamental principles
   - Design patterns

3. **Connection fields** → Read `../../reference/x-connection-fields.md`
   - Advanced authentication patterns
   - Dynamic field configuration

**You're done** - you now understand the architecture.

### Task 4: "Add capability to existing component"

**Path to follow:**

1. **Find the capability section** → Read `build-new-component.md`
   - Locate section for your capability
   - Understand requirements

2. **Check the contract** → Read appropriate checklist:
   - Discovery mode? → `checklists/discovery_contract.md`
   - Connection testing? → `checklists/connections_doctor_contract.md`
   - Validation? → `checklists/COMPONENT_AI_CHECKLIST.md`

3. **Update three layers:**
   - `spec.yaml` - Component specification
   - `driver.py` - Implementation logic
   - `tests/` - Test coverage

### Task 5: "Review/approve a component PR"

**Path to follow:**

1. **Run validation** → Read `checklists/COMPONENT_AI_CHECKLIST.md`
   - Verify all checklist items pass
   - Check test coverage

2. **Test manually** → Run connections doctor
   ```bash
   osiris connections doctor <connection-name>
   ```

3. **Verify contracts** → Check relevant checklists:
   - Discovery contract
   - Connection doctor contract

## Quick Reference by Question

| Question | Document to Read |
|----------|-----------------|
| "What auth type should I use?" | `decision-trees/auth-selector.md` |
| "How do I implement pagination?" | `decision-trees/pagination-selector.md` |
| "What API type is this?" | `decision-trees/api-type-selector.md` |
| "What fields are required in spec.yaml?" | `build-new-component.md` section 2 |
| "How do I test discovery mode?" | `checklists/discovery_contract.md` |
| "What's the x-connection-fields syntax?" | `../../reference/x-connection-fields.md` |
| "How do I debug connection errors?" | `error-patterns.md` |
| "What does component doctor check?" | `checklists/connections_doctor_contract.md` |
| "How do I structure driver code?" | `recipes/[api-type]-extractor.md` |
| "What's the complete spec schema?" | `../../reference/components-spec.md` |

## Document Index (Organized by Purpose)

### Decision Making (Start Here)
- `decision-trees/api-type-selector.md` - Choose REST/GraphQL/SQL
- `decision-trees/auth-selector.md` - Choose auth mechanism
- `decision-trees/pagination-selector.md` - Choose pagination strategy

### Working Examples (Copy These)
- `recipes/rest-api-extractor.md` - Complete REST API example
- `recipes/graphql-extractor.md` - Complete GraphQL example
- `recipes/sql-extractor.md` - Complete SQL database example

### Step-by-Step Guides
- `build-new-component.md` - Complete build guide (all steps)
- `error-patterns.md` - Common errors and fixes

### Validation (Check Your Work)
- `checklists/COMPONENT_AI_CHECKLIST.md` - Master validation checklist
- `checklists/discovery_contract.md` - Discovery mode requirements
- `checklists/connections_doctor_contract.md` - Doctor test requirements

### Reference (Look Up Details)
- `../../reference/components-spec.md` - Complete schema specification
- `../../reference/x-connection-fields.md` - Advanced auth patterns

### Human Context (Background Reading)
- `../human/CONCEPTS.md` - Core concepts and philosophy
- `../human/TESTING.md` - Testing approach

## Anti-Patterns: Don't Do This

❌ **Don't read all 25+ documents** - You'll waste time and get confused

❌ **Don't start without knowing your API type** - Different types need different approaches

❌ **Don't skip validation checklists** - They catch 80% of common errors

❌ **Don't copy-paste without understanding** - Understand why the pattern works

❌ **Don't hardcode secrets** - Always use connection fields and environment variables

❌ **Don't skip discovery mode** - It's required for Osiris chat to work

## Pro Tips

✅ **Start with decision trees** - They ask the right questions upfront

✅ **Use recipes as templates** - They're complete, tested examples

✅ **Validate early and often** - Run component doctor during development

✅ **Read only what you need** - Focus on your current task

✅ **Test with real credentials** - Never use fake test data

✅ **Follow the contracts** - Discovery and doctor contracts are non-negotiable

## Typical Workflow Example

**Scenario: Building a new Stripe API extractor**

1. Read `decision-trees/api-type-selector.md` → Determined it's REST API
2. Read `decision-trees/auth-selector.md` → Determined it's Bearer token
3. Read `decision-trees/pagination-selector.md` → Determined it's cursor-based
4. Read `recipes/rest-api-extractor.md` → Used as template
5. Built spec.yaml, driver.py, tests
6. Read `checklists/COMPONENT_AI_CHECKLIST.md` → Validated everything
7. Ran `osiris connections doctor stripe-test` → All checks passed
8. Done in ~45 minutes

## Document Maintenance

This START-HERE.md file is the canonical entry point. If you add new documents to the ai/ directory:

1. Add them to the appropriate section above
2. Add relevant Q&A to Quick Reference
3. Update task paths if they change workflows
4. Keep this file under 300 lines

## Getting Help

If you're stuck:

1. Check `error-patterns.md` for your specific error
2. Review the relevant recipe for a working example
3. Verify against the appropriate checklist
4. Test with `osiris connections doctor`

## Version Info

- Last updated: 2025-10-26
- Osiris version: v0.5.0
- Document count: 15+ files in ai/ directory
- Maintenance: Update paths when files move

---

**Ready to start?** Pick your task above and follow the path. Don't overthink it.
