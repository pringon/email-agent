"""Exceptions for Gmail fetcher module."""


class AuthenticationError(Exception):
    """Raised when Gmail authentication fails."""

    pass


class ScopeMismatchError(AuthenticationError):
    """Raised when token scopes don't match required scopes.

    This typically happens when the code requests different scopes
    than what the existing token was authorized for.
    """

    def __init__(self, required_scopes: list[str], token_scopes: list[str]):
        self.required_scopes = required_scopes
        self.token_scopes = token_scopes
        missing = set(required_scopes) - set(token_scopes)
        super().__init__(
            f"Token scopes mismatch. Missing scopes: {missing}. "
            f"Required: {required_scopes}, Token has: {token_scopes}. "
            "Delete the token file and re-authenticate with correct scopes."
        )


class NonInteractiveAuthError(AuthenticationError):
    """Raised when authentication requires user interaction but running in non-interactive mode."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(
            f"Authentication requires user interaction but GMAIL_NON_INTERACTIVE=1 is set. "
            f"Reason: {reason}. "
            "Either run locally to re-authenticate, or update the stored token."
        )
