"""OML schema validation guard for ensuring correct pipeline format."""

import logging
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def check_oml_schema(pipeline_yaml: str) -> tuple[bool, str | None, dict[str, Any] | None]:
    """Check if the pipeline YAML conforms to OML v0.1.0 schema.

    Args:
        pipeline_yaml: The YAML string to validate

    Returns:
        (is_valid, error_message, parsed_data)
    """
    try:
        # Parse the YAML
        data = yaml.safe_load(pipeline_yaml)

        if not isinstance(data, dict):
            return False, "Pipeline must be a YAML dictionary", None

        # Check for legacy keys that MUST NOT exist
        legacy_keys = {"version", "connectors", "tasks", "outputs", "schedule"}
        found_legacy = legacy_keys & set(data.keys())
        if found_legacy:
            return (
                False,
                f"Found legacy schema keys that are not OML: {', '.join(found_legacy)}. "
                f"Use 'oml_version' instead of 'version', 'steps' instead of 'tasks'.",
                data,
            )

        # Check for required OML keys
        if "oml_version" not in data:
            return False, "Missing required 'oml_version' field. Must be '0.1.0'", data

        if data["oml_version"] != "0.1.0":
            return False, f"Invalid oml_version '{data['oml_version']}'. Must be '0.1.0'", data

        if "name" not in data:
            return False, "Missing required 'name' field", data

        if "steps" not in data:
            return False, "Missing required 'steps' field. Use 'steps' not 'tasks'", data

        if not isinstance(data["steps"], list):
            return False, "'steps' must be an array", data

        if len(data["steps"]) == 0:
            return False, "'steps' array cannot be empty", data

        # Validate each step has minimum required fields
        for i, step in enumerate(data["steps"]):
            if not isinstance(step, dict):
                return False, f"Step {i} must be a dictionary", data

            required_step_fields = ["id", "component", "mode", "config"]
            for field in required_step_fields:
                if field not in step:
                    return False, f"Step {i} missing required field '{field}'", data

            # Validate mode is correct
            valid_modes = {"read", "write", "transform"}
            if step["mode"] not in valid_modes:
                return (
                    False,
                    f"Step {i} has invalid mode '{step['mode']}'. Must be one of: {valid_modes}",
                    data,
                )

        return True, None, data

    except yaml.YAMLError as e:
        return False, f"Invalid YAML syntax: {e}", None
    except Exception as e:
        return False, f"Schema validation error: {e}", None


def create_oml_regeneration_prompt(
    _original_yaml: str, error_message: str, parsed_data: dict[str, Any] | None = None
) -> str:
    """Create a directed prompt for regenerating valid OML.

    Args:
        _original_yaml: The invalid YAML that was generated (unused but kept for API compatibility)
        error_message: The validation error message
        parsed_data: Parsed YAML data if available

    Returns:
        Regeneration prompt string
    """
    # Detect common issues and provide specific guidance
    guidance = []

    if parsed_data:
        if "tasks" in parsed_data:
            guidance.append("- Replace 'tasks:' with 'steps:'")
        if "version" in parsed_data:
            guidance.append("- Replace 'version: 1' with 'oml_version: \"0.1.0\"'")
        if "connectors" in parsed_data:
            guidance.append("- Remove 'connectors:' section - component configs go in each step")
        if "outputs" in parsed_data:
            guidance.append("- Remove 'outputs:' section - not part of OML")

    prompt = f"""Your last pipeline was not valid OML v0.1.0 format.

Error: {error_message}

Required OML structure:
```yaml
oml_version: "0.1.0"  # REQUIRED
name: pipeline-name   # REQUIRED
steps:               # REQUIRED (not 'tasks')
  - id: step-id
    component: mysql.extractor  # from available components
    mode: read           # read|write|transform
    config:
      query: "SELECT..."
      connection: "@default"
```

Specific fixes needed:
{chr(10).join(guidance) if guidance else '- Follow the OML structure above exactly'}

Generate ONLY the corrected OML YAML with the same functionality but proper schema."""

    return prompt


def create_mysql_csv_template(tables: list) -> str:
    """Create a deterministic OML template for MySQL to CSV export.

    Args:
        tables: List of table names to export

    Returns:
        Valid OML YAML string
    """
    steps = []
    for table in tables:
        steps.append(
            {
                "id": f"extract-{table}",
                "component": "mysql.extractor",
                "mode": "read",
                "config": {
                    "query": f"SELECT * FROM {table}",  # nosec B608
                    "connection": "@default",
                },
            }
        )
        steps.append(
            {
                "id": f"write-{table}-csv",
                "component": "duckdb.writer",
                "mode": "write",
                "needs": [f"extract-{table}"],
                "config": {
                    "format": "csv",
                    "path": f"./{table}.csv",
                    "delimiter": ",",
                    "header": True,
                },
            }
        )

    pipeline = {
        "oml_version": "0.1.0",
        "name": "mysql-to-csv-export",
        "description": f"Export {len(tables)} MySQL tables to CSV files",
        "steps": steps,
    }

    return yaml.dump(pipeline, default_flow_style=False, sort_keys=False)
