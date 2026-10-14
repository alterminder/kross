"""Errors the database functions raise; the API maps them to status codes. Messages are safe to show to users."""


class NotFound(Exception):
    """Nothing the caller may see matches. Also used for rows of other orgs, so their existence never leaks."""


class Forbidden(Exception):
    """The caller may see it but not do this."""


class Conflict(Exception):
    """The request breaks a rule, for example removing an org's last admin."""


class Gone(Exception):
    """The thing existed but can no longer be used, for example an expired invite."""


class LimitReached(Exception):
    """A daily limit or the deployment's spend ceiling was reached; nothing was sent to a model."""
