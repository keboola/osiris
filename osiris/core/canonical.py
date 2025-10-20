"""Canonical serialization for deterministic output."""

from collections import OrderedDict
import json
from typing import Any

import yaml


def _normalize_value(value: Any) -> Any:
    """Normalize a value for canonical representation."""
    if isinstance(value, dict):
        # Sort keys and recurse
        return OrderedDict((k, _normalize_value(v)) for k, v in sorted(value.items()))
    elif isinstance(value, list):
        # Recurse on list items (maintain order)
        return [_normalize_value(v) for v in value]
    elif isinstance(value, bool):
        # Booleans before numbers (Python's bool is subclass of int)
        return value
    elif isinstance(value, int | float):
        # Normalize numbers
        return value
    elif value is None:
        return None
    else:
        # Everything else as string
        return str(value)


def canonical_json(data: Any) -> str:
    """
    Serialize data to canonical JSON format.

    Rules:
    - Stable key ordering (sorted)
    - UTF-8 encoding
    - No trailing spaces
    - Compact format (no extra whitespace)
    - LF line endings
    """
    normalized = _normalize_value(data)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=False,  # Already sorted in _normalize_value
    )


def canonical_yaml(data: Any) -> str:
    """
    Serialize data to canonical YAML format.

    Rules:
    - Stable key ordering (sorted)
    - UTF-8 encoding
    - No trailing spaces
    - LF line endings
    - Explicit document start/end markers
    """
    normalized = _normalize_value(data)

    # Custom YAML representer to maintain order
    def ordered_dict_representer(dumper, data):
        return dumper.represent_mapping(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, data.items())

    yaml.add_representer(OrderedDict, ordered_dict_representer)

    output = yaml.dump(
        normalized,
        default_flow_style=False,
        explicit_start=True,
        explicit_end=True,
        allow_unicode=True,
        width=120,
        sort_keys=False,  # Already sorted in _normalize_value
    )

    # Ensure LF line endings and no trailing spaces
    lines = output.split("\n")
    cleaned_lines = [line.rstrip() for line in lines]
    return "\n".join(cleaned_lines)


def canonical_bytes(data: Any, format: str = "json") -> bytes:
    """
    Get canonical bytes representation for fingerprinting.

    Args:
        data: Data to serialize
        format: 'json' or 'yaml'

    Returns:
        UTF-8 encoded bytes
    """
    if format == "json":
        text = canonical_json(data)
    elif format == "yaml":
        text = canonical_yaml(data)
    else:
        raise ValueError(f"Unknown format: {format}")

    return text.encode("utf-8")
