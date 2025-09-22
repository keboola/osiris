"""Tests for M1a.2 bootstrap component specifications."""

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator


class TestBootstrapSpecs:
    """Test the four bootstrap component specifications."""

    @pytest.fixture
    def spec_schema(self):
        """Load the component spec schema."""
        schema_path = Path("components/spec.schema.json")
        with open(schema_path) as f:
            return json.load(f)

    @pytest.fixture
    def mysql_extractor_spec(self):
        """Load MySQL extractor spec."""
        spec_path = Path("components/mysql.extractor/spec.yaml")
        with open(spec_path) as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def mysql_writer_spec(self):
        """Load MySQL writer spec."""
        spec_path = Path("components/mysql.writer/spec.yaml")
        with open(spec_path) as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def supabase_extractor_spec(self):
        """Load Supabase extractor spec."""
        spec_path = Path("components/supabase.extractor/spec.yaml")
        with open(spec_path) as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def supabase_writer_spec(self):
        """Load Supabase writer spec."""
        spec_path = Path("components/supabase.writer/spec.yaml")
        with open(spec_path) as f:
            return yaml.safe_load(f)

    def test_mysql_extractor_spec_valid(self, spec_schema, mysql_extractor_spec):
        """Test MySQL extractor spec validates against schema."""
        validator = Draft202012Validator(spec_schema)
        validator.validate(mysql_extractor_spec)  # Should not raise

        # Check required fields
        assert mysql_extractor_spec["name"] == "mysql.extractor"
        assert mysql_extractor_spec["version"] == "1.0.0"
        assert "extract" in mysql_extractor_spec["modes"]
        assert "discover" in mysql_extractor_spec["modes"]
        assert mysql_extractor_spec["capabilities"]["discover"] is True
        assert mysql_extractor_spec["capabilities"]["bulkOperations"] is True

    def test_mysql_writer_spec_valid(self, spec_schema, mysql_writer_spec):
        """Test MySQL writer spec validates against schema."""
        validator = Draft202012Validator(spec_schema)
        validator.validate(mysql_writer_spec)  # Should not raise

        # Check required fields
        assert mysql_writer_spec["name"] == "mysql.writer"
        assert mysql_writer_spec["version"] == "1.0.0"
        assert "write" in mysql_writer_spec["modes"]
        assert "discover" in mysql_writer_spec["modes"]
        assert mysql_writer_spec["capabilities"]["bulkOperations"] is True
        assert mysql_writer_spec["capabilities"]["transactions"] is True
        assert mysql_writer_spec["capabilities"]["discover"] is True

    def test_supabase_extractor_spec_valid(self, spec_schema, supabase_extractor_spec):
        """Test Supabase extractor spec validates against schema."""
        validator = Draft202012Validator(spec_schema)
        validator.validate(supabase_extractor_spec)  # Should not raise

        # Check required fields
        assert supabase_extractor_spec["name"] == "supabase.extractor"
        assert supabase_extractor_spec["version"] == "1.0.0"
        assert "extract" in supabase_extractor_spec["modes"]
        assert "discover" in supabase_extractor_spec["modes"]
        assert supabase_extractor_spec["capabilities"]["discover"] is True

    def test_supabase_writer_spec_valid(self, spec_schema, supabase_writer_spec):
        """Test Supabase writer spec validates against schema."""
        validator = Draft202012Validator(spec_schema)
        validator.validate(supabase_writer_spec)  # Should not raise

        # Check required fields
        assert supabase_writer_spec["name"] == "supabase.writer"
        assert supabase_writer_spec["version"] == "1.0.0"
        assert "write" in supabase_writer_spec["modes"]
        assert "discover" in supabase_writer_spec["modes"]
        assert supabase_writer_spec["capabilities"]["bulkOperations"] is True
        assert supabase_writer_spec["capabilities"]["discover"] is True

    def test_mysql_extractor_examples_valid(self, mysql_extractor_spec):
        """Test MySQL extractor examples validate against configSchema."""
        config_schema = mysql_extractor_spec["configSchema"]
        validator = Draft202012Validator(config_schema)

        for example in mysql_extractor_spec["examples"]:
            config = example["config"]
            validator.validate(config)  # Should not raise

    def test_mysql_writer_examples_valid(self, mysql_writer_spec):
        """Test MySQL writer examples validate against configSchema."""
        config_schema = mysql_writer_spec["configSchema"]
        validator = Draft202012Validator(config_schema)

        for example in mysql_writer_spec["examples"]:
            config = example["config"]
            validator.validate(config)  # Should not raise

    def test_supabase_extractor_examples_valid(self, supabase_extractor_spec):
        """Test Supabase extractor examples validate against configSchema."""
        config_schema = supabase_extractor_spec["configSchema"]
        validator = Draft202012Validator(config_schema)

        for example in supabase_extractor_spec["examples"]:
            config = example["config"]
            validator.validate(config)  # Should not raise

    def test_supabase_writer_examples_valid(self, supabase_writer_spec):
        """Test Supabase writer examples validate against configSchema."""
        config_schema = supabase_writer_spec["configSchema"]
        validator = Draft202012Validator(config_schema)

        for example in supabase_writer_spec["examples"]:
            config = example["config"]
            validator.validate(config)  # Should not raise

    def test_mysql_extractor_secrets_declared(self, mysql_extractor_spec):
        """Test MySQL extractor declares password as secret."""
        assert "/password" in mysql_extractor_spec["secrets"]

    def test_mysql_writer_secrets_declared(self, mysql_writer_spec):
        """Test MySQL writer declares password as secret."""
        assert "/password" in mysql_writer_spec["secrets"]

    def test_supabase_extractor_secrets_declared(self, supabase_extractor_spec):
        """Test Supabase extractor declares key as secret."""
        assert "/key" in supabase_extractor_spec["secrets"]

    def test_supabase_writer_secrets_declared(self, supabase_writer_spec):
        """Test Supabase writer declares key as secret."""
        assert "/key" in supabase_writer_spec["secrets"]

    def test_mysql_writer_upsert_constraint(self, mysql_writer_spec):
        """Test MySQL writer has constraint for upsert mode."""
        constraints = mysql_writer_spec.get("constraints", {})
        required_constraints = constraints.get("required", [])

        # Find upsert constraint
        has_upsert_constraint = False
        for constraint in required_constraints:
            if constraint.get("when", {}).get("mode") == "upsert":
                has_upsert_constraint = True
                assert "upsert_keys" in constraint.get("must", {})
                break

        assert has_upsert_constraint, "MySQL writer should have upsert constraint"

    def test_supabase_writer_upsert_constraint(self, supabase_writer_spec):
        """Test Supabase writer has constraint for upsert mode."""
        constraints = supabase_writer_spec.get("constraints", {})
        required_constraints = constraints.get("required", [])

        # Find upsert constraint
        has_upsert_constraint = False
        for constraint in required_constraints:
            if constraint.get("when", {}).get("write_mode") == "upsert":
                has_upsert_constraint = True
                assert "primary_key" in constraint.get("must", {})
                break

        assert has_upsert_constraint, "Supabase writer should have upsert constraint"

    def test_all_specs_have_llm_hints(
        self,
        mysql_extractor_spec,
        mysql_writer_spec,
        supabase_extractor_spec,
        supabase_writer_spec,
    ):
        """Test all specs have LLM hints for better generation."""
        specs = [
            mysql_extractor_spec,
            mysql_writer_spec,
            supabase_extractor_spec,
            supabase_writer_spec,
        ]

        for spec in specs:
            assert "llmHints" in spec
            llm_hints = spec["llmHints"]
            assert "promptGuidance" in llm_hints
            assert len(llm_hints["promptGuidance"]) <= 500  # Token efficiency
            assert "yamlSnippets" in llm_hints
            assert len(llm_hints["yamlSnippets"]) > 0

    def test_all_specs_have_examples(
        self,
        mysql_extractor_spec,
        mysql_writer_spec,
        supabase_extractor_spec,
        supabase_writer_spec,
    ):
        """Test all specs have at least one example."""
        specs = [
            mysql_extractor_spec,
            mysql_writer_spec,
            supabase_extractor_spec,
            supabase_writer_spec,
        ]

        for spec in specs:
            assert "examples" in spec
            assert len(spec["examples"]) >= 1
            assert len(spec["examples"]) <= 2  # ≤2 examples for token efficiency

    def test_supabase_specs_require_key(self, supabase_extractor_spec, supabase_writer_spec):
        """Test that Supabase specs require 'key' field."""
        specs = [supabase_extractor_spec, supabase_writer_spec]

        for spec in specs:
            schema = spec["configSchema"]
            required = schema.get("required", [])
            assert "key" in required, f"{spec['name']} must require 'key'"
            assert "table" in required, f"{spec['name']} must require 'table'"

    def test_supabase_url_or_project_id_constraint(
        self, supabase_extractor_spec, supabase_writer_spec
    ):
        """Test Supabase specs have url XOR project_id constraint."""
        specs = [supabase_extractor_spec, supabase_writer_spec]

        for spec in specs:
            constraints = spec.get("constraints", {}).get("required", [])
            # Should have at least one constraint for url/project_id
            url_constraint_found = False
            for constraint in constraints:
                when = constraint.get("when", {})
                if "url" in when and when["url"] is None:
                    assert "project_id" in constraint.get("must", {})
                    assert "Either 'url' or 'project_id'" in constraint.get("error", "")
                    url_constraint_found = True
            assert url_constraint_found, f"{spec['name']} must have url/project_id constraint"

    def test_capabilities_snapshot(
        self,
        mysql_extractor_spec,
        mysql_writer_spec,
        supabase_extractor_spec,
        supabase_writer_spec,
    ):
        """Test capabilities match expected values (snapshot test)."""
        # MySQL Extractor capabilities
        assert mysql_extractor_spec["capabilities"] == {
            "discover": True,
            "adHocAnalytics": True,  # execute_query implemented
            "inMemoryMove": False,
            "streaming": False,
            "bulkOperations": True,
            "transactions": False,
            "partitioning": False,
            "customTransforms": False,
        }

        # MySQL Writer capabilities
        assert mysql_writer_spec["capabilities"] == {
            "discover": True,
            "adHocAnalytics": False,
            "inMemoryMove": False,
            "streaming": False,
            "bulkOperations": True,
            "transactions": True,  # uses conn.commit()
            "partitioning": False,
            "customTransforms": False,
        }

        # Supabase Extractor capabilities
        assert supabase_extractor_spec["capabilities"] == {
            "discover": True,
            "adHocAnalytics": False,  # execute_query raises NotImplementedError
            "inMemoryMove": False,
            "streaming": False,
            "bulkOperations": True,
            "transactions": False,
            "partitioning": False,
            "customTransforms": False,
        }

        # Supabase Writer capabilities
        assert supabase_writer_spec["capabilities"] == {
            "discover": True,
            "adHocAnalytics": False,
            "inMemoryMove": False,
            "streaming": False,
            "bulkOperations": True,
            "transactions": False,  # REST API doesn't support transactions
            "partitioning": False,
            "customTransforms": False,
        }

    def test_cli_required_config_rendering(self):
        """Test CLI shows correct required configuration."""
        import io
        from contextlib import redirect_stdout

        from osiris.cli.components_cmd import show_component

        # Capture stdout
        captured = io.StringIO()

        # Test MySQL writer
        with redirect_stdout(captured):
            show_component("mysql.writer", as_json=False)

        output = captured.getvalue()
        assert "Required Configuration:" in output
        assert "• host" in output
        assert "• database" in output
        assert "• user" in output
        assert "• password" in output
        assert "• table" in output

        # Test Supabase writer
        captured = io.StringIO()
        with redirect_stdout(captured):
            show_component("supabase.writer", as_json=False)

        output = captured.getvalue()
        assert "Required Configuration:" in output
        assert "• key" in output
        assert "• table" in output
        assert "Secrets (masked in logs):" in output
