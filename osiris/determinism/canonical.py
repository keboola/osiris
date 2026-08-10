"""Canonical serialization for deterministic output."""

from collections import OrderedDict
import json
from typing import Any

import yaml


def _normalize_value(value: Any) -> Any:
    """Normalize a value for canonical representation."""
    if isinstance(value, dict):
        return OrderedDict((k, _normalize_value(v)) for k, v in sorted(value.items()))
    elif isinstance(value, list):
        return [_normalize_value(v) for v in value]
    elif isinstance(value, bool):
        # Checked before int: Python's bool is a subclass of int.
        return value
    elif isinstance(value, int | float):
        return value
    elif value is None:
        return None
    else:
        return str(value)


def canonical_json(data: Any) -> str:
    """Serialize to canonical JSON: sorted keys, compact separators, unescaped UTF-8."""
    normalized = _normalize_value(data)
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), sort_keys=False)


def canonical_yaml(data: Any) -> str:
    """Serialize to canonical YAML: sorted keys, explicit start/end markers, no trailing spaces."""
    normalized = _normalize_value(data)

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
        sort_keys=False,
    )
    return "\n".join(line.rstrip() for line in output.split("\n"))


def canonical_bytes(data: Any, fmt: str = "json") -> bytes:
    """UTF-8 bytes of the canonical representation, for fingerprinting."""
    if fmt == "json":
        text = canonical_json(data)
    elif fmt == "yaml":
        text = canonical_yaml(data)
    else:
        raise ValueError(f"Unknown format: {fmt}")
    return text.encode("utf-8")
