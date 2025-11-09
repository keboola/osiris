# Osiris Component Developer Skill

This Claude skill enables development of Osiris components in isolated projects, completely separate from the main Osiris repository.

## What This Skill Does

Guides developers through creating production-ready Osiris ETL components:
- Extractors (pull data from APIs, databases)
- Writers (push data to destinations)
- Processors (transform data)

## When Claude Uses This Skill

Claude automatically loads this skill when you:
- Ask to create an Osiris component
- Mention building an extractor, writer, or processor
- Request help with discovery or doctor capabilities
- Need to package a component for distribution
- Want to validate against the 60-rule checklist

## Files in This Skill

- **SKILL.md** - Main instructions with workflow and quick-start guide
- **CHECKLIST.md** - 60 validation rules all components must pass
- **POSTHOG_EXAMPLE.md** - Complete working example (PostHog extractor)
- **TEMPLATES.md** - Code templates for common patterns
- **README.md** - This file

## Usage Example

In your separate project (e.g., PostHog connector):

```
You: "Help me create a PostHog extractor for Osiris that can extract events and persons"

Claude: [Loads osiris-component-developer skill]
        I'll help you create a production-ready PostHog extractor. Let me guide you through...

        [Creates project structure, spec.yaml, driver.py, tests, etc.]
```

## Key Features

- ✅ Complete component architecture knowledge
- ✅ 60-rule validation checklist
- ✅ E2B cloud compatibility guidance
- ✅ Driver Context API contract (logging, input parity)
- ✅ Security best practices
- ✅ Working code examples
- ✅ Testing strategies
- ✅ Packaging instructions

## Progressive Disclosure

The skill uses Claude's progressive disclosure:
- **Level 1**: Metadata always loaded (minimal tokens)
- **Level 2**: SKILL.md loaded when triggered (~150 lines)
- **Level 3**: Additional files loaded as needed
  - CHECKLIST.md when validating
  - POSTHOG_EXAMPLE.md when needing examples
  - TEMPLATES.md when needing specific patterns

## For Third-Party Developers

This skill is specifically designed for developers building Osiris components outside the main repository. You can:

1. Develop in your own project
2. Use your own git repository
3. Package as Python wheel or tarball
4. Distribute via PyPI or directly
5. Install in Osiris via `pip install`

## Compatibility

- **Osiris Version**: >=0.5.4
- **Python**: >=3.11
- **E2B Cloud**: Fully compatible
- **Platforms**: Works on Claude API, Claude.ai, Claude Code

## References

- Osiris Main Repo: https://github.com/keboola/osiris
- Component Docs: `docs/developer-guide/COMPONENT-DOCS-MASTER-INDEX.md`
- JSON Schema: https://json-schema.org/draft/2020-12/
- E2B Sandbox: https://e2b.dev/docs