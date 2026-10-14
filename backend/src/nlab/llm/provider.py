"""The one interface every model call goes through."""

from collections.abc import AsyncIterator
from typing import Protocol

from pydantic import BaseModel

from nlab.llm.config import RoleConfig
from nlab.llm.types import Completion, Request, Usage


class Provider(Protocol):
    async def complete(
        self, config: RoleConfig, request: Request, schema: type[BaseModel] | None = None, json: bool = False
    ) -> Completion:
        """One answer. With `schema` (or `json=True`) the provider asks for JSON in the best mode the model supports."""
        ...

    def stream(self, config: RoleConfig, request: Request) -> AsyncIterator[str | Usage]:
        """Text chunks as they arrive, then the token usage if the provider reports it."""
        ...
