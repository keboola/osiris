"""Pytest configuration and shared fixtures."""

import importlib
import os
import tempfile
from pathlib import Path

import pytest

# IMPORTANT: Set offline mode BEFORE any test imports driver module
# This is the earliest point where we can set env vars
os.environ.setdefault("OSIRIS_TEST_SUPABASE_OFFLINE", "1")
os.environ.setdefault("RETRY_MAX_ATTEMPTS", "1")
os.environ.setdefault("RETRY_BASE_SLEEP", "0")


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


@pytest.fixture(autouse=True, scope="function")
def supabase_test_guard(request, monkeypatch):
    """
    Unified autouse fixture for all Supabase test setup.

    This fixture:
    1. Sets OSIRIS_TEST_SUPABASE_OFFLINE=1 to prevent network calls
    2. Clamps retries and timeouts for fast tests
    3. For Supabase tests: Reloads supabase_writer_driver module to honor env changes
    4. For Supabase tests: Calls _reset_test_state() to clear any module-level state
    5. For Supabase tests: Patches time.sleep in supabase_writer_driver to prevent delays

    Applied to ALL tests to ensure no accidental network calls.
    Tests can override OSIRIS_TEST_SUPABASE_FORCE_REAL_CLIENT=1 for MagicMock testing.
    """
    # Set env BEFORE any driver imports - this is the safety net
    monkeypatch.setenv("OSIRIS_TEST_SUPABASE_OFFLINE", "1")
    monkeypatch.setenv("RETRY_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("RETRY_BASE_SLEEP", "0")
    monkeypatch.setenv("SUPABASE_HTTP_TIMEOUT_S", "0.2")

    # Check if this is a Supabase test (has the supabase marker)
    is_supabase_test = request.node.get_closest_marker("supabase") is not None

    # Only reload/patch for Supabase tests to avoid cross-contamination
    if is_supabase_test:
        try:
            import osiris.drivers.supabase_writer_driver as swd_module

            importlib.reload(swd_module)
            # Call reset hook to clear any module state
            if hasattr(swd_module, "_reset_test_state"):
                swd_module._reset_test_state()
            # Patch time.sleep only in the driver module to prevent delays
            monkeypatch.setattr("osiris.drivers.supabase_writer_driver.time.sleep", lambda *_a, **_kw: None)
        except ImportError:
            # Module not yet loaded, that's fine
            pass

    yield

    # Cleanup after test (only for Supabase tests)
    if is_supabase_test:
        try:
            import osiris.drivers.supabase_writer_driver as swd_module

            if hasattr(swd_module, "_reset_test_state"):
                swd_module._reset_test_state()
        except ImportError:
            pass
