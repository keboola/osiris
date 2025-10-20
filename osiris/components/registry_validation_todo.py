"""
TODO for M1a.3: Component Registry Validation

This shows what needs to be implemented in the actual registry.
"""

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError
import yaml


class ComponentSpecValidator:
    """
    Full validation for component specifications.
    This needs to be integrated into osiris/components/registry.py in M1a.3
    """

    def __init__(self):
        # Load the spec schema
        schema_path = Path("components/spec.schema.json")
        with open(schema_path) as f:
            self.schema = json.load(f)
        self.validator = Draft202012Validator(self.schema)

    def validate_spec(self, spec: dict[str, Any]) -> list[str]:
        """
        Validate a component spec with all levels of validation.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Level 1: Structural validation against spec.schema.json
        try:
            self.validator.validate(spec)
        except ValidationError as e:
            errors.append(f"Structural validation failed: {e.message}")
            return errors  # Can't continue if structure is invalid

        # Level 2: Validate configSchema is valid JSON Schema
        if "configSchema" in spec:
            try:
                Draft202012Validator.check_schema(spec["configSchema"])
            except Exception as e:
                errors.append(f"configSchema is not valid JSON Schema: {e}")

        # Level 3: Validate examples match configSchema
        if "examples" in spec and "configSchema" in spec:
            config_validator = Draft202012Validator(spec["configSchema"])
            for i, example in enumerate(spec["examples"]):
                if "config" in example:
                    try:
                        config_validator.validate(example["config"])
                    except ValidationError as e:
                        errors.append(f"Example {i+1} doesn't match configSchema: {e.message}")

        # Level 4: Validate inputAliases reference real fields
        if (
            "llmHints" in spec
            and "inputAliases" in spec["llmHints"]
            and "configSchema" in spec
            and "properties" in spec["configSchema"]
        ):
            config_fields = set(spec["configSchema"]["properties"].keys())
            for alias_key in spec["llmHints"]["inputAliases"]:
                if alias_key not in config_fields:
                    errors.append(
                        f"inputAlias key '{alias_key}' doesn't match any configSchema field. "
                        f"Available: {', '.join(config_fields)}"
                    )

        # Level 5: Validate JSON Pointers (basic check)
        for pointer_field in ["secrets", "sensitivePaths"]:
            if pointer_field in spec:
                for pointer in spec[pointer_field]:
                    if not pointer.startswith("/"):
                        errors.append(f"Invalid JSON Pointer in {pointer_field}: {pointer}")

        return errors


class ComponentRegistry:
    """
    This is what needs to be implemented in M1a.3.
    The registry MUST use the ComponentSpecValidator.
    """

    def __init__(self):
        self.validator = ComponentSpecValidator()
        self.components = {}

    def load_component(self, spec_path: Path) -> bool:
        """
        Load and validate a component spec.

        This is where the robust validation happens in the actual system!
        """
        # Load the spec file
        with open(spec_path) as f:
            spec = yaml.safe_load(f) if spec_path.suffix in [".yaml", ".yml"] else json.load(f)

        # CRITICAL: Validate with full validation
        errors = self.validator.validate_spec(spec)

        if errors:
            print(f"❌ Component {spec_path} validation failed:")
            for error in errors:
                print(f"   • {error}")
            return False

        # Store validated component
        component_name = spec["name"]
        self.components[component_name] = spec
        print(f"✅ Loaded component: {component_name} v{spec['version']}")
        return True

    def get_component(self, name: str) -> dict[str, Any]:
        """Get a validated component spec by name"""
        return self.components.get(name)

    def validate_config(self, component_name: str, config: dict[str, Any]) -> list[str]:
        """
        Validate a configuration against a component's configSchema.

        This is used at runtime to validate pipeline configurations!
        """
        if component_name not in self.components:
            return [f"Unknown component: {component_name}"]

        component = self.components[component_name]
        if "configSchema" not in component:
            return []  # No schema to validate against

        errors = []
        config_validator = Draft202012Validator(component["configSchema"])

        try:
            config_validator.validate(config)
        except ValidationError as e:
            errors.append(f"Config validation failed: {e.message}")

        return errors


# Example of how this will be used in M1a.3:
if __name__ == "__main__":
    # This is what the CLI will do
    registry = ComponentRegistry()

    # Load components (this happens at startup)
    registry.load_component(Path("components/mysql.table/spec.yaml"))
    registry.load_component(Path("components/supabase.table/spec.yaml"))

    # At runtime, when generating or running pipelines:
    config = {"connection": "@mysql", "table": "customers", "options": {"batchSize": 1000}}

    errors = registry.validate_config("mysql.table", config)
    if errors:
        print("Configuration errors:", errors)
    else:
        print("Configuration is valid!")
