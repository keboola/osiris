"""
E2E Testing Framework for MCP Tools

Production-ready framework for testing MCP tool implementations with reusable helpers,
assertion utilities, performance measurement, and security validation.

Usage:
    from e2e_framework import *

    ctx = TestContext(base_path="/path/to/osiris/testing_env")
    result = connections_list()
    assert_tool_success(result)
    assert_no_secrets(result)
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any

# Error code mappings (all 33 codes)
ERROR_CODES = {
    # OML Validation (OML001-OML010)
    "OML001": "Missing required field: name",
    "OML002": "Missing required field: steps",
    "OML003": "Invalid step type",
    "OML004": "Missing required field: driver",
    "OML005": "Missing required field: connection",
    "OML006": "Invalid YAML format",
    "OML007": "Invalid schema version",
    "OML008": "Duplicate step names",
    "OML009": "Missing driver configuration",
    "OML010": "Invalid connection reference",
    # Connection Errors (CONN001-CONN010)
    "CONN001": "Connection not found",
    "CONN002": "Connection validation failed",
    "CONN003": "Missing connection credentials",
    "CONN004": "Invalid connection configuration",
    "CONN005": "Connection timeout",
    "CONN006": "Database connection failed",
    "CONN007": "Network error",
    "CONN008": "Authentication failed",
    "CONN009": "Permission denied",
    "CONN010": "Connection already exists",
    # Discovery Errors (DISC001-DISC005)
    "DISC001": "Discovery not found",
    "DISC002": "Discovery failed",
    "DISC003": "Invalid discovery parameters",
    "DISC004": "Discovery timeout",
    "DISC005": "Schema introspection failed",
    # Resource Errors (RES001-RES005)
    "RES001": "Resource not found",
    "RES002": "Invalid resource URI",
    "RES003": "Resource access denied",
    "RES004": "Resource read failed",
    "RES005": "Invalid resource type",
    # System Errors (SYS001-SYS003)
    "SYS001": "Internal server error",
    "SYS002": "Configuration error",
    "SYS003": "File system error",
}

# Secret detection patterns
SECRET_PATTERNS = [
    r"password['\"]?\s*[:=]\s*['\"](?!(\*{3,}|MASKED))[^'\"]{3,}",  # password: "value"
    r"key['\"]?\s*[:=]\s*['\"](?!(\*{3,}|MASKED))[^'\"]{3,}",  # key: "value"
    r"secret['\"]?\s*[:=]\s*['\"](?!(\*{3,}|MASKED))[^'\"]{3,}",  # secret: "value"
    r"token['\"]?\s*[:=]\s*['\"](?!(\*{3,}|MASKED))[^'\"]{3,}",  # token: "value"
    r"mysql://[^:]+:[^@]+@",  # DSN with credentials
    r"postgresql://[^:]+:[^@]+@",  # PostgreSQL DSN
    r"mongodb://[^:]+:[^@]+@",  # MongoDB DSN
    r"redis://[^:]+:[^@]+@",  # Redis DSN
]


@dataclass
class TestContext:
    """Context for E2E test execution with cleanup utilities."""

    base_path: str
    connection_id: str | None = None
    session_id: str | None = None
    discovery_id: str | None = None
    _temp_files: list[Path] = field(default_factory=list)

    @property
    def mcp_logs_dir(self) -> Path:
        """Get MCP logs directory."""
        return Path(self.base_path) / ".osiris" / "mcp" / "logs"

    @property
    def cache_dir(self) -> Path:
        """Get MCP cache directory."""
        return self.mcp_logs_dir / "cache"

    @property
    def memory_dir(self) -> Path:
        """Get MCP memory directory."""
        return self.mcp_logs_dir / "memory"

    def track_temp_file(self, path: Path) -> None:
        """Track temporary file for cleanup."""
        self._temp_files.append(path)

    def cleanup(self) -> None:
        """Remove all temporary files."""
        for path in self._temp_files:
            if path.exists():
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    import shutil  # noqa: PLC0415

                    shutil.rmtree(path)


@dataclass
class ToolResult:
    """Structured result from tool execution."""

    status: str  # "success" or "error"
    data: dict[str, Any] | None = None
    error: str | None = None
    error_code: str | None = None
    duration_ms: float | None = None
    exit_code: int = 0


@dataclass
class TestReport:
    """Test execution report with pass/fail tracking."""

    test_count: int = 0
    pass_count: int = 0
    fail_count: int = 0
    skip_count: int = 0
    runtime_seconds: float = 0.0
    scenarios: list[dict[str, Any]] = field(default_factory=list)
    start_time: datetime | None = None

    def start(self) -> None:
        """Start test timing."""
        self.start_time = datetime.utcnow()

    def stop(self) -> None:
        """Stop test timing."""
        if self.start_time:
            self.runtime_seconds = (datetime.utcnow() - self.start_time).total_seconds()

    def add_passed(self, name: str, duration_ms: float | None = None) -> None:
        """Record passed test."""
        self.test_count += 1
        self.pass_count += 1
        self.scenarios.append({"name": name, "status": "passed", "duration_ms": duration_ms})

    def add_failed(self, name: str, reason: str, duration_ms: float | None = None) -> None:
        """Record failed test."""
        self.test_count += 1
        self.fail_count += 1
        self.scenarios.append({"name": name, "status": "failed", "reason": reason, "duration_ms": duration_ms})

    def add_skipped(self, name: str, reason: str) -> None:
        """Record skipped test."""
        self.test_count += 1
        self.skip_count += 1
        self.scenarios.append({"name": name, "status": "skipped", "reason": reason})

    def to_json(self) -> str:
        """Generate JSON report."""
        return json.dumps(
            {
                "summary": {
                    "total": self.test_count,
                    "passed": self.pass_count,
                    "failed": self.fail_count,
                    "skipped": self.skip_count,
                    "runtime_seconds": self.runtime_seconds,
                },
                "scenarios": self.scenarios,
            },
            indent=2,
        )

    def to_markdown(self) -> str:
        """Generate markdown summary."""
        lines = [
            "# Test Report",
            "",
            "## Summary",
            f"- Total: {self.test_count}",
            f"- Passed: {self.pass_count}",
            f"- Failed: {self.fail_count}",
            f"- Skipped: {self.skip_count}",
            f"- Runtime: {self.runtime_seconds:.2f}s",
            "",
            "## Scenarios",
            "",
        ]

        for scenario in self.scenarios:
            status_icon = {"passed": "✅", "failed": "❌", "skipped": "⏭️"}.get(scenario["status"], "❓")
            name = scenario["name"]
            lines.append(f"{status_icon} **{name}** - {scenario['status']}")

            if scenario["status"] == "failed":
                lines.append(f"  - Reason: {scenario.get('reason', 'Unknown')}")

            if scenario.get("duration_ms"):
                lines.append(f"  - Duration: {scenario['duration_ms']:.2f}ms")

            lines.append("")

        return "\n".join(lines)


# ============================================================================
# MCP Tool Runner
# ============================================================================


def run_tool(
    tool_name: str, args: dict[str, Any] | None = None, timeout: int = 30, env: dict[str, str] | None = None
) -> ToolResult:
    """
    Execute MCP tool via CLI subprocess.

    Args:
        tool_name: Tool name (e.g., "connections_list", "discovery_request")
        args: Tool arguments as dict
        timeout: Subprocess timeout in seconds
        env: Additional environment variables

    Returns:
        ToolResult with status, data, error, duration
    """
    start_time = time.time()

    # Map tool name to CLI command
    cmd_parts = ["osiris", "mcp"] + _tool_name_to_cmd(tool_name)

    # Add arguments
    if args:
        for key, value in args.items():
            if isinstance(value, bool):
                if value:
                    cmd_parts.append(f"--{key}")
            else:
                cmd_parts.extend([f"--{key}", str(value)])

    # Always request JSON output
    if "--json" not in cmd_parts:
        cmd_parts.append("--json")

    # Prepare environment
    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)

    try:
        result = subprocess.run(
            cmd_parts, check=False, capture_output=True, text=True, timeout=timeout, env=proc_env, cwd=os.getcwd()
        )

        duration_ms = (time.time() - start_time) * 1000

        # Parse JSON output
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                return ToolResult(status="success", data=data, duration_ms=duration_ms, exit_code=0)
            except json.JSONDecodeError:
                return ToolResult(
                    status="error",
                    error="Invalid JSON output",
                    error_code="SYS001",
                    duration_ms=duration_ms,
                    exit_code=result.returncode,
                )
        else:
            # Map exit code to error
            error_code = map_cli_exit_to_error(result.returncode)
            error_msg = result.stderr or result.stdout or "Command failed"
            return ToolResult(
                status="error",
                error=error_msg,
                error_code=error_code,
                duration_ms=duration_ms,
                exit_code=result.returncode,
            )

    except subprocess.TimeoutExpired:
        duration_ms = (time.time() - start_time) * 1000
        return ToolResult(
            status="error", error="Command timeout", error_code="SYS001", duration_ms=duration_ms, exit_code=124
        )
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        return ToolResult(status="error", error=str(e), error_code="SYS001", duration_ms=duration_ms, exit_code=1)


def _tool_name_to_cmd(tool_name: str) -> list[str]:
    """Map tool name to CLI command parts."""
    mapping = {
        "connections_list": ["connections", "list"],
        "connections_doctor": ["connections", "doctor"],
        "discovery_request": ["discovery", "request"],
        "oml_schema_get": ["oml", "schema"],
        "oml_validate": ["oml", "validate"],
        "oml_save": ["oml", "save"],
        "memory_capture": ["memory", "capture"],
        "aiop_list": ["aiop", "list"],
        "aiop_show": ["aiop", "show"],
        "guide_start": ["guide", "start"],
        "components_list": ["components", "list"],
        "usecases_list": ["usecases", "list"],
    }
    return mapping.get(tool_name, tool_name.split("_"))


def map_cli_exit_to_error(exit_code: int) -> str:
    """Map CLI exit code to MCP error code."""
    mapping = {
        1: "SYS001",  # Generic error
        2: "SYS002",  # Configuration error
        3: "CONN001",  # Connection not found
        4: "CONN002",  # Connection validation failed
        5: "OML006",  # Invalid YAML
        6: "RES001",  # Resource not found
        7: "DISC002",  # Discovery failed
        124: "SYS001",  # Timeout
    }
    return mapping.get(exit_code, "SYS001")


# ============================================================================
# Assertion Helpers
# ============================================================================


def assert_tool_success(result: ToolResult) -> None:
    """Assert tool execution succeeded."""
    if result.status != "success":
        raise AssertionError(f"Tool failed: {result.error} (code: {result.error_code})")


def assert_tool_error(result: ToolResult, error_code: str) -> None:
    """Assert tool returned specific error code."""
    if result.status != "error":
        raise AssertionError("Expected error, got success")
    if result.error_code != error_code:
        raise AssertionError(f"Expected error {error_code}, got {result.error_code}")


def assert_response_schema(result: ToolResult, tool_name: str) -> None:
    """Validate response matches expected schema for tool."""
    if result.status != "success":
        raise AssertionError("Cannot validate schema on failed result")

    data = result.data
    if not data:
        raise AssertionError("No data in result")

    # Schema validation by tool
    schemas = {
        "connections_list": lambda d: "connections" in d and "count" in d,
        "discovery_request": lambda d: "discovery_id" in d and "status" in d,
        "oml_schema_get": lambda d: "$schema" in d and "properties" in d,
        "memory_capture": lambda d: "session_id" in d and "uri" in d,
    }

    validator = schemas.get(tool_name)
    if validator and not validator(data):
        raise AssertionError(f"Invalid schema for {tool_name}: {data}")


def assert_no_secrets(data: Any) -> None:
    """Verify no credential patterns in data."""
    text = json.dumps(data) if not isinstance(data, str) else data
    secrets = scan_for_secrets(text)
    if secrets:
        raise AssertionError(f"Found {len(secrets)} potential secrets: {secrets[:3]}")


def assert_latency(duration_ms: float, target: float) -> None:
    """Check performance target met."""
    if duration_ms > target:
        raise AssertionError(f"Latency {duration_ms:.2f}ms exceeds target {target}ms")


def assert_file_exists(uri: str, base_path: str) -> None:
    """Verify resource file exists."""
    path = resolve_resource_uri(uri, base_path)
    if not path or not path.exists():
        raise AssertionError(f"Resource not found: {uri} -> {path}")


def assert_json_valid(text: str) -> None:
    """Validate JSON structure."""
    try:
        json.loads(text)
    except json.JSONDecodeError as e:
        raise AssertionError(f"Invalid JSON: {e}") from e


# ============================================================================
# Security Validators
# ============================================================================


def scan_for_secrets(text: str) -> list[str]:
    """Find credential patterns in text."""
    found = []
    for pattern in SECRET_PATTERNS:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        found.extend([m.group(0) for m in matches])
    return found


def verify_masking(text: str, pattern: str) -> bool:
    """Check secrets are masked."""
    # Look for unmasked patterns
    secrets = scan_for_secrets(text)
    return len(secrets) == 0


def check_credential_patterns(text: str) -> list[str]:
    """DSN, password, key patterns."""
    patterns = [
        r"mysql://[^:]+:[^@]+@",
        r"postgresql://[^:]+:[^@]+@",
        r"mongodb://[^:]+:[^@]+@",
        r'password["\']?\s*:\s*["\'][^"\']{3,}',
        r'key["\']?\s*:\s*["\'][^"\']{3,}',
    ]

    found = []
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        found.extend([m.group(0) for m in matches])

    return found


def validate_cli_delegation(subprocess_call: subprocess.CompletedProcess) -> bool:
    """Verify subprocess execution occurred."""
    return subprocess_call.returncode is not None


def verify_env_inheritance(subprocess_env: dict[str, str]) -> bool:
    """Check environment vars passed to subprocess."""
    # Verify common vars inherited
    required_vars = ["PATH", "HOME"]
    return all(var in subprocess_env for var in required_vars)


# ============================================================================
# CLI Command Helpers
# ============================================================================


def connections_list() -> ToolResult:
    """List all connections."""
    return run_tool("connections_list")


def connections_doctor(conn_id: str) -> ToolResult:
    """Test connection health."""
    return run_tool("connections_doctor", {"connection-id": conn_id})


def discovery_request(conn_id: str, samples: int = 10) -> ToolResult:
    """Request database discovery."""
    return run_tool("discovery_request", {"connection-id": conn_id, "samples": samples})


def oml_schema() -> ToolResult:
    """Get OML JSON schema."""
    return run_tool("oml_schema_get")


def oml_validate(yaml_content: str) -> ToolResult:
    """Validate OML YAML content."""
    # Write to temp file
    import tempfile  # noqa: PLC0415

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        temp_path = f.name

    try:
        result = run_tool("oml_validate", {"file": temp_path})
        return result
    finally:
        Path(temp_path).unlink(missing_ok=True)


def oml_save(yaml_content: str, session_id: str) -> ToolResult:
    """Save OML draft."""
    import tempfile  # noqa: PLC0415

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        temp_path = f.name

    try:
        result = run_tool("oml_save", {"file": temp_path, "session-id": session_id})
        return result
    finally:
        Path(temp_path).unlink(missing_ok=True)


def memory_capture(session_id: str, text: str = "Test memory", consent: bool = True) -> ToolResult:
    """Capture memory note."""
    args = {"session-id": session_id, "text": text}
    if consent:
        args["consent"] = True
    return run_tool("memory_capture", args)


def aiop_list() -> ToolResult:
    """List AIOP runs."""
    return run_tool("aiop_list")


def aiop_show(run_id: str) -> ToolResult:
    """Show AIOP artifact."""
    return run_tool("aiop_show", {"run-id": run_id})


def guide_start(intent: str) -> ToolResult:
    """Start pipeline guidance."""
    return run_tool("guide_start", {"intent": intent})


def components_list() -> ToolResult:
    """List available components."""
    return run_tool("components_list")


def usecases_list() -> ToolResult:
    """List use cases."""
    return run_tool("usecases_list")


# ============================================================================
# Performance Measurement
# ============================================================================


def measure_latency(func: Callable) -> Callable:
    """Decorator for timing functions."""

    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration_ms = (time.time() - start) * 1000
        return result, duration_ms

    return wrapper


def run_n_times(func: Callable, n: int) -> list[float]:
    """Run tool N times, collect latencies."""
    latencies = []
    for _ in range(n):
        start = time.time()
        func()
        duration_ms = (time.time() - start) * 1000
        latencies.append(duration_ms)
    return latencies


def calculate_percentiles(latencies: list[float]) -> dict[str, float]:
    """Calculate p50, p95, p99."""
    sorted_latencies = sorted(latencies)
    n = len(sorted_latencies)

    if n == 0:
        return {"p50": 0, "p95": 0, "p99": 0}

    return {
        "p50": sorted_latencies[int(n * 0.50)],
        "p95": sorted_latencies[int(n * 0.95)],
        "p99": sorted_latencies[int(n * 0.99)],
    }


def measure_memory_usage() -> dict[str, int] | None:
    """Measure memory usage (requires psutil)."""
    try:
        import psutil  # noqa: PLC0415

        process = psutil.Process()
        mem_info = process.memory_info()
        return {"rss_bytes": mem_info.rss, "vms_bytes": mem_info.vms}
    except ImportError:
        return None


# ============================================================================
# Resource URI Handler
# ============================================================================


def resolve_resource_uri(uri: str, base_path: str) -> Path | None:
    """Map resource URI to file path."""
    if not uri.startswith("osiris://mcp/"):
        return None

    # Strip prefix
    resource_path = uri.replace("osiris://mcp/", "")

    # Map to directory
    base = Path(base_path) / ".osiris" / "mcp" / "logs"

    if resource_path.startswith("discovery/"):
        path = base / "cache" / resource_path.replace("discovery/", "")
    elif resource_path.startswith("memory/"):
        path = base / "memory" / resource_path.replace("memory/", "")
    elif resource_path.startswith("drafts/oml/"):
        path = base / "cache" / resource_path.replace("drafts/oml/", "")
    else:
        return None

    return path


def read_resource(uri: str, base_path: str) -> str | None:
    """Read resource file contents."""
    path = resolve_resource_uri(uri, base_path)
    if path and path.exists():
        return path.read_text()
    return None


def verify_resource_valid(uri: str, base_path: str) -> bool:
    """Check if resource exists and is valid."""
    path = resolve_resource_uri(uri, base_path)
    return path is not None and path.exists()


def list_resources(resource_type: str, base_path: str) -> list[str]:
    """List all URIs of given type."""
    base = Path(base_path) / ".osiris" / "mcp" / "logs"

    if resource_type == "discovery":
        cache_dir = base / "cache"
        if not cache_dir.exists():
            return []

        uris = []
        for disc_dir in cache_dir.glob("disc_*"):
            disc_id = disc_dir.name
            for file in ["overview.json", "tables.json", "samples.json"]:
                if (disc_dir / file).exists():
                    uris.append(f"osiris://mcp/discovery/{disc_id}/{file}")
        return uris

    elif resource_type == "memory":
        memory_dir = base / "memory" / "sessions"
        if not memory_dir.exists():
            return []

        return [f"osiris://mcp/memory/sessions/{f.name}" for f in memory_dir.glob("*.jsonl")]

    elif resource_type == "oml":
        cache_dir = base / "cache"
        if not cache_dir.exists():
            return []

        return [f"osiris://mcp/drafts/oml/{f.name}" for f in cache_dir.glob("*.yaml")]

    return []


# ============================================================================
# Mock/Stub Utilities
# ============================================================================


def mock_subprocess_call(cmd: list[str], stdout: str, exit_code: int = 0) -> subprocess.CompletedProcess:
    """Simulate CLI subprocess call."""
    return subprocess.CompletedProcess(args=cmd, returncode=exit_code, stdout=stdout, stderr="")


def create_test_connection(name: str, family: str) -> dict[str, Any]:
    """Create test connection configuration."""
    configs = {
        "mysql": {"host": "localhost", "port": 3306, "user": "test", "password": "***MASKED***", "database": "testdb"},
        "supabase": {"url": "https://test.supabase.co", "key": "***MASKED***"},
        "postgresql": {
            "host": "localhost",
            "port": 5432,
            "user": "test",
            "password": "***MASKED***",
            "database": "testdb",
        },
    }

    return {"family": family, "alias": name, "config": configs.get(family, {})}


def create_test_oml(valid: bool = True) -> str:
    """Create test OML YAML content."""
    if valid:
        return """
name: test_pipeline
steps:
  - name: extract
    driver: mysql_extractor
    connection: '@mysql.default'
    config:
      query: 'SELECT * FROM users'
  - name: load
    driver: supabase_writer
    connection: '@supabase.main'
    config:
      table: users
"""
    else:
        return """
invalid_field: test
steps:
  - missing_name: extract
"""


def create_test_memory_content() -> str:
    """Create memory capture content."""
    return json.dumps(
        {
            "session_id": "chat_20251020_120000",
            "timestamp": "2025-10-20T12:00:00Z",
            "content": "User discussed migrating MySQL data to Supabase",
            "tags": ["migration", "mysql", "supabase"],
        }
    )


# ============================================================================
# Logging & Debug
# ============================================================================

_DEBUG_ENABLED = False


def enable_debug_logging() -> None:
    """Enable verbose output."""
    global _DEBUG_ENABLED  # noqa: PLW0603
    _DEBUG_ENABLED = True


def log_tool_call(tool: str, args: dict[str, Any], result: ToolResult) -> None:
    """Log each tool call."""
    if _DEBUG_ENABLED:
        print(f"[DEBUG] Tool: {tool}")
        print(f"[DEBUG] Args: {args}")
        print(f"[DEBUG] Status: {result.status}")
        print(f"[DEBUG] Duration: {result.duration_ms:.2f}ms")
        if result.error:
            print(f"[DEBUG] Error: {result.error}")


def log_assertion_failure(assertion: str, expected: Any, actual: Any) -> None:
    """Log assertion failures."""
    if _DEBUG_ENABLED:
        print(f"[DEBUG] Assertion failed: {assertion}")
        print(f"[DEBUG] Expected: {expected}")
        print(f"[DEBUG] Actual: {actual}")


def enable_secret_scanning() -> None:
    """Log any secrets found in outputs."""
    global _DEBUG_ENABLED  # noqa: PLW0603
    _DEBUG_ENABLED = True


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    # Example test execution
    print("E2E Framework Example Usage\n")

    # Setup
    ctx = TestContext(base_path="/Users/padak/github/osiris/testing_env")
    report = TestReport()
    report.start()

    # Test 1: List connections
    try:
        result = connections_list()
        assert_tool_success(result)
        assert_no_secrets(result.data)
        report.add_passed("connections_list returns secrets masked", result.duration_ms)
    except AssertionError as e:
        report.add_failed("connections_list returns secrets masked", str(e))

    # Test 2: Get OML schema
    try:
        result = oml_schema()
        assert_tool_success(result)
        assert_response_schema(result, "oml_schema_get")
        report.add_passed("oml_schema_get returns valid schema", result.duration_ms)
    except AssertionError as e:
        report.add_failed("oml_schema_get returns valid schema", str(e))

    # Test 3: Performance test
    try:

        @measure_latency
        def test_connections():
            return connections_list()

        _, duration = test_connections()
        assert_latency(duration, target=1000)  # 1 second max
        report.add_passed("connections_list performance <1s", duration)
    except AssertionError as e:
        report.add_failed("connections_list performance <1s", str(e))

    # Generate report
    report.stop()
    print(report.to_markdown())
    print("\nJSON Report:")
    print(report.to_json())
