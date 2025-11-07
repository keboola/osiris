---
name: codex
description: Invoke OpenAI Codex CLI for second opinions, multi-model analysis, architectural validation, or structured JSON output. Use when you need external AI perspective from OpenAI models to validate your decisions or get comparative analysis.
---

# Codex Second Opinion Skill

This skill enables you to leverage OpenAI Codex CLI as a second opinion source for code analysis, architectural validation, and technical reviews.

## When to Use This Skill

Invoke this skill when you need to:
- **Get second opinion** on architectural decisions or implementation approaches
- **Multi-model validation** - compare OpenAI vs Anthropic perspectives
- **Code review** from different AI model for better coverage
- **Structured JSON output** with schemas for predictable parsing
- **Complex analysis** that benefits from consensus of multiple AI models

**Do NOT use for**:
- Simple tasks that don't need validation
- Time-sensitive operations where single perspective is sufficient
- Tasks already completed and validated

## How This Skill Works

When invoked, use `codex exec` via Bash tool with these patterns:

### Pattern 1: Simple Question-Answer
```bash
codex exec --output-last-message /tmp/claude/codex-answer.txt "Your question"
cat /tmp/claude/codex-answer.txt
```

### Pattern 2: Structured Analysis (Recommended)
```bash
# Create schema
cat > /tmp/claude/schema.json << 'EOF'
{
  "type": "object",
  "properties": {
    "summary": { "type": "string" },
    "strengths": { "type": "array", "items": { "type": "string" } },
    "weaknesses": { "type": "array", "items": { "type": "string" } },
    "recommendations": { "type": "array", "items": { "type": "string" } }
  },
  "required": ["summary", "strengths", "weaknesses"]
}
EOF

# Execute with schema
codex exec --output-schema /tmp/claude/schema.json \
  --output-last-message /tmp/claude/result.json \
  "Analyze [topic]. Provide structured assessment."

# Read result
cat /tmp/claude/result.json
```

### Pattern 3: Comparative Analysis
```bash
# Get Codex perspective
codex exec --output-last-message /tmp/claude/codex-view.txt \
  "Review this approach: [your plan]. List pros, cons, alternatives."

# Present both perspectives
cat /tmp/claude/codex-view.txt
```

## Common Use Cases

### 1. Architecture Review
```bash
cat > /tmp/claude/arch-schema.json << 'EOF'
{
  "type": "object",
  "properties": {
    "assessment": { "type": "string" },
    "risks": { "type": "array", "items": { "type": "string" } },
    "alternatives": { "type": "array", "items": { "type": "string" } },
    "risk_level": { "type": "string", "enum": ["low", "medium", "high"] }
  }
}
EOF

codex exec --output-schema /tmp/claude/arch-schema.json \
  --output-last-message /tmp/claude/arch-review.json \
  "Review MCP CLI bridge pattern. Assess security, performance, maintainability."

cat /tmp/claude/arch-review.json
```

### 2. Security Review
```bash
codex exec -m gpt-5-codex --output-last-message /tmp/claude/security.txt \
  "Security review of osiris/mcp/server.py:
   - Input validation
   - Secret handling
   - Filesystem access
   Provide specific vulnerabilities and fixes."

cat /tmp/claude/security.txt
```

### 3. Code Review
```bash
codex exec --output-last-message /tmp/claude/review.txt \
  "Review osiris/mcp/tools/discovery.py focusing on:
   1. Security vulnerabilities
   2. Performance issues
   3. Code maintainability
   Provide line-level recommendations."

cat /tmp/claude/review.txt
```

### 4. Validate ADR
```bash
codex exec --output-last-message /tmp/claude/adr-review.txt \
  "Review this ADR for completeness and issues: [ADR content or file reference]"

cat /tmp/claude/adr-review.txt
```

## Key Parameters

- **Model selection**: `-m gpt-5-codex` (for complex tasks) or `-m o4-mini` (faster)
- **Working directory**: `-C /path/to/analyze` (defaults to current)
- **Sandbox mode**: `--sandbox read-only` (default, safe)
- **Output**: `--output-last-message /tmp/claude/file.txt` (cleanest for text)

## Best Practices

1. **Always use `/tmp/claude/` for outputs** - respects filesystem contract
2. **Prefer JSON schemas** for structured, parseable responses
3. **Be specific in prompts** - mention file paths, exact concerns, context
4. **Compare perspectives** - present both Codex and your analysis
5. **Use for validation** - Codex complements, doesn't replace your work
6. **Check authentication** - ensure `codex --version` works before use

## Output Interpretation

When presenting Codex results to user:
1. **Label clearly** - "Codex perspective" or "Second opinion from OpenAI"
2. **Compare** with your own analysis
3. **Synthesize** insights from both models
4. **Highlight** agreement and disagreement
5. **Recommend** based on multi-model consensus

## Error Handling

Always verify Codex is available:
```bash
if ! command -v codex &> /dev/null; then
    echo "Codex CLI not found. User needs to install Codex."
    exit 1
fi
```

If authentication fails, inform user to run:
```bash
codex login  # ChatGPT login
# OR
printenv OPENAI_API_KEY | codex login --with-api-key
```

## Limitations

- Codex uses OpenAI models (GPT-5, O4), not Claude
- Requires internet connection
- Different context limits than Claude
- May have different coding style/perspective

## Quick Reference

```bash
# Simple question
codex exec --output-last-message /tmp/claude/out.txt "analyze X"

# Structured output
codex exec --output-schema schema.json -o /tmp/claude/result.json "analyze X"

# Different model
codex exec -m gpt-5-codex --output-last-message /tmp/claude/out.txt "complex task"

# With image
codex exec -i screenshot.png --output-last-message /tmp/claude/out.txt "explain this"
```

---

See `reference.md` for comprehensive Codex CLI documentation and advanced usage patterns.