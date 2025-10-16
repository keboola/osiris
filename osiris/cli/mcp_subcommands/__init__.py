"""
MCP CLI subcommands - thin delegation layer.

This package provides thin wrappers that delegate to existing CLI commands.
NO business logic should be reimplemented here - only schema transformation.
"""

# This module is intentionally minimal
# All MCP commands delegate directly to existing CLI functions
__all__ = []
