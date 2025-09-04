# ADR-0013: Chat Retry Policy for Post-Generation Validation

## Status

Accepted (Implemented in M1b.3)

## Context

As part of M1b.3 (Post-Generation Validation), we need to validate LLM-generated OML pipelines against the Component Registry specifications. When validation fails, we want to give the LLM a chance to correct its mistakes rather than failing immediately.

Key considerations:
- LLMs can make simple mistakes (wrong field names, incorrect types) that are easily fixable
- Retrying with validation errors as feedback often produces correct results
- Unlimited retries could lead to infinite loops and excessive token consumption
- Users need visibility into what's happening during retries
- We must maintain deterministic behavior for testing and debugging

## Decision

We will implement a bounded retry mechanism for post-generation validation with the following characteristics:

### Configuration

Introduce a new configuration key hierarchy:
```yaml
validation:
  retry:
    max_attempts: 2  # default value, range: 0-5
```

With standard precedence: CLI > ENV > YAML > defaults
- CLI flag: `--retry-attempts N`
- Environment: `OSIRIS_VALIDATE_RETRY_ATTEMPTS`
- YAML: `validation.retry.max_attempts`

### Retry Trigger

A retry is triggered when:
- The LLM generates OML that fails validation against component specs
- This includes: schema violations, invalid field names, type mismatches, constraint failures
- The current attempt count is less than `max_attempts`

### Retry Prompt Strategy

When retrying, we will:
1. Include the friendly validation errors from M1a.4's FriendlyErrorMapper
2. Add a concise delta instruction: "Please fix only these validation errors: [errors]. Keep all other fields unchanged."
3. Include the previously generated (invalid) OML as context
4. Maintain the same conversation context and component information

### Backoff Policy

For CLI usage:
- No backoff delay (immediate retry)
- LLM adapters may implement their own rate limiting if needed

### Determinism and Logging

Each retry attempt will:
1. Be logged as a distinct session event with:
   - `event_type`: `validation_retry`
   - `attempt_index`: Current attempt number (1-based)
   - `validation_errors`: Structured error data
   - `token_usage`: Tokens consumed in retry
   - `duration_ms`: Time taken for retry
2. Include the validation errors in a structured format
3. Track cumulative token usage across all attempts
4. Maintain a clear audit trail for debugging

### Security Constraints

- **NEVER** echo secrets or sensitive values into retry prompts
- Validation errors must use the same redaction policy as other logs
- Failed OML is not saved to artifacts unless explicitly requested

### User Experience

- Setting `max_attempts` to 0 enables "strict mode" (no retries)
- Default of 2 attempts balances user experience with token costs
- Users see a progress indicator during retries
- Final success/failure is clearly communicated

### HITL Reset Extension

When HITL escalation occurs:
- User is shown the retry history with a concise summary of attempts
- User can provide corrections or additional context
- After user input, the retry counter resets for a fresh validation cycle
- This allows iterative refinement with human guidance

## Consequences

### Positive

- **Higher success rate**: Simple mistakes get corrected automatically
- **Better UX**: Users don't have to retry manually for fixable errors  
- **Clear audit trail**: Every attempt is logged for debugging
- **Bounded costs**: Maximum token usage is predictable
- **Configurable**: Users can adjust retry behavior to their needs

### Negative

- **Increased token consumption**: Each retry consumes additional tokens
- **Potential latency**: Multiple attempts take more time
- **Complexity**: Retry logic adds code complexity to the chat flow

### Neutral

- **Learning opportunity**: Retry patterns could inform prompt improvements
- **Metrics collection**: Retry rates provide insight into LLM performance

## References

- [M1b Milestone: Context Builder and Validation](../milestones/m1b-context-builder-and-validation.md)
- [M1a.4: Friendly Error Mapper](../milestones/m1a-component-registry.md)
- [ADR-0007: Component Specification and Capabilities](./0007-component-specification-and-capabilities.md)
