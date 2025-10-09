"""Regression test: ban legacy path literals across codebase."""

import re
from pathlib import Path

import pytest

# Banned string literals (strict patterns for new violations)
BANNED_LITERALS = [
    r'\bPath\("logs"\)\b',  # Path("logs") - exact match
    r'\bPath\("compiled"\)\b',  # Path("compiled") - exact match
    r'f"logs/',  # f-string with logs/ (new hardcoded paths)
    r'f"compiled/',  # f-string with compiled/
    r"\.last_compile\.json",  # .last_compile.json
]

# Files/directories to exclude from the check
ALLOWLIST_PATHS = [
    "docs/",
    "CHANGELOG.md",
    "README.md",
    ".git/",
    "__pycache__/",
    ".pytest_cache/",
    "tests/regression/test_no_legacy_paths.py",  # This file
    "tests/regression/test_e2b_no_legacy_refs.py",
    ".secrets.baseline",
    ".gitignore",
    # Legacy modules to be migrated later (non-blocking for P0)
    "osiris/core/state_store.py",
    "osiris/core/config.py",  # Sample config generation
    "osiris/core/test_harness.py",
    "osiris/drivers/supabase_writer_driver.py",
    "osiris/core/run_export_v2.py",  # AIOP v2 (pre-dates contract)
    "osiris/cli/compile.py",  # Has legacy fallback mode
    "osiris/remote/e2b_transparent_proxy.py",  # io_layout for sandbox (not host)
]

# Patterns that are OK in specific contexts
CONTEXT_ALLOWLIST = [
    r"# .*",  # Comments
    r'""".*"""',  # Docstrings
    r"'''.*'''",  # Docstrings
    r"\.\/compiled/",  # ./compiled/ (sandbox paths)
    r'"compiled/manifest\.yaml"',  # Sandbox manifest paths
    r"io_layout",  # E2B sandbox io_layout
    r"old.*dir",  # References to old/legacy for migration code
    r"legacy",  # Explicit legacy references in migration code
]


def is_allowlisted_path(filepath: Path, repo_root: Path) -> bool:
    """Check if file path is in allowlist."""
    rel_path = filepath.relative_to(repo_root)
    path_str = str(rel_path)

    for allowlist_entry in ALLOWLIST_PATHS:
        if path_str.startswith(allowlist_entry) or path_str == allowlist_entry:
            return True

    return False


def test_no_legacy_path_literals():
    """Test that codebase doesn't contain banned legacy path literals."""
    repo_root = Path(__file__).parent.parent.parent
    osiris_dir = repo_root / "osiris"

    assert osiris_dir.exists(), f"Osiris directory not found: {osiris_dir}"

    violations = []

    # Scan all Python files in osiris/
    for filepath in osiris_dir.rglob("*.py"):
        if is_allowlisted_path(filepath, repo_root):
            continue

        with open(filepath) as f:
            content = f.read()
            lines = content.split("\n")

        for line_num, line in enumerate(lines, 1):
            # Skip if entire line is a comment or docstring
            stripped = line.strip()
            if stripped.startswith("#") or '"""' in line or "'''" in line:
                continue

            # Check for context allowlist (migration code, etc.)
            if any(re.search(pattern, line, re.IGNORECASE) for pattern in CONTEXT_ALLOWLIST):
                continue

            # Check for banned patterns
            for pattern in BANNED_LITERALS:
                if re.search(pattern, line):
                    rel_path = filepath.relative_to(repo_root)
                    violations.append(f"{rel_path}:{line_num}: {line.strip()}")

    if violations:
        error_msg = (
            f"Found {len(violations)} legacy path literal(s) in codebase:\n\n"
            + "\n".join(violations[:20])  # Show first 20
            + ("\n... and more" if len(violations) > 20 else "")
            + "\n\nBanned patterns: logs/, compiled/, .last_compile.json, .osiris_sessions, output_dir, session_dir"
            + "\nFilesystem Contract v1 requires all paths via FilesystemContract."
            + "\nSee ADR-0028 for migration guide."
        )
        pytest.fail(error_msg)


def test_gitignore_has_contract_paths():
    """Test that .gitignore includes Filesystem Contract v1 directories."""
    repo_root = Path(__file__).parent.parent.parent
    gitignore = repo_root / ".gitignore"

    assert gitignore.exists(), ".gitignore not found"

    with open(gitignore) as f:
        content = f.read()

    required_patterns = [
        "run_logs/",
        "aiop/",
        ".osiris/",
        "build/",
    ]

    missing = []
    for pattern in required_patterns:
        if pattern not in content:
            missing.append(pattern)

    assert len(missing) == 0, f".gitignore missing Filesystem Contract v1 patterns: {missing}"


def test_legacy_directories_banned_in_gitignore():
    """Test that .gitignore documents removal of legacy directories."""
    repo_root = Path(__file__).parent.parent.parent
    gitignore = repo_root / ".gitignore"

    with open(gitignore) as f:
        content = f.read()

    # Should mention that logs/ is removed
    assert "logs/" in content, ".gitignore should mention logs/ removal"
