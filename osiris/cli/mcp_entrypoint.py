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
import sys
from pathlib import Path

# Add parent directory to path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

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
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            # Log to stderr to avoid interfering with stdio protocol
            logging.StreamHandler(sys.stderr)
        ]
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

    if selftest:
        # Run self-test mode
        logger.info("Running MCP server self-test...")
        from osiris.mcp.selftest import run_selftest
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