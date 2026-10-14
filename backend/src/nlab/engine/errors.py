class EngineError(ValueError):
    """A request the engine refuses: the session is over, the message is empty, an unknown twist or dial, a bad rule
    edit. The message is safe to show to the user."""
