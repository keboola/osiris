"""The package must import cleanly and expose a version."""


def test_package_imports_and_has_version():
    import osiris

    assert osiris.__version__.startswith("0.6.0")


def test_no_deleted_packages_remain():
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent / "osiris"
    for gone in ("drivers", "connectors", "remote", "mcp", "runtime", "core", "cli"):
        assert not (root / gone).exists(), f"osiris/{gone}/ must be deleted"


def test_new_subpackages_exist():
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent / "osiris"
    for pkg in ("determinism", "fsc", "evidence", "cfng", "plan", "run", "relay"):
        assert (root / pkg / "__init__.py").exists(), f"osiris/{pkg}/__init__.py missing"
