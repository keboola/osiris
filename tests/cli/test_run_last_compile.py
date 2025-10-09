"""Test for run command with last-compile features."""

import tempfile
from pathlib import Path

import yaml


def test_compile_writes_pointer_files(tmp_path, monkeypatch):
    """Test that compile command writes pointer files using contract paths."""
    from unittest.mock import MagicMock, patch

    from osiris.cli.compile import compile_command

    monkeypatch.chdir(tmp_path)

    # Create minimal osiris.yaml
    osiris_yaml = tmp_path / "osiris.yaml"
    osiris_yaml.write_text(
        """
version: "2.0"
filesystem:
  compilations: ".osiris/index/compilations"
"""
    )

    # Create a simple OML file
    oml_file = tmp_path / "test.yaml"
    oml_content = {
        "oml_version": "0.1.0",
        "name": "test_pipeline",
        "steps": [
            {
                "id": "extract_test",
                "component": "mysql.extractor",
                "config": {"connection": {"host": "test"}, "query": "SELECT 1"},
            }
        ],
    }
    with open(oml_file, "w") as f:
        yaml.dump(oml_content, f)

    # Mock the compiler to succeed
    with patch("osiris.cli.compile.CompilerV0") as mock_compiler_cls:
        mock_compiler = MagicMock()
        mock_compiler.compile.return_value = (True, "Success")
        mock_compiler.manifest_hash = "abc123"
        mock_compiler.manifest_short = "test"
        mock_compiler_cls.return_value = mock_compiler

        # Patch sys.exit to avoid test exit
        with patch("sys.exit"):
            # Run compile (will create pointer files)
            compile_command([str(oml_file)])

    # Check that contract-based pointer files were created
    # Global latest pointer
    global_pointer = tmp_path / ".osiris" / "index" / "last_compile.txt"
    assert global_pointer.exists(), f"Global pointer not found at {global_pointer}"

    # Per-pipeline latest pointer (uses manifest_short, not pipeline name)
    pipeline_pointer = tmp_path / ".osiris" / "index" / "latest" / "test.txt"
    assert pipeline_pointer.exists(), f"Pipeline pointer not found at {pipeline_pointer}"


def test_run_with_last_compile():
    """Test that run --last-compile uses the pointer file."""
    from osiris.cli.run import find_last_compile_manifest

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create osiris.yaml
        osiris_yaml = tmp_path / "osiris.yaml"
        osiris_yaml.write_text(
            """
version: "2.0"
filesystem:
  compilations: ".osiris/index/compilations"
"""
        )

        # Create contract structure
        index_dir = tmp_path / ".osiris" / "index"
        index_dir.mkdir(parents=True)

        # Create compilation directory
        compile_dir = index_dir / "compilations" / "test_abc123"
        compile_dir.mkdir(parents=True)
        manifest_path = compile_dir / "manifest.yaml"
        manifest_path.write_text("test: manifest")

        # Create global pointer file
        pointer_file = index_dir / "last_compile.txt"
        pointer_file.write_text(str(manifest_path))

        # Test finding last compile (should work from tmp_path)
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = find_last_compile_manifest()
            assert result == str(manifest_path), f"Expected {manifest_path}, got {result}"
        finally:
            os.chdir(original_cwd)


def test_run_with_last_compile_in():
    """Test that run --last-compile-in uses per-pipeline pointer."""
    from osiris.cli.run import find_last_compile_manifest

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create osiris.yaml
        osiris_yaml = tmp_path / "osiris.yaml"
        osiris_yaml.write_text(
            """
version: "2.0"
filesystem:
  compilations: ".osiris/index/compilations"
"""
        )

        # Create contract structure
        index_dir = tmp_path / ".osiris" / "index"
        latest_dir = index_dir / "latest"
        latest_dir.mkdir(parents=True)

        # Create compilation directory
        compile_dir = index_dir / "compilations" / "pipe_200_xyz789"
        compile_dir.mkdir(parents=True)
        manifest_path = compile_dir / "manifest.yaml"
        manifest_path.write_text("test: pipeline_200")

        # Create per-pipeline pointer
        pipeline_pointer = latest_dir / "pipeline_200.txt"
        pipeline_pointer.write_text(str(manifest_path))

        # Test finding pipeline-specific compile
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = find_last_compile_manifest(pipeline_slug="pipeline_200")
            assert result is not None, "Expected manifest path, got None"
            assert "pipeline_200" in result or "pipe_200" in result, f"Expected pipeline_200 in path, got {result}"
        finally:
            os.chdir(original_cwd)


def test_detect_file_type(tmp_path):
    """Test the file type detection logic."""
    from osiris.cli.run import detect_file_type

    # Create a manifest file (has pipeline, steps, meta)
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(
        """
pipeline: test
steps:
  - id: step1
meta:
  version: 1.0
"""
    )
    assert detect_file_type(str(manifest_file)) == "manifest"

    # Create an OML file (has oml_version or name, steps, but no meta)
    oml_file = tmp_path / "pipeline.yaml"
    oml_file.write_text(
        """
oml_version: "0.1.0"
name: test_pipeline
steps:
  - id: step1
"""
    )
    assert detect_file_type(str(oml_file)) == "oml"

    # Create an unknown/unparseable file (defaults to 'oml')
    unknown_file = tmp_path / "unknown.txt"
    unknown_file.write_text("random content")
    assert detect_file_type(str(unknown_file)) == "oml"  # Defaults to oml on parse errors
