"""Pytest configuration and shared fixtures."""

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def testing_env_tmp():
    """Provide a testing environment tmp directory that gets cleaned up."""
    project_root = Path(__file__).parent.parent
    testing_tmp = project_root / "testing_env" / "tmp"
    testing_tmp.mkdir(exist_ok=True)

    # Create a unique subdirectory for this test
    with tempfile.TemporaryDirectory(dir=testing_tmp) as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def isolated_osiris_dirs(testing_env_tmp, monkeypatch):
    """Isolate Osiris directories to testing_env/tmp for a test."""
    # Create subdirectories in testing temp
    logs_dir = testing_env_tmp / "logs"
    sessions_dir = testing_env_tmp / ".osiris_sessions"
    prompts_dir = testing_env_tmp / ".osiris_prompts"
    cache_dir = testing_env_tmp / ".osiris_cache"
    output_dir = testing_env_tmp / "output"

    logs_dir.mkdir(exist_ok=True)
    sessions_dir.mkdir(exist_ok=True)
    prompts_dir.mkdir(exist_ok=True)
    cache_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)

    # Change to testing temp directory so relative paths work
    monkeypatch.chdir(testing_env_tmp)

    # Set environment variables that might be used by the code
    monkeypatch.setenv("OSIRIS_LOGS_DIR", str(logs_dir))
    monkeypatch.setenv("OSIRIS_SESSIONS_DIR", str(sessions_dir))
    monkeypatch.setenv("OSIRIS_CACHE_DIR", str(cache_dir))

    yield {
        "logs": logs_dir,
        "sessions": sessions_dir,
        "prompts": prompts_dir,
        "cache": cache_dir,
        "output": output_dir,
        "tmp": testing_env_tmp,
    }

    # Clean up is handled by the tempfile.TemporaryDirectory context manager


@pytest.fixture
def clean_project_root():
    """Clean up any artifacts created in project root after test."""
    project_root = Path(__file__).parent.parent
    original_cwd = os.getcwd()

    # List of directories/files that should be cleaned up
    artifacts = [
        ".osiris_sessions",
        ".osiris_prompts",
        ".osiris_cache",
        "logs",
        "output",
    ]

    # Store what exists before the test
    existing_before = {artifact: (project_root / artifact).exists() for artifact in artifacts}

    yield

    # Clean up any new artifacts created during the test
    for artifact in artifacts:
        path = project_root / artifact
        if path.exists() and not existing_before[artifact]:
            if path.is_dir():
                import shutil

                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)

    # Restore working directory
    os.chdir(original_cwd)
