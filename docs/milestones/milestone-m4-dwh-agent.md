# Milestone M4: Data Warehouse Agent & Persistence

## Goals

TODO: Define high-level goals for M4:

1. **Enable Data Persistence**: Build Iceberg writer for long-term data storage
2. **Create DWH Agent**: Intelligent agent for managing data warehouse operations
3. **Support Analytics Platforms**: Integration with MotherDuck, Snowflake, BigQuery
4. **Implement Data Versioning**: Time-travel and data lineage in storage layer
5. **Automate Table Management**: Schema evolution, partitioning, and optimization

## Deliverables

### D1: Iceberg Writer Component

TODO: Implement Apache Iceberg writer:

```yaml
# Component spec for Iceberg writer
name: "iceberg.writer"
version: "1.0.0"
description: "Write data to Apache Iceberg tables with ACID guarantees"

config_schema:
  type: object
  required: ["table", "catalog"]
  properties:
    catalog:
      type: string
      description: "Iceberg catalog (glue, hive, hadoop)"
      enum: ["glue", "hive", "hadoop", "rest"]

    catalog_config:
      type: object
      description: "Catalog-specific configuration"
      properties:
        uri:
          type: string
          format: uri
        warehouse:
          type: string
          description: "Warehouse location (S3, HDFS path)"

    table:
      type: string
      description: "Target table name (database.table)"

    write_mode:
      type: string
      enum: ["append", "overwrite", "upsert", "merge"]
      default: "append"

    partition_spec:
      type: array
      items:
        type: object
        properties:
          field:
            type: string
          transform:
            enum: ["identity", "year", "month", "day", "hour", "bucket", "truncate"]

    schema_evolution:
      type: object
      properties:
        enabled:
          type: boolean
          default: true
        mode:
          enum: ["strict", "permissive"]
          default: "strict"

capabilities:
  modes: ["write"]
  features: ["batch", "streaming", "versioning", "time-travel"]
  doctor:
    enabled: true
    checks: ["catalog_connection", "table_exists", "permissions"]
```

#### Iceberg Driver Implementation
```python
# Iceberg writer driver
from pyiceberg import catalog
from pyiceberg.table import Table
import pyarrow as pa

class IcebergWriterDriver(Driver):
    """Driver for writing to Iceberg tables"""

    def run(self, step_id: str, config: dict, inputs: dict, ctx) -> dict:
        """Write data to Iceberg table"""

        # Initialize catalog
        cat = self._init_catalog(config["catalog"], config["catalog_config"])

        # Get or create table
        table = self._get_table(cat, config["table"], inputs.get("df"))

        # Convert DataFrame to PyArrow
        df = inputs["df"]
        arrow_table = pa.Table.from_pandas(df)

        # Handle schema evolution
        if config.get("schema_evolution", {}).get("enabled", True):
            table = self._evolve_schema(table, arrow_table.schema)

        # Write data based on mode
        write_mode = config.get("write_mode", "append")
        if write_mode == "append":
            table.append(arrow_table)
        elif write_mode == "overwrite":
            table.overwrite(arrow_table)
        elif write_mode == "upsert":
            self._upsert(table, arrow_table, config.get("key_columns"))
        elif write_mode == "merge":
            self._merge(table, arrow_table, config.get("merge_condition"))

        # Log metrics
        ctx.log_metric("rows_written", len(df))
        ctx.log_metric("files_written", table.current_snapshot().summary.get("total-files"))
        ctx.log_event("iceberg.write.complete", {
            "table": config["table"],
            "snapshot_id": table.current_snapshot().snapshot_id,
            "manifest_files": table.current_snapshot().manifest_list
        })

        return {
            "rows_written": len(df),
            "snapshot_id": table.current_snapshot().snapshot_id,
            "table_location": table.location()
        }

    def _evolve_schema(self, table: Table, new_schema: pa.Schema) -> Table:
        """Handle schema evolution"""
        # TODO: Implementation
        pass

    def _upsert(self, table: Table, data: pa.Table, key_columns: list):
        """Upsert data using key columns"""
        # TODO: Implementation using merge-on-read
        pass
```

### D2: DWH Agent

TODO: Create intelligent data warehouse agent:

```python
# Data Warehouse Agent for automated management
class DWHAgent:
    """
    Intelligent agent for data warehouse operations

    Responsibilities:
    - Analyze data patterns and suggest optimizations
    - Automate table maintenance (compaction, statistics)
    - Monitor query performance and suggest indexes
    - Handle schema evolution intelligently
    - Optimize storage and partitioning
    """

    def __init__(self, warehouse_config: dict):
        self.warehouse = self._connect_warehouse(warehouse_config)
        self.memory = MemoryStore()  # From ADR-0029
        self.llm = LLMAdapter()

    async def analyze_and_optimize(self, table: str) -> OptimizationPlan:
        """
        Analyze table and create optimization plan

        Steps:
        1. Profile data distribution
        2. Analyze query patterns
        3. Check storage efficiency
        4. Generate recommendations
        5. Create execution plan
        """

        # Profile the table
        profile = await self.profile_table(table)

        # Analyze query patterns from logs
        query_patterns = await self.analyze_query_logs(table)

        # Check storage efficiency
        storage_analysis = await self.analyze_storage(table)

        # Generate recommendations using LLM
        recommendations = await self.generate_recommendations(
            profile, query_patterns, storage_analysis
        )

        # Create optimization plan
        plan = OptimizationPlan()
        for rec in recommendations:
            if rec.type == "partition":
                plan.add_partitioning(rec.spec)
            elif rec.type == "compact":
                plan.add_compaction(rec.schedule)
            elif rec.type == "index":
                plan.add_index(rec.columns)
            elif rec.type == "clustering":
                plan.add_clustering(rec.keys)

        return plan

    async def profile_table(self, table: str) -> TableProfile:
        """Profile table characteristics"""

        profile = TableProfile()

        # Get basic statistics
        profile.row_count = await self.warehouse.count(table)
        profile.size_bytes = await self.warehouse.size(table)
        profile.column_stats = await self.warehouse.column_statistics(table)

        # Analyze data distribution
        profile.cardinality = {}
        for column in profile.column_stats:
            profile.cardinality[column] = await self.warehouse.cardinality(table, column)

        # Detect patterns
        profile.patterns = {
            "time_series": self.detect_time_series(profile),
            "slowly_changing": self.detect_scd(profile),
            "append_only": self.detect_append_only(profile)
        }

        return profile

    async def execute_maintenance(self, table: str):
        """Execute automated maintenance tasks"""

        # Compact small files
        if await self.needs_compaction(table):
            await self.compact_table(table)

        # Update statistics
        if await self.needs_stats_update(table):
            await self.update_statistics(table)

        # Expire old snapshots
        if await self.needs_snapshot_cleanup(table):
            await self.expire_snapshots(table)

        # Rewrite manifests
        if await self.needs_manifest_rewrite(table):
            await self.rewrite_manifests(table)
```

### D3: Analytics Platform Integration

TODO: Integrate with modern analytics platforms:

#### MotherDuck Integration
```python
# MotherDuck (DuckDB in the cloud) integration
class MotherDuckWriter(Driver):
    """Write to MotherDuck cloud data warehouse"""

    def __init__(self):
        import duckdb
        self.connection_string = "md:?token=${MOTHERDUCK_TOKEN}"

    def run(self, step_id: str, config: dict, inputs: dict, ctx) -> dict:
        """Write data to MotherDuck"""

        conn = duckdb.connect(self.connection_string)

        # Create or replace table
        table_name = config["table"]
        df = inputs["df"]

        if config.get("create_table", True):
            # Let DuckDB infer schema
            conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM df")
        else:
            # Append to existing table
            conn.execute(f"INSERT INTO {table_name} SELECT * FROM df")

        # Create indexes if specified
        for index in config.get("indexes", []):
            conn.execute(f"CREATE INDEX ON {table_name} ({index})")

        ctx.log_metric("rows_written", len(df))

        return {"rows_written": len(df)}
```

#### Snowflake Integration
```python
# Snowflake data warehouse integration
class SnowflakeWriter(Driver):
    """Write to Snowflake data warehouse"""

    def run(self, step_id: str, config: dict, inputs: dict, ctx) -> dict:
        """Write data to Snowflake using optimal method"""

        df = inputs["df"]
        rows = len(df)

        if rows > 100000:
            # Use COPY for large datasets
            return self._bulk_copy(config, df, ctx)
        else:
            # Use INSERT for small datasets
            return self._insert(config, df, ctx)

    def _bulk_copy(self, config: dict, df: pd.DataFrame, ctx) -> dict:
        """Bulk load using COPY command"""

        # Write to staging
        stage_file = f"@~/osiris_{uuid.uuid4()}.parquet"
        df.to_parquet(stage_file)

        # COPY into table
        conn = self._get_connection(config)
        conn.execute(f"""
            COPY INTO {config['table']}
            FROM {stage_file}
            FILE_FORMAT = (TYPE = PARQUET)
            PURGE = TRUE
        """)

        return {"method": "COPY", "rows_written": len(df)}
```

### D4: Data Versioning & Time Travel

TODO: Implement versioning capabilities:

```python
# Time travel and versioning support
class VersionedDataStore:
    """Manage versioned data with time travel"""

    def __init__(self, catalog: IcebergCatalog):
        self.catalog = catalog
        self.version_history = {}

    def create_version(self, table: str, tag: str = None) -> str:
        """Create a new version/snapshot"""

        table_obj = self.catalog.load_table(table)
        snapshot = table_obj.current_snapshot()

        version_id = str(snapshot.snapshot_id)

        # Tag the version if requested
        if tag:
            table_obj.manage_tags().create(tag, snapshot.snapshot_id)

        # Store version metadata
        self.version_history[version_id] = {
            "timestamp": snapshot.timestamp_ms,
            "tag": tag,
            "summary": snapshot.summary,
            "parent": snapshot.parent_snapshot_id
        }

        return version_id

    def time_travel(self, table: str, point_in_time) -> pd.DataFrame:
        """Read data as of specific time"""

        table_obj = self.catalog.load_table(table)

        if isinstance(point_in_time, str):
            # Tag-based time travel
            snapshot_id = table_obj.manage_tags().get(point_in_time)
        elif isinstance(point_in_time, datetime):
            # Timestamp-based time travel
            snapshot_id = self._find_snapshot_at_time(table_obj, point_in_time)
        else:
            # Snapshot ID
            snapshot_id = point_in_time

        # Read data from specific snapshot
        return table_obj.scan(snapshot_id=snapshot_id).to_pandas()

    def compare_versions(self, table: str, v1: str, v2: str) -> dict:
        """Compare two versions of data"""

        df1 = self.time_travel(table, v1)
        df2 = self.time_travel(table, v2)

        return {
            "rows_added": len(df2) - len(df1),
            "rows_removed": 0,  # Calculate based on keys
            "rows_modified": 0,  # Calculate based on content
            "schema_changes": self._compare_schemas(df1, df2)
        }
```

### D5: Automated Table Management

TODO: Implement intelligent table management:

```python
# Automated table lifecycle management
class TableManager:
    """Manage table lifecycle automatically"""

    def __init__(self, dwh_agent: DWHAgent):
        self.agent = dwh_agent
        self.policies = {}

    def register_table(self, table: str, policy: TablePolicy):
        """Register table with management policy"""

        self.policies[table] = policy

        # Schedule automated tasks
        self.schedule_maintenance(table, policy.maintenance_schedule)
        self.schedule_optimization(table, policy.optimization_schedule)
        self.schedule_archival(table, policy.retention_policy)

    async def apply_policy(self, table: str):
        """Apply management policy to table"""

        policy = self.policies[table]

        # Partitioning strategy
        if policy.partitioning:
            await self.apply_partitioning(table, policy.partitioning)

        # Clustering strategy
        if policy.clustering:
            await self.apply_clustering(table, policy.clustering)

        # Compaction strategy
        if policy.compaction:
            await self.apply_compaction(table, policy.compaction)

        # Retention strategy
        if policy.retention:
            await self.apply_retention(table, policy.retention)

    async def auto_partition(self, table: str) -> PartitionSpec:
        """Automatically determine optimal partitioning"""

        profile = await self.agent.profile_table(table)

        # Analyze data patterns
        if profile.patterns["time_series"]:
            # Time-based partitioning
            return PartitionSpec(
                field=profile.time_column,
                transform="month" if profile.row_count > 1e9 else "day"
            )
        elif profile.has_high_cardinality_column():
            # Hash partitioning
            return PartitionSpec(
                field=profile.highest_cardinality_column,
                transform=f"bucket[{self.calculate_buckets(profile)}]"
            )
        else:
            # No partitioning needed
            return None
```

## Success Criteria

TODO: Define measurable success criteria:

1. **Iceberg Writer**
   - [ ] ACID transactions working
   - [ ] Schema evolution handled gracefully
   - [ ] Time travel queries functional
   - [ ] Performance: >1M rows/second write

2. **DWH Agent**
   - [ ] Automated optimization reduces query time by 30%
   - [ ] Proactive maintenance prevents issues
   - [ ] Intelligent recommendations accepted >80% of time
   - [ ] Storage costs reduced by 20%

3. **Platform Integration**
   - [ ] MotherDuck integration complete
   - [ ] Snowflake integration complete
   - [ ] BigQuery integration complete
   - [ ] Round-trip data integrity verified

4. **Data Versioning**
   - [ ] Point-in-time recovery works
   - [ ] Version comparison accurate
   - [ ] Tag-based versioning functional
   - [ ] Storage overhead <10%

5. **Table Management**
   - [ ] Auto-partitioning improves performance
   - [ ] Compaction reduces file count by 90%
   - [ ] Retention policies enforced
   - [ ] Zero manual intervention required

## Timeline

TODO: Implementation sequence:

### Stage 1: Foundation
- Iceberg writer implementation
- Basic DWH agent
- MotherDuck integration

### Stage 2: Intelligence
- Advanced DWH agent features
- Snowflake & BigQuery integration
- Automated optimization

### Stage 3: Advanced Features
- Full versioning support
- Automated table management
- Performance optimization

### Stage 4: Production Hardening
- Scale testing
- Production deployment
- Documentation & training

## Dependencies

TODO: External dependencies:

- Apache Iceberg libraries
- PyArrow for columnar processing
- Cloud platform SDKs (AWS, GCP, Azure)
- MotherDuck/DuckDB client
- Snowflake connector
- BigQuery client library

## Risks

TODO: Risk assessment:

| Risk | Impact | Probability | Mitigation |
|------|--------|------------|------------|
| Iceberg complexity | High | Medium | Phased implementation |
| Platform API changes | Medium | Low | Version pinning |
| Storage costs | Medium | Medium | Retention policies |
| Performance issues | High | Low | Extensive benchmarking |
| Schema evolution bugs | High | Medium | Comprehensive testing |

## Open Questions

TODO: Questions to resolve:

1. Which Iceberg catalog should be the default?
2. How to handle cross-platform data movement?
3. Should we support Delta Lake and Hudi too?
4. What's the optimal compaction strategy?
5. How to price DWH agent as a service?

## References

- Apache Iceberg documentation
- MotherDuck API reference
- Snowflake bulk loading guide
- BigQuery best practices
- Data warehouse optimization papers
