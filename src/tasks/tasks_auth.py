"""Google Tasks API authentication helper."""

import os
from pathlib import Path
from typing import Optional

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

from .exceptions import TasksAuthError

# Default Google Tasks API scope
DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/tasks",  # Full access to tasks
]


class TasksAuthenticator:
    """Handles Google Tasks API authentication with token refresh.

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
                Defaults to TASKS_CREDENTIALS_PATH env var, or config/credentials.json.
            token_path: Path to store/load access token.
                Defaults to TASKS_TOKEN_PATH env var, or config/tasks_token.json.
            scopes: List of Tasks API scopes to request.
                Defaults to full tasks access.
            interactive: If False, raise an error instead of opening browser for OAuth.
                Also checks TASKS_NON_INTERACTIVE env var. Defaults to True.
        """
        project_root = Path(__file__).parent.parent.parent

        # Support environment variables for credential paths
        if credentials_path:
            self._credentials_path = credentials_path
        elif os.environ.get("TASKS_CREDENTIALS_PATH"):
            self._credentials_path = Path(os.environ["TASKS_CREDENTIALS_PATH"])
        else:
            # Share credentials file with Gmail by default
            self._credentials_path = project_root / "config" / "credentials.json"

        if token_path:
            self._token_path = token_path
        elif os.environ.get("TASKS_TOKEN_PATH"):
            self._token_path = Path(os.environ["TASKS_TOKEN_PATH"])
        else:
            # Separate token file for Tasks API
            self._token_path = project_root / "config" / "tasks_token.json"

        self._scopes = scopes or DEFAULT_SCOPES
        self._service: Optional[Resource] = None
        self._credentials: Optional[Credentials] = None

        # Non-interactive mode: check both parameter and env var
        self._interactive = interactive and not os.environ.get("TASKS_NON_INTERACTIVE")

    def _validate_token_scopes(self, creds: Credentials) -> bool:
        """Check if token has all required scopes.

        Args:
            creds: Credentials object to validate

        Returns:
            True if token has all required scopes, False otherwise
        """
        if not creds.scopes:
            return False
        return all(scope in creds.scopes for scope in self._scopes)

    def _load_or_refresh_credentials(self) -> Credentials:
        """Load existing credentials or create new ones.

        Returns:
            Valid credentials object

        Raises:
            FileNotFoundError: If credentials.json doesn't exist
            TasksAuthError: If re-auth needed but in non-interactive mode
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
                    required = self._scopes
                    token_scopes = list(creds.scopes) if creds.scopes else []
                    raise TasksAuthError(
                        f"Token scopes mismatch. Required: {required}, Token has: {token_scopes}. "
                        "Delete the token file and re-authenticate with correct scopes."
                    )
                # In interactive mode, delete token and re-auth
                self._token_path.unlink()
                creds = None

        # Refresh or create new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except RefreshError as e:
                    if not self._interactive:
                        raise TasksAuthError(
                            f"Token refresh failed: {e}. "
                            "Re-authenticate locally and update the stored token."
                        ) from e
                    # In interactive mode, fall through to re-auth
                    creds = None
            if not creds or not creds.valid:
                # Need to run OAuth flow
                if not self._interactive:
                    reason = "No valid token exists" if not creds else "Token expired without refresh token"
                    raise TasksAuthError(
                        f"Authentication requires user interaction but TASKS_NON_INTERACTIVE=1 is set. "
                        f"Reason: {reason}. "
                        "Either run locally to re-authenticate, or update the stored token."
                    )

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
        """Get or create Google Tasks API service.

        Creates the service lazily on first call and caches it.

        Returns:
            Google Tasks API service resource
        """
        if self._service is None:
            self._credentials = self._load_or_refresh_credentials()
            self._service = build("tasks", "v1", credentials=self._credentials)
        return self._service

    @property
    def credentials(self) -> Optional[Credentials]:
        """Access the current credentials (after service creation)."""
        return self._credentials
