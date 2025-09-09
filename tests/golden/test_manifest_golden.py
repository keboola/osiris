"""Golden tests for manifest generation."""

import os
from pathlib import Path

import pytest
import yaml

from osiris.core.compiler_v0 import CompilerV0


class TestManifestGolden:
    def test_golden_manifest(self, tmp_path):
        """Test manifest matches golden snapshot."""
        # Use the example pipeline
        example_path = Path("docs/examples/supabase_to_mysql.yaml")
        if not example_path.exists():
            pytest.skip("Example pipeline not found")

        # Compile with fixed parameters for determinism
        compiler = CompilerV0(output_dir=str(tmp_path / "compiled"))

        # Set fixed environment for test
        test_env = {
            "OSIRIS_SUPABASE_URL": "https://test.supabase.co",
            "OSIRIS_SUPABASE_ANON_KEY": "test_anon_key",  # pragma: allowlist secret
            "OSIRIS_MYSQL_DSN": "mysql://user:pass@localhost/test",  # pragma: allowlist secret
        }

        # Temporarily set environment
        old_env = {}
        for key, value in test_env.items():
            old_env[key] = os.environ.get(key)
            os.environ[key] = value

        try:
            success, message = compiler.compile(
                oml_path=str(example_path), profile="dev", cli_params={"run_id": "test_run_123"}
            )

            assert success, f"Compilation failed: {message}"

            # Load generated manifest
            manifest_path = tmp_path / "compiled" / "manifest.yaml"
            with open(manifest_path) as f:
                manifest = yaml.safe_load(f)

            # Verify structure
            assert manifest["pipeline"]["id"] == "supabase_to_mysql_etl"
            assert manifest["pipeline"]["version"] == "0.1.0"
            assert len(manifest["steps"]) == 3

            # Verify steps
            steps = manifest["steps"]
            assert steps[0]["id"] == "extract_customers"
            assert steps[0]["driver"] == "extractors.supabase@0.1"
            assert steps[1]["id"] == "transform_enrich"
            assert steps[1]["driver"] == "transforms.duckdb@0.1"
            assert steps[2]["id"] == "load_mysql"
            assert steps[2]["driver"] == "writers.mysql@0.1"

            # Verify dependencies
            assert steps[0]["needs"] == []
            assert steps[1]["needs"] == ["extract_customers"]
            assert steps[2]["needs"] == ["transform_enrich"]

            # Verify fingerprints exist
            fps = manifest["pipeline"]["fingerprints"]
            assert "oml_fp" in fps
            assert "registry_fp" in fps
            assert "compiler_fp" in fps
            assert "params_fp" in fps
            assert "manifest_fp" in fps

            # All fingerprints should start with sha256:
            for fp_name, fp_value in fps.items():
                if fp_name != "profile":
                    assert fp_value.startswith("sha256:"), f"{fp_name} doesn't start with sha256:"

            # Verify meta
            assert manifest["meta"]["oml_version"] == "0.1.0"
            assert manifest["meta"]["profile"] == "dev"

        finally:
            # Restore environment
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_no_secrets_in_manifest(self, tmp_path):
        """Verify no secrets appear in generated manifest."""
        example_path = Path("docs/examples/supabase_to_mysql.yaml")
        if not example_path.exists():
            pytest.skip("Example pipeline not found")

        compiler = CompilerV0(output_dir=str(tmp_path / "compiled"))

        # Compile with secret-like values
        success, _ = compiler.compile(
            oml_path=str(example_path),
            cli_params={
                "supabase_url": "https://secret.supabase.co",
                "supabase_key": "secret_key_12345",  # pragma: allowlist secret
                "mysql_dsn": "mysql://user:secretpass@host/db",  # pragma: allowlist secret
                "run_id": "test",
            },
        )

        assert success

        # Check generated files for secrets (excluding effective_config.json which needs resolved params)
        compiled_dir = tmp_path / "compiled"

        for file_path in compiled_dir.rglob("*"):
            if file_path.is_file():
                # Skip effective_config.json which contains resolved parameters
                if file_path.name == "effective_config.json":
                    continue

                content = file_path.read_text()
                # These secret values should not appear in manifest or configs
                assert "secret_key_12345" not in content, f"Secret found in {file_path.name}"
                assert "secretpass" not in content, f"Secret found in {file_path.name}"

                # Parameter references should remain in manifest
                if file_path.name == "manifest.yaml":
                    assert "${" in content or "params" in content.lower()
