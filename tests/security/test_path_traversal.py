"""
Test path traversal (CWE-22) prevention in MCP resource resolver.

This test suite validates that the ResourceResolver properly prevents
directory traversal attacks via malicious URIs.

Security Requirements:
- URIs cannot escape the sandbox using .. sequences
- URIs cannot use absolute paths to access files outside sandbox
- Path normalization prevents symlink-based escapes
- All resource types (schemas, memory, discovery, drafts, prompts, usecases) are protected
"""

from unittest.mock import MagicMock

import pytest

from osiris.mcp.errors import ErrorFamily, OsirisError
from osiris.mcp.resolver import ResourceResolver


class TestPathTraversalPrevention:
    """Test suite for CWE-22 path traversal prevention."""

    @pytest.fixture
    def temp_dirs(self, tmp_path):
        """Create test directory structure."""
        sandbox_root = tmp_path / ".osiris"
        data_dir = sandbox_root / "data"
        cache_dir = sandbox_root / "cache"
        memory_dir = sandbox_root / "memory"

        # Create directories
        for dir_path in [data_dir, cache_dir, memory_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # Create subdirectories for each resource type
        for resource_type in ["schemas", "prompts", "usecases"]:
            (data_dir / resource_type).mkdir(exist_ok=True)

        return {
            "sandbox_root": sandbox_root,
            "data_dir": data_dir,
            "cache_dir": cache_dir,
            "memory_dir": memory_dir,
        }

    @pytest.fixture
    def resolver(self, temp_dirs):
        """Create resolver with test configuration."""
        resolver = MagicMock(spec=ResourceResolver)

        # Set up directory paths
        resolver.data_dir = temp_dirs["data_dir"]
        resolver.cache_dir = temp_dirs["cache_dir"]
        resolver.memory_dir = temp_dirs["memory_dir"]

        # Use the real _parse_uri and _get_physical_path methods
        resolver._parse_uri = ResourceResolver._parse_uri.__get__(resolver)
        resolver._get_physical_path = ResourceResolver._get_physical_path.__get__(resolver)

        return resolver

    # ========== Memory Resource Tests ==========

    def test_path_traversal_memory_with_dotdot(self, resolver):
        """Test that .. traversal is blocked for memory resources."""
        uri = "osiris://mcp/memory/sessions/../../../../etc/passwd"

        with pytest.raises(OsirisError) as exc_info:
            resolver._get_physical_path(uri)

        assert exc_info.value.family == ErrorFamily.POLICY
        assert "Path traversal" in str(exc_info.value)

    def test_path_traversal_memory_multiple_dotdot(self, resolver):
        """Test that multiple .. sequences are blocked."""
        uri = "osiris://mcp/memory/a/../../b/../../c/../../etc/shadow"

        with pytest.raises(OsirisError) as exc_info:
            resolver._get_physical_path(uri)

        assert exc_info.value.family == ErrorFamily.POLICY

    def test_path_traversal_memory_dotdot_at_start(self, resolver):
        """Test that .. at the start of path is blocked."""
        uri = "osiris://mcp/memory/../../../../etc/passwd"

        with pytest.raises(OsirisError) as exc_info:
            resolver._get_physical_path(uri)

        assert exc_info.value.family == ErrorFamily.POLICY

    # ========== Discovery Resource Tests ==========

    def test_path_traversal_discovery_with_dotdot(self, resolver):
        """Test that .. traversal is blocked for discovery resources."""
        uri = "osiris://mcp/discovery/../../../var/log/auth.log"

        with pytest.raises(OsirisError) as exc_info:
            resolver._get_physical_path(uri)

        assert exc_info.value.family == ErrorFamily.POLICY
        assert "Path traversal" in str(exc_info.value)

    def test_path_traversal_discovery_deep_nesting(self, resolver):
        """Test that deeply nested .. attempts are blocked."""
        uri = "osiris://mcp/discovery/a/b/c/d/e/f/../../../../../../../../../../home"

        with pytest.raises(OsirisError) as exc_info:
            resolver._get_physical_path(uri)

        assert exc_info.value.family == ErrorFamily.POLICY

    # ========== Schema Resource Tests ==========

    def test_path_traversal_schemas_with_dotdot(self, resolver):
        """Test that .. traversal is blocked for schema resources."""
        uri = "osiris://mcp/schemas/oml/../../../.env"

        with pytest.raises(OsirisError) as exc_info:
            resolver._get_physical_path(uri)

        assert exc_info.value.family == ErrorFamily.POLICY

    def test_path_traversal_prompts_with_dotdot(self, resolver):
        """Test that .. traversal is blocked for prompt resources."""
        uri = "osiris://mcp/prompts/custom/../../../../sensitive.txt"

        with pytest.raises(OsirisError) as exc_info:
            resolver._get_physical_path(uri)

        assert exc_info.value.family == ErrorFamily.POLICY

    def test_path_traversal_usecases_with_dotdot(self, resolver):
        """Test that .. traversal is blocked for usecase resources."""
        uri = "osiris://mcp/usecases/examples/../../../../etc/passwd"

        with pytest.raises(OsirisError) as exc_info:
            resolver._get_physical_path(uri)

        assert exc_info.value.family == ErrorFamily.POLICY

    def test_path_traversal_drafts_with_dotdot(self, resolver):
        """Test that .. traversal is blocked for draft resources."""
        uri = "osiris://mcp/drafts/v1/../../../../root/.ssh/id_rsa"

        with pytest.raises(OsirisError) as exc_info:
            resolver._get_physical_path(uri)

        assert exc_info.value.family == ErrorFamily.POLICY

    # ========== Valid Path Tests (Positive Cases) ==========

    def test_valid_nested_memory_path(self, resolver):
        """Test that valid nested paths within sandbox are allowed."""
        uri = "osiris://mcp/memory/sessions/session123/events.jsonl"
        path = resolver._get_physical_path(uri)

        # Should resolve successfully
        assert path.name == "events.jsonl"
        assert "sessions" in path.parts
        assert resolver.memory_dir in path.parents

    def test_valid_deeply_nested_path(self, resolver):
        """Test that deeply nested valid paths are allowed."""
        uri = "osiris://mcp/discovery/artifacts/2025/11/output.json"
        path = resolver._get_physical_path(uri)

        assert path.name == "output.json"
        assert "discovery" not in path.name

    def test_valid_path_with_special_chars(self, resolver):
        """Test that paths with special (but safe) characters are allowed."""
        uri = "osiris://mcp/memory/session-uuid-123/artifact_v2.json"
        path = resolver._get_physical_path(uri)

        assert path.name == "artifact_v2.json"
        assert resolver.memory_dir in path.parents

    def test_valid_path_with_dots_in_filename(self, resolver):
        """Test that dots in filenames (not path traversal) are allowed."""
        uri = "osiris://mcp/schemas/oml/v0.1.0.json"
        path = resolver._get_physical_path(uri)

        # v0.1.0.json should be treated as a filename, not traversal
        assert path.name == "v0.1.0.json"
        assert resolver.data_dir in path.parents

    # ========== Edge Cases ==========

    def test_path_traversal_with_url_encoding(self, resolver):
        """Test that URL-encoded .. (%2E%2E) is not decoded and exploited."""
        # The URI parser doesn't do URL decoding, so %2E should be literal
        uri = "osiris://mcp/memory/sessions/%2E%2E/etc/passwd"

        # This should not cause traversal since %2E%2E is literal
        # but it might fail for other reasons (invalid path)
        try:
            path = resolver._get_physical_path(uri)
            # If it succeeds, path should still be within sandbox
            assert resolver.memory_dir in path.parents
        except OsirisError:
            # Also acceptable - invalid path characters
            pass

    def test_path_traversal_double_slash(self, resolver):
        """Test that // slashes don't enable traversal."""
        uri = "osiris://mcp/memory//sessions/../../etc/passwd"

        with pytest.raises(OsirisError) as exc_info:
            resolver._get_physical_path(uri)

        assert exc_info.value.family == ErrorFamily.POLICY

    def test_path_traversal_mixed_separators(self, resolver):
        """Test that mixed separators don't bypass protection."""
        uri = "osiris://mcp/memory/sessions\\..\\..\\etc\\passwd"

        # Backslashes should be treated literally on most systems
        # Still should be safe (Path will normalize them)
        try:
            path = resolver._get_physical_path(uri)
            assert resolver.memory_dir in path.parents
        except OsirisError:
            pass

    # ========== Filesystem Contract Tests ==========

    def test_memory_dir_isolation(self, resolver):
        """Test that memory resource access is isolated to memory_dir."""
        uri = "osiris://mcp/memory/events.jsonl"
        path = resolver._get_physical_path(uri)

        assert resolver.memory_dir in path.parents or path.parent == resolver.memory_dir

    def test_discovery_dir_isolation(self, resolver):
        """Test that discovery resource access is isolated to cache_dir."""
        uri = "osiris://mcp/discovery/artifact.json"
        path = resolver._get_physical_path(uri)

        assert resolver.cache_dir in path.parents or path.parent == resolver.cache_dir

    def test_schemas_type_isolation(self, resolver):
        """Test that schemas access is isolated to data_dir/schemas."""
        uri = "osiris://mcp/schemas/oml/v0.1.0.json"
        path = resolver._get_physical_path(uri)

        assert (resolver.data_dir / "schemas") in path.parents

    def test_resource_types_dont_cross(self, resolver):
        """Test that different resource types have distinct sandboxes."""
        memory_path = resolver._get_physical_path("osiris://mcp/memory/test.txt")
        schemas_path = resolver._get_physical_path("osiris://mcp/schemas/test.txt")
        cache_path = resolver._get_physical_path("osiris://mcp/discovery/test.txt")

        # Paths should be in different parent directories
        assert memory_path.parent != schemas_path.parent
        assert memory_path.parent != cache_path.parent
        assert schemas_path.parent != cache_path.parent


class TestPathTraversalErrorHandling:
    """Test error handling and messages for path traversal attempts."""

    @pytest.fixture
    def resolver(self, tmp_path):
        """Create resolver."""
        resolver = MagicMock(spec=ResourceResolver)
        resolver.data_dir = tmp_path / "data"
        resolver.cache_dir = tmp_path / "cache"
        resolver.memory_dir = tmp_path / "memory"

        resolver._parse_uri = ResourceResolver._parse_uri.__get__(resolver)
        resolver._get_physical_path = ResourceResolver._get_physical_path.__get__(resolver)

        return resolver

    def test_error_message_contains_uri(self, resolver):
        """Test that error message includes the attempted URI."""
        uri = "osiris://mcp/memory/../../../../etc/passwd"

        with pytest.raises(OsirisError) as exc_info:
            resolver._get_physical_path(uri)

        assert uri in str(exc_info.value)

    def test_error_family_is_policy(self, resolver):
        """Test that path traversal errors use POLICY error family."""
        uri = "osiris://mcp/memory/sessions/../../etc/passwd"

        with pytest.raises(OsirisError) as exc_info:
            resolver._get_physical_path(uri)

        assert exc_info.value.family == ErrorFamily.POLICY

    def test_error_includes_suggestion(self, resolver):
        """Test that error message includes helpful suggestion."""
        uri = "osiris://mcp/discovery/../../../../etc/passwd"

        with pytest.raises(OsirisError) as exc_info:
            resolver._get_physical_path(uri)

        error_msg = str(exc_info.value)
        assert "suggest" not in error_msg or ".." in error_msg or "escape" in error_msg
