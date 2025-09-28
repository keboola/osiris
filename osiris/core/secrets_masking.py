# Copyright (c) 2025 Osiris Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Secrets masking for secure logging."""

import re
from typing import Any

# Sensitive field patterns (case-insensitive)
SENSITIVE_PATTERNS = [
    r"^password$",
    r"^passwd$",
    r"^pwd$",
    r"^.*password.*$",
    r"^.*_pw$",  # Catches oracle_pw, db_pw, admin_pw, etc.
    r"^.*_pass$",  # Catches admin_pass, user_pass, etc.
    r"^.*token.*$",
    r"^api_?key$",
    r"^.*secret.*$",
    r"^authorization$",
    r"^auth$",
    r"^.*credential.*$",
    r"^(private_?key|access_?key|secret_?key|session_?key|encryption_?key)$",  # Specific key types
    r"^key$",  # Exact match for "key" - considered sensitive in security contexts
]

# Compile regex patterns for efficiency
SENSITIVE_REGEX = re.compile("|".join(f"({pattern})" for pattern in SENSITIVE_PATTERNS), re.IGNORECASE)

# Structural keys that should NEVER be masked (used for system operation)
STRUCTURAL_KEYS = {
    "session_id",
    "session",
    "event",
    "event_type",
    "event_name",
    "command",
    "timestamp",
    "duration",
    "duration_ms",
    "token_count",
    "tokens",
    "total_tokens",
    "prompt_tokens",
    "completion_tokens",
    "size",
    "count",
    "attempts",
    "retry_count",
}

MASK_VALUE = "***"


def mask_sensitive_value(key: str, value: Any) -> Any:
    """Mask sensitive values based on key name.

    Args:
        key: Field name to check
        value: Value to potentially mask

    Returns:
        Masked value if key is sensitive, original value otherwise
    """
    # Never mask structural keys
    if isinstance(key, str):
        if key.lower() in STRUCTURAL_KEYS:
            return value
        if SENSITIVE_REGEX.search(key):
            return MASK_VALUE
    return value


def mask_sensitive_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively mask sensitive fields in a dictionary.

    Args:
        data: Dictionary to mask

    Returns:
        Dictionary with sensitive values masked
    """
    if not isinstance(data, dict):
        return data

    masked = {}
    for key, value in data.items():
        if isinstance(value, dict):
            masked[key] = mask_sensitive_dict(value)
        elif isinstance(value, list):
            masked[key] = [mask_sensitive_dict(item) if isinstance(item, dict) else item for item in value]
        else:
            masked[key] = mask_sensitive_value(key, value)

    return masked


def mask_sensitive_string(text: str) -> str:
    """Mask sensitive information in string representations.

    Args:
        text: String to mask

    Returns:
        String with sensitive patterns masked
    """
    # Simple patterns without anchors for string matching
    simple_patterns = [
        "password",
        "passwd",
        "pwd",
        "token",
        "api_key",
        "apikey",
        "secret",
        "authorization",
        "auth",
        "credential",
        "private_key",
        "privatekey",
        "access_key",
        "session_key",
        "encryption_key",
        "key",
    ]

    # Multiple patterns to handle different formats
    patterns = [
        # JSON-like: "key": "value"
        (
            r'("(?:' + "|".join(simple_patterns) + r')"\s*:\s*")([^"]+)(")',
            r"\1" + MASK_VALUE + r"\3",
        ),
        # Config-like: key=value
        (r"(\b(?:" + "|".join(simple_patterns) + r")\s*=\s*)([^\s,}]+)", r"\1" + MASK_VALUE),
        # Log message: key: value (like "password: secret")
        (r"(\b(?:" + "|".join(simple_patterns) + r")\s*:\s*)([^\s,}]+)", r"\1" + MASK_VALUE),
        # URL-like: key:value@host
        (r"(:(?:" + "|".join(simple_patterns) + r"))([^@\s&]+)", r"\1" + MASK_VALUE),
        # Query params: ?key=value or &key=value
        (r"([?&](?:" + "|".join(simple_patterns) + r")=)([^&\s]+)", r"\1" + MASK_VALUE),
    ]

    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    return result


def safe_repr(obj: Any) -> str:
    """Create a safe string representation with sensitive data masked.

    Args:
        obj: Object to represent

    Returns:
        Safe string representation
    """
    if isinstance(obj, dict):
        masked = mask_sensitive_dict(obj)
        return repr(masked)

    # For other objects, mask their string representation
    return mask_sensitive_string(repr(obj))
