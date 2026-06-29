"""Guard test: the package imports its own modules relatively."""

import ast
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent  # recorder/


def _package_modules() -> list[Path]:
    """Every .py module inside the package, excluding the test suite."""
    return [p for p in _PACKAGE_ROOT.rglob("*.py") if "tests" not in p.parts]


def test_package_should_import_its_own_modules_relatively() -> None:
    """No module under recorder/ imports the package absolutely.

    Walk every package module's AST and assert it never does ``from recorder...``
    or ``import recorder...``; within the package, siblings must be imported
    relatively so the package stays relocatable. External consumers (tests,
    scripts) still import ``recorder`` absolutely. Guards the house import rule
    that neither ruff nor pyright can enforce.
    """
    offenders: list[str] = []
    for module in _package_modules():
        tree = ast.parse(module.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                absolute_self = node.level == 0 and (
                    node.module or ""
                ).startswith("recorder")
                if absolute_self:
                    offenders.append(f"{module}: from {node.module} import ...")
            elif isinstance(node, ast.Import):
                offenders.extend(
                    f"{module}: import {alias.name}"
                    for alias in node.names
                    if alias.name.startswith("recorder")
                )

    assert not offenders, "absolute self-imports found:\n" + "\n".join(offenders)
