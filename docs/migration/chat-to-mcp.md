# Migration Guide: Chat to MCP

This guide helps users and developers migrate from the legacy chat interface to the new MCP (Model Context Protocol) interface in Osiris v0.5.0.

## Overview of Changes

The legacy conversational chat interface has been replaced with a standardized MCP server that provides:
- Deterministic, single-shot tool calls instead of conversational state
- Structured error responses with consistent taxonomy
- Resource URIs under `osiris://mcp/` namespace
- Tool-based interaction model compatible with Claude Desktop and other MCP clients

## Key Differences

### Legacy Chat Interface
- Conversational state machine
- WebSocket/HTTP transport
- Session-based context
- Multi-turn dialogue
- Free-form text responses

### New MCP Interface
- Stateless tool calls
- stdio transport with JSON-RPC
- Idempotent operations
- Single-shot request/response
- Structured JSON responses

## Migration Mapping

### Chat Intent to MCP Tool Mapping

| Chat Intent | MCP Tool | Notes |
|------------|----------|-------|
| "Show me my database connections" | `osiris.connections.list` | Returns all configured connections |
| "Check if MySQL is working" | `osiris.connections.doctor` | Diagnose specific connection |
| "What components are available?" | `osiris.components.list` | List pipeline components |
| "Explore the users table" | `osiris.introspect_sources` | Discover schema with samples |
| "Show me pipeline examples" | `osiris.usecases.list` | Get use case templates |
| "Validate my pipeline" | `osiris.validate_oml` | Validate OML content |
| "Save this pipeline" | `osiris.save_oml` | Persist OML draft |
| "What should I do next?" | `osiris.guide_start` | Get guided recommendations |
| "Remember this session" | `osiris.memory.capture` | Capture session memory |

## Code Migration Examples

### Legacy Chat Session

```python
# OLD: Chat-based interaction
from osiris.chat import ChatSession

session = ChatSession()
session.start()
response = session.send_message("Show me all MySQL tables")
response = session.send_message("Extract data from users table")
pipeline = session.generate_pipeline()
```

### New MCP Client

```python
# NEW: MCP tool-based interaction
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

server_params = StdioServerParameters(
    command="python",
    args=["-m", "osiris.cli.mcp_entrypoint"]
)

async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()

        # List connections
        connections = await session.call_tool(
            "osiris.connections.list", {}
        )

        # Discover schema
        discovery = await session.call_tool(
            "osiris.introspect_sources", {
                "connection": "@mysql.default",
                "component": "mysql.extractor",
                "samples": 5
            }
        )

        # Validate OML
        validation = await session.call_tool(
            "osiris.validate_oml", {
                "oml_content": pipeline_yaml,
                "strict": True
            }
        )
```

## Workflow Migration

### Legacy Workflow: Interactive Pipeline Creation

1. Start chat session
2. Describe intent in natural language
3. AI discovers connections iteratively
4. Multi-turn refinement of requirements
5. Generate pipeline through conversation
6. Validate and save in chat context

### New Workflow: Tool-Based Pipeline Creation

1. Initialize MCP client
2. Call `osiris.guide_start` with intent
3. Execute recommended tools sequentially:
   - `osiris.connections.list` - discover available connections
   - `osiris.introspect_sources` - explore schema
   - `osiris.validate_oml` - validate draft
   - `osiris.save_oml` - persist pipeline
4. Use `osiris.memory.capture` to save session

## Error Handling Migration

### Legacy Error Handling

```python
# OLD: Unstructured error messages
try:
    response = session.send_message(query)
except ChatError as e:
    print(f"Chat error: {e.message}")
    # Retry logic based on error text
```

### New Error Handling

```python
# NEW: Structured error responses
result = await session.call_tool("osiris.validate_oml", args)
response = json.loads(result.content[0].text)

if not response.get("success", True):
    error = response["error"]
    print(f"Error code: {error['code']}")  # e.g., "SCHEMA/ABC123"
    print(f"Path: {error['path']}")        # ["field", "subfield"]
    print(f"Message: {error['message']}")
    if "suggest" in error:
        print(f"Suggestion: {error['suggest']}")
```

## Configuration Migration

### Legacy Configuration

```yaml
# .osiris.yaml
chat:
  model: gpt-4
  temperature: 0.7
  max_retries: 3
  session_timeout: 300
```

### New Configuration

```bash
# Environment variables
export OSIRIS_MCP_PAYLOAD_LIMIT_MB=16
export OSIRIS_MCP_CACHE_TTL_HOURS=24
export OSIRIS_MCP_TELEMETRY_ENABLED=true
export OSIRIS_HOME=/path/to/osiris/data
```

## Claude Desktop Integration

To use Osiris with Claude Desktop, add to your Claude configuration:

```json
{
  "mcpServers": {
    "osiris": {
      "command": "python",
      "args": ["-m", "osiris.cli.mcp_entrypoint"],
      "env": {
        "OSIRIS_HOME": "/Users/you/.osiris"
      }
    }
  }
}
```

Then in Claude:
- Use `@osiris` to invoke tools
- Tools appear in the tool palette
- Responses are structured and deterministic

## Deprecation Timeline

- **v0.5.0** (Current): MCP interface available, chat deprecated
- **v0.6.0** (Future): Chat interface removed entirely

## Common Migration Issues

### Issue: Multi-turn Context Lost

**Problem**: Chat maintained context across messages, MCP doesn't.

**Solution**: Use `osiris.memory.capture` to persist session data and pass context explicitly in tool calls.

### Issue: Free-form Queries Not Supported

**Problem**: Can't send arbitrary text to MCP server.

**Solution**: Use `osiris.guide_start` with intent to get structured guidance on which tools to use.

### Issue: No Streaming Responses

**Problem**: Chat provided streaming updates, MCP is request/response.

**Solution**: Use discovery caching and break large operations into smaller tool calls.

## Testing Migration

Run the self-test to verify MCP server functionality:

```bash
# Test MCP server
osiris mcp run --selftest

# Expected output:
# ✅ Handshake completed in X.XXXs (<2s requirement)
# ✅ connections.list responded successfully
# ✅ oml.schema.get returned valid schema
# ✅ Found N registered tools
```

## Support and Resources

- **Documentation**: [MCP Overview](../mcp/overview.md)
- **Tool Reference**: [Tool I/O Schemas](../mcp/tool-reference.md)
- **ADR**: [ADR-0036 MCP Interface](../adr/0036-mcp-interface.md)
- **Issues**: Report migration issues on GitHub

## Best Practices for MCP

1. **Always check tool availability first**
   ```python
   tools = await session.list_tools()
   available = [t.name for t in tools.tools]
   ```

2. **Handle structured errors properly**
   - Check `success` field
   - Parse error codes and paths
   - Follow suggestions when provided

3. **Use idempotency keys for determinism**
   ```python
   await session.call_tool("osiris.introspect_sources", {
       "connection": "@mysql.default",
       "component": "mysql.extractor",
       "idempotency_key": "discovery_123"
   })
   ```

4. **Respect payload limits**
   - Keep requests under 16MB
   - Use pagination for large results
   - Request only needed fields

5. **Leverage caching**
   - Discovery results cached for 24 hours
   - Use same parameters for cache hits
   - Clear cache when data changes

## Summary

The migration from chat to MCP represents a shift from conversational to tool-based interaction. While this requires adjusting workflows, it provides better reliability, determinism, and integration with AI assistants like Claude. The structured nature of MCP tools makes pipeline authoring more predictable and easier to automate.