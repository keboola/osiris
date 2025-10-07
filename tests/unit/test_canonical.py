"""Tests for canonical serialization."""

import json

import pytest

from osiris.core.canonical import canonical_bytes, canonical_json, canonical_yaml


class TestCanonicalJSON:
    def test_deterministic_output(self):
        """Same input produces identical output."""
        data = {"z": 1, "a": 2, "m": {"nested": True}}

        output1 = canonical_json(data)
        output2 = canonical_json(data)

        assert output1 == output2

    def test_key_ordering(self):
        """Keys are sorted alphabetically."""
        data = {"z": 1, "a": 2, "m": 3}
        output = canonical_json(data)

        # Parse back to verify order
        parsed = json.loads(output)
        keys = list(parsed.keys())
        assert keys == ["a", "m", "z"]

    def test_nested_normalization(self):
        """Nested structures are normalized."""
        data = {"outer": {"z": 1, "a": [{"y": 2, "x": 3}]}}

        output = canonical_json(data)
        assert output == '{"outer":{"a":[{"x":3,"y":2}],"z":1}}'

    def test_number_types(self):
        """Numbers are preserved correctly."""
        data = {"int": 42, "float": 3.14, "bool": True, "null": None}
        output = canonical_json(data)

        parsed = json.loads(output)
        assert parsed["int"] == 42
        assert parsed["float"] == 3.14
        assert parsed["bool"] is True
        assert parsed["null"] is None


class TestCanonicalYAML:
    def test_deterministic_output(self):
        """Same input produces identical output."""
        data = {"z": 1, "a": 2, "m": {"nested": True}}

        output1 = canonical_yaml(data)
        output2 = canonical_yaml(data)

        assert output1 == output2

    def test_key_ordering(self):
        """Keys are sorted in YAML output."""
        data = {"z": 1, "a": 2}
        output = canonical_yaml(data)

        # Check order in output
        lines = output.strip().split("\n")
        # Skip --- marker
        content_lines = [line for line in lines if not line.startswith("---") and not line.startswith("...")]
        assert content_lines[0].startswith("a:")
        assert content_lines[1].startswith("z:")

    def test_no_trailing_spaces(self):
        """No trailing spaces in output."""
        data = {"key": "value", "list": [1, 2, 3]}
        output = canonical_yaml(data)

        for line in output.split("\n"):
            assert line == line.rstrip()

    def test_document_markers(self):
        """YAML has explicit start/end markers."""
        data = {"key": "value"}
        output = canonical_yaml(data)

        assert output.startswith("---")
        assert "..." in output


class TestCanonicalBytes:
    def test_utf8_encoding(self):
        """Output is UTF-8 encoded."""
        data = {"key": "value with émoji 🚀"}

        json_bytes = canonical_bytes(data, format="json")
        yaml_bytes = canonical_bytes(data, format="yaml")

        # Should decode as UTF-8
        json_bytes.decode("utf-8")
        yaml_bytes.decode("utf-8")

    def test_format_selection(self):
        """Format parameter selects serialization."""
        data = {"key": "value"}

        json_bytes = canonical_bytes(data, format="json")
        yaml_bytes = canonical_bytes(data, format="yaml")

        assert b"{" in json_bytes  # JSON starts with {
        assert b"---" in yaml_bytes  # YAML has marker

    def test_invalid_format(self):
        """Invalid format raises error."""
        with pytest.raises(ValueError, match="Unknown format"):
            canonical_bytes({}, format="xml")
