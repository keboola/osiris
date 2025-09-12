"""Payload builder for E2B sandbox execution.

Builds a minimal, allowlisted payload for remote execution.
"""

import hashlib
import json
import tarfile
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class PayloadManifest:
    """Manifest of files included in the payload."""

    files: List[Dict[str, Any]]
    total_size_bytes: int
    sha256: str
    created_at: str


@dataclass
class RunConfig:
    """Configuration for running the pipeline."""

    seed: Optional[int] = None
    profile: bool = False
    params: Dict[str, Any] = None
    flags: Dict[str, bool] = None

    def __post_init__(self):
        if self.params is None:
            self.params = {}
        if self.flags is None:
            self.flags = {}


class PayloadBuilder:
    """Builds payload tarball for E2B execution."""

    # Strict allowlist of files to include
    ALLOWED_FILES = {
        "manifest.json",  # Compiled manifest
        "mini_runner.py",  # Minimal runner script
        "requirements.txt",  # Python dependencies
        "run_config.json",  # Runtime configuration
    }

    # Directories allowed in payload
    ALLOWED_DIRS = {
        "cfg",  # Configuration files referenced by manifest
    }

    # Maximum payload size (10 MB)
    MAX_PAYLOAD_SIZE = 10 * 1024 * 1024

    def __init__(self, session_dir: Path, build_dir: Path):
        """Initialize payload builder.

        Args:
            session_dir: Session directory with compiled manifest
            build_dir: Directory to build payload in
        """
        self.session_dir = session_dir
        self.build_dir = build_dir
        self.payload_dir = build_dir / "e2b"
        self.payload_dir.mkdir(parents=True, exist_ok=True)

    def build(
        self, manifest_path: Path, run_config: RunConfig, mini_runner_path: Optional[Path] = None
    ) -> Path:
        """Build payload tarball.

        Args:
            manifest_path: Path to compiled manifest.json
            run_config: Runtime configuration
            mini_runner_path: Optional path to custom mini_runner.py

        Returns:
            Path to generated payload.tgz
        """
        # Clean payload directory
        for item in self.payload_dir.iterdir():
            if item.is_file():
                # Check allowlist before cleaning
                if item.name not in self.ALLOWED_FILES:
                    raise ValueError(f"File not in allowlist: {item.name}")
                item.unlink()
            elif item.is_dir():
                import shutil

                shutil.rmtree(item)

        # Copy manifest (convert YAML to JSON)
        manifest_dest = self.payload_dir / "manifest.json"
        with open(manifest_path) as src, open(manifest_dest, "w") as dst:
            manifest_data = yaml.safe_load(src)
            json.dump(manifest_data, dst, indent=2)

        # Parse manifest to find cfg dependencies
        cfg_paths = self._extract_cfg_paths(manifest_data)

        # Include cfg files in payload
        self._include_cfg_files(manifest_path, cfg_paths)

        # Create or copy mini_runner.py
        runner_dest = self.payload_dir / "mini_runner.py"
        if mini_runner_path and mini_runner_path.exists():
            with open(mini_runner_path) as src, open(runner_dest, "w") as dst:
                dst.write(src.read())
        else:
            # Create minimal runner
            self._create_mini_runner(runner_dest)

        # Create requirements.txt with minimal dependencies
        self._create_requirements(self.payload_dir / "requirements.txt")

        # Write run configuration
        config_dest = self.payload_dir / "run_config.json"
        with open(config_dest, "w") as f:
            json.dump(asdict(run_config), f, indent=2)

        # Verify allowlist
        for file_path in self.payload_dir.iterdir():
            if file_path.is_file() and file_path.name not in self.ALLOWED_FILES:
                raise ValueError(f"File not in allowlist: {file_path.name}")
            elif file_path.is_dir() and file_path.name not in self.ALLOWED_DIRS:
                raise ValueError(f"Directory not in allowlist: {file_path.name}")

        # Create tarball
        tarball_path = self.build_dir / "payload.tgz"
        with tarfile.open(tarball_path, "w:gz") as tar:
            for item_path in self.payload_dir.iterdir():
                if item_path.is_file():
                    tar.add(item_path, arcname=item_path.name)
                elif item_path.is_dir():
                    # Add directory recursively, preserving structure
                    tar.add(item_path, arcname=item_path.name)

        # Check size
        size = tarball_path.stat().st_size
        if size > self.MAX_PAYLOAD_SIZE:
            raise ValueError(
                f"Payload size ({size} bytes) exceeds maximum " f"({self.MAX_PAYLOAD_SIZE} bytes)"
            )

        # Compute SHA256
        sha256 = self._compute_sha256(tarball_path)

        # Create manifest - include all files (including those in subdirectories)
        from datetime import datetime

        files_list = []
        for item in self.payload_dir.rglob("*"):
            if item.is_file():
                # Get relative path from payload_dir
                rel_path = item.relative_to(self.payload_dir)
                files_list.append({"name": str(rel_path), "size_bytes": item.stat().st_size})

        manifest = PayloadManifest(
            files=files_list,
            total_size_bytes=size,
            sha256=sha256,
            created_at=datetime.utcnow().isoformat() + "Z",
        )

        # Write manifest to session metadata
        metadata_path = self.session_dir / "metadata.json"
        metadata = {}
        if metadata_path.exists():
            with open(metadata_path) as f:
                metadata = json.load(f)

        metadata["remote"] = {"payload": asdict(manifest)}

        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        return tarball_path

    def _create_mini_runner(self, path: Path) -> None:
        """Create real runner script with driver implementations."""
        runner_code = '''#!/usr/bin/env python3
"""Real runner for executing Osiris manifests in E2B sandbox.

This runner uses resolved connection descriptors from the PreparedRun,
rather than building connections directly from environment variables.
"""

import json
import logging
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import sqlalchemy as sa

# Error taxonomy for unified error reporting
class ErrorCode:
    """Standard error codes."""
    CONNECTION_FAILED = "connection.failed"
    CONNECTION_AUTH_FAILED = "connection.auth_failed"
    EXTRACT_QUERY_FAILED = "extract.query_failed"
    WRITE_FAILED = "write.failed"
    CONFIG_MISSING_REQUIRED = "config.missing_required"
    RUNTIME_DEPENDENCY_FAILED = "runtime.dependency_failed"
    SYSTEM_ERROR = "system.error"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('osiris.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class EventLogger:
    """Handles structured event and metric logging."""

    def __init__(self):
        self.events_file = open("events.jsonl", "w")
        self.metrics_file = open("metrics.jsonl", "w")
        self.source = "remote"  # Tag all events as remote

    def log_event(self, event_name: str, **kwargs):
        """Log a structured event."""
        event_data = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "event": event_name,
            "source": self.source,  # Add source tag
            **kwargs
        }
        self.events_file.write(json.dumps(event_data, default=str) + "\\n")
        self.events_file.flush()

    def log_metric(self, metric: str, value: Any, unit: str = "", **kwargs):
        """Log a metric."""
        metric_data = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "metric": metric,
            "value": value,
            "unit": unit,
            "source": self.source,  # Add source tag
            **kwargs
        }
        self.metrics_file.write(json.dumps(metric_data, default=str) + "\\n")
        self.metrics_file.flush()

    def close(self):
        """Close log files."""
        self.events_file.close()
        self.metrics_file.close()


class MySQLExtractorDriver:
    """MySQL extractor driver for E2B execution."""

    def run(self, step_id: str, config: dict, inputs: Optional[dict] = None, ctx: Any = None) -> dict:
        """Extract data from MySQL using resolved connections."""
        # Get query
        query = config.get("query")
        if not query:
            raise ValueError(f"Step {step_id}: 'query' is required in config")

        # Get resolved connection from config
        conn_info = config.get("resolved_connection", {})
        if not conn_info:
            raise ValueError(f"Step {step_id}: 'resolved_connection' is required")

        # Extract connection details with environment variable substitution
        host = conn_info.get("host", "localhost")
        port = conn_info.get("port", 3306)
        database = conn_info.get("database")
        user = conn_info.get("user", "root")
        password_ref = conn_info.get("password", "")

        # Resolve password from environment if it's a placeholder
        if password_ref.startswith("${") and password_ref.endswith("}"):
            env_var = password_ref[2:-1]  # Extract var name from ${VAR}
            password = os.getenv(env_var, "")
            if not password:
                logger.warning(f"Step {step_id}: Environment variable {env_var} not set")
        else:
            password = password_ref

        # Validate required fields
        if not database:
            error_msg = f"Step {step_id}: 'database' is required in connection"
            if ctx:
                ctx.log_event(
                    "error",
                    error_code=ErrorCode.CONFIG_MISSING_REQUIRED,
                    message=error_msg,
                    step_id=step_id
                )
            raise ValueError(error_msg)

        # Redact password for logging
        safe_conn = conn_info.copy()
        safe_conn["password"] = "***" if password else "(empty)"
        logger.info(f"Connecting to MySQL: {safe_conn}")

        # Build connection URL
        connection_url = (
            f"mysql+pymysql://{user}:{password}@"
            f"{host}:{port}/{database}"
        )

        try:
            # Create engine and execute query
            engine = sa.create_engine(connection_url)

            logger.info(f"Executing query: {query}")
            df = pd.read_sql(query, engine)
        except sa.exc.OperationalError as e:
            error_msg = f"Database connection failed: {str(e)}"
            if ctx:
                ctx.log_event(
                    "error",
                    error_code=ErrorCode.CONNECTION_FAILED,
                    message=error_msg,
                    step_id=step_id,
                    exception_type=e.__class__.__name__
                )
            raise
        except Exception as e:
            error_msg = f"Query execution failed: {str(e)}"
            if ctx:
                ctx.log_event(
                    "error",
                    error_code=ErrorCode.EXTRACT_QUERY_FAILED,
                    message=error_msg,
                    step_id=step_id,
                    exception_type=e.__class__.__name__
                )
            raise

        # Log metrics
        if ctx:
            ctx.log_metric("rows_read", len(df), unit="rows", step_id=step_id)

        logger.info(f"Extracted {len(df)} rows")
        return {"df": df}


class FilesystemCsvWriterDriver:
    """CSV writer driver for E2B execution."""

    def run(self, step_id: str, config: dict, inputs: Optional[dict] = None, ctx: Any = None) -> dict:
        """Write DataFrame to CSV file."""
        # Validate inputs
        if not inputs or "df" not in inputs:
            raise ValueError(f"Step {step_id}: requires 'df' in inputs")

        df = inputs["df"]

        # Get configuration
        file_path = config.get("path")
        if not file_path:
            raise ValueError(f"Step {step_id}: 'path' is required in config")

        # CSV options with defaults
        delimiter = config.get("delimiter", ",")
        encoding = config.get("encoding", "utf-8")
        header = config.get("header", True)
        newline_config = config.get("newline", "lf")

        # Map newline config
        newline_map = {"lf": "\\n", "crlf": "\\r\\n", "cr": "\\r"}
        line_terminator = newline_map.get(newline_config, "\\n")

        # Ensure output directory exists
        output_path = Path(file_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Sort columns for deterministic output
        df_sorted = df.reindex(sorted(df.columns), axis=1)

        try:
            # Write CSV
            df_sorted.to_csv(
                output_path,
                sep=delimiter,
                encoding=encoding,
                header=header,
                index=False,
                line_terminator=line_terminator
            )
        except PermissionError as e:
            error_msg = f"Permission denied writing to {output_path}: {str(e)}"
            if ctx:
                ctx.log_event(
                    "error",
                    error_code=ErrorCode.WRITE_FAILED,
                    message=error_msg,
                    step_id=step_id,
                    exception_type="PermissionError"
                )
            raise
        except Exception as e:
            error_msg = f"Failed to write CSV: {str(e)}"
            if ctx:
                ctx.log_event(
                    "error",
                    error_code=ErrorCode.WRITE_FAILED,
                    message=error_msg,
                    step_id=step_id,
                    exception_type=e.__class__.__name__
                )
            raise

        # Log metrics
        if ctx:
            ctx.log_metric("rows_written", len(df), unit="rows", step_id=step_id)

        logger.info(f"Wrote {len(df)} rows to {output_path}")
        return {}


class PipelineRunner:
    """Executes pipeline manifests with topological ordering."""

    def __init__(self, event_logger: EventLogger, resolved_connections: Optional[Dict] = None):
        self.event_logger = event_logger
        self.drivers = {
            "mysql.extractor": MySQLExtractorDriver(),
            "filesystem.csv_writer": FilesystemCsvWriterDriver(),
        }
        self.step_cache = {}  # Store outputs from completed steps
        self.resolved_connections = resolved_connections or {}  # Store global resolved connections

    def topological_sort(self, steps: List[dict]) -> List[dict]:
        """Sort steps in topological order based on dependencies."""
        # Build dependency graph
        step_map = {step["id"]: step for step in steps}

        # Kahn's algorithm for topological sorting
        in_degree = {step["id"]: 0 for step in steps}

        # Calculate in-degrees
        for step in steps:
            for dep in step.get("needs", []):
                if dep in in_degree:
                    in_degree[step["id"]] += 1

        # Queue of steps with no dependencies
        queue = [step_id for step_id, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            current_id = queue.pop(0)
            result.append(step_map[current_id])

            # Reduce in-degree of dependent steps
            for step in steps:
                if current_id in step.get("needs", []):
                    in_degree[step["id"]] -= 1
                    if in_degree[step["id"]] == 0:
                        queue.append(step["id"])

        if len(result) != len(steps):
            raise ValueError("Circular dependency detected in pipeline")

        return result

    def load_step_config(self, step: dict, cfg_path: str) -> dict:
        """Load configuration for a step and inject resolved connection.

        Args:
            step: Step definition from manifest
            cfg_path: Path to configuration file

        Returns:
            Configuration dict with resolved_connection injected
        """
        config_file = Path(cfg_path)
        if not config_file.exists():
            raise ValueError(f"Configuration file not found: {cfg_path}")

        with open(config_file) as f:
            config = json.load(f)

        # Inject resolved connection if step has connection reference
        connection_ref = config.get("connection")
        if connection_ref and connection_ref.startswith("@"):
            # Look up in global resolved connections
            if connection_ref in self.resolved_connections:
                resolved_conn = self.resolved_connections[connection_ref].copy()
                # Resolve any environment placeholders
                for key, value in resolved_conn.items():
                    resolved_conn[key] = resolve_env_placeholder(value)
                config["resolved_connection"] = resolved_conn
            else:
                logger.warning(f"Connection {connection_ref} not found in resolved connections")

        return config

    def execute_step(self, step: dict) -> None:
        """Execute a single pipeline step."""
        step_id = step["id"]
        driver_name = step.get("driver") or step.get("component", "unknown")
        cfg_path = step["cfg_path"]

        # Load step configuration with resolved connection
        config = self.load_step_config(step, cfg_path)

        # Get driver
        if driver_name not in self.drivers:
            raise ValueError(f"Unknown driver: {driver_name}")
        driver = self.drivers[driver_name]

        # Collect inputs from dependencies
        inputs = {}
        for dep_id in step.get("needs", []):
            if dep_id in self.step_cache:
                # For single dependency, pass the output directly
                # For multiple dependencies, we'd need more complex input mapping
                inputs.update(self.step_cache[dep_id])

        self.event_logger.log_event("step_start", step_id=step_id, driver=driver_name)
        start_time = datetime.utcnow()

        try:
            # Execute driver
            output = driver.run(
                step_id=step_id,
                config=config,
                inputs=inputs if inputs else None,
                ctx=self.event_logger
            )

            # Cache output for dependent steps
            self.step_cache[step_id] = output

            # Calculate duration
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            self.event_logger.log_event(
                "step_complete",
                step_id=step_id,
                driver=driver_name,
                duration_ms=duration_ms
            )

            logger.info(f"Completed step {step_id} in {duration_ms:.0f}ms")

        except Exception as e:
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            # Map to standard error code
            error_msg = str(e)
            error_code = ErrorCode.SYSTEM_ERROR

            # Try to determine error category
            if "connection" in error_msg.lower():
                error_code = ErrorCode.CONNECTION_FAILED
            elif "query" in error_msg.lower() or "sql" in error_msg.lower():
                error_code = ErrorCode.EXTRACT_QUERY_FAILED
            elif "write" in error_msg.lower() or "permission" in error_msg.lower():
                error_code = ErrorCode.WRITE_FAILED
            elif "config" in error_msg.lower() or "required" in error_msg.lower():
                error_code = ErrorCode.CONFIG_MISSING_REQUIRED

            self.event_logger.log_event(
                "step_error",
                step_id=step_id,
                driver=driver_name,
                error=error_msg,
                error_code=error_code,
                duration_ms=duration_ms,
                exception_type=e.__class__.__name__
            )
            raise

    def run(self, manifest: dict) -> int:
        """Execute the pipeline."""
        steps = manifest.get("steps", [])
        if not steps:
            logger.warning("No steps found in manifest")
            return 2  # Exit code 2 for zero steps executed

        # Sort steps topologically
        sorted_steps = self.topological_sort(steps)

        self.event_logger.log_event(
            "run_start",
            pipeline_id=manifest.get("pipeline", {}).get("id", "unknown"),
            total_steps=len(sorted_steps)
        )

        executed_steps = 0

        try:
            for step in sorted_steps:
                self.execute_step(step)
                executed_steps += 1

            # Create sentinel file
            sentinel_dir = Path("artifacts")
            sentinel_dir.mkdir(exist_ok=True)
            (sentinel_dir / ".mini_runner_ran").touch()

            self.event_logger.log_event(
                "run_complete",
                total_steps=len(sorted_steps),
                executed_steps=executed_steps,
                status="success"
            )

            logger.info(f"Pipeline completed successfully: {executed_steps}/{len(sorted_steps)} steps")
            return 0

        except Exception as e:
            self.event_logger.log_event(
                "run_error",
                total_steps=len(sorted_steps),
                executed_steps=executed_steps,
                error=str(e),
                error_code=ErrorCode.RUNTIME_DEPENDENCY_FAILED if executed_steps > 0 else ErrorCode.SYSTEM_ERROR,
                status="error"
            )

            logger.error(f"Pipeline failed after {executed_steps} steps: {e}")
            logger.error(traceback.format_exc())
            return 1


def resolve_env_placeholder(value: str) -> str:
    """Resolve environment variable placeholders in connection values.

    Args:
        value: Value that may contain ${ENV_VAR} placeholder

    Returns:
        Resolved value with environment variable substituted
    """
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        env_var = value[2:-1]
        return os.getenv(env_var, "")
    return value


def validate_required_env() -> None:
    """Validate that required environment variables are present.

    Since we use resolved connections with placeholders, we need to ensure
    the referenced environment variables exist.
    """
    # Check for common secret env vars that might be referenced
    # Note: The actual requirements depend on the manifest's resolved_connections
    common_vars = [
        "MYSQL_PASSWORD",
        "SUPABASE_SERVICE_ROLE_KEY",
        "POSTGRES_PASSWORD"
    ]

    missing_critical = []
    for var in common_vars:
        if var in os.environ:
            # Variable exists, log that it's available (without value)
            logger.info(f"Environment variable {var} is set")
        else:
            # Not necessarily critical - depends on the pipeline
            logger.debug(f"Environment variable {var} not found")

    # Don't fail here - let the actual connection usage fail with proper error


def main():
    """Execute manifest using real drivers."""
    logger.info("Starting E2B mini runner v3.0 (with resolved connections)")

    # Validate environment
    validate_required_env()

    # Load manifest
    manifest_path = Path("manifest.json")
    if not manifest_path.exists():
        logger.error("Manifest not found")
        sys.exit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    # Load run config
    config_path = Path("run_config.json")
    config = {}
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)

    # Initialize logging
    event_logger = EventLogger()

    # Extract resolved connections from manifest if available
    resolved_connections = {}
    if "metadata" in manifest and "resolved_connections" in manifest["metadata"]:
        resolved_connections = manifest["metadata"]["resolved_connections"]

    try:
        # Create and run pipeline with resolved connections
        runner = PipelineRunner(event_logger, resolved_connections)
        exit_code = runner.run(manifest)

        return exit_code

    except Exception as e:
        event_logger.log_event("fatal_error", error=str(e))
        logger.error(f"Fatal error: {e}")
        logger.error(traceback.format_exc())
        return 1

    finally:
        event_logger.close()


if __name__ == "__main__":
    sys.exit(main())
'''
        with open(path, "w") as f:
            f.write(runner_code)
        path.chmod(0o755)

    def _create_requirements(self, path: Path) -> None:
        """Create minimal requirements.txt."""
        # Minimal set for running manifests
        requirements = [
            "duckdb==1.1.3",
            "pandas==2.2.3",
            "pymysql==1.1.1",
            "sqlalchemy==2.0.36",
            "supabase==2.10.0",
            "python-dotenv==1.0.1",
        ]

        with open(path, "w") as f:
            f.write("\n".join(requirements))

    def _compute_sha256(self, file_path: Path) -> str:
        """Compute SHA256 hash of file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _extract_cfg_paths(self, manifest_data: Dict[str, Any]) -> List[str]:
        """Extract cfg_path entries from manifest steps.

        Args:
            manifest_data: Parsed manifest data

        Returns:
            List of cfg file paths referenced by steps
        """
        cfg_paths = []
        for step in manifest_data.get("steps", []):
            cfg_path = step.get("cfg_path")
            if cfg_path:
                cfg_paths.append(cfg_path)
        return cfg_paths

    def _include_cfg_files(self, manifest_path: Path, cfg_paths: List[str]) -> None:
        """Include cfg files in payload, validating they exist.

        Args:
            manifest_path: Path to the original manifest file
            cfg_paths: List of cfg file paths to include

        Raises:
            ValueError: If any referenced cfg file is missing
        """
        if not cfg_paths:
            return

        # The cfg files should be relative to the compiled directory
        # which is the parent directory of the manifest
        compiled_dir = manifest_path.parent

        # Create cfg directory in payload
        cfg_payload_dir = self.payload_dir / "cfg"
        cfg_payload_dir.mkdir(exist_ok=True)

        missing_files = []

        for cfg_path in cfg_paths:
            # cfg_path should be like "cfg/extract-actors.json"
            source_path = compiled_dir / cfg_path

            if not source_path.exists():
                missing_files.append(cfg_path)
                continue

            # Copy to payload preserving relative structure
            if cfg_path.startswith("cfg/"):
                dest_name = cfg_path[4:]  # Remove "cfg/" prefix
                dest_path = cfg_payload_dir / dest_name

                # Ensure destination directory exists
                dest_path.parent.mkdir(parents=True, exist_ok=True)

                with open(source_path) as src, open(dest_path, "w") as dst:
                    dst.write(src.read())

        if missing_files:
            raise ValueError(
                f"Missing cfg files referenced by manifest: {', '.join(missing_files)}. "
                f"Expected files in {compiled_dir}"
            )

    def validate_payload(self, tarball_path: Path) -> PayloadManifest:
        """Validate payload contents and return manifest.

        Args:
            tarball_path: Path to payload.tgz

        Returns:
            PayloadManifest with validation results
        """
        # Extract to temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Extract tarball
            with tarfile.open(tarball_path, "r:gz") as tar:
                tar.extractall(temp_path)  # nosec B202 - controlled validation context

            # Check files and directories against allowlist
            extracted_items = list(temp_path.iterdir())
            for item_path in extracted_items:
                if item_path.is_file() and item_path.name not in self.ALLOWED_FILES:
                    raise ValueError(f"Unauthorized file in payload: {item_path.name}")
                elif item_path.is_dir() and item_path.name not in self.ALLOWED_DIRS:
                    raise ValueError(f"Unauthorized directory in payload: {item_path.name}")

            # Compute size and hash
            size = tarball_path.stat().st_size
            sha256 = self._compute_sha256(tarball_path)

            from datetime import datetime

            # Build file list including files in subdirectories
            files_list = []
            for item in temp_path.rglob("*"):
                if item.is_file():
                    rel_path = item.relative_to(temp_path)
                    files_list.append({"name": str(rel_path), "size_bytes": item.stat().st_size})

            return PayloadManifest(
                files=files_list,
                total_size_bytes=size,
                sha256=sha256,
                created_at=datetime.utcnow().isoformat() + "Z",
            )
