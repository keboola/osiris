# Milestone M3: Technical Scale & Performance

## Goals

TODO: Define high-level goals for M3:

1. **Enable Streaming Processing**: Implement RowStream interface for large-scale data
2. **Add DAG Parallel Execution**: Execute independent pipeline steps in parallel
3. **Integrate Observability**: Connect with Datadog, Prometheus, OpenTelemetry
4. **Optimize Resource Usage**: Reduce memory footprint and improve performance
5. **Support Distributed Execution**: Enable multi-node pipeline execution

## Deliverables

### D1: Streaming IO Implementation

TODO: Implement RowStream interface from ADR-0022:

```python
# RowStream interface for scalable processing
class RowStream(Protocol):
    """Streaming interface for large datasets"""

    def read_batch(self, size: int = 1000) -> Iterator[pd.DataFrame]:
        """Read data in batches"""
        pass

    def write_batch(self, batch: pd.DataFrame) -> None:
        """Write data batch"""
        pass

    def estimate_size(self) -> int:
        """Estimate total rows"""
        pass

    def checkpoint(self) -> str:
        """Create resumable checkpoint"""
        pass

    def resume(self, checkpoint: str) -> None:
        """Resume from checkpoint"""
        pass
```

#### Streaming Drivers
```python
# MySQL Streaming Extractor
class MySQLStreamingExtractor(Driver):
    def run(self, step_id: str, config: dict, inputs: dict, ctx) -> dict:
        """Stream data from MySQL"""

        connection = create_connection(config["connection"])
        query = config["query"]
        batch_size = config.get("batch_size", 10000)

        stream = MySQLRowStream(connection, query, batch_size)

        # Return stream instead of DataFrame
        return {"stream": stream, "type": "streaming"}

# CSV Streaming Writer
class CSVStreamingWriter(Driver):
    def run(self, step_id: str, config: dict, inputs: dict, ctx) -> dict:
        """Stream data to CSV"""

        stream = inputs.get("stream")
        if not stream:
            # Fallback to DataFrame mode
            return self.run_batch(step_id, config, inputs, ctx)

        output_path = config["path"]
        total_rows = 0

        with open(output_path, 'w') as f:
            writer = None
            for batch in stream.read_batch():
                if writer is None:
                    writer = csv.DictWriter(f, batch.columns)
                    writer.writeheader()

                batch.to_csv(f, header=False, index=False)
                total_rows += len(batch)

                # Emit progress metrics
                ctx.log_metric("rows_written", total_rows)
                ctx.log_event("progress", {
                    "rows": total_rows,
                    "memory_mb": get_memory_usage()
                })

        return {"rows_written": total_rows}
```

#### Spill-to-Disk for Large Datasets
```python
# Automatic spilling when memory threshold exceeded
class SpillManager:
    """Manage memory with disk spilling"""

    def __init__(self, memory_limit_mb: int = 1000):
        self.memory_limit = memory_limit_mb * 1024 * 1024
        self.spill_dir = tempfile.mkdtemp(prefix="osiris_spill_")
        self.spilled_chunks = []

    def process_stream(self, stream: RowStream) -> Iterator[pd.DataFrame]:
        """Process stream with automatic spilling"""

        memory_used = 0
        buffer = []

        for batch in stream.read_batch():
            batch_size = batch.memory_usage().sum()

            if memory_used + batch_size > self.memory_limit:
                # Spill to disk
                self.spill_buffer(buffer)
                buffer = []
                memory_used = 0

            buffer.append(batch)
            memory_used += batch_size

        # Yield from memory and disk
        yield from buffer
        yield from self.read_spilled()
```

### D2: DAG Parallel Execution

TODO: Implement parallel step execution:

```yaml
# Pipeline with parallel branches
oml_version: "0.2.0"
name: "parallel_processing"

steps:
  # Step 1: Extract source data
  - id: "extract_source"
    component: "mysql.extractor"
    mode: "read"
    config:
      connection: "@mysql.primary"
      query: "SELECT * FROM events"

  # Parallel branch 1: Aggregate by user
  - id: "aggregate_users"
    component: "transform.aggregator"
    mode: "transform"
    depends_on: ["extract_source"]  # Explicit dependency
    config:
      group_by: ["user_id"]
      aggregations:
        event_count: "count"

  # Parallel branch 2: Aggregate by product
  - id: "aggregate_products"
    component: "transform.aggregator"
    mode: "transform"
    depends_on: ["extract_source"]  # Can run parallel with aggregate_users
    config:
      group_by: ["product_id"]
      aggregations:
        revenue: "sum"

  # Join parallel results
  - id: "join_aggregates"
    component: "transform.joiner"
    mode: "transform"
    depends_on: ["aggregate_users", "aggregate_products"]
    config:
      join_type: "inner"
      on: ["date"]
```

#### DAG Executor
```python
# Parallel DAG executor
class DAGExecutor:
    """Execute pipeline steps in parallel"""

    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.futures = {}
        self.results = {}

    def execute(self, manifest: dict, context: ExecutionContext):
        """Execute pipeline with parallelism"""

        # Build dependency graph
        dag = self.build_dag(manifest["steps"])

        # Topological sort for execution order
        execution_order = self.topological_sort(dag)

        # Execute in waves
        for wave in execution_order:
            # Submit parallel tasks
            wave_futures = []
            for step_id in wave:
                future = self.executor.submit(
                    self.execute_step,
                    step_id,
                    manifest,
                    context
                )
                self.futures[step_id] = future
                wave_futures.append(future)

            # Wait for wave completion
            for future in as_completed(wave_futures):
                step_id = self.get_step_id(future)
                self.results[step_id] = future.result()

    def build_dag(self, steps: List[dict]) -> DAG:
        """Build directed acyclic graph from steps"""
        # TODO: Implementation
        pass

    def topological_sort(self, dag: DAG) -> List[List[str]]:
        """Sort DAG into executable waves"""
        # TODO: Implementation
        pass
```

### D3: Observability Integration

TODO: Integrate monitoring and metrics:

#### Datadog Integration
```python
# Datadog metrics publisher
from datadog import initialize, statsd

class DatadogPublisher:
    """Publish metrics to Datadog"""

    def __init__(self, api_key: str, app_key: str):
        initialize(api_key=api_key, app_key=app_key)
        self.statsd = statsd

    def publish_metric(self, metric: dict):
        """Publish metric to Datadog"""

        name = f"osiris.{metric['name']}"
        value = metric['value']
        tags = [f"{k}:{v}" for k, v in metric.get('tags', {}).items()]

        if metric['type'] == 'counter':
            self.statsd.increment(name, value, tags=tags)
        elif metric['type'] == 'gauge':
            self.statsd.gauge(name, value, tags=tags)
        elif metric['type'] == 'histogram':
            self.statsd.histogram(name, value, tags=tags)

    def publish_event(self, event: dict):
        """Publish event to Datadog"""
        self.statsd.event(
            title=event['title'],
            text=event['text'],
            tags=event.get('tags', []),
            alert_type=event.get('alert_type', 'info')
        )
```

#### OpenTelemetry Integration
```python
# OpenTelemetry tracing
from opentelemetry import trace
from opentelemetry.exporter.otlp import OTLPSpanExporter

class OTLPTracer:
    """OpenTelemetry tracing for pipelines"""

    def __init__(self, endpoint: str):
        self.tracer = trace.get_tracer("osiris.pipeline")
        self.exporter = OTLPSpanExporter(endpoint=endpoint)

    @contextmanager
    def trace_step(self, step_id: str, attributes: dict):
        """Trace pipeline step execution"""
        with self.tracer.start_as_current_span(
            f"step.{step_id}",
            attributes=attributes
        ) as span:
            try:
                yield span
                span.set_status(trace.Status(trace.StatusCode.OK))
            except Exception as e:
                span.set_status(
                    trace.Status(trace.StatusCode.ERROR, str(e))
                )
                span.record_exception(e)
                raise

    @contextmanager
    def trace_pipeline(self, pipeline_name: str):
        """Trace entire pipeline execution"""
        with self.tracer.start_as_current_span(
            f"pipeline.{pipeline_name}",
            kind=trace.SpanKind.SERVER
        ) as span:
            yield span
```

#### Metrics Configuration
```yaml
# osiris.yaml with observability config
observability:
  metrics:
    - type: "datadog"
      config:
        api_key: "${DD_API_KEY}"
        app_key: "${DD_APP_KEY}"
        tags:
          environment: "production"
          team: "data-platform"

    - type: "prometheus"
      config:
        push_gateway: "http://prometheus:9091"
        job_name: "osiris_pipelines"

  tracing:
    type: "opentelemetry"
    config:
      endpoint: "http://otel-collector:4317"
      service_name: "osiris"
      sample_rate: 0.1

  logging:
    type: "structured"
    config:
      format: "json"
      include_trace_id: true
      ship_to: "elasticsearch"
```

### D4: Performance Optimization

TODO: Optimize core performance:

#### Memory Optimization
```python
# Memory-efficient data handling
class MemoryOptimizer:
    """Optimize memory usage during execution"""

    def optimize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Reduce DataFrame memory footprint"""

        for col in df.columns:
            col_type = df[col].dtype

            if col_type != 'object':
                c_min = df[col].min()
                c_max = df[col].max()

                if str(col_type)[:3] == 'int':
                    if c_min > np.iinfo(np.int8).min and c_max < np.iinfo(np.int8).max:
                        df[col] = df[col].astype(np.int8)
                    elif c_min > np.iinfo(np.int16).min and c_max < np.iinfo(np.int16).max:
                        df[col] = df[col].astype(np.int16)
                    # ... continue for int32, int64

                else:  # float
                    if c_min > np.finfo(np.float16).min and c_max < np.finfo(np.float16).max:
                        df[col] = df[col].astype(np.float16)
                    # ... continue for float32

            else:  # object (string)
                # Convert to category if low cardinality
                if df[col].nunique() / len(df[col]) < 0.5:
                    df[col] = df[col].astype('category')

        return df
```

#### Query Optimization
```python
# Smart query optimization
class QueryOptimizer:
    """Optimize SQL queries for performance"""

    def optimize_query(self, query: str, schema: dict) -> str:
        """Optimize query based on schema information"""

        # Add index hints
        if self.has_indexes(schema):
            query = self.add_index_hints(query, schema)

        # Partition pruning
        if self.is_partitioned(schema):
            query = self.add_partition_filter(query, schema)

        # Column pruning
        query = self.remove_unused_columns(query)

        # Limit pushdown
        query = self.pushdown_limits(query)

        return query
```

### D5: Distributed Execution

TODO: Enable multi-node execution:

```python
# Distributed execution coordinator
class DistributedCoordinator:
    """Coordinate execution across multiple nodes"""

    def __init__(self, nodes: List[str]):
        self.nodes = nodes
        self.scheduler = self.create_scheduler()

    def distribute_pipeline(self, manifest: dict) -> dict:
        """Distribute pipeline across nodes"""

        # Analyze pipeline for distribution
        distribution_plan = self.analyze_pipeline(manifest)

        # Assign steps to nodes
        assignments = {}
        for step in manifest["steps"]:
            node = self.select_node(step, distribution_plan)
            assignments[step["id"]] = node

        return assignments

    def execute_distributed(self, manifest: dict, assignments: dict):
        """Execute pipeline across nodes"""

        # Start execution on each node
        futures = []
        for node, steps in self.group_by_node(assignments).items():
            future = self.execute_on_node(node, steps, manifest)
            futures.append(future)

        # Coordinate data transfer between nodes
        self.coordinate_transfers(futures, assignments)

        # Collect results
        return self.collect_results(futures)
```

## Success Criteria

TODO: Define measurable success criteria:

1. **Streaming Performance**
   - [ ] Process 1TB dataset with <2GB memory usage
   - [ ] Streaming throughput >100k rows/second
   - [ ] Checkpoint/resume functionality works
   - [ ] Spill-to-disk activates at threshold

2. **Parallelization**
   - [ ] 3x speedup for parallelizable pipelines
   - [ ] DAG execution correctness validated
   - [ ] Resource utilization >80% during parallel execution
   - [ ] No deadlocks or race conditions

3. **Observability**
   - [ ] All metrics visible in Datadog
   - [ ] Distributed tracing working
   - [ ] Alert on SLA breaches
   - [ ] Dashboard templates created

4. **Performance Gains**
   - [ ] 50% memory reduction for large datasets
   - [ ] 30% faster query execution
   - [ ] <100ms scheduling overhead
   - [ ] Linear scaling up to 10 nodes

5. **Reliability**
   - [ ] No OOM errors for datasets <1TB
   - [ ] Automatic retry on transient failures
   - [ ] Graceful degradation under load
   - [ ] Zero data loss guarantees

## Timeline

TODO: Implementation sequence:

### Phase 1: Streaming Foundation
- RowStream interface and base implementation
- Streaming drivers (MySQL, CSV)

### Phase 2: Parallelization
- DAG builder and executor
- Parallel execution testing

### Phase 3: Observability
- Datadog integration
- OpenTelemetry and dashboards

### Phase 4: Optimization & Distribution
- Performance optimization
- Distributed execution MVP

## Dependencies

TODO: External dependencies:

- ADR-0022: Streaming IO specification
- Datadog Agent installation
- OpenTelemetry Collector
- Network bandwidth for distributed execution
- Additional compute resources for parallel execution

## Risks

TODO: Risk assessment:

| Risk | Impact | Probability | Mitigation |
|------|--------|------------|------------|
| Streaming complexity | High | High | Incremental implementation |
| Memory leaks | High | Medium | Extensive testing and monitoring |
| Network bottlenecks | Medium | Medium | Data locality optimization |
| Observability overhead | Low | Medium | Sampling and buffering |
| Distributed coordination | High | Low | Start with single-node parallel |

## Open Questions

TODO: Questions to resolve:

1. Should streaming be opt-in or automatic based on data size?
2. How to handle schema evolution in streaming mode?
3. What's the optimal default batch size?
4. Should we support custom metrics backends?
5. How to handle partial failures in distributed execution?

## References

- ADR-0022: Streaming IO and Spill
- Apache Arrow streaming format
- Datadog API documentation
- OpenTelemetry specification
- Distributed systems best practices
