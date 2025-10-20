# # Copyright (c) 2025 Osiris Project
# #
# # Licensed under the Apache License, Version 2.0 (the "License");
# # you may not use this file except in compliance with the License.
# # You may obtain a copy of the License at
# #
# #     http://www.apache.org/licenses/LICENSE-2.0
# #
# # Unless required by applicable law or agreed to in writing, software
# # distributed under the License is distributed on an "AS IS" BASIS,
# # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# # See the License for the specific language governing permissions and
# # limitations under the License.

"""Configuration management for Osiris v2."""

import contextlib
import datetime
import os
from pathlib import Path
import re
from typing import Any

import yaml


class ConfigError(Exception):
    """Configuration-related errors."""

    pass


def load_config(config_path: str = ".osiris.yaml") -> dict[str, Any]:
    """Load configuration from YAML file.

    Args:
        config_path: Path to configuration file

    Returns:
        Configuration dictionary

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid
    """
    config_file = Path(config_path)

    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file '{config_path}' not found")

    with open(config_file) as f:
        config = yaml.safe_load(f)

    return config or {}


def create_sample_config(
    config_path: str = "osiris.yaml", no_comments: bool = False, to_stdout: bool = False, base_path: str = ""
) -> str:
    """Create a sample configuration file with Filesystem Contract v1.

    Args:
        config_path: Path where to create the config file
        no_comments: If True, remove comment lines
        to_stdout: If True, return content instead of writing to file
        base_path: Base path for the filesystem contract (default: empty string, uses CWD)

    Returns:
        Generated config content if to_stdout is True, else empty string
    """
    config_content = """version: '2.0'

# ============================================================================
# OSIRIS FILESYSTEM CONTRACT v1 (ADR-0028)
# All paths resolve relative to `base_path`. If omitted, the project root is used.
# ============================================================================

filesystem:
  # Absolute root for all Osiris project files (useful for servers/CI).
  # Example: "/srv/osiris/acme" or leave empty to use the repo root.
  base_path: "__BASE_PATH_PLACEHOLDER__"

  # Profiles: explicitly list allowed profile names and the default.
  # When enabled, Osiris injects a "{profile}/" path segment in build/aiop/run_logs.
  profiles:
    enabled: true
    values: ["dev", "staging", "prod", "ml", "finance", "incident_debug"]
    default: "dev"

  # Where AI/human-authored OML lives (pipeline sources).
  # With profiles enabled, you may mirror pipelines/<profile>/..., or keep a flat pipelines/.
  pipelines_dir: "pipelines"

  # Deterministic, versionable build artifacts:
  # build/pipelines/[{profile}/]<slug>/<manifest_short>-<manifest_hash>/{manifest.yaml, plan.json, fingerprints.json, run_summary.json, cfg/...}
  build_dir: "build"

  # Per-run AI Observability Packs (NEVER overwritten):
  # aiop/[{profile}/]<slug>/<manifest_short>-<manifest_hash>/<run_id>/{summary.json, run-card.md, annex/...}
  aiop_dir: "aiop"

  # User-facing full runtime logs by run (cleaned by retention):
  # run_logs/[{profile}/]<slug>/{run_ts}_{run_id}-{manifest_short}/{events.jsonl, metrics.jsonl, debug.log, osiris.log, artifacts/...}
  run_logs_dir: "run_logs"

  # Internal hidden state (advanced users rarely need to touch this):
  # sessions: conversational/chat session state for Osiris chat/agents
  # cache:    discovery/profiling cache (table schemas, sampled stats)
  # index:    append-only run indexes and counters for fast listing/queries
  # mcp_logs: MCP server logs (audit, telemetry, cache)
  sessions_dir: ".osiris/sessions"
  cache_dir: ".osiris/cache"
  index_dir: ".osiris/index"
  mcp_logs_dir: ".osiris/mcp/logs"

  # Naming templates (human-friendly yet machine-stable).
  # Available tokens:
  #   {pipeline_slug} {profile} {manifest_hash} {manifest_short} {run_id} {run_ts} {status} {branch} {user} {tags}
  naming:
    # Build folder for a compiled manifest (relative to build_dir/pipelines[/profile]):
    manifest_dir: "{pipeline_slug}/{manifest_short}-{manifest_hash}"

    # Run folder under run_logs_dir[/profile]:
    run_dir: "{pipeline_slug}/{run_ts}_{run_id}-{manifest_short}"

    # Per-run folder name under aiop/.../<manifest>/:
    aiop_run_dir: "{run_id}"

    # Timestamp format for {run_ts} (no colons). Options: "iso_basic_z" -> YYYY-mm-ddTHH-MM-SSZ, or "none".
    run_ts_format: "iso_basic_z"

    # Number of characters used in {manifest_short}:
    manifest_short_len: 7

  # What to write into build/ (deterministic artifacts):
  artifacts:
    # Save compiled manifest (deterministic plan of execution).
    manifest: true
    # Save normalized DAG/execution plan (JSON).
    plan: true
    # Save SHA-256 fingerprints of inputs (for caching/consistency checks).
    fingerprints: true
    # Save compile-time metadata (compiler version, inputs, timestamps, profile, tags).
    run_summary: true
    # Save per-step effective configs (useful for diffs and debuggability).
    cfg: true
    # Optionally copy last N events to build/ for quick inspection (0 = disabled).
    save_events_tail: 0

  # Retention applies ONLY to run_logs_dir and aiop annex shards (build/ is permanent).
  # Execute retention via:
  #   - "osiris maintenance clean" (manual or scheduled), or
  #   - a library call from your own cron/systemd timer.
  retention:
    run_logs_days: 7  # delete run_logs older than N days
    aiop_keep_runs_per_pipeline: 200  # keep last N runs per pipeline in aiop/
    annex_keep_days: 14  # delete NDJSON annex shards older than N days

  # Output configuration for pipeline data exports
  outputs:
    directory: "output"  # where pipeline data exports land
    format: "csv"        # default writer format if not overridden

ids:
  # Run identifier format (choose one OR compose multiple; examples):
  # - "ulid"        -> 01J9Z8KQ8R1WQH6K9Z7Q2R1X7F
  # - "iso_ulid"    -> 2025-10-07T14-22-19Z_01J9Z8KQ8R1WQH6K9Z7Q2R1X7F
  # - "uuidv4"      -> 550e8400-e29b-41d4-a716-446655440000
  # - "snowflake"   -> 193514046488576000 (time-ordered 64-bit)
  # - "incremental" -> run-000123  (requires the indexer to maintain counters)
  #
  # You may also define a composite format, e.g. ["incremental", "ulid"]
  # which renders as "run-000124_01J9Z8KQ8R1..." (order matters).
  run_id_format: ["incremental", "ulid"]

  # Manifest fingerprint algorithm (used for build folder naming):
  # - "sha256_slug": hex sha256; {manifest_short} length controlled above
  manifest_hash_algo: "sha256_slug"

# ============================================================================
# LOGGING CONFIGURATION
# Enhanced session logging with structured events and metrics (M0-Validation-4)
# ============================================================================
logging:
  level: INFO           # Log verbosity for .log files: DEBUG, INFO, WARNING, ERROR, CRITICAL

  # IMPORTANT: Events and log levels are INDEPENDENT systems:
  # - 'level' controls what goes into osiris.log (Python logging messages)
  # - 'events' controls what goes into events.jsonl (structured events)
  # Events are ALWAYS logged regardless of level setting - they use separate filtering below.

  events:               # Event types to log (structured JSONL format)
    # Use "*" to log ALL events (recommended), or specify individual events below:
    #
    # Session Lifecycle:
    #   run_start         - Session begins (command starts)
    #   run_end           - Session completes successfully
    #   run_error         - Session fails with error
    #
    # Chat & Conversation:
    #   chat_start        - Chat session begins
    #   chat_end          - Chat session ends
    #   user_message      - User sends a message
    #   assistant_response - AI responds to user
    #   chat_interrupted  - Chat stopped by Ctrl+C
    #
    # Chat Modes:
    #   sql_mode_start           - Direct SQL mode begins
    #   single_message_start     - One-shot message mode
    #   interactive_mode_start   - Interactive conversation mode
    #
    # Database Discovery:
    #   discovery_start   - Schema discovery begins
    #   discovery_end     - Schema discovery completes
    #   cache_hit         - Found cached discovery data
    #   cache_miss        - No cached data, discovering fresh
    #   cache_lookup      - Checking cache for discovery data
    #   cache_error       - Cache access failed
    #
    # Validation & Config:
    #   validate_start    - Configuration validation begins
    #   validate_complete - Configuration validation done
    #   validate_error    - Configuration validation failed
    #
    # Response Quality:
    #   sql_response             - SQL mode generated response
    #   single_message_response  - Single message got response
    #   single_message_empty_response - Single message got no response
    #   sql_error               - SQL mode encountered error
    #   single_message_error    - Single message mode failed
    #   chat_error              - General chat error occurred
    #
    # Examples:
    #   - "*"                          # Log ALL events (recommended)
    #   - ["run_start", "run_end"]     # Only session lifecycle
    #   - ["user_message", "assistant_response"]  # Only conversation
    #
    # NOTE: Events are filtered HERE, not by 'level' above. Even with level: ERROR,
    # validate_start events will still be logged if included in this list.
    - "*"
  metrics:
    enabled: true       # Enable performance metrics collection
    retention_hours: 168   # Keep metrics for 7 days (168 hours)
  retention: 7d         # Session retention policy (7d = 7 days, supports: 1d, 30d, 6m, 1y)
  env_overrides:        # Environment variables that can override these settings
    OSIRIS_LOG_LEVEL: level
  cli_flags:            # CLI flags that can override these settings (highest precedence)
    --log-level: level

# ============================================================================
# DATABASE DISCOVERY SETTINGS
# Controls how Osiris explores your database schema and samples data
# ============================================================================
discovery:
  sample_size: 10       # Number of sample rows to fetch per table for AI context
  parallel_tables: 5    # Max tables to discover simultaneously (performance tuning)
  timeout_seconds: 30   # Discovery timeout per table (prevents hanging)

# ============================================================================
# LLM (AI) CONFIGURATION
# Controls the AI behavior - API keys go in .env file, not here
# ============================================================================
llm:
  provider: openai      # Primary LLM: openai, claude, gemini

  # OpenAI models (active by default)
  model: gpt-5-mini           # Primary OpenAI model
  fallback_model: gpt-5       # Fallback OpenAI model

  # For Claude (uncomment below and comment OpenAI models above):
  # provider: claude
  # model: claude-sonnet-4-20250514       # Primary Claude model
  # fallback_model: claude-opus-4-1-20250805  # Fallback Claude model

  # For Gemini (uncomment below and comment other models above):
  # provider: gemini
  # model: gemini-2.5-flash               # Primary Gemini model
  # fallback_model: gemini-2.5-pro        # Fallback Gemini model

  temperature: 0.1      # Low temperature = deterministic SQL generation
  max_tokens: 2000      # Maximum response length from AI
  timeout_seconds: 30   # API request timeout
  fallback_enabled: true   # Use backup models if primary fails

# ============================================================================
# PIPELINE SAFETY & VALIDATION
# Security settings to prevent dangerous operations
# ============================================================================
pipeline:
  validation_required: true   # Always require human approval before execution
  auto_execute: false         # Never auto-execute without user confirmation
  max_sql_length: 10000       # Reject extremely long SQL queries
  dangerous_keywords:         # Block destructive operations
  - DROP
  - DELETE
  - TRUNCATE
  - ALTER

# ============================================================================
# VALIDATION CONFIGURATION
# Configuration validation modes and output formats (M0-Validation-4)
# ============================================================================
validate:
  mode: warn            # Validation mode: strict, warn, off
  json: false           # Output validation results in JSON format
  show_effective: true  # Show effective configuration values and their sources

# ============================================================================
# VALIDATION RETRY CONFIGURATION
# Pipeline validation retry settings (M1b.3 per ADR-0013)
# ============================================================================
validation:
  retry:
    max_attempts: 2           # Maximum retry attempts (0-5, 0 = strict mode)
    include_history_in_hitl: true  # Show retry history in HITL prompts
    history_limit: 3          # Max attempts to show in HITL history
    diff_format: patch        # Diff format: "patch" or "summary"

# ============================================================================
# AIOP (AI Operation Package) CONFIGURATION
# Precedence: CLI > Environment ($OSIRIS_AIOP_*) > Osiris.yaml > built-in defaults
# AIOP: Structured export for LLMs (Narrative, Semantic, Evidence; Control in future)
# ============================================================================
aiop:
  enabled: true            # Auto-generate AIOP after each run (even on failure)
  policy: core             # core = Core only (LLM-friendly); annex = Core + NDJSON Annex; custom = Core + fine-tuning knobs
  max_core_bytes: 300000   # Hard cap for Core size; deterministic truncation with markers when exceeded

  # How many timeline events go into Core (Annex can still contain all)
  timeline_density: medium # low = key events only; medium = + aggregated per-step metrics (default); high = all incl. debug
  metrics_topk: 100        # Keep top-K metrics/steps in Core (errors/checks prioritized)
  schema_mode: summary     # summary = names/relations/fingerprints; detailed = adds small schema/config excerpts (no secrets)
  delta: previous          # previous = compare to last run of same pipeline@manifest_hash (first_run:true if none); none = disable
  run_card: true           # Also write Markdown run-card for PR/Slack

  output:
    core_path: "aiop/{session_id}/aiop.json"         # Where to write Core JSON
    run_card_path: "aiop/{session_id}/run-card.md"   # Where to write Markdown run-card

  annex:
    enabled: false         # Enable NDJSON Annex (timeline/metrics/errors shards)
    dir: aiop/annex        # Directory for Annex shards
    compress: none         # none|gzip|zstd (applies to Annex only; Core is always uncompressed for readability)

  # Path variable templating (for output paths)
  path_vars:
    ts_format: "%Y%m%d_%H%M%S"  # Timestamp format for {ts} variable
    # Available variables in paths:
    # {session_id} - Full session ID
    # {ts} - Timestamp formatted with ts_format
    # {manifest_hash} - Pipeline manifest hash
    # {status} - Run status (success/failure)

  # Index configuration (tracks all runs for delta analysis)
  index:
    enabled: true          # Enable index updates after each run
    runs_jsonl: "aiop/index/runs.jsonl"        # All runs chronologically
    by_pipeline_dir: "aiop/index/by_pipeline"  # Per-pipeline run history
    latest_symlink: "aiop/latest"              # Symlink to latest run

  retention:
    keep_runs: 50          # Keep last N Core files (optional)
    annex_keep_days: 14    # Delete Annex shards older than N days (optional)

  # Narrative layer configuration
  narrative:
    sources: [manifest, repo_readme, commit_message, discovery]  # default source list
    session_chat:
      enabled: false       # opt-in for chat logs (default: false)
      mode: masked         # masked|quotes|off
      max_chars: 2000      # truncation limit for chat logs
      redact_pii: true     # PII removal before Annex inclusion
"""

    # Replace base_path placeholder with actual value
    config_content = config_content.replace("__BASE_PATH_PLACEHOLDER__", base_path)

    # Process content based on flags
    if no_comments:
        # Remove lines starting with # (comments) but keep YAML comments after values
        lines = config_content.split("\n")
        filtered_lines = []
        for line in lines:
            # Keep empty lines and lines that don't start with #
            # Also keep lines where # appears after content (inline comments)
            stripped = line.lstrip()
            if not stripped.startswith("#") or not stripped[1:].lstrip():
                filtered_lines.append(line)
            elif line.strip() == "#":
                # Keep separator lines that are just #
                pass
            # Skip other comment lines
        config_content = "\n".join(filtered_lines)

    if to_stdout:
        return config_content

    # Write to file (with backup if exists)
    config_file = Path(config_path)
    if config_file.exists():
        backup_path = f"{config_path}.backup"
        config_file.rename(backup_path)

    with open(config_file, "w") as f:
        f.write(config_content)

    return ""


class ConfigManager:
    """Configuration manager for loading and managing Osiris configuration."""

    def __init__(self, config_path: str | None = None):
        """Initialize configuration manager.

        Args:
            config_path: Path to configuration file (defaults to osiris.yaml)
        """
        self.config_path = config_path or "osiris.yaml"
        self._config = None

    def load_config(self) -> dict[str, Any]:
        """Load configuration from file.

        Returns:
            Configuration dictionary
        """
        if self._config is None:
            try:
                self._config = load_config(self.config_path)
            except FileNotFoundError:
                # Return default configuration if file doesn't exist
                self._config = self._get_default_config()

        return self._config

    def _get_default_config(self) -> dict[str, Any]:
        """Get default configuration when no config file exists."""
        return {
            "version": "2.0",
            # Logging Configuration
            "logging": {
                "level": "INFO",
                "file": None,  # Console-only logging by default
                "format": "%(asctime)s - %(name)s - [%(session_id)s] - %(levelname)s - %(message)s",
            },
            # Output Configuration
            "output": {
                "format": "csv",
                "directory": "output/",
                "filename_template": "pipeline_{session_id}_{timestamp}",
            },
            # Session Management
            "sessions": {"directory": ".osiris_sessions/", "cleanup_days": 30, "cache_ttl": 3600},
            # Discovery Settings
            "discovery": {"sample_size": 10, "parallel_tables": 5, "timeout_seconds": 30},
            # LLM Configuration (non-sensitive)
            "llm": {
                "provider": "openai",
                "temperature": 0.1,
                "max_tokens": 2000,
                "timeout_seconds": 30,
                "fallback_enabled": True,
            },
            # Pipeline Generation Settings
            "pipeline": {
                "validation_required": True,
                "auto_execute": False,
                "max_sql_length": 10000,
                "dangerous_keywords": ["DROP", "DELETE", "TRUNCATE", "ALTER"],
            },
        }


def load_connections_yaml(substitute_env: bool = True) -> dict[str, Any]:
    """Load connections configuration with optional ${VAR} substitution from environment.

    Args:
        substitute_env: If True, substitute ${VAR} with environment values.
                       If False, return raw config with ${VAR} patterns intact.

    Searches for osiris_connections.yaml in:
    1. OSIRIS_HOME (if set)
    2. Current working directory
    3. Repository root (parent directories)

    Returns:
        Dict structure {family: {alias: {fields}}}
        Returns empty dict if no connections file found
    """
    import os

    # Search for connections file
    search_paths = []

    # 1. Check OSIRIS_HOME first (highest priority)
    osiris_home = os.environ.get("OSIRIS_HOME", "").strip()
    if osiris_home:
        search_paths.append(Path(osiris_home) / "osiris_connections.yaml")

    # 2. Check current working directory
    search_paths.append(Path.cwd() / "osiris_connections.yaml")

    # 3. Check parent of current working directory
    search_paths.append(Path.cwd().parent / "osiris_connections.yaml")

    # 4. Check repository root (from osiris/core/)
    search_paths.append(Path(__file__).parent.parent.parent / "osiris_connections.yaml")

    connections_file = None
    for path in search_paths:
        if path.exists():
            connections_file = path
            break

    if not connections_file:
        return {}

    # Load YAML
    with open(connections_file) as f:
        data = yaml.safe_load(f) or {}

    if "connections" not in data:
        return {}

    connections = data["connections"]

    if not substitute_env:
        # Return raw config without substitution
        return connections

    # Perform environment variable substitution
    def substitute_env_vars(obj):
        """Recursively substitute ${VAR} with environment variable values."""
        if isinstance(obj, str):
            # Find all ${VAR} patterns
            pattern = r"\$\{([^}]+)\}"

            def replacer(match):
                var_name = match.group(1)
                value = os.environ.get(var_name)
                if value is None or value == "":
                    # Keep original if not found or empty (will error later if required)
                    return match.group(0)
                return value

            return re.sub(pattern, replacer, obj)
        elif isinstance(obj, dict):
            return {k: substitute_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [substitute_env_vars(item) for item in obj]
        else:
            return obj

    return substitute_env_vars(connections)


def parse_connection_ref(ref: str) -> tuple[str | None, str | None]:
    """Parse a connection reference string like '@family.alias'.

    Args:
        ref: Connection reference string (e.g., '@mysql.primary')

    Returns:
        Tuple of (family, alias) or (None, None) if invalid format

    Examples:
        parse_connection_ref('@mysql.primary') -> ('mysql', 'primary')
        parse_connection_ref('@mysql') -> Error
        parse_connection_ref('mysql.primary') -> (None, None)
    """
    if not ref or not ref.startswith("@"):
        return None, None

    # Strip @ and split
    ref = ref[1:]  # Remove @
    if "." not in ref:
        raise ValueError(f"Invalid connection reference format: '@{ref}'. Expected '@family.alias'")

    parts = ref.split(".", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid connection reference format: '@{ref}'. Expected '@family.alias'")

    family, alias = parts
    if not family or not alias:
        raise ValueError(f"Invalid connection reference format: '@{ref}'. Family and alias cannot be empty")

    return family, alias


def resolve_connection(family: str, alias: str | None = None) -> dict[str, Any]:  # noqa: PLR0915
    """Resolve connection by family and optional alias.

    Args:
        family: Connection family (e.g., "mysql", "supabase", "duckdb")
        alias: Optional alias name. Can be:
            - None: Apply default selection precedence
            - "@family.alias": Parse and resolve specific alias
            - "alias_name": Direct alias name

    Returns:
        Resolved dict with secrets substituted

    Raises:
        ValueError: If connection cannot be resolved
    """
    # Parse @family.alias format if provided
    if alias and alias.startswith("@"):
        # Parse @family.alias format
        parts = alias[1:].split(".", 1)
        if len(parts) == 2:
            parsed_family, parsed_alias = parts
            # Override family if specified in @ format
            if parsed_family:
                family = parsed_family
            alias = parsed_alias
        else:
            raise ValueError(f"Invalid connection reference format: {alias}. Expected @family.alias")

    # Load connections
    connections = load_connections_yaml()

    # Check if family exists
    if family not in connections:
        available = list(connections.keys())
        if not available:
            raise ValueError(f"No connections configured. Create osiris_connections.yaml with {family} connections.")
        raise ValueError(f"Connection family '{family}' not found. Available families: {', '.join(available)}")

    family_connections = connections[family]

    if not family_connections:
        raise ValueError(f"No connections defined for family '{family}'")

    # If specific alias requested, return it
    if alias:
        if alias not in family_connections:
            available_aliases = list(family_connections.keys())
            raise ValueError(
                f"Connection alias '{alias}' not found in family '{family}'. "
                f"Available aliases: {', '.join(available_aliases)}"
            )
        connection = family_connections[alias].copy()
        # Remove the 'default' flag if present (not needed in resolved connection)
        connection.pop("default", None)

        # Check for unresolved environment variables
        def check_unresolved_vars(obj, path=""):
            """Check for any remaining ${VAR} patterns."""
            if isinstance(obj, str):
                pattern = r"\$\{([^}]+)\}"
                matches = re.findall(pattern, obj)
                if matches:
                    for var in matches:
                        field_name = path.split(".")[-1] if path else "field"
                        raise ConfigError(f"Environment variable '{var}' not set for {field_name} in {family}.{alias}")
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    new_path = f"{path}.{k}" if path else k
                    check_unresolved_vars(v, new_path)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    check_unresolved_vars(item, f"{path}[{i}]")

        check_unresolved_vars(connection)
        return connection

    # Apply default selection precedence

    # 1. Look for alias with default: true
    for alias_name, conn_data in family_connections.items():
        if conn_data.get("default") is True:
            connection = conn_data.copy()
            connection.pop("default", None)

            # Check for unresolved vars
            def check_unresolved_vars(obj, path="", current_alias=alias_name):
                if isinstance(obj, str):
                    pattern = r"\$\{([^}]+)\}"
                    matches = re.findall(pattern, obj)
                    if matches:
                        for var in matches:
                            field_name = path.split(".")[-1] if path else "field"
                            raise ConfigError(
                                f"Environment variable '{var}' not set for {field_name} in {family}.{current_alias}"
                            )
                elif isinstance(obj, dict):
                    for k, v in obj.items():
                        new_path = f"{path}.{k}" if path else k
                        check_unresolved_vars(v, new_path, current_alias)
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        check_unresolved_vars(item, f"{path}[{i}]", current_alias)

            check_unresolved_vars(connection)
            return connection

    # 2. Look for alias named "default"
    if "default" in family_connections:
        connection = family_connections["default"].copy()
        connection.pop("default", None)

        # Check for unresolved vars
        def check_unresolved_vars(obj, path=""):
            if isinstance(obj, str):
                pattern = r"\$\{([^}]+)\}"
                matches = re.findall(pattern, obj)
                if matches:
                    for var in matches:
                        field_name = path.split(".")[-1] if path else "field"
                        raise ValueError(f"Environment variable '{var}' not set for {field_name} in {family}.default")
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    new_path = f"{path}.{k}" if path else k
                    check_unresolved_vars(v, new_path)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    check_unresolved_vars(item, f"{path}[{i}]")

        check_unresolved_vars(connection)
        return connection

    # 3. Error with available aliases
    available_aliases = list(family_connections.keys())
    raise ValueError(
        f"No default connection for family '{family}'. "
        f"Available aliases: {', '.join(available_aliases)}. "
        f"Either: 1) Set 'default: true' on an alias, 2) Name an alias 'default', "
        f"or 3) Specify an alias explicitly."
    )


# ============================================================================
# AIOP Configuration Functions
# ============================================================================


# Define AIOP defaults
def _env_truthy(value: str | None) -> bool:
    """Return True if environment-like string is truthy."""

    if value is None:
        return False
    return value.strip().lower() not in {"", "0", "false", "off", "no"}


AIOP_DEFAULTS = {
    "enabled": True,
    "policy": "core",
    "max_core_bytes": 300000,
    "timeline_density": "medium",
    "metrics_topk": 100,
    "schema_mode": "summary",
    "delta": "previous",
    "run_card": True,
    "use_session_dir": False,
    "path_vars": {
        "ts_format": "%Y%m%d-%H%M%S",
    },
    "output": {
        "core_path": "aiop/aiop.json",
        "run_card_path": "aiop/run-card.md",
    },
    "annex": {
        "enabled": False,
        "dir": "aiop/annex",
        "compress": "none",
    },
    "index": {
        "enabled": True,
        "runs_jsonl": "aiop/index/runs.jsonl",
        "by_pipeline_dir": "aiop/index/by_pipeline",
        "latest_symlink": "aiop/latest",
    },
    "retention": {
        "keep_runs": 50,
        "annex_keep_days": 14,
    },
    "narrative": {
        "sources": ["manifest", "repo_readme", "commit_message", "discovery"],
        "session_chat": {
            "enabled": False,
            "mode": "masked",
            "max_chars": 2000,
            "redact_pii": True,
        },
    },
}


def load_osiris_yaml(path: str | None = None) -> dict[str, Any]:
    """Load Osiris YAML configuration file.

    Args:
        path: Path to osiris.yaml (defaults to "osiris.yaml")

    Returns:
        Loaded configuration dict or empty dict if file doesn't exist
    """
    yaml_path = Path(path or "osiris.yaml")
    if not yaml_path.exists():
        return {}

    try:
        with open(yaml_path) as f:
            config = yaml.safe_load(f) or {}
        return config
    except Exception:
        # If file exists but can't be parsed, return empty dict
        return {}


def load_aiop_env() -> dict[str, Any]:
    """Load AIOP configuration from environment variables.

    Returns:
        Dictionary of AIOP configuration from environment
    """
    config = {}

    # Simple mappings
    env_mappings = [
        ("OSIRIS_AIOP_ENABLED", "enabled", lambda x: x.lower() == "true"),
        ("OSIRIS_AIOP_POLICY", "policy", str),
        ("OSIRIS_AIOP_MAX_CORE_BYTES", "max_core_bytes", int),
        ("OSIRIS_AIOP_TIMELINE_DENSITY", "timeline_density", str),
        ("OSIRIS_AIOP_METRICS_TOPK", "metrics_topk", int),
        ("OSIRIS_AIOP_SCHEMA_MODE", "schema_mode", str),
        ("OSIRIS_AIOP_DELTA", "delta", str),
        ("OSIRIS_AIOP_RUN_CARD", "run_card", lambda x: x.lower() == "true"),
        ("OSIRIS_AIOP_USE_SESSION_DIR", "use_session_dir", _env_truthy),
    ]

    for env_key, config_key, converter in env_mappings:
        value = os.environ.get(env_key)
        if value is not None:
            with contextlib.suppress(ValueError, TypeError):
                config[config_key] = converter(value)
                # Skip invalid values

    # Nested mappings
    if "OSIRIS_AIOP_OUTPUT_CORE_PATH" in os.environ:
        config.setdefault("output", {})["core_path"] = os.environ["OSIRIS_AIOP_OUTPUT_CORE_PATH"]

    if "OSIRIS_AIOP_OUTPUT_RUN_CARD_PATH" in os.environ:
        config.setdefault("output", {})["run_card_path"] = os.environ["OSIRIS_AIOP_OUTPUT_RUN_CARD_PATH"]

    if "OSIRIS_AIOP_ANNEX_ENABLED" in os.environ:
        config.setdefault("annex", {})["enabled"] = os.environ["OSIRIS_AIOP_ANNEX_ENABLED"].lower() == "true"

    if "OSIRIS_AIOP_ANNEX_DIR" in os.environ:
        config.setdefault("annex", {})["dir"] = os.environ["OSIRIS_AIOP_ANNEX_DIR"]

    if "OSIRIS_AIOP_ANNEX_COMPRESS" in os.environ:
        config.setdefault("annex", {})["compress"] = os.environ["OSIRIS_AIOP_ANNEX_COMPRESS"]

    if "OSIRIS_AIOP_RETENTION_KEEP_RUNS" in os.environ:
        config.setdefault("retention", {})["keep_runs"] = int(os.environ["OSIRIS_AIOP_RETENTION_KEEP_RUNS"])

    if "OSIRIS_AIOP_RETENTION_ANNEX_KEEP_DAYS" in os.environ:
        config.setdefault("retention", {})["annex_keep_days"] = int(os.environ["OSIRIS_AIOP_RETENTION_ANNEX_KEEP_DAYS"])

    # Narrative sources (comma-separated list)
    if "OSIRIS_AIOP_NARRATIVE_SOURCES" in os.environ:
        sources_str = os.environ["OSIRIS_AIOP_NARRATIVE_SOURCES"]
        config.setdefault("narrative", {})["sources"] = [s.strip() for s in sources_str.split(",")]

    # Session chat
    if "OSIRIS_AIOP_NARRATIVE_SESSION_CHAT_ENABLED" in os.environ:
        config.setdefault("narrative", {}).setdefault("session_chat", {})["enabled"] = (
            os.environ["OSIRIS_AIOP_NARRATIVE_SESSION_CHAT_ENABLED"].lower() == "true"
        )

    if "OSIRIS_AIOP_NARRATIVE_SESSION_CHAT_MODE" in os.environ:
        config.setdefault("narrative", {}).setdefault("session_chat", {})["mode"] = os.environ[
            "OSIRIS_AIOP_NARRATIVE_SESSION_CHAT_MODE"
        ]

    if "OSIRIS_AIOP_NARRATIVE_SESSION_CHAT_MAX_CHARS" in os.environ:
        config.setdefault("narrative", {}).setdefault("session_chat", {})["max_chars"] = int(
            os.environ["OSIRIS_AIOP_NARRATIVE_SESSION_CHAT_MAX_CHARS"]
        )

    if "OSIRIS_AIOP_NARRATIVE_SESSION_CHAT_REDACT_PII" in os.environ:
        config.setdefault("narrative", {}).setdefault("session_chat", {})["redact_pii"] = (
            os.environ["OSIRIS_AIOP_NARRATIVE_SESSION_CHAT_REDACT_PII"].lower() == "true"
        )

    # Path vars
    if "OSIRIS_AIOP_PATH_VARS_TS_FORMAT" in os.environ:
        config.setdefault("path_vars", {})["ts_format"] = os.environ["OSIRIS_AIOP_PATH_VARS_TS_FORMAT"]

    # Support legacy flag (without OSIRIS_ prefix) for per-session directories
    if "AIOP_USE_SESSION_DIR" in os.environ:
        config["use_session_dir"] = _env_truthy(os.environ["AIOP_USE_SESSION_DIR"])

    # Index configuration
    if "OSIRIS_AIOP_INDEX_ENABLED" in os.environ:
        config.setdefault("index", {})["enabled"] = os.environ["OSIRIS_AIOP_INDEX_ENABLED"].lower() == "true"

    if "OSIRIS_AIOP_INDEX_RUNS_JSONL" in os.environ:
        config.setdefault("index", {})["runs_jsonl"] = os.environ["OSIRIS_AIOP_INDEX_RUNS_JSONL"]

    if "OSIRIS_AIOP_INDEX_BY_PIPELINE_DIR" in os.environ:
        config.setdefault("index", {})["by_pipeline_dir"] = os.environ["OSIRIS_AIOP_INDEX_BY_PIPELINE_DIR"]

    if "OSIRIS_AIOP_INDEX_LATEST_SYMLINK" in os.environ:
        config.setdefault("index", {})["latest_symlink"] = os.environ["OSIRIS_AIOP_INDEX_LATEST_SYMLINK"]

    return config


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries, with overlay taking precedence.

    Args:
        base: Base dictionary
        overlay: Dictionary to overlay on top

    Returns:
        Merged dictionary
    """
    result = base.copy()

    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def resolve_aiop_config(
    cli_args: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Resolve AIOP configuration with precedence: CLI > ENV > YAML > defaults.

    Args:
        cli_args: CLI arguments dictionary (optional)

    Returns:
        Tuple of (effective_config, sources_map)
        - effective_config: Final resolved configuration
        - sources_map: Map of config key to source ("DEFAULT", "YAML", "ENV", "CLI")
    """
    # Start with defaults
    effective = AIOP_DEFAULTS.copy()
    sources = {_flatten_key(k, v): "DEFAULT" for k, v in _flatten_dict(AIOP_DEFAULTS).items()}

    # Layer 2: YAML
    yaml_config = load_osiris_yaml()
    if yaml_config and "aiop" in yaml_config:
        aiop_yaml = yaml_config["aiop"]
        effective = _deep_merge(effective, aiop_yaml)
        for k, v in _flatten_dict(aiop_yaml).items():
            sources[_flatten_key(k, v)] = "YAML"

    # Layer 3: Environment
    env_config = load_aiop_env()
    if env_config:
        effective = _deep_merge(effective, env_config)
        for k, v in _flatten_dict(env_config).items():
            sources[_flatten_key(k, v)] = "ENV"

    # Layer 4: CLI
    if cli_args:
        # Map CLI args to config keys
        cli_config = {}

        # Direct mappings
        if "max_core_bytes" in cli_args and cli_args["max_core_bytes"] is not None:
            cli_config["max_core_bytes"] = cli_args["max_core_bytes"]
        if "timeline_density" in cli_args and cli_args["timeline_density"] is not None:
            cli_config["timeline_density"] = cli_args["timeline_density"]
        if "metrics_topk" in cli_args and cli_args["metrics_topk"] is not None:
            cli_config["metrics_topk"] = cli_args["metrics_topk"]
        if "schema_mode" in cli_args and cli_args["schema_mode"] is not None:
            cli_config["schema_mode"] = cli_args["schema_mode"]
        if "policy" in cli_args and cli_args["policy"] is not None:
            cli_config["policy"] = cli_args["policy"]
        if "compress" in cli_args and cli_args["compress"] is not None:
            cli_config.setdefault("annex", {})["compress"] = cli_args["compress"]
        if "annex_dir" in cli_args and cli_args["annex_dir"] is not None:
            cli_config.setdefault("annex", {})["dir"] = cli_args["annex_dir"]

        if cli_config:
            effective = _deep_merge(effective, cli_config)
            for k, v in _flatten_dict(cli_config).items():
                sources[_flatten_key(k, v)] = "CLI"

    effective, sources = _apply_aiop_session_dir(effective, sources)
    return effective, sources


def _apply_aiop_session_dir(config: dict[str, Any], sources: dict[str, str]) -> tuple[dict[str, Any], dict[str, str]]:
    """Apply session-aware path overrides when requested.

    When `use_session_dir` (or env `AIOP_USE_SESSION_DIR`) is truthy we rewrite the
    default paths to include `{session_id}` placeholders. This keeps legacy
    defaults stable while opt-in builds can still segregate outputs per run.
    """

    default_core = "aiop/aiop.json"
    default_run_card = "aiop/run-card.md"
    default_annex = "aiop/annex"

    session_core = "aiop/{session_id}/aiop.json"
    session_run_card = "aiop/{session_id}/run-card.md"
    session_annex = "aiop/{session_id}/annex"

    use_session_dir = bool(config.get("use_session_dir"))

    # Environment flag takes precedence over config for toggling behaviour
    if "AIOP_USE_SESSION_DIR" in os.environ:
        use_session_dir = _env_truthy(os.environ.get("AIOP_USE_SESSION_DIR"))
        sources["use_session_dir"] = "ENV"

    output_cfg = config.setdefault("output", {})
    annex_cfg = config.setdefault("annex", {})

    if use_session_dir:
        if output_cfg.get("core_path") == default_core:
            output_cfg["core_path"] = session_core
            sources["output.core_path"] = sources.get("output.core_path", "DEFAULT")
        if output_cfg.get("run_card_path") == default_run_card:
            output_cfg["run_card_path"] = session_run_card
            sources["output.run_card_path"] = sources.get("output.run_card_path", "DEFAULT")
        if annex_cfg.get("dir") == default_annex:
            annex_cfg["dir"] = session_annex
            sources["annex.dir"] = sources.get("annex.dir", "DEFAULT")

    return config, sources


def _flatten_dict(d: dict[str, Any], parent_key: str = "") -> dict[str, Any]:
    """Flatten a nested dictionary.

    Args:
        d: Dictionary to flatten
        parent_key: Parent key for recursion

    Returns:
        Flattened dictionary
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}.{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key).items())
        else:
            items.append((new_key, v))
    return dict(items)


def _flatten_key(key: str, value: Any) -> str:
    """Create a flattened key suitable for sources map."""
    _ = value  # Unused but required for signature compatibility
    return key


def render_path(template: str, ctx: dict, ts_format: str = "%Y%m%d-%H%M%S") -> str:
    """Render {session_id},{ts},{manifest_hash},{status} into an FS-safe relative path.

    Args:
        template: Path template with {var} placeholders
        ctx: Context dict with session_id, ts (datetime), manifest_hash, status
        ts_format: Format string for timestamp formatting

    Returns:
        Rendered path with variables substituted

    Raises:
        ValueError: If template contains unsafe path components
    """
    from pathlib import Path

    # Check if template contains any variables
    has_variables = "{" in template and "}" in template

    # Format timestamp if present
    render_ctx = ctx.copy()
    if "ts" in render_ctx and isinstance(render_ctx["ts"], datetime.datetime):
        render_ctx["ts"] = render_ctx["ts"].strftime(ts_format)

    # Simple string format substitution
    try:
        rendered = template.format(**render_ctx)
    except KeyError as e:
        # Provide default empty string for missing keys
        missing_key = str(e).strip("'")
        render_ctx[missing_key] = ""
        rendered = template.format(**render_ctx)

    # If template had no variables and file already exists, auto-suffix with session_id
    if not has_variables and Path(rendered).exists():
        # Insert session_id before the file extension
        path = Path(rendered)
        session_id = ctx.get("session_id", "unknown")
        if path.suffix:
            # Has extension: file.json -> file.run_123.json
            rendered = str(path.with_suffix(f".{session_id}{path.suffix}"))
        else:
            # No extension: file -> file.run_123
            rendered = f"{rendered}.{session_id}"

    # Security: ensure no parent directory escapes
    if ".." in rendered:
        raise ValueError(f"Path template resolved to unsafe path with '..': {rendered}")

    # Normalize path separators
    rendered = os.path.normpath(rendered)

    # Ensure relative path (remove leading slash if present)
    if rendered.startswith(os.sep):
        rendered = rendered[1:]

    return rendered
