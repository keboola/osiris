"""Build minimal component context for LLM consumption.

This module extracts essential component information from the registry
and creates a compact JSON context optimized for token efficiency.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from jsonschema import Draft202012Validator, ValidationError

from ..components.registry import get_registry
from ..core.session_logging import get_current_session

logger = logging.getLogger(__name__)

# Context schema version - increment when schema changes
CONTEXT_SCHEMA_VERSION = "1.0.0"


class ContextBuilder:
    """Build minimal component context for LLM consumption."""

    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize the context builder.

        Args:
            cache_dir: Directory for caching context. Defaults to .osiris_prompts/
        """
        self.cache_dir = Path(cache_dir) if cache_dir else Path(".osiris_prompts")
        self.cache_file = self.cache_dir / "context.json"
        self.cache_meta_file = self.cache_dir / "context.meta.json"
        self.schema_path = Path(__file__).parent / "context.schema.json"
        self.registry = get_registry()

        # Load schema for validation
        with open(self.schema_path) as f:
            self.schema = json.load(f)
        self.validator = Draft202012Validator(self.schema)

    def _compute_fingerprint(self, components: Dict[str, Any]) -> str:
        """Compute SHA-256 fingerprint of component specs.

        Args:
            components: Component specifications from registry

        Returns:
            Hex string of SHA-256 hash
        """
        # Create deterministic string representation
        fingerprint_data = {
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "components": {
                name: {
                    "version": spec.get("version"),
                    "modes": sorted(spec.get("modes", [])),
                    "required": sorted(spec.get("configSchema", {}).get("required", [])),
                    "properties": sorted(spec.get("configSchema", {}).get("properties", {}).keys()),
                }
                for name, spec in sorted(components.items())
            },
        }

        # Compute hash
        json_str = json.dumps(fingerprint_data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()

    def _extract_minimal_config(self, spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract minimal required configuration from component spec.

        Args:
            spec: Component specification

        Returns:
            List of required config fields with types and constraints
        """
        config_schema = spec.get("configSchema", {})
        properties = config_schema.get("properties", {})
        required = set(config_schema.get("required", []))

        minimal_config = []
        for field_name in required:
            if field_name in properties:
                field_spec = properties[field_name]
                field_info = {"field": field_name, "type": field_spec.get("type", "string")}

                # Include enum if present (important for LLM)
                if "enum" in field_spec:
                    field_info["enum"] = field_spec["enum"]

                # Include default if present
                if "default" in field_spec:
                    field_info["default"] = field_spec["default"]

                minimal_config.append(field_info)

        return minimal_config

    def _extract_minimal_example(self, spec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract a single minimal example from component spec.

        Args:
            spec: Component specification

        Returns:
            Minimal example configuration or None
        """
        examples = spec.get("examples", [])
        if not examples:
            return None

        # Take first example and extract only config
        example = examples[0]
        config = example.get("config", {})

        # Filter to only required fields
        required = set(spec.get("configSchema", {}).get("required", []))
        minimal_config = {k: v for k, v in config.items() if k in required}

        return minimal_config if minimal_config else None

    def _is_cache_valid(self, fingerprint: str) -> bool:
        """Check if cached context is still valid.

        Args:
            fingerprint: Current fingerprint of component specs

        Returns:
            True if cache is valid, False otherwise
        """
        if not self.cache_file.exists() or not self.cache_meta_file.exists():
            return False

        try:
            with open(self.cache_meta_file) as f:
                meta = json.load(f)

            # Check fingerprint and schema version
            if meta.get("fingerprint") != fingerprint:
                logger.debug("Cache invalid: fingerprint mismatch")
                return False

            if meta.get("schema_version") != CONTEXT_SCHEMA_VERSION:
                logger.debug("Cache invalid: schema version mismatch")
                return False

            # Check if any component spec files are newer than cache
            cache_mtime = self.cache_file.stat().st_mtime
            for component_dir in self.registry.root.iterdir():
                if not component_dir.is_dir():
                    continue
                spec_file = component_dir / "spec.yaml"
                if not spec_file.exists():
                    spec_file = component_dir / "spec.json"
                if spec_file.exists() and spec_file.stat().st_mtime > cache_mtime:
                    logger.debug(f"Cache invalid: {spec_file} is newer than cache")
                    return False

            return True

        except Exception as e:
            logger.debug(f"Cache validation error: {e}")
            return False

    def build_context(self, force_rebuild: bool = False) -> Dict[str, Any]:
        """Build minimal component context for LLM.

        Args:
            force_rebuild: Force rebuild even if cache is valid

        Returns:
            Component context dictionary
        """
        session = get_current_session()
        if session:
            session.log_event("context_build_start", schema_version=CONTEXT_SCHEMA_VERSION)

        # Load all component specs
        components = self.registry.load_specs()

        # Compute fingerprint
        fingerprint = self._compute_fingerprint(components)

        # Check cache unless forced
        if not force_rebuild and self._is_cache_valid(fingerprint):
            logger.info("Using cached context")
            with open(self.cache_file) as f:
                context = json.load(f)

            if session:
                # Calculate token count (approximate)
                json_str = json.dumps(context, separators=(",", ":"))
                token_count = len(json_str) // 4  # Rough approximation

                session.log_event(
                    "context_build_complete",
                    cached=True,
                    size_bytes=len(json_str),
                    token_count=token_count,
                    component_count=len(context["components"]),
                )
            return context

        # Build new context
        logger.info("Building new component context")

        context_components = []
        for name, spec in components.items():
            # Skip components without required fields (e.g., schema itself)
            if "configSchema" not in spec:
                continue

            component_info = {
                "name": name,
                "modes": spec.get("modes", []),
                "required_config": self._extract_minimal_config(spec),
            }

            # Add example if available
            example = self._extract_minimal_example(spec)
            if example:
                component_info["example"] = example

            context_components.append(component_info)

        # Build final context
        context = {
            "version": CONTEXT_SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "fingerprint": fingerprint,
            "components": context_components,
        }

        # Validate against schema
        try:
            self.validator.validate(context)
        except ValidationError as e:
            logger.error(f"Context validation failed: {e.message}")
            raise

        # Save to cache
        self._save_cache(context, fingerprint)

        # Log completion
        if session:
            json_str = json.dumps(context, separators=(",", ":"))
            token_count = len(json_str) // 4  # Rough approximation

            session.log_event(
                "context_build_complete",
                cached=False,
                size_bytes=len(json_str),
                token_count=token_count,
                component_count=len(context_components),
            )

        return context

    def _save_cache(self, context: Dict[str, Any], fingerprint: str):
        """Save context and metadata to cache.

        Args:
            context: Component context
            fingerprint: Fingerprint of component specs
        """
        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Save context (compact JSON)
        with open(self.cache_file, "w") as f:
            json.dump(context, f, separators=(",", ":"))

        # Save metadata
        meta = {
            "fingerprint": fingerprint,
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.cache_meta_file, "w") as f:
            json.dump(meta, f, indent=2)

        logger.info(f"Context cached to {self.cache_file}")


def main(output_path: Optional[str] = None, force: bool = False):
    """Build component context from CLI.

    Args:
        output_path: Output file path. Defaults to .osiris_prompts/context.json
        force: Force rebuild even if cache is valid
    """
    # Setup basic logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    builder = ContextBuilder()
    context = builder.build_context(force_rebuild=force)

    # Write to output file
    output = Path(output_path) if output_path else builder.cache_file
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, "w") as f:
        json.dump(context, f, separators=(",", ":"))

    # Display summary
    json_str = json.dumps(context, separators=(",", ":"))
    token_count = len(json_str) // 4

    print("✓ Context built successfully")
    print(f"  Components: {len(context['components'])}")
    print(f"  Size: {len(json_str)} bytes")
    print(f"  Estimated tokens: ~{token_count}")
    print(f"  Output: {output}")


if __name__ == "__main__":
    import sys

    # Simple CLI parsing
    output = None
    force = False

    for arg in sys.argv[1:]:
        if arg.startswith("--out="):
            output = arg.split("=", 1)[1]
        elif arg == "--force":
            force = True

    main(output, force)
