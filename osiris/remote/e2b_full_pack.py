"""E2B Full Source Payload Builder - Runs complete Osiris CLI in sandbox."""

import json
import logging
from pathlib import Path
import tarfile
import tempfile
from typing import Any

from osiris.core.execution_adapter import PreparedRun

logger = logging.getLogger(__name__)


def build_full_payload(prepared: PreparedRun, session_dir: Path) -> Path:
    """Build payload.tgz with full Osiris source for sandbox execution.

    Args:
        prepared: PreparedRun with manifest and configuration
        session_dir: Session directory for logs

    Returns:
        Path to generated payload.tgz
    """
    build_dir = session_dir / "e2b_build"
    build_dir.mkdir(parents=True, exist_ok=True)

    # Create staging directory
    with tempfile.TemporaryDirectory() as tmpdir:
        staging = Path(tmpdir) / "payload"
        staging.mkdir()

        # 1. Copy Osiris source tree
        _copy_osiris_source(staging)

        # 2. Copy requirements and setup files
        _copy_setup_files(staging)

        # 3. Create compiled directory with manifest and cfg files
        _create_compiled_artifacts(staging, prepared)

        # 4. Create osiris_connections.yaml (with placeholders)
        _create_connections_file(staging, prepared)

        # 5. Create prepared_run.json (metadata only)
        _create_prepared_run_metadata(staging, prepared)

        # 6. Create run.sh entrypoint
        _create_run_script(staging)

        # 7. Create requirements.txt with all runtime deps
        _create_requirements(staging)

        # Create tarball
        payload_path = build_dir / "payload.tgz"
        with tarfile.open(payload_path, "w:gz") as tar:
            tar.add(staging, arcname=".")

        # Log payload info
        size = payload_path.stat().st_size
        logger.info(f"Built full payload: {payload_path} ({size} bytes)")

        return payload_path


def _copy_osiris_source(staging: Path) -> None:
    """Copy Osiris source code to staging."""
    import shutil

    # Get repo root (parent of osiris package)
    osiris_package = Path(__file__).parent.parent  # osiris/
    repo_root = osiris_package.parent

    # Copy osiris package
    dest_osiris = staging / "osiris"
    shutil.copytree(
        osiris_package,
        dest_osiris,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "*.egg-info", ".DS_Store"),
    )

    # Copy components directory (required for driver registry)
    components_src = repo_root / "components"
    if components_src.exists():
        components_dest = staging / "components"
        shutil.copytree(
            components_src,
            components_dest,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
        )
        logger.debug(f"Copied components to {components_dest}")

    logger.debug(f"Copied osiris source to {dest_osiris}")


def _copy_setup_files(staging: Path) -> None:
    """Copy setup files from repo root."""
    import shutil

    repo_root = Path(__file__).parent.parent.parent

    # Copy pyproject.toml if exists (required for -e . install)
    if (repo_root / "pyproject.toml").exists():
        shutil.copy2(repo_root / "pyproject.toml", staging / "pyproject.toml")
        print("[DEBUG] Copied pyproject.toml to payload")

    # Copy setup.py if exists
    if (repo_root / "setup.py").exists():
        shutil.copy2(repo_root / "setup.py", staging / "setup.py")

    # Copy setup.cfg if exists
    if (repo_root / "setup.cfg").exists():
        shutil.copy2(repo_root / "setup.cfg", staging / "setup.cfg")

    # Copy README.md if exists (might be referenced in pyproject.toml)
    if (repo_root / "README.md").exists():
        shutil.copy2(repo_root / "README.md", staging / "README.md")


def _create_compiled_artifacts(staging: Path, prepared: PreparedRun) -> None:
    """Create compiled directory with manifest and cfg files at root level."""
    # Create compiled directory for manifest
    compiled_dir = staging / "compiled"
    compiled_dir.mkdir()

    # Write manifest with updated metadata for sandbox cfg resolution
    manifest_path = compiled_dir / "manifest.yaml"

    # Update plan metadata to include sandbox-relative source_manifest_path
    updated_plan = prepared.plan.copy()
    if "metadata" not in updated_plan:
        updated_plan["metadata"] = {}

    # Set source_manifest_path to the sandbox location for proper cfg resolution
    updated_plan["metadata"]["source_manifest_path"] = "./compiled/manifest.yaml"

    with open(manifest_path, "w") as f:
        import yaml

        yaml.dump(updated_plan, f)

    # Create cfg directory under compiled for proper relative resolution
    cfg_dir = compiled_dir / "cfg"
    cfg_dir.mkdir()

    for cfg_path, config in prepared.cfg_index.items():
        # cfg_path is like "cfg/extract-actors.json"
        cfg_name = Path(cfg_path).name
        cfg_file = cfg_dir / cfg_name

        # Remove any resolved_connection (contains secrets)
        clean_config = {k: v for k, v in config.items() if k != "resolved_connection"}

        with open(cfg_file, "w") as f:
            json.dump(clean_config, f, indent=2)

    logger.debug(f"Created compiled artifacts with {len(prepared.cfg_index)} cfg files")


def _create_connections_file(staging: Path, prepared: PreparedRun) -> None:
    """Create osiris_connections.yaml using actual resolved connections."""
    if not prepared.resolved_connections:
        return

    # Build connections structure from resolved_connections
    connections = {}

    for connection_ref, connection_config in prepared.resolved_connections.items():
        if connection_ref.startswith("@"):
            # Parse connection reference like @mysql.db_movies
            family, alias = connection_ref[1:].split(".", 1)
            if family not in connections:
                connections[family] = {}
            connections[family][alias] = connection_config

    # Write connections file using the actual resolved connection configurations
    if connections:
        import yaml

        with open(staging / "osiris_connections.yaml", "w") as f:
            yaml.dump({"connections": connections}, f)


def _create_prepared_run_metadata(staging: Path, prepared: PreparedRun) -> None:
    """Create prepared_run.json with metadata only (no secrets)."""
    metadata = {
        "manifest_id": prepared.plan.get("pipeline", {}).get("id", "unknown"),
        "total_steps": len(prepared.plan.get("steps", [])),
        "run_params": {k: v for k, v in prepared.run_params.items() if k not in ["env_vars", "secrets", "credentials"]},
        "constraints": prepared.constraints,
        "metadata": prepared.metadata,
    }

    with open(staging / "prepared_run.json", "w") as f:
        json.dump(metadata, f, indent=2)


def _create_run_script(staging: Path) -> None:
    """Create run.sh entrypoint script with virtualenv and driver sanity checks."""
    script_content = """#!/bin/bash
set -euo pipefail

# Helper function to log to both stdout and diag.txt
log_diag() {
    echo "$1" | tee -a remote/diag.txt
}

echo "=== E2B Osiris Full CLI Execution ==="
echo "Working directory: $(pwd)"
echo "Directory contents:"
ls -la

# Set up remote directory early for logging
mkdir -p remote/artifacts
touch remote/diag.txt

echo ""
echo "=== Creating Virtual Environment ==="
python -m venv .venv 2>&1 | tee -a remote/diag.txt
if [ $? -ne 0 ]; then
    echo "❌ Virtual environment creation failed" | tee -a remote/diag.txt
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

echo ""
echo "=== Environment Info ==="
log_diag "Python version: $(python -V)"
log_diag "Python path: $(which python)"
log_diag "Pip version: $(pip --version)"

echo ""
echo "=== Installing Dependencies ==="
pip install --upgrade pip 2>&1 | tee -a remote/diag.txt
pip install -r requirements.txt 2>&1 | tee -a remote/diag.txt
if [ $? -ne 0 ]; then
    echo "❌ Dependency installation failed" | tee -a remote/diag.txt >&2
    exit 1
fi

echo ""
echo "=== Dependency Sanity Check ==="
log_diag "=== Installed packages ==="
pip list | sort >> remote/diag.txt

echo ""
echo "=== Driver Sanity Check ==="
python -c "
import sys
sys.path.insert(0, '.')
try:
    from osiris.core.driver import DriverRegistry
    from osiris.components.registry import ComponentRegistry

    # Build driver registry like the real runner does
    registry = DriverRegistry()
    component_registry = ComponentRegistry()
    specs = component_registry.load_specs()

    # Count registered drivers
    driver_count = 0
    drivers = []

    for component_name, spec in specs.items():
        runtime_config = spec.get('x-runtime', {})
        driver_path = runtime_config.get('driver')
        if driver_path:
            drivers.append(component_name)
            driver_count += 1

    print(f'Available drivers ({driver_count}): {sorted(drivers)}')

    # Check for required drivers
    required_drivers = ['mysql.extractor', 'filesystem.csv_writer']
    missing_drivers = [d for d in required_drivers if d not in drivers]

    if missing_drivers:
        print(f'❌ Missing required drivers: {missing_drivers}', file=sys.stderr)
        sys.exit(1)
    else:
        print(f'✓ All required drivers present: {required_drivers}')

except Exception as e:
    print(f'❌ Driver sanity check failed: {e}', file=sys.stderr)
    sys.exit(1)
" 2>&1 | tee -a remote/diag.txt

# Check if driver sanity check passed
if [ $? -ne 0 ]; then
    echo "❌ Driver sanity check failed - see diag.txt" | tee -a remote/diag.txt >&2
    exit 1
fi

echo "✓ deps+drivers sanity"

echo ""
echo "=== Setting up environment ==="
# Make session root deterministic
export OSIRIS_LOGS_DIR="$PWD/logs"
echo "OSIRIS_LOGS_DIR=$OSIRIS_LOGS_DIR"
mkdir -p "$OSIRIS_LOGS_DIR"

# Note: OSIRIS_ARTIFACTS_DIR will be set to session-scoped path once session is created
# The runner will automatically use logs/run_<id>/artifacts/

echo ""
echo "=== Running Osiris CLI ==="
# Use unbuffered output and redirect to log files
python -u -m osiris.cli.main run ./compiled/manifest.yaml \
  > >(tee remote/stdout.txt) \
  2> >(tee remote/stderr.txt >&2)

# Capture exit code
EXIT_CODE=$?

echo ""
echo "=== Discovering session directory ==="
# Find the most recent session directory under logs/ (by mtime)
SESSION_DIR=""
SESSION_COUNT=$(find "$OSIRIS_LOGS_DIR" -maxdepth 1 -type d -name "run_*" 2>/dev/null | wc -l)

if [ $SESSION_COUNT -eq 0 ]; then
    echo "ERROR: No session directories found under $OSIRIS_LOGS_DIR"
    SESSION_DIR=""
elif [ $SESSION_COUNT -eq 1 ]; then
    SESSION_DIR=$(find "$OSIRIS_LOGS_DIR" -maxdepth 1 -type d -name "run_*")
    echo "Found single session directory: $SESSION_DIR"
else
    # Multiple sessions - pick newest by mtime
    SESSION_DIR=$(find "$OSIRIS_LOGS_DIR" -maxdepth 1 -type d -name "run_*" -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2)
    if [ -z "$SESSION_DIR" ]; then
        # Fallback for systems without -printf
        SESSION_DIR=$(ls -dt "$OSIRIS_LOGS_DIR"/run_* 2>/dev/null | head -1)
    fi
    echo "Found $SESSION_COUNT session directories, selected newest: $SESSION_DIR"
fi

echo ""
echo "=== Copying session logs for download ==="
SESSION_COPIED=false
EVENTS_JSONL_EXISTS=false
METRICS_JSONL_EXISTS=false
OSIRIS_LOG_EXISTS=false
EVENTS_JSONL_SIZE=0
METRICS_JSONL_SIZE=0
ARTIFACTS_COUNT=0

if [ -n "$SESSION_DIR" ] && [ -d "$SESSION_DIR" ]; then
    echo "Copying session directory: $SESSION_DIR"

    # Create remote/session directory
    mkdir -p remote/session

    # Copy entire session directory preserving timestamps and permissions
    cp -a "$SESSION_DIR"/* remote/session/ 2>/dev/null || cp -r "$SESSION_DIR"/* remote/session/ 2>/dev/null || true

    # Verify what was copied
    if [ -d "remote/session" ]; then
        SESSION_COPIED=true
        echo "✓ Session directory copied to remote/session/"

        # Check for key files and get sizes
        if [ -f "remote/session/events.jsonl" ]; then
            EVENTS_JSONL_EXISTS=true
            EVENTS_JSONL_SIZE=$(stat -c%s "remote/session/events.jsonl" 2>/dev/null || stat -f%z "remote/session/events.jsonl" 2>/dev/null || echo 0)
            echo "✓ events.jsonl found (${EVENTS_JSONL_SIZE} bytes)"
        else
            echo "⚠️  events.jsonl not found in session"
        fi

        if [ -f "remote/session/metrics.jsonl" ]; then
            METRICS_JSONL_EXISTS=true
            METRICS_JSONL_SIZE=$(stat -c%s "remote/session/metrics.jsonl" 2>/dev/null || stat -f%z "remote/session/metrics.jsonl" 2>/dev/null || echo 0)
            echo "✓ metrics.jsonl found (${METRICS_JSONL_SIZE} bytes)"
        else
            echo "⚠️  metrics.jsonl not found in session"
        fi

        if [ -f "remote/session/osiris.log" ]; then
            OSIRIS_LOG_EXISTS=true
            echo "✓ osiris.log found"
        else
            echo "⚠️  osiris.log not found in session"
        fi

        # Count artifacts and track which steps have them
        STEPS_WITH_ARTIFACTS="[]"
        if [ -d "remote/session/artifacts" ]; then
            ARTIFACTS_COUNT=$(find "remote/session/artifacts" -type f 2>/dev/null | wc -l)
            echo "✓ Found $ARTIFACTS_COUNT artifact files"

            # List step directories that have artifacts
            STEP_DIRS=$(find "remote/session/artifacts" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | xargs -r basename -a | sort)
            if [ -n "$STEP_DIRS" ]; then
                # Convert to JSON array
                STEPS_WITH_ARTIFACTS=$(echo "$STEP_DIRS" | python3 -c "import sys, json; print(json.dumps(sys.stdin.read().strip().split('\\n')))")
                echo "✓ Steps with artifacts: $STEPS_WITH_ARTIFACTS"
            fi
        else
            echo "⚠️  No artifacts directory found"
        fi
    else
        echo "ERROR: Failed to create remote/session directory"
    fi
else
    echo "ERROR: No valid session directory to copy"
fi

echo ""
echo "=== Generating status.json ==="
# Read manifest to get steps_total
STEPS_TOTAL=$(python -c "
import json
try:
    with open('compiled/manifest.yaml', 'r') as f:
        import yaml
        manifest = yaml.safe_load(f)
        print(len(manifest.get('steps', [])))
except Exception:
    print(0)
")

# Count completed steps from stdout
STEPS_COMPLETED=$(grep -cE '^  ✓ .+: Complete' remote/stdout.txt 2>/dev/null || echo 0)

# Classify stderr lines into errors and warnings
ERRORS_COUNT=0
WARNINGS_COUNT=0

if [ -f "remote/stderr.txt" ]; then
    # Count warning patterns first
    WARNINGS_COUNT=$(grep -c "RuntimeWarning\\|DeprecationWarning\\|WARNING:" remote/stderr.txt 2>/dev/null || echo 0)

    # Count error patterns (exclude warnings)
    TOTAL_ERRORS=$(grep -c "Traceback\\|Error\\|Exception" remote/stderr.txt 2>/dev/null || echo 0)
    WARNING_FALSE_POSITIVES=$(grep -c "RuntimeWarning\\|DeprecationWarning" remote/stderr.txt 2>/dev/null || echo 0)
    ERRORS_COUNT=$((TOTAL_ERRORS - WARNING_FALSE_POSITIVES))

    # Ensure non-negative
    if [ $ERRORS_COUNT -lt 0 ]; then
        ERRORS_COUNT=0
    fi
fi

# Determine success status (four-proof validation)
if [ $EXIT_CODE -eq 0 ] && [ $STEPS_COMPLETED -eq $STEPS_TOTAL ] && [ "$SESSION_COPIED" = "true" ] && [ "$EVENTS_JSONL_EXISTS" = "true" ]; then
    STATUS_OK=true
    STATUS_REASON=""
else
    STATUS_OK=false
    if [ $EXIT_CODE -ne 0 ]; then
        STATUS_REASON="non_zero_exit_code"
    elif [ $STEPS_COMPLETED -ne $STEPS_TOTAL ]; then
        STATUS_REASON="incomplete_steps"
    elif [ "$SESSION_COPIED" = "false" ]; then
        STATUS_REASON="session_not_copied"
    elif [ "$EVENTS_JSONL_EXISTS" = "false" ]; then
        STATUS_REASON="missing_events_jsonl"
    else
        STATUS_REASON="unknown"
    fi
fi

# Generate status.json with complete metadata
cat > remote/status.json << EOF
{
  "sandbox_id": "${E2B_SANDBOX_ID:-unknown}",
  "exit_code": $EXIT_CODE,
  "ok": $STATUS_OK,
  "steps_completed": $STEPS_COMPLETED,
  "steps_total": $STEPS_TOTAL,
  "session_path": "${SESSION_DIR#./}",
  "session_copied": $SESSION_COPIED,
  "events_jsonl_exists": $EVENTS_JSONL_EXISTS,
  "metrics_jsonl_exists": $METRICS_JSONL_EXISTS,
  "osiris_log_exists": $OSIRIS_LOG_EXISTS,
  "artifacts_count": $ARTIFACTS_COUNT,
  "steps_with_artifacts": $STEPS_WITH_ARTIFACTS,
  "events_jsonl_size": $EVENTS_JSONL_SIZE,
  "metrics_jsonl_size": $METRICS_JSONL_SIZE,
  "warnings_count": $WARNINGS_COUNT,
  "errors_count": $ERRORS_COUNT,
  "reason": "$STATUS_REASON"
}
EOF

echo "Generated status.json:"
cat remote/status.json

echo ""
echo "=== Execution complete with exit code: $EXIT_CODE ==="
exit $EXIT_CODE
"""

    run_script = staging / "run.sh"
    with open(run_script, "w") as f:
        f.write(script_content)

    # Make executable
    run_script.chmod(0o755)


def _create_requirements(staging: Path) -> None:
    """Create requirements.txt with deterministic Osiris install with extras."""
    requirements = [
        # Install local Osiris package with MySQL extras from current directory
        "-e .[mysql]",
        # Pin critical dependencies for deterministic builds
        "duckdb>=1.1.3",
        "pandas>=2.2.3",
        "pymysql>=1.1.1",
        "sqlalchemy>=2.0.36",
        "supabase>=2.10.0",
        "python-dotenv>=1.0.1",
        "pyyaml>=6.0",
        "rich>=13.0.0",
        "jsonschema>=4.0.0",
    ]

    with open(staging / "requirements.txt", "w") as f:
        f.write("\n".join(requirements))


def get_required_env_vars(prepared: PreparedRun) -> set[str]:
    """Extract required environment variables from manifest connections.

    This function determines the precise set of environment variables needed
    by analyzing the resolved_connections in the PreparedRun, which contains
    the connection configurations with ${ENV_VAR} placeholders.

    Args:
        prepared: PreparedRun with manifest and configuration

    Returns:
        Set of environment variable names needed for execution
    """
    env_vars = set()

    # Extract env vars from resolved connections (most precise approach)
    for _connection_id, connection_config in prepared.resolved_connections.items():
        _extract_env_vars_from_dict(connection_config, env_vars)

    # Also check step configurations for any direct env var references
    for _cfg_path, config in prepared.cfg_index.items():
        _extract_env_vars_from_dict(config, env_vars)

    return env_vars


def _extract_env_vars_from_dict(data: Any, env_vars: set[str]) -> None:
    """Recursively extract environment variable references."""
    if isinstance(data, dict):
        for value in data.values():
            _extract_env_vars_from_dict(value, env_vars)
    elif isinstance(data, list):
        for item in data:
            _extract_env_vars_from_dict(item, env_vars)
    elif isinstance(data, str):
        # Look for ${VAR_NAME} pattern
        import re

        matches = re.findall(r"\$\{([A-Z_][A-Z0-9_]*)\}", data)
        env_vars.update(matches)
