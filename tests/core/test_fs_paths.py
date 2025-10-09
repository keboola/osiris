"""Tests for filesystem paths and token rendering (ADR-0028)."""

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from osiris.core.fs_config import FilesystemConfig, IdsConfig, NamingConfig
from osiris.core.fs_paths import (
    FilesystemContract,
    TokenRenderer,
    compute_manifest_hash,
    get_current_user,
    get_git_branch,
    normalize_tags,
    slugify_token,
)


class TestTokenRenderer:
    """Test token rendering."""

    def test_render_basic_tokens(self):
        """Test rendering with basic tokens."""
        renderer = TokenRenderer()
        template = "{pipeline_slug}/{run_id}"
        tokens = {"pipeline_slug": "orders_etl", "run_id": "run-000123"}

        result = renderer.render(template, tokens)
        # Slugification converts underscores to hyphens
        assert result == "orders-etl/run-000123"

    def test_render_missing_tokens(self):
        """Test rendering with missing tokens."""
        renderer = TokenRenderer()
        template = "{pipeline_slug}/{profile}/{run_id}"
        tokens = {"pipeline_slug": "orders_etl", "run_id": "run-000123"}

        result = renderer.render(template, tokens)
        # Profile is missing, should be empty; slugification converts underscores
        assert result == "orders-etl/run-000123"

    def test_render_with_unsafe_chars(self):
        """Test rendering with unsafe characters."""
        renderer = TokenRenderer()
        template = "{pipeline_slug}"
        tokens = {"pipeline_slug": "My Pipeline!@#$"}

        result = renderer.render(template, tokens)
        # Should be slugified
        assert result == "my-pipeline"

    def test_collapse_separators(self):
        """Test collapsing duplicate separators."""
        renderer = TokenRenderer()
        template = "{pipeline_slug}//{profile}///{run_id}"
        tokens = {"pipeline_slug": "orders", "profile": "", "run_id": "123"}

        result = renderer.render(template, tokens)
        # Should collapse multiple slashes
        assert result == "orders/123"


class TestSlugifyToken:
    """Test token slugification."""

    def test_slugify_basic(self):
        """Test basic slugification."""
        assert slugify_token("hello world") == "hello-world"
        assert slugify_token("HELLO_WORLD") == "hello-world"

    def test_slugify_special_chars(self):
        """Test slugification with special characters."""
        assert slugify_token("hello@world!") == "helloworld"
        assert slugify_token("test.pipeline") == "testpipeline"

    def test_slugify_empty(self):
        """Test slugification of empty string."""
        assert slugify_token("") == ""

    def test_slugify_collapse_separators(self):
        """Test collapsing separators."""
        assert slugify_token("hello---world") == "hello-world"
        assert slugify_token("test___case") == "test-case"


class TestComputeManifestHash:
    """Test manifest hash computation."""

    def test_compute_hash_deterministic(self):
        """Test hash is deterministic."""
        manifest = {"version": "1.0", "steps": [{"id": "step1"}]}

        hash1 = compute_manifest_hash(manifest)
        hash2 = compute_manifest_hash(manifest)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest

    def test_compute_hash_with_profile(self):
        """Test hash includes profile."""
        manifest = {"version": "1.0"}

        hash_no_profile = compute_manifest_hash(manifest)
        hash_with_profile = compute_manifest_hash(manifest, profile="prod")

        assert hash_no_profile != hash_with_profile

    def test_compute_hash_order_independent(self):
        """Test hash is order-independent for dict keys."""
        manifest1 = {"b": 2, "a": 1}
        manifest2 = {"a": 1, "b": 2}

        hash1 = compute_manifest_hash(manifest1)
        hash2 = compute_manifest_hash(manifest2)

        assert hash1 == hash2


class TestNormalizeTags:
    """Test tag normalization."""

    def test_normalize_empty(self):
        """Test empty tags."""
        assert normalize_tags([]) == ""

    def test_normalize_single(self):
        """Test single tag."""
        assert normalize_tags(["billing"]) == "billing"

    def test_normalize_multiple(self):
        """Test multiple tags."""
        result = normalize_tags(["billing", "ml", "critical"])
        assert result == "billing+ml+critical"

    def test_normalize_with_special_chars(self):
        """Test tags with special characters."""
        result = normalize_tags(["Billing Dept", "ML-Model"])
        assert result == "billing-dept+ml-model"


class TestFilesystemContract:
    """Test filesystem contract."""

    def test_manifest_paths_no_profile(self):
        """Test manifest paths without profile."""
        fs_config = FilesystemConfig(profiles={"enabled": False})
        ids_config = IdsConfig()
        contract = FilesystemContract(fs_config, ids_config)

        paths = contract.manifest_paths(
            pipeline_slug="orders_etl",
            manifest_hash="abc123def456",  # pragma: allowlist secret
            manifest_short="abc123d",
            profile=None,
        )

        assert "base" in paths
        assert "manifest" in paths
        # Should not include profile segment; slugification converts underscores
        assert "pipelines/orders-etl" in str(paths["base"])

    def test_manifest_paths_with_profile(self):
        """Test manifest paths with profile."""
        fs_config = FilesystemConfig()
        ids_config = IdsConfig()
        contract = FilesystemContract(fs_config, ids_config)

        paths = contract.manifest_paths(
            pipeline_slug="orders_etl",
            manifest_hash="abc123def456",
            manifest_short="abc123d",
            profile="prod",
        )

        # Should include profile segment; slugification converts underscores
        assert "pipelines/prod/orders-etl" in str(paths["base"])

    def test_run_log_paths(self):
        """Test run log paths."""
        fs_config = FilesystemConfig()
        ids_config = IdsConfig()
        contract = FilesystemContract(fs_config, ids_config)

        run_ts = datetime(2025, 10, 7, 14, 22, 19, tzinfo=UTC)

        paths = contract.run_log_paths(
            pipeline_slug="orders_etl",
            run_id="run-000123",
            run_ts=run_ts,
            manifest_short="abc123d",
            profile="dev",
        )

        assert "base" in paths
        assert "events" in paths
        assert "metrics" in paths
        # Should include timestamp (slugified to lowercase)
        assert "20251007t142219z" in str(paths["base"])

    def test_aiop_paths(self):
        """Test AIOP paths."""
        fs_config = FilesystemConfig()
        ids_config = IdsConfig()
        contract = FilesystemContract(fs_config, ids_config)

        paths = contract.aiop_paths(
            pipeline_slug="orders_etl",
            manifest_hash="abc123def456",
            manifest_short="abc123d",
            run_id="run-000123",
            profile="dev",
        )

        assert "base" in paths
        assert "summary" in paths
        assert "run_card" in paths
        assert "annex" in paths
        # Should include run_id in path
        assert "run-000123" in str(paths["base"])

    def test_index_paths(self):
        """Test index paths."""
        fs_config = FilesystemConfig()
        ids_config = IdsConfig()
        contract = FilesystemContract(fs_config, ids_config)

        paths = contract.index_paths()

        assert "runs" in paths
        assert "by_pipeline" in paths
        assert "latest" in paths
        assert "counters" in paths
        # Should use index_dir
        assert ".osiris/index" in str(paths["base"])

    def test_ensure_dir(self):
        """Test directory creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fs_config = FilesystemConfig(base_path=tmpdir)
            ids_config = IdsConfig()
            contract = FilesystemContract(fs_config, ids_config)

            test_path = Path(tmpdir) / "test" / "nested" / "dir"
            result = contract.ensure_dir(test_path)

            assert result.exists()
            assert result.is_dir()
            assert result == test_path

    def test_format_timestamp_iso_basic(self):
        """Test timestamp formatting in ISO basic format."""
        fs_config = FilesystemConfig(naming=NamingConfig(run_ts_format="iso_basic_z"))
        ids_config = IdsConfig()
        contract = FilesystemContract(fs_config, ids_config)

        ts = datetime(2025, 10, 7, 14, 22, 19, tzinfo=UTC)
        result = contract._format_timestamp(ts)

        assert result == "20251007T142219Z"

    def test_format_timestamp_epoch(self):
        """Test timestamp formatting as epoch."""
        fs_config = FilesystemConfig(naming=NamingConfig(run_ts_format="epoch_ms"))
        ids_config = IdsConfig()
        contract = FilesystemContract(fs_config, ids_config)

        ts = datetime(2025, 10, 7, 14, 22, 19, tzinfo=UTC)
        result = contract._format_timestamp(ts)

        assert result.isdigit()
        assert len(result) == 13  # Milliseconds

    def test_format_timestamp_none(self):
        """Test timestamp formatting as none."""
        fs_config = FilesystemConfig(naming=NamingConfig(run_ts_format="none"))
        ids_config = IdsConfig()
        contract = FilesystemContract(fs_config, ids_config)

        ts = datetime(2025, 10, 7, 14, 22, 19, tzinfo=UTC)
        result = contract._format_timestamp(ts)

        assert result == ""


class TestHelpers:
    """Test helper functions."""

    def test_get_current_user(self):
        """Test getting current user."""
        user = get_current_user()
        assert isinstance(user, str)
        # Should return something or empty string
        assert user is not None

    def test_get_git_branch(self):
        """Test getting git branch."""
        branch = get_git_branch()
        assert isinstance(branch, str)
        # May be empty if not in git repo
