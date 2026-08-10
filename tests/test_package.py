"""The package must import cleanly, expose a version, and reference nothing deleted."""

import ast
import importlib.util
import pathlib
import subprocess  # nosec B404 - fixed argv, no shell, repo-local

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Imports that need not resolve in the runtime environment. Every entry is a
# hole in the check below, so each one carries its justification and nothing is
# added without one.
#
#   setuptools — named only by setup.py, a PEP 517 shim. pip installs it from
#   [build-system].requires into an isolated build environment; it is not a
#   runtime dependency and is deliberately absent from .venv.
OPTIONAL_IMPORTS: frozenset[str] = frozenset({"setuptools"})


def test_package_imports_and_has_version():
    import osiris

    assert osiris.__version__.startswith("0.6.0")


def test_no_deleted_packages_remain():
    root = REPO_ROOT / "osiris"
    for gone in ("drivers", "connectors", "remote", "mcp", "runtime", "core", "cli"):
        assert not (root / gone).exists(), f"osiris/{gone}/ must be deleted"


def test_new_subpackages_exist():
    root = REPO_ROOT / "osiris"
    for pkg in ("determinism", "fsc", "evidence", "cfng", "plan", "run", "relay"):
        assert (root / pkg / "__init__.py").exists(), f"osiris/{pkg}/__init__.py missing"


def _tracked_python_files() -> list[pathlib.Path]:
    """Every .py file in the working tree outside tests/, ignored files excluded.

    `--cached` is the set that ships and that a reviewer sees; `--others
    --exclude-standard` adds files staged for a commit that has not happened
    yet, so a newly added script is checked before it can be merged rather than
    after. Falling back to a walk keeps the test honest inside an sdist, where
    there is no git metadata.
    """
    try:
        out = subprocess.run(  # nosec B603 - fixed argv, no shell
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "*.py"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
            text=True,
        ).stdout
        names = [n for n in out.split("\0") if n]
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover - no git available
        skip = {".venv", "venv", "build", "dist", "__pycache__", ".git", "testing_env"}
        names = [
            str(p.relative_to(REPO_ROOT))
            for p in REPO_ROOT.rglob("*.py")
            if not skip.intersection(p.relative_to(REPO_ROOT).parts)
        ]
    return [REPO_ROOT / n for n in names if not n.startswith("tests/")]


def _imported_modules(tree: ast.Module, module_parts: list[str]) -> set[str]:
    """Absolute dotted module names named by a file's imports.

    Imports guarded by ``try: ... except ImportError`` are excluded: they are
    declared optional by construction. Relative imports are resolved against
    the importing file's own package.
    """
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        handles_import_error = any(
            isinstance(h.type, ast.Name) and h.type.id in {"ImportError", "ModuleNotFoundError", "Exception"}
            for h in node.handlers
        )
        if handles_import_error:
            for stmt in node.body:
                for inner in ast.walk(stmt):
                    guarded.add(id(inner))

    modules: set[str] = set()
    for node in ast.walk(tree):
        if id(node) in guarded:
            continue
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = module_parts[: len(module_parts) - node.level + 1]
                modules.add(".".join([*base, node.module] if node.module else base))
            elif node.module:
                modules.add(node.module)
    return modules


def _resolves(module: str) -> bool:
    """True when `module` exists, without executing it.

    First-party modules are resolved on disk so that no `osiris.*` package
    __init__ runs. Third-party and stdlib names are resolved through the import
    machinery at their top level, which finds a spec without executing it.
    """
    parts = module.split(".")
    if parts[0] == "osiris":
        candidate = REPO_ROOT.joinpath(*parts)
        return candidate.with_suffix(".py").is_file() or (candidate / "__init__.py").is_file()
    try:
        return importlib.util.find_spec(parts[0]) is not None
    except (ImportError, ValueError):
        return False


def test_no_file_imports_a_module_that_does_not_exist():
    """Every import in tracked, non-test code must resolve.

    `test_no_deleted_packages_remain` only asserts that directories are gone
    under `osiris/`, so five tracked files under `scripts/` kept importing
    `osiris.core.*` and `osiris.connectors.*` long after those packages were
    deleted — each one a guaranteed `ModuleNotFoundError`, each one invisible
    to the suite, ruff, black and bandit alike.

    Files are parsed, never executed: running a script to discover its imports
    would run whatever else it does.
    """
    broken: dict[str, list[str]] = {}
    for path in _tracked_python_files():
        relative = path.relative_to(REPO_ROOT)
        if not path.is_file():  # pragma: no cover - staged deletion not yet on disk
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        module_parts = list(relative.with_suffix("").parts)
        missing = sorted(
            module
            for module in _imported_modules(tree, module_parts)
            if module not in OPTIONAL_IMPORTS and not _resolves(module)
        )
        if missing:
            broken[str(relative)] = missing
    assert broken == {}, f"imports that cannot resolve: {broken}"
