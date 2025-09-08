"""Minimal local runner for compiled manifests."""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .config import parse_connection_ref, resolve_connection
from .session_logging import log_event, log_metric

logger = logging.getLogger(__name__)


class RunnerV0:
    """Minimal sequential runner for linear pipelines."""

    def __init__(self, manifest_path: str, output_dir: str = "_artifacts"):
        self.manifest_path = Path(manifest_path)
        self.output_dir = Path(output_dir)
        self.manifest = None
        self.components = {}
        self.events = []

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
                    self._log_event(
                        "run_error", {"step_id": step["id"], "message": "Step execution failed"}
                    )
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

        except Exception as e:
            logger.error(f"Runner error: {str(e)}")
            self._log_event("run_error", {"error": str(e)})
            return False

    def _log_event(self, event_type: str, data: Dict[str, Any]):
        """Log an event."""
        event = {"timestamp": datetime.utcnow().isoformat(), "type": event_type, "data": data}
        self.events.append(event)
        logger.debug(f"Event: {event_type} - {data}")

        # Also emit to session logging
        log_event(event_type, **data)

    def _family_from_component(self, component: str) -> str:
        """Extract family from component name.

        Examples:
            'mysql.extractor' -> 'mysql'
            'supabase.writer' -> 'supabase'
            'duckdb.writer' -> 'duckdb'
        """
        return component.split(".", 1)[0]

    def _resolve_step_connection(
        self, step: Dict[str, Any], config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
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
                raise ValueError(
                    f"Connection family mismatch: step uses {family}, ref is {ref_family}"
                )

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

    def _execute_step(self, step: Dict[str, Any]) -> bool:
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

            # Resolve config path relative to manifest
            if not Path(cfg_path).is_absolute():
                cfg_full_path = self.manifest_path.parent / cfg_path
            else:
                cfg_full_path = Path(cfg_path)

            # Load step config
            with open(cfg_full_path) as f:
                config = json.load(f)

            # Resolve connection if needed
            connection = self._resolve_step_connection(step, config)

            # Execute based on driver type
            success = self._run_component(driver, config, step_output_dir, connection=connection)

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
                    "step_error", {"step_id": step_id, "driver": driver, "duration": duration}
                )

            return success

        except Exception as e:
            logger.error(f"Step {step_id} failed: {str(e)}")
            self._log_event("step_error", {"step_id": step_id, "error": str(e)})
            return False

    def _run_component(
        self, driver: str, config: Dict, output_dir: Path, connection: Optional[Dict] = None
    ) -> bool:
        """Run a specific component.

        Args:
            driver: Component driver/type
            config: Step configuration
            output_dir: Output directory for step
            connection: Resolved connection dict (if applicable)
        """

        # Map drivers to component handlers
        if driver == "extractors.supabase@0.1" or driver == "supabase.extractor":
            return self._run_supabase_extractor(config, output_dir, connection)
        elif driver == "transforms.duckdb@0.1" or driver == "duckdb.transform":
            return self._run_duckdb_transform(config, output_dir, connection)
        elif driver == "writers.mysql@0.1" or driver == "mysql.writer":
            return self._run_mysql_writer(config, output_dir, connection)
        elif driver == "mysql.extractor" or driver == "extractors.mysql@0.1":
            return self._run_mysql_extractor(config, output_dir, connection)
        elif driver == "supabase.writer" or driver == "writers.supabase@0.1":
            return self._run_supabase_writer(config, output_dir, connection)
        elif driver == "duckdb.writer":
            return self._run_duckdb_writer(config, output_dir, connection)
        else:
            logger.error(f"Unknown driver: {driver}")
            return False

    def _run_supabase_extractor(
        self, config: Dict, output_dir: Path, connection: Optional[Dict] = None
    ) -> bool:
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

    def _run_duckdb_transform(
        self, config: Dict, output_dir: Path, connection: Optional[Dict] = None
    ) -> bool:
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

    def _run_mysql_extractor(
        self, config: Dict, output_dir: Path, connection: Optional[Dict] = None
    ) -> bool:
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
                # TODO: Implement actual extraction with output_dir
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

    def _run_mysql_writer(
        self, config: Dict, output_dir: Path, connection: Optional[Dict] = None
    ) -> bool:
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

    def _run_supabase_writer(
        self, config: Dict, output_dir: Path, connection: Optional[Dict] = None
    ) -> bool:
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

    def _run_duckdb_writer(
        self, config: Dict, output_dir: Path, connection: Optional[Dict] = None
    ) -> bool:
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
