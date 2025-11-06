"""Minimal local runner for compiled manifests."""

from datetime import datetime
import json
import logging
from pathlib import Path
import time
from typing import Any

import yaml

from ..components.registry import ComponentRegistry
from .config import ConfigError, parse_connection_ref, resolve_connection
from .driver import DriverRegistry
from .session_logging import log_event, log_metric

logger = logging.getLogger(__name__)


class RunnerV0:
    """Minimal sequential runner for linear pipelines."""

    def __init__(self, manifest_path: str, output_dir: str | Path, fs_contract=None):
        """Initialize runner with output directory.

        Args:
            manifest_path: Path to the manifest file
            output_dir: Artifacts directory (only used if fs_contract not provided)
            fs_contract: Optional FilesystemContract for path resolution
        """
        self.manifest_path = Path(manifest_path)
        self.output_dir = Path(output_dir)
        self.fs_contract = fs_contract

        # Ensure output_dir is absolute to avoid CWD issues
        if not self.output_dir.is_absolute():
            self.output_dir = Path.cwd() / self.output_dir

        self.manifest = None
        self.components = {}
        self.events = []
        self.results = {}  # Step results cache
        self.driver_registry = self._build_driver_registry()

        # Log artifact base for debugging
        logger.debug(f"Artifacts base directory: {self.output_dir}")

    def _build_driver_registry(self) -> DriverRegistry:
        """Build and populate the driver registry from component specs."""
        registry = DriverRegistry()

        # Load component registry fresh, bypassing any cached specs
        component_registry = ComponentRegistry()

        # Clear any cached specs in the registry to prevent test pollution
        registry._loaded_specs = None

        specs = registry.load_specs(component_registry)

        summary = registry.populate_from_component_specs(
            specs,
            on_success=lambda component, driver: logger.debug(f"Registered driver for {component}: {driver}"),
        )

        for component_name, reason in summary.skipped.items():
            logger.debug(f"Component {component_name} skipped during driver registration: {reason}")

        for component_name, error in summary.errors.items():
            logger.error(
                "Driver registration warning for %s: %s",
                component_name,
                error,
            )

        return registry

    def run(self) -> bool:
        """
        Execute the manifest.

        Returns:
            True if successful, False on error
        """
        try:
            # Load manifest
            with open(self.manifest_path) as f:
                self.manifest = yaml.safe_load(f)

            # Log run start
            self._log_event(
                "run_start",
                {
                    "manifest_path": str(self.manifest_path),
                    "pipeline_id": self.manifest["pipeline"]["id"],
                    "profile": self.manifest["meta"].get("profile", "default"),
                },
            )

            # Execute steps in order
            for step in self.manifest["steps"]:
                if not self._execute_step(step):
                    self._log_event("run_error", {"step_id": step["id"], "message": "Step execution failed"})
                    return False

            # Log run complete
            self._log_event(
                "run_complete",
                {
                    "pipeline_id": self.manifest["pipeline"]["id"],
                    "steps_executed": len(self.manifest["steps"]),
                },
            )

            return True

        except ConfigError:
            # Re-raise ConfigError so tests can catch it
            raise
        except Exception as e:
            logger.error(f"Runner error: {str(e)}")
            self._log_event("run_error", {"error": str(e)})
            return False

    def _log_event(self, event_type: str, data: dict[str, Any]):
        """Log an event."""
        event = {"timestamp": datetime.utcnow().isoformat(), "type": event_type, "data": data}
        self.events.append(event)
        logger.debug(f"Event: {event_type} - {data}")

        # Also emit to session logging
        log_event(event_type, **data)

    def _emit_inputs_resolved(
        self,
        *,
        step_id: str,
        from_step: str,
        key: str,
        rows: int,
        from_memory: bool,
    ) -> None:
        """Emit inputs_resolved telemetry mirroring sandbox semantics."""

        payload = {
            "step_id": step_id,
            "from_step": from_step,
            "key": key,
            "rows": rows,
            "from_memory": from_memory,
        }

        self._log_event("inputs_resolved", payload)

    def _count_rows(self, data: Any) -> int:
        """Best-effort row counter for tabular inputs."""

        if data is None:
            return 0

        try:
            import pandas as pd  # type: ignore

            if isinstance(data, pd.DataFrame):
                return int(len(data.index))
        except Exception:  # pragma: no cover - pandas optional in runtime
            pass

        try:
            return int(len(data))  # type: ignore[arg-type]
        except Exception:
            return 0

    def _write_cleaned_config_artifact(self, clean_config: dict[str, Any], cleaned_path: Path) -> bool:
        """Persist cleaned config artifact with masked secrets.

        Returns True if the artifact was created, False if it already existed.
        """

        cleaned_path.parent.mkdir(parents=True, exist_ok=True)

        artifact_config = json.loads(json.dumps(clean_config)) if clean_config else {}
        resolved = artifact_config.get("resolved_connection")
        if isinstance(resolved, dict):
            masked = resolved.copy()
            for key in ["password", "key", "token", "secret", "service_role_key", "anon_key"]:
                if key in masked:
                    masked[key] = "***MASKED***"
            artifact_config["resolved_connection"] = masked

        created = not cleaned_path.exists()
        with open(cleaned_path, "w") as f:
            json.dump(artifact_config, f, indent=2)

        return created

    def _family_from_component(self, component: str) -> str:
        """Extract family from component name.

        Examples:
            'mysql.extractor' -> 'mysql'
            'supabase.writer' -> 'supabase'
            'duckdb.writer' -> 'duckdb'
        """
        return component.split(".", 1)[0]

    def _resolve_step_connection(self, step: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        """Resolve connection for a step.

        Returns None if no connection needed (e.g., duckdb local operations).
        """
        # Get component from step
        component = step.get("component", "")
        if not component:
            # Legacy driver format, try to infer from driver
            driver = step.get("driver", "")
            if "mysql" in driver:
                family = "mysql"
            elif "supabase" in driver:
                family = "supabase"
            elif "duckdb" in driver:
                # DuckDB may not need connection for local operations
                return None
            else:
                return None
        else:
            family = self._family_from_component(component)

        # Special case: duckdb with no connection needed
        if family == "duckdb" and "connection" not in config:
            return None

        # Parse connection reference from config
        conn_ref = config.get("connection")
        alias = None

        if isinstance(conn_ref, str) and conn_ref.startswith("@"):
            ref_family, alias = parse_connection_ref(conn_ref)
            if ref_family and ref_family != family:
                raise ValueError(f"Connection family mismatch: step uses {family}, ref is {ref_family}")

        # Log connection resolution start
        log_event(
            "connection_resolve_start",
            step_id=step.get("id", "unknown"),
            family=family,
            alias=alias or "(default)",
        )

        try:
            resolved = resolve_connection(family, alias)

            # Log success (with masked values)
            log_event(
                "connection_resolve_complete",
                step_id=step.get("id", "unknown"),
                family=family,
                alias=alias or "(default)",
                ok=True,
            )

            return resolved

        except Exception as e:
            log_event(
                "connection_resolve_complete",
                step_id=step.get("id", "unknown"),
                family=family,
                alias=alias or "(default)",
                ok=False,
                error=str(e),
            )
            raise

    def _execute_step(self, step: dict[str, Any]) -> bool:  # noqa: PLR0915
        """Execute a single step."""
        step_id = step["id"]
        driver = step.get("driver") or step.get("component", "unknown")
        cfg_path = step["cfg_path"]

        try:
            # Log step start
            start_time = time.time()
            self._log_event("step_start", {"step_id": step_id, "driver": driver})

            # Create step output directory
            step_output_dir = self.output_dir / step_id
            step_output_dir.mkdir(parents=True, exist_ok=True)

            # Log artifact directory creation (verbose)
            logger.debug(f"Created artifacts directory for step {step_id}: {step_output_dir}")
            log_event(
                "artifacts_dir_created",
                step_id=step_id,
                path=str(step_output_dir),
            )

            # Resolve config path relative to manifest
            if not Path(cfg_path).is_absolute():
                cfg_full_path = self.manifest_path.parent / cfg_path
            else:
                cfg_full_path = Path(cfg_path)

            # Load step config
            with open(cfg_full_path) as f:
                config = json.load(f)

            # Clean config for driver (strip meta keys)
            clean_config = config.copy()
            meta_keys_removed = []

            if "component" in clean_config:
                del clean_config["component"]
                meta_keys_removed.append("component")

            if "connection" in clean_config:
                del clean_config["connection"]
                meta_keys_removed.append("connection")

            # Log that meta keys were stripped
            if meta_keys_removed:
                self._log_event(
                    "config_meta_stripped",
                    {
                        "step_id": step_id,
                        "keys_removed": meta_keys_removed,
                        "config_meta_stripped": True,
                    },
                )

            # Save cleaned config as artifact (no secrets in resolved_connection)
            cleaned_config_path = step_output_dir / "cleaned_config.json"
            artifact_created = self._write_cleaned_config_artifact(clean_config, cleaned_config_path)
            if artifact_created:
                logger.debug(f"Created artifact: {cleaned_config_path}")
                log_event(
                    "artifact_created",
                    step_id=step_id,
                    artifact_type="cleaned_config",
                    path=str(cleaned_config_path),
                )

            # Resolve connection after artifact creation so tests can observe
            # cleaned configs even when resolution fails.
            connection = self._resolve_step_connection(step, config)
            if connection:
                clean_config["resolved_connection"] = connection
                self._write_cleaned_config_artifact(clean_config, cleaned_config_path)

            # Execute using driver registry with cleaned config
            success, error_message = self._run_with_driver(step, clean_config, step_output_dir)

            # Calculate step duration
            duration = time.time() - start_time
            log_metric(f"step_{step_id}_duration", duration, unit="seconds")

            if success:
                self._log_event(
                    "step_complete",
                    {
                        "step_id": step_id,
                        "driver": driver,
                        "output_dir": str(step_output_dir),
                        "duration": duration,
                    },
                )
            else:
                self._log_event(
                    "step_error",
                    {
                        "step_id": step_id,
                        "driver": driver,
                        "duration": duration,
                        "error": error_message or "Driver execution failed",
                    },
                )

            return success

        except ConfigError:
            # Re-raise ConfigError so tests can catch it
            raise
        except Exception as e:
            logger.error(f"Step {step_id} failed: {str(e)}")
            self._log_event("step_error", {"step_id": step_id, "error": str(e)})
            return False

    def _run_with_driver(self, step: dict[str, Any], config: dict, output_dir: Path) -> tuple[bool, str | None]:
        """Run a step using the driver registry.

        Args:
            step: Step definition from manifest
            config: Step configuration (with resolved_connection if applicable)
            output_dir: Output directory for step

        Returns:
            Tuple of (success, error_message)
        """
        step_id = step["id"]
        driver_name = step.get("driver") or step.get("component", "unknown")

        try:
            # Get driver from registry
            driver = self.driver_registry.get(driver_name)

            # Prepare inputs based on step dependencies
            inputs = None
            if "needs" in step and step["needs"]:
                from .step_naming import build_dataframe_keys

                # Collect inputs from upstream steps
                inputs = {}

                # Build safe DataFrame keys with collision detection
                upstream_ids = [uid for uid in step["needs"] if uid in self.results]
                df_keys = build_dataframe_keys(upstream_ids)

                for upstream_id in step["needs"]:
                    if upstream_id in self.results:
                        upstream_result = self.results[upstream_id]

                        # Store full upstream result by step_id
                        inputs[upstream_id] = upstream_result

                        # If result contains DataFrame, also register with safe key
                        if "df" in upstream_result:
                            safe_key = df_keys[upstream_id]
                            inputs[safe_key] = upstream_result["df"]

                            # Log for debugging
                            rows = self._count_rows(upstream_result["df"])
                            logger.debug(f"Step {step_id}: Registered {safe_key} with {rows} rows from {upstream_id}")
                            self._emit_inputs_resolved(
                                step_id=step_id,
                                from_step=upstream_id,
                                key=safe_key,
                                rows=rows,
                                from_memory=True,
                            )

            # Create context for metrics and output
            class RunnerContext:
                def __init__(self, output_dir):
                    self.output_dir = output_dir

                def log_metric(self, name: str, value: Any, **kwargs):
                    log_metric(name, value, **kwargs)

            ctx = RunnerContext(output_dir)

            # Run the driver
            result = driver.run(step_id=step_id, config=config, inputs=inputs, ctx=ctx)

            # Cache result if it contains data
            if result and "df" in result:
                self.results[step_id] = result

            return True, None

        except ValueError as e:
            # Driver not found or other value errors
            error_msg = f"Driver error: {str(e)}"
            logger.error(f"Step {step_id} failed: {error_msg}")
            return False, error_msg
        except Exception as e:
            # Runtime execution errors (including MySQL connection failures)
            error_msg = f"Execution failed: {str(e)}"
            logger.error(f"Step {step_id} execution failed: {error_msg}")
            return False, error_msg

    def _run_component(self, driver: str, config: dict, output_dir: Path, connection: dict | None = None) -> bool:
        """Run a specific component.

        Args:
            driver: Component driver/type
            config: Step configuration
            output_dir: Output directory for step
            connection: Resolved connection dict (if applicable)
        """

        # Map drivers to component handlers
        if driver in {"extractors.supabase@0.1", "supabase.extractor"}:
            return self._run_supabase_extractor(config, output_dir, connection)
        elif driver in {"transforms.duckdb@0.1", "duckdb.transform"}:
            return self._run_duckdb_transform(config, output_dir, connection)
        elif driver in {"writers.mysql@0.1", "mysql.writer"}:
            return self._run_mysql_writer(config, output_dir, connection)
        elif driver in {"mysql.extractor", "extractors.mysql@0.1"}:
            return self._run_mysql_extractor(config, output_dir, connection)
        elif driver in {"supabase.writer", "writers.supabase@0.1"}:
            return self._run_supabase_writer(config, output_dir, connection)
        elif driver == "duckdb.writer":
            return self._run_duckdb_writer(config, output_dir, connection)
        elif driver == "filesystem.csv_writer":
            return self._run_filesystem_csv_writer(config, output_dir, connection)
        else:
            logger.error(f"Unknown driver: {driver}")
            return False

    def _run_supabase_extractor(self, config: dict, output_dir: Path, connection: dict | None = None) -> bool:
        """Run Supabase extractor."""
        try:
            # Use real connector if available
            try:
                from osiris.connectors.supabase.extractor import SupabaseExtractor

                # Merge connection into config if provided
                if connection:
                    # Connection overrides config values
                    merged_config = {**config, **connection}
                else:
                    merged_config = config

                extractor = SupabaseExtractor(merged_config)
                # Run extraction logic
                # TODO: Implement actual extraction
                return True
            except ImportError:
                # Fallback to stub for MVP
                pass

            # Simulate extraction
            output_file = output_dir / "data.json"
            sample_data = {
                "table": config.get("table", "unknown"),
                "rows": [
                    {"id": 1, "email": "user1@example.com", "name": "User One"},
                    {"id": 2, "email": "user2@example.com", "name": "User Two"},
                ],
                "extracted_at": datetime.utcnow().isoformat(),
            }

            with open(output_file, "w") as f:
                json.dump(sample_data, f, indent=2)

            logger.debug(f"Extracted data to {output_file}")
            return True

        except Exception as e:
            logger.error(f"Supabase extraction failed: {str(e)}")
            return False

    def _run_duckdb_transform(self, config: dict, output_dir: Path, connection: dict | None = None) -> bool:
        """Run DuckDB transform."""
        try:
            import duckdb

            # Get input from previous step
            input_dir = self.output_dir / "extract_customers"
            input_file = input_dir / "data.json"

            if input_file.exists():
                with open(input_file) as f:
                    input_data = json.load(f)
            else:
                # Create sample data if no input
                input_data = {
                    "rows": [
                        {"id": 1, "email": "user1@example.com"},
                        {"id": 2, "email": "user2@example.com"},
                    ]
                }

            # Connect to DuckDB (in-memory)
            conn = duckdb.connect(":memory:")

            # Create input table
            if "rows" in input_data and input_data["rows"]:
                import pandas as pd

                df = pd.DataFrame(input_data["rows"])
                conn.register("input", df)
            else:
                # Empty table
                conn.execute("CREATE TABLE input (id INT, email VARCHAR)")

            # Run SQL transform
            sql = config.get("sql", "SELECT * FROM input")
            result = conn.execute(sql).fetchdf()

            # Save output
            output_file = output_dir / "transformed.json"
            result_dict = {
                "rows": result.to_dict("records"),
                "transformed_at": datetime.utcnow().isoformat(),
            }

            with open(output_file, "w") as f:
                json.dump(result_dict, f, indent=2)

            logger.debug(f"Transformed data to {output_file}")
            conn.close()
            return True

        except Exception as e:
            logger.error(f"DuckDB transform failed: {str(e)}")
            return False

    def _run_mysql_extractor(self, config: dict, output_dir: Path, connection: dict | None = None) -> bool:
        """Run MySQL extractor."""
        try:
            # Use real connector if available
            try:
                from osiris.connectors.mysql.extractor import MySQLExtractor

                # Merge connection into config if provided
                if connection:
                    merged_config = {**config, **connection}
                else:
                    merged_config = config

                extractor = MySQLExtractor(merged_config)
                # Run extraction logic
                data = extractor.extract()  # Assuming this returns data

                # Log metrics
                if isinstance(data, list) or hasattr(data, "__len__"):
                    rows_read = len(data)
                else:
                    rows_read = 0

                log_metric("rows_read", rows_read)
                logger.info(f"MySQL extraction complete: read {rows_read} rows")

                # Save data for downstream steps
                output_file = output_dir / "data.json"
                with open(output_file, "w") as f:
                    if hasattr(data, "to_dict"):
                        # Handle pandas DataFrame
                        json.dump({"rows": data.to_dict("records")}, f, indent=2)
                    elif isinstance(data, list):
                        json.dump({"rows": data}, f, indent=2)
                    else:
                        json.dump({"rows": []}, f, indent=2)

                return True
            except ImportError:
                # Fallback to stub
                pass

            # Stub implementation
            output_file = output_dir / "data.json"
            sample_data = {
                "table": config.get("table", "unknown"),
                "rows": [{"id": 1, "data": "sample"}],
                "extracted_at": datetime.utcnow().isoformat(),
            }
            with open(output_file, "w") as f:
                json.dump(sample_data, f, indent=2)
            return True

        except Exception as e:
            logger.error(f"MySQL extraction failed: {str(e)}")
            return False

    def _run_mysql_writer(self, config: dict, output_dir: Path, connection: dict | None = None) -> bool:
        """Run MySQL writer."""
        try:
            # Use real connector if available
            try:
                from osiris.connectors.mysql.writer import MySQLWriter

                # Merge connection into config if provided
                if connection:
                    merged_config = {**config, **connection}
                else:
                    merged_config = config

                writer = MySQLWriter(merged_config)
                # Run write logic
                # TODO: Implement actual writing from input
                return True
            except ImportError:
                # Fallback to stub
                pass

            # Get input from previous step
            input_dir = self.output_dir / "transform_enrich"
            input_file = input_dir / "transformed.json"

            if input_file.exists():
                with open(input_file) as f:
                    input_data = json.load(f)
            else:
                input_data = {"rows": []}

            # Simulate write
            output_file = output_dir / "mysql_load.csv"

            if input_data.get("rows"):
                import pandas as pd

                df = pd.DataFrame(input_data["rows"])
                df.to_csv(output_file, index=False)

                # Also save metadata
                meta_file = output_dir / "mysql_load_meta.json"
                with open(meta_file, "w") as f:
                    json.dump(
                        {
                            "table": config.get("table", "unknown"),
                            "mode": config.get("mode", "append"),
                            "rows_written": len(df),
                            "written_at": datetime.utcnow().isoformat(),
                        },
                        f,
                        indent=2,
                    )

            logger.debug(f"Wrote data to {output_file}")
            return True

        except Exception as e:
            logger.error(f"MySQL write failed: {str(e)}")
            return False

    def _run_supabase_writer(self, config: dict, output_dir: Path, connection: dict | None = None) -> bool:
        """Run Supabase writer."""
        try:
            # Use real connector if available
            try:
                from osiris.connectors.supabase.writer import SupabaseWriter

                # Merge connection into config if provided
                if connection:
                    merged_config = {**config, **connection}
                else:
                    merged_config = config

                writer = SupabaseWriter(merged_config)
                # Run write logic
                # TODO: Implement actual writing
                return True
            except ImportError:
                # Fallback to stub
                pass

            # Stub implementation
            output_file = output_dir / "write_result.json"
            result = {
                "table": config.get("table", "unknown"),
                "rows_written": 0,
                "written_at": datetime.utcnow().isoformat(),
            }
            with open(output_file, "w") as f:
                json.dump(result, f, indent=2)
            return True

        except Exception as e:
            logger.error(f"Supabase write failed: {str(e)}")
            return False

    def _run_duckdb_writer(self, config: dict, output_dir: Path, connection: dict | None = None) -> bool:
        """Run DuckDB writer."""
        try:
            import duckdb

            # DuckDB connection can be local (no connection dict) or remote
            if connection and "path" in connection:
                conn = duckdb.connect(connection["path"])
            else:
                # Local/in-memory
                conn = duckdb.connect(":memory:")

            # Stub implementation
            output_file = output_dir / "duckdb_result.json"
            result = {
                "format": config.get("format", "parquet"),
                "path": config.get("path", "output.parquet"),
                "written_at": datetime.utcnow().isoformat(),
            }
            with open(output_file, "w") as f:
                json.dump(result, f, indent=2)

            conn.close()
            return True

        except Exception as e:
            logger.error(f"DuckDB write failed: {str(e)}")
            return False

    def _run_filesystem_csv_writer(self, config: dict, output_dir: Path, connection: dict | None = None) -> bool:
        """Run filesystem CSV writer."""
        try:
            from osiris.connectors.filesystem.writer import FilesystemCSVWriter

            # Get input data from previous step
            # For MVP, look for common output files
            input_files = [
                output_dir.parent / "extract" / "data.json",
                output_dir.parent / "transform" / "transformed.json",
                # Try previous step output dirs
            ]

            input_data = []
            for input_file in input_files:
                if input_file.exists():
                    with open(input_file) as f:
                        data = json.load(f)
                        if "rows" in data:
                            input_data = data["rows"]
                            break
                        elif isinstance(data, list):
                            input_data = data
                            break

            # Check for empty input data
            if not input_data:
                error_msg = (
                    "Upstream produced 0 rows or no data artifact for step. " "Check the mode and upstream step output."
                )
                logger.error(error_msg)
                raise ValueError(error_msg)

            # Create writer and write data
            writer = FilesystemCSVWriter(config)
            result = writer.write(input_data)

            # Save result metadata
            result_file = output_dir / "write_result.json"
            with open(result_file, "w") as f:
                json.dump(result, f, indent=2)

            # Log metrics
            rows_written = result.get("rows_written", 0)
            log_metric("rows_written", rows_written)
            logger.info(f"CSV write complete: wrote {rows_written} rows to {result.get('path')}")

            return True

        except Exception as e:
            logger.error(f"Filesystem CSV write failed: {str(e)}")
            return False
