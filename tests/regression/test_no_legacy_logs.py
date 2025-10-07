"""Regression test: Ensure no legacy logs/ writes (ADR-0028)."""

import ast
from pathlib import Path

import pytest


def find_python_files():
    """Find all Python files in osiris package."""
    root = Path(__file__).parent.parent.parent
    osiris_dir = root / "osiris"

    python_files = []
    for path in osiris_dir.rglob("*.py"):
        # Skip __pycache__ and test files
        if "__pycache__" in str(path) or "test_" in path.name:
            continue
        python_files.append(path)

    return python_files


def check_file_for_legacy_logs(file_path: Path) -> list[str]:
    """Check file for legacy logs/ directory references.

    Returns:
        List of violations found
    """
    violations = []

    with open(file_path) as f:
        content = f.read()

    # Parse AST
    try:
        tree = ast.parse(content, filename=str(file_path))
    except SyntaxError:
        return []  # Skip files with syntax errors

    # Check for string literals containing "logs/"
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value

            # Check for legacy paths
            if any(
                pattern in value
                for pattern in [
                    "logs/",
                    "./logs/",
                    "logs\\",
                    ".\\logs\\",
                ]
            ):
                # Allowlist: Test files and config samples are OK
                if "test" in str(file_path).lower() or "sample" in value.lower():
                    continue

                # Allowlist: Comments and docstrings may mention logs/
                if node.lineno:
                    line = content.split("\n")[node.lineno - 1]
                    if "#" in line or '"""' in line or "'''" in line:
                        continue

                # Allowlist: Contract modules may reference legacy paths for migration
                if any(
                    module in str(file_path)
                    for module in [
                        "fs_config.py",
                        "fs_paths.py",
                        "run_index.py",
                        "retention.py",
                    ]
                ):
                    continue

                violations.append(f"{file_path}:{node.lineno} - Found legacy 'logs/' reference: {value[:50]}")

    return violations


@pytest.mark.regression
def test_no_legacy_logs_writes():
    """Test that no code writes to legacy logs/ directory."""
    python_files = find_python_files()
    all_violations = []

    for file_path in python_files:
        violations = check_file_for_legacy_logs(file_path)
        all_violations.extend(violations)

    if all_violations:
        violation_msg = "\n".join(all_violations)
        pytest.fail(
            f"Found {len(all_violations)} legacy 'logs/' references:\n{violation_msg}\n\n"
            "ADR-0028 requires using FilesystemContract with build/, run_logs/, aiop/ directories."
        )


@pytest.mark.regression
def test_filesystem_contract_available():
    """Test that FilesystemContract is importable."""
    try:
        from osiris.core.fs_config import FilesystemConfig, IdsConfig
        from osiris.core.fs_paths import FilesystemContract

        # Verify classes are usable
        assert FilesystemConfig is not None
        assert IdsConfig is not None
        assert FilesystemContract is not None
    except ImportError as e:
        pytest.fail(f"FilesystemContract not available: {e}")


@pytest.mark.regression
def test_required_directories_in_contract():
    """Test that FilesystemContract defines required directories."""
    from osiris.core.fs_config import FilesystemConfig

    config = FilesystemConfig()

    # Verify new directories are defined
    assert hasattr(config, "build_dir")
    assert hasattr(config, "run_logs_dir")
    assert hasattr(config, "aiop_dir")
    assert hasattr(config, "index_dir")

    # Verify correct default values
    assert config.build_dir == "build"
    assert config.run_logs_dir == "run_logs"
    assert config.aiop_dir == "aiop"
    assert config.index_dir == ".osiris/index"
