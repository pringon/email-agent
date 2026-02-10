# Agentic Email Organizer

An intelligent assistant that processes your Gmail inbox, summarizes messages, extracts tasks, and tracks their completion using Google Tasks. The agent uses OpenAI to understand emails and generate actionable insights, running automatically via a cronjob.

## Features

- Periodically reads Gmail inbox via Gmail API
- Uses OpenAI to summarize and extract tasks from emails
- Creates tasks in Google Tasks with relevant context and deadlines
- Monitors Sent Mail to auto-close tasks when you reply
- Supports user comments to influence task handling
- Sends daily digest of email summaries and pending actions

## Tech Stack

- **Language:** Python 3.10+
- **Email Access:** Gmail API (`google-api-python-client`)
- **AI Integration:** OpenAI GPT-4 via API
- **Task Management:** Google Tasks API
- **Scheduler:** GitHub Actions cron workflows
- **Storage:** Local cache / SQLite (optional)

## Prerequisites

- Python 3.10 or higher
- Google Cloud Project with Gmail and Tasks APIs enabled
- OpenAI API key

## Setup

1. **Clone the repository**
   ```bash
   git clone <repo-url>
   cd email-agent
   ```

2. **Create virtual environment and install dependencies**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Set up Google Cloud credentials**
   - Create a Google Cloud Project
   - Enable Gmail API and Google Tasks API
   - Create OAuth 2.0 credentials (Desktop app)
   - Download the credentials JSON and save as `config/credentials.json`

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your OpenAI API key
   ```

5. **Run the agent**
   ```bash
   python run_agent.py
   python run_agent.py --max-emails 10  # limit emails processed
   ```

## Deployment

The agent runs automatically via GitHub Actions cron workflows - no Docker or separate infrastructure needed.

- **Schedule:** Every 2 hours
- **Manual trigger:** Available via the Actions tab in GitHub (`workflow_dispatch`)
- **Monitoring:** Run history and logs in the GitHub Actions tab; email notifications on failure

Credentials are stored as GitHub Secrets (base64-encoded OAuth tokens and API keys). The same secrets used for CI e2e tests power the scheduled runs. See [docs/scheduler_design.md](docs/scheduler_design.md) for the full design.

## Testing

Run the integration tests to verify your Gmail credentials are working:

```bash
source venv/bin/activate
pytest tests/test_gmail_integration.py -v
```

On first run, a browser window will open for OAuth authorization. After authorizing, a `token.json` file is saved for future use.

## Documentation

- [docs/agentic_email_organizer_spec.md](docs/agentic_email_organizer_spec.md) - Full specification with architecture and project plan
- [docs/scheduler_design.md](docs/scheduler_design.md) - Scheduler and orchestrator design

## Security

- OAuth2 for Gmail and Google Tasks access with minimal scopes
- API credentials stored securely via `.env` and encrypted config
- Email content passed to OpenAI is handled with care to avoid sensitive data exposure
- Logging is minimal and local-only by default

## License

MIT
