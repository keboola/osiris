"""Unit tests for E2B payload builder."""

import hashlib
import json
import tarfile
import tempfile
from pathlib import Path

import pytest

from osiris.remote.e2b_pack import PayloadBuilder, PayloadManifest, RunConfig


class TestPayloadBuilder:
    """Test payload builder functionality."""

    def test_build_basic_payload(self):
        """Test building a basic payload."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            session_dir = tmpdir / "session"
            build_dir = tmpdir / "build"
            session_dir.mkdir()
            build_dir.mkdir()

            # Create a mock manifest
            manifest_path = session_dir / "manifest.json"
            manifest_data = {
                "name": "test-pipeline",
                "steps": [
                    {"id": "step1", "component": "mysql.extractor"},
                    {"id": "step2", "component": "filesystem.csv.writer"},
                ],
            }
            with open(manifest_path, "w") as f:
                json.dump(manifest_data, f)

            # Build payload
            builder = PayloadBuilder(session_dir, build_dir)
            run_config = RunConfig(seed=42, profile=True)

            payload_path = builder.build(manifest_path, run_config)

            # Verify tarball was created
            assert payload_path.exists()
            assert payload_path.name == "payload.tgz"

            # Verify contents
            with tarfile.open(payload_path, "r:gz") as tar:
                members = tar.getnames()
                assert "manifest.json" in members
                assert "mini_runner.py" in members
                assert "requirements.txt" in members
                assert "run_config.json" in members

            # Verify metadata was written
            metadata_path = session_dir / "metadata.json"
            assert metadata_path.exists()
            with open(metadata_path) as f:
                metadata = json.load(f)
            assert "remote" in metadata
            assert "payload" in metadata["remote"]
            assert "sha256" in metadata["remote"]["payload"]

    def test_payload_allowlist(self):
        """Test that only allowed files are included."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            session_dir = tmpdir / "session"
            build_dir = tmpdir / "build"
            session_dir.mkdir()
            build_dir.mkdir()

            # Create manifest
            manifest_path = session_dir / "manifest.json"
            with open(manifest_path, "w") as f:
                json.dump({"name": "test"}, f)

            builder = PayloadBuilder(session_dir, build_dir)

            # Add an unauthorized file to payload directory
            builder.payload_dir.mkdir(parents=True, exist_ok=True)
            unauthorized_file = builder.payload_dir / "secrets.txt"
            unauthorized_file.write_text("secret data")

            # Building should fail
            with pytest.raises(ValueError, match="not in allowlist"):
                builder.build(manifest_path, RunConfig())

    def test_payload_size_limit(self):
        """Test that payload size is enforced."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            session_dir = tmpdir / "session"
            build_dir = tmpdir / "build"
            session_dir.mkdir()
            build_dir.mkdir()

            # Create a manifest
            manifest_path = session_dir / "manifest.json"
            with open(manifest_path, "w") as f:
                json.dump({"name": "test"}, f)

            builder = PayloadBuilder(session_dir, build_dir)

            # Temporarily lower the max size to make test faster
            original_max = builder.MAX_PAYLOAD_SIZE
            builder.MAX_PAYLOAD_SIZE = 1024  # 1KB - very small

            try:
                # Building should fail due to size
                with pytest.raises(ValueError, match="exceeds maximum"):
                    builder.build(manifest_path, RunConfig())
            finally:
                builder.MAX_PAYLOAD_SIZE = original_max

    def test_sha256_computation(self):
        """Test SHA256 hash computation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            session_dir = tmpdir / "session"
            build_dir = tmpdir / "build"
            session_dir.mkdir()
            build_dir.mkdir()

            # Create manifest
            manifest_path = session_dir / "manifest.json"
            manifest_data = {"name": "test", "version": "1.0"}
            with open(manifest_path, "w") as f:
                json.dump(manifest_data, f)

            builder = PayloadBuilder(session_dir, build_dir)
            payload_path = builder.build(manifest_path, RunConfig())

            # Compute SHA256 manually
            sha256_hash = hashlib.sha256()
            with open(payload_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            expected_sha256 = sha256_hash.hexdigest()

            # Check metadata
            metadata_path = session_dir / "metadata.json"
            with open(metadata_path) as f:
                metadata = json.load(f)

            assert metadata["remote"]["payload"]["sha256"] == expected_sha256

    def test_validate_payload(self):
        """Test payload validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            session_dir = tmpdir / "session"
            build_dir = tmpdir / "build"
            session_dir.mkdir()
            build_dir.mkdir()

            # Create manifest
            manifest_path = session_dir / "manifest.json"
            with open(manifest_path, "w") as f:
                json.dump({"name": "test"}, f)

            builder = PayloadBuilder(session_dir, build_dir)
            payload_path = builder.build(manifest_path, RunConfig())

            # Validate payload
            manifest = builder.validate_payload(payload_path)

            assert isinstance(manifest, PayloadManifest)
            assert manifest.total_size_bytes > 0
            assert len(manifest.sha256) == 64  # SHA256 hex length
            assert len(manifest.files) == 4  # Expected files

    def test_run_config_serialization(self):
        """Test RunConfig serialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            session_dir = tmpdir / "session"
            build_dir = tmpdir / "build"
            session_dir.mkdir()
            build_dir.mkdir()

            # Create manifest
            manifest_path = session_dir / "manifest.json"
            with open(manifest_path, "w") as f:
                json.dump({"name": "test"}, f)

            # Build with custom run config
            builder = PayloadBuilder(session_dir, build_dir)
            run_config = RunConfig(
                seed=123,
                profile=True,
                params={"db": "test_db", "table": "users"},
                flags={"verbose": True, "debug": False},
            )

            builder.build(manifest_path, run_config)

            # Check run_config.json was created correctly
            config_path = builder.payload_dir / "run_config.json"
            assert config_path.exists()

            with open(config_path) as f:
                saved_config = json.load(f)

            assert saved_config["seed"] == 123
            assert saved_config["profile"] is True
            assert saved_config["params"]["db"] == "test_db"
            assert saved_config["flags"]["verbose"] is True

    def test_mini_runner_creation(self):
        """Test mini_runner.py creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            session_dir = tmpdir / "session"
            build_dir = tmpdir / "build"
            session_dir.mkdir()
            build_dir.mkdir()

            # Create manifest
            manifest_path = session_dir / "manifest.json"
            with open(manifest_path, "w") as f:
                json.dump({"name": "test"}, f)

            builder = PayloadBuilder(session_dir, build_dir)
            builder.build(manifest_path, RunConfig())

            # Check mini_runner.py was created
            runner_path = builder.payload_dir / "mini_runner.py"
            assert runner_path.exists()
            assert runner_path.stat().st_mode & 0o111  # Executable

            # Check content
            content = runner_path.read_text()
            assert "def main():" in content
            assert "manifest.json" in content
            assert "events.jsonl" in content

    def test_requirements_creation(self):
        """Test requirements.txt creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            session_dir = tmpdir / "session"
            build_dir = tmpdir / "build"
            session_dir.mkdir()
            build_dir.mkdir()

            # Create manifest
            manifest_path = session_dir / "manifest.json"
            with open(manifest_path, "w") as f:
                json.dump({"name": "test"}, f)

            builder = PayloadBuilder(session_dir, build_dir)
            builder.build(manifest_path, RunConfig())

            # Check requirements.txt
            req_path = builder.payload_dir / "requirements.txt"
            assert req_path.exists()

            content = req_path.read_text()
            assert "duckdb" in content
            assert "pandas" in content
            assert "pymysql" in content
