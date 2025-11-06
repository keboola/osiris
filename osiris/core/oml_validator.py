"""OML v0.1.0 validation logic."""

import re
from typing import Any

from ..components.registry import ComponentRegistry
from .mode_mapper import ModeMapper


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
        self.errors: list[dict[str, str]] = []
        self.warnings: list[dict[str, str]] = []
        self.registry = ComponentRegistry()

    def validate(self, oml: Any) -> tuple[bool, list[dict[str, str]], list[dict[str, str]]]:
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
            self.errors.append({"type": "invalid_type", "message": "OML must be a dictionary/object"})
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

    def _check_required_keys(self, oml: dict[str, Any]) -> None:
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

    def _check_forbidden_keys(self, oml: dict[str, Any]) -> None:
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

    def _get_connection_fields_info(self, component_spec: dict) -> dict:
        """
        Extract connection fields from component spec with override policies.

        Returns:
            {
                "fields": set of field names,
                "overrides": dict of {field_name: override_policy}
            }
        """
        if "x-connection-fields" not in component_spec:
            # Fallback to secrets for backward compatibility
            secrets = set()
            for secret_path in component_spec.get("secrets", []):
                field = secret_path.lstrip("/").split("/")[0]
                secrets.add(field)
            for secret_path in component_spec.get("x-secret", []):
                field = secret_path.lstrip("/").split("/")[0]
                secrets.add(field)
            return {"fields": secrets, "overrides": {f: "forbidden" for f in secrets}}

        conn_fields_def = component_spec["x-connection-fields"]

        # Handle simple array format: ["host", "port", ...]
        if isinstance(conn_fields_def, list) and len(conn_fields_def) > 0 and isinstance(conn_fields_def[0], str):
            return {"fields": set(conn_fields_def), "overrides": {f: "allowed" for f in conn_fields_def}}

        # Handle advanced format: [{name: "host", override: "allowed"}, ...]
        fields = set()
        overrides = {}
        for field_def in conn_fields_def:
            if isinstance(field_def, dict):
                name = field_def["name"]
                fields.add(name)
                overrides[name] = field_def.get("override", "allowed")
            else:
                # Fallback for mixed format
                fields.add(field_def)
                overrides[field_def] = "allowed"

        return {"fields": fields, "overrides": overrides}

    def _validate_version(self, oml: dict[str, Any]) -> None:
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

    def _validate_name(self, oml: dict[str, Any]) -> None:
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
            self.errors.append({"type": "empty_name", "message": "name cannot be empty", "location": "name"})

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

        step_ids: set[str] = set()
        all_step_ids: set[str] = {step.get("id") for step in steps if isinstance(step, dict) and "id" in step}

        for i, step in enumerate(steps):
            self._validate_step(step, i, step_ids, all_step_ids)

    def _validate_step(self, step: Any, index: int, step_ids: set[str], all_step_ids: set[str]) -> None:
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
            else:
                # Check if component exists in registry
                component_spec = self.registry.get_component(component)
                if not component_spec:
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
            elif component and isinstance(component, str):
                # Check if mode is compatible with component
                component_spec = self.registry.get_component(component)
                if component_spec:
                    component_modes = component_spec.get("modes", [])
                    if not ModeMapper.is_mode_compatible(mode, component_modes):
                        # Find which canonical modes are allowed
                        allowed_canonical = [
                            m
                            for m in ModeMapper.get_canonical_modes()
                            if ModeMapper.is_mode_compatible(m, component_modes)
                        ]
                        self.errors.append(
                            {
                                "type": "incompatible_mode",
                                "message": f"Step '{step_id}': mode '{mode}' not supported by component '{component}'. Allowed: {', '.join(allowed_canonical)}",
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

    def _validate_step_config(self, config: dict[str, Any], component: str | None, location: str) -> None:
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

        # Business Logic Validation
        # ------------------------
        # These validations match the compiler's business rules to provide early feedback
        # and prevent "valid OML" that fails at compilation time.

        if component:
            # 1. Primary Key Requirement for Writers with replace/upsert modes
            # Components that support write_mode: mysql.writer, supabase.writer, duckdb.writer
            # Note: mysql.writer uses "mode" field, while supabase.writer uses "write_mode"
            writer_components = {
                "mysql.writer",
                "supabase.writer",
                "duckdb.writer",
                "filesystem.csv_writer",  # if it supports write_mode
            }

            if component in writer_components:
                # Check both "write_mode" (Supabase) and "mode" (MySQL) fields
                write_mode_value = config.get("write_mode", config.get("mode"))

                if write_mode_value in {"replace", "upsert"}:
                    # Primary key is required for replace and upsert operations
                    if "primary_key" not in config:
                        self.errors.append(
                            {
                                "type": "missing_required_field",
                                "message": f"'primary_key' is required when write_mode is '{write_mode_value}'",
                                "location": f"{location}.primary_key",
                            }
                        )

            # 2. Write Mode Validation
            # Warn about unknown write modes (valid values: append, replace, upsert, truncate)
            write_mode = config.get("write_mode")
            mode = config.get("mode")
            mode_value = write_mode or mode

            if mode_value is not None:
                valid_write_modes = {"append", "replace", "upsert", "truncate"}
                if mode_value not in valid_write_modes:
                    self.warnings.append(
                        {
                            "type": "unknown_write_mode",
                            "message": f"Unknown write mode '{mode_value}' (expected one of: {', '.join(sorted(valid_write_modes))})",
                            "location": f"{location}.{'write_mode' if write_mode else 'mode'}",
                        }
                    )

        # Reserved keys that don't need to be in component spec
        reserved_keys = {"connection"}

        # Validate config keys against component spec
        if component:
            component_spec = self.registry.get_component(component)
            if component_spec and "configSchema" in component_spec:
                schema = component_spec["configSchema"]
                allowed_fields = set(schema.get("properties", {}).keys())
                required_fields = set(schema.get("required", []))

                # Check for unknown keys
                for key in config:
                    if key not in allowed_fields and key not in reserved_keys:
                        self.errors.append(
                            {
                                "type": "unknown_config_key",
                                "message": f"Unknown configuration key '{key}' for component '{component}'",
                                "location": f"{location}.{key}",
                            }
                        )

                # Check for missing required keys
                # If connection reference is provided, skip validation of connection-provided fields
                has_connection_ref = (
                    "connection" in config
                    and isinstance(config["connection"], str)
                    and config["connection"].startswith("@")
                )

                if has_connection_ref and component:
                    # Get connection fields from spec
                    conn_info = self._get_connection_fields_info(component_spec)
                    connection_provided = conn_info["fields"]
                    override_policies = conn_info["overrides"]

                    # Check for invalid overrides
                    for key in config:
                        if key in override_policies:
                            policy = override_policies[key]
                            if policy == "forbidden":
                                self.errors.append(
                                    {
                                        "type": "forbidden_override",
                                        "message": f"Cannot override connection field '{key}' (policy: forbidden)",
                                        "location": f"{location}.{key}",
                                    }
                                )
                            elif policy == "warning":
                                self.warnings.append(
                                    {
                                        "type": "override_warning",
                                        "message": f"Overriding connection field '{key}' (consider using connection value)",
                                        "location": f"{location}.{key}",
                                    }
                                )
                else:
                    connection_provided = set()

                for req_key in required_fields:
                    # Skip if it's a reserved key
                    if req_key in reserved_keys:
                        continue
                    # Skip connection-provided fields when connection ref is used
                    if has_connection_ref and req_key in connection_provided:
                        continue
                    # Otherwise check if required key is missing
                    if req_key not in config:
                        self.errors.append(
                            {
                                "type": "missing_config_key",
                                "message": f"Missing required configuration key '{req_key}' for component '{component}'",
                                "location": f"{location}.{req_key}",
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

    def _check_unknown_keys(self, oml: dict[str, Any]) -> None:
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
