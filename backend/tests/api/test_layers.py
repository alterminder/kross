"""nlab.db knows nothing about HTTP; the engine and LLM layer know nothing about either."""

import ast
from pathlib import Path

import nlab

SRC = Path(nlab.__file__).parent


def imports(path: Path) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_the_database_layer_knows_nothing_about_http():
    forbidden = ("fastapi", "starlette", "authlib", "httpx", "nlab.api")
    for path in (SRC / "db").rglob("*.py"):
        for name in imports(path):
            assert not name.startswith(forbidden), f"{path.name} imports {name}"


def test_the_engine_and_llm_layer_know_nothing_about_the_app():
    for package in ("engine", "llm"):
        for path in (SRC / package).rglob("*.py"):
            for name in imports(path):
                assert not name.startswith(("nlab.api", "nlab.db", "sqlalchemy")), f"{path.name} imports {name}"
