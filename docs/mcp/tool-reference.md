# MCP Tool Reference

This document provides detailed input/output schemas for all MCP tools in Osiris v0.5.0.

## Connection Management

### osiris.connections.list

List all configured database connections.

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

### osiris.connections.doctor

Diagnose connection issues.

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

### osiris.components.list

List available pipeline components.

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

### osiris.introspect_sources

Discover database schema with caching.

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

### osiris.oml.schema.get

Get OML v0.1.0 JSON schema.

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

### osiris.validate_oml

Validate OML pipeline definition.

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

### osiris.save_oml

Save OML pipeline draft.

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

### osiris.guide_start

Get guided next steps for OML authoring.

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

### osiris.memory.capture

Capture session memory with consent.

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

### osiris.usecases.list

List OML use case templates.

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

## Tool Aliases

The following aliases are provided for backward compatibility:

- `discovery.request` → `osiris.introspect_sources`
- `guide.start` → `osiris.guide_start`
- `oml.validate` → `osiris.validate_oml`
- `oml.save` → `osiris.save_oml`

All aliases accept the same input and return the same output as their primary tools.