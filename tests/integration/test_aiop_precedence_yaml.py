#!/usr/bin/env python3
# Copyright (c) 2025 Osiris Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for AIOP configuration precedence: CLI > ENV > YAML > defaults."""


import yaml


class TestAIOPPrecedence:
    """Test AIOP configuration precedence resolution."""

    def test_case_a_only_defaults(self, tmp_path, monkeypatch):
        """Case A: Only defaults → values match AIOP_DEFAULTS."""
        monkeypatch.chdir(tmp_path)

        from osiris.core.config import AIOP_DEFAULTS, resolve_aiop_config

        # No YAML, no ENV, no CLI
        config, sources = resolve_aiop_config()

        # Check values match defaults
        assert config["timeline_density"] == AIOP_DEFAULTS["timeline_density"]
        assert config["timeline_density"] == "medium"
        assert sources["timeline_density"] == "DEFAULT"

        assert config["max_core_bytes"] == AIOP_DEFAULTS["max_core_bytes"]
        assert config["max_core_bytes"] == 300000
        assert sources["max_core_bytes"] == "DEFAULT"

        assert config["metrics_topk"] == AIOP_DEFAULTS["metrics_topk"]
        assert config["metrics_topk"] == 100
        assert sources["metrics_topk"] == "DEFAULT"

    def test_case_b_yaml_sets_timeline_density(self, tmp_path, monkeypatch):
        """Case B: YAML sets timeline_density: high → effective is high."""
        monkeypatch.chdir(tmp_path)

        # Create YAML with custom timeline_density
        config_yaml = {"version": "2.0", "aiop": {"timeline_density": "high"}}

        with open(tmp_path / "osiris.yaml", "w") as f:
            yaml.dump(config_yaml, f)

        from osiris.core.config import resolve_aiop_config

        config, sources = resolve_aiop_config()

        # Check timeline_density from YAML
        assert config["timeline_density"] == "high"
        assert sources["timeline_density"] == "YAML"

        # Other values should be defaults
        assert config["max_core_bytes"] == 300000
        assert sources["max_core_bytes"] == "DEFAULT"

    def test_case_c_env_overrides_yaml(self, tmp_path, monkeypatch):
        """Case C: ENV sets OSIRIS_AIOP_TIMELINE_DENSITY=low overrides YAML."""
        monkeypatch.chdir(tmp_path)

        # Create YAML with high
        config_yaml = {"version": "2.0", "aiop": {"timeline_density": "high", "metrics_topk": 200}}

        with open(tmp_path / "osiris.yaml", "w") as f:
            yaml.dump(config_yaml, f)

        # Set ENV variable
        monkeypatch.setenv("OSIRIS_AIOP_TIMELINE_DENSITY", "low")

        from osiris.core.config import resolve_aiop_config

        config, sources = resolve_aiop_config()

        # Check ENV overrides YAML
        assert config["timeline_density"] == "low"
        assert sources["timeline_density"] == "ENV"

        # YAML value for other field
        assert config["metrics_topk"] == 200
        assert sources["metrics_topk"] == "YAML"

    def test_case_d_cli_overrides_all(self, tmp_path, monkeypatch):
        """Case D: CLI --timeline-density medium overrides ENV."""
        monkeypatch.chdir(tmp_path)

        # Create YAML with high
        config_yaml = {
            "version": "2.0",
            "aiop": {"timeline_density": "high", "metrics_topk": 200, "max_core_bytes": 500000},
        }

        with open(tmp_path / "osiris.yaml", "w") as f:
            yaml.dump(config_yaml, f)

        # Set ENV variables
        monkeypatch.setenv("OSIRIS_AIOP_TIMELINE_DENSITY", "low")
        monkeypatch.setenv("OSIRIS_AIOP_METRICS_TOPK", "50")

        from osiris.core.config import resolve_aiop_config

        # Simulate CLI args
        cli_args = {"timeline_density": "medium"}

        config, sources = resolve_aiop_config(cli_args)

        # Check CLI overrides all
        assert config["timeline_density"] == "medium"
        assert sources["timeline_density"] == "CLI"

        # ENV overrides YAML
        assert config["metrics_topk"] == 50
        assert sources["metrics_topk"] == "ENV"

        # YAML value (no ENV or CLI)
        assert config["max_core_bytes"] == 500000
        assert sources["max_core_bytes"] == "YAML"

    def test_nested_config_precedence(self, tmp_path, monkeypatch):
        """Test precedence for nested configuration values."""
        monkeypatch.chdir(tmp_path)

        # Create YAML with nested values
        config_yaml = {
            "version": "2.0",
            "aiop": {
                "output": {"core_path": "custom/aiop.json"},
                "annex": {"enabled": True, "compress": "gzip"},
            },
        }

        with open(tmp_path / "osiris.yaml", "w") as f:
            yaml.dump(config_yaml, f)

        # Set ENV for some nested values
        monkeypatch.setenv("OSIRIS_AIOP_ANNEX_COMPRESS", "zstd")

        from osiris.core.config import resolve_aiop_config

        config, sources = resolve_aiop_config()

        # YAML value
        assert config["output"]["core_path"] == "custom/aiop.json"
        assert sources["output.core_path"] == "YAML"

        # ENV overrides YAML
        assert config["annex"]["compress"] == "zstd"
        assert sources["annex.compress"] == "ENV"

        # YAML value (not overridden)
        assert config["annex"]["enabled"] is True
        assert sources["annex.enabled"] == "YAML"

        # Default value
        assert config["annex"]["dir"] == "logs/aiop/annex"
        assert sources["annex.dir"] == "DEFAULT"

    def test_config_effective_in_metadata(self, tmp_path, monkeypatch):
        """Test that metadata.config_effective contains source information."""
        monkeypatch.chdir(tmp_path)

        # Create minimal YAML
        config_yaml = {"version": "2.0", "aiop": {"timeline_density": "high"}}

        with open(tmp_path / "osiris.yaml", "w") as f:
            yaml.dump(config_yaml, f)

        # Set ENV
        monkeypatch.setenv("OSIRIS_AIOP_METRICS_TOPK", "50")

        from osiris.core.config import resolve_aiop_config
        from osiris.core.run_export_v2 import _build_config_effective

        # Simulate CLI
        cli_args = {"policy": "annex"}

        config, sources = resolve_aiop_config(cli_args)
        config_effective = _build_config_effective(config, sources)

        # Check structure
        assert config_effective["timeline_density"]["value"] == "high"
        assert config_effective["timeline_density"]["source"] == "YAML"

        assert config_effective["metrics_topk"]["value"] == 50
        assert config_effective["metrics_topk"]["source"] == "ENV"

        assert config_effective["policy"]["value"] == "annex"
        assert config_effective["policy"]["source"] == "CLI"

        assert config_effective["max_core_bytes"]["value"] == 300000
        assert config_effective["max_core_bytes"]["source"] == "DEFAULT"
