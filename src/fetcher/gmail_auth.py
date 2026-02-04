"""Gmail API authentication helper."""

from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

# Default Gmail API scopes
DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",  # For marking as read
]


class GmailAuthenticator:
    """Handles Gmail API authentication with token refresh.

    Supports configurable paths for credentials and token files,
    and lazy service creation.
    """

    def __init__(
        self,
        credentials_path: Optional[Path] = None,
        token_path: Optional[Path] = None,
        scopes: Optional[list[str]] = None,
    ):
        """Initialize the authenticator.

        Args:
            credentials_path: Path to OAuth credentials JSON file.
                Defaults to config/credentials.json relative to project root.
            token_path: Path to store/load access token.
                Defaults to config/token.json relative to project root.
            scopes: List of Gmail API scopes to request.
                Defaults to readonly and modify scopes.
        """
        project_root = Path(__file__).parent.parent.parent
        self._credentials_path = credentials_path or project_root / "config" / "credentials.json"
        self._token_path = token_path or project_root / "config" / "token.json"
        self._scopes = scopes or DEFAULT_SCOPES
        self._service: Optional[Resource] = None
        self._credentials: Optional[Credentials] = None

    def _load_or_refresh_credentials(self) -> Credentials:
        """Load existing credentials or create new ones.

        Returns:
            Valid credentials object

        Raises:
            FileNotFoundError: If credentials.json doesn't exist
        """
        creds = None

        # Load existing token if available
        if self._token_path.exists():
            creds = Credentials.from_authorized_user_file(
                str(self._token_path), self._scopes
            )

        # Refresh or create new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
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
