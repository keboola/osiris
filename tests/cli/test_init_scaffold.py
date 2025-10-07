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

"""Tests for osiris init command - Filesystem Contract v1 scaffolder."""

import json
from pathlib import Path
import subprocess

import pytest
import yaml


def test_init_creates_directory_structure(tmp_path):
    """Test that 'osiris init' creates the full Filesystem Contract v1 directory structure."""
    from osiris.cli.init import init_command

    # Run init in temporary directory
    init_command([str(tmp_path)], json_output=False)

    # Verify directory structure
    assert (tmp_path / "pipelines").is_dir()
    assert (tmp_path / "build").is_dir()
    assert (tmp_path / "aiop").is_dir()
    assert (tmp_path / "run_logs").is_dir()
    assert (tmp_path / ".osiris/sessions").is_dir()
    assert (tmp_path / ".osiris/cache").is_dir()
    assert (tmp_path / ".osiris/index").is_dir()


def test_init_creates_osiris_yaml(tmp_path):
    """Test that 'osiris init' creates osiris.yaml with Filesystem Contract v1 config."""
    from osiris.cli.init import init_command

    init_command([str(tmp_path)], json_output=False)

    # Verify osiris.yaml exists and is valid
    config_file = tmp_path / "osiris.yaml"
    assert config_file.exists()

    # Parse YAML
    with open(config_file) as f:
        config = yaml.safe_load(f)

    # Verify key filesystem contract sections
    assert "filesystem" in config
    assert "ids" in config

    # Verify filesystem subsections
    fs = config["filesystem"]
    assert fs["base_path"] == ""
    assert fs["pipelines_dir"] == "pipelines"
    assert fs["build_dir"] == "build"
    assert fs["aiop_dir"] == "aiop"
    assert fs["run_logs_dir"] == "run_logs"
    assert fs["sessions_dir"] == ".osiris/sessions"
    assert fs["cache_dir"] == ".osiris/cache"
    assert fs["index_dir"] == ".osiris/index"

    # Verify profiles
    assert "profiles" in fs
    assert fs["profiles"]["enabled"] is True
    assert "dev" in fs["profiles"]["values"]
    assert fs["profiles"]["default"] == "dev"

    # Verify naming
    assert "naming" in fs
    assert fs["naming"]["manifest_short_len"] == 7

    # Verify IDs config
    assert config["ids"]["run_id_format"] == ["incremental", "ulid"]
    assert config["ids"]["manifest_hash_algo"] == "sha256_slug"


def test_init_creates_gitignore(tmp_path):
    """Test that 'osiris init' creates .gitignore with correct patterns."""
    from osiris.cli.init import init_command

    init_command([str(tmp_path)], json_output=False)

    gitignore_file = tmp_path / ".gitignore"
    assert gitignore_file.exists()

    content = gitignore_file.read_text()

    # Verify key patterns are present
    assert "run_logs/" in content
    assert "aiop/**/annex/" in content
    assert ".osiris/cache/" in content
    assert ".osiris/sessions/" in content
    assert ".osiris/index/counters.sqlite" in content
    assert ".env" in content
    assert "osiris_connections.yaml" in content


def test_init_creates_env_example(tmp_path):
    """Test that 'osiris init' creates .env.example."""
    from osiris.cli.init import init_command

    init_command([str(tmp_path)], json_output=False)

    env_example = tmp_path / ".env.example"
    assert env_example.exists()

    content = env_example.read_text()
    assert "MYSQL_HOST" in content
    assert "OPENAI_API_KEY" in content
    assert "OSIRIS_PROFILE" in content


def test_init_creates_connections_example(tmp_path):
    """Test that 'osiris init' creates osiris_connections.example.yaml."""
    from osiris.cli.init import init_command

    init_command([str(tmp_path)], json_output=False)

    connections_example = tmp_path / "osiris_connections.example.yaml"
    assert connections_example.exists()

    # Verify it's valid YAML
    with open(connections_example) as f:
        config = yaml.safe_load(f)

    assert "connections" in config
    assert "mysql" in config["connections"]
    assert "supabase" in config["connections"]


def test_init_json_output(tmp_path):
    """Test that 'osiris init --json' produces valid JSON output."""
    import sys
    from unittest.mock import patch

    from osiris.cli.init import init_command

    # Capture stdout
    output = []

    def mock_print(msg):
        output.append(msg)

    with patch("builtins.print", mock_print):
        init_command([str(tmp_path), "--json"], json_output=True)

    # Parse JSON output
    assert len(output) > 0
    result = json.loads(output[0])

    assert result["status"] == "success"
    assert "created" in result
    assert result["created"]["osiris_yaml"] is True
    assert "directories" in result["created"]


def test_init_force_overwrite(tmp_path):
    """Test that 'osiris init --force' overwrites existing osiris.yaml."""
    from osiris.cli.init import init_command

    # Create initial osiris.yaml
    config_file = tmp_path / "osiris.yaml"
    config_file.write_text("version: '1.0'")

    # Run init with --force
    init_command([str(tmp_path), "--force"], json_output=False)

    # Verify file was overwritten
    with open(config_file) as f:
        config = yaml.safe_load(f)

    assert config["version"] == "2.0"  # New version
    assert "filesystem" in config  # New structure


def test_init_without_force_fails_if_exists(tmp_path):
    """Test that 'osiris init' fails if osiris.yaml exists without --force."""
    from osiris.cli.init import init_command

    # Create existing osiris.yaml
    config_file = tmp_path / "osiris.yaml"
    config_file.write_text("version: '1.0'")

    # Run init without --force should fail
    with pytest.raises(SystemExit):
        init_command([str(tmp_path)], json_output=False)


def test_init_git_option(tmp_path):
    """Test that 'osiris init --git' initializes git repository (if git available)."""
    from osiris.cli.init import init_command

    # Check if git is available
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        git_available = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        git_available = False

    if not git_available:
        pytest.skip("Git not available")

    init_command([str(tmp_path), "--git"], json_output=False)

    # Verify .git directory exists
    git_dir = tmp_path / ".git"
    assert git_dir.exists()

    # Verify initial commit exists
    result = subprocess.run(["git", "log", "--oneline"], capture_output=True, text=True, cwd=tmp_path)
    assert "initialize osiris project" in result.stdout.lower()


def test_config_loads_via_fs_config(tmp_path):
    """Test that generated osiris.yaml can be loaded by fs_config.load_osiris_config()."""
    from osiris.cli.init import init_command
    from osiris.core.fs_config import load_osiris_config

    init_command([str(tmp_path)], json_output=False)

    # Change to temp directory to load config
    import os

    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        fs_config, ids_config, raw_config = load_osiris_config()

        # Verify configs loaded successfully
        assert fs_config.pipelines_dir == "pipelines"
        assert fs_config.build_dir == "build"
        assert fs_config.profiles.enabled is True
        assert fs_config.profiles.default == "dev"
        assert ids_config.run_id_format == ["incremental", "ulid"]
    finally:
        os.chdir(old_cwd)
