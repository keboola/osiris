"""No test may be disabled at module level.

v0.5.4 shipped a runtime that could not execute anything because the
integration tests that would have caught it carried
`pytestmark = pytest.mark.skip(reason="...")` — a plausible-sounding reason
that silenced the only real check. Skips belong on individual tests with a
runtime condition, never on a whole module.
"""

import pathlib
import re

MODULE_SKIP = re.compile(r"^pytestmark\s*=\s*pytest\.mark\.skip|^pytest\.skip\(", re.MULTILINE)


def test_no_module_level_skips():
    root = pathlib.Path(__file__).resolve().parent
    offenders = [
        str(path.relative_to(root))
        for path in root.rglob("test_*.py")
        if MODULE_SKIP.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"module-level skips are forbidden: {offenders}"
