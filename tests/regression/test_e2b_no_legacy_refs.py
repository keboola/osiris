"""Regression test: E2B modules must not contain legacy path references."""

import re
from pathlib import Path

BANNED_PATTERNS = [
    r'\bPath\("logs"\)',  # Path("logs")
    r'"logs/"',  # Hardcoded "logs/" string (but allow in comments/docstrings)
    r"\.last_compile\.json",  # .last_compile.json references
    r"\.osiris_sessions",  # .osiris_sessions references
    r"\bcompiled/",  # compiled/ directory (allow in sandbox context ./compiled/)
]

# Patterns that are OK in specific contexts
ALLOWLIST_PATTERNS = [
    r"# .*logs/",  # Comments
    r'""".*logs/',  # Docstrings
    r"'''.*logs/",  # Docstrings
    r"\.\/compiled/",  # ./compiled/ is OK (sandbox path)
    r'"compiled/manifest\.yaml"',  # Sandbox manifest path is OK
    r"'compiled/manifest\.yaml'",  # Sandbox manifest path (single quotes) is OK
    r"io_layout.*logs/",  # io_layout defines sandbox paths
]


def test_e2b_modules_no_legacy_paths():
    """Test that E2B modules don't contain legacy path literals."""
    e2b_dir = Path(__file__).parent.parent.parent / "osiris" / "remote"
    assert e2b_dir.exists(), f"E2B directory not found: {e2b_dir}"

    e2b_files = list(e2b_dir.glob("e2b_*.py"))
    assert len(e2b_files) > 0, "No E2B files found"

    violations = []

    for filepath in e2b_files:
        with open(filepath) as f:
            content = f.read()
            lines = content.split("\n")

        for line_num, line in enumerate(lines, 1):
            # Skip if line matches allowlist
            if any(re.search(pattern, line) for pattern in ALLOWLIST_PATTERNS):
                continue

            # Check for banned patterns
            for pattern in BANNED_PATTERNS:
                if re.search(pattern, line):
                    violations.append(f"{filepath.name}:{line_num}: {line.strip()}")

    assert len(violations) == 0, (
        f"Found {len(violations)} legacy path reference(s) in E2B modules:\n"
        + "\n".join(violations)
        + "\n\nE2B modules must use FilesystemContract paths or sandbox-relative paths only."
    )


def test_e2b_modules_exist():
    """Verify expected E2B modules exist."""
    e2b_dir = Path(__file__).parent.parent.parent / "osiris" / "remote"

    expected_files = [
        "e2b_transparent_proxy.py",
        "e2b_adapter.py",
        "e2b_full_pack.py",
    ]

    for filename in expected_files:
        filepath = e2b_dir / filename
        assert filepath.exists(), f"Expected E2B module not found: {filepath}"
