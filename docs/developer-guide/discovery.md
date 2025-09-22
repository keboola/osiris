# Osiris Pipeline - Discovery Mode for Components

## Purpose

Discovery mode enables components to work with the interactive AI agent (`osiris chat --interactive`) by allowing the agent to query source and target systems for metadata. This is critical for:
- Understanding database schemas before generating pipelines
- Validating table and column existence
- Profiling data distributions and patterns
- Identifying optimal extraction strategies
- Caching discovery results for performance

## Technical Contract

### Discovery Interface

TODO: Complete discovery interface specification:

```python
class DiscoveryCapability(Protocol):
    """Protocol for component discovery capabilities"""

    def discover_schema(self, config: dict, options: dict = None) -> SchemaInfo:
        """
        Discover schema information from the data source

        Args:
            config: Connection configuration
            options: Discovery options (tables, depth, sampling)

        Returns:
            SchemaInfo with tables, columns, types, constraints
        """
        pass

    def discover_statistics(self, config: dict, table: str) -> TableStatistics:
        """
        Gather statistics about a specific table

        Args:
            config: Connection configuration
            table: Table name to profile

        Returns:
            TableStatistics with row counts, cardinality, patterns
        """
        pass

    def discover_samples(self, config: dict, table: str, limit: int = 5) -> list:
        """
        Retrieve sample rows for understanding data

        Args:
            config: Connection configuration
            table: Table name
            limit: Number of sample rows

        Returns:
            List of sample rows as dictionaries
        """
        pass
```

### Component Declaration

TODO: How components declare discovery capability:

```yaml
# In component spec.yaml
name: "mysql.extractor"
version: "1.0.0"

capabilities:
  modes: ["read"]
  discovery:
    enabled: true
    features:
      - schema       # Can discover table/column structure
      - statistics   # Can gather row counts and cardinality
      - samples      # Can retrieve sample data
      - incremental  # Can detect changes since last discovery
    cache_ttl: 3600  # Discovery cache validity in seconds
```

### Discovery Driver Implementation

TODO: Example discovery implementation:

```python
class MySQLExtractorDriver(Driver):
    """MySQL extractor with discovery support"""

    def discover_schema(self, config: dict, options: dict = None) -> SchemaInfo:
        """Discover MySQL database schema"""

        connection = self._connect(config)
        tables = options.get("tables", []) if options else []

        schema_info = SchemaInfo()

        # Discover tables
        query = """
            SELECT TABLE_NAME, TABLE_ROWS, DATA_LENGTH
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s
        """

        if tables:
            query += f" AND TABLE_NAME IN ({','.join(['%s'] * len(tables))})"

        cursor = connection.cursor()
        cursor.execute(query, [config["database"]] + tables)

        for row in cursor:
            table_info = TableInfo(
                name=row[0],
                estimated_rows=row[1],
                size_bytes=row[2]
            )

            # Discover columns for each table
            col_query = """
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
            """
            cursor.execute(col_query, [config["database"], row[0]])

            for col in cursor:
                table_info.add_column(ColumnInfo(
                    name=col[0],
                    data_type=col[1],
                    nullable=col[2] == "YES",
                    is_primary_key=col[3] == "PRI",
                    is_unique=col[3] == "UNI"
                ))

            schema_info.add_table(table_info)

        return schema_info

    def discover_statistics(self, config: dict, table: str) -> TableStatistics:
        """Gather table statistics for optimization"""

        stats = TableStatistics(table=table)
        connection = self._connect(config)

        # Row count
        cursor = connection.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        stats.row_count = cursor.fetchone()[0]

        # Column cardinality
        cursor.execute(f"SHOW COLUMNS FROM {table}")
        columns = [row[0] for row in cursor]

        for column in columns:
            cursor.execute(f"SELECT COUNT(DISTINCT {column}) FROM {table} LIMIT 1000")
            stats.cardinality[column] = cursor.fetchone()[0]

        # Detect patterns
        stats.patterns = self._detect_patterns(connection, table)

        return stats
```

### Discovery Cache Integration

TODO: How discovery results are cached:

```python
class DiscoveryCache:
    """Cache for discovery results"""

    def __init__(self, cache_dir: str = ".osiris_cache"):
        self.cache_dir = cache_dir
        self.fingerprinter = CacheFingerprinter()

    def get_cached(self, component: str, config: dict) -> Optional[SchemaInfo]:
        """Retrieve cached discovery if valid"""

        # Generate fingerprint for cache key
        fingerprint = self.fingerprinter.compute(component, config)
        cache_file = f"{self.cache_dir}/discovery_{fingerprint}.json"

        if os.path.exists(cache_file):
            with open(cache_file) as f:
                cached = json.load(f)

            # Check TTL
            if time.time() - cached["timestamp"] < cached["ttl"]:
                return SchemaInfo.from_dict(cached["data"])

        return None

    def cache_result(self, component: str, config: dict,
                    result: SchemaInfo, ttl: int = 3600):
        """Cache discovery result"""

        fingerprint = self.fingerprinter.compute(component, config)
        cache_file = f"{self.cache_dir}/discovery_{fingerprint}.json"

        with open(cache_file, 'w') as f:
            json.dump({
                "timestamp": time.time(),
                "ttl": ttl,
                "component": component,
                "data": result.to_dict()
            }, f)
```

### Interactive Agent Integration

TODO: How the chat agent uses discovery:

```python
class InteractiveAgent:
    """Chat agent with discovery support"""

    def __init__(self):
        self.discovery_cache = DiscoveryCache()
        self.registry = ComponentRegistry()

    async def handle_intent(self, user_intent: str):
        """Process user intent with discovery"""

        # Parse intent to identify data sources
        sources = self.parse_data_sources(user_intent)

        # Discover schemas for each source
        discoveries = {}
        for source in sources:
            component = self.registry.get(source.component)

            if component.has_capability("discovery"):
                # Check cache first
                schema = self.discovery_cache.get_cached(
                    source.component, source.config
                )

                if not schema:
                    # Perform discovery
                    driver = self.registry.get_driver(source.component)
                    schema = driver.discover_schema(source.config)

                    # Cache result
                    self.discovery_cache.cache_result(
                        source.component, source.config, schema
                    )

                discoveries[source.name] = schema

        # Use discoveries to generate pipeline
        pipeline = await self.generate_pipeline(user_intent, discoveries)
        return pipeline
```

## Examples

TODO: Complete discovery examples:

### MySQL Discovery Example
```python
# MySQL component with full discovery
driver = MySQLExtractorDriver()

# Discover all tables
schema = driver.discover_schema({
    "host": "db.example.com",
    "database": "production",
    "user": "readonly"
})

# Discover specific tables
schema = driver.discover_schema(
    config,
    options={"tables": ["customers", "orders"]}
)

# Get statistics for optimization
stats = driver.discover_statistics(config, "customers")
print(f"Customers table: {stats.row_count} rows")
print(f"Email cardinality: {stats.cardinality['email']}")
```

### Supabase Discovery Example
```python
# Supabase with schema introspection
driver = SupabaseExtractorDriver()

schema = driver.discover_schema({
    "url": "https://project.supabase.co",
    "schema": "public"
})

# Discover foreign key relationships
relationships = driver.discover_relationships(config)
```

### Custom Discovery Implementation
```python
# Custom component with discovery
class CustomExtractorDriver(Driver):
    def discover_schema(self, config: dict, options: dict = None):
        # Connect to custom system
        client = self._get_client(config)

        # Retrieve metadata
        metadata = client.get_metadata()

        # Convert to standard format
        schema_info = SchemaInfo()
        for entity in metadata.entities:
            table_info = TableInfo(name=entity.name)
            for field in entity.fields:
                table_info.add_column(ColumnInfo(
                    name=field.name,
                    data_type=field.type
                ))
            schema_info.add_table(table_info)

        return schema_info
```

## Best Practices

TODO: Discovery implementation best practices:

### Performance
- Cache discovery results with appropriate TTL
- Use sampling for large tables
- Implement progressive discovery (start shallow, go deeper as needed)
- Batch metadata queries when possible

### Security
- Use read-only connections for discovery
- Never expose sensitive data in discovery results
- Mask or redact sample data appropriately
- Validate discovery permissions

### Reliability
- Handle missing tables gracefully
- Provide fallback for systems without metadata APIs
- Validate discovered schema against expectations
- Include discovery errors in diagnostics

### User Experience
- Show discovery progress to users
- Explain what is being discovered and why
- Allow users to skip or limit discovery
- Provide manual schema input as alternative
