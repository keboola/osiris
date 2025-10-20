"""JSON serializers for logs with schema validation.

This module provides functions to serialize session data to JSON format
that conforms to the defined schemas.
"""

from datetime import datetime
import json
from pathlib import Path

from osiris.core.session_reader import SessionSummary


def to_index_json(sessions: list[SessionSummary]) -> str:
    """Serialize session list to JSON matching logs_index schema.

    Args:
        sessions: List of SessionSummary objects

    Returns:
        JSON string conforming to logs_index.schema.json
    """
    index_data = {
        "version": "1.0.0",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_sessions": len(sessions),
        "sessions": [],
    }

    for session in sessions:
        session_data = {
            "session_id": session.session_id,
            "started_at": session.started_at,
            "finished_at": session.finished_at,
            "duration_ms": session.duration_ms,
            "status": (session.status if session.status in ["success", "failed", "running", "unknown"] else "unknown"),
            "labels": session.labels,
            "pipeline_name": session.pipeline_name,
            "steps_total": session.steps_total,
            "steps_ok": session.steps_ok,
            "rows_in": session.rows_in,
            "rows_out": session.rows_out,
            "errors": session.errors,
            "warnings": session.warnings,
        }
        index_data["sessions"].append(session_data)

    # Ensure deterministic JSON output
    return json.dumps(index_data, indent=2, sort_keys=True, ensure_ascii=False)


def to_session_json(session: SessionSummary, logs_dir: str = "./logs") -> str:
    """Serialize single session to JSON matching logs_session schema.

    Args:
        session: SessionSummary object
        logs_dir: Path to logs directory for artifact paths

    Returns:
        JSON string conforming to logs_session.schema.json
    """
    session_path = Path(logs_dir) / session.session_id

    # Build artifacts section with relative paths
    artifacts = {}

    # Check for pipeline YAML
    yaml_files = list(session_path.glob("artifacts/*.yaml")) + list(session_path.glob("artifacts/*.yml"))
    if yaml_files:
        artifacts["pipeline_yaml"] = f"artifacts/{yaml_files[0].name}"
    else:
        artifacts["pipeline_yaml"] = None

    # Check for manifest
    manifest_path = session_path / "artifacts" / "compiled" / "manifest.yaml"
    if manifest_path.exists():
        artifacts["manifest"] = "artifacts/compiled/manifest.yaml"
    else:
        artifacts["manifest"] = None

    # Log file paths
    artifacts["logs"] = {"events": "events.jsonl", "metrics": "metrics.jsonl"}

    session_data = {
        "version": "1.0.0",
        "session_id": session.session_id,
        "started_at": session.started_at,
        "finished_at": session.finished_at,
        "duration_ms": session.duration_ms,
        "status": (session.status if session.status in ["success", "failed", "running", "unknown"] else "unknown"),
        "labels": session.labels,
        "pipeline_name": session.pipeline_name,
        "oml_version": session.oml_version,
        "steps": {
            "total": session.steps_total,
            "completed": session.steps_ok,
            "failed": session.steps_failed,
            "success_rate": round(session.success_rate, 3),
        },
        "data_flow": {
            "rows_in": session.rows_in,
            "rows_out": session.rows_out,
            "tables": session.tables,
        },
        "diagnostics": {"errors": session.errors, "warnings": session.warnings},
        "artifacts": artifacts,
    }

    # Ensure deterministic JSON output
    return json.dumps(session_data, indent=2, sort_keys=True, ensure_ascii=False)


def validate_against_schema(json_str: str, schema_path: str) -> bool:
    """Validate JSON string against a schema file.

    Args:
        json_str: JSON string to validate
        schema_path: Path to JSON schema file

    Returns:
        True if valid, False otherwise

    Note: This is a lightweight validation that checks basic structure.
    For full validation, use jsonschema library if available.
    """
    try:
        data = json.loads(json_str)
        schema = json.loads(Path(schema_path).read_text())

        # Basic structural validation
        required_fields = schema.get("required", [])
        for field in required_fields:
            if field not in data:
                return False

        # Check version if specified
        if "properties" in schema and "version" in schema["properties"]:
            version_spec = schema["properties"]["version"]
            if "const" in version_spec and data.get("version") != version_spec["const"]:
                return False

        return True

    except (OSError, json.JSONDecodeError, KeyError):
        return False
