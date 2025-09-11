"""Tests for E2B packer with cfg file inclusion and validation."""

import json
import tarfile
import tempfile
from pathlib import Path

import pytest
import yaml

from osiris.remote.e2b_pack import PayloadBuilder, RunConfig


class TestPayloadBuilderCfgInclusion:
    """Test cfg file inclusion and validation in payload builder."""

    def test_extract_cfg_paths_from_manifest(self):
        """Test extracting cfg paths from manifest data."""
        manifest_data = {
            "steps": [
                {"id": "step1", "cfg_path": "cfg/step1.json", "driver": "test"},
                {"id": "step2", "cfg_path": "cfg/step2.json", "driver": "test"},
                {"id": "step3", "driver": "test"},  # No cfg_path
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            session_dir = Path(temp_dir) / "session"
            build_dir = Path(temp_dir) / "build"
            builder = PayloadBuilder(session_dir, build_dir)

            cfg_paths = builder._extract_cfg_paths(manifest_data)

            assert cfg_paths == ["cfg/step1.json", "cfg/step2.json"]

    def test_include_cfg_files_success(self, tmp_path):
        """Test successful inclusion of cfg files."""
        # Setup directory structure
        session_dir = tmp_path / "session"
        build_dir = tmp_path / "build"
        compiled_dir = tmp_path / "compiled"
        cfg_dir = compiled_dir / "cfg"

        session_dir.mkdir()
        build_dir.mkdir()
        cfg_dir.mkdir(parents=True)

        # Create test cfg files
        cfg1_content = {"component": "mysql.extractor", "query": "SELECT * FROM test1"}
        cfg2_content = {"component": "filesystem.csv_writer", "path": "./output/test.csv"}

        (cfg_dir / "step1.json").write_text(json.dumps(cfg1_content))
        (cfg_dir / "step2.json").write_text(json.dumps(cfg2_content))

        # Create manifest
        manifest_path = compiled_dir / "manifest.yaml"
        manifest_data = {
            "steps": [
                {"id": "step1", "cfg_path": "cfg/step1.json", "driver": "mysql.extractor"},
                {"id": "step2", "cfg_path": "cfg/step2.json", "driver": "filesystem.csv_writer"},
            ]
        }
        manifest_path.write_text(yaml.dump(manifest_data))

        # Create builder and build payload
        builder = PayloadBuilder(session_dir, build_dir)
        run_config = RunConfig()

        payload_path = builder.build(manifest_path, run_config)

        # Verify tarball was created
        assert payload_path.exists()
        assert payload_path.name == "payload.tgz"

        # Extract and verify contents
        with tempfile.TemporaryDirectory() as extract_dir:
            extract_path = Path(extract_dir)
            with tarfile.open(payload_path, "r:gz") as tar:
                tar.extractall(extract_path)

            # Check required files exist
            assert (extract_path / "manifest.json").exists()
            assert (extract_path / "mini_runner.py").exists()
            assert (extract_path / "requirements.txt").exists()
            assert (extract_path / "run_config.json").exists()

            # Check cfg directory and files exist
            assert (extract_path / "cfg").is_dir()
            assert (extract_path / "cfg" / "step1.json").exists()
            assert (extract_path / "cfg" / "step2.json").exists()

            # Verify cfg file contents
            with open(extract_path / "cfg" / "step1.json") as f:
                assert json.load(f) == cfg1_content
            with open(extract_path / "cfg" / "step2.json") as f:
                assert json.load(f) == cfg2_content

    def test_missing_cfg_files_error(self, tmp_path):
        """Test error when referenced cfg files are missing."""
        session_dir = tmp_path / "session"
        build_dir = tmp_path / "build"
        compiled_dir = tmp_path / "compiled"

        session_dir.mkdir()
        build_dir.mkdir()
        compiled_dir.mkdir()

        # Create manifest referencing non-existent cfg files
        manifest_path = compiled_dir / "manifest.yaml"
        manifest_data = {
            "steps": [
                {"id": "step1", "cfg_path": "cfg/missing1.json", "driver": "test"},
                {"id": "step2", "cfg_path": "cfg/missing2.json", "driver": "test"},
            ]
        }
        manifest_path.write_text(yaml.dump(manifest_data))

        # Create builder and attempt to build
        builder = PayloadBuilder(session_dir, build_dir)
        run_config = RunConfig()

        with pytest.raises(ValueError, match="Missing cfg files referenced by manifest"):
            builder.build(manifest_path, run_config)

    def test_partial_missing_cfg_files_error(self, tmp_path):
        """Test error when some cfg files are missing."""
        session_dir = tmp_path / "session"
        build_dir = tmp_path / "build"
        compiled_dir = tmp_path / "compiled"
        cfg_dir = compiled_dir / "cfg"

        session_dir.mkdir()
        build_dir.mkdir()
        cfg_dir.mkdir(parents=True)

        # Create only one of two cfg files
        (cfg_dir / "exists.json").write_text('{"test": "data"}')

        # Create manifest referencing both existing and missing files
        manifest_path = compiled_dir / "manifest.yaml"
        manifest_data = {
            "steps": [
                {"id": "step1", "cfg_path": "cfg/exists.json", "driver": "test"},
                {"id": "step2", "cfg_path": "cfg/missing.json", "driver": "test"},
            ]
        }
        manifest_path.write_text(yaml.dump(manifest_data))

        builder = PayloadBuilder(session_dir, build_dir)
        run_config = RunConfig()

        with pytest.raises(ValueError) as exc_info:
            builder.build(manifest_path, run_config)

        error_msg = str(exc_info.value)
        assert "Missing cfg files referenced by manifest" in error_msg
        assert "cfg/missing.json" in error_msg
        assert "cfg/exists.json" not in error_msg

    def test_payload_manifest_includes_cfg_files(self, tmp_path):
        """Test that payload manifest includes cfg files in file listing."""
        session_dir = tmp_path / "session"
        build_dir = tmp_path / "build"
        compiled_dir = tmp_path / "compiled"
        cfg_dir = compiled_dir / "cfg"

        session_dir.mkdir()
        build_dir.mkdir()
        cfg_dir.mkdir(parents=True)

        # Create cfg files
        (cfg_dir / "test.json").write_text('{"test": "data"}')

        # Create manifest
        manifest_path = compiled_dir / "manifest.yaml"
        manifest_data = {"steps": [{"id": "test", "cfg_path": "cfg/test.json", "driver": "test"}]}
        manifest_path.write_text(yaml.dump(manifest_data))

        builder = PayloadBuilder(session_dir, build_dir)
        run_config = RunConfig()

        payload_path = builder.build(manifest_path, run_config)

        # Read metadata
        metadata_path = session_dir / "metadata.json"
        assert metadata_path.exists()

        with open(metadata_path) as f:
            metadata = json.load(f)

        # Check that cfg files are listed in the manifest
        files = metadata["remote"]["payload"]["files"]
        file_names = [f["name"] for f in files]

        assert "manifest.json" in file_names
        assert "cfg/test.json" in file_names
        assert any(f["name"] == "cfg/test.json" for f in files)

    def test_no_cfg_files_still_works(self, tmp_path):
        """Test that manifests with no cfg files still work."""
        session_dir = tmp_path / "session"
        build_dir = tmp_path / "build"
        compiled_dir = tmp_path / "compiled"

        session_dir.mkdir()
        build_dir.mkdir()
        compiled_dir.mkdir()

        # Create manifest with no cfg_path entries
        manifest_path = compiled_dir / "manifest.yaml"
        manifest_data = {
            "steps": [
                {"id": "step1", "driver": "test"},
                {"id": "step2", "driver": "test"},
            ]
        }
        manifest_path.write_text(yaml.dump(manifest_data))

        builder = PayloadBuilder(session_dir, build_dir)
        run_config = RunConfig()

        # Should not raise an error
        payload_path = builder.build(manifest_path, run_config)
        assert payload_path.exists()

        # Extract and verify no cfg directory
        with tempfile.TemporaryDirectory() as extract_dir:
            extract_path = Path(extract_dir)
            with tarfile.open(payload_path, "r:gz") as tar:
                tar.extractall(extract_path)

            # Should not have cfg directory
            assert not (extract_path / "cfg").exists()

    def test_cfg_directory_allowlisted(self, tmp_path):
        """Test that cfg directory is properly allowlisted."""
        session_dir = tmp_path / "session"
        build_dir = tmp_path / "build"
        compiled_dir = tmp_path / "compiled"
        cfg_dir = compiled_dir / "cfg"

        session_dir.mkdir()
        build_dir.mkdir()
        cfg_dir.mkdir(parents=True)

        # Create cfg file
        (cfg_dir / "test.json").write_text('{"test": "data"}')

        # Create manifest
        manifest_path = compiled_dir / "manifest.yaml"
        manifest_data = {"steps": [{"id": "test", "cfg_path": "cfg/test.json", "driver": "test"}]}
        manifest_path.write_text(yaml.dump(manifest_data))

        builder = PayloadBuilder(session_dir, build_dir)
        run_config = RunConfig()

        # Should not raise allowlist error
        payload_path = builder.build(manifest_path, run_config)

        # Validate payload should also pass
        manifest = builder.validate_payload(payload_path)
        assert any(f["name"] == "cfg/test.json" for f in manifest.files)

    def test_unauthorized_directory_rejected(self, tmp_path):
        """Test that unauthorized directories are rejected during validation."""
        session_dir = tmp_path / "session"
        build_dir = tmp_path / "build"
        payload_dir = build_dir / "e2b"

        session_dir.mkdir()
        payload_dir.mkdir(parents=True)

        # Create allowed files
        (payload_dir / "manifest.json").write_text('{"test": "data"}')
        (payload_dir / "mini_runner.py").write_text('print("test")')

        # Create unauthorized directory
        unauthorized_dir = payload_dir / "unauthorized"
        unauthorized_dir.mkdir()
        (unauthorized_dir / "bad.txt").write_text("unauthorized content")

        builder = PayloadBuilder(session_dir, build_dir)

        # Should raise error during allowlist validation
        with pytest.raises(ValueError, match="Directory not in allowlist: unauthorized"):
            # Create a dummy tarball with the unauthorized directory
            tarball_path = build_dir / "payload.tgz"
            with tarfile.open(tarball_path, "w:gz") as tar:
                tar.add(payload_dir, arcname=".")

            builder.validate_payload(tarball_path)
