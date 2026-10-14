"""The LLM layer never reads the environment or files, and only one module talks to the SDK."""

import ast
from pathlib import Path

import nlab.llm

LLM = Path(nlab.llm.__file__).parent
FORBIDDEN = {"os", "sys", "pathlib", "io", "dotenv", "subprocess", "sqlalchemy", "fastapi", "nlab.api", "nlab.db"}


def imports(path: Path) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_no_environment_or_file_access():
    for path in LLM.rglob("*.py"):
        for name in imports(path):
            assert not any(name == bad or name.startswith(bad + ".") for bad in FORBIDDEN), (
                f"{path.name} imports {name}"
            )
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"open", "__import__", "print"}, f"{path.name} calls {node.func.id}()"


def test_only_the_provider_imports_the_sdk():
    users = {
        path.name for path in LLM.rglob("*.py") if any(n == "openai" or n.startswith("openai.") for n in imports(path))
    }
    assert users == {"openai_compat.py"}


def test_the_engine_does_not_import_the_llm_layer():
    engine = LLM.parent / "engine"
    for path in engine.rglob("*.py"):
        assert not any(name.startswith("nlab.llm") for name in imports(path)), path.name


def test_the_public_api_is_complete():
    for name in (
        "LLMConfig",
        "RoleConfig",
        "Provider",
        "OpenAICompatibleProvider",
        "Line",
        "Request",
        "CallRecord",
        "Result",
        "MalformedAnswer",
        "NoAnswer",
        "classify",
        "evaluate",
        "grant_check",
        "debrief",
        "counterpart_request",
        "CounterpartStream",
        "render_cue",
        "convert_brief",
        "convert_upload",
        "Conversion",
        "TurnScores",
        "Evaluation",
        "Debrief",
    ):
        assert hasattr(nlab.llm, name), name
