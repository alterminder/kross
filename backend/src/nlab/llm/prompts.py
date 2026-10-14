"""Prompt texts, loaded once from the bundled prompts.toml."""

import tomllib
from functools import cache
from importlib.resources import files


@cache
def _prompts() -> dict[str, str]:
    return tomllib.loads(files("nlab.llm").joinpath("prompts.toml").read_text(encoding="utf-8"))


def prompt(name: str, **values: str) -> str:
    """The named prompt; placeholders are filled only when values are given (some prompts contain literal braces)."""
    text = _prompts()[name]
    return text.format(**values) if values else text
