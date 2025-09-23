# ADR-0033: Pipeline Resilience and Retry Policies

## Status
Proposed

## Context
Data pipelines often face transient failures due to network issues, temporary resource constraints, or external service unavailability. Currently, Osiris lacks standardized retry mechanisms, timeout controls, and failure handling strategies. Modern orchestrators like Prefect and Dagster provide sophisticated retry policies that significantly improve pipeline reliability.

## Problem
- No built-in retry mechanism for transient failures
- Missing timeout controls for long-running operations
- No standardized failure handling or compensation logic
- Lack of idempotency guarantees for safe retries

## Constraints
- Retry policies must be deterministic and predictable
- Must not retry on permanent failures (e.g., syntax errors)
- Should support different strategies for different failure types
- Must maintain audit trail of retry attempts

## Decision
Add comprehensive resilience features to OML at the step level:

### 1. Retry Policies
```yaml
steps:
  - id: extract-data
    component: mysql.extractor
    retry:
      max_attempts: 3
      backoff: exponential  # none | linear | exponential
      initial_delay_ms: 1000
      max_delay_ms: 30000
      jitter: 0.1  # 10% randomization
      on_errors:
        - network_error
        - timeout
      skip_on_errors:
        - syntax_error
        - permission_denied
```

### 2. Timeout Controls
```yaml
steps:
  - id: long-query
    component: mysql.extractor
    timeout:
      step_ms: 300000  # 5 minutes for this step
      total_ms: 600000  # 10 minutes including retries
```

### 3. Idempotency Keys
```yaml
steps:
  - id: write-data
    component: supabase.writer
    idempotency:
      key: "${connection}:${table}:${params.batch_id}"
      cache_ttl_s: 3600  # Remember for 1 hour
```

### 4. Compensation (Saga Pattern)
```yaml
steps:
  - id: reserve-capacity
    component: resource.allocator
    compensate:
      component: resource.deallocator
      config:
        allocation_id: "${steps.reserve-capacity.outputs.allocation_id}"

  - id: process-data
    component: data.processor
    depends_on: [reserve-capacity]
    # If this fails, compensation will run
```

### 5. Circuit Breaker (Future)
```yaml
steps:
  - id: call-external-api
    component: http.caller
    circuit_breaker:
      failure_threshold: 5
      reset_timeout_s: 60
      half_open_requests: 2
```

## Error Classification
Errors are classified for appropriate retry behavior:
- **Transient**: Network timeouts, rate limits, temporary unavailability
- **Permanent**: Syntax errors, validation failures, permission denied
- **Unclear**: Generic errors (configurable retry behavior)

## Compilation and Runtime Behavior
### Compile Time
- Validate retry configuration consistency
- Check that compensation steps exist if referenced
- Generate deterministic retry schedule in manifest

### Runtime
- Execute step with timeout enforcement
- On failure, classify error and check retry policy
- Log retry attempts with exponential backoff
- If all retries exhausted, optionally run compensation
- Maintain retry state for idempotency

## Alternatives Considered
1. **Global retry policy only**: Single policy for entire pipeline (rejected: insufficient granularity)
2. **External retry management**: Delegate to orchestrator (rejected: reduces portability)
3. **Complex state machines**: Full saga orchestration (rejected: too complex for MVP)

## Consequences
### Positive
- Significantly improved reliability for production pipelines
- Granular control over failure handling
- Clear audit trail of retry attempts
- Safe compensation for partial failures

### Negative
- Increased execution complexity
- Potential for retry storms if misconfigured
- Compensation logic adds complexity

## Implementation Notes
### Retry Algorithm
```python
delay = initial_delay_ms
for attempt in range(max_attempts):
    try:
        return execute_step()
    except Exception as e:
        if not should_retry(e, policy):
            raise
        if attempt < max_attempts - 1:
            jittered_delay = delay * (1 + random(-jitter, jitter))
            sleep(min(jittered_delay, max_delay_ms))
            if backoff == 'exponential':
                delay *= 2
            elif backoff == 'linear':
                delay += initial_delay_ms
```

## Observability
Each retry attempt generates events:
- `step_retry_attempt`: attempt number, error, next_delay
- `step_retry_exhausted`: final failure after all attempts
- `compensation_triggered`: when compensation runs
- `circuit_breaker_open`: when circuit breaker trips

## Security Considerations
- Error messages in retry events must be sanitized
- Idempotency keys must not contain secrets
- Compensation must not leak sensitive data

## Status Tracking
- M1d: Basic retry with exponential backoff
- M2: Full retry policies with error classification
- M3: Compensation and idempotency
- M4: Circuit breakers
