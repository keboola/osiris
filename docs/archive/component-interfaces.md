# MVP Component Interfaces - Minimal & Essential

**Date:** 2025-08-28
**Version:** MVP 1.0
**Purpose:** Define minimal interfaces for clean architecture in 10-day MVP
**Principle:** Just enough abstraction for testability, not over-engineering

## Core Philosophy

For the MVP, we need **only 3 essential interfaces**:

1. **IStateStore** - State management
2. **ITemplateEngine** - Template matching
3. **IDiscovery** - Data discovery

Skip complex patterns (factories, adapters) until post-MVP.

## Essential Interfaces (MVP Only)

### 1. State Store Interface (~20 lines)

```python
from abc import ABC, abstractmethod
from typing import Any, Optional

class IStateStore(ABC):
    """Minimal state store interface"""

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """Store a value"""
        pass

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value"""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all state"""
        pass
```

**Implementation:**

```python
class SQLiteStateStore(IStateStore):
    """Simple SQLite implementation"""

    def __init__(self, session_id: str):
        self.db = sqlite3.connect(f".osiris/{session_id}/state.db")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS state
            (key TEXT PRIMARY KEY, value TEXT)
        """)

    def set(self, key: str, value: Any) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO state VALUES (?, ?)",
            (key, json.dumps(value))
        )
        self.db.commit()

    def get(self, key: str, default: Any = None) -> Any:
        row = self.db.execute(
            "SELECT value FROM state WHERE key = ?", (key,)
        ).fetchone()
        return json.loads(row[0]) if row else default

    def clear(self) -> None:
        self.db.execute("DELETE FROM state")
        self.db.commit()
```

### 2. Template Engine Interface (~30 lines)

```python
from dataclasses import dataclass
from typing import Optional, Dict, List

@dataclass
class Template:
    """Minimal template structure"""
    id: str
    pattern: str  # Regex for matching
    sql_template: str
    params: List[str]  # Required params

class ITemplateEngine(ABC):
    """Minimal template engine interface"""

    @abstractmethod
    def match(self, user_input: str) -> Optional[Template]:
        """Match input to template"""
        pass

    @abstractmethod
    def apply(self, template: Template, params: Dict[str, Any]) -> str:
        """Apply params to template"""
        pass
```

**Implementation:**

```python
class SimpleTemplateEngine(ITemplateEngine):
    """YAML-based template engine"""

    def __init__(self, template_file: str = "templates.yaml"):
        with open(template_file) as f:
            self.templates = yaml.safe_load(f)['templates']

    def match(self, user_input: str) -> Optional[Template]:
        for t in self.templates:
            if re.search(t['pattern'], user_input, re.I):
                return Template(
                    id=t['id'],
                    pattern=t['pattern'],
                    sql_template=t['sql'],
                    params=t.get('params', [])
                )
        return None

    def apply(self, template: Template, params: Dict[str, Any]) -> str:
        return template.sql_template.format(**params)
```

### 3. Discovery Interface (~40 lines)

```python
@dataclass
class TableInfo:
    """Minimal table information"""
    name: str
    columns: List[Dict[str, str]]  # [{name, type}]
    row_count: int
    sample: List[Dict[str, Any]]  # Sample rows

class IDiscovery(ABC):
    """Minimal discovery interface"""

    @abstractmethod
    async def list_tables(self) -> List[str]:
        """List available tables"""
        pass

    @abstractmethod
    async def get_table_info(self, table: str, sample_size: int = 10) -> TableInfo:
        """Get table info with sample"""
        pass
```

**Implementation:**

```python
class ProgressiveDiscovery(IDiscovery):
    """Progressive discovery with existing Osiris components"""

    def __init__(self, connection_config: dict):
        # Reuse existing Osiris discovery
        from osiris.core.discovery import DiscoveryEngine
        self.engine = DiscoveryEngine(connection_config)

    async def list_tables(self) -> List[str]:
        # Wrap existing functionality
        return await self.engine.list_tables()

    async def get_table_info(self, table: str, sample_size: int = 10) -> TableInfo:
        # Progressive: start with 10 rows
        schema = await self.engine.get_schema(table)
        sample = await self.engine.get_sample(table, sample_size)
        count = await self.engine.get_count(table)

        return TableInfo(
            name=table,
            columns=[{"name": c.name, "type": c.type} for c in schema.columns],
            row_count=count,
            sample=sample.to_dict('records')
        )
```

## Integration Pattern (Simple)

```python
class ConversationalAgent:
    """Main agent using interfaces"""

    def __init__(self, session_id: str, config: dict):
        # Direct instantiation for MVP (no factories)
        self.state = SQLiteStateStore(session_id)
        self.templates = SimpleTemplateEngine()
        self.discovery = ProgressiveDiscovery(config)

    async def generate_pipeline(self, user_input: str) -> str:
        # 1. Try template match
        template = self.templates.match(user_input)

        if template:
            # Fast path
            tables = await self.discovery.list_tables()
            info = await self.discovery.get_table_info(tables[0])

            # Apply template
            sql = self.templates.apply(template, {
                "table": tables[0],
                "columns": info.columns
            })

            # Save state
            self.state.set("sql", sql)
            self.state.set("tables", tables)
        else:
            # LLM fallback (implement in Day 5)
            sql = await self.generate_with_llm(user_input)

        # Generate YAML
        return self.create_yaml(sql)
```

## Testing Benefits

```python
class MockStateStore(IStateStore):
    """Mock for testing"""
    def __init__(self):
        self.data = {}

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def clear(self) -> None:
        self.data.clear()

# Easy to test
def test_agent():
    agent = ConversationalAgent("test", {})
    agent.state = MockStateStore()  # Inject mock
    agent.templates = MockTemplateEngine()

    result = agent.generate_pipeline("top 10 movies")
    assert "SELECT" in result
```

## What We're NOT Doing (MVP)

- ❌ Complex factory patterns
- ❌ Dependency injection frameworks
- ❌ Abstract base classes for everything
- ❌ Configuration-driven component creation
- ❌ Plugin architecture
- ❌ Service locator pattern

## Implementation Timeline

**Day 0 (Added):** Define interfaces (2-3 hours)

- Create this document
- Define 3 core interfaces
- Update existing code to use interfaces

**Day 1-2:** Implement interfaces

- SQLiteStateStore
- SimpleTemplateEngine
- ProgressiveDiscovery wrapper

## Benefits for MVP

1. **Testability** - Can mock for unit tests
2. **Clear Boundaries** - Know what each component does
3. **Future-Proof** - Easy to swap implementations post-MVP
4. **Simple** - Only ~90 lines of interface code

## Post-MVP Evolution

After shipping, we can add:

- Factory pattern for component creation
- More sophisticated discovery interface
- SQL validator interface
- Pipeline generator interface
- Adapter pattern for external systems

But for now, **keep it simple** and ship in 10 days!
