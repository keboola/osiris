# Osiris Pipeline - Execution Adapter Development Guide

## Execution Adapter Contract

TODO: Document the ExecutionAdapter abstract base class:

### Core Interface
```python
# TODO: Complete interface documentation
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional

@dataclass
class ExecutionContext:
    """Execution context for adapters"""
    session_id: str
    session_dir: str
    verbose: bool
    timeout: int
    environment: Dict[str, str]

@dataclass
class PreparedRun:
    """Prepared execution package"""
    manifest: dict
    configs: Dict[str, dict]
    environment: Dict[str, str]
    artifacts_dir: str

class ExecutionAdapter(ABC):
    """Abstract base class for execution adapters"""

    @abstractmethod
    def prepare(self, manifest: dict, context: ExecutionContext) -> PreparedRun:
        """
        Prepare execution environment

        Args:
            manifest: Compiled pipeline manifest
            context: Execution context

        Returns:
            PreparedRun with all execution details
        """
        pass

    @abstractmethod
    def execute(self, prepared: PreparedRun, context: ExecutionContext) -> None:
        """
        Execute the pipeline

        Args:
            prepared: Prepared execution package
            context: Execution context

        Raises:
            ExecutionError: If execution fails
        """
        pass

    @abstractmethod
    def collect(self, prepared: PreparedRun, context: ExecutionContext) -> dict:
        """
        Collect execution results

        Args:
            prepared: Prepared execution package
            context: Execution context

        Returns:
            Execution results and metrics
        """
        pass
```

### Adapter Lifecycle
TODO: Document the three-phase lifecycle:

1. **Prepare Phase**
   - Validate manifest
   - Resolve connections
   - Create execution package
   - Set up environment

2. **Execute Phase**
   - Run pipeline steps
   - Emit events and metrics
   - Handle errors
   - Generate artifacts

3. **Collect Phase**
   - Gather artifacts
   - Summarize metrics
   - Create status report
   - Clean up resources

### Contract Requirements
TODO: Document adapter contract requirements:

#### Event Emission
- Must emit standardized events
- Event types: start, complete, error
- Include timestamps and session_id
- Structured JSON format

#### Metric Collection
- Track rows_read, rows_written
- Measure execution_time_ms
- Report memory_usage_mb
- Custom metrics allowed

#### Error Handling
- Graceful error recovery
- Detailed error messages
- Stack trace preservation
- Retry logic support

#### Artifact Management
- Preserve all outputs
- Maintain directory structure
- Handle binary files
- Compress if needed

## Local Adapter Example

TODO: Complete LocalAdapter implementation:

### Implementation
```python
# osiris/runtime/local_adapter.py

from osiris.core.execution_adapter import ExecutionAdapter
from osiris.core.driver import DriverRegistry
import json
import os

class LocalAdapter(ExecutionAdapter):
    """Local execution adapter using native drivers"""

    def __init__(self):
        self.driver_registry = DriverRegistry()
        self.data_cache = {}

    def prepare(self, manifest: dict, context: ExecutionContext) -> PreparedRun:
        """Prepare local execution environment"""
        # TODO: Complete implementation

        # Create artifacts directory
        artifacts_dir = os.path.join(context.session_dir, "artifacts")
        os.makedirs(artifacts_dir, exist_ok=True)

        # Resolve connections
        configs = {}
        for step in manifest["steps"]:
            config = self._resolve_config(step["config"])
            configs[step["id"]] = config

        # Prepare environment
        environment = self._prepare_environment(context.environment)

        return PreparedRun(
            manifest=manifest,
            configs=configs,
            environment=environment,
            artifacts_dir=artifacts_dir
        )

    def execute(self, prepared: PreparedRun, context: ExecutionContext) -> None:
        """Execute pipeline locally"""
        # TODO: Complete implementation

        for step in prepared.manifest["steps"]:
            step_id = step["id"]
            driver_name = step["driver"]
            config = prepared.configs[step_id]

            # Get driver
            driver = self.driver_registry.get(driver_name)

            # Prepare inputs
            inputs = self._resolve_inputs(step.get("inputs", {}))

            # Create step context
            step_ctx = self._create_step_context(step_id, context)

            # Execute driver
            try:
                self._emit_event("step.start", {"step_id": step_id})

                output = driver.run(step_id, config, inputs, step_ctx)

                # Cache output for downstream steps
                self.data_cache[step_id] = output

                self._emit_event("step.complete", {
                    "step_id": step_id,
                    "rows": output.get("rows", 0)
                })

            except Exception as e:
                self._emit_event("step.error", {
                    "step_id": step_id,
                    "error": str(e)
                })
                raise

    def collect(self, prepared: PreparedRun, context: ExecutionContext) -> dict:
        """Collect execution results"""
        # TODO: Complete implementation

        return {
            "status": "completed",
            "artifacts": self._list_artifacts(prepared.artifacts_dir),
            "metrics": self._summarize_metrics(),
            "environment": "local"
        }

    # Helper methods
    def _resolve_config(self, config: dict) -> dict:
        """Resolve configuration with connections"""
        # TODO: Implementation
        pass

    def _resolve_inputs(self, inputs: dict) -> dict:
        """Resolve symbolic input references"""
        # TODO: Implementation
        pass

    def _create_step_context(self, step_id: str, context: ExecutionContext):
        """Create context for step execution"""
        # TODO: Implementation
        pass

    def _emit_event(self, event_type: str, data: dict):
        """Emit structured event"""
        # TODO: Implementation
        pass
```

### Testing LocalAdapter
```python
# TODO: Test implementation
def test_local_adapter():
    adapter = LocalAdapter()
    manifest = load_manifest("test.yaml")
    context = ExecutionContext(
        session_id="test_123",
        session_dir="/tmp/test",
        verbose=True,
        timeout=300,
        environment={"MYSQL_PASSWORD": "test"}
    )

    # Test prepare phase
    prepared = adapter.prepare(manifest, context)
    assert prepared.configs

    # Test execute phase
    adapter.execute(prepared, context)

    # Test collect phase
    results = adapter.collect(prepared, context)
    assert results["status"] == "completed"
```

## E2B Adapter Example

TODO: Complete E2BTransparentProxy implementation:

### Implementation Overview
```python
# osiris/remote/e2b_transparent_proxy.py

from osiris.core.execution_adapter import ExecutionAdapter
from osiris.remote.rpc_protocol import RPCClient
from e2b import Sandbox
import json

class E2BTransparentProxy(ExecutionAdapter):
    """E2B cloud execution via transparent proxy"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.sandbox = None
        self.rpc_client = None

    def prepare(self, manifest: dict, context: ExecutionContext) -> PreparedRun:
        """Prepare E2B sandbox environment"""
        # TODO: Complete implementation

        # Create sandbox
        self.sandbox = Sandbox(
            api_key=self.api_key,
            cpu=4,
            memory_gb=8,
            timeout=context.timeout
        )

        # Upload proxy worker
        self._deploy_proxy_worker()

        # Initialize RPC client
        self.rpc_client = RPCClient(self.sandbox)

        # Prepare execution package
        prepared = self._prepare_package(manifest, context)

        # Upload to sandbox
        self._upload_package(prepared)

        return prepared

    def execute(self, prepared: PreparedRun, context: ExecutionContext) -> None:
        """Execute pipeline in E2B sandbox"""
        # TODO: Complete implementation

        # Start proxy worker
        self.rpc_client.call("start", {
            "manifest": prepared.manifest,
            "configs": prepared.configs,
            "environment": prepared.environment
        })

        # Stream events
        while True:
            event = self.rpc_client.receive_event()
            if event["type"] == "complete":
                break
            elif event["type"] == "error":
                raise ExecutionError(event["message"])
            else:
                # Forward event to local session
                self._forward_event(event)

    def collect(self, prepared: PreparedRun, context: ExecutionContext) -> dict:
        """Collect results from E2B sandbox"""
        # TODO: Complete implementation

        # Download artifacts
        artifacts = self._download_artifacts()

        # Get execution summary
        summary = self.rpc_client.call("get_summary", {})

        # Cleanup sandbox
        self.sandbox.close()

        return {
            "status": "completed",
            "artifacts": artifacts,
            "metrics": summary["metrics"],
            "environment": "e2b",
            "sandbox_id": self.sandbox.id,
            "overhead_ms": summary["overhead_ms"]
        }

    # Helper methods
    def _deploy_proxy_worker(self):
        """Deploy proxy worker to sandbox"""
        # TODO: Implementation
        pass

    def _prepare_package(self, manifest: dict, context: ExecutionContext) -> PreparedRun:
        """Prepare execution package for E2B"""
        # TODO: Implementation
        pass

    def _upload_package(self, prepared: PreparedRun):
        """Upload package to sandbox"""
        # TODO: Implementation
        pass

    def _forward_event(self, event: dict):
        """Forward event from sandbox to local session"""
        # TODO: Implementation
        pass

    def _download_artifacts(self) -> list:
        """Download artifacts from sandbox"""
        # TODO: Implementation
        pass
```

### RPC Protocol
```python
# TODO: RPC protocol for E2B communication
class RPCProtocol:
    """JSON-RPC protocol for proxy communication"""

    def create_request(self, method: str, params: dict) -> dict:
        """Create RPC request"""
        return {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._generate_id()
        }

    def create_response(self, id: str, result: Any) -> dict:
        """Create RPC response"""
        return {
            "jsonrpc": "2.0",
            "result": result,
            "id": id
        }

    def create_error(self, id: str, error: dict) -> dict:
        """Create RPC error"""
        return {
            "jsonrpc": "2.0",
            "error": error,
            "id": id
        }
```

### ProxyWorker Implementation
```python
# osiris/remote/proxy_worker.py
# TODO: Worker that runs inside E2B sandbox

class ProxyWorker:
    """Worker process for E2B execution"""

    def __init__(self):
        self.driver_registry = DriverRegistry()
        self.rpc_server = RPCServer()

    def run(self):
        """Main worker loop"""
        while True:
            request = self.rpc_server.receive_request()

            if request["method"] == "start":
                self.execute_pipeline(request["params"])
            elif request["method"] == "get_summary":
                self.send_summary()
            elif request["method"] == "heartbeat":
                self.send_heartbeat()
```

## Custom Adapter Development

TODO: Guide for creating custom adapters:

### Template
```python
# TODO: Custom adapter template
from osiris.core.execution_adapter import ExecutionAdapter

class CustomAdapter(ExecutionAdapter):
    """Custom execution adapter for [platform]"""

    def __init__(self, **kwargs):
        # Initialize platform-specific resources
        pass

    def prepare(self, manifest: dict, context: ExecutionContext) -> PreparedRun:
        # Prepare execution environment
        pass

    def execute(self, prepared: PreparedRun, context: ExecutionContext) -> None:
        # Execute pipeline
        pass

    def collect(self, prepared: PreparedRun, context: ExecutionContext) -> dict:
        # Collect results
        pass
```

### Registration
```python
# TODO: Adapter registration
from osiris.core.adapter_factory import AdapterFactory

# Register custom adapter
AdapterFactory.register("custom", CustomAdapter)

# Use in execution
adapter = AdapterFactory.create("custom", **config)
```

### Testing Strategy
TODO: Testing custom adapters:
- Unit tests for each phase
- Integration tests with real pipelines
- Performance benchmarking
- Error handling validation
- Parity tests with LocalAdapter

## Performance Considerations

TODO: Performance optimization for adapters:

### Optimization Strategies
- Connection pooling
- Batch processing
- Parallel execution (future)
- Resource pre-allocation
- Caching strategies

### Benchmarking
```python
# TODO: Benchmarking framework
class AdapterBenchmark:
    def benchmark_prepare(self, adapter, manifest):
        # Measure prepare phase
        pass

    def benchmark_execute(self, adapter, prepared):
        # Measure execute phase
        pass

    def benchmark_collect(self, adapter, prepared):
        # Measure collect phase
        pass
```

### Metrics to Track
- Preparation time
- Execution time per step
- Total overhead
- Memory usage
- Network latency (for remote)
- Artifact transfer time

## Security Considerations

TODO: Security best practices:

### Credential Management
- Never log secrets
- Use secure storage
- Rotate credentials
- Audit access

### Sandbox Isolation
- Network segmentation
- Resource limits
- Process isolation
- Filesystem restrictions

### Data Protection
- Encryption in transit
- Encryption at rest
- Data masking
- Compliance (GDPR, HIPAA)

## Troubleshooting

TODO: Common adapter issues:

### Debugging Techniques
- Enable verbose logging
- Use debug breakpoints
- Inspect RPC messages
- Monitor resource usage

### Common Problems
- Connection timeouts
- Memory exhaustion
- Serialization issues
- Version mismatches

### Solutions
- Retry mechanisms
- Circuit breakers
- Fallback strategies
- Graceful degradation
