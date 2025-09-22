# ADR-0029: Osiris Memory Store

## Status
Proposed

## Context

Osiris currently has no persistence of discovered information, user preferences, or learned patterns across sessions. This leads to:
- Repeated discovery of the same database schemas
- Loss of context explained by users in previous conversations
- No sharing of knowledge between team members
- Inability to learn from successful pipeline patterns
- Redundant work when creating similar pipelines

The problem manifests as:
- **Discovery Repetition**: Same tables profiled multiple times
- **Context Loss**: User explanations forgotten between sessions
- **No Learning**: Cannot improve suggestions based on history
- **Team Silos**: Each user discovers everything independently
- **Pattern Blindness**: Cannot suggest proven pipeline patterns

Organizations need:
- Persistent storage of discovery results
- Shared knowledge base across team
- Context preservation between sessions
- Pattern learning from successful pipelines
- Freshness validation to detect schema changes

## Decision

Introduce a persistent memory store that preserves discovery results, user context, and learned patterns. Start with SQLite for v1, with extensibility to S3/PostgreSQL for organizational sharing.

### Memory Store Architecture

```python
# Core Memory API
class MemoryStore:
    """Persistent memory for Osiris knowledge"""

    def put(self, key: str, value: Any, tags: List[str], ttl: Optional[int] = None) -> str:
        """
        Store information with tags and optional TTL

        Args:
            key: Unique identifier
            value: Information to store (JSON-serializable)
            tags: Searchable tags
            ttl: Time-to-live in seconds

        Returns:
            Memory ID for retrieval
        """
        pass

    def query(self, tags: List[str] = None, pattern: str = None,
              since: datetime = None, limit: int = 100) -> List[Memory]:
        """
        Query memories by tags, pattern, or time

        Args:
            tags: Filter by tags (AND operation)
            pattern: Text pattern search
            since: Return memories after this time
            limit: Maximum results

        Returns:
            List of matching memories
        """
        pass

    def get(self, memory_id: str) -> Optional[Memory]:
        """Get specific memory by ID"""
        pass

    def refresh(self, memory_id: str) -> bool:
        """Check if memory is still valid/fresh"""
        pass

    def forget(self, memory_id: str) -> bool:
        """Remove memory from store"""
        pass
```

### Memory Categories

TODO: Define memory categories and schemas:

1. **Discovery Memory**
   ```json
   {
     "type": "discovery.schema",
     "key": "mysql.primary.customers",
     "value": {
       "table": "customers",
       "columns": [
         {"name": "id", "type": "INTEGER", "primary_key": true},
         {"name": "email", "type": "VARCHAR(255)", "unique": true}
       ],
       "row_count": 15234,
       "discovered_at": "2024-01-15T10:00:00Z",
       "sample_queries": [
         "SELECT * FROM customers WHERE created_at > '2024-01-01'"
       ]
     },
     "tags": ["mysql", "primary", "customers", "schema"],
     "ttl": 86400,  // 24 hours
     "fingerprint": "sha256:abc123..."  // For freshness check
   }
   ```

2. **Context Memory**
   ```json
   {
     "type": "context.explanation",
     "key": "business.customer_segments",
     "value": {
       "explanation": "Premium customers have lifetime value > $10000",
       "sql_fragment": "CASE WHEN lifetime_value > 10000 THEN 'premium'",
       "explained_by": "user@company.com",
       "session_id": "chat_123"
     },
     "tags": ["business", "customers", "segmentation"],
     "ttl": null  // Never expires
   }
   ```

3. **Pattern Memory**
   ```json
   {
     "type": "pattern.pipeline",
     "key": "pattern.mysql_to_csv",
     "value": {
       "description": "Standard MySQL to CSV export",
       "oml_template": "...",
       "usage_count": 45,
       "success_rate": 0.98,
       "average_runtime": 120,
       "last_used": "2024-01-14T15:00:00Z"
     },
     "tags": ["pattern", "mysql", "csv", "proven"],
     "ttl": null
   }
   ```

4. **Team Memory**
   ```json
   {
     "type": "team.knowledge",
     "key": "team.data_quirks.orders",
     "value": {
       "warning": "Orders table has duplicate rows for cancelled orders",
       "workaround": "Use DISTINCT when querying orders",
       "discovered_by": "alice@company.com",
       "confirmed_by": ["bob@company.com", "charlie@company.com"]
     },
     "tags": ["team", "orders", "data_quality", "warning"],
     "ttl": 2592000  // 30 days
   }
   ```

### Storage Backends

TODO: Implement storage backends:

1. **SQLite Backend** (Default for v1)
   ```sql
   CREATE TABLE memories (
     id TEXT PRIMARY KEY,
     type TEXT NOT NULL,
     key TEXT UNIQUE NOT NULL,
     value JSON NOT NULL,
     tags JSON NOT NULL,
     created_at TIMESTAMP NOT NULL,
     expires_at TIMESTAMP,
     accessed_at TIMESTAMP,
     access_count INTEGER DEFAULT 0,
     fingerprint TEXT,
     owner TEXT,
     visibility TEXT DEFAULT 'private'
   );

   CREATE INDEX idx_tags ON memories(tags);
   CREATE INDEX idx_type ON memories(type);
   CREATE INDEX idx_expires ON memories(expires_at);
   ```

2. **S3 Backend** (Future - Organization sharing)
   ```
   s3://osiris-memory/
     ├── org-name/
     │   ├── discovery/
     │   ├── patterns/
     │   └── context/
     └── personal/
         └── user@company.com/
   ```

3. **PostgreSQL Backend** (Future - Real-time sync)
   ```sql
   -- Shared organizational memory with access control
   -- Real-time updates across team
   -- Full-text search capabilities
   ```

### Memory Integration Points

TODO: Integrate memory throughout Osiris:

1. **Discovery Integration**
   ```python
   def discover_schema(table: str) -> Schema:
       # Check memory first
       memory = memory_store.query(
           tags=["discovery", "schema", table],
           since=datetime.now() - timedelta(hours=24)
       )

       if memory and memory[0].is_fresh():
           return memory[0].value

       # Perform discovery
       schema = perform_discovery(table)

       # Store in memory
       memory_store.put(
           key=f"discovery.{table}",
           value=schema,
           tags=["discovery", "schema", table],
           ttl=86400
       )

       return schema
   ```

2. **Chat Integration**
   ```python
   def generate_oml(intent: str) -> str:
       # Retrieve relevant context
       context = memory_store.query(
           pattern=intent,
           tags=["context", "pattern"],
           limit=10
       )

       # Use context in prompt
       prompt = build_prompt(intent, context)

       # Generate OML
       oml = llm.generate(prompt)

       # Learn from success
       if validate_oml(oml):
           memory_store.put(
               key=f"pattern.{hash(intent)}",
               value={"intent": intent, "oml": oml},
               tags=["pattern", "successful"]
           )

       return oml
   ```

3. **CLI Commands**
   ```bash
   # Memory management commands
   osiris memory search "customer segmentation"
   osiris memory show <memory_id>
   osiris memory forget <memory_id>
   osiris memory export --format json > memories.json
   osiris memory import memories.json
   osiris memory stats

   # Share memories with team
   osiris memory share <memory_id> --team
   osiris memory sync --org
   ```

### Freshness Validation

TODO: Implement freshness checking:

```python
def check_freshness(memory: Memory) -> bool:
    """Validate if memory is still accurate"""

    if memory.type == "discovery.schema":
        # Re-fingerprint current schema
        current_fingerprint = calculate_fingerprint(
            get_current_schema(memory.value["table"])
        )
        return current_fingerprint == memory.fingerprint

    elif memory.type == "context.explanation":
        # Context doesn't expire unless explicitly removed
        return not memory.is_expired()

    elif memory.type == "pattern.pipeline":
        # Check if pattern still succeeds
        return memory.value["success_rate"] > 0.9

    return True
```

### Privacy & Security

TODO: Implement access controls:

```python
class MemoryVisibility(Enum):
    PRIVATE = "private"      # Only visible to creator
    TEAM = "team"            # Visible to team members
    ORGANIZATION = "org"     # Visible to entire org
    PUBLIC = "public"        # Visible to all (future)

class MemoryAccess:
    def can_read(self, memory: Memory, user: User) -> bool:
        if memory.owner == user.id:
            return True

        if memory.visibility == MemoryVisibility.TEAM:
            return user.team == memory.owner_team

        if memory.visibility == MemoryVisibility.ORGANIZATION:
            return user.org == memory.owner_org

        return False
```

## Consequences

### Positive
- **Efficiency**: Avoid repeated discovery and profiling
- **Knowledge Sharing**: Teams share discoveries and patterns
- **Learning System**: Osiris improves over time
- **Context Preservation**: User explanations retained
- **Pattern Reuse**: Successful pipelines become templates

### Negative
- **Storage Requirements**: Memory store needs disk space
- **Freshness Overhead**: Validation checks add latency
- **Privacy Concerns**: Shared memories may leak information
- **Complexity**: Another system to maintain and backup

### Neutral
- **Migration Path**: Need strategy for adopting memory
- **Sync Challenges**: Keeping distributed memories consistent
- **Retention Policies**: Deciding what to remember/forget

## Implementation Plan

TODO: Phased implementation:

### Phase 1: Local SQLite Store (Week 1-2)
- Core MemoryStore API
- SQLite backend implementation
- Discovery integration
- Basic CLI commands

### Phase 2: Memory Integration (Week 3)
- Chat context retrieval
- Pattern learning
- Freshness validation
- Memory search

### Phase 3: Team Features (Week 4)
- Visibility controls
- Team sharing
- Memory sync
- Export/import

### Phase 4: Advanced Backends (Future)
- S3 backend for organizations
- PostgreSQL for real-time sync
- Redis for caching layer
- Memory analytics

## Migration Strategy

TODO: Adoption strategy:

```bash
# Import existing discovery cache
osiris memory import --from-cache

# Learn from historical runs
osiris memory learn --from-logs ./logs/

# Export for backup
osiris memory export > backup.json
```

## References
- Issue #XXX: Knowledge persistence request
- ADR-0002: Discovery cache (to be enhanced)
- ADR-0028: Git integration (memory in repos)
- ADR-0030: Agents need memory for context
- Vector databases for semantic search (future)
