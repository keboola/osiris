# State Management Issues - Osiris Codebase

**Detection Date:** 2025-10-16
**Detection Method:** Systematic agent-based code analysis
**Total Issues Found:** 15 (2 Critical, 5 High, 6 Medium, 2 Low)

---

## Executive Summary

A systematic review of state management revealed **15 concurrency and consistency issues**, with **2 critical race conditions** that can corrupt audit logs and telemetry data. Key findings:

- **Race Conditions:** Audit logger creates new locks per-call, telemetry metrics unprotected
- **Global State:** 4 global singletons modified without thread-safety
- **Resource Leaks:** Session stores and state history never cleaned up
- **Cache Coherency:** Memory and disk caches can diverge

**Impact:** Multi-threaded CLI commands or concurrent MCP requests will experience data corruption, memory leaks, and inconsistent state.

---

## CRITICAL Issues

### BUG-STATE-001: Race Condition in Audit Logger File Writing

**Severity:** CRITICAL
**File:** `/Users/padak/github/osiris/osiris/mcp/audit.py:257-259`
**Category:** Concurrency bug - race condition

**Current Code:**
```python
async def _write_event(self, event: dict[str, Any]):
    try:
        # Append to JSONL file
        async with asyncio.Lock():  # ← NEW lock created each time!
            with open(self.log_file, "a") as f:
                f.write(json.dumps(event) + "\n")
```

**Problem:**
- `asyncio.Lock()` creates a **NEW** lock instance on every call
- Each invocation of `_write_event()` creates its own lock
- Multiple concurrent calls ignore each other's locks
- Result: JSON writes interleave, corrupting the audit log

**Attack Surface:** Multiple concurrent MCP tool calls will interleave JSON writes

**Failure Scenario:**
```
Thread 1: async with Lock_A:  # Thread 1's lock
Thread 2: async with Lock_B:  # Thread 2's lock (different!)
Thread 1:   f.write('{"event": "tool_call"}\n')
Thread 2:   f.write('{"event": "error"}\n')  # INTERLEAVED!
Result: {"event": "tool_call"}
{"event": "er  ← CORRUPTED!
ror"}
\n
```

**Impact:**
- Audit log integrity violated
- Unable to recover tool call sequence
- Compliance audit trail corrupted
- Security forensics impossible

**Recommended Fix:**
```python
def __init__(self, ...):
    self._write_lock = asyncio.Lock()  # Create once

async def _write_event(self, event):
    async with self._write_lock:  # Reuse same lock
        with open(self.log_file, "a") as f:
            f.write(json.dumps(event) + "\n")
```

**Priority:** P0 - Fix immediately

---

### BUG-STATE-002: Race Condition in Telemetry Metrics Accumulation

**Severity:** CRITICAL
**File:** `/Users/padak/github/osiris/osiris/mcp/telemetry.py:73-78`
**Category:** Concurrency bug - lost updates

**Current Code:**
```python
def emit_tool_call(self, tool: str, status: str, ...):
    if not self.enabled:
        return

    # Update metrics (UNPROTECTED)
    self.metrics["tool_calls"] += 1
    self.metrics["total_bytes_in"] += bytes_in
    self.metrics["total_bytes_out"] += bytes_out
    self.metrics["total_duration_ms"] += duration_ms
    if status == "error":
        self.metrics["errors"] += 1
```

**Problem:**
- `self.metrics` dictionary modified without any locking
- Multiple concurrent MCP tool invocations cause lost updates

**Example Race:**
```
Thread 1: reads metrics["tool_calls"] = 5
Thread 2: reads metrics["tool_calls"] = 5
Thread 1: writes metrics["tool_calls"] = 6
Thread 2: writes metrics["tool_calls"] = 6  # Lost update! Should be 7
```

**Attack Surface:** Any concurrent MCP server usage with simultaneous tool calls

**Impact:**
- Metrics become inaccurate (undercount actual usage)
- Performance analysis based on telemetry is unreliable
- Cannot accurately monitor tool call rates
- Billing/quota enforcement broken

**Recommended Fix:**
```python
def __init__(self, ...):
    self._metrics_lock = threading.Lock()

def emit_tool_call(self, ...):
    with self._metrics_lock:
        self.metrics["tool_calls"] += 1
        self.metrics["total_bytes_in"] += bytes_in
        # ... rest of updates
```

**Priority:** P0 - Fix immediately

---

## HIGH Priority Issues

### BUG-STATE-003: Unprotected Global Session State

**Severity:** HIGH
**File:** `/Users/padak/github/osiris/osiris/core/session_logging.py:441-452`
**Category:** Global state without locking

**Current Code:**
```python
_current_session: SessionContext | None = None

def set_current_session(session: SessionContext | None) -> None:
    global _current_session
    _current_session = session  # ← No lock!

def get_current_session() -> SessionContext | None:
    return _current_session  # ← Can read partially-written state
```

**Problem:**
- Global state modified without locks
- Multi-threaded CLI commands or concurrent MCP requests will mix sessions

**Race Scenarios:**
- Thread 1 starts setting new session
- Thread 2 reads partially-constructed session object
- Thread 3 clears session while Thread 1 is still using it

**Impact:**
- Session context mixed between concurrent operations
- Memory leaks if sessions not properly cleared
- State from one command bleeds into another
- Logs attributed to wrong session

**Related Files:**
- `/Users/padak/github/osiris/osiris/mcp/config.py:230-246` - `_config` global
- `/Users/padak/github/osiris/osiris/mcp/telemetry.py:200-222` - `_telemetry` global
- `/Users/padak/github/osiris/osiris/components/registry.py:472-491` - `_registry` global

**Recommended Fix:**
```python
import threading

_current_session: SessionContext | None = None
_session_lock = threading.Lock()

def set_current_session(session: SessionContext | None) -> None:
    global _current_session
    with _session_lock:
        _current_session = session

def get_current_session() -> SessionContext | None:
    with _session_lock:
        return _current_session
```

**Priority:** P1 - Affects multi-threaded usage

---

### BUG-STATE-004: Uninitialized State - Memory Leak in State History

**Severity:** HIGH
**File:** `/Users/padak/github/osiris/osiris/core/conversational_agent.py:95, 135-136`
**Category:** Memory leak

**Current Code:**
```python
def __init__(self, ...):
    self.state_stores = {}  # Session ID -> SQLiteStateStore
    self.current_state = ChatState.INIT
    self.state_history = []  # ← List created but never cleaned up
```

**Problem:**
- `state_history` accumulates indefinitely (no maximum size)
- No cleanup mechanism in `__del__` or `close()`
- Long-running conversational agent consumes unbounded memory

**Impact:**
- Memory leak in long-running chat sessions
- Eventually causes OOM errors
- Performance degradation over time

**Recommended Fix:**
```python
self.state_history = []  # Keep last 100 transitions
MAX_STATE_HISTORY = 100

def _transition_state(self, new_state):
    self.state_history.append((old_state, new_state))
    if len(self.state_history) > self.MAX_STATE_HISTORY:
        self.state_history.pop(0)  # FIFO
```

**Priority:** P1 - Memory leak

---

### BUG-STATE-005: Session State Stores Not Cleaned Up

**Severity:** HIGH
**File:** `/Users/padak/github/osiris/osiris/core/conversational_agent.py:184-187`
**Category:** Resource leak

**Current Code:**
```python
async def chat(self, user_message: str, session_id: str | None = None, ...):
    if session_id not in self.state_stores:
        self.state_stores[session_id] = SQLiteStateStore(session_id)  # ← Created but never destroyed

    state_store = self.state_stores[session_id]
    # ... never closed
```

**Problem:**
- SQLite connections leak (file handles + memory)
- `state_stores` dict grows unbounded
- No cleanup when session ends

**Attack Surface:** Long-running chat sessions create resource exhaustion

**Impact:**
- Eventually runs out of file handles
- Memory usage grows indefinitely
- SQLite database locks persist
- System instability

**Recommended Fix:**
```python
def cleanup_session(self, session_id: str):
    if session_id in self.state_stores:
        self.state_stores[session_id].close()
        del self.state_stores[session_id]

async def __del__(self):
    for store in self.state_stores.values():
        store.close()
```

**Priority:** P1 - Resource leak

---

### BUG-STATE-006: Cache Memory/Disk Divergence

**Severity:** MEDIUM-HIGH
**File:** `/Users/padak/github/osiris/osiris/mcp/cache.py:78-105`
**Category:** Cache coherency

**Current Code:**
```python
async def get(self, connection_id, component_id, ...):
    cache_key = self._generate_cache_key(...)

    # Check memory cache first
    if cache_key in self._memory_cache:
        entry = self._memory_cache[cache_key]
        if not self._is_expired(entry):
            return entry["data"]
        else:
            del self._memory_cache[cache_key]  # ← Delete from memory only

    # Check disk cache
    cache_file = self.cache_dir / f"{cache_key}.json"
    if cache_file.exists():
        # ... loads from disk, updates memory
```

**Problem:**
- Expired entries deleted from memory but not disk
- Next process sees stale disk cache
- `clear_expired()` deletes from disk but memory cache not updated atomically

**Race Condition:**
- Process A calls `clear_expired()`, deletes disk file
- Process A crashes before clearing memory
- Process B reads stale memory cache entry

**Impact:**
- Cache coherency violations
- Stale discovery data served to users
- Unpredictable cache behavior across processes

**Recommended Fix:**
```python
def _delete_cache_entry(self, cache_key):
    # Delete both atomically
    if cache_key in self._memory_cache:
        del self._memory_cache[cache_key]
    cache_file = self.cache_dir / f"{cache_key}.json"
    cache_file.unlink(missing_ok=True)
```

**Priority:** P1 - Data accuracy

---

### BUG-STATE-007: GlobalRegistry Session Context Race

**Severity:** MEDIUM
**File:** `/Users/padak/github/osiris/osiris/components/registry.py:475-491`
**Category:** Race condition in singleton

**Current Code:**
```python
def get_registry(..., session_context: SessionContext | None = None):
    global _registry
    if _registry is None:
        _registry = ComponentRegistry(root, session_context)
    elif session_context and not _registry.session_context:
        _registry.session_context = session_context  # ← No lock!
    return _registry
```

**Problem:**
- Multiple threads calling `get_registry()` simultaneously
- Non-deterministic final state

**Race:**
```
Thread 1: reads _registry.session_context is None
Thread 2: sets _registry.session_context to Context_B
Thread 1: sets _registry.session_context to Context_A (overwrites)
Final: Context_A (but Thread 2 expected Context_B)
```

**Impact:** Session context can be lost or mixed

**Recommended Fix:** Use thread-safe singleton pattern with lock

**Priority:** P2 - Affects multi-threaded usage

---

## MEDIUM Priority Issues

### BUG-STATE-008 through BUG-STATE-015

Additional issues documented:
- Session path fallback not persisted consistently
- Metrics dictionary not atomic
- Component cache mtime-based (misses rapid updates)
- Telemetry file handle churn
- PromptManager context cache not invalidated
- State transitions not validated

Full details in detection agent report.

---

## Summary Table

| Bug ID | Severity | Category | File | Thread-Safe |
|--------|----------|----------|------|-------------|
| STATE-001 | CRITICAL | Race - audit log | audit.py:257 | ❌ No |
| STATE-002 | CRITICAL | Race - metrics | telemetry.py:73 | ❌ No |
| STATE-003 | HIGH | Global state | session_logging.py:441 | ❌ No |
| STATE-004 | HIGH | Memory leak | conversational_agent.py:136 | N/A |
| STATE-005 | HIGH | Resource leak | conversational_agent.py:184 | N/A |
| STATE-006 | HIGH | Cache coherency | cache.py:78 | ❌ No |
| STATE-007 | MEDIUM | Singleton race | registry.py:475 | ❌ No |
| STATE-008-015 | MEDIUM/LOW | Various | (multiple) | Mixed |

---

## Recommended Fix Priority

**Phase 1 (P0 - Critical):**
1. STATE-001: Fix audit logger lock (instance variable)
2. STATE-002: Add threading.Lock() to telemetry metrics

**Phase 2 (P1 - High):**
3. STATE-003: Add locks to all global state (session, config, telemetry, registry)
4. STATE-004: Implement state_history size limit and cleanup
5. STATE-005: Add session cleanup/close mechanisms
6. STATE-006: Make cache invalidation atomic

**Phase 3 (P2 - Medium):**
7. STATE-007 through STATE-015: Code quality improvements

---

## Testing Strategy

- Add concurrent access tests for all global state
- Test with multiple threads accessing same agent/config/registry
- Verify cache coherency across processes
- Stress test with rapid tool invocations
- Monitor for resource leaks (file handles, memory) in long-running scenarios

---

## References

- Main bug report: `docs/security/ARCHITECTURAL_BUGS_2025-10-16.md`
- Detection methodology: `docs/security/AGENT_SEARCH_GUIDE.md`
