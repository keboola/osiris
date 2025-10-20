"""E2B payload packing module with validation."""

from dataclasses import dataclass
import json
from pathlib import Path
import tarfile
import tempfile
from typing import Any


@dataclass
class RunConfig:
    """Configuration for running a pipeline."""

    seed: int | None = None
    profile: bool = False
    manifest_path: str | None = None
    session_id: str | None = None
    output_dir: str = "/home/user/artifacts"
    log_level: str = "INFO"
    environment: dict[str, str] = None

    def __post_init__(self):
        if self.environment is None:
            self.environment = {}


@dataclass
class PayloadManifest:
    """Manifest describing payload contents."""

    version: str = "1.0"
    files: list[str] = None
    directories: list[str] = None
    entry_point: str = "mini_runner.py"
    run_config: RunConfig = None

    def __post_init__(self):
        if self.files is None:
            self.files = []
        if self.directories is None:
            self.directories = []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = {
            "version": self.version,
            "files": self.files,
            "directories": self.directories,
            "entry_point": self.entry_point,
        }
        if self.run_config:
            data["run_config"] = {
                "manifest_path": self.run_config.manifest_path,
                "session_id": self.run_config.session_id,
                "output_dir": self.run_config.output_dir,
                "log_level": self.run_config.log_level,
                "environment": self.run_config.environment,
            }
        return data


class PayloadBuilder:
    """Builder for E2B execution payloads."""

    def __init__(self, session_dir: Path, build_dir: Path | None = None):
        """Initialize payload builder.

        Args:
            session_dir: Session directory containing manifest and configs
            build_dir: Directory for building payload (defaults to session_dir)
        """
        self.session_dir = session_dir
        self.build_dir = build_dir or session_dir
        self.payload_dir = None
        self.manifest = PayloadManifest()

    def build(
        self,
        manifest_path: Path,
        run_config: RunConfig,
    ) -> Path:
        """Build E2B payload tarball.

        Args:
            manifest_path: Path to compiled manifest.yaml
            run_config: Run configuration

        Returns:
            Path to created payload.tgz file

        Raises:
            ValueError: If required files are missing or validation fails
        """
        # Create temporary directory for payload
        with tempfile.TemporaryDirectory() as temp_dir:
            self.payload_dir = Path(temp_dir)

            # Copy pipeline manifest with different name to avoid confusion
            pipeline_dest = self.payload_dir / "pipeline.json"
            if manifest_path.suffix == ".yaml":
                # Convert YAML to JSON
                import yaml

                with open(manifest_path) as f:
                    pipeline_data = yaml.safe_load(f)
                with open(pipeline_dest, "w") as f:
                    json.dump(pipeline_data, f, indent=2)
            else:
                # Copy JSON directly
                import shutil

                shutil.copy2(manifest_path, pipeline_dest)
            self.manifest.files.append("pipeline.json")

            # Create mini_runner.py
            mini_runner_content = self._create_mini_runner()
            mini_runner_path = self.payload_dir / "mini_runner.py"
            with open(mini_runner_path, "w") as f:
                f.write(mini_runner_content)
            self.manifest.files.append("mini_runner.py")

            # Create requirements.txt
            requirements_content = self._create_requirements()
            requirements_path = self.payload_dir / "requirements.txt"
            with open(requirements_path, "w") as f:
                f.write(requirements_content)
            self.manifest.files.append("requirements.txt")

            # Copy cfg directory if it exists
            cfg_dir = self.session_dir / "cfg"
            if cfg_dir.exists():
                cfg_dest = self.payload_dir / "cfg"
                import shutil

                shutil.copytree(cfg_dir, cfg_dest)
                self.manifest.directories.append("cfg")

                # Add cfg files to manifest
                for cfg_file in cfg_dest.glob("*.json"):
                    self.manifest.files.append(f"cfg/{cfg_file.name}")

            # Write run config
            run_config_path = self.payload_dir / "run_config.json"
            run_config_data = {
                "seed": run_config.seed,
                "profile": run_config.profile,
                "manifest_path": "pipeline.json",  # Point to pipeline file
                "session_id": run_config.session_id,
                "output_dir": run_config.output_dir,
                "log_level": run_config.log_level,
                "environment": run_config.environment,
            }
            with open(run_config_path, "w") as f:
                json.dump(run_config_data, f, indent=2)
            self.manifest.files.append("run_config.json")

            # Update manifest with run config
            self.manifest.run_config = run_config

            # Write payload manifest (metadata about the payload itself)
            payload_manifest_path = self.payload_dir / "manifest.json"
            with open(payload_manifest_path, "w") as f:
                json.dump(self.manifest.to_dict(), f, indent=2)

            # Validate payload before packing
            validate_payload(self.payload_dir)

            # Create tarball
            output_path = self.build_dir / "payload.tgz"
            with tarfile.open(output_path, "w:gz") as tar:
                for item in self.payload_dir.iterdir():
                    tar.add(item, arcname=item.name)

            # Compute SHA256 of payload
            import hashlib

            sha256_hash = hashlib.sha256()
            with open(output_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            payload_sha256 = sha256_hash.hexdigest()

            # Write metadata to session directory
            metadata = {
                "remote": {
                    "payload": {
                        "sha256": payload_sha256,
                        "size_bytes": output_path.stat().st_size,
                        "path": str(output_path),
                    }
                }
            }
            metadata_path = self.session_dir / "metadata.json"
            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=2)

            return output_path

    def _create_mini_runner(self) -> str:
        """Create mini_runner.py content."""
        return '''#!/usr/bin/env python3
"""Mini runner for E2B execution."""

import json
import sys
from pathlib import Path

def main():
    # Load run config
    with open("run_config.json") as f:
        config = json.load(f)

    # Load pipeline manifest
    with open(config.get("manifest_path", "pipeline.json")) as f:
        manifest = json.load(f)

    print(f"Running pipeline: {manifest.get('pipeline', {}).get('name', 'unknown')}")
    print(f"Session ID: {config.get('session_id', 'unknown')}")

    # Placeholder for actual execution
    print("Pipeline execution would happen here")

    return 0

if __name__ == "__main__":
    sys.exit(main())
'''

    def _create_requirements(self) -> str:
        """Create requirements.txt content."""
        return """# Osiris dependencies
pyyaml>=6.0
pandas>=1.5.0
duckdb>=0.9.0
pymysql>=1.0.0
sqlalchemy>=2.0.0
supabase>=2.0.0
"""


def validate_payload(payload_dir: Path) -> None:
    """Validate payload directory structure.

    Args:
        payload_dir: Directory containing payload files

    Raises:
        ValueError: If validation fails
    """
    # Define allowed items at payload root
    allowed_root_items = {
        "manifest.json",  # Payload manifest (metadata)
        "pipeline.json",  # Pipeline manifest (actual pipeline)
        "mini_runner.py",
        "requirements.txt",
        "run_config.json",
        "cfg",  # Directory
    }

    # Check for unexpected items
    actual_items = set()
    for item in payload_dir.iterdir():
        actual_items.add(item.name)

    # Check for extra items
    extra_items = actual_items - allowed_root_items
    if extra_items:
        raise ValueError(f"Unexpected items in payload root: {extra_items}. " f"Only allowed: {allowed_root_items}")

    # Check required files exist
    required_files = ["manifest.json", "mini_runner.py"]
    for required in required_files:
        if not (payload_dir / required).exists():
            raise ValueError(f"Required file missing: {required}")

    # Validate manifest.json structure
    manifest_path = payload_dir / "manifest.json"
    try:
        with open(manifest_path) as f:
            manifest_data = json.load(f)

        # Check required fields
        required_fields = ["version", "files", "entry_point"]
        for field in required_fields:
            if field not in manifest_data:
                raise ValueError(f"Manifest missing required field: {field}")

        # Validate entry point
        if manifest_data["entry_point"] != "mini_runner.py":
            raise ValueError(f"Invalid entry_point: {manifest_data['entry_point']}. " "Must be 'mini_runner.py'")

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid manifest.json: {e}") from e

    # If cfg directory exists, validate it
    cfg_dir = payload_dir / "cfg"
    if cfg_dir.exists():
        if not cfg_dir.is_dir():
            raise ValueError("cfg must be a directory")

        # Check that cfg only contains JSON files
        for item in cfg_dir.iterdir():
            if item.is_file() and not item.suffix == ".json":
                raise ValueError(f"Non-JSON file in cfg directory: {item.name}")
            elif item.is_dir():
                raise ValueError(f"Subdirectory not allowed in cfg: {item.name}")
