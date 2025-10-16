"""Helper functions for CLI session management."""

from pathlib import Path


def get_logs_directory_for_cli() -> Path:
    """Get the base logs directory for CLI commands from filesystem contract.

    This function loads the filesystem configuration and returns the appropriate
    logs directory path. For non-MCP CLI commands (like 'osiris connections list'),
    logs go to filesystem.run_logs_dir.

    Returns:
        Path to base logs directory, resolved against base_path if configured

    Examples:
        >>> # With osiris.yaml: filesystem.run_logs_dir="run_logs"
        >>> get_logs_directory_for_cli()
        Path('/Users/padak/github/osiris/testing_env/run_logs')

        >>> # With osiris.yaml: filesystem.base_path="~/data", run_logs_dir="logs"
        >>> get_logs_directory_for_cli()
        Path('/Users/padak/data/logs')
    """
    from osiris.core.fs_config import load_osiris_config  # noqa: PLC0415  # Lazy import for CLI performance

    try:
        # Load filesystem contract configuration
        fs_config, _, _ = load_osiris_config()

        # Resolve run_logs_dir against base_path
        logs_dir = fs_config.resolve_path(fs_config.run_logs_dir)

        return logs_dir

    except Exception:
        # Fallback to default if config loading fails
        # This ensures commands don't crash if osiris.yaml is missing or invalid
        return Path("run_logs")
