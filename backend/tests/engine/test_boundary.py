"""The engine does no I/O: no file, environment, network, database or model access."""

import ast
from pathlib import Path

import pytest

import nlab.engine

FORBIDDEN_MODULES = {
    "os",
    "sys",
    "pathlib",
    "io",
    "shutil",
    "socket",
    "subprocess",
    "urllib",
    "http",
    "asyncio",
    "sqlalchemy",
    "sqlite3",
    "dbm",
    "fastapi",
    "starlette",
    "httpx",
    "requests",
    "openai",
    "yaml",
    "dotenv",
    "nlab.llm",
    "nlab.api",
    "nlab.db",
}
FORBIDDEN_CALLS = {"open", "exec", "eval", "__import__", "input", "print"}
ENGINE = Path(nlab.engine.__file__).parent


def package_of(path: Path) -> str:
    """The package a scanned module resolves its relative imports against."""
    rel = path.relative_to(ENGINE).with_suffix("")
    parts = ["nlab", "engine", *(part for part in rel.parts if part != "__init__")]
    return ".".join(parts if path.name == "__init__.py" else parts[:-1])


def imported_names(source: str, package: str) -> list[str]:
    """Every fully qualified name an import in `source` can pull in, resolved against the module's package."""
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            anchor = package.split(".")[: len(package.split(".")) - (node.level - 1)] if node.level else []
            base = ".".join([*anchor, *([node.module] if node.module else [])])
            if base:
                names.append(base)
            names.extend(f"{base}.{alias.name}" for alias in node.names if base or alias)
    return names


def is_forbidden(name: str) -> bool:
    return any(name == bad or name.startswith(bad + ".") for bad in FORBIDDEN_MODULES)


def test_the_engine_imports_nothing_that_does_io():
    for path in ENGINE.rglob("*.py"):
        for name in imported_names(path.read_text(encoding="utf-8"), package_of(path)):
            assert not is_forbidden(name), f"{path.name} imports {name}"


def test_the_engine_calls_no_io_builtins():
    for path in ENGINE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in FORBIDDEN_CALLS, f"{path.name} calls {node.func.id}()"


@pytest.mark.parametrize(
    "source",
    [
        "from ..llm import x",  # relative import of a forbidden sibling package
        "from nlab import llm",  # forbidden package as an imported member
        "from .. import db",  # forbidden package as a relative member
        "import sqlite3",  # standard-library database access
    ],
)
def test_forbidden_import_spellings_are_caught(source):
    assert any(is_forbidden(name) for name in imported_names(source, "nlab.engine"))


def test_the_public_api_is_complete():
    for name in (
        "start",
        "step",
        "grant",
        "grantable",
        "inject",
        "set_dial",
        "end",
        "is_red_line",
        "validate",
        "Issue",
        "effective_rules",
        "apply_changes",
        "validate_overrides",
        "RuleOverrides",
        "Rules",
        "Rubric",
        "Scenario",
        "State",
        "Step",
        "Event",
        "Cue",
        "Outcome",
        "Offer",
        "Classification",
        "EngineError",
        "ConditionError",
    ):
        assert hasattr(nlab.engine, name), name
