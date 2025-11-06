"""Component Registry for Osiris Pipeline.

This module provides centralized management of component specifications including
loading, validation, caching, and secret mapping. It serves as the single source
of truth for component capabilities and configuration schemas.
"""

import json
import logging
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator, ValidationError
import yaml

from ..core.session_logging import SessionContext
from .error_mapper import FriendlyError, FriendlyErrorMapper

logger = logging.getLogger(__name__)


class ComponentRegistry:
    """Registry for loading and managing component specifications."""

    def __init__(self, root: Path | None = None, session_context: SessionContext | None = None):
        """Initialize the registry.

        Args:
            root: Root directory containing component specs. Defaults to 'components/'.
            session_context: Optional session context for logging integration.
        """
        if root:
            self.root = Path(root)
        else:
            # Default: look for components/ relative to package installation
            # This supports both development (cwd) and installed package (site-packages)
            package_dir = Path(__file__).parent.parent.parent  # osiris/components/registry.py -> project root
            installed_components = package_dir / "components"

            if installed_components.exists():
                # Found in installed package location (site-packages/components/)
                self.root = installed_components
            elif Path("components").exists():
                # Development mode: components/ in current directory
                self.root = Path("components")
            elif (Path("..") / "components").exists():
                # Testing mode: components/ in parent directory
                self.root = Path("..") / "components"
            else:
                # Fallback to default (will warn later if not found)
                self.root = Path("components")

        self.session_context = session_context
        self._cache: dict[str, dict[str, Any]] = {}
        self._mtime_cache: dict[str, float] = {}
        self._schema: dict[str, Any] | None = None

        # Load the JSON Schema for validation
        self._load_schema()

    def _load_schema(self) -> None:
        """Load the component spec JSON Schema."""
        schema_path = self.root / "spec.schema.json"
        if not schema_path.exists():
            logger.warning(f"Schema not found at {schema_path}")
            return

        try:
            with open(schema_path) as f:
                self._schema = json.load(f)
            logger.debug(f"Loaded schema from {schema_path}")
        except Exception as e:
            logger.error(f"Failed to load schema: {e}")
            self._schema = None

    def _is_cache_valid(self, name: str, spec_path: Path) -> bool:
        """Check if cached spec is still valid based on mtime."""
        if name not in self._cache:
            return False

        current_mtime = spec_path.stat().st_mtime
        cached_mtime = self._mtime_cache.get(name, 0)
        return current_mtime == cached_mtime

    def _load_spec_file(self, spec_path: Path) -> dict[str, Any]:
        """Load a spec file (YAML or JSON)."""
        content = spec_path.read_text()
        if spec_path.suffix in [".yaml", ".yml"]:
            return yaml.safe_load(content)
        else:
            return json.loads(content)

    def load_specs(self, root: Path | None = None) -> dict[str, dict[str, Any]]:
        """Load all component specs from the root directory.

        Args:
            root: Optional override for root directory.

        Returns:
            Dictionary mapping component names to their specifications.
        """
        search_root = Path(root) if root else self.root

        if not search_root.exists():
            logger.warning(f"Components directory not found at {search_root}")
            return {}

        specs = {}
        errors = []

        # Log loading start
        if self.session_context:
            self.session_context.log_event("registry_load_start", root=str(search_root))

        for component_dir in sorted(search_root.iterdir()):
            if not component_dir.is_dir():
                continue

            spec_file = component_dir / "spec.yaml"
            if not spec_file.exists():
                spec_file = component_dir / "spec.json"
                if not spec_file.exists():
                    continue

            try:
                spec = self._load_spec_file(spec_file)
                name = spec.get("name", component_dir.name)

                # Basic validation - skip invalid specs
                if self._schema:
                    validator = Draft202012Validator(self._schema)
                    validation_errors = list(validator.iter_errors(spec))
                    if validation_errors:
                        error_msg = f"Invalid spec {spec_file}: {validation_errors[0].message}"
                        logger.warning(error_msg)
                        errors.append(error_msg)
                        continue

                specs[name] = spec

                # Update cache
                self._cache[name] = spec
                self._mtime_cache[name] = spec_file.stat().st_mtime

                logger.debug(f"Loaded component spec: {name}")

            except Exception as e:
                error_msg = f"Failed to load {spec_file}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        # Log loading complete
        if self.session_context:
            self.session_context.log_event(
                "registry_load_complete",
                root=str(search_root),
                components_loaded=len(specs),
                errors=errors,
            )

        return specs

    def get_component(self, name: str) -> dict[str, Any] | None:
        """Get a specific component specification by name.

        Args:
            name: Component name.

        Returns:
            Component specification or None if not found.
        """
        # Check cache first
        spec_path = self.root / name / "spec.yaml"
        if not spec_path.exists():
            spec_path = self.root / name / "spec.json"

        if spec_path.exists():
            if self._is_cache_valid(name, spec_path):
                return self._cache[name]

            # Load fresh
            try:
                spec = self._load_spec_file(spec_path)
                self._cache[name] = spec
                self._mtime_cache[name] = spec_path.stat().st_mtime
                return spec
            except Exception as e:
                logger.error(f"Failed to load component {name}: {e}")
                return None

        # Try loading all if not found (in case new components were added)
        self.load_specs()
        return self._cache.get(name)

    def list_components(self, mode: str | None = None) -> list[dict[str, Any]]:
        """List all available components, optionally filtered by mode.

        Args:
            mode: Optional mode to filter by (e.g., 'extract', 'write').

        Returns:
            List of component summaries.
        """
        # Ensure specs are loaded
        if not self._cache:
            self.load_specs()

        components = []
        for name, spec in self._cache.items():
            # Filter by mode if specified
            if mode and mode not in spec.get("modes", []):
                continue

            components.append(
                {
                    "name": spec.get("name", name),
                    "version": spec.get("version", "unknown"),
                    "modes": spec.get("modes", []),
                    "title": spec.get("title", ""),
                    "description": spec.get("description", "")[:100] + "...",
                    "capabilities": {k: v for k, v in spec.get("capabilities", {}).items() if v},
                }
            )

        return sorted(components, key=lambda x: x["name"])

    def validate_spec(
        self, name_or_path: str, level: Literal["basic", "enhanced", "strict"] = "basic"
    ) -> tuple[bool, list[str | dict[str, Any]]]:
        """Validate a component specification at various levels.

        Args:
            name_or_path: Component name or path to spec file.
            level: Validation level:
                   - basic: Validate against spec.schema.json
                   - enhanced: Also validate configSchema is valid JSON Schema
                   - strict: Also perform semantic validation (aliases, pointers, etc.)

        Returns:
            Tuple of (is_valid, list_of_errors) where errors can be strings or dicts with friendly info
        """
        errors = []
        mapper = FriendlyErrorMapper()

        # Get the spec
        spec = None
        if Path(name_or_path).exists():
            # It's a path
            try:
                spec = self._load_spec_file(Path(name_or_path))
            except Exception as e:
                errors.append(f"Failed to load spec file: {e}")
                return False, errors
        else:
            # It's a component name
            spec = self.get_component(name_or_path)
            if not spec:
                errors.append(f"Component '{name_or_path}' not found")
                return False, errors

        # Log validation start
        if self.session_context:
            self.session_context.log_event("component_validation_start", component=name_or_path, level=level)

        # Basic validation against schema
        if self._schema:
            validator = Draft202012Validator(self._schema)
            for error in validator.iter_errors(spec):
                # Create structured error with both technical and friendly info
                error_dict = {
                    "message": error.message,
                    "path": "/" + "/".join(str(x) for x in error.absolute_path),
                    "validator": error.validator,
                    "schema_path": list(error.absolute_schema_path),
                    "instance": error.instance,
                    "schema": error.schema,
                }

                # Map to friendly error
                friendly = mapper.map_error(error_dict)

                # Store as dict with both friendly and technical details
                errors.append(
                    {
                        "friendly": friendly,
                        "technical": f"Schema validation: {error.message} at {' -> '.join(str(x) for x in error.absolute_path)}",
                    }
                )

        if errors:
            return False, errors

        # Enhanced validation - check configSchema is valid JSON Schema
        if level in ["enhanced", "strict"]:
            config_schema = spec.get("configSchema", {})
            try:
                Draft202012Validator.check_schema(config_schema)
            except Exception as e:
                friendly = mapper.map_error(e)
                errors.append({"friendly": friendly, "technical": f"Invalid configSchema: {str(e)}"})

            # Validate examples against configSchema
            if "examples" in spec and "configSchema" in spec:
                config_validator = Draft202012Validator(config_schema)
                for i, example in enumerate(spec.get("examples", [])):
                    if "config" in example:
                        try:
                            config_validator.validate(example["config"])
                        except ValidationError as e:
                            error_dict = {
                                "message": e.message,
                                "path": "/" + "/".join(str(x) for x in e.absolute_path),
                                "validator": e.validator,
                                "schema_path": list(e.absolute_schema_path),
                                "instance": e.instance,
                                "schema": e.schema,
                            }
                            friendly = mapper.map_error(error_dict)
                            errors.append(
                                {
                                    "friendly": friendly,
                                    "technical": f"Example {i+1} invalid: {e.message}",
                                }
                            )

        # Strict validation - semantic checks
        if level == "strict":
            errors.extend(self._validate_semantic(spec))

        # Log validation result
        if self.session_context:
            self.session_context.log_event(
                "component_validation_complete",
                component=name_or_path,
                level=level,
                is_valid=len(errors) == 0,
                error_count=len(errors),
            )

        return len(errors) == 0, errors

    def _validate_semantic(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        """Perform semantic validation on a spec.

        Args:
            spec: Component specification to validate.

        Returns:
            List of semantic validation errors with friendly info.
        """
        errors = []

        # Extract config field paths
        config_fields = self._extract_config_fields(spec.get("configSchema", {}))

        # Validate JSON Pointer references in secrets
        for pointer in spec.get("secrets", []):
            if not self._validate_json_pointer(pointer, config_fields):
                technical = f"Secret pointer '{pointer}' doesn't reference a valid config field"
                friendly = FriendlyError(
                    category="constraint_error",
                    field_label="Secret Field Reference",
                    problem=f"The secret pointer '{pointer}' doesn't match any configuration field",
                    fix_hint=f"Check that '{pointer}' points to an actual field in configSchema",
                    example="secrets:\n  - /password  # Must match a field in configSchema",
                )
                errors.append({"friendly": friendly, "technical": technical})

        # Validate redaction extras
        if "redaction" in spec and "extras" in spec["redaction"]:
            for pointer in spec["redaction"]["extras"]:
                if not self._validate_json_pointer(pointer, config_fields):
                    technical = f"Redaction pointer '{pointer}' doesn't reference a valid config field"
                    friendly = FriendlyError(
                        category="constraint_error",
                        field_label="Redaction Field Reference",
                        problem=f"The redaction pointer '{pointer}' doesn't match any configuration field",
                        fix_hint=f"Ensure '{pointer}' points to an existing field in configSchema",
                        example="redaction:\n  extras:\n    - /host  # Must match a field in configSchema",
                    )
                    errors.append({"friendly": friendly, "technical": technical})

        # Validate input aliases
        if "llmHints" in spec and "inputAliases" in spec["llmHints"]:
            config_schema = spec.get("configSchema", {})
            if "properties" in config_schema:
                valid_fields = set(config_schema["properties"].keys())
                for alias_key in spec["llmHints"]["inputAliases"]:
                    if alias_key not in valid_fields:
                        technical = (
                            f"Input alias '{alias_key}' doesn't match any config field. "
                            f"Valid fields: {', '.join(sorted(valid_fields))}"
                        )
                        friendly = FriendlyError(
                            category="constraint_error",
                            field_label="LLM Input Alias",
                            problem=f"The alias '{alias_key}' doesn't match any configuration field",
                            fix_hint=f"Use one of these fields: {', '.join(sorted(valid_fields))}",
                            example="llmHints:\n  inputAliases:\n    host:  # Must be an actual field name\n      - hostname\n      - server",
                        )
                        errors.append({"friendly": friendly, "technical": technical})

        return errors

    def _extract_config_fields(self, schema_obj: dict[str, Any], prefix: str = "") -> set[str]:
        """Extract all field paths from a JSON Schema.

        Args:
            schema_obj: JSON Schema object.
            prefix: Path prefix for recursion.

        Returns:
            Set of field paths.
        """
        fields = set()

        if not isinstance(schema_obj, dict):
            return fields

        # Handle properties
        if "properties" in schema_obj:
            for field_name, field_schema in schema_obj["properties"].items():
                field_path = f"{prefix}/{field_name}" if prefix else field_name
                fields.add(field_path)
                # Recursively extract nested fields
                if isinstance(field_schema, dict):
                    fields.update(self._extract_config_fields(field_schema, field_path))

        # Handle items (for arrays)
        if "items" in schema_obj:
            fields.update(self._extract_config_fields(schema_obj["items"], f"{prefix}/[]"))

        return fields

    def _validate_json_pointer(self, pointer: str, config_fields: set[str]) -> bool:
        """Validate a JSON Pointer references a valid field.

        Args:
            pointer: JSON Pointer string.
            config_fields: Set of valid config field paths.

        Returns:
            True if pointer is valid.
        """
        # Remove leading slash and check if path exists
        path = pointer[1:] if pointer.startswith("/") else pointer
        path_parts = path.split("/")

        # Check if any config field starts with this path
        for field in config_fields:
            if field.startswith(path_parts[0]):
                return True

        # Allow common nested paths
        return path_parts[0] in ["auth", "credentials", "connection"]

    def get_secret_map(self, name: str) -> dict[str, list[str]]:
        """Get the secret mapping for a component for runtime redaction.

        Args:
            name: Component name.

        Returns:
            Dictionary with 'secrets' and 'redaction_extras' lists.
        """
        spec = self.get_component(name)
        if not spec:
            return {"secrets": [], "redaction_extras": []}

        result = {"secrets": spec.get("secrets", []), "redaction_extras": []}

        # Include redaction extras if present
        if "redaction" in spec and "extras" in spec["redaction"]:
            result["redaction_extras"] = spec["redaction"]["extras"]

        return result

    def clear_cache(self) -> None:
        """Clear the in-memory cache."""
        self._cache.clear()
        self._mtime_cache.clear()
        logger.debug("Component registry cache cleared")


# Module-level singleton instance
_registry: ComponentRegistry | None = None


def get_registry(root: Path | None = None, session_context: SessionContext | None = None) -> ComponentRegistry:
    """Get or create the global registry instance.

    Args:
        root: Optional root directory for components.
        session_context: Optional session context for logging.

    Returns:
        The global ComponentRegistry instance.
    """
    global _registry
    if _registry is None:
        _registry = ComponentRegistry(root, session_context)
    elif session_context and not _registry.session_context:
        # Update session context if provided
        _registry.session_context = session_context
    return _registry
