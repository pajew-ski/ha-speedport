class LoginException(Exception):
    """The router rejected the password or keeps the login locked."""


class SessionError(PermissionError):
    """The router does not serve the request under the current session."""


class DecryptionKeyError(SessionError):
    """The answer is encrypted with another key than the session's."""


class UnexpectedResponseError(SessionError):
    """The router answered with a page (login page, 404) instead of data."""


class LoginPausedError(PermissionError):
    """No login is attempted until the pause after a lost session is over."""


class NotAvailableError(Exception):
    """The router does not have the requested page or data (HTTP 404)."""
