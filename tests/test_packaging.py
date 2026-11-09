from __future__ import annotations

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "cardspec"


def test_runtime_imports_only_the_standard_library():
    stdlib = set(sys.stdlib_module_names)
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                assert name in stdlib or name == "cardspec", f"{path.name} imports {name}"


def test_typed_marker_ships():
    assert (SRC / "py.typed").exists()


def test_pointer_to_the_notice_in_derived_modules():
    for name in ("catalogue.py", "validate.py", "prompt.py"):
        head = (SRC / name).read_text().splitlines()[:6]
        assert any("NOTICE" in line for line in head), name


def test_version_is_available():
    import cardspec

    assert isinstance(cardspec.__version__, str)
