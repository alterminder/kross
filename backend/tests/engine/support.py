"""Helpers for engine tests."""

from nlab.engine.state import Classification

QUIET = Classification()
ASKS = Classification(asked_for_goal=True)


def said(*moves: tuple[str, str], asked: bool = False) -> Classification:
    """A classification with (move id, quote) pairs."""
    return Classification.model_validate(
        {"moves": [{"id": move_id, "quote": quote} for move_id, quote in moves], "asked_for_goal": asked}
    )
