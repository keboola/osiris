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

"""Tests for osiris init AIOP configuration generation."""


import yaml


class TestInitAIOP:
    """Test osiris init command with AIOP configuration."""

    def test_creates_osiris_yaml_with_aiop_block(self, tmp_path, monkeypatch):
        """Test that init creates osiris.yaml with AIOP configuration block."""
        # Change to temp directory
        monkeypatch.chdir(tmp_path)

        from osiris.core.config import create_sample_config

        # Create config
        create_sample_config("osiris.yaml")

        # Check file exists
        config_path = tmp_path / "osiris.yaml"
        assert config_path.exists()

        # Load and check AIOP section exists
        with open(config_path) as f:
            content = f.read()
            assert "aiop:" in content
            assert "enabled: true" in content
            assert "policy: core" in content
            assert "max_core_bytes: 300000" in content
            assert "timeline_density: medium" in content

        # Parse YAML and check structure
        with open(config_path) as f:
            config = yaml.safe_load(f)
            assert "aiop" in config
            assert config["aiop"]["enabled"] is True
            assert config["aiop"]["policy"] == "core"
            assert config["aiop"]["max_core_bytes"] == 300000
            assert config["aiop"]["timeline_density"] == "medium"
            assert config["aiop"]["metrics_topk"] == 100

    def test_merge_safe_behavior_preserves_existing(self, tmp_path, monkeypatch):
        """Test that existing values are preserved, missing keys added."""
        monkeypatch.chdir(tmp_path)

        # Create initial config with custom values
        initial_config = {
            "version": "2.0",
            "aiop": {
                "enabled": False,  # Custom value to preserve
                "policy": "annex",  # Custom value to preserve
                # max_core_bytes missing - should be added
            },
            "custom_section": {"custom_key": "custom_value"},
        }

        config_path = tmp_path / "osiris.yaml"
        with open(config_path, "w") as f:
            yaml.dump(initial_config, f)

        # Run create_sample_config (it creates backup)
        from osiris.core.config import create_sample_config

        create_sample_config("osiris.yaml")

        # Check backup was created
        backup_path = tmp_path / "osiris.yaml.backup"
        assert backup_path.exists()

        # Load new config
        with open(config_path) as f:
            new_config = yaml.safe_load(f)

        # Check AIOP section has all required keys
        assert new_config["aiop"]["enabled"] is True  # Default value
        assert new_config["aiop"]["policy"] == "core"  # Default value
        assert new_config["aiop"]["max_core_bytes"] == 300000  # Added missing key
        assert new_config["aiop"]["timeline_density"] == "medium"  # Added missing key

    def test_no_comments_flag_removes_comments(self, tmp_path, monkeypatch):
        """Test --no-comments flag removes comment lines."""
        monkeypatch.chdir(tmp_path)

        from osiris.core.config import create_sample_config

        # Create config without comments
        create_sample_config("osiris.yaml", no_comments=True)

        config_path = tmp_path / "osiris.yaml"
        with open(config_path) as f:
            content = f.read()

        # Check no standalone comment lines
        lines = content.split("\n")
        for line in lines:
            stripped = line.lstrip()
            # No lines should start with # (except inline comments)
            if stripped and stripped.startswith("#"):
                # Check if it's after content (inline comment)
                if line.strip() == "#":
                    continue
                # This should be an inline comment only
                assert ":" in line or "=" in line, f"Found comment line: {line}"

        # But YAML should still be valid
        with open(config_path) as f:
            config = yaml.safe_load(f)
            assert "aiop" in config
            assert config["aiop"]["enabled"] is True

    def test_stdout_flag_outputs_to_stdout(self, tmp_path, monkeypatch, capsys):
        """Test --stdout flag outputs config to stdout instead of file."""
        monkeypatch.chdir(tmp_path)

        from osiris.core.config import create_sample_config

        # Create config to stdout
        output = create_sample_config("osiris.yaml", to_stdout=True)

        # Check output was returned
        assert "aiop:" in output
        assert "enabled: true" in output

        # Check no file was created
        config_path = tmp_path / "osiris.yaml"
        assert not config_path.exists()

        # Verify valid YAML
        config = yaml.safe_load(output)
        assert config["aiop"]["enabled"] is True

    def test_aiop_section_contains_all_required_fields(self, tmp_path, monkeypatch):
        """Test that AIOP section contains all required configuration fields."""
        monkeypatch.chdir(tmp_path)

        from osiris.core.config import create_sample_config

        create_sample_config("osiris.yaml")

        with open(tmp_path / "osiris.yaml") as f:
            config = yaml.safe_load(f)

        aiop = config["aiop"]

        # Check all top-level fields
        assert aiop["enabled"] is True
        assert aiop["policy"] == "core"
        assert aiop["max_core_bytes"] == 300000
        assert aiop["timeline_density"] == "medium"
        assert aiop["metrics_topk"] == 100
        assert aiop["schema_mode"] == "summary"
        assert aiop["delta"] == "previous"
        assert aiop["run_card"] is True

        # Check output section
        assert "output" in aiop
        assert aiop["output"]["core_path"] == "aiop/{session_id}/aiop.json"
        assert aiop["output"]["run_card_path"] == "aiop/{session_id}/run-card.md"

        # Check annex section
        assert "annex" in aiop
        assert aiop["annex"]["enabled"] is False
        assert aiop["annex"]["dir"] == "aiop/annex"
        assert aiop["annex"]["compress"] == "none"

        # Check retention section
        assert "retention" in aiop
        assert aiop["retention"]["keep_runs"] == 50
        assert aiop["retention"]["annex_keep_days"] == 14

        # Check narrative section
        assert "narrative" in aiop
        assert aiop["narrative"]["sources"] == [
            "manifest",
            "repo_readme",
            "commit_message",
            "discovery",
        ]
        assert "session_chat" in aiop["narrative"]
        assert aiop["narrative"]["session_chat"]["enabled"] is False
        assert aiop["narrative"]["session_chat"]["mode"] == "masked"
        assert aiop["narrative"]["session_chat"]["max_chars"] == 2000
        assert aiop["narrative"]["session_chat"]["redact_pii"] is True
