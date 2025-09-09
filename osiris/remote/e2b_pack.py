"""Payload builder for E2B sandbox execution.

Builds a minimal, allowlisted payload for remote execution.
"""

import hashlib
import json
import tarfile
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class PayloadManifest:
    """Manifest of files included in the payload."""

    files: List[Dict[str, Any]]
    total_size_bytes: int
    sha256: str
    created_at: str


@dataclass
class RunConfig:
    """Configuration for running the pipeline."""

    seed: Optional[int] = None
    profile: bool = False
    params: Dict[str, Any] = None
    flags: Dict[str, bool] = None

    def __post_init__(self):
        if self.params is None:
            self.params = {}
        if self.flags is None:
            self.flags = {}


class PayloadBuilder:
    """Builds payload tarball for E2B execution."""

    # Strict allowlist of files to include
    ALLOWED_FILES = {
        "manifest.json",  # Compiled manifest
        "mini_runner.py",  # Minimal runner script
        "requirements.txt",  # Python dependencies
        "run_config.json",  # Runtime configuration
    }

    # Maximum payload size (10 MB)
    MAX_PAYLOAD_SIZE = 10 * 1024 * 1024

    def __init__(self, session_dir: Path, build_dir: Path):
        """Initialize payload builder.

        Args:
            session_dir: Session directory with compiled manifest
            build_dir: Directory to build payload in
        """
        self.session_dir = session_dir
        self.build_dir = build_dir
        self.payload_dir = build_dir / "e2b"
        self.payload_dir.mkdir(parents=True, exist_ok=True)

    def build(
        self, manifest_path: Path, run_config: RunConfig, mini_runner_path: Optional[Path] = None
    ) -> Path:
        """Build payload tarball.

        Args:
            manifest_path: Path to compiled manifest.json
            run_config: Runtime configuration
            mini_runner_path: Optional path to custom mini_runner.py

        Returns:
            Path to generated payload.tgz
        """
        # Clean payload directory
        for item in self.payload_dir.iterdir():
            if item.is_file():
                # Check allowlist before cleaning
                if item.name not in self.ALLOWED_FILES:
                    raise ValueError(f"File not in allowlist: {item.name}")
                item.unlink()
            elif item.is_dir():
                import shutil

                shutil.rmtree(item)

        # Copy manifest (convert YAML to JSON)
        manifest_dest = self.payload_dir / "manifest.json"
        with open(manifest_path) as src, open(manifest_dest, "w") as dst:
            manifest_data = yaml.safe_load(src)
            json.dump(manifest_data, dst, indent=2)

        # Create or copy mini_runner.py
        runner_dest = self.payload_dir / "mini_runner.py"
        if mini_runner_path and mini_runner_path.exists():
            with open(mini_runner_path) as src, open(runner_dest, "w") as dst:
                dst.write(src.read())
        else:
            # Create minimal runner
            self._create_mini_runner(runner_dest)

        # Create requirements.txt with minimal dependencies
        self._create_requirements(self.payload_dir / "requirements.txt")

        # Write run configuration
        config_dest = self.payload_dir / "run_config.json"
        with open(config_dest, "w") as f:
            json.dump(asdict(run_config), f, indent=2)

        # Verify allowlist
        for file_path in self.payload_dir.iterdir():
            if file_path.is_file() and file_path.name not in self.ALLOWED_FILES:
                raise ValueError(f"File not in allowlist: {file_path.name}")

        # Create tarball
        tarball_path = self.build_dir / "payload.tgz"
        with tarfile.open(tarball_path, "w:gz") as tar:
            for file_path in self.payload_dir.iterdir():
                if file_path.is_file():
                    tar.add(file_path, arcname=file_path.name)

        # Check size
        size = tarball_path.stat().st_size
        if size > self.MAX_PAYLOAD_SIZE:
            raise ValueError(
                f"Payload size ({size} bytes) exceeds maximum " f"({self.MAX_PAYLOAD_SIZE} bytes)"
            )

        # Compute SHA256
        sha256 = self._compute_sha256(tarball_path)

        # Create manifest
        from datetime import datetime

        manifest = PayloadManifest(
            files=[
                {"name": f.name, "size_bytes": f.stat().st_size}
                for f in self.payload_dir.iterdir()
                if f.is_file()
            ],
            total_size_bytes=size,
            sha256=sha256,
            created_at=datetime.utcnow().isoformat() + "Z",
        )

        # Write manifest to session metadata
        metadata_path = self.session_dir / "metadata.json"
        metadata = {}
        if metadata_path.exists():
            with open(metadata_path) as f:
                metadata = json.load(f)

        metadata["remote"] = {"payload": asdict(manifest)}

        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        return tarball_path

    def _create_mini_runner(self, path: Path) -> None:
        """Create minimal runner script."""
        runner_code = '''#!/usr/bin/env python3
"""Minimal runner for executing Osiris manifests in E2B sandbox."""

import json
import logging
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('osiris.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def main():
    """Execute manifest using minimal runtime."""
    logger.info("Starting mini runner")

    # Load manifest
    manifest_path = Path("manifest.json")
    if not manifest_path.exists():
        logger.error("Manifest not found")
        sys.exit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    # Load run config
    config_path = Path("run_config.json")
    config = {}
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)

    # Initialize event logging
    events_file = open("events.jsonl", "w")
    metrics_file = open("metrics.jsonl", "w")

    # Log start event
    from datetime import datetime
    start_event = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "event": "run_start",
        "manifest": manifest.get("name", "unknown")
    }
    events_file.write(json.dumps(start_event) + "\\n")
    events_file.flush()

    # Execute steps (simplified - real implementation would use drivers)
    total_steps = len(manifest.get("steps", []))
    completed_steps = 0

    for step in manifest.get("steps", []):
        step_event = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "event": "step_start",
            "step_id": step.get("id"),
            "component": step.get("component")
        }
        events_file.write(json.dumps(step_event) + "\\n")
        events_file.flush()

        # Simulate step execution
        import time
        time.sleep(0.1)  # Placeholder for actual execution

        completed_steps += 1
        complete_event = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "event": "step_complete",
            "step_id": step.get("id")
        }
        events_file.write(json.dumps(complete_event) + "\\n")
        events_file.flush()

    # Log end event
    end_event = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "event": "run_end",
        "steps_total": total_steps,
        "steps_completed": completed_steps,
        "status": "success" if completed_steps == total_steps else "partial"
    }
    events_file.write(json.dumps(end_event) + "\\n")
    events_file.flush()

    # Write a sample metric
    metric = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "metric": "steps_completed",
        "value": completed_steps
    }
    metrics_file.write(json.dumps(metric) + "\\n")
    metrics_file.flush()

    events_file.close()
    metrics_file.close()

    logger.info(f"Execution complete: {completed_steps}/{total_steps} steps")
    return 0 if completed_steps == total_steps else 1


if __name__ == "__main__":
    sys.exit(main())
'''
        with open(path, "w") as f:
            f.write(runner_code)
        path.chmod(0o755)

    def _create_requirements(self, path: Path) -> None:
        """Create minimal requirements.txt."""
        # Minimal set for running manifests
        requirements = [
            "duckdb==1.1.3",
            "pandas==2.2.3",
            "pymysql==1.1.1",
            "sqlalchemy==2.0.36",
            "supabase==2.10.0",
            "python-dotenv==1.0.1",
        ]

        with open(path, "w") as f:
            f.write("\n".join(requirements))

    def _compute_sha256(self, file_path: Path) -> str:
        """Compute SHA256 hash of file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def validate_payload(self, tarball_path: Path) -> PayloadManifest:
        """Validate payload contents and return manifest.

        Args:
            tarball_path: Path to payload.tgz

        Returns:
            PayloadManifest with validation results
        """
        # Extract to temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Extract tarball
            with tarfile.open(tarball_path, "r:gz") as tar:
                tar.extractall(temp_path)  # nosec B202 - controlled validation context

            # Check files against allowlist
            extracted_files = list(temp_path.iterdir())
            for file_path in extracted_files:
                if file_path.is_file() and file_path.name not in self.ALLOWED_FILES:
                    raise ValueError(f"Unauthorized file in payload: {file_path.name}")

            # Compute size and hash
            size = tarball_path.stat().st_size
            sha256 = self._compute_sha256(tarball_path)

            from datetime import datetime

            return PayloadManifest(
                files=[
                    {"name": f.name, "size_bytes": f.stat().st_size}
                    for f in extracted_files
                    if f.is_file()
                ],
                total_size_bytes=size,
                sha256=sha256,
                created_at=datetime.utcnow().isoformat() + "Z",
            )
