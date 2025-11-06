"""Build minimal component context for LLM consumption.

This module extracts essential component information from the registry
and creates a compact JSON context optimized for token efficiency.
"""

from datetime import UTC, datetime
import hashlib
import json
import logging
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from ..components.registry import get_registry
from ..core.session_logging import SessionContext, get_current_session

logger = logging.getLogger(__name__)

# Context schema version - increment when schema changes
CONTEXT_SCHEMA_VERSION = "1.0.0"

# Secret filtering version - increment when filtering logic changes
SECRET_FILTER_VERSION = "1.1.0"  # nosec B105 - version string, not a password


class ContextBuilder:
    """Build minimal component context for LLM consumption."""

    def __init__(self, cache_dir: Path | None = None):
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

    def _compute_fingerprint(self, components: dict[str, Any]) -> str:
        """Compute SHA-256 fingerprint of component specs.

        Args:
            components: Component specifications from registry

        Returns:
            Hex string of SHA-256 hash
        """
        # Create deterministic string representation
        fingerprint_data = {
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "secret_filter_version": SECRET_FILTER_VERSION,  # Include filter version
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

    def _is_secret_field(self, field_path: str, spec: dict[str, Any]) -> bool:
        """Check if a field path is a secret field.

        Args:
            field_path: Field name or path (e.g., 'password', '/password')
            spec: Component specification

        Returns:
            True if field is a secret
        """
        secrets = spec.get("secrets", [])
        # Normalize field path
        if not field_path.startswith("/"):
            field_path = f"/{field_path}"
        return field_path in secrets

    def _redact_suspicious_value(self, value: Any) -> Any:
        """Redact values that look like credentials.

        Args:
            value: Value to check and potentially redact

        Returns:
            Redacted value if suspicious, original otherwise
        """
        if not isinstance(value, str):
            return value

        value_lower = value.lower()

        # Check for suspicious substrings first (case-insensitive)
        suspicious_keywords = [
            "password",
            "passwd",
            "secret",
            "token",
            "api_key",
            "apikey",
            "api-key",
            "access_key",
            "access-key",
            "private_key",
            "private-key",
        ]

        for keyword in suspicious_keywords:
            if keyword in value_lower:
                return "***redacted***"

        # Check for auth patterns
        if value_lower.startswith("bearer "):
            return "***redacted***"
        if value_lower.startswith("basic ") and len(value) > 10:
            return "***redacted***"

        # Check for JWT-like tokens (three base64 parts separated by dots)
        if re.match(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$", value):
            return "***redacted***"

        # Check for hex strings that could be keys (but not SHA hashes in fingerprints)
        # Only redact hex strings that are exactly 32 or 64 chars (common key lengths)
        # but not those that are clearly SHA-256 (64 chars) in a fingerprint context
        if re.match(r"^[A-Fa-f0-9]+$", value) and (len(value) in [32, 40, 48] or len(value) >= 80):  # Not 64 (SHA-256)
            return "***redacted***"

        # Check for base64-encoded strings (but be conservative)
        if re.match(r"^[A-Za-z0-9+/]{20,}={0,2}$", value) and len(value) >= 40:
            # Long base64 strings that could be keys/tokens
            return "***redacted***"

        return value

    def _get_display_fields(self, spec: dict[str, Any]) -> list[str]:
        """Determine which config fields should appear in prompt context."""
        config_schema = spec.get("configSchema", {})
        properties: dict[str, Any] = config_schema.get("properties", {})
        required = set(config_schema.get("required", []))

        # Include fields showcased in examples or LLM hints so optional-but-core
        # settings (like Supabase URL) are retained.
        example_fields: set[str] = set()
        for example in spec.get("examples", []) or []:
            example_fields.update(example.get("config", {}).keys())

        hint_fields = set((spec.get("llmHints", {}) or {}).get("inputAliases", {}).keys())

        candidate_fields = required | (example_fields & properties.keys()) | (hint_fields & properties.keys())

        if not candidate_fields:
            candidate_fields = set(properties.keys())

        ordered_fields: list[str] = []
        for field_name in properties:  # preserve spec order
            if field_name in candidate_fields:
                ordered_fields.append(field_name)
        return ordered_fields

    def _extract_minimal_config(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract minimal required configuration from component spec.

        Args:
            spec: Component specification

        Returns:
            List of required config fields with types and constraints (excluding secrets)
        """
        config_schema = spec.get("configSchema", {})
        properties = config_schema.get("properties", {})

        minimal_config = []
        for field_name in self._get_display_fields(spec):
            if field_name not in properties:
                continue

            # Skip secret fields entirely
            if self._is_secret_field(field_name, spec):
                continue

            field_spec = properties.get(field_name, {})
            field_info = {"field": field_name, "type": field_spec.get("type", "string")}

            # Include enum if present (important for LLM) but redact suspicious values
            if "enum" in field_spec:
                field_info["enum"] = [self._redact_suspicious_value(v) for v in field_spec["enum"]]

            # Include default if present but redact if suspicious
            if "default" in field_spec:
                field_info["default"] = self._redact_suspicious_value(field_spec["default"])

            minimal_config.append(field_info)

        return minimal_config

    def _extract_minimal_example(self, spec: dict[str, Any]) -> dict[str, Any] | None:
        """Extract a single minimal example from component spec.

        Args:
            spec: Component specification

        Returns:
            Minimal example configuration or None (excluding secrets)
        """
        examples = spec.get("examples", [])
        if not examples:
            return None

        # Take first example and extract only config
        example = examples[0]
        config = example.get("config", {})

        # Filter to only required fields, exclude secrets, and redact suspicious values
        display_fields = set(self._get_display_fields(spec))
        minimal_config = {}

        for k, v in config.items():
            if k not in display_fields:
                continue
            if self._is_secret_field(k, spec):
                continue
            minimal_config[k] = self._redact_suspicious_value(v)

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

    def build_context(self, force_rebuild: bool = False) -> dict[str, Any]:
        """Build minimal component context for LLM.

        Args:
            force_rebuild: Force rebuild even if cache is valid

        Returns:
            Component context dictionary
        """
        session = get_current_session()
        cache_hit = False

        if session:
            # Check if cache would be hit before building
            components = self.registry.load_specs()
            fingerprint = self._compute_fingerprint(components)
            cache_hit = not force_rebuild and self._is_cache_valid(fingerprint)

            session.log_event(
                "context_build_start",
                command="prompts.build-context",
                out=str(self.cache_file),
                force=force_rebuild,
                cache_hit=cache_hit,
                schema_version=CONTEXT_SCHEMA_VERSION,
            )

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
                    size_bytes=len(json_str),
                    token_estimate=token_count,
                    components_count=len(context["components"]),
                    cache_written=False,  # Read from cache, not written
                    duration_ms=0,  # Immediate cache hit
                    status="ok",
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
            "generated_at": datetime.now(UTC).isoformat(),
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

            import time

            duration_ms = int((time.time() - session.start_time.timestamp()) * 1000)
            session.log_event(
                "context_build_complete",
                size_bytes=len(json_str),
                token_estimate=token_count,
                components_count=len(context_components),
                cache_written=True,
                duration_ms=duration_ms,
                status="ok",
            )

        return context

    def _save_cache(self, context: dict[str, Any], fingerprint: str):
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
            "generated_at": datetime.now(UTC).isoformat(),
        }
        with open(self.cache_meta_file, "w") as f:
            json.dump(meta, f, indent=2)

        logger.info(f"Context cached to {self.cache_file}")


def main(
    output_path: str | None = None,
    force: bool = False,
    json_output: bool = False,
    session: SessionContext | None = None,
) -> dict[str, Any] | None:
    """Build component context from CLI.

    Args:
        output_path: Output file path. Defaults to .osiris_prompts/context.json
        force: Force rebuild even if cache is valid
        json_output: Return JSON data instead of printing
        session: Optional session context for logging

    Returns:
        JSON data if json_output is True, None otherwise
    """
    # Setup basic logging only if no session
    if not session:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    import time

    start_time = time.time()

    try:
        builder = ContextBuilder()
        context = builder.build_context(force_rebuild=force)

        # Write to output file
        output = Path(output_path) if output_path else builder.cache_file
        output.parent.mkdir(parents=True, exist_ok=True)

        with open(output, "w") as f:
            json.dump(context, f, separators=(",", ":"))
            pass  # Cache written successfully

        # Calculate metrics
        json_str = json.dumps(context, separators=(",", ":"))
        token_count = len(json_str) // 4
        duration_ms = int((time.time() - start_time) * 1000)

        # Note: context_build_complete event is already logged by build_context()

        if json_output:
            # Return JSON data
            return {
                "success": True,
                "components": len(context["components"]),
                "size_bytes": len(json_str),
                "token_estimate": token_count,
                "output": str(output),
            }
        else:
            # Display summary
            print("✓ Context built successfully")
            print(f"  Components: {len(context['components'])}")
            print(f"  Size: {len(json_str)} bytes")
            print(f"  Estimated tokens: ~{token_count}")
            print(f"  Output: {output}")
            return None

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)

        # Log failure event if session exists
        if session:
            session.log_event(
                "context_build_complete",
                size_bytes=0,
                token_estimate=0,
                components_count=0,
                cache_written=False,
                duration_ms=duration_ms,
                status="failed",
                error=str(e),
            )
        raise


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
