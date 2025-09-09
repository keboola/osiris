"""Parameter resolution with precedence and profiles."""

import os
import re
from typing import Any, Dict, Optional, Set


class ParamsResolver:
    """Resolve parameters with proper precedence."""

    def __init__(self):
        self.params: Dict[str, Any] = {}
        self.unresolved: Set[str] = set()

    def load_params(
        self,
        defaults: Dict[str, Any] = None,
        env_prefix: str = "OSIRIS_PARAM_",
        cli_params: Dict[str, Any] = None,
        profile: Optional[str] = None,
        profiles: Dict[str, Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Load parameters with precedence: defaults < ENV < profile < CLI.

        Args:
            defaults: Default parameter values
            env_prefix: Environment variable prefix
            cli_params: CLI-provided parameters
            profile: Active profile name
            profiles: Available profiles

        Returns:
            Resolved parameter dictionary
        """
        self.params = {}

        # 1. Defaults (lowest precedence)
        if defaults:
            self.params.update(defaults)

        # 2. Environment variables
        for key, value in os.environ.items():
            if key.startswith(env_prefix):
                param_name = key[len(env_prefix) :].lower()
                self.params[param_name] = value

        # 3. Profile parameters
        if profile and profiles and profile in profiles:
            profile_params = profiles[profile].get("params", {})
            self.params.update(profile_params)

        # 4. CLI parameters (highest precedence)
        if cli_params:
            self.params.update(cli_params)

        return self.params

    def resolve_string(self, template: str) -> str:
        """
        Resolve ${params.*} placeholders in a string.

        Args:
            template: String with potential placeholders

        Returns:
            Resolved string

        Raises:
            ValueError: If unresolved parameters remain
        """
        pattern = re.compile(r"\$\{params\.([^}]+)\}")

        def replacer(match):
            param_name = match.group(1)
            if param_name in self.params:
                return str(self.params[param_name])
            else:
                self.unresolved.add(param_name)
                return match.group(0)  # Keep placeholder

        result = pattern.sub(replacer, template)

        if self.unresolved:
            raise ValueError(f"Unresolved parameters: {sorted(self.unresolved)}")

        return result

    def resolve_value(self, value: Any) -> Any:
        """
        Recursively resolve parameters in any value.

        Args:
            value: Value to resolve (string, dict, list, etc.)

        Returns:
            Resolved value
        """
        if isinstance(value, str):
            return self.resolve_string(value)
        elif isinstance(value, dict):
            return {k: self.resolve_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.resolve_value(v) for v in value]
        else:
            return value

    def resolve_oml(self, oml: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve all parameters in an OML document.

        Args:
            oml: OML document dictionary

        Returns:
            OML with resolved parameters

        Raises:
            ValueError: If unresolved parameters remain
        """
        self.unresolved.clear()

        # First extract defaults from OML params section
        oml_defaults = {}
        if "params" in oml:
            for param_name, param_def in oml["params"].items():
                if isinstance(param_def, dict) and "default" in param_def:
                    oml_defaults[param_name] = param_def["default"]
                elif not isinstance(param_def, dict):
                    # Simple value is the default
                    oml_defaults[param_name] = param_def

        # Merge with existing params (OML defaults have lowest precedence)
        merged_params = {}
        merged_params.update(oml_defaults)
        merged_params.update(self.params)
        self.params = merged_params

        # Now resolve the entire document
        resolved = self.resolve_value(oml)

        if self.unresolved:
            raise ValueError(f"Unresolved parameters: {sorted(self.unresolved)}")

        return resolved

    def get_effective_params(self) -> Dict[str, Any]:
        """Get the final resolved parameters."""
        return self.params.copy()
