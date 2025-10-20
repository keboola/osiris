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

"""Retention policy execution for run logs and AIOP (ADR-0028)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil
from typing import Any

from osiris.core.fs_config import FilesystemConfig


@dataclass
class RetentionAction:
    """Action to perform during retention."""

    action_type: str  # "delete_run_logs" | "delete_annex"
    path: Path
    reason: str
    size_bytes: int = 0
    age_days: int | None = None

    @property
    def action(self) -> str:
        """Alias for action_type."""
        return self.action_type

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action": self.action_type,
            "path": str(self.path),
            "reason": self.reason,
            "size_bytes": self.size_bytes,
            "age_days": self.age_days,
        }

    def execute(self) -> None:
        """Execute the retention action."""
        if self.path.is_dir():
            shutil.rmtree(self.path, ignore_errors=True)
        elif self.path.is_file():
            self.path.unlink(missing_ok=True)


class RetentionPlan:
    """Compute and execute retention plans."""

    def __init__(self, fs_config: FilesystemConfig):
        """Initialize retention plan.

        Args:
            fs_config: Filesystem configuration
        """
        self.fs_config = fs_config
        self.retention_config = fs_config.retention

    def compute(
        self,
        run_logs_days: int | None = None,
        keep_runs: int | None = None,
        annex_days: int | None = None,
    ) -> list[RetentionAction]:
        """Compute retention actions.

        Args:
            run_logs_days: Override for run logs retention days
            keep_runs: Override for number of runs to keep per pipeline
            annex_days: Override for annex retention days

        Returns:
            List of retention actions to perform
        """
        actions = []

        # Use overrides or config defaults
        run_logs_days = run_logs_days if run_logs_days is not None else self.retention_config.run_logs_days
        keep_runs = keep_runs if keep_runs is not None else self.retention_config.aiop_keep_runs_per_pipeline
        annex_days = annex_days if annex_days is not None else self.retention_config.annex_keep_days

        # Compute cutoff times
        now = datetime.now(UTC)
        run_logs_cutoff = now - timedelta(days=run_logs_days) if run_logs_days > 0 else None
        annex_cutoff = now - timedelta(days=annex_days) if annex_days > 0 else None

        # Process run logs
        if run_logs_cutoff:
            actions.extend(self._select_run_logs_for_deletion(run_logs_cutoff))

        # Process AIOP
        if keep_runs > 0:
            actions.extend(self._select_aiop_for_retention(keep_runs))

        # Process annex
        if annex_cutoff:
            actions.extend(self._select_annex_for_deletion(annex_cutoff))

        return actions

    def apply(self, actions: list[RetentionAction], dry_run: bool = True) -> dict[str, Any]:
        """Apply retention actions.

        Args:
            actions: List of actions to apply
            dry_run: If True, don't actually delete

        Returns:
            Summary of actions taken
        """
        deleted_count = 0
        deleted_bytes = 0
        errors = []

        for action in actions:
            try:
                if action.path.exists():
                    if not dry_run:
                        if action.path.is_dir():
                            shutil.rmtree(action.path)
                        else:
                            action.path.unlink()
                    deleted_count += 1
                    deleted_bytes += action.size_bytes
            except Exception as e:
                errors.append({"path": str(action.path), "error": str(e)})

        return {
            "dry_run": dry_run,
            "actions_planned": len(actions),
            "deleted_count": deleted_count,
            "deleted_bytes": deleted_bytes,
            "errors": errors,
        }

    def _select_run_logs_for_deletion(self, cutoff: datetime) -> list[RetentionAction]:
        """Select run logs directories for deletion.

        Args:
            cutoff: Cutoff time for deletion

        Returns:
            List of retention actions
        """
        actions = []
        run_logs_root = self.fs_config.resolve_path(self.fs_config.run_logs_dir)

        if not run_logs_root.exists():
            return actions

        # Walk run logs directory
        for run_dir in self._iter_run_dirs(run_logs_root):
            try:
                # Get modification time as proxy for completion time
                mtime = datetime.fromtimestamp(run_dir.stat().st_mtime, tz=UTC)

                if mtime < cutoff:
                    size = self._get_dir_size(run_dir)
                    age_days = (datetime.now(UTC) - mtime).days
                    actions.append(
                        RetentionAction(
                            action_type="delete_run_logs",
                            path=run_dir,
                            reason=f"Older than retention policy ({age_days} days old)",
                            size_bytes=size,
                            age_days=age_days,
                        )
                    )
            except Exception:  # nosec B112 - safe: best-effort cleanup, permissions/race conditions are expected
                # Skip directories we can't access (permissions, deleted, etc.)
                continue

        return actions

    def _select_aiop_for_retention(self, keep_runs: int) -> list[RetentionAction]:
        """Select AIOP runs to keep/delete based on count.

        Args:
            keep_runs: Number of runs to keep per pipeline

        Returns:
            List of retention actions
        """
        actions = []
        aiop_root = self.fs_config.resolve_path(self.fs_config.aiop_dir)

        if not aiop_root.exists():
            return actions

        # Group runs by pipeline and manifest
        for manifest_dir in self._iter_manifest_dirs(aiop_root):
            runs = self._list_runs_in_manifest(manifest_dir)

            # Keep newest runs, delete older
            if len(runs) > keep_runs:
                for run_dir in runs[keep_runs:]:
                    # Don't delete summary.json or run-card.md, only annex
                    annex_dir = run_dir / "annex"
                    if annex_dir.exists():
                        size = self._get_dir_size(annex_dir)
                        actions.append(
                            RetentionAction(
                                action_type="delete_annex",
                                path=annex_dir,
                                reason=f"Beyond keep_runs limit ({keep_runs})",
                                size_bytes=size,
                            )
                        )

        return actions

    def _select_annex_for_deletion(self, cutoff: datetime) -> list[RetentionAction]:
        """Select annex shards for deletion.

        Args:
            cutoff: Cutoff time for deletion

        Returns:
            List of retention actions
        """
        actions = []
        aiop_root = self.fs_config.resolve_path(self.fs_config.aiop_dir)

        if not aiop_root.exists():
            return actions

        # Find all annex directories
        for annex_dir in aiop_root.rglob("annex"):
            if annex_dir.is_dir():
                try:
                    mtime = datetime.fromtimestamp(annex_dir.stat().st_mtime, tz=UTC)
                    if mtime < cutoff:
                        size = self._get_dir_size(annex_dir)
                        actions.append(
                            RetentionAction(
                                action_type="delete_annex",
                                path=annex_dir,
                                reason=f"Annex older than {(datetime.now(UTC) - cutoff).days} days",
                                size_bytes=size,
                            )
                        )
                except Exception:  # nosec B112 - safe: best-effort cleanup, filesystem errors are expected
                    continue

        return actions

    def _iter_run_dirs(self, root: Path) -> list[Path]:
        """Iterate over run directories.

        Args:
            root: Root directory

        Returns:
            List of run directories
        """
        run_dirs = []
        for item in root.rglob("*"):
            if item.is_dir() and self._looks_like_run_dir(item):
                run_dirs.append(item)
        return run_dirs

    def _iter_manifest_dirs(self, root: Path) -> list[Path]:
        """Iterate over manifest directories.

        Args:
            root: Root directory

        Returns:
            List of manifest directories
        """
        manifest_dirs = []
        for item in root.rglob("*"):
            if item.is_dir() and self._looks_like_manifest_dir(item):
                manifest_dirs.append(item)
        return manifest_dirs

    def _list_runs_in_manifest(self, manifest_dir: Path) -> list[Path]:
        """List runs in manifest directory, sorted by modification time (newest first).

        Args:
            manifest_dir: Manifest directory

        Returns:
            List of run directories sorted newest first
        """
        runs = [item for item in manifest_dir.iterdir() if item.is_dir()]

        # Sort by modification time, newest first
        runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        return runs

    def _looks_like_run_dir(self, path: Path) -> bool:
        """Check if path looks like a run directory.

        Args:
            path: Path to check

        Returns:
            True if looks like run directory
        """
        # Run directories typically contain events.jsonl or osiris.log
        return (path / "events.jsonl").exists() or (path / "osiris.log").exists()

    def _looks_like_manifest_dir(self, path: Path) -> bool:
        """Check if path looks like a manifest directory.

        Args:
            path: Path to check

        Returns:
            True if looks like manifest directory
        """
        # Manifest directories contain run subdirectories
        # Simple heuristic: has subdirectories
        return any(item.is_dir() for item in path.iterdir()) if path.exists() else False

    def _get_dir_size(self, path: Path) -> int:
        """Get total size of directory.

        Args:
            path: Directory path

        Returns:
            Total size in bytes
        """
        total = 0
        try:
            for item in path.rglob("*"):
                if item.is_file():
                    total += item.stat().st_size
        except Exception:
            pass
        return total
