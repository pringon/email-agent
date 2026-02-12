"""Gmail API authentication helper."""

import os
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

from .exceptions import NonInteractiveAuthError, ScopeMismatchError

# Default Gmail API scopes
DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",  # For marking as read
]


class GmailAuthenticator:
    """Handles Gmail API authentication with token refresh.

    Supports configurable paths for credentials and token files,
    lazy service creation, and non-interactive mode for CI environments.
    """

    def __init__(
        self,
        credentials_path: Optional[Path] = None,
        token_path: Optional[Path] = None,
        scopes: Optional[list[str]] = None,
        interactive: bool = True,
    ):
        """Initialize the authenticator.

        Args:
            credentials_path: Path to OAuth credentials JSON file.
                Defaults to GMAIL_CREDENTIALS_PATH env var, or config/credentials.json.
            token_path: Path to store/load access token.
                Defaults to GMAIL_TOKEN_PATH env var, or config/token.json.
            scopes: List of Gmail API scopes to request.
                Defaults to readonly and modify scopes.
            interactive: If False, raise an error instead of opening browser for OAuth.
                Also checks GMAIL_NON_INTERACTIVE env var. Defaults to True.
        """
        project_root = Path(__file__).parent.parent.parent

        # Support environment variables for credential paths
        if credentials_path:
            self._credentials_path = credentials_path
        elif os.environ.get("GMAIL_CREDENTIALS_PATH"):
            self._credentials_path = Path(os.environ["GMAIL_CREDENTIALS_PATH"])
        else:
            self._credentials_path = project_root / "config" / "credentials.json"

        if token_path:
            self._token_path = token_path
        elif os.environ.get("GMAIL_TOKEN_PATH"):
            self._token_path = Path(os.environ["GMAIL_TOKEN_PATH"])
        else:
            self._token_path = project_root / "config" / "token.json"

        self._scopes = scopes or DEFAULT_SCOPES
        self._service: Optional[Resource] = None
        self._credentials: Optional[Credentials] = None

        # Non-interactive mode: check both parameter and env var
        self._interactive = interactive and not os.environ.get("GMAIL_NON_INTERACTIVE")

    def _validate_token_scopes(self, creds: Credentials) -> bool:
        """Check if token has all required scopes.

        Uses granted_scopes (the scopes actually stored in the token file)
        rather than scopes (the requested scopes passed at load time),
        so that mismatches between the token and the requested scopes are
        properly detected.

        Args:
            creds: Credentials object to validate

        Returns:
            True if token has all required scopes, False otherwise
        """
        granted = creds.granted_scopes or creds.scopes
        if not granted:
            return False
        return all(scope in granted for scope in self._scopes)

    def _load_or_refresh_credentials(self) -> Credentials:
        """Load existing credentials or create new ones.

        Returns:
            Valid credentials object

        Raises:
            FileNotFoundError: If credentials.json doesn't exist
            ScopeMismatchError: If token scopes don't match and non-interactive
            NonInteractiveAuthError: If re-auth needed but in non-interactive mode
        """
        creds = None

        # Load existing token if available
        if self._token_path.exists():
            creds = Credentials.from_authorized_user_file(
                str(self._token_path), self._scopes
            )

            # Validate scopes match what we need
            if creds and not self._validate_token_scopes(creds):
                if not self._interactive:
                    raise ScopeMismatchError(
                        required_scopes=self._scopes,
                        token_scopes=list(creds.scopes) if creds.scopes else [],
                    )
                # In interactive mode, delete token and re-auth
                self._token_path.unlink()
                creds = None

        # Refresh or create new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Need to run OAuth flow
                if not self._interactive:
                    reason = "No valid token exists" if not creds else "Token expired without refresh token"
                    raise NonInteractiveAuthError(reason)

                if not self._credentials_path.exists():
                    raise FileNotFoundError(
                        f"Credentials file not found at {self._credentials_path}. "
                        "Please download OAuth credentials from Google Cloud Console."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self._credentials_path), self._scopes
                )
                creds = flow.run_local_server(port=0)

            # Save token for future runs
            self._token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._token_path, "w") as token_file:
                token_file.write(creds.to_json())

        return creds

    def get_service(self) -> Resource:
        """Get or create Gmail API service.

        Creates the service lazily on first call and caches it.

        Returns:
            Gmail API service resource
        """
        if self._service is None:
            self._credentials = self._load_or_refresh_credentials()
            self._service = build("gmail", "v1", credentials=self._credentials)
        return self._service

    @property
    def credentials(self) -> Optional[Credentials]:
        """Access the current credentials (after service creation)."""
        return self._credentials
