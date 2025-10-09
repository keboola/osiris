"""Unit tests for the minimal compiler."""

import yaml


class TestCompilerV0:
    def test_extract_defaults(self, compiler_instance):
        """Test extracting default values from OML."""
        compiler = compiler_instance

        oml = {
            "params": {
                "simple": "value1",
                "with_spec": {"type": "string", "default": "value2"},
                "no_default": {"type": "int"},
            }
        }

        defaults = compiler._extract_defaults(oml)

        assert defaults["simple"] == "value1"
        assert defaults["with_spec"] == "value2"
        assert "no_default" not in defaults

    def test_validate_no_secrets_pass(self, compiler_instance):
        """Test that non-secret values pass validation."""
        compiler = compiler_instance

        oml = {
            "steps": [
                {
                    "id": "test",
                    "with": {
                        "url": "${params.url}",  # Parameterized is OK
                        "table": "plain_value",  # Non-secret field
                        "database": "test_db",  # Another non-secret
                    },
                }
            ]
        }

        assert compiler._validate_no_secrets(oml) is True
        assert len(compiler.errors) == 0

    def test_validate_no_secrets_fail(self, compiler_instance):
        """Test that inline secrets are detected."""
        compiler = compiler_instance

        oml = {
            "steps": [
                {
                    "id": "test",
                    "with": {
                        "key": "hardcoded_api_key",  # pragma: allowlist secret
                        "password": "my_password",  # pragma: allowlist secret
                    },
                }
            ]
        }

        assert compiler._validate_no_secrets(oml) is False
        assert len(compiler.errors) > 0
        assert any("key" in err for err in compiler.errors)

    def test_compute_fingerprints(self, compiler_instance):
        """Test fingerprint computation."""
        compiler = compiler_instance
        compiler.resolver.params = {"test": "value"}

        oml = {"oml_version": "0.1.0", "name": "test", "steps": []}

        compiler._compute_fingerprints(oml, "dev")

        assert "oml_fp" in compiler.fingerprints
        assert "registry_fp" in compiler.fingerprints
        assert "compiler_fp" in compiler.fingerprints
        assert "params_fp" in compiler.fingerprints
        assert compiler.fingerprints["profile"] == "dev"

        # All fingerprints should be sha256
        for key, value in compiler.fingerprints.items():
            if key != "profile":
                assert value.startswith("sha256:")

    def test_generate_manifest_structure(self, compiler_instance):
        """Test manifest generation structure."""
        compiler = compiler_instance
        compiler.fingerprints = {
            "oml_fp": "sha256:test1",
            "registry_fp": "sha256:test2",
            "compiler_fp": "sha256:test3",
            "params_fp": "sha256:test4",
            "profile": "test",
        }

        oml = {
            "oml_version": "0.1.0",
            "name": "Test Pipeline",
            "steps": [
                {"id": "step1", "component": "supabase.extractor", "mode": "read"},
                {"id": "step2", "component": "duckdb.transform", "mode": "transform"},
            ],
        }

        manifest = compiler._generate_manifest(oml)

        # Check structure
        assert "pipeline" in manifest
        assert "steps" in manifest
        assert "meta" in manifest

        # Check pipeline metadata
        assert manifest["pipeline"]["id"] == "test_pipeline"
        assert manifest["pipeline"]["version"] == "0.1.0"

        # Check steps
        assert len(manifest["steps"]) == 2
        assert manifest["steps"][0]["id"] == "step1"
        assert manifest["steps"][0]["driver"] == "supabase.extractor"
        assert manifest["steps"][1]["needs"] == ["step1"]

    def test_generate_configs_filters_secrets(self, compiler_instance):
        """Test that per-step configs filter out secrets."""
        compiler = compiler_instance

        oml = {
            "steps": [
                {
                    "id": "test",
                    "with": {
                        "url": "https://example.com",
                        "key": "secret_value",  # pragma: allowlist secret
                        "password": "another_secret",  # pragma: allowlist secret
                        "table": "my_table",  # Should remain
                    },
                }
            ]
        }

        configs = compiler._generate_configs(oml)

        assert "test" in configs
        config = configs["test"]

        # Non-secrets should remain
        assert config.get("table") == "my_table"

        # Secrets should be filtered
        assert "key" not in config
        assert "password" not in config

    def test_full_compilation_flow(self, tmp_path, compiler_instance):
        """Test full compilation flow."""
        # Use the provided compiler instance (already has contract)
        compiler = compiler_instance

        # Create test OML
        oml = {
            "oml_version": "0.1.0",
            "name": "Full Test",
            "params": {"db": {"default": "test_db"}},
            "steps": [
                {
                    "id": "extract",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {"connection": "@mysql.main", "query": "SELECT * FROM ${params.db}"},
                }
            ],
        }

        oml_path = tmp_path / "test.yaml"
        with open(oml_path, "w") as f:
            yaml.dump(oml, f)

        # Compile (compiler already set up with contract)
        success, message = compiler.compile(oml_path=str(oml_path), cli_params={"db": "test_db"})

        assert success, f"Compilation failed: {message}"

        # Check outputs exist in contract's compilation dir
        # The compiler should have created files in .osiris/index/compilations/<manifest_short>-<hash>/
        assert compiler.manifest_hash is not None
        assert compiler.manifest_short is not None
