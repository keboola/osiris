"""Unit tests for mode mapping functionality."""

from osiris.core.mode_mapper import ModeMapper


class TestModeMapper:
    """Test mode mapping between OML canonical and component modes."""

    def test_canonical_to_component_mapping(self):
        """Test mapping from OML canonical modes to component modes."""
        assert ModeMapper.to_component_mode("read") == "extract"
        assert ModeMapper.to_component_mode("write") == "write"
        assert ModeMapper.to_component_mode("transform") == "transform"

    def test_unknown_mode_passthrough(self):
        """Test that unknown modes pass through unchanged."""
        assert ModeMapper.to_component_mode("custom") == "custom"

    def test_component_to_canonical_mapping(self):
        """Test reverse mapping from component to canonical modes."""
        assert ModeMapper.to_canonical_mode("extract") == "read"
        assert ModeMapper.to_canonical_mode("write") == "write"
        assert ModeMapper.to_canonical_mode("transform") == "transform"

    def test_discover_mode_not_supported(self):
        """Test that discover mode is not supported in compiled runs."""
        assert ModeMapper.to_canonical_mode("discover") is None

    def test_mode_compatibility_check(self):
        """Test checking if OML mode is compatible with component modes."""
        # Extractor component supports 'extract' mode
        component_modes = ["extract", "discover"]

        # 'read' should map to 'extract' and be compatible
        assert ModeMapper.is_mode_compatible("read", component_modes) is True

        # 'write' should not be compatible
        assert ModeMapper.is_mode_compatible("write", component_modes) is False

        # Writer component supports 'write' mode
        writer_modes = ["write"]
        assert ModeMapper.is_mode_compatible("write", writer_modes) is True
        assert ModeMapper.is_mode_compatible("read", writer_modes) is False

    def test_get_canonical_modes(self):
        """Test getting list of canonical OML modes."""
        canonical = ModeMapper.get_canonical_modes()
        assert "read" in canonical
        assert "write" in canonical
        assert "transform" in canonical
        assert len(canonical) == 3
