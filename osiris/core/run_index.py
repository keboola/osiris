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

"""Run index management for tracking pipeline executions (ADR-0028)."""

from dataclasses import asdict, dataclass
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
from typing import Any


@dataclass
class RunRecord:
    """Record of a pipeline run."""

    run_id: str
    pipeline_slug: str
    profile: str
    manifest_hash: str
    manifest_short: str
    run_ts: str
    status: str
    duration_ms: int
    run_logs_path: str
    aiop_path: str
    build_manifest_path: str
    tags: list[str]
    branch: str = ""
    user: str = ""
    git_commit: str = ""
    runtime_env: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class RunIndexWriter:
    """Thread-safe and process-safe writer for run indexes."""

    def __init__(self, index_dir: Path):
        """Initialize index writer.

        Args:
            index_dir: Index directory path
        """
        self.index_dir = index_dir
        self.index_dir.mkdir(parents=True, exist_ok=True)

        self.runs_jsonl = index_dir / "runs.jsonl"
        self.by_pipeline_dir = index_dir / "by_pipeline"
        self.latest_dir = index_dir / "latest"

        self.by_pipeline_dir.mkdir(parents=True, exist_ok=True)
        self.latest_dir.mkdir(parents=True, exist_ok=True)

    def append(self, record: RunRecord) -> None:
        """Append run record to indexes.

        Writes to:
        - .osiris/index/runs.jsonl (all runs)
        - .osiris/index/by_pipeline/<slug>.jsonl (per-pipeline)
        - .osiris/index/latest/<slug>.txt (latest manifest pointer)

        Args:
            record: Run record to append

        Raises:
            ValueError: If manifest_hash contains algorithm prefix (e.g., "sha256:")
        """
        # Validate manifest_hash is pure hex (no algorithm prefix)
        if ":" in record.manifest_hash:
            raise ValueError(f"manifest_hash must be pure hex (no algorithm prefix): {record.manifest_hash}")

        # Write to main index
        self._append_jsonl(self.runs_jsonl, record.to_dict())

        # Write to per-pipeline index
        pipeline_index = self.by_pipeline_dir / f"{record.pipeline_slug}.jsonl"
        self._append_jsonl(pipeline_index, record.to_dict())

        # Update latest pointer
        self._update_latest_pointer(
            record.pipeline_slug, record.build_manifest_path, record.manifest_hash, record.profile
        )

    def write_latest_manifest(self, pipeline_slug: str, profile: str, manifest_path: str, manifest_hash: str) -> None:
        """Write latest manifest pointer for a pipeline.

        Args:
            pipeline_slug: Pipeline identifier
            profile: Profile name
            manifest_path: Path to manifest file
            manifest_hash: Manifest hash
        """
        self._update_latest_pointer(pipeline_slug, manifest_path, manifest_hash, profile)

    def _append_jsonl(self, path: Path, record: dict[str, Any]) -> None:
        """Append record to JSONL file with file locking.

        Args:
            path: JSONL file path
            record: Record dictionary
        """
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Open file in append mode with exclusive lock
        with open(path, "a") as f:
            # Acquire exclusive lock
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                # Write record
                json.dump(record, f, separators=(",", ":"))
                f.write("\n")
                # Flush to disk
                f.flush()
                os.fsync(f.fileno())
            finally:
                # Release lock
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def _update_latest_pointer(self, pipeline_slug: str, manifest_path: str, manifest_hash: str, profile: str) -> None:
        """Update latest manifest pointer.

        File format (3 lines):
        1. manifest_path
        2. manifest_hash
        3. profile

        Args:
            pipeline_slug: Pipeline identifier
            manifest_path: Path to manifest
            manifest_hash: Manifest hash
            profile: Profile name
        """
        latest_file = self.latest_dir / f"{pipeline_slug}.txt"

        # Write atomically using temp file
        temp_file = latest_file.with_suffix(".tmp")

        with open(temp_file, "w") as f:
            f.write(f"{manifest_path}\n")
            f.write(f"{manifest_hash}\n")
            f.write(f"{profile}\n")
            f.flush()
            os.fsync(f.fileno())

        # Atomic rename
        temp_file.replace(latest_file)


class RunIndexReader:
    """Reader for run indexes."""

    def __init__(self, index_dir: Path):
        """Initialize index reader.

        Args:
            index_dir: Index directory path
        """
        self.index_dir = index_dir
        self.runs_jsonl = index_dir / "runs.jsonl"
        self.by_pipeline_dir = index_dir / "by_pipeline"
        self.latest_dir = index_dir / "latest"

    def list_runs(
        self, pipeline_slug: str | None = None, profile: str | None = None, limit: int = 20
    ) -> list[RunRecord]:
        """List runs with optional filtering.

        Args:
            pipeline_slug: Filter by pipeline slug
            profile: Filter by profile
            limit: Maximum number of runs to return

        Returns:
            List of run records (newest first)
        """
        records = []

        # Choose index file
        if pipeline_slug:
            index_file = self.by_pipeline_dir / f"{pipeline_slug}.jsonl"
        else:
            index_file = self.runs_jsonl

        if not index_file.exists():
            return []

        # Read records
        with open(index_file) as f:
            for line in f:
                if line.strip():
                    record_dict = json.loads(line)
                    record = RunRecord(**record_dict)

                    # Apply filters
                    if profile and record.profile != profile:
                        continue

                    records.append(record)

        # Sort newest first and limit
        records.reverse()
        return records[:limit]

    def get_run(self, run_id: str) -> RunRecord | None:
        """Get specific run by ID.

        Args:
            run_id: Run identifier

        Returns:
            Run record or None if not found
        """
        if not self.runs_jsonl.exists():
            return None

        with open(self.runs_jsonl) as f:
            for line in f:
                if line.strip():
                    record_dict = json.loads(line)
                    if record_dict.get("run_id") == run_id:
                        return RunRecord(**record_dict)

        return None

    def get_latest_manifest(self, pipeline_slug: str) -> tuple[str, str, str] | None:
        """Get latest manifest info for pipeline.

        Args:
            pipeline_slug: Pipeline identifier

        Returns:
            Tuple of (manifest_path, manifest_hash, profile) or None if not found
        """
        latest_file = self.latest_dir / f"{pipeline_slug}.txt"

        if not latest_file.exists():
            return None

        with open(latest_file) as f:
            lines = f.readlines()
            if len(lines) >= 3:
                manifest_path = lines[0].strip()
                manifest_hash = lines[1].strip()
                profile = lines[2].strip()
                return manifest_path, manifest_hash, profile

        return None

    def query_runs(
        self,
        pipeline_slug: str | None = None,
        profile: str | None = None,
        tag: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[RunRecord]:
        """Query runs with multiple filters.

        Args:
            pipeline_slug: Filter by pipeline slug
            profile: Filter by profile
            tag: Filter by tag
            since: Filter by start time (runs started after this time)
            limit: Maximum number of runs to return

        Returns:
            List of matching run records (newest first)
        """
        records = []

        # Choose index file
        if pipeline_slug:
            index_file = self.by_pipeline_dir / f"{pipeline_slug}.jsonl"
        else:
            index_file = self.runs_jsonl

        if not index_file.exists():
            return []

        # Read records
        with open(index_file) as f:
            for line in f:
                if line.strip():
                    record_dict = json.loads(line)

                    # Apply filters
                    if profile and record_dict.get("profile") != profile:
                        continue

                    if tag:
                        tags = record_dict.get("tags", [])
                        if tag not in tags:
                            continue

                    if since:
                        run_ts = record_dict.get("run_ts", "")
                        if run_ts:
                            try:
                                run_time = datetime.fromisoformat(run_ts.replace("Z", "+00:00"))
                                if run_time < since:
                                    continue
                            except ValueError:
                                continue

                    record = RunRecord(**record_dict)
                    records.append(record)

        # Sort newest first and limit
        records.reverse()
        return records[:limit]


def latest_manifest_path(index_dir: Path, pipeline_slug: str) -> Path | None:
    """Get path to latest compiled manifest for a pipeline.

    Args:
        index_dir: Index directory
        pipeline_slug: Pipeline identifier

    Returns:
        Path to manifest file or None if not found
    """
    reader = RunIndexReader(index_dir)
    result = reader.get_latest_manifest(pipeline_slug)

    if result:
        manifest_path, _, _ = result
        return Path(manifest_path)

    return None
