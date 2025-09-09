"""Integration tests for compile and run commands."""

import json
import os

import yaml

from osiris.core.compiler_v0 import CompilerV0
from osiris.core.runner_v0 import RunnerV0


class TestCompileIntegration:
    @classmethod
    def setup_class(cls):
        """Ensure test directory exists."""

        os.makedirs("testing_env/tmp", exist_ok=True)

    def test_compile_simple_pipeline(self, tmp_path):
        """Test compiling a simple linear pipeline."""
        # Create test OML
        oml = {
            "oml_version": "0.1.0",
            "name": "test pipeline",
            "params": {"table": {"default": "test_table"}},
            "steps": [
                {
                    "id": "extract",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {
                        "connection": "@mysql.main",
                        "query": "SELECT * FROM ${params.table}",
                    },
                },
                {
                    "id": "load",
                    "component": "supabase.writer",
                    "mode": "write",
                    "config": {
                        "connection": "@supabase.main",
                        "table": "output_table",
                    },
                },
            ],
        }

        oml_path = tmp_path / "pipeline.yaml"
        with open(oml_path, "w") as f:
            yaml.dump(oml, f)

        # Compile
        compiler = CompilerV0(output_dir=str(tmp_path / "compiled"))
        success, message = compiler.compile(
            oml_path=str(oml_path),
            cli_params={
                "table": "test_table",
            },
        )

        assert success, f"Compilation failed: {message}"

        # Check outputs
        manifest_path = tmp_path / "compiled" / "manifest.yaml"
        assert manifest_path.exists()

        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)

        assert manifest["pipeline"]["id"] == "test_pipeline"
        assert len(manifest["steps"]) == 2
        assert manifest["steps"][0]["id"] == "extract"
        assert manifest["steps"][1]["needs"] == ["extract"]

    def test_compile_with_profiles(self, tmp_path):
        """Test compilation with profiles."""
        oml = {
            "oml_version": "0.1.0",
            "name": "profile test",
            "params": {"env": {"default": "dev"}},
            "profiles": {"prod": {"params": {"env": "production"}}},
            "steps": [
                {
                    "id": "test",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {
                        "connection": "@mysql.main",
                        "query": "SELECT '${params.env}' as env",
                    },
                }
            ],
        }

        oml_path = tmp_path / "pipeline.yaml"
        with open(oml_path, "w") as f:
            yaml.dump(oml, f)

        # Compile with prod profile
        compiler = CompilerV0(output_dir=str(tmp_path / "compiled"))
        success, _ = compiler.compile(oml_path=str(oml_path), profile="prod")

        assert success

        # Check effective config
        config_path = tmp_path / "compiled" / "effective_config.json"
        with open(config_path) as f:
            config = json.load(f)

        assert config["params"]["env"] == "production"
        assert config["profile"] == "prod"

    def test_compile_rejects_secrets(self, tmp_path):
        """Test that inline secrets cause compilation failure."""
        oml = {
            "oml_version": "0.1.0",
            "name": "secret test",
            "steps": [
                {
                    "id": "bad",
                    "uses": "extractors.supabase",
                    "with": {
                        "url": "https://test.supabase.co",
                        "key": "hardcoded_secret_key_123",  # Inline secret
                    },
                }
            ],
        }

        oml_path = tmp_path / "pipeline.yaml"
        with open(oml_path, "w") as f:
            yaml.dump(oml, f)

        compiler = CompilerV0()
        success, message = compiler.compile(oml_path=str(oml_path))

        assert not success
        assert "secret" in message.lower()

    def test_compile_deterministic(self, tmp_path):
        """Test that compilation is deterministic."""
        oml = {
            "oml_version": "0.1.0",
            "name": "determinism test",
            "params": {"value": {"default": "42"}},
            "steps": [
                {
                    "id": "step1",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {
                        "connection": "@mysql.main",
                        "query": "SELECT ${params.value} as value",
                    },
                }
            ],
        }

        oml_path = tmp_path / "pipeline.yaml"
        with open(oml_path, "w") as f:
            yaml.dump(oml, f)

        # Compile twice
        out1 = tmp_path / "compiled1"
        out2 = tmp_path / "compiled2"

        compiler1 = CompilerV0(output_dir=str(out1))
        compiler2 = CompilerV0(output_dir=str(out2))

        success1, _ = compiler1.compile(oml_path=str(oml_path))
        success2, _ = compiler2.compile(oml_path=str(oml_path))

        assert success1 and success2

        # Compare manifests (should be byte-identical except timestamps)
        with open(out1 / "manifest.yaml") as f:
            manifest1 = yaml.safe_load(f)
        with open(out2 / "manifest.yaml") as f:
            manifest2 = yaml.safe_load(f)

        # Remove timestamps
        del manifest1["meta"]["generated_at"]
        del manifest2["meta"]["generated_at"]

        # Fingerprints should match
        assert (
            manifest1["pipeline"]["fingerprints"]["oml_fp"]
            == manifest2["pipeline"]["fingerprints"]["oml_fp"]
        )
        assert (
            manifest1["pipeline"]["fingerprints"]["params_fp"]
            == manifest2["pipeline"]["fingerprints"]["params_fp"]
        )


class TestRunnerIntegration:
    def test_run_linear_pipeline(self, tmp_path):
        """Test running a compiled linear pipeline."""
        # Create a simple manifest
        manifest = {
            "pipeline": {"id": "test_pipeline", "version": "0.1.0", "fingerprints": {}},
            "steps": [
                {
                    "id": "extract",
                    "driver": "supabase.extractor",
                    "cfg_path": str(tmp_path / "cfg" / "extract.json"),
                    "needs": [],
                },
                {
                    "id": "transform",
                    "driver": "duckdb.transform",
                    "cfg_path": str(tmp_path / "cfg" / "transform.json"),
                    "needs": ["extract"],
                },
                {
                    "id": "load",
                    "driver": "mysql.writer",
                    "cfg_path": str(tmp_path / "cfg" / "load.json"),
                    "needs": ["transform"],
                },
            ],
            "meta": {"oml_version": "0.1.0"},
        }

        # Create config files
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()

        configs = {
            "extract": {"table": "test_table"},
            "transform": {"sql": "SELECT * FROM input"},
            "load": {"table": "output_table", "mode": "replace"},
        }

        for step_id, config in configs.items():
            with open(cfg_dir / f"{step_id}.json", "w") as f:
                json.dump(config, f)

        # Write manifest
        manifest_path = tmp_path / "manifest.yaml"
        with open(manifest_path, "w") as f:
            yaml.dump(manifest, f)

        # Create dummy connections file for test
        connections = {
            "version": 1,
            "connections": {
                "supabase": {
                    "default": {
                        "url": "https://test.supabase.co",
                        "key": "test_key",  # pragma: allowlist secret
                    }
                },
                "mysql": {
                    "default": {
                        "host": "localhost",
                        "port": 3306,
                        "database": "test",
                        "user": "test",
                        "password": "test",  # pragma: allowlist secret
                    }
                },
            },
        }
        connections_path = tmp_path / "osiris_connections.yaml"
        with open(connections_path, "w") as f:
            yaml.dump(connections, f)

        # Run with patched cwd for connections
        from unittest.mock import MagicMock, patch

        import pandas as pd

        with patch("osiris.core.config.Path.cwd", return_value=tmp_path):
            runner = RunnerV0(
                manifest_path=str(manifest_path), output_dir=str(tmp_path / "_artifacts")
            )

            # Mock all drivers for this test
            mock_driver = MagicMock()
            mock_driver.run.return_value = {"df": pd.DataFrame({"test": [1, 2, 3]})}

            with patch.object(runner.driver_registry, "get", return_value=mock_driver):
                success = runner.run()
                assert success

        # Check artifacts were created
        artifacts_dir = tmp_path / "_artifacts"
        assert (artifacts_dir / "extract").exists()
        assert (artifacts_dir / "transform").exists()
        assert (artifacts_dir / "load").exists()
