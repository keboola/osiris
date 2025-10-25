# API Type Selector

## Decision Tree

**START: What type of data source are you connecting to?**

### Question 1: Is it a relational database (MySQL, PostgreSQL, Supabase)?

**YES** → Use SQL-based extractor pattern
- **Component family**: `[database].extractor`
- **Modes**: `["extract", "discover"]`
- **Reference**: `recipes/sql-extractor.md`
- **Examples**: `mysql.extractor`, `supabase.extractor`

**Key characteristics**:
- Connection: host, port, database, user, password
- Discovery: `SHOW TABLES`, `INFORMATION_SCHEMA` queries
- Extraction: `SELECT` queries with WHERE clauses
- Pagination: `LIMIT/OFFSET` in SQL

**NO** → Continue to Question 2

---

### Question 2: Is it a GraphQL API?

**YES** → Use GraphQL extractor pattern
- **Component family**: `graphql.extractor`
- **Modes**: `["extract"]`
- **Reference**: `recipes/graphql-extractor.md`
- **Example**: `graphql.extractor`

**Key characteristics**:
- Connection: endpoint URL, optional auth token
- Discovery: Introspection query (optional)
- Extraction: GraphQL queries with variables
- Pagination: Varies by API (check schema)

**NO** → Continue to Question 3

---

### Question 3: Is it a REST API?

**YES** → Use REST extractor pattern
- **Component family**: `[service].extractor`
- **Modes**: `["extract"]`
- **Reference**: `recipes/rest-api-extractor.md`
- **Next decisions**:
  - `auth-selector.md` (choose authentication)
  - `pagination-selector.md` (choose pagination)

**Key characteristics**:
- Connection: base URL, auth credentials
- Discovery: Usually not supported (manual schema definition)
- Extraction: HTTP GET/POST requests
- Pagination: offset, cursor, or link-based (next decision)

**NO** → Contact team (unsupported data source type)

---

## Characteristics by Type

### SQL Database
```yaml
connection:
  host: "db.example.com"
  port: 3306
  database: "mydb"
  user: "admin"
  password: "***"  # secret

discovery:
  - SHOW TABLES
  - SELECT * FROM information_schema.columns WHERE table_name = ?

extraction:
  - SELECT * FROM table WHERE updated_at >= ? LIMIT 1000 OFFSET 0

pagination:
  - LIMIT/OFFSET based
  - Deterministic with ORDER BY
```

**Pros**:
- Built-in discovery support
- Efficient filtering with indexes
- Transactional consistency

**Cons**:
- Requires database credentials
- Schema changes need migration

---

### GraphQL API
```yaml
connection:
  endpoint: "https://api.example.com/graphql"
  auth_token: "***"  # optional secret

discovery:
  query: |
    {
      __schema {
        types { name fields { name type { name } } }
      }
    }

extraction:
  query: |
    query GetUsers($cursor: String) {
      users(first: 100, after: $cursor) {
        edges { node { id name email } }
        pageInfo { endCursor hasNextPage }
      }
    }

pagination:
  - Cursor-based (Relay style)
  - Or custom pagination schema
```

**Pros**:
- Type-safe schema
- Request exactly what you need
- Built-in pagination support

**Cons**:
- Requires GraphQL knowledge
- Complex nested queries

---

### REST API
```yaml
connection:
  base_url: "https://api.example.com/v1"
  api_key: "***"  # secret

extraction:
  endpoint: "/users"
  method: "GET"
  params:
    page: 1
    per_page: 100

pagination:
  - Offset: page=1, per_page=100
  - Cursor: cursor=abc123
  - Link: Follow "next" URL
```

**Pros**:
- Widely supported
- Simple HTTP requests
- Good tooling support

**Cons**:
- No discovery support
- Inconsistent pagination patterns
- Schema must be manually defined

---

## Next Steps

After choosing API type, proceed to:

1. **SQL Database** → `recipes/sql-extractor.md`
   - Implement discovery mode
   - Use connection pooling
   - Add incremental extraction

2. **GraphQL API** → `recipes/graphql-extractor.md`
   - Define GraphQL queries
   - Handle introspection
   - Implement cursor pagination

3. **REST API** → Decision trees:
   - First: `decision-trees/auth-selector.md` (choose authentication)
   - Then: `decision-trees/pagination-selector.md` (choose pagination)
   - Finally: `recipes/rest-api-extractor.md` (implementation)

---

## Common Patterns

### Discovery Support Matrix

| Type     | Discovery | How                          |
|----------|-----------|------------------------------|
| SQL      | ✓ Yes     | INFORMATION_SCHEMA queries   |
| GraphQL  | ✓ Yes     | Introspection query          |
| REST     | ✗ No      | Manual schema definition     |

### Connection Validation

All types should implement `validate_connection()`:

```python
def validate_connection(self, config: Dict[str, Any]) -> bool:
    """Test connection to data source."""
    try:
        # SQL: SELECT 1
        # GraphQL: Simple query
        # REST: GET /health or similar
        return True
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        return False
```

---

## Quick Reference

**Choose SQL if**:
- Structured relational data
- Need schema discovery
- Have database credentials
- Want incremental extraction

**Choose GraphQL if**:
- API provides GraphQL endpoint
- Need type safety
- Want flexible querying
- API uses Relay-style pagination

**Choose REST if**:
- Traditional HTTP API
- JSON/XML responses
- Simple request/response pattern
- Various auth methods needed

---

**Document Version**: 1.0
**Last Updated**: 2025-10-26
**Related**: `auth-selector.md`, `pagination-selector.md`, `../recipes/`
