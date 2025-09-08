"""OML v0.1.0 validation logic."""

import re
from typing import Any, Dict, List, Optional, Set, Tuple


class OMLValidator:
    """Validates OML (Osiris Markup Language) files according to v0.1.0 spec."""

    # OML v0.1.0 contract
    REQUIRED_TOP_KEYS = {"oml_version", "name", "steps"}
    FORBIDDEN_TOP_KEYS = {"version", "connectors", "tasks", "outputs"}
    VALID_MODES = {"read", "write", "transform"}
    CONNECTION_REF_PATTERN = re.compile(r"^@[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+$")

    # Known component families
    KNOWN_COMPONENTS = {
        "mysql.extractor",
        "mysql.writer",
        "supabase.extractor",
        "supabase.writer",
        "duckdb.reader",
        "duckdb.writer",
        "duckdb.transformer",
        "filesystem.csv_writer",
        "filesystem.csv_reader",
        "filesystem.json_writer",
        "filesystem.json_reader",
    }

    def __init__(self):
        """Initialize the validator."""
        self.errors: List[Dict[str, str]] = []
        self.warnings: List[Dict[str, str]] = []

    def validate(self, oml: Any) -> Tuple[bool, List[Dict[str, str]], List[Dict[str, str]]]:
        """Validate an OML document.

        Args:
            oml: The OML document (should be a dict)

        Returns:
            Tuple of (is_valid, errors, warnings)
        """
        self.errors = []
        self.warnings = []

        # Check basic structure
        if not isinstance(oml, dict):
            self.errors.append(
                {"type": "invalid_type", "message": "OML must be a dictionary/object"}
            )
            return False, self.errors, self.warnings

        # Check required top-level keys
        self._check_required_keys(oml)

        # Check forbidden keys
        self._check_forbidden_keys(oml)

        # Validate OML version
        self._validate_version(oml)

        # Validate name
        self._validate_name(oml)

        # Validate steps
        if "steps" in oml:
            self._validate_steps(oml["steps"])

        # Check for unknown top-level keys (warnings)
        self._check_unknown_keys(oml)

        return len(self.errors) == 0, self.errors, self.warnings

    def _check_required_keys(self, oml: Dict[str, Any]) -> None:
        """Check for required top-level keys."""
        missing = self.REQUIRED_TOP_KEYS - set(oml.keys())
        for key in missing:
            self.errors.append(
                {
                    "type": "missing_required_key",
                    "message": f"Missing required top-level key: '{key}'",
                    "location": "root",
                }
            )

    def _check_forbidden_keys(self, oml: Dict[str, Any]) -> None:
        """Check for forbidden top-level keys."""
        forbidden = self.FORBIDDEN_TOP_KEYS & set(oml.keys())
        for key in forbidden:
            self.errors.append(
                {
                    "type": "forbidden_key",
                    "message": f"Forbidden top-level key: '{key}' (use 'oml_version' instead of 'version')",
                    "location": "root",
                }
            )

    def _validate_version(self, oml: Dict[str, Any]) -> None:
        """Validate OML version."""
        version = oml.get("oml_version")
        if version is None:
            return  # Already caught by required keys check

        if not isinstance(version, str):
            self.errors.append(
                {
                    "type": "invalid_version_type",
                    "message": f"oml_version must be a string, got {type(version).__name__}",
                    "location": "oml_version",
                }
            )
            return

        if version != "0.1.0":
            self.warnings.append(
                {
                    "type": "unsupported_version",
                    "message": f"OML version '{version}' may not be fully supported (expected '0.1.0')",
                    "location": "oml_version",
                }
            )

    def _validate_name(self, oml: Dict[str, Any]) -> None:
        """Validate pipeline name."""
        name = oml.get("name")
        if name is None:
            return  # Already caught by required keys check

        if not isinstance(name, str):
            self.errors.append(
                {
                    "type": "invalid_name_type",
                    "message": f"name must be a string, got {type(name).__name__}",
                    "location": "name",
                }
            )
            return

        if not name.strip():
            self.errors.append(
                {"type": "empty_name", "message": "name cannot be empty", "location": "name"}
            )

        # Check naming convention (warning only)
        if not re.match(r"^[a-z0-9][a-z0-9-]*$", name):
            self.warnings.append(
                {
                    "type": "naming_convention",
                    "message": f"Pipeline name '{name}' doesn't follow naming convention (lowercase, hyphens)",
                    "location": "name",
                }
            )

    def _validate_steps(self, steps: Any) -> None:
        """Validate pipeline steps."""
        if not isinstance(steps, list):
            self.errors.append(
                {
                    "type": "invalid_steps_type",
                    "message": f"steps must be a list, got {type(steps).__name__}",
                    "location": "steps",
                }
            )
            return

        if not steps:
            self.errors.append(
                {
                    "type": "empty_steps",
                    "message": "Pipeline must have at least one step",
                    "location": "steps",
                }
            )
            return

        step_ids: Set[str] = set()
        all_step_ids: Set[str] = {
            step.get("id") for step in steps if isinstance(step, dict) and "id" in step
        }

        for i, step in enumerate(steps):
            self._validate_step(step, i, step_ids, all_step_ids)

    def _validate_step(
        self, step: Any, index: int, step_ids: Set[str], all_step_ids: Set[str]
    ) -> None:
        """Validate a single step."""
        location = f"steps[{index}]"

        if not isinstance(step, dict):
            self.errors.append(
                {
                    "type": "invalid_step_type",
                    "message": f"Step must be a dictionary, got {type(step).__name__}",
                    "location": location,
                }
            )
            return

        # Required step fields
        required = {"id", "component", "mode"}
        missing = required - set(step.keys())
        for field in missing:
            self.errors.append(
                {
                    "type": "missing_step_field",
                    "message": f"Step missing required field: '{field}'",
                    "location": f"{location}.{field}",
                }
            )

        # Validate ID
        step_id = step.get("id")
        if step_id:
            if not isinstance(step_id, str):
                self.errors.append(
                    {
                        "type": "invalid_id_type",
                        "message": f"Step ID must be a string, got {type(step_id).__name__}",
                        "location": f"{location}.id",
                    }
                )
            elif step_id in step_ids:
                self.errors.append(
                    {
                        "type": "duplicate_id",
                        "message": f"Duplicate step ID: '{step_id}'",
                        "location": f"{location}.id",
                    }
                )
            else:
                step_ids.add(step_id)

        # Validate component
        component = step.get("component")
        if component:
            if not isinstance(component, str):
                self.errors.append(
                    {
                        "type": "invalid_component_type",
                        "message": f"Component must be a string, got {type(component).__name__}",
                        "location": f"{location}.component",
                    }
                )
            elif component not in self.KNOWN_COMPONENTS:
                self.warnings.append(
                    {
                        "type": "unknown_component",
                        "message": f"Unknown component: '{component}'",
                        "location": f"{location}.component",
                    }
                )

        # Validate mode
        mode = step.get("mode")
        if mode:
            if not isinstance(mode, str):
                self.errors.append(
                    {
                        "type": "invalid_mode_type",
                        "message": f"Mode must be a string, got {type(mode).__name__}",
                        "location": f"{location}.mode",
                    }
                )
            elif mode not in self.VALID_MODES:
                self.errors.append(
                    {
                        "type": "invalid_mode",
                        "message": f"Invalid mode: '{mode}' (must be one of: {', '.join(self.VALID_MODES)})",
                        "location": f"{location}.mode",
                    }
                )

        # Validate needs (dependencies)
        needs = step.get("needs")
        if needs is not None:
            if not isinstance(needs, list):
                self.errors.append(
                    {
                        "type": "invalid_needs_type",
                        "message": f"needs must be a list, got {type(needs).__name__}",
                        "location": f"{location}.needs",
                    }
                )
            else:
                for dep in needs:
                    if not isinstance(dep, str):
                        self.errors.append(
                            {
                                "type": "invalid_dependency_type",
                                "message": f"Dependency must be a string, got {type(dep).__name__}",
                                "location": f"{location}.needs",
                            }
                        )
                    elif dep not in all_step_ids:
                        self.errors.append(
                            {
                                "type": "unknown_dependency",
                                "message": f"Unknown dependency: '{dep}'",
                                "location": f"{location}.needs",
                            }
                        )

        # Validate config
        config = step.get("config")
        if config is not None:
            if not isinstance(config, dict):
                self.errors.append(
                    {
                        "type": "invalid_config_type",
                        "message": f"config must be a dictionary, got {type(config).__name__}",
                        "location": f"{location}.config",
                    }
                )
            else:
                self._validate_step_config(config, component, f"{location}.config")

    def _validate_step_config(
        self, config: Dict[str, Any], component: Optional[str], location: str
    ) -> None:
        """Validate step configuration."""
        # Check connection references
        connection = config.get("connection")
        if (
            connection
            and isinstance(connection, str)
            and connection.startswith("@")
            and not self.CONNECTION_REF_PATTERN.match(connection)
        ):
            self.errors.append(
                {
                    "type": "invalid_connection_ref",
                    "message": f"Invalid connection reference: '{connection}' (expected format: '@family.alias')",
                    "location": f"{location}.connection",
                }
            )

        # Component-specific validation
        if component == "filesystem.csv_writer":
            if "path" not in config:
                self.errors.append(
                    {
                        "type": "missing_config_field",
                        "message": "filesystem.csv_writer requires 'path' in config",
                        "location": f"{location}.path",
                    }
                )

            # Validate optional fields
            delimiter = config.get("delimiter")
            if delimiter is not None and not isinstance(delimiter, str):
                self.errors.append(
                    {
                        "type": "invalid_config_value",
                        "message": f"delimiter must be a string, got {type(delimiter).__name__}",
                        "location": f"{location}.delimiter",
                    }
                )

            encoding = config.get("encoding")
            if encoding and encoding not in {"utf-8", "utf-16", "ascii", "latin-1"}:
                self.warnings.append(
                    {
                        "type": "unsupported_encoding",
                        "message": f"Encoding '{encoding}' may not be supported",
                        "location": f"{location}.encoding",
                    }
                )

            newline = config.get("newline")
            if newline and newline not in {"lf", "crlf"}:
                self.errors.append(
                    {
                        "type": "invalid_config_value",
                        "message": f"newline must be 'lf' or 'crlf', got '{newline}'",
                        "location": f"{location}.newline",
                    }
                )

    def _check_unknown_keys(self, oml: Dict[str, Any]) -> None:
        """Check for unknown top-level keys (warnings)."""
        known = self.REQUIRED_TOP_KEYS | {"description", "metadata", "schedule"}
        unknown = set(oml.keys()) - known - self.FORBIDDEN_TOP_KEYS

        for key in unknown:
            self.warnings.append(
                {
                    "type": "unknown_key",
                    "message": f"Unknown top-level key: '{key}'",
                    "location": "root",
                }
            )
