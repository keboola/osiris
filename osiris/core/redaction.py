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

"""Advanced redaction system with configurable privacy levels."""

import os
from pathlib import Path
import re
from typing import Any

# Privacy levels
PRIVACY_STANDARD = "standard"
PRIVACY_STRICT = "strict"

# Full mask for secrets
MASK_FULL = "***"

# Fields that should ALWAYS be fully masked (case-insensitive)
SECRET_FIELDS = {
    "api_key",
    "apikey",
    "token",
    "auth",
    "authorization",
    "password",
    "passwd",
    "pwd",
    "secret",
    "connection_string",
    "dsn",
    "bearer",
    "private_key",
    "access_key",
    "secret_key",
    "session_key",
    "encryption_key",
}

# Numeric operational metrics that should NOT be masked
NUMERIC_METRICS = {
    "prompt_tokens",
    "prompt_tokens_est",
    "response_tokens",
    "response_tokens_est",
    "total_tokens",
    "total_tokens_est",
    "duration_ms",
    "response_seconds",
    "cache_hits",
    "cache_misses",
    "components_count",
    "size_bytes",
    "est_tokens",
    "message_length",
    "response_length",
    "bytes",
    "token_count",
    "token_estimate",
}

# Fingerprint/hash fields that should be partially revealed
FINGERPRINT_FIELDS = {
    "spec_fp",
    "options_fp",
    "context_fp",
    "fingerprint",
    "cache_fingerprint",
    "hash",
    "sha",
    "md5",
}

# Pattern for detecting key-like values
# More specific: must look like actual API keys/tokens (mix of upper/lower/digits, very long)
KEY_PATTERN = re.compile(r"\b(?=.*[A-Z])(?=.*[a-z])(?=.*[0-9])[A-Za-z0-9_\-]{32,}\b")

# Pattern for detecting absolute paths
ABSOLUTE_PATH_PATTERN = re.compile(r"^(/[^/]+(?:/[^/]+)*|[A-Z]:\\[^\\]+(?:\\[^\\]+)*)$")


class Redactor:
    """Configurable redaction system for sensitive data."""

    def __init__(self, privacy_level: str = PRIVACY_STANDARD, repo_root: Path | None = None):
        """Initialize redactor.

        Args:
            privacy_level: Privacy level (standard or strict)
            repo_root: Repository root for path relativization
        """
        self.privacy_level = privacy_level
        self.repo_root = repo_root or self._find_repo_root()

    @staticmethod
    def _find_repo_root() -> Path:
        """Find repository root by looking for .git directory."""
        current = Path.cwd()
        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent
        return Path.cwd()

    def _is_secret_field(self, key: str) -> bool:
        """Check if field name indicates a secret."""
        if not isinstance(key, str):
            return False

        key_lower = key.lower()

        # Special case: "key" by itself in cache context is usually a cache key, not a secret
        if key_lower == "key":
            return False

        # Special case: "tokens" in context of metrics is not a secret
        if "tokens" in key_lower and any(metric in key_lower for metric in ["prompt", "response", "total"]):
            return False

        # Check exact matches first (but skip "key" as we handled it above)
        if key_lower in SECRET_FIELDS and key_lower != "key":
            return True

        # Then check for substrings, but be more careful
        for secret in SECRET_FIELDS:
            # Skip "token" if it's part of "_tokens" (metrics)
            if secret == "token" and key_lower.endswith("_tokens"):  # nosec B105  # pragma: allowlist secret
                continue
            # Skip bare "key" - we handled it above
            if secret == "key":  # pragma: allowlist secret  # nosec B105
                continue
            # Check for compound names like "api_key", "access_key"
            if secret in key_lower and secret != key_lower:
                return True

        return False

    def _is_numeric_metric(self, key: str) -> bool:
        """Check if field is a numeric metric that should be preserved."""
        if not isinstance(key, str):
            return False
        key_lower = key.lower()
        return (
            key_lower in NUMERIC_METRICS
            or key_lower.endswith("_count")
            or key_lower.endswith("_ms")
            or key_lower.endswith("_seconds")
            or key_lower.endswith("_bytes")
            or key_lower.endswith("_tokens")
        )

    def _is_fingerprint_field(self, key: str) -> bool:
        """Check if field is a fingerprint/hash that should be shortened."""
        if not isinstance(key, str):
            return False
        key_lower = key.lower()
        return (
            key_lower in FINGERPRINT_FIELDS
            or key_lower.endswith("_fp")
            or key_lower.endswith("_hash")
            or key_lower.endswith("_fingerprint")
        )

    def _shorten_fingerprint(self, value: str) -> str:
        """Shorten a fingerprint/hash to first 8 chars."""
        if not isinstance(value, str) or len(value) < 16:
            return value
        # Check if it looks like a hash (hex characters)
        if re.match(r"^[a-fA-F0-9]{16,}$", value):
            return f"{value[:8]}..."
        return value

    def _relativize_path(self, value: str) -> str:
        """Convert absolute path to repo-relative path."""
        if not isinstance(value, str):
            return value

        # Check if it looks like a path
        if not ("/" in value or "\\" in value):
            return value

        try:
            path = Path(value)
            if path.is_absolute():
                # Try to make relative to repo root
                try:
                    rel_path = path.relative_to(self.repo_root)
                    return str(rel_path)
                except ValueError:
                    # Not under repo root
                    # For known temp/system paths, return basename
                    path_str = str(path)
                    if path_str.startswith(("/tmp", "/var", "/etc")) or "Temp" in path_str:  # nosec B108
                        return path.name
                    # Otherwise keep the path (might be important)
                    return value
            return value
        except (ValueError, OSError):
            return value

    def _looks_like_key(self, value: str) -> bool:
        """Check if value looks like an API key or token."""
        if not isinstance(value, str):
            return False

        # Skip if it's a known fingerprint (already handled)
        if re.match(r"^[a-fA-F0-9]{32,64}$", value):
            return False

        # Skip common event names and identifiers
        # Event names typically have underscores and are descriptive
        if "_" in value and any(
            part in value.lower()
            for part in [
                "start",
                "complete",
                "error",
                "validation",
                "build",
                "load",
                "cache",
                "context",
                "request",
                "response",
                "init",
                "end",
            ]
        ):
            return False

        # Skip session IDs (date_time_hash format)
        if re.match(r"^\d{8}_\d{6}_[a-f0-9]{8}$", value):
            return False

        # Check for known token patterns
        # Slack tokens (xoxp-, xoxb-, xoxa-, xoxr-)
        if re.match(r"^xox[pbar]-[\d\-a-zA-Z]+$", value):
            return True

        # AWS access keys
        if re.match(r"^AKIA[A-Z0-9]{16}$", value):
            return True

        # GitHub tokens (ghp_, ghs_, gho_, etc)
        if re.match(r"^gh[pousr]_[A-Za-z0-9]{36,}$", value):
            return True

        # Check for generic key-like pattern (long mixed-case strings with numbers)
        return bool(KEY_PATTERN.match(value))

    def redact_value(self, key: str, value: Any, parent_key: str | None = None) -> Any:  # noqa: ARG002
        """Redact a single value based on its key and content.

        Args:
            key: Field name
            value: Field value
            parent_key: Parent field name for nested structures

        Returns:
            Redacted value
        """
        # Handle None and basic types that don't need redaction
        if value is None or isinstance(value, bool):
            return value

        # Preserve numeric metrics FIRST (before checking for secrets)
        if isinstance(value, int | float) and self._is_numeric_metric(key):
            return value

        # Check if field is a secret
        if self._is_secret_field(key):
            return MASK_FULL

        # Handle fingerprints
        if self._is_fingerprint_field(key) and isinstance(value, str):
            return self._shorten_fingerprint(value)

        # Handle paths
        if key in ["path", "file", "file_path", "dir", "directory", "out", "output"] and isinstance(value, str):
            value = self._relativize_path(value)

        # Check for key-like values in string
        if isinstance(value, str):
            # In strict mode, mask long text fields and raw prompts
            if (
                self.privacy_level == PRIVACY_STRICT
                and key in ["prompt", "message", "content", "text", "body"]
                and len(value) > 256
            ):
                return f"{value[:50]}... [REDACTED - {len(value)} chars]"

            # Special handling for cache keys and similar - don't mask them
            if key == "key":
                return value

            # Special handling for session and event fields - don't mask their values
            if key in ["session", "session_id", "event", "event_type", "command"]:
                return value

            # Check if value looks like a key (but not in certain contexts)
            if self._looks_like_key(value) and not self._is_fingerprint_field(key):
                return MASK_FULL

        return value

    def redact_dict(self, data: dict[str, Any], parent_key: str | None = None) -> dict[str, Any]:
        """Recursively redact sensitive fields in a dictionary.

        Args:
            data: Dictionary to redact
            parent_key: Parent field name for nested structures

        Returns:
            Dictionary with sensitive values redacted
        """
        if not isinstance(data, dict):
            return data

        redacted = {}
        for key, value in data.items():
            if isinstance(value, dict):
                redacted[key] = self.redact_dict(value, parent_key=key)
            elif isinstance(value, list):
                redacted[key] = [
                    (
                        self.redact_dict(item, parent_key=key)
                        if isinstance(item, dict)
                        else self.redact_value(f"{key}_item", item, parent_key=key)
                    )
                    for item in value
                ]
            else:
                redacted[key] = self.redact_value(key, value, parent_key=parent_key)

        return redacted


def get_privacy_level() -> str:
    """Get privacy level from environment or default."""
    return os.environ.get("OSIRIS_PRIVACY", PRIVACY_STANDARD).lower()


def create_redactor(privacy_level: str | None = None) -> Redactor:
    """Create a redactor with the specified or default privacy level."""
    if privacy_level is None:
        privacy_level = get_privacy_level()
    return Redactor(privacy_level)


# Backward compatibility functions
def mask_sensitive_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Legacy function for masking sensitive data."""
    redactor = create_redactor()
    return redactor.redact_dict(data)


def mask_sensitive_string(text: str) -> str:
    """Legacy function for masking sensitive strings."""
    # Use the old implementation for string masking
    from .secrets_masking import mask_sensitive_string as legacy_mask

    return legacy_mask(text)
