"""Unit tests for connection parsing utilities."""

import pytest

from osiris.core.config import parse_connection_ref


class TestParseConnectionRef:
    """Test parse_connection_ref function."""

    def test_parse_valid_reference(self):
        """Test parsing valid @family.alias format."""
        family, alias = parse_connection_ref("@mysql.primary")
        assert family == "mysql"
        assert alias == "primary"

    def test_parse_with_underscore(self):
        """Test parsing with underscores in alias."""
        family, alias = parse_connection_ref("@supabase.prod_db")
        assert family == "supabase"
        assert alias == "prod_db"

    def test_parse_with_dash(self):
        """Test parsing with dashes in alias."""
        family, alias = parse_connection_ref("@duckdb.local-db")
        assert family == "duckdb"
        assert alias == "local-db"

    def test_parse_without_at_symbol(self):
        """Test parsing string without @ returns None."""
        family, alias = parse_connection_ref("mysql.primary")
        assert family is None
        assert alias is None

    def test_parse_empty_string(self):
        """Test parsing empty string returns None."""
        family, alias = parse_connection_ref("")
        assert family is None
        assert alias is None

    def test_parse_none(self):
        """Test parsing None returns None."""
        family, alias = parse_connection_ref(None)
        assert family is None
        assert alias is None

    def test_parse_missing_dot(self):
        """Test error when dot is missing."""
        with pytest.raises(ValueError) as exc_info:
            parse_connection_ref("@mysql")
        assert "Invalid connection reference format" in str(exc_info.value)
        assert "Expected '@family.alias'" in str(exc_info.value)

    def test_parse_empty_family(self):
        """Test error when family is empty."""
        with pytest.raises(ValueError) as exc_info:
            parse_connection_ref("@.alias")
        assert "Family and alias cannot be empty" in str(exc_info.value)

    def test_parse_empty_alias(self):
        """Test error when alias is empty."""
        with pytest.raises(ValueError) as exc_info:
            parse_connection_ref("@mysql.")
        assert "Family and alias cannot be empty" in str(exc_info.value)

    def test_parse_multiple_dots(self):
        """Test parsing with multiple dots (only first dot splits)."""
        family, alias = parse_connection_ref("@mysql.db.prod.primary")
        assert family == "mysql"
        assert alias == "db.prod.primary"  # Everything after first dot

    def test_parse_special_characters(self):
        """Test parsing with numbers and allowed special chars."""
        family, alias = parse_connection_ref("@mysql2.db_prod-01")
        assert family == "mysql2"
        assert alias == "db_prod-01"
