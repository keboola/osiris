"""AIOP automatic export and indexing functionality."""

import datetime
import gzip
import json
from pathlib import Path
import shutil
from typing import Any

from .config import render_path, resolve_aiop_config


def export_aiop_auto(
    session_id: str,
    manifest_hash: str | None = None,
    status: str = "completed",
    end_time: datetime.datetime | None = None,
    fs_contract=None,
    pipeline_slug: str | None = None,
    profile: str | None = None,
    run_id: str | None = None,
    manifest_short: str | None = None,
    session_dir: Path | None = None,
) -> tuple[bool, str | None]:
    """Automatically export AIOP at the end of a run.

    Args:
        session_id: Session ID
        manifest_hash: Hash of the manifest (if available)
        status: Run status (completed, failed, partial)
        end_time: End time of the run
        fs_contract: Optional FilesystemContract for path resolution
        pipeline_slug: Pipeline identifier
        profile: Profile name
        run_id: Run identifier
        manifest_short: Short manifest hash
        session_dir: Path to session directory (overrides session_id lookup)

    Returns:
        Tuple of (success, error_message)
    """
    try:

        # Get AIOP configuration
        config, config_sources = resolve_aiop_config()

        # Check if AIOP is enabled
        if not config.get("enabled", True):
            return True, None

        # Get output paths from filesystem contract if available
        if fs_contract and pipeline_slug and run_id and manifest_hash and manifest_short:
            paths = fs_contract.aiop_paths(
                pipeline_slug=pipeline_slug,
                manifest_hash=manifest_hash,
                manifest_short=manifest_short,
                run_id=run_id,
                profile=profile,
            )
            core_path = str(paths["summary"])
            run_card_path = str(paths["run_card"]) if config.get("run_card", True) else None
            annex_dir = paths["annex"] if config.get("annex", {}).get("enabled", False) else None
        else:
            # Legacy path mode - DEPRECATED
            ts = end_time or datetime.datetime.utcnow()
            ctx = {
                "session_id": session_id,
                "ts": ts,
                "manifest_hash": manifest_hash or "unknown",
                "status": status,
            }
            ts_format = config.get("path_vars", {}).get("ts_format", "%Y%m%d-%H%M%S")
            core_path = render_path(config["output"]["core_path"], ctx, ts_format)
            run_card_path = None
            if config.get("run_card", True):
                run_card_path = render_path(config["output"]["run_card_path"], ctx, ts_format)
            annex_dir = None

        # Create parent directories
        Path(core_path).parent.mkdir(parents=True, exist_ok=True)
        if run_card_path:
            Path(run_card_path).parent.mkdir(parents=True, exist_ok=True)

        # Read session data (similar to logs.py aiop_export)
        import json

        import yaml

        from ..core.session_reader import SessionReader

        # Use provided session_dir or fallback to legacy logs/ lookup
        if session_dir:
            session_path = session_dir
            logs_dir = session_path.parent
        else:
            # Legacy fallback - DEPRECATED
            logs_dir = Path("run_logs")
            session_path = logs_dir / session_id

        if not session_path.exists():
            return False, f"Session not found: {session_path}"

        # Read session summary
        reader = SessionReader(str(logs_dir))
        session_summary = reader.read_session(session_id)

        # Load events
        events = []
        events_file = session_path / "events.jsonl"
        if events_file.exists():
            with open(events_file) as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))

        # Load metrics
        metrics = []
        metrics_file = session_path / "metrics.jsonl"
        if metrics_file.exists():
            with open(metrics_file) as f:
                for line in f:
                    if line.strip():
                        metrics.append(json.loads(line))

        # Get artifacts
        artifacts = []
        artifacts_dir = session_path / "artifacts"
        if artifacts_dir.exists():
            for artifact_file in artifacts_dir.iterdir():
                if artifact_file.is_file():
                    artifacts.append(artifact_file)

        # Get manifest - check session root first (where it actually is), then other locations
        manifest = {}
        # First try session root
        manifest_file = session_path / "manifest.yaml"
        if not manifest_file.exists():
            # Then try compiled directory
            compiled_dir = session_path / "compiled"
            manifest_file = compiled_dir / "manifest.yaml" if compiled_dir.exists() else None
        if not manifest_file or not manifest_file.exists():
            # Finally try artifacts directory
            manifest_file = artifacts_dir / "manifest.yaml" if artifacts_dir.exists() else None

        if manifest_file and manifest_file.exists():
            with open(manifest_file) as f:
                manifest = yaml.safe_load(f) or {}

        # The manifest already has 'name' and 'metadata' at root level from compilation
        # No need to extract from pipeline.id or add it - it's already there!
        # Just ensure manifest_hash is available for build_aiop to find
        if not manifest.get("manifest_hash"):
            # Extract manifest hash from meta.manifest_hash (canonical source)
            from osiris.core.fs_paths import normalize_manifest_hash

            manifest_hash = manifest.get("meta", {}).get("manifest_hash", "unknown")
            if manifest_hash != "unknown":
                # Normalize to pure hex (remove any sha256: prefix)
                manifest_hash = normalize_manifest_hash(manifest_hash)
                # Add to root for easy access by build_aiop
                manifest["manifest_hash"] = manifest_hash

        # Extract start and end times from events if not in summary
        started_at = session_summary.started_at if session_summary else None
        completed_at = session_summary.finished_at if session_summary else end_time

        # Look for run_start and run_end events as fallback
        if not started_at or not completed_at:
            for event in events:
                if event.get("event") == "run_start" and not started_at:
                    started_at = event.get("timestamp")
                elif event.get("event") in ["run_end", "run_error"] and not completed_at:
                    completed_at = event.get("timestamp")

        # Build session data (convert datetime to ISO string for JSON serialization)
        session_data = {
            "session_id": session_id,
            "started_at": (started_at.isoformat() if hasattr(started_at, "isoformat") else started_at),
            "completed_at": (
                (completed_at or end_time).isoformat()
                if hasattr(completed_at or end_time, "isoformat")
                else (completed_at or end_time)
            ),
            "status": status,  # Use provided status
            "environment": ("e2b" if session_summary and session_summary.adapter_type == "E2B" else "local"),
        }

        # Build AIOP using existing builder
        from .run_export_v2 import build_aiop as build_aiop_func

        aiop = build_aiop_func(
            session_data=session_data,
            manifest=manifest,
            events=events,
            metrics=metrics,
            artifacts=artifacts,
            config=config,
            show_progress=False,
            config_sources=config_sources,
        )

        # Convert to JSON
        import json

        aiop_json = json.dumps(aiop, indent=2, ensure_ascii=False)

        # Write Core JSON
        with open(core_path, "w") as f:
            f.write(aiop_json)

        core_size = len(aiop_json.encode("utf-8"))

        # Write run-card if enabled
        if run_card_path:
            # Generate markdown run-card
            from .run_export_v2 import generate_markdown_runcard

            run_card_md = generate_markdown_runcard(aiop)
            with open(run_card_path, "w") as f:
                f.write(run_card_md)

        # Handle Annex if enabled
        annex_size = 0
        if annex_dir and config.get("annex", {}).get("enabled", False):
            Path(annex_dir).mkdir(parents=True, exist_ok=True)
            annex_size = _export_annex(session_id, annex_dir, config.get("annex", {}), session_path=session_path)

        # Extract started_at, total_rows, and duration_ms from AIOP for index
        started_at = None
        if "run" in aiop and "started_at" in aiop["run"]:
            started_at_str = aiop["run"]["started_at"]
            if started_at_str:
                try:
                    started_at = datetime.datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
                except Exception:
                    pass  # Keep None if parsing fails

        total_rows = None
        if "run" in aiop and "total_rows" in aiop["run"]:
            total_rows = aiop["run"]["total_rows"]

        duration_ms = None
        if "run" in aiop and "duration_ms" in aiop["run"]:
            duration_ms = aiop["run"]["duration_ms"]

        # Update indexes if enabled
        if config.get("index", {}).get("enabled", True):
            _update_indexes(
                session_id=session_id,
                manifest_hash=manifest_hash,
                status=status,
                started_at=started_at,  # Now extracted from AIOP
                ended_at=completed_at or end_time,
                total_rows=total_rows,  # Now extracted from AIOP
                duration_ms=duration_ms,  # Now extracted from AIOP
                bytes_core=core_size,
                bytes_annex=annex_size,
                core_path=core_path,
                run_card_path=run_card_path,
                annex_dir=annex_dir,
                config=config,
            )

            # Update latest symlink (best-effort)
            latest_symlink = config.get("index", {}).get("latest_symlink", "logs/aiop/latest")
            if latest_symlink and core_path:
                run_dir = str(Path(core_path).parent)
                _update_latest_symlink(latest_symlink, run_dir)

        # Apply retention policies
        if config.get("retention", {}).get("keep_runs", 0) > 0:
            _apply_retention(config)

        return True, None

    except Exception as e:
        return False, str(e)


def _export_annex(
    session_id: str, annex_dir: str, annex_config: dict[str, Any], session_path: Path | None = None
) -> int:
    """Export NDJSON annex shards.

    Args:
        session_id: Session ID
        annex_dir: Directory for annex files
        annex_config: Annex configuration
        session_path: Optional path to session directory (overrides session_id lookup)

    Returns:
        Total bytes written to annex
    """
    total_bytes = 0
    compress = annex_config.get("compress", "none")

    # Read session data
    if session_path:
        session_dir = session_path
    else:
        session_dir = Path(f"run_logs/{session_id}")  # Legacy fallback

    if not session_dir.exists():
        return 0

    # Export timeline events
    events_file = session_dir / "events.jsonl"
    if events_file.exists():
        target = Path(annex_dir) / "timeline.ndjson"
        if compress == "gzip":
            target = target.with_suffix(".ndjson.gz")
            with open(events_file, "rb") as src, gzip.open(target, "wb") as dst:
                dst.write(src.read())
        else:
            shutil.copy(events_file, target)
        total_bytes += target.stat().st_size

    # Export metrics
    metrics_file = session_dir / "metrics.jsonl"
    if metrics_file.exists():
        target = Path(annex_dir) / "metrics.ndjson"
        if compress == "gzip":
            target = target.with_suffix(".ndjson.gz")
            with open(metrics_file, "rb") as src, gzip.open(target, "wb") as dst:
                dst.write(src.read())
        else:
            shutil.copy(metrics_file, target)
        total_bytes += target.stat().st_size

    # Export errors (if any) - extract from events
    errors = []
    if events_file.exists():
        with open(events_file) as f:
            for line in f:
                if line.strip():
                    try:
                        event = json.loads(line)
                        if event.get("type") == "ERROR" or event.get("event") == "error":
                            errors.append(event)
                    except Exception:
                        pass

    if errors:
        target = Path(annex_dir) / "errors.ndjson"
        if compress == "gzip":
            target = target.with_suffix(".ndjson.gz")
            with gzip.open(target, "wt") as f:
                for error in errors:
                    f.write(json.dumps(error) + "\n")
        else:
            with open(target, "w") as f:
                for error in errors:
                    f.write(json.dumps(error) + "\n")
        total_bytes += target.stat().st_size

    # Export chat logs if enabled in configuration
    # Get config from resolve_aiop_config if not passed
    from .config import resolve_aiop_config

    config, _ = resolve_aiop_config()

    if config.get("narrative", {}).get("session_chat", {}).get("enabled", False):
        # Look for chat logs
        chat_log_path = session_dir / "artifacts" / "chat_log.json"
        if not chat_log_path.exists():
            chat_log_path = session_dir / "chat_log.json"

        if chat_log_path.exists():
            # Load and redact chat logs
            try:
                with open(chat_log_path) as f:
                    chat_logs = json.load(f)

                # Apply redaction based on mode
                mode = config.get("narrative", {}).get("session_chat", {}).get("mode", "masked")
                max_chars = config.get("narrative", {}).get("session_chat", {}).get("max_chars", 10000)

                if mode == "masked":
                    # Apply PII redaction
                    from .run_export_v2 import redact_secrets

                    redacted_logs = []
                    total_chars = 0
                    for entry in chat_logs:
                        if total_chars >= max_chars:
                            break
                        redacted_entry = redact_secrets(entry)
                        content_len = len(str(redacted_entry.get("content", "")))
                        if total_chars + content_len > max_chars:
                            remaining = max_chars - total_chars
                            redacted_entry["content"] = redacted_entry.get("content", "")[:remaining] + "..."
                            redacted_logs.append(redacted_entry)
                            break
                        redacted_logs.append(redacted_entry)
                        total_chars += content_len
                    chat_logs = redacted_logs
                elif mode != "off":
                    # Just apply truncation
                    truncated_logs = []
                    total_chars = 0
                    for entry in chat_logs:
                        if total_chars >= max_chars:
                            break
                        content_len = len(str(entry.get("content", "")))
                        if total_chars + content_len > max_chars:
                            remaining = max_chars - total_chars
                            entry_copy = entry.copy()
                            entry_copy["content"] = entry.get("content", "")[:remaining] + "..."
                            truncated_logs.append(entry_copy)
                            break
                        truncated_logs.append(entry)
                        total_chars += content_len
                    chat_logs = truncated_logs

                # Write to annex
                if mode != "off" and chat_logs:
                    target = Path(annex_dir) / "chat_logs.ndjson"
                    if compress == "gzip":
                        target = target.with_suffix(".ndjson.gz")
                        with gzip.open(target, "wt") as f:
                            for entry in chat_logs:
                                f.write(json.dumps(entry) + "\n")
                    else:
                        with open(target, "w") as f:
                            for entry in chat_logs:
                                f.write(json.dumps(entry) + "\n")
                    total_bytes += target.stat().st_size
            except Exception:
                pass  # Best effort

    return total_bytes


def _update_indexes(
    session_id: str,
    manifest_hash: str | None,
    status: str,
    started_at: datetime.datetime | None,
    ended_at: datetime.datetime,
    total_rows: int | None,
    duration_ms: int | None,
    bytes_core: int,
    bytes_annex: int,
    core_path: str,
    run_card_path: str | None,
    annex_dir: str | None,
    config: dict[str, Any],
) -> None:
    """Update index files with run information.

    Args:
        Various run metadata and paths
    """
    # Calculate duration_ms if not provided but we have timestamps
    if duration_ms is None and started_at and ended_at:
        duration_ms = int((ended_at - started_at).total_seconds() * 1000)

    # Prepare index record with enriched fields
    record = {
        "session_id": session_id,
        "manifest_hash": manifest_hash or "unknown",
        "status": status,
        "started_at": started_at.isoformat() if started_at else None,
        "ended_at": ended_at.isoformat() if ended_at else None,
        "duration_ms": duration_ms,
        "total_rows": total_rows if total_rows is not None else 0,
        "errors_count": 0,  # Would need to be passed in or calculated
        "bytes_core": bytes_core,
        "bytes_annex": bytes_annex,
        "core_path": core_path,
        "run_card_path": run_card_path,
        "annex_dir": annex_dir,
    }

    # Append to runs.jsonl
    runs_jsonl = config.get("index", {}).get("runs_jsonl", "logs/aiop/index/runs.jsonl")
    Path(runs_jsonl).parent.mkdir(parents=True, exist_ok=True)
    with open(runs_jsonl, "a") as f:
        f.write(json.dumps(record) + "\n")

    # Append to by_pipeline index
    if manifest_hash and manifest_hash != "unknown":
        by_pipeline_dir = config.get("index", {}).get("by_pipeline_dir", "logs/aiop/index/by_pipeline")
        Path(by_pipeline_dir).mkdir(parents=True, exist_ok=True)
        pipeline_index = Path(by_pipeline_dir) / f"{manifest_hash}.jsonl"
        with open(pipeline_index, "a") as f:
            f.write(json.dumps(record) + "\n")


def _update_latest_symlink(latest_path: str, run_dir: str) -> None:
    """Update the latest symlink to point to the current run directory.

    Args:
        latest_path: Path to the latest symlink/file
        run_dir: Directory to point to
    """
    import os
    import platform

    try:
        latest_path = Path(latest_path)
        run_dir = Path(run_dir)

        # Ensure parent directory exists
        latest_path.parent.mkdir(parents=True, exist_ok=True)

        # Remove old symlink/file if exists
        if latest_path.exists() or latest_path.is_symlink():
            latest_path.unlink()

        # Try to create symlink (POSIX systems)
        if platform.system() != "Windows":
            try:
                # Use relative path for symlink for better portability
                rel_path = os.path.relpath(str(run_dir), str(latest_path.parent))
                latest_path.symlink_to(rel_path)
                return
            except (OSError, NotImplementedError):
                # Fall through to fallback
                pass

        # Fallback: write path to text file (Windows or symlink failure)
        with open(latest_path, "w") as f:
            f.write(str(run_dir.absolute()) + "\n")

    except Exception:
        # Best-effort, ignore failures silently
        pass


def _apply_retention(config: dict[str, Any]) -> None:
    """Apply retention policies to AIOP outputs.

    Args:
        config: AIOP configuration
    """
    keep_runs = config.get("retention", {}).get("keep_runs", 50)
    annex_keep_days = config.get("retention", {}).get("annex_keep_days", 14)

    # Find all run directories under logs/aiop/
    aiop_dir = Path("logs/aiop")
    if not aiop_dir.exists():
        return

    # Get all session directories (excluding index and latest)
    run_dirs = []
    for item in aiop_dir.iterdir():
        if item.is_dir() and item.name not in ["index", "latest"]:
            # Get modification time for sorting
            mtime = item.stat().st_mtime
            run_dirs.append((mtime, item))

    # Sort by modification time (oldest first)
    run_dirs.sort()

    # Remove oldest directories if exceeding keep_runs
    if keep_runs > 0 and len(run_dirs) > keep_runs:
        dirs_to_remove = run_dirs[: len(run_dirs) - keep_runs]
        for _, dir_path in dirs_to_remove:
            shutil.rmtree(dir_path, ignore_errors=True)

    # Remove old annex files if configured
    if annex_keep_days > 0:
        cutoff_time = datetime.datetime.utcnow() - datetime.timedelta(days=annex_keep_days)
        cutoff_timestamp = cutoff_time.timestamp()

        for _, dir_path in run_dirs:
            annex_dir = dir_path / "annex"
            if annex_dir.exists():
                # Check if annex is older than threshold
                if annex_dir.stat().st_mtime < cutoff_timestamp:
                    shutil.rmtree(annex_dir, ignore_errors=True)


def prune_aiop() -> tuple[bool, str | None]:
    """Manually run AIOP retention policies.

    Returns:
        Tuple of (success, error_message)
    """
    try:
        config, _ = resolve_aiop_config()
        _apply_retention(config)
        return True, None
    except Exception as e:
        return False, str(e)
