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

"""Filesystem Contract v1 - Path resolution and token rendering (ADR-0028)."""

from dataclasses import dataclass
from datetime import datetime
import getpass
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from osiris.core.fs_config import FilesystemConfig, IdsConfig


@dataclass
class TokenContext:
    """Context for rendering naming tokens."""

    pipeline_slug: str = ""
    profile: str = ""
    manifest_hash: str = ""
    manifest_short: str = ""
    run_id: str = ""
    run_ts: str = ""
    status: str = ""
    branch: str = ""
    user: str = ""
    tags: str = ""
    manifest_version: str = ""

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for token rendering."""
        return {
            "pipeline_slug": self.pipeline_slug,
            "profile": self.profile,
            "manifest_hash": self.manifest_hash,
            "manifest_short": self.manifest_short,
            "run_id": self.run_id,
            "run_ts": self.run_ts,
            "status": self.status,
            "branch": self.branch,
            "user": self.user,
            "tags": self.tags,
            "manifest_version": self.manifest_version,
        }


class TokenRenderer:
    """Renders naming templates with token substitution."""

    def render(self, template: str, tokens: dict[str, str]) -> str:
        """Render template with token substitution.

        Missing tokens are rendered as empty strings.
        Filesystem-unsafe characters are slugified.
        Duplicate separators are collapsed.

        Args:
            template: Template string with {token} placeholders
            tokens: Token values

        Returns:
            Rendered path string
        """
        # Substitute tokens
        result = template
        for key, value in tokens.items():
            placeholder = f"{{{key}}}"
            if placeholder in result:
                # Slugify value for filesystem safety
                safe_value = slugify_token(value)
                result = result.replace(placeholder, safe_value)

        # Replace any remaining placeholders with empty string
        result = re.sub(r"\{[^}]+\}", "", result)

        # Collapse duplicate separators (/, -, _)
        result = re.sub(r"/{2,}", "/", result)  # Multiple slashes
        result = re.sub(r"-{2,}", "-", result)  # Multiple dashes
        result = re.sub(r"_{2,}", "_", result)  # Multiple underscores

        # Remove leading/trailing separators
        result = result.strip("/-_")

        return result


class FilesystemContract:
    """Filesystem Contract v1 - Manages all path resolution per ADR-0028."""

    def __init__(self, fs_config: FilesystemConfig, ids_config: IdsConfig):
        """Initialize filesystem contract.

        Args:
            fs_config: Filesystem configuration
            ids_config: ID generation configuration
        """
        self.fs_config = fs_config
        self.ids_config = ids_config
        self.renderer = TokenRenderer()

    def manifest_paths(
        self, pipeline_slug: str, manifest_hash: str, manifest_short: str, profile: str | None = None
    ) -> dict[str, Path]:
        """Resolve build manifest paths.

        Args:
            pipeline_slug: Pipeline identifier
            manifest_hash: Full manifest hash
            manifest_short: Short manifest hash
            profile: Optional profile name

        Returns:
            Dictionary of paths for build artifacts
        """
        # Use default profile if enabled and not provided
        if profile is None and self.fs_config.profiles.enabled:
            profile = self.fs_config.profiles.default

        # Build tokens
        tokens = {
            "pipeline_slug": pipeline_slug,
            "profile": profile or "",
            "manifest_hash": manifest_hash,
            "manifest_short": manifest_short,
        }

        # Render manifest directory name
        manifest_dir_name = self.renderer.render(self.fs_config.naming.manifest_dir, tokens)

        # Build base path
        if self.fs_config.profiles.enabled and profile:
            base_path = (
                self.fs_config.resolve_path(self.fs_config.build_dir) / "pipelines" / profile / manifest_dir_name
            )
        else:
            base_path = self.fs_config.resolve_path(self.fs_config.build_dir) / "pipelines" / manifest_dir_name

        return {
            "base": base_path,
            "manifest": base_path / "manifest.yaml",
            "plan": base_path / "plan.json",
            "fingerprints": base_path / "fingerprints.json",
            "run_summary": base_path / "run_summary.json",
            "cfg_dir": base_path / "cfg",
        }

    def run_log_paths(
        self, pipeline_slug: str, run_id: str, run_ts: datetime, manifest_short: str, profile: str | None = None
    ) -> dict[str, Path]:
        """Resolve run log paths.

        Args:
            pipeline_slug: Pipeline identifier
            run_id: Run identifier
            run_ts: Run timestamp
            manifest_short: Short manifest hash
            profile: Optional profile name

        Returns:
            Dictionary of paths for run logs
        """
        # Use default profile if enabled and not provided
        if profile is None and self.fs_config.profiles.enabled:
            profile = self.fs_config.profiles.default

        # Format timestamp
        ts_str = self._format_timestamp(run_ts)

        # Build tokens
        tokens = {
            "pipeline_slug": pipeline_slug,
            "profile": profile or "",
            "run_id": run_id,
            "run_ts": ts_str,
            "manifest_short": manifest_short,
        }

        # Render run directory name
        run_dir_name = self.renderer.render(self.fs_config.naming.run_dir, tokens)

        # Build base path
        if self.fs_config.profiles.enabled and profile:
            base_path = self.fs_config.resolve_path(self.fs_config.run_logs_dir) / profile / run_dir_name
        else:
            base_path = self.fs_config.resolve_path(self.fs_config.run_logs_dir) / run_dir_name

        return {
            "base": base_path,
            "events": base_path / "events.jsonl",
            "metrics": base_path / "metrics.jsonl",
            "debug_log": base_path / "debug.log",
            "osiris_log": base_path / "osiris.log",
            "artifacts": base_path / "artifacts",
        }

    def aiop_paths(
        self, pipeline_slug: str, manifest_hash: str, manifest_short: str, run_id: str, profile: str | None = None
    ) -> dict[str, Path]:
        """Resolve AIOP (AI Observability Pack) paths.

        Args:
            pipeline_slug: Pipeline identifier
            manifest_hash: Full manifest hash
            manifest_short: Short manifest hash
            run_id: Run identifier
            profile: Optional profile name

        Returns:
            Dictionary of paths for AIOP outputs
        """
        # Use default profile if enabled and not provided
        if profile is None and self.fs_config.profiles.enabled:
            profile = self.fs_config.profiles.default

        # Build tokens for manifest directory
        manifest_tokens = {
            "pipeline_slug": pipeline_slug,
            "profile": profile or "",
            "manifest_hash": manifest_hash,
            "manifest_short": manifest_short,
        }

        # Render manifest directory name
        manifest_dir_name = self.renderer.render(self.fs_config.naming.manifest_dir, manifest_tokens)

        # Build tokens for run directory
        run_tokens = {"run_id": run_id}

        # Render run directory name
        run_dir_name = self.renderer.render(self.fs_config.naming.aiop_run_dir, run_tokens)

        # Build base path
        if self.fs_config.profiles.enabled and profile:
            base_path = (
                self.fs_config.resolve_path(self.fs_config.aiop_dir) / profile / manifest_dir_name / run_dir_name
            )
        else:
            base_path = self.fs_config.resolve_path(self.fs_config.aiop_dir) / manifest_dir_name / run_dir_name

        return {
            "base": base_path,
            "summary": base_path / "summary.json",
            "run_card": base_path / "run-card.md",
            "annex": base_path / "annex",
        }

    def index_paths(self) -> dict[str, Path]:
        """Resolve index paths.

        Returns:
            Dictionary of paths for indexes
        """
        index_dir = self.fs_config.resolve_path(self.fs_config.index_dir)

        return {
            "base": index_dir,
            "runs": index_dir / "runs.jsonl",
            "by_pipeline": index_dir / "by_pipeline",
            "latest": index_dir / "latest",
            "counters": index_dir / "counters.sqlite",
        }

    def ensure_dir(self, path: Path) -> Path:
        """Ensure directory exists.

        Args:
            path: Directory path to create

        Returns:
            Created directory path
        """
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _format_timestamp(self, ts: datetime) -> str:
        """Format timestamp according to configuration.

        Args:
            ts: Timestamp to format

        Returns:
            Formatted timestamp string
        """
        ts_format = self.fs_config.naming.run_ts_format

        if ts_format == "iso_basic_z":
            # ISO 8601 basic format: YYYY-mm-ddTHH-MM-SSZ
            return ts.strftime("%Y%m%dT%H%M%SZ")
        elif ts_format == "epoch_ms":
            # Unix timestamp in milliseconds
            return str(int(ts.timestamp() * 1000))
        elif ts_format == "none":
            # No timestamp
            return ""
        else:
            # Custom strftime format
            try:
                return ts.strftime(ts_format)
            except Exception:
                # Fallback to ISO basic on error
                return ts.strftime("%Y%m%dT%H%M%SZ")


def slugify_token(value: str) -> str:
    """Slugify a token value for filesystem safety.

    Converts to lowercase, replaces spaces with hyphens,
    removes unsafe characters, and collapses separators.

    Args:
        value: Raw token value

    Returns:
        Filesystem-safe slug
    """
    if not value:
        return ""

    # Convert to lowercase
    slug = value.lower()

    # Replace spaces and underscores with hyphens
    slug = slug.replace(" ", "-").replace("_", "-")

    # Keep only alphanumeric, hyphens, and underscores
    slug = re.sub(r"[^a-z0-9\-_]", "", slug)

    # Collapse multiple separators
    slug = re.sub(r"-+", "-", slug)
    slug = re.sub(r"_+", "_", slug)

    # Remove leading/trailing separators
    slug = slug.strip("-_")

    return slug


def normalize_manifest_hash(hash_str: str) -> str:
    """Normalize manifest hash to pure hex format (remove algorithm prefix if present).

    Accepts various formats and returns pure hex:
    - 'sha256:<hex>' → '<hex>'
    - 'sha256<hex>' → '<hex>'
    - '<hex>' → '<hex>'

    Args:
        hash_str: Hash string (possibly with algorithm prefix)

    Returns:
        Pure hex hash string (no prefix)

    Examples:
        >>> normalize_manifest_hash('sha256:abc123')
        'abc123'
        >>> normalize_manifest_hash('sha256abc123')
        'abc123'
        >>> normalize_manifest_hash('abc123')
        'abc123'
    """
    if not hash_str:
        return ""

    # Handle 'sha256:<hex>' format
    if ":" in hash_str:
        return hash_str.split(":", 1)[1]

    # Handle 'sha256<hex>' format (no colon)
    if hash_str.startswith("sha256") and len(hash_str) > 6:
        # Check if remainder looks like hex
        remainder = hash_str[6:]
        if all(c in "0123456789abcdef" for c in remainder.lower()):
            return remainder

    # Already pure hex
    return hash_str


def compute_manifest_hash(manifest: dict[str, Any], algo: str = "sha256_slug", profile: str | None = None) -> str:
    """Compute deterministic manifest hash.

    Excludes ephemeral metadata fields (generated_at, manifest_hash, manifest_short)
    to ensure the same OML inputs always produce the same hash.

    Args:
        manifest: Manifest dictionary
        algo: Hash algorithm (currently only "sha256_slug" supported)
        profile: Optional profile name to include in hash

    Returns:
        Hex digest of manifest hash

    Raises:
        ValueError: If algorithm is not supported
    """
    if algo != "sha256_slug":
        raise ValueError(f"Unsupported manifest_hash_algo: {algo}")

    # Create a copy of manifest excluding ephemeral fields
    import copy

    manifest_for_hash = copy.deepcopy(manifest)

    # Remove ephemeral metadata fields that would break determinism
    if "meta" in manifest_for_hash:
        meta = manifest_for_hash["meta"]
        # Exclude timestamp (changes every compilation)
        meta.pop("generated_at", None)
        # Exclude circular references (added after hash computation)
        meta.pop("manifest_hash", None)
        meta.pop("manifest_short", None)

    # Remove manifest_fp from fingerprints (it's added before hash computation)
    if "pipeline" in manifest_for_hash and "fingerprints" in manifest_for_hash["pipeline"]:
        manifest_for_hash["pipeline"]["fingerprints"].pop("manifest_fp", None)

    # Create deterministic JSON representation
    # Include profile in hash to ensure different profiles have different hashes
    hash_data = {
        "manifest": manifest_for_hash,
        "profile": profile or "",
    }

    # Sort keys for determinism
    canonical_json = json.dumps(hash_data, sort_keys=True, separators=(",", ":"))

    # Compute SHA-256
    hash_obj = hashlib.sha256(canonical_json.encode("utf-8"))

    return hash_obj.hexdigest()


def get_git_branch() -> str:
    """Get current git branch name.

    Returns:
        Branch name or empty string if not in git repo
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def get_current_user() -> str:
    """Get current username.

    Returns:
        Username or empty string if not available
    """
    try:
        return getpass.getuser()
    except Exception:
        return ""


def normalize_tags(tags: list[str]) -> str:
    """Normalize tags for path inclusion.

    Args:
        tags: List of tags

    Returns:
        Normalized tag string (joined with +)
    """
    if not tags:
        return ""

    # Slugify each tag and join with +
    normalized = [slugify_token(tag) for tag in tags]
    normalized = [tag for tag in normalized if tag]  # Filter empty tags

    return "+".join(normalized)
