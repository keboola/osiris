# E2B Transparent Proxy Prototype

This prototype validates the transparent proxy architecture for E2B execution, demonstrating JSON-RPC communication between host and worker.

## Files

- `proxy_worker.py` - Worker that runs inside E2B sandbox (or locally)
- `local_prototype.py` - Local demonstration of JSON-RPC pattern (no E2B required)
- `fake_orchestrator.py` - E2B version (requires E2B_API_KEY and e2b-code-interpreter)

## Quick Start

### Local Prototype (No E2B Required)

```bash
python local_prototype.py
```

This demonstrates:
- JSON-RPC command/response pattern over stdin/stdout
- Event and metric streaming
- Session state management
- Host-side log collection

### E2B Prototype (Requires API Key and SDK)

```bash
# Install E2B SDK if not already installed
pip install e2b-code-interpreter

# Set your API key
export E2B_API_KEY="your-key-here"

# Run the prototype
python fake_orchestrator.py
```

## Key Concepts Validated

### 1. JSON-RPC Protocol ✅

Commands and responses flow over stdin/stdout:

```json
// Host → Worker (stdin)
{"cmd": "prepare", "session_id": "run_123", "manifest": {...}}

// Worker → Host (stdout)  
{"status": "ready", "session_id": "run_123"}
```

### 2. Event Streaming ✅

Events stream in real-time as execution progresses:

```json
{"type": "event", "name": "step_start", "data": {"step_id": "extract-data"}}
{"type": "metric", "name": "rows_processed", "value": 42}
```

### 3. Session State Management ✅

Worker maintains session state across commands:
- Session ID preserved
- Step counter incremented
- Configuration retained

### 4. Log Collection ✅

Host writes events and metrics to structured log files:
- `events.jsonl` - All events with timestamps
- `metrics.jsonl` - All metrics with values

## Prototype Output

```
🚀 Starting Local Transparent Proxy Prototype

1️⃣ Starting ProxyWorker subprocess...
✅ ProxyWorker started

2️⃣ Sending test commands:

→ Sending PING...
   Response: {'status': 'pong', 'echo': 'test-123'}

→ Sending PREPARE...
   📊 Event: session_initialized
   📈 Metric: steps_total = 3
   Response: {'status': 'ready', 'session_id': 'local_proto_123'}

→ Sending EXEC_STEP for step-1...
   📊 Event: step_start
   📈 Metric: rows_processed = 42
   📊 Event: step_complete
   Response: {'status': 'complete', 'step_id': 'step-1'}

3️⃣ Collected logs:
📊 Events (9 total)
📈 Metrics (7 total)

✅ Prototype completed successfully!
```

## Next Steps

With the prototype validated, we can proceed with the full implementation:

1. **Implement ProxyWorker** with real driver execution
2. **Create E2BTransparentProxy** adapter using AsyncSandbox
3. **Integrate** with ExecutionAdapter interface
4. **Test** with real pipelines

## Key Advantages Confirmed

- ✅ **No nested sessions** - Single session ID throughout
- ✅ **Deterministic logging** - Events/metrics in correct order
- ✅ **Simple protocol** - JSON over stdio, no WebSocket complexity
- ✅ **State preservation** - Worker maintains context across commands
- ✅ **Real-time streaming** - Events flow as they happen
