# MCP Tool Reference

This document provides detailed input/output schemas for all MCP tools in Osiris v0.5.0.

**IMPORTANT**: All tool names use underscores (`_`) instead of periods (`.`) to comply with Claude Desktop's MCP validation requirements. Legacy dot-notation names are supported via backward compatibility aliases.

## Connection Management

### connections_list

List all configured database connections from `osiris_connections.yaml`.

**Tool Name**: `connections_list`
**Aliases**: `osiris.connections.list`, `connections.list`

**Input Schema:**
```json
{
  "type": "object",
  "properties": {}
}
```

**Output Schema:**
```json
{
  "type": "object",
  "properties": {
    "connections": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "family": {"type": "string"},
          "alias": {"type": "string"},
          "reference": {"type": "string"},
          "config": {"type": "object"}
        }
      }
    },
    "count": {"type": "integer"},
    "status": {"type": "string", "enum": ["success", "error"]}
  }
}
```

**Example Output:**
```json
{
  "connections": [
    {
      "family": "mysql",
      "alias": "db_movies",
      "reference": "@mysql.db_movies",
      "config": {
        "host": "test-api-to-mysql.cjtmwuzxk8bh.us-east-1.rds.amazonaws.com",
        "database": "padak",
        "default": true
      }
    },
    {
      "family": "supabase",
      "alias": "main",
      "reference": "@supabase.main",
      "config": {
        "url": "https://nedklmkgzjsyvqfxbmve.supabase.co",
        "default": true
      }
    }
  ],
  "count": 2,
  "status": "success"
}
```

### connections_doctor

Diagnose connection issues and validate configuration.

**Tool Name**: `connections_doctor`
**Aliases**: `osiris.connections.doctor`, `connections.doctor`

**Input Schema:**
```json
{
  "type": "object",
  "required": ["connection_id"],
  "properties": {
    "connection_id": {
      "type": "string",
      "description": "Connection reference (e.g., @mysql.default)"
    }
  }
}
```

**Output Schema:**
```json
{
  "type": "object",
  "properties": {
    "connection_id": {"type": "string"},
    "family": {"type": "string"},
    "alias": {"type": "string"},
    "health": {"type": "string", "enum": ["healthy", "unhealthy"]},
    "diagnostics": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "check": {"type": "string"},
          "status": {"type": "string", "enum": ["passed", "failed"]},
          "message": {"type": "string"},
          "severity": {"type": "string", "enum": ["error", "warning", "info"]}
        }
      }
    },
    "status": {"type": "string"}
  }
}
```

## Component Management

### components_list

List available pipeline components from the component registry.

**Tool Name**: `components_list`
**Aliases**: `osiris.components.list`, `components.list`

**Input Schema:**
```json
{
  "type": "object",
  "properties": {}
}
```

**Output Schema:**
```json
{
  "type": "object",
  "properties": {
    "components": {
      "type": "object",
      "properties": {
        "extractors": {"type": "array"},
        "writers": {"type": "array"},
        "processors": {"type": "array"},
        "other": {"type": "array"}
      }
    },
    "total_count": {"type": "integer"},
    "status": {"type": "string"}
  }
}
```

## Discovery

### discovery_request

Discover database schema with optional sampling and caching.

**Tool Name**: `discovery_request`
**Aliases**: `osiris.introspect_sources`, `discovery.request`

**Input Schema:**
```json
{
  "type": "object",
  "required": ["connection_id", "component_id"],
  "properties": {
    "connection_id": {
      "type": "string",
      "description": "Database connection ID"
    },
    "component_id": {
      "type": "string",
      "description": "Component ID for discovery"
    },
    "samples": {
      "type": "integer",
      "minimum": 0,
      "maximum": 100,
      "description": "Number of sample rows"
    },
    "idempotency_key": {
      "type": "string",
      "description": "Key for deterministic caching"
    }
  }
}
```

**Output Schema:**
```json
{
  "type": "object",
  "properties": {
    "discovery_id": {"type": "string"},
    "cached": {"type": "boolean"},
    "status": {"type": "string"},
    "artifacts": {
      "type": "object",
      "properties": {
        "overview": {"type": "string", "format": "uri"},
        "tables": {"type": "string", "format": "uri"},
        "samples": {"type": "string", "format": "uri"}
      }
    },
    "summary": {"type": "object"}
  }
}
```

## OML Operations

### oml_schema_get

Get OML v0.1.0 JSON schema.

**Tool Name**: `oml_schema_get`
**Aliases**: `osiris.oml.schema.get`, `oml.schema.get`

**Input Schema:**
```json
{
  "type": "object",
  "properties": {}
}
```

**Output Schema:**
```json
{
  "type": "object",
  "properties": {
    "schema_uri": {"type": "string", "format": "uri"},
    "version": {"type": "string"},
    "schema": {"type": "object"},
    "status": {"type": "string"}
  }
}
```

### oml_validate

Validate OML pipeline definition with ADR-0019 compatible diagnostics.

**Tool Name**: `oml_validate`
**Aliases**: `osiris.validate_oml`, `oml.validate`

**Input Schema:**
```json
{
  "type": "object",
  "required": ["oml_content"],
  "properties": {
    "oml_content": {
      "type": "string",
      "description": "OML YAML content"
    },
    "strict": {
      "type": "boolean",
      "default": true,
      "description": "Enable strict validation"
    }
  }
}
```

**Output Schema:**
```json
{
  "type": "object",
  "properties": {
    "valid": {"type": "boolean"},
    "diagnostics": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "type": {"type": "string", "enum": ["error", "warning", "info"]},
          "line": {"type": "integer"},
          "column": {"type": "integer"},
          "message": {"type": "string"},
          "id": {"type": "string"}
        }
      }
    },
    "summary": {
      "type": "object",
      "properties": {
        "errors": {"type": "integer"},
        "warnings": {"type": "integer"},
        "info": {"type": "integer"}
      }
    },
    "status": {"type": "string"}
  }
}
```

### oml_save

Save OML pipeline draft to session-scoped storage.

**Tool Name**: `oml_save`
**Aliases**: `osiris.save_oml`, `oml.save`

**Input Schema:**
```json
{
  "type": "object",
  "required": ["oml_content", "session_id"],
  "properties": {
    "oml_content": {
      "type": "string",
      "description": "OML YAML content"
    },
    "session_id": {
      "type": "string",
      "description": "Session identifier"
    },
    "filename": {
      "type": "string",
      "description": "Optional filename"
    }
  }
}
```

**Output Schema:**
```json
{
  "type": "object",
  "properties": {
    "saved": {"type": "boolean"},
    "uri": {"type": "string", "format": "uri"},
    "filename": {"type": "string"},
    "session_id": {"type": "string"},
    "timestamp": {"type": "string", "format": "date-time"},
    "status": {"type": "string"}
  }
}
```

## Guidance

### guide_start

Get guided next steps for OML authoring based on current context.

**Tool Name**: `guide_start`
**Aliases**: `osiris.guide_start`, `guide.start`

**Input Schema:**
```json
{
  "type": "object",
  "required": ["intent"],
  "properties": {
    "intent": {
      "type": "string",
      "description": "User's intent or goal"
    },
    "known_connections": {
      "type": "array",
      "items": {"type": "string"},
      "description": "List of known connection IDs"
    },
    "has_discovery": {
      "type": "boolean",
      "description": "Whether discovery has been performed"
    },
    "has_previous_oml": {
      "type": "boolean",
      "description": "Whether there's a previous OML draft"
    },
    "has_error_report": {
      "type": "boolean",
      "description": "Whether there's an error report"
    }
  }
}
```

**Output Schema:**
```json
{
  "type": "object",
  "properties": {
    "objective": {"type": "string"},
    "next_step": {"type": "string"},
    "example": {
      "type": "object",
      "properties": {
        "tool": {"type": "string"},
        "arguments": {"type": "object"},
        "description": {"type": "string"}
      }
    },
    "references": {
      "type": "array",
      "items": {"type": "string", "format": "uri"}
    },
    "context": {"type": "object"},
    "tips": {
      "type": "array",
      "items": {"type": "string"}
    },
    "status": {"type": "string"}
  }
}
```

## Memory

### memory_capture

Capture session memory with consent and PII redaction.

**Tool Name**: `memory_capture`
**Aliases**: `osiris.memory.capture`, `memory.capture`

**Input Schema:**
```json
{
  "type": "object",
  "required": ["consent", "session_id", "intent"],
  "properties": {
    "consent": {
      "type": "boolean",
      "description": "User consent for capture"
    },
    "retention_days": {
      "type": "integer",
      "default": 365,
      "description": "Days to retain memory"
    },
    "session_id": {"type": "string"},
    "actor_trace": {"type": "array"},
    "intent": {"type": "string"},
    "decisions": {"type": "array"},
    "artifacts": {"type": "array"},
    "oml_uri": {"type": ["string", "null"]},
    "error_report": {"type": ["object", "null"]},
    "notes": {"type": "string"}
  }
}
```

**Output Schema:**
```json
{
  "type": "object",
  "properties": {
    "captured": {"type": "boolean"},
    "memory_uri": {"type": "string", "format": "uri"},
    "session_id": {"type": "string"},
    "timestamp": {"type": "string", "format": "date-time"},
    "entry_size_bytes": {"type": "integer"},
    "redactions_applied": {"type": "integer"},
    "status": {"type": "string"}
  }
}
```

## Use Cases

### usecases_list

List OML use case templates with examples and requirements.

**Tool Name**: `usecases_list`
**Aliases**: `osiris.usecases.list`, `usecases.list`

**Input Schema:**
```json
{
  "type": "object",
  "properties": {}
}
```

**Output Schema:**
```json
{
  "type": "object",
  "properties": {
    "usecases": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": {"type": "string"},
          "name": {"type": "string"},
          "description": {"type": "string"},
          "category": {"type": "string"},
          "tags": {"type": "array"},
          "difficulty": {"type": "string"},
          "snippet_uri": {"type": "string", "format": "uri"},
          "requirements": {"type": "object"},
          "example": {"type": "object"}
        }
      }
    },
    "by_category": {"type": "object"},
    "total_count": {"type": "integer"},
    "categories": {"type": "array"},
    "status": {"type": "string"}
  }
}
```

## Tool Naming and Aliases

### Current Names (v0.5.0+)

All tools use underscore-separated names to comply with MCP validation pattern `^[a-zA-Z0-9_-]{1,64}$`:

- `connections_list`
- `connections_doctor`
- `components_list`
- `discovery_request`
- `usecases_list`
- `oml_schema_get`
- `oml_validate`
- `oml_save`
- `guide_start`
- `memory_capture`

### Backward Compatibility Aliases

The server provides comprehensive backward compatibility through alias resolution:

#### Osiris-Prefixed Names (ADR-0036)
- `osiris.connections.list` → `connections_list`
- `osiris.connections.doctor` → `connections_doctor`
- `osiris.components.list` → `components_list`
- `osiris.introspect_sources` → `discovery_request`
- `osiris.usecases.list` → `usecases_list`
- `osiris.oml.schema.get` → `oml_schema_get`
- `osiris.validate_oml` → `oml_validate`
- `osiris.save_oml` → `oml_save`
- `osiris.guide_start` → `guide_start`
- `osiris.memory.capture` → `memory_capture`

#### Dot-Notation Names (Pre-0.5.0)
- `connections.list` → `connections_list`
- `connections.doctor` → `connections_doctor`
- `components.list` → `components_list`
- `discovery.request` → `discovery_request`
- `usecases.list` → `usecases_list`
- `oml.schema.get` → `oml_schema_get`
- `oml.validate` → `oml_validate`
- `oml.save` → `oml_save`
- `guide.start` → `guide_start`
- `memory.capture` → `memory_capture`

All aliases accept the same input schemas and return the same output schemas as their primary tool names.

## Migration Guide

### From v0.4.x to v0.5.0

**Breaking Change**: Tool names changed from dot-notation to underscore-notation.

**Action Required**: None for most users - backward compatibility aliases are automatically applied.

**Recommended**: Update code/docs to use new underscore names:

```python
# Old (still works via alias)
await client.call_tool("connections.list", {})

# New (recommended)
await client.call_tool("connections_list", {})
```

**Claude Desktop**: Restart after update to pick up new tool names. No config changes needed.
