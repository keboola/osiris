"""
Component Registry Utilities

Helper functions for working with component specifications,
including secret path collection and redaction policies.
"""

from typing import Any, NamedTuple


class RedactionPolicy(NamedTuple):
    """Redaction policy for sensitive data"""

    strategy: str = "mask"  # mask, drop, or hash
    mask: str = "***"
    paths: set[str] = set()


def collect_secret_paths(spec: dict[str, Any]) -> set[str]:
    """
    Collect all secret paths from a component specification.

    Args:
        spec: Component specification dictionary

    Returns:
        Set of JSON Pointer paths to secret fields
    """
    paths = set(spec.get("secrets", []))

    # Add extras from redaction policy
    if "redaction" in spec:
        paths.update(spec["redaction"].get("extras", []))

    # Add sensitive paths from logging policy
    if "loggingPolicy" in spec:
        paths.update(spec["loggingPolicy"].get("sensitivePaths", []))

    return paths


def redaction_policy(spec: dict[str, Any]) -> RedactionPolicy:
    """
    Extract redaction policy from component specification.

    Args:
        spec: Component specification dictionary

    Returns:
        RedactionPolicy with strategy, mask, and paths
    """
    policy = spec.get("redaction", {})
    return RedactionPolicy(
        strategy=policy.get("strategy", "mask"),
        mask=policy.get("mask", "***"),
        paths=collect_secret_paths(spec),
    )


def validate_json_pointer(pointer: str) -> bool:
    """
    Validate JSON Pointer format.

    Args:
        pointer: JSON Pointer string

    Returns:
        True if valid JSON Pointer format
    """
    if not pointer or not pointer.startswith("/"):
        return False

    # Check for invalid patterns
    return not ("//" in pointer or pointer.endswith("/"))


def resolve_json_pointer(data: dict[str, Any], pointer: str) -> Any:
    """
    Resolve a JSON Pointer against data.

    Args:
        data: Data dictionary to resolve against
        pointer: JSON Pointer string

    Returns:
        Value at the pointer location, or None if not found
    """
    if not validate_json_pointer(pointer):
        return None

    # Remove leading slash and split path
    parts = pointer[1:].split("/") if pointer != "/" else []

    current = data
    for part in parts:
        # Unescape special characters
        part = part.replace("~1", "/").replace("~0", "~")

        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        elif isinstance(current, list):
            try:
                index = int(part)
                if index < 0 or index >= len(current):
                    return None
                current = current[index]
            except (ValueError, IndexError):
                return None
        else:
            return None

    return current


def mask_value(value: Any, mask: str = "***") -> Any:
    """
    Mask a value for redaction.

    Args:
        value: Value to mask
        mask: Mask string to use

    Returns:
        Masked value
    """
    if value is None:
        return None
    elif isinstance(value, str | int | float | bool):
        return mask
    elif isinstance(value, list):
        return [mask] * len(value)
    elif isinstance(value, dict):
        return dict.fromkeys(value, mask)
    else:
        return mask


def apply_redaction(data: dict[str, Any], policy: RedactionPolicy) -> dict[str, Any]:
    """
    Apply redaction policy to data.

    Args:
        data: Data dictionary to redact
        policy: Redaction policy to apply

    Returns:
        Redacted copy of data
    """
    import copy

    result = copy.deepcopy(data)

    for pointer in policy.paths:
        if not validate_json_pointer(pointer):
            continue

        # Split pointer into parent path and field name
        parts = pointer[1:].split("/") if pointer != "/" else []
        if not parts:
            continue

        parent_path = "/" + "/".join(parts[:-1]) if len(parts) > 1 else ""
        field_name = parts[-1]

        # Resolve parent object
        parent = resolve_json_pointer(result, parent_path) if parent_path else result

        if not isinstance(parent, dict) or field_name not in parent:
            continue

        # Apply redaction based on strategy
        if policy.strategy == "mask":
            parent[field_name] = mask_value(parent[field_name], policy.mask)
        elif policy.strategy == "drop":
            del parent[field_name]
        elif policy.strategy == "hash":
            import hashlib

            value_str = str(parent[field_name])
            parent[field_name] = hashlib.sha256(value_str.encode()).hexdigest()[:8]

    return result


# TODO: Additional helpers for M1a.3 - Component Registry
# - load_spec(path: Path) -> Dict
# - validate_spec(spec: Dict) -> List[ValidationError]
# - get_component_context(spec: Dict) -> Dict  # For LLM context
# - validate_config_against_schema(config: Dict, schema: Dict) -> List[ValidationError]
