"""
Test suite for ResourceResolver - comprehensive coverage for URI resolution and resource operations.

Tests cover:
- Memory resource resolution (sessions)
- Discovery resource resolution (artifacts)
- OML resource resolution (drafts)
- Resource listing
- Error handling
- Edge cases
"""

import json

from mcp import types
import pytest

from osiris.mcp.config import MCPConfig, MCPFilesystemConfig
from osiris.mcp.errors import ErrorFamily, OsirisError
from osiris.mcp.resolver import ResourceResolver


class TestResourceResolverInitialization:
    """Test resolver initialization and configuration."""

    def test_resolver_init_with_config(self, tmp_path):
        """Test resolver initialization with explicit config."""
        fs_config = MCPFilesystemConfig()
        fs_config.base_path = tmp_path
        fs_config.mcp_logs_dir = tmp_path / ".osiris" / "mcp" / "logs"
        config = MCPConfig(fs_config=fs_config)

        resolver = ResourceResolver(config)

        assert resolver.cache_dir == config.cache_dir
        assert resolver.memory_dir == config.memory_dir
        assert resolver.data_dir.exists()

    def test_resolver_init_without_config(self):
        """Test resolver initialization with default config."""
        resolver = ResourceResolver()

        assert resolver.cache_dir is not None
        assert resolver.memory_dir is not None
        assert resolver.data_dir is not None

    def test_resolver_creates_directories(self, tmp_path):
        """Test resolver creates necessary directories on init."""
        fs_config = MCPFilesystemConfig()
        fs_config.base_path = tmp_path
        fs_config.mcp_logs_dir = tmp_path / ".osiris" / "mcp" / "logs"
        config = MCPConfig(fs_config=fs_config)

        resolver = ResourceResolver(config)

        assert resolver.data_dir.exists()
        assert resolver.cache_dir.exists()
        assert resolver.memory_dir.exists()


class TestMemoryResourceResolution:
    """Test memory resource resolution (sessions)."""

    @pytest.fixture
    def resolver(self, tmp_path):
        """Create resolver with test config."""
        fs_config = MCPFilesystemConfig()
        fs_config.base_path = tmp_path
        fs_config.mcp_logs_dir = tmp_path / ".osiris" / "mcp" / "logs"
        config = MCPConfig(fs_config=fs_config)
        return ResourceResolver(config)

    @pytest.mark.asyncio
    async def test_resolve_memory_session_uri(self, resolver, tmp_path):
        """Test resolving valid memory session URI."""
        # Create test session file
        # memory_dir is already set to tmp_path / ".osiris" / "mcp" / "logs" / "memory"
        # URI osiris://mcp/memory/sessions/chat.jsonl -> relative_path = sessions/chat.jsonl
        # Physical path = memory_dir / sessions / chat.jsonl
        session_dir = resolver.memory_dir / "sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        session_file = session_dir / "chat_20251016_143022.jsonl"
        session_file.write_text('{"event": "test"}\n')

        uri = "osiris://mcp/memory/sessions/chat_20251016_143022.jsonl"
        result = await resolver.read_resource(uri)

        assert len(result.contents) == 1
        assert result.contents[0].text is not None
        assert '{"event": "test"}' in result.contents[0].text

    @pytest.mark.asyncio
    async def test_resolve_memory_session_not_found(self, resolver):
        """Test resolving non-existent memory session URI."""
        uri = "osiris://mcp/memory/sessions/nonexistent_session.jsonl"

        with pytest.raises(OsirisError) as exc_info:
            await resolver.read_resource(uri)

        assert exc_info.value.family == ErrorFamily.SEMANTIC
        assert "Resource not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_resolve_memory_invalid_format(self, resolver):
        """Test resolving memory URI with invalid format."""
        uri = "osiris://mcp/memory/invalid"

        with pytest.raises(OsirisError):
            await resolver.read_resource(uri)

    @pytest.mark.asyncio
    async def test_write_memory_session(self, resolver, tmp_path):
        """Test writing to memory session resource."""
        uri = "osiris://mcp/memory/sessions/new_session.jsonl"
        content = '{"event": "session_start", "timestamp": "2025-10-16T14:30:00Z"}\n'

        result = await resolver.write_resource(uri, content)

        assert result is True

        # Verify file was written
        session_file = resolver.memory_dir / "sessions" / "new_session.jsonl"
        assert session_file.exists()
        assert session_file.read_text() == content

    @pytest.mark.asyncio
    async def test_memory_session_complex_content(self, resolver, tmp_path):
        """Test memory session with complex JSONL content."""
        session_dir = resolver.memory_dir / "sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        session_file = session_dir / "complex_session.jsonl"

        content = (
            '{"event": "discover", "target": "@mysql.prod", "timestamp": "2025-10-16T14:30:00Z"}\n'
            '{"event": "validate", "target": "pipeline.yaml", "errors": 0}\n'
            '{"event": "execute", "target": "pipeline.yaml", "status": "success"}\n'
        )
        session_file.write_text(content)

        uri = "osiris://mcp/memory/sessions/complex_session.jsonl"
        result = await resolver.read_resource(uri)

        assert len(result.contents) == 1
        assert result.contents[0].text is not None
        assert "discover" in result.contents[0].text
        assert "validate" in result.contents[0].text
        assert "execute" in result.contents[0].text

    def test_memory_uri_validation(self, resolver):
        """Test memory URI validation."""
        valid_uri = "osiris://mcp/memory/sessions/test.jsonl"
        invalid_uri = "https://example.com/resource"

        assert resolver.validate_uri(valid_uri) is True
        assert resolver.validate_uri(invalid_uri) is False


class TestDiscoveryResourceResolution:
    """Test discovery resource resolution (artifacts)."""

    @pytest.fixture
    def resolver(self, tmp_path):
        """Create resolver with test config."""
        fs_config = MCPFilesystemConfig()
        fs_config.base_path = tmp_path
        fs_config.mcp_logs_dir = tmp_path / ".osiris" / "mcp" / "logs"
        config = MCPConfig(fs_config=fs_config)
        return ResourceResolver(config)

    @pytest.mark.asyncio
    async def test_resolve_discovery_overview(self, resolver, tmp_path):
        """Test resolving discovery overview artifact."""
        # Create discovery artifact
        # URI osiris://mcp/discovery/disc_a1b2c3d4/overview.json -> relative_path = disc_a1b2c3d4/overview.json
        # Physical path = cache_dir / disc_a1b2c3d4 / overview.json
        disc_dir = resolver.cache_dir / "disc_a1b2c3d4"
        disc_dir.mkdir(parents=True, exist_ok=True)
        overview_file = disc_dir / "overview.json"
        overview_data = {
            "discovery_id": "disc_a1b2c3d4",
            "timestamp": "2025-10-16T14:30:00Z",
            "database": "test_db",
            "tables_count": 5,
        }
        overview_file.write_text(json.dumps(overview_data, indent=2))

        uri = "osiris://mcp/discovery/disc_a1b2c3d4/overview.json"
        result = await resolver.read_resource(uri)

        assert len(result.contents) == 1
        assert result.contents[0].text is not None
        content = json.loads(result.contents[0].text)
        assert content["discovery_id"] == "disc_a1b2c3d4"
        assert content["tables_count"] == 5

    @pytest.mark.asyncio
    async def test_resolve_discovery_tables(self, resolver, tmp_path):
        """Test resolving discovery tables artifact."""
        disc_dir = resolver.cache_dir / "disc_xyz789"
        disc_dir.mkdir(parents=True, exist_ok=True)
        tables_file = disc_dir / "tables.json"
        tables_data = {
            "discovery_id": "disc_xyz789",
            "tables": [
                {"name": "users", "row_count": 1000},
                {"name": "orders", "row_count": 5000},
            ],
        }
        tables_file.write_text(json.dumps(tables_data, indent=2))

        uri = "osiris://mcp/discovery/disc_xyz789/tables.json"
        result = await resolver.read_resource(uri)

        assert len(result.contents) == 1
        content = json.loads(result.contents[0].text)
        assert len(content["tables"]) == 2
        assert content["tables"][0]["name"] == "users"

    @pytest.mark.asyncio
    async def test_resolve_discovery_samples(self, resolver, tmp_path):
        """Test resolving discovery samples artifact."""
        disc_dir = resolver.cache_dir / "disc_samples"
        disc_dir.mkdir(parents=True, exist_ok=True)
        samples_file = disc_dir / "samples.json"
        samples_data = {
            "discovery_id": "disc_samples",
            "samples": {
                "users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
                "orders": [{"id": 100, "user_id": 1, "total": 99.99}],
            },
        }
        samples_file.write_text(json.dumps(samples_data, indent=2))

        uri = "osiris://mcp/discovery/disc_samples/samples.json"
        result = await resolver.read_resource(uri)

        assert len(result.contents) == 1
        content = json.loads(result.contents[0].text)
        assert "users" in content["samples"]
        assert len(content["samples"]["users"]) == 2

    @pytest.mark.asyncio
    async def test_discovery_artifact_not_found_generates_placeholder(self, resolver):
        """Test that non-existent discovery artifact generates placeholder."""
        uri = "osiris://mcp/discovery/disc_nonexistent/overview.json"
        result = await resolver.read_resource(uri)

        assert len(result.contents) == 1
        content = json.loads(result.contents[0].text)
        assert content["discovery_id"] == "disc_nonexistent"
        assert content["database"] == "unknown"

    @pytest.mark.asyncio
    async def test_discovery_tables_placeholder(self, resolver):
        """Test discovery tables placeholder generation."""
        uri = "osiris://mcp/discovery/disc_new/tables.json"
        result = await resolver.read_resource(uri)

        content = json.loads(result.contents[0].text)
        assert content["discovery_id"] == "disc_new"
        assert content["tables"] == []

    @pytest.mark.asyncio
    async def test_discovery_samples_placeholder(self, resolver):
        """Test discovery samples placeholder generation."""
        uri = "osiris://mcp/discovery/disc_new/samples.json"
        result = await resolver.read_resource(uri)

        content = json.loads(result.contents[0].text)
        assert content["discovery_id"] == "disc_new"
        assert content["samples"] == {}

    @pytest.mark.asyncio
    async def test_discovery_unknown_artifact(self, resolver):
        """Test discovery with unknown artifact type."""
        uri = "osiris://mcp/discovery/disc_test/unknown.json"

        with pytest.raises(OsirisError) as exc_info:
            await resolver.read_resource(uri)

        assert exc_info.value.family == ErrorFamily.SEMANTIC
        assert "Unknown discovery artifact" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_discovery_invalid_uri_format(self, resolver):
        """Test discovery URI with invalid format."""
        uri = "osiris://mcp/discovery/incomplete"

        with pytest.raises(OsirisError) as exc_info:
            await resolver.read_resource(uri)

        assert exc_info.value.family == ErrorFamily.SEMANTIC


class TestOMLResourceResolution:
    """Test OML resource resolution (drafts)."""

    @pytest.fixture
    def resolver(self, tmp_path):
        """Create resolver with test config."""
        fs_config = MCPFilesystemConfig()
        fs_config.base_path = tmp_path
        fs_config.mcp_logs_dir = tmp_path / ".osiris" / "mcp" / "logs"
        config = MCPConfig(fs_config=fs_config)
        return ResourceResolver(config)

    @pytest.mark.asyncio
    async def test_resolve_oml_draft(self, resolver, tmp_path):
        """Test resolving valid OML draft."""
        # URI osiris://mcp/drafts/oml/pipeline_v1.yaml -> relative_path = oml/pipeline_v1.yaml
        # Physical path = cache_dir / oml / pipeline_v1.yaml
        drafts_dir = resolver.cache_dir / "oml"
        drafts_dir.mkdir(parents=True, exist_ok=True)
        draft_file = drafts_dir / "pipeline_v1.yaml"
        draft_content = """
version: "0.1.0"
steps:
  - id: extract
    type: mysql.extractor
"""
        draft_file.write_text(draft_content)

        uri = "osiris://mcp/drafts/oml/pipeline_v1.yaml"
        result = await resolver.read_resource(uri)

        assert len(result.contents) == 1
        assert result.contents[0].text is not None
        assert 'version: "0.1.0"' in result.contents[0].text
        assert "mysql.extractor" in result.contents[0].text

    @pytest.mark.asyncio
    async def test_resolve_oml_draft_not_found(self, resolver):
        """Test resolving non-existent OML draft."""
        uri = "osiris://mcp/drafts/oml/nonexistent.yaml"

        with pytest.raises(OsirisError) as exc_info:
            await resolver.read_resource(uri)

        assert exc_info.value.family == ErrorFamily.SEMANTIC
        assert "Resource not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_write_oml_draft(self, resolver, tmp_path):
        """Test writing OML draft resource."""
        uri = "osiris://mcp/drafts/oml/new_pipeline.yaml"
        content = """
version: "0.1.0"
steps:
  - id: extract
    type: supabase.extractor
    config:
      query: "SELECT * FROM users"
"""

        result = await resolver.write_resource(uri, content)

        assert result is True

        # Verify file was written
        draft_file = resolver.cache_dir / "oml" / "new_pipeline.yaml"
        assert draft_file.exists()
        assert "supabase.extractor" in draft_file.read_text()

    @pytest.mark.asyncio
    async def test_oml_draft_complex_pipeline(self, resolver, tmp_path):
        """Test OML draft with complex multi-step pipeline."""
        drafts_dir = resolver.cache_dir / "oml"
        drafts_dir.mkdir(parents=True, exist_ok=True)
        draft_file = drafts_dir / "complex_pipeline.yaml"
        draft_content = """
version: "0.1.0"
steps:
  - id: extract
    type: mysql.extractor
    config:
      query: "SELECT * FROM orders WHERE created_at > '2024-01-01'"
  - id: transform
    type: duckdb.processor
    config:
      query: "SELECT user_id, SUM(total) as revenue FROM extract GROUP BY user_id"
  - id: load
    type: supabase.writer
    config:
      table: "user_revenue"
"""
        draft_file.write_text(draft_content)

        uri = "osiris://mcp/drafts/oml/complex_pipeline.yaml"
        result = await resolver.read_resource(uri)

        assert len(result.contents) == 1
        content = result.contents[0].text
        assert "mysql.extractor" in content
        assert "duckdb.processor" in content
        assert "supabase.writer" in content

    def test_oml_uri_validation(self, resolver):
        """Test OML URI validation."""
        valid_uri = "osiris://mcp/drafts/oml/test.yaml"
        invalid_uri = "osiris://invalid/path"

        assert resolver.validate_uri(valid_uri) is True
        assert resolver.validate_uri(invalid_uri) is False


class TestResourceListing:
    """Test resource listing functionality."""

    @pytest.fixture
    def resolver(self, tmp_path):
        """Create resolver with test config."""
        fs_config = MCPFilesystemConfig()
        fs_config.base_path = tmp_path
        fs_config.mcp_logs_dir = tmp_path / ".osiris" / "mcp" / "logs"
        config = MCPConfig(fs_config=fs_config)
        return ResourceResolver(config)

    @pytest.mark.asyncio
    async def test_list_resources_returns_templates(self, resolver):
        """Test list_resources returns resource templates."""
        resources = await resolver.list_resources()

        assert len(resources) > 0
        assert all(isinstance(r, types.Resource) for r in resources)

        # Check for expected resource types
        uris = [str(r.uri) for r in resources]
        assert any("schemas/oml" in uri for uri in uris)
        assert any("prompts" in uri for uri in uris)
        assert any("usecases" in uri for uri in uris)

    @pytest.mark.asyncio
    async def test_list_resources_schema_metadata(self, resolver):
        """Test schema resource has correct metadata."""
        resources = await resolver.list_resources()

        schema_resources = [r for r in resources if "schemas" in str(r.uri)]
        assert len(schema_resources) > 0

        schema = schema_resources[0]
        assert schema.name is not None
        assert schema.description is not None
        assert schema.mimeType == "application/json"

    @pytest.mark.asyncio
    async def test_list_resources_prompt_metadata(self, resolver):
        """Test prompt resource has correct metadata."""
        resources = await resolver.list_resources()

        prompt_resources = [r for r in resources if "prompts" in str(r.uri)]
        assert len(prompt_resources) > 0

        prompt = prompt_resources[0]
        assert prompt.name is not None
        assert prompt.description is not None
        assert prompt.mimeType == "text/markdown"

    @pytest.mark.asyncio
    async def test_list_resources_usecase_metadata(self, resolver):
        """Test usecase resource has correct metadata."""
        resources = await resolver.list_resources()

        usecase_resources = [r for r in resources if "usecases" in str(r.uri)]
        assert len(usecase_resources) > 0

        usecase = usecase_resources[0]
        assert usecase.name is not None
        assert usecase.description is not None
        assert usecase.mimeType == "application/x-yaml"

    @pytest.mark.asyncio
    async def test_list_resources_empty_runtime_dirs(self, resolver):
        """Test list_resources with empty runtime directories."""
        resources = await resolver.list_resources()

        # Should still return static resources even if runtime dirs are empty
        assert len(resources) > 0


class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.fixture
    def resolver(self, tmp_path):
        """Create resolver with test config."""
        fs_config = MCPFilesystemConfig()
        fs_config.base_path = tmp_path
        fs_config.mcp_logs_dir = tmp_path / ".osiris" / "mcp" / "logs"
        config = MCPConfig(fs_config=fs_config)
        return ResourceResolver(config)

    @pytest.mark.asyncio
    async def test_invalid_uri_scheme(self, resolver):
        """Test error on invalid URI scheme."""
        with pytest.raises(OsirisError) as exc_info:
            await resolver.read_resource("https://example.com/resource")

        assert exc_info.value.family == ErrorFamily.SEMANTIC
        assert "Invalid URI scheme" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_malformed_uri_format(self, resolver):
        """Test error on malformed URI format."""
        with pytest.raises(OsirisError) as exc_info:
            await resolver.read_resource("osiris://mcp/")

        assert exc_info.value.family == ErrorFamily.SEMANTIC
        assert "Invalid URI format" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_unknown_resource_type(self, resolver):
        """Test error on unknown resource type."""
        with pytest.raises(OsirisError) as exc_info:
            await resolver.read_resource("osiris://mcp/unknown/resource.json")

        assert exc_info.value.family == ErrorFamily.SEMANTIC
        assert "Unknown resource type" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_write_readonly_resource(self, resolver):
        """Test error when writing to read-only resource."""
        uri = "osiris://mcp/schemas/oml/custom.json"

        with pytest.raises(OsirisError) as exc_info:
            await resolver.write_resource(uri, '{"test": true}')

        assert exc_info.value.family == ErrorFamily.POLICY
        assert "read-only" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_read_corrupted_json(self, resolver, tmp_path):
        """Test error when reading corrupted JSON file."""
        # URI osiris://mcp/drafts/oml/corrupted.json -> relative_path = oml/corrupted.json
        cache_dir = resolver.cache_dir / "oml"
        cache_dir.mkdir(parents=True, exist_ok=True)
        corrupted_file = cache_dir / "corrupted.json"
        corrupted_file.write_text("{invalid json")

        uri = "osiris://mcp/drafts/oml/corrupted.json"

        with pytest.raises(OsirisError) as exc_info:
            await resolver.read_resource(uri)

        assert exc_info.value.family == ErrorFamily.SEMANTIC
        assert "Failed to read resource" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_helpful_error_messages(self, resolver):
        """Test error messages include helpful suggestions."""
        with pytest.raises(OsirisError) as exc_info:
            await resolver.read_resource("osiris://mcp/memory/sessions/missing.jsonl")

        error = exc_info.value
        assert error.suggest is not None
        assert "Check the resource URI" in error.suggest or "run discovery" in error.suggest.lower()


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def resolver(self, tmp_path):
        """Create resolver with test config."""
        fs_config = MCPFilesystemConfig()
        fs_config.base_path = tmp_path
        fs_config.mcp_logs_dir = tmp_path / ".osiris" / "mcp" / "logs"
        config = MCPConfig(fs_config=fs_config)
        return ResourceResolver(config)

    @pytest.mark.asyncio
    async def test_very_long_uri_path(self, resolver, tmp_path):
        """Test handling of very long URI paths."""
        # Create deeply nested directory
        # URI osiris://mcp/drafts/oml/level1/level2/level3/deep_resource.yaml
        # -> relative_path = oml/level1/level2/level3/deep_resource.yaml
        deep_dir = resolver.cache_dir / "oml" / "level1" / "level2" / "level3"
        deep_dir.mkdir(parents=True, exist_ok=True)
        deep_file = deep_dir / "deep_resource.yaml"
        deep_file.write_text("test: value")

        uri = "osiris://mcp/drafts/oml/level1/level2/level3/deep_resource.yaml"
        result = await resolver.read_resource(uri)

        assert len(result.contents) == 1
        assert "test: value" in result.contents[0].text

    @pytest.mark.asyncio
    async def test_special_characters_in_filename(self, resolver, tmp_path):
        """Test handling special characters in filenames."""
        cache_dir = resolver.cache_dir / "oml"
        cache_dir.mkdir(parents=True, exist_ok=True)
        special_file = cache_dir / "test-pipeline_v1.2.yaml"
        special_file.write_text("version: 0.1.0")

        uri = "osiris://mcp/drafts/oml/test-pipeline_v1.2.yaml"
        result = await resolver.read_resource(uri)

        assert len(result.contents) == 1
        assert "version: 0.1.0" in result.contents[0].text

    @pytest.mark.asyncio
    async def test_empty_file_content(self, resolver, tmp_path):
        """Test reading empty file."""
        cache_dir = resolver.cache_dir / "oml"
        cache_dir.mkdir(parents=True, exist_ok=True)
        empty_file = cache_dir / "empty.yaml"
        empty_file.write_text("")

        uri = "osiris://mcp/drafts/oml/empty.yaml"
        result = await resolver.read_resource(uri)

        assert len(result.contents) == 1
        assert result.contents[0].text == ""

    @pytest.mark.asyncio
    async def test_large_file_content(self, resolver, tmp_path):
        """Test reading large file content."""
        cache_dir = resolver.cache_dir / "oml"
        cache_dir.mkdir(parents=True, exist_ok=True)
        large_file = cache_dir / "large.yaml"

        # Create ~1MB content
        large_content = "line: test\n" * 100000
        large_file.write_text(large_content)

        uri = "osiris://mcp/drafts/oml/large.yaml"
        result = await resolver.read_resource(uri)

        assert len(result.contents) == 1
        assert len(result.contents[0].text) > 1000000

    @pytest.mark.asyncio
    async def test_write_creates_parent_directories(self, resolver, tmp_path):
        """Test write creates parent directories if missing."""
        uri = "osiris://mcp/memory/sessions/nested/deep/session.jsonl"
        content = '{"event": "test"}\n'

        result = await resolver.write_resource(uri, content)

        assert result is True
        session_file = resolver.memory_dir / "sessions" / "nested" / "deep" / "session.jsonl"
        assert session_file.exists()
        assert session_file.read_text() == content

    @pytest.mark.asyncio
    async def test_concurrent_read_access(self, resolver, tmp_path):
        """Test concurrent read access to same resource."""
        import asyncio

        cache_dir = resolver.cache_dir / "oml"
        cache_dir.mkdir(parents=True, exist_ok=True)
        test_file = cache_dir / "concurrent.yaml"
        test_file.write_text("test: concurrent")

        uri = "osiris://mcp/drafts/oml/concurrent.yaml"

        # Simulate concurrent reads
        results = await asyncio.gather(
            resolver.read_resource(uri),
            resolver.read_resource(uri),
            resolver.read_resource(uri),
        )

        assert len(results) == 3
        assert all(len(r.contents) == 1 for r in results)
        assert all("concurrent" in r.contents[0].text for r in results)

    def test_parse_uri_with_query_params(self, resolver):
        """Test URI parsing ignores query parameters (if any)."""
        # Even though query params aren't officially supported, test graceful handling
        uri = "osiris://mcp/drafts/oml/pipeline.yaml"
        resource_type, relative_path = resolver._parse_uri(uri)

        assert resource_type == "drafts"
        assert str(relative_path) == "oml/pipeline.yaml"

    def test_validate_uri_edge_cases(self, resolver):
        """Test URI validation with edge cases."""
        assert resolver.validate_uri("osiris://mcp/memory/a") is True
        assert resolver.validate_uri("osiris://mcp/") is False
        assert resolver.validate_uri("osiris://") is False
        assert resolver.validate_uri("") is False


class TestURIParsing:
    """Test URI parsing and validation."""

    @pytest.fixture
    def resolver(self, tmp_path):
        """Create resolver with test config."""
        fs_config = MCPFilesystemConfig()
        fs_config.base_path = tmp_path
        fs_config.mcp_logs_dir = tmp_path / ".osiris" / "mcp" / "logs"
        config = MCPConfig(fs_config=fs_config)
        return ResourceResolver(config)

    def test_parse_memory_uri(self, resolver):
        """Test parsing memory URI."""
        uri = "osiris://mcp/memory/sessions/chat_123.jsonl"
        resource_type, relative_path = resolver._parse_uri(uri)

        assert resource_type == "memory"
        assert str(relative_path) == "sessions/chat_123.jsonl"

    def test_parse_discovery_uri(self, resolver):
        """Test parsing discovery URI."""
        uri = "osiris://mcp/discovery/disc_abc/overview.json"
        resource_type, relative_path = resolver._parse_uri(uri)

        assert resource_type == "discovery"
        assert str(relative_path) == "disc_abc/overview.json"

    def test_parse_drafts_uri(self, resolver):
        """Test parsing drafts URI."""
        uri = "osiris://mcp/drafts/oml/pipeline.yaml"
        resource_type, relative_path = resolver._parse_uri(uri)

        assert resource_type == "drafts"
        assert str(relative_path) == "oml/pipeline.yaml"

    def test_parse_schemas_uri(self, resolver):
        """Test parsing schemas URI."""
        uri = "osiris://mcp/schemas/oml/v0.1.0.json"
        resource_type, relative_path = resolver._parse_uri(uri)

        assert resource_type == "schemas"
        assert str(relative_path) == "oml/v0.1.0.json"

    def test_get_physical_path_memory(self, resolver):
        """Test getting physical path for memory resource."""
        uri = "osiris://mcp/memory/sessions/test.jsonl"
        path = resolver._get_physical_path(uri)

        assert path.parent.name == "sessions"
        assert path.name == "test.jsonl"

    def test_get_physical_path_discovery(self, resolver):
        """Test getting physical path for discovery resource."""
        uri = "osiris://mcp/discovery/disc_123/tables.json"
        path = resolver._get_physical_path(uri)

        assert "disc_123" in str(path)
        assert path.name == "tables.json"

    def test_get_physical_path_schemas(self, resolver):
        """Test getting physical path for schemas resource."""
        uri = "osiris://mcp/schemas/oml/v0.1.0.json"
        path = resolver._get_physical_path(uri)

        assert "schemas" in str(path)
        assert path.name == "v0.1.0.json"


class TestJSONResourceHandling:
    """Test JSON-specific resource handling."""

    @pytest.fixture
    def resolver(self, tmp_path):
        """Create resolver with test config."""
        fs_config = MCPFilesystemConfig()
        fs_config.base_path = tmp_path
        fs_config.mcp_logs_dir = tmp_path / ".osiris" / "mcp" / "logs"
        config = MCPConfig(fs_config=fs_config)
        return ResourceResolver(config)

    @pytest.mark.asyncio
    async def test_json_formatting(self, resolver, tmp_path):
        """Test JSON files are formatted with indentation."""
        cache_dir = resolver.cache_dir / "oml"
        cache_dir.mkdir(parents=True, exist_ok=True)
        json_file = cache_dir / "test.json"
        json_data = {"key": "value", "nested": {"a": 1, "b": 2}}
        json_file.write_text(json.dumps(json_data))

        uri = "osiris://mcp/drafts/oml/test.json"
        result = await resolver.read_resource(uri)

        # Should be formatted with indentation
        assert len(result.contents) == 1
        content = result.contents[0].text
        assert "\n" in content  # Has newlines (formatted)
        assert "  " in content  # Has indentation

    @pytest.mark.asyncio
    async def test_non_json_file_raw_content(self, resolver, tmp_path):
        """Test non-JSON files return raw content."""
        cache_dir = resolver.cache_dir / "oml"
        cache_dir.mkdir(parents=True, exist_ok=True)
        text_file = cache_dir / "test.txt"
        raw_content = "This is raw text\nwith multiple lines\nand no formatting"
        text_file.write_text(raw_content)

        uri = "osiris://mcp/drafts/oml/test.txt"
        result = await resolver.read_resource(uri)

        assert len(result.contents) == 1
        assert result.contents[0].text == raw_content
