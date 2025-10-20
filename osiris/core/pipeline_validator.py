"""Pipeline validation against component specifications.

This module validates OML (Osiris Markup Language) pipelines against
the component registry specifications, ensuring that generated pipelines
are valid before presentation to users.
"""

from dataclasses import dataclass, field
import logging
from typing import Any

import jsonschema
import yaml

from osiris.components.error_mapper import FriendlyErrorMapper
from osiris.components.registry import ComponentRegistry

logger = logging.getLogger(__name__)


@dataclass
class ValidationError:
    """Represents a single validation error with friendly and technical details."""

    component_type: str
    field_path: str
    error_type: str  # missing_field, type_error, enum_error, constraint_error
    friendly_message: str
    technical_message: str
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "component_type": self.component_type,
            "field_path": self.field_path,
            "error_type": self.error_type,
            "friendly_message": self.friendly_message,
            "technical_message": self.technical_message,
            "suggestion": self.suggestion,
        }


@dataclass
class ValidationResult:
    """Result of pipeline validation."""

    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    validated_components: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": self.warnings,
            "validated_components": self.validated_components,
            "error_count": len(self.errors),
            "error_categories": list({e.error_type for e in self.errors}),
        }

    def get_friendly_summary(self, limit: int = 3) -> str:
        """Get a friendly summary of validation errors."""
        if self.valid:
            return "✓ Pipeline validated successfully"

        lines = [f"❌ Pipeline validation failed with {len(self.errors)} error(s):"]

        # Group errors by component
        by_component = {}
        for error in self.errors[:limit]:
            if error.component_type not in by_component:
                by_component[error.component_type] = []
            by_component[error.component_type].append(error)

        for comp_type, comp_errors in by_component.items():
            lines.append(f"\n{comp_type}:")
            for error in comp_errors:
                lines.append(f"  • {error.friendly_message}")
                if error.suggestion:
                    lines.append(f"    → {error.suggestion}")

        if len(self.errors) > limit:
            lines.append(f"\n... and {len(self.errors) - limit} more error(s)")

        return "\n".join(lines)


class PipelineValidator:
    """Validates OML pipelines against component specifications."""

    def __init__(self, registry: ComponentRegistry | None = None):
        """Initialize validator with component registry.

        Args:
            registry: Component registry instance. If None, creates new instance.
        """
        self.registry = registry or ComponentRegistry()
        self.error_mapper = FriendlyErrorMapper()

    def validate_pipeline(self, pipeline_yaml: str) -> ValidationResult:
        """Validate an OML pipeline YAML string.

        Args:
            pipeline_yaml: YAML string containing the pipeline definition

        Returns:
            ValidationResult with validation status and any errors
        """
        try:
            # Parse YAML
            pipeline = yaml.safe_load(pipeline_yaml)
            if not pipeline:
                return ValidationResult(
                    valid=False,
                    errors=[
                        ValidationError(
                            component_type="pipeline",
                            field_path="/",
                            error_type="parse_error",
                            friendly_message="Pipeline is empty or invalid",
                            technical_message="YAML parsed to None or empty",
                            suggestion="Ensure the pipeline contains valid YAML",
                        )
                    ],
                )

            # Validate pipeline structure
            if not isinstance(pipeline, dict):
                return ValidationResult(
                    valid=False,
                    errors=[
                        ValidationError(
                            component_type="pipeline",
                            field_path="/",
                            error_type="structure_error",
                            friendly_message="Pipeline must be a YAML object",
                            technical_message=f"Expected dict, got {type(pipeline).__name__}",
                            suggestion="Ensure the pipeline starts with key-value pairs",
                        )
                    ],
                )

            # Extract steps
            steps = pipeline.get("steps", [])
            if not steps:
                return ValidationResult(
                    valid=False,
                    errors=[
                        ValidationError(
                            component_type="pipeline",
                            field_path="/steps",
                            error_type="missing_field",
                            friendly_message="Pipeline must have at least one step",
                            technical_message="No 'steps' field found",
                            suggestion="Add a 'steps' field with at least one step",
                        )
                    ],
                )

            # Validate each step
            all_errors = []
            validated_count = 0

            for i, step in enumerate(steps):
                step_errors = self._validate_step(step, i)
                all_errors.extend(step_errors)
                validated_count += 1

            return ValidationResult(valid=len(all_errors) == 0, errors=all_errors, validated_components=validated_count)

        except yaml.YAMLError as e:
            return ValidationResult(
                valid=False,
                errors=[
                    ValidationError(
                        component_type="pipeline",
                        field_path="/",
                        error_type="parse_error",
                        friendly_message="Failed to parse pipeline YAML",
                        technical_message=str(e),
                        suggestion="Check YAML syntax and indentation",
                    )
                ],
            )
        except Exception as e:
            logger.error(f"Unexpected error during validation: {e}")
            return ValidationResult(
                valid=False,
                errors=[
                    ValidationError(
                        component_type="pipeline",
                        field_path="/",
                        error_type="validation_error",
                        friendly_message="Unexpected error during validation",
                        technical_message=str(e),
                        suggestion="Check pipeline format and try again",
                    )
                ],
            )

    def _validate_step(self, step: dict[str, Any], index: int) -> list[ValidationError]:
        """Validate a single pipeline step.

        Args:
            step: Step configuration dictionary
            index: Step index in the pipeline

        Returns:
            List of validation errors for this step
        """
        errors = []
        step_path = f"/steps/{index}"

        # Check required step fields
        if not isinstance(step, dict):
            errors.append(
                ValidationError(
                    component_type="step",
                    field_path=step_path,
                    error_type="type_error",
                    friendly_message=f"Step {index + 1} must be an object",
                    technical_message=f"Expected dict, got {type(step).__name__}",
                    suggestion="Ensure each step is a YAML object with 'type' and 'config'",
                )
            )
            return errors

        # Get component type
        component_type = step.get("type")
        if not component_type:
            errors.append(
                ValidationError(
                    component_type="step",
                    field_path=f"{step_path}/type",
                    error_type="missing_field",
                    friendly_message=f"Step {index + 1} is missing 'type' field",
                    technical_message="No 'type' field in step",
                    suggestion="Add a 'type' field (e.g., 'mysql.extractor')",
                )
            )
            return errors

        # Get component spec
        spec = self.registry.get_component(component_type)
        if not spec:
            errors.append(
                ValidationError(
                    component_type=component_type,
                    field_path=f"{step_path}/type",
                    error_type="unknown_component",
                    friendly_message=f"Unknown component type: {component_type}",
                    technical_message=f"Component '{component_type}' not found in registry",
                    suggestion="Use a valid component type (e.g., 'mysql.extractor', 'supabase.writer')",
                )
            )
            return errors

        # Get step config
        config = step.get("config", {})
        if not isinstance(config, dict):
            errors.append(
                ValidationError(
                    component_type=component_type,
                    field_path=f"{step_path}/config",
                    error_type="type_error",
                    friendly_message=f"Step {index + 1} config must be an object",
                    technical_message=f"Expected dict, got {type(config).__name__}",
                    suggestion="Ensure 'config' is a YAML object with component settings",
                )
            )
            return errors

        # Validate config against component's configSchema
        config_schema = spec.get("configSchema", {})
        if config_schema:
            # Use jsonschema validator to collect all errors
            validator = jsonschema.Draft7Validator(config_schema)
            validation_errors = list(validator.iter_errors(config))

            for e in validation_errors:
                try:
                    # Convert jsonschema error to our ValidationError
                    field_path = "/" + "/".join(str(p) for p in e.absolute_path) if e.absolute_path else ""

                    # Determine error type based on validation error
                    error_type = "validation_error"
                    if e.validator == "required":
                        error_type = "missing_field"
                    elif e.validator == "type":
                        error_type = "type_error"
                    elif e.validator == "enum":
                        error_type = "enum_error"
                    elif e.validator in ["minimum", "maximum", "minLength", "maxLength"]:
                        error_type = "constraint_error"

                    # Use FriendlyErrorMapper if available
                    error_dict = {
                        "path": field_path,
                        "message": e.message,
                        "validator": e.validator,
                    }

                    # Add validator_value if present
                    if hasattr(e, "validator_value"):
                        error_dict["validator_value"] = e.validator_value

                    friendly = self.error_mapper.map_error(error_dict)

                    errors.append(
                        ValidationError(
                            component_type=component_type,
                            field_path=f"{step_path}/config{field_path}",
                            error_type=error_type,
                            friendly_message=f"{friendly.field_label}: {friendly.problem}",
                            technical_message=e.message,
                            suggestion=friendly.fix_hint,
                        )
                    )
                except Exception as map_error:
                    # Fallback if error mapping fails
                    logger.debug(f"Failed to map error: {map_error}")
                    errors.append(
                        ValidationError(
                            component_type=component_type,
                            field_path=f"{step_path}/config{field_path}",
                            error_type=error_type,
                            friendly_message=e.message,
                            technical_message=e.message,
                            suggestion=None,
                        )
                    )

        return errors

    def validate_pipeline_dict(self, pipeline: dict[str, Any]) -> ValidationResult:
        """Validate a pipeline dictionary.

        Args:
            pipeline: Pipeline dictionary

        Returns:
            ValidationResult with validation status and any errors
        """
        # Convert to YAML and validate
        pipeline_yaml = yaml.dump(pipeline, default_flow_style=False)
        return self.validate_pipeline(pipeline_yaml)

    def get_retry_prompt_context(self, errors: list[ValidationError], limit: int = 5) -> str:
        """Generate context for LLM retry prompt.

        Args:
            errors: List of validation errors
            limit: Maximum number of errors to include

        Returns:
            Formatted string for inclusion in retry prompt
        """
        if not errors:
            return ""

        lines = ["Please fix the following validation errors:"]

        # Group by component and limit
        shown_errors = errors[:limit]
        by_component = {}
        for error in shown_errors:
            if error.component_type not in by_component:
                by_component[error.component_type] = []
            by_component[error.component_type].append(error)

        for comp_type, comp_errors in by_component.items():
            lines.append(f"\n{comp_type}:")
            for error in comp_errors:
                field = error.field_path.split("/config/")[-1] if "/config/" in error.field_path else error.field_path
                lines.append(f"  - {field}: {error.friendly_message}")
                if error.suggestion:
                    lines.append(f"    Fix: {error.suggestion}")

        if len(errors) > limit:
            lines.append(f"\n(Showing {limit} of {len(errors)} errors)")

        lines.append("\nKeep all other fields unchanged.")

        return "\n".join(lines)
