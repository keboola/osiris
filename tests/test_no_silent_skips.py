"""No test may be disabled at import time.

v0.5.4 shipped a runtime that could not execute anything because the
integration tests that would have caught it carried
`pytestmark = pytest.mark.skip(reason="...")` — a plausible-sounding reason
that silenced the only real check. Skips belong on individual tests with a
runtime condition, never on a whole module or class.

This guard parses the AST rather than matching a regex. The regex it replaced
required one exact spelling and was evaded by three ordinary idioms, each of
which hid a test asserting ``False`` while the suite reported ``passed``:

    pytestmark = [pytest.mark.skip(...)]   # the standard list idiom
    @pytest.mark.skip                      # applied to a Test* class
    import pytest as pt; pt.mark.skip      # an aliased import

An AST cannot be fooled by any of them: aliases are resolved back to the
module they were bound from, and a mark is recognised by its shape, not by
its source text. Formatting, line breaks and indentation are irrelevant.
"""

import ast
import pathlib

# Anything that disables tests wholesale at import time.
BANNED = {"pytest.mark.skip", "pytest.skip"}


def _alias_map(tree: ast.Module) -> dict[str, str]:
    """Map every local name back to the pytest attribute path it was bound from.

    ``import pytest as pt`` yields ``{"pt": "pytest"}``; ``from pytest import
    mark as m`` yields ``{"m": "pytest.mark"}``. Names bound to anything other
    than pytest are not recorded, so an unrelated ``skip`` helper is not
    mistaken for the marker.
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "pytest" or alias.name.startswith("pytest."):
                    aliases[alias.asname or alias.name.split(".")[0]] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "pytest":
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def _dotted(node: ast.AST, aliases: dict[str, str]) -> str | None:
    """Canonical dotted path of an attribute chain, with the head de-aliased."""
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    head = aliases.get(current.id)
    if head is None:
        return None
    parts.append(head)
    return ".".join(reversed(parts))


def _is_banned(node: ast.AST, aliases: dict[str, str]) -> bool:
    """True when the expression is a skip marker or a skip call, called or bare."""
    target = node.func if isinstance(node, ast.Call) else node
    return _dotted(target, aliases) in BANNED


def _marks_in(value: ast.AST) -> list[ast.AST]:
    """A pytestmark value, flattened: bare marker, list of markers, or tuple."""
    if isinstance(value, ast.List | ast.Tuple):
        return list(value.elts)
    return [value]


def _offences(tree: ast.Module, aliases: dict[str, str]) -> list[str]:
    found: list[str] = []

    def check_assignments(body: list[ast.stmt], where: str) -> None:
        """`pytestmark = ...` silences every test in its scope."""
        for stmt in body:
            targets: list[ast.expr] = []
            if isinstance(stmt, ast.Assign):
                targets = list(stmt.targets)
            elif isinstance(stmt, ast.AnnAssign):
                targets = [stmt.target]
            if not any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in targets):
                continue
            if stmt.value is None:
                continue
            for mark in _marks_in(stmt.value):
                if _is_banned(mark, aliases):
                    found.append(f"line {stmt.lineno}: pytestmark skip in {where}")

    def walk(body: list[ast.stmt], where: str) -> None:
        """Recurse over import-time code only; never descend into a function body.

        A skip inside a test function is a runtime decision, which is the
        allowed form. Everything reachable at import time is not.
        """
        for stmt in body:
            if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if isinstance(stmt, ast.ClassDef):
                for decorator in stmt.decorator_list:
                    if _is_banned(decorator, aliases):
                        found.append(f"line {decorator.lineno}: skip marker on class {stmt.name}")
                check_assignments(stmt.body, f"class {stmt.name}")
                walk(stmt.body, f"class {stmt.name}")
                continue
            if isinstance(stmt, ast.Expr) and _is_banned(stmt.value, aliases):
                found.append(f"line {stmt.lineno}: import-time pytest.skip() in {where}")
            # if/try/with/for wrappers still execute at import time, so their
            # bodies — including except handlers — count as import-time code.
            nested: list[ast.stmt] = []
            for child in ast.iter_child_nodes(stmt):
                if isinstance(child, ast.stmt):
                    nested.append(child)
                elif isinstance(child, ast.ExceptHandler):
                    nested.extend(child.body)
            if nested:
                check_assignments(nested, where)
                walk(nested, where)

    check_assignments(tree.body, "module")
    walk(tree.body, "module")
    return found


def test_no_import_time_skips():
    root = pathlib.Path(__file__).resolve().parent
    offenders: dict[str, list[str]] = {}
    for path in sorted([*root.rglob("test_*.py"), *root.rglob("conftest.py")]):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        hits = _offences(tree, _alias_map(tree))
        if hits:
            offenders[str(path.relative_to(root))] = hits
    assert offenders == {}, f"import-time skips are forbidden: {offenders}"


def test_guard_catches_every_known_evasion():
    """The regex this guard replaced passed all but the first of these. It must not."""
    canonical = 'import pytest\npytestmark = pytest.mark.skip(reason="x")\n'
    as_list = 'import pytest\npytestmark = [pytest.mark.skip(reason="x")]\n'
    on_class = "import pytest\n\n\n@pytest.mark.skip\nclass TestThing:\n    def test_a(self):\n        assert False\n"
    aliased = 'import pytest as pt\npytestmark = pt.mark.skip(reason="x")\n'
    module_call = 'import pytest\npytest.skip("x", allow_module_level=True)\n'
    from_import = 'from pytest import mark\npytestmark = mark.skip(reason="x")\n'

    for source in (canonical, as_list, on_class, aliased, module_call, from_import):
        tree = ast.parse(source)
        assert _offences(tree, _alias_map(tree)), f"evasion not caught:\n{source}"


def test_guard_allows_runtime_skips_inside_tests():
    """A skip with a runtime condition, inside a test, is the sanctioned form."""
    source = (
        "import pytest\n"
        "\n"
        "def test_needs_server():\n"
        '    if not have_server():\n        pytest.skip("no server")\n'
        "    assert True\n"
    )
    tree = ast.parse(source)
    assert _offences(tree, _alias_map(tree)) == []
