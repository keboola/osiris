"""Shared helper functions for connection management.

This module provides reusable functions for both osiris connections
and osiris mcp connections commands to eliminate code duplication and
ensure consistent secret masking behavior.

SECRET MASKING STRATEGY:
- Uses component spec.yaml declarations (x-secret fields) as the source of truth
- Falls back to COMMON_SECRET_NAMES for connections without specs
- Same pattern as compiler_v0.py for consistency
"""

import os
import re
from typing import Any

from osiris.components.registry import get_registry
from osiris.core.config import load_connections_yaml

# Fallback secret names when component spec is not available
# (Same as COMMON_SECRET_NAMES in compiler_v0.py)
COMMON_SECRET_NAMES = {
    "password",
    "passwd",
    "pass",
    "pwd",
    "secret",
    "key",
    "token",
    "auth",
    "credential",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "private_key",
    "client_secret",
    "service_role_key",
    "anon_key",
    "access_key_id",
    "secret_access_key",
}


def check_env_var_set(var_name: str) -> bool:
    """Check if an environment variable is set (not checking value)."""
    return var_name in os.environ


def extract_env_vars(value: Any) -> list[str]:
    """Extract environment variable names from a value with ${VAR} patterns."""
    if isinstance(value, str):
        pattern = r"\$\{([^}]+)\}"
        return re.findall(pattern, value)
    elif isinstance(value, dict):
        vars_list = []
        for v in value.values():
            vars_list.extend(extract_env_vars(v))
        return vars_list
    elif isinstance(value, list):
        vars_list = []
        for item in value:
            vars_list.extend(extract_env_vars(item))
        return vars_list
    return []


def _extract_field_from_pointer(pointer: str) -> str | None:
    """Extract field name from JSON pointer.

    Examples:
        "/key" -> "key"
        "/password" -> "password"
        "/resolved_connection/password" -> "password"
        "/auth/api_key" -> "api_key"

    Args:
        pointer: JSON pointer string (e.g., "/key", "/auth/password")

    Returns:
        Last segment of the pointer, or None if invalid
    """
    if not pointer:
        return None

    # Remove leading slash and split
    trimmed = pointer[1:] if pointer.startswith("/") else pointer
    if not trimmed:
        return None

    segments = trimmed.split("/")
    # Return the last segment (the actual field name)
    return segments[-1] if segments else None


def _get_secret_fields_for_family(family: str | None) -> set[str]:
    """Get secret field names from component specs for a connection family.

    Uses component spec.yaml x-secret declarations as the source of truth.
    Falls back to COMMON_SECRET_NAMES for unknown families.

    Args:
        family: Connection family (e.g., "mysql", "supabase", "duckdb")

    Returns:
        Set of lowercase field names that should be masked
    """
    if not family:
        # No family provided, use fallback
        return {name.lower() for name in COMMON_SECRET_NAMES}

    registry = get_registry()
    secret_fields = set()

    # Try common component types for this family
    # Most families have .extractor and .writer components
    for mode in ["extractor", "writer"]:
        component_name = f"{family}.{mode}"
        secret_map = registry.get_secret_map(component_name)

        # Parse x-secret JSON pointers from the component spec
        for pointer in secret_map.get("secrets", []):
            field_name = _extract_field_from_pointer(pointer)
            if field_name:
                secret_fields.add(field_name.lower())

    # Always include fallback common names for safety
    secret_fields.update(name.lower() for name in COMMON_SECRET_NAMES)

    # Remove non-secrets that might match heuristics
    secret_fields.discard("primary_key")  # Not a secret!

    return secret_fields


def _is_secret_key(key_name: str, secret_fields: set[str]) -> bool:
    """Check if a connection key name matches a secret field pattern.

    Uses intelligent matching to avoid false positives like "primary_key"
    while catching compound names like "service_role_key".

    Args:
        key_name: Connection field name to check
        secret_fields: Set of secret field names from specs

    Returns:
        True if the key should be masked
    """
    key_lower = key_name.lower()

    # Check for exact match first
    if key_lower in secret_fields:
        return True

    # Check for compound names (e.g., "service_role_key" should match "key")
    # But avoid false positives like "primary_key"
    for secret in secret_fields:
        # Skip exact matches (already checked above)
        if secret == key_lower:
            continue

        # For compound names, check if the secret appears as a word boundary
        # e.g., "service_role_key" matches "key", but "primary_key" doesn't
        if secret in key_lower:
            # Check if it's at word boundaries (underscore-separated)
            parts = key_lower.split("_")
            if secret in parts or any(part.endswith(secret) for part in parts):
                # Additional check: exclude known non-secrets
                return not ("primary" in key_lower and secret == "key")  # nosec B105  # Comparing field name pattern

    return False


def mask_connection_for_display(connection: dict[str, Any], family: str | None = None) -> dict[str, Any]:
    """Mask sensitive fields in a connection for display using component spec declarations.

    This is the single source of truth for secret masking across all
    connection-related commands. It uses component spec.yaml x-secret
    declarations to identify which fields are secrets, with fallback to
    heuristic detection for unknown families.

    Recursively masks nested dictionaries to handle structures like
    /resolved_connection/password declared in component specs.

    Args:
        connection: Connection configuration dictionary
        family: Connection family (e.g., "mysql", "supabase", "duckdb").
                If provided, uses component spec to detect secrets.
                If None, uses fallback heuristics only.

    Returns:
        Deep copy of connection with all sensitive fields masked
    """
    # Get secret fields from component specs (or fallback)
    secret_fields = _get_secret_fields_for_family(family)

    def _mask_recursive(obj: Any) -> Any:
        """Recursively mask secrets in nested structures."""
        if isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                # Check if this key is a secret field
                if _is_secret_key(key, secret_fields):
                    # Preserve env var references like ${VAR}
                    if isinstance(value, str) and value.startswith("${"):
                        result[key] = value
                    else:
                        # Mask the actual value
                        result[key] = "***MASKED***"
                # Recursively mask nested dicts
                elif isinstance(value, dict):
                    result[key] = _mask_recursive(value)
                # Keep non-dict, non-secret values as-is
                else:
                    result[key] = value
            return result
        # Non-dict values pass through
        return obj

    return _mask_recursive(connection)


def load_and_mask_connections(substitute_env: bool = True) -> dict[str, dict[str, dict[str, Any]]]:
    """Load connections from YAML and apply spec-aware secret masking.

    Args:
        substitute_env: Whether to substitute environment variables

    Returns:
        Nested dictionary: {family: {alias: masked_config}}
    """
    connections = load_connections_yaml(substitute_env=substitute_env)

    masked_connections = {}
    for family, aliases in connections.items():
        masked_connections[family] = {}
        for alias, config in aliases.items():
            # Pass family to enable spec-aware masking
            masked_connections[family][alias] = mask_connection_for_display(config, family=family)

    return masked_connections


def get_connection_env_status(raw_config: dict[str, Any]) -> dict[str, bool]:
    """Check which environment variables are set for a connection.

    Args:
        raw_config: Raw connection config with ${VAR} patterns

    Returns:
        Dictionary mapping variable names to boolean (set or not)
    """
    env_vars = extract_env_vars(raw_config)
    return {var: check_env_var_set(var) for var in env_vars}


def get_required_fields(family: str) -> list[str]:
    """Get required fields for a connection family.

    Args:
        family: Connection family name (e.g., 'mysql', 'supabase')

    Returns:
        List of required field names for that family
    """
    required_by_family = {
        "mysql": ["host", "database", "username", "password"],
        "postgresql": ["host", "database", "username", "password"],
        "supabase": ["url", "key"],
        "duckdb": ["database"],
        "filesystem": ["path"],
    }

    return required_by_family.get(family, [])
