"""Unit tests for the minimal compiler."""

import yaml

from osiris.core.compiler_v0 import CompilerV0


class TestCompilerV0:
    def test_extract_defaults(self):
        """Test extracting default values from OML."""
        compiler = CompilerV0()

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

    def test_validate_no_secrets_pass(self):
        """Test that non-secret values pass validation."""
        compiler = CompilerV0()

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

    def test_validate_no_secrets_fail(self):
        """Test that inline secrets are detected."""
        compiler = CompilerV0()

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

    def test_compute_fingerprints(self):
        """Test fingerprint computation."""
        compiler = CompilerV0()
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

    def test_generate_manifest_structure(self):
        """Test manifest generation structure."""
        compiler = CompilerV0()
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
                {"id": "step1", "uses": "extractors.supabase"},
                {"id": "step2", "uses": "transforms.duckdb"},
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
        assert manifest["steps"][0]["driver"] == "extractors.supabase@0.1"
        assert manifest["steps"][1]["needs"] == ["step1"]

    def test_generate_configs_filters_secrets(self):
        """Test that per-step configs filter out secrets."""
        compiler = CompilerV0()

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

    def test_full_compilation_flow(self, tmp_path):
        """Test full compilation flow."""
        # Create test OML
        oml = {
            "oml_version": "0.1.0",
            "name": "Full Test",
            "params": {"db": {"default": "test_db"}},
            "steps": [
                {
                    "id": "extract",
                    "uses": "extractors.supabase",
                    "with": {"url": "${params.url}", "table": "${params.db}"},
                }
            ],
        }

        oml_path = tmp_path / "test.yaml"
        with open(oml_path, "w") as f:
            yaml.dump(oml, f)

        # Compile
        compiler = CompilerV0(output_dir=str(tmp_path / "out"))
        success, message = compiler.compile(
            oml_path=str(oml_path), cli_params={"url": "https://test.com", "key": "test"}
        )

        assert success, f"Compilation failed: {message}"

        # Check outputs exist
        out_dir = tmp_path / "out"
        assert (out_dir / "manifest.yaml").exists()
        assert (out_dir / "meta.json").exists()
        assert (out_dir / "effective_config.json").exists()
        assert (out_dir / "cfg" / "extract.json").exists()
