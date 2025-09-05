
# ADR 0018: Agent‑Call Adapter (Proposed)

## Status
Proposed

## Context
Some steps may need to call external LLMs/agents (MCP tools, A2A flows, third‑party services). We need a **safe, auditable adapter** so that agent calls can be modeled as components without polluting the compiler with non‑determinism. The adapter must enforce budgets and redact sensitive context.

## Decision
Introduce a standard component driver `agent.call` with strict contracts and logging.

### Contract
- Inputs: 
  - `provider` (enum: `openai|anthropic|vertex|http`…)
  - `model` (string)
  - `tools` (optional, declarative)
  - `prompt_template` (string or reference)
  - `context_refs` (array of pointers to prior artifacts/memory entries)
  - `budget` (tokens/ms cap), `timeout_ms`
- Outputs:
  - `artifacts`: response text, optional structured data
  - `metrics`: token usage, latency, tool calls

### Guardrails
- Redaction of secrets and user PII prior to emission.
- Deterministic inputs at runtime (no randomness unless explicitly allowed).
- Compiler stays LLM‑free; this driver is used **by the runner only**.

### Logging
- Events: `agent_call_start`, `agent_call_complete`, `agent_call_error`
- Attach token/duration metrics and redaction summaries.
- Store prompts/responses in memory store with redaction.

## Consequences
- Clean separation: compiler deterministic; runner may use LLM calls as normal components.
- Unified observability of agent usage.

## References
- ADR‑0014, ADR‑0015
- ADR‑0017 (Memory Store)
