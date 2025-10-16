#!/usr/bin/env python3
"""
MCP Server entrypoint for Osiris.

This module provides the main entry point for running the Osiris MCP server
via stdio transport, compatible with Claude Desktop and other MCP clients.

Usage:
    python -m osiris.cli.mcp_entrypoint [--debug]
"""

import asyncio
import logging
import os
import sys
from pathlib import Path


def find_repo_root():
    """
    Find repository root by looking for the 'osiris' package directory.

    Returns:
        Path: Resolved absolute path to repository root
    """
    current = Path(__file__).resolve()

    # Walk up the directory tree looking for a directory containing 'osiris' package
    for parent in current.parents:
        if (parent / "osiris").is_dir():
            return parent.resolve()

    # Fallback to grandparent (2 levels up from this file)
    return Path(__file__).resolve().parents[2]


def setup_environment():
    """
    Setup OSIRIS_HOME and PYTHONPATH before importing osiris modules.

    Resolution order for OSIRIS_HOME:
    1. If env OSIRIS_HOME is set and non-empty: use Path(env["OSIRIS_HOME"]).resolve()
    2. Else: OSIRIS_HOME = (repo_root / "testing_env").resolve()

    Creates OSIRIS_HOME directory if it doesn't exist.
    """
    repo_root = find_repo_root()

    # Add repo root to PYTHONPATH
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    # Resolve OSIRIS_HOME with proper precedence
    osiris_home_env = os.environ.get("OSIRIS_HOME", "").strip()
    if osiris_home_env:
        osiris_home = Path(osiris_home_env).resolve()
    else:
        osiris_home = (repo_root / "testing_env").resolve()

    # Create OSIRIS_HOME if it doesn't exist
    osiris_home.mkdir(parents=True, exist_ok=True)

    # Set environment variable for child processes
    os.environ["OSIRIS_HOME"] = str(osiris_home)

    # Set PYTHONPATH if not already set
    if "PYTHONPATH" not in os.environ:
        os.environ["PYTHONPATH"] = str(repo_root)

    return repo_root, osiris_home


# Setup environment before importing osiris modules
repo_root, osiris_home = setup_environment()

from osiris.mcp.server import OsirisMCPServer


def setup_logging(debug: bool = False):
    """
    Configure logging for the MCP server.

    Args:
        debug: Enable debug logging
    """
    level = logging.DEBUG if debug else logging.INFO

    # Configure root logger
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            # Log to stderr to avoid interfering with stdio protocol
            logging.StreamHandler(sys.stderr)
        ],
    )

    # Suppress noisy libraries unless in debug mode
    if not debug:
        logging.getLogger("asyncio").setLevel(logging.WARNING)
        logging.getLogger("mcp").setLevel(logging.WARNING)


def main():
    """Main entry point for the MCP server."""
    # Parse command line arguments
    debug = "--debug" in sys.argv
    selftest = "--selftest" in sys.argv

    # Setup logging
    setup_logging(debug)

    logger = logging.getLogger(__name__)
    logger.info("Starting Osiris MCP Server v0.5.0")

    # Log environment configuration
    logger.info(f"Repository root: {repo_root}")
    logger.info(f"OSIRIS_HOME: {osiris_home}")
    logger.info(f"PYTHONPATH: {os.environ.get('PYTHONPATH', 'not set')}")
    logger.info(f"Current working directory: {Path.cwd()}")

    if selftest:
        # Run self-test mode
        logger.info("Running MCP server self-test...")
        from osiris.mcp.selftest import run_selftest  # noqa: PLC0415  # Lazy import for CLI performance

        success = asyncio.run(run_selftest())
        sys.exit(0 if success else 1)
    else:
        # Create and run server
        server = OsirisMCPServer(debug=debug)

        try:
            # Run the server
            asyncio.run(server.run())
        except KeyboardInterrupt:
            logger.info("Server interrupted by user")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Server error: {e}", exc_info=True)
            sys.exit(1)


if __name__ == "__main__":
    main()
