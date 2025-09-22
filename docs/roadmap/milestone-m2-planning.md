# Milestone M2: Scheduling & Planning Enhancements

## Goals

TODO: Define high-level goals for M2:

1. **Enable Production Scheduling**: Add scheduling capabilities to OML for automated pipeline execution
2. **Enhance Pipeline Metadata**: Include ownership, testing, and lineage information
3. **Improve Operational Visibility**: Add monitoring and alerting hooks
4. **Support Orchestrator Integration**: Enable integration with Airflow, Prefect, Dagster
5. **Validate Production Readiness**: Comprehensive validation before deployment

## Deliverables

### D1: OML Schedule Block

TODO: Implement scheduling configuration in OML:

```yaml
# Enhanced OML with schedule block
oml_version: "0.2.0"  # Version bump for new features
name: "daily_customer_sync"

schedule:
  type: "cron"
  expression: "0 2 * * *"  # Daily at 2 AM
  timezone: "UTC"
  retry:
    attempts: 3
    delay: 300  # seconds
    backoff: "exponential"
  timeout: 3600  # 1 hour max runtime
  concurrency: 1  # Max parallel runs
  catchup: false  # Don't backfill missed runs

  # Windowing for incremental loads
  window:
    type: "sliding"
    size: "24h"
    offset: "-1h"  # Look back 1 hour
    field: "updated_at"  # Field to window on

steps:
  - id: "extract_customers"
    component: "mysql.extractor"
    mode: "read"
    config:
      connection: "@mysql.primary"
      # Use window variables in query
      query: |
        SELECT * FROM customers
        WHERE updated_at >= '${window.start}'
          AND updated_at < '${window.end}'
```

### D2: Pipeline Metadata

TODO: Add comprehensive metadata to pipelines:

```yaml
metadata:
  owner: "data-team@company.com"
  team: "data-platform"
  sla: "4h"  # Expected completion time
  criticality: "high"  # low, medium, high, critical

  description: |
    Daily synchronization of customer data from production MySQL
    to analytics warehouse. Critical for daily reporting.

  tags:
    - "customer"
    - "daily"
    - "production"

  # Data quality tests
  tests:
    - type: "row_count"
      min: 100
      max: 10000
    - type: "schema"
      expected: "v2.1"
    - type: "freshness"
      max_age: "25h"
    - type: "custom"
      script: "tests/validate_customers.py"

  # Lineage tracking
  lineage:
    upstream:
      - "pipeline: order_processing"
      - "table: mysql.orders"
    downstream:
      - "dashboard: customer_analytics"
      - "pipeline: marketing_segments"

  # Notifications
  notifications:
    on_failure:
      - email: "oncall@company.com"
      - slack: "#data-alerts"
    on_success:
      - email: "data-team@company.com"
    on_sla_breach:
      - pagerduty: "data-platform"
```

### D3: CLI Schedule Validation

TODO: Implement schedule validation commands:

```bash
# Validate schedule configuration
osiris schedule validate pipeline.oml

# Output:
# ✓ Valid cron expression: "0 2 * * *"
# ✓ Next 5 runs:
#   - 2024-01-16 02:00:00 UTC
#   - 2024-01-17 02:00:00 UTC
#   - 2024-01-18 02:00:00 UTC
#   - 2024-01-19 02:00:00 UTC
#   - 2024-01-20 02:00:00 UTC
# ✓ Window calculation valid
# ✓ No schedule conflicts detected

# Preview window calculations
osiris schedule preview pipeline.oml --date "2024-01-15"

# Output:
# Window for 2024-01-15:
#   Start: 2024-01-14 01:00:00
#   End:   2024-01-15 01:00:00
#   Query will process: ~1,234 rows (estimated)

# Test schedule locally
osiris schedule test pipeline.oml --dry-run

# Export to orchestrator format
osiris schedule export pipeline.oml --format airflow > dag.py
osiris schedule export pipeline.oml --format prefect > flow.py
```

### D4: Orchestrator Integration

TODO: Build integration adapters:

#### Airflow Integration
```python
# Generated Airflow DAG
from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'data-team@company.com',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email': ['oncall@company.com'],
    'email_on_failure': True,
    'retries': 3,
    'retry_delay': timedelta(seconds=300),
}

dag = DAG(
    'daily_customer_sync',
    default_args=default_args,
    description='Daily customer data synchronization',
    schedule_interval='0 2 * * *',
    catchup=False,
    tags=['customer', 'daily', 'production'],
)

run_pipeline = BashOperator(
    task_id='run_osiris_pipeline',
    bash_command='osiris run /pipelines/daily_customer_sync.oml',
    dag=dag,
)
```

#### Prefect Integration
```python
# TODO: Prefect flow generation
from prefect import flow, task
from prefect.schedules import CronSchedule

@flow(
    name="daily_customer_sync",
    schedule=CronSchedule(cron="0 2 * * *"),
)
def customer_sync_flow():
    # Implementation
    pass
```

### D5: Production Validation

TODO: Comprehensive validation suite:

```python
# osiris/scheduling/validator.py
class ScheduleValidator:
    """Validate pipeline schedules for production"""

    def validate(self, pipeline: OML) -> ValidationResult:
        result = ValidationResult()

        # Schedule validation
        result.add(self.validate_cron(pipeline.schedule))
        result.add(self.validate_window(pipeline.schedule))
        result.add(self.validate_timeout(pipeline.schedule))

        # Metadata validation
        result.add(self.validate_owner(pipeline.metadata))
        result.add(self.validate_tests(pipeline.metadata))
        result.add(self.validate_lineage(pipeline.metadata))

        # Conflict detection
        result.add(self.detect_conflicts(pipeline))

        # Resource validation
        result.add(self.validate_resources(pipeline))

        return result
```

## Success Criteria

TODO: Define measurable success criteria:

1. **Schedule Support**
   - [ ] Cron expressions parsed and validated
   - [ ] Window calculations correct for all timezones
   - [ ] Retry logic implemented with backoff
   - [ ] Concurrent run limiting works

2. **Metadata Completeness**
   - [ ] All production pipelines have owners
   - [ ] SLA tracking implemented
   - [ ] Lineage visualization available
   - [ ] Test framework integrated

3. **Orchestrator Integration**
   - [ ] Airflow DAG generation works
   - [ ] Prefect flow generation works
   - [ ] At least one orchestrator fully integrated
   - [ ] Round-trip preservation (OML → DAG → OML)

4. **Validation Coverage**
   - [ ] 100% of schedule configs validated
   - [ ] Conflict detection prevents overlaps
   - [ ] Resource limits enforced
   - [ ] Test suite passes

5. **Performance Requirements**
   - [ ] Schedule validation < 100ms
   - [ ] DAG generation < 1 second
   - [ ] No performance regression in pipeline execution

## Timeline

TODO: Implementation sequence:

### Phase 1: Schedule Block
- Design schedule schema
- Implement cron parsing
- Add window calculations
- Build retry logic

### Phase 2: Metadata Enhancement
- Design metadata schema
- Implement ownership tracking
- Add test framework
- Build lineage tracking

### Phase 3: Orchestrator Integration
- Airflow adapter
- Prefect adapter
- Export/import commands
- Round-trip testing

### Phase 4: Validation & Testing
- Schedule validator
- Conflict detection
- Integration tests
- Documentation

### Phase 5: Production Hardening
- Performance optimization
- Error handling
- Monitoring integration
- Release preparation

## Dependencies

TODO: External dependencies:

- ADR-0028: Git integration (for versioned schedules)
- ADR-0029: Memory store (for schedule history)
- Orchestrator APIs (Airflow, Prefect)
- Notification services (Slack, PagerDuty)

## Risks

TODO: Risk assessment:

| Risk | Impact | Probability | Mitigation |
|------|--------|------------|------------|
| Schedule format incompatibility | High | Medium | Support multiple formats |
| Orchestrator API changes | Medium | Low | Version pinning |
| Window calculation errors | High | Medium | Extensive testing |
| Performance degradation | Medium | Low | Benchmark suite |
| Adoption resistance | Medium | Medium | Migration tools |

## Open Questions

TODO: Questions to resolve:

1. Should we support multiple schedule formats (cron, natural language, interval)?
2. How to handle timezone changes and DST?
3. Should schedules be in OML or separate files?
4. How to manage secrets in orchestrator integration?
5. What level of orchestrator feature parity is required?

## References

- Airflow documentation
- Prefect documentation
- Cron expression standards
- Data pipeline best practices
