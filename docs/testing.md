# Testing Guide

This guide covers setting up and running tests for the Email Agent, including E2E tests that require Gmail API access.

## Test Types

- **Unit tests**: Test individual components with mocked dependencies
- **Integration tests**: Test Gmail API connectivity (`test_gmail_integration.py`)
- **E2E tests**: Full pipeline tests with real Gmail and OpenAI (`test_email_task_e2e.py`)

## Running Tests

```bash
# Run all tests
python -m pytest -v

# Run unit tests only (fast, no external dependencies)
python -m pytest tests/test_email_fetcher.py tests/test_email_analyzer.py -v

# Run integration tests (requires Gmail credentials)
python -m pytest tests/test_gmail_integration.py -v

# Run E2E tests (requires Gmail + OpenAI)
python -m pytest tests/test_email_task_e2e.py -v -s
```

## Setting Up a Test Gmail Account

For E2E testing, we recommend using a dedicated Gmail account to avoid issues with personal email credentials.

### 1. Create a Test Gmail Account

1. Create a new Gmail account (e.g., `your-project-test@gmail.com`)
2. Send a few test emails to this account so there's content to analyze

### 2. Set Up Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or use an existing one
3. Enable the Gmail API:
   - Navigate to "APIs & Services" > "Library"
   - Search for "Gmail API" and enable it
4. Configure OAuth consent screen:
   - Go to "APIs & Services" > "OAuth consent screen"
   - Choose "External" user type
   - Fill in the app name and your email
   - Add scopes: `gmail.readonly` and `gmail.modify`
   - Add your test Gmail account as a test user
5. Create OAuth credentials:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - Choose "Desktop app"
   - Download the JSON file

### 3. Generate OAuth Token

1. Place the downloaded credentials file at `config/credentials.json`
2. Run the tests locally once:
   ```bash
   python -m pytest tests/test_gmail_integration.py -v
   ```
3. A browser window will open - sign in with your test Gmail account
4. After authorization, a `config/token.json` file will be created

### 4. Publish the OAuth App (Optional but Recommended)

By default, Google Cloud projects in "testing" mode expire OAuth refresh tokens after 7 days. To avoid this:

1. Go to "APIs & Services" > "OAuth consent screen"
2. Click "Publish App"
3. For internal use only, no Google review is required

## Environment Variables

The Gmail authenticator supports configuration via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `GMAIL_CREDENTIALS_PATH` | Path to OAuth credentials.json | `config/credentials.json` |
| `GMAIL_TOKEN_PATH` | Path to OAuth token.json | `config/token.json` |
| `GMAIL_NON_INTERACTIVE` | Set to `1` to fail if re-auth needed | Not set (interactive) |
| `OPENAI_API_KEY` | OpenAI API key for LLM analysis | Required for E2E tests |

## CI/CD Setup (GitHub Actions)

### 1. Encode Credentials as Secrets

```bash
# Encode credentials.json
base64 -i config/credentials.json | pbcopy  # macOS
# Paste as GMAIL_TEST_CREDENTIALS secret

# Encode token.json
base64 -i config/token.json | pbcopy  # macOS
# Paste as GMAIL_TEST_TOKEN secret
```

### 2. GitHub Actions Workflow

```yaml
name: E2E Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Setup Gmail test credentials
        run: |
          mkdir -p config
          echo "${{ secrets.GMAIL_TEST_CREDENTIALS }}" | base64 -d > config/credentials.json
          echo "${{ secrets.GMAIL_TEST_TOKEN }}" | base64 -d > config/token.json

      - name: Run E2E tests
        env:
          GMAIL_NON_INTERACTIVE: "1"
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: python -m pytest tests/test_email_task_e2e.py -v
```

## Troubleshooting

### Scope Mismatch Error

If you see `ScopeMismatchError`, the existing token was created with different scopes than required:

```
Token scopes mismatch. Missing scopes: {...}
```

**Fix**: Delete `config/token.json` and re-authenticate:
```bash
rm config/token.json
python -m pytest tests/test_gmail_integration.py -v
```

### Non-Interactive Auth Error

If running in CI and you see `NonInteractiveAuthError`:

```
Authentication requires user interaction but GMAIL_NON_INTERACTIVE=1 is set.
```

**Fix**: The stored token is invalid or expired. Regenerate locally:
1. Run tests locally to generate a fresh token
2. Update the `GMAIL_TEST_TOKEN` secret with the new base64-encoded token

### Token Expires After 7 Days

Google Cloud projects in "testing" mode expire refresh tokens after 7 days.

**Fix**: Publish your OAuth app (see "Publish the OAuth App" section above) or set up a scheduled job to refresh the token before it expires.
